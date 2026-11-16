"""Watchlist CRUD, re-arming, turnover enrichment, and manual check-now endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import time
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_catalog, get_poller
from app.api.schemas import BatchWatchGroupRequest, CreateWatchRequest, UpdateWatchRequest
from app.auth import get_current_user, get_db
from app.config import Settings, get_settings
from app.db import Database
from app.providers.base import SectionRecord
from app.providers.cornell import is_ithaca_or_virtual_section
from app.services.catalog import CatalogSyncService
from app.services.common import chunk_list, decode_json_list, parse_utc_dt
from app.services.drop_odds import (
    compute_all_window_stats,
    compute_drop_odds_from_windows,
    compute_tracking_days,
)
from app.services.poller import PollerEngine, _is_linked_group_ready, _target_statuses

router = APIRouter(prefix="/api/watches", tags=["watches"])

_WATCH_LIST_SQL = """
    SELECT *
    FROM watches
    WHERE user_id = ?
    ORDER BY active DESC, priority DESC, created_at DESC
""".strip()


def _normalize_group_key(raw: Optional[str]) -> str:
    return " ".join((raw or "").split())[:48]


def _filter_section_candidates(
    sec_rows: list[dict[str, Any]],
    comp_filter: Optional[str],
    ith_only: bool,
) -> list[dict[str, Any]]:
    comp = (comp_filter or "").strip().upper()
    return [
        s
        for s in sec_rows
        if (not comp or str(s.get("ssr_component") or "").upper() == comp)
        and (
            not ith_only
            or is_ithaca_or_virtual_section(
                campus=str(s.get("campus") or ""),
                location=str(s.get("location") or ""),
                instruction_mode=str(s.get("instruction_mode") or ""),
            )
        )
    ]


def _filter_events_for_watch(
    watch: dict[str, Any],
    events: list[dict[str, Any]],
    section_by_nbr: Optional[dict[tuple[str, int], dict[str, Any]]] = None,
) -> list[dict[str, Any]]:
    mode = str(watch.get("mode") or "")
    target_nbr = watch.get("class_nbr")
    comp_filter = str(watch.get("component_filter") or "").strip().upper()
    ith_only = bool(watch.get("ithaca_or_virtual", 0))
    roster_u = str(watch["roster"])

    target_eg_idx = watch.get("enroll_group_idx")
    if mode == "linked_group" and target_eg_idx is None and target_nbr is not None and section_by_nbr:
        target_sec = section_by_nbr.get((roster_u, int(target_nbr)))
        if target_sec is not None:
            target_eg_idx = target_sec.get("enroll_group_idx")

    out: list[dict[str, Any]] = []
    for ev in events:
        if (
            ev["roster"] != watch["roster"]
            or ev["subject"] != watch["subject"]
            or str(ev["catalog_nbr"]) != str(watch["catalog_nbr"])
        ):
            continue
        ev_nbr = int(ev["class_nbr"])
        if mode == "exact" and target_nbr is not None and ev_nbr != int(target_nbr):
            continue
        if mode == "linked_group" and target_eg_idx is not None and section_by_nbr:
            ev_sec = section_by_nbr.get((roster_u, ev_nbr))
            if ev_sec is not None and int(ev_sec.get("enroll_group_idx") or 0) != int(target_eg_idx):
                continue
        if mode == "any_section":
            if comp_filter:
                lbl = str(ev.get("section_label") or "").strip().upper()
                ev_comp = lbl.split(" ", 1)[0] if lbl else ""
                if ev_comp != comp_filter:
                    continue
            if ith_only and section_by_nbr:
                ev_sec = section_by_nbr.get((roster_u, ev_nbr))
                if ev_sec is not None and not is_ithaca_or_virtual_section(
                    campus=str(ev_sec.get("campus") or ""),
                    location=str(ev_sec.get("location") or ""),
                    instruction_mode=str(ev_sec.get("instruction_mode") or ""),
                ):
                    continue
        out.append(ev)
    return out


async def _fetch_sections_index(
    db: Database,
    course_keys: list[tuple[str, str, str]],
) -> tuple[dict[tuple[str, str, str], list[dict[str, Any]]], dict[tuple[str, int], dict[str, Any]]]:
    sections_by_course: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    section_by_nbr: dict[tuple[str, int], dict[str, Any]] = {}
    for chunk in chunk_list(course_keys, 150):
        clauses = " OR ".join("(roster = ? AND subject = ? AND catalog_nbr = ?)" for _ in chunk)
        params: list[Any] = []
        for r, s, c in chunk:
            params.extend([r, s, c])
        sec_rows = await db.fetch_all(
            f"""
            SELECT roster, subject, catalog_nbr, class_nbr, enroll_group_idx, ssr_component,
                   section, open_status, meetings_summary, instructors_summary,
                   campus, location, location_descr, instruction_mode, updated_at
            FROM roster_sections
            WHERE {clauses}
            ORDER BY enroll_group_idx ASC, class_nbr ASC
            """,
            params,
        )
        for sec in sec_rows:
            ckey = (str(sec["roster"]), str(sec["subject"]), str(sec["catalog_nbr"]))
            sections_by_course.setdefault(ckey, []).append(sec)
            section_by_nbr[(str(sec["roster"]), int(sec["class_nbr"]))] = sec
    return sections_by_course, section_by_nbr


async def _enrich_watches(db: Database, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return []

    course_keys = sorted({(str(w["roster"]), str(w["subject"]), str(w["catalog_nbr"])) for w in rows})
    sections_by_course, section_by_nbr = await _fetch_sections_index(db, course_keys)

    events_by_course: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    first_synced_by_subj: dict[tuple[str, str], Optional[str]] = {}

    subj_keys = sorted({(r, s) for r, s, _ in course_keys})
    for chunk in chunk_list(subj_keys, 200):
        subj_ph = " OR ".join("(roster = ? AND value = ?)" for _ in chunk)
        subj_params: list[Any] = []
        for r, s in chunk:
            subj_params.extend([r, s])
        subj_rows = await db.fetch_all(
            f"SELECT roster, value, first_synced_at, synced_at FROM subjects WHERE {subj_ph}",
            subj_params,
        )
        for sr in subj_rows:
            first_synced_by_subj[(str(sr["roster"]), str(sr["value"]))] = (
                sr.get("first_synced_at") or sr.get("synced_at")
            )

    for chunk in chunk_list(course_keys, 120):
        placeholders = " OR ".join("(roster = ? AND subject = ? AND catalog_nbr = ?)" for _ in chunk)
        params: list[Any] = []
        for r, s, c in chunk:
            params.extend([r, s, c])
        ev_rows = await db.fetch_all(
            f"""
            SELECT id, roster, subject, catalog_nbr, class_nbr, section_label,
                   old_status, new_status, detected_at
            FROM (
                SELECT id, roster, subject, catalog_nbr, class_nbr, section_label,
                       old_status, new_status, detected_at,
                       ROW_NUMBER() OVER (
                           PARTITION BY roster, subject, catalog_nbr
                           ORDER BY detected_at DESC, id DESC
                       ) AS rn
                FROM status_events
                WHERE {placeholders}
            ) ranked
            WHERE rn <= 250
            ORDER BY detected_at DESC, id DESC
            """,
            params,
        )
        for ev in ev_rows:
            k = (str(ev["roster"]), str(ev["subject"]), str(ev["catalog_nbr"]))
            events_by_course.setdefault(k, []).append(ev)

    now_dt = datetime.now(timezone.utc)
    cutoffs: dict[str, Optional[datetime]] = {
        "24h": now_dt - timedelta(hours=24),
        "7d": now_dt - timedelta(days=7),
        "30d": now_dt - timedelta(days=30),
        "all": None,
    }

    enriched: list[dict[str, Any]] = []
    for w in rows:
        item = dict(w)
        item["active"] = bool(item["active"])
        item["auto_pause"] = bool(item["auto_pause"])
        ith_only = bool(item.get("ithaca_or_virtual", 0))
        item["ithaca_or_virtual"] = ith_only
        wanted_statuses = _target_statuses(str(w.get("trigger_on") or "open"))
        ckey = (str(w["roster"]), str(w["subject"]), str(w["catalog_nbr"]))
        course_secs = sections_by_course.get(ckey, [])
        open_sections: list[dict[str, Any]] = []

        if w["class_nbr"] is not None:
            sec = section_by_nbr.get((str(w["roster"]), int(w["class_nbr"])))
            if sec is None:
                sec = await db.fetch_one(
                    """
                    SELECT class_nbr, enroll_group_idx, ssr_component, section, open_status,
                           meetings_summary, instructors_summary, campus, location,
                           location_descr, instruction_mode, updated_at
                    FROM roster_sections
                    WHERE roster = ? AND class_nbr = ?
                    """,
                    (w["roster"], w["class_nbr"]),
                )
            item["section_info"] = sec
            if sec is not None:
                if w.get("mode") == "linked_group":
                    eg_idx = w.get("enroll_group_idx")
                    if eg_idx is None:
                        eg_idx = sec.get("enroll_group_idx")
                    eg_rows = [
                        r for r in course_secs if int(r.get("enroll_group_idx") or 0) == int(eg_idx or 0)
                    ]
                    for r in eg_rows:
                        if str(r["open_status"]).upper() in wanted_statuses:
                            open_sections.append(
                                {
                                    "class_nbr": int(r["class_nbr"]),
                                    "ssr_component": r["ssr_component"],
                                    "section": r["section"],
                                    "open_status": r["open_status"],
                                    "meetings_summary": r.get("meetings_summary") or "",
                                    "instructors_summary": r.get("instructors_summary") or "",
                                    "is_target": int(r["class_nbr"]) == int(w["class_nbr"]),
                                }
                            )
                    open_sections.sort(
                        key=lambda s: (
                            0 if s["is_target"] else 1,
                            0 if s["open_status"] == "O" else 1,
                            s["class_nbr"],
                        )
                    )
                elif str(sec["open_status"]).upper() in wanted_statuses:
                    open_sections.append(
                        {
                            "class_nbr": int(w["class_nbr"]),
                            "ssr_component": sec["ssr_component"],
                            "section": sec["section"],
                            "open_status": sec["open_status"],
                            "meetings_summary": sec.get("meetings_summary") or "",
                            "instructors_summary": sec.get("instructors_summary") or "",
                            "is_target": True,
                        }
                    )
        else:
            filtered = _filter_section_candidates(course_secs, w.get("component_filter"), ith_only)
            open_cnt = sum(1 for s in filtered if s["open_status"] == "O")
            wait_cnt = sum(1 for s in filtered if s["open_status"] == "W")
            comp = (w.get("component_filter") or "").strip().upper()
            item["section_info"] = {
                "ssr_component": comp or "ANY",
                "section": f"{open_cnt}/{len(filtered)} open",
                "open_status": "O" if open_cnt > 0 else ("W" if wait_cnt > 0 else "C"),
                "meetings_summary": f"{len(filtered)} matching {'Ithaca/virtual ' if ith_only else ''}sections",
                "instructors_summary": "",
                "campus": "MAIN" if ith_only else "",
                "location": "ITH" if ith_only else "",
                "location_descr": "Ithaca / Virtual" if ith_only else "",
                "instruction_mode": "",
                "updated_at": None,
            }
            for s in filtered:
                if str(s["open_status"]).upper() in wanted_statuses:
                    open_sections.append(
                        {
                            "class_nbr": int(s["class_nbr"]),
                            "ssr_component": s["ssr_component"],
                            "section": s["section"],
                            "open_status": s["open_status"],
                            "meetings_summary": s.get("meetings_summary") or "",
                            "instructors_summary": s.get("instructors_summary") or "",
                            "is_target": False,
                        }
                    )
            open_sections.sort(
                key=lambda s: (
                    0 if s["open_status"] == "O" else 1,
                    s["ssr_component"],
                    s["class_nbr"],
                )
            )
        item["open_sections"] = open_sections
        item["group_key"] = str(item.get("group_key") or "").strip()

        course_events = _filter_events_for_watch(
            item,
            events_by_course.get(ckey, []),
            section_by_nbr=section_by_nbr,
        )
        windows = compute_all_window_stats(course_events, cutoffs)
        s24, s7, s30, s_all = windows["24h"], windows["7d"], windows["30d"], windows["all"]
        item["turnover_summary"] = {
            "h24": s24["total_flips"],
            "d7": s7["total_flips"],
            "d30": s30["total_flips"],
            "all": s_all["total_flips"],
            "opened_24h": s24["opened_count"],
            "opened_7d": s7["opened_count"],
            "avg_open_sec_7d": s7["avg_open_sec"],
            "last_opened_at": s_all["last_opened_at"],
        }
        tracking_days = compute_tracking_days(
            first_synced_by_subj.get((str(w["roster"]), str(w["subject"]))),
            course_events,
            fallback_since=w.get("created_at"),
            now=now_dt,
        )
        item["drop_odds"] = compute_drop_odds_from_windows(windows, tracking_days=tracking_days)
        enriched.append(item)
    return enriched


async def _fetch_enriched_watch(db: Database, watch_id: int) -> dict[str, Any]:
    row = await db.fetch_one("SELECT * FROM watches WHERE id = ?", (watch_id,))
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Watch not found")
    enriched = await _enrich_watches(db, [row])
    if not enriched:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Watch not found")
    return enriched[0]


async def _enforce_subject_budget(
    db: Database,
    user: dict[str, Any],
    settings: Settings,
    roster_u: str,
    subject_u: str,
) -> None:
    if user["role"] == "admin":
        return
    distinct_rows = await db.fetch_all(
        "SELECT DISTINCT roster, subject FROM watches WHERE user_id = ? AND active = 1",
        (user["id"],),
    )
    existing_buckets = {(str(r["roster"]).upper(), str(r["subject"]).upper()) for r in distinct_rows}
    if (roster_u, subject_u) not in existing_buckets and len(existing_buckets) >= settings.max_subjects_per_invited_user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Invited users may actively track up to {settings.max_subjects_per_invited_user} subjects at once.",
        )


@router.get("")
async def list_watches(
    user: dict[str, Any] = Depends(get_current_user),
    db: Database = Depends(get_db),
) -> dict[str, Any]:
    rows = await db.fetch_all(_WATCH_LIST_SQL, (user["id"],))
    return {"watches": await _enrich_watches(db, rows)}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_watch(
    body: CreateWatchRequest,
    user: dict[str, Any] = Depends(get_current_user),
    db: Database = Depends(get_db),
    settings: Settings = Depends(get_settings),
    catalog: CatalogSyncService = Depends(get_catalog),
    poller: PollerEngine = Depends(get_poller),
) -> dict[str, Any]:
    roster_u = body.roster.strip().upper()
    subject_u = body.subject.strip().upper()
    catalog_nbr = body.catalog_nbr.strip()
    comp_filter = body.component_filter.strip().upper() if body.component_filter else None

    if body.mode in {"exact", "linked_group"} and body.class_nbr is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="class_nbr is required for exact and linked_group watch modes",
        )

    await _enforce_subject_budget(db, user, settings, roster_u, subject_u)

    course_row = await db.fetch_one(
        "SELECT title_long FROM courses_meta WHERE roster = ? AND subject = ? AND catalog_nbr = ?",
        (roster_u, subject_u, catalog_nbr),
    )
    if course_row is None:
        try:
            await catalog.ensure_subject_synced(roster_u, subject_u)
            course_row = await db.fetch_one(
                "SELECT title_long FROM courses_meta WHERE roster = ? AND subject = ? AND catalog_nbr = ?",
                (roster_u, subject_u, catalog_nbr),
            )
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Could not fetch course from Cornell: {exc}") from exc

    if course_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found in roster")

    dup = await db.fetch_one(
        """
        SELECT id FROM watches
        WHERE user_id = ? AND roster = ? AND subject = ? AND catalog_nbr = ?
          AND mode = ? AND COALESCE(class_nbr, -1) = COALESCE(?, -1)
          AND COALESCE(component_filter, '') = COALESCE(?, '')
        """,
        (user["id"], roster_u, subject_u, catalog_nbr, body.mode, body.class_nbr, comp_filter),
    )
    if dup is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="You are already watching this section/mode")

    enroll_group_idx = body.enroll_group_idx
    last_observed: str | None = None

    if body.class_nbr is not None:
        sec_row = await db.fetch_one(
            """
            SELECT class_nbr, enroll_group_idx, ssr_component, open_status, components_required_json
            FROM roster_sections
            WHERE roster = ? AND subject = ? AND catalog_nbr = ? AND class_nbr = ?
            """,
            (roster_u, subject_u, catalog_nbr, body.class_nbr),
        )
        if sec_row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class number not found for this course in roster")
        enroll_group_idx = int(sec_row["enroll_group_idx"])
        poller.seed_section_status(roster_u, int(sec_row["class_nbr"]), sec_row["open_status"])

        if body.mode == "linked_group":
            eg_rows = await db.fetch_all(
                """
                SELECT class_nbr, enroll_group_idx, ssr_component, section, open_status, components_required_json
                FROM roster_sections
                WHERE roster = ? AND subject = ? AND catalog_nbr = ? AND enroll_group_idx = ?
                """,
                (roster_u, subject_u, catalog_nbr, enroll_group_idx),
            )
            status_map = {int(r["class_nbr"]): str(r["open_status"]) for r in eg_rows}
            for r in eg_rows:
                poller.seed_section_status(roster_u, int(r["class_nbr"]), r["open_status"])
            target_sec_obj = SectionRecord(
                class_nbr=int(sec_row["class_nbr"]),
                enroll_group_idx=enroll_group_idx,
                ssr_component=sec_row["ssr_component"],
                section="",
                open_status=sec_row["open_status"],
                components_required=decode_json_list(sec_row.get("components_required_json")),
            )
            eg_objs = [
                SectionRecord(
                    class_nbr=int(r["class_nbr"]),
                    enroll_group_idx=int(r["enroll_group_idx"]),
                    ssr_component=r["ssr_component"],
                    section=r["section"],
                    open_status=r["open_status"],
                    components_required=decode_json_list(r.get("components_required_json")),
                )
                for r in eg_rows
            ]
            ready = _is_linked_group_ready(target_sec_obj, eg_objs, status_map, _target_statuses(body.trigger_on))
            last_observed = "READY" if ready else "NOT_READY"
        else:
            last_observed = sec_row["open_status"]
    else:
        sec_rows = await db.fetch_all(
            """
            SELECT class_nbr, ssr_component, open_status, campus, location, instruction_mode
            FROM roster_sections
            WHERE roster = ? AND subject = ? AND catalog_nbr = ?
            """,
            (roster_u, subject_u, catalog_nbr),
        )
        for r in sec_rows:
            poller.seed_section_status(roster_u, int(r["class_nbr"]), r["open_status"])
        targets = _target_statuses(body.trigger_on)
        filtered = _filter_section_candidates(sec_rows, comp_filter, bool(body.ithaca_or_virtual))
        if body.ithaca_or_virtual and sec_rows and not filtered:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No Ithaca or virtual sections match this watch filter",
            )
        last_observed = "OPEN_ANY" if any(r["open_status"] in targets for r in filtered) else "NONE_OPEN"

    priority = body.priority if user["role"] == "admin" else 1
    ith_flag = 1 if (body.mode == "any_section" and body.ithaca_or_virtual) else 0
    group_key = _normalize_group_key(body.group_key)

    cursor = await db.execute(
        """
        INSERT INTO watches (
            user_id, roster, subject, catalog_nbr, course_title,
            class_nbr, enroll_group_idx, component_filter, mode, trigger_on,
            priority, active, auto_pause, ithaca_or_virtual, cooldown_sec,
            group_key, last_observed_status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?)
        """,
        (
            user["id"],
            roster_u,
            subject_u,
            catalog_nbr,
            course_row["title_long"],
            body.class_nbr,
            enroll_group_idx,
            comp_filter,
            body.mode,
            body.trigger_on,
            priority,
            1 if body.auto_pause else 0,
            ith_flag,
            body.cooldown_sec,
            group_key,
            last_observed,
        ),
    )
    watch_id = int(cursor.lastrowid)
    poller.wake()
    return {"watch": await _fetch_enriched_watch(db, watch_id)}


async def _get_owned_watch(db: Database, watch_id: int, user: dict[str, Any]) -> dict[str, Any]:
    watch = await db.fetch_one("SELECT * FROM watches WHERE id = ?", (watch_id,))
    if watch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Watch not found")
    if watch["user_id"] != user["id"] and user["role"] != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized for this watch")
    return watch


@router.patch("/{watch_id}")
async def update_watch(
    watch_id: int,
    body: UpdateWatchRequest,
    user: dict[str, Any] = Depends(get_current_user),
    db: Database = Depends(get_db),
    settings: Settings = Depends(get_settings),
    poller: PollerEngine = Depends(get_poller),
) -> dict[str, Any]:
    watch = await _get_owned_watch(db, watch_id, user)
    if body.active is True and not watch["active"]:
        await _enforce_subject_budget(db, user, settings, str(watch["roster"]).upper(), str(watch["subject"]).upper())

    updates: list[str] = []
    params: list[Any] = []
    if body.active is not None:
        updates.append("active = ?")
        params.append(1 if body.active else 0)
    if body.auto_pause is not None:
        updates.append("auto_pause = ?")
        params.append(1 if body.auto_pause else 0)
    if body.trigger_on is not None:
        updates.append("trigger_on = ?")
        params.append(body.trigger_on)
    if body.priority is not None and user["role"] == "admin":
        updates.append("priority = ?")
        params.append(body.priority)
    if body.cooldown_sec is not None:
        updates.append("cooldown_sec = ?")
        params.append(body.cooldown_sec)
    if body.group_key is not None:
        updates.append("group_key = ?")
        params.append(_normalize_group_key(body.group_key))

    if updates:
        params.append(watch_id)
        await db.execute(f"UPDATE watches SET {', '.join(updates)} WHERE id = ?", params)
        poller.wake()

    return {"watch": await _fetch_enriched_watch(db, watch_id)}


@router.post("/{watch_id}/rearm")
async def rearm_watch(
    watch_id: int,
    user: dict[str, Any] = Depends(get_current_user),
    db: Database = Depends(get_db),
    settings: Settings = Depends(get_settings),
    poller: PollerEngine = Depends(get_poller),
) -> dict[str, Any]:
    watch = await _get_owned_watch(db, watch_id, user)
    if not watch["active"]:
        await _enforce_subject_budget(db, user, settings, str(watch["roster"]).upper(), str(watch["subject"]).upper())
    await db.execute(
        """
        UPDATE watches
        SET active = 1, last_notified_at = NULL, last_notified_status = NULL
        WHERE id = ?
        """,
        (watch_id,),
    )
    poller.wake()
    return {"watch": await _fetch_enriched_watch(db, watch_id)}


@router.post("/{watch_id}/check-now")
async def check_watch_now(
    watch_id: int,
    user: dict[str, Any] = Depends(get_current_user),
    db: Database = Depends(get_db),
    poller: PollerEngine = Depends(get_poller),
) -> dict[str, Any]:
    watch = await _get_owned_watch(db, watch_id, user)
    roster_u = str(watch["roster"]).upper()
    subject_u = str(watch["subject"]).upper()
    now_mono = time.monotonic()

    # Enforce per-bucket AND global 1.2s guard so manual clicks (even across paused watches) obey Cornell RPS
    bucket = poller._buckets.get((roster_u, subject_u))
    last_bucket_mono = (
        (bucket.last_polled_mono if bucket else 0.0)
        or poller._manual_check_mono.get((roster_u, subject_u), 0.0)
    )
    if (last_bucket_mono and (now_mono - last_bucket_mono) < 1.2) or (
        poller._last_request_mono and (now_mono - poller._last_request_mono) < 1.0
    ):
        cached_rtt = bucket.last_rtt_ms if bucket else int(poller.telemetry.get("last_poll_rtt_ms") or 0)
        return {"ok": True, "cached": True, "rtt_ms": cached_rtt, "alerts_count": 0}
    return await poller.poll_bucket(roster_u, subject_u)


@router.delete("/{watch_id}")
async def delete_watch(
    watch_id: int,
    user: dict[str, Any] = Depends(get_current_user),
    db: Database = Depends(get_db),
    poller: PollerEngine = Depends(get_poller),
) -> dict[str, str]:
    await _get_owned_watch(db, watch_id, user)
    await db.execute("DELETE FROM watches WHERE id = ?", (watch_id,))
    poller.wake()
    return {"status": "deleted"}


@router.post("/group")
async def batch_update_watch_group(
    body: BatchWatchGroupRequest,
    user: dict[str, Any] = Depends(get_current_user),
    db: Database = Depends(get_db),
) -> dict[str, Any]:
    """Assign or clear a mutually-exclusive 'Pick Any 1' group_key across owned watches."""
    group_key = _normalize_group_key(body.group_key)
    ids = sorted(set(body.watch_ids))
    placeholders = ", ".join("?" for _ in ids)
    rows = await db.fetch_all(
        f"SELECT id, user_id FROM watches WHERE id IN ({placeholders})",
        ids,
    )
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No matching watches found")
    for r in rows:
        if r["user_id"] != user["id"] and user["role"] != "admin":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized for one or more watches")

    async with db.write_tx() as conn:
        await conn.execute(
            f"UPDATE watches SET group_key = ? WHERE id IN ({placeholders})",
            [group_key, *ids],
        )

    updated_rows = await db.fetch_all(_WATCH_LIST_SQL, (user["id"],))
    return {"watches": await _enrich_watches(db, updated_rows), "group_key": group_key}


@router.get("/{watch_id}/history")
async def get_watch_history(
    watch_id: int,
    window: Literal["24h", "7d", "30d", "all"] = Query(default="7d"),
    limit: int = Query(default=60, ge=1, le=200),
    user: dict[str, Any] = Depends(get_current_user),
    db: Database = Depends(get_db),
) -> dict[str, Any]:
    """Return multi-window seat turnover statistics and status flip timeline for a watch."""
    watch = await _get_owned_watch(db, watch_id, user)
    course_key = (str(watch["roster"]), str(watch["subject"]), str(watch["catalog_nbr"]))
    _, section_by_nbr = await _fetch_sections_index(db, [course_key])
    rows = await db.fetch_all(
        """
        SELECT id, roster, subject, catalog_nbr, class_nbr, section_label,
               old_status, new_status, poll_rtt_ms, detected_at
        FROM status_events
        WHERE roster = ? AND subject = ? AND catalog_nbr = ?
        ORDER BY detected_at DESC, id DESC
        LIMIT 2000
        """,
        course_key,
    )
    matching = _filter_events_for_watch(watch, rows, section_by_nbr=section_by_nbr)

    now_dt = datetime.now(timezone.utc)
    cutoffs: dict[str, Optional[datetime]] = {
        "24h": now_dt - timedelta(hours=24),
        "7d": now_dt - timedelta(days=7),
        "30d": now_dt - timedelta(days=30),
        "all": None,
    }
    windows = compute_all_window_stats(matching, cutoffs)

    subj_row = await db.fetch_one(
        "SELECT first_synced_at, synced_at FROM subjects WHERE roster = ? AND value = ?",
        (watch["roster"], watch["subject"]),
    )
    tracking_days = compute_tracking_days(
        (subj_row or {}).get("first_synced_at") or (subj_row or {}).get("synced_at"),
        matching,
        fallback_since=watch.get("created_at"),
        now=now_dt,
    )
    drop_odds = compute_drop_odds_from_windows(windows, tracking_days=tracking_days)

    selected_cutoff = cutoffs[window]
    filtered_events: list[dict[str, Any]] = []
    for ev in matching:
        dt = parse_utc_dt(ev.get("detected_at"))
        if dt is None:
            continue
        if selected_cutoff is not None and dt < selected_cutoff:
            continue
        filtered_events.append({**ev, "detected_at": dt.isoformat()})
        if len(filtered_events) >= limit:
            break

    return {
        "watch_id": watch_id,
        "window": window,
        "windows": windows,
        "drop_odds": drop_odds,
        "events": filtered_events,
    }
