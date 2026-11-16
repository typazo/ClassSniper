"""Lazy, SQLite-cached CU Reviews, RateMyProfessors, and external course link enrichment."""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional
from urllib.parse import quote, quote_plus

import httpx
import orjson

from app.db import Database
from app.services.common import parse_utc_dt
from app.services.notifiers import build_roster_course_url

CORNELL_RMP_LEGACY_ID = "298"
CORNELL_RMP_SCHOOL_ID = "U2Nob29sLTI5OA=="  # base64("School-298")
CUREVIEWS_BASE_URL = "https://www.cureviews.org"
RMP_GRAPHQL_URL = "https://www.ratemyprofessors.com/graphql"

_RMP_SEARCH_QUERY = """
query NewSearchTeachersQuery($query: TeacherSearchQuery!, $count: Int) {
  newSearch {
    teachers(query: $query, first: $count) {
      edges {
        node {
          legacyId
          firstName
          lastName
          department
          avgRating
          avgDifficulty
          wouldTakeAgainPercent
          numRatings
        }
      }
    }
  }
}
"""

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def build_external_links(roster: str, subject: str, catalog_nbr: str) -> dict[str, str]:
    """Return canonical Cornell Roster, CU Reviews, Coursicle, and RMP links for a course."""
    roster_u = roster.upper()
    subject_u = subject.upper()
    cat_clean = catalog_nbr.strip()
    return {
        "roster": build_roster_course_url(roster_u, subject_u, cat_clean),
        "cu_reviews": f"{CUREVIEWS_BASE_URL}/course/{quote(subject_u)}/{quote(cat_clean)}",
        "coursicle": f"https://www.coursicle.com/cornell/courses/{quote(subject_u)}/{quote(cat_clean)}/",
        "rmp_search": build_rmp_search_url(subject_u),
    }


def build_rmp_search_url(name: str) -> str:
    return f"https://www.ratemyprofessors.com/search/professors/{CORNELL_RMP_LEGACY_ID}?q={quote_plus(name.strip())}"


def extract_unique_instructors(summaries: Iterable[str], limit: int = 8) -> list[str]:
    """Extract unique real instructor names from section instructor summaries."""
    seen: set[str] = set()
    names: list[str] = []
    for raw in summaries:
        for part in (raw or "").split(","):
            name = " ".join(part.split()).strip()
            if not name:
                continue
            low = name.lower()
            if low in {"staff", "tba", "tbd", "instructor", "to be assigned"}:
                continue
            if low in seen:
                continue
            seen.add(low)
            names.append(name)
            if len(names) >= limit:
                return names
    return names


def normalize_instructor_query(name: str) -> tuple[str, str, str]:
    """Normalize 'First [M.] Last' into (query_text, first_token, last_token)."""
    raw_tokens = [tok.strip("., ") for tok in name.split() if tok.strip("., ")]
    if not raw_tokens:
        return "", "", ""
    if len(raw_tokens) == 1:
        tok = raw_tokens[0].lower()
        return raw_tokens[0], "", tok

    first = raw_tokens[0]
    last = raw_tokens[-1]
    # Keep multi-part non-initial tokens while stripping single-letter middle initials
    filtered = [first] + [t for t in raw_tokens[1:-1] if len(t) > 1] + [last]
    return " ".join(filtered), first.lower(), last.lower()


def _clean_token(value: str) -> str:
    return _NON_ALNUM_RE.sub("", (value or "").lower())


def _select_best_rmp_match(
    edges: list[dict[str, Any]],
    target_first: str,
    target_last: str,
    allow_initial_only: bool = False,
) -> Optional[dict[str, Any]]:
    """Score RMP search edges and return a confident match, or None."""
    target_last_c = _clean_token(target_last)
    target_first_c = _clean_token(target_first)
    if not target_last_c:
        return None

    scored: list[tuple[int, int, dict[str, Any]]] = []
    for edge in edges:
        node = (edge or {}).get("node") or {}
        node_last_c = _clean_token(node.get("lastName") or "")
        node_first_raw = (node.get("firstName") or "").strip()
        node_first_c = _clean_token(node_first_raw.split()[0] if node_first_raw else "")

        if node_last_c != target_last_c:
            # Handle hyphenated last names cleanly (e.g. "Smith-Jones")
            node_last_parts = {_clean_token(p) for p in re.split(r"[\s-]+", node.get("lastName") or "") if p}
            if target_last_c not in node_last_parts:
                continue

        score = 0
        if target_first_c:
            if node_first_c == target_first_c:
                score = 100
            elif node_first_c.startswith(target_first_c) or target_first_c.startswith(node_first_c):
                if min(len(node_first_c), len(target_first_c)) >= 2:
                    score = 75
                elif allow_initial_only:
                    score = 40
            elif allow_initial_only and node_first_c and node_first_c[0] == target_first_c[0]:
                score = 40
            else:
                continue
        else:
            score = 50

        num_ratings = int(node.get("numRatings") or 0)
        scored.append((score, num_ratings, node))

    if not scored:
        return None
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    best_score, _, best_node = scored[0]
    if allow_initial_only and best_score == 40 and sum(1 for s, _, _ in scored if s == 40) > 1:
        return None
    return best_node


def _is_fresh(fetched_at: Optional[str], found: int, ttl_hours: float, miss_ttl_hours: float) -> bool:
    dt = parse_utc_dt(fetched_at)
    if dt is None:
        return False
    max_age = timedelta(hours=ttl_hours if found else miss_ttl_hours)
    return datetime.now(timezone.utc) - dt <= max_age


def _format_round_num(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if num <= 0:
        return None
    return round(num, 2)


class CourseInsightsService:
    """Fetches and SQLite-caches CU Reviews & RateMyProfessors insights outside the Cornell poller."""

    def __init__(
        self,
        db: Database,
        client: Optional[httpx.AsyncClient] = None,
        cache_ttl_hours: float = 168.0,
        miss_ttl_hours: float = 24.0,
    ) -> None:
        self.db = db
        self.cache_ttl_hours = cache_ttl_hours
        self.miss_ttl_hours = miss_ttl_hours
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(4.5, connect=2.5),
            limits=httpx.Limits(max_connections=12, max_keepalive_connections=6, keepalive_expiry=60.0),
            headers={"User-Agent": "ClassSniper/0.1 (self-hosted)"},
        )
        self._course_locks: dict[tuple[str, str], asyncio.Lock] = {}
        self._rmp_locks: dict[str, asyncio.Lock] = {}

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _get_course_lock(self, subject: str, catalog_nbr: str) -> asyncio.Lock:
        key = (subject.upper(), catalog_nbr.strip())
        lock = self._course_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._course_locks[key] = lock
        return lock

    def _get_rmp_lock(self, name_key: str) -> asyncio.Lock:
        lock = self._rmp_locks.get(name_key)
        if lock is None:
            lock = asyncio.Lock()
            self._rmp_locks[name_key] = lock
        return lock

    async def get_course_insights(
        self,
        roster: str,
        subject: str,
        catalog_nbr: str,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        roster_u = roster.upper()
        subject_u = subject.upper()
        cat_clean = catalog_nbr.strip()

        sec_rows = await self.db.fetch_all(
            """
            SELECT instructors_summary
            FROM roster_sections
            WHERE roster = ? AND subject = ? AND catalog_nbr = ?
            ORDER BY enroll_group_idx ASC, class_nbr ASC
            """,
            (roster_u, subject_u, cat_clean),
        )
        instructors = extract_unique_instructors(r["instructors_summary"] for r in sec_rows)

        cu_task = self.get_cureviews(subject_u, cat_clean, force_refresh=force_refresh)
        rmp_tasks = [self.get_rmp_instructor(name, force_refresh=force_refresh) for name in instructors]
        results = await asyncio.gather(cu_task, *rmp_tasks, return_exceptions=True)

        cu_raw = results[0]
        if isinstance(cu_raw, Exception):
            cu_data = {
                "found": False,
                "status": "error",
                "error": "CU Reviews temporarily unreachable",
                "course_url": f"{CUREVIEWS_BASE_URL}/course/{quote(subject_u)}/{quote(cat_clean)}",
                "reviews": [],
                "summary_tags": [],
                "semesters_offered": [],
            }
        else:
            cu_data = cu_raw

        rmp_items: list[dict[str, Any]] = []
        for name, res in zip(instructors, results[1:]):
            if isinstance(res, Exception):
                rmp_items.append(
                    {
                        "name": name,
                        "found": False,
                        "status": "error",
                        "rmp_url": build_rmp_search_url(name),
                        "search_url": build_rmp_search_url(name),
                    }
                )
            else:
                rmp_items.append(res)

        links = build_external_links(roster_u, subject_u, cat_clean)
        return {
            "roster": roster_u,
            "subject": subject_u,
            "catalog_nbr": cat_clean,
            "links": links,
            "cu_reviews": cu_data,
            "rmp": {
                "instructors": rmp_items,
                "search_url": links["rmp_search"],
            },
        }

    async def _cached_fetch(
        self,
        lock: asyncio.Lock,
        force_refresh: bool,
        select_sql: str,
        select_params: tuple[Any, ...],
        upsert_sql: str,
        build_upsert_params: Any,
        fetcher: Any,
    ) -> dict[str, Any]:
        """Serialize SQLite-backed external insight fetch & cache upsert cleanly."""
        async with lock:
            if not force_refresh:
                cached = await self.db.fetch_one(select_sql, select_params)
                if cached and _is_fresh(cached["fetched_at"], cached["found"], self.cache_ttl_hours, self.miss_ttl_hours):
                    data = orjson.loads(cached["payload_json"])
                    data["cached"] = True
                    return data

            fetched, cacheable = await fetcher()
            if cacheable:
                await self.db.execute(upsert_sql, build_upsert_params(fetched))
            fetched["cached"] = False
            return fetched

    async def get_cureviews(self, subject: str, catalog_nbr: str, force_refresh: bool = False) -> dict[str, Any]:
        subject_u = subject.upper()
        cat_clean = catalog_nbr.strip()
        course_url = f"{CUREVIEWS_BASE_URL}/course/{quote(subject_u)}/{quote(cat_clean)}"
        return await self._cached_fetch(
            lock=self._get_course_lock(subject_u, cat_clean),
            force_refresh=force_refresh,
            select_sql="SELECT payload_json, found, fetched_at FROM course_insights_cache WHERE subject = ? AND catalog_nbr = ?",
            select_params=(subject_u, cat_clean),
            upsert_sql="""
                INSERT INTO course_insights_cache (subject, catalog_nbr, payload_json, found, fetched_at)
                VALUES (?, ?, ?, ?, datetime('now'))
                ON CONFLICT(subject, catalog_nbr) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    found = excluded.found,
                    fetched_at = datetime('now')
            """,
            build_upsert_params=lambda f: (subject_u, cat_clean, orjson.dumps(f).decode("utf-8"), 1 if f["found"] else 0),
            fetcher=lambda: self._fetch_cureviews_remote(subject_u, cat_clean, course_url),
        )

    async def _fetch_cureviews_remote(self, subject_u: str, cat_clean: str, course_url: str) -> tuple[dict[str, Any], bool]:
        base_miss: dict[str, Any] = {
            "found": False,
            "status": "not_found",
            "course_url": course_url,
            "rating": None,
            "difficulty": None,
            "workload": None,
            "summary": "",
            "summary_tags": [],
            "semesters_offered": [],
            "review_count": 0,
            "reviews": [],
        }

        try:
            resp = await self._client.post(
                f"{CUREVIEWS_BASE_URL}/api/courses/get-by-info",
                json={"subject": subject_u, "number": cat_clean},
            )
        except httpx.HTTPError:
            return {**base_miss, "status": "error", "error": "CU Reviews unreachable"}, False

        if resp.status_code == 404:
            return base_miss, True
        if resp.status_code >= 400:
            return {**base_miss, "status": "error", "error": f"CU Reviews HTTP {resp.status_code}"}, False

        try:
            payload = orjson.loads(resp.content)
        except ValueError:
            return {**base_miss, "status": "error", "error": "Invalid CU Reviews response"}, False

        course_obj = payload.get("result")
        if not isinstance(course_obj, dict) or not course_obj.get("_id"):
            return base_miss, True

        tags_raw = course_obj.get("summaryTags") or {}
        summary_tags: list[dict[str, str]] = []
        if isinstance(tags_raw, dict):
            for category, val in tags_raw.items():
                if isinstance(val, list) and val:
                    label = str(val[0]).strip()
                    sentiment = str(val[1]).strip() if len(val) > 1 else "neutral"
                elif val:
                    label = str(val).strip()
                    sentiment = "neutral"
                else:
                    continue
                if label:
                    summary_tags.append({"category": str(category), "label": label, "sentiment": sentiment})

        reviews_out: list[dict[str, Any]] = []
        review_count = 0
        try:
            rev_resp = await self._client.post(
                f"{CUREVIEWS_BASE_URL}/api/courses/get-reviews",
                json={"courseId": course_obj["_id"]},
            )
            if rev_resp.status_code == 200:
                rev_payload = orjson.loads(rev_resp.content)
                raw_reviews = rev_payload.get("result") or []
                visible_reviews = [
                    r
                    for r in raw_reviews
                    if isinstance(r, dict)
                    and r.get("visible", 1)
                    and not r.get("reported", 0)
                    and str(r.get("text") or "").strip()
                ]
                review_count = len(visible_reviews)
                for r in visible_reviews[:5]:
                    profs = [str(p).strip() for p in (r.get("professors") or []) if str(p).strip()]
                    text = str(r.get("text") or "").strip()
                    if len(text) > 550:
                        text = text[:547].rstrip() + "..."
                    reviews_out.append(
                        {
                            "id": str(r.get("_id") or ""),
                            "text": text,
                            "rating": _format_round_num(r.get("rating")),
                            "difficulty": _format_round_num(r.get("difficulty")),
                            "workload": _format_round_num(r.get("workload")),
                            "grade": str(r.get("grade") or "").strip(),
                            "professors": profs,
                            "likes": int(r.get("likes") or 0),
                            "date": str(r.get("date") or ""),
                        }
                    )
        except (httpx.HTTPError, ValueError):
            pass

        result = {
            "found": True,
            "status": "ok",
            "course_url": course_url,
            "rating": _format_round_num(course_obj.get("classRating")),
            "difficulty": _format_round_num(course_obj.get("classDifficulty")),
            "workload": _format_round_num(course_obj.get("classWorkload")),
            "summary": str(course_obj.get("classSummary") or "").strip(),
            "summary_tags": summary_tags,
            "semesters_offered": [str(s) for s in (course_obj.get("classSems") or [])[-8:]],
            "review_count": review_count,
            "reviews": reviews_out,
        }
        return result, True

    async def get_rmp_instructor(self, name: str, force_refresh: bool = False) -> dict[str, Any]:
        cleaned_query, target_first, target_last = normalize_instructor_query(name)
        name_key = cleaned_query.lower() or name.strip().lower()
        search_url = build_rmp_search_url(cleaned_query or name)
        return await self._cached_fetch(
            lock=self._get_rmp_lock(name_key),
            force_refresh=force_refresh,
            select_sql="SELECT payload_json, found, fetched_at FROM rmp_instructor_cache WHERE name_key = ?",
            select_params=(name_key,),
            upsert_sql="""
                INSERT INTO rmp_instructor_cache (name_key, payload_json, found, fetched_at)
                VALUES (?, ?, ?, datetime('now'))
                ON CONFLICT(name_key) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    found = excluded.found,
                    fetched_at = datetime('now')
            """,
            build_upsert_params=lambda f: (name_key, orjson.dumps(f).decode("utf-8"), 1 if f["found"] else 0),
            fetcher=lambda: self._fetch_rmp_remote(
                display_name=name,
                cleaned_query=cleaned_query or name,
                target_first=target_first,
                target_last=target_last,
                search_url=search_url,
            ),
        )

    async def _query_rmp_edges(self, text: str) -> Optional[list[dict[str, Any]]]:
        try:
            resp = await self._client.post(
                RMP_GRAPHQL_URL,
                headers={"Content-Type": "application/json", "Authorization": "Basic dGVzdDp0ZXN0"},
                json={
                    "query": _RMP_SEARCH_QUERY,
                    "variables": {
                        "query": {"text": text, "schoolID": CORNELL_RMP_SCHOOL_ID},
                        "count": 6,
                    },
                },
            )
        except httpx.HTTPError:
            return None

        if resp.status_code != 200:
            return None
        try:
            payload = orjson.loads(resp.content)
        except ValueError:
            return None

        teachers = ((payload.get("data") or {}).get("newSearch") or {}).get("teachers") or {}
        return teachers.get("edges") or []

    async def _fetch_rmp_remote(
        self,
        display_name: str,
        cleaned_query: str,
        target_first: str,
        target_last: str,
        search_url: str,
    ) -> tuple[dict[str, Any], bool]:
        miss = {
            "name": display_name,
            "found": False,
            "status": "not_found",
            "legacy_id": None,
            "rmp_url": search_url,
            "search_url": search_url,
            "department": "",
            "avg_rating": None,
            "avg_difficulty": None,
            "would_take_again_percent": None,
            "num_ratings": 0,
        }

        edges = await self._query_rmp_edges(cleaned_query)
        if edges is None:
            return {**miss, "status": "error"}, False

        match = _select_best_rmp_match(edges, target_first=target_first, target_last=target_last, allow_initial_only=False)
        if match is None and target_last and cleaned_query.lower() != target_last:
            fallback_edges = await self._query_rmp_edges(target_last)
            if fallback_edges is None:
                return {**miss, "status": "error"}, False
            match = _select_best_rmp_match(
                fallback_edges,
                target_first=target_first,
                target_last=target_last,
                allow_initial_only=True,
            )

        if match is None:
            return miss, True

        legacy_id = match.get("legacyId")
        num_ratings = int(match.get("numRatings") or 0)
        wta_raw = match.get("wouldTakeAgainPercent")
        wta_pct: Optional[int] = None
        if isinstance(wta_raw, (int, float)) and not isinstance(wta_raw, bool) and wta_raw >= 0:
            wta_pct = round(float(wta_raw))

        rmp_url = f"https://www.ratemyprofessors.com/professor/{legacy_id}" if legacy_id else search_url
        matched_full = " ".join(p for p in [match.get("firstName"), match.get("lastName")] if p).strip()

        return {
            "name": display_name,
            "matched_name": matched_full or display_name,
            "found": True,
            "status": "ok",
            "legacy_id": legacy_id,
            "rmp_url": rmp_url,
            "search_url": search_url,
            "department": str(match.get("department") or "").strip(),
            "avg_rating": _format_round_num(match.get("avgRating")) if num_ratings > 0 else None,
            "avg_difficulty": _format_round_num(match.get("avgDifficulty")) if num_ratings > 0 else None,
            "would_take_again_percent": wta_pct if num_ratings > 0 else None,
            "num_ratings": num_ratings,
        }, True
