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
    # All 3 CS Electives + 1 Tech Elective filled cleanly across FA26 & uncached historical codes
    filled_elective_courses = {
        slots["cs_elec_1"]["course"],
        slots["cs_elec_2"]["course"],
        slots["cs_elec_3"]["course"],
        slots["tech_elec_1"]["course"],
    }
    assert filled_elective_courses == {"CS 4700", "CS 5112", "CS 5306", "CS 5470"}
    # Titles hydrated from FA26 courses_meta even when viewing SP27
    by_course = {sl["course"]: sl for sl in slots.values() if sl["course"]}
    assert by_course["CS 5470"]["title"] == "Systems for Large-Scale ML"
    assert by_course["CS 5306"]["title"] == "Crowdsourcing and Human Computation"


@pytest.mark.asyncio
async def test_batch_load_schedule_insights(app_client) -> None:
    app, admin = app_client
    await admin.post("/api/auth/bootstrap", json={"username": "tyler", "password": "password123"})

    qa = await admin.post("/api/schedules/quick-add", json={"roster": "SP27", "subject": "CS", "catalog_nbr": "2110"})
    sched_id = qa.json()["active"]["schedule"]["id"]

    calls: list[tuple[str, str, str]] = []

    async def fake_get_course_insights(roster: str, subject: str, catalog_nbr: str, force: bool = False):
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
