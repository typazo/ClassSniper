"""Tests for Cornell ILR New Curriculum classification, distribution filters, summary & major_mode."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import aiosqlite
import httpx
import pytest

from app.config import Settings
from app.db import Database
from app.main import create_app
from app.providers.base import CourseRecord, FetchResult, RosterRecord, SectionRecord, SubjectRecord
from app.services.ilr_requirements import (
    ILRRequirementsIndex,
    parse_ilr_codes_from_attrs,
)


def _make_ilr_course(
    subject: str,
    nbr: str,
    title: str,
    *,
    crse_attrs: list[dict[str, str]] | None = None,
    units_min: float = 3.0,
    units_max: float = 3.0,
    grading_basis: str = "OPT",
    prereq: str = "",
    crosslists: list[tuple[str, str]] | None = None,
    class_nbr: int = 1000,
    open_status: str = "O",
    acad_career: str = "UG",
    acad_group: str = "IL",
    campus: str = "MAIN",
    location: str = "ITH",
    instruction_mode: str = "In Person",
) -> CourseRecord:
    combos = [{"subject": s, "catalogNbr": n, "type": "B"} for (s, n) in (crosslists or [])]
    return CourseRecord(
        roster="SP27",
        subject=subject,
        catalog_nbr=nbr,
        title_short=title[:30],
        title_long=title,
        description=f"{title} description.",
        crse_id=class_nbr + 400000,
        enroll_groups=[
            {
                "unitsMinimum": units_min,
                "unitsMaximum": units_max,
                "gradingBasis": grading_basis,
                "simpleCombinations": combos,
                "componentsRequired": ["LEC"],
                "classSections": [{"ssrComponent": "LEC", "classNbr": class_nbr, "openStatus": open_status}],
            }
        ],
        sections=[
            SectionRecord(
                class_nbr=class_nbr,
                enroll_group_idx=0,
                ssr_component="LEC",
                section="001",
                open_status=open_status,
                components_required=["LEC"],
                meetings_summary="TR 10:10AM-11:25AM",
                instructors_summary="Faculty Member",
                campus=campus,
                location=location,
                location_descr="Ithaca" if location == "ITH" else "Cornell Tech",
                instruction_mode=instruction_mode,
            )
        ],
        acad_career=acad_career,
        acad_group=acad_group,
        catalog_prereq=prereq,
        crse_attrs=crse_attrs or [],
    )


class RichILRFakeProvider:
    """Deterministic fake provider with realistic Cornell SP27 ILR metadata & edge cases."""

    def __init__(self) -> None:
        self.rosters = [RosterRecord(slug="SP27", descr="Spring 2027", is_default=True, strm="2951")]
        self.subjects = [
            SubjectRecord(value="ILRGL", descr="ILR Global Labor & Work"),
            SubjectRecord(value="ILROB", descr="ILR Organizational Behavior"),
            SubjectRecord(value="ILRST", descr="ILR Social Statistics"),
            SubjectRecord(value="ECON", descr="Economics"),
            SubjectRecord(value="PUBPOL", descr="Public Policy"),
            SubjectRecord(value="PLSCI", descr="Plant Sciences"),
            SubjectRecord(value="PHYS", descr="Physics"),
            SubjectRecord(value="INFO", descr="Information Science"),
        ]
        self.courses_by_bucket: dict[tuple[str, str], list[CourseRecord]] = {
            ("SP27", "ILRGL"): [
                _make_ilr_course(
                    "ILRGL",
                    "1100",
                    "Introduction to U.S. Labor History",
                    crse_attrs=[],
                    class_nbr=1001,
                    open_status="O",
                ),
                _make_ilr_course(
                    "ILRGL",
                    "2390",
                    "Multinational Corporations",
                    crse_attrs=[{"attrDescr": "Distr", "crseAttrValues": "(ICE-IL, ICL-IL, SOW-IL)"}],
                    class_nbr=1002,
                    open_status="O",
                ),
                _make_ilr_course(
                    "ILRGL",
                    "3280",
                    "Comparative Labor Law",
                    crse_attrs=[{"attrDescr": "Distr", "crseAttrValues": "(AWI-IL, ICE-IL, ICL-IL)"}],
                    units_min=4.0,
                    units_max=4.0,
                    class_nbr=1003,
                    open_status="W",
                ),
                _make_ilr_course(
                    "ILRGL",
                    "3820",
                    "Special Topics in Labor Policy",
                    crse_attrs=[{"attrDescr": "Distr", "crseAttrValues": "(ICE-IL)"}],
                    units_min=1.5,
                    units_max=1.5,
                    grading_basis="SUS",
                    class_nbr=1004,
                    open_status="C",
                ),
            ],
            ("SP27", "ILROB"): [
                _make_ilr_course(
                    "ILROB",
                    "1220",
                    "Introduction to Organizational Behavior",
                    crse_attrs=[],
                    class_nbr=2001,
                    open_status="O",
                ),
            ],
            ("SP27", "ILRST"): [
                _make_ilr_course(
                    "ILRST",
                    "2100",
                    "Introductory Statistics",
                    crse_attrs=[{"attrDescr": "Distr", "crseAttrValues": "(STA-IL)"}],
                    units_min=4.0,
                    units_max=4.0,
                    class_nbr=3001,
                    open_status="O",
                ),
                _make_ilr_course(
                    "ILRST",
                    "5110",
                    "Statistical Methods for the Social Sciences",
                    crse_attrs=[{"attrDescr": "Distr", "crseAttrValues": "(ICE-IL)"}],
                    units_min=4.0,
                    units_max=4.0,
                    acad_career="GR",
                    class_nbr=3002,
                    open_status="O",
                ),
            ],
            ("SP27", "ECON"): [
                _make_ilr_course(
                    "ECON",
                    "1110",
                    "Introductory Microeconomics",
                    crse_attrs=[],
                    acad_group="AS",
                    class_nbr=4001,
                    open_status="O",
                ),
                _make_ilr_course(
                    "ECON",
                    "3120",
                    "Applied Econometrics",
                    crse_attrs=[{"attrDescr": "Distr", "crseAttrValues": "(OCE-IL, QP-IL, STA-IL)"}],
                    units_min=4.0,
                    units_max=4.0,
                    prereq="ECON 1110.",
                    acad_group="AS",
                    class_nbr=4002,
                    open_status="W",
                ),
                _make_ilr_course(
                    "ECON",
                    "3340",
                    "Evolution of Social Policy",
                    crse_attrs=[{"attrDescr": "Distr", "crseAttrValues": "(ICE-IL, ICL-IL, LH-IL, QP-IL)"}],
                    prereq="ECON 1110.",
                    acad_group="AS",
                    class_nbr=4003,
                    open_status="O",
                ),
                _make_ilr_course(
                    "ECON",
                    "3670",
                    "Public Policy in Developing Countries",
                    crse_attrs=[{"attrDescr": "Distr", "crseAttrValues": "(OCE-IL, QP-IL)"}],
                    crosslists=[("PUBPOL", "3130"), ("PUBPOL", "5130")],
                    acad_group="AS",
                    class_nbr=4004,
                    open_status="O",
                ),
            ],
            ("SP27", "PUBPOL"): [
                _make_ilr_course(
                    "PUBPOL",
                    "3130",
                    "Public Policy in Developing Countries",
                    crse_attrs=[{"attrDescr": "Distr", "crseAttrValues": "(OCE-IL, QP-IL)"}],
                    crosslists=[("ECON", "3670"), ("PUBPOL", "5130")],
                    acad_group="PB",
                    class_nbr=5001,
                    open_status="O",
                ),
                _make_ilr_course(
                    "PUBPOL",
                    "5130",
                    "Public Policy in Developing Countries",
                    crse_attrs=[],
                    crosslists=[("ECON", "3670"), ("PUBPOL", "3130")],
                    acad_career="GR",
                    acad_group="PB",
                    class_nbr=5002,
                    open_status="O",
                ),
            ],
            ("SP27", "PLSCI"): [
                _make_ilr_course(
                    "PLSCI",
                    "2010",
                    "Magical Mushrooms",
                    crse_attrs=[],
                    crosslists=[("PLSCI", "2013")],
                    acad_group="AG",
                    class_nbr=6001,
                    open_status="C",
                ),
                _make_ilr_course(
                    "PLSCI",
                    "2013",
                    "Magical Mushrooms (Writing)",
                    crse_attrs=[{"attrDescr": "Distr", "crseAttrValues": "(SCT-IL)"}],
                    crosslists=[("PLSCI", "2010")],
                    acad_group="AG",
                    class_nbr=6002,
                    open_status="O",
                ),
            ],
            ("SP27", "PHYS"): [
                _make_ilr_course(
                    "PHYS",
                    "1110",
                    "Introductory Experimental Physics",
                    crse_attrs=[{"attrDescr": "Distr", "crseAttrValues": "(SCT-IL)"}],
                    units_min=1.0,
                    units_max=1.0,
                    acad_group="AS",
                    class_nbr=7001,
                    open_status="O",
                ),
            ],
            ("SP27", "INFO"): [
                _make_ilr_course(
                    "INFO",
                    "5300",
                    "NYC Tech Quantitative Policy Studio",
                    crse_attrs=[{"attrDescr": "Distr", "crseAttrValues": "(QP-IL)"}],
                    acad_group="CI",
                    campus="NYC",
                    location="TECH",
                    class_nbr=8001,
                    open_status="O",
                ),
            ],
        }

    async def fetch_rosters(self) -> list[RosterRecord]:
        return deepcopy(self.rosters)

    async def fetch_subjects(self, roster: str) -> list[SubjectRecord]:
        return deepcopy(self.subjects)

    async def fetch_subject_classes(self, roster: str, subject: str) -> FetchResult:
        return FetchResult(
            courses=deepcopy(self.courses_by_bucket.get((roster.upper(), subject.upper()), [])),
            rtt_ms=10,
            payload_bytes=2048,
        )

    async def close(self) -> None:
        return None


def test_parse_ilr_codes_and_core_warnings() -> None:
    attrs = json.dumps(
        [
            {"attrDescr": "Distribution Requirements", "crseAttrValues": "(SBA-AS, AWI-IL, ICE-IL, ICL-IL)"},
            {"attrDescr": "Other", "crseAttrValues": "LH-IL"},
        ]
    )
    assert parse_ilr_codes_from_attrs(attrs) == ["ICL-IL", "LH-IL", "AWI-IL", "ICE-IL"]
    assert parse_ilr_codes_from_attrs(None) == []

    rows = [
        {
            "subject": "ILRGL",
            "catalog_nbr": "1100",
            "acad_career": "UG",
            "units_min": 3.0,
            "units_max": 3.0,
            "has_letter_grade": 1,
            "crosslists_json": "[]",
            "crse_attrs_json": "[]",
        },
        {
            "subject": "PHYS",
            "catalog_nbr": "1110",
            "acad_career": "UG",
            "units_min": 1.0,
            "units_max": 1.0,
            "has_letter_grade": 1,
            "crosslists_json": "[]",
            "crse_attrs_json": json.dumps([{"crseAttrValues": "(SCT-IL)"}]),
        },
        {
            "subject": "ILRGL",
            "catalog_nbr": "3820",
            "acad_career": "UG",
            "units_min": 1.5,
            "units_max": 1.5,
            "has_letter_grade": 0,
            "crosslists_json": "[]",
            "crse_attrs_json": json.dumps([{"crseAttrValues": "(ICE-IL)"}]),
        },
        {
            "subject": "ILRST",
            "catalog_nbr": "5110",
            "acad_career": "GR",
            "units_min": 4.0,
            "units_max": 4.0,
            "has_letter_grade": 1,
            "crosslists_json": "[]",
            "crse_attrs_json": json.dumps([{"crseAttrValues": "(ICE-IL)"}]),
        },
    ]
    index = ILRRequirementsIndex(rows)

    core = index.get("ILRGL", "1100")
    assert core is not None
    assert core.codes == ("ILR-CORE",)
    assert core.is_ilr_core is True
    assert core.warnings == ()

    phys = index.get("PHYS", "1110")
    assert phys is not None
    assert phys.codes == ("SCT-IL",)
    assert any("< 3 cr" in w for w in phys.warnings)

    su_course = index.get("ILRGL", "3820")
    assert su_course is not None
    assert any("S/U Only" in w for w in su_course.warnings)

    grad_course = index.get("ILRST", "5110")
    assert grad_course is not None
    assert any("Grad level" in w for w in grad_course.warnings)


def test_ug_grad_crosslist_non_inheritance_and_filter_matching() -> None:
    rows = [
        {
            "subject": "PUBPOL",
            "catalog_nbr": "3130",
            "acad_career": "UG",
            "units_min": 3.0,
            "units_max": 3.0,
            "has_letter_grade": 1,
            "crosslists_json": json.dumps(["PUBPOL 5130"]),
            "crse_attrs_json": json.dumps([{"crseAttrValues": "(QP-IL, OCE-IL)"}]),
        },
        {
            "subject": "PUBPOL",
            "catalog_nbr": "5130",
            "acad_career": "GR",
            "units_min": 3.0,
            "units_max": 3.0,
            "has_letter_grade": 1,
            "crosslists_json": json.dumps(["PUBPOL 3130"]),
            "crse_attrs_json": "[]",
        },
        {
            "subject": "ECON",
            "catalog_nbr": "3340",
            "acad_career": "UG",
            "units_min": 3.0,
            "units_max": 3.0,
            "has_letter_grade": 1,
            "crosslists_json": "[]",
            "crse_attrs_json": json.dumps([{"crseAttrValues": "(ICE-IL, ICL-IL, LH-IL, QP-IL)"}]),
        },
        {
            "subject": "ILRST",
            "catalog_nbr": "2100",
            "acad_career": "UG",
            "units_min": 4.0,
            "units_max": 4.0,
            "has_letter_grade": 1,
            "crosslists_json": "[]",
            "crse_attrs_json": json.dumps([{"crseAttrValues": "(STA-IL)"}]),
        },
        {
            "subject": "ILROB",
            "catalog_nbr": "1220",
            "acad_career": "UG",
            "units_min": 3.0,
            "units_max": 3.0,
            "has_letter_grade": 1,
            "crosslists_json": "[]",
            "crse_attrs_json": "[]",
        },
    ]
    index = ILRRequirementsIndex(rows)

    ug = index.get("PUBPOL", "3130")
    gr = index.get("PUBPOL", "5130")
    econ = index.get("ECON", "3340")
    stats = index.get("ILRST", "2100")
    core = index.get("ILROB", "1220")
    assert ug and gr and econ and stats and core

    # Grad cross-list must NEVER copy UG -IL codes, only hint to enroll in UG number.
    assert gr.codes == ()
    assert len(gr.ug_crosslist_hints) == 1
    assert "PUBPOL 3130" in gr.ug_crosslist_hints[0]

    assert index.matches_filter(econ, ["ICL-IL", "QP-IL"], match_mode="all") is True
    assert index.matches_filter(ug, ["ICL-IL", "QP-IL"], match_mode="all") is False
    assert index.matches_filter(ug, ["MAIN_3"], match_mode="any") is True
    assert index.matches_filter(core, ["ANY_IL"], match_mode="any") is False
    assert index.matches_filter(econ, ["ANY_IL"], match_mode="any", ilr_multi_only=True) is True
    assert index.matches_filter(stats, [], ilr_multi_only=True) is False


@pytest.mark.asyncio
async def test_major_mode_migration_and_preferences_roundtrip(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy_prefs.db"
    async with aiosqlite.connect(db_path) as conn:
        await conn.executescript(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                priority_tier INTEGER NOT NULL DEFAULT 1,
                show_cs_features INTEGER NOT NULL DEFAULT 1
            );
            INSERT INTO users (username, password_hash, role, show_cs_features)
            VALUES ('alice', 'hash1', 'admin', 1),
                   ('bob', 'hash2', 'user', 0);
            """
        )
        await conn.commit()

    db = Database(db_path)
    await db.connect()
    try:
        alice = await db.fetch_one("SELECT major_mode FROM users WHERE username = 'alice'")
        bob = await db.fetch_one("SELECT major_mode FROM users WHERE username = 'bob'")
        assert alice is not None and alice["major_mode"] == "cs"
        assert bob is not None and bob["major_mode"] == "none"
    finally:
        await db.close()

    # Full HTTP preferences + login + status persistence test
    settings = Settings(
        app_domain="sniper.hodgman.net",
        app_origin="https://sniper.hodgman.net",
        data_dir=tmp_path / "app_data",
        static_dir=tmp_path / "static",
        enable_background_workers=False,
    )
    settings.ensure_persisted_secrets()
    app = create_app(custom_settings=settings, custom_provider=RichILRFakeProvider())
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="https://sniper.hodgman.net") as client:
            boot = await client.post("/api/auth/bootstrap", json={"username": "ilr_admin", "password": "password123"})
            assert boot.status_code == 201
            assert boot.json()["user"]["major_mode"] == "cs"
            assert boot.json()["user"]["show_cs_features"] is True

            pref_ilr = await client.put("/api/auth/preferences", json={"major_mode": "ilr"})
            assert pref_ilr.status_code == 200
            assert pref_ilr.json()["user"]["major_mode"] == "ilr"
            assert pref_ilr.json()["user"]["show_cs_features"] is False

            # Re-verify across /me, /status, and fresh /login
            assert (await client.get("/api/auth/me")).json()["user"]["major_mode"] == "ilr"
            assert (await client.get("/api/auth/status")).json()["user"]["major_mode"] == "ilr"
            await client.post("/api/auth/logout")
            login = await client.post("/api/auth/login", json={"username": "ilr_admin", "password": "password123"})
            assert login.status_code == 200
            assert login.json()["user"]["major_mode"] == "ilr"
            assert login.json()["user"]["show_cs_features"] is False

            # Legacy show_cs_features boolean still works seamlessly
            pref_off = await client.put("/api/auth/preferences", json={"show_cs_features": False})
            assert pref_off.status_code == 200
            assert pref_off.json()["user"]["major_mode"] == "none"

            pref_cs = await client.put("/api/auth/preferences", json={"show_cs_features": True})
            assert pref_cs.status_code == 200
            assert pref_cs.json()["user"]["major_mode"] == "cs"


@pytest.mark.asyncio
async def test_ilr_summary_and_search_end_to_end(tmp_path: Path) -> None:
    settings = Settings(
        app_domain="sniper.hodgman.net",
        app_origin="https://sniper.hodgman.net",
        data_dir=tmp_path / "data",
        static_dir=tmp_path / "static",
        enable_background_workers=False,
    )
    settings.ensure_persisted_secrets()
    app = create_app(custom_settings=settings, custom_provider=RichILRFakeProvider())

    async with app.router.lifespan_context(app):
        await app.state.catalog.sync_rosters_and_subjects("SP27")
        await app.state.catalog.sync_full_roster("SP27", delay_sec=0.0)

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="https://sniper.hodgman.net") as client:
            await client.post("/api/auth/bootstrap", json={"username": "ilr_student", "password": "password123"})
            await client.put("/api/auth/preferences", json={"major_mode": "ilr"})

            # 1. Summary respects Ithaca + Virtual filter (INFO 5300 at NYC/TECH excluded when ithaca_or_virtual=true)
            sum_ith = (await client.get("/api/ilr/summary?roster=SP27&ithaca_or_virtual=true")).json()
            sum_all = (await client.get("/api/ilr/summary?roster=SP27&ithaca_or_virtual=false")).json()
            req_ith = {r["code"]: r for r in sum_ith["requirements"]}
            req_all = {r["code"]: r for r in sum_all["requirements"]}

            # QP-IL in Ithaca: ECON 3120 (W), ECON 3340 (O), ECON 3670 (O), PUBPOL 3130 (O) -> 4 total (3 open, 1 waitlist)
            assert req_ith["QP-IL"]["total"] == 4
            assert req_ith["QP-IL"]["open"] == 3
            assert req_ith["QP-IL"]["waitlist"] == 1
            # With All Locations: adds NYC INFO 5300 (O) -> 5 total (4 open)
            assert req_all["QP-IL"]["total"] == 5
            assert req_all["QP-IL"]["open"] == 4
            assert req_ith["ILR-CORE"]["total"] == 3  # ILRGL 1100, ILROB 1220, ECON 1110

            # 2. Search SOW-IL returns ILRGL 2390 with also_fits_codes = ['ICL-IL', 'ICE-IL']
            sow_res = (await client.get("/api/courses/search", params={"roster": "SP27", "ilr_codes": "SOW-IL"})).json()
            sow_codes = [f"{c['subject']} {c['catalog_nbr']}" for c in sow_res["courses"]]
            assert sow_codes == ["ILRGL 2390"]
            assert sow_res["courses"][0]["ilr_eligibility"]["also_fits_codes"] == ["ICL-IL", "ICE-IL"]

            # 3. ALL match on ICL-IL + QP-IL isolates ECON 3340
            both_res = (
                await client.get(
                    "/api/courses/search",
                    params={"roster": "SP27", "ilr_codes": "ICL-IL,QP-IL", "ilr_match": "all"},
                )
            ).json()
            assert [f"{c['subject']} {c['catalog_nbr']}" for c in both_res["courses"]] == ["ECON 3340"]

            # 4. Double-counts filter sorts Open warning-free 4-req ECON 3340 ahead of waitlist/grad/warning courses
            multi_res = (
                await client.get(
                    "/api/courses/search",
                    params={"roster": "SP27", "ilr_multi_only": "true"},
                )
            ).json()
            multi_keys = [f"{c['subject']} {c['catalog_nbr']}" for c in multi_res["courses"]]
            assert "ECON 3340" in multi_keys
            assert "ILRGL 2390" in multi_keys
            assert "ILRST 2100" not in multi_keys  # Only 1 tag (STA-IL)
            assert multi_keys[0] == "ECON 3340"  # Open, UG, 4 requirements

            # 5. Grad cross-list PUBPOL 5130 carries UG cross-list hint without inheriting QP-IL
            pubpol_res = (
                await client.get(
                    "/api/courses/search",
                    params={"roster": "SP27", "q": "PUBPOL 5130"},
                )
            ).json()
            pub5130 = next(c for c in pubpol_res["courses"] if c["catalog_nbr"] == "5130")
            assert pub5130["ilr_eligibility"]["qualifies_any"] is False
            assert any("PUBPOL 3130" in h or "ECON 3670" in h for h in pub5130["ilr_eligibility"]["ug_crosslist_hints"])

            # 6. Pre-reqs autocomplete with mode=ilr surfaces ILR/ECON subjects cleanly
            opts = (await client.get("/api/user/prereqs/options?roster=SP27&mode=ilr")).json()["options"]
            opt_subjs = {o["subject"] for o in opts}
            assert "ILRGL" in opt_subjs or "ILROB" in opt_subjs
