"""Tests for Cornell CS Electives, Technical Electives, External Spec, DB migrations, Gate & SSE refresh."""

from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiosqlite
import httpx
import pytest

from app.config import Settings
from app.db import Database
from app.main import create_app
from app.providers.base import CourseRecord, FetchResult, RosterRecord, SectionRecord, SubjectRecord
from app.providers.cornell import parse_cornell_classes_payload
from app.services.cs_requirements import (
    CSRequirementsIndex,
    decode_completed_courses,
    evaluate_prereq_node,
    expand_satisfied_courses,
    extract_prereq_codes,
    match_qualifying_prereq_text,
    normalize_completed_courses,
    parse_prereq_ast,
    strip_recommended_clauses,
)
from app.services.gate import PRIORITY_POLLER, PRIORITY_SEARCH, PRIORITY_WARMUP, CornellRequestGate


def _make_course(
    subject: str,
    nbr: str,
    title: str,
    units_min: float = 3.0,
    units_max: float = 3.0,
    grading_basis: str = "OPT",
    prereq: str = "",
    coreq: str = "",
    crosslists: list[tuple[str, str]] | None = None,
    component: str = "LEC",
    class_nbr: int = 1000,
    open_status: str = "C",
    acad_career: str = "UG",
    acad_group: str = "CI",
) -> CourseRecord:
    combos = [{"subject": s, "catalogNbr": n, "type": "B"} for (s, n) in (crosslists or [])]
    return CourseRecord(
        roster="SP27",
        subject=subject,
        catalog_nbr=nbr,
        title_short=title[:30],
        title_long=title,
        description=f"{title} description.",
        crse_id=class_nbr + 300000,
        enroll_groups=[
            {
                "unitsMinimum": units_min,
                "unitsMaximum": units_max,
                "gradingBasis": grading_basis,
                "simpleCombinations": combos,
                "componentsRequired": [component],
                "classSections": [{"ssrComponent": component, "classNbr": class_nbr, "openStatus": open_status}],
            }
        ],
        sections=[
            SectionRecord(
                class_nbr=class_nbr,
                enroll_group_idx=0,
                ssr_component=component,
                section="001",
                open_status=open_status,
                components_required=[component],
                meetings_summary="TR 10:10AM-11:25AM",
                instructors_summary="Ada Lovelace",
                campus="MAIN",
                instruction_mode="In Person",
            )
        ],
        acad_career=acad_career,
        acad_group=acad_group,
        catalog_prereq=prereq,
        catalog_coreq=coreq,
    )


class RichCSFakeProvider:
    """Deterministic fake provider covering real Cornell CS / TE / ExtSpec / edge-case offerings."""

    def __init__(self) -> None:
        self.rosters = [RosterRecord(slug="SP27", descr="Spring 2027", is_default=True, strm="2951")]
        self.subjects = [
            SubjectRecord(value="CS", descr="Computer Science"),
            SubjectRecord(value="MATH", descr="Mathematics"),
            SubjectRecord(value="ORIE", descr="Operations Research"),
            SubjectRecord(value="ECON", descr="Economics"),
            SubjectRecord(value="INFO", descr="Information Science"),
            SubjectRecord(value="BIOMG", descr="Molecular Biology"),
            SubjectRecord(value="ECE", descr="Electrical & Computer Engr"),
            SubjectRecord(value="PE", descr="Physical Education"),
        ]
        self.courses_by_bucket: dict[tuple[str, str], list[CourseRecord]] = {
            ("SP27", "CS"): [
                _make_course("CS", "2110", "OOP and Data Structures", 4.0, 4.0, "OPI", prereq="CS 1110.", class_nbr=1001, crosslists=[("ENGRD", "2110")]),
                _make_course("CS", "2770", "Computational Sustainability", 3.0, 3.0, "OPT", prereq="CS 1110.", class_nbr=1002, crosslists=[("INFO", "2770")]),
                _make_course("CS", "3110", "Functional Programming", 4.0, 4.0, "GRI", prereq="CS 2110.", class_nbr=1003),
                _make_course("CS", "3420", "Embedded Systems", 4.0, 4.0, "GRD", prereq="ECE 2300 or ENGRD 2300.", class_nbr=1004, crosslists=[("ECE", "3140")]),
                _make_course("CS", "3700", "Foundations of AI", 3.0, 3.0, "OPI", prereq="CS 2110 and CS 2800.", class_nbr=1005, crosslists=[("CS", "5700")]),
                _make_course("CS", "3780", "Intro to Machine Learning", 4.0, 4.0, "OPT", prereq="MATH 2940, CS 2110.", class_nbr=1006, crosslists=[("CS", "5780")]),
                _make_course("CS", "4090", "Teaching Experience in CS", 1.0, 4.0, "SUS", component="IND", class_nbr=1007),
                _make_course("CS", "4121", "Practicum in Compilers", 2.0, 2.0, "GRD", prereq="CS 4120.", class_nbr=1008),
                _make_course("CS", "4300", "Language and Information", 3.0, 3.0, "GRI", prereq="CS 2110.", class_nbr=1009, crosslists=[("INFO", "4300")]),
                _make_course("CS", "4410", "Operating Systems", 3.0, 3.0, "GRI", prereq="CS 3410.", class_nbr=1010, crosslists=[("CS", "5410")]),
                _make_course("CS", "4782", "Intro to Deep Learning", 4.0, 4.0, "OPI", prereq="CS 3780.", class_nbr=1011, open_status="O"),
                _make_course("CS", "4820", "Analysis of Algorithms", 4.0, 4.0, "OPI", prereq="CS 2800 and CS 3110.", class_nbr=1012, crosslists=[("CS", "5820")]),
                _make_course("CS", "4997", "Practical Training", 0.25, 0.25, "SUI", component="IND", class_nbr=1013),
                _make_course("CS", "4998", "Team Projects", 1.0, 4.0, "OPI", component="PRJ", class_nbr=1014),
                _make_course("CS", "4999", "Independent Reading and Research", 1.0, 4.0, "OPT", component="IND", class_nbr=1015),
                _make_course("CS", "5410", "Operating Systems", 3.0, 3.0, "GRI", prereq="CS 3410.", class_nbr=1016, crosslists=[("CS", "4410")], acad_career="GR"),
                _make_course("CS", "5780", "Intro to Machine Learning", 4.0, 4.0, "OPT", prereq="MATH 2940.", class_nbr=1017, crosslists=[("CS", "3780")], acad_career="GR"),
                _make_course("CS", "5820", "Analysis of Algorithms", 4.0, 4.0, "OPI", prereq="CS 3110.", class_nbr=1018, crosslists=[("CS", "4820")], acad_career="GR"),
                _make_course("CS", "5150", "Software Engineering", 4.0, 4.0, "GRI", prereq="CS 2110.", class_nbr=1019, acad_career="GR"),
                _make_course("CS", "7090", "CS Colloquium", 1.0, 1.0, "SUS", class_nbr=1020, acad_career="GR"),
            ],
            ("SP27", "MATH"): [
                _make_course("MATH", "1110", "Calculus I", 4.0, 4.0, "OPT", class_nbr=2001, acad_group="AS"),
                _make_course("MATH", "1920", "Multivariable Calculus", 4.0, 4.0, "OPT", prereq="MATH 1910.", class_nbr=2002, acad_group="EN"),
                _make_course("MATH", "2940", "Linear Algebra for Engineers", 4.0, 4.0, "GRD", prereq="MATH 1920.", class_nbr=2003, acad_group="EN"),
                _make_course("MATH", "3110", "Intro to Analysis", 4.0, 4.0, "OPT", prereq="MATH 1920 or 2220.", class_nbr=2004, acad_group="AS"),
            ],
            ("SP27", "ORIE"): [
                _make_course("ORIE", "3300", "Optimization I", 4.0, 4.0, "OPT", prereq="MATH 2940.", class_nbr=3001, acad_group="EN"),
                _make_course("ORIE", "3310", "Optimization II", 4.0, 4.0, "OPT", prereq="ORIE 3300.", class_nbr=3002, acad_group="EN"),
                _make_course("ORIE", "4126", "Practical Tools for Ops Research", 3.0, 3.0, "OPT", prereq="ORIE 3310.", class_nbr=3003, acad_group="EN"),
            ],
            ("SP27", "ECON"): [
                _make_course("ECON", "1110", "Intro Microeconomics", 3.0, 3.0, "OPT", class_nbr=4001, acad_group="AS"),
                _make_course("ECON", "3010", "Microeconomic Topics", 3.0, 3.0, "OPT", prereq="ECON 1110.", class_nbr=4002, acad_group="AS"),
                _make_course("ECON", "3110", "Probability Models and Inference", 4.0, 4.0, "OPT", prereq="MATH 1110.", class_nbr=4003, acad_group="AS"),
                _make_course("ECON", "3120", "Applied Econometrics", 4.0, 4.0, "OPT", prereq="ECON 3110 or ECON 3130.", class_nbr=4004, acad_group="AS"),
                _make_course("ECON", "3130", "Statistics and Probability", 4.0, 4.0, "OPT", prereq="Multivariable calculus.", class_nbr=4005, acad_group="AS"),
            ],
            ("SP27", "INFO"): [
                _make_course("INFO", "3152", "Intro Game Architecture", 4.0, 4.0, "OPI", prereq="", coreq="ENGRC 3152.", crosslists=[("CS", "3152")], class_nbr=5001),
                _make_course("INFO", "4300", "Language and Information", 3.0, 3.0, "GRI", prereq="CS 2110.", crosslists=[("CS", "4300")], class_nbr=5002),
                _make_course("INFO", "4470", "Human-AI Interaction Design", 3.0, 3.0, "GRI", prereq="CS 3780.", class_nbr=5003),
                _make_course("INFO", "4900", "Independent Reading and Research", 1.0, 4.0, "OPT", prereq="Recommended: CS 2110.", component="IND", class_nbr=5004),
                _make_course("INFO", "4910", "Teaching in Information Science", 1.0, 4.0, "SUS", component="IND", class_nbr=5005),
                _make_course("INFO", "4940", "Special Topics in Information Science", 3.0, 3.0, "OPT", prereq="No statistics background required.", class_nbr=5006),
                _make_course("INFO", "4998", "Team Projects", 1.0, 4.0, "OPT", component="PRJ", class_nbr=5007),
                _make_course("INFO", "5555", "Health Tech Short Course", 2.0, 2.0, "OPT", prereq="CS 2110.", class_nbr=5008),
            ],
            ("SP27", "BIOMG"): [
                _make_course("BIOMG", "3300", "Principles of Biochemistry", 4.0, 4.0, "GRD", prereq="One year of college-level introductory biology.", class_nbr=6001, acad_group="AG"),
                _make_course("BIOMG", "4380", "RNA in Biology and Medicine", 3.0, 3.0, "GRD", prereq="BIOMG 3300.", class_nbr=6002, acad_group="AG"),
            ],
            ("SP27", "ECE"): [
                _make_course("ECE", "2300", "Digital Logic and Computer Org", 4.0, 4.0, "GRD", prereq="CS 1110.", class_nbr=7001, acad_group="EN", crosslists=[("ENGRD", "2300")]),
                _make_course("ECE", "3140", "Embedded Systems", 4.0, 4.0, "GRD", prereq="ECE 2300 or any ENGRD course.", class_nbr=7002, acad_group="EN", crosslists=[("CS", "3420")]),
            ],
            ("SP27", "PE"): [
                _make_course("PE", "3210", "Advanced Rock Climbing", 3.0, 3.0, "OPT", class_nbr=8001),
            ],
        }

    async def fetch_rosters(self) -> list[RosterRecord]:
        return deepcopy(self.rosters)

    async def fetch_subjects(self, roster: str) -> list[SubjectRecord]:
        return deepcopy(self.subjects)

    async def fetch_subject_classes(self, roster: str, subject: str) -> FetchResult:
        courses = deepcopy(self.courses_by_bucket.get((roster.upper(), subject.upper()), []))
        return FetchResult(courses=courses, rtt_ms=10, payload_bytes=4096)

    async def close(self) -> None:
        return None


def test_parse_cornell_metadata_and_crosslists() -> None:
    payload = {
        "status": "success",
        "data": {
            "classes": [
                {
                    "subject": "CS",
                    "catalogNbr": "3420",
                    "titleShort": "Embedded Systems",
                    "titleLong": "Embedded Systems",
                    "description": "Low-level systems.",
                    "crseId": 351234,
                    "acadCareer": "UG",
                    "acadGroup": "CI",
                    "catalogPrereq": "ECE 2300 or ENGRD 2300.",
                    "catalogCoreq": "",
                    "catalogForbiddenOverlaps": "None.",
                    "crseAttrValueGroups": [{"attrDescr": "Distr", "crseAttrValues": "(SMR-AS)"}],
                    "enrollGroups": [
                        {
                            "unitsMinimum": 4.0,
                            "unitsMaximum": 4.0,
                            "gradingBasis": "GRD",
                            "simpleCombinations": [{"subject": "ECE", "catalogNbr": "3140", "type": "B"}],
                            "componentsRequired": ["LEC", "LAB"],
                            "classSections": [
                                {"ssrComponent": "LEC", "section": "001", "classNbr": 1234, "openStatus": "O", "meetings": []}
                            ],
                        }
                    ],
                }
            ]
        },
    }
    courses = parse_cornell_classes_payload(json.dumps(payload).encode("utf-8"), "SP27")
    assert len(courses) == 1
    c = courses[0]
    assert c.acad_career == "UG"
    assert c.acad_group == "CI"
    assert c.catalog_prereq == "ECE 2300 or ENGRD 2300."
    assert c.catalog_num == 3420
    assert c.units_min == 4.0
    assert c.units_max == 4.0
    assert c.has_letter_grade is True
    assert c.crosslists == ["ECE 3140"]
    assert c.components == ["LEC"]


def test_prereq_sanitizer_and_extractor() -> None:
    s1 = strip_recommended_clauses("CS 2110. Recommended: CS 2800 and MATH 2940.")
    assert "2800" not in s1
    assert "CS 2110" in s1

    s2 = strip_recommended_clauses("Recommended: CS 2110. Corequisite: MATH 2940.")
    assert "CS 2110" not in s2
    assert "MATH 2940" in s2

    s3 = strip_recommended_clauses("Prerequisite: MATH 1110 (MATH 1920 recommended).")
    assert "1920" not in s3
    assert "MATH 1110" in s3

    codes, has_engrd = extract_prereq_codes("MATH 1920, 2220 or 2940; any ENGRD course")
    assert has_engrd is True
    assert codes == ["MATH 1920", "MATH 2220", "MATH 2940"]

    assert match_qualifying_prereq_text("Multivariable calculus and probability") == [
        "Second-semester+ calculus",
        "Probability / statistics",
    ]
    assert match_qualifying_prereq_text("No statistics background required; differential calculus") == []
    assert match_qualifying_prereq_text("One year of college-level introductory biology") == ["College-level biology"]


@pytest.mark.asyncio
async def test_legacy_db_migration_preserves_data_and_resets_stale_subjects(tmp_path: Path) -> None:
    db_file = tmp_path / "legacy.db"
    async with aiosqlite.connect(db_file) as conn:
        await conn.executescript(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                priority_tier INTEGER NOT NULL DEFAULT 1,
                discord_user_id TEXT,
                discord_ping_enabled INTEGER NOT NULL DEFAULT 1,
                personal_webhook_url TEXT,
                web_push_enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE subjects (
                roster TEXT NOT NULL,
                value TEXT NOT NULL,
                descr TEXT NOT NULL,
                synced_at TEXT,
                PRIMARY KEY (roster, value)
            );
            CREATE TABLE courses_meta (
                roster TEXT NOT NULL,
                subject TEXT NOT NULL,
                catalog_nbr TEXT NOT NULL,
                title_short TEXT NOT NULL,
                title_long TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                crse_id INTEGER,
                enroll_groups_json TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (roster, subject, catalog_nbr)
            );
            INSERT INTO users (username, password_hash, role) VALUES ('tyler', 'hash', 'admin');
            INSERT INTO subjects (roster, value, descr, synced_at) VALUES ('SP27', 'CS', 'Computer Science', '2026-11-01 00:00:00');
            INSERT INTO courses_meta (roster, subject, catalog_nbr, title_short, title_long, enroll_groups_json)
            VALUES ('SP27', 'CS', '4820', 'Algo', 'Algorithms', '[]');
            """
        )
        await conn.commit()

    db = Database(db_file)
    await db.connect()
    try:
        cols = await db.fetch_all("PRAGMA table_info(courses_meta)")
        col_names = {c["name"] for c in cols}
        assert {"acad_group", "catalog_prereq", "catalog_num", "units_max", "has_letter_grade", "crosslists_json"} <= col_names

        user = await db.fetch_one("SELECT username FROM users WHERE username = 'tyler'")
        assert user is not None

        subj = await db.fetch_one("SELECT synced_at FROM subjects WHERE roster = 'SP27' AND value = 'CS'")
        assert subj is not None and subj["synced_at"] is None
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_cornell_request_gate_prioritizes_poller() -> None:
    gate = CornellRequestGate()
    order: list[str] = []

    async with gate.slot(PRIORITY_SEARCH, min_interval_sec=0.0):
        # Launch warmup & search BEFORE poller while gate is occupied; poller must still jump first
        async def wait_and_log(prio: int, label: str) -> None:
            async with gate.slot(prio, min_interval_sec=0.0):
                order.append(label)

        t_warm = asyncio.create_task(wait_and_log(PRIORITY_WARMUP, "warmup"))
        await asyncio.sleep(0.01)
        t_search = asyncio.create_task(wait_and_log(PRIORITY_SEARCH, "search"))
        await asyncio.sleep(0.01)
        t_poller = asyncio.create_task(wait_and_log(PRIORITY_POLLER, "poller"))
        await asyncio.sleep(0.01)
        assert gate.poller_is_pending() is True

    await asyncio.gather(t_warm, t_search, t_poller)
    assert order == ["poller", "search", "warmup"]

    # Ensure steady PRIORITY_POLLER ticks do not starve PRIORITY_WARMUP min_interval_sec catalog pacing
    gate2 = CornellRequestGate()
    async with gate2.slot(PRIORITY_POLLER, min_interval_sec=0.0):
        pass

    async def run_warmup_slot() -> None:
        async with gate2.slot(PRIORITY_WARMUP, min_interval_sec=1.25):
            order.append("warmup_after_poller")

    await asyncio.wait_for(run_warmup_slot(), timeout=0.2)
    assert order[-1] == "warmup_after_poller"


@pytest.mark.asyncio
async def test_cs_requirements_filters_multi_select_and_sse_lazy_refresh(tmp_path: Path) -> None:
    settings = Settings(
        app_domain="sniper.hodgman.net",
        app_origin="https://sniper.hodgman.net",
        data_dir=tmp_path / "data",
        static_dir=tmp_path / "static",
        enable_background_workers=False,
    )
    settings.ensure_persisted_secrets()
    provider = RichCSFakeProvider()
    app = create_app(custom_settings=settings, custom_provider=provider)

    async with app.router.lifespan_context(app):
        # Sync all test subjects into catalog so prereq BFS sees every department cleanly
        await app.state.catalog.sync_rosters_and_subjects("SP27")
        await app.state.catalog.sync_full_roster("SP27", delay_sec=0.0)

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="https://sniper.hodgman.net") as client:
            await client.post("/api/auth/bootstrap", json={"username": "tyler", "password": "password123"})

            # 1) CS Electives (Post-Fall 2024 default vs Pre-Fall 2024)
            cs_cur = (
                await client.get(
                    "/api/courses/search",
                    params={"roster": "SP27", "cs_requirement": "cs_elective", "curriculum": "current"},
                )
            ).json()["courses"]
            cs_cur_codes = {f"{c['subject']} {c['catalog_nbr']}": c for c in cs_cur}
            assert {"CS 3700", "CS 3780", "CS 4300", "CS 4782", "CS 5150", "CS 5780"} <= set(cs_cur_codes.keys())
            assert "NOT used for CS Core" in cs_cur_codes["CS 3700"]["cs_eligibility"]["cs_elective_warning"]
            # Exclusions: fixed core + core crosslists + 4090/4997/4998/4999 + 2-cr practicum + 1-cr SUS colloquium
            for banned in ("CS 4410", "CS 4820", "CS 5410", "CS 5820", "CS 4090", "CS 4997", "CS 4998", "CS 4999", "CS 4121", "CS 7090"):
                assert banned not in cs_cur_codes

            cs_pre = (
                await client.get(
                    "/api/courses/search",
                    params={"roster": "SP27", "cs_requirement": "cs_elective", "curriculum": "pre2024"},
                )
            ).json()["courses"]
            cs_pre_codes = {f"{c['subject']} {c['catalog_nbr']}" for c in cs_pre}
            assert "CS 3700" not in cs_pre_codes
            assert "CS 3780" not in cs_pre_codes
            assert "CS 4782" in cs_pre_codes

            # 2) Technical Electives (defaults: 2000+ & CS 4999 included WITH warning badges!)
            te_all = (
                await client.get(
                    "/api/courses/search",
                    params={"roster": "SP27", "cs_requirement": "tech_elective", "limit": 200},
                )
            ).json()["courses"]
            te_by_code = {f"{c['subject']} {c['catalog_nbr']}": c for c in te_all}

            # Direct seeds, chains, bio, calc2+, ENGRD, and crosslist prereq propagation
            assert "ORIE 3310" in te_by_code
            assert "ORIE 4126" in te_by_code and "ORIE 3310" in te_by_code["ORIE 4126"]["cs_eligibility"]["tech_elective_reason"]
            assert "MATH 3110" in te_by_code  # via 'MATH 1920 or 2220' carried subject
            assert "ECON 3130" in te_by_code  # multivariable calculus text
            assert "ECON 3120" in te_by_code  # via ECON 3110
            assert "ECON 3110" not in te_by_code  # MATH 1110 alone rejected!
            assert "ECON 3010" not in te_by_code
            assert "BIOMG 3300" in te_by_code  # college-level bio text
            assert "BIOMG 4380" in te_by_code  # chain BIOMG 4380 -> BIOMG 3300
            assert "INFO 4470" in te_by_code and "CS 3780" in te_by_code["INFO 4470"]["cs_eligibility"]["tech_elective_reason"]
            assert "ECE 3140" in te_by_code  # ENGRD mention
            # INFO 4900 has Recommended only, INFO 4940 has negated stats -> rejected
            assert "INFO 4900" not in te_by_code
            assert "INFO 4940" not in te_by_code
            assert "CS 3110" not in te_by_code
            assert "CS 4820" not in te_by_code

            # Warning defaults on 2000+ (MATH 2940, CS 2770) & CS 4999 research
            assert "MATH 2940" in te_by_code
            assert "Max 1" in te_by_code["MATH 2940"]["cs_eligibility"]["tech_elective_warning"]
            assert "CS 4999" in te_by_code
            assert "Letter Grade" in te_by_code["CS 4999"]["cs_eligibility"]["tech_elective_warning"]

            # Can hide 2000+ & CS 4999 explicitly via flags
            te_strict = (
                await client.get(
                    "/api/courses/search",
                    params={
                        "roster": "SP27",
                        "cs_requirement": "tech_elective",
                        "include_2000_te": "false",
                        "include_research_te": "false",
                    },
                )
            ).json()["courses"]
            te_strict_codes = {f"{c['subject']} {c['catalog_nbr']}" for c in te_strict}
            assert "MATH 2940" not in te_strict_codes
            assert "CS 4999" not in te_strict_codes
            assert "ORIE 3310" in te_strict_codes

            # 3) External Specialization multi-select subject dropdown
            ext = (
                await client.get(
                    "/api/courses/search",
                    params={
                        "roster": "SP27",
                        "subjects": "ECON,INFO,CS,PE",
                        "level_min": 3000,
                        "cs_requirement": "external_spec",
                    },
                )
            ).json()["courses"]
            ext_by_code = {f"{c['subject']} {c['catalog_nbr']}": c for c in ext}
            assert "ECON 3010" in ext_by_code
            assert "ECON 3110" in ext_by_code
            assert "INFO 4940" in ext_by_code  # 3 cr OPT LEC Special Topics allowed!
            assert "INFO 4300" in ext_by_code
            assert "Cross-listed with CS 4300" in ext_by_code["INFO 4300"]["cs_eligibility"]["external_spec_warning"]

            # Banned in External Spec: CS*, PE*, <3000, <3cr, SUS/SUI, IND/PRJ research/teaching
            for banned in ("CS 4300", "PE 3210", "ECON 1110", "INFO 5555", "INFO 4900", "INFO 4910", "INFO 4998"):
                assert banned not in ext_by_code

            # 4) Lazy stale status refresh + SSE emission
            old_ts = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
            await app.state.db.execute(
                "UPDATE subjects SET synced_at = ? WHERE roster = 'SP27' AND value = 'ORIE'",
                (old_ts,),
            )

            # Flip ORIE 3310 open_status in upstream provider before refresh
            provider.courses_by_bucket[("SP27", "ORIE")][1].sections[0].open_status = "O"

            stale_res = (
                await client.get(
                    "/api/courses/search",
                    params={"roster": "SP27", "subjects": "ORIE"},
                )
            ).json()
            assert stale_res["courses"][0]["status_is_stale"] is True
            assert "ORIE" in stale_res["meta"]["queued_subjects"]

            # Subscribe to SSEHub and drain one refresh item
            async with app.state.sse_hub.subscribe(user_id=1, is_admin=True) as queue:
                await app.state.catalog.process_one_refresh(timeout_sec=1.0)
                evt = await asyncio.wait_for(queue.get(), timeout=1.0)
                assert evt["event"] == "catalog_subject_refreshed"
                assert evt["data"]["subject"] == "ORIE"
                assert evt["data"]["section_statuses"]["3002"] == "O"

            fresh_res = (
                await client.get(
                    "/api/courses/search",
                    params={"roster": "SP27", "subjects": "ORIE"},
                )
            ).json()
            assert fresh_res["courses"][0]["status_is_stale"] is False
            orie3310 = [c for c in fresh_res["courses"] if c["catalog_nbr"] == "3310"][0]
            assert orie3310["sections"][0]["open_status"] == "O"

            # 5) Actively polled bucket overrides old subjects.synced_at -> immediately fresh!
            await app.state.db.execute(
                "UPDATE subjects SET synced_at = ? WHERE roster = 'SP27' AND value = 'ECON'",
                (old_ts,),
            )
            await client.post(
                "/api/watches",
                json={"roster": "SP27", "subject": "ECON", "catalog_nbr": "3120", "class_nbr": 4004, "mode": "exact"},
            )
            await app.state.poller._refresh_buckets()
            await app.state.poller.poll_bucket("SP27", "ECON")
            econ_res = (
                await client.get("/api/courses/search", params={"roster": "SP27", "subjects": "ECON"})
            ).json()
            assert econ_res["courses"][0]["status_is_stale"] is False


def test_prereq_ast_boolean_and_edge_cases() -> None:
    # 1) CS 4300: Recommended clause ignored
    mode, node = parse_prereq_ast("CS 2110. Recommended prerequisite: CS 3300.")
    assert mode == "ast"
    ev_cs2110 = evaluate_prereq_node(mode, node, {"CS 2110"})
    assert ev_cs2110["prereq_status"] == "met"
    assert ev_cs2110["prereqs_met"] is True
    assert ev_cs2110["satisfied_by"] == ["CS 2110"]
    ev_empty = evaluate_prereq_node(mode, node, set())
    assert ev_empty["prereq_status"] == "unmet"
    assert ev_empty["missing_prereqs"] == "CS 2110"

    # 2) ORIE 4750: (ENGRD 2700 or BTRY 3080) AND CS 2110 (with static equivalents + crosslists)
    mode2, node2 = parse_prereq_ast("ENGRD 2700 or BTRY 3080, CS 2110 or equivalent.")
    assert mode2 == "ast"
    sat_orie, _ = expand_satisfied_courses(
        ["STSCI 3080", "ENGRD 2110"],
        crosslists_by_code={"ENGRD 2110": ["CS 2110"], "CS 2110": ["ENGRD 2110"]},
        include_implied=True,
    )
    assert evaluate_prereq_node(mode2, node2, sat_orie)["prereqs_met"] is True
    # Also verify crosslists work even when include_implied=False
    sat_cross_only, imp_off = expand_satisfied_courses(
        ["STSCI 3080", "ENGRD 2110"],
        crosslists_by_code={"ENGRD 2110": ["CS 2110"], "CS 2110": ["ENGRD 2110"]},
        include_implied=False,
    )
    assert imp_off == []
    assert evaluate_prereq_node(mode2, node2, sat_cross_only)["prereqs_met"] is True
    missing_cs = evaluate_prereq_node(mode2, node2, {"ENGRD 2700"})
    assert missing_cs["prereqs_met"] is False
    assert missing_cs["missing_prereqs"] == "CS 2110"

    # 3) ORIE 5126: OR chain across comma-or + implied CS 1110 from CS 2110
    mode3, node3 = parse_prereq_ast("CS 1110, CS 1112, OR INFO 2950.")
    assert mode3 == "ast"
    assert evaluate_prereq_node(mode3, node3, {"INFO 2950"})["prereqs_met"] is True
    sat_with_implied, implied = expand_satisfied_courses(["CS 2110"], include_implied=True)
    assert "CS 1110" in implied
    assert evaluate_prereq_node(mode3, node3, sat_with_implied)["prereqs_met"] is True
    sat_no_implied, implied_off = expand_satisfied_courses(["CS 2110"], include_implied=False)
    assert implied_off == []
    assert evaluate_prereq_node(mode3, node3, sat_no_implied)["prereqs_met"] is False

    # 4) CS 4152 multi-track: 'for programmers: CS 3110 or CS 2110; Prerequisites for designers: CS 1110'
    mode4, node4 = parse_prereq_ast(
        "Prerequisite for programmers: CS 3110 or CS 2110; Prerequisites for designers: CS 1110."
    )
    assert mode4 == "ast"
    assert evaluate_prereq_node(mode4, node4, {"CS 1110"})["prereqs_met"] is True

    # 5) BEE 4550 threshold: AtLeast(2)
    mode5, node5 = parse_prereq_ast("At least two of: CS 1110, CS 2110, ENGRD 2700.")
    assert mode5 == "ast"
    assert evaluate_prereq_node(mode5, node5, {"CS 1110", "ENGRD 2700"})["prereqs_met"] is True
    ev_one = evaluate_prereq_node(mode5, node5, {"CS 1110"})
    assert ev_one["prereqs_met"] is False
    assert "any 1 of" in ev_one["missing_prereqs"]

    # 6) AND/OR normalization (mixed and upper case)
    for raw in ("CS 2110 and/or CS 2800.", "CS 2110 AND / OR CS 2800."):
        m_andor, n_andor = parse_prereq_ast(raw)
        assert m_andor == "ast"
        assert evaluate_prereq_node(m_andor, n_andor, {"CS 2800"})["prereqs_met"] is True
        assert evaluate_prereq_node(m_andor, n_andor, {"CS 2110"})["prereqs_met"] is True

    # 7) Corequisites ignored in CSRequirementsIndex.evaluate_course_prereqs
    idx = CSRequirementsIndex(
        [
            {
                "subject": "CS",
                "catalog_nbr": "4120",
                "catalog_num": 4120,
                "catalog_prereq": "CS 3110.",
                "catalog_coreq": "CS 4121.",
                "crosslists": [],
                "units_min": 4.0,
                "units_max": 4.0,
                "has_letter_grade": True,
                "components": ["LEC"],
            }
        ]
    )
    coreq_eval = idx.evaluate_course_prereqs("CS", "4120", {"CS 3110"})
    assert coreq_eval["prereq_status"] == "met"
    assert coreq_eval["prereqs_met"] is True

    # 8) Prose-only requirement classified cleanly
    mode_p, node_p = parse_prereq_ast("Two semesters of college-level biology.")
    assert mode_p == "prose" and node_p is None
    ev_p = evaluate_prereq_node(mode_p, node_p, {"CS 2110", "CS 3110"})
    assert ev_p["prereq_status"] == "prose"
    assert ev_p["prereqs_met"] is False


@pytest.mark.asyncio
async def test_legacy_users_db_migration(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy_users.db"
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                priority_tier INTEGER NOT NULL DEFAULT 1,
                discord_user_id TEXT NOT NULL DEFAULT '',
                discord_ping_enabled INTEGER NOT NULL DEFAULT 1,
                personal_webhook_url TEXT NOT NULL DEFAULT '',
                web_push_enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        await conn.execute(
            "INSERT INTO users (username, password_hash, role, priority_tier) VALUES (?, ?, 'admin', 2)",
            ("legacy_admin", "hash123"),
        )
        await conn.commit()

    db = Database(db_path)
    await db.connect()
    try:
        cols = await db.fetch_all("PRAGMA table_info(users)")
        col_names = {c["name"] for c in cols}
        assert {"completed_courses_json", "include_implied_prereqs", "show_cs_features"} <= col_names
        row = await db.fetch_one(
            "SELECT completed_courses_json, include_implied_prereqs, show_cs_features FROM users WHERE username = 'legacy_admin'"
        )
        assert row is not None
        assert decode_completed_courses(row["completed_courses_json"]) == []
        assert row["include_implied_prereqs"] == 1
        assert row["show_cs_features"] == 1
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_per_user_prereqs_isolation_and_search_filtering(tmp_path: Path) -> None:
    settings = Settings(
        app_domain="sniper.hodgman.net",
        app_origin="https://sniper.hodgman.net",
        data_dir=tmp_path / "data",
        static_dir=tmp_path / "static",
        enable_background_workers=False,
    )
    settings.ensure_persisted_secrets()
    provider = RichCSFakeProvider()
    # Add an extra course with both a prereq AND a concurrent coreq to prove coreq does not block
    provider.courses_by_bucket[("SP27", "ORIE")].append(
        _make_course(
            "ORIE",
            "4130",
            "Simulation Modeling",
            3.0,
            3.0,
            "OPT",
            prereq="CS 2110.",
            coreq="ORIE 3510.",
            class_nbr=3004,
            acad_group="EN",
        )
    )
    app = create_app(custom_settings=settings, custom_provider=provider)

    async with app.router.lifespan_context(app):
        await app.state.catalog.sync_rosters_and_subjects("SP27")
        await app.state.catalog.sync_full_roster("SP27", delay_sec=0.0)

        transport = httpx.ASGITransport(app=app)
        async with (
            httpx.AsyncClient(transport=transport, base_url="https://sniper.hodgman.net") as client_a,
            httpx.AsyncClient(transport=transport, base_url="https://sniper.hodgman.net") as client_b,
        ):
            boot = await client_a.post("/api/auth/bootstrap", json={"username": "alice", "password": "password123"})
            assert boot.status_code == 201
            assert boot.json()["user"]["completed_courses"] == []
            assert boot.json()["user"]["include_implied_prereqs"] is True
            assert boot.json()["user"]["show_cs_features"] is True

            # User A creates an invite and User B registers on a separate client session
            inv = (await client_a.post("/api/admin/invites", json={"max_uses": 1, "expires_hours": 24, "note": "bob"})).json()
            reg = await client_b.post(
                "/api/auth/register",
                json={"invite_code": inv["invite"]["code"], "username": "bob", "password": "password123"},
            )
            assert reg.status_code == 201
            assert reg.json()["user"]["show_cs_features"] is True

            # User B hides CS-major-specific UI features; User A stays enabled
            pref_b = await client_b.put("/api/auth/preferences", json={"show_cs_features": False})
            assert pref_b.status_code == 200
            assert pref_b.json()["user"]["show_cs_features"] is False
            assert (await client_b.get("/api/auth/me")).json()["user"]["show_cs_features"] is False
            assert (await client_a.get("/api/auth/me")).json()["user"]["show_cs_features"] is True

            # User A sets prereqs (with lowercase/no-space code to verify normalization)
            put_a = await client_a.put(
                "/api/user/prereqs?roster=SP27",
                json={"completed_courses": ["cs2110", "MATH 1920", "cs 2110"], "include_implied_prereqs": True},
            )
            assert put_a.status_code == 200
            data_a = put_a.json()
            assert data_a["completed_courses"] == ["CS 2110", "MATH 1920"]
            assert data_a["include_implied_prereqs"] is True
            assert {"CS 1110", "MATH 1910"} <= set(data_a["implied_courses"])

            # /api/auth/me reflects persisted prereqs for User A
            me_a = (await client_a.get("/api/auth/me")).json()["user"]
            assert me_a["completed_courses"] == ["CS 2110", "MATH 1920"]
            assert me_a["include_implied_prereqs"] is True

            # User B remains completely isolated with empty prereqs
            me_b = (await client_b.get("/api/auth/me")).json()["user"]
            assert me_b["completed_courses"] == []
            get_b = (await client_b.get("/api/user/prereqs?roster=SP27")).json()
            assert get_b["completed_courses"] == []
            assert get_b["implied_courses"] == []

            # User B saves different prereqs and disables implied foundations
            put_b = await client_b.put(
                "/api/user/prereqs?roster=SP27",
                json={"completed_courses": ["CS 3410"], "include_implied_prereqs": False},
            )
            assert put_b.status_code == 200
            assert put_b.json() == {
                "completed_courses": ["CS 3410"],
                "include_implied_prereqs": False,
                "implied_courses": [],
            }
            # User A still intact
            assert (await client_a.get("/api/user/prereqs?roster=SP27")).json()["completed_courses"] == [
                "CS 2110",
                "MATH 1920",
            ]

            # Search Technical Electives with only_eligible=true for User A
            te_elig = (
                await client_a.get(
                    "/api/courses/search",
                    params={"roster": "SP27", "cs_requirement": "tech_elective", "only_eligible": "true", "limit": 200},
                )
            ).json()
            elig_by_code = {f"{c['subject']} {c['catalog_nbr']}": c for c in te_elig["courses"]}
            assert te_elig["meta"]["total_matched"] == len(te_elig["courses"])

            # Met via CS 2110 / MATH 1920 / implied CS 1110 / no prereqs / non-blocking coreq ORIE 3510
            assert "CS 4300" in elig_by_code
            assert elig_by_code["CS 4300"]["cs_eligibility"]["prereq_status"] == "met"
            assert "MATH 2940" in elig_by_code  # MATH 1920 prereq met!
            assert "MATH 3110" in elig_by_code  # MATH 1920 or 2220 met!
            assert "CS 2770" in elig_by_code    # CS 1110 implied via CS 2110!
            assert "ORIE 4130" in elig_by_code  # CS 2110 met; concurrent coreq ORIE 3510 ignored!
            assert "CS 4999" in elig_by_code and elig_by_code["CS 4999"]["cs_eligibility"]["prereq_status"] == "none"

            # Validation rejects malformed course codes with 422
            bad_put = await client_a.put(
                "/api/user/prereqs",
                json={"completed_courses": ["NOT_A_COURSE"]},
            )
            assert bad_put.status_code == 422

            # Unmet or prose-only TEs filtered out cleanly
            for excluded in ("CS 3700", "CS 3780", "CS 4782", "ORIE 3300", "ORIE 3310", "BIOMG 3300", "ECON 3130"):
                assert excluded not in elig_by_code

            # Verify User A sees missing_prereqs metadata when only_eligible=false
            te_all_a = (
                await client_a.get(
                    "/api/courses/search",
                    params={"roster": "SP27", "cs_requirement": "tech_elective", "only_eligible": "false", "limit": 200},
                )
            ).json()["courses"]
            all_a_by_code = {f"{c['subject']} {c['catalog_nbr']}": c for c in te_all_a}
            assert all_a_by_code["CS 3700"]["cs_eligibility"]["prereq_status"] == "unmet"
            assert all_a_by_code["CS 3700"]["cs_eligibility"]["missing_prereqs"] == "CS 2800"
            assert all_a_by_code["BIOMG 3300"]["cs_eligibility"]["prereq_status"] == "prose"

            # Verify All Courses mode with only_eligible=true returns only prereqs_met courses for User B
            all_elig_b = (
                await client_b.get(
                    "/api/courses/search",
                    params={"roster": "SP27", "cs_requirement": "", "only_eligible": "true", "limit": 200},
                )
            ).json()
            b_codes = {f"{c['subject']} {c['catalog_nbr']}" for c in all_elig_b["courses"]}
            assert all_elig_b["meta"]["total_matched"] == len(all_elig_b["courses"])
            assert "CS 4410" in b_codes   # prereq CS 3410 met by Bob
            assert "CS 3110" not in b_codes  # needs CS 2110 (Bob doesn't have it)
            assert "CS 4300" not in b_codes

            # Local prereq options autocomplete works cleanly
            opts = (await client_a.get("/api/user/prereqs/options", params={"roster": "SP27", "q": "211"})).json()
            assert any(o["code"] == "CS 2110" for o in opts["options"])


def test_te_reason_clarity_crosslist_priority_and_no_cycle() -> None:
    def _row(
        subject: str,
        nbr: str,
        prereq: str = "",
        coreq: str = "",
        crosslists: list[str] | None = None,
    ) -> dict:
        return {
            "subject": subject,
            "catalog_nbr": nbr,
            "catalog_num": int("".join(ch for ch in nbr if ch.isdigit()) or "0"),
            "title_long": f"{subject} {nbr}",
            "catalog_prereq": prereq,
            "catalog_coreq": coreq,
            "crosslists": crosslists or [],
            "units_min": 3.0,
            "units_max": 3.0,
            "has_letter_grade": True,
            "components": ["LEC"],
        }

    idx = CSRequirementsIndex(
        [
            _row("CHEM", "4810", prereq="MATH 2220.", crosslists=["CHEME 5540"]),
            _row("CHEME", "5540", prereq="background equivalent to: CS 1110 or CS 1112.", crosslists=["CHEM 4810"]),
            _row("AAA", "4000", prereq="MATH 2220.", crosslists=["ZZZ 4000"]),
            _row("ZZZ", "4000", prereq="CS 2110.", crosslists=["AAA 4000"]),
            _row("CS", "4152", prereq="CS 2110.", crosslists=["INFO 4152"]),
            _row("INFO", "4152", prereq="CS 2110.", crosslists=["CS 4152"]),
            _row("CHEM", "2070", coreq="CHEM 2071."),
            _row("CHEM", "2071", prereq="CHEM 2070."),
        ]
    )

    # Cross-listed TE reason is clearly labeled as a TE rule and does not poison enrollment prereq check
    cheme = idx.get("CHEME", "5540")
    assert cheme.tech_elective is True
    assert cheme.tech_elective_reason == "TE rule: cross-listed CHEM 4810 lists MATH 2220 prereq"
    sat, _ = idx.expand_satisfied_courses(["CS 1110"])
    ev = idx.evaluate_course_prereqs("CHEME", "5540", sat)
    assert ev["prereqs_met"] is True
    assert ev["satisfied_by"] == ["CS 1110"]

    # Pass 0a runs before Pass 0b: alphabetically later sibling keeps its own direct TE reason
    aaa = idx.get("AAA", "4000")
    zzz = idx.get("ZZZ", "4000")
    assert aaa.tech_elective is True
    assert aaa.tech_elective_reason == "TE rule: lists MATH 2220 prereq"
    assert zzz.tech_elective is True
    assert zzz.tech_elective_reason == "TE rule: lists CS 2110 prereq"

    # CS 3000+ course reports direct auto-qualification instead of cross-list/prereq noise
    cs_4152 = idx.get("CS", "4152")
    assert cs_4152.tech_elective is True
    assert cs_4152.tech_elective_reason == "CS 3000+ course (auto-qualifies as Tech Elective)"

    # Coreq/prereq cycle does not produce bogus TE chain back onto CHEM 2070 itself
    assert idx.get("CHEM", "2070").tech_elective is False
    chem_2071 = idx.get("CHEM", "2071")
    assert chem_2071.tech_elective is True
    assert chem_2071.tech_elective_reason == "TE rule: lists CHEM 2070 prereq"


