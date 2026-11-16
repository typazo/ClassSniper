"""Shared, dependency-free normalization, parsing, and utility helpers."""

from __future__ import annotations

import base64
import json
import re
from datetime import datetime, timezone
from typing import Any, Iterator, Optional, TypeVar

import orjson

T = TypeVar("T")

_STRICT_CODE_RE = re.compile(r"^([A-Za-z]{2,8})[\s\-_]*([1-9]\d{3}[A-Za-z]?)$")
_LOOSE_CODE_RE = re.compile(r"^([A-Za-z]+)\s*[- ]?\s*(\d+[A-Za-z]?)$")
_CATALOG_DIGITS_RE = re.compile(r"(\d+)")


def b64url_nopad(raw: bytes) -> str:
    """Encode bytes as unpadded URL-safe base64 ASCII string."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def to_float(val: Any) -> Optional[float]:
    """Coerce numeric inputs safely to float, returning None when blank or invalid."""
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def parse_json_value(raw: Any, default: T) -> Any:
    """Decode JSON strings/bytes safely, returning native objects or default on failure."""
    if raw is None or raw == "":
        return default
    if isinstance(raw, (list, dict)):
        return raw
    if isinstance(raw, (bytes, bytearray)):
        try:
            return orjson.loads(raw)
        except Exception:
            return default
    if isinstance(raw, str):
        try:
            return orjson.loads(raw)
        except Exception:
            try:
                return json.loads(raw)
            except Exception:
                return default
    return default


def decode_json_list(raw: Any) -> list[Any]:
    """Decode a JSON value expected to be a list cleanly."""
    parsed = parse_json_value(raw, [])
    return parsed if isinstance(parsed, list) else []


def decode_json_dict(raw: Any) -> dict[str, Any]:
    """Decode a JSON value expected to be a dict cleanly."""
    parsed = parse_json_value(raw, {})
    return parsed if isinstance(parsed, dict) else {}


def parse_utc_dt(ts: Any) -> Optional[datetime]:
    """Parse SQLite datetime or ISO-8601 string into an aware UTC datetime."""
    if not ts:
        return None
    raw = str(ts).strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def parse_catalog_num(catalog_nbr: str, fallback: Any = None) -> int:
    """Extract leading integer course number (e.g., '2110A' -> 2110)."""
    if isinstance(fallback, (int, float)) and int(fallback) > 0:
        return int(fallback)
    match = _CATALOG_DIGITS_RE.search(str(catalog_nbr or "").strip())
    return int(match.group(1)) if match else 0


def normalize_course_code_strict(raw: str) -> Optional[str]:
    """Normalize standard 4-digit Cornell course codes ('CS2110' -> 'CS 2110'), else None."""
    cleaned = " ".join(str(raw or "").strip().upper().split())
    if not cleaned:
        return None
    match = _STRICT_CODE_RE.match(cleaned)
    if not match:
        return None
    return f"{match.group(1)} {match.group(2)}"


def normalize_course_code_loose(raw: str) -> str:
    """Normalize arbitrary Cornell course codes ('pam-2300' -> 'PAM 2300') permissively."""
    text = str(raw or "").strip().upper()
    if not text:
        return ""
    match = _LOOSE_CODE_RE.match(text)
    if match:
        return f"{match.group(1)} {match.group(2)}"
    parts = text.split()
    if len(parts) >= 2:
        return f"{parts[0]} {parts[1]}"
    return text


def extract_crosslist_codes(raw_crosslists: Any) -> list[str]:
    """Extract deduplicated 'SUBJ NBR' codes from crosslists JSON dicts or string lists."""
    items = decode_json_list(raw_crosslists)
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        code = ""
        if isinstance(item, str):
            code = normalize_course_code_loose(item)
        elif isinstance(item, dict):
            subj = str(item.get("subject") or "").strip().upper()
            nbr = str(item.get("catalogNbr") or item.get("catalog_nbr") or "").strip().upper()
            if subj and nbr:
                code = f"{subj} {nbr}"
        if code and code not in seen:
            seen.add(code)
            out.append(code)
    return out


def format_credits_range(u_min: Any, u_max: Any, suffix: str = "", sep: str = "-") -> str:
    """Format min/max credits cleanly ('3', '3-4', or with suffix/separator)."""
    lo = to_float(u_min) or 0.0
    hi = to_float(u_max) or 0.0
    if lo <= 0 and hi <= 0:
        return ""
    if hi <= 0 or abs(lo - hi) < 1e-6:
        v = lo if lo > 0 else hi
        base = str(int(v)) if v.is_integer() else f"{v:g}"
    else:
        base = f"{lo:g}{sep}{hi:g}"
    return f"{base}{suffix}" if suffix else base


def chunk_list(items: list[T], size: int) -> Iterator[list[T]]:
    """Yield fixed-size slices of a list to stay safely below SQLite parameter/expression limits."""
    step = max(1, size)
    for idx in range(0, len(items), step):
        yield items[idx : idx + step]
