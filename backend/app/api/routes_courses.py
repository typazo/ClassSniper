"""Course search, roster listing, and catalog sync API routes."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Optional

import orjson
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.api.schemas import SyncCatalogRequest
from app.auth import get_current_user, get_db
from app.db import Database
from app.services.catalog import CatalogSyncService

router = APIRouter(prefix="/api", tags=["courses"])


def get_catalog(request: Request) -> CatalogSyncService:
    return request.app.state.catalog


@router.get("/rosters")
async def list_rosters(
    _: dict[str, Any] = Depends(get_current_user),
    db: Database = Depends(get_db),
    catalog: CatalogSyncService = Depends(get_catalog),
) -> dict[str, Any]:
    rows = await db.fetch_all(
        """
        SELECT slug, descr, is_default, archive_mode, strm, last_modified_dttm
        FROM rosters
        ORDER BY archive_mode ASC, strm DESC
        """
    )
    if not rows:
        try:
            await catalog.sync_rosters_and_subjects()
            rows = await db.fetch_all(
                """
                SELECT slug, descr, is_default, archive_mode, strm, last_modified_dttm
                FROM rosters
                ORDER BY archive_mode ASC, strm DESC
                """
            )
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Failed to fetch rosters from Cornell: {exc}") from exc

    return {"rosters": rows}


@router.get("/subjects")
async def list_subjects(
    roster: str = Query(..., min_length=3, max_length=10),
    _: dict[str, Any] = Depends(get_current_user),
    db: Database = Depends(get_db),
    catalog: CatalogSyncService = Depends(get_catalog),
) -> dict[str, Any]:
    roster_u = roster.upper()
    rows = await db.fetch_all(
        "SELECT value, descr, synced_at FROM subjects WHERE roster = ? ORDER BY value ASC",
        (roster_u,),
    )
    if not rows:
        try:
            await catalog.sync_rosters_and_subjects(roster_u)
            rows = await db.fetch_all(
                "SELECT value, descr, synced_at FROM subjects WHERE roster = ? ORDER BY value ASC",
                (roster_u,),
            )
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Failed to fetch subjects: {exc}") from exc

    return {"roster": roster_u, "subjects": rows}


@router.get("/courses/search")
async def search_courses(
    roster: str = Query(..., min_length=3, max_length=10),
    q: str = Query(default="", max_length=100),
    subject: str = Query(default="", max_length=12),
    limit: int = Query(default=40, ge=1, le=100),
    _: dict[str, Any] = Depends(get_current_user),
    catalog: CatalogSyncService = Depends(get_catalog),
) -> dict[str, Any]:
    courses = await catalog.search_courses(roster=roster, query=q, subject=subject, limit=limit)
    return {"roster": roster.upper(), "courses": courses}


@router.get("/courses/{roster}/{subject}/{catalog_nbr}")
async def get_course_detail(
    roster: str,
    subject: str,
    catalog_nbr: str,
    _: dict[str, Any] = Depends(get_current_user),
    db: Database = Depends(get_db),
    catalog: CatalogSyncService = Depends(get_catalog),
) -> dict[str, Any]:
    roster_u = roster.upper()
    subject_u = subject.upper()
    await catalog.ensure_subject_synced(roster_u, subject_u)

    course = await db.fetch_one(
        """
        SELECT roster, subject, catalog_nbr, title_short, title_long, description,
               crse_id, enroll_groups_json, updated_at
        FROM courses_meta
        WHERE roster = ? AND subject = ? AND catalog_nbr = ?
        """,
        (roster_u, subject_u, catalog_nbr),
    )
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

    sections = await db.fetch_all(
        """
        SELECT class_nbr, enroll_group_idx, ssr_component, section, open_status,
               components_required_json, meetings_summary, instructors_summary,
               campus, instruction_mode, updated_at
        FROM roster_sections
        WHERE roster = ? AND subject = ? AND catalog_nbr = ?
        ORDER BY enroll_group_idx ASC, class_nbr ASC
        """,
        (roster_u, subject_u, catalog_nbr),
    )
    for sec in sections:
        sec["components_required"] = json.loads(sec.pop("components_required_json", "[]"))

    course["enroll_groups"] = orjson.loads(course.pop("enroll_groups_json"))
    course["sections"] = sections
    return {"course": course}


@router.post("/catalog/sync")
async def sync_catalog(
    body: SyncCatalogRequest,
    user: dict[str, Any] = Depends(get_current_user),
    catalog: CatalogSyncService = Depends(get_catalog),
) -> dict[str, Any]:
    target_roster = (body.roster or await catalog.get_default_roster_slug()).upper()
    if body.subject:
        synced = await catalog.ensure_subject_synced(target_roster, body.subject.upper(), force=True)
        return {"status": "synced", "roster": target_roster, "subject": body.subject.upper(), "updated": synced}

    if user["role"] != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins can trigger full roster sync")

    if catalog.status["in_progress"]:
        return {"status": "already_running", "roster": target_roster}

    asyncio.create_task(catalog.sync_full_roster(target_roster), name=f"sync-{target_roster}")
    return {"status": "started", "roster": target_roster}
