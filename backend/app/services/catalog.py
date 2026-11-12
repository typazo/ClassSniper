"""Local Cornell roster/course catalog synchronization and instant FTS5 search."""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import orjson

from app.db import Database, build_fts_query
from app.providers.base import AvailabilityProvider, CourseRecord

SUBJECT_PREFIX_RE = re.compile(r"^\s*([A-Za-z]{2,8})(?:[\s\-:]+\d.*)?$")


class CatalogSyncService:
    """Maintains cached rosters, subjects, courses, and FTS5 index in SQLite."""

    def __init__(
        self,
        db: Database,
        provider: AvailabilityProvider,
        sync_interval_hours: float = 12.0,
    ) -> None:
        self.db = db
        self.provider = provider
        self.sync_interval_hours = sync_interval_hours
        self._subject_locks: dict[tuple[str, str], asyncio.Lock] = {}
        self._bg_sync_lock = asyncio.Lock()
        self.status: dict[str, Any] = {
            "in_progress": False,
            "last_sync_at": None,
            "last_error": None,
            "rosters_count": 0,
        }

    def _get_subject_lock(self, roster: str, subject: str) -> asyncio.Lock:
        key = (roster.upper(), subject.upper())
        lock = self._subject_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._subject_locks[key] = lock
        return lock

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
                eg_json = orjson.dumps(c.enroll_groups).decode("utf-8")
                await conn.execute(
                    """
                    INSERT INTO courses_meta (
                        roster, subject, catalog_nbr, title_short, title_long,
                        description, crse_id, enroll_groups_json, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                    """,
                    (
                        roster_u,
                        c.subject,
                        c.catalog_nbr,
                        c.title_short,
                        c.title_long,
                        c.description,
                        c.crse_id,
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

    async def is_subject_stale(self, roster: str, subject: str, max_age_hours: Optional[float] = None) -> bool:
        age_hours = max_age_hours if max_age_hours is not None else self.sync_interval_hours
        row = await self.db.fetch_one(
            "SELECT synced_at FROM subjects WHERE roster = ? AND value = ?",
            (roster.upper(), subject.upper()),
        )
        if row is None or not row["synced_at"]:
            return True
        try:
            synced_dt = datetime.fromisoformat(row["synced_at"]).replace(tzinfo=timezone.utc)
        except ValueError:
            return True
        return datetime.now(timezone.utc) - synced_dt > timedelta(hours=age_hours)

    async def ensure_subject_synced(
        self,
        roster: str,
        subject: str,
        force: bool = False,
    ) -> bool:
        """Fetch and index a single (roster, subject) if missing or stale. Returns True if fetched."""
        roster_u = roster.upper()
        subject_u = subject.upper()
        lock = self._get_subject_lock(roster_u, subject_u)
        async with lock:
            if not force and not await self.is_subject_stale(roster_u, subject_u):
                return False
            result = await self.provider.fetch_subject_classes(roster_u, subject_u)
            await self.upsert_courses_batch(roster_u, subject_u, result.courses)
            return True

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
                    if await self.ensure_subject_synced(roster_u, row["value"], force=False):
                        synced += 1
                        if idx < len(subjects) - 1:
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

    async def search_courses(
        self,
        roster: str,
        query: str = "",
        subject: str = "",
        limit: int = 40,
    ) -> list[dict[str, Any]]:
        """Instant local FTS5 course search with automatic on-demand subject hydration."""
        roster_u = roster.upper()
        subject_u = subject.strip().upper()
        query_clean = query.strip()

        # Auto-hydrate subject on demand if user explicitly filters by subject or types e.g. "CS 2110"
        candidate_subject = subject_u
        if not candidate_subject and query_clean:
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
                    candidate_subject = maybe_subj

        if candidate_subject:
            try:
                await self.ensure_subject_synced(roster_u, candidate_subject)
            except Exception:
                # If offline or upstream transient error, still serve any cached rows gracefully
                pass

        fts_expr = build_fts_query(query_clean)
        params: list[Any] = [roster_u]
        if fts_expr:
            sql = """
                SELECT cm.roster, cm.subject, cm.catalog_nbr, cm.title_short, cm.title_long,
                       cm.description, cm.updated_at
                FROM courses_fts
                JOIN courses_meta cm
                  ON cm.roster = courses_fts.roster
                 AND cm.subject = courses_fts.subject
                 AND cm.catalog_nbr = courses_fts.catalog_nbr
                WHERE courses_fts MATCH ?
                  AND courses_fts.roster = ?
            """
            params = [fts_expr, roster_u]
            if subject_u:
                sql += " AND cm.subject = ?"
                params.append(subject_u)
            sql += " ORDER BY rank, cm.subject, cm.catalog_nbr LIMIT ?"
            params.append(limit)
        else:
            sql = """
                SELECT roster, subject, catalog_nbr, title_short, title_long, description, updated_at
                FROM courses_meta
                WHERE roster = ?
            """
            if subject_u:
                sql += " AND subject = ?"
                params.append(subject_u)
            sql += " ORDER BY subject, catalog_nbr LIMIT ?"
            params.append(limit)

        courses = await self.db.fetch_all(sql, params)
        if not courses:
            return []

        # Attach section summaries in one batch query
        keys = [(c["subject"], c["catalog_nbr"]) for c in courses]
        placeholders = " OR ".join("(subject = ? AND catalog_nbr = ?)" for _ in keys)
        sec_params: list[Any] = [roster_u]
        for subj, cat in keys:
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

        sec_by_course: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for sec in sections:
            sec["components_required"] = json.loads(sec.pop("components_required_json", "[]"))
            sec_by_course.setdefault((sec["subject"], sec["catalog_nbr"]), []).append(sec)

        for c in courses:
            c["sections"] = sec_by_course.get((c["subject"], c["catalog_nbr"]), [])

        return courses
