"""Admin management, telemetry metrics, health check, and SSE live stream routes."""

from __future__ import annotations

import asyncio
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.api.schemas import CreateInviteRequest, UpdateAdminSettingsRequest
from app.auth import get_admin_user, get_current_user, get_db
from app.config import Settings, get_settings
from app.db import Database
from app.services.catalog import CatalogSyncService
from app.services.dispatcher import AlertDispatcher
from app.services.drop_odds import fetch_drop_leaderboard
from app.services.poller import PollerEngine
from app.services.sse import SSEHub

router = APIRouter(prefix="/api", tags=["admin-telemetry"])


def get_poller(request: Request) -> PollerEngine:
    return request.app.state.poller


def get_catalog(request: Request) -> CatalogSyncService:
    return request.app.state.catalog


def get_sse(request: Request) -> SSEHub:
    return request.app.state.sse_hub


def get_dispatcher(request: Request) -> AlertDispatcher:
    return request.app.state.dispatcher


@router.get("/health")
async def health(poller: PollerEngine = Depends(get_poller)) -> dict[str, Any]:
    return {
        "status": "ok",
        "poller_state": poller.telemetry["state"],
        "total_polls": poller.telemetry["total_polls"],
    }


@router.get("/metrics")
async def get_metrics(
    user: dict[str, Any] = Depends(get_current_user),
    db: Database = Depends(get_db),
    poller: PollerEngine = Depends(get_poller),
    catalog: CatalogSyncService = Depends(get_catalog),
) -> dict[str, Any]:
    events = await db.fetch_all(
        """
        SELECT id, roster, subject, catalog_nbr, class_nbr, section_label,
               old_status, new_status, poll_rtt_ms, detected_at
        FROM status_events
        ORDER BY id DESC
        LIMIT 25
        """
    )
    leaderboard = await fetch_drop_leaderboard(db, limit=12)
    return {
        "poller": poller.get_metrics_snapshot(),
        "catalog": catalog.status,
        "recent_events": events,
        "drop_leaderboard": leaderboard,
    }


@router.get("/events/stream")
async def stream_events(
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
    sse_hub: SSEHub = Depends(get_sse),
    poller: PollerEngine = Depends(get_poller),
) -> StreamingResponse:
    async def event_generator() -> AsyncIterator[str]:
        initial = json.dumps(poller.get_metrics_snapshot())
        yield f"event: telemetry\ndata: {initial}\n\n"

        async with sse_hub.subscribe(user_id=user["id"], is_admin=(user["role"] == "admin")) as queue:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=20.0)
                    yield f"event: {msg['event']}\ndata: {json.dumps(msg['data'])}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/admin/invites")
async def list_invites(
    _: dict[str, Any] = Depends(get_admin_user),
    db: Database = Depends(get_db),
) -> dict[str, Any]:
    rows = await db.fetch_all(
        """
        SELECT i.code, i.max_uses, i.uses_count, i.note, i.expires_at, i.created_at,
               u.username AS created_by_username
        FROM invites i
        JOIN users u ON u.id = i.created_by
        ORDER BY i.created_at DESC
        """
    )
    return {"invites": rows}


@router.post("/admin/invites", status_code=status.HTTP_201_CREATED)
async def create_invite(
    body: CreateInviteRequest,
    admin: dict[str, Any] = Depends(get_admin_user),
    db: Database = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    code = secrets.token_urlsafe(8)
    expires_at = None
    if body.expires_hours is not None:
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=body.expires_hours)).isoformat()

    await db.execute(
        """
        INSERT INTO invites (code, created_by, max_uses, uses_count, note, expires_at)
        VALUES (?, ?, ?, 0, ?, ?)
        """,
        (code, admin["id"], body.max_uses, body.note.strip(), expires_at),
    )
    row = await db.fetch_one("SELECT * FROM invites WHERE code = ?", (code,))
    return {
        "invite": row,
        "invite_url": f"{settings.app_origin}/?invite={code}",
    }


@router.delete("/admin/invites/{code}")
async def delete_invite(
    code: str,
    _: dict[str, Any] = Depends(get_admin_user),
    db: Database = Depends(get_db),
) -> dict[str, str]:
    await db.execute("DELETE FROM invites WHERE code = ?", (code,))
    return {"status": "deleted"}


@router.get("/admin/users")
async def list_users(
    _: dict[str, Any] = Depends(get_admin_user),
    db: Database = Depends(get_db),
) -> dict[str, Any]:
    rows = await db.fetch_all(
        """
        SELECT u.id, u.username, u.role, u.priority_tier, u.discord_user_id, u.created_at,
               (SELECT COUNT(*) FROM watches w WHERE w.user_id = u.id AND w.active = 1) AS active_watches,
               (SELECT COUNT(*) FROM push_subscriptions p WHERE p.user_id = u.id) AS push_devices
        FROM users u
        ORDER BY u.id ASC
        """
    )
    return {"users": rows}


@router.delete("/admin/users/{user_id}")
async def delete_user(
    user_id: int,
    admin: dict[str, Any] = Depends(get_admin_user),
    db: Database = Depends(get_db),
    poller: PollerEngine = Depends(get_poller),
) -> dict[str, str]:
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="Cannot delete your own admin account")
    await db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    poller.wake()
    return {"status": "deleted"}


@router.get("/admin/settings")
async def get_admin_settings(
    _: dict[str, Any] = Depends(get_admin_user),
    db: Database = Depends(get_db),
    settings: Settings = Depends(get_settings),
    dispatcher: AlertDispatcher = Depends(get_dispatcher),
) -> dict[str, Any]:
    shared_url = await dispatcher.get_shared_discord_webhook_url()
    poll_rps_raw = await db.get_setting("poll_max_rps", "")
    poll_rps = float(poll_rps_raw) if poll_rps_raw else settings.poll_max_rps
    return {
        "app_domain": settings.app_domain,
        "app_origin": settings.app_origin,
        "discord_shared_webhook_url": shared_url,
        "poll_max_rps": poll_rps,
        "max_subjects_per_invited_user": settings.max_subjects_per_invited_user,
    }


@router.put("/admin/settings")
async def update_admin_settings(
    body: UpdateAdminSettingsRequest,
    _: dict[str, Any] = Depends(get_admin_user),
    db: Database = Depends(get_db),
) -> dict[str, str]:
    if body.discord_shared_webhook_url is not None:
        await db.set_setting("discord_shared_webhook_url", body.discord_shared_webhook_url)
    if body.poll_max_rps is not None:
        await db.set_setting("poll_max_rps", str(body.poll_max_rps))
    return {"status": "updated"}
