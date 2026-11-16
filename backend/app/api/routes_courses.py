"""Course search, roster listing, and catalog sync API routes."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Literal, Optional

import orjson
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_catalog, get_insights, get_scheduler
from app.api.schemas import (
    CompletedPrereqsRequest,
    ImportTranscriptRequest,
    SyncCatalogRequest,
    UpdateCsChecklistRequest,
)
from app.auth import get_current_user, get_db
from app.db import Database
from app.services.attributes import extract_course_attributes
from app.services.catalog import CatalogSyncService
from app.services.cs_checklist import build_cs_checklist_payload, merge_transcript_into_user_checklist
from app.services.drop_odds import fetch_course_drop_odds_map
from app.services.cs_requirements import (
    decode_completed_course_details,
    decode_completed_courses,
    normalize_completed_courses,
    normalize_course_code,
    normalize_course_detail,
)
from app.services.insights import CourseInsightsService, build_external_links
from app.services.scheduler import SchedulerService

router = APIRouter(prefix="/api", tags=["courses"])

_REGULAR_ROSTER_RE = re.compile(r"^(?:FA|SP|WI|SU)\d{2}$")
_SEASON_ORDER = {"WI": 0, "SP": 1, "SU": 2, "FA": 3}


def _roster_sort_key(slug: str) -> tuple[int, int, str]:
    s = slug.strip().upper()
    if len(s) == 4 and s[:2] in _SEASON_ORDER and s[2:].isdigit():
        return (int(s[2:]), _SEASON_ORDER[s[:2]], s)
    return (9999, 9, s)


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
    cs_requirement: Literal["", "cs_elective", "cs_project", "tech_elective", "external_spec"] = Query(default=""),
    include_2000_te: bool = Query(default=True),
    include_research_te: bool = Query(default=True),
    curriculum: Literal["current", "pre2024"] = Query(default="current"),
    ilr_codes: str = Query(default="", max_length=200),
    ilr_match: Literal["any", "all"] = Query(default="any"),
    ilr_multi_only: bool = Query(default=False),
    include_ilr: bool = Query(default=False),
    attrs: str = Query(default="", max_length=200),
    attr_match: Literal["any", "all"] = Query(default="any"),
    minor: str = Query(default="", max_length=40),
    minor_version: str = Query(default="", max_length=60),
    minor_categories: str = Query(default="", max_length=400),
    minor_completed: Optional[str] = Query(default=None, max_length=400),
    minor_hide_completed: Optional[bool] = Query(default=None),
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
    parsed_attrs = [c.strip().upper() for c in attrs.split(",") if c.strip()]
    minor_id = minor.strip().lower()
    user_minor_prefs = user.get("minor_prefs") or {}
    saved_versions = user_minor_prefs.get("versions") or {}
    saved_completed_map = user_minor_prefs.get("completed_categories") or {}

    resolved_minor_version = (
        minor_version.strip().lower()
        or str(saved_versions.get(minor_id) or "").strip().lower()
    )
    parsed_minor_categories = [
        c.strip().lower() for c in minor_categories.split(",") if c.strip()
    ]
    if minor_completed is not None:
        parsed_minor_completed = [
            c.strip().lower() for c in minor_completed.split(",") if c.strip()
        ]
    else:
        parsed_minor_completed = [
            str(c).strip().lower()
            for c in (saved_completed_map.get(minor_id) or [])
            if str(c).strip()
        ]
    effective_hide_completed = (
        bool(user_minor_prefs.get("hide_completed", True))
        if minor_hide_completed is None
        else bool(minor_hide_completed)
    )
    effective_include_ilr = (
        include_ilr
        or bool(parsed_ilr_codes)
        or ilr_multi_only
        or user.get("major_mode") == "ilr"
    )

    completed_courses = normalize_completed_courses(
        [
            *list(user.get("completed_courses") or []),
            *list(user.get("in_progress_courses") or []),
        ]
    )
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
        attrs=parsed_attrs,
        attr_match=attr_match,
        minor=minor_id,
        minor_version=resolved_minor_version,
        minor_categories=parsed_minor_categories,
        minor_completed_categories=parsed_minor_completed,
        minor_hide_completed=effective_hide_completed,
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


@router.get("/courses/attributes")
async def get_course_attribute_options(
    roster: Optional[str] = Query(default=None, min_length=3, max_length=10),
    _: dict[str, Any] = Depends(get_current_user),
    catalog: CatalogSyncService = Depends(get_catalog),
) -> dict[str, Any]:
    target_roster = (roster or await catalog.get_default_roster_slug()).upper()
    options = await catalog.get_attribute_options(target_roster)
    return {"roster": target_roster, "attributes": options}


@router.get("/minors/catalog")
async def get_minors_catalog(
    roster: Optional[str] = Query(default=None, min_length=3, max_length=10),
    user: dict[str, Any] = Depends(get_current_user),
    catalog: CatalogSyncService = Depends(get_catalog),
) -> dict[str, Any]:
    target_roster = (roster or await catalog.get_default_roster_slug()).upper()
    return await catalog.get_minors_catalog(
        target_roster,
        completed_courses=list(user.get("completed_courses") or []),
        in_progress_courses=list(user.get("in_progress_courses") or []),
    )


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
    course["crse_attrs"] = extract_course_attributes(course)
    course.pop("crse_attrs_json", None)
    drop_odds_map = await fetch_course_drop_odds_map(db, roster_u, [(subject_u, catalog_nbr)])
    course["drop_odds"] = drop_odds_map.get((subject_u, catalog_nbr))
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
    completed_set = set(completed)
    include_implied = (
        bool(user.get("include_implied_prereqs", True))
        if body.include_implied_prereqs is None
        else bool(body.include_implied_prereqs)
    )
    row_ip = await db.fetch_one(
        "SELECT in_progress_courses_json, in_progress_course_details_json FROM users WHERE id = ?",
        (user["id"],),
    )
    remaining_ip = [
        c
        for c in decode_completed_courses(row_ip.get("in_progress_courses_json") if row_ip else None)
        if c not in completed_set
    ]
    remaining_ip_set = set(remaining_ip)
    remaining_ip_details = {
        k: v
        for k, v in decode_completed_course_details(
            row_ip.get("in_progress_course_details_json") if row_ip else None
        ).items()
        if k in remaining_ip_set
    }
    async with db.write_tx() as conn:
        await conn.execute(
            """
            UPDATE users
            SET completed_courses_json = ?,
                in_progress_courses_json = ?,
                in_progress_course_details_json = ?,
                include_implied_prereqs = ?
            WHERE id = ?
            """,
            (
                json.dumps(completed),
                json.dumps(remaining_ip),
                json.dumps(remaining_ip_details),
                1 if include_implied else 0,
                user["id"],
            ),
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


@router.get("/cs/checklist")
async def get_cs_checklist(
    roster: Optional[str] = Query(default=None, min_length=3, max_length=10),
    user: dict[str, Any] = Depends(get_current_user),
    db: Database = Depends(get_db),
    catalog: CatalogSyncService = Depends(get_catalog),
) -> dict[str, Any]:
    target_roster = (roster or await catalog.get_default_roster_slug()).upper()
    cs_index = await catalog.get_cs_requirements_index(target_roster)
    payload = await build_cs_checklist_payload(
        db=db,
        user=user,
        cs_index=cs_index,
        roster=target_roster,
    )
    if payload.get("missing_metadata_courses"):
        catalog.queue_historical_course_lookup(payload["missing_metadata_courses"])
    return payload


@router.put("/cs/checklist")
async def update_cs_checklist(
    body: UpdateCsChecklistRequest,
    roster: Optional[str] = Query(default=None, min_length=3, max_length=10),
    user: dict[str, Any] = Depends(get_current_user),
    db: Database = Depends(get_db),
    catalog: CatalogSyncService = Depends(get_catalog),
) -> dict[str, Any]:
    target_roster = (roster or await catalog.get_default_roster_slug()).upper()
    row = await db.fetch_one(
        """
        SELECT completed_courses_json, completed_course_details_json,
               in_progress_courses_json, in_progress_course_details_json
        FROM users WHERE id = ?
        """,
        (user["id"],),
    )
    existing_completed = decode_completed_courses(row.get("completed_courses_json") if row else None)
    details_map = decode_completed_course_details(row.get("completed_course_details_json") if row else None)
    existing_in_progress = decode_completed_courses(row.get("in_progress_courses_json") if row else None)
    in_progress_details_map = decode_completed_course_details(
        row.get("in_progress_course_details_json") if row else None
    )

    completed_override: Optional[list[str]] = None
    active_completed_set = set(existing_completed)
    if body.sync_completed_courses is not None:
        completed_override = normalize_completed_courses(body.sync_completed_courses)
        active_completed_set = set(completed_override)

    in_progress_override: Optional[list[str]] = None
    if body.sync_in_progress_courses is not None:
        in_progress_override = [
            c
            for c in normalize_completed_courses(body.sync_in_progress_courses)
            if c not in active_completed_set
        ]
    elif completed_override is not None:
        filtered_ip = [c for c in existing_in_progress if c not in active_completed_set]
        if filtered_ip != existing_in_progress:
            in_progress_override = filtered_ip

    active_in_progress_set = set(
        in_progress_override if in_progress_override is not None else existing_in_progress
    )
    in_progress_details_map = {
        k: v for k, v in in_progress_details_map.items() if k in active_in_progress_set
    }

    # Persist manual {gr, sem, cr} edits on completed / currently-taking courses into details maps
    # so grades/terms stay attached across slot swaps and Re-auto-fill.
    for sl_val in body.slots.values():
        if sl_val.cleared:
            continue
        code = normalize_course_code(sl_val.course)
        if not code:
            continue
        cleaned_edit = normalize_course_detail(
            {"gr": sl_val.gr, "sem": sl_val.sem, "cr": sl_val.cr}
        )
        if not cleaned_edit:
            continue
        if code in active_completed_set:
            cur_det = dict(details_map.get(code) or {})
            for k, v in cleaned_edit.items():
                cur_det[k] = v
            details_map[code] = cur_det
        elif code in active_in_progress_set:
            cur_det = dict(in_progress_details_map.get(code) or {})
            for k, v in cleaned_edit.items():
                if k in {"sem", "cr"}:
                    cur_det[k] = v
            if cur_det:
                in_progress_details_map[code] = cur_det

    serialized = json.dumps(
        {
            "college": body.college,
            "curriculum": body.curriculum,
            "include_active_schedule": body.include_active_schedule,
            "pe_completed": body.pe_completed,
            "slots": {k: v.model_dump() for k, v in body.slots.items()},
        }
    )
    async with db.write_tx() as conn:
        await conn.execute(
            """
            UPDATE users
            SET cs_checklist_json = ?,
                completed_courses_json = ?,
                completed_course_details_json = ?,
                in_progress_courses_json = ?,
                in_progress_course_details_json = ?
            WHERE id = ?
            """,
            (
                serialized,
                json.dumps(completed_override if completed_override is not None else existing_completed),
                json.dumps(details_map),
                json.dumps(in_progress_override if in_progress_override is not None else existing_in_progress),
                json.dumps(in_progress_details_map),
                user["id"],
            ),
        )
    cs_index = await catalog.get_cs_requirements_index(target_roster)
    payload = await build_cs_checklist_payload(
        db=db,
        user=user,
        cs_index=cs_index,
        roster=target_roster,
        completed_courses_override=completed_override,
        completed_details_override=details_map,
        in_progress_courses_override=in_progress_override,
        in_progress_details_override=in_progress_details_map,
    )
    if payload.get("missing_metadata_courses"):
        catalog.queue_historical_course_lookup(payload["missing_metadata_courses"])
    return payload


@router.post("/cs/checklist/import-transcript")
async def import_transcript_to_checklist_and_scheduler(
    body: ImportTranscriptRequest,
    user: dict[str, Any] = Depends(get_current_user),
    db: Database = Depends(get_db),
    catalog: CatalogSyncService = Depends(get_catalog),
    scheduler: SchedulerService = Depends(get_scheduler),
) -> dict[str, Any]:
    """Merge privacy-stripped browser-parsed transcript courses into Checklist & Scheduler."""
    target_roster = (body.roster or await catalog.get_default_roster_slug()).upper()
    merge_result = await merge_transcript_into_user_checklist(
        db=db,
        user_id=int(user["id"]),
        imported_completed=[item.model_dump() for item in body.completed_courses],
        pe_completed=body.pe_completed,
        imported_in_progress=[item.model_dump() for item in body.in_progress_courses],
        sync_in_progress_to_checklist=body.sync_in_progress_to_checklist,
    )

    by_roster: dict[str, list[dict[str, str]]] = {}
    seen_roster_courses: dict[str, set[str]] = {}

    def _queue_for_scheduler(roster_slug: str, course_code: str, cr_val: str) -> None:
        r_u = roster_slug.strip().upper()
        c_u = normalize_course_code(course_code) or ""
        if not r_u or not c_u:
            return
        seen_set = seen_roster_courses.setdefault(r_u, set())
        if c_u in seen_set:
            return
        seen_set.add(c_u)
        by_roster.setdefault(r_u, []).append({"course": c_u, "cr": cr_val})

    for item in body.in_progress_courses:
        _queue_for_scheduler(item.roster, item.course, item.cr)

    past_by_roster: dict[str, list[dict[str, str]]] = {}
    if body.sync_completed_to_scheduler:
        known_rows = await db.fetch_all(
            "SELECT DISTINCT slug FROM rosters UNION SELECT DISTINCT roster AS slug FROM courses_meta"
        )
        known_rosters = {str(r["slug"]).strip().upper() for r in known_rows if r.get("slug")}

        for item in body.past_schedule_courses:
            r_u = item.roster.strip().upper()
            if _REGULAR_ROSTER_RE.match(r_u) and (not known_rosters or r_u in known_rosters):
                past_by_roster.setdefault(r_u, []).append({"course": item.course, "cr": item.cr})
        for item in body.completed_courses:
            sem_u = item.sem.strip().upper()
            if _REGULAR_ROSTER_RE.match(sem_u) and (not known_rosters or sem_u in known_rosters):
                past_by_roster.setdefault(sem_u, []).append({"course": item.course, "cr": item.cr})

        for r_u, items in past_by_roster.items():
            for entry in items:
                _queue_for_scheduler(r_u, entry["course"], entry["cr"])

    scheduler_results: list[dict[str, Any]] = []
    for r_slug in sorted(by_roster.keys(), key=_roster_sort_key):
        res = await scheduler.merge_imported_courses(
            user_id=int(user["id"]),
            roster=r_slug,
            courses=by_roster[r_slug],
        )
        scheduler_results.append(res)

    cs_index = await catalog.get_cs_requirements_index(target_roster)
    payload = await build_cs_checklist_payload(
        db=db,
        user=user,
        cs_index=cs_index,
        roster=target_roster,
        completed_courses_override=merge_result["completed_courses"],
        completed_details_override=merge_result["completed_course_details"],
        in_progress_courses_override=merge_result["in_progress_courses"],
        in_progress_details_override=merge_result["in_progress_course_details"],
    )
    if payload.get("missing_metadata_courses"):
        catalog.queue_historical_course_lookup(payload["missing_metadata_courses"])

    return {
        "checklist": payload,
        "import_summary": {
            "added_completed": merge_result["added_courses"],
            "added_in_progress": merge_result["added_in_progress"],
            "enriched_completed": merge_result["enriched_courses"],
            "unchanged_completed": merge_result["unchanged_courses"],
            "enriched_slots": merge_result["enriched_slots"],
            "pe_completed": merge_result["pe_completed"],
            "scheduler": scheduler_results,
        },
    }
