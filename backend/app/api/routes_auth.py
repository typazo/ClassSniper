"""Authentication, first-run admin bootstrap, and invite registration routes."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.auth import (
    USER_SELECT_COLUMNS,
    clear_session_cookie,
    get_current_user,
    get_db,
    hash_password_async,
    normalize_major_mode,
    serialize_user_row,
    set_session_cookie,
    verify_password_async,
    verify_session_token,
)
from app.config import Settings, get_settings
from app.db import Database
from app.api.schemas import (
    BootstrapRequest,
    LoginRequest,
    RegisterInviteRequest,
    UserPreferencesRequest,
)
from app.services.common import parse_utc_dt
from app.services.minors import encode_minor_prefs, normalize_minor_prefs

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _serialize_user(user: dict[str, Any]) -> dict[str, Any]:
    return serialize_user_row(user)


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
                f"""
                SELECT {USER_SELECT_COLUMNS}
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
        "user": _serialize_user(
            {
                "id": user_id,
                "username": body.username.strip(),
                "role": "admin",
                "priority_tier": 2,
            }
        )
    }


@router.post("/login")
async def login(
    body: LoginRequest,
    response: Response,
    db: Database = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    user = await db.fetch_one(
        f"""
        SELECT password_hash, {USER_SELECT_COLUMNS}
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
            exp_dt = parse_utc_dt(invite["expires_at"])
            if exp_dt is not None and datetime.now(timezone.utc) > exp_dt:
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
        "user": _serialize_user(
            {
                "id": user_id,
                "username": username,
                "role": "user",
                "priority_tier": 1,
            }
        )
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


@router.put("/preferences")
async def update_user_preferences(
    body: UserPreferencesRequest,
    user: dict[str, Any] = Depends(get_current_user),
    db: Database = Depends(get_db),
) -> dict[str, Any]:
    if body.major_mode is not None:
        next_mode, next_show_cs = normalize_major_mode(body.major_mode)
    elif body.show_cs_features is not None:
        next_mode, next_show_cs = normalize_major_mode(None, body.show_cs_features)
    else:
        next_mode, next_show_cs = normalize_major_mode(
            user.get("major_mode"),
            user.get("show_cs_features"),
        )
    next_minor_prefs = (
        normalize_minor_prefs(body.minor_prefs)
        if body.minor_prefs is not None
        else normalize_minor_prefs(user.get("minor_prefs") or user.get("minor_prefs_json"))
    )
    async with db.write_tx() as conn:
        await conn.execute(
            "UPDATE users SET major_mode = ?, show_cs_features = ?, minor_prefs_json = ? WHERE id = ?",
            (next_mode, 1 if next_show_cs else 0, encode_minor_prefs(next_minor_prefs), user["id"]),
        )
    return {
        "user": _serialize_user(
            {
                **user,
                "major_mode": next_mode,
                "show_cs_features": next_show_cs,
                "minor_prefs": next_minor_prefs,
            }
        )
    }
