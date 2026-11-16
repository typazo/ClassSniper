"""Tests for Cornell minor definitions, evaluation, completed-part hiding, and API endpoints."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from app.config import Settings
from app.main import create_app
from app.providers.base import CourseRecord, FetchResult, RosterRecord, SectionRecord, SubjectRecord
from app.services.minors import (
    build_minors_catalog,
    course_matches_minor_filter,
    evaluate_course_for_minor,
    normalize_minor_prefs,
    suggest_completed_categories,
)
from app.services.minors_data import MINORS_BY_ID


def _make_course_record(
    subject: str,
    nbr: str,
    title: str,
    *,
    units_min: float = 3.0,
    units_max: float = 3.0,
    grading_basis: str = "OPT",
    components: list[str] | None = None,
    crosslists: list[tuple[str, str]] | None = None,
    class_nbr: int = 2000,
    roster: str = "SP27",
) -> CourseRecord:
    comps = components or ["LEC"]
    combos = [{"subject": s, "catalogNbr": n, "type": "B"} for (s, n) in (crosslists or [])]
    return CourseRecord(
        roster=roster,
        subject=subject,
        catalog_nbr=nbr,
        title_short=title[:30],
        title_long=title,
        description=f"{title} catalog description.",
        crse_id=class_nbr + 500000,
        enroll_groups=[
            {
                "unitsMinimum": units_min,
                "unitsMaximum": units_max,
                "gradingBasis": grading_basis,
                "simpleCombinations": combos,
                "componentsRequired": comps,
                "classSections": [
                    {"ssrComponent": comps[0], "classNbr": class_nbr, "openStatus": "O"}
                ],
            }
        ],
        sections=[
            SectionRecord(
                class_nbr=class_nbr,
                enroll_group_idx=0,
                ssr_component=comps[0],
                section="001",
                open_status="O",
                components_required=comps,
                meetings_summary="TR 10:10AM-11:25AM",
                instructors_summary="Faculty Member",
                campus="MAIN",
                location="ITH",
                location_descr="Ithaca",
                instruction_mode="In Person",
            )
        ],
        acad_career="UG",
        acad_group="AS",
        crse_attrs=[],
    )


class MinorsFakeProvider:
    """Deterministic fake provider containing representative courses for all 7 minors."""

    def __init__(self) -> None:
        self.courses: list[CourseRecord] = [
            _make_course_record("PHIL", "2990", "Philosophy of Law", class_nbr=2001),
            _make_course_record("GOVT", "3121", "Crime and Punishment", crosslists=[("AMST", "3121")], class_nbr=2002),
            _make_course_record("ECON", "1110", "Introductory Microeconomics", class_nbr=2003),
            _make_course_record("AEM", "3100", "Business Statistics", class_nbr=2004),
            _make_course_record("AEM", "3249", "Entrepreneurial Marketing & Strategy", class_nbr=2005),
            _make_course_record("AEM", "4970", "Individual Study in AEM", components=["IND"], class_nbr=2006),
            _make_course_record("NS", "2600", "Introduction to Global Health", class_nbr=2007),
            _make_course_record("ILRGL", "2010", "Labor & Employment Law", class_nbr=2008),
            _make_course_record("ILRGL", "4990", "Directed Studies", components=["IND"], class_nbr=2009),
            _make_course_record("HIST", "1510", "History of Modern Europe", components=["LEC"], units_max=4.0, class_nbr=2010),
            _make_course_record("HIST", "2660", "Seminar in American Law", components=["SEM"], units_max=4.0, class_nbr=2011),
            _make_course_record("HIST", "1100", "FWS: Empires and Maps", components=["SEM"], units_max=3.0, class_nbr=2012),
            _make_course_record("HIST", "4001", "Honors Seminar", components=["SEM"], units_max=4.0, class_nbr=2013),
            _make_course_record("INFO", "1200", "Information Ethics, Law, and Policy", class_nbr=2014),
            _make_course_record("INFO", "1300", "Introductory Design and Programming for the Web", class_nbr=2023),
            _make_course_record("INFO", "4470", "HCI Seminar 2026-27 Update", class_nbr=2015),
            _make_course_record("COMM", "3190", "Communicating Emerging Tech", class_nbr=2016),
            _make_course_record("SOC", "4390", "Social Networks Seminar", class_nbr=2017),
            _make_course_record("HADM", "3740", "Fundamentals of Database Mgmt", class_nbr=2024),
            _make_course_record("AEM", "3220", "Digital Business Strategy", class_nbr=2025),
            _make_course_record("PSYCH", "1101", "Introduction to Psychology", class_nbr=2018),
            _make_course_record("PSYCH", "3140", "Computational Psychology", class_nbr=2019),
            _make_course_record("PSYCH", "2090", "Developmental Psychology", class_nbr=2020),
            _make_course_record("PSYCH", "4700", "Undergraduate Research", grading_basis="SUX", components=["IND"], units_max=3.0, class_nbr=2021),
            _make_course_record("PSYCH", "1120", "FWS: Writing About Mind", components=["SEM"], units_max=3.0, class_nbr=2022),
        ]

    async def fetch_rosters(self) -> list[RosterRecord]:
        return [RosterRecord(slug="SP27", descr="Spring 2027", is_default=True, archive_mode=False, strm="2951")]

    async def fetch_subjects(self, roster: str) -> list[SubjectRecord]:
        seen: dict[str, str] = {}
        for c in self.courses:
            seen[c.subject] = c.subject
        return [SubjectRecord(value=s, descr=s) for s in sorted(seen)]

    async def fetch_subject_classes(self, roster: str, subject: str) -> FetchResult:
        return FetchResult(
            courses=[c for c in self.courses if c.subject == subject],
            rtt_ms=1,
            payload_bytes=256,
        )

    async def fetch_course_details(self, roster: str, subject: str, crse_id: int) -> dict | None:
        return None

    async def close(self) -> None:
        return None


def test_law_society_wildcard_and_aliases() -> None:
    phil2990 = {"subject": "PHIL", "catalog_nbr": "2990", "components": ["LEC"], "has_letter_grade": True}
    ev = evaluate_course_for_minor(phil2990, "law_society", "standard")
    assert ev is not None
    assert set(ev["matched_categories"]) == {
        "legal_institutions",
        "law_policy",
        "law_social_structure",
        "law_culture",
        "law_ethics",
    }

    # Visible while at least one category remains uncompleted; hidden when all 5 are checked done.
    ev_four_done = evaluate_course_for_minor(
        phil2990,
        "law_society",
        "standard",
        completed_categories={"legal_institutions", "law_policy", "law_social_structure", "law_culture"},
    )
    assert course_matches_minor_filter(ev_four_done, hide_completed=True) is True
    ev_all_done = evaluate_course_for_minor(
        phil2990,
        "law_society",
        "standard",
        completed_categories=set(ev["matched_categories"]),
    )
    assert course_matches_minor_filter(ev_all_done, hide_completed=True) is False
    assert course_matches_minor_filter(ev_all_done, hide_completed=False) is True

    # Historical PAM rename maps to PUBPOL automatically
    pam_course = {"subject": "PAM", "catalog_nbr": "3172", "components": ["LEC"], "has_letter_grade": True}
    ev_pam = evaluate_course_for_minor(pam_course, "law_society", "standard")
    assert ev_pam is not None
    assert "legal_institutions" in ev_pam["matched_categories"]


def test_business_versions_and_dynamic_rules() -> None:
    aem3249 = {"subject": "AEM", "catalog_nbr": "3249", "components": ["LEC"], "has_letter_grade": True, "units_max": 3.0}
    aem4970 = {"subject": "AEM", "catalog_nbr": "4970", "components": ["IND"], "has_letter_grade": True, "units_max": 3.0}
    aem3100 = {"subject": "AEM", "catalog_nbr": "3100", "components": ["LEC"], "has_letter_grade": True, "units_max": 3.0}

    assert "bme_career_goals" in (evaluate_course_for_minor(aem3249, "business", "bme") or {})["matched_categories"]
    assert evaluate_course_for_minor(aem4970, "business", "bme") is None

    ev_3100 = evaluate_course_for_minor(aem3100, "business", "bme")
    assert ev_3100 is not None
    assert any("ORIE 3300/3500" in w for w in ev_3100["warnings"])

    aem4661 = {"subject": "AEM", "catalog_nbr": "4661", "components": ["LEC"], "has_letter_grade": True}
    ev_dbmls = evaluate_course_for_minor(aem4661, "business", "dbmls")
    assert ev_dbmls is not None
    assert "dbmls_capstone" in ev_dbmls["matched_categories"]


def test_inequality_lsj_and_history_rules() -> None:
    ns2600 = {"subject": "NS", "catalog_nbr": "2600", "components": ["LEC"], "has_letter_grade": True}
    ev_gen = evaluate_course_for_minor(ns2600, "inequality", "general")
    assert ev_gen is not None
    assert ev_gen["matched_categories"] == ["ineq_elective"]
    ev_het = evaluate_course_for_minor(ns2600, "inequality", "health_equity")
    assert ev_het is not None
    assert "ineq_het_elective" in ev_het["matched_categories"]

    ilrgl2010 = {"subject": "ILRGL", "catalog_nbr": "2010", "components": ["LEC"], "has_letter_grade": True}
    ilrgl4990 = {"subject": "ILRGL", "catalog_nbr": "4990", "components": ["IND"], "has_letter_grade": True}
    ilric_hist = {"subject": "ILRIC", "catalog_nbr": "2340", "components": ["LEC"], "has_letter_grade": True}
    assert evaluate_course_for_minor(ilrgl2010, "lsj", "standard") is not None
    assert evaluate_course_for_minor(ilric_hist, "lsj", "standard") is not None
    assert evaluate_course_for_minor(ilrgl4990, "lsj", "standard") is None

    hist_sem = {"subject": "HIST", "catalog_nbr": "2660", "title_short": "American Law Sem", "components": ["SEM"], "has_letter_grade": True, "units_max": 4.0}
    hist_lec = {"subject": "HIST", "catalog_nbr": "1510", "title_short": "Modern Europe", "components": ["LEC"], "has_letter_grade": True, "units_max": 4.0}
    hist_fws = {"subject": "HIST", "catalog_nbr": "1100", "title_short": "FWS: Maps", "components": ["SEM"], "has_letter_grade": True, "units_max": 3.0}
    hist_hon = {"subject": "HIST", "catalog_nbr": "4001", "title_short": "Honors Seminar", "components": ["SEM"], "has_letter_grade": True, "units_max": 4.0}

    assert evaluate_course_for_minor(hist_fws, "history", "standard") is None
    assert evaluate_course_for_minor(hist_hon, "history", "standard") is None
    assert evaluate_course_for_minor(hist_lec, "history", "standard")["matched_categories"] == ["hist_course"]
    assert evaluate_course_for_minor(hist_sem, "history", "standard")["matched_categories"] == [
        "hist_seminar_2000",
        "hist_course",
    ]


def test_info_science_and_psychology_requirements() -> None:
    info4470 = {"subject": "INFO", "catalog_nbr": "4470", "components": ["LEC"], "has_letter_grade": True, "units_max": 3.0}
    comm3190 = {"subject": "COMM", "catalog_nbr": "3190", "components": ["LEC"], "has_letter_grade": True, "units_max": 3.0}
    soc4390 = {"subject": "SOC", "catalog_nbr": "4390", "components": ["SEM"], "has_letter_grade": True, "units_max": 3.0}
    info1200 = {"subject": "INFO", "catalog_nbr": "1200", "components": ["LEC"], "has_letter_grade": True, "units_max": 3.0}
    info1300 = {"subject": "INFO", "catalog_nbr": "1300", "components": ["LEC"], "has_letter_grade": True, "units_max": 3.0}

    assert "is_conc_ux" in evaluate_course_for_minor(info4470, "info_science", "ux")["matched_categories"]
    assert "is_conc_digital_culture" in evaluate_course_for_minor(comm3190, "info_science", "digital_culture")["matched_categories"]
    assert "is_conc_data_science" in evaluate_course_for_minor(soc4390, "info_science", "data_science")["matched_categories"]

    # Core IS classes can also count toward Electives, unless the student ALREADY took that exact course.
    ev_1300_after_core = evaluate_course_for_minor(
        info1300,
        "info_science",
        "data_science",
        completed_categories={"is_core"},
        taken_courses=["INFO 1200"],
    )
    assert ev_1300_after_core is not None
    assert "is_elective" in ev_1300_after_core["matched_categories"]
    assert course_matches_minor_filter(ev_1300_after_core, hide_completed=True) is True

    # Already-taken course (INFO 1200) must NOT double-count as Elective even if Elective is unfinished.
    ev_1200_taken = evaluate_course_for_minor(
        info1200,
        "info_science",
        "data_science",
        completed_categories={"is_core"},
        taken_courses=["INFO 1200"],
    )
    assert ev_1200_taken is not None
    assert ev_1200_taken["already_taken"] is True
    assert course_matches_minor_filter(ev_1200_taken, hide_completed=True) is False
    assert any("double-count" in w for w in ev_1200_taken["warnings"])

    # Auto-fill must assign each course to at most 1 IS slot (no double-counting), and adjust by college:
    # 1) Single course INFO 2950 fills only 1 slot total (not Core + Conc + Elective!)
    single_assign = suggest_completed_categories(
        "info_science", "data_science", completed_courses=["INFO 2950"], college="engineering"
    )
    assert sum(len(v) for v in single_assign.values()) == 1

    # 2) Two Core courses [INFO 1200, INFO 1300] assign one to Core and the second Core course to Elective!
    two_core_eng = suggest_completed_categories(
        "info_science", "data_science", completed_courses=["INFO 1200", "INFO 1300"], college="engineering"
    )
    assert len(two_core_eng.get("is_core", [])) == 1
    assert len(two_core_eng.get("is_elective", [])) == 1
    assert set(two_core_eng["is_core"] + two_core_eng["is_elective"]) == {"INFO 1200", "INFO 1300"}

    # 3) Nolan Hotel college requires HADM 3740/4760, 2 Conc courses, and accepts AEM 3220 as Elective!
    hotel_assign = suggest_completed_categories(
        "info_science",
        "data_science",
        completed_courses=["INFO 1200", "HADM 3740", "AEM 3220"],
        college="hotel",
    )
    assert hotel_assign.get("is_core") == ["INFO 1200"]
    assert hotel_assign.get("is_hotel_req") == ["HADM 3740"]
    assert hotel_assign.get("is_elective") == ["AEM 3220"]

    # Psychology minor has ONLY requirement categories (psych_course + psych_research), not unrequired area tracks
    psych_def = MINORS_BY_ID["psychology"]
    assert [c.id for c in psych_def.versions[0].categories] == ["psych_course", "psych_research"]

    psych_cog = {"subject": "PSYCH", "catalog_nbr": "3140", "components": ["LEC"], "has_letter_grade": True, "units_max": 3.0}
    psych_res = {"subject": "PSYCH", "catalog_nbr": "4700", "components": ["IND"], "has_letter_grade": False, "units_max": 3.0}
    psych_fws = {"subject": "PSYCH", "catalog_nbr": "1120", "title_short": "FWS: Mind", "components": ["SEM"], "has_letter_grade": True, "units_max": 3.0}

    ev_psych = evaluate_course_for_minor(psych_cog, "psychology", "standard", completed_categories={"psych_course"})
    assert ev_psych is not None
    assert ev_psych["matched_categories"] == ["psych_course"]
    assert course_matches_minor_filter(ev_psych, hide_completed=True) is False

    ev_res = evaluate_course_for_minor(psych_res, "psychology", "standard")
    assert ev_res is not None
    assert ev_res["matched_categories"] == ["psych_research"]
    assert any("6 credits" in w for w in ev_res["warnings"])
    assert evaluate_course_for_minor(psych_fws, "psychology", "standard") is None


def test_minor_prefs_normalization_and_autofill() -> None:
    prefs = normalize_minor_prefs(
        {
            "selected_minor": "business",
            "versions": {"business": "bme", "invalid_minor": "x"},
            "colleges": {"info_science": "engineering", "business": "bogus"},
            "completed_categories": {"business": ["microeconomics", "bogus_cat", "microeconomics"]},
            "hide_completed": False,
        }
    )
    assert prefs["selected_minor"] == "business"
    assert prefs["versions"]["business"] == "bme"
    assert prefs["colleges"]["info_science"] == "engineering"
    assert prefs["completed_categories"] == {"business": ["microeconomics"]}
    assert prefs["hide_completed"] is False

    suggestions = suggest_completed_categories(
        "psychology",
        "standard",
        completed_courses=["PSYCH 3140"],
        in_progress_courses=["PSYCH 4700"],
    )
    assert suggestions["psych_course"] == ["PSYCH 3140"]
    assert suggestions["psych_research"] == ["PSYCH 4700 (IP)"]

    # AP Psych 1101 must NOT count toward psych_course; 6 completed credits + 1 IP must NOT auto-complete 18 cr
    cat_6cr = build_minors_catalog(
        [],
        completed_courses=["PSYCH 1101", "PSYCH 2450", "PSYCH 3420"],
        in_progress_courses=["PSYCH 2260"],
        completed_course_details={
            "PSYCH 1101": {"gr": "S", "sem": "AP FA24", "cr": "3"},
            "PSYCH 2450": {"gr": "A", "sem": "FA25", "cr": "3"},
            "PSYCH 3420": {"gr": "A+", "sem": "SP26", "cr": "3"},
        },
        in_progress_course_details={"PSYCH 2260": {"sem": "FA26"}},
    )
    psy_cats = {c["id"]: c for c in next(m for m in cat_6cr if m["id"] == "psychology")["versions"][0]["categories"]}
    assert psy_cats["psych_course"]["matched_user_courses"] == ["PSYCH 2450", "PSYCH 3420", "PSYCH 2260 (IP)"]
    assert psy_cats["psych_course"]["earned_credits"] == 6.0
    assert psy_cats["psych_course"]["auto_complete"] is False

    # AP PSYCH 1101 in search shows an AP warning without falsely blocking as taken for the minor
    ev_ap = evaluate_course_for_minor(
        {"subject": "PSYCH", "catalog_nbr": "1101", "components": ["LEC"], "has_letter_grade": True, "units_max": 3.0},
        "psychology",
        "standard",
        taken_courses=["PSYCH 1101"],
        taken_course_details={"PSYCH 1101": {"gr": "S", "sem": "AP FA24", "cr": "3"}},
    )
    assert ev_ap is not None
    assert ev_ap["already_taken"] is False
    assert any("AP credit" in w for w in ev_ap["warnings"])

    # Research S/U credit counts up to 6 cr toward 18-credit PSYCH total, while research itself requires >= 6 cr
    cat_18cr = build_minors_catalog(
        [],
        completed_courses=["PSYCH 2450", "PSYCH 3420", "PSYCH 3140", "PSYCH 3800", "PSYCH 4320", "PSYCH 4700"],
        completed_course_details={
            "PSYCH 2450": {"gr": "A", "sem": "FA25", "cr": "3"},
            "PSYCH 3420": {"gr": "A", "sem": "SP26", "cr": "3"},
            "PSYCH 3140": {"gr": "B+", "sem": "FA25", "cr": "3"},
            "PSYCH 3800": {"gr": "A-", "sem": "FA25", "cr": "3"},
            "PSYCH 4320": {"gr": "A", "sem": "SP26", "cr": "3"},
            "PSYCH 4700": {"gr": "S", "sem": "SP26", "cr": "3"},
        },
    )
    psy_18 = {c["id"]: c for c in next(m for m in cat_18cr if m["id"] == "psychology")["versions"][0]["categories"]}
    assert psy_18["psych_course"]["earned_credits"] == 18.0
    assert psy_18["psych_course"]["auto_complete"] is True
    assert psy_18["psych_research"]["earned_credits"] == 3.0
    assert psy_18["psych_research"]["auto_complete"] is False


@pytest.mark.asyncio
async def test_minors_catalog_preferences_and_search_api(tmp_path: Path) -> None:
    settings = Settings(
        app_domain="sniper.hodgman.net",
        app_origin="https://sniper.hodgman.net",
        data_dir=tmp_path / "data",
        static_dir=tmp_path / "static",
        enable_background_workers=False,
    )
    settings.ensure_persisted_secrets()
    app = create_app(custom_settings=settings, custom_provider=MinorsFakeProvider())

    async with app.router.lifespan_context(app):
        await app.state.catalog.sync_rosters_and_subjects("SP27")
        await app.state.catalog.sync_full_roster("SP27", delay_sec=0.0)

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="https://sniper.hodgman.net") as client:
            await client.post(
                "/api/auth/bootstrap",
                json={"username": "minor_tester", "password": "password123"},
            )
            await client.put(
                "/api/user/prereqs",
                json={
                    "completed_courses": ["PSYCH 3140", "HIST 2660"],
                    "include_implied_prereqs": True,
                },
            )
            cs_res = await client.put(
                "/api/cs/checklist",
                json={
                    "college": "arts",
                    "curriculum": "current",
                    "include_active_schedule": False,
                    "pe_completed": 0,
                    "slots": {},
                    "sync_completed_courses": ["PSYCH 3140", "HIST 2660"],
                    "sync_in_progress_courses": ["ECON 1110"],
                },
            )
            assert cs_res.status_code == 200

            # 1. Catalog lists all 7 minors and surfaces historical seminar + completed suggestions
            cat_res = await client.get("/api/minors/catalog?roster=SP27")
            assert cat_res.status_code == 200
            minors = cat_res.json()["minors"]
            assert len(minors) == len(MINORS_BY_ID) == 7

            by_id = {m["id"]: m for m in minors}
            psych_cats = {c["id"]: c for c in by_id["psychology"]["versions"][0]["categories"]}
            assert psych_cats["psych_course"]["matched_user_courses"] == ["PSYCH 3140"]
            assert psych_cats["psych_course"]["roster_count"] >= 1

            is_eng_res = await client.get("/api/minors/catalog?roster=SP27&college=engineering")
            assert is_eng_res.status_code == 200
            is_eng = {m["id"]: m for m in is_eng_res.json()["minors"]}["info_science"]
            assert is_eng["active_college"] == "engineering"
            eng_ds = next(v for v in is_eng["versions"] if v["id"] == "data_science")
            eng_elec = next(c for c in eng_ds["categories"] if c["id"] == "is_elective")
            assert eng_elec["required_count"] == 1

            hist_cats = {c["id"]: c for c in by_id["history"]["versions"][0]["categories"]}
            assert hist_cats["hist_seminar_2000"]["matched_user_courses"] == ["HIST 2660"]

            biz_gen_cats = {c["id"]: c for c in by_id["business"]["versions"][0]["categories"]}
            assert biz_gen_cats["microeconomics"]["matched_user_courses"] == ["ECON 1110 (IP)"]

            # 2. Save minor preferences via /api/auth/preferences and verify round-trip
            pref_res = await client.put(
                "/api/auth/preferences",
                json={
                    "minor_prefs": {
                        "selected_minor": "psychology",
                        "versions": {"psychology": "standard"},
                        "colleges": {"info_science": "engineering"},
                        "completed_categories": {"psychology": ["psych_course"]},
                        "hide_completed": True,
                    }
                },
            )
            assert pref_res.status_code == 200
            saved_user = pref_res.json()["user"]
            assert saved_user["minor_prefs"]["completed_categories"]["psychology"] == ["psych_course"]
            assert saved_user["minor_prefs"]["colleges"]["info_science"] == "engineering"

            status_res = await client.get("/api/auth/status")
            assert status_res.json()["user"]["minor_prefs"]["selected_minor"] == "psychology"

            # 3. Search hides PSYCH 3140 (completed psych_course + already taken) while keeping PSYCH 4700 (research cap)
            search_hidden = (
                await client.get(
                    "/api/courses/search",
                    params={"roster": "SP27", "minor": "psychology"},
                )
            ).json()
            codes_hidden = {f"{c['subject']} {c['catalog_nbr']}" for c in search_hidden["courses"]}
            assert "PSYCH 3140" not in codes_hidden
            assert "PSYCH 4700" in codes_hidden
            assert "PSYCH 1120" not in codes_hidden

            # 4. With minor_hide_completed=false, PSYCH 3140 appears with badge completed=true
            search_all = (
                await client.get(
                    "/api/courses/search",
                    params={
                        "roster": "SP27",
                        "minor": "psychology",
                        "minor_hide_completed": "false",
                    },
                )
            ).json()
            by_code_all = {f"{c['subject']} {c['catalog_nbr']}": c for c in search_all["courses"]}
            assert "PSYCH 3140" in by_code_all
            assert by_code_all["PSYCH 3140"]["minor_eligibility"]["badges"][0]["completed"] is True
