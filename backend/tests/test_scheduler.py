"""Unit and API integration tests for the Scheduler service and routes."""

from __future__ import annotations

import httpx
import pytest

from app.services.scheduler import normalize_enroll_groups, parse_pattern_days, parse_time_to_minutes


def test_parse_time_and_pattern_helpers() -> None:
    assert parse_time_to_minutes("10:10AM") == 610
    assert parse_time_to_minutes("12:00PM") == 720
    assert parse_time_to_minutes("12:30AM") == 30
    assert parse_time_to_minutes("01:25PM") == 805
    assert parse_time_to_minutes("TBA") is None

    assert parse_pattern_days("MWF") == ["M", "W", "F"]
    assert parse_pattern_days("TR") == ["T", "R"]
    assert parse_pattern_days("SaSu") == ["Sa", "Su"]
    assert parse_pattern_days("S") == ["Sa"]
    assert parse_pattern_days("TBA") == []


def test_normalize_enroll_groups_overlays_live_status() -> None:
    raw_egs = [
        {
            "componentsRequired": ["LEC", "DIS"],
            "unitsMinimum": 3,
            "unitsMaximum": 4,
            "gradingBasis": "GRD",
            "sessionCode": "1",
            "classSections": [
                {
                    "classNbr": 6582,
                    "ssrComponent": "LEC",
                    "section": "001",
                    "openStatus": "C",
                    "campus": "MAIN",
                    "location": "ITH",
                    "locationDescr": "Ithaca",
                    "instrModeDescrshort": "In Person",
                    "meetings": [
                        {
                            "pattern": "TR",
                            "timeStart": "10:10AM",
                            "timeEnd": "11:25AM",
                            "startDt": "01/21/2027",
                            "endDt": "05/05/2027",
                            "facilityDescr": "Gates Hall G01",
                            "instructors": [{"firstName": "Erasmo", "lastName": "Tani"}],
                        }
                    ],
                }
            ],
        }
    ]
    live_rows = [
        {
            "class_nbr": 6582,
            "enroll_group_idx": 0,
            "ssr_component": "LEC",
            "section": "001",
            "open_status": "O",
            "meetings_summary": "TR 10:10AM-11:25AM (Gates Hall G01)",
            "instructors_summary": "Erasmo Tani",
            "campus": "MAIN",
            "location": "ITH",
            "location_descr": "Ithaca",
            "instruction_mode": "In Person",
            "updated_at": "2027-01-10T12:00:00",
        }
    ]

    norm = normalize_enroll_groups(raw_egs, live_rows)
    assert len(norm) == 1
    assert norm[0]["units_min"] == 3.0
    assert norm[0]["units_max"] == 4.0
    sec = norm[0]["sections"][0]
    assert sec["open_status"] == "O"
    assert sec["meetings"][0]["days"] == ["T", "R"]
    assert sec["meetings"][0]["start_min"] == 610
    assert sec["meetings"][0]["end_min"] == 685
    assert sec["meetings"][0]["facility_descr"] == "Gates Hall G01"


@pytest.mark.asyncio
async def test_scheduler_crud_quick_add_blocks_and_sharing(app_client) -> None:
    app, admin = app_client

    await admin.post("/api/auth/bootstrap", json={"username": "tyler", "password": "password123"})
    inv = (await admin.post("/api/admin/invites", json={"max_uses": 1})).json()["invite"]["code"]

    # Default schedule auto-created for roster
    res = await admin.get("/api/schedules", params={"roster": "SP27"})
    assert res.status_code == 200
    body = res.json()
    assert len(body["schedules"]) == 1
    sched_id = body["active"]["schedule"]["id"]
    assert body["active"]["schedule"]["name"] == "Main Schedule"
    assert body["active"]["schedule"]["share_enabled"] is False

    # Quick-add CS 2110 to active schedule
    qa = await admin.post(
        "/api/schedules/quick-add",
        json={"roster": "SP27", "subject": "CS", "catalog_nbr": "2110"},
    )
    assert qa.status_code == 200
    assert qa.json()["already_present"] is False
    courses = qa.json()["active"]["courses"]
    assert len(courses) == 1
    cs_item = courses[0]
    assert cs_item["subject"] == "CS"
    assert cs_item["catalog_nbr"] == "2110"
    assert 6582 in cs_item["selected_class_nbrs"]
    assert len(cs_item["enroll_groups"][0]["sections"]) == 3
    assert cs_item["enroll_groups"][0]["sections"][0]["meetings"][0]["days"] == ["T", "R"]

    # Duplicate quick-add reports already_present cleanly
    qa2 = await admin.post(
        "/api/schedules/quick-add",
        json={"roster": "SP27", "subject": "CS", "catalog_nbr": "2110"},
    )
    assert qa2.status_code == 200
    assert qa2.json()["already_present"] is True

    # Add MATH 2940 + update section & lock
    add_math = await admin.post(
        f"/api/schedules/{sched_id}/courses",
        json={"subject": "MATH", "catalog_nbr": "2940"},
    )
    assert add_math.status_code == 201
    assert len(add_math.json()["courses"]) == 2

    upd_cs = await admin.patch(
        f"/api/schedules/{sched_id}/courses/{cs_item['id']}",
        json={"selected_class_nbrs": [6582, 6585], "locked_class_nbrs": [6582]},
    )
    assert upd_cs.status_code == 200
    updated_cs = next(c for c in upd_cs.json()["courses"] if c["id"] == cs_item["id"])
    assert updated_cs["selected_class_nbrs"] == [6582, 6585]
    assert updated_cs["locked_class_nbrs"] == [6582]

    # Apply generated schedule sections
    gen_res = await admin.put(
        f"/api/schedules/{sched_id}/apply-generated",
        json={"items": [{"item_id": cs_item["id"], "selected_class_nbrs": [6582, 6584]}]},
    )
    assert gen_res.status_code == 200
    applied_cs = next(c for c in gen_res.json()["courses"] if c["id"] == cs_item["id"])
    assert applied_cs["selected_class_nbrs"] == [6582, 6584]

    # Add, toggle, and delete busy time block
    blk_res = await admin.post(
        f"/api/schedules/{sched_id}/blocks",
        json={"label": "Lunch", "days": ["M", "W", "F"], "start_min": 720, "end_min": 780},
    )
    assert blk_res.status_code == 201
    blk_id = blk_res.json()["blocks"][0]["id"]
    assert blk_res.json()["blocks"][0]["days"] == ["M", "W", "F"]

    blk_upd = await admin.patch(
        f"/api/schedules/{sched_id}/blocks/{blk_id}",
        json={"enabled": False},
    )
    assert blk_upd.status_code == 200
    assert blk_upd.json()["blocks"][0]["enabled"] is False

    # Enable opt-in sharing & test unauthenticated public shared view
    share_on = await admin.patch(
        f"/api/schedules/{sched_id}",
        json={"share_enabled": True, "name": "Spring Dream Plan"},
    )
    assert share_on.status_code == 200
    token = share_on.json()["active"]["schedule"]["share_token"]
    assert token
    assert share_on.json()["active"]["schedule"]["share_url"] == f"https://sniper.hodgman.net/?share={token}"

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://sniper.hodgman.net") as anon:
        pub = await anon.get(f"/api/schedules/shared/{token}")
        assert pub.status_code == 200
        pub_data = pub.json()
        assert pub_data["owner_username"] == "tyler"
        assert pub_data["schedule"]["name"] == "Spring Dream Plan"
        assert len(pub_data["courses"]) == 2

    # Regenerate token invalidates old link
    regen = await admin.patch(f"/api/schedules/{sched_id}", json={"regenerate_share_token": True})
    assert regen.status_code == 200
    new_token = regen.json()["active"]["schedule"]["share_token"]
    assert new_token != token
    assert (await admin.get(f"/api/schedules/shared/{token}")).status_code == 404
    assert (await admin.get(f"/api/schedules/shared/{new_token}")).status_code == 200

    # Turn off sharing -> public link returns 404
    share_off = await admin.patch(f"/api/schedules/{sched_id}", json={"share_enabled": False})
    assert share_off.status_code == 200
    assert (await admin.get(f"/api/schedules/shared/{new_token}")).status_code == 404

    # Duplicate schedule
    dup = await admin.post(
        "/api/schedules",
        json={"roster": "SP27", "name": "Backup Plan", "duplicate_from_id": sched_id},
    )
    assert dup.status_code == 201
    assert len(dup.json()["schedules"]) == 2
    assert len(dup.json()["active"]["courses"]) == 2
    assert len(dup.json()["active"]["blocks"]) == 1
    dup_id = dup.json()["active"]["schedule"]["id"]

    # Cross-user isolation
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://sniper.hodgman.net") as friend:
        await friend.post("/api/auth/register", json={"invite_code": inv, "username": "alex", "password": "password123"})
        assert (await friend.get(f"/api/schedules/{sched_id}")).status_code == 404
        assert (await friend.patch(f"/api/schedules/{sched_id}", json={"name": "Hacked"})).status_code == 404
        assert (await friend.delete(f"/api/schedules/{dup_id}")).status_code == 404

    # Delete duplicate schedule and block
    del_blk = await admin.delete(f"/api/schedules/{sched_id}/blocks/{blk_id}")
    assert del_blk.status_code == 200
    assert del_blk.json()["blocks"] == []

    del_dup = await admin.delete(f"/api/schedules/{dup_id}")
    assert del_dup.status_code == 200
    assert len(del_dup.json()["schedules"]) == 1
