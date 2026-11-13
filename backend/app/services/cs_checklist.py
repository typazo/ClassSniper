"""Interactive Cornell CS Checklist builder & What-If evaluator (A&S and Engineering)."""

from __future__ import annotations

import json
from typing import Any, Iterable, Optional

from app.db import Database
from app.services.attributes import AS_DISTRIBUTION_CODES, extract_course_attributes, normalize_attr_code
from app.services.cs_requirements import (
    CSRequirementsIndex,
    CourseEligibility,
    normalize_course_code,
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


def _fmt_credits(u_min: Any, u_max: Any) -> str:
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


async def build_cs_checklist_payload(
    db: Database,
    user: dict[str, Any],
    cs_index: CSRequirementsIndex,
    roster: str,
    completed_courses_override: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Evaluate user's CS Checklist combining completed courses, active schedule (What-If), and manual slot edits."""
    roster_u = roster.upper()
    row = await db.fetch_one(
        "SELECT cs_checklist_json, completed_courses_json FROM users WHERE id = ?",
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

    # Collect all course codes we need metadata for (completed + planned + manual)
    candidate_pool: list[dict[str, Any]] = []
    seen_pool: set[str] = set()
    for raw_code in completed_list:
        code = normalize_course_code(raw_code)
        if code and code not in seen_pool:
            seen_pool.add(code)
            candidate_pool.append({"code": code, "source": "completed", "sem": "Done"})

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
        meta = meta_by_code.get(norm, {})
        attrs = list(meta.get("attrs") or [])
        cr = ""
        if norm in planned_courses and planned_courses[norm].get("selected_units"):
            su = float(planned_courses[norm]["selected_units"])
            cr = str(int(su)) if su.is_integer() else f"{su:g}"
        elif meta:
            cr = _fmt_credits(meta.get("units_min"), meta.get("units_max"))
        return {
            "course": norm,
            "title": str(meta.get("title_long") or meta.get("title_short") or ""),
            "cr": cr,
            "sem": fallback_sem,
            "gr": "",
            "attrs": attrs,
            "source": fallback_source,
        }

    pool_enriched: list[dict[str, Any]] = [
        enrich_code(p["code"], fallback_source=p["source"], fallback_sem=p.get("sem", ""))
        for p in candidate_pool
    ]

    def resolve_manual_or_auto(
        slot_id: str,
        label: str,
        expected: str,
        search: dict[str, Any],
        auto_matcher: Any,
        used_in_group: Optional[set[str]] = None,
        note: str = "",
    ) -> dict[str, Any]:
        override = manual_slots.get(slot_id)
        if isinstance(override, dict) and override.get("cleared"):
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
                "notes": str(override.get("notes") or note),
                "attrs": [],
                "source": "empty",
                "search": search,
            }

        manual_course = (
            normalize_course_code(str(override.get("course") or ""))
            if isinstance(override, dict)
            else None
        )
        if manual_course:
            base = enrich_code(
                manual_course,
                fallback_source=("schedule" if manual_course in planned_courses else ("completed" if manual_course in seen_pool else "manual")),
                fallback_sem=(planned_courses[manual_course]["sem"] if manual_course in planned_courses else ""),
            )
            if used_in_group is not None:
                used_in_group.add(manual_course)
            return {
                "id": slot_id,
                "label": label,
                "expected": expected,
                "filled": True,
                "course": base["course"],
                "title": str(override.get("title") or base["title"]),
                "cr": str(override.get("cr") or base["cr"]),
                "sem": str(override.get("sem") or base["sem"]),
                "gr": str(override.get("gr") or ""),
                "notes": str(override.get("notes") or note),
                "attrs": base["attrs"],
                "source": "manual" if base["source"] == "manual" else base["source"],
                "search": search,
            }

        # Auto-match from completed + schedule pool
        for item in pool_enriched:
            code = item["course"]
            if used_in_group is not None and code in used_in_group:
                continue
            if auto_matcher(item):
                if used_in_group is not None:
                    used_in_group.add(code)
                return {
                    "id": slot_id,
                    "label": label,
                    "expected": expected,
                    "filled": True,
                    "course": code,
                    "title": item["title"],
                    "cr": str((override or {}).get("cr") or item["cr"]),
                    "sem": str((override or {}).get("sem") or item["sem"]),
                    "gr": str((override or {}).get("gr") or ""),
                    "notes": str((override or {}).get("notes") or note),
                    "attrs": item["attrs"],
                    "source": item["source"],
                    "search": search,
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
            "notes": str((override or {}).get("notes") or note),
            "attrs": [],
            "source": "empty",
            "search": search,
        }

    # --- Build Sections ---
    sections: list[dict[str, Any]] = []
    used_non_double_electives: set[str] = set()

    # Track core choice winners so CS 3700/3780 doesn't count as BOTH core & elective unless unused
    core_slots: list[dict[str, Any]] = []
    used_core_codes: set[str] = set()
    for spec in CORE_MATCHERS:
        if spec.get("current_only") and curriculum == "pre2024":
            continue
        opts = spec["options"]
        slot = resolve_manual_or_auto(
            slot_id=spec["id"],
            label=spec["label"],
            expected=spec["expected"],
            search=spec["search"],
            auto_matcher=lambda item, opts=opts: item["course"] in opts,
            used_in_group=used_core_codes,
        )
        core_slots.append(slot)
        if slot["filled"] and slot["course"]:
            used_non_double_electives.add(slot["course"])

    # College-specific sections
    as_dist_summary: Optional[dict[str, Any]] = None
    if college == "arts":
        fws_used: set[str] = set()
        college_slots = [
            resolve_manual_or_auto(
                "as_fws_1",
                "FWS 1",
                "First-Year Writing Seminar",
                {"attrs": ["FWS"]},
                lambda it: "FWS" in it["attrs"],
                used_in_group=fws_used,
            ),
            resolve_manual_or_auto(
                "as_fws_2",
                "FWS 2",
                "First-Year Writing Seminar",
                {"attrs": ["FWS"]},
                lambda it: "FWS" in it["attrs"],
                used_in_group=fws_used,
            ),
            resolve_manual_or_auto(
                "as_lang_1",
                "Lang 1",
                "Foreign Language",
                {"attrs": ["LANG"]},
                lambda it: "LANG" in it["attrs"],
                used_in_group=fws_used,
            ),
            resolve_manual_or_auto(
                "as_lang_2",
                "Lang 2",
                "Foreign Language",
                {"attrs": ["LANG"]},
                lambda it: "LANG" in it["attrs"],
                used_in_group=fws_used,
            ),
            resolve_manual_or_auto(
                "as_lang_3",
                "Lang 3",
                "Foreign Language (Opt. 2000+ single course)",
                {"attrs": ["LANG"]},
                lambda it: "LANG" in it["attrs"],
                used_in_group=fws_used,
            ),
        ]
        sections.append(
            {
                "id": "college_req",
                "title": "College Requirements (A&S)",
                "subtitle": "2 Freshman Writing Seminars, Foreign Language sequence (or 2000+ course), & 2 PE courses",
                "slots": college_slots,
            }
        )

        # A&S 10 Distributions (double-counting allowed with Math/CS!)
        dist_slots: list[dict[str, Any]] = []
        unique_dist_courses: set[str] = set()
        covered_dist_cats = 0
        for api_code, display_code, descr in AS_DIST_DISPLAY:
            slot_id = f"as_dist_{display_code.lower().replace('-', '_')}"
            slot = resolve_manual_or_auto(
                slot_id=slot_id,
                label=display_code,
                expected=descr,
                search={"attrs": [api_code]},
                auto_matcher=lambda it, ac=api_code: ac in it["attrs"] or normalize_attr_code(ac) in it["attrs"],
            )
            slot["attr_code"] = api_code
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

        math_used: set[str] = set()
        math_slots = []
        for spec in ARTS_MATH_INTRO_MATCHERS:
            opts = spec["options"]
            s = resolve_manual_or_auto(
                slot_id=spec["id"],
                label=spec["label"],
                expected=spec["expected"],
                search=spec["search"],
                auto_matcher=lambda it, opts=opts: it["course"] in opts,
                used_in_group=math_used,
            )
            math_slots.append(s)
            if s["filled"] and s["course"]:
                used_non_double_electives.add(s["course"])

        sections.append(
            {
                "id": "math_intro",
                "title": "Mathematics & Intro CS",
                "subtitle": "Calculus I–II, Linear Algebra, CS 1110/1112 & CS 2110/2112",
                "slots": math_slots,
            }
        )
    else:
        eng_used: set[str] = set()
        eng_slots = []
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

            s = resolve_manual_or_auto(
                slot_id=spec["id"],
                label=spec["label"],
                expected=spec["expected"],
                search=spec["search"],
                auto_matcher=_eng_match,
                used_in_group=eng_used,
            )
            eng_slots.append(s)
            if s["filled"] and s["course"]:
                used_non_double_electives.add(s["course"])

        sections.append(
            {
                "id": "eng_math_sci",
                "title": "Engineering Math, Sciences & Intro",
                "subtitle": "MATH 1910–2940, PHYS 1112/2213, CHEM 2090, ENGRI, ENGRD, & Intro CS",
                "slots": eng_slots,
            }
        )

        fws_lib_used: set[str] = set()
        eng_lib_slots = [
            resolve_manual_or_auto(
                "eng_fws_1",
                "FWS 1",
                "First-Year Writing Seminar",
                {"attrs": ["FWS"]},
                lambda it: "FWS" in it["attrs"],
                used_in_group=fws_lib_used,
            ),
            resolve_manual_or_auto(
                "eng_fws_2",
                "FWS 2",
                "First-Year Writing Seminar",
                {"attrs": ["FWS"]},
                lambda it: "FWS" in it["attrs"],
                used_in_group=fws_lib_used,
            ),
        ]
        lib_set = set(LIBERAL_STUDIES_ATTRS)
        for idx in range(1, 7):
            eng_lib_slots.append(
                resolve_manual_or_auto(
                    f"eng_lib_{idx}",
                    f"Liberal Studies {idx}",
                    "CA / HA / KCM / LA / SBA / FL (18+ cr total, 2x 2000+)",
                    {"attrs": ["CA-AG", "HA-AG", "KCM-AG", "LA-AG", "SBA-AG"]},
                    lambda it, lib_set=lib_set: any(a in lib_set for a in it["attrs"]),
                    used_in_group=fws_lib_used,
                )
            )
        sections.append(
            {
                "id": "eng_liberal",
                "title": "Writing & Liberal Studies (Engineering)",
                "subtitle": "2 FWS + 6 Liberal Studies courses across >=3 categories (18+ cr)",
                "slots": eng_lib_slots,
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

    # CS Project first or CS Electives? Assign CS Project first if a practicum was taken cleanly, OR prioritize explicit CS Project slots!
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

    # First reserve any explicitly pinned manual overrides in electives so auto-fill skips them
    for key in (
        "cs_proj",
        "cs_elec_1",
        "cs_elec_2",
        "cs_elec_3",
        "tech_elec_1",
        "tech_elec_2",
        "tech_elec_3",
        "ext_spec_1",
        "ext_spec_2",
        "ext_spec_3",
        "maj_elec_1",
        "maj_elec_2",
        "maj_elec_3",
    ):
        ov = manual_slots.get(key)
        if isinstance(ov, dict) and not ov.get("cleared"):
            mc = normalize_course_code(str(ov.get("course") or ""))
            if mc:
                used_non_double_electives.add(mc)

    proj_slot = resolve_manual_or_auto(
        "cs_proj",
        "CS Project",
        "CS 4xx1 Practicum / 3152 / 4152 / 5150",
        {"cs_requirement": "cs_project", "subjects": ["CS"]},
        _is_cs_project,
        used_in_group=used_non_double_electives,
    )

    cs_elec_slots = [
        resolve_manual_or_auto(
            f"cs_elec_{i}",
            f"CS Elective {i}",
            "CS 4000+ non-core (>=3 cr letter)",
            {"cs_requirement": "cs_elective", "subjects": ["CS"]},
            _is_cs_elective,
            used_in_group=used_non_double_electives,
        )
        for i in range(1, 4)
    ]

    tech_elec_slots = [
        resolve_manual_or_auto(
            f"tech_elec_{i}",
            f"Tech Elective {i}",
            "3000+ STEM / Quant application area",
            {"cs_requirement": "tech_elective"},
            _is_tech_elective,
            used_in_group=used_non_double_electives,
        )
        for i in range(1, 4)
    ]

    # Pick dominant non-CS subject for External Spec auto-fill consistency if unpinned
    ext_candidates = [
        it for it in pool_enriched
        if it["course"] not in used_non_double_electives and _is_ext_spec(it)
    ]
    subj_counts: dict[str, int] = {}
    for it in ext_candidates:
        su = it["course"].split(" ", 1)[0]
        subj_counts[su] = subj_counts.get(su, 0) + 1
    inferred_ext_subj = (
        max(subj_counts.items(), key=lambda kv: (kv[1], kv[0]))[0]
        if subj_counts
        else ""
    )

    # If user manually assigned any ext_spec slot, prefer that subject for empty search hints
    for i in range(1, 4):
        ov = manual_slots.get(f"ext_spec_{i}")
        if isinstance(ov, dict) and not ov.get("cleared"):
            mc = normalize_course_code(str(ov.get("course") or ""))
            if mc:
                inferred_ext_subj = mc.split(" ", 1)[0]
                break

    ext_spec_slots = [
        resolve_manual_or_auto(
            f"ext_spec_{i}",
            f"External Spec {i}",
            f"3000+ {inferred_ext_subj or 'same subject'} outside CS",
            {
                "cs_requirement": "external_spec",
                **({"subjects": [inferred_ext_subj]} if inferred_ext_subj else {}),
            },
            lambda it, target=inferred_ext_subj: _is_ext_spec(it)
            and (not target or it["course"].split(" ", 1)[0] == target),
            used_in_group=used_non_double_electives,
        )
        for i in range(1, 4)
    ]

    maj_count = 1 if curriculum == "current" else 3
    maj_slots = [
        resolve_manual_or_auto(
            f"maj_elec_{i}",
            f"Major Approved {i}" if maj_count > 1 else "Major Approved Elective",
            "Any 3+ cr academic course (no PE)",
            {"min_credits": 3},
            lambda it: it["course"] not in used_non_double_electives and not it["course"].startswith("PE "),
            used_in_group=used_non_double_electives,
        )
        for i in range(1, maj_count + 1)
    ]

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

    # Summary stats
    total_boxes = sum(len(sec["slots"]) for sec in sections)
    filled_boxes = sum(1 for sec in sections for sl in sec["slots"] if sl["filled"])
    completed_boxes = sum(1 for sec in sections for sl in sec["slots"] if sl["filled"] and sl["source"] == "completed")
    whatif_boxes = sum(1 for sec in sections for sl in sec["slots"] if sl["filled"] and sl["source"] == "schedule")

    return {
        "roster": roster_u,
        "college": college,
        "curriculum": curriculum,
        "include_active_schedule": include_sched,
        "active_schedule_name": active_schedule_name,
        "pe_completed": saved["pe_completed"],
        "completed_courses": completed_list,
        "planned_courses": sorted(planned_courses.keys()),
        "as_distribution_summary": as_dist_summary,
        "summary": {
            "total_slots": total_boxes,
            "filled_slots": filled_boxes,
            "completed_slots": completed_boxes,
            "whatif_slots": whatif_boxes,
            "remaining_slots": total_boxes - filled_boxes,
        },
        "sections": sections,
    }
