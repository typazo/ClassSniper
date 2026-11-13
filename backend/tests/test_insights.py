"""Tests for CU Reviews / RMP insights caching, instructor matching, and enhanced course search."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from app.config import Settings
from app.db import Database
from app.main import create_app
from app.services.insights import (
    CourseInsightsService,
    extract_unique_instructors,
    normalize_instructor_query,
)
from tests.conftest import FakeCornellProvider


def test_instructor_extraction_and_normalization() -> None:
    instructors = extract_unique_instructors(
        [
            "Michael R. Clarkson, Staff",
            "TBA",
            "michael r. clarkson, Eva Tardos",
            "Walker White",
        ]
    )
    assert instructors == ["Michael R. Clarkson", "Eva Tardos", "Walker White"]

    assert normalize_instructor_query("Michael R. Clarkson") == ("Michael Clarkson", "michael", "clarkson")
    assert normalize_instructor_query("Eva Tardos") == ("Eva Tardos", "eva", "tardos")


@pytest.mark.asyncio
async def test_insights_fetching_matching_and_caching(tmp_path) -> None:
    db = Database(tmp_path / "insights.db")
    await db.connect()

    await db.execute(
        """
        INSERT INTO roster_sections (
            roster, subject, catalog_nbr, class_nbr, enroll_group_idx,
            ssr_component, section, open_status, instructors_summary
        ) VALUES
            ('SP27', 'CS', '2110', 6582, 0, 'LEC', '001', 'C', 'Michael R. Clarkson, Staff'),
            ('SP27', 'CS', '2110', 6584, 0, 'DIS', '202', 'O', 'Unknown TA')
        """
    )

    upstream_calls: dict[str, int] = {"cu_info": 0, "cu_reviews": 0, "rmp": 0}
    simulate_cu_error = False

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        body = json.loads(request.content.decode("utf-8")) if request.content else {}

        if url.endswith("/api/courses/get-by-info"):
            upstream_calls["cu_info"] += 1
            if simulate_cu_error:
                return httpx.Response(503, text="upstream down")
            if body.get("subject") == "CS" and body.get("number") == "2110":
                return httpx.Response(
                    200,
                    json={
                        "result": {
                            "_id": "cu123",
                            "classRating": 3.85,
                            "classDifficulty": 3.05,
                            "classWorkload": 2.95,
                            "classSummary": "Great core data structures class.",
                            "summaryTags": {"Lectures": ["Clear", "positive"]},
                            "classSems": ["FA25", "SP26", "FA26"],
                        }
                    },
                )
            return httpx.Response(404, json={"error": "not found"})

        if url.endswith("/api/courses/get-reviews"):
            upstream_calls["cu_reviews"] += 1
            return httpx.Response(
                200,
                json={
                    "result": [
                        {
                            "_id": "r1",
                            "text": "Awesome class and clear assignments.",
                            "rating": 5,
                            "difficulty": 3,
                            "workload": 3,
                            "grade": "A",
                            "professors": ["Michael Clarkson"],
                            "likes": 4,
                            "date": "2025-11-10T00:00:00Z",
                            "visible": 1,
                            "reported": 0,
                        },
                        {
                            "_id": "r_hidden",
                            "text": "Hidden spam review",
                            "visible": 0,
                            "reported": 0,
                        },
                    ]
                },
            )

        if url.endswith("/graphql"):
            upstream_calls["rmp"] += 1
            q_text = (((body.get("variables") or {}).get("query") or {}).get("text") or "").lower()
            if "clarkson" in q_text:
                return httpx.Response(
                    200,
                    json={
                        "data": {
                            "newSearch": {
                                "teachers": {
                                    "edges": [
                                        {
                                            "node": {
                                                "legacyId": 999001,
                                                "firstName": "R. Keith",
                                                "lastName": "Dennis",
                                                "department": "Mathematics",
                                                "avgRating": 3.7,
                                                "avgDifficulty": 4.4,
                                                "wouldTakeAgainPercent": -1,
                                                "numRatings": 5,
                                            }
                                        },
                                        {
                                            "node": {
                                                "legacyId": 2239807,
                                                "firstName": "Michael",
                                                "lastName": "Clarkson",
                                                "department": "Computer Science",
                                                "avgRating": 4.1,
                                                "avgDifficulty": 3.5,
                                                "wouldTakeAgainPercent": -1,
                                                "numRatings": 54,
                                            }
                                        },
                                    ]
                                }
                            }
                        }
                    },
                )
            return httpx.Response(200, json={"data": {"newSearch": {"teachers": {"edges": []}}}})

        raise AssertionError(f"Unexpected URL: {url}")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    svc = CourseInsightsService(db=db, client=client)

    try:
        res1 = await svc.get_course_insights("SP27", "CS", "2110")
        assert res1["links"]["cu_reviews"] == "https://www.cureviews.org/course/CS/2110"
        assert res1["links"]["coursicle"] == "https://www.coursicle.com/cornell/courses/CS/2110/"
        assert res1["links"]["roster"] == "https://classes.cornell.edu/browse/roster/SP27/class/CS/2110"

        cu = res1["cu_reviews"]
        assert cu["found"] is True
        assert cu["cached"] is False
        assert cu["rating"] == 3.85
        assert cu["review_count"] == 1
        assert cu["reviews"][0]["grade"] == "A"
        assert cu["summary_tags"] == [{"category": "Lectures", "label": "Clear", "sentiment": "positive"}]

        profs = {p["name"]: p for p in res1["rmp"]["instructors"]}
        clarkson = profs["Michael R. Clarkson"]
        assert clarkson["found"] is True
        assert clarkson["legacy_id"] == 2239807
        assert clarkson["rmp_url"] == "https://www.ratemyprofessors.com/professor/2239807"
        assert clarkson["avg_rating"] == 4.1
        # Negative -1 sentinel must map cleanly to None
        assert clarkson["would_take_again_percent"] is None

        unknown = profs["Unknown TA"]
        assert unknown["found"] is False
        assert "ratemyprofessors.com/search/professors/298?q=" in unknown["rmp_url"]

        # Second call hits SQLite cache with zero extra upstream requests
        calls_before = dict(upstream_calls)
        res2 = await svc.get_course_insights("SP27", "CS", "2110")
        assert upstream_calls == calls_before
        assert res2["cu_reviews"]["cached"] is True

        # Transient 503 error must not poison cache for misses
        simulate_cu_error = True
        miss_err = await svc.get_cureviews("PE", "1448")
        assert miss_err["status"] == "error"
        simulate_cu_error = False
        miss_404 = await svc.get_cureviews("PE", "1448")
        assert miss_404["status"] == "not_found"
    finally:
        await svc.close()
        await db.close()


@pytest.mark.asyncio
async def test_search_nospace_instructor_and_insights_route(tmp_path) -> None:
    settings = Settings(
        app_domain="sniper.hodgman.net",
        app_origin="https://sniper.hodgman.net",
        data_dir=tmp_path / "data",
        static_dir=tmp_path / "static",
        enable_background_workers=False,
    )
    settings.ensure_persisted_secrets()
    provider = FakeCornellProvider()

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("/api/courses/get-by-info"):
            return httpx.Response(
                200,
                json={"result": {"_id": "abc", "classRating": 4.2, "classDifficulty": 2.5, "classWorkload": 2.4}},
            )
        if url.endswith("/api/courses/get-reviews"):
            return httpx.Response(200, json={"result": []})
        return httpx.Response(200, json={"data": {"newSearch": {"teachers": {"edges": []}}}})

    app = create_app(custom_settings=settings, custom_provider=provider)
    async with app.router.lifespan_context(app):
        # Swap insights client with deterministic offline mock before serving requests
        await app.state.insights.close()
        app.state.insights = CourseInsightsService(
            db=app.state.db,
            client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://sniper.hodgman.net") as client:
            await client.post("/api/auth/bootstrap", json={"username": "tyler", "password": "password123"})

            # No-space query "cs2110" hydrates & finds CS 2110
            no_space = await client.get("/api/courses/search", params={"roster": "SP27", "q": "cs2110"})
            assert no_space.status_code == 200
            courses = no_space.json()["courses"]
            assert len(courses) == 1
            assert courses[0]["subject"] == "CS"
            assert courses[0]["catalog_nbr"] == "2110"
            assert courses[0]["external_links"]["coursicle"].endswith("/CS/2110/")

            # Instructor query "Tani" matches Erasmo Tani on CS 2110
            by_prof = await client.get("/api/courses/search", params={"roster": "SP27", "q": "Tani"})
            assert by_prof.status_code == 200
            prof_courses = by_prof.json()["courses"]
            assert len(prof_courses) == 1
            assert prof_courses[0]["catalog_nbr"] == "2110"

            # Course insights endpoint returns CU Reviews, RMP, and external links
            ins = await client.get("/api/courses/SP27/CS/2110/insights")
            assert ins.status_code == 200
            data: dict[str, Any] = ins.json()
            assert data["cu_reviews"]["rating"] == 4.2
            assert data["links"]["cu_reviews"] == "https://www.cureviews.org/course/CS/2110"
            assert data["rmp"]["instructors"][0]["name"] == "Erasmo Tani"
