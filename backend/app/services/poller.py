"""High-frequency deduplicated poller engine with priority-weighted scheduling."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Optional

from app.config import Settings
from app.db import Database
from app.providers.base import (
    AvailabilityProvider,
    CourseRecord,
    RateLimitedError,
    SectionRecord,
    UpstreamUnavailableError,
)
from app.providers.cornell import is_ithaca_or_virtual_section
from app.services.catalog import CatalogSyncService
from app.services.dispatcher import AlertDispatcher, MatchedAlert
from app.services.gate import PRIORITY_POLLER, CornellRequestGate
from app.services.sse import SSEHub


@dataclass(slots=True)
class _BucketMeta:
    roster: str
    subject: str
    weight: int
    watch_count: int
    last_polled_mono: float = 0.0
    last_polled_at: Optional[str] = None
    last_rtt_ms: int = 0
    credit: float = 0.0


def _target_statuses(trigger_on: str) -> set[str]:
    if trigger_on == "open_or_waitlist":
        return {"O", "W"}
    return {"O"}


def _is_linked_group_ready(
    target_sec: SectionRecord,
    group_sections: list[SectionRecord],
    status_lookup: dict[int, Optional[str]],
    targets: set[str],
) -> Optional[bool]:
    """Return True if section and all required companion components in its enrollGroup are open.
    Returns None if baseline statuses are incomplete."""
    target_status = status_lookup.get(target_sec.class_nbr)
    if target_status is None:
        return None
    if target_status not in targets:
        return False

    required = set(target_sec.components_required or [])
    for comp in required:
        if comp == target_sec.ssr_component:
            continue
        companions = [s for s in group_sections if s.ssr_component == comp]
        if not companions:
            continue
        comp_statuses = [status_lookup.get(s.class_nbr) for s in companions]
        if all(st is None for st in comp_statuses):
            return None
        if not any(st in targets for st in comp_statuses if st is not None):
            return False
    return True


class PollerEngine:
    """Continuously polls active (roster, subject) buckets within a configurable RPS cap."""

    def __init__(
        self,
        db: Database,
        settings: Settings,
        provider: AvailabilityProvider,
        catalog: CatalogSyncService,
        dispatcher: AlertDispatcher,
        sse_hub: SSEHub,
        gate: Optional[CornellRequestGate] = None,
    ) -> None:
        self.db = db
        self.settings = settings
        self.provider = provider
        self.catalog = catalog
        self.dispatcher = dispatcher
        self.sse_hub = sse_hub
        self.gate = gate
        if self.gate is not None:
            self.gate.set_active_poller_fn(self.has_active_buckets)

        # In-memory cache: (roster, class_nbr) -> open_status
        self.section_status: dict[tuple[str, int], str] = {}
        self._buckets: dict[tuple[str, str], _BucketMeta] = {}
        self._stop_event = asyncio.Event()
        self._wake_event = asyncio.Event()
        self._task: Optional[asyncio.Task[None]] = None
        self._poll_lock = asyncio.Lock()

        # Token bucket / backoff state
        self._last_request_mono: float = 0.0
        self._backoff_sec: float = 0.0
        self._backoff_until_mono: float = 0.0
        self._recent_rtts: deque[int] = deque(maxlen=50)
        self._meta_synced_mono: dict[tuple[str, str], float] = {}

        self.telemetry: dict[str, Any] = {
            "state": "stopped",
            "total_polls": 0,
            "error_count": 0,
            "rate_limit_hits": 0,
            "alerts_triggered": 0,
            "last_poll_at": None,
            "last_poll_subject": None,
            "last_poll_rtt_ms": 0,
            "last_error": None,
        }

    def has_active_buckets(self) -> bool:
        return bool(self._buckets)

    def get_bucket_last_polled_at(self, roster: str, subject: str) -> Optional[str]:
        bucket = self._buckets.get((roster.upper(), subject.upper()))
        return bucket.last_polled_at if bucket is not None else None

    @asynccontextmanager
    async def _gate_slot(self) -> AsyncIterator[None]:
        if self.gate is None:
            yield
        else:
            async with self.gate.slot(PRIORITY_POLLER, min_interval_sec=0.0, honor_backoff=False):
                yield

    async def hydrate_from_db(self) -> None:
        """Seed in-memory state map from cached SQLite sections so restarts catch missed flips."""
        rows = await self.db.fetch_all("SELECT roster, class_nbr, open_status FROM roster_sections")
        for r in rows:
            self.section_status[(str(r["roster"]).upper(), int(r["class_nbr"]))] = str(r["open_status"]).upper()

    def seed_section_status(self, roster: str, class_nbr: int, open_status: str) -> None:
        self.section_status[(roster.upper(), int(class_nbr))] = open_status.upper()

    def wake(self) -> None:
        """Wake scheduler immediately when a watch is added/resumed."""
        self._wake_event.set()

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop_event.clear()
        self.telemetry["state"] = "idle"
        self._task = asyncio.create_task(self._run_loop(), name="classsniper-poller")

    async def stop(self) -> None:
        self._stop_event.set()
        self._wake_event.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except asyncio.TimeoutError:
                self._task.cancel()
            self._task = None
        self.telemetry["state"] = "stopped"

    async def _get_max_rps(self) -> float:
        raw = await self.db.get_setting("poll_max_rps", "")
        if raw:
            try:
                return max(0.1, min(5.0, float(raw)))
            except ValueError:
                pass
        return max(0.1, min(5.0, float(self.settings.poll_max_rps)))

    async def _refresh_buckets(self) -> list[_BucketMeta]:
        rows = await self.db.fetch_all(
            """
            SELECT w.roster, w.subject,
                   COUNT(*) AS watch_count,
                   MAX(w.priority * u.priority_tier) AS max_weight
            FROM watches w
            JOIN users u ON u.id = w.user_id
            WHERE w.active = 1
            GROUP BY w.roster, w.subject
            """
        )
        active_keys: set[tuple[str, str]] = set()
        for r in rows:
            key = (str(r["roster"]).upper(), str(r["subject"]).upper())
            active_keys.add(key)
            existing = self._buckets.get(key)
            if existing is None:
                self._buckets[key] = _BucketMeta(
                    roster=key[0],
                    subject=key[1],
                    weight=int(r["max_weight"] or 1),
                    watch_count=int(r["watch_count"] or 1),
                    credit=float(r["max_weight"] or 1),
                )
            else:
                existing.weight = int(r["max_weight"] or 1)
                existing.watch_count = int(r["watch_count"] or 1)

        for stale_key in list(self._buckets.keys()):
            if stale_key not in active_keys:
                del self._buckets[stale_key]

        return list(self._buckets.values())

    def _select_next_bucket(self, buckets: list[_BucketMeta]) -> _BucketMeta:
        """Priority-weighted deficit round-robin selection."""
        for b in buckets:
            b.credit += float(b.weight)
        chosen = max(buckets, key=lambda b: (b.credit, -b.last_polled_mono))
        total_weight = sum(b.weight for b in buckets)
        chosen.credit -= float(total_weight)
        return chosen

    async def _run_loop(self) -> None:
        await self.hydrate_from_db()
        while not self._stop_event.is_set():
            try:
                buckets = await self._refresh_buckets()
                if not buckets:
                    self.telemetry["state"] = "idle"
                    self._wake_event.clear()
                    try:
                        await asyncio.wait_for(self._wake_event.wait(), timeout=2.0)
                    except asyncio.TimeoutError:
                        pass
                    continue

                now_mono = time.monotonic()
                if now_mono < self._backoff_until_mono:
                    self.telemetry["state"] = "backoff"
                    wait_for = min(self._backoff_until_mono - now_mono, 2.0)
                    await asyncio.sleep(wait_for)
                    continue

                max_rps = await self._get_max_rps()
                min_interval = 1.0 / max_rps
                elapsed = now_mono - self._last_request_mono
                if elapsed < min_interval:
                    await asyncio.sleep(min_interval - elapsed)
                    if self._stop_event.is_set():
                        break

                buckets = await self._refresh_buckets()
                if not buckets:
                    continue
                target = self._select_next_bucket(buckets)
                self.telemetry["state"] = "polling"
                await self.poll_bucket(target.roster, target.subject)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self.telemetry["error_count"] += 1
                self.telemetry["last_error"] = str(exc)[:300]
                await asyncio.sleep(2.0)

    async def poll_bucket(self, roster: str, subject: str) -> dict[str, Any]:
        """Fetch one (roster, subject) bucket, diff all sections, and fire matched alerts."""
        roster_u = roster.upper()
        subject_u = subject.upper()

        async with self._poll_lock:
            self._last_request_mono = time.monotonic()
            try:
                async with self._gate_slot():
                    fetch_res = await self.provider.fetch_subject_classes(roster_u, subject_u)
            except RateLimitedError as exc:
                self.telemetry["rate_limit_hits"] += 1
                self.telemetry["error_count"] += 1
                self.telemetry["last_error"] = str(exc)
                self.telemetry["state"] = "backoff"
                self._backoff_sec = max(exc.retry_after_sec, min(60.0, (self._backoff_sec or 5.0) * 2.0))
                self._backoff_until_mono = time.monotonic() + self._backoff_sec
                if self.gate is not None:
                    self.gate.record_rate_limit(self._backoff_sec)
                return {"ok": False, "error": str(exc)}
            except UpstreamUnavailableError as exc:
                self.telemetry["error_count"] += 1
                self.telemetry["last_error"] = str(exc)
                self.telemetry["state"] = "backoff"
                self._backoff_sec = min(60.0, max(5.0, (self._backoff_sec or 2.5) * 2.0))
                self._backoff_until_mono = time.monotonic() + self._backoff_sec
                return {"ok": False, "error": str(exc)}

            # Successful poll resets backoff
            self._backoff_sec = 0.0
            self._backoff_until_mono = 0.0
            if self.gate is not None:
                self.gate.clear_backoff()
            now_iso = datetime.now(timezone.utc).isoformat()

            self.telemetry["total_polls"] += 1
            self.telemetry["last_poll_at"] = now_iso
            self.telemetry["last_poll_subject"] = f"{roster_u} {subject_u}"
            self.telemetry["last_poll_rtt_ms"] = fetch_res.rtt_ms
            self.telemetry["last_error"] = None
            self._recent_rtts.append(fetch_res.rtt_ms)

            bucket = self._buckets.get((roster_u, subject_u))
            if bucket is not None:
                bucket.last_polled_mono = time.monotonic()
                bucket.last_polled_at = now_iso
                bucket.last_rtt_ms = fetch_res.rtt_ms

            alerts = await self.evaluate_courses(
                roster=roster_u,
                subject=subject_u,
                courses=fetch_res.courses,
                rtt_ms=fetch_res.rtt_ms,
            )

            if alerts:
                self.telemetry["alerts_triggered"] += len(alerts)
                await self.dispatcher.dispatch_alerts(alerts)

            # Reuse polled payload after alert dispatch to refresh stale/migrated course metadata at zero HTTP cost
            now_mono = time.monotonic()
            last_meta = self._meta_synced_mono.get((roster_u, subject_u), 0.0)
            if now_mono - last_meta >= 3600.0:
                self._meta_synced_mono[(roster_u, subject_u)] = now_mono
                if await self.catalog.is_subject_stale(roster_u, subject_u):
                    await self.catalog.upsert_courses_batch(roster_u, subject_u, fetch_res.courses)

            # Publish lightweight telemetry tick for live UI
            self.sse_hub.publish("telemetry", self.get_metrics_snapshot())
            return {
                "ok": True,
                "roster": roster_u,
                "subject": subject_u,
                "rtt_ms": fetch_res.rtt_ms,
                "alerts_count": len(alerts),
            }

    async def evaluate_courses(
        self,
        roster: str,
        subject: str,
        courses: list[CourseRecord],
        rtt_ms: int = 0,
    ) -> list[MatchedAlert]:
        """Diff live CourseRecord statuses against in-memory baseline and return MatchedAlerts."""
        roster_u = roster.upper()
        subject_u = subject.upper()

        # Snapshot previous section statuses for this (roster, subject) before mutating
        prev_status_by_nbr: dict[int, Optional[str]] = {}
        new_status_by_nbr: dict[int, str] = {}
        sec_lookup: dict[int, tuple[CourseRecord, SectionRecord]] = {}
        course_sections_map: dict[str, list[tuple[CourseRecord, SectionRecord]]] = {}
        eg_sections_map: dict[tuple[str, int], list[SectionRecord]] = {}
        changed_sections: list[tuple[int, str]] = []
        raw_flips: list[tuple[str, int, str, str, str]] = []

        for course in courses:
            for sec in course.sections:
                key = (roster_u, sec.class_nbr)
                prev_val = self.section_status.get(key)
                prev_status_by_nbr[sec.class_nbr] = prev_val
                new_status_by_nbr[sec.class_nbr] = sec.open_status
                sec_lookup[sec.class_nbr] = (course, sec)
                course_sections_map.setdefault(course.catalog_nbr, []).append((course, sec))
                eg_sections_map.setdefault((course.catalog_nbr, sec.enroll_group_idx), []).append(sec)

                if prev_val != sec.open_status:
                    changed_sections.append((sec.class_nbr, sec.open_status))
                    if prev_val is not None:
                        sec_lbl = f"{sec.ssr_component} {sec.section}".strip()
                        raw_flips.append((course.catalog_nbr, sec.class_nbr, sec_lbl, prev_val, sec.open_status))
                self.section_status[key] = sec.open_status

        # Ensure catalog exists or incrementally update changed statuses in SQLite
        existing_meta = await self.db.fetch_one(
            "SELECT COUNT(*) AS cnt FROM courses_meta WHERE roster = ? AND subject = ?",
            (roster_u, subject_u),
        )
        if not existing_meta or int(existing_meta["cnt"]) == 0:
            await self.catalog.upsert_courses_batch(roster_u, subject_u, courses)
        elif changed_sections:
            await self.catalog.update_section_statuses(roster_u, changed_sections)

        # Load active watches in this (roster, subject) bucket
        rows = await self.db.fetch_all(
            """
            SELECT w.*,
                   u.username, u.role, u.priority_tier, u.discord_user_id,
                   u.discord_ping_enabled, u.personal_webhook_url, u.web_push_enabled
            FROM watches w
            JOIN users u ON u.id = w.user_id
            WHERE w.active = 1 AND w.roster = ? AND w.subject = ?
            """,
            (roster_u, subject_u),
        )
        if not rows:
            if raw_flips:
                async with self.db.write_tx() as conn:
                    for cat_nbr, cls_nbr, sec_lbl, old_st, new_st in raw_flips:
                        await conn.execute(
                            """
                            INSERT INTO status_events (
                                roster, subject, catalog_nbr, class_nbr, section_label,
                                old_status, new_status, poll_rtt_ms
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (roster_u, subject_u, cat_nbr, cls_nbr, sec_lbl, old_st, new_st, rtt_ms),
                        )
            return []

        now_dt = datetime.now(timezone.utc)
        now_iso = now_dt.isoformat()
        matched_alerts: list[MatchedAlert] = []
        watch_updates: list[tuple[str, Optional[str], Optional[str], int, int]] = []
        fired_groups: dict[tuple[int, str], int] = {}

        for row in rows:
            user_dict = {
                "id": row["user_id"],
                "username": row["username"],
                "role": row["role"],
                "priority_tier": row["priority_tier"],
                "discord_user_id": row["discord_user_id"],
                "discord_ping_enabled": row["discord_ping_enabled"],
                "personal_webhook_url": row["personal_webhook_url"],
                "web_push_enabled": row["web_push_enabled"],
            }
            gkey = str(row.get("group_key") or "").strip().lower()
            group_token = (int(row["user_id"]), gkey) if gkey else None
            group_already_fired = bool(group_token and group_token in fired_groups)

            targets = _target_statuses(row["trigger_on"])
            mode = row["mode"]
            cooldown_sec = int(row["cooldown_sec"] or 0)

            in_cooldown = False
            if row["last_notified_at"] and cooldown_sec > 0:
                try:
                    last_dt = datetime.fromisoformat(row["last_notified_at"])
                    if last_dt.tzinfo is None:
                        last_dt = last_dt.replace(tzinfo=timezone.utc)
                    in_cooldown = (now_dt - last_dt).total_seconds() < cooldown_sec
                except ValueError:
                    in_cooldown = False

            if mode == "exact":
                c_nbr = row["class_nbr"]
                if c_nbr is None or int(c_nbr) not in sec_lookup:
                    continue
                course, sec = sec_lookup[int(c_nbr)]
                prev_st = prev_status_by_nbr.get(sec.class_nbr)
                if prev_st is None:
                    prev_st = row["last_observed_status"]

                now_st = sec.open_status
                triggered = (
                    now_st in targets
                    and prev_st is not None
                    and prev_st not in targets
                    and not in_cooldown
                    and not group_already_fired
                )
                if triggered:
                    if group_token is not None:
                        fired_groups[group_token] = int(row["id"])
                    matched_alerts.append(
                        MatchedAlert(
                            watch=row,
                            user=user_dict,
                            course=course,
                            section=sec,
                            old_status=prev_st,
                            new_status=now_st,
                            poll_rtt_ms=rtt_ms,
                        )
                    )
                    new_active = 0 if row["auto_pause"] else 1
                    watch_updates.append((now_st, now_st, now_iso, new_active, row["id"]))
                elif row["last_observed_status"] != now_st:
                    watch_updates.append(
                        (now_st, row["last_notified_status"], row["last_notified_at"], row["active"], row["id"])
                    )

            elif mode == "linked_group":
                c_nbr = row["class_nbr"]
                if c_nbr is None or int(c_nbr) not in sec_lookup:
                    continue
                course, sec = sec_lookup[int(c_nbr)]
                group_secs = eg_sections_map.get((course.catalog_nbr, sec.enroll_group_idx), [])
                now_ready = _is_linked_group_ready(sec, group_secs, new_status_by_nbr, targets)
                prev_ready = _is_linked_group_ready(sec, group_secs, prev_status_by_nbr, targets)
                if prev_ready is None and row["last_observed_status"] in {"READY", "NOT_READY"}:
                    prev_ready = row["last_observed_status"] == "READY"

                obs_label = "READY" if now_ready else "NOT_READY"
                triggered = (
                    bool(now_ready)
                    and prev_ready is False
                    and not in_cooldown
                    and not group_already_fired
                )
                if triggered:
                    if group_token is not None:
                        fired_groups[group_token] = int(row["id"])
                    prev_st = prev_status_by_nbr.get(sec.class_nbr) or "C"
                    matched_alerts.append(
                        MatchedAlert(
                            watch=row,
                            user=user_dict,
                            course=course,
                            section=sec,
                            old_status=prev_st,
                            new_status=sec.open_status,
                            poll_rtt_ms=rtt_ms,
                        )
                    )
                    new_active = 0 if row["auto_pause"] else 1
                    watch_updates.append((obs_label, sec.open_status, now_iso, new_active, row["id"]))
                elif row["last_observed_status"] != obs_label:
                    watch_updates.append(
                        (obs_label, row["last_notified_status"], row["last_notified_at"], row["active"], row["id"])
                    )

            elif mode == "any_section":
                candidates = course_sections_map.get(str(row["catalog_nbr"]), [])
                comp_filter = (row["component_filter"] or "").strip().upper()
                ith_only = bool(row.get("ithaca_or_virtual", 0))
                matching_secs = [
                    (c, s)
                    for (c, s) in candidates
                    if (not comp_filter or s.ssr_component == comp_filter)
                    and (
                        not ith_only
                        or is_ithaca_or_virtual_section(
                            campus=s.campus,
                            location=s.location,
                            instruction_mode=s.instruction_mode,
                        )
                    )
                ]
                if not matching_secs:
                    continue

                open_now = [s for _, s in matching_secs if s.open_status in targets]
                newly_opened = [
                    (c, s, prev_status_by_nbr.get(s.class_nbr))
                    for (c, s) in matching_secs
                    if s.open_status in targets
                    and prev_status_by_nbr.get(s.class_nbr) is not None
                    and prev_status_by_nbr.get(s.class_nbr) not in targets
                ]
                obs_label = "OPEN_ANY" if open_now else "NONE_OPEN"

                if newly_opened and not in_cooldown and not group_already_fired:
                    if group_token is not None:
                        fired_groups[group_token] = int(row["id"])
                    first_course, first_sec, prev_st = newly_opened[0]
                    matched_alerts.append(
                        MatchedAlert(
                            watch=row,
                            user=user_dict,
                            course=first_course,
                            section=first_sec,
                            old_status=prev_st,
                            new_status=first_sec.open_status,
                            poll_rtt_ms=rtt_ms,
                        )
                    )
                    new_active = 0 if row["auto_pause"] else 1
                    watch_updates.append((obs_label, first_sec.open_status, now_iso, new_active, row["id"]))
                elif row["last_observed_status"] != obs_label:
                    watch_updates.append(
                        (obs_label, row["last_notified_status"], row["last_notified_at"], row["active"], row["id"])
                    )

        alert_flip_keys = {(a.section.class_nbr, a.new_status) for a in matched_alerts}
        non_alert_flips = [
            f for f in raw_flips if (f[1], f[4]) not in alert_flip_keys
        ]
        paused_group_events: list[tuple[int, str, int]] = []

        if watch_updates or fired_groups or non_alert_flips:
            async with self.db.write_tx() as conn:
                for obs, notif_st, notif_at, act, wid in watch_updates:
                    await conn.execute(
                        """
                        UPDATE watches
                        SET last_observed_status = ?,
                            last_notified_status = ?,
                            last_notified_at = ?,
                            active = ?
                        WHERE id = ?
                        """,
                        (obs, notif_st, notif_at, act, wid),
                    )
                for (uid, gkey), winner_id in fired_groups.items():
                    cur = await conn.execute(
                        """
                        UPDATE watches
                        SET active = 0
                        WHERE user_id = ?
                          AND LOWER(TRIM(group_key)) = ?
                          AND id != ?
                          AND active = 1
                        """,
                        (uid, gkey, winner_id),
                    )
                    if (cur.rowcount or 0) > 0:
                        paused_group_events.append((uid, gkey, int(cur.rowcount)))
                for cat_nbr, cls_nbr, sec_lbl, old_st, new_st in non_alert_flips:
                    await conn.execute(
                        """
                        INSERT INTO status_events (
                            roster, subject, catalog_nbr, class_nbr, section_label,
                            old_status, new_status, poll_rtt_ms
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (roster_u, subject_u, cat_nbr, cls_nbr, sec_lbl, old_st, new_st, rtt_ms),
                    )

        for uid, gkey, cnt in paused_group_events:
            self.sse_hub.publish(
                "watches_changed",
                {"reason": "pick_one_group", "user_id": uid, "group_key": gkey, "paused_count": cnt},
            )

        return matched_alerts

    def get_metrics_snapshot(self) -> dict[str, Any]:
        avg_rtt = round(sum(self._recent_rtts) / len(self._recent_rtts), 1) if self._recent_rtts else 0.0
        return {
            **self.telemetry,
            "avg_rtt_ms": avg_rtt,
            "cached_sections_count": len(self.section_status),
            "buckets": [
                {
                    "roster": b.roster,
                    "subject": b.subject,
                    "weight": b.weight,
                    "watch_count": b.watch_count,
                    "last_polled_at": b.last_polled_at,
                    "last_rtt_ms": b.last_rtt_ms,
                }
                for b in sorted(self._buckets.values(), key=lambda x: (x.roster, x.subject))
            ],
        }
