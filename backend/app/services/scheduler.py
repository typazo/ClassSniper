"""Scheduler persistence, structured meeting normalization, and shareable read-only views."""

from __future__ import annotations

import json
import re
import secrets
from typing import Any, Optional

import orjson

from app.config import Settings
from app.db import Database
from app.providers.cornell import is_ithaca_or_virtual_section
from app.services.catalog import CatalogSyncService
from app.services.insights import build_external_links, normalize_instructor_query

_TIME_RE = re.compile(r"^\s*(\d{1,2}):(\d{2})\s*([AP]M)?\s*$", re.IGNORECASE)
_SUMMARY_SLOT_RE = re.compile(
    r"^\s*([A-Za-z]+)?\s*(\d{1,2}:\d{2}\s*[AP]M)\s*-\s*(\d{1,2}:\d{2}\s*[AP]M)(?:\s*\(([^)]+)\))?\s*$",
    re.IGNORECASE,
)
_WEEKDAY_ORDER = ("M", "T", "W", "R", "F", "Sa", "Su")
_WEEKDAY_RANK = {day: idx for idx, day in enumerate(_WEEKDAY_ORDER)}


def parse_time_to_minutes(raw: str) -> Optional[int]:
    """Convert Cornell time strings like '10:10AM' or '01:25PM' to minutes since midnight."""
    if not raw:
        return None
    m = _TIME_RE.match(raw)
    if not m:
        return None
    hour = int(m.group(1))
    minute = int(m.group(2))
    ampm = (m.group(3) or "").upper()
    if minute < 0 or minute >= 60:
        return None
    if ampm:
        if hour < 1 or hour > 12:
            return None
        if ampm == "AM":
            hour = 0 if hour == 12 else hour
        else:
            hour = 12 if hour == 12 else hour + 12
    elif hour < 0 or hour > 23:
        return None
    return hour * 60 + minute


def parse_pattern_days(pattern: str) -> list[str]:
    """Parse Cornell meeting patterns like 'MWF', 'TR', 'Sa', 'Su' into canonical day codes."""
    raw = (pattern or "").strip()
    if not raw:
        return []
    upper = raw.upper()
    if upper in {"TBA", "ARR", "NONE"}:
        return []

    days: set[str] = set()
    i = 0
    while i < len(raw):
        two = raw[i : i + 2].lower()
        if two == "su":
            days.add("Su")
            i += 2
            continue
        if two == "sa":
            days.add("Sa")
            i += 2
            continue
        ch = raw[i].upper()
        if ch in {"M", "T", "W", "R", "F"}:
            days.add(ch)
        elif ch == "S":
            days.add("Sa")
        i += 1
    return sorted(days, key=lambda d: _WEEKDAY_RANK[d])


def _extract_instructors(raw_instructors: Any) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for instr in raw_instructors or []:
        if not isinstance(instr, dict):
            continue
        first = str(instr.get("firstName") or "").strip()
        last = str(instr.get("lastName") or "").strip()
        full = " ".join(p for p in (first, last) if p)
        if full and full not in seen:
            seen.add(full)
            names.append(full)
    return names


def _parse_summary_fallback_meetings(summary: str, instructors_summary: str) -> list[dict[str, Any]]:
    """Fallback parser when raw enrollGroups JSON lacks classSections (e.g. compact test fixtures)."""
    text = (summary or "").strip()
    if not text or text.upper() == "TBA":
        return []
    instr_list = [
        name.strip()
        for name in (instructors_summary or "").split(",")
        if name.strip() and name.strip().lower() != "staff"
    ]
    meetings: list[dict[str, Any]] = []
    for part in text.split(";"):
        m = _SUMMARY_SLOT_RE.match(part.strip())
        if not m:
            continue
        pattern = (m.group(1) or "").strip()
        time_start = m.group(2).replace(" ", "").upper()
        time_end = m.group(3).replace(" ", "").upper()
        facility = (m.group(4) or "").strip()
        start_min = parse_time_to_minutes(time_start)
        end_min = parse_time_to_minutes(time_end)
        days = parse_pattern_days(pattern)
        if start_min is None or end_min is None or end_min <= start_min or not days:
            continue
        meetings.append(
            {
                "pattern": pattern,
                "days": days,
                "time_start": time_start,
                "time_end": time_end,
                "start_min": start_min,
                "end_min": end_min,
                "start_dt": "",
                "end_dt": "",
                "facility_descr": facility,
                "building_descr": facility,
                "instructors": instr_list,
            }
        )
    return meetings


def normalize_enroll_groups(
    raw_enroll_groups: list[dict[str, Any]],
    section_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Combine raw Cornell enrollGroups JSON with live roster_sections statuses into structured scheduler data."""
    live_by_nbr: dict[int, dict[str, Any]] = {}
    rows_by_eg: dict[int, list[dict[str, Any]]] = {}
    for row in section_rows:
        nbr = int(row["class_nbr"])
        live_by_nbr[nbr] = row
        eg_idx = int(row.get("enroll_group_idx") or 0)
        rows_by_eg.setdefault(eg_idx, []).append(row)

    normalized_groups: list[dict[str, Any]] = []
    seen_class_nbrs: set[int] = set()

    for eg_idx, raw_eg in enumerate(raw_enroll_groups or []):
        if not isinstance(raw_eg, dict):
            continue
        req_comps = [str(c).strip().upper() for c in (raw_eg.get("componentsRequired") or []) if c]
        u_min = raw_eg.get("unitsMinimum")
        u_max = raw_eg.get("unitsMaximum")
        units_min = float(u_min) if u_min not in (None, "") else 0.0
        units_max = float(u_max) if u_max not in (None, "") else units_min
        grading_basis = str(raw_eg.get("gradingBasis") or "").strip().upper()
        session_code = str(raw_eg.get("sessionCode") or "").strip().upper()
        crosslists = []
        for comb in raw_eg.get("simpleCombinations") or []:
            if isinstance(comb, dict):
                subj = str(comb.get("subject") or "").strip().upper()
                nbr = str(comb.get("catalogNbr") or "").strip()
                if subj and nbr:
                    crosslists.append(f"{subj} {nbr}")

        sections_out: list[dict[str, Any]] = []
        raw_sections = raw_eg.get("classSections") or []
        if raw_sections:
            for raw_sec in raw_sections:
                nbr_raw = raw_sec.get("classNbr")
                if nbr_raw is None:
                    continue
                class_nbr = int(nbr_raw)
                seen_class_nbrs.add(class_nbr)
                live = live_by_nbr.get(class_nbr)
                open_status = str(
                    (live["open_status"] if live else raw_sec.get("openStatus")) or "C"
                ).strip().upper()
                campus = str((live["campus"] if live else raw_sec.get("campus")) or "").strip().upper()
                location = str((live["location"] if live else raw_sec.get("location")) or "").strip().upper()
                location_descr = str(
                    (live["location_descr"] if live else raw_sec.get("locationDescr")) or ""
                ).strip()
                instruction_mode = str(
                    (live["instruction_mode"] if live else raw_sec.get("instrModeDescrshort") or raw_sec.get("instructionMode"))
                    or ""
                ).strip()

                meetings_out: list[dict[str, Any]] = []
                all_instructors: list[str] = []
                seen_instr: set[str] = set()
                for mtg in raw_sec.get("meetings") or []:
                    if not isinstance(mtg, dict):
                        continue
                    pattern = str(mtg.get("pattern") or "").strip()
                    days = parse_pattern_days(pattern)
                    t_start = str(mtg.get("timeStart") or "").strip()
                    t_end = str(mtg.get("timeEnd") or "").strip()
                    start_min = parse_time_to_minutes(t_start)
                    end_min = parse_time_to_minutes(t_end)
                    facility = str(mtg.get("facilityDescr") or "").strip()
                    bldg_descr = str(mtg.get("bldgDescr") or facility).strip()
                    mtg_instrs = _extract_instructors(mtg.get("instructors"))
                    for name in mtg_instrs:
                        if name not in seen_instr:
                            seen_instr.add(name)
                            all_instructors.append(name)

                    if days and start_min is not None and end_min is not None and end_min > start_min:
                        meetings_out.append(
                            {
                                "pattern": pattern,
                                "days": days,
                                "time_start": t_start,
                                "time_end": t_end,
                                "start_min": start_min,
                                "end_min": end_min,
                                "start_dt": str(mtg.get("startDt") or "").strip(),
                                "end_dt": str(mtg.get("endDt") or "").strip(),
                                "facility_descr": facility,
                                "building_descr": bldg_descr,
                                "instructors": mtg_instrs,
                            }
                        )

                meetings_summary = (
                    str(live["meetings_summary"])
                    if live and live.get("meetings_summary")
                    else "TBA"
                )
                instructors_summary = (
                    str(live["instructors_summary"])
                    if live and live.get("instructors_summary")
                    else (", ".join(all_instructors) or "Staff")
                )

                sections_out.append(
                    {
                        "class_nbr": class_nbr,
                        "enroll_group_idx": eg_idx,
                        "ssr_component": str(raw_sec.get("ssrComponent") or "").strip().upper(),
                        "section": str(raw_sec.get("section") or "").strip(),
                        "open_status": open_status,
                        "components_required": req_comps,
                        "meetings_summary": meetings_summary,
                        "instructors_summary": instructors_summary,
                        "instructors": all_instructors,
                        "campus": campus,
                        "location": location,
                        "location_descr": location_descr,
                        "instruction_mode": instruction_mode,
                        "is_ithaca_or_virtual": is_ithaca_or_virtual_section(
                            campus=campus,
                            location=location,
                            instruction_mode=instruction_mode,
                        ),
                        "topic_description": str(raw_sec.get("topicDescription") or "").strip(),
                        "updated_at": live.get("updated_at") if live else None,
                        "meetings": meetings_out,
                    }
                )
        else:
            for live in rows_by_eg.get(eg_idx, []):
                class_nbr = int(live["class_nbr"])
                seen_class_nbrs.add(class_nbr)
                meetings_out = _parse_summary_fallback_meetings(
                    str(live.get("meetings_summary") or ""),
                    str(live.get("instructors_summary") or ""),
                )
                instrs = [
                    n.strip()
                    for n in str(live.get("instructors_summary") or "").split(",")
                    if n.strip() and n.strip().lower() != "staff"
                ]
                campus = str(live.get("campus") or "")
                location = str(live.get("location") or "")
                instruction_mode = str(live.get("instruction_mode") or "")
                sections_out.append(
                    {
                        "class_nbr": class_nbr,
                        "enroll_group_idx": eg_idx,
                        "ssr_component": str(live.get("ssr_component") or "").strip().upper(),
                        "section": str(live.get("section") or "").strip(),
                        "open_status": str(live.get("open_status") or "C").strip().upper(),
                        "components_required": req_comps,
                        "meetings_summary": str(live.get("meetings_summary") or "TBA"),
                        "instructors_summary": str(live.get("instructors_summary") or "Staff"),
                        "instructors": instrs,
                        "campus": campus,
                        "location": location,
                        "location_descr": str(live.get("location_descr") or ""),
                        "instruction_mode": instruction_mode,
                        "is_ithaca_or_virtual": is_ithaca_or_virtual_section(
                            campus=campus,
                            location=location,
                            instruction_mode=instruction_mode,
                        ),
                        "topic_description": "",
                        "updated_at": live.get("updated_at"),
                        "meetings": meetings_out,
                    }
                )

        if not req_comps and sections_out:
            seen_comp: list[str] = []
            for sec in sections_out:
                if sec["ssr_component"] and sec["ssr_component"] not in seen_comp:
                    seen_comp.append(sec["ssr_component"])
            req_comps = seen_comp

        normalized_groups.append(
            {
                "enroll_group_idx": eg_idx,
                "components_required": req_comps,
                "units_min": units_min,
                "units_max": units_max,
                "grading_basis": grading_basis,
                "session_code": session_code,
                "crosslists": crosslists,
                "sections": sections_out,
            }
        )

    # Append any orphan live sections not present in raw enroll_groups
    for row in section_rows:
        class_nbr = int(row["class_nbr"])
        if class_nbr in seen_class_nbrs:
            continue
        eg_idx = int(row.get("enroll_group_idx") or 0)
        while len(normalized_groups) <= eg_idx:
            normalized_groups.append(
                {
                    "enroll_group_idx": len(normalized_groups),
                    "components_required": [],
                    "units_min": 0.0,
                    "units_max": 0.0,
                    "grading_basis": "",
                    "session_code": "",
                    "crosslists": [],
                    "sections": [],
                }
            )
        campus = str(row.get("campus") or "")
        location = str(row.get("location") or "")
        instruction_mode = str(row.get("instruction_mode") or "")
        normalized_groups[eg_idx]["sections"].append(
            {
                "class_nbr": class_nbr,
                "enroll_group_idx": eg_idx,
                "ssr_component": str(row.get("ssr_component") or "").strip().upper(),
                "section": str(row.get("section") or "").strip(),
                "open_status": str(row.get("open_status") or "C").strip().upper(),
                "components_required": json.loads(row.get("components_required_json") or "[]"),
                "meetings_summary": str(row.get("meetings_summary") or "TBA"),
                "instructors_summary": str(row.get("instructors_summary") or "Staff"),
                "instructors": [],
                "campus": campus,
                "location": location,
                "location_descr": str(row.get("location_descr") or ""),
                "instruction_mode": instruction_mode,
                "is_ithaca_or_virtual": is_ithaca_or_virtual_section(
                    campus=campus,
                    location=location,
                    instruction_mode=instruction_mode,
                ),
                "topic_description": "",
                "updated_at": row.get("updated_at"),
                "meetings": _parse_summary_fallback_meetings(
                    str(row.get("meetings_summary") or ""),
                    str(row.get("instructors_summary") or ""),
                ),
            }
        )

    return normalized_groups


def _pick_default_sections(enroll_groups: list[dict[str, Any]]) -> list[int]:
    """Select one sensible default section per required component from the first available enrollGroup."""
    if not enroll_groups:
        return []
    # Prefer an enrollGroup containing Ithaca/virtual sections and open seats
    ranked_groups = sorted(
        enroll_groups,
        key=lambda eg: (
            0 if any(s.get("is_ithaca_or_virtual") for s in eg["sections"]) else 1,
            0 if any(s.get("open_status") == "O" for s in eg["sections"]) else 1,
            eg["enroll_group_idx"],
        ),
    )
    eg = ranked_groups[0]
    secs = eg.get("sections") or []
    if not secs:
        return []
    req_comps = eg.get("components_required") or []
    if not req_comps:
        req_comps = list(dict.fromkeys(s["ssr_component"] for s in secs if s.get("ssr_component")))

    picked: list[int] = []
    for comp in req_comps:
        matching = [s for s in secs if s.get("ssr_component") == comp]
        if not matching:
            continue
        matching.sort(
            key=lambda s: (
                0 if s.get("is_ithaca_or_virtual") else 1,
                0 if s.get("open_status") == "O" else (1 if s.get("open_status") == "W" else 2),
                s["class_nbr"],
            )
        )
        picked.append(int(matching[0]["class_nbr"]))
    return picked


def _decode_int_list(raw: Any) -> list[int]:
    if isinstance(raw, list):
        return [int(x) for x in raw]
    if isinstance(raw, str) and raw:
        try:
            loaded = json.loads(raw)
            if isinstance(loaded, list):
                return [int(x) for x in loaded]
        except (ValueError, TypeError):
            pass
    return []


def _decode_str_list(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return [str(x) for x in raw]
    if isinstance(raw, str) and raw:
        try:
            loaded = json.loads(raw)
            if isinstance(loaded, list):
                return [str(x) for x in loaded]
        except ValueError:
            pass
    return []


class SchedulerService:
    """Manages user course schedules, blocked times, hydration, and opt-in sharing."""

    def __init__(self, db: Database, catalog: CatalogSyncService, settings: Settings) -> None:
        self.db = db
        self.catalog = catalog
        self.settings = settings

    def _build_share_url(self, token: Optional[str], share_enabled: bool) -> Optional[str]:
        if not share_enabled or not token:
            return None
        origin = (self.settings.app_origin or "").rstrip("/")
        if origin:
            return f"{origin}/?share={token}"
        return f"/?share={token}"

    async def list_schedules(self, user_id: int, roster: str) -> list[dict[str, Any]]:
        roster_u = roster.upper()
        rows = await self.db.fetch_all(
            """
            SELECT s.id, s.roster, s.name, s.is_active, s.share_enabled, s.share_token,
                   s.created_at, s.updated_at,
                   (SELECT COUNT(*) FROM schedule_courses sc WHERE sc.schedule_id = s.id) AS course_count
            FROM schedules s
            WHERE s.user_id = ? AND s.roster = ?
            ORDER BY s.is_active DESC, s.id ASC
            """,
            (user_id, roster_u),
        )
        if not rows:
            async with self.db.write_tx() as conn:
                cur = await conn.execute(
                    """
                    INSERT INTO schedules (user_id, roster, name, is_active)
                    VALUES (?, ?, 'Main Schedule', 1)
                    """,
                    (user_id, roster_u),
                )
                sched_id = cur.lastrowid
            rows = await self.db.fetch_all(
                """
                SELECT s.id, s.roster, s.name, s.is_active, s.share_enabled, s.share_token,
                       s.created_at, s.updated_at, 0 AS course_count
                FROM schedules s
                WHERE s.id = ?
                """,
                (sched_id,),
            )

        out: list[dict[str, Any]] = []
        for r in rows:
            share_enabled = bool(r["share_enabled"])
            out.append(
                {
                    "id": int(r["id"]),
                    "roster": str(r["roster"]),
                    "name": str(r["name"]),
                    "is_active": bool(r["is_active"]),
                    "share_enabled": share_enabled,
                    "share_token": r["share_token"] if share_enabled else None,
                    "share_url": self._build_share_url(r["share_token"], share_enabled),
                    "course_count": int(r.get("course_count") or 0),
                    "created_at": r["created_at"],
                    "updated_at": r["updated_at"],
                }
            )
        return out

    async def _get_owned_schedule(self, schedule_id: int, user_id: int) -> Optional[dict[str, Any]]:
        return await self.db.fetch_one(
            "SELECT * FROM schedules WHERE id = ? AND user_id = ?",
            (schedule_id, user_id),
        )

    async def create_schedule(
        self,
        user_id: int,
        roster: str,
        name: str,
        duplicate_from_id: Optional[int] = None,
    ) -> dict[str, Any]:
        roster_u = roster.upper()
        clean_name = name.strip() or "New Schedule"
        source_courses: list[dict[str, Any]] = []
        source_blocks: list[dict[str, Any]] = []
        if duplicate_from_id is not None:
            src = await self._get_owned_schedule(duplicate_from_id, user_id)
            if src is None:
                raise ValueError("Source schedule not found")
            if str(src["roster"]).upper() != roster_u:
                raise ValueError("Cannot duplicate a schedule from a different roster")
            source_courses = await self.db.fetch_all(
                "SELECT * FROM schedule_courses WHERE schedule_id = ? ORDER BY sort_order ASC, id ASC",
                (duplicate_from_id,),
            )
            source_blocks = await self.db.fetch_all(
                "SELECT * FROM schedule_blocks WHERE schedule_id = ? ORDER BY id ASC",
                (duplicate_from_id,),
            )

        async with self.db.write_tx() as conn:
            await conn.execute(
                "UPDATE schedules SET is_active = 0 WHERE user_id = ? AND roster = ?",
                (user_id, roster_u),
            )
            cur = await conn.execute(
                """
                INSERT INTO schedules (user_id, roster, name, is_active)
                VALUES (?, ?, ?, 1)
                """,
                (user_id, roster_u, clean_name),
            )
            new_id = int(cur.lastrowid)
            for idx, c in enumerate(source_courses):
                await conn.execute(
                    """
                    INSERT INTO schedule_courses (
                        schedule_id, subject, catalog_nbr, enabled, selected_units,
                        selected_class_nbrs_json, locked_class_nbrs_json, color_idx, sort_order
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        new_id,
                        c["subject"],
                        c["catalog_nbr"],
                        c["enabled"],
                        c["selected_units"],
                        c["selected_class_nbrs_json"],
                        c["locked_class_nbrs_json"],
                        c["color_idx"],
                        idx,
                    ),
                )
            for b in source_blocks:
                await conn.execute(
                    """
                    INSERT INTO schedule_blocks (schedule_id, label, days_json, start_min, end_min, enabled)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (new_id, b["label"], b["days_json"], b["start_min"], b["end_min"], b["enabled"]),
                )

        return await self.hydrate_schedule(new_id, user_id=user_id)

    async def update_schedule(
        self,
        schedule_id: int,
        user_id: int,
        name: Optional[str] = None,
        is_active: Optional[bool] = None,
        share_enabled: Optional[bool] = None,
        regenerate_share_token: Optional[bool] = None,
    ) -> Optional[dict[str, Any]]:
        sched = await self._get_owned_schedule(schedule_id, user_id)
        if sched is None:
            return None

        new_name = name.strip() if name is not None else str(sched["name"])
        new_share_enabled = bool(sched["share_enabled"]) if share_enabled is None else bool(share_enabled)
        new_token = sched["share_token"]
        if regenerate_share_token or (new_share_enabled and not new_token):
            new_token = secrets.token_urlsafe(16)

        async with self.db.write_tx() as conn:
            if is_active:
                await conn.execute(
                    "UPDATE schedules SET is_active = 0 WHERE user_id = ? AND roster = ?",
                    (user_id, sched["roster"]),
                )
            new_active = 1 if is_active else (0 if is_active is False else int(sched["is_active"]))
            await conn.execute(
                """
                UPDATE schedules
                SET name = ?,
                    is_active = ?,
                    share_enabled = ?,
                    share_token = ?,
                    updated_at = datetime('now')
                WHERE id = ? AND user_id = ?
                """,
                (new_name, new_active, 1 if new_share_enabled else 0, new_token, schedule_id, user_id),
            )
        return await self.hydrate_schedule(schedule_id, user_id=user_id)

    async def delete_schedule(self, schedule_id: int, user_id: int) -> bool:
        sched = await self._get_owned_schedule(schedule_id, user_id)
        if sched is None:
            return False
        async with self.db.write_tx() as conn:
            await conn.execute("DELETE FROM schedules WHERE id = ? AND user_id = ?", (schedule_id, user_id))
            if sched["is_active"]:
                nxt = await conn.execute(
                    "SELECT id FROM schedules WHERE user_id = ? AND roster = ? ORDER BY id ASC LIMIT 1",
                    (user_id, sched["roster"]),
                )
                row = await nxt.fetchone()
                if row is not None:
                    await conn.execute("UPDATE schedules SET is_active = 1 WHERE id = ?", (row["id"],))
        return True

    async def add_course(
        self,
        schedule_id: int,
        user_id: int,
        subject: str,
        catalog_nbr: str,
        enabled: bool = True,
        selected_units: Optional[float] = None,
        selected_class_nbrs: Optional[list[int]] = None,
        locked_class_nbrs: Optional[list[int]] = None,
        color_idx: Optional[int] = None,
    ) -> dict[str, Any]:
        sched = await self._get_owned_schedule(schedule_id, user_id)
        if sched is None:
            raise LookupError("Schedule not found")
        roster_u = str(sched["roster"]).upper()
        subject_u = subject.strip().upper()
        nbr_clean = catalog_nbr.strip()

        existing = await self.db.fetch_one(
            """
            SELECT id FROM schedule_courses
            WHERE schedule_id = ? AND subject = ? AND catalog_nbr = ?
            """,
            (schedule_id, subject_u, nbr_clean),
        )
        if existing is not None:
            raise FileExistsError(f"{subject_u} {nbr_clean} is already in this schedule")

        meta = await self.db.fetch_one(
            """
            SELECT enroll_groups_json, units_min, units_max
            FROM courses_meta
            WHERE roster = ? AND subject = ? AND catalog_nbr = ?
            """,
            (roster_u, subject_u, nbr_clean),
        )
        if meta is None:
            await self.catalog.ensure_subject_synced(roster_u, subject_u)
            meta = await self.db.fetch_one(
                """
                SELECT enroll_groups_json, units_min, units_max
                FROM courses_meta
                WHERE roster = ? AND subject = ? AND catalog_nbr = ?
                """,
                (roster_u, subject_u, nbr_clean),
            )
        if meta is None:
            raise LookupError(f"Course {subject_u} {nbr_clean} not found in {roster_u}")

        sec_rows = await self.db.fetch_all(
            """
            SELECT class_nbr, enroll_group_idx, ssr_component, section, open_status,
                   components_required_json, meetings_summary, instructors_summary,
                   campus, location, location_descr, instruction_mode, updated_at
            FROM roster_sections
            WHERE roster = ? AND subject = ? AND catalog_nbr = ?
            ORDER BY enroll_group_idx ASC, class_nbr ASC
            """,
            (roster_u, subject_u, nbr_clean),
        )
        raw_egs = orjson.loads(meta["enroll_groups_json"]) if meta.get("enroll_groups_json") else []
        norm_egs = normalize_enroll_groups(raw_egs, sec_rows)

        if selected_class_nbrs is None:
            chosen_nbrs = _pick_default_sections(norm_egs)
        else:
            valid_nbrs = {int(s["class_nbr"]) for eg in norm_egs for s in eg["sections"]}
            chosen_nbrs = [int(n) for n in selected_class_nbrs if int(n) in valid_nbrs]

        chosen_locked = [int(n) for n in (locked_class_nbrs or []) if int(n) in chosen_nbrs]
        eff_units = selected_units
        if eff_units is None:
            u_max = float(meta.get("units_max") or 0.0)
            u_min = float(meta.get("units_min") or 0.0)
            eff_units = u_max if u_max > 0 else u_min

        count_row = await self.db.fetch_one(
            "SELECT COUNT(*) AS cnt, COALESCE(MAX(sort_order), -1) AS max_sort FROM schedule_courses WHERE schedule_id = ?",
            (schedule_id,),
        )
        cnt = int(count_row["cnt"]) if count_row else 0
        next_sort = (int(count_row["max_sort"]) + 1) if count_row else 0
        eff_color = color_idx if color_idx is not None else (cnt % 10)

        async with self.db.write_tx() as conn:
            await conn.execute(
                """
                INSERT INTO schedule_courses (
                    schedule_id, subject, catalog_nbr, enabled, selected_units,
                    selected_class_nbrs_json, locked_class_nbrs_json, color_idx, sort_order
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    schedule_id,
                    subject_u,
                    nbr_clean,
                    1 if enabled else 0,
                    eff_units,
                    json.dumps(chosen_nbrs),
                    json.dumps(chosen_locked),
                    eff_color,
                    next_sort,
                ),
            )
            await conn.execute(
                "UPDATE schedules SET updated_at = datetime('now') WHERE id = ?",
                (schedule_id,),
            )

        return await self.hydrate_schedule(schedule_id, user_id=user_id)

    async def update_course(
        self,
        schedule_id: int,
        item_id: int,
        user_id: int,
        enabled: Optional[bool] = None,
        selected_units: Optional[float] = None,
        selected_class_nbrs: Optional[list[int]] = None,
        locked_class_nbrs: Optional[list[int]] = None,
        color_idx: Optional[int] = None,
    ) -> Optional[dict[str, Any]]:
        sched = await self._get_owned_schedule(schedule_id, user_id)
        if sched is None:
            return None
        item = await self.db.fetch_one(
            "SELECT * FROM schedule_courses WHERE id = ? AND schedule_id = ?",
            (item_id, schedule_id),
        )
        if item is None:
            return None

        new_enabled = bool(item["enabled"]) if enabled is None else bool(enabled)
        new_units = item["selected_units"] if selected_units is None else float(selected_units)
        new_selected = (
            _decode_int_list(item["selected_class_nbrs_json"])
            if selected_class_nbrs is None
            else [int(x) for x in selected_class_nbrs]
        )
        new_locked = (
            _decode_int_list(item["locked_class_nbrs_json"])
            if locked_class_nbrs is None
            else [int(x) for x in locked_class_nbrs]
        )
        # Keep locked class numbers aligned with selected if sections were swapped
        selected_set = set(new_selected)
        new_locked = [n for n in new_locked if n in selected_set]
        new_color = int(item["color_idx"]) if color_idx is None else int(color_idx)

        async with self.db.write_tx() as conn:
            await conn.execute(
                """
                UPDATE schedule_courses
                SET enabled = ?,
                    selected_units = ?,
                    selected_class_nbrs_json = ?,
                    locked_class_nbrs_json = ?,
                    color_idx = ?
                WHERE id = ? AND schedule_id = ?
                """,
                (
                    1 if new_enabled else 0,
                    new_units,
                    json.dumps(new_selected),
                    json.dumps(new_locked),
                    new_color,
                    item_id,
                    schedule_id,
                ),
            )
            await conn.execute(
                "UPDATE schedules SET updated_at = datetime('now') WHERE id = ?",
                (schedule_id,),
            )
        return await self.hydrate_schedule(schedule_id, user_id=user_id)

    async def apply_generated(
        self,
        schedule_id: int,
        user_id: int,
        updates: list[tuple[int, list[int]]],
    ) -> Optional[dict[str, Any]]:
        sched = await self._get_owned_schedule(schedule_id, user_id)
        if sched is None:
            return None

        async with self.db.write_tx() as conn:
            for item_id, nbrs in updates:
                clean_nbrs = [int(x) for x in nbrs]
                await conn.execute(
                    """
                    UPDATE schedule_courses
                    SET selected_class_nbrs_json = ?
                    WHERE id = ? AND schedule_id = ?
                    """,
                    (json.dumps(clean_nbrs), item_id, schedule_id),
                )
            await conn.execute(
                "UPDATE schedules SET updated_at = datetime('now') WHERE id = ?",
                (schedule_id,),
            )
        return await self.hydrate_schedule(schedule_id, user_id=user_id)

    async def remove_course(self, schedule_id: int, item_id: int, user_id: int) -> Optional[dict[str, Any]]:
        sched = await self._get_owned_schedule(schedule_id, user_id)
        if sched is None:
            return None
        async with self.db.write_tx() as conn:
            cur = await conn.execute(
                "DELETE FROM schedule_courses WHERE id = ? AND schedule_id = ?",
                (item_id, schedule_id),
            )
            if cur.rowcount == 0:
                return None
            await conn.execute(
                "UPDATE schedules SET updated_at = datetime('now') WHERE id = ?",
                (schedule_id,),
            )
        return await self.hydrate_schedule(schedule_id, user_id=user_id)

    async def add_block(
        self,
        schedule_id: int,
        user_id: int,
        label: str,
        days: list[str],
        start_min: int,
        end_min: int,
        enabled: bool = True,
    ) -> Optional[dict[str, Any]]:
        sched = await self._get_owned_schedule(schedule_id, user_id)
        if sched is None:
            return None
        if end_min <= start_min:
            raise ValueError("End time must be after start time")
        clean_days = sorted(set(days), key=lambda d: _WEEKDAY_RANK.get(d, 99))
        async with self.db.write_tx() as conn:
            await conn.execute(
                """
                INSERT INTO schedule_blocks (schedule_id, label, days_json, start_min, end_min, enabled)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (schedule_id, label.strip() or "Busy", json.dumps(clean_days), start_min, end_min, 1 if enabled else 0),
            )
            await conn.execute(
                "UPDATE schedules SET updated_at = datetime('now') WHERE id = ?",
                (schedule_id,),
            )
        return await self.hydrate_schedule(schedule_id, user_id=user_id)

    async def update_block(
        self,
        schedule_id: int,
        block_id: int,
        user_id: int,
        label: Optional[str] = None,
        days: Optional[list[str]] = None,
        start_min: Optional[int] = None,
        end_min: Optional[int] = None,
        enabled: Optional[bool] = None,
    ) -> Optional[dict[str, Any]]:
        sched = await self._get_owned_schedule(schedule_id, user_id)
        if sched is None:
            return None
        blk = await self.db.fetch_one(
            "SELECT * FROM schedule_blocks WHERE id = ? AND schedule_id = ?",
            (block_id, schedule_id),
        )
        if blk is None:
            return None

        new_label = label.strip() if label is not None else str(blk["label"])
        new_days = (
            _decode_str_list(blk["days_json"])
            if days is None
            else sorted(set(days), key=lambda d: _WEEKDAY_RANK.get(d, 99))
        )
        new_start = int(blk["start_min"]) if start_min is None else int(start_min)
        new_end = int(blk["end_min"]) if end_min is None else int(end_min)
        if new_end <= new_start:
            raise ValueError("End time must be after start time")
        new_enabled = bool(blk["enabled"]) if enabled is None else bool(enabled)

        async with self.db.write_tx() as conn:
            await conn.execute(
                """
                UPDATE schedule_blocks
                SET label = ?, days_json = ?, start_min = ?, end_min = ?, enabled = ?
                WHERE id = ? AND schedule_id = ?
                """,
                (new_label, json.dumps(new_days), new_start, new_end, 1 if new_enabled else 0, block_id, schedule_id),
            )
            await conn.execute(
                "UPDATE schedules SET updated_at = datetime('now') WHERE id = ?",
                (schedule_id,),
            )
        return await self.hydrate_schedule(schedule_id, user_id=user_id)

    async def delete_block(self, schedule_id: int, block_id: int, user_id: int) -> Optional[dict[str, Any]]:
        sched = await self._get_owned_schedule(schedule_id, user_id)
        if sched is None:
            return None
        async with self.db.write_tx() as conn:
            cur = await conn.execute(
                "DELETE FROM schedule_blocks WHERE id = ? AND schedule_id = ?",
                (block_id, schedule_id),
            )
            if cur.rowcount == 0:
                return None
            await conn.execute(
                "UPDATE schedules SET updated_at = datetime('now') WHERE id = ?",
                (schedule_id,),
            )
        return await self.hydrate_schedule(schedule_id, user_id=user_id)

    async def get_shared_schedule(self, share_token: str) -> Optional[dict[str, Any]]:
        row = await self.db.fetch_one(
            """
            SELECT s.*, u.username AS owner_username
            FROM schedules s
            JOIN users u ON u.id = s.user_id
            WHERE s.share_token = ? AND s.share_enabled = 1
            """,
            (share_token.strip(),),
        )
        if row is None:
            return None
        payload = await self.hydrate_schedule(int(row["id"]), user_id=None, schedule_row=row)
        payload["owner_username"] = str(row["owner_username"])
        return payload

    async def hydrate_schedule(
        self,
        schedule_id: int,
        user_id: Optional[int],
        schedule_row: Optional[dict[str, Any]] = None,
        user: Optional[dict[str, Any]] = None,
    ) -> Optional[dict[str, Any]]:
        sched = schedule_row
        if sched is None:
            if user_id is not None:
                sched = await self._get_owned_schedule(schedule_id, user_id)
            else:
                sched = await self.db.fetch_one("SELECT * FROM schedules WHERE id = ?", (schedule_id,))
        if sched is None:
            return None

        roster_u = str(sched["roster"]).upper()
        share_enabled = bool(sched["share_enabled"])
        item_rows = await self.db.fetch_all(
            "SELECT * FROM schedule_courses WHERE schedule_id = ? ORDER BY sort_order ASC, id ASC",
            (schedule_id,),
        )
        block_rows = await self.db.fetch_all(
            "SELECT * FROM schedule_blocks WHERE schedule_id = ? ORDER BY id ASC",
            (schedule_id,),
        )

        # Resolve user prefs for CS/ILR eligibility & prereq evaluation (skip for anonymous shared views)
        cs_index = None
        ilr_index = None
        satisfied_set: set[str] = set()
        if user is not None:
            cs_index = await self.catalog.get_cs_requirements_index(roster_u)
            satisfied_set, _ = cs_index.expand_satisfied_courses(
                list(user.get("completed_courses") or []),
                include_implied=bool(user.get("include_implied_prereqs", True)),
            )
            if user.get("major_mode") == "ilr":
                ilr_index = await self.catalog.get_ilr_requirements_index(roster_u)
        elif user_id is not None:
            u_row = await self.db.fetch_one(
                "SELECT completed_courses_json, include_implied_prereqs, major_mode FROM users WHERE id = ?",
                (user_id,),
            )
            if u_row is not None:
                cs_index = await self.catalog.get_cs_requirements_index(roster_u)
                satisfied_set, _ = cs_index.expand_satisfied_courses(
                    _decode_str_list(u_row.get("completed_courses_json")),
                    include_implied=bool(u_row.get("include_implied_prereqs", 1)),
                )
                if u_row.get("major_mode") == "ilr":
                    ilr_index = await self.catalog.get_ilr_requirements_index(roster_u)

        courses_out: list[dict[str, Any]] = []
        for item in item_rows:
            subj = str(item["subject"]).upper()
            nbr = str(item["catalog_nbr"])
            meta = await self.db.fetch_one(
                """
                SELECT title_short, title_long, description, acad_career, acad_group,
                       catalog_prereq, catalog_coreq, catalog_forbidden_overlaps,
                       units_min, units_max, has_letter_grade, crosslists_json,
                       components_json, enroll_groups_json, updated_at
                FROM courses_meta
                WHERE roster = ? AND subject = ? AND catalog_nbr = ?
                """,
                (roster_u, subj, nbr),
            )
            sec_rows = await self.db.fetch_all(
                """
                SELECT class_nbr, enroll_group_idx, ssr_component, section, open_status,
                       components_required_json, meetings_summary, instructors_summary,
                       campus, location, location_descr, instruction_mode, updated_at
                FROM roster_sections
                WHERE roster = ? AND subject = ? AND catalog_nbr = ?
                ORDER BY enroll_group_idx ASC, class_nbr ASC
                """,
                (roster_u, subj, nbr),
            )
            raw_egs = orjson.loads(meta["enroll_groups_json"]) if (meta and meta.get("enroll_groups_json")) else []
            norm_egs = normalize_enroll_groups(raw_egs, sec_rows)
            is_fresh, eff_iso = await self.catalog._get_subject_freshness(roster_u, subj)

            # Read cached CU Reviews + RMP metrics locally (zero external network calls)
            cu_cache = await self.db.fetch_one(
                "SELECT payload_json, found FROM course_insights_cache WHERE subject = ? AND catalog_nbr = ?",
                (subj, nbr),
            )
            cu_summary: Optional[dict[str, Any]] = None
            if cu_cache and int(cu_cache.get("found") or 0) == 1:
                try:
                    cu_payload = orjson.loads(cu_cache["payload_json"])
                    cu_summary = {
                        "rating": cu_payload.get("rating"),
                        "difficulty": cu_payload.get("difficulty"),
                        "workload": cu_payload.get("workload"),
                        "review_count": cu_payload.get("review_count") or 0,
                    }
                except Exception:
                    cu_summary = None

            rmp_summary: dict[str, dict[str, Any]] = {}
            instr_names: set[str] = set()
            for eg in norm_egs:
                for sec in eg["sections"]:
                    for nm in sec.get("instructors") or []:
                        instr_names.add(nm)
            for nm in instr_names:
                cleaned_query, _, _ = normalize_instructor_query(nm)
                key = cleaned_query.lower() or nm.strip().lower()
                if not key:
                    continue
                rmp_row = await self.db.fetch_one(
                    "SELECT payload_json, found FROM rmp_instructor_cache WHERE name_key = ?",
                    (key,),
                )
                if rmp_row and int(rmp_row.get("found") or 0) == 1:
                    try:
                        rp = orjson.loads(rmp_row["payload_json"])
                        rmp_summary[nm] = {
                            "avg_rating": rp.get("avg_rating"),
                            "avg_difficulty": rp.get("avg_difficulty"),
                            "num_ratings": rp.get("num_ratings") or 0,
                            "rmp_url": rp.get("rmp_url") or "",
                        }
                    except Exception:
                        pass

            cs_elig_dict: Optional[dict[str, Any]] = None
            if cs_index is not None:
                prereq_eval = cs_index.evaluate_course_prereqs(subj, nbr, satisfied_set)
                cs_elig_dict = {
                    **cs_index.get(subj, nbr).to_dict(),
                    **prereq_eval,
                }

            ilr_elig_dict: Optional[dict[str, Any]] = None
            if ilr_index is not None:
                ilr_elig = ilr_index.get(subj, nbr)
                ilr_elig_dict = ilr_elig.to_dict() if ilr_elig is not None else None

            courses_out.append(
                {
                    "id": int(item["id"]),
                    "subject": subj,
                    "catalog_nbr": nbr,
                    "enabled": bool(item["enabled"]),
                    "selected_units": item["selected_units"],
                    "selected_class_nbrs": _decode_int_list(item["selected_class_nbrs_json"]),
                    "locked_class_nbrs": _decode_int_list(item["locked_class_nbrs_json"]),
                    "color_idx": int(item["color_idx"]),
                    "sort_order": int(item["sort_order"]),
                    "title_short": meta["title_short"] if meta else f"{subj} {nbr}",
                    "title_long": meta["title_long"] if meta else f"{subj} {nbr}",
                    "description": meta["description"] if meta else "",
                    "acad_career": meta["acad_career"] if meta else "",
                    "acad_group": meta["acad_group"] if meta else "",
                    "catalog_prereq": meta["catalog_prereq"] if meta else "",
                    "catalog_coreq": meta["catalog_coreq"] if meta else "",
                    "catalog_forbidden_overlaps": meta["catalog_forbidden_overlaps"] if meta else "",
                    "units_min": float(meta["units_min"]) if meta else 0.0,
                    "units_max": float(meta["units_max"]) if meta else 0.0,
                    "has_letter_grade": bool(meta["has_letter_grade"]) if meta else True,
                    "crosslists": _decode_str_list(meta["crosslists_json"]) if meta else [],
                    "components": _decode_str_list(meta["components_json"]) if meta else [],
                    "enroll_groups": norm_egs,
                    "external_links": build_external_links(roster_u, subj, nbr),
                    "cs_eligibility": cs_elig_dict,
                    "ilr_eligibility": ilr_elig_dict,
                    "cached_insights": cu_summary,
                    "cached_rmp": rmp_summary,
                    "subject_synced_at": eff_iso,
                    "status_is_stale": not is_fresh,
                }
            )

        blocks_out = [
            {
                "id": int(b["id"]),
                "label": str(b["label"]),
                "days": _decode_str_list(b["days_json"]),
                "start_min": int(b["start_min"]),
                "end_min": int(b["end_min"]),
                "enabled": bool(b["enabled"]),
            }
            for b in block_rows
        ]

        return {
            "schedule": {
                "id": int(sched["id"]),
                "roster": roster_u,
                "name": str(sched["name"]),
                "is_active": bool(sched["is_active"]),
                "share_enabled": share_enabled,
                "share_token": sched["share_token"] if (user_id is not None and share_enabled) else None,
                "share_url": self._build_share_url(sched["share_token"], share_enabled)
                if user_id is not None
                else None,
                "created_at": sched["created_at"],
                "updated_at": sched["updated_at"],
            },
            "courses": courses_out,
            "blocks": blocks_out,
        }
