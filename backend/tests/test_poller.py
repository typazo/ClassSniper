"""Tests for PollerEngine diffing, watch modes, anti-spam cooldowns, and priority scheduling."""

from __future__ import annotations

import pytest

from app.services.poller import _BucketMeta
from tests.conftest import make_sample_courses


@pytest.mark.asyncio
async def test_exact_watch_transition_cooldown_and_autopause(app_client) -> None:
    app, client = app_client
    poller = app.state.poller

    await client.post("/api/auth/bootstrap", json={"username": "tyler", "password": "password123"})

    # Watch 6584 (DIS 202) exact, with auto_pause=True
    res = await client.post(
        "/api/watches",
        json={
            "roster": "SP27",
            "subject": "CS",
            "catalog_nbr": "2110",
            "class_nbr": 6584,
            "mode": "exact",
            "trigger_on": "open",
            "auto_pause": True,
            "cooldown_sec": 120,
        },
    )
    assert res.status_code == 201
    watch_id = res.json()["watch"]["id"]

    # Poll with all closed -> no alert
    alerts = await poller.evaluate_courses("SP27", "CS", make_sample_courses(lec_status="C", dis202_status="C"))
    assert alerts == []

    # Waitlist status should NOT trigger trigger_on='open'
    alerts = await poller.evaluate_courses("SP27", "CS", make_sample_courses(lec_status="C", dis202_status="W"))
    assert alerts == []

    # Open status triggers alert AND auto-pauses watch
    alerts = await poller.evaluate_courses("SP27", "CS", make_sample_courses(lec_status="C", dis202_status="O"), rtt_ms=19)
    assert len(alerts) == 1
    assert alerts[0].section.class_nbr == 6584
    assert alerts[0].old_status == "W"
    assert alerts[0].new_status == "O"

    w_list = (await client.get("/api/watches")).json()["watches"]
    assert w_list[0]["id"] == watch_id
    assert w_list[0]["active"] is False

    # Re-arming and flipping closed -> open within cooldown should be suppressed until re-arm clears cooldown
    await client.post(f"/api/watches/{watch_id}/rearm")
    alerts_c = await poller.evaluate_courses("SP27", "CS", make_sample_courses(lec_status="C", dis202_status="C"))
    assert alerts_c == []
    alerts_o = await poller.evaluate_courses("SP27", "CS", make_sample_courses(lec_status="C", dis202_status="O"))
    assert len(alerts_o) == 1

    # Now disable auto_pause, test cooldown suppression when flapping C -> O within 120s
    await client.post(f"/api/watches/{watch_id}/rearm")
    await client.patch(f"/api/watches/{watch_id}", json={"auto_pause": False, "cooldown_sec": 120})
    await poller.evaluate_courses("SP27", "CS", make_sample_courses(lec_status="C", dis202_status="C"))
    first_fire = await poller.evaluate_courses("SP27", "CS", make_sample_courses(lec_status="C", dis202_status="O"))
    assert len(first_fire) == 1
    await poller.evaluate_courses("SP27", "CS", make_sample_courses(lec_status="C", dis202_status="C"))
    suppressed = await poller.evaluate_courses("SP27", "CS", make_sample_courses(lec_status="C", dis202_status="O"))
    assert suppressed == []


@pytest.mark.asyncio
async def test_linked_group_requires_companion_lecture(app_client) -> None:
    app, client = app_client
    poller = app.state.poller

    await client.post("/api/auth/bootstrap", json={"username": "tyler", "password": "password123"})
    res = await client.post(
        "/api/watches",
        json={
            "roster": "SP27",
            "subject": "CS",
            "catalog_nbr": "2110",
            "class_nbr": 6584,
            "mode": "linked_group",
            "trigger_on": "open",
            "auto_pause": False,
        },
    )
    assert res.status_code == 201

    # DIS 202 opens while LEC 001 is still CLOSED -> linked_group must NOT alert
    alerts = await poller.evaluate_courses("SP27", "CS", make_sample_courses(lec_status="C", dis202_status="O"))
    assert alerts == []

    # Now LEC 001 opens too -> linked_group becomes READY and alerts!
    alerts = await poller.evaluate_courses("SP27", "CS", make_sample_courses(lec_status="O", dis202_status="O"))
    assert len(alerts) == 1
    assert alerts[0].section.class_nbr == 6584


@pytest.mark.asyncio
async def test_any_section_watch_with_component_filter(app_client) -> None:
    app, client = app_client
    poller = app.state.poller

    await client.post("/api/auth/bootstrap", json={"username": "tyler", "password": "password123"})
    res = await client.post(
        "/api/watches",
        json={
            "roster": "SP27",
            "subject": "CS",
            "catalog_nbr": "2110",
            "mode": "any_section",
            "component_filter": "DIS",
            "trigger_on": "open",
        },
    )
    assert res.status_code == 201

    # LEC opens -> filtered out because component_filter='DIS'
    alerts = await poller.evaluate_courses("SP27", "CS", make_sample_courses(lec_status="O", dis202_status="C"))
    assert alerts == []

    # DIS 203 opens -> alerts with #6585!
    alerts = await poller.evaluate_courses("SP27", "CS", make_sample_courses(lec_status="O", dis203_status="O"))
    assert len(alerts) == 1
    assert alerts[0].section.class_nbr == 6585


@pytest.mark.asyncio
async def test_priority_deficit_round_robin_and_rate_limit_backoff(app_client) -> None:
    app, _ = app_client
    poller = app.state.poller
    provider = app.state.provider

    b_cs = _BucketMeta(roster="SP27", subject="CS", weight=2, watch_count=1)
    b_math = _BucketMeta(roster="SP27", subject="MATH", weight=1, watch_count=1)
    picks = [poller._select_next_bucket([b_cs, b_math]).subject for _ in range(6)]
    assert picks.count("CS") == 4
    assert picks.count("MATH") == 2

    provider.raise_rate_limit = True
    res = await poller.poll_bucket("SP27", "CS")
    assert res["ok"] is False
    assert poller.telemetry["rate_limit_hits"] == 1
    assert poller.telemetry["state"] == "backoff"
