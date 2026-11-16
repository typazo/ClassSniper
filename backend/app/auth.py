"""Password hashing, signed session cookies, and auth dependencies."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import time
from typing import Any, Optional

from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error
from fastapi import Depends, HTTPException, Request, Response, status

from app.config import Settings, get_settings
from app.db import Database
from app.services.common import b64url_nopad
from app.services.cs_requirements import decode_completed_course_details, decode_completed_courses
from app.services.minors import decode_minor_prefs

_ph = PasswordHasher()

USER_SELECT_COLUMNS = """
    id, username, role, priority_tier, discord_user_id,
    discord_ping_enabled, personal_webhook_url, web_push_enabled,
    completed_courses_json, completed_course_details_json,
    in_progress_courses_json, in_progress_course_details_json,
    include_implied_prereqs, show_cs_features,
    major_mode, minor_prefs_json, created_at
""".strip()


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except (Argon2Error, ValueError, TypeError):
        return False


async def hash_password_async(password: str) -> str:
    return await asyncio.to_thread(hash_password, password)


async def verify_password_async(password_hash: str, password: str) -> bool:
    return await asyncio.to_thread(verify_password, password_hash, password)


def _b64url_decode(raw: str) -> bytes:
    padding = "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode(raw + padding)


def sign_session_token(user_id: int, settings: Settings) -> str:
    payload = {"uid": user_id, "exp": int(time.time()) + settings.session_ttl_seconds}
    encoded = b64url_nopad(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = hmac.new(
        settings.session_secret.encode("utf-8"),
        encoded.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{encoded}.{b64url_nopad(sig)}"


def verify_session_token(token: str, settings: Settings) -> Optional[int]:
    if "." not in token:
        return None
    encoded, sig_b64 = token.split(".", 1)
    expected_sig = hmac.new(
        settings.session_secret.encode("utf-8"),
        encoded.encode("ascii"),
        hashlib.sha256,
    ).digest()
    try:
        actual_sig = _b64url_decode(sig_b64)
    except Exception:
        return None
    if not hmac.compare_digest(expected_sig, actual_sig):
        return None
    try:
        payload = json.loads(_b64url_decode(encoded).decode("utf-8"))
    except Exception:
        return None
    if int(payload.get("exp", 0)) < int(time.time()):
        return None
    uid = payload.get("uid")
    return int(uid) if isinstance(uid, int) else None


def set_session_cookie(response: Response, user_id: int, settings: Settings) -> None:
    token = sign_session_token(user_id, settings)
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(key=settings.session_cookie_name, path="/")


def get_db(request: Request) -> Database:
    return request.app.state.db


VALID_MAJOR_MODES = ("none", "cs", "ilr")


def normalize_major_mode(
    major_mode: Any,
    show_cs_features: Any = True,
) -> tuple[str, bool]:
    """Normalize user major_mode ('none' | 'cs' | 'ilr') and derive show_cs_features."""
    mode = str(major_mode or "").strip().lower()
    if mode not in VALID_MAJOR_MODES:
        show_cs = True if show_cs_features is None else bool(show_cs_features)
        mode = "cs" if show_cs else "none"
    return mode, (mode == "cs")


def decode_user_record(user: dict[str, Any]) -> dict[str, Any]:
    """Hydrate decoded course/preference fields on a DB user row cleanly."""
    completed = (
        list(user["completed_courses"])
        if isinstance(user.get("completed_courses"), list)
        else decode_completed_courses(user.get("completed_courses_json"))
    )
    completed_details = (
        dict(user["completed_course_details"])
        if isinstance(user.get("completed_course_details"), dict)
        else decode_completed_course_details(user.get("completed_course_details_json"))
    )
    in_progress = (
        list(user["in_progress_courses"])
        if isinstance(user.get("in_progress_courses"), list)
        else decode_completed_courses(user.get("in_progress_courses_json"))
    )
    in_progress_details = (
        dict(user["in_progress_course_details"])
        if isinstance(user.get("in_progress_course_details"), dict)
        else decode_completed_course_details(user.get("in_progress_course_details_json"))
    )
    raw_implied = user.get("include_implied_prereqs")
    mode, show_cs = normalize_major_mode(user.get("major_mode"), user.get("show_cs_features"))
    minor_prefs = (
        dict(user["minor_prefs"])
        if isinstance(user.get("minor_prefs"), dict)
        else decode_minor_prefs(user.get("minor_prefs_json"))
    )
    return {
        **user,
        "completed_courses": completed,
        "completed_course_details": completed_details,
        "in_progress_courses": in_progress,
        "in_progress_course_details": in_progress_details,
        "include_implied_prereqs": True if raw_implied is None else bool(raw_implied),
        "major_mode": mode,
        "show_cs_features": show_cs,
        "minor_prefs": minor_prefs,
    }


def serialize_user_row(user: dict[str, Any]) -> dict[str, Any]:
    """Serialize a DB or hydrated user dict into the public API response shape."""
    hydrated = decode_user_record(user)
    return {
        "id": hydrated["id"],
        "username": hydrated["username"],
        "role": hydrated["role"],
        "priority_tier": hydrated["priority_tier"],
        "discord_user_id": hydrated.get("discord_user_id") or "",
        "discord_ping_enabled": bool(hydrated.get("discord_ping_enabled", 1)),
        "web_push_enabled": bool(hydrated.get("web_push_enabled", 1)),
        "has_personal_webhook": bool((hydrated.get("personal_webhook_url") or "").strip()),
        "completed_courses": hydrated["completed_courses"],
        "completed_course_details": hydrated["completed_course_details"],
        "in_progress_courses": hydrated["in_progress_courses"],
        "in_progress_course_details": hydrated["in_progress_course_details"],
        "include_implied_prereqs": hydrated["include_implied_prereqs"],
        "major_mode": hydrated["major_mode"],
        "show_cs_features": hydrated["show_cs_features"],
        "minor_prefs": hydrated["minor_prefs"],
    }


async def get_current_user(
    request: Request,
    db: Database = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    user_id = verify_session_token(token, settings)
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session")
    user = await db.fetch_one(
        f"""
        SELECT {USER_SELECT_COLUMNS}
        FROM users
        WHERE id = ?
        """,
        (user_id,),
    )
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User no longer exists")
    return decode_user_record(user)


async def get_admin_user(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    if user["role"] != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required")
    return user
