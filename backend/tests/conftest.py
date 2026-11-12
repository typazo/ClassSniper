"""Shared test fixtures and fake Cornell provider."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import AsyncIterator

import httpx
import pytest
import pytest_asyncio

from app.config import Settings
from app.main import create_app
from app.providers.base import (
    CourseRecord,
    FetchResult,
    RateLimitedError,
    RosterRecord,
    SectionRecord,
    SubjectRecord,
)


def make_sample_courses(
    lec_status: str = "C",
    dis202_status: str = "C",
    dis203_status: str = "C",
) -> list[CourseRecord]:
    return [
        CourseRecord(
            roster="SP27",
            subject="CS",
            catalog_nbr="2110",
            title_short="OO Prog & Data Structures",
            title_long="Object-Oriented Programming and Data Structures",
            description="Intermediate programming in a high-level language.",
            crse_id=351740,
            enroll_groups=[{"componentsRequired": ["LEC", "DIS"]}],
            sections=[
                SectionRecord(
                    class_nbr=6582,
                    enroll_group_idx=0,
                    ssr_component="LEC",
                    section="001",
                    open_status=lec_status,
                    components_required=["LEC", "DIS"],
                    meetings_summary="TR 10:10AM-11:25AM",
                    instructors_summary="Erasmo Tani",
                    campus="MAIN",
                    instruction_mode="In Person",
                ),
                SectionRecord(
                    class_nbr=6584,
                    enroll_group_idx=0,
                    ssr_component="DIS",
                    section="202",
                    open_status=dis202_status,
                    components_required=["LEC", "DIS"],
                    meetings_summary="W 01:25PM-02:40PM",
                    instructors_summary="Staff",
                    campus="MAIN",
                    instruction_mode="In Person",
                ),
                SectionRecord(
                    class_nbr=6585,
                    enroll_group_idx=0,
                    ssr_component="DIS",
                    section="203",
                    open_status=dis203_status,
                    components_required=["LEC", "DIS"],
                    meetings_summary="W 11:40AM-12:55PM",
                    instructors_summary="Staff",
                    campus="MAIN",
                    instruction_mode="In Person",
                ),
            ],
        )
    ]


class FakeCornellProvider:
    """In-memory deterministic provider for unit and API integration tests."""

    def __init__(self) -> None:
        self.rosters = [
            RosterRecord(slug="SP27", descr="Spring 2027", is_default=True, archive_mode=False, strm="2951"),
            RosterRecord(slug="FA26", descr="Fall 2026", is_default=False, archive_mode=False, strm="2937"),
        ]
        self.subjects = [
            SubjectRecord(value="CS", descr="Computer Science"),
            SubjectRecord(value="MATH", descr="Mathematics"),
        ]
        self.courses_by_bucket: dict[tuple[str, str], list[CourseRecord]] = {
            ("SP27", "CS"): make_sample_courses(),
            ("SP27", "MATH"): [
                CourseRecord(
                    roster="SP27",
                    subject="MATH",
                    catalog_nbr="2940",
                    title_short="Linear Algebra",
                    title_long="Linear Algebra for Engineers",
                    description="Linear systems, matrices, eigenvalues.",
                    crse_id=100200,
                    enroll_groups=[{"componentsRequired": ["LEC"]}],
                    sections=[
                        SectionRecord(
                            class_nbr=9001,
                            enroll_group_idx=0,
                            ssr_component="LEC",
                            section="001",
                            open_status="C",
                            components_required=["LEC"],
                            meetings_summary="MWF 09:05AM-09:55AM",
                            instructors_summary="Jane Doe",
                        )
                    ],
                )
            ],
        }
        self.raise_rate_limit = False

    async def fetch_rosters(self) -> list[RosterRecord]:
        return deepcopy(self.rosters)

    async def fetch_subjects(self, roster: str) -> list[SubjectRecord]:
        return deepcopy(self.subjects)

    async def fetch_subject_classes(self, roster: str, subject: str) -> FetchResult:
        if self.raise_rate_limit:
            raise RateLimitedError(retry_after_sec=10.0)
        courses = deepcopy(self.courses_by_bucket.get((roster.upper(), subject.upper()), []))
        return FetchResult(courses=courses, rtt_ms=12, payload_bytes=2048)

    async def close(self) -> None:
        return None


@pytest.fixture()
def fake_provider() -> FakeCornellProvider:
    return FakeCornellProvider()


@pytest.fixture()
def test_settings(tmp_path: Path) -> Settings:
    s = Settings(
        app_domain="sniper.hodgman.net",
        app_origin="https://sniper.hodgman.net",
        data_dir=tmp_path / "data",
        static_dir=tmp_path / "static",
        enable_background_workers=False,
        max_subjects_per_invited_user=2,
        discord_shared_webhook_url="https://discord.com/api/webhooks/123456/abcdef",
    )
    s.ensure_persisted_secrets()
    return s


@pytest_asyncio.fixture()
async def app_client(
    test_settings: Settings,
    fake_provider: FakeCornellProvider,
) -> AsyncIterator[tuple[object, httpx.AsyncClient]]:
    app = create_app(custom_settings=test_settings, custom_provider=fake_provider)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="https://sniper.hodgman.net") as client:
            yield app, client
