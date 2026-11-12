"""Authentication, first-run admin bootstrap, and invite registration routes."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.auth import (
    clear_session_cookie,
    get_current_user,
    get_db,
    hash_password_async,
    set_session_cookie,
    verify_password_async,
    verify_session_token,
)
from app.config import Settings, get_settings
from app.db import Database
from app.api.schemas import BootstrapRequest, LoginRequest, RegisterInviteRequest

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _serialize_user(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": user["id"],
        "username": user["username"],
        "role": user["role"],
        "priority_tier": user["priority_tier"],
        "discord_user_id": user.get("discord_user_id") or "",
        "discord_ping_enabled": bool(user.get("discord_ping_enabled", 1)),
        "web_push_enabled": bool(user.get("web_push_enabled", 1)),
        "has_personal_webhook": bool((user.get("personal_webhook_url") or "").strip()),
    }


@router.get("/status")
async def auth_status(
    request: Request,
    db: Database = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    count_row = await db.fetch_one("SELECT COUNT(*) AS cnt FROM users")
    needs_bootstrap = (count_row["cnt"] if count_row else 0) == 0

    user_data = None
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        uid = verify_session_token(token, settings)
        if uid is not None:
            row = await db.fetch_one(
                """
                SELECT id, username, role, priority_tier, discord_user_id,
                       discord_ping_enabled, personal_webhook_url, web_push_enabled
                FROM users
                WHERE id = ?
                """,
                (uid,),
            )
            if row is not None:
                user_data = _serialize_user(row)

    return {
        "needs_bootstrap": needs_bootstrap,
        "user": user_data,
        "app_domain": settings.app_domain,
        "app_origin": settings.app_origin,
    }


@router.post("/bootstrap", status_code=status.HTTP_201_CREATED)
async def bootstrap_admin(
    body: BootstrapRequest,
    response: Response,
    db: Database = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    pw_hash = await hash_password_async(body.password)
    async with db.write_tx() as conn:
        cur = await conn.execute("SELECT COUNT(*) AS cnt FROM users")
        row = await cur.fetchone()
        if row and row["cnt"] > 0:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin account already exists. Please sign in.",
            )
        cur = await conn.execute(
            """
            INSERT INTO users (username, password_hash, role, priority_tier)
            VALUES (?, ?, 'admin', 2)
            """,
            (body.username.strip(), pw_hash),
        )
        user_id = int(cur.lastrowid)

    set_session_cookie(response, user_id, settings)
    return {
        "user": {
            "id": user_id,
            "username": body.username.strip(),
            "role": "admin",
            "priority_tier": 2,
            "discord_user_id": "",
            "discord_ping_enabled": True,
            "web_push_enabled": True,
            "has_personal_webhook": False,
        }
    }


@router.post("/login")
async def login(
    body: LoginRequest,
    response: Response,
    db: Database = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    user = await db.fetch_one(
        """
        SELECT id, username, password_hash, role, priority_tier, discord_user_id,
               discord_ping_enabled, personal_webhook_url, web_push_enabled
        FROM users
        WHERE username = ?
        """,
        (body.username.strip(),),
    )
    if user is None or not await verify_password_async(user["password_hash"], body.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    set_session_cookie(response, user["id"], settings)
    return {"user": _serialize_user(user)}


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_with_invite(
    body: RegisterInviteRequest,
    response: Response,
    db: Database = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    pw_hash = await hash_password_async(body.password)
    code = body.invite_code.strip()
    username = body.username.strip()

    async with db.write_tx() as conn:
        cur = await conn.execute("SELECT * FROM invites WHERE code = ?", (code,))
        invite = await cur.fetchone()
        if invite is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid invite code")

        if invite["uses_count"] >= invite["max_uses"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invite code has already been used")

        if invite["expires_at"]:
            exp_dt = datetime.fromisoformat(invite["expires_at"])
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > exp_dt:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invite code has expired")

        existing = await conn.execute("SELECT id FROM users WHERE username = ?", (username,))
        if await existing.fetchone() is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username is already taken")

        user_cur = await conn.execute(
            """
            INSERT INTO users (username, password_hash, role, priority_tier)
            VALUES (?, ?, 'user', 1)
            """,
            (username, pw_hash),
        )
        user_id = int(user_cur.lastrowid)

        await conn.execute(
            "UPDATE invites SET uses_count = uses_count + 1 WHERE code = ?",
            (code,),
        )

    set_session_cookie(response, user_id, settings)
    return {
        "user": {
            "id": user_id,
            "username": username,
            "role": "user",
            "priority_tier": 1,
            "discord_user_id": "",
            "discord_ping_enabled": True,
            "web_push_enabled": True,
            "has_personal_webhook": False,
        }
    }


@router.post("/logout")
async def logout(
    response: Response,
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    clear_session_cookie(response, settings)
    return {"status": "ok"}


@router.get("/me")
async def me(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    return {"user": _serialize_user(user)}
