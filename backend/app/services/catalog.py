"""Local Cornell roster/course catalog synchronization, CS requirement search, and lazy refresh."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator, Optional

import orjson

from app.db import Database, build_fts_query
from app.providers.base import AvailabilityProvider, CourseRecord, RateLimitedError, UpstreamUnavailableError
from app.providers.cornell import compute_course_derived_fields
from app.services.cs_requirements import (
    PRIORITY_STEM_SUBJECTS,
    CourseEligibility,
    CSRequirementsIndex,
)
from app.services.gate import PRIORITY_SEARCH, PRIORITY_WARMUP, CornellRequestGate
from app.services.insights import build_external_links
from app.services.sse import SSEHub

logger = logging.getLogger("classsniper.catalog")

SUBJECT_PREFIX_RE = re.compile(r"^\s*([A-Za-z]{2,8})(?:[\s\-:]*\d.*)?$")
_ALPHA_DIGIT_BOUNDARY_RE = re.compile(r"([A-Za-z])(\d)")

# Visible search results whose subject was synced/polled more recently than 120s show live status immediately.
STATUS_FRESHNESS_SEC = 120.0
INLINE_UNCACHED_HYDRATE_CAP = 3
VISIBLE_STALE_REFRESH_CAP = 10


def normalize_search_query(raw_query: str) -> str:
    """Split alpha/digit boundaries like 'cs2110' into 'cs 2110' for FTS5 matching."""
    return _ALPHA_DIGIT_BOUNDARY_RE.sub(r"\1 \2", raw_query.strip())


def _escape_like(token: str) -> str:
    return token.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _parse_utc_dt(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.strip())
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _decode_json_list(raw: Any) -> list[Any]:
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str) and raw:
        try:
            loaded = json.loads(raw)
            if isinstance(loaded, list):
                return loaded
        except ValueError:
            pass
    return []


class CatalogSyncService:
    """Maintains cached rosters, subjects, courses, CS eligibility index, and lazy live refreshes."""

    def __init__(
        self,
        db: Database,
        provider: AvailabilityProvider,
        sync_interval_hours: float = 12.0,
        gate: Optional[CornellRequestGate] = None,
        sse_hub: Optional[SSEHub] = None,
    ) -> None:
        self.db = db
        self.provider = provider
        self.sync_interval_hours = sync_interval_hours
        self.gate = gate
        self.sse_hub = sse_hub
        self._poller: Optional[Any] = None

        self._subject_locks: dict[tuple[str, str], asyncio.Lock] = {}
        self._bg_sync_lock = asyncio.Lock()
        self._catalog_generation: dict[str, int] = {}
        self._cs_index_cache: dict[str, tuple[int, CSRequirementsIndex]] = {}

        self._refresh_queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue(maxsize=200)
        self._refresh_pending: set[tuple[str, str]] = set()
        self._stop_event = asyncio.Event()
        self._refresh_worker_task: Optional[asyncio.Task[None]] = None
        self._warmup_worker_task: Optional[asyncio.Task[None]] = None

        self.status: dict[str, Any] = {
            "in_progress": False,
            "warmup_active": False,
            "last_sync_at": None,
            "last_error": None,
            "rosters_count": 0,
        }

    def set_poller(self, poller: Any) -> None:
        self._poller = poller

    def set_sse_hub(self, sse_hub: SSEHub) -> None:
        self.sse_hub = sse_hub

    def start_workers(self) -> None:
        """Start lazy visible-subject refresh consumer and STEM-first background warmer."""
        self._stop_event.clear()
        if self._refresh_worker_task is None or self._refresh_worker_task.done():
            self._refresh_worker_task = asyncio.create_task(
                self._refresh_worker_loop(),
                name="catalog-visible-refresh",
            )
        if self._warmup_worker_task is None or self._warmup_worker_task.done():
            self._warmup_worker_task = asyncio.create_task(
                self._warmup_worker_loop(),
                name="catalog-stem-warmup",
            )

    async def stop_workers(self) -> None:
        self._stop_event.set()
        for task in (self._refresh_worker_task, self._warmup_worker_task):
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._refresh_worker_task = None
        self._warmup_worker_task = None

    def _get_subject_lock(self, roster: str, subject: str) -> asyncio.Lock:
        key = (roster.upper(), subject.upper())
        lock = self._subject_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._subject_locks[key] = lock
        return lock

    @asynccontextmanager
    async def _acquire_fetch_slot(self, priority: int, min_interval_sec: float) -> AsyncIterator[None]:
        if self.gate is None:
            yield
        else:
            async with self.gate.slot(priority=priority, min_interval_sec=min_interval_sec, honor_backoff=True):
                yield

    async def sync_rosters_and_subjects(self, roster_filter: Optional[str] = None) -> list[str]:
        """Fetch rosters and subject lists for non-archived rosters."""
        rosters = await self.provider.fetch_rosters()
        active_rosters: list[str] = []

        async with self.db.write_tx() as conn:
            for r in rosters:
                await conn.execute(
                    """
                    INSERT INTO rosters (slug, descr, is_default, archive_mode, strm, last_modified_dttm, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                    ON CONFLICT(slug) DO UPDATE SET
                        descr = excluded.descr,
                        is_default = excluded.is_default,
                        archive_mode = excluded.archive_mode,
                        strm = excluded.strm,
                        last_modified_dttm = excluded.last_modified_dttm,
                        updated_at = datetime('now')
                    """,
                    (
                        r.slug,
                        r.descr,
                        1 if r.is_default else 0,
                        1 if r.archive_mode else 0,
                        r.strm,
                        r.last_modified_dttm,
                    ),
                )
                if not r.archive_mode or r.is_default:
                    active_rosters.append(r.slug)

        target_rosters = [roster_filter.upper()] if roster_filter else (active_rosters or [r.slug for r in rosters[-2:]])
        for slug in target_rosters:
            subjects = await self.provider.fetch_subjects(slug)
            async with self.db.write_tx() as conn:
                for s in subjects:
                    await conn.execute(
                        """
                        INSERT INTO subjects (roster, value, descr)
                        VALUES (?, ?, ?)
                        ON CONFLICT(roster, value) DO UPDATE SET
                            descr = excluded.descr
                        """,
                        (slug, s.value, s.descr),
                    )

        self.status["rosters_count"] = len(rosters)
        self.status["last_sync_at"] = datetime.now(timezone.utc).isoformat()
        self.status["last_error"] = None
        return target_rosters

    async def upsert_courses_batch(
        self,
        roster: str,
        subject: str,
        courses: list[CourseRecord],
    ) -> None:
        """Persist full course metadata, sections, and FTS5 rows for a (roster, subject)."""
        roster_u = roster.upper()
        subject_u = subject.upper()

        async with self.db.write_tx() as conn:
            await conn.execute(
                "DELETE FROM courses_fts WHERE roster = ? AND subject = ?",
                (roster_u, subject_u),
            )
            await conn.execute(
                "DELETE FROM roster_sections WHERE roster = ? AND subject = ?",
                (roster_u, subject_u),
            )
            await conn.execute(
                "DELETE FROM courses_meta WHERE roster = ? AND subject = ?",
                (roster_u, subject_u),
            )

            for c in courses:
                derived = compute_course_derived_fields(c.catalog_nbr, c.enroll_groups, c.sections)
                catalog_num = c.catalog_num or derived["catalog_num"]
                units_min = c.units_min if (c.units_min or c.units_max) else derived["units_min"]
                units_max = c.units_max if (c.units_min or c.units_max) else derived["units_max"]
                has_letter = c.has_letter_grade if c.enroll_groups else True
                if c.enroll_groups:
                    has_letter = derived["has_letter_grade"] and c.has_letter_grade
                crosslists = c.crosslists or derived["crosslists"]
                components = c.components or derived["components"]

                eg_json = orjson.dumps(c.enroll_groups).decode("utf-8")
                crse_attrs_json = orjson.dumps(c.crse_attrs).decode("utf-8")
                crosslists_json = json.dumps(crosslists)
                components_json = json.dumps(components)

                await conn.execute(
                    """
                    INSERT INTO courses_meta (
                        roster, subject, catalog_nbr, title_short, title_long,
                        description, crse_id, acad_career, acad_group,
                        catalog_prereq, catalog_coreq, catalog_forbidden_overlaps,
                        crse_attrs_json, catalog_num, units_min, units_max,
                        has_letter_grade, crosslists_json, components_json,
                        enroll_groups_json, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                    """,
                    (
                        roster_u,
                        c.subject,
                        c.catalog_nbr,
                        c.title_short,
                        c.title_long,
                        c.description,
                        c.crse_id,
                        c.acad_career,
                        c.acad_group,
                        c.catalog_prereq,
                        c.catalog_coreq,
                        c.catalog_forbidden_overlaps,
                        crse_attrs_json,
                        catalog_num,
                        units_min,
                        units_max,
                        1 if has_letter else 0,
                        crosslists_json,
                        components_json,
                        eg_json,
                    ),
                )

                class_nbrs_tokens: list[str] = []
                for sec in c.sections:
                    class_nbrs_tokens.append(str(sec.class_nbr))
                    await conn.execute(
                        """
                        INSERT INTO roster_sections (
                            roster, subject, catalog_nbr, class_nbr, enroll_group_idx,
                            ssr_component, section, open_status, components_required_json,
                            meetings_summary, instructors_summary, campus, instruction_mode, updated_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                        """,
                        (
                            roster_u,
                            c.subject,
                            c.catalog_nbr,
                            sec.class_nbr,
                            sec.enroll_group_idx,
                            sec.ssr_component,
                            sec.section,
                            sec.open_status,
                            json.dumps(sec.components_required),
                            sec.meetings_summary,
                            sec.instructors_summary,
                            sec.campus,
                            sec.instruction_mode,
                        ),
                    )

                await conn.execute(
                    """
                    INSERT INTO courses_fts (
                        roster, subject, catalog_nbr, course_code, title_long, description, class_nbrs
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        roster_u,
                        c.subject,
                        c.catalog_nbr,
                        f"{c.subject} {c.catalog_nbr}",
                        c.title_long,
                        c.description,
                        " ".join(class_nbrs_tokens),
                    ),
                )

            await conn.execute(
                """
                INSERT INTO subjects (roster, value, descr, synced_at)
                VALUES (?, ?, ?, datetime('now'))
                ON CONFLICT(roster, value) DO UPDATE SET
                    synced_at = datetime('now')
                """,
                (roster_u, subject_u, subject_u),
            )

        self._catalog_generation[roster_u] = self._catalog_generation.get(roster_u, 0) + 1
        self._cs_index_cache.pop(roster_u, None)

    async def update_section_statuses(
        self,
        roster: str,
        changed_sections: list[tuple[int, str]],
    ) -> None:
        """Fast incremental update of open_status for sections whose state changed during polling."""
        if not changed_sections:
            return
        roster_u = roster.upper()
        async with self.db.write_tx() as conn:
            for class_nbr, new_status in changed_sections:
                await conn.execute(
                    """
                    UPDATE roster_sections
                    SET open_status = ?, updated_at = datetime('now')
                    WHERE roster = ? AND class_nbr = ?
                    """,
                    (new_status, roster_u, class_nbr),
                )

    async def is_subject_stale(
        self,
        roster: str,
        subject: str,
        max_age_hours: Optional[float] = None,
        max_age_seconds: Optional[float] = None,
    ) -> bool:
        row = await self.db.fetch_one(
            "SELECT synced_at FROM subjects WHERE roster = ? AND value = ?",
            (roster.upper(), subject.upper()),
        )
        if row is None or not row["synced_at"]:
            return True
        synced_dt = _parse_utc_dt(row["synced_at"])
        if synced_dt is None:
            return True
        delta = timedelta(seconds=max_age_seconds) if max_age_seconds is not None else timedelta(
            hours=(max_age_hours if max_age_hours is not None else self.sync_interval_hours)
        )
        return datetime.now(timezone.utc) - synced_dt > delta

    async def _subject_is_never_synced(self, roster: str, subject: str) -> bool:
        row = await self.db.fetch_one(
            "SELECT synced_at FROM subjects WHERE roster = ? AND value = ?",
            (roster.upper(), subject.upper()),
        )
        return row is None or not row["synced_at"]

    async def ensure_subject_synced(
        self,
        roster: str,
        subject: str,
        force: bool = False,
        priority: int = PRIORITY_SEARCH,
        min_interval_sec: float = 0.0,
        emit_sse: bool = False,
    ) -> bool:
        """Fetch and index a single (roster, subject) if missing or stale. Returns True if fetched."""
        roster_u = roster.upper()
        subject_u = subject.upper()
        lock = self._get_subject_lock(roster_u, subject_u)
        async with lock:
            if not force and not await self.is_subject_stale(roster_u, subject_u):
                return False
            try:
                async with self._acquire_fetch_slot(priority=priority, min_interval_sec=min_interval_sec):
                    result = await self.provider.fetch_subject_classes(roster_u, subject_u)
            except RateLimitedError as exc:
                if self.gate is not None:
                    self.gate.record_rate_limit(exc.retry_after_sec)
                raise

            await self.upsert_courses_batch(roster_u, subject_u, result.courses)

            if emit_sse and self.sse_hub is not None:
                now_iso = datetime.now(timezone.utc).isoformat()
                coverage = await self.get_catalog_status(roster_u)
                self.sse_hub.publish(
                    "catalog_subject_refreshed",
                    {
                        "roster": roster_u,
                        "subject": subject_u,
                        "synced_at": now_iso,
                        "courses_count": len(result.courses),
                        "section_statuses": {
                            str(sec.class_nbr): sec.open_status
                            for c in result.courses
                            for sec in c.sections
                        },
                        "coverage": {
                            "synced_subjects": coverage["synced_subjects"],
                            "total_subjects": coverage["total_subjects"],
                            "stem_synced": coverage["stem_synced"],
                            "stem_total": coverage["stem_total"],
                        },
                    },
                )
            return True

    def queue_visible_refresh(self, roster: str, subjects: list[str]) -> list[str]:
        """Enqueue stale/uncached subjects from search results for gentle SSE live refresh."""
        roster_u = roster.upper()
        queued: list[str] = []
        for raw_subj in subjects:
            subj_u = raw_subj.strip().upper()
            if not subj_u:
                continue
            key = (roster_u, subj_u)
            if key in self._refresh_pending:
                continue
            if self._refresh_queue.full():
                break
            self._refresh_pending.add(key)
            self._refresh_queue.put_nowait(key)
            queued.append(subj_u)
        return queued

    async def process_one_refresh(self, timeout_sec: float = 0.2) -> Optional[tuple[str, str]]:
        """Process at most one queued visible-subject refresh (used by worker loop & deterministic tests)."""
        try:
            roster_u, subject_u = await asyncio.wait_for(self._refresh_queue.get(), timeout=timeout_sec)
        except asyncio.TimeoutError:
            return None

        try:
            is_fresh, _ = await self._get_subject_freshness(roster_u, subject_u)
            if not is_fresh:
                await self.ensure_subject_synced(
                    roster_u,
                    subject_u,
                    force=True,
                    priority=PRIORITY_SEARCH,
                    min_interval_sec=1.15,
                    emit_sse=True,
                )
        except (RateLimitedError, UpstreamUnavailableError) as exc:
            logger.debug("Lazy subject refresh skipped for %s %s: %s", roster_u, subject_u, exc)
        except Exception as exc:
            logger.warning("Lazy subject refresh error for %s %s: %s", roster_u, subject_u, exc)
        finally:
            self._refresh_pending.discard((roster_u, subject_u))
            self._refresh_queue.task_done()
        return (roster_u, subject_u)

    async def _refresh_worker_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self.process_one_refresh(timeout_sec=1.0)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Refresh worker loop error: %s", exc)
                await asyncio.sleep(1.0)

    def _ordered_warmup_subjects(self, subject_rows: list[dict[str, Any]]) -> list[str]:
        """Prioritize ~26 STEM & CS-adjacent subjects first so TE/CS filters work quickly."""
        by_val = {str(r["value"]).upper(): r for r in subject_rows}
        ordered: list[str] = []
        seen: set[str] = set()
        for stem_subj in PRIORITY_STEM_SUBJECTS:
            if stem_subj in by_val and stem_subj not in seen:
                ordered.append(stem_subj)
                seen.add(stem_subj)
        for r in subject_rows:
            val = str(r["value"]).upper()
            if val not in seen:
                ordered.append(val)
                seen.add(val)
        return ordered

    async def warm_up_roster_once(self, roster: str) -> int:
        """Warm uncached or expired catalog subjects STEM-first at PRIORITY_WARMUP, yielding to PollerEngine."""
        roster_u = roster.upper()
        self.status["warmup_active"] = True
        synced = 0
        try:
            rows = await self.db.fetch_all(
                "SELECT value, synced_at FROM subjects WHERE roster = ? ORDER BY value ASC",
                (roster_u,),
            )
            if not rows:
                await self.sync_rosters_and_subjects(roster_u)
                rows = await self.db.fetch_all(
                    "SELECT value, synced_at FROM subjects WHERE roster = ? ORDER BY value ASC",
                    (roster_u,),
                )
            stale_map = {}
            for r in rows:
                val = str(r["value"]).upper()
                stale_map[val] = await self.is_subject_stale(roster_u, val)

            ordered = [s for s in self._ordered_warmup_subjects(rows) if stale_map.get(s)]
            for subj in ordered:
                if self._stop_event.is_set():
                    break
                # Wait briefly while active visible-subject searches are ahead of background warm-up
                while not self._refresh_queue.empty() and not self._stop_event.is_set():
                    await asyncio.sleep(0.5)
                if self.gate is not None and self.gate.has_active_poller():
                    # Active watches take priority: pause/trickle politely at 12s intervals instead of competing
                    await asyncio.sleep(12.0)
                try:
                    did_sync = await self.ensure_subject_synced(
                        roster_u,
                        subj,
                        force=False,
                        priority=PRIORITY_WARMUP,
                        min_interval_sec=1.25,
                        emit_sse=True,
                    )
                    if did_sync:
                        synced += 1
                except RateLimitedError:
                    await asyncio.sleep(15.0)
                except UpstreamUnavailableError:
                    await asyncio.sleep(5.0)
                await asyncio.sleep(0.25 if not (self.gate and self.gate.has_active_poller()) else 2.0)
        finally:
            self.status["warmup_active"] = False
        return synced

    async def _warmup_worker_loop(self) -> None:
        # Let uvicorn & initial user requests settle for 2s before starting background warm-up
        await asyncio.sleep(2.0)
        while not self._stop_event.is_set():
            try:
                default_roster = await self.get_default_roster_slug()
                await self.warm_up_roster_once(default_roster)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Background catalog warm-up error: %s", exc)
            # Re-check periodically in case new offerings expire (>12h) or roster updates
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=300.0)
            except asyncio.TimeoutError:
                continue

    async def sync_full_roster(self, roster: str, delay_sec: float = 1.15) -> int:
        """Sequentially sync every subject for a roster while respecting Cornell's <= 1 req/s rate limit."""
        if self._bg_sync_lock.locked():
            return 0
        async with self._bg_sync_lock:
            self.status["in_progress"] = True
            self.status["last_error"] = None
            synced = 0
            try:
                roster_u = roster.upper()
                subjects = await self.db.fetch_all(
                    "SELECT value FROM subjects WHERE roster = ? ORDER BY value ASC",
                    (roster_u,),
                )
                if not subjects:
                    await self.sync_rosters_and_subjects(roster_u)
                    subjects = await self.db.fetch_all(
                        "SELECT value FROM subjects WHERE roster = ? ORDER BY value ASC",
                        (roster_u,),
                    )

                for idx, row in enumerate(subjects):
                    if await self.ensure_subject_synced(
                        roster_u,
                        row["value"],
                        force=False,
                        priority=PRIORITY_WARMUP,
                        min_interval_sec=delay_sec,
                        emit_sse=True,
                    ):
                        synced += 1
                        if idx < len(subjects) - 1 and self.gate is None:
                            await asyncio.sleep(delay_sec)
                self.status["last_sync_at"] = datetime.now(timezone.utc).isoformat()
            except Exception as exc:
                self.status["last_error"] = str(exc)
                raise
            finally:
                self.status["in_progress"] = False
            return synced

    async def get_default_roster_slug(self) -> str:
        row = await self.db.fetch_one(
            "SELECT slug FROM rosters ORDER BY is_default DESC, archive_mode ASC, strm DESC LIMIT 1"
        )
        return row["slug"] if row else "SP27"

    async def get_catalog_status(self, roster: str) -> dict[str, Any]:
        roster_u = roster.upper()
        rows = await self.db.fetch_all(
            "SELECT value, synced_at FROM subjects WHERE roster = ?",
            (roster_u,),
        )
        total_subjects = len(rows)
        synced_subjects = sum(1 for r in rows if r["synced_at"])
        stem_set = set(PRIORITY_STEM_SUBJECTS)
        stem_rows = [r for r in rows if str(r["value"]).upper() in stem_set]
        stem_total = len(stem_rows) if stem_rows else len(PRIORITY_STEM_SUBJECTS)
        stem_synced = sum(1 for r in stem_rows if r["synced_at"])
        return {
            "roster": roster_u,
            "synced_subjects": synced_subjects,
            "total_subjects": total_subjects,
            "stem_synced": stem_synced,
            "stem_total": stem_total,
            "warmup_active": bool(self.status.get("warmup_active")),
            "refreshing_subjects": sorted(s for r, s in self._refresh_pending if r == roster_u),
        }

    async def _get_subject_freshness(self, roster_u: str, subject_u: str) -> tuple[bool, Optional[str]]:
        """Return (is_fresh, effective_synced_at_iso) using subjects.synced_at and live poller bucket."""
        row = await self.db.fetch_one(
            "SELECT synced_at FROM subjects WHERE roster = ? AND value = ?",
            (roster_u, subject_u),
        )
        subj_dt = _parse_utc_dt(row["synced_at"]) if row else None
        poll_iso = self._poller.get_bucket_last_polled_at(roster_u, subject_u) if self._poller else None
        poll_dt = _parse_utc_dt(poll_iso)

        best_dt: Optional[datetime] = None
        if subj_dt and poll_dt:
            best_dt = max(subj_dt, poll_dt)
        else:
            best_dt = subj_dt or poll_dt

        if best_dt is None:
            return False, None
        age_sec = (datetime.now(timezone.utc) - best_dt).total_seconds()
        return age_sec <= STATUS_FRESHNESS_SEC, best_dt.isoformat()

    async def get_cs_requirements_index(self, roster: str) -> CSRequirementsIndex:
        """Build or return cached CSRequirementsIndex over all cached courses for a roster."""
        roster_u = roster.upper()
        gen = self._catalog_generation.get(roster_u, 0)
        cached = self._cs_index_cache.get(roster_u)
        if cached is not None and cached[0] == gen:
            return cached[1]

        rows = await self.db.fetch_all(
            """
            SELECT subject, catalog_nbr, title_short, title_long,
                   acad_career, acad_group, catalog_prereq, catalog_coreq,
                   catalog_num, units_min, units_max, has_letter_grade,
                   crosslists_json, components_json, enroll_groups_json
            FROM courses_meta
            WHERE roster = ?
            """,
            (roster_u,),
        )
        index = CSRequirementsIndex(rows)
        self._cs_index_cache[roster_u] = (gen, index)
        return index

    def _matches_requirement_filter(
        self,
        elig: CourseEligibility,
        cs_requirement: str,
        include_2000_te: bool,
        include_research_te: bool,
        curriculum: str,
    ) -> bool:
        if not cs_requirement:
            return True
        if cs_requirement == "cs_elective":
            return elig.cs_elective_pre2024 if curriculum == "pre2024" else elig.cs_elective
        if cs_requirement == "tech_elective":
            if not elig.tech_elective:
                return False
            if elig.tech_elective_is_2000 and not include_2000_te:
                return False
            if elig.tech_elective_is_research and not include_research_te:
                return False
            return True
        if cs_requirement == "external_spec":
            return elig.external_spec
        return True

    def _sort_courses(
        self,
        rows: list[dict[str, Any]],
        cs_index: CSRequirementsIndex,
        cs_requirement: str,
        has_query: bool,
    ) -> list[dict[str, Any]]:
        if has_query:
            return rows

        def sort_key(row: dict[str, Any]) -> tuple[int, str, int, str]:
            subj = str(row["subject"])
            nbr = str(row["catalog_nbr"])
            cat_num = int(row.get("catalog_num") or 0)
            elig = cs_index.get(subj, nbr)
            tier = 0
            if cs_requirement == "cs_elective":
                if 4000 <= cat_num < 5000:
                    tier = 0
                elif cat_num < 4000:
                    tier = 1
                else:
                    tier = 2
            elif cs_requirement == "tech_elective":
                if elig.tech_elective_is_research:
                    tier = 3
                elif elig.tech_elective_is_2000:
                    tier = 2
                elif elig.tech_elective_warning:
                    tier = 1
                else:
                    tier = 0
            return (tier, subj, cat_num, nbr)

        return sorted(rows, key=sort_key)

    async def search_courses_advanced(
        self,
        roster: str,
        query: str = "",
        subjects: Optional[list[str]] = None,
        level_min: Optional[int] = None,
        min_credits: Optional[float] = None,
        cs_requirement: str = "",
        include_2000_te: bool = True,
        include_research_te: bool = True,
        curriculum: str = "current",
        refresh_stale: bool = True,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Instant local FTS5 + CS eligibility search with polite lazy SSE status refresh."""
        roster_u = roster.upper()
        subject_list: list[str] = []
        seen_subjs: set[str] = set()
        for s in subjects or []:
            su = s.strip().upper()
            if su and su not in seen_subjs:
                seen_subjs.add(su)
                subject_list.append(su)

        query_clean = normalize_search_query(query)
        req_mode = cs_requirement.strip().lower()
        curriculum_mode = "pre2024" if curriculum == "pre2024" else "current"

        # Hydrate up to INLINE_UNCACHED_HYDRATE_CAP never-synced subjects that are explicitly targeted
        targets_to_check: list[str] = list(subject_list)
        if not targets_to_check and query_clean:
            match = SUBJECT_PREFIX_RE.match(query_clean)
            if match:
                maybe_subj = match.group(1).upper()
                has_subjects = await self.db.fetch_one(
                    "SELECT value FROM subjects WHERE roster = ? LIMIT 1",
                    (roster_u,),
                )
                if not has_subjects:
                    try:
                        await self.sync_rosters_and_subjects(roster_u)
                    except Exception:
                        pass
                exists = await self.db.fetch_one(
                    "SELECT value FROM subjects WHERE roster = ? AND value = ?",
                    (roster_u, maybe_subj),
                )
                if exists:
                    targets_to_check = [maybe_subj]

        if req_mode == "cs_elective" and not targets_to_check:
            targets_to_check = ["CS"]
        elif req_mode == "tech_elective" and not targets_to_check:
            targets_to_check = ["CS"]

        inline_hydrated = 0
        overflow_uncached: list[str] = []
        for target_subj in targets_to_check:
            try:
                if await self._subject_is_never_synced(roster_u, target_subj):
                    if inline_hydrated < INLINE_UNCACHED_HYDRATE_CAP:
                        await self.ensure_subject_synced(
                            roster_u,
                            target_subj,
                            priority=PRIORITY_SEARCH,
                            min_interval_sec=0.0 if inline_hydrated == 0 else 0.8,
                        )
                        inline_hydrated += 1
                    else:
                        overflow_uncached.append(target_subj)
            except Exception:
                # If offline or upstream transient error, continue gracefully with cached DB rows
                pass

        # Ensure minimum level defaults make sense when explicitly not overridden
        effective_level_min = level_min
        if req_mode == "external_spec" and (effective_level_min is None or effective_level_min < 3000):
            effective_level_min = 3000

        fts_expr = build_fts_query(query_clean)
        sql_limit = 4500 if req_mode else max(limit, 200)

        where_extra: list[str] = []
        extra_params: list[Any] = []
        if subject_list:
            qmarks = ", ".join("?" for _ in subject_list)
            where_extra.append(f"cm.subject IN ({qmarks})")
            extra_params.extend(subject_list)
        if effective_level_min is not None and effective_level_min > 0:
            where_extra.append("cm.catalog_num >= ?")
            extra_params.append(int(effective_level_min))
        if min_credits is not None and min_credits > 0:
            where_extra.append("(cm.units_max = 0 OR cm.units_max >= ?)")
            extra_params.append(float(min_credits))

        extra_sql = (" AND " + " AND ".join(where_extra)) if where_extra else ""
        select_cols = """
            cm.roster, cm.subject, cm.catalog_nbr, cm.title_short, cm.title_long,
            cm.description, cm.acad_career, cm.acad_group,
            cm.catalog_prereq, cm.catalog_coreq, cm.catalog_forbidden_overlaps,
            cm.catalog_num, cm.units_min, cm.units_max, cm.has_letter_grade,
            cm.crosslists_json, cm.components_json, cm.updated_at
        """

        if fts_expr:
            sql = f"""
                SELECT {select_cols}
                FROM courses_fts
                JOIN courses_meta cm
                  ON cm.roster = courses_fts.roster
                 AND cm.subject = courses_fts.subject
                 AND cm.catalog_nbr = courses_fts.catalog_nbr
                WHERE courses_fts MATCH ?
                  AND courses_fts.roster = ?
                  {extra_sql}
                ORDER BY rank, cm.subject, cm.catalog_num, cm.catalog_nbr
                LIMIT ?
            """
            params: list[Any] = [fts_expr, roster_u, *extra_params, sql_limit]
        else:
            sql = f"""
                SELECT {select_cols}
                FROM courses_meta cm
                WHERE cm.roster = ?
                  {extra_sql}
                ORDER BY cm.subject, cm.catalog_num, cm.catalog_nbr
                LIMIT ?
            """
            params = [roster_u, *extra_params, sql_limit]

        courses = await self.db.fetch_all(sql, params)

        # Also match cached section instructors (e.g. "Clarkson", "Tani", "CS Tani")
        tokens = [t.lower() for t in re.findall(r"[A-Za-z0-9]+", query_clean)]
        if tokens and len(courses) < sql_limit:
            seen_keys = {(c["subject"], c["catalog_nbr"]) for c in courses}
            inst_clauses = ["cm.roster = ?", *where_extra]
            inst_params: list[Any] = [roster_u, *extra_params]
            for tok in tokens[:5]:
                inst_clauses.append(
                    "LOWER(cm.subject || ' ' || cm.catalog_nbr || ' ' || cm.title_long || ' ' || rs.instructors_summary) LIKE ? ESCAPE '\\'"
                )
                inst_params.append(f"%{_escape_like(tok)}%")

            inst_params.append(sql_limit)
            extra = await self.db.fetch_all(
                f"""
                SELECT DISTINCT {select_cols}
                FROM courses_meta cm
                JOIN roster_sections rs
                  ON rs.roster = cm.roster
                 AND rs.subject = cm.subject
                 AND rs.catalog_nbr = cm.catalog_nbr
                WHERE {' AND '.join(inst_clauses)}
                ORDER BY cm.subject, cm.catalog_num, cm.catalog_nbr
                LIMIT ?
                """,
                inst_params,
            )
            for row in extra:
                key = (row["subject"], row["catalog_nbr"])
                if key not in seen_keys:
                    seen_keys.add(key)
                    courses.append(row)
                    if len(courses) >= sql_limit:
                        break

        cs_index = await self.get_cs_requirements_index(roster_u)

        if req_mode:
            courses = [
                c
                for c in courses
                if self._matches_requirement_filter(
                    elig=cs_index.get(c["subject"], c["catalog_nbr"]),
                    cs_requirement=req_mode,
                    include_2000_te=include_2000_te,
                    include_research_te=include_research_te,
                    curriculum=curriculum_mode,
                )
            ]

        courses = self._sort_courses(
            courses,
            cs_index=cs_index,
            cs_requirement=req_mode,
            has_query=bool(fts_expr),
        )
        total_matched = len(courses)
        courses = courses[:limit]

        # Batch fetch sections & annotate freshness + CS eligibility
        if courses:
            keys = [(c["subject"], c["catalog_nbr"]) for c in courses]
            sec_by_course: dict[tuple[str, str], list[dict[str, Any]]] = {}
            # Chunk keys cleanly to stay comfortably within SQLite parameter limit
            for start in range(0, len(keys), 150):
                chunk = keys[start : start + 150]
                placeholders = " OR ".join("(subject = ? AND catalog_nbr = ?)" for _ in chunk)
                sec_params: list[Any] = [roster_u]
                for subj, cat in chunk:
                    sec_params.extend([subj, cat])

                sections = await self.db.fetch_all(
                    f"""
                    SELECT subject, catalog_nbr, class_nbr, enroll_group_idx, ssr_component, section,
                           open_status, components_required_json, meetings_summary,
                           instructors_summary, campus, instruction_mode
                    FROM roster_sections
                    WHERE roster = ? AND ({placeholders})
                    ORDER BY enroll_group_idx ASC, class_nbr ASC
                    """,
                    sec_params,
                )
                for sec in sections:
                    sec["components_required"] = json.loads(sec.pop("components_required_json", "[]"))
                    sec_by_course.setdefault((sec["subject"], sec["catalog_nbr"]), []).append(sec)
        else:
            sec_by_course = {}

        # Compute freshness once per visible subject
        visible_subjects: list[str] = []
        seen_vis: set[str] = set()
        for c in courses:
            su = str(c["subject"]).upper()
            if su not in seen_vis:
                seen_vis.add(su)
                visible_subjects.append(su)

        freshness_by_subj: dict[str, tuple[bool, Optional[str]]] = {}
        stale_visible_subjects: list[str] = []
        for su in visible_subjects:
            is_fresh, eff_iso = await self._get_subject_freshness(roster_u, su)
            freshness_by_subj[su] = (is_fresh, eff_iso)
            if not is_fresh:
                stale_visible_subjects.append(su)

        for c in courses:
            su = str(c["subject"]).upper()
            nbr = str(c["catalog_nbr"])
            is_fresh, eff_iso = freshness_by_subj.get(su, (False, None))
            c["crosslists"] = _decode_json_list(c.pop("crosslists_json", "[]"))
            c["components"] = _decode_json_list(c.pop("components_json", "[]"))
            c["has_letter_grade"] = bool(c.get("has_letter_grade", 1))
            c["sections"] = sec_by_course.get((su, nbr), [])
            c["external_links"] = build_external_links(c["roster"], su, nbr)
            c["cs_eligibility"] = cs_index.get(su, nbr).to_dict()
            c["subject_synced_at"] = eff_iso
            c["status_is_stale"] = not is_fresh

        queued_subjects: list[str] = []
        if refresh_stale:
            to_queue: list[str] = list(overflow_uncached)
            for s in stale_visible_subjects:
                if s not in to_queue:
                    to_queue.append(s)
            cap = max(VISIBLE_STALE_REFRESH_CAP, len(subject_list)) if subject_list else VISIBLE_STALE_REFRESH_CAP
            if to_queue:
                queued_subjects = self.queue_visible_refresh(roster_u, to_queue[:cap])

        coverage = await self.get_catalog_status(roster_u)
        return {
            "courses": courses,
            "meta": {
                "total_matched": total_matched,
                "returned": len(courses),
                "queued_subjects": queued_subjects,
                "synced_subjects": coverage["synced_subjects"],
                "total_subjects": coverage["total_subjects"],
                "stem_synced": coverage["stem_synced"],
                "stem_total": coverage["stem_total"],
                "refreshing_subjects": coverage["refreshing_subjects"],
                "warmup_active": coverage["warmup_active"],
            },
        }

    async def search_courses(
        self,
        roster: str,
        query: str = "",
        subject: str = "",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Backwards-compatible search returning only the matching courses list."""
        res = await self.search_courses_advanced(
            roster=roster,
            query=query,
            subjects=[subject] if subject.strip() else None,
            limit=limit,
        )
        return res["courses"]
