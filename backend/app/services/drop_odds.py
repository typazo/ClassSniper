"""Drop Odds & Seat Turnover Analytics.

Derives empirical seat-drop likelihood and open-window statistics from
observed ``status_events`` transitions and subject tracking duration.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from statistics import median
from typing import Any

from app.db import Database

_TIER_LABELS: dict[str, str] = {
    "high": "High",
    "moderate": "Moderate",
    "low": "Low",
    "none": "0 Drops",
    "untracked": "Tracking",
}


def parse_event_dt(ts: str | None) -> datetime | None:
    """Parse SQLite or ISO-8601 UTC timestamp strings into aware datetimes."""
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
        return dt
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _format_duration_short(seconds: float | None) -> str:
    if seconds is None:
        return ""
    s = max(0, int(round(seconds)))
    if s < 60:
        return f"{s}s"
    if s < 3600:
        m, rem = divmod(s, 60)
        return f"{m}m {rem}s" if rem else f"{m}m"
    h, rem = divmod(s, 3600)
    m = rem // 60
    return f"{h}h {m}m" if m else f"{h}h"


def compute_window_stats(
    events: list[dict[str, Any]],
    cutoff: datetime | None = None,
) -> dict[str, Any]:
    """Compute flip counts and open-window duration stats for an event slice."""
    parsed: list[tuple[datetime, dict[str, Any]]] = []
    for ev in events:
        dt = parse_event_dt(ev.get("detected_at"))
        if dt is None:
            continue
        parsed.append((dt, ev))

    parsed.sort(key=lambda item: (item[0], int(item[1].get("id") or 0)))

    # Track completed O -> (C|W) durations across full history, attributing each
    # closed episode to its close timestamp (or open timestamp) within cutoff.
    open_started_at: dict[int, datetime] = {}
    durations_sec: list[float] = []

    total_flips = 0
    opened_count = 0
    closed_count = 0
    waitlisted_count = 0
    last_opened_at: str | None = None
    last_flip_at: str | None = None

    for dt, ev in parsed:
        class_nbr = int(ev.get("class_nbr") or 0)
        new_s = str(ev.get("new_status") or "").upper()
        in_window = cutoff is None or dt >= cutoff

        if new_s == "O":
            if class_nbr not in open_started_at:
                open_started_at[class_nbr] = dt
        elif new_s in ("C", "W"):
            started = open_started_at.pop(class_nbr, None)
            if started is not None and in_window:
                elapsed = max(0.0, (dt - started).total_seconds())
                durations_sec.append(elapsed)

        if not in_window:
            continue

        total_flips += 1
        iso_ts = dt.isoformat()
        last_flip_at = iso_ts
        if new_s == "O":
            opened_count += 1
            last_opened_at = iso_ts
        elif new_s == "C":
            closed_count += 1
        elif new_s == "W":
            waitlisted_count += 1

    avg_open_sec = round(sum(durations_sec) / len(durations_sec), 1) if durations_sec else None
    median_open_sec = round(float(median(durations_sec)), 1) if durations_sec else None

    return {
        "total_flips": total_flips,
        "opened_count": opened_count,
        "closed_count": closed_count,
        "waitlisted_count": waitlisted_count,
        "avg_open_sec": avg_open_sec,
        "median_open_sec": median_open_sec,
        "last_opened_at": last_opened_at,
        "last_flip_at": last_flip_at,
    }


def compute_tracking_days(
    first_synced_at: str | None,
    events: list[dict[str, Any]],
    fallback_since: str | None = None,
    now: datetime | None = None,
) -> float:
    """Compute how many days this course/subject has been observed."""
    now_dt = now or datetime.now(timezone.utc)
    candidates: list[datetime] = []

    for ts in (first_synced_at, fallback_since):
        dt = parse_event_dt(ts)
        if dt is not None:
            candidates.append(dt)

    for ev in events:
        dt = parse_event_dt(ev.get("detected_at"))
        if dt is not None:
            candidates.append(dt)

    if not candidates:
        return 0.0
    earliest = min(candidates)
    return round(max(0.0, (now_dt - earliest).total_seconds() / 86400.0), 1)


def _classify_drop_tier(
    opened_24h: int,
    opened_7d: int,
    opened_30d: int,
    opened_all: int,
    waitlisted_7d: int,
    flips_all: int,
    tracking_days: float,
) -> str:
    if opened_24h >= 3 or opened_7d >= 7:
        return "high"
    if opened_7d >= 2 or opened_24h >= 1 or opened_30d >= 4:
        return "moderate"
    if opened_all >= 1 or waitlisted_7d >= 1:
        return "low"
    if flips_all > 0 or tracking_days >= 1.0:
        return "none"
    return "untracked"


def compute_drop_odds(
    events: list[dict[str, Any]],
    tracking_days: float = 0.0,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Compute Drop Odds tier, counts, durations, and summary from real events."""
    now_dt = now or datetime.now(timezone.utc)
    s24 = compute_window_stats(events, now_dt - timedelta(hours=24))
    s7 = compute_window_stats(events, now_dt - timedelta(days=7))
    s30 = compute_window_stats(events, now_dt - timedelta(days=30))
    s_all = compute_window_stats(events, None)

    opened_24h = int(s24["opened_count"])
    opened_7d = int(s7["opened_count"])
    opened_30d = int(s30["opened_count"])
    opened_all = int(s_all["opened_count"])
    waitlisted_7d = int(s7["waitlisted_count"])
    flips_7d = int(s7["total_flips"])
    flips_all = int(s_all["total_flips"])
    td = round(max(0.0, float(tracking_days)), 1)

    tier = _classify_drop_tier(
        opened_24h=opened_24h,
        opened_7d=opened_7d,
        opened_30d=opened_30d,
        opened_all=opened_all,
        waitlisted_7d=waitlisted_7d,
        flips_all=flips_all,
        tracking_days=td,
    )
    label = _TIER_LABELS[tier]

    med_sec = s7["median_open_sec"] if s7["median_open_sec"] is not None else s_all["median_open_sec"]
    avg_sec = s7["avg_open_sec"] if s7["avg_open_sec"] is not None else s_all["avg_open_sec"]

    if opened_7d > 0:
        dur_note = f" (median {_format_duration_short(med_sec)})" if med_sec is not None else ""
        summary = f"{opened_7d} open{'s' if opened_7d != 1 else ''} in 7d{dur_note}"
    elif opened_all > 0:
        summary = f"{opened_all} historical open{'s' if opened_all != 1 else ''} logged"
    elif waitlisted_7d > 0:
        summary = f"{waitlisted_7d} waitlist shift{'s' if waitlisted_7d != 1 else ''} in 7d"
    elif tier == "none":
        summary = f"0 opens over {td:.1f}d tracked"
    else:
        summary = "Tracking started (<24h)"

    return {
        "tier": tier,
        "label": label,
        "opened_24h": opened_24h,
        "opened_7d": opened_7d,
        "opened_30d": opened_30d,
        "opened_all": opened_all,
        "waitlisted_7d": waitlisted_7d,
        "flips_7d": flips_7d,
        "flips_all": flips_all,
        "avg_open_sec_7d": avg_sec,
        "median_open_sec_7d": med_sec,
        "last_opened_at": s_all["last_opened_at"],
        "tracking_days": td,
        "summary": summary,
    }


async def fetch_course_drop_odds_map(
    db: Database,
    roster: str,
    course_keys: list[tuple[str, str]],
) -> dict[tuple[str, str], dict[str, Any]]:
    """Batch-compute Drop Odds for a list of (subject, catalog_nbr) keys in a roster."""
    if not course_keys:
        return {}

    roster_u = roster.upper()
    unique_keys = sorted({(str(s).upper(), str(c)) for s, c in course_keys})
    subjects = sorted({s for s, _ in unique_keys})

    subj_placeholders = ",".join("?" for _ in subjects)
    subj_rows = await db.fetch_all(
        f"SELECT value, first_synced_at, synced_at FROM subjects WHERE roster = ? AND value IN ({subj_placeholders})",
        (roster_u, *subjects),
    )
    first_synced_by_subj: dict[str, str | None] = {
        str(r["value"]).upper(): r.get("first_synced_at") or r.get("synced_at")
        for r in subj_rows
    }

    events_by_key: dict[tuple[str, str], list[dict[str, Any]]] = {k: [] for k in unique_keys}
    # Chunk queries to stay comfortably below SQLite parameter limits.
    chunk_size = 200
    for i in range(0, len(unique_keys), chunk_size):
        chunk = unique_keys[i : i + chunk_size]
        pair_clauses = " OR ".join("(subject = ? AND catalog_nbr = ?)" for _ in chunk)
        params: list[Any] = [roster_u]
        for s, c in chunk:
            params.extend([s, c])
        rows = await db.fetch_all(
            f"""
            SELECT id, roster, subject, catalog_nbr, class_nbr, section_label,
                   old_status, new_status, detected_at
            FROM status_events
            WHERE roster = ? AND ({pair_clauses})
            ORDER BY id ASC
            """,
            tuple(params),
        )
        for row in rows:
            k = (str(row["subject"]).upper(), str(row["catalog_nbr"]))
            if k in events_by_key:
                events_by_key[k].append(row)

    now_dt = datetime.now(timezone.utc)
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for s, c in unique_keys:
        evs = events_by_key.get((s, c), [])
        td = compute_tracking_days(first_synced_by_subj.get(s), evs, now=now_dt)
        result[(s, c)] = compute_drop_odds(evs, tracking_days=td, now=now_dt)
    return result


async def fetch_drop_leaderboard(
    db: Database,
    roster: str | None = None,
    limit: int = 12,
) -> list[dict[str, Any]]:
    """Return courses ranked by 7-day seat turnover and drop frequency."""
    now_dt = datetime.now(timezone.utc)
    cutoff_30d = (now_dt - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    where = ["detected_at >= ?"]
    params: list[Any] = [cutoff_30d]
    if roster:
        where.append("roster = ?")
        params.append(roster.upper())

    event_rows = await db.fetch_all(
        f"""
        SELECT id, roster, subject, catalog_nbr, class_nbr, section_label,
               old_status, new_status, detected_at
        FROM status_events
        WHERE {' AND '.join(where)}
        ORDER BY id ASC
        """,
        tuple(params),
    )
    if not event_rows:
        return []

    by_course: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in event_rows:
        k = (str(row["roster"]).upper(), str(row["subject"]).upper(), str(row["catalog_nbr"]))
        by_course.setdefault(k, []).append(row)

    subj_rows = await db.fetch_all("SELECT roster, value, first_synced_at, synced_at FROM subjects")
    first_synced: dict[tuple[str, str], str | None] = {
        (str(r["roster"]).upper(), str(r["value"]).upper()): r.get("first_synced_at") or r.get("synced_at")
        for r in subj_rows
    }

    course_keys = sorted(by_course.keys())
    course_ph = " OR ".join("(roster = ? AND subject = ? AND catalog_nbr = ?)" for _ in course_keys)
    course_params: list[Any] = []
    for r_u, s_u, cat in course_keys:
        course_params.extend([r_u, s_u, cat])
    course_rows = await db.fetch_all(
        f"SELECT roster, subject, catalog_nbr, title_short FROM courses_meta WHERE {course_ph}",
        tuple(course_params),
    )
    titles: dict[tuple[str, str, str], str] = {
        (str(r["roster"]).upper(), str(r["subject"]).upper(), str(r["catalog_nbr"])): str(r.get("title_short") or "")
        for r in course_rows
    }

    entries: list[dict[str, Any]] = []
    for (r_u, s_u, cat), evs in by_course.items():
        td = compute_tracking_days(first_synced.get((r_u, s_u)), evs, now=now_dt)
        odds = compute_drop_odds(evs, tracking_days=td, now=now_dt)
        if odds["flips_7d"] == 0 and odds["opened_all"] == 0:
            continue
        entries.append(
            {
                "roster": r_u,
                "subject": s_u,
                "catalog_nbr": cat,
                "title": titles.get((r_u, s_u, cat), ""),
                **odds,
            }
        )

    entries.sort(
        key=lambda e: (
            e["opened_7d"],
            e["opened_24h"],
            e["flips_7d"],
            e["opened_all"],
            e["last_opened_at"] or "",
        ),
        reverse=True,
    )
    return entries[: max(1, limit)]
