"""Course search, roster listing, and catalog sync API routes."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Literal, Optional

import orjson
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.api.schemas import CompletedPrereqsRequest, RefreshSubjectsRequest, SyncCatalogRequest
from app.auth import get_current_user, get_db
from app.db import Database
from app.services.catalog import CatalogSyncService
from app.services.insights import CourseInsightsService, build_external_links

router = APIRouter(prefix="/api", tags=["courses"])


def get_catalog(request: Request) -> CatalogSyncService:
    return request.app.state.catalog


def get_insights(request: Request) -> CourseInsightsService:
    return request.app.state.insights


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
    subjects: str = Query(default="", max_length=300),
    level_min: Optional[int] = Query(default=None, ge=1000, le=9000),
    min_credits: Optional[float] = Query(default=None, ge=0.0, le=20.0),
    cs_requirement: Literal["", "cs_elective", "tech_elective", "external_spec"] = Query(default=""),
    include_2000_te: bool = Query(default=True),
    include_research_te: bool = Query(default=True),
    curriculum: Literal["current", "pre2024"] = Query(default="current"),
    ilr_codes: str = Query(default="", max_length=200),
    ilr_match: Literal["any", "all"] = Query(default="any"),
    ilr_multi_only: bool = Query(default=False),
    include_ilr: bool = Query(default=False),
    only_eligible: bool = Query(default=False),
    include_implied_prereqs: Optional[bool] = Query(default=None),
    ithaca_or_virtual: bool = Query(default=True),
    refresh_stale: bool = Query(default=True),
    limit: int = Query(default=100, ge=1, le=300),
    user: dict[str, Any] = Depends(get_current_user),
    catalog: CatalogSyncService = Depends(get_catalog),
) -> dict[str, Any]:
    parsed_subjects = [s.strip().upper() for s in subjects.split(",") if s.strip()]
    if subject.strip():
        single = subject.strip().upper()
        if single not in parsed_subjects:
            parsed_subjects.insert(0, single)

    parsed_ilr_codes = [c.strip().upper() for c in ilr_codes.split(",") if c.strip()]
    effective_include_ilr = (
        include_ilr
        or bool(parsed_ilr_codes)
        or ilr_multi_only
        or user.get("major_mode") == "ilr"
    )

    completed_courses = list(user.get("completed_courses") or [])
    effective_implied = (
        bool(user.get("include_implied_prereqs", True))
        if include_implied_prereqs is None
        else bool(include_implied_prereqs)
    )

    result = await catalog.search_courses_advanced(
        roster=roster,
        query=q,
        subjects=parsed_subjects,
        level_min=level_min,
        min_credits=min_credits,
        cs_requirement=cs_requirement,
        include_2000_te=include_2000_te,
        include_research_te=include_research_te,
        curriculum=curriculum,
        ilr_codes=parsed_ilr_codes,
        ilr_match=ilr_match,
        ilr_multi_only=ilr_multi_only,
        include_ilr=effective_include_ilr,
        completed_courses=completed_courses,
        only_eligible=only_eligible,
        include_implied_prereqs=effective_implied,
        ithaca_or_virtual=ithaca_or_virtual,
        refresh_stale=refresh_stale,
        limit=limit,
    )
    return {
        "roster": roster.upper(),
        "courses": result["courses"],
        "meta": result["meta"],
    }


@router.get("/ilr/summary")
async def get_ilr_summary(
    roster: Optional[str] = Query(default=None, min_length=3, max_length=10),
    ithaca_or_virtual: bool = Query(default=True),
    sync_priority: bool = Query(default=False),
    _: dict[str, Any] = Depends(get_current_user),
    catalog: CatalogSyncService = Depends(get_catalog),
) -> dict[str, Any]:
    target_roster = (roster or await catalog.get_default_roster_slug()).upper()
    return await catalog.get_ilr_summary(
        target_roster,
        ithaca_or_virtual=ithaca_or_virtual,
        sync_priority=sync_priority,
    )


@router.post("/courses/refresh-subjects")
async def queue_refresh_subjects(
    body: RefreshSubjectsRequest,
    _: dict[str, Any] = Depends(get_current_user),
    catalog: CatalogSyncService = Depends(get_catalog),
) -> dict[str, Any]:
    queued = catalog.queue_visible_refresh(body.roster, body.subjects)
    return {"roster": body.roster.upper(), "queued": queued}


@router.get("/catalog/status")
async def get_catalog_status(
    roster: Optional[str] = Query(default=None, min_length=3, max_length=10),
    _: dict[str, Any] = Depends(get_current_user),
    catalog: CatalogSyncService = Depends(get_catalog),
) -> dict[str, Any]:
    target_roster = (roster or await catalog.get_default_roster_slug()).upper()
    return await catalog.get_catalog_status(target_roster)


@router.get("/courses/{roster}/{subject}/{catalog_nbr}/insights")
async def get_course_insights(
    roster: str,
    subject: str,
    catalog_nbr: str,
    refresh: bool = Query(default=False),
    _: dict[str, Any] = Depends(get_current_user),
    insights: CourseInsightsService = Depends(get_insights),
) -> dict[str, Any]:
    return await insights.get_course_insights(
        roster=roster,
        subject=subject,
        catalog_nbr=catalog_nbr,
        force_refresh=refresh,
    )


@router.get("/courses/{roster}/{subject}/{catalog_nbr}")
async def get_course_detail(
    roster: str,
    subject: str,
    catalog_nbr: str,
    include_ilr: bool = Query(default=False),
    user: dict[str, Any] = Depends(get_current_user),
    db: Database = Depends(get_db),
    catalog: CatalogSyncService = Depends(get_catalog),
) -> dict[str, Any]:
    roster_u = roster.upper()
    subject_u = subject.upper()
    await catalog.ensure_subject_synced(roster_u, subject_u)

    course = await db.fetch_one(
        """
        SELECT roster, subject, catalog_nbr, title_short, title_long, description,
               crse_id, acad_career, acad_group, catalog_prereq, catalog_coreq,
               catalog_forbidden_overlaps, catalog_num, units_min, units_max,
               has_letter_grade, crosslists_json, components_json,
               crse_attrs_json, enroll_groups_json, updated_at
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
               campus, location, location_descr, instruction_mode, updated_at
        FROM roster_sections
        WHERE roster = ? AND subject = ? AND catalog_nbr = ?
        ORDER BY enroll_group_idx ASC, class_nbr ASC
        """,
        (roster_u, subject_u, catalog_nbr),
    )
    for sec in sections:
        sec["components_required"] = json.loads(sec.pop("components_required_json", "[]"))

    course["crosslists"] = json.loads(course.pop("crosslists_json", "[]"))
    course["components"] = json.loads(course.pop("components_json", "[]"))
    course["has_letter_grade"] = bool(course.get("has_letter_grade", 1))
    course["enroll_groups"] = orjson.loads(course.pop("enroll_groups_json"))
    course["sections"] = sections
    course["external_links"] = build_external_links(roster_u, subject_u, catalog_nbr)
    if include_ilr or user.get("major_mode") == "ilr":
        ilr_index = await catalog.get_ilr_requirements_index(roster_u)
        elig = ilr_index.get(subject_u, catalog_nbr)
        course["ilr_eligibility"] = elig.to_dict() if elig is not None else None
    course.pop("crse_attrs_json", None)
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


async def _build_user_prereqs_payload(
    catalog: CatalogSyncService,
    roster: Optional[str],
    completed_courses: list[str],
    include_implied_prereqs: bool,
) -> dict[str, Any]:
    target_roster = (roster or await catalog.get_default_roster_slug()).upper()
    cs_index = await catalog.get_cs_requirements_index(target_roster)
    _, implied_courses = cs_index.expand_satisfied_courses(
        completed_courses,
        include_implied=include_implied_prereqs,
    )
    return {
        "completed_courses": completed_courses,
        "include_implied_prereqs": include_implied_prereqs,
        "implied_courses": implied_courses,
    }


@router.get("/user/prereqs")
async def get_user_prereqs(
    roster: Optional[str] = Query(default=None, min_length=3, max_length=10),
    user: dict[str, Any] = Depends(get_current_user),
    catalog: CatalogSyncService = Depends(get_catalog),
) -> dict[str, Any]:
    return await _build_user_prereqs_payload(
        catalog=catalog,
        roster=roster,
        completed_courses=list(user.get("completed_courses") or []),
        include_implied_prereqs=bool(user.get("include_implied_prereqs", True)),
    )


@router.put("/user/prereqs")
async def update_user_prereqs(
    body: CompletedPrereqsRequest,
    roster: Optional[str] = Query(default=None, min_length=3, max_length=10),
    user: dict[str, Any] = Depends(get_current_user),
    db: Database = Depends(get_db),
    catalog: CatalogSyncService = Depends(get_catalog),
) -> dict[str, Any]:
    completed = list(body.completed_courses)
    include_implied = (
        bool(user.get("include_implied_prereqs", True))
        if body.include_implied_prereqs is None
        else bool(body.include_implied_prereqs)
    )
    async with db.write_tx() as conn:
        await conn.execute(
            """
            UPDATE users
            SET completed_courses_json = ?,
                include_implied_prereqs = ?
            WHERE id = ?
            """,
            (json.dumps(completed), 1 if include_implied else 0, user["id"]),
        )
    return await _build_user_prereqs_payload(
        catalog=catalog,
        roster=roster,
        completed_courses=completed,
        include_implied_prereqs=include_implied,
    )


@router.get("/user/prereqs/options")
async def get_user_prereq_options(
    roster: Optional[str] = Query(default=None, min_length=3, max_length=10),
    q: str = Query(default="", max_length=100),
    limit: int = Query(default=30, ge=1, le=100),
    mode: Optional[Literal["cs", "ilr", "general"]] = Query(default=None),
    user: dict[str, Any] = Depends(get_current_user),
    catalog: CatalogSyncService = Depends(get_catalog),
) -> dict[str, Any]:
    target_roster = (roster or await catalog.get_default_roster_slug()).upper()
    effective_mode = mode or ("ilr" if user.get("major_mode") == "ilr" else "cs")
    options = await catalog.get_prereq_course_options(
        target_roster,
        query=q,
        limit=limit,
        mode=effective_mode,
    )
    return {"roster": target_roster, "options": options}
