"""Normalized provider models, errors, and AvailabilityProvider protocol."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


class RateLimitedError(Exception):
    """Raised when an upstream API signals HTTP 429 rate limiting."""

    def __init__(self, retry_after_sec: float = 15.0, message: str = "Upstream rate limited") -> None:
        super().__init__(message)
        self.retry_after_sec = retry_after_sec


class UpstreamUnavailableError(Exception):
    """Raised on upstream 5xx or transport failure."""

    def __init__(self, status_code: int = 0, message: str = "Upstream unavailable") -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(slots=True)
class RosterRecord:
    slug: str
    descr: str
    is_default: bool = False
    archive_mode: bool = False
    strm: str = ""
    last_modified_dttm: str = ""


@dataclass(slots=True)
class SubjectRecord:
    value: str
    descr: str


@dataclass(slots=True)
class SectionRecord:
    class_nbr: int
    enroll_group_idx: int
    ssr_component: str
    section: str
    open_status: str
    components_required: list[str] = field(default_factory=list)
    meetings_summary: str = ""
    instructors_summary: str = ""
    campus: str = ""
    instruction_mode: str = ""


@dataclass(slots=True)
class CourseRecord:
    roster: str
    subject: str
    catalog_nbr: str
    title_short: str
    title_long: str
    description: str
    crse_id: int | None
    enroll_groups: list[dict[str, Any]]
    sections: list[SectionRecord]
    acad_career: str = ""
    acad_group: str = ""
    catalog_prereq: str = ""
    catalog_coreq: str = ""
    catalog_forbidden_overlaps: str = ""
    crse_attrs: list[dict[str, Any]] = field(default_factory=list)
    catalog_num: int = 0
    units_min: float = 0.0
    units_max: float = 0.0
    has_letter_grade: bool = True
    crosslists: list[str] = field(default_factory=list)
    components: list[str] = field(default_factory=list)


@dataclass(slots=True)
class FetchResult:
    courses: list[CourseRecord]
    rtt_ms: int
    payload_bytes: int


class AvailabilityProvider(Protocol):
    """Pluggable provider contract for fetching university rosters and availability."""

    async def fetch_rosters(self) -> list[RosterRecord]: ...

    async def fetch_subjects(self, roster: str) -> list[SubjectRecord]: ...

    async def fetch_subject_classes(self, roster: str, subject: str) -> FetchResult: ...

    async def close(self) -> None: ...
