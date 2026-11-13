"""Interactive Cornell CS Checklist builder & What-If evaluator (A&S and Engineering)."""

from __future__ import annotations

from collections import deque
import json
from typing import Any, Iterable, Optional

from app.db import Database
from app.services.attributes import AS_DISTRIBUTION_CODES, extract_course_attributes, normalize_attr_code
from app.services.cs_requirements import (
    TRANSCRIPT_EQUIVALENT_CATALOG,
    CSRequirementsIndex,
    CourseEligibility,
    decode_completed_course_details,
    decode_completed_courses,
    merge_course_detail_fields,
    normalize_completed_courses,
    normalize_course_code,
    normalize_course_detail,
    parse_catalog_num,
)

LIBERAL_STUDIES_ATTRS: tuple[str, ...] = (
    "CA-AG",
    "HA-AG",
    "KCM-AG",
    "LA-AG",
    "SBA-AG",
    "FL-AG",
    "CA-HE",
    "HA-HE",
    "KCM-HE",
    "SBA-HE",
)

CORE_MATCHERS: list[dict[str, Any]] = [
    {
        "id": "core_2800",
        "label": "Discrete Structures",
        "expected": "CS 2800 / 2802",
        "options": {"CS 2800", "CS 2802"},
        "search": {"q": "CS 2800", "subjects": ["CS"]},
    },
    {
        "id": "core_3110",
        "label": "Data Structures & Functional Programming",
        "expected": "CS 3110",
        "options": {"CS 3110"},
        "search": {"q": "CS 3110", "subjects": ["CS"]},
    },
    {
        "id": "core_3410",
        "label": "Systems / Architecture",
        "expected": "CS 3410 / 3420 / ECE 2300",
        "options": {"CS 3410", "CS 3420", "ECE 2300", "ENGRD 2300"},
        "search": {"q": "CS 3410", "subjects": ["CS"]},
    },
    {
        "id": "core_aiml",
        "label": "Intro to ML / AI (Fall 2024+)",
        "expected": "CS 3780 / 3700",
        "options": {"CS 3780", "CS 3700", "CS 4780", "CS 5780", "CS 5700"},
        "search": {"q": "CS 3780", "subjects": ["CS"]},
        "current_only": True,
    },
    {
        "id": "core_4410",
        "label": "Operating Systems",
        "expected": "CS 4410 / 4414",
        "options": {"CS 4410", "CS 4414", "CS 5410"},
        "search": {"q": "CS 4410", "subjects": ["CS"]},
    },
    {
        "id": "core_4820",
        "label": "Intro Analysis of Algorithms",
        "expected": "CS 4820",
        "options": {"CS 4820", "CS 5820"},
        "search": {"q": "CS 4820", "subjects": ["CS"]},
    },
]

ARTS_MATH_INTRO_MATCHERS: list[dict[str, Any]] = [
    {
        "id": "math_calc_1",
        "label": "Calculus I",
        "expected": "MATH 1110 / 1910",
        "options": {"MATH 1110", "MATH 1910"},
        "search": {"q": "MATH 1110", "subjects": ["MATH"]},
    },
    {
        "id": "math_calc_2",
        "label": "Calculus II",
        "expected": "MATH 1120 / 1920",
        "options": {"MATH 1120", "MATH 1920"},
        "search": {"q": "MATH 1120", "subjects": ["MATH"]},
    },
    {
        "id": "math_linalg",
        "label": "Linear Algebra",
        "expected": "MATH 2210 / 2940 / 2230",
        "options": {"MATH 2210", "MATH 2940", "MATH 2230", "MATH 2310"},
        "search": {"q": "MATH 2210", "subjects": ["MATH"]},
    },
    {
        "id": "intro_cs_1",
        "label": "Intro Computing",
        "expected": "CS 1110 / 1112",
        "options": {"CS 1110", "CS 1112", "CS 1114", "CS 1115"},
        "search": {"q": "CS 1110", "subjects": ["CS"]},
    },
    {
        "id": "intro_cs_2",
        "label": "OO Programming & Data Structures",
        "expected": "CS 2110 / 2112",
        "options": {"CS 2110", "CS 2112"},
        "search": {"q": "CS 2110", "subjects": ["CS"]},
    },
]

ENG_MATH_SCI_MATCHERS: list[dict[str, Any]] = [
    {
        "id": "eng_math_1",
        "label": "Calculus for Engineers",
        "expected": "MATH 1910",
        "options": {"MATH 1910", "MATH 1110"},
        "search": {"q": "MATH 1910", "subjects": ["MATH"]},
    },
    {
        "id": "eng_math_2",
        "label": "Multivariable Calculus",
        "expected": "MATH 1920",
        "options": {"MATH 1920", "MATH 2220"},
        "search": {"q": "MATH 1920", "subjects": ["MATH"]},
    },
    {
        "id": "eng_math_3",
        "label": "Linear Algebra for Engineers",
        "expected": "MATH 2940",
        "options": {"MATH 2940", "MATH 2210"},
        "search": {"q": "MATH 2940", "subjects": ["MATH"]},
    },
    {
        "id": "eng_math_4",
        "label": "Probability / Diff Eq / Math",
        "expected": "ENGRD 2700 / MATH 2930 / BTRY 3080",
        "options": {"ENGRD 2700", "ORIE 3500", "MATH 2930", "BTRY 3080", "STSCI 3080", "ECON 3130", "MATH 4710", "CS 4850"},
        "search": {"q": "ENGRD 2700", "subjects": ["ENGRD", "MATH", "ORIE", "STSCI"]},
    },
    {
        "id": "eng_phys_1",
        "label": "Physics I (Mechanics)",
        "expected": "PHYS 1112 / 1116",
        "options": {"PHYS 1112", "PHYS 1116"},
        "search": {"q": "PHYS 1112", "subjects": ["PHYS"]},
    },
    {
        "id": "eng_phys_2",
        "label": "Physics II (E&M)",
        "expected": "PHYS 2213 / 2217",
        "options": {"PHYS 2213", "PHYS 2217"},
        "search": {"q": "PHYS 2213", "subjects": ["PHYS"]},
    },
    {
        "id": "eng_chem",
        "label": "General Chemistry",
        "expected": "CHEM 2090 / 2080",
        "options": {"CHEM 2090", "CHEM 2080", "CHEM 2070"},
        "search": {"q": "CHEM 2090", "subjects": ["CHEM"]},
    },
    {
        "id": "eng_sci_extra",
        "label": "Additional Engineering Science",
        "expected": "PHYS 2214 / BIOG / CHEM / EAS",
        "options": {"PHYS 2214", "PHYS 2218", "CHEM 2080", "BIOG 1440", "BIOG 1445", "BIOMG 1350", "EAS 2250"},
        "search": {"q": "PHYS 2214", "subjects": ["PHYS", "CHEM", "BIOG", "BIOMG"]},
    },
    {
        "id": "intro_cs_1",
        "label": "Intro Computing",
        "expected": "CS 1110 / 1112",
        "options": {"CS 1110", "CS 1112", "CS 1114", "CS 1115"},
        "search": {"q": "CS 1110", "subjects": ["CS"]},
    },
    {
        "id": "intro_cs_2",
        "label": "OO Programming & Data Structures",
        "expected": "CS 2110 / 2112",
        "options": {"CS 2110", "CS 2112", "ENGRD 2110", "ENGRD 2112"},
        "search": {"q": "CS 2110", "subjects": ["CS"]},
    },
    {
        "id": "eng_engri",
        "label": "Intro to Engineering",
        "expected": "ENGRI 1xxx",
        "options": set(),
        "attr_match": "ENGRI",
        "search": {"attrs": ["ENGRI"], "subjects": ["ENGRI"]},
    },
    {
        "id": "eng_engrd",
        "label": "2nd Engineering Distribution",
        "expected": "ENGRD 2xxx (not 2110)",
        "options": set(),
        "attr_match": "ENGRD",
        "exclude": {"ENGRD 2110", "ENGRD 2112"},
        "search": {"attrs": ["ENGRD"], "subjects": ["ENGRD"]},
    },
]

AS_DIST_DISPLAY: list[tuple[str, str, str]] = [
    ("ALC-AS", "ALC-AS", "Arts, Literature & Culture"),
    ("BIO-AS", "BIO-AS", "Biological Sciences"),
    ("ETM-AS", "ETM-AS", "Ethics & the Mind"),
    ("GLC-AS", "GLC-AS", "Global Citizenship"),
    ("HST-AS", "HIST-AS", "Historical Analysis"),
    ("PHS-AS", "PHS-AS", "Physical Sciences"),
    ("SCD-AS", "SCD-AS", "Social Difference"),
    ("SSC-AS", "SSC-AS", "Social Sciences"),
    ("SDS-AS", "SDS-AS", "Statistics & Data Science"),
    ("SMR-AS", "SMR-AS", "Symbolic & Math Reasoning"),
]

# Closely related interdisciplinary External Specialization department groups soft-allowed
# with CS Assistant Director, Undergraduate Advising approval (when >1 department is used).
RELATED_EXT_SPEC_CLUSTERS: tuple[tuple[str, frozenset[str]], ...] = (
    ("Psych / CogSci / HD / Comm / Info / HCI", frozenset({"PSYCH", "COGST", "HD", "COMM", "INFO", "DESIGN", "DEA"})),
    ("Business / Econ / Management", frozenset({"AEM", "ECON", "HADM", "NBA", "NCC", "ILROB", "ILRHR", "ILRLE"})),
    ("Math / Stats / Data", frozenset({"MATH", "STSCI", "BTRY", "ORIE", "ILRST"})),
    ("Biology / Neuro / Biomedical", frozenset({"BIOG", "BIOMG", "BIOEE", "BIONB", "BIOMI", "BME", "NS"})),
    ("Physics / Earth / Hardware Eng", frozenset({"PHYS", "ASTRO", "EAS", "AEP", "ECE", "MAE"})),
    ("Policy / Gov / History / Philosophy", frozenset({"GOVT", "PUBPOL", "PAM", "SOC", "HIST", "PHIL", "STS"})),
)
EXT_SPEC_ADVISOR_WARNING = "Run by CS Assistant Director, Undergraduate Advising first (multi-dept External Spec)"

_EXCLUDED_FIXED_CODES: frozenset[str] = {
    "CS 1110",
    "CS 1112",
    "CS 1114",
    "CS 1115",
    "CS 2110",
    "CS 2112",
    "CS 2800",
    "CS 2802",
    "CS 3110",
    "CS 3410",
    "CS 3420",
    "CS 4410",
    "CS 4414",
    "CS 4820",
}


def decode_checklist_state(raw_json: Any) -> dict[str, Any]:
    default_state: dict[str, Any] = {
        "college": "arts",
        "curriculum": "current",
        "include_active_schedule": True,
        "pe_completed": 0,
        "slots": {},
    }
    if not raw_json:
        return default_state
    try:
        parsed = json.loads(raw_json) if isinstance(raw_json, str) else dict(raw_json)
    except Exception:
        return default_state
    if not isinstance(parsed, dict):
        return default_state

    college = "engineering" if parsed.get("college") == "engineering" else "arts"
    curriculum = "pre2024" if parsed.get("curriculum") == "pre2024" else "current"
    include_sched = bool(parsed.get("include_active_schedule", True))
    pe_completed = max(0, min(4, int(parsed.get("pe_completed") or 0)))
    slots = parsed.get("slots") if isinstance(parsed.get("slots"), dict) else {}
    return {
        "college": college,
        "curriculum": curriculum,
        "include_active_schedule": include_sched,
        "pe_completed": pe_completed,
        "slots": slots,
    }


def format_credits_range(u_min: Any, u_max: Any) -> str:
    """Format min/max credit bounds as e.g. '4' or '3-4' (empty string if unknown)."""
    try:
        lo = float(u_min or 0.0)
        hi = float(u_max or 0.0)
    except (TypeError, ValueError):
        return ""
    if lo <= 0 and hi <= 0:
        return ""
    if hi <= 0 or abs(lo - hi) < 1e-6:
        v = lo if lo > 0 else hi
        return str(int(v)) if v.is_integer() else f"{v:g}"
    return f"{lo:g}-{hi:g}"


_fmt_credits = format_credits_range


def _solve_max_bipartite_matching(
    n_courses: int,
    n_slots: int,
    edges: list[tuple[int, int, int]],
) -> tuple[dict[int, int], int]:
    """Exact max-cardinality, max-weight bipartite matching via successive shortest augmenting paths."""
    if n_courses == 0 or n_slots == 0 or not edges:
        return {}, 0

    src = n_courses + n_slots
    snk = src + 1
    total_nodes = snk + 1
    adj: list[list[list[int]]] = [[] for _ in range(total_nodes)]

    def _add_edge(u: int, v: int, cap: int, cost: int) -> None:
        rev_u = len(adj[v])
        rev_v = len(adj[u])
        adj[u].append([v, cap, cost, rev_u])
        adj[v].append([u, 0, -cost, rev_v])

    for c in range(n_courses):
        _add_edge(src, c, 1, 0)
    for s in range(n_slots):
        _add_edge(n_courses + s, snk, 1, 0)
    for c, s, weight in edges:
        _add_edge(c, n_courses + s, 1, -weight)

    inf = 10**24
    total_weight = 0
    while True:
        dist = [inf] * total_nodes
        parent_node = [-1] * total_nodes
        parent_edge = [-1] * total_nodes
        in_queue = [False] * total_nodes
        dist[src] = 0
        q: deque[int] = deque([src])
        in_queue[src] = True
        while q:
            u = q.popleft()
            in_queue[u] = False
            du = dist[u]
            for idx, (v, cap, cost, _) in enumerate(adj[u]):
                if cap > 0 and du + cost < dist[v]:
                    dist[v] = du + cost
                    parent_node[v] = u
                    parent_edge[v] = idx
                    if not in_queue[v]:
                        q.append(v)
                        in_queue[v] = True
        if dist[snk] >= 0:
            break
        v = snk
        while v != src:
            u = parent_node[v]
            e_idx = parent_edge[v]
            edge = adj[u][e_idx]
            edge[1] -= 1
            adj[v][edge[3]][1] += 1
            v = u
        total_weight += -dist[snk]

    slot_to_course: dict[int, int] = {}
    for c in range(n_courses):
        for v, cap, _, _ in adj[c]:
            if n_courses <= v < n_courses + n_slots and cap == 0:
                slot_to_course[v - n_courses] = c
    return slot_to_course, total_weight


async def build_cs_checklist_payload(
    db: Database,
    user: dict[str, Any],
    cs_index: CSRequirementsIndex,
    roster: str,
    completed_courses_override: Optional[list[str]] = None,
    completed_details_override: Optional[dict[str, dict[str, str]]] = None,
    in_progress_courses_override: Optional[list[str]] = None,
    in_progress_details_override: Optional[dict[str, dict[str, str]]] = None,
) -> dict[str, Any]:
    """Evaluate user's CS Checklist combining completed, currently taking, active schedule (What-If), and manual slot edits."""
    roster_u = roster.upper()
    row = await db.fetch_one(
        """
        SELECT cs_checklist_json, completed_courses_json, completed_course_details_json,
               in_progress_courses_json, in_progress_course_details_json
        FROM users WHERE id = ?
        """,
        (user["id"],),
    )
    saved = decode_checklist_state(row.get("cs_checklist_json") if row else None)
    if completed_courses_override is not None:
        completed_list = list(completed_courses_override)
    else:
        raw_comp = row.get("completed_courses_json") if row else "[]"
        try:
            completed_list = json.loads(raw_comp or "[]")
        except Exception:
            completed_list = list(user.get("completed_courses") or [])

    if completed_details_override is not None:
        course_details = dict(completed_details_override)
    else:
        course_details = decode_completed_course_details(
            row.get("completed_course_details_json") if row else user.get("completed_course_details")
        )

    if in_progress_courses_override is not None:
        raw_in_prog = list(in_progress_courses_override)
    elif row is not None:
        raw_in_prog = decode_completed_courses(row.get("in_progress_courses_json"))
    else:
        raw_in_prog = list(user.get("in_progress_courses") or [])

    if in_progress_details_override is not None:
        in_progress_details = dict(in_progress_details_override)
    else:
        in_progress_details = decode_completed_course_details(
            row.get("in_progress_course_details_json") if row else user.get("in_progress_course_details")
        )

    completed_set = {normalize_course_code(c) for c in completed_list if normalize_course_code(c)}
    in_progress_list = [
        c for c in normalize_completed_courses(raw_in_prog)
        if c not in completed_set
    ]
    in_progress_set = set(in_progress_list)
    in_progress_details = {
        k: v for k, v in in_progress_details.items() if k in in_progress_set
    }

    college = saved["college"]
    curriculum = saved["curriculum"]
    include_sched = saved["include_active_schedule"]
    manual_slots: dict[str, dict[str, Any]] = saved["slots"]

    # Fetch enabled courses from user's active schedule for this roster
    planned_courses: dict[str, dict[str, Any]] = {}
    active_schedule_name = ""
    if include_sched:
        sched = await db.fetch_one(
            """
            SELECT id, name
            FROM schedules
            WHERE user_id = ? AND roster = ?
            ORDER BY is_active DESC, updated_at DESC, id DESC
            LIMIT 1
            """,
            (user["id"], roster_u),
        )
        if sched is not None:
            active_schedule_name = str(sched["name"] or "")
            items = await db.fetch_all(
                """
                SELECT subject, catalog_nbr, selected_units
                FROM schedule_courses
                WHERE schedule_id = ? AND enabled = 1
                ORDER BY id ASC
                """,
                (sched["id"],),
            )
            for item in items:
                code = normalize_course_code(f"{item['subject']} {item['catalog_nbr']}")
                if code:
                    planned_courses[code] = {
                        "sem": roster_u,
                        "selected_units": item.get("selected_units"),
                    }

    # Collect all course codes we need metadata for (completed + currently taking + planned + manual)
    candidate_pool: list[dict[str, Any]] = []
    seen_pool: set[str] = set()
    for raw_code in completed_list:
        code = normalize_course_code(raw_code)
        if code and code not in seen_pool:
            seen_pool.add(code)
            candidate_pool.append({"code": code, "source": "completed", "sem": "Done"})

    for code in in_progress_list:
        if code not in seen_pool:
            seen_pool.add(code)
            candidate_pool.append({"code": code, "source": "in_progress", "sem": "Taking"})

    for code, pinfo in planned_courses.items():
        if code not in seen_pool:
            seen_pool.add(code)
            candidate_pool.append(
                {
                    "code": code,
                    "source": "schedule",
                    "sem": pinfo["sem"],
                    "selected_units": pinfo.get("selected_units"),
                }
            )

    manual_codes: set[str] = set()
    for slot_data in manual_slots.values():
        if isinstance(slot_data, dict):
            mc = normalize_course_code(str(slot_data.get("course") or ""))
            if mc:
                manual_codes.add(mc)

    all_codes = sorted(seen_pool | manual_codes)
    meta_by_code: dict[str, dict[str, Any]] = {}
    if all_codes:
        pairs = []
        for code in all_codes:
            parts = code.split(" ", 1)
            if len(parts) == 2:
                pairs.append((parts[0], parts[1]))
        if pairs:
            # Query active roster first, then fallback to any cached roster
            placeholders = " OR ".join("(subject = ? AND catalog_nbr = ?)" for _ in pairs)
            params: list[Any] = []
            for s, n in pairs:
                params.extend([s, n])
            meta_rows = await db.fetch_all(
                f"""
                SELECT roster, subject, catalog_nbr, title_short, title_long,
                       acad_career, acad_group, catalog_prereq, catalog_coreq,
                       catalog_num, units_min, units_max, has_letter_grade,
                       crosslists_json, components_json, enroll_groups_json,
                       crse_attrs_json
                FROM courses_meta
                WHERE {placeholders}
                ORDER BY CASE WHEN roster = ? THEN 0 ELSE 1 END, updated_at DESC
                """,
                [*params, roster_u],
            )
            for mr in meta_rows:
                code = normalize_course_code(f"{mr['subject']} {mr['catalog_nbr']}")
                if code and code not in meta_by_code:
                    meta_by_code[code] = {
                        **mr,
                        "attrs": extract_course_attributes(mr),
                    }

    for code in all_codes:
        if code not in meta_by_code and code in TRANSCRIPT_EQUIVALENT_CATALOG:
            eq = TRANSCRIPT_EQUIVALENT_CATALOG[code]
            meta_by_code[code] = {
                **eq,
                "roster": "",
                "attrs": list(eq.get("attrs") or []),
            }

    # Fallback CSRequirementsIndex for taken/planned courses from other rosters (e.g. FA26 electives)
    # or uncached historical courses so CS 4000+/5000+ & TEs still classify cleanly on any term.
    fallback_indexes: dict[str, CSRequirementsIndex] = {}
    fallback_rosters_needed: set[str] = set()
    synthetic_rows: list[dict[str, Any]] = []
    for code in all_codes:
        parts = code.split(" ", 1)
        if len(parts) != 2:
            continue
        subj, nbr = parts
        if cs_index.has_course(subj, nbr):
            continue
        mr = meta_by_code.get(code)
        if mr and mr.get("roster"):
            fallback_rosters_needed.add(str(mr["roster"]).upper())
        else:
            synthetic_rows.append(
                {
                    "subject": subj,
                    "catalog_nbr": nbr,
                    "title_short": code,
                    "title_long": code,
                    "acad_career": "GR" if parse_catalog_num(nbr) >= 5000 else "UG",
                    "acad_group": "EN" if subj in {"CS", "ECE", "ENGRD", "ENGRI", "ORIE", "MAE"} else "AS",
                    "catalog_prereq": "",
                    "catalog_coreq": "",
                    "catalog_num": parse_catalog_num(nbr),
                    "units_min": 3.0,
                    "units_max": 3.0,
                    "has_letter_grade": 1,
                    "crosslists_json": "[]",
                    "components_json": '["LEC"]',
                    "enroll_groups_json": "[]",
                }
            )

    for fb_roster in sorted(fallback_rosters_needed):
        fb_rows = await db.fetch_all(
            """
            SELECT subject, catalog_nbr, title_short, title_long,
                   acad_career, acad_group, catalog_prereq, catalog_coreq,
                   catalog_num, units_min, units_max, has_letter_grade,
                   crosslists_json, components_json, enroll_groups_json
            FROM courses_meta
            WHERE roster = ?
            """,
            (fb_roster,),
        )
        if fb_rows:
            fallback_indexes[fb_roster] = CSRequirementsIndex(fb_rows)

    synthetic_index = CSRequirementsIndex(synthetic_rows) if synthetic_rows else None

    def get_course_eligibility(code: str) -> CourseEligibility:
        parts = code.split(" ", 1)
        if len(parts) != 2:
            return CourseEligibility()
        subj, nbr = parts
        if cs_index.has_course(subj, nbr):
            return cs_index.get(subj, nbr)
        mr = meta_by_code.get(code)
        if mr and mr.get("roster"):
            fb_idx = fallback_indexes.get(str(mr["roster"]).upper())
            if fb_idx is not None and fb_idx.has_course(subj, nbr):
                return fb_idx.get(subj, nbr)
        if synthetic_index is not None and synthetic_index.has_course(subj, nbr):
            return synthetic_index.get(subj, nbr)
        return CourseEligibility()

    def enrich_code(code: str, fallback_source: str = "completed", fallback_sem: str = "") -> dict[str, Any]:
        norm = normalize_course_code(code) or code.upper().strip()
        meta = meta_by_code.get(norm) or TRANSCRIPT_EQUIVALENT_CATALOG.get(norm) or {}
        if norm in completed_set or fallback_source == "completed":
            det = course_details.get(norm) or {}
        elif norm in in_progress_set or fallback_source == "in_progress":
            det = in_progress_details.get(norm) or {}
        else:
            det = course_details.get(norm) or in_progress_details.get(norm) or {}
        attrs = list(meta.get("attrs") or [])
        cr = ""
        effective_units_max = float(meta.get("units_max") or 0.0) if meta else 0.0
        if norm in planned_courses and planned_courses[norm].get("selected_units"):
            su = float(planned_courses[norm]["selected_units"])
            cr = str(int(su)) if su.is_integer() else f"{su:g}"
            effective_units_max = su
        elif det.get("cr"):
            cr = str(det["cr"])
            try:
                du = float(cr)
                if du > 0:
                    effective_units_max = du
            except ValueError:
                pass
        elif meta:
            cr = _fmt_credits(meta.get("units_min"), meta.get("units_max"))

        resolved_sem = fallback_sem
        if det.get("sem") and (fallback_source != "schedule" or not fallback_sem):
            resolved_sem = str(det["sem"])

        return {
            "course": norm,
            "title": str(meta.get("title_long") or meta.get("title_short") or ""),
            "cr": cr,
            "effective_units_max": effective_units_max,
            "sem": resolved_sem,
            "gr": str(det.get("gr") or ""),
            "attrs": attrs,
            "source": fallback_source,
        }

    pool_enriched: list[dict[str, Any]] = [
        enrich_code(p["code"], fallback_source=p["source"], fallback_sem=p.get("sem", ""))
        for p in candidate_pool
    ]

    def _build_quick_list(quick_options: Optional[Iterable[str]]) -> list[dict[str, str]]:
        quick_list: list[dict[str, str]] = []
        for qc in quick_options or ():
            norm_qc = normalize_course_code(str(qc))
            if not norm_qc:
                continue
            info = enrich_code(norm_qc)
            quick_list.append({"code": info["course"], "title": info["title"], "cr": info["cr"]})
        return quick_list

    def _materialize_slot(
        spec: dict[str, Any],
        override: Any,
        matched_item: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        slot_id = spec["id"]
        label = spec["label"]
        expected = spec["expected"]
        search = spec["search"]
        note = spec.get("note", "")
        quick_list = _build_quick_list(spec.get("quick_options"))
        ov_dict = override if isinstance(override, dict) else {}

        if ov_dict.get("cleared"):
            return {
                "id": slot_id,
                "label": label,
                "expected": expected,
                "filled": False,
                "course": "",
                "title": "",
                "cr": "",
                "sem": "",
                "gr": "",
                "notes": str(ov_dict.get("notes") or note),
                "attrs": [],
                "source": "empty",
                "search": search,
                "quick_options": quick_list,
            }

        manual_course = normalize_course_code(str(ov_dict.get("course") or ""))
        if manual_course:
            base = enrich_code(
                manual_course,
                fallback_source=(
                    "completed"
                    if manual_course in completed_set
                    else (
                        "in_progress"
                        if manual_course in in_progress_set
                        else ("schedule" if manual_course in planned_courses else "manual")
                    )
                ),
                fallback_sem=(
                    "Taking"
                    if manual_course in in_progress_set
                    else (planned_courses[manual_course]["sem"] if manual_course in planned_courses else "")
                ),
            )
            ov_sem = str(ov_dict.get("sem") or "").strip()
            eff_sem = (
                base["sem"]
                if (not ov_sem or (ov_sem.upper() in ("DONE", "TAKING") and base["sem"]))
                else ov_sem
            )
            ov_cr = str(ov_dict.get("cr") or "").strip()
            eff_cr = base["cr"] if (not ov_cr or ("-" in ov_cr and base["cr"] and "-" not in base["cr"])) else ov_cr
            return {
                "id": slot_id,
                "label": label,
                "expected": expected,
                "filled": True,
                "course": base["course"],
                "title": base["title"] or str(ov_dict.get("title") or ""),
                "cr": eff_cr,
                "sem": eff_sem,
                "gr": str(ov_dict.get("gr") or base["gr"]),
                "notes": str(ov_dict.get("notes") or note),
                "attrs": base["attrs"],
                "source": "manual" if base["source"] == "manual" else base["source"],
                "search": search,
                "quick_options": quick_list,
            }

        if matched_item is not None:
            ov_sem = str(ov_dict.get("sem") or "").strip()
            eff_sem = (
                matched_item["sem"]
                if (not ov_sem or (ov_sem.upper() in ("DONE", "TAKING") and matched_item["sem"]))
                else ov_sem
            )
            ov_cr = str(ov_dict.get("cr") or "").strip()
            eff_cr = matched_item["cr"] if (not ov_cr or ("-" in ov_cr and matched_item["cr"] and "-" not in matched_item["cr"])) else ov_cr
            return {
                "id": slot_id,
                "label": label,
                "expected": expected,
                "filled": True,
                "course": matched_item["course"],
                "title": matched_item["title"],
                "cr": eff_cr,
                "sem": eff_sem,
                "gr": str(ov_dict.get("gr") or matched_item["gr"]),
                "notes": str(ov_dict.get("notes") or note),
                "attrs": matched_item["attrs"],
                "source": matched_item["source"],
                "search": search,
                "quick_options": quick_list,
            }

        return {
            "id": slot_id,
            "label": label,
            "expected": expected,
            "filled": False,
            "course": "",
            "title": "",
            "cr": "",
            "sem": "",
            "gr": "",
            "notes": str(ov_dict.get("notes") or note),
            "attrs": [],
            "source": "empty",
            "search": search,
            "quick_options": quick_list,
        }

    def resolve_exclusive_group(slot_specs: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], int]:
        """Globally assign courses to non-double-countable slots maximizing total filled boxes."""
        fixed: dict[str, dict[str, Any]] = {}
        reserved_courses: set[str] = set()
        open_specs: list[dict[str, Any]] = []

        for spec in slot_specs:
            sid = spec["id"]
            ov = manual_slots.get(sid)
            if isinstance(ov, dict) and ov.get("cleared"):
                fixed[sid] = _materialize_slot(spec, ov, None)
                continue
            mc = normalize_course_code(str(ov.get("course") or "")) if isinstance(ov, dict) else None
            if mc:
                fixed[sid] = _materialize_slot(spec, ov, None)
                reserved_courses.add(mc)
                continue
            open_specs.append(spec)

        avail = [
            (orig_idx, item)
            for orig_idx, item in enumerate(pool_enriched)
            if item["course"] not in reserved_courses
        ]
        edges: list[tuple[int, int, int]] = []
        for c_idx, (orig_idx, item) in enumerate(avail):
            comp_bonus = (
                2 * 10**9
                if item["source"] == "completed"
                else (10**9 if item["source"] == "in_progress" else 0)
            )
            for s_idx, spec in enumerate(open_specs):
                if spec["matcher"](item):
                    tier_bonus = int(spec.get("tier", 1)) * 10**6
                    order_penalty = orig_idx * 100 + s_idx
                    edges.append((c_idx, s_idx, 10**12 + comp_bonus + tier_bonus - order_penalty))

        matched_s_to_c, score = _solve_max_bipartite_matching(len(avail), len(open_specs), edges)
        resolved = dict(fixed)
        for s_idx, spec in enumerate(open_specs):
            c_idx = matched_s_to_c.get(s_idx)
            matched_item = avail[c_idx][1] if c_idx is not None else None
            resolved[spec["id"]] = _materialize_slot(spec, manual_slots.get(spec["id"]), matched_item)
        return resolved, score

    def resolve_non_exclusive_slot(spec: dict[str, Any]) -> dict[str, Any]:
        """Resolve a slot in a category where double counting is allowed (e.g. A&S Distributions)."""
        sid = spec["id"]
        ov = manual_slots.get(sid)
        matched_item: Optional[dict[str, Any]] = None
        for item in pool_enriched:
            if spec["matcher"](item):
                matched_item = item
                break
        return _materialize_slot(spec, ov, matched_item)

    # --- Build Requirement Specs ---
    def _is_cs_project(it: dict[str, Any]) -> bool:
        return get_course_eligibility(it["course"]).cs_project

    def _is_cs_elective(it: dict[str, Any]) -> bool:
        code = it["course"]
        if code in _EXCLUDED_FIXED_CODES:
            return False
        elig = get_course_eligibility(code)
        return elig.cs_elective_pre2024 if curriculum == "pre2024" else elig.cs_elective

    def _is_tech_elective(it: dict[str, Any]) -> bool:
        code = it["course"]
        if code in _EXCLUDED_FIXED_CODES:
            return False
        return get_course_eligibility(code).tech_elective

    def _is_ext_spec(it: dict[str, Any]) -> bool:
        return get_course_eligibility(it["course"]).external_spec

    core_specs: list[dict[str, Any]] = []
    for spec in CORE_MATCHERS:
        if spec.get("current_only") and curriculum == "pre2024":
            continue
        opts = spec["options"]
        core_specs.append(
            {
                "id": spec["id"],
                "label": spec["label"],
                "expected": spec["expected"],
                "search": spec["search"],
                "matcher": lambda it, opts=opts: it["course"] in opts,
                "quick_options": sorted(opts),
                "tier": 6,
            }
        )

    college_math_specs: list[dict[str, Any]] = []
    if college == "arts":
        for spec in ARTS_MATH_INTRO_MATCHERS:
            opts = spec["options"]
            college_math_specs.append(
                {
                    "id": spec["id"],
                    "label": spec["label"],
                    "expected": spec["expected"],
                    "search": spec["search"],
                    "matcher": lambda it, opts=opts: it["course"] in opts,
                    "quick_options": sorted(opts),
                    "tier": 6,
                }
            )
    else:
        for spec in ENG_MATH_SCI_MATCHERS:
            opts = spec["options"]
            attr_req = spec.get("attr_match")
            excl = spec.get("exclude", set())

            def _eng_match(it: dict[str, Any], opts=opts, attr_req=attr_req, excl=excl) -> bool:
                if it["course"] in excl:
                    return False
                if opts:
                    return it["course"] in opts
                if attr_req:
                    return attr_req in it["attrs"]
                return False

            college_math_specs.append(
                {
                    "id": spec["id"],
                    "label": spec["label"],
                    "expected": spec["expected"],
                    "search": spec["search"],
                    "matcher": _eng_match,
                    "quick_options": sorted(opts),
                    "tier": 6,
                }
            )

    proj_spec: dict[str, Any] = {
        "id": "cs_proj",
        "label": "CS Project",
        "expected": "CS 4xx1 Practicum / 3152 / 4152 / 5150",
        "search": {"cs_requirement": "cs_project", "subjects": ["CS"]},
        "matcher": _is_cs_project,
        "tier": 5,
    }
    cs_elec_count = 2 if curriculum == "current" else 3
    cs_elec_specs: list[dict[str, Any]] = [
        {
            "id": f"cs_elec_{i}",
            "label": f"CS Elective {i}",
            "expected": "CS 4000+ non-core (>=3 cr letter)",
            "search": {"cs_requirement": "cs_elective", "subjects": ["CS"]},
            "matcher": _is_cs_elective,
            "tier": 4,
        }
        for i in range(1, cs_elec_count + 1)
    ]
    tech_elec_specs: list[dict[str, Any]] = [
        {
            "id": f"tech_elec_{i}",
            "label": f"Tech Elective {i}",
            "expected": "3000+ STEM / Quant application area",
            "search": {"cs_requirement": "tech_elective"},
            "matcher": _is_tech_elective,
            "tier": 2,
        }
        for i in range(1, 4)
    ]

    def _build_ext_specs(
        target_subjects: Optional[frozenset[str]],
        label_hint: str,
        tier: int = 3,
    ) -> list[dict[str, Any]]:
        subj_list = sorted(target_subjects) if target_subjects else []
        return [
            {
                "id": f"ext_spec_{i}",
                "label": f"External Spec {i}",
                "expected": label_hint,
                "search": {
                    "cs_requirement": "external_spec",
                    **({"subjects": subj_list} if subj_list else {}),
                },
                "matcher": lambda it, ts=target_subjects: _is_ext_spec(it)
                and (not ts or it["course"].split(" ", 1)[0] in ts),
                "tier": tier,
            }
            for i in range(1, 4)
        ]

    maj_count = 1 if curriculum == "current" else 3
    maj_elec_specs: list[dict[str, Any]] = [
        {
            "id": f"maj_elec_{i}",
            "label": f"Major Approved {i}" if maj_count > 1 else "Major Approved Elective",
            "expected": "Any 3+ cr academic course (no PE)",
            "search": {"min_credits": 3},
            "matcher": lambda it: (
                not it["course"].startswith("PE ")
                and (it["effective_units_max"] == 0.0 or it["effective_units_max"] >= 3.0)
            ),
            "tier": 1,
        }
        for i in range(1, maj_count + 1)
    ]

    # Jointly optimize Group A (Core + Math/Sci + Project + CS Electives + Tech + Ext Spec + Maj Approved)
    # Prefer same-department External Spec (tier 3, no warning), and soft-allow closely related
    # interdisciplinary clusters (tier 2) when single-department cannot fill as many boxes.
    pinned_ext_subjects: set[str] = set()
    for i in range(1, 4):
        ov = manual_slots.get(f"ext_spec_{i}")
        if isinstance(ov, dict) and not ov.get("cleared"):
            mc = normalize_course_code(str(ov.get("course") or ""))
            if mc:
                pinned_ext_subjects.add(mc.split(" ", 1)[0])

    ext_candidates: list[tuple[Optional[frozenset[str]], str, int]] = []
    if pinned_ext_subjects:
        if len(pinned_ext_subjects) == 1:
            psubj = next(iter(pinned_ext_subjects))
            ext_candidates.append(
                (frozenset({psubj}), f"3000+ {psubj} outside CS (or related w/ approval)", 3)
            )
        for cluster_name, cluster_set in RELATED_EXT_SPEC_CLUSTERS:
            if pinned_ext_subjects.issubset(cluster_set):
                ext_candidates.append(
                    (cluster_set, f"3000+ related ({cluster_name}) · advisor approval", 2)
                )
        if not ext_candidates:
            ext_candidates.append((None, "3000+ related dept outside CS · advisor approval", 2))
    else:
        ext_pool_subjs = sorted(
            {it["course"].split(" ", 1)[0] for it in pool_enriched if _is_ext_spec(it)}
        )
        for subj in ext_pool_subjs:
            ext_candidates.append(
                (frozenset({subj}), f"3000+ {subj} outside CS (or related w/ approval)", 3)
            )
        ext_pool_set = set(ext_pool_subjs)
        for cluster_name, cluster_set in RELATED_EXT_SPEC_CLUSTERS:
            if len(ext_pool_set & cluster_set) >= 2:
                ext_candidates.append(
                    (cluster_set, f"3000+ related ({cluster_name}) · advisor approval", 2)
                )
        if not ext_candidates:
            ext_candidates.append((None, "3000+ same dept outside CS (or related w/ approval)", 3))

    best_group_a: dict[str, dict[str, Any]] = {}
    best_group_a_score = -1
    for cand_set, cand_hint, cand_tier in ext_candidates:
        ext_specs = _build_ext_specs(cand_set, cand_hint, tier=cand_tier)
        group_a_specs = [
            *core_specs,
            *college_math_specs,
            proj_spec,
            *cs_elec_specs,
            *ext_specs,
            *tech_elec_specs,
            *maj_elec_specs,
        ]
        resolved_map, score = resolve_exclusive_group(group_a_specs)
        if score > best_group_a_score:
            best_group_a_score = score
            best_group_a = resolved_map

    # If no External Spec slot ended up filled and nothing was pinned, keep empty hint generic
    if not pinned_ext_subjects and not any(best_group_a[f"ext_spec_{i}"]["filled"] for i in range(1, 4)):
        for i in range(1, 4):
            s = best_group_a[f"ext_spec_{i}"]
            s["expected"] = "3000+ same dept outside CS (or related w/ approval)"
            s["search"] = {"cs_requirement": "external_spec"}

    ext_spec_slots = [best_group_a[f"ext_spec_{i}"] for i in range(1, 4)]
    filled_ext_subjs = {
        sl["course"].split(" ", 1)[0]
        for sl in ext_spec_slots
        if sl["filled"] and " " in sl["course"]
    }
    if len(filled_ext_subjs) > 1:
        for sl in ext_spec_slots:
            if sl["filled"]:
                sl["warning"] = EXT_SPEC_ADVISOR_WARNING

    core_slots = [best_group_a[s["id"]] for s in core_specs]
    math_or_eng_slots = [best_group_a[s["id"]] for s in college_math_specs]
    proj_slot = best_group_a["cs_proj"]
    cs_elec_slots = [best_group_a[f"cs_elec_{i}"] for i in range(1, cs_elec_count + 1)]
    tech_elec_slots = [best_group_a[f"tech_elec_{i}"] for i in range(1, 4)]
    maj_slots = [best_group_a[f"maj_elec_{i}"] for i in range(1, maj_count + 1)]

    # --- Assemble Sections (plus College-specific exclusive & distribution groups) ---
    sections: list[dict[str, Any]] = []
    as_dist_summary: Optional[dict[str, Any]] = None
    if college == "arts":
        def _is_lang_option_a(it: dict[str, Any]) -> bool:
            if "LANG" not in it["attrs"]:
                return False
            parts = it["course"].split(" ", 1)
            cat_num = parse_catalog_num(parts[1]) if len(parts) == 2 else 0
            return cat_num >= 2000 and (
                it["effective_units_max"] == 0.0 or it["effective_units_max"] >= 3.0
            )

        as_college_specs = [
            {
                "id": "as_fws_1",
                "label": "FWS 1",
                "expected": "First-Year Writing Seminar",
                "search": {"attrs": ["FWS"]},
                "matcher": lambda it: "FWS" in it["attrs"],
                "quick_options": ["ENGL 1100F"],
                "tier": 2,
            },
            {
                "id": "as_fws_2",
                "label": "FWS 2",
                "expected": "First-Year Writing Seminar",
                "search": {"attrs": ["FWS"]},
                "matcher": lambda it: "FWS" in it["attrs"],
                "quick_options": ["ENGL 1100F"],
                "tier": 2,
            },
            {
                "id": "as_lang_1",
                "label": "Lang 1",
                "expected": "Foreign Language",
                "search": {"attrs": ["LANG"]},
                "matcher": lambda it: "LANG" in it["attrs"],
                "tier": 1,
            },
            {
                "id": "as_lang_2",
                "label": "Lang 2",
                "expected": "Foreign Language",
                "search": {"attrs": ["LANG"]},
                "matcher": lambda it: "LANG" in it["attrs"],
                "tier": 1,
            },
            {
                "id": "as_lang_3",
                "label": "Lang 3",
                "expected": "Foreign Language (Opt. 2000+ single course)",
                "search": {"attrs": ["LANG"]},
                "matcher": lambda it: "LANG" in it["attrs"],
                "tier": 1,
            },
        ]
        college_resolved, _ = resolve_exclusive_group(as_college_specs)

        # Evaluate Option A: a single 2000+ (3+ cr) LANG course in Lang 3 satisfies the full
        # A&S foreign language requirement and waives/greys out Lang 1 & Lang 2.
        opt_a_specs = [
            as_college_specs[0],
            as_college_specs[1],
            {
                **as_college_specs[4],
                "matcher": _is_lang_option_a,
                "tier": 3,
            },
        ]
        plan_a, _ = resolve_exclusive_group(opt_a_specs)
        opt_a_slot = plan_a["as_lang_3"]
        opt_a_course = opt_a_slot["course"] if opt_a_slot["filled"] else ""
        opt_a_valid = bool(opt_a_course) and (
            _is_lang_option_a(enrich_code(opt_a_course))
            or parse_catalog_num(opt_a_course.split(" ", 1)[1] if " " in opt_a_course else "") >= 2000
        )
        if opt_a_valid:
            plan_a_fws = sum(1 for k in ("as_fws_1", "as_fws_2") if plan_a[k]["filled"])
            plan_b_total = sum(1 for s in college_resolved.values() if s["filled"])
            if plan_a_fws + 3 >= plan_b_total:
                college_resolved["as_fws_1"] = plan_a["as_fws_1"]
                college_resolved["as_fws_2"] = plan_a["as_fws_2"]
                college_resolved["as_lang_3"] = {
                    **opt_a_slot,
                    "notes": opt_a_slot.get("notes") or "Option A satisfied (2000+ single course)",
                }
                for l_id in ("as_lang_1", "as_lang_2"):
                    ov = manual_slots.get(l_id)
                    pinned_other = (
                        isinstance(ov, dict)
                        and not ov.get("cleared")
                        and bool(normalize_course_code(str(ov.get("course") or "")))
                    )
                    if not pinned_other:
                        college_resolved[l_id] = {
                            **college_resolved[l_id],
                            "filled": False,
                            "waived": True,
                            "waived_by": opt_a_course,
                            "course": "",
                            "title": "",
                            "cr": "",
                            "sem": "",
                            "gr": "",
                            "attrs": [],
                            "source": "waived",
                            "notes": f"Satisfied by {opt_a_course} (2000+ Option A)",
                        }

        sections.append(
            {
                "id": "college_req",
                "title": "College Requirements (A&S)",
                "subtitle": "2 Freshman Writing Seminars, Foreign Language sequence (or 2000+ course), & 2 PE courses",
                "slots": [college_resolved[s["id"]] for s in as_college_specs],
            }
        )

        # A&S 10 Distributions (double-counting allowed with Math/CS & across categories):
        # First assign distinct courses across categories via maximum bipartite matching so unique
        # distribution courses are maximized toward the 8-course minimum, then allow double counting
        # for any remaining uncovered categories.
        dist_specs: list[dict[str, Any]] = []
        for api_code, display_code, descr in AS_DIST_DISPLAY:
            slot_id = f"as_dist_{display_code.lower().replace('-', '_')}"
            dist_specs.append(
                {
                    "id": slot_id,
                    "label": display_code,
                    "expected": descr,
                    "search": {"attrs": [api_code]},
                    "matcher": lambda it, ac=api_code: ac in it["attrs"]
                    or normalize_attr_code(ac) in it["attrs"],
                    "attr_code": api_code,
                    "tier": 1,
                }
            )

        dist_resolved, _ = resolve_exclusive_group(dist_specs)
        dist_slots: list[dict[str, Any]] = []
        unique_dist_courses: set[str] = set()
        covered_dist_cats = 0
        for spec in dist_specs:
            slot = dist_resolved[spec["id"]]
            if not slot["filled"]:
                slot = resolve_non_exclusive_slot(spec)
            slot["attr_code"] = spec["attr_code"]
            dist_slots.append(slot)
            if slot["filled"]:
                covered_dist_cats += 1
                if slot["course"]:
                    unique_dist_courses.add(slot["course"])

        as_dist_summary = {
            "covered_categories": covered_dist_cats,
            "total_categories": 10,
            "unique_courses": len(unique_dist_courses),
            "min_unique_courses": 8,
        }
        sections.append(
            {
                "id": "as_distribution",
                "title": "A&S Distribution Requirements",
                "subtitle": f"{covered_dist_cats}/10 categories covered · {len(unique_dist_courses)}/8 minimum unique courses (double counting allowed)",
                "slots": dist_slots,
            }
        )
        sections.append(
            {
                "id": "math_intro",
                "title": "Mathematics & Intro CS",
                "subtitle": "Calculus I–II, Linear Algebra, CS 1110/1112 & CS 2110/2112",
                "slots": math_or_eng_slots,
            }
        )
    else:
        sections.append(
            {
                "id": "eng_math_sci",
                "title": "Engineering Math, Sciences & Intro",
                "subtitle": "MATH 1910–2940, PHYS 1112/2213, CHEM 2090, ENGRI, ENGRD, & Intro CS",
                "slots": math_or_eng_slots,
            }
        )

        lib_set = set(LIBERAL_STUDIES_ATTRS)
        eng_lib_specs: list[dict[str, Any]] = [
            {
                "id": "eng_fws_1",
                "label": "FWS 1",
                "expected": "First-Year Writing Seminar",
                "search": {"attrs": ["FWS"]},
                "matcher": lambda it: "FWS" in it["attrs"],
                "quick_options": ["ENGL 1100F"],
                "tier": 2,
            },
            {
                "id": "eng_fws_2",
                "label": "FWS 2",
                "expected": "First-Year Writing Seminar",
                "search": {"attrs": ["FWS"]},
                "matcher": lambda it: "FWS" in it["attrs"],
                "quick_options": ["ENGL 1100F"],
                "tier": 2,
            },
            *[
                {
                    "id": f"eng_lib_{idx}",
                    "label": f"Liberal Studies {idx}",
                    "expected": "CA / HA / KCM / LA / SBA / FL (18+ cr total, 2x 2000+)",
                    "search": {"attrs": ["CA-AG", "HA-AG", "KCM-AG", "LA-AG", "SBA-AG"]},
                    "matcher": lambda it, ls=lib_set: any(a in ls for a in it["attrs"]),
                    "tier": 1,
                }
                for idx in range(1, 7)
            ],
        ]
        eng_lib_resolved, _ = resolve_exclusive_group(eng_lib_specs)
        sections.append(
            {
                "id": "eng_liberal",
                "title": "Writing & Liberal Studies (Engineering)",
                "subtitle": "2 FWS + 6 Liberal Studies courses across >=3 categories (18+ cr)",
                "slots": [eng_lib_resolved[s["id"]] for s in eng_lib_specs],
            }
        )

    sections.append(
        {
            "id": "cs_core",
            "title": "Computer Science Core",
            "subtitle": "Must be passed with C- or better; CS 2800/3110/3410/4410/4820"
            + (" + CS 3780/3700 (Fall 2024+)" if curriculum == "current" else " (Pre-Fall 2024)"),
            "slots": core_slots,
        }
    )

    sections.append(
        {
            "id": "cs_electives",
            "title": "CS Electives, Project, Technical & External Specialization",
            "subtitle": "No double counting across electives, project, technical electives, external spec, or core",
            "slots": [
                *cs_elec_slots,
                proj_slot,
                *tech_elec_slots,
                *ext_spec_slots,
                *maj_slots,
            ],
        }
    )

    # Summary stats (exclude waived Option A language slots so 100% completion reaches 0 remaining)
    active_boxes = [sl for sec in sections for sl in sec["slots"] if not sl.get("waived")]
    total_boxes = len(active_boxes)
    filled_boxes = sum(1 for sl in active_boxes if sl["filled"])
    completed_boxes = sum(1 for sl in active_boxes if sl["filled"] and sl["source"] == "completed")
    in_progress_boxes = sum(1 for sl in active_boxes if sl["filled"] and sl["source"] == "in_progress")
    whatif_boxes = sum(1 for sl in active_boxes if sl["filled"] and sl["source"] == "schedule")

    missing_metadata_courses = [code for code in all_codes if code not in meta_by_code]

    return {
        "roster": roster_u,
        "college": college,
        "curriculum": curriculum,
        "include_active_schedule": include_sched,
        "active_schedule_name": active_schedule_name,
        "pe_completed": saved["pe_completed"],
        "completed_courses": completed_list,
        "completed_course_details": course_details,
        "in_progress_courses": in_progress_list,
        "in_progress_course_details": in_progress_details,
        "planned_courses": sorted(planned_courses.keys()),
        "missing_metadata_courses": missing_metadata_courses,
        "as_distribution_summary": as_dist_summary,
        "summary": {
            "total_slots": total_boxes,
            "filled_slots": filled_boxes,
            "completed_slots": completed_boxes,
            "in_progress_slots": in_progress_boxes,
            "whatif_slots": whatif_boxes,
            "remaining_slots": total_boxes - filled_boxes,
        },
        "sections": sections,
        "manual_slots": manual_slots,
    }


async def merge_transcript_into_user_checklist(
    db: Database,
    user_id: int,
    imported_completed: list[dict[str, str]],
    pe_completed: Optional[int] = None,
    imported_in_progress: Optional[list[dict[str, str]]] = None,
    sync_in_progress_to_checklist: bool = True,
) -> dict[str, Any]:
    """Merge imported completed & currently-taking courses without duplicates or clobbering."""
    row = await db.fetch_one(
        """
        SELECT cs_checklist_json, completed_courses_json, completed_course_details_json,
               in_progress_courses_json, in_progress_course_details_json
        FROM users WHERE id = ?
        """,
        (user_id,),
    )
    existing_completed = decode_completed_courses(row.get("completed_courses_json") if row else None)
    existing_details = decode_completed_course_details(row.get("completed_course_details_json") if row else None)
    existing_in_progress = decode_completed_courses(row.get("in_progress_courses_json") if row else None)
    existing_in_progress_details = decode_completed_course_details(
        row.get("in_progress_course_details_json") if row else None
    )
    saved = decode_checklist_state(row.get("cs_checklist_json") if row else None)

    existing_set = set(existing_completed)
    incoming_by_code: dict[str, dict[str, str]] = {}
    for item in imported_completed:
        code = normalize_course_code(str(item.get("course") or ""))
        if not code:
            continue
        cleaned = normalize_course_detail(item)
        if code in incoming_by_code:
            merged_dup, _ = merge_course_detail_fields(incoming_by_code[code], cleaned)
            incoming_by_code[code] = merged_dup
        else:
            incoming_by_code[code] = cleaned

    added_courses = sorted(c for c in incoming_by_code if c not in existing_set)
    merged_completed = normalize_completed_courses([*existing_completed, *incoming_by_code.keys()])
    merged_completed_set = set(merged_completed)

    merged_details = dict(existing_details)
    enriched_courses: list[str] = []
    unchanged_courses: list[str] = []
    for code, inc_det in incoming_by_code.items():
        if code in merged_details:
            updated_det, changed = merge_course_detail_fields(merged_details[code], inc_det)
            if updated_det:
                merged_details[code] = updated_det
            if code in existing_set:
                if changed:
                    enriched_courses.append(code)
                else:
                    unchanged_courses.append(code)
        elif inc_det:
            merged_details[code] = inc_det
            if code in existing_set:
                enriched_courses.append(code)
        elif code in existing_set:
            unchanged_courses.append(code)

    # Merge imported in-progress courses into Currently Taking (graduating any newly completed ones)
    in_progress_incoming_by_code: dict[str, dict[str, str]] = {}
    if sync_in_progress_to_checklist and imported_in_progress:
        for item in imported_in_progress:
            code = normalize_course_code(str(item.get("course") or ""))
            if not code or code in merged_completed_set:
                continue
            cleaned = normalize_course_detail(
                {"sem": str(item.get("roster") or "").strip().upper(), "cr": str(item.get("cr") or "").strip()}
            )
            if code in in_progress_incoming_by_code:
                merged_dup, _ = merge_course_detail_fields(in_progress_incoming_by_code[code], cleaned)
                in_progress_incoming_by_code[code] = merged_dup
            else:
                in_progress_incoming_by_code[code] = cleaned

    existing_in_progress_set = set(existing_in_progress)
    added_in_progress = sorted(
        c for c in in_progress_incoming_by_code if c not in existing_in_progress_set
    )
    merged_in_progress = [
        c
        for c in normalize_completed_courses([*existing_in_progress, *in_progress_incoming_by_code.keys()])
        if c not in merged_completed_set
    ]
    merged_in_progress_set = set(merged_in_progress)
    merged_in_progress_details = {
        k: dict(v) for k, v in existing_in_progress_details.items() if k in merged_in_progress_set
    }
    for code, inc_det in in_progress_incoming_by_code.items():
        if code not in merged_in_progress_set:
            continue
        if code in merged_in_progress_details:
            updated_det, _ = merge_course_detail_fields(merged_in_progress_details[code], inc_det)
            if updated_det:
                merged_in_progress_details[code] = updated_det
        elif inc_det:
            merged_in_progress_details[code] = inc_det

    # Enrich existing non-cleared manual checklist slots holding any imported course
    # (adding missing/placeholder gr, sem, cr while keeping user's notes, pinned, title, placement).
    all_incoming_details = {**in_progress_incoming_by_code, **incoming_by_code}
    updated_slots = {k: dict(v) if isinstance(v, dict) else v for k, v in saved["slots"].items()}
    enriched_slots: list[str] = []
    for slot_id, slot_val in list(updated_slots.items()):
        if not isinstance(slot_val, dict) or slot_val.get("cleared"):
            continue
        slot_code = normalize_course_code(str(slot_val.get("course") or ""))
        if not slot_code or slot_code not in all_incoming_details:
            continue
        inc_det = all_incoming_details[slot_code]
        merged_slot, slot_changed = merge_course_detail_fields(slot_val, inc_det)
        if slot_changed:
            updated_slots[slot_id] = merged_slot
            enriched_slots.append(slot_id)
            if slot_code not in enriched_courses and slot_code in existing_set:
                enriched_courses.append(slot_code)
                if slot_code in unchanged_courses:
                    unchanged_courses.remove(slot_code)

    next_pe = saved["pe_completed"]
    if pe_completed is not None:
        next_pe = max(saved["pe_completed"], max(0, min(4, int(pe_completed))))

    next_checklist_json = json.dumps(
        {
            "college": saved["college"],
            "curriculum": saved["curriculum"],
            "include_active_schedule": saved["include_active_schedule"],
            "pe_completed": next_pe,
            "slots": updated_slots,
        }
    )

    async with db.write_tx() as conn:
        await conn.execute(
            """
            UPDATE users
            SET completed_courses_json = ?,
                completed_course_details_json = ?,
                in_progress_courses_json = ?,
                in_progress_course_details_json = ?,
                cs_checklist_json = ?
            WHERE id = ?
            """,
            (
                json.dumps(merged_completed),
                json.dumps(merged_details),
                json.dumps(merged_in_progress),
                json.dumps(merged_in_progress_details),
                next_checklist_json,
                user_id,
            ),
        )

    return {
        "completed_courses": merged_completed,
        "completed_course_details": merged_details,
        "in_progress_courses": merged_in_progress,
        "in_progress_course_details": merged_in_progress_details,
        "added_courses": added_courses,
        "added_in_progress": added_in_progress,
        "enriched_courses": sorted(enriched_courses),
        "unchanged_courses": sorted(unchanged_courses),
        "enriched_slots": enriched_slots,
        "pe_completed": next_pe,
    }
