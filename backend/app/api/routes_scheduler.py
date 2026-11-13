"""Scheduler API routes for saved schedules, course items, busy blocks, and opt-in share links."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.api.schemas import (
    AddScheduleCourseRequest,
    ApplyGeneratedScheduleRequest,
    CreateScheduleBlockRequest,
    CreateScheduleRequest,
    QuickAddScheduleCourseRequest,
    UpdateScheduleBlockRequest,
    UpdateScheduleCourseRequest,
    UpdateScheduleRequest,
)
from app.auth import get_current_user
from app.services.catalog import CatalogSyncService
from app.services.insights import CourseInsightsService
from app.services.scheduler import SchedulerService


def get_insights(request: Request) -> CourseInsightsService:
    return request.app.state.insights

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/schedules", tags=["scheduler"])


def get_scheduler(request: Request) -> SchedulerService:
    return request.app.state.scheduler


def get_catalog(request: Request) -> CatalogSyncService:
    return request.app.state.catalog


@router.get("/shared/{token}")
async def get_shared_schedule(
    token: str,
    scheduler: SchedulerService = Depends(get_scheduler),
) -> dict[str, Any]:
    """Public read-only endpoint for schedules with opt-in sharing enabled."""
    payload = await scheduler.get_shared_schedule(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shared schedule not found or sharing has been disabled.",
        )
    return payload


@router.get("")
async def list_schedules(
    roster: Optional[str] = Query(default=None, min_length=3, max_length=10),
    user: dict[str, Any] = Depends(get_current_user),
    scheduler: SchedulerService = Depends(get_scheduler),
    catalog: CatalogSyncService = Depends(get_catalog),
) -> dict[str, Any]:
    target_roster = (roster or await catalog.get_default_roster_slug()).upper()
    schedules = await scheduler.list_schedules(int(user["id"]), target_roster)
    active = next((s for s in schedules if s["is_active"]), schedules[0])
    hydrated = await scheduler.hydrate_schedule(int(active["id"]), user_id=int(user["id"]), user=user)
    return {
        "roster": target_roster,
        "schedules": schedules,
        "active": hydrated,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_schedule(
    body: CreateScheduleRequest,
    user: dict[str, Any] = Depends(get_current_user),
    scheduler: SchedulerService = Depends(get_scheduler),
) -> dict[str, Any]:
    try:
        hydrated = await scheduler.create_schedule(
            user_id=int(user["id"]),
            roster=body.roster,
            name=body.name,
            duplicate_from_id=body.duplicate_from_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    schedules = await scheduler.list_schedules(int(user["id"]), body.roster.upper())
    return {"schedules": schedules, "active": hydrated}


@router.post("/quick-add")
async def quick_add_course_to_active_schedule(
    body: QuickAddScheduleCourseRequest,
    user: dict[str, Any] = Depends(get_current_user),
    scheduler: SchedulerService = Depends(get_scheduler),
) -> dict[str, Any]:
    roster_u = body.roster.strip().upper()
    schedules = await scheduler.list_schedules(int(user["id"]), roster_u)
    active = next((s for s in schedules if s["is_active"]), schedules[0])
    schedule_id = int(active["id"])
    already_present = False
    try:
        hydrated = await scheduler.add_course(
            schedule_id=schedule_id,
            user_id=int(user["id"]),
            subject=body.subject,
            catalog_nbr=body.catalog_nbr,
            enabled=body.enabled,
            selected_units=body.selected_units,
            selected_class_nbrs=body.selected_class_nbrs,
            locked_class_nbrs=body.locked_class_nbrs,
            color_idx=body.color_idx,
        )
    except FileExistsError:
        already_present = True
        hydrated = await scheduler.hydrate_schedule(schedule_id, user_id=int(user["id"]), user=user)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return {
        "already_present": already_present,
        "schedule_name": active["name"],
        "active": hydrated,
    }


@router.get("/{schedule_id}")
async def get_schedule(
    schedule_id: int,
    user: dict[str, Any] = Depends(get_current_user),
    scheduler: SchedulerService = Depends(get_scheduler),
) -> dict[str, Any]:
    hydrated = await scheduler.hydrate_schedule(schedule_id, user_id=int(user["id"]), user=user)
    if hydrated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")
    return hydrated


@router.patch("/{schedule_id}")
async def update_schedule(
    schedule_id: int,
    body: UpdateScheduleRequest,
    user: dict[str, Any] = Depends(get_current_user),
    scheduler: SchedulerService = Depends(get_scheduler),
) -> dict[str, Any]:
    try:
        hydrated = await scheduler.update_schedule(
            schedule_id=schedule_id,
            user_id=int(user["id"]),
            name=body.name,
            is_active=body.is_active,
            share_enabled=body.share_enabled,
            regenerate_share_token=body.regenerate_share_token,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    if hydrated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")
    schedules = await scheduler.list_schedules(int(user["id"]), hydrated["schedule"]["roster"])
    return {"schedules": schedules, "active": hydrated}


@router.delete("/{schedule_id}")
async def delete_schedule(
    schedule_id: int,
    roster: Optional[str] = Query(default=None),
    user: dict[str, Any] = Depends(get_current_user),
    scheduler: SchedulerService = Depends(get_scheduler),
    catalog: CatalogSyncService = Depends(get_catalog),
) -> dict[str, Any]:
    sched = await scheduler.hydrate_schedule(schedule_id, user_id=int(user["id"]), user=user)
    if sched is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")
    target_roster = (roster or sched["schedule"]["roster"] or await catalog.get_default_roster_slug()).upper()
    ok = await scheduler.delete_schedule(schedule_id, user_id=int(user["id"]))
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")
    schedules = await scheduler.list_schedules(int(user["id"]), target_roster)
    active = next((s for s in schedules if s["is_active"]), schedules[0])
    hydrated = await scheduler.hydrate_schedule(int(active["id"]), user_id=int(user["id"]), user=user)
    return {"schedules": schedules, "active": hydrated}


@router.post("/{schedule_id}/courses", status_code=status.HTTP_201_CREATED)
async def add_schedule_course(
    schedule_id: int,
    body: AddScheduleCourseRequest,
    user: dict[str, Any] = Depends(get_current_user),
    scheduler: SchedulerService = Depends(get_scheduler),
) -> dict[str, Any]:
    try:
        hydrated = await scheduler.add_course(
            schedule_id=schedule_id,
            user_id=int(user["id"]),
            subject=body.subject,
            catalog_nbr=body.catalog_nbr,
            enabled=body.enabled,
            selected_units=body.selected_units,
            selected_class_nbrs=body.selected_class_nbrs,
            locked_class_nbrs=body.locked_class_nbrs,
            color_idx=body.color_idx,
        )
    except FileExistsError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return hydrated


@router.patch("/{schedule_id}/courses/{item_id}")
async def update_schedule_course(
    schedule_id: int,
    item_id: int,
    body: UpdateScheduleCourseRequest,
    user: dict[str, Any] = Depends(get_current_user),
    scheduler: SchedulerService = Depends(get_scheduler),
) -> dict[str, Any]:
    try:
        hydrated = await scheduler.update_course(
            schedule_id=schedule_id,
            item_id=item_id,
            user_id=int(user["id"]),
            enabled=body.enabled,
            selected_units=body.selected_units,
            selected_class_nbrs=body.selected_class_nbrs,
            locked_class_nbrs=body.locked_class_nbrs,
            color_idx=body.color_idx,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    if hydrated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule item not found")
    return hydrated


@router.put("/{schedule_id}/apply-generated")
async def apply_generated_schedule(
    schedule_id: int,
    body: ApplyGeneratedScheduleRequest,
    user: dict[str, Any] = Depends(get_current_user),
    scheduler: SchedulerService = Depends(get_scheduler),
) -> dict[str, Any]:
    hydrated = await scheduler.apply_generated(
        schedule_id=schedule_id,
        user_id=int(user["id"]),
        updates=[(item.item_id, item.selected_class_nbrs) for item in body.items],
    )
    if hydrated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")
    return hydrated


@router.delete("/{schedule_id}/courses/{item_id}")
async def remove_schedule_course(
    schedule_id: int,
    item_id: int,
    user: dict[str, Any] = Depends(get_current_user),
    scheduler: SchedulerService = Depends(get_scheduler),
) -> dict[str, Any]:
    try:
        hydrated = await scheduler.remove_course(
            schedule_id=schedule_id,
            item_id=item_id,
            user_id=int(user["id"]),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    if hydrated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule item not found")
    return hydrated


@router.post("/{schedule_id}/blocks", status_code=status.HTTP_201_CREATED)
async def create_schedule_block(
    schedule_id: int,
    body: CreateScheduleBlockRequest,
    user: dict[str, Any] = Depends(get_current_user),
    scheduler: SchedulerService = Depends(get_scheduler),
) -> dict[str, Any]:
    try:
        hydrated = await scheduler.add_block(
            schedule_id=schedule_id,
            user_id=int(user["id"]),
            label=body.label,
            days=list(body.days),
            start_min=body.start_min,
            end_min=body.end_min,
            enabled=body.enabled,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if hydrated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")
    return hydrated


@router.patch("/{schedule_id}/blocks/{block_id}")
async def update_schedule_block(
    schedule_id: int,
    block_id: int,
    body: UpdateScheduleBlockRequest,
    user: dict[str, Any] = Depends(get_current_user),
    scheduler: SchedulerService = Depends(get_scheduler),
) -> dict[str, Any]:
    try:
        hydrated = await scheduler.update_block(
            schedule_id=schedule_id,
            block_id=block_id,
            user_id=int(user["id"]),
            label=body.label,
            days=list(body.days) if body.days is not None else None,
            start_min=body.start_min,
            end_min=body.end_min,
            enabled=body.enabled,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if hydrated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule block not found")
    return hydrated


@router.delete("/{schedule_id}/blocks/{block_id}")
async def delete_schedule_block(
    schedule_id: int,
    block_id: int,
    user: dict[str, Any] = Depends(get_current_user),
    scheduler: SchedulerService = Depends(get_scheduler),
) -> dict[str, Any]:
    hydrated = await scheduler.delete_block(
        schedule_id=schedule_id,
        block_id=block_id,
        user_id=int(user["id"]),
    )
    if hydrated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule block not found")
    return hydrated


@router.post("/{schedule_id}/insights")
async def batch_load_schedule_insights(
    schedule_id: int,
    force: bool = Query(default=False),
    user: dict[str, Any] = Depends(get_current_user),
    scheduler: SchedulerService = Depends(get_scheduler),
    insights: CourseInsightsService = Depends(get_insights),
) -> dict[str, Any]:
    """Fetch CU Reviews & RateMyProfessors insights for all courses in a schedule."""
    hydrated = await scheduler.hydrate_schedule(schedule_id, user_id=int(user["id"]), user=user)
    if hydrated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")

    roster_u = str((hydrated.get("schedule") or {}).get("roster") or hydrated.get("roster") or "").upper()
    sem = asyncio.Semaphore(3)
    courses_to_load = [
        c
        for c in hydrated["courses"]
        if force or (c.get("cached_insights") is None and not (c.get("cached_rmp") or {}))
    ]

    async def _fetch_one(course_item: dict[str, Any]) -> bool:
        async with sem:
            try:
                await insights.get_course_insights(
                    roster_u,
                    str(course_item["subject"]),
                    str(course_item["catalog_nbr"]),
                    force_refresh=force,
                )
                return True
            except Exception as exc:
                logger.warning(
                    "Failed loading insights for %s %s %s: %s",
                    roster_u,
                    course_item.get("subject"),
                    course_item.get("catalog_nbr"),
                    exc,
                )
                return False

    results = await asyncio.gather(*(_fetch_one(c) for c in courses_to_load))
    refreshed = await scheduler.hydrate_schedule(schedule_id, user_id=int(user["id"]), user=user)
    return {
        **(refreshed or hydrated),
        "insights_fetched_count": sum(1 for ok in results if ok),
    }
