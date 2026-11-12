"""End-to-end HTTP API tests covering auth, invites, FTS5 search, watches, and admin rules."""

from __future__ import annotations

import httpx
import pytest


@pytest.mark.asyncio
async def test_auth_bootstrap_invites_and_access_control(app_client) -> None:
    app, admin = app_client

    # Unauthenticated request blocked
    assert (await admin.get("/api/watches")).status_code == 401

    st = (await admin.get("/api/auth/status")).json()
    assert st["needs_bootstrap"] is True
    assert st["app_domain"] == "sniper.hodgman.net"

    # Bootstrap admin
    res = await admin.post("/api/auth/bootstrap", json={"username": "tyler", "password": "password123"})
    assert res.status_code == 201
    assert res.json()["user"]["role"] == "admin"

    # Second bootstrap locked out
    res2 = await admin.post("/api/auth/bootstrap", json={"username": "evil", "password": "password123"})
    assert res2.status_code == 403

    # Create single-use invite
    inv_res = await admin.post("/api/admin/invites", json={"max_uses": 1, "note": "friend"})
    assert inv_res.status_code == 201
    code = inv_res.json()["invite"]["code"]
    assert inv_res.json()["invite_url"] == f"https://sniper.hodgman.net/?invite={code}"

    # Friend registers with invite
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://sniper.hodgman.net") as friend:
        reg = await friend.post(
            "/api/auth/register",
            json={"invite_code": code, "username": "alex", "password": "password123"},
        )
        assert reg.status_code == 201
        assert reg.json()["user"]["role"] == "user"

        # Friend cannot access admin routes
        assert (await friend.get("/api/admin/users")).status_code == 403

        # Single-use code cannot be reused
        reuse = await friend.post(
            "/api/auth/register",
            json={"invite_code": code, "username": "bob", "password": "password123"},
        )
        assert reuse.status_code == 400


@pytest.mark.asyncio
async def test_search_watches_isolation_and_subject_limits(app_client) -> None:
    app, admin = app_client

    await admin.post("/api/auth/bootstrap", json={"username": "tyler", "password": "password123"})
    code = (await admin.post("/api/admin/invites", json={"max_uses": 1})).json()["invite"]["code"]

    # Course search by code, classNbr, and noisy punctuation
    s1 = await admin.get("/api/courses/search", params={"roster": "SP27", "q": "CS 2110"})
    assert s1.status_code == 200
    assert s1.json()["courses"][0]["catalog_nbr"] == "2110"

    s2 = await admin.get("/api/courses/search", params={"roster": "SP27", "q": "6584"})
    assert s2.status_code == 200
    assert s2.json()["courses"][0]["subject"] == "CS"

    s3 = await admin.get("/api/courses/search", params={"roster": "SP27", "q": "CS-2110++!!"})
    assert s3.status_code == 200
    assert len(s3.json()["courses"]) == 1

    # Admin creates a watch
    w_res = await admin.post(
        "/api/watches",
        json={"roster": "SP27", "subject": "CS", "catalog_nbr": "2110", "class_nbr": 6582, "mode": "exact"},
    )
    assert w_res.status_code == 201
    admin_watch_id = w_res.json()["watch"]["id"]

    # Duplicate watch rejected
    dup = await admin.post(
        "/api/watches",
        json={"roster": "SP27", "subject": "CS", "catalog_nbr": "2110", "class_nbr": 6582, "mode": "exact"},
    )
    assert dup.status_code == 409

    # Invited friend cannot delete admin's watch
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://sniper.hodgman.net") as friend:
        await friend.post(
            "/api/auth/register",
            json={"invite_code": code, "username": "alex", "password": "password123"},
        )
        del_other = await friend.delete(f"/api/watches/{admin_watch_id}")
        assert del_other.status_code == 403

        # Notification preference validation
        bad_id = await friend.put("/api/notify/preferences", json={"discord_user_id": "@alex"})
        assert bad_id.status_code == 422

        bad_wh = await friend.put("/api/notify/preferences", json={"personal_webhook_url": "http://evil.local/hook"})
        assert bad_wh.status_code == 422

        good_pref = await friend.put(
            "/api/notify/preferences",
            json={"discord_user_id": "123456789012345678", "discord_ping_enabled": True},
        )
        assert good_pref.status_code == 200

    # Metrics & Health endpoints
    health = await admin.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    metrics = await admin.get("/api/metrics")
    assert metrics.status_code == 200
    assert "poller" in metrics.json()
