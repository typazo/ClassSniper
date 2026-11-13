"""Tests for Ithaca + Virtual location filtering, DB backfill migration, and watch scoping."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from app.db import Database
from app.providers.cornell import (
    is_ithaca_or_virtual_section,
    is_virtual_instruction_mode,
    parse_cornell_classes_payload,
)
from tests.conftest import make_sample_courses  # noqa: F401 - ensures test helpers import cleanly


def _make_section_json(
    *,
    class_nbr: int,
    ssr_component: str = "LEC",
    section: str = "001",
    campus: str = "MAIN",
    location: str = "ITH",
    location_descr: str = "Ithaca, NY (Main Campus)",
    instruction_mode: str = "P",
    open_status: str = "O",
) -> dict:
    return {
        "classNbr": class_nbr,
        "ssrComponent": ssr_component,
        "section": section,
        "campus": campus,
        "location": location,
        "locationDescr": location_descr,
        "instructionMode": instruction_mode,
        "openStatus": open_status,
        "meetings": [
            {
                "pattern": "MWF",
                "timeStart": "10:10AM",
                "timeEnd": "11:00AM",
                "instructors": [{"firstName": "Ada", "lastName": "Lovelace"}],
            }
        ],
    }


def _make_course_json(
    *,
    crse_id: int,
    subject: str,
    catalog_nbr: str,
    title: str,
    sections: list[dict],
) -> dict:
    return {
        "crseId": crse_id,
        "subject": subject,
        "catalogNbr": catalog_nbr,
        "titleShort": title,
        "titleLong": title,
        "acadCareer": "UG",
        "acadGroup": "EN",
        "catalogPrint": "Y",
        "enrollGroups": [
            {
                "unitsMinimum": 3.0,
                "unitsMaximum": 3.0,
                "componentsRequired": ["LEC"],
                "classSections": sections,
            }
        ],
    }


def _parse(roster: str, payload: dict):
    return parse_cornell_classes_payload(json.dumps(payload).encode("utf-8"), roster)


def test_parse_cornell_payload_extracts_location_and_predicates() -> None:
    payload = {
        "status": "success",
        "data": {
            "classes": [
                _make_course_json(
                    crse_id=10001,
                    subject="CS",
                    catalog_nbr="6110",
                    title="Advanced Programming Languages",
                    sections=[
                        _make_section_json(
                            class_nbr=10101,
                            section="001",
                            campus="MAIN",
                            location="ITH",
                            location_descr="Ithaca, NY (Main Campus)",
                            instruction_mode="P",
                            open_status="C",
                        ),
                        # Real Cornell Roster trap: campus='MAIN' while location='NYCTECH'!
                        _make_section_json(
                            class_nbr=10102,
                            section="030",
                            campus="MAIN",
                            location="NYCTECH",
                            location_descr="Cornell Tech",
                            instruction_mode="P",
                            open_status="O",
                        ),
                        _make_section_json(
                            class_nbr=10103,
                            section="090",
                            campus="NYT",
                            location="ITH",
                            location_descr="Ithaca, NY (Main Campus)",
                            instruction_mode="SD",
                            open_status="O",
                        ),
                        _make_section_json(
                            class_nbr=10104,
                            section="031",
                            campus="NYT",
                            location="NYCTECH",
                            location_descr="Cornell Tech",
                            instruction_mode="AD",
                            open_status="O",
                        ),
                        _make_section_json(
                            class_nbr=10105,
                            section="032",
                            campus="NYT",
                            location="NYCTECH",
                            location_descr="Cornell Tech",
                            instruction_mode="HY",
                            open_status="O",
                        ),
                    ],
                ),
                _make_course_json(
                    crse_id=10002,
                    subject="ENGRG",
                    catalog_nbr="1400",
                    title="Online Engineering Seminar",
                    sections=[
                        _make_section_json(
                            class_nbr=10201,
                            section="001",
                            campus="MAIN",
                            location="ITH",
                            location_descr="Ithaca, NY (Main Campus)",
                            instruction_mode="OL",
                            open_status="O",
                        )
                    ],
                ),
            ]
        },
    }

    courses = _parse("SP27", payload)
    assert len(courses) == 2

    cs6110_secs = {s.class_nbr: s for s in courses[0].sections}
    assert cs6110_secs[10101].location == "ITH"
    assert cs6110_secs[10102].location == "NYCTECH"
    assert cs6110_secs[10102].location_descr == "Cornell Tech"

    # Predicate checks
    def _ok(sec) -> bool:
        return is_ithaca_or_virtual_section(
            campus=sec.campus,
            location=sec.location,
            instruction_mode=sec.instruction_mode,
        )

    assert _ok(cs6110_secs[10101]) is True  # MAIN + ITH In Person
    assert _ok(cs6110_secs[10102]) is False  # MAIN + NYCTECH In Person
    assert _ok(cs6110_secs[10103]) is True  # NYT + ITH DL-SD
    assert _ok(cs6110_secs[10104]) is False  # NYT + NYCTECH DL-AD (Cornell Tech restricted)
    assert _ok(cs6110_secs[10105]) is False  # NYT + NYCTECH Hybrid

    engrg_sec = courses[1].sections[0]
    assert is_virtual_instruction_mode(engrg_sec.instruction_mode) is True
    assert _ok(engrg_sec) is True  # MAIN + ITH Online (OL)

    # Empty location with campus='MAIN' should fall back to Ithaca, whereas campus='NYT' with empty location should not
    assert is_ithaca_or_virtual_section(campus="MAIN", location="", instruction_mode="P") is True
    assert is_ithaca_or_virtual_section(campus="MAIN", location="ROME", instruction_mode="P") is False
    assert is_ithaca_or_virtual_section(campus="NYT", location="", instruction_mode="P") is False


@pytest.mark.asyncio
async def test_db_migration_backfills_location_from_enroll_groups(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_path)
    # Minimal legacy schema before location/location_descr/ithaca_or_virtual columns existed
    conn.executescript(
        """
        CREATE TABLE roster_sections (
            roster TEXT NOT NULL,
            subject TEXT NOT NULL,
            catalog_nbr TEXT NOT NULL,
            class_nbr INTEGER NOT NULL,
            enroll_group_idx INTEGER NOT NULL,
            ssr_component TEXT NOT NULL,
            section TEXT NOT NULL,
            campus TEXT NOT NULL DEFAULT 'MAIN',
            instruction_mode TEXT NOT NULL DEFAULT 'P',
            open_status TEXT NOT NULL,
            waitlist_avail INTEGER NOT NULL DEFAULT 0,
            units_min REAL NOT NULL DEFAULT 3.0,
            units_max REAL NOT NULL DEFAULT 3.0,
            components_required_json TEXT NOT NULL DEFAULT '[]',
            meetings_summary TEXT NOT NULL DEFAULT '',
            instructors_summary TEXT NOT NULL DEFAULT '',
            course_title TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL,
            PRIMARY KEY (roster, class_nbr)
        );
        CREATE TABLE courses_meta (
            roster TEXT NOT NULL,
            subject TEXT NOT NULL,
            catalog_nbr TEXT NOT NULL,
            crse_id INTEGER,
            title_short TEXT NOT NULL DEFAULT '',
            title_long TEXT NOT NULL DEFAULT '',
            acad_career TEXT NOT NULL DEFAULT '',
            acad_group TEXT NOT NULL DEFAULT '',
            units_min REAL NOT NULL DEFAULT 3.0,
            units_max REAL NOT NULL DEFAULT 3.0,
            description TEXT NOT NULL DEFAULT '',
            catalog_prereq TEXT NOT NULL DEFAULT '',
            catalog_coreq TEXT NOT NULL DEFAULT '',
            catalog_forbidden_overlaps TEXT NOT NULL DEFAULT '',
            catalog_when_offered TEXT NOT NULL DEFAULT '',
            catalog_permission TEXT NOT NULL DEFAULT '',
            catalog_notes TEXT NOT NULL DEFAULT '',
            catalog_breadth TEXT NOT NULL DEFAULT '',
            catalog_distr TEXT TEXT NOT NULL DEFAULT '',
            enroll_groups_json TEXT NOT NULL DEFAULT '[]',
            raw_json TEXT NOT NULL DEFAULT '{}',
            updated_at TEXT NOT NULL,
            PRIMARY KEY (roster, subject, catalog_nbr)
        );
        CREATE TABLE watches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            roster TEXT NOT NULL,
            subject TEXT NOT NULL,
            catalog_nbr TEXT NOT NULL,
            class_nbr INTEGER,
            enroll_group_idx INTEGER,
            component_filter TEXT,
            mode TEXT NOT NULL,
            trigger_on TEXT NOT NULL DEFAULT 'open',
            priority INTEGER NOT NULL DEFAULT 1,
            auto_pause INTEGER NOT NULL DEFAULT 1,
            cooldown_sec INTEGER NOT NULL DEFAULT 120,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        );
        """
    )
    enroll_groups = [
        {
            "unitsMinimum": 3.0,
            "unitsMaximum": 3.0,
            "componentsRequired": ["LEC"],
            "classSections": [
                {
                    "classNbr": 77701,
                    "ssrComponent": "LEC",
                    "section": "030",
                    "campus": "MAIN",
                    "location": "NYCTECH",
                    "locationDescr": "Cornell Tech",
                    "instructionMode": "P",
                    "openStatus": "O",
                }
            ],
        }
    ]
    conn.execute(
        """
        INSERT INTO courses_meta (roster, subject, catalog_nbr, title_long, enroll_groups_json, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("SP27", "CS", "5304", "Data Science in the Wild", json.dumps(enroll_groups), "2026-10-01T00:00:00Z"),
    )
    conn.execute(
        """
        INSERT INTO roster_sections (
            roster, subject, catalog_nbr, class_nbr, enroll_group_idx,
            ssr_component, section, campus, instruction_mode, open_status, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("SP27", "CS", "5304", 77701, 0, "LEC", "030", "MAIN", "P", "O", "2026-10-01T00:00:00Z"),
    )
    conn.commit()
    conn.close()

    db = Database(db_path)
    await db.connect()
    try:
        async with db.conn.execute(
            "SELECT location, location_descr FROM roster_sections WHERE roster='SP27' AND class_nbr=77701"
        ) as cur:
            row = await cur.fetchone()
        assert row is not None
        assert row["location"] == "NYCTECH"
        assert row["location_descr"] == "Cornell Tech"

        async with db.conn.execute("PRAGMA table_info(watches)") as cur:
            watch_cols = {r["name"] for r in await cur.fetchall()}
        assert "ithaca_or_virtual" in watch_cols
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_search_and_watch_scoping_ithaca_or_virtual(app_client) -> None:
    app, client = app_client
    catalog = app.state.catalog
    poller = app.state.poller

    await client.post("/api/auth/bootstrap", json={"username": "tyler", "password": "password123"})

    payload = {
        "status": "success",
        "data": {
            "classes": [
                _make_course_json(
                    crse_id=20001,
                    subject="CS",
                    catalog_nbr="2110",
                    title="Object-Oriented Programming",
                    sections=[
                        _make_section_json(
                            class_nbr=21001,
                            section="001",
                            campus="MAIN",
                            location="ITH",
                            location_descr="Ithaca, NY (Main Campus)",
                            instruction_mode="P",
                            open_status="O",
                        )
                    ],
                ),
                # Pure Cornell Tech course (even disguised under campus='MAIN')
                _make_course_json(
                    crse_id=20002,
                    subject="CS",
                    catalog_nbr="5304",
                    title="Data Science in the Wild",
                    sections=[
                        _make_section_json(
                            class_nbr=53041,
                            section="030",
                            campus="MAIN",
                            location="NYCTECH",
                            location_descr="Cornell Tech",
                            instruction_mode="P",
                            open_status="O",
                        )
                    ],
                ),
                # Pure online Ithaca course
                _make_course_json(
                    crse_id=20003,
                    subject="ENGRG",
                    catalog_nbr="1400",
                    title="Online Seminar",
                    sections=[
                        _make_section_json(
                            class_nbr=14001,
                            section="001",
                            campus="MAIN",
                            location="ITH",
                            location_descr="Ithaca, NY (Main Campus)",
                            instruction_mode="OL",
                            open_status="O",
                        )
                    ],
                ),
                # Mixed-location course: Ithaca sec CLOSED + Cornell Tech sec OPEN
                _make_course_json(
                    crse_id=20004,
                    subject="CS",
                    catalog_nbr="6110",
                    title="Advanced Programming Languages",
                    sections=[
                        _make_section_json(
                            class_nbr=61101,
                            section="001",
                            campus="MAIN",
                            location="ITH",
                            location_descr="Ithaca, NY (Main Campus)",
                            instruction_mode="P",
                            open_status="C",
                        ),
                        _make_section_json(
                            class_nbr=61102,
                            section="030",
                            campus="NYT",
                            location="NYCTECH",
                            location_descr="Cornell Tech",
                            instruction_mode="P",
                            open_status="O",
                        ),
                    ],
                ),
            ]
        },
    }

    parsed_cs = _parse("SP27", {"status": "success", "data": {"classes": [
        payload["data"]["classes"][0],
        payload["data"]["classes"][1],
        payload["data"]["classes"][3],
    ]}})
    parsed_engrg = _parse("SP27", {"status": "success", "data": {"classes": [
        payload["data"]["classes"][2],
    ]}})
    await catalog.upsert_courses_batch("SP27", "CS", parsed_cs)
    await catalog.upsert_courses_batch("SP27", "ENGRG", parsed_engrg)

    # 1. Default search (ithaca_or_virtual=true) omits CS 5304 and strips Cornell Tech section from CS 6110
    res_default = await client.get("/api/courses/search", params={"roster": "SP27", "refresh_stale": "false"})
    assert res_default.status_code == 200
    body_default = res_default.json()
    codes_default = {f"{c['subject']} {c['catalog_nbr']}": c for c in body_default["courses"]}
    assert "CS 2110" in codes_default
    assert "ENGRG 1400" in codes_default
    assert "CS 5304" not in codes_default
    assert "CS 6110" in codes_default
    assert [s["class_nbr"] for s in codes_default["CS 6110"]["sections"]] == [61101]
    assert codes_default["CS 6110"]["hidden_other_location_count"] == 1
    assert "Cornell Tech" in codes_default["CS 6110"]["hidden_other_locations"]
    assert body_default["meta"]["filtered_out_location_count"] == 1
    assert "Cornell Tech" in body_default["meta"]["filtered_out_locations"]

    # 2. Direct search for CS 5304 while ithaca_or_virtual=true reports filtered_out_location_count=1
    res_5304 = await client.get("/api/courses/search", params={"roster": "SP27", "q": "5304", "refresh_stale": "false"})
    assert res_5304.status_code == 200
    assert res_5304.json()["courses"] == []
    assert res_5304.json()["meta"]["filtered_out_location_count"] == 1

    # 3. ithaca_or_virtual=false returns CS 5304 and both CS 6110 sections
    res_all = await client.get(
        "/api/courses/search",
        params={"roster": "SP27", "ithaca_or_virtual": "false", "refresh_stale": "false"},
    )
    assert res_all.status_code == 200
    codes_all = {f"{c['subject']} {c['catalog_nbr']}": c for c in res_all.json()["courses"]}
    assert "CS 5304" in codes_all
    assert len(codes_all["CS 6110"]["sections"]) == 2
    assert codes_all["CS 6110"]["hidden_other_location_count"] == 0

    # 4. Creating an any_section watch scoped to ithaca_or_virtual on pure Cornell Tech CS 5304 is rejected
    bad_watch = await client.post(
        "/api/watches",
        json={
            "roster": "SP27",
            "subject": "CS",
            "catalog_nbr": "5304",
            "mode": "any_section",
            "trigger_on": "open",
            "ithaca_or_virtual": True,
        },
    )
    assert bad_watch.status_code == 400

    # 5. Any-section watch on mixed CS 6110 with ithaca_or_virtual=True ignores Cornell Tech opening
    good_watch = await client.post(
        "/api/watches",
        json={
            "roster": "SP27",
            "subject": "CS",
            "catalog_nbr": "6110",
            "mode": "any_section",
            "trigger_on": "open",
            "ithaca_or_virtual": True,
        },
    )
    assert good_watch.status_code == 201
    watch_data = good_watch.json()["watch"]
    assert watch_data["ithaca_or_virtual"] is True
    assert watch_data["section_info"]["location"] == "ITH"

    # Evaluate when NYCTECH sec #61102 is OPEN and ITH sec #61101 is CLOSED -> 0 alerts
    alerts_nyc_only = await poller.evaluate_courses("SP27", "CS", parsed_cs)
    assert alerts_nyc_only == []

    # Now open ITH sec #61101 -> triggers 1 alert on #61101
    parsed_cs_ith_open = _parse(
        "SP27",
        {
            "status": "success",
            "data": {
                "classes": [
                    _make_course_json(
                        crse_id=20004,
                        subject="CS",
                        catalog_nbr="6110",
                        title="Advanced Programming Languages",
                        sections=[
                            _make_section_json(
                                class_nbr=61101,
                                section="001",
                                campus="MAIN",
                                location="ITH",
                                location_descr="Ithaca, NY (Main Campus)",
                                instruction_mode="P",
                                open_status="O",
                            ),
                            _make_section_json(
                                class_nbr=61102,
                                section="030",
                                campus="NYT",
                                location="NYCTECH",
                                location_descr="Cornell Tech",
                                instruction_mode="P",
                                open_status="O",
                            ),
                        ],
                    )
                ]
            },
        },
    )
    alerts_ith_open = await poller.evaluate_courses("SP27", "CS", parsed_cs_ith_open)
    assert len(alerts_ith_open) == 1
    assert alerts_ith_open[0].section.class_nbr == 61101
