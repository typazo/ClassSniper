"""Cornell Class Roster API v2.0 client with warm HTTP/2 pool and orjson parsing."""

from __future__ import annotations

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


def parse_cornell_classes_payload(raw_bytes: bytes, roster: str) -> list[CourseRecord]:
    """Parse Cornell /search/classes.json response bytes into normalized CourseRecord items."""
    payload = orjson.loads(raw_bytes)
    if payload.get("status") != "success":
        raise UpstreamUnavailableError(message=f"Unexpected Cornell API status: {payload.get('status')}")

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
        crse_id = int(crse_id_raw) if crse_id_raw is not None else None

        raw_egs = cls.get("enrollGroups") or []
        sections: list[SectionRecord] = []

        for eg_idx, eg in enumerate(raw_egs):
            req_comps = [str(c).strip().upper() for c in (eg.get("componentsRequired") or []) if c]
            for sec in eg.get("classSections") or []:
                class_nbr_raw = sec.get("classNbr")
                if class_nbr_raw is None:
                    continue
                class_nbr = int(class_nbr_raw)
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
                        campus=str(sec.get("campus") or "").strip(),
                        instruction_mode=str(sec.get("instrModeDescrshort") or sec.get("instructionMode") or "").strip(),
                    )
                )

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
        payload = orjson.loads(raw)
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
        payload = orjson.loads(raw)
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
