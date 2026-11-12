"""Notification preferences, Web Push VAPID subscriptions, and test alert endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.schemas import (
    NotificationPreferencesRequest,
    PushSubscribeRequest,
    PushUnsubscribeRequest,
    TestNotifyRequest,
)
from app.auth import get_current_user, get_db
from app.config import Settings, get_settings
from app.db import Database
from app.services.dispatcher import AlertDispatcher

router = APIRouter(prefix="/api", tags=["notifications"])


def get_dispatcher(request: Request) -> AlertDispatcher:
    return request.app.state.dispatcher


@router.get("/push/vapid-key")
async def get_vapid_public_key(
    _: dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    return {"public_key": settings.vapid_public_key}


@router.post("/push/subscribe", status_code=status.HTTP_201_CREATED)
async def subscribe_push(
    body: PushSubscribeRequest,
    user: dict[str, Any] = Depends(get_current_user),
    db: Database = Depends(get_db),
) -> dict[str, Any]:
    await db.execute(
        """
        INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth, device_label)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(endpoint) DO UPDATE SET
            user_id = excluded.user_id,
            p256dh = excluded.p256dh,
            auth = excluded.auth,
            device_label = excluded.device_label
        """,
        (user["id"], body.endpoint, body.keys.p256dh, body.keys.auth, body.device_label.strip()),
    )
    row = await db.fetch_one(
        "SELECT id, endpoint, device_label, created_at FROM push_subscriptions WHERE endpoint = ?",
        (body.endpoint,),
    )
    return {"subscription": row}


@router.delete("/push/subscribe")
async def unsubscribe_push(
    body: PushUnsubscribeRequest,
    user: dict[str, Any] = Depends(get_current_user),
    db: Database = Depends(get_db),
) -> dict[str, str]:
    if body.id is not None:
        await db.execute("DELETE FROM push_subscriptions WHERE id = ? AND user_id = ?", (body.id, user["id"]))
    elif body.endpoint:
        await db.execute("DELETE FROM push_subscriptions WHERE endpoint = ? AND user_id = ?", (body.endpoint, user["id"]))
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provide id or endpoint")
    return {"status": "unsubscribed"}


@router.get("/notify/preferences")
async def get_notify_preferences(
    user: dict[str, Any] = Depends(get_current_user),
    db: Database = Depends(get_db),
    settings: Settings = Depends(get_settings),
    dispatcher: AlertDispatcher = Depends(get_dispatcher),
) -> dict[str, Any]:
    subs = await db.fetch_all(
        "SELECT id, endpoint, device_label, created_at FROM push_subscriptions WHERE user_id = ? ORDER BY created_at DESC",
        (user["id"],),
    )
    logs = await db.fetch_all(
        """
        SELECT d.id, d.channel_kind, d.status, d.latency_ms, d.error_text, d.sent_at,
               e.roster, e.subject, e.catalog_nbr, e.class_nbr, e.section_label, e.new_status
        FROM delivery_logs d
        LEFT JOIN status_events e ON e.id = d.event_id
        WHERE d.user_id = ?
        ORDER BY d.sent_at DESC, d.id DESC
        LIMIT 20
        """,
        (user["id"],),
    )
    shared_webhook = await dispatcher.get_shared_discord_webhook_url()
    return {
        "discord_user_id": user.get("discord_user_id") or "",
        "discord_ping_enabled": bool(user.get("discord_ping_enabled", 1)),
        "web_push_enabled": bool(user.get("web_push_enabled", 1)),
        "personal_webhook_url": user.get("personal_webhook_url") or "",
        "allow_custom_personal_webhooks": settings.allow_custom_personal_webhooks,
        "shared_discord_configured": bool(shared_webhook),
        "push_subscriptions": subs,
        "recent_deliveries": logs,
    }


@router.put("/notify/preferences")
async def update_notify_preferences(
    body: NotificationPreferencesRequest,
    user: dict[str, Any] = Depends(get_current_user),
    db: Database = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    updates: list[str] = []
    params: list[Any] = []

    if body.discord_user_id is not None:
        updates.append("discord_user_id = ?")
        params.append(body.discord_user_id or None)
    if body.discord_ping_enabled is not None:
        updates.append("discord_ping_enabled = ?")
        params.append(1 if body.discord_ping_enabled else 0)
    if body.web_push_enabled is not None:
        updates.append("web_push_enabled = ?")
        params.append(1 if body.web_push_enabled else 0)
    if body.personal_webhook_url is not None:
        if body.personal_webhook_url and not settings.allow_custom_personal_webhooks:
            raise HTTPException(status_code=403, detail="Personal webhooks are disabled by admin")
        updates.append("personal_webhook_url = ?")
        params.append(body.personal_webhook_url or None)

    if updates:
        params.append(user["id"])
        await db.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", params)

    return {"status": "updated"}


@router.post("/notify/test")
async def send_test_notification(
    body: TestNotifyRequest,
    user: dict[str, Any] = Depends(get_current_user),
    dispatcher: AlertDispatcher = Depends(get_dispatcher),
) -> dict[str, Any]:
    results = await dispatcher.send_test_alerts(user=user, target=body.target)
    return {"results": results}
