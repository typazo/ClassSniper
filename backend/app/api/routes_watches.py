"""Watchlist CRUD, re-arming, and manual check-now endpoints."""

from __future__ import annotations

import json
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.schemas import CreateWatchRequest, UpdateWatchRequest
from app.auth import get_current_user, get_db
from app.config import Settings, get_settings
from app.db import Database
from app.services.catalog import CatalogSyncService
from app.services.poller import PollerEngine, _is_linked_group_ready, _target_statuses
from app.providers.base import SectionRecord
from app.providers.cornell import is_ithaca_or_virtual_section

router = APIRouter(prefix="/api/watches", tags=["watches"])


def get_poller(request: Request) -> PollerEngine:
    return request.app.state.poller


def get_catalog(request: Request) -> CatalogSyncService:
    return request.app.state.catalog


async def _enrich_watches(db: Database, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return []

    enriched: list[dict[str, Any]] = []
    for w in rows:
        item = dict(w)
        item["active"] = bool(item["active"])
        item["auto_pause"] = bool(item["auto_pause"])
        ith_only = bool(item.get("ithaca_or_virtual", 0))
        item["ithaca_or_virtual"] = ith_only
        wanted_statuses = {"O", "W"} if w.get("trigger_on") == "open_or_waitlist" else {"O"}
        open_sections: list[dict[str, Any]] = []

        if w["class_nbr"] is not None:
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
                    eg_rows = await db.fetch_all(
                        """
                        SELECT class_nbr, ssr_component, section, open_status,
                               meetings_summary, instructors_summary
                        FROM roster_sections
                        WHERE roster = ? AND subject = ? AND catalog_nbr = ? AND enroll_group_idx = ?
                        ORDER BY class_nbr ASC
                        """,
                        (w["roster"], w["subject"], w["catalog_nbr"], eg_idx),
                    )
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
            sec_rows = await db.fetch_all(
                """
                SELECT class_nbr, ssr_component, section, open_status,
                       meetings_summary, instructors_summary,
                       campus, location, location_descr, instruction_mode
                FROM roster_sections
                WHERE roster = ? AND subject = ? AND catalog_nbr = ?
                ORDER BY class_nbr ASC
                """,
                (w["roster"], w["subject"], w["catalog_nbr"]),
            )
            comp = (w.get("component_filter") or "").strip().upper()
            filtered = [
                s
                for s in sec_rows
                if (not comp or s["ssr_component"] == comp)
                and (
                    not ith_only
                    or is_ithaca_or_virtual_section(
                        campus=str(s.get("campus") or ""),
                        location=str(s.get("location") or ""),
                        instruction_mode=str(s.get("instruction_mode") or ""),
                    )
                )
            ]
            open_cnt = sum(1 for s in filtered if s["open_status"] == "O")
            wait_cnt = sum(1 for s in filtered if s["open_status"] == "W")
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
        enriched.append(item)
    return enriched


@router.get("")
async def list_watches(
    user: dict[str, Any] = Depends(get_current_user),
    db: Database = Depends(get_db),
) -> dict[str, Any]:
    rows = await db.fetch_all(
        """
        SELECT *
        FROM watches
        WHERE user_id = ?
        ORDER BY active DESC, priority DESC, created_at DESC
        """,
        (user["id"],),
    )
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

    # Enforce per-invited-user subject budget
    if user["role"] != "admin":
        distinct_rows = await db.fetch_all(
            "SELECT DISTINCT roster, subject FROM watches WHERE user_id = ? AND active = 1",
            (user["id"],),
        )
        existing_buckets = {(r["roster"], r["subject"]) for r in distinct_rows}
        if (roster_u, subject_u) not in existing_buckets and len(existing_buckets) >= settings.max_subjects_per_invited_user:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Invited users may actively track up to {settings.max_subjects_per_invited_user} subjects at once.",
            )

    # Ensure course/subject is present locally
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

    # Prevent duplicate watch on identical target for the same user
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
            WHERE roster = ? AND class_nbr = ?
            """,
            (roster_u, body.class_nbr),
        )
        if sec_row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class number not found in roster")
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
                components_required=json.loads(sec_row["components_required_json"] or "[]"),
            )
            eg_objs = [
                SectionRecord(
                    class_nbr=int(r["class_nbr"]),
                    enroll_group_idx=int(r["enroll_group_idx"]),
                    ssr_component=r["ssr_component"],
                    section=r["section"],
                    open_status=r["open_status"],
                    components_required=json.loads(r["components_required_json"] or "[]"),
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
        filtered = [
            r
            for r in sec_rows
            if (not comp_filter or r["ssr_component"] == comp_filter)
            and (
                not body.ithaca_or_virtual
                or is_ithaca_or_virtual_section(
                    campus=str(r.get("campus") or ""),
                    location=str(r.get("location") or ""),
                    instruction_mode=str(r.get("instruction_mode") or ""),
                )
            )
        ]
        if body.ithaca_or_virtual and sec_rows and not filtered:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No Ithaca or virtual sections match this watch filter",
            )
        last_observed = "OPEN_ANY" if any(r["open_status"] in targets for r in filtered) else "NONE_OPEN"

    priority = body.priority if user["role"] == "admin" else 1
    ith_flag = 1 if (body.mode == "any_section" and body.ithaca_or_virtual) else 0

    cursor = await db.execute(
        """
        INSERT INTO watches (
            user_id, roster, subject, catalog_nbr, course_title,
            class_nbr, enroll_group_idx, component_filter, mode, trigger_on,
            priority, active, auto_pause, ithaca_or_virtual, cooldown_sec, last_observed_status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)
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
            last_observed,
        ),
    )
    watch_id = int(cursor.lastrowid)
    poller.wake()

    created = await db.fetch_one("SELECT * FROM watches WHERE id = ?", (watch_id,))
    enriched = await _enrich_watches(db, [created] if created else [])
    return {"watch": enriched[0]}


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
    poller: PollerEngine = Depends(get_poller),
) -> dict[str, Any]:
    watch = await _get_owned_watch(db, watch_id, user)

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

    if updates:
        params.append(watch_id)
        await db.execute(f"UPDATE watches SET {', '.join(updates)} WHERE id = ?", params)
        poller.wake()

    updated = await db.fetch_one("SELECT * FROM watches WHERE id = ?", (watch_id,))
    enriched = await _enrich_watches(db, [updated] if updated else [])
    return {"watch": enriched[0]}


@router.post("/{watch_id}/rearm")
async def rearm_watch(
    watch_id: int,
    user: dict[str, Any] = Depends(get_current_user),
    db: Database = Depends(get_db),
    poller: PollerEngine = Depends(get_poller),
) -> dict[str, Any]:
    await _get_owned_watch(db, watch_id, user)
    await db.execute(
        """
        UPDATE watches
        SET active = 1, last_notified_at = NULL, last_notified_status = NULL
        WHERE id = ?
        """,
        (watch_id,),
    )
    poller.wake()
    updated = await db.fetch_one("SELECT * FROM watches WHERE id = ?", (watch_id,))
    enriched = await _enrich_watches(db, [updated] if updated else [])
    return {"watch": enriched[0]}


@router.post("/{watch_id}/check-now")
async def check_watch_now(
    watch_id: int,
    user: dict[str, Any] = Depends(get_current_user),
    db: Database = Depends(get_db),
    poller: PollerEngine = Depends(get_poller),
) -> dict[str, Any]:
    watch = await _get_owned_watch(db, watch_id, user)
    # Respect minimum 1s bucket guard so manual clicks cannot exceed Cornell rate limit
    bucket = poller._buckets.get((watch["roster"], watch["subject"]))
    if bucket and bucket.last_polled_mono and (time.monotonic() - bucket.last_polled_mono) < 1.2:
        return {"ok": True, "cached": True, "rtt_ms": bucket.last_rtt_ms, "alerts_count": 0}
    return await poller.poll_bucket(watch["roster"], watch["subject"])


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
