"""Tests for distribution filters, CS checklist, batch insights, Pick-1 watch groups, and flip history."""

from __future__ import annotations

import json

import pytest

from app.services.attributes import (
    course_matches_attrs,
    extract_course_attributes,
    normalize_attr_code,
)
from tests.conftest import make_sample_courses


def test_attribute_extraction_aliases_and_matching() -> None:
    assert normalize_attr_code("HIST-AS") == "HST-AS"
    assert normalize_attr_code("hst-as") == "HST-AS"

    attrs_hist = extract_course_attributes(
        {
            "subject": "HIST",
            "catalog_nbr": "1510",
            "title_long": "FWS: Early Modern World",
            "crse_attrs_json": json.dumps(
                [{"crseAttr": "DIST", "attrDescr": "Distribution", "crseAttrValues": "Historical Analysis (HST-AS)"}]
            ),
        }
    )
    assert "HST-AS" in attrs_hist
    assert "FWS" in attrs_hist

    attrs_pe = extract_course_attributes(
        {
            "subject": "PE",
            "catalog_nbr": "1420",
            "title_long": "Introduction to Climbing",
            "crse_attrs_json": "[]",
        }
    )
    assert "PE" in attrs_pe

    attrs_lang = extract_course_attributes(
        {
            "subject": "FREN",
            "catalog_nbr": "1210",
            "title_long": "Elementary French",
            "crse_attrs_json": json.dumps(
                [{"crseAttr": "LANG", "crseAttrValues": "FL-AG"}]
            ),
        }
    )
    assert "FL-AG" in attrs_lang
    assert "LANG" in attrs_lang

    assert course_matches_attrs(attrs_hist, ["HIST-AS"], match_mode="all") is True
    assert course_matches_attrs(attrs_hist, ["HST-AS", "FWS"], match_mode="all") is True
    assert course_matches_attrs(attrs_hist, ["HST-AS", "PE"], match_mode="all") is False
    assert course_matches_attrs(attrs_hist, ["HST-AS", "PE"], match_mode="any") is True


@pytest.mark.asyncio
async def test_distribution_filters_cs_project_and_attributes_endpoint(app_client) -> None:
    app, admin = app_client
    await admin.post("/api/auth/bootstrap", json={"username": "tyler", "password": "password123"})

    db = app.state.db
    # Seed an FWS Historical course, a PE course, and CS 4152 (explicit CS Project)
    await db.execute(
        """
        INSERT INTO subjects (roster, value, descr, synced_at)
        VALUES ('SP27', 'HIST', 'History', datetime('now')),
               ('SP27', 'PE', 'Physical Education', datetime('now')),
               ('SP27', 'CS', 'Computer Science', datetime('now'))
        ON CONFLICT(roster, value) DO UPDATE SET synced_at = datetime('now')
        """
    )
    await db.execute(
        """
        INSERT INTO courses_meta (
            roster, subject, catalog_nbr, catalog_num, title_short, title_long, description,
            acad_career, acad_group, crse_id, enroll_groups_json, crosslists_json,
            components_json, units_min, units_max, has_letter_grade, crse_attrs_json
        ) VALUES
        (
            'SP27', 'HIST', '1105', 1105, 'FWS History', 'FWS: Global Archives',
            'First-year writing seminar.', 'UG', 'AS', 90001, '[]', '[]', '["SEM"]',
            3.0, 3.0, 1, '[{"crseAttr":"DIST","crseAttrValues":"HST-AS"}]'
        ),
        (
            'SP27', 'PE', '1100', 1100, 'Jogging', 'Jogging & Conditioning',
            'Physical education course.', 'UG', 'OT', 90002, '[]', '[]', '["LAB"]',
            1.0, 1.0, 0, '[]'
        ),
        (
            'SP27', 'CS', '4152', 4152, 'Advanced Game Design', 'Advanced Topics in Computer Game Architecture',
            'Team project game development.', 'UG', 'EN', 90003, '[]', '[]', '["LEC"]',
            3.0, 4.0, 1, '[{"crseAttr":"CU","crseAttrValues":"SMR-AS"}]'
        )
        """
    )
    app.state.catalog._cs_index_cache.pop("SP27", None)
    await db.execute(
        """
        INSERT INTO roster_sections (
            roster, subject, catalog_nbr, class_nbr, enroll_group_idx,
            ssr_component, section, open_status, campus, location, location_descr, instruction_mode
        ) VALUES
        ('SP27', 'HIST', '1105', 9101, 0, 'SEM', '101', 'O', 'MAIN', 'ITH', 'Ithaca', 'In Person'),
        ('SP27', 'PE', '1100', 9102, 0, 'LAB', '001', 'O', 'MAIN', 'ITH', 'Ithaca', 'In Person'),
        ('SP27', 'CS', '4152', 9103, 0, 'LEC', '001', 'O', 'MAIN', 'ITH', 'Ithaca', 'In Person')
        """
    )

    attrs_res = await admin.get("/api/courses/attributes", params={"roster": "SP27"})
    assert attrs_res.status_code == 200
    codes = {a["code"] for a in attrs_res.json()["attributes"]}
    assert {"HST-AS", "FWS", "PE", "SMR-AS"}.issubset(codes)

    # Alias HIST-AS -> HST-AS + FWS combined with attr_match=all
    res_hist = await admin.get(
        "/api/courses/search",
        params={"roster": "SP27", "attrs": "HIST-AS,FWS", "attr_match": "all", "major_mode": "none"},
    )
    assert res_hist.status_code == 200
    hist_courses = res_hist.json()["courses"]
    assert [(c["subject"], c["catalog_nbr"]) for c in hist_courses] == [("HIST", "1105")]
    assert "HST-AS" in hist_courses[0]["crse_attrs"]
    assert "FWS" in hist_courses[0]["crse_attrs"]

    # attr_match=any across PE + HIST-AS
    res_any = await admin.get(
        "/api/courses/search",
        params={"roster": "SP27", "attrs": "PE,HST-AS", "attr_match": "any", "major_mode": "none"},
    )
    assert res_any.status_code == 200
    assert {(c["subject"], c["catalog_nbr"]) for c in res_any.json()["courses"]} == {
        ("HIST", "1105"),
        ("PE", "1100"),
    }

    # CS Project filter
    res_proj = await admin.get(
        "/api/courses/search",
        params={"roster": "SP27", "cs_requirement": "cs_project"},
    )
    assert res_proj.status_code == 200
    proj_courses = res_proj.json()["courses"]
    assert [(c["subject"], c["catalog_nbr"]) for c in proj_courses] == [("CS", "4152")]
    assert proj_courses[0]["cs_eligibility"]["cs_project"] is True


def _flatten_checklist_slots(payload: dict) -> dict[str, dict]:
    return {
        slot["id"]: slot
        for sec in payload.get("sections", [])
        for slot in sec.get("slots", [])
    }


@pytest.mark.asyncio
async def test_cs_checklist_auto_fill_what_if_and_manual_persistence(app_client) -> None:
    app, admin = app_client
    await admin.post("/api/auth/bootstrap", json={"username": "tyler", "password": "password123"})

    # Set completed courses + add MATH 2940 to active SP27 schedule
    await admin.put(
        "/api/user/prereqs",
        json={"completed_courses": ["CS 1110", "CS 2110", "CS 2800"], "include_implied_prereqs": True},
    )
    await admin.post("/api/schedules/quick-add", json={"roster": "SP27", "subject": "MATH", "catalog_nbr": "2940"})

    # Default include_active_schedule=True -> MATH 2940 appears in math_linalg as source="schedule"
    cl_on = await admin.get("/api/cs/checklist", params={"roster": "SP27"})
    assert cl_on.status_code == 200
    slots_on = _flatten_checklist_slots(cl_on.json())
    assert slots_on["intro_cs_1"]["course"] == "CS 1110"
    assert slots_on["intro_cs_1"]["source"] == "completed"
    assert slots_on["intro_cs_2"]["course"] == "CS 2110"
    assert slots_on["core_2800"]["course"] == "CS 2800"
    assert slots_on["math_linalg"]["course"] == "MATH 2940"
    assert slots_on["math_linalg"]["source"] == "schedule"

    # Toggle include_active_schedule=False -> linear algebra reverts to empty
    cl_off = await admin.put(
        "/api/cs/checklist",
        params={"roster": "SP27"},
        json={
            "college": "arts",
            "curriculum": "current",
            "include_active_schedule": False,
            "pe_completed": 1,
            "slots": {},
        },
    )
    assert cl_off.status_code == 200
    slots_off = _flatten_checklist_slots(cl_off.json())
    assert slots_off["math_linalg"]["course"] == ""
    assert slots_off["math_linalg"]["filled"] is False

    # Persist manual override + switch college & curriculum
    put_res = await admin.put(
        "/api/cs/checklist",
        params={"roster": "SP27"},
        json={
            "college": "engineering",
            "curriculum": "pre2024",
            "include_active_schedule": False,
            "pe_completed": 2,
            "slots": {
                "eng_math_4": {"course": "BTRY 3080", "gr": "A", "sem": "FA26"},
                "tech_elec_1": {"course": "ORIE 3300", "gr": "IP", "sem": "SP27"},
            },
        },
    )
    assert put_res.status_code == 200
    put_body = put_res.json()
    assert put_body["college"] == "engineering"
    assert put_body["curriculum"] == "pre2024"
    put_slots = _flatten_checklist_slots(put_body)
    assert put_slots["eng_math_4"]["course"] == "BTRY 3080"
    assert put_slots["eng_math_4"]["source"] == "manual"
    assert put_slots["eng_math_4"]["gr"] == "A"
    assert put_slots["tech_elec_1"]["course"] == "ORIE 3300"


@pytest.mark.asyncio
async def test_cs_checklist_cross_roster_and_historical_electives(app_client) -> None:
    app, admin = app_client
    await admin.post("/api/auth/bootstrap", json={"username": "tyler", "password": "password123"})

    db = app.state.db
    # Seed CS 5306 and CS 5470 ONLY in FA26 (not in SP27) plus FTS rows for autocomplete
    await db.execute(
        """
        INSERT INTO subjects (roster, value, descr, synced_at)
        VALUES ('FA26', 'CS', 'Computer Science', datetime('now'))
        ON CONFLICT(roster, value) DO UPDATE SET synced_at = datetime('now')
        """
    )
    await db.execute(
        """
        INSERT INTO courses_meta (
            roster, subject, catalog_nbr, catalog_num, title_short, title_long, description,
            acad_career, acad_group, crse_id, enroll_groups_json, crosslists_json,
            components_json, units_min, units_max, has_letter_grade, crse_attrs_json
        ) VALUES
        (
            'FA26', 'CS', '5306', 5306, 'Crowdsourcing & Human Comp', 'Crowdsourcing and Human Computation',
            'Human-in-the-loop computation.', 'GR', 'EN', 91001, '[]', '[]', '["LEC"]',
            3.0, 3.0, 1, '[]'
        ),
        (
            'FA26', 'CS', '5470', 5470, 'Systems for Large-Scale ML', 'Systems for Large-Scale ML',
            'Distributed ML systems.', 'GR', 'EN', 91002, '[]', '[]', '["LEC"]',
            3.0, 3.0, 1, '[]'
        )
        """
    )
    await db.execute(
        """
        INSERT INTO courses_fts (roster, subject, catalog_nbr, course_code, title_long, description, class_nbrs)
        VALUES ('FA26', 'CS', '5306', 'CS 5306 CS5306', 'Crowdsourcing and Human Computation', 'Human-in-the-loop computation.', ''),
               ('FA26', 'CS', '5470', 'CS 5470 CS5470', 'Systems for Large-Scale ML', 'Distributed ML systems.', '')
        """
    )

    # Autocomplete options for SP27 still find FA26 courses
    opt_res = await admin.get("/api/user/prereqs/options", params={"roster": "SP27", "q": "5470"})
    assert opt_res.status_code == 200
    assert any(o["code"] == "CS 5470" for o in opt_res.json()["options"])

    # Add CS 5306, CS 5470 (FA26 only), plus uncached CS 4700, CS 4780 & CS 5112
    await admin.put(
        "/api/user/prereqs",
        json={
            "completed_courses": ["CS 4700", "CS 4780", "CS 5112", "CS 5306", "CS 5470"],
            "include_implied_prereqs": True,
        },
    )
    cl = await admin.get("/api/cs/checklist", params={"roster": "SP27"})
    assert cl.status_code == 200
    slots = _flatten_checklist_slots(cl.json())

    assert slots["core_aiml"]["course"] == "CS 4780"
    # Fall 2024+ (current) has 2 CS Electives + 1 Project; overflow fills Tech Elective / Major Approved
    assert "cs_elec_3" not in slots
    filled_elective_courses = {
        sl["course"]
        for k, sl in slots.items()
        if k.startswith(("cs_elec_", "tech_elec_", "maj_elec_")) and sl["filled"]
    }
    assert filled_elective_courses == {"CS 4700", "CS 5112", "CS 5306", "CS 5470"}
    assert slots["cs_elec_1"]["filled"] and slots["cs_elec_2"]["filled"]
    # Titles hydrated from FA26 courses_meta even when viewing SP27
    by_course = {sl["course"]: sl for sl in slots.values() if sl["course"]}
    assert by_course["CS 5470"]["title"] == "Systems for Large-Scale ML"
    assert by_course["CS 5306"]["title"] == "Crowdsourcing and Human Computation"

    # Pre-Fall 2024 still exposes 3 CS Electives (+ 1 Project)
    await admin.put(
        "/api/cs/checklist",
        params={"roster": "SP27"},
        json={
            "college": "arts",
            "curriculum": "pre2024",
            "include_active_schedule": False,
            "pe_completed": 0,
            "slots": {},
        },
    )
    cl_pre = await admin.get("/api/cs/checklist", params={"roster": "SP27"})
    assert cl_pre.status_code == 200
    pre_slots = _flatten_checklist_slots(cl_pre.json())
    assert "cs_elec_3" in pre_slots
    assert pre_slots["cs_elec_1"]["filled"] and pre_slots["cs_elec_2"]["filled"] and pre_slots["cs_elec_3"]["filled"]


@pytest.mark.asyncio
async def test_cs_checklist_slot_swap_heals_stale_title(app_client) -> None:
    app, admin = app_client
    await admin.post("/api/auth/bootstrap", json={"username": "tyler", "password": "password123"})

    db = app.state.db
    await db.execute(
        """
        INSERT INTO courses_meta (
            roster, subject, catalog_nbr, catalog_num, title_short, title_long, description,
            acad_career, acad_group, crse_id, enroll_groups_json, crosslists_json,
            components_json, units_min, units_max, has_letter_grade, crse_attrs_json
        ) VALUES (
            'SP27', 'SPAN', '1230', 1230, 'Continuing Spanish', 'Continuing Spanish',
            'Intermediate Spanish.', 'UG', 'AS', 92001, '[]', '[]', '["SEM"]',
            4.0, 4.0, 1, '[]'
        )
        """
    )

    # Auto-filled completed course should NOT leak into manual_slots
    await admin.put("/api/user/prereqs", json={"completed_courses": ["CS 2110"], "include_implied_prereqs": True})
    initial = (await admin.get("/api/cs/checklist", params={"roster": "SP27"})).json()
    assert initial["manual_slots"] == {}
    assert _flatten_checklist_slots(initial)["intro_cs_2"]["course"] == "CS 2110"

    # Simulate swapping CS 1340 -> SPAN 1230 while stale CS 1340 title was still saved
    put_res = await admin.put(
        "/api/cs/checklist",
        params={"roster": "SP27"},
        json={
            "college": "arts",
            "curriculum": "current",
            "include_active_schedule": True,
            "pe_completed": 0,
            "slots": {
                "maj_elec_1": {
                    "course": "SPAN 1230",
                    "title": "Choices and Consequences in Computing",
                    "cr": "4",
                }
            },
        },
    )
    assert put_res.status_code == 200
    data = put_res.json()
    slot = _flatten_checklist_slots(data)["maj_elec_1"]
    assert slot["course"] == "SPAN 1230"
    assert slot["title"] == "Continuing Spanish"
    assert list(data["manual_slots"].keys()) == ["maj_elec_1"]

    # Fixed-choice boxes provide quick_options with credits/titles & prereq autocomplete returns cr
    flat_data = _flatten_checklist_slots(data)
    core_2800_codes = [opt["code"] for opt in flat_data["core_2800"]["quick_options"]]
    assert "CS 2800" in core_2800_codes
    assert "CS 2802" in core_2800_codes
    opt_span = (await admin.get("/api/user/prereqs/options", params={"roster": "SP27", "q": "1230"})).json()
    span_entry = next(o for o in opt_span["options"] if o["code"] == "SPAN 1230")
    assert span_entry["cr"] == "4"

    # Adding directly inside a box with sync_completed_courses updates both slot & Classes I've Taken
    sync_res = await admin.put(
        "/api/cs/checklist",
        params={"roster": "SP27"},
        json={
            "college": "arts",
            "curriculum": "current",
            "include_active_schedule": True,
            "pe_completed": 0,
            "slots": {
                "maj_elec_1": {"course": "SPAN 1230", "cr": "4", "pinned": True, "cleared": False}
            },
            "sync_completed_courses": ["CS 2110", "SPAN 1230"],
        },
    )
    assert sync_res.status_code == 200
    sync_body = sync_res.json()
    assert "SPAN 1230" in sync_body["completed_courses"]
    assert _flatten_checklist_slots(sync_body)["maj_elec_1"]["source"] == "completed"


@pytest.mark.asyncio
async def test_cs_checklist_maximizes_filled_slots_matching(app_client) -> None:
    app, admin = app_client
    await admin.post("/api/auth/bootstrap", json={"username": "tyler", "password": "password123"})

    db = app.state.db
    await db.execute(
        """
        INSERT INTO courses_meta (
            roster, subject, catalog_nbr, catalog_num, title_short, title_long, description,
            acad_career, acad_group, crse_id, enroll_groups_json, crosslists_json,
            components_json, units_min, units_max, has_letter_grade, crse_attrs_json
        ) VALUES
        (
            'SP27', 'CS', '5150', 5150, 'Software Engineering', 'Software Engineering',
            'Software engineering project course.', 'GR', 'EN', 93001, '[]', '[]', '["LEC", "PRJ"]',
            4.0, 4.0, 1, '[]'
        ),
        (
            'SP27', 'CS', '4701', 4701, 'AI Practicum', 'Practicum in Artificial Intelligence',
            '2-credit AI practicum.', 'UG', 'EN', 93002, '[]', '[]', '["PRJ"]',
            2.0, 2.0, 1, '[]'
        ),
        (
            'SP27', 'SPAN', '2090', 2090, 'Intermediate Spanish FWS/Lang', 'FWS: Intermediate Spanish',
            'Counts for both FWS and LANG in test.', 'UG', 'AS', 93003, '[]', '[]', '["SEM"]',
            3.0, 3.0, 1, '[{"crseAttr":"DIST","crseAttrValues":"FL-AG"}]'
        ),
        (
            'SP27', 'WRIT', '1420', 1420, 'Writing FWS', 'FWS: Writing Seminar',
            'Pure FWS.', 'UG', 'AS', 93004, '[]', '[]', '["SEM"]',
            3.0, 3.0, 1, '[{"crseAttr":"CU","crseAttrValues":"FWS"}]'
        ),
        (
            'SP27', 'WRIT', '1430', 1430, 'Rhetoric FWS', 'FWS: Public Rhetoric',
            'Pure FWS 2.', 'UG', 'AS', 93009, '[]', '[]', '["SEM"]',
            3.0, 3.0, 1, '[{"crseAttr":"CU","crseAttrValues":"FWS"}]'
        ),
        (
            'SP27', 'ORIE', '3300', 3300, 'Optimization I', 'Optimization I',
            'ORIE modeling.', 'UG', 'EN', 93005, '[]', '[]', '["LEC"]',
            4.0, 4.0, 1, '[]'
        ),
        (
            'SP27', 'ORIE', '3500', 3500, 'Engineering Probability', 'Engineering Probability & Statistics II',
            'Probability.', 'UG', 'EN', 93006, '[]', '[]', '["LEC"]',
            4.0, 4.0, 1, '[]'
        ),
        (
            'SP27', 'ORIE', '4150', 4150, 'Service Engineering', 'Data Analytics',
            'ORIE elective.', 'UG', 'EN', 93007, '[]', '[]', '["LEC"]',
            3.0, 3.0, 1, '[]'
        ),
        (
            'SP27', 'BTRY', '3080', 3080, 'Probability Models', 'Probability Models and Inference',
            'Probability.', 'UG', 'AG', 93008, '[]', '[]', '["LEC"]',
            4.0, 4.0, 1, '[]'
        ),
        (
            'SP27', 'SPAN', '1230', 1230, 'Continuing Spanish', 'Continuing Spanish',
            'Option B intro Spanish.', 'UG', 'AS', 93010, '[]', '[]', '["SEM"]',
            4.0, 4.0, 1, '[{"attrDescr":"Distribution Requirements","crseAttrValues":"(FL-AG)"}]'
        ),
        (
            'SP27', 'SPAN', '2070', 2070, 'Spanish Medical', 'Intermediate Spanish for the Medical Professions',
            'Option A 2000+ Spanish.', 'UG', 'AS', 93011, '[]', '[]', '["SEM"]',
            3.0, 3.0, 1, '[{"attrDescr":"Distribution Requirements","crseAttrValues":"(FL-AG), (FLOPI-AS)"}]'
        )
        """
    )
    app.state.catalog._cs_index_cache.pop("SP27", None)

    # 1) CS 4701 (2 cr PRJ) is CS Project ONLY; CS 5150 (4 cr) qualifies for CS Project + CS Elective + Tech Elective
    cs_idx = await app.state.catalog.get_cs_requirements_index("SP27")
    assert cs_idx.get("CS", "4701").cs_project is True
    assert cs_idx.get("CS", "4701").cs_elective is False
    assert cs_idx.get("CS", "5150").cs_project is True
    assert cs_idx.get("CS", "5150").cs_elective is True

    # Even with CS 5150 listed BEFORE CS 4701, matching puts CS 4701 -> cs_proj and CS 5150 -> cs_elec_1
    await admin.put(
        "/api/user/prereqs",
        json={"completed_courses": ["CS 5150", "CS 4701"], "include_implied_prereqs": True},
    )
    cl1 = (await admin.get("/api/cs/checklist", params={"roster": "SP27"})).json()
    slots1 = _flatten_checklist_slots(cl1)
    assert slots1["cs_proj"]["course"] == "CS 4701"
    assert slots1["cs_elec_1"]["course"] == "CS 5150"

    # 2) Fall 2024+ has 2 CS electives + 1 CS project; remaining CS 4000+ courses overflow to tech_elec while CS 4701 stays in cs_proj
    await admin.put(
        "/api/user/prereqs",
        json={
            "completed_courses": ["CS 5150", "CS 4701", "CS 4700", "CS 4740", "CS 4860"],
            "include_implied_prereqs": True,
        },
    )
    cl2 = (await admin.get("/api/cs/checklist", params={"roster": "SP27"})).json()
    slots2 = _flatten_checklist_slots(cl2)
    assert slots2["cs_proj"]["course"] == "CS 4701"
    assert "cs_elec_3" not in slots2
    cs_elecs = {slots2[f"cs_elec_{i}"]["course"] for i in range(1, 3)}
    assert len(cs_elecs) == 2
    tech_elecs = {slots2[f"tech_elec_{i}"]["course"] for i in range(1, 4) if slots2[f"tech_elec_{i}"]["filled"]}
    assert "CS 5150" in (cs_elecs | tech_elecs)
    assert slots2["tech_elec_1"]["filled"] is True

    # 3) A&S FWS vs LANG matching (Option A 2000+ in Lang 3 waives Lang 1 & 2) + Eng Math4 vs ORIE Ext Spec
    await admin.put(
        "/api/user/prereqs",
        json={
            "completed_courses": ["SPAN 2090", "WRIT 1420", "WRIT 1430", "ORIE 3500", "ORIE 3300", "ORIE 4150", "BTRY 3080"],
            "include_implied_prereqs": True,
        },
    )
    cl3 = (await admin.get("/api/cs/checklist", params={"roster": "SP27"})).json()
    slots3 = _flatten_checklist_slots(cl3)
    # SPAN 2090 satisfies Option A in Lang 3, freeing WRIT 1420 + WRIT 1430 for FWS 1 & FWS 2, and waiving Lang 1 & 2
    assert {slots3["as_fws_1"]["course"], slots3["as_fws_2"]["course"]} == {"WRIT 1420", "WRIT 1430"}
    assert slots3["as_lang_3"]["course"] == "SPAN 2090"
    assert slots3["as_lang_1"]["source"] == "waived"
    assert slots3["as_lang_1"]["waived"] is True
    assert slots3["as_lang_2"]["source"] == "waived"
    assert slots3["as_lang_2"]["waived"] is True
    assert slots3["as_lang_2"]["waived_by"] == "SPAN 2090"

    # Switch to Engineering: ORIE 3300/3500/4150 should fill all 3 ext_spec slots while BTRY 3080 fills eng_math_4
    eng_res = await admin.put(
        "/api/cs/checklist",
        params={"roster": "SP27"},
        json={
            "college": "engineering",
            "curriculum": "current",
            "include_active_schedule": True,
            "pe_completed": 0,
            "slots": {},
        },
    )
    assert eng_res.status_code == 200
    eng_slots = _flatten_checklist_slots(eng_res.json())
    assert eng_slots["eng_math_4"]["course"] == "BTRY 3080"
    assert {eng_slots[f"ext_spec_{i}"]["course"] for i in range(1, 4)} == {
        "ORIE 3300",
        "ORIE 3500",
        "ORIE 4150",
    }

    # Switch back to A&S: Taking BOTH SPAN 1230 + SPAN 2070 uses ONLY SPAN 2070 in Lang 3 and greys out Lang 1 & Lang 2
    await admin.put(
        "/api/cs/checklist",
        params={"roster": "SP27"},
        json={
            "college": "arts",
            "curriculum": "current",
            "include_active_schedule": True,
            "pe_completed": 0,
            "slots": {},
            "sync_completed_courses": ["SPAN 1230", "SPAN 2070"],
        },
    )
    cl_opt_a = (await admin.get("/api/cs/checklist", params={"roster": "SP27"})).json()
    slots_opt_a = _flatten_checklist_slots(cl_opt_a)
    assert slots_opt_a["as_lang_3"]["course"] == "SPAN 2070"
    assert slots_opt_a["as_lang_1"]["waived"] is True
    assert slots_opt_a["as_lang_1"]["waived_by"] == "SPAN 2070"
    assert slots_opt_a["as_lang_2"]["waived"] is True
    assert slots_opt_a["as_lang_2"]["waived_by"] == "SPAN 2070"

    # Only SPAN 1230 (< 2000) fills Lang 1 normally without waiving
    await admin.put(
        "/api/user/prereqs",
        json={"completed_courses": ["SPAN 1230"], "include_implied_prereqs": True},
    )
    cl_opt_b = (await admin.get("/api/cs/checklist", params={"roster": "SP27"})).json()
    slots_opt_b = _flatten_checklist_slots(cl_opt_b)
    assert slots_opt_b["as_lang_1"]["course"] == "SPAN 1230"
    assert slots_opt_b["as_lang_1"].get("waived") is not True
    assert slots_opt_b["as_lang_3"]["filled"] is False


@pytest.mark.asyncio
async def test_batch_load_schedule_insights(app_client) -> None:
    app, admin = app_client
    await admin.post("/api/auth/bootstrap", json={"username": "tyler", "password": "password123"})

    qa = await admin.post("/api/schedules/quick-add", json={"roster": "SP27", "subject": "CS", "catalog_nbr": "2110"})
    sched_id = qa.json()["active"]["schedule"]["id"]

    calls: list[tuple[str, str, str]] = []

    async def fake_get_course_insights(
        roster: str, subject: str, catalog_nbr: str, force_refresh: bool = False
    ):
        calls.append((roster, subject, catalog_nbr))
        await app.state.db.execute(
            """
            INSERT INTO course_insights_cache (subject, catalog_nbr, payload_json, found, fetched_at)
            VALUES (?, ?, ?, 1, datetime('now'))
            ON CONFLICT(subject, catalog_nbr) DO UPDATE SET
                payload_json = excluded.payload_json,
                found = excluded.found,
                fetched_at = excluded.fetched_at
            """,
            (
                subject,
                catalog_nbr,
                json.dumps({"found": True, "rating": 4.4, "difficulty": 2.9, "workload": 3.1, "review_count": 42}),
            ),
        )
        return {"found": True}

    app.state.insights.get_course_insights = fake_get_course_insights

    res = await admin.post(f"/api/schedules/{sched_id}/insights")
    assert res.status_code == 200
    data = res.json()
    assert data["insights_fetched_count"] == 1
    assert calls == [("SP27", "CS", "2110")]
    assert data["courses"][0]["cached_insights"]["workload"] == 3.1


@pytest.mark.asyncio
async def test_pick_one_watch_group_and_multi_window_history(app_client) -> None:
    app, admin = app_client
    poller = app.state.poller

    await admin.post("/api/auth/bootstrap", json={"username": "tyler", "password": "password123"})

    w1_res = await admin.post(
        "/api/watches",
        json={
            "roster": "SP27",
            "subject": "CS",
            "catalog_nbr": "2110",
            "class_nbr": 6584,
            "mode": "exact",
            "trigger_on": "open",
            "auto_pause": True,
            "cooldown_sec": 0,
        },
    )
    w2_res = await admin.post(
        "/api/watches",
        json={
            "roster": "SP27",
            "subject": "CS",
            "catalog_nbr": "2110",
            "class_nbr": 6585,
            "mode": "exact",
            "trigger_on": "open",
            "auto_pause": True,
            "cooldown_sec": 0,
        },
    )
    assert w1_res.status_code == 201 and w2_res.status_code == 201
    w1_id = w1_res.json()["watch"]["id"]
    w2_id = w2_res.json()["watch"]["id"]

    # Assign both watches to mutually exclusive Pick-1 group via batch endpoint
    grp = await admin.post(
        "/api/watches/group",
        json={"watch_ids": [w1_id, w2_id], "group_key": "CS 2110 Dis"},
    )
    assert grp.status_code == 200
    assert grp.json()["group_key"] == "CS 2110 Dis"
    grouped = {w["id"]: w for w in grp.json()["watches"]}
    assert grouped[w1_id]["group_key"] == "CS 2110 Dis"
    assert grouped[w2_id]["group_key"] == "CS 2110 Dis"

    # Baseline closed poll -> 0 alerts
    a0 = await poller.evaluate_courses(
        "SP27", "CS", make_sample_courses(lec_status="O", dis202_status="C", dis203_status="C")
    )
    assert a0 == []

    # Both sections open simultaneously -> Pick-1 guarantees ONLY 1 alert & pauses sibling
    a1 = await poller.evaluate_courses(
        "SP27", "CS", make_sample_courses(lec_status="O", dis202_status="O", dis203_status="O"), rtt_ms=14
    )
    assert len(a1) == 1
    assert a1[0].section.class_nbr == 6584

    # Dispatch alert so status_events records alert open without duplicate
    await app.state.dispatcher.dispatch_alerts(a1)

    watches_after = {w["id"]: w for w in (await admin.get("/api/watches")).json()["watches"]}
    assert watches_after[w1_id]["group_key"] == "CS 2110 Dis"
    assert watches_after[w1_id]["active"] is False
    assert watches_after[w2_id]["active"] is False

    # Re-arm w1 with auto_pause=False and verify C -> O -> C flip tracking without double counting
    await admin.patch(f"/api/watches/{w1_id}", json={"auto_pause": False})
    await admin.post(f"/api/watches/{w1_id}/rearm")

    # O -> C closes 6584 (non-alert flip logged by poller)
    a2 = await poller.evaluate_courses(
        "SP27", "CS", make_sample_courses(lec_status="O", dis202_status="C", dis203_status="C"), rtt_ms=12
    )
    assert a2 == []

    # C -> O reopens 6584 (alert flip logged by dispatcher)
    a3 = await poller.evaluate_courses(
        "SP27", "CS", make_sample_courses(lec_status="O", dis202_status="O", dis203_status="C"), rtt_ms=16
    )
    assert len(a3) == 1
    await app.state.dispatcher.dispatch_alerts(a3)

    # Check turnover summary on list_watches
    watches_list = {w["id"]: w for w in (await admin.get("/api/watches")).json()["watches"]}
    summary = watches_list[w1_id]["turnover_summary"]
    assert summary["h24"] == 3  # 1st open (alert) + close (non-alert) + 2nd open (alert)
    assert summary["d7"] == 3
    assert summary["d30"] == 3
    assert summary["all"] == 3
    assert summary["opened_24h"] == 2
    assert summary["opened_7d"] == 2

    # Check detailed history endpoint across windows
    hist_res = await admin.get(f"/api/watches/{w1_id}/history", params={"window": "7d"})
    assert hist_res.status_code == 200
    hist = hist_res.json()
    assert hist["window"] == "7d"
    assert set(hist["windows"].keys()) == {"24h", "7d", "30d", "all"}
    assert hist["windows"]["24h"]["total_flips"] == 3
    assert hist["windows"]["all"]["opened_count"] == 2
    assert hist["windows"]["all"]["closed_count"] == 1
    assert len(hist["events"]) == 3
    # Newest event first
    assert hist["events"][0]["new_status"] == "O"
    assert hist["events"][1]["new_status"] == "C"
    assert hist["events"][2]["new_status"] == "O"


@pytest.mark.asyncio
async def test_as_distribution_unique_courses_and_historical_lookup(app_client, fake_provider) -> None:
    from app.providers.base import CourseRecord, RosterRecord, SectionRecord

    app, admin = app_client
    await admin.post("/api/auth/bootstrap", json={"username": "tyler", "password": "password123"})

    # Seed SP27 courses: CS 1340 covers BOTH ETM-AS & SDS-AS; CS 3780 covers SDS-AS
    await app.state.db.execute(
        """
        INSERT OR REPLACE INTO courses_meta (
            roster, subject, catalog_nbr, catalog_num, title_short, title_long,
            description, acad_career, acad_group, crse_id, enroll_groups_json,
            crosslists_json, components_json, units_min, units_max, has_letter_grade, crse_attrs_json
        ) VALUES
        (
            'SP27', 'CS', '1340', 1340, 'Choices & Consequences', 'Choices and Consequences in Computing',
            'Ethics and data.', 'UG', 'AS', 94001, '[]', '[]', '["LEC"]',
            3.0, 3.0, 1, '[{"crseAttrValues":"(ETM-AS), (SDS-AS)"}]'
        ),
        (
            'SP27', 'CS', '3780', 3780, 'Machine Learning', 'Introduction to Machine Learning',
            'ML.', 'UG', 'EN', 94002, '[]', '[]', '["LEC"]',
            4.0, 4.0, 1, '[{"crseAttrValues":"(SDS-AS)"}]'
        ),
        (
            'SP27', 'BIOMI', '1100', 1100, 'Locker Rooms Microbes', 'Locker Rooms, Kitchens and Bedrooms',
            'Bio.', 'UG', 'AS', 94003, '[]', '[]', '["LEC"]',
            3.0, 3.0, 1, '[{"crseAttrValues":"(BIO-AS)"}]'
        ),
        (
            'SP27', 'CS', '2800', 2800, 'Discrete Structures', 'Discrete Structures',
            'Math/CS.', 'UG', 'EN', 94004, '[]', '[]', '["LEC"]',
            3.0, 3.0, 1, '[{"crseAttrValues":"(SMR-AS)"}]'
        )
        """
    )
    await app.state.db.execute(
        """
        INSERT INTO subjects (roster, value, descr, synced_at)
        VALUES ('SP27', 'HIST', 'History', datetime('now'))
        ON CONFLICT(roster, value) DO UPDATE SET synced_at = datetime('now')
        """
    )

    # Also add older Fall/Spring rosters and put HIST 2640 only in FA26 (not SP27)
    fake_provider.rosters = [
        RosterRecord(slug="SP27", descr="Spring 2027", is_default=True, archive_mode=False, strm="2951"),
        RosterRecord(slug="FA26", descr="Fall 2026", is_default=False, archive_mode=True, strm="2937"),
        RosterRecord(slug="SP26", descr="Spring 2026", is_default=False, archive_mode=True, strm="2923"),
        RosterRecord(slug="FA25", descr="Fall 2025", is_default=False, archive_mode=True, strm="2909"),
    ]
    fake_provider.courses_by_bucket[("FA26", "HIST")] = [
        CourseRecord(
            roster="FA26",
            subject="HIST",
            catalog_nbr="2640",
            title_short="History of Science",
            title_long="Introduction to the History of Science",
            description="History of science.",
            crse_id=94005,
            acad_career="UG",
            acad_group="AS",
            enroll_groups=[{"componentsRequired": ["LEC"], "unitsMinimum": 4, "unitsMaximum": 4}],
            crse_attrs=[{"attrDescr": "Distribution Requirements", "crseAttrValues": "(HIST-AS), (HA-AS), (SCD-AS)"}],
            sections=[
                SectionRecord(
                    class_nbr=9901,
                    enroll_group_idx=0,
                    ssr_component="LEC",
                    section="001",
                    open_status="C",
                    components_required=["LEC"],
                    meetings_summary="TR 11:40AM-12:55PM",
                    instructors_summary="Staff",
                )
            ],
        )
    ]

    # Put CS 1340, CS 3780, BIOMI 1100, CS 2800 + uncached HIST 2640 into completed courses
    await admin.put(
        "/api/user/prereqs",
        json={
            "completed_courses": ["BIOMI 1100", "CS 1340", "CS 2800", "CS 3780", "HIST 2640"],
            "include_implied_prereqs": True,
        },
    )

    cl1 = (await admin.get("/api/cs/checklist", params={"roster": "SP27"})).json()
    slots1 = _flatten_checklist_slots(cl1)
    # CS 1340 fills ETM-AS and CS 3780 fills SDS-AS -> 4 unique courses instead of reusing CS 1340
    assert slots1["as_dist_etm_as"]["course"] == "CS 1340"
    assert slots1["as_dist_sds_as"]["course"] == "CS 3780"
    assert cl1["as_distribution_summary"]["covered_categories"] == 4
    assert cl1["as_distribution_summary"]["unique_courses"] == 4
    assert cl1["missing_metadata_courses"] == ["HIST 2640"]

    # Polite historical lookup resolves HIST 2640 from FA26 without touching already-synced SP27
    lookup_res = await app.state.catalog.process_historical_course_lookup()
    assert "HIST 2640" in lookup_res["resolved"]
    assert lookup_res["synced_buckets"] == 1

    # Checklist now automatically populates HIST-AS and SCD-AS from HIST 2640
    cl2 = (await admin.get("/api/cs/checklist", params={"roster": "SP27"})).json()
    slots2 = _flatten_checklist_slots(cl2)
    assert cl2["missing_metadata_courses"] == []
    assert slots2["as_dist_hist_as"]["course"] == "HIST 2640"
    assert slots2["as_dist_scd_as"]["course"] == "HIST 2640"
    assert cl2["as_distribution_summary"]["covered_categories"] == 6
    assert cl2["as_distribution_summary"]["unique_courses"] == 5

    # Without CS 3780, double-counting still fills BOTH ETM-AS and SDS-AS using CS 1340
    await admin.put(
        "/api/user/prereqs",
        json={
            "completed_courses": ["CS 1340"],
            "include_implied_prereqs": True,
        },
    )
    cl3 = (await admin.get("/api/cs/checklist", params={"roster": "SP27"})).json()
    slots3 = _flatten_checklist_slots(cl3)
    assert slots3["as_dist_etm_as"]["course"] == "CS 1340"
    assert slots3["as_dist_sds_as"]["course"] == "CS 1340"
    assert cl3["as_distribution_summary"]["covered_categories"] == 2
    assert cl3["as_distribution_summary"]["unique_courses"] == 1


@pytest.mark.asyncio
async def test_ap_transcript_equivalents_fws_and_prereq_options(app_client) -> None:
    app, admin = app_client
    await admin.post("/api/auth/bootstrap", json={"username": "tyler", "password": "password123"})

    # Searching 'AP Lit' and 'AP Stats' surfaces non-roster transcript credit equivalents
    ap_lit_opts = (
        await admin.get("/api/user/prereqs/options", params={"roster": "SP27", "q": "AP Lit"})
    ).json()["options"]
    assert any(o["code"] == "ENGL 1100F" and o["cr"] == "3" for o in ap_lit_opts)

    ap_stat_opts = (
        await admin.get("/api/user/prereqs/options", params={"roster": "SP27", "q": "AP Stats"})
    ).json()["options"]
    assert any(o["code"] == "MATH 1710" and o["cr"] == "4" for o in ap_stat_opts)

    ap_bio_opts = (
        await admin.get("/api/user/prereqs/options", params={"roster": "SP27", "q": "AP Bio"})
    ).json()["options"]
    assert {o["code"] for o in ap_bio_opts} >= {"BIOG 1101F", "BIOG 1102F"}

    ap_span_opts = (
        await admin.get("/api/user/prereqs/options", params={"roster": "SP27", "q": "AP Spanish"})
    ).json()["options"]
    assert any(o["code"] == "SPAN 1100C" and o["cr"] == "3" for o in ap_span_opts)

    # Adding ENGL 1100F, MATH 1710 & BIOG 1102F fills one FWS box without queueing historical lookups
    await admin.put(
        "/api/user/prereqs",
        json={
            "completed_courses": ["BIOG 1102F", "ENGL 1100F", "MATH 1710"],
            "include_implied_prereqs": True,
        },
    )
    cl_as = (await admin.get("/api/cs/checklist", params={"roster": "SP27"})).json()
    assert cl_as["missing_metadata_courses"] == []
    assert app.state.catalog._historical_lookup_queued == set()
    slots_as = _flatten_checklist_slots(cl_as)
    assert slots_as["as_fws_1"]["course"] == "ENGL 1100F"
    assert slots_as["as_fws_1"]["cr"] == "3"
    assert "AP Lit" in slots_as["as_fws_1"]["title"]
    assert any(q["code"] == "ENGL 1100F" for q in slots_as["as_fws_1"].get("quick_options", []))
    assert slots_as["as_fws_2"]["filled"] is False

    # Engineering checklist also recognizes ENGL 1100F in FWS 1 only
    cl_eng = (
        await admin.put(
            "/api/cs/checklist",
            params={"roster": "SP27"},
            json={
                "college": "engineering",
                "curriculum": "current",
                "include_active_schedule": True,
                "pe_completed": 0,
                "slots": {},
            },
        )
    ).json()
    slots_eng = _flatten_checklist_slots(cl_eng)
    assert slots_eng["eng_fws_1"]["course"] == "ENGL 1100F"
    assert slots_eng["eng_fws_2"]["filled"] is False


@pytest.mark.asyncio
async def test_external_spec_soft_related_depts_warning_and_same_dept_preference(app_client) -> None:
    app, admin = app_client
    await admin.post("/api/auth/bootstrap", json={"username": "tyler", "password": "password123"})

    await app.state.db.execute(
        """
        INSERT OR REPLACE INTO courses_meta (
            roster, subject, catalog_nbr, catalog_num, title_short, title_long,
            description, acad_career, acad_group, crse_id, enroll_groups_json,
            crosslists_json, components_json, units_min, units_max, has_letter_grade, crse_attrs_json
        ) VALUES
        (
            'SP27', 'PSYCH', '3420', 3420, 'Human Perception', 'Human Perception',
            'Perception.', 'UG', 'AS', 95001, '[]', '[]', '["LEC"]',
            3.0, 3.0, 1, '[]'
        ),
        (
            'SP27', 'PSYCH', '3140', 3140, 'Computational Psychology', 'Computational Psychology',
            'Comp psych.', 'UG', 'AS', 95002, '[]', '[]', '["LEC"]',
            3.0, 3.0, 1, '[]'
        ),
        (
            'SP27', 'PSYCH', '3800', 3800, 'Social Cognition', 'Social Cognition',
            'Cognition.', 'UG', 'AS', 95003, '[]', '[]', '["LEC"]',
            3.0, 3.0, 1, '[]'
        ),
        (
            'SP27', 'COGST', '3100', 3100, 'Intro to CogSci Research', 'Intro to CogSci Research',
            'CogSci.', 'UG', 'AS', 95004, '[]', '[]', '["LEC"]',
            3.0, 3.0, 1, '[]'
        ),
        (
            'SP27', 'INFO', '3450', 3450, 'Human-Computer Interaction', 'Human-Computer Interaction Design',
            'HCI.', 'UG', 'AS', 95005, '[]', '[]', '["LEC"]',
            3.0, 3.0, 1, '[]'
        )
        """
    )
    app.state.catalog._cs_index_cache.pop("SP27", None)

    # 1) Mixed closely related departments (PSYCH + COGST + INFO) soft-fills all 3 with advising warning
    await admin.put(
        "/api/user/prereqs",
        json={
            "completed_courses": ["PSYCH 3420", "COGST 3100", "INFO 3450"],
            "include_implied_prereqs": True,
        },
    )
    cl_mixed = (await admin.get("/api/cs/checklist", params={"roster": "SP27"})).json()
    slots_mixed = _flatten_checklist_slots(cl_mixed)
    assert {slots_mixed[f"ext_spec_{i}"]["course"] for i in range(1, 4)} == {
        "PSYCH 3420",
        "COGST 3100",
        "INFO 3450",
    }
    for i in range(1, 4):
        assert "Assistant Director, Undergraduate Advising" in slots_mixed[f"ext_spec_{i}"].get("warning", "")

    # 2) When 3 same-department PSYCH courses are available alongside COGST/INFO, same-dept wins with NO warning
    await admin.put(
        "/api/user/prereqs",
        json={
            "completed_courses": ["PSYCH 3420", "PSYCH 3140", "PSYCH 3800", "COGST 3100", "INFO 3450"],
            "include_implied_prereqs": True,
        },
    )
    cl_same = (await admin.get("/api/cs/checklist", params={"roster": "SP27"})).json()
    slots_same = _flatten_checklist_slots(cl_same)
    assert {slots_same[f"ext_spec_{i}"]["course"] for i in range(1, 4)} == {
        "PSYCH 3420",
        "PSYCH 3140",
        "PSYCH 3800",
    }
    for i in range(1, 4):
        assert not slots_same[f"ext_spec_{i}"].get("warning")


@pytest.mark.asyncio
async def test_transcript_import_grades_enrichment_and_scheduler_sync(app_client) -> None:
    app, admin = app_client
    await admin.post("/api/auth/bootstrap", json={"username": "tyler", "password": "password123"})

    db = app.state.db
    await db.execute(
        """
        INSERT OR REPLACE INTO rosters (slug, descr, is_default, archive_mode, strm, updated_at)
        VALUES ('FA26', 'Fall 2026', 0, 0, '2935', datetime('now'))
        """
    )
    await db.execute(
        """
        INSERT OR REPLACE INTO subjects (roster, value, descr, synced_at)
        VALUES ('FA26', 'CS', 'Computer Science', datetime('now'))
        """
    )
    eg_3780 = json.dumps(
        [{"classSections": [{"classNbr": 10101, "section": "001", "ssrComponent": "LEC", "openStatus": "O", "meetings": []}]}]
    )
    eg_4820 = json.dumps(
        [{"classSections": [{"classNbr": 10202, "section": "001", "ssrComponent": "LEC", "openStatus": "O", "meetings": []}]}]
    )
    await db.execute(
        """
        INSERT OR REPLACE INTO courses_meta (
            roster, subject, catalog_nbr, catalog_num, title_short, title_long,
            description, acad_career, acad_group, crse_id, enroll_groups_json,
            crosslists_json, components_json, units_min, units_max, has_letter_grade, crse_attrs_json
        ) VALUES
        (
            'FA26', 'CS', '3780', 3780, 'Intro Machine Learning', 'Introduction to Machine Learning',
            'ML.', 'UG', 'EN', 96001, ?, '[]', '["LEC"]', 4.0, 4.0, 1, '[]'
        ),
        (
            'FA26', 'CS', '4820', 4820, 'Intro Analysis Algorithms', 'Introduction to Analysis of Algorithms',
            'Algorithms.', 'UG', 'EN', 96002, ?, '[]', '["LEC"]', 4.0, 4.0, 1, '[]'
        )
        """,
        (eg_3780, eg_4820),
    )

    # Pre-seed already-added user state:
    # - Completed courses: CS 2110 (no details), CS 2800 (pinned manual slot w/ custom notes & empty gr/sem), MATH 1110 (keep intact)
    # - FA26 active schedule already has CS 3780 with custom color_idx=7, locked section [10101], selected_units=0 (missing)
    await admin.put(
        "/api/user/prereqs",
        json={"completed_courses": ["CS 2110", "CS 2800", "MATH 1110"], "include_implied_prereqs": True},
    )
    await admin.put(
        "/api/cs/checklist",
        params={"roster": "SP27"},
        json={
            "college": "arts",
            "curriculum": "current",
            "include_active_schedule": True,
            "pe_completed": 1,
            "slots": {
                "core_2800": {
                    "course": "CS 2800",
                    "title": "",
                    "cr": "",
                    "sem": "Done",
                    "gr": "",
                    "notes": "Keep my custom note",
                    "pinned": True,
                    "cleared": False,
                }
            },
        },
    )
    fa26_list = (await admin.get("/api/schedules", params={"roster": "FA26"})).json()
    fa26_sched_id = fa26_list["active"]["schedule"]["id"]
    await admin.post(
        f"/api/schedules/{fa26_sched_id}/courses",
        json={
            "subject": "CS",
            "catalog_nbr": "3780",
            "enabled": False,
            "selected_units": 0.0,
            "selected_class_nbrs": [10101],
            "locked_class_nbrs": [10101],
            "color_idx": 7,
        },
    )

    # Import transcript payload (sanitized courses + grades + in-progress FA26 courses)
    imp_res = await admin.post(
        "/api/cs/checklist/import-transcript",
        json={
            "roster": "SP27",
            "completed_courses": [
                {"course": "CS 2110", "sem": "FA24", "gr": "A", "cr": "4"},
                {"course": "CS 2800", "sem": "SP25", "gr": "A-", "cr": "4"},
                {"course": "CS 3110", "sem": "FA25", "gr": "B+", "cr": "4"},
                {"course": "CS 2110", "sem": "FA24", "gr": "A", "cr": "4"},  # duplicate in payload ignored
            ],
            "in_progress_courses": [
                {"course": "CS 3780", "roster": "FA26", "cr": "4"},
                {"course": "CS 4820", "roster": "FA26", "cr": "4"},
                {"course": "CS 3780", "roster": "FA26", "cr": "4"},  # duplicate in payload ignored
            ],
            "pe_completed": 2,
        },
    )
    assert imp_res.status_code == 200
    body = imp_res.json()
    cl = body["checklist"]
    summary = body["import_summary"]

    # Completed union preserves MATH 1110, adds CS 3110, enriches CS 2110 & CS 2800 without duplicates
    assert cl["completed_courses"] == ["CS 2110", "CS 2800", "CS 3110", "MATH 1110"]
    assert summary["added_completed"] == ["CS 3110"]
    assert set(summary["enriched_completed"]) == {"CS 2110", "CS 2800"}
    assert cl["pe_completed"] == 2
    assert cl["completed_course_details"]["CS 2110"] == {"gr": "A", "sem": "FA24", "cr": "4"}
    assert cl["completed_course_details"]["CS 3110"] == {"gr": "B+", "sem": "FA25", "cr": "4"}

    slots = _flatten_checklist_slots(cl)
    assert slots["intro_cs_2"]["course"] == "CS 2110"
    assert slots["intro_cs_2"]["gr"] == "A"
    assert slots["intro_cs_2"]["sem"] == "FA24"
    assert slots["intro_cs_2"]["cr"] == "4"
    # Manual slot preserves user's custom notes while upgrading placeholder "Done" & empty gr/cr
    assert slots["core_2800"]["notes"] == "Keep my custom note"
    assert slots["core_2800"]["gr"] == "A-"
    assert slots["core_2800"]["sem"] == "SP25"
    assert slots["core_2800"]["cr"] == "4"
    assert slots["core_3110"]["gr"] == "B+"
    assert slots["core_3110"]["sem"] == "FA25"

    # Re-auto-fill (clearing manual slots) keeps imported grades/terms attached to completed courses
    cl_reset = (
        await admin.put(
            "/api/cs/checklist",
            params={"roster": "SP27"},
            json={
                "college": "arts",
                "curriculum": "current",
                "include_active_schedule": True,
                "pe_completed": 2,
                "slots": {},
            },
        )
    ).json()
    reset_slots = _flatten_checklist_slots(cl_reset)
    assert reset_slots["intro_cs_2"]["gr"] == "A"
    assert reset_slots["core_2800"]["gr"] == "A-"
    assert reset_slots["core_2800"]["sem"] == "SP25"

    # Scheduler FA26 syncs into dedicated Transcript schedule while leaving custom Main Schedule untouched
    fa26_sched_res = summary["scheduler"][0]
    assert fa26_sched_res["roster"] == "FA26"
    assert fa26_sched_res["schedule_name"] == "Transcript"
    assert set(fa26_sched_res["added"]) == {"CS 3780", "CS 4820"}

    fa26_after = (await admin.get("/api/schedules", params={"roster": "FA26"})).json()
    assert fa26_after["active"]["schedule"]["name"] == "Transcript"
    assert fa26_after["active"]["schedule"]["is_transcript"] is True
    courses_by_code = {f"{c['subject']} {c['catalog_nbr']}": c for c in fa26_after["active"]["courses"]}
    assert set(courses_by_code.keys()) == {"CS 3780", "CS 4820"}
    assert courses_by_code["CS 3780"]["enabled"] is True
    assert courses_by_code["CS 3780"]["selected_units"] == 4.0
    assert courses_by_code["CS 4820"]["enabled"] is True
    assert courses_by_code["CS 4820"]["selected_units"] == 4.0

    # Original Main Schedule keeps its manual edits untouched
    main_sched_after = (await admin.get(f"/api/schedules/{fa26_sched_id}")).json()
    assert len(main_sched_after["courses"]) == 1
    assert main_sched_after["courses"][0]["color_idx"] == 7
    assert main_sched_after["courses"][0]["locked_class_nbrs"] == [10101]
    assert main_sched_after["courses"][0]["enabled"] is False

    # Re-importing the exact same transcript is idempotent (no duplicates, keeps everything unchanged)
    imp_again = (
        await admin.post(
            "/api/cs/checklist/import-transcript",
            json={
                "roster": "SP27",
                "completed_courses": [
                    {"course": "CS 2110", "sem": "FA24", "gr": "A", "cr": "4"},
                ],
                "in_progress_courses": [
                    {"course": "CS 3780", "roster": "FA26", "cr": "4"},
                    {"course": "CS 4820", "roster": "FA26", "cr": "4"},
                ],
            },
        )
    ).json()
    assert imp_again["import_summary"]["added_completed"] == []
    assert imp_again["import_summary"]["added_in_progress"] == []
    assert imp_again["import_summary"]["enriched_completed"] == []
    assert imp_again["import_summary"]["scheduler"][0]["added"] == []
    assert set(imp_again["import_summary"]["scheduler"][0]["already_present"]) == {"CS 3780", "CS 4820"}

    # Imported FA26 courses also populate Currently Taking boxes on SP27 checklist
    assert cl["in_progress_courses"] == ["CS 3780", "CS 4820"]
    assert summary["added_in_progress"] == ["CS 3780", "CS 4820"]
    assert slots["core_aiml"]["source"] == "in_progress"
    assert slots["core_aiml"]["sem"] == "FA26"
    assert slots["core_4820"]["source"] == "in_progress"


@pytest.mark.asyncio
async def test_cs_checklist_currently_taking_category_and_promotion(app_client) -> None:
    app, admin = app_client
    await admin.post("/api/auth/bootstrap", json={"username": "tyler", "password": "password123"})

    # Seed SP27 CS 5306 & CS 4780 plus next-term course requiring CS 4820
    db = app.state.db
    await db.execute(
        """
        INSERT INTO courses_meta (
            roster, subject, catalog_nbr, catalog_num, title_short, title_long, description,
            acad_career, acad_group, crse_id, enroll_groups_json, crosslists_json,
            components_json, units_min, units_max, has_letter_grade, crse_attrs_json
        ) VALUES
        (
            'FA26', 'CS', '5306', 5306, 'Crowdsourcing & Human Comp', 'Crowdsourcing and Human Computation',
            'Human-in-the-loop systems.', 'GR', 'EN', 94001, '[]', '[]', '["LEC"]',
            3.0, 3.0, 1, '[]'
        )
        """
    )
    # Completed: CS 4700; Currently Taking: CS 5306; What-If SP27 Schedule: MATH 2940
    await admin.put(
        "/api/user/prereqs",
        json={"completed_courses": ["CS 4700"], "include_implied_prereqs": True},
    )
    await admin.post(
        "/api/schedules/quick-add",
        json={"roster": "SP27", "subject": "MATH", "catalog_nbr": "2940"},
    )

    res = await admin.put(
        "/api/cs/checklist",
        params={"roster": "SP27"},
        json={
            "college": "arts",
            "curriculum": "current",
            "include_active_schedule": True,
            "pe_completed": 0,
            "slots": {},
            "sync_in_progress_courses": ["CS 5306", "CS 4820"],
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["in_progress_courses"] == ["CS 4820", "CS 5306"]
    slots = _flatten_checklist_slots(body)

    # CS 4820 fills core_4820 as in_progress, CS 5306 fills a CS Elective as in_progress
    assert slots["core_4820"]["course"] == "CS 4820"
    assert slots["core_4820"]["source"] == "in_progress"
    assert slots["core_4820"]["sem"] == "Taking"
    elec_by_course = {
        slots[f"cs_elec_{i}"]["course"]: slots[f"cs_elec_{i}"] for i in (1, 2) if slots[f"cs_elec_{i}"]["filled"]
    }
    assert elec_by_course["CS 4700"]["source"] == "completed"
    assert elec_by_course["CS 5306"]["source"] == "in_progress"
    assert elec_by_course["CS 5306"]["title"] == "Crowdsourcing and Human Computation"
    assert slots["math_linalg"]["course"] == "MATH 2940"
    assert slots["math_linalg"]["source"] == "schedule"

    assert body["summary"]["in_progress_slots"] == 2
    assert body["summary"]["completed_slots"] >= 1
    assert body["summary"]["whatif_slots"] >= 1

    # Promote CS 5306 from Currently Taking -> Completed (with grade)
    promoted = await admin.put(
        "/api/cs/checklist",
        params={"roster": "SP27"},
        json={
            "college": "arts",
            "curriculum": "current",
            "include_active_schedule": True,
            "pe_completed": 0,
            "slots": {},
            "sync_completed_courses": ["CS 4700", "CS 5306"],
            "sync_in_progress_courses": ["CS 4820"],
        },
    )
    assert promoted.status_code == 200
    p_body = promoted.json()
    assert p_body["completed_courses"] == ["CS 4700", "CS 5306"]
    assert p_body["in_progress_courses"] == ["CS 4820"]
    p_slots = _flatten_checklist_slots(p_body)
    p_by_course = {sl["course"]: sl for sl in p_slots.values() if sl["course"]}
    assert p_by_course["CS 5306"]["source"] == "completed"
    assert p_by_course["CS 4820"]["source"] == "in_progress"
    assert p_body["summary"]["in_progress_slots"] == 1


@pytest.mark.asyncio
async def test_transcript_import_past_semesters_sync_to_scheduler(app_client) -> None:
    app, admin = app_client
    await admin.post("/api/auth/bootstrap", json={"username": "tyler", "password": "password123"})

    db = app.state.db
    await db.execute(
        """
        INSERT OR REPLACE INTO rosters (slug, descr, is_default, archive_mode, strm, updated_at)
        VALUES
            ('FA24', 'Fall 2024', 0, 1, '2879', datetime('now')),
            ('SP25', 'Spring 2025', 0, 1, '2893', datetime('now'))
        """
    )
    for roster_slug, subj, nbr, cid, title in (
        ("FA24", "CS", "1110", 95001, "Intro to Computing: Python"),
        ("SP25", "CS", "2110", 95002, "OO Programming & Data Structures"),
        ("FA26", "CS", "5306", 95003, "Crowdsourcing and Human Computation"),
    ):
        await db.execute(
            """
            INSERT INTO subjects (roster, value, descr, synced_at)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(roster, value) DO UPDATE SET synced_at = datetime('now')
            """,
            (roster_slug, subj, subj),
        )
        await db.execute(
            """
            INSERT INTO courses_meta (
                roster, subject, catalog_nbr, catalog_num, title_short, title_long, description,
                acad_career, acad_group, crse_id, enroll_groups_json, crosslists_json,
                components_json, units_min, units_max, has_letter_grade, crse_attrs_json
            ) VALUES (?, ?, ?, ?, ?, ?, '', 'UG', 'EN', ?, '[]', '[]', '["LEC"]', 4.0, 4.0, 1, '[]')
            """,
            (roster_slug, subj, nbr, int(nbr), title, title, cid),
        )

    res = await admin.post(
        "/api/cs/checklist/import-transcript",
        json={
            "roster": "SP27",
            "completed_courses": [
                {"course": "MATH 1110", "sem": "AP FA24", "gr": "S", "cr": "4"},
                {"course": "CS 2110", "sem": "SP25", "gr": "A-", "cr": "4"},
                {"course": "CS 1110", "sem": "FA24", "gr": "A", "cr": "4"},
            ],
            "in_progress_courses": [
                {"course": "CS 5306", "roster": "FA26", "cr": "3"},
            ],
            "sync_completed_to_scheduler": True,
        },
    )
    assert res.status_code == 200
    sched_results = res.json()["import_summary"]["scheduler"]
    # Synced chronologically: FA24, SP25, FA26 (and AP credits are NOT turned into a schedule)
    assert [s["roster"] for s in sched_results] == ["FA24", "SP25", "FA26"]
    assert sched_results[0]["added"] == ["CS 1110"]
    assert sched_results[1]["added"] == ["CS 2110"]
    assert sched_results[2]["added"] == ["CS 5306"]

    fa24 = (await admin.get("/api/schedules", params={"roster": "FA24"})).json()
    sp25 = (await admin.get("/api/schedules", params={"roster": "SP25"})).json()
    assert fa24["active"]["schedule"]["name"] == "Transcript"
    assert fa24["active"]["schedule"]["is_transcript"] is True
    assert sp25["active"]["schedule"]["is_transcript"] is True
    assert [f"{c['subject']} {c['catalog_nbr']}" for c in fa24["active"]["courses"]] == ["CS 1110"]
    assert [f"{c['subject']} {c['catalog_nbr']}" for c in sp25["active"]["courses"]] == ["CS 2110"]


@pytest.mark.asyncio
async def test_dedicated_transcript_schedule_locked_and_duplicatable(app_client) -> None:
    app, admin = app_client
    await admin.post("/api/auth/bootstrap", json={"username": "tyler", "password": "password123"})

    db = app.state.db
    await db.execute(
        """
        INSERT INTO subjects (roster, value, descr, synced_at)
        VALUES ('FA26', 'CS', 'CS', datetime('now')), ('FA26', 'MATH', 'MATH', datetime('now'))
        ON CONFLICT(roster, value) DO UPDATE SET synced_at = datetime('now')
        """
    )
    enroll_groups_cs = [
        {
            "enrollGroup": 0,
            "unitsMinimum": 3.0,
            "unitsMaximum": 4.0,
            "classSections": [
                {
                    "classNbr": 30101,
                    "ssrComponent": "LEC",
                    "section": "001",
                    "openStatus": "O",
                    "campus": "MAIN",
                    "location": "ITH",
                    "meetings": [{"pattern": "MWF", "timeStart": "10:10AM", "timeEnd": "11:00AM"}],
                },
                {
                    "classNbr": 30102,
                    "ssrComponent": "DIS",
                    "section": "201",
                    "openStatus": "O",
                    "campus": "MAIN",
                    "location": "ITH",
                    "meetings": [{"pattern": "T", "timeStart": "01:25PM", "timeEnd": "02:15PM"}],
                },
                {
                    "classNbr": 30103,
                    "ssrComponent": "DIS",
                    "section": "202",
                    "openStatus": "C",
                    "campus": "MAIN",
                    "location": "ITH",
                    "meetings": [{"pattern": "R", "timeStart": "02:55PM", "timeEnd": "03:45PM"}],
                },
            ],
        }
    ]
    import orjson as _orjson

    await db.execute(
        """
        INSERT INTO courses_meta (
            roster, subject, catalog_nbr, catalog_num, title_short, title_long, description,
            acad_career, acad_group, crse_id, enroll_groups_json, crosslists_json,
            components_json, units_min, units_max, has_letter_grade, crse_attrs_json
        ) VALUES
        ('FA26', 'CS', '3110', 3110, 'Functional Prog', 'Functional Programming', '', 'UG', 'EN', 96001, ?, '[]', '["LEC","DIS"]', 3.0, 4.0, 1, '[]'),
        ('FA26', 'MATH', '2940', 2940, 'Linear Algebra', 'Linear Algebra', '', 'UG', 'AS', 96002, '[]', '[]', '["LEC"]', 4.0, 4.0, 1, '[]')
        """,
        (_orjson.dumps(enroll_groups_cs).decode(),),
    )

    # Custom active schedule has a non-transcript course (MATH 2940) -> importing must keep it active & untouched
    fa26_init = (await admin.get("/api/schedules", params={"roster": "FA26"})).json()
    custom_id = fa26_init["active"]["schedule"]["id"]
    await admin.post(f"/api/schedules/{custom_id}/courses", json={"subject": "MATH", "catalog_nbr": "2940"})

    imp_res = await admin.post(
        "/api/cs/checklist/import-transcript",
        json={
            "roster": "SP27",
            "in_progress_courses": [{"course": "CS 3110", "roster": "FA26", "cr": ""}],
        },
    )
    assert imp_res.status_code == 200
    assert imp_res.json()["import_summary"]["scheduler"][0]["schedule_name"] == "Transcript"

    fa26_list = (await admin.get("/api/schedules", params={"roster": "FA26"})).json()
    # Custom Main Schedule stayed active because it had non-transcript course MATH 2940
    assert fa26_list["active"]["schedule"]["id"] == custom_id
    assert [c["subject"] for c in fa26_list["active"]["courses"]] == ["MATH"]

    transcript_meta = next(s for s in fa26_list["schedules"] if s["is_transcript"])
    t_id = transcript_meta["id"]
    t_sched = (await admin.get(f"/api/schedules/{t_id}")).json()
    assert t_sched["schedule"]["is_transcript"] is True
    assert len(t_sched["courses"]) == 1
    item_id = t_sched["courses"][0]["id"]

    # Force selected_units to 0 & color_idx to 5, then re-import with cr="4" to verify enrichment on Transcript schedule
    await db.execute("UPDATE schedule_courses SET selected_units = 0.0, color_idx = 5 WHERE id = ?", (item_id,))
    imp_enrich = await admin.post(
        "/api/cs/checklist/import-transcript",
        json={
            "roster": "SP27",
            "in_progress_courses": [{"course": "CS 3110", "roster": "FA26", "cr": "4"}],
        },
    )
    assert imp_enrich.status_code == 200
    assert imp_enrich.json()["import_summary"]["scheduler"][0]["updated"] == ["CS 3110"]
    t_enriched = (await admin.get(f"/api/schedules/{t_id}")).json()
    assert t_enriched["courses"][0]["selected_units"] == 4.0
    assert t_enriched["courses"][0]["color_idx"] == 5

    # Locked membership & rename on Transcript schedule -> 403 Forbidden
    assert (await admin.post(f"/api/schedules/{t_id}/courses", json={"subject": "MATH", "catalog_nbr": "2940"})).status_code == 403
    assert (await admin.delete(f"/api/schedules/{t_id}/courses/{item_id}")).status_code == 403
    assert (await admin.patch(f"/api/schedules/{t_id}/courses/{item_id}", json={"enabled": False})).status_code == 403
    assert (await admin.patch(f"/api/schedules/{t_id}", json={"name": "Renamed"})).status_code == 403

    # Activate Transcript -> quick-add also returns 403 cleanly
    await admin.patch(f"/api/schedules/{t_id}", json={"is_active": True})
    assert (await admin.post("/api/schedules/quick-add", json={"roster": "FA26", "subject": "MATH", "catalog_nbr": "2940"})).status_code == 403

    # Section swap, lock pin, Auto-Generate apply, and busy blocks STILL work on Transcript!
    swap_res = await admin.patch(
        f"/api/schedules/{t_id}/courses/{item_id}",
        json={"selected_class_nbrs": [30101, 30103], "locked_class_nbrs": [30101]},
    )
    assert swap_res.status_code == 200
    assert swap_res.json()["courses"][0]["selected_class_nbrs"] == [30101, 30103]
    assert swap_res.json()["courses"][0]["locked_class_nbrs"] == [30101]

    gen_res = await admin.put(
        f"/api/schedules/{t_id}/apply-generated",
        json={"items": [{"item_id": item_id, "selected_class_nbrs": [30101, 30102]}]},
    )
    assert gen_res.status_code == 200
    assert gen_res.json()["courses"][0]["selected_class_nbrs"] == [30101, 30102]

    blk_res = await admin.post(
        f"/api/schedules/{t_id}/blocks",
        json={"label": "Club", "days": ["F"], "start_min": 900, "end_min": 960},
    )
    assert blk_res.status_code == 201

    # Duplicating Transcript creates an unrestricted editable plan
    dup_res = await admin.post(
        "/api/schedules",
        json={"roster": "FA26", "name": "Editable Copy", "duplicate_from_id": t_id},
    )
    assert dup_res.status_code == 201
    dup_body = dup_res.json()["active"]
    assert dup_body["schedule"]["is_transcript"] is False
    dup_id = dup_body["schedule"]["id"]
    assert (await admin.post(f"/api/schedules/{dup_id}/courses", json={"subject": "MATH", "catalog_nbr": "2940"})).status_code == 201


@pytest.mark.asyncio
async def test_drop_odds_unwatched_recording_and_endpoints(app_client, fake_provider) -> None:
    from datetime import datetime, timedelta, timezone
    from app.providers.base import CourseRecord, RosterRecord, SectionRecord
    from app.services.drop_odds import compute_drop_odds

    app, admin = app_client
    db = app.state.db
    await admin.post("/api/auth/bootstrap", json={"username": "tyler", "password": "password123"})

    fake_provider.rosters = [
        RosterRecord(slug="SP27", descr="Spring 2027", is_default=True, archive_mode=False, strm="2951"),
        RosterRecord(slug="FA26", descr="Fall 2026", is_default=False, archive_mode=True, strm="2937"),
    ]
    await app.state.catalog.sync_rosters_and_subjects()

    # Verify Drop Odds tier classification boundaries cleanly
    now = datetime(2027, 1, 20, 12, 0, tzinfo=timezone.utc)
    assert compute_drop_odds([], tracking_days=0.2, now=now)["tier"] == "untracked"
    assert compute_drop_odds([], tracking_days=1.5, now=now)["tier"] == "none"

    low_ev = [{"id": 1, "class_nbr": 100, "new_status": "O", "detected_at": (now - timedelta(days=10)).isoformat()}]
    assert compute_drop_odds(low_ev, tracking_days=12.0, now=now)["tier"] == "low"

    mod_evs = [
        {"id": 1, "class_nbr": 100, "new_status": "O", "detected_at": (now - timedelta(days=2)).isoformat()},
        {"id": 2, "class_nbr": 100, "new_status": "C", "detected_at": (now - timedelta(days=2) + timedelta(seconds=90)).isoformat()},
        {"id": 3, "class_nbr": 100, "new_status": "O", "detected_at": (now - timedelta(days=1)).isoformat()},
    ]
    mod_odds = compute_drop_odds(mod_evs, tracking_days=5.0, now=now)
    assert mod_odds["tier"] == "moderate"
    assert mod_odds["opened_7d"] == 2
    assert mod_odds["median_open_sec_7d"] == 90.0

    high_evs = [
        {"id": i + 1, "class_nbr": 200, "new_status": "O", "detected_at": (now - timedelta(hours=i + 1)).isoformat()}
        for i in range(3)
    ]
    assert compute_drop_odds(high_evs, tracking_days=1.0, now=now)["tier"] == "high"

    # Seed SP27 CS with watched CS 4701 AND unwatched CS 3110
    def make_cs_courses(s3110: str, s4701: str) -> list[CourseRecord]:
        return [
            CourseRecord(
                roster="SP27",
                subject="CS",
                catalog_nbr="3110",
                title_short="Data Structures",
                title_long="Data Structures and Functional Programming",
                description="OCaml.",
                crse_id=71001,
                acad_career="UG",
                acad_group="EN",
                enroll_groups=[{"componentsRequired": ["LEC"], "unitsMinimum": 4, "unitsMaximum": 4}],
                sections=[
                    SectionRecord(
                        class_nbr=31101,
                        enroll_group_idx=0,
                        ssr_component="LEC",
                        section="001",
                        open_status=s3110,
                        components_required=["LEC"],
                    )
                ],
            ),
            CourseRecord(
                roster="SP27",
                subject="CS",
                catalog_nbr="4701",
                title_short="Practicum in AI",
                title_long="Practicum in Artificial Intelligence",
                description="AI.",
                crse_id=71002,
                acad_career="UG",
                acad_group="EN",
                enroll_groups=[{"componentsRequired": ["LEC"], "unitsMinimum": 2, "unitsMaximum": 2}],
                sections=[
                    SectionRecord(
                        class_nbr=47011,
                        enroll_group_idx=0,
                        ssr_component="LEC",
                        section="001",
                        open_status=s4701,
                        components_required=["LEC"],
                    )
                ],
            ),
        ]

    # 1) Initial catalog sync establishes first_synced_at & baseline section statuses
    fake_provider.courses_by_bucket[("SP27", "CS")] = make_cs_courses("C", "C")
    await app.state.catalog.ensure_subject_synced("SP27", "CS", force=True)
    subj_before = await db.fetch_one("SELECT first_synced_at FROM subjects WHERE roster = 'SP27' AND value = 'CS'")
    assert subj_before and subj_before["first_synced_at"] is not None

    # 2) Catalog re-sync detects CS 3110 flipping C -> O into status_events and preserves first_synced_at
    fake_provider.courses_by_bucket[("SP27", "CS")] = make_cs_courses("O", "C")
    await app.state.catalog.ensure_subject_synced("SP27", "CS", force=True)
    subj_after = await db.fetch_one("SELECT first_synced_at FROM subjects WHERE roster = 'SP27' AND value = 'CS'")
    assert subj_after and subj_after["first_synced_at"] == subj_before["first_synced_at"]
    cat_ev = await db.fetch_all(
        "SELECT * FROM status_events WHERE roster = 'SP27' AND subject = 'CS' AND catalog_nbr = '3110'"
    )
    assert len(cat_ev) == 1
    assert cat_ev[0]["old_status"] == "C"
    assert cat_ev[0]["new_status"] == "O"
    assert cat_ev[0]["poll_rtt_ms"] == 0

    # 3) Archived roster re-sync must NOT log status_events diffs
    fake_provider.courses_by_bucket[("FA26", "CS")] = [
        CourseRecord(
            roster="FA26",
            subject="CS",
            catalog_nbr="3110",
            title_short="Data Structures",
            title_long="Data Structures",
            description="OCaml.",
            crse_id=71001,
            acad_career="UG",
            acad_group="EN",
            enroll_groups=[{"componentsRequired": ["LEC"], "unitsMinimum": 4, "unitsMaximum": 4}],
            sections=[
                SectionRecord(
                    class_nbr=31199,
                    enroll_group_idx=0,
                    ssr_component="LEC",
                    section="001",
                    open_status="C",
                    components_required=["LEC"],
                )
            ],
        )
    ]
    await app.state.catalog.ensure_subject_synced("FA26", "CS", force=True)
    fake_provider.courses_by_bucket[("FA26", "CS")][0].sections[0].open_status = "O"
    await app.state.catalog.ensure_subject_synced("FA26", "CS", force=True)
    assert await db.fetch_all("SELECT * FROM status_events WHERE roster = 'FA26'") == []

    # 4) Watch ONLY CS 4701, then run poller when UNWATCHED CS 3110 flips O -> C -> O
    w_res = await admin.post(
        "/api/watches",
        json={"roster": "SP27", "subject": "CS", "catalog_nbr": "4701", "class_nbr": 47011, "mode": "exact"},
    )
    assert w_res.status_code == 201
    watch_id = w_res.json()["watch"]["id"]

    await app.state.poller.hydrate_from_db()
    fake_provider.courses_by_bucket[("SP27", "CS")] = make_cs_courses("C", "C")
    await app.state.poller.poll_bucket("SP27", "CS")
    fake_provider.courses_by_bucket[("SP27", "CS")] = make_cs_courses("O", "C")
    await app.state.poller.poll_bucket("SP27", "CS")

    unwatched_events = await db.fetch_all(
        "SELECT old_status, new_status FROM status_events WHERE roster = 'SP27' AND subject = 'CS' AND catalog_nbr = '3110' ORDER BY id ASC"
    )
    assert [(e["old_status"], e["new_status"]) for e in unwatched_events] == [("C", "O"), ("O", "C"), ("C", "O")]

    # 5) Check Search, Course Detail, WatchList, History, and Telemetry Metrics surface drop_odds & leaderboard
    search_res = await admin.get("/api/courses/search", params={"roster": "SP27", "subject": "CS", "q": "3110"})
    assert search_res.status_code == 200
    cs3110 = search_res.json()["courses"][0]
    assert cs3110["drop_odds"]["tier"] == "moderate"
    assert cs3110["drop_odds"]["opened_7d"] == 2

    detail_res = await admin.get("/api/courses/SP27/CS/3110")
    assert detail_res.status_code == 200
    assert detail_res.json()["course"]["drop_odds"]["opened_7d"] == 2

    watches_res = await admin.get("/api/watches")
    assert watches_res.status_code == 200
    w_item = next(w for w in watches_res.json()["watches"] if w["id"] == watch_id)
    assert w_item["drop_odds"]["tier"] == "untracked"

    hist_res = await admin.get(f"/api/watches/{watch_id}/history")
    assert hist_res.status_code == 200
    assert hist_res.json()["drop_odds"]["tier"] == "untracked"

    metrics_res = await admin.get("/api/metrics")
    assert metrics_res.status_code == 200
    lb = metrics_res.json()["drop_leaderboard"]
    assert len(lb) >= 1
    assert lb[0]["subject"] == "CS"
    assert lb[0]["catalog_nbr"] == "3110"
    assert lb[0]["opened_7d"] == 2
