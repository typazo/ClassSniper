"""Tests for Discord coalesced @mentions, Web Push dispatch, and 410 pruning."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from app.services.dispatcher import MatchedAlert
from app.services.notifiers import DeliveryOutcome, DiscordWebhookNotifier
from tests.conftest import make_sample_courses


def test_discord_payload_mentions_only_valid_ids_in_content() -> None:
    payload = DiscordWebhookNotifier.build_seat_payload(
        roster="SP27",
        subject="CS",
        catalog_nbr="2110",
        course_title="OO Programming",
        section_label="LEC 001",
        class_nbr=6582,
        old_status="C",
        new_status="O",
        meetings_summary="TR 10:10AM-11:25AM",
        instructors_summary="Erasmo Tani",
        mention_user_ids=["11111111111111111", "not-a-snowflake", "@everyone", "22222222222222222", "11111111111111111"],
        poll_rtt_ms=14,
        app_origin="https://sniper.hodgman.net",
    )

    assert "<@11111111111111111>" in payload["content"]
    assert "<@22222222222222222>" in payload["content"]
    assert "@everyone" not in payload["content"]
    assert payload["allowed_mentions"] == {
        "parse": [],
        "users": ["11111111111111111", "22222222222222222"],
    }
    assert payload["embeds"][0]["fields"][0]["value"] == "`6582`"


@respx.mock
@pytest.mark.asyncio
async def test_dispatcher_coalesces_shared_discord_and_prunes_dead_push(app_client, monkeypatch) -> None:
    app, client = app_client
    db = app.state.db
    dispatcher = app.state.dispatcher

    # Bootstrap admin & create friend
    await client.post("/api/auth/bootstrap", json={"username": "admin", "password": "password123"})
    await client.put(
        "/api/notify/preferences",
        json={"discord_user_id": "11111111111111111", "discord_ping_enabled": True},
    )
    await client.post(
        "/api/push/subscribe",
        json={
            "endpoint": "https://push.example/expired-device",
            "keys": {"p256dh": "BTestKey1234567890", "auth": "AuthSecret123"},
            "device_label": "Dead iPhone",
        },
    )
    inv_code = (await client.post("/api/admin/invites", json={"max_uses": 1})).json()["invite"]["code"]

    # Register friend in separate client session
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://sniper.hodgman.net") as friend_client:
        await friend_client.post(
            "/api/auth/register",
            json={"invite_code": inv_code, "username": "friend", "password": "password123"},
        )
        await friend_client.put(
            "/api/notify/preferences",
            json={"discord_user_id": "22222222222222222", "discord_ping_enabled": True},
        )

    users = await db.fetch_all("SELECT * FROM users ORDER BY id ASC")
    course = make_sample_courses(lec_status="O")[0]
    sec = course.sections[0]

    # Mock shared Discord webhook & Web Push 410 Gone
    discord_route = respx.post("https://discord.com/api/webhooks/123456/abcdef").mock(
        return_value=httpx.Response(204)
    )

    async def fake_webpush_send(subscription, **kwargs):
        return DeliveryOutcome(
            channel_kind="web_push",
            status="pruned",
            latency_ms=25,
            error_text="Subscription expired (HTTP 410)",
            subscription_id=subscription["id"],
        )

    monkeypatch.setattr(dispatcher.web_push, "send", fake_webpush_send)

    alerts = [
        MatchedAlert(watch={"id": 1}, user=users[0], course=course, section=sec, old_status="C", new_status="O", poll_rtt_ms=15),
        MatchedAlert(watch={"id": 2}, user=users[1], course=course, section=sec, old_status="C", new_status="O", poll_rtt_ms=15),
    ]
    await dispatcher.dispatch_alerts(alerts)

    # Exactly ONE coalesced webhook call pinging BOTH users
    assert discord_route.call_count == 1
    sent_body = json.loads(discord_route.calls[0].request.content)
    assert sent_body["allowed_mentions"]["users"] == ["11111111111111111", "22222222222222222"]
    assert "<@11111111111111111>" in sent_body["content"]
    assert "<@22222222222222222>" in sent_body["content"]

    # Expired push subscription pruned automatically
    subs_left = await db.fetch_all("SELECT * FROM push_subscriptions")
    assert subs_left == []

    # Status event & delivery logs persisted
    events = await db.fetch_all("SELECT * FROM status_events")
    assert len(events) == 1
    assert events[0]["class_nbr"] == 6582
    logs = await db.fetch_all("SELECT * FROM delivery_logs ORDER BY id ASC")
    assert len(logs) == 2
