"""Cornell Class Roster API v2.0 client with warm HTTP/2 pool and orjson parsing."""

from __future__ import annotations

import re
import time
from typing import Any, Optional

import httpx
import orjson

from app.providers.base import (
    CourseRecord,
    FetchResult,
    RateLimitedError,
    RosterRecord,
    SectionRecord,
    SubjectRecord,
    UpstreamUnavailableError,
)
from app.services.common import parse_catalog_num, to_float as _to_float

LETTER_GRADE_BASES: frozenset[str] = frozenset({"GRD", "GRI", "OPT", "OPI"})
ITHACA_LOCATIONS: frozenset[str] = frozenset({"ITH"})
ITHACA_FALLBACK_CAMPUSES: frozenset[str] = frozenset({"", "MAIN"})
VIRTUAL_INSTRUCTION_MODES: frozenset[str] = frozenset(
    {
        "OL",
        "AD",
        "DL-AD",
        "SD",
        "DL-SD",
        "ONLINE",
        "DISTANCE LEARNING-ONLINE",
        "DISTANCE LEARNING-ASYNCHRONOUS",
        "DISTANCE LEARNING-SYNCHRONOUS",
    }
)
VIRTUAL_ALLOWED_LOCATIONS: frozenset[str] = frozenset(
    {"", "ITH", "ONLINE", "VIRT", "VIRTUAL", "DIST", "REMOTE", "WEB"}
)


def is_virtual_instruction_mode(instruction_mode: str = "") -> bool:
    """Return True if instruction mode represents purely virtual delivery (OL, DL-AD, DL-SD)."""
    mode = (instruction_mode or "").strip().upper()
    return mode in VIRTUAL_INSTRUCTION_MODES or mode.startswith("DL-")


def is_ithaca_or_virtual_section(
    campus: str = "",
    location: str = "",
    instruction_mode: str = "",
) -> bool:
    """Return True if a section is based on the Ithaca campus or offered virtually without an off-campus cohort lock."""
    loc = (location or "").strip().upper()
    camp = (campus or "").strip().upper()

    if loc in ITHACA_LOCATIONS:
        return True
    if not loc and camp in ITHACA_FALLBACK_CAMPUSES:
        return True
    if is_virtual_instruction_mode(instruction_mode) and loc in VIRTUAL_ALLOWED_LOCATIONS:
        return True
    return False


def compute_course_derived_fields(
    catalog_nbr: str,
    enroll_groups: list[dict[str, Any]],
    sections: list[Any],
) -> dict[str, Any]:
    """Compute numeric level, credit bounds, letter-grade availability, crosslists, and components."""
    catalog_num = parse_catalog_num(catalog_nbr)
    mins: list[float] = []
    maxs: list[float] = []
    grading_bases: list[str] = []
    crosslists: list[str] = []
    seen_cross: set[str] = set()
    components: set[str] = set()

    for eg in enroll_groups or []:
        u_min = _to_float(eg.get("unitsMinimum"))
        u_max = _to_float(eg.get("unitsMaximum"))
        if u_min is not None:
            mins.append(u_min)
        if u_max is not None:
            maxs.append(u_max)
        elif u_min is not None:
            maxs.append(u_min)

        gb = str(eg.get("gradingBasis") or "").strip().upper()
        if gb:
            grading_bases.append(gb)

        for comb in eg.get("simpleCombinations") or []:
            c_subj = str(comb.get("subject") or "").strip().upper()
            c_nbr = str(comb.get("catalogNbr") or "").strip()
            if c_subj and c_nbr:
                code = f"{c_subj} {c_nbr}"
                if code not in seen_cross:
                    seen_cross.add(code)
                    crosslists.append(code)

        for raw_sec in eg.get("classSections") or []:
            comp = str(raw_sec.get("ssrComponent") or "").strip().upper()
            if comp:
                components.add(comp)

    for sec in sections or []:
        comp = getattr(sec, "ssr_component", None)
        if comp is None and isinstance(sec, dict):
            comp = sec.get("ssr_component") or sec.get("ssrComponent")
        if comp:
            components.add(str(comp).strip().upper())

    units_min = min(mins) if mins else 0.0
    units_max = max(maxs) if maxs else 0.0
    has_letter_grade = True if not grading_bases else any(gb in LETTER_GRADE_BASES for gb in grading_bases)

    return {
        "catalog_num": catalog_num,
        "units_min": units_min,
        "units_max": units_max,
        "has_letter_grade": has_letter_grade,
        "crosslists": crosslists,
        "components": sorted(components),
    }


def _format_meetings(meetings: list[dict[str, Any]]) -> tuple[str, str]:
    """Summarize meeting times and unique instructors cleanly."""
    meeting_parts: list[str] = []
    instructors: list[str] = []
    seen_instr: set[str] = set()

    for mtg in meetings:
        pattern = (mtg.get("pattern") or "").strip()
        start = (mtg.get("timeStart") or "").strip()
        end = (mtg.get("timeEnd") or "").strip()
        facility = (mtg.get("facilityDescr") or "").strip()
        slot = " ".join(p for p in [pattern, f"{start}-{end}" if start and end else start] if p)
        if facility:
            slot = f"{slot} ({facility})" if slot else facility
        if slot:
            meeting_parts.append(slot)

        for instr in mtg.get("instructors") or []:
            first = (instr.get("firstName") or "").strip()
            last = (instr.get("lastName") or "").strip()
            name = " ".join(p for p in [first, last] if p)
            if name and name not in seen_instr:
                seen_instr.add(name)
                instructors.append(name)

    return "; ".join(meeting_parts) or "TBA", ", ".join(instructors) or "Staff"


def _decode_cornell_json(raw_bytes: bytes) -> dict[str, Any]:
    try:
        payload = orjson.loads(raw_bytes)
    except Exception as exc:
        raise UpstreamUnavailableError(message=f"Invalid JSON from Cornell API: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("status") != "success":
        status_val = payload.get("status") if isinstance(payload, dict) else type(payload).__name__
        raise UpstreamUnavailableError(message=f"Unexpected Cornell API status: {status_val}")
    return payload


def parse_cornell_classes_payload(raw_bytes: bytes, roster: str) -> list[CourseRecord]:
    """Parse Cornell /search/classes.json response bytes into normalized CourseRecord items."""
    payload = _decode_cornell_json(raw_bytes)

    raw_classes = (payload.get("data") or {}).get("classes") or []
    courses: list[CourseRecord] = []

    for cls in raw_classes:
        subject = str(cls.get("subject") or "").strip().upper()
        catalog_nbr = str(cls.get("catalogNbr") or "").strip()
        if not subject or not catalog_nbr:
            continue

        title_short = str(cls.get("titleShort") or cls.get("titleLong") or "").strip()
        title_long = str(cls.get("titleLong") or title_short).strip()
        description = str(cls.get("description") or "").strip()
        crse_id_raw = cls.get("crseId")
        try:
            crse_id = int(crse_id_raw) if crse_id_raw is not None else None
        except (TypeError, ValueError):
            crse_id = None
        acad_career = str(cls.get("acadCareer") or "").strip().upper()
        acad_group = str(cls.get("acadGroup") or "").strip().upper()
        catalog_prereq = str(cls.get("catalogPrereq") or cls.get("catalogPrereqCoreq") or "").strip()
        catalog_coreq = str(cls.get("catalogCoreq") or "").strip()
        catalog_forbidden = str(cls.get("catalogForbiddenOverlaps") or "").strip()
        raw_attrs = cls.get("crseAttrValueGroups") or []
        crse_attrs = raw_attrs if isinstance(raw_attrs, list) else []

        raw_egs = cls.get("enrollGroups") or []
        sections: list[SectionRecord] = []

        for eg_idx, eg in enumerate(raw_egs):
            req_comps = [str(c).strip().upper() for c in (eg.get("componentsRequired") or []) if c]
            for sec in eg.get("classSections") or []:
                class_nbr_raw = sec.get("classNbr")
                if class_nbr_raw is None:
                    continue
                try:
                    class_nbr = int(class_nbr_raw)
                except (TypeError, ValueError):
                    continue
                meetings_summary, instructors_summary = _format_meetings(sec.get("meetings") or [])
                sections.append(
                    SectionRecord(
                        class_nbr=class_nbr,
                        enroll_group_idx=eg_idx,
                        ssr_component=str(sec.get("ssrComponent") or "").strip().upper(),
                        section=str(sec.get("section") or "").strip(),
                        open_status=str(sec.get("openStatus") or "C").strip().upper(),
                        components_required=req_comps,
                        meetings_summary=meetings_summary,
                        instructors_summary=instructors_summary,
                        campus=str(sec.get("campus") or "").strip().upper(),
                        location=str(sec.get("location") or "").strip().upper(),
                        location_descr=str(sec.get("locationDescr") or "").strip(),
                        instruction_mode=str(sec.get("instrModeDescrshort") or sec.get("instructionMode") or "").strip(),
                    )
                )

        derived = compute_course_derived_fields(catalog_nbr, raw_egs, sections)
        courses.append(
            CourseRecord(
                roster=roster.upper(),
                subject=subject,
                catalog_nbr=catalog_nbr,
                title_short=title_short,
                title_long=title_long,
                description=description,
                crse_id=crse_id,
                enroll_groups=raw_egs,
                sections=sections,
                acad_career=acad_career,
                acad_group=acad_group,
                catalog_prereq=catalog_prereq,
                catalog_coreq=catalog_coreq,
                catalog_forbidden_overlaps=catalog_forbidden,
                crse_attrs=crse_attrs,
                catalog_num=derived["catalog_num"],
                units_min=derived["units_min"],
                units_max=derived["units_max"],
                has_letter_grade=derived["has_letter_grade"],
                crosslists=derived["crosslists"],
                components=derived["components"],
            )
        )

    return courses


class CornellRosterApiProvider:
    """Persistent HTTP/2 client targeting classes.cornell.edu/api/2.0."""

    def __init__(
        self,
        base_url: str = "https://classes.cornell.edu/api/2.0",
        timeout_sec: float = 8.0,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            http2=True,
            timeout=httpx.Timeout(timeout_sec, connect=5.0),
            limits=httpx.Limits(max_connections=16, max_keepalive_connections=8, keepalive_expiry=120.0),
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "gzip, deflate",
                "User-Agent": "ClassSniper/0.1 (self-hosted)",
            },
        )

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _get_bytes(self, path: str, params: Optional[dict[str, str]] = None) -> tuple[bytes, int]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        started = time.perf_counter()
        try:
            resp = await self._client.get(url, params=params)
        except httpx.HTTPError as exc:
            raise UpstreamUnavailableError(message=f"HTTP error reaching Cornell API: {exc}") from exc

        rtt_ms = max(1, int((time.perf_counter() - started) * 1000))

        if resp.status_code == 429:
            retry_hdr = resp.headers.get("Retry-After", "")
            try:
                retry_after = max(5.0, float(retry_hdr))
            except ValueError:
                retry_after = 15.0
            raise RateLimitedError(retry_after_sec=retry_after)

        if resp.status_code >= 500:
            raise UpstreamUnavailableError(status_code=resp.status_code, message=f"Cornell API {resp.status_code}")

        if resp.status_code != 200:
            raise UpstreamUnavailableError(status_code=resp.status_code, message=f"Unexpected HTTP {resp.status_code}")

        return resp.content, rtt_ms

    async def fetch_rosters(self) -> list[RosterRecord]:
        raw, _ = await self._get_bytes("config/rosters.json")
        payload = _decode_cornell_json(raw)
        rows = (payload.get("data") or {}).get("rosters") or []
        return [
            RosterRecord(
                slug=str(r.get("slug") or "").strip().upper(),
                descr=str(r.get("descr") or r.get("slug") or "").strip(),
                is_default=str(r.get("isDefaultRoster") or "N").upper() == "Y",
                archive_mode=str(r.get("archiveMode") or "N").upper() == "Y",
                strm=str(r.get("strm") or "").strip(),
                last_modified_dttm=str(r.get("lastModifiedDttm") or "").strip(),
            )
            for r in rows
            if r.get("slug")
        ]

    async def fetch_subjects(self, roster: str) -> list[SubjectRecord]:
        raw, _ = await self._get_bytes("config/subjects.json", params={"roster": roster.upper()})
        payload = _decode_cornell_json(raw)
        rows = (payload.get("data") or {}).get("subjects") or []
        return [
            SubjectRecord(
                value=str(s.get("value") or "").strip().upper(),
                descr=str(s.get("descr") or s.get("value") or "").strip(),
            )
            for s in rows
            if s.get("value")
        ]

    async def fetch_subject_classes(self, roster: str, subject: str) -> FetchResult:
        raw, rtt_ms = await self._get_bytes(
            "search/classes.json",
            params={"roster": roster.upper(), "subject": subject.upper()},
        )
        courses = parse_cornell_classes_payload(raw, roster=roster.upper())
        return FetchResult(courses=courses, rtt_ms=rtt_ms, payload_bytes=len(raw))
