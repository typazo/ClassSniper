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
from app.providers.cornell import compute_course_derived_fields, is_ithaca_or_virtual_section
from app.services.attributes import (
    course_matches_attrs,
    extract_course_attributes,
    normalize_attr_code,
    summarize_roster_attributes,
)
from app.services.cs_checklist import format_credits_range
from app.services.drop_odds import fetch_course_drop_odds_map
from app.services.minors import (
    build_minors_catalog,
    course_matches_minor_filter,
    evaluate_course_for_minor,
    normalize_course_code as normalize_minor_course_code,
)
from app.services.cs_requirements import (
    PRIORITY_STEM_SUBJECTS,
    TRANSCRIPT_EQUIVALENT_CATALOG,
    CourseEligibility,
    CSRequirementsIndex,
)
from app.services.ilr_requirements import (
    ILRRequirementsIndex,
    PRIORITY_ILR_PREREQ_SUBJECTS,
    PRIORITY_ILR_SUBJECTS,
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
        self._ilr_index_cache: dict[str, tuple[int, ILRRequirementsIndex]] = {}

        self._refresh_queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue(maxsize=200)
        self._refresh_pending: set[tuple[str, str]] = set()
        self._historical_lookup_queued: set[str] = set()
        self._historical_lookup_checked: set[str] = set()
        self._historical_lookup_task: Optional[asyncio.Task[None]] = None
        self._workers_started = False
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
        self._workers_started = True
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
        if self._historical_lookup_queued and (
            self._historical_lookup_task is None or self._historical_lookup_task.done()
        ):
            self._historical_lookup_task = asyncio.create_task(
                self._historical_lookup_runner(),
                name="catalog-historical-lookup",
            )

    async def stop_workers(self) -> None:
        self._stop_event.set()
        self._workers_started = False
        for task in (
            self._refresh_worker_task,
            self._warmup_worker_task,
            self._historical_lookup_task,
        ):
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._refresh_worker_task = None
        self._warmup_worker_task = None
        self._historical_lookup_task = None

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
            roster_cur = await conn.execute(
                "SELECT archive_mode FROM rosters WHERE slug = ?",
                (roster_u,),
            )
            roster_row = await roster_cur.fetchone()
            is_archived_roster = bool(roster_row and roster_row[0])

            prev_sec_cur = await conn.execute(
                "SELECT class_nbr, open_status FROM roster_sections WHERE roster = ? AND subject = ?",
                (roster_u, subject_u),
            )
            prev_status_by_nbr: dict[int, str] = {
                int(r[0]): str(r[1]) for r in await prev_sec_cur.fetchall()
            }
            status_flips: list[tuple[Any, ...]] = []

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
                    prev_st = prev_status_by_nbr.get(sec.class_nbr)
                    if (
                        not is_archived_roster
                        and prev_st is not None
                        and prev_st != sec.open_status
                    ):
                        sec_lbl = f"{sec.ssr_component} {sec.section}".strip()
                        status_flips.append(
                            (
                                roster_u,
                                c.subject,
                                c.catalog_nbr,
                                sec.class_nbr,
                                sec_lbl,
                                prev_st,
                                sec.open_status,
                                0,
                            )
                        )
                    await conn.execute(
                        """
                        INSERT INTO roster_sections (
                            roster, subject, catalog_nbr, class_nbr, enroll_group_idx,
                            ssr_component, section, open_status, components_required_json,
                            meetings_summary, instructors_summary, campus, location, location_descr,
                            instruction_mode, updated_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
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
                            sec.location,
                            sec.location_descr,
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

            if status_flips:
                await conn.executemany(
                    """
                    INSERT INTO status_events (
                        roster, subject, catalog_nbr, class_nbr, section_label,
                        old_status, new_status, poll_rtt_ms
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    status_flips,
                )

            await conn.execute(
                """
                INSERT INTO subjects (roster, value, descr, synced_at, first_synced_at)
                VALUES (?, ?, ?, datetime('now'), datetime('now'))
                ON CONFLICT(roster, value) DO UPDATE SET
                    synced_at = datetime('now'),
                    first_synced_at = COALESCE(subjects.first_synced_at, datetime('now'))
                """,
                (roster_u, subject_u, subject_u),
            )

        self._catalog_generation[roster_u] = self._catalog_generation.get(roster_u, 0) + 1
        self._cs_index_cache.pop(roster_u, None)
        self._ilr_index_cache.pop(roster_u, None)

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

    _REGULAR_ROSTER_RE = re.compile(r"^(FA|SP)(\d{2})$")
    _COURSE_CODE_RE = re.compile(r"^([A-Za-z]{2,8})\s+(\d{3,4}[A-Za-z]?)$")

    def queue_historical_course_lookup(self, codes: list[str]) -> list[str]:
        """Queue missing completed/planned courses for polite background historical roster lookup."""
        queued: list[str] = []
        for raw in codes:
            cleaned = " ".join(str(raw or "").strip().upper().split())
            m = self._COURSE_CODE_RE.match(cleaned)
            if not m:
                continue
            code = f"{m.group(1)} {m.group(2)}"
            if (
                code in TRANSCRIPT_EQUIVALENT_CATALOG
                or code in self._historical_lookup_checked
                or code in self._historical_lookup_queued
            ):
                continue
            if len(self._historical_lookup_queued) >= 200:
                break
            self._historical_lookup_queued.add(code)
            queued.append(code)

        if (
            queued
            and self._workers_started
            and (self._historical_lookup_task is None or self._historical_lookup_task.done())
        ):
            self._historical_lookup_task = asyncio.create_task(
                self._historical_lookup_runner(),
                name="catalog-historical-lookup",
            )
        return queued

    async def _historical_lookup_runner(self) -> None:
        try:
            await self.process_historical_course_lookup()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Historical course lookup runner error: %s", exc)

    async def _load_regular_rosters_desc(self) -> list[str]:
        rows = await self.db.fetch_all("SELECT slug, strm FROM rosters")
        matches: list[tuple[int, int, str, str]] = []
        for r in rows:
            slug = str(r["slug"] or "").upper()
            m = self._REGULAR_ROSTER_RE.match(slug)
            if not m:
                continue
            term = m.group(1)
            yr = int(m.group(2))
            matches.append((yr, 1 if term == "FA" else 0, str(r["strm"] or ""), slug))

        if len(matches) < 4:
            try:
                async with self._acquire_fetch_slot(priority=PRIORITY_WARMUP, min_interval_sec=1.15):
                    rosters = await self.provider.fetch_rosters()
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
                rows = await self.db.fetch_all("SELECT slug, strm FROM rosters")
                matches = []
                for r in rows:
                    slug = str(r["slug"] or "").upper()
                    m = self._REGULAR_ROSTER_RE.match(slug)
                    if not m:
                        continue
                    matches.append((int(m.group(2)), 1 if m.group(1) == "FA" else 0, str(r["strm"] or ""), slug))
            except (RateLimitedError, UpstreamUnavailableError) as exc:
                logger.debug("Historical roster list refresh skipped: %s", exc)

        matches.sort(key=lambda item: (item[0], item[1], item[2], item[3]), reverse=True)
        return [item[3] for item in matches]

    async def process_historical_course_lookup(self, max_rosters_per_subject: int = 8) -> dict[str, Any]:
        """Search recent Fall/Spring rosters at PRIORITY_WARMUP for uncached checklist courses."""
        resolved: list[str] = []
        synced_buckets = 0
        rate_limited = False

        while self._historical_lookup_queued and not self._stop_event.is_set() and not rate_limited:
            batch = sorted(self._historical_lookup_queued)
            by_subj: dict[str, set[str]] = {}
            for code in batch:
                subj, nbr = code.split(" ", 1)
                row = await self.db.fetch_one(
                    "SELECT 1 FROM courses_meta WHERE subject = ? AND catalog_nbr = ? LIMIT 1",
                    (subj, nbr),
                )
                if row is not None:
                    self._historical_lookup_queued.discard(code)
                    resolved.append(code)
                    continue
                by_subj.setdefault(subj, set()).add(nbr)

            if not by_subj:
                break

            candidate_rosters = (await self._load_regular_rosters_desc())[:max_rosters_per_subject]
            for subj, target_nbrs in sorted(by_subj.items()):
                if self._stop_event.is_set() or rate_limited:
                    break
                if not candidate_rosters:
                    break

                synced_rows = await self.db.fetch_all(
                    "SELECT roster, synced_at FROM subjects WHERE value = ? AND synced_at IS NOT NULL",
                    (subj,),
                )
                already_synced = {str(r["roster"]).upper() for r in synced_rows}
                had_transient_failure = False

                for roster_slug in candidate_rosters:
                    if self._stop_event.is_set() or not target_nbrs:
                        break
                    if roster_slug in already_synced:
                        continue
                    while not self._refresh_queue.empty() and not self._stop_event.is_set():
                        await asyncio.sleep(0.5)
                    if self.gate is not None and self.gate.has_active_poller():
                        await asyncio.sleep(2.0)

                    try:
                        did_sync = await self.ensure_subject_synced(
                            roster_slug,
                            subj,
                            force=False,
                            priority=PRIORITY_WARMUP,
                            min_interval_sec=1.25,
                            emit_sse=False,
                        )
                        if did_sync:
                            synced_buckets += 1
                    except RateLimitedError:
                        rate_limited = True
                        had_transient_failure = True
                        await asyncio.sleep(2.0)
                        break
                    except UpstreamUnavailableError as exc:
                        logger.debug("Historical lookup skipped %s %s: %s", roster_slug, subj, exc)
                        had_transient_failure = True
                        continue

                    found_nbrs = await self.db.fetch_all(
                        "SELECT DISTINCT catalog_nbr FROM courses_meta WHERE roster = ? AND subject = ?",
                        (roster_slug, subj),
                    )
                    present_in_roster = {str(r["catalog_nbr"]).upper() for r in found_nbrs}
                    newly_found = sorted(nbr for nbr in target_nbrs if nbr in present_in_roster)
                    if newly_found:
                        found_codes = [f"{subj} {nbr}" for nbr in newly_found]
                        for nbr in newly_found:
                            target_nbrs.discard(nbr)
                            self._historical_lookup_queued.discard(f"{subj} {nbr}")
                        resolved.extend(found_codes)
                        if self.sse_hub is not None:
                            self.sse_hub.publish(
                                "catalog_subject_refreshed",
                                {
                                    "roster": roster_slug,
                                    "subject": subj,
                                    "synced_at": datetime.now(timezone.utc).isoformat(),
                                    "courses_count": len(present_in_roster),
                                    "section_statuses": {},
                                    "historical_lookup": True,
                                    "resolved_courses": found_codes,
                                },
                            )

                if target_nbrs and not rate_limited and not had_transient_failure:
                    for nbr in list(target_nbrs):
                        code = f"{subj} {nbr}"
                        self._historical_lookup_queued.discard(code)
                        if len(self._historical_lookup_checked) < 2000:
                            self._historical_lookup_checked.add(code)

        return {"resolved": resolved, "synced_buckets": synced_buckets}

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

    async def get_ilr_requirements_index(self, roster: str) -> ILRRequirementsIndex:
        """Build or return cached ILRRequirementsIndex over all cached courses for a roster."""
        roster_u = roster.upper()
        gen = self._catalog_generation.get(roster_u, 0)
        cached = self._ilr_index_cache.get(roster_u)
        if cached is not None and cached[0] == gen:
            return cached[1]

        rows = await self.db.fetch_all(
            """
            SELECT subject, catalog_nbr, acad_career,
                   units_min, units_max, has_letter_grade,
                   crosslists_json, crse_attrs_json
            FROM courses_meta
            WHERE roster = ?
            """,
            (roster_u,),
        )
        index = ILRRequirementsIndex(rows)
        self._ilr_index_cache[roster_u] = (gen, index)
        return index

    async def get_ilr_summary(
        self,
        roster: str,
        ithaca_or_virtual: bool = True,
        sync_priority: bool = False,
        auto_warmup_unsynced: bool = True,
    ) -> dict[str, Any]:
        """Compute live ILR requirement availability counts for a roster."""
        roster_u = roster.upper()
        ilr_index = await self.get_ilr_requirements_index(roster_u)

        course_rows = await self.db.fetch_all(
            """
            SELECT subject, catalog_nbr
            FROM courses_meta
            WHERE roster = ?
            """,
            (roster_u,),
        )

        # Keep only courses with at least one ILR requirement code / core tag.
        ilr_courses: set[tuple[str, str]] = set()
        ilr_subjects: set[str] = set()
        for row in course_rows:
            su = str(row["subject"]).upper()
            nbr = str(row["catalog_nbr"])
            elig = ilr_index.get(su, nbr)
            if elig is not None and elig.codes:
                ilr_courses.add((su, nbr))
                ilr_subjects.add(su)

        freshness_by_subj: dict[str, bool] = {}
        for su in ilr_subjects:
            is_fresh, _ = await self._get_subject_freshness(roster_u, su)
            freshness_by_subj[su] = is_fresh

        sec_by_course: dict[tuple[str, str], list[dict[str, Any]]] = {}
        if ilr_courses:
            sec_rows = await self.db.fetch_all(
                """
                SELECT subject, catalog_nbr, open_status, campus, location, instruction_mode
                FROM roster_sections
                WHERE roster = ?
                """,
                (roster_u,),
            )
            for sec in sec_rows:
                key = (str(sec["subject"]).upper(), str(sec["catalog_nbr"]))
                if key in ilr_courses:
                    sec_by_course.setdefault(key, []).append(sec)

        course_status_map: dict[str, tuple[str, bool]] = {}
        filtered_out_location_count = 0
        for su, nbr in ilr_courses:
            elig = ilr_index.get(su, nbr)
            if elig is None:
                continue
            all_secs = sec_by_course.get((su, nbr), [])
            if ithaca_or_virtual and all_secs:
                active_secs = [
                    s
                    for s in all_secs
                    if is_ithaca_or_virtual_section(
                        campus=str(s.get("campus") or ""),
                        location=str(s.get("location") or ""),
                        instruction_mode=str(s.get("instruction_mode") or ""),
                    )
                ]
                if not active_secs:
                    filtered_out_location_count += 1
                    continue
            else:
                active_secs = all_secs

            open_cnt = sum(1 for s in active_secs if s.get("open_status") == "O")
            wait_cnt = sum(1 for s in active_secs if s.get("open_status") == "W")
            status = "open" if open_cnt > 0 else ("waitlist" if wait_cnt > 0 else "closed")
            course_status_map[elig.course_code] = (status, freshness_by_subj.get(su, False))

        summary = ilr_index.build_summary(course_status_map)
        coverage = await self.get_catalog_status(roster_u)

        subj_rows = await self.db.fetch_all(
            "SELECT value, synced_at FROM subjects WHERE roster = ?",
            (roster_u,),
        )
        synced_lookup = {str(r["value"]).upper(): r.get("synced_at") for r in subj_rows}
        ilr_total = sum(1 for s in PRIORITY_ILR_SUBJECTS if s in synced_lookup)
        ilr_synced = sum(1 for s in PRIORITY_ILR_SUBJECTS if synced_lookup.get(s))

        queued_subjects: list[str] = []
        if sync_priority or auto_warmup_unsynced:
            to_queue: list[str] = []
            for s in PRIORITY_ILR_SUBJECTS:
                if s not in synced_lookup:
                    continue
                if sync_priority:
                    if await self.is_subject_stale(roster_u, s):
                        to_queue.append(s)
                elif not synced_lookup.get(s):
                    to_queue.append(s)
            if to_queue:
                queued_subjects = self.queue_visible_refresh(roster_u, to_queue)

        return {
            "roster": roster_u,
            "ithaca_or_virtual": ithaca_or_virtual,
            **summary,
            "filtered_out_location_count": filtered_out_location_count,
            "queued_subjects": queued_subjects,
            "coverage": {
                "synced_subjects": coverage["synced_subjects"],
                "total_subjects": coverage["total_subjects"],
                "ilr_synced": ilr_synced,
                "ilr_total": ilr_total,
                "refreshing_subjects": coverage["refreshing_subjects"],
                "warmup_active": coverage["warmup_active"],
            },
        }

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
        if cs_requirement == "cs_project":
            return elig.cs_project
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
        ilr_index: Optional[ILRRequirementsIndex] = None,
        ilr_filter_active: bool = False,
        sec_by_course: Optional[dict[tuple[str, str], list[dict[str, Any]]]] = None,
    ) -> list[dict[str, Any]]:
        if has_query:
            return rows

        if ilr_filter_active and ilr_index is not None:
            def ilr_sort_key(row: dict[str, Any]) -> tuple[int, int, int, int, int, str, int, str]:
                subj = str(row["subject"]).upper()
                nbr = str(row["catalog_nbr"])
                cat_num = int(row.get("catalog_num") or 0)
                elig = ilr_index.get(subj, nbr)
                has_warnings = 1 if (elig and elig.warnings) else 0
                not_ug = 0 if (elig and elig.acad_career == "UG") else 1
                secs = (sec_by_course or {}).get((subj, nbr), [])
                open_cnt = sum(1 for s in secs if s.get("open_status") == "O")
                wait_cnt = sum(1 for s in secs if s.get("open_status") == "W")
                avail_rank = 0 if open_cnt > 0 else (1 if wait_cnt > 0 else 2)
                req_cnt = elig.requirement_count if elig else 0
                main_cnt = len(elig.main_electives) if elig else 0
                return (has_warnings, not_ug, avail_rank, -req_cnt, -main_cnt, subj, cat_num, nbr)

            return sorted(rows, key=ilr_sort_key)

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

    async def _fetch_sections_for_courses(
        self,
        roster_u: str,
        courses: list[dict[str, Any]],
    ) -> dict[tuple[str, str], list[dict[str, Any]]]:
        """Batch-fetch sections for candidate courses using the fewest indexed SQLite queries."""
        sec_by_course: dict[tuple[str, str], list[dict[str, Any]]] = {}
        if not courses:
            return sec_by_course

        select_sql = """
            SELECT subject, catalog_nbr, class_nbr, enroll_group_idx, ssr_component, section,
                   open_status, components_required_json, meetings_summary,
                   instructors_summary, campus, location, location_descr, instruction_mode
            FROM roster_sections
        """
        course_keys = {(str(c["subject"]).upper(), str(c["catalog_nbr"])) for c in courses}
        unique_subjects = sorted({subj for subj, _ in course_keys})

        rows: list[dict[str, Any]] = []
        if len(courses) > 450 and len(unique_subjects) > 40:
            rows = await self.db.fetch_all(
                f"{select_sql} WHERE roster = ? ORDER BY enroll_group_idx ASC, class_nbr ASC",
                (roster_u,),
            )
        elif len(courses) > 150 and len(unique_subjects) <= 40:
            qmarks = ", ".join("?" for _ in unique_subjects)
            rows = await self.db.fetch_all(
                f"""
                {select_sql}
                WHERE roster = ? AND subject IN ({qmarks})
                ORDER BY enroll_group_idx ASC, class_nbr ASC
                """,
                [roster_u, *unique_subjects],
            )
        else:
            keys_list = list(course_keys)
            for start in range(0, len(keys_list), 150):
                chunk = keys_list[start : start + 150]
                placeholders = " OR ".join("(subject = ? AND catalog_nbr = ?)" for _ in chunk)
                sec_params: list[Any] = [roster_u]
                for subj, cat in chunk:
                    sec_params.extend([subj, cat])
                rows.extend(
                    await self.db.fetch_all(
                        f"""
                        {select_sql}
                        WHERE roster = ? AND ({placeholders})
                        ORDER BY enroll_group_idx ASC, class_nbr ASC
                        """,
                        sec_params,
                    )
                )

        for sec in rows:
            key = (str(sec["subject"]).upper(), str(sec["catalog_nbr"]))
            if key not in course_keys:
                continue
            sec["components_required"] = _decode_json_list(sec.pop("components_required_json", "[]"))
            sec_by_course.setdefault(key, []).append(sec)

        return sec_by_course

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
        ilr_codes: Optional[list[str]] = None,
        ilr_match: str = "any",
        ilr_multi_only: bool = False,
        include_ilr: bool = False,
        attrs: Optional[list[str]] = None,
        attr_match: str = "any",
        minor: str = "",
        minor_version: str = "",
        minor_categories: Optional[list[str]] = None,
        minor_completed_categories: Optional[list[str]] = None,
        minor_hide_completed: bool = True,
        completed_courses: Optional[list[str]] = None,
        only_eligible: bool = False,
        include_implied_prereqs: bool = True,
        ithaca_or_virtual: bool = True,
        refresh_stale: bool = True,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Instant local FTS5 + CS/ILR eligibility search with polite lazy SSE status refresh."""
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
        ilr_filter_list = [c.strip().upper() for c in (ilr_codes or []) if c.strip()]
        ilr_match_mode = "all" if str(ilr_match).strip().lower() == "all" else "any"
        has_ilr_filter = bool(ilr_filter_list or ilr_multi_only)
        attrs_list = [normalize_attr_code(a) for a in (attrs or []) if normalize_attr_code(a)]
        attr_match_mode = "all" if str(attr_match).strip().lower() == "all" else "any"
        minor_id = str(minor or "").strip().lower()
        minor_ver = str(minor_version or "").strip().lower()
        minor_cat_set = {c.strip().lower() for c in (minor_categories or []) if str(c).strip()}
        minor_done_set = {
            c.strip().lower() for c in (minor_completed_categories or []) if str(c).strip()
        }

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

        if req_mode in {"cs_elective", "cs_project", "tech_elective"} and not targets_to_check:
            targets_to_check = ["CS"]
        elif attrs_list and not targets_to_check:
            for virtual_subj in ("PE", "ENGRI", "ENGRD"):
                if virtual_subj in attrs_list:
                    targets_to_check.append(virtual_subj)

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
        sql_limit = (
            8000
            if (req_mode or only_eligible or ithaca_or_virtual or has_ilr_filter or attrs_list or minor_id)
            else max(limit, 200)
        )

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
            cm.crse_attrs_json, cm.catalog_num, cm.units_min, cm.units_max, cm.has_letter_grade,
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
        satisfied_set, implied_courses = cs_index.expand_satisfied_courses(
            completed_courses or [],
            include_implied=include_implied_prereqs,
        )

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

        ilr_index: Optional[ILRRequirementsIndex] = None
        if include_ilr or has_ilr_filter:
            ilr_index = await self.get_ilr_requirements_index(roster_u)
            if has_ilr_filter:
                courses = [
                    c
                    for c in courses
                    if (ilr_elig := ilr_index.get(c["subject"], c["catalog_nbr"])) is not None
                    and ilr_index.matches_filter(
                        ilr_elig,
                        ilr_filter_list,
                        match_mode=ilr_match_mode,
                        ilr_multi_only=ilr_multi_only,
                    )
                ]

        if attrs_list:
            courses = [
                c
                for c in courses
                if course_matches_attrs(
                    extract_course_attributes(c),
                    attrs_list,
                    match_mode=attr_match_mode,
                )
            ]

        minor_by_course: dict[tuple[str, str], dict[str, Any]] = {}
        if minor_id:
            filtered_minor: list[dict[str, Any]] = []
            for c in courses:
                ev = evaluate_course_for_minor(
                    c,
                    minor_id,
                    minor_ver,
                    completed_categories=minor_done_set,
                    active_categories=minor_cat_set,
                )
                if course_matches_minor_filter(
                    ev,
                    selected_categories=minor_cat_set or None,
                    hide_completed=minor_hide_completed,
                ):
                    minor_key = (str(c["subject"]).upper(), str(c["catalog_nbr"]).upper())
                    if ev is not None:
                        minor_by_course[minor_key] = ev
                    filtered_minor.append(c)
            courses = filtered_minor

        prereq_by_course: dict[tuple[str, str], dict[str, Any]] = {
            (c["subject"].upper(), str(c["catalog_nbr"]).upper()): cs_index.evaluate_course_prereqs(
                c["subject"],
                c["catalog_nbr"],
                satisfied_set,
            )
            for c in courses
        }

        if only_eligible:
            courses = [
                c
                for c in courses
                if prereq_by_course[(c["subject"].upper(), str(c["catalog_nbr"]).upper())]["prereqs_met"]
            ]

        sec_by_course = await self._fetch_sections_for_courses(roster_u, courses)
        hidden_by_course: dict[tuple[str, str], list[str]] = {}
        filtered_out_location_count = 0
        filtered_out_locations_set: set[str] = set()

        if ithaca_or_virtual and courses:
            location_kept: list[dict[str, Any]] = []
            for c in courses:
                key = (str(c["subject"]).upper(), str(c["catalog_nbr"]))
                all_secs = sec_by_course.get(key, [])
                if not all_secs:
                    location_kept.append(c)
                    continue
                kept_secs: list[dict[str, Any]] = []
                hidden_locs: list[str] = []
                for sec in all_secs:
                    if is_ithaca_or_virtual_section(
                        campus=str(sec.get("campus") or ""),
                        location=str(sec.get("location") or ""),
                        instruction_mode=str(sec.get("instruction_mode") or ""),
                    ):
                        kept_secs.append(sec)
                    else:
                        loc_label = (
                            str(sec.get("location_descr") or "").strip()
                            or str(sec.get("location") or "").strip()
                            or str(sec.get("campus") or "").strip()
                            or "Off-campus"
                        )
                        hidden_locs.append(loc_label)
                        filtered_out_locations_set.add(loc_label)
                if kept_secs:
                    sec_by_course[key] = kept_secs
                    if hidden_locs:
                        hidden_by_course[key] = hidden_locs
                    location_kept.append(c)
                else:
                    filtered_out_location_count += 1
            courses = location_kept

        courses = self._sort_courses(
            courses,
            cs_index=cs_index,
            cs_requirement=req_mode,
            has_query=bool(fts_expr),
            ilr_index=ilr_index,
            ilr_filter_active=has_ilr_filter,
            sec_by_course=sec_by_course,
        )
        total_matched = len(courses)
        courses = courses[:limit]

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

        active_ilr_set: set[str] = set()
        for raw_code in ilr_filter_list:
            if raw_code == "MAIN_3":
                active_ilr_set.update(("ICL-IL", "LH-IL", "QP-IL"))
            elif raw_code != "ANY_IL":
                active_ilr_set.add(raw_code)

        drop_odds_map = await fetch_course_drop_odds_map(
            self.db,
            roster_u,
            [(str(c["subject"]), str(c["catalog_nbr"])) for c in courses],
        )

        for c in courses:
            su = str(c["subject"]).upper()
            nbr = str(c["catalog_nbr"])
            is_fresh, eff_iso = freshness_by_subj.get(su, (False, None))
            hidden_locs = hidden_by_course.get((su, nbr), [])
            c["crosslists"] = _decode_json_list(c.pop("crosslists_json", "[]"))
            c["components"] = _decode_json_list(c.pop("components_json", "[]"))
            c["crse_attrs"] = extract_course_attributes(c)
            c.pop("crse_attrs_json", None)
            c["has_letter_grade"] = bool(c.get("has_letter_grade", 1))
            c["sections"] = sec_by_course.get((su, nbr), [])
            c["hidden_other_location_count"] = len(hidden_locs)
            c["hidden_other_locations"] = sorted(set(hidden_locs))
            c["external_links"] = build_external_links(c["roster"], su, nbr)
            prereq_eval = prereq_by_course.get((su, str(nbr).upper())) or cs_index.evaluate_course_prereqs(
                su,
                nbr,
                satisfied_set,
            )
            c["cs_eligibility"] = {
                **cs_index.get(su, nbr).to_dict(),
                **prereq_eval,
            }
            if ilr_index is not None:
                ilr_elig = ilr_index.get(su, nbr)
                c["ilr_eligibility"] = (
                    ilr_elig.to_dict(active_filter_codes=active_ilr_set)
                    if ilr_elig is not None
                    else None
                )
            if minor_id:
                c["minor_eligibility"] = minor_by_course.get((su, nbr))
            c["subject_synced_at"] = eff_iso
            c["status_is_stale"] = not is_fresh
            c["drop_odds"] = drop_odds_map.get((su, nbr))

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
                "filtered_out_location_count": filtered_out_location_count,
                "filtered_out_locations": sorted(filtered_out_locations_set)[:6],
                "queued_subjects": queued_subjects,
                "synced_subjects": coverage["synced_subjects"],
                "total_subjects": coverage["total_subjects"],
                "stem_synced": coverage["stem_synced"],
                "stem_total": coverage["stem_total"],
                "refreshing_subjects": coverage["refreshing_subjects"],
                "warmup_active": coverage["warmup_active"],
                "implied_courses": implied_courses,
            },
        }

    async def get_attribute_options(self, roster: str) -> list[dict[str, Any]]:
        """Summarize cached distribution/curriculum attributes available for a roster."""
        roster_u = roster.upper()
        rows = await self.db.fetch_all(
            """
            SELECT subject, catalog_nbr, title_short, title_long, crse_attrs_json
            FROM courses_meta
            WHERE roster = ?
            """,
            (roster_u,),
        )
        return summarize_roster_attributes(rows)

    async def get_minors_catalog(
        self,
        roster: str,
        completed_courses: Optional[list[str]] = None,
        in_progress_courses: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Return Cornell minor definitions, live roster course counts, and user auto-fill matches."""
        roster_u = roster.upper()
        roster_rows = await self.db.fetch_all(
            """
            SELECT subject, catalog_nbr, catalog_num, title_short, title_long,
                   has_letter_grade, units_min, units_max, components_json, crosslists_json
            FROM courses_meta
            WHERE roster = ?
            """,
            (roster_u,),
        )
        meta_by_code: dict[str, dict[str, Any]] = {}
        for row in roster_rows:
            code = normalize_minor_course_code(f"{row.get('subject', '')} {row.get('catalog_nbr', '')}")
            if code:
                meta_by_code[code] = row

        missing_codes: list[tuple[str, str]] = []
        for raw_code in [*(completed_courses or []), *(in_progress_courses or [])]:
            code = normalize_minor_course_code(raw_code)
            if code and code not in meta_by_code and " " in code:
                subj, nbr = code.split(" ", 1)
                missing_codes.append((subj, nbr))

        if missing_codes:
            pairs_sql = " OR ".join("(subject = ? AND catalog_nbr = ?)" for _ in missing_codes)
            params: list[Any] = []
            for subj, nbr in missing_codes:
                params.extend((subj, nbr))
            hist_rows = await self.db.fetch_all(
                f"""
                SELECT roster, subject, catalog_nbr, catalog_num, title_short, title_long,
                       has_letter_grade, units_min, units_max, components_json, crosslists_json
                FROM courses_meta
                WHERE {pairs_sql}
                ORDER BY roster DESC
                """,
                tuple(params),
            )
            for row in hist_rows:
                code = normalize_minor_course_code(f"{row.get('subject', '')} {row.get('catalog_nbr', '')}")
                if code and code not in meta_by_code:
                    meta_by_code[code] = row

        return {
            "roster": roster_u,
            "minors": build_minors_catalog(
                roster_rows,
                completed_courses=completed_courses,
                in_progress_courses=in_progress_courses,
                meta_by_code=meta_by_code,
            ),
        }

    async def get_prereq_course_options(
        self,
        roster: str,
        query: str = "",
        limit: int = 30,
        mode: str = "cs",
    ) -> list[dict[str, Any]]:
        """Query local cached courses_meta for prerequisite autocomplete with zero Cornell API calls."""
        roster_u = roster.upper()
        query_clean = normalize_search_query(query)
        mode_norm = str(mode or "cs").strip().lower()
        rows: list[dict[str, Any]] = []
        seen_keys: set[tuple[str, str]] = set()

        def _append_rows(batch: list[dict[str, Any]]) -> None:
            for row in batch:
                key = (row["subject"].upper(), str(row["catalog_nbr"]).upper())
                if key not in seen_keys:
                    seen_keys.add(key)
                    rows.append(
                        {
                            "code": f"{key[0]} {key[1]}",
                            "subject": key[0],
                            "catalog_nbr": key[1],
                            "title": row.get("title_long") or row.get("title_short") or "",
                            "cr": format_credits_range(row.get("units_min"), row.get("units_max")),
                            "crosslists": _decode_json_list(row.get("crosslists_json", "[]")),
                        }
                    )
                    if len(rows) >= limit:
                        return

        if not query_clean:
            default_subjects = (
                PRIORITY_ILR_PREREQ_SUBJECTS
                if mode_norm == "ilr"
                else ("CS", "MATH", "ORIE", "ECE", "INFO", "STSCI", "ENGRD", "BTRY")
            )
            subj_qmarks = ", ".join("?" for _ in default_subjects)
            default_rows = await self.db.fetch_all(
                f"""
                SELECT subject, catalog_nbr, title_short, title_long, units_min, units_max, crosslists_json
                FROM courses_meta
                WHERE roster = ?
                  AND subject IN ({subj_qmarks})
                  AND catalog_num BETWEEN 1000 AND 4999
                ORDER BY subject, catalog_num, catalog_nbr
                LIMIT ?
                """,
                (roster_u, *default_subjects, limit),
            )
            _append_rows(default_rows)
            if len(rows) < limit:
                fallback_rows = await self.db.fetch_all(
                    """
                    SELECT subject, catalog_nbr, title_short, title_long, units_min, units_max, crosslists_json
                    FROM courses_meta
                    WHERE roster = ?
                      AND catalog_num BETWEEN 1000 AND 4999
                    ORDER BY subject, catalog_num, catalog_nbr
                    LIMIT ?
                    """,
                    (roster_u, limit),
                )
                _append_rows(fallback_rows)
            return rows[:limit]

        tokens = [t.lower() for t in re.findall(r"[A-Za-z0-9]+", query_clean)]
        if tokens:
            equiv_matches: list[dict[str, Any]] = []
            for eq in TRANSCRIPT_EQUIVALENT_CATALOG.values():
                haystack = " ".join(
                    [
                        str(eq["code"]),
                        str(eq["subject"]),
                        str(eq["catalog_nbr"]),
                        str(eq["title_short"]),
                        str(eq["title_long"]),
                        " ".join(eq.get("keywords") or ()),
                    ]
                ).lower()
                if all(tok in haystack for tok in tokens):
                    equiv_matches.append(
                        {
                            "subject": eq["subject"],
                            "catalog_nbr": eq["catalog_nbr"],
                            "title_short": eq["title_short"],
                            "title_long": eq["title_long"],
                            "units_min": eq["units_min"],
                            "units_max": eq["units_max"],
                            "crosslists_json": "[]",
                        }
                    )
            if equiv_matches:
                _append_rows(equiv_matches)

        fts_expr = build_fts_query(query_clean)
        if fts_expr:
            fts_rows = await self.db.fetch_all(
                """
                SELECT cm.subject, cm.catalog_nbr, cm.title_short, cm.title_long, cm.units_min, cm.units_max, cm.crosslists_json
                FROM courses_fts
                JOIN courses_meta cm
                  ON cm.roster = courses_fts.roster
                 AND cm.subject = courses_fts.subject
                 AND cm.catalog_nbr = courses_fts.catalog_nbr
                WHERE courses_fts MATCH ?
                ORDER BY CASE WHEN courses_fts.roster = ? THEN 0 ELSE 1 END, rank, cm.subject, cm.catalog_num, cm.catalog_nbr
                LIMIT ?
                """,
                (fts_expr, roster_u, limit * 2),
            )
            _append_rows(fts_rows)

        if tokens and len(rows) < limit:
            clauses: list[str] = []
            params: list[Any] = []
            for tok in tokens[:5]:
                clauses.append(
                    "LOWER(subject || ' ' || catalog_nbr || ' ' || COALESCE(title_long, title_short, '')) LIKE ? ESCAPE '\\'"
                )
                params.append(f"%{_escape_like(tok)}%")
            params.extend([roster_u, limit * 2])
            like_rows = await self.db.fetch_all(
                f"""
                SELECT subject, catalog_nbr, title_short, title_long, units_min, units_max, crosslists_json
                FROM courses_meta
                WHERE {' AND '.join(clauses)}
                ORDER BY CASE WHEN roster = ? THEN 0 ELSE 1 END, subject, catalog_num, catalog_nbr
                LIMIT ?
                """,
                params,
            )
            _append_rows(like_rows)

        return rows[:limit]

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
