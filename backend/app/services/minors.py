"""Evaluation, filtering, persistence helpers, and catalog assembly for Cornell minors."""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from app.services.common import (
    normalize_course_code_loose as normalize_course_code,
    parse_catalog_num,
    parse_json_value,
)
from app.services.minors_data import (
    MINORS_BY_ID,
    MINORS_REGISTRY,
    SUBJECT_ALIASES,
    MinorCategoryDef,
    MinorDef,
    MinorVersionDef,
    resolve_is_version_for_college,
)

_BME_EXCLUDED_NBRS = frozenset(
    {"4660", "4661", "4665", "4960", "4970", "4975", "4980", "4990", "4992", "4993"}
)
_LSJ_EXCLUDED_NBRS = frozenset(
    {"3991", "3992", "4940", "4950", "4960", "4970", "4980", "4990", "4999"}
)
_HIST_EXCLUDED_NBRS = frozenset({"2001", "3002", "4001", "4002", "8004"})
_INFOSCI_EXCLUDED_NBRS = frozenset({"1998", "4900", "4910", "4997", "4998"})
_IS_HOTEL_REQUIRED_NBRS = frozenset({"HADM 3740", "HADM 4760"})
_PSYCH_NON_MINOR_NBRS = frozenset({"1104", "2091", "2801", "4700", "4710", "4720", "4910"})

_MINOR_WARNINGS: dict[str, dict[str, str]] = {
    "business": {
        "AEM 3100": "ENG/ORIE students: ORIE 3300/3500 satisfies the Statistics prerequisite instead of AEM 3100.",
    },
    "info_science": {
        "INFO 2950": "Credit overlap: cannot receive credit for both INFO 2950 and INFO 2951.",
        "INFO 2951": "Credit overlap: cannot receive credit for both INFO 2950 and INFO 2951.",
        "HADM 3740": "Forbidden overlap with AEM 2820.",
    },
    "psychology": {
        "PSYCH 4700": "Maximum 6 credits total across PSYCH 4700 and PSYCH 4710 can count toward the 18-credit minor.",
        "PSYCH 4710": "Maximum 6 credits total across PSYCH 4700 and PSYCH 4710 can count toward the 18-credit minor.",
    },
}


def expand_code_with_aliases(subject: str, nbr: str) -> list[str]:
    """Expand 'SUBJ NBR' using department rename aliases (PAM<->PUBPOL, etc.)."""
    subj = str(subject or "").strip().upper()
    num = str(nbr or "").strip().upper()
    if not subj or not num:
        return []
    aliases = SUBJECT_ALIASES.get(subj, (subj,))
    seen: list[str] = []
    for alias in aliases:
        code = f"{alias} {num}"
        if code not in seen:
            seen.append(code)
    return seen


def get_candidate_course_codes(
    subject: str,
    catalog_nbr: str,
    crosslists: Any = None,
) -> tuple[list[str], set[str], dict[str, set[str]]]:
    """Return all normalized codes (primary + crosslists + dept aliases) for a course."""
    ordered_codes: list[str] = []
    subjects: set[str] = set()
    nbrs_by_subject: dict[str, set[str]] = {}

    def _add(subj_raw: str, nbr_raw: str) -> None:
        subj = str(subj_raw or "").strip().upper()
        nbr = str(nbr_raw or "").strip().upper()
        if not subj or not nbr:
            return
        for alias in SUBJECT_ALIASES.get(subj, (subj,)):
            code = f"{alias} {nbr}"
            if code not in ordered_codes:
                ordered_codes.append(code)
            subjects.add(alias)
            nbrs_by_subject.setdefault(alias, set()).add(nbr)

    _add(subject, catalog_nbr)

    raw_crosslists = parse_json_value(crosslists, [])
    if isinstance(raw_crosslists, list):
        for item in raw_crosslists:
            if isinstance(item, dict):
                _add(
                    str(item.get("subject") or ""),
                    str(item.get("catalogNbr") or item.get("catalog_nbr") or ""),
                )
            elif isinstance(item, str):
                norm = normalize_course_code(item)
                if " " in norm:
                    s, n = norm.split(" ", 1)
                    _add(s, n)

    return ordered_codes, subjects, nbrs_by_subject


def _valid_category_ids_for_minor(minor_def: MinorDef) -> set[str]:
    cats = {
        cat.id
        for ver in minor_def.versions
        for cat in ver.categories
    }
    if minor_def.id == "info_science":
        cats.add("is_hotel_req")
    return cats


def default_minor_prefs() -> dict[str, Any]:
    """Return empty normalized minor preferences structure."""
    colleges = {m.id: m.default_college for m in MINORS_REGISTRY if m.default_college}
    return {
        "selected_minor": "",
        "versions": {m.id: m.default_version for m in MINORS_REGISTRY},
        "colleges": colleges,
        "completed_categories": {},
        "hide_completed": True,
    }


def normalize_minor_prefs(raw: Any) -> dict[str, Any]:
    """Sanitize user minor preferences (selected minor, versions, colleges, completed parts)."""
    prefs = default_minor_prefs()
    if isinstance(raw, str):
        raw = parse_json_value(raw, {})
    if not isinstance(raw, dict):
        return prefs

    sel_minor = str(raw.get("selected_minor") or "").strip()
    if sel_minor in MINORS_BY_ID:
        prefs["selected_minor"] = sel_minor

    raw_versions = raw.get("versions")
    if isinstance(raw_versions, dict):
        for minor_id, minor_def in MINORS_BY_ID.items():
            ver_id = str(raw_versions.get(minor_id) or "").strip()
            valid_vers = {v.id for v in minor_def.versions}
            if ver_id in valid_vers:
                prefs["versions"][minor_id] = ver_id

    raw_colleges = raw.get("colleges")
    if isinstance(raw_colleges, dict):
        for minor_id, minor_def in MINORS_BY_ID.items():
            if not minor_def.colleges:
                continue
            col_id = str(raw_colleges.get(minor_id) or "").strip().lower()
            valid_cols = {c.id for c in minor_def.colleges}
            if col_id in valid_cols:
                prefs["colleges"][minor_id] = col_id

    raw_completed = raw.get("completed_categories")
    if isinstance(raw_completed, dict):
        cleaned_completed: dict[str, list[str]] = {}
        for minor_id, cat_list in raw_completed.items():
            minor_def = MINORS_BY_ID.get(str(minor_id or "").strip())
            if minor_def is None or not isinstance(cat_list, list):
                continue
            valid_cats = _valid_category_ids_for_minor(minor_def)
            deduped: list[str] = []
            for raw_cid in cat_list:
                cid = str(raw_cid or "").strip()
                if cid in valid_cats and cid not in deduped:
                    deduped.append(cid)
            if deduped:
                cleaned_completed[minor_def.id] = deduped
        prefs["completed_categories"] = cleaned_completed

    if "hide_completed" in raw:
        prefs["hide_completed"] = bool(raw.get("hide_completed"))

    return prefs


def decode_minor_prefs(raw_json: Any) -> dict[str, Any]:
    """Decode stored SQLite minor_prefs_json safely."""
    return normalize_minor_prefs(raw_json)


def encode_minor_prefs(raw: Any) -> str:
    """Serialize normalized minor preferences to compact JSON."""
    return json.dumps(normalize_minor_prefs(raw), separators=(",", ":"))


def resolve_minor_and_version(
    minor_id: str,
    version_id: str = "",
    college_id: str = "",
) -> tuple[Optional[MinorDef], Optional[MinorVersionDef]]:
    """Resolve MinorDef and MinorVersionDef (adapted for home college when applicable)."""
    minor = MINORS_BY_ID.get(str(minor_id or "").strip())
    if minor is None:
        return None, None
    req_ver = str(version_id or "").strip() or minor.default_version
    ver_map = {v.id: v for v in minor.versions}
    ver = ver_map.get(req_ver) or ver_map.get(minor.default_version) or minor.versions[0]
    if minor.id == "info_science":
        ver, _ = resolve_is_version_for_college(ver, college_id or minor.default_college)
    return minor, ver


def _extract_course_fields(course: dict[str, Any]) -> dict[str, Any]:
    subject = str(course.get("subject") or "").strip().upper()
    catalog_nbr = str(course.get("catalog_nbr") or course.get("catalogNbr") or "").strip().upper()
    catalog_num = parse_catalog_num(catalog_nbr, course.get("catalog_num"))
    title_short = str(course.get("title_short") or course.get("titleShort") or "").strip()
    title_long = str(course.get("title_long") or course.get("titleLong") or "").strip()
    title_upper = f"{title_short} {title_long}".upper()

    raw_letter = course.get("has_letter_grade")
    has_letter_grade = True if raw_letter is None else bool(raw_letter)

    raw_units_max = course.get("units_max")
    try:
        units_max = float(raw_units_max) if raw_units_max is not None else 3.0
    except (TypeError, ValueError):
        units_max = 3.0

    raw_components = parse_json_value(
        course.get("components") if course.get("components") is not None else course.get("components_json"),
        [],
    )
    components = {
        str(c).strip().upper()
        for c in (raw_components if isinstance(raw_components, list) else [])
        if str(c).strip()
    }

    crosslists = (
        course.get("crosslists")
        if course.get("crosslists") is not None
        else course.get("crosslists_json")
    )
    candidate_codes, candidate_subjects, nbrs_by_subject = get_candidate_course_codes(
        subject, catalog_nbr, crosslists
    )
    return {
        "primary_code": f"{subject} {catalog_nbr}".strip(),
        "subject": subject,
        "catalog_nbr": catalog_nbr,
        "catalog_num": catalog_num,
        "title_upper": title_upper,
        "is_fws": "FWS:" in title_upper or title_short.upper().startswith("FWS "),
        "has_letter_grade": has_letter_grade,
        "units_max": units_max,
        "components": components,
        "is_only_ind_rsc": bool(components) and components <= {"IND", "RSC"},
        "candidate_codes": candidate_codes,
        "candidate_code_set": set(candidate_codes),
        "candidate_subjects": candidate_subjects,
        "nbrs_by_subject": nbrs_by_subject,
    }


def _subject_numbers(fields: dict[str, Any], target_subjects: set[str]) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    for subj in target_subjects:
        for nbr in fields["nbrs_by_subject"].get(subj, ()):
            out.append((nbr, parse_catalog_num(nbr)))
    return out


def _matches_dynamic_rule(
    rule: str,
    fields: dict[str, Any],
    cat: MinorCategoryDef,
    matched_static_cats: set[str],
) -> bool:
    if rule == "bme_career_goals":
        if not fields["has_letter_grade"] or fields["units_max"] < 1.5 or fields["is_only_ind_rsc"]:
            return False
        for nbr, num in _subject_numbers(fields, {"AEM", "HADM", "NBA", "NCC"}):
            if 3000 <= num < 7000 and nbr not in _BME_EXCLUDED_NBRS:
                return True
        return False

    if rule == "lsj_ilrgl":
        if not fields["has_letter_grade"] or fields["is_only_ind_rsc"]:
            return False
        for nbr, num in _subject_numbers(fields, {"ILRGL"}):
            if 1000 <= num < 5000 and nbr not in _LSJ_EXCLUDED_NBRS:
                return True
        return False

    if rule == "history_seminar_2000":
        if (
            not fields["has_letter_grade"]
            or fields["is_fws"]
            or fields["is_only_ind_rsc"]
            or fields["units_max"] < 3.0
            or "SEM" not in fields["components"]
        ):
            return False
        for nbr, num in _subject_numbers(fields, {"HIST"}):
            if 2000 <= num < 5000 and nbr not in _HIST_EXCLUDED_NBRS:
                return True
        return False

    if rule == "history_non_fws":
        if (
            not fields["has_letter_grade"]
            or fields["is_fws"]
            or fields["is_only_ind_rsc"]
            or fields["units_max"] < 3.0
        ):
            return False
        for nbr, num in _subject_numbers(fields, {"HIST"}):
            if 1000 <= num < 5000 and nbr not in _HIST_EXCLUDED_NBRS:
                return True
        return False

    if rule == "psych_course":
        if fields["is_fws"] or fields["units_max"] < 1.0 or not fields["has_letter_grade"] or fields["is_only_ind_rsc"]:
            return False
        for nbr, num in _subject_numbers(fields, {"PSYCH"}):
            if 1000 <= num < 5000 and nbr not in _PSYCH_NON_MINOR_NBRS:
                return True
        return False

    if rule in {"infosci_elective", "infosci_elective_hotel"}:
        # Any approved concentration course, extra Core course (incl. INFO 1200/1260/1300),
        # 2000+ non-IND INFO course, or AEM 3220 (Hotel) can satisfy an Elective.
        # Double-counting the same course enrollment is prevented separately.
        is_hotel = rule == "infosci_elective_hotel"
        for code in fields["candidate_codes"]:
            if is_hotel and code in _IS_HOTEL_REQUIRED_NBRS:
                return False
            if code in cat.courses:
                return True
        if not fields["has_letter_grade"] or fields["units_max"] < 1.5 or fields["is_only_ind_rsc"]:
            return False
        for nbr, num in _subject_numbers(fields, {"INFO"}):
            if 2000 <= num < 5000 and nbr not in _INFOSCI_EXCLUDED_NBRS:
                return True
        return False

    return False


def _match_course_categories(
    fields: dict[str, Any],
    version: MinorVersionDef,
) -> list[MinorCategoryDef]:
    code_set = fields["candidate_code_set"]
    matched_static_ids: set[str] = set()
    static_hits: dict[str, bool] = {}

    for cat in version.categories:
        if cat.dynamic_rule:
            continue
        is_hit = bool(code_set & cat.courses) or bool(code_set & cat.wildcard_courses)
        static_hits[cat.id] = is_hit
        if is_hit:
            matched_static_ids.add(cat.id)

    matched: list[MinorCategoryDef] = []
    for cat in version.categories:
        if cat.dynamic_rule:
            if _matches_dynamic_rule(cat.dynamic_rule, fields, cat, matched_static_ids):
                matched.append(cat)
        elif static_hits.get(cat.id):
            matched.append(cat)
    return matched


_GRADE_POINTS: dict[str, float] = {
    "A+": 4.3,
    "A": 4.0,
    "A-": 3.7,
    "B+": 3.3,
    "B": 3.0,
    "B-": 2.7,
    "C+": 2.3,
    "C": 2.0,
    "C-": 1.7,
    "D+": 1.3,
    "D": 1.0,
    "D-": 0.7,
    "F": 0.0,
}
_SU_GRADES = frozenset({"S", "SX", "S*"})
_DISQUALIFYING_GRADES = frozenset({"F", "U", "UX", "W", "WD", "INC", "AUD", "N", "NG"})
_MIN_GRADE_BY_MINOR: dict[str, float] = {
    "psychology": 1.7,   # C-
    "info_science": 2.0, # C
    "history": 2.3,      # C+
}
_STRICT_CORNELL_ONLY_MINORS = frozenset({"info_science", "psychology", "history", "lsj"})


def _is_ap_detail(detail: Optional[dict[str, str]]) -> bool:
    if not detail:
        return False
    sem_u = str(detail.get("sem") or "").strip().upper()
    gr_u = str(detail.get("gr") or "").strip().upper()
    return sem_u == "AP" or sem_u.startswith("AP ") or gr_u == "AP"


def _is_transfer_detail(detail: Optional[dict[str, str]]) -> bool:
    if not detail:
        return False
    sem_u = str(detail.get("sem") or "").strip().upper()
    gr_u = str(detail.get("gr") or "").strip().upper()
    return sem_u == "TR" or sem_u.startswith("TR ") or gr_u == "TR"


def _is_course_credit_eligible(
    detail: Optional[dict[str, str]],
    minor_id: str,
    cat_id: str,
    is_in_progress: bool,
) -> bool:
    """Return False when transcript metadata marks AP, disallowed transfer, S/U, or too-low grade."""
    if not detail:
        return True
    if _is_ap_detail(detail):
        return False
    if minor_id in _STRICT_CORNELL_ONLY_MINORS and _is_transfer_detail(detail):
        return False
    if is_in_progress:
        return True

    gr_u = str(detail.get("gr") or "").strip().upper()
    if not gr_u:
        return True
    if gr_u in _DISQUALIFYING_GRADES:
        return False
    if gr_u in _SU_GRADES:
        return cat_id == "psych_research"
    if gr_u in _GRADE_POINTS:
        min_pts = _MIN_GRADE_BY_MINOR.get(minor_id, 1.7)
        return _GRADE_POINTS[gr_u] >= min_pts
    return True


def _resolve_course_credits(
    detail: Optional[dict[str, str]],
    row: dict[str, Any],
) -> float:
    """Resolve numeric credits from transcript detail or catalog row metadata."""
    if detail and detail.get("cr"):
        m = re.search(r"(\d+(?:\.\d+)?)", str(detail.get("cr") or ""))
        if m:
            try:
                val = float(m.group(1))
                if val > 0:
                    return val
            except ValueError:
                pass
    try:
        units = float(row.get("units_max") or 0.0)
        if units > 0:
            return units
    except (TypeError, ValueError):
        pass
    return 3.0


def _build_taken_sets(
    taken_courses: Optional[list[str]],
    taken_course_details: Optional[dict[str, dict[str, str]]] = None,
) -> tuple[set[str], set[str]]:
    """Return (cornell_taken_set, ap_taken_set) expanded with subject aliases."""
    details = taken_course_details or {}
    cornell_out: set[str] = set()
    ap_out: set[str] = set()
    for raw_code in taken_courses or []:
        norm = normalize_course_code(raw_code)
        if not norm or " " not in norm:
            continue
        subj, nbr = norm.split(" ", 1)
        expanded = set(expand_code_with_aliases(subj, nbr)) | {norm}
        if _is_ap_detail(details.get(norm)):
            ap_out.update(expanded)
        else:
            cornell_out.update(expanded)
    return cornell_out, ap_out


def evaluate_course_for_minor(
    course: dict[str, Any],
    minor_id: str,
    version_id: str = "",
    completed_categories: Optional[set[str]] = None,
    active_categories: Optional[set[str]] = None,
    college: str = "",
    taken_courses: Optional[list[str]] = None,
    taken_course_details: Optional[dict[str, dict[str, str]]] = None,
) -> Optional[dict[str, Any]]:
    """Evaluate a course against a minor version; return eligibility dict or None."""
    minor, version = resolve_minor_and_version(minor_id, version_id, college_id=college)
    if minor is None or version is None:
        return None

    fields = _extract_course_fields(course)
    matched = _match_course_categories(fields, version)
    if not matched:
        return None

    completed_set = completed_categories or set()
    active_set = active_categories or set()
    cornell_taken_set, ap_taken_set = _build_taken_sets(taken_courses, taken_course_details)
    is_already_taken = bool(cornell_taken_set and (fields["candidate_code_set"] & cornell_taken_set))
    is_ap_on_transcript = bool(not is_already_taken and ap_taken_set and (fields["candidate_code_set"] & ap_taken_set))

    matched_ids = [cat.id for cat in matched]
    if is_already_taken:
        remaining = []
        completed_matches = list(matched)
    else:
        remaining = [cat for cat in matched if cat.id not in completed_set]
        completed_matches = [cat for cat in matched if cat.id in completed_set]

    badges_source = remaining if (completed_set and remaining and not is_already_taken) else matched
    if active_set:
        filtered_badges = [cat for cat in badges_source if cat.id in active_set]
        if filtered_badges:
            badges_source = filtered_badges

    badges = [
        {
            "category_id": cat.id,
            "tone": cat.tone,
            "label": cat.short_label,
            "completed": is_already_taken or (cat.id in completed_set),
        }
        for cat in badges_source[:4]
    ]

    warnings: list[str] = []
    if is_already_taken:
        warnings.append("Already on your Completed/In-Progress list — cannot double-count within the minor.")
    elif is_ap_on_transcript:
        warnings.append("On your transcript as AP credit (AP credits do not count toward this minor).")
    warn_map = _MINOR_WARNINGS.get(minor.id, {})
    for code in fields["candidate_codes"]:
        msg = warn_map.get(code)
        if msg and msg not in warnings:
            warnings.append(msg)

    return {
        "minor_id": minor.id,
        "minor_label": minor.short_label,
        "version_id": version.id,
        "version_label": version.short_label,
        "matched_categories": matched_ids,
        "remaining_categories": [cat.id for cat in remaining],
        "covered_by_completed": [cat.id for cat in completed_matches],
        "has_uncompleted": bool(remaining),
        "already_taken": is_already_taken,
        "badges": badges,
        "warnings": warnings,
    }


def course_matches_minor_filter(
    eligibility: Optional[dict[str, Any]],
    selected_categories: Optional[set[str]] = None,
    hide_completed: bool = True,
) -> bool:
    """Return True if evaluated course satisfies active minor/category/completed filters."""
    if not eligibility:
        return False

    matched_ids = set(eligibility.get("matched_categories") or [])
    remaining_ids = set(eligibility.get("remaining_categories") or [])
    effective_ids = remaining_ids if hide_completed else matched_ids
    if not effective_ids:
        return False

    if selected_categories:
        return bool(effective_ids & selected_categories)
    return True


def _build_minimal_meta_row(code: str) -> dict[str, Any]:
    norm = normalize_course_code(code)
    parts = norm.split(" ", 1)
    subj = parts[0] if parts else norm
    nbr = parts[1] if len(parts) > 1 else ""
    # Synthetic default assumes UG 3-cr seminar/course unknown unless real metadata exists.
    return {
        "subject": subj,
        "catalog_nbr": nbr,
        "catalog_num": parse_catalog_num(nbr),
        "title_short": "",
        "title_long": "",
        "has_letter_grade": True,
        "units_max": 3.0,
        "components": ["LEC"],
        "crosslists": [],
    }


def _assign_infosci_slots(
    per_course: list[tuple[str, list[MinorCategoryDef]]],
    version: MinorVersionDef,
) -> dict[str, list[str]]:
    """Assign each taken/in-progress course to at most ONE Info Sci minor requirement slot."""
    suggestions: dict[str, list[str]] = {}
    if not per_course:
        return suggestions

    cat_by_id = {c.id: c for c in version.categories}

    if version.id == "all":
        used: set[int] = set()
        if "is_hotel_req" in cat_by_id:
            req_n = cat_by_id["is_hotel_req"].required_count or 2
            for idx, (lbl, cats) in enumerate(per_course):
                if len(suggestions.get("is_hotel_req", [])) >= req_n:
                    break
                if any(c.id == "is_hotel_req" for c in cats):
                    suggestions.setdefault("is_hotel_req", []).append(lbl)
                    used.add(idx)

        # Prefer a Core-only course (not matching a concentration) for Core before multi-role courses.
        core_candidates = [
            (idx, sum(1 for c in cats if c.id.startswith("is_conc_")))
            for idx, (_, cats) in enumerate(per_course)
            if idx not in used and any(c.id == "is_core" for c in cats)
        ]
        if core_candidates:
            core_candidates.sort(key=lambda pair: (pair[1], pair[0]))
            chosen_idx = core_candidates[0][0]
            suggestions.setdefault("is_core", []).append(per_course[chosen_idx][0])
            used.add(chosen_idx)

        elec_cap = (cat_by_id.get("is_elective").required_count if "is_elective" in cat_by_id else 2) or 2
        for idx, (lbl, cats) in enumerate(per_course):
            if idx in used:
                continue
            for c in cats:
                if c.id == "is_elective":
                    if len(suggestions.get("is_elective", [])) < elec_cap:
                        suggestions.setdefault("is_elective", []).append(lbl)
                elif c.id.startswith("is_conc_"):
                    suggestions.setdefault(c.id, []).append(lbl)
        return suggestions

    slot_priority = {"is_hotel_req": 0, "is_core": 1, "is_elective": 3}
    ordered_cats = sorted(
        version.categories,
        key=lambda c: (slot_priority.get(c.id, 2 if c.id.startswith("is_conc_") else 4), c.id),
    )
    slots: list[str] = []
    for cat in ordered_cats:
        cap = cat.required_count or 1
        for _ in range(cap):
            slots.append(cat.id)

    course_order = sorted(
        range(len(per_course)),
        key=lambda i: (len({c.id for c in per_course[i][1]}), i),
    )
    slot_owner: list[Optional[int]] = [None] * len(slots)

    def _try_match(c_idx: int, seen_slots: set[int]) -> bool:
        allowed = {c.id for c in per_course[c_idx][1]}
        for s_idx, cat_id in enumerate(slots):
            if s_idx in seen_slots or cat_id not in allowed:
                continue
            seen_slots.add(s_idx)
            owner = slot_owner[s_idx]
            if owner is None or _try_match(owner, seen_slots):
                slot_owner[s_idx] = c_idx
                return True
        return False

    for c_idx in course_order:
        _try_match(c_idx, set())

    assigned_pairs: list[tuple[int, str, str]] = []
    for s_idx, owner in enumerate(slot_owner):
        if owner is not None:
            assigned_pairs.append((owner, slots[s_idx], per_course[owner][0]))
    assigned_pairs.sort(key=lambda t: t[0])
    for _, cat_id, lbl in assigned_pairs:
        suggestions.setdefault(cat_id, []).append(lbl)
    return suggestions


def _collect_user_minor_entries(
    minor: MinorDef,
    version: MinorVersionDef,
    completed_courses: list[str],
    in_progress_courses: Optional[list[str]] = None,
    meta_by_code: Optional[dict[str, dict[str, Any]]] = None,
    completed_course_details: Optional[dict[str, dict[str, str]]] = None,
    in_progress_course_details: Optional[dict[str, dict[str, str]]] = None,
) -> tuple[dict[str, list[str]], dict[str, float], dict[str, float]]:
    """Return (matched_labels_by_cat, earned_credits_by_cat, in_progress_credits_by_cat)."""
    meta_lookup = meta_by_code or {}
    comp_details = completed_course_details or {}
    ip_details = in_progress_course_details or {}

    ordered_courses: list[tuple[str, str, bool, Optional[dict[str, str]]]] = []
    seen_codes: set[str] = set()

    for raw_code in completed_courses or []:
        code = normalize_course_code(raw_code)
        if code and code not in seen_codes:
            seen_codes.add(code)
            ordered_courses.append((code, code, False, comp_details.get(code)))

    for raw_code in in_progress_courses or []:
        code = normalize_course_code(raw_code)
        if code and code not in seen_codes:
            seen_codes.add(code)
            ordered_courses.append((code, f"{code} (IP)", True, ip_details.get(code)))

    per_course: list[tuple[str, list[MinorCategoryDef]]] = []
    credits_by_label: dict[str, tuple[float, bool]] = {}

    for code, display_label, is_ip, detail in ordered_courses:
        row = meta_lookup.get(code)
        if row is None:
            subj, _, nbr = code.partition(" ")
            for alias_code in expand_code_with_aliases(subj, nbr):
                if alias_code in meta_lookup:
                    row = meta_lookup[alias_code]
                    break
        if row is None:
            row = _build_minimal_meta_row(code)

        fields = _extract_course_fields(row)
        subj, _, nbr = code.partition(" ")
        for alias_code in expand_code_with_aliases(subj, nbr):
            if alias_code not in fields["candidate_code_set"]:
                fields["candidate_codes"].append(alias_code)
                fields["candidate_code_set"].add(alias_code)
                s_alias, _, n_alias = alias_code.partition(" ")
                fields["candidate_subjects"].add(s_alias)
                fields["nbrs_by_subject"].setdefault(s_alias, set()).add(n_alias)

        matched_cats = [
            cat
            for cat in _match_course_categories(fields, version)
            if _is_course_credit_eligible(detail, minor.id, cat.id, is_in_progress=is_ip)
        ]
        if matched_cats:
            per_course.append((display_label, matched_cats))
            credits_by_label[display_label] = (_resolve_course_credits(detail, row), is_ip)

    if minor.id == "info_science":
        suggestions = _assign_infosci_slots(per_course, version)
    else:
        suggestions = {}
        for display_label, matched_cats in per_course:
            for cat in matched_cats:
                suggestions.setdefault(cat.id, []).append(display_label)

    earned_credits: dict[str, float] = {}
    ip_credits: dict[str, float] = {}
    for cat_id, labels in suggestions.items():
        e_total = 0.0
        ip_total = 0.0
        for lbl in labels:
            cr, is_ip = credits_by_label.get(lbl, (3.0, False))
            if is_ip:
                ip_total += cr
            else:
                e_total += cr
        earned_credits[cat_id] = round(e_total, 2)
        ip_credits[cat_id] = round(ip_total, 2)

    return suggestions, earned_credits, ip_credits


def suggest_completed_categories(
    minor_id: str,
    version_id: str,
    completed_courses: list[str],
    in_progress_courses: Optional[list[str]] = None,
    meta_by_code: Optional[dict[str, dict[str, Any]]] = None,
    college: str = "",
    completed_course_details: Optional[dict[str, dict[str, str]]] = None,
    in_progress_course_details: Optional[dict[str, dict[str, str]]] = None,
) -> dict[str, list[str]]:
    """Map category_id -> matching user completed/in-progress course codes for auto-fill."""
    minor, version = resolve_minor_and_version(minor_id, version_id, college_id=college)
    if minor is None or version is None:
        return {}
    suggestions, _, _ = _collect_user_minor_entries(
        minor,
        version,
        completed_courses,
        in_progress_courses=in_progress_courses,
        meta_by_code=meta_by_code,
        completed_course_details=completed_course_details,
        in_progress_course_details=in_progress_course_details,
    )
    return suggestions


def build_minors_catalog(
    roster_courses: list[dict[str, Any]],
    completed_courses: Optional[list[str]] = None,
    in_progress_courses: Optional[list[str]] = None,
    meta_by_code: Optional[dict[str, dict[str, Any]]] = None,
    college_by_minor: Optional[dict[str, str]] = None,
    completed_course_details: Optional[dict[str, dict[str, str]]] = None,
    in_progress_course_details: Optional[dict[str, dict[str, str]]] = None,
) -> list[dict[str, Any]]:
    """Build full API payload describing all minors, versions, counts, and user auto-fill."""
    comp_list = completed_courses or []
    ip_list = in_progress_courses or []

    extracted_roster: list[tuple[dict[str, Any], dict[str, Any]]] = [
        (course, _extract_course_fields(course)) for course in roster_courses
    ]

    catalog_items: list[dict[str, Any]] = []
    for minor in MINORS_REGISTRY:
        req_college = (college_by_minor or {}).get(minor.id, minor.default_college)
        valid_college_ids = {c.id for c in minor.colleges}
        active_college = req_college if req_college in valid_college_ids else minor.default_college

        versions_payload: list[dict[str, Any]] = []
        for base_version in minor.versions:
            _, version = resolve_minor_and_version(minor.id, base_version.id, college_id=active_college)
            if version is None:
                continue

            cat_counts: dict[str, int] = {}
            total_matches = 0
            for _, fields in extracted_roster:
                matched = _match_course_categories(fields, version)
                if matched:
                    total_matches += 1
                    for cat in matched:
                        cat_counts[cat.id] = cat_counts.get(cat.id, 0) + 1

            auto_matches, earned_by_cat, ip_by_cat = _collect_user_minor_entries(
                minor,
                version,
                comp_list,
                ip_list,
                meta_by_code=meta_by_code,
                completed_course_details=completed_course_details,
                in_progress_course_details=in_progress_course_details,
            )
            cats_payload = []
            for cat in version.categories:
                matched_user = auto_matches.get(cat.id, [])
                req_n = cat.required_count
                req_cr = cat.required_credits
                earned_cr = earned_by_cat.get(cat.id, 0.0)
                ip_cr = ip_by_cat.get(cat.id, 0.0)
                effective_cr = earned_cr
                if minor.id == "psychology" and cat.id == "psych_course":
                    effective_cr = round(earned_cr + min(6.0, earned_by_cat.get("psych_research", 0.0)), 2)

                if req_cr is not None:
                    auto_done = effective_cr >= req_cr
                elif req_n is not None:
                    auto_done = len(matched_user) >= req_n
                else:
                    auto_done = len(matched_user) > 0

                cats_payload.append(
                    {
                        "id": cat.id,
                        "label": cat.label,
                        "short_label": cat.short_label,
                        "required_summary": cat.required_summary,
                        "rule_summary": cat.rule_summary,
                        "tone": cat.tone,
                        "required_count": req_n,
                        "required_credits": req_cr,
                        "earned_credits": effective_cr if (minor.id == "psychology" and cat.id == "psych_course") else earned_cr,
                        "in_progress_credits": ip_cr,
                        "auto_complete": auto_done,
                        "roster_count": cat_counts.get(cat.id, 0),
                        "matched_user_courses": matched_user,
                    }
                )
            versions_payload.append(
                {
                    "id": version.id,
                    "label": version.label,
                    "short_label": version.short_label,
                    "description": version.description,
                    "total_required_summary": version.total_required_summary,
                    "roster_count": total_matches,
                    "categories": cats_payload,
                }
            )
        item: dict[str, Any] = {
            "id": minor.id,
            "label": minor.label,
            "short_label": minor.short_label,
            "department": minor.department,
            "default_version": minor.default_version,
            "overview": minor.overview,
            "versions": versions_payload,
        }
        if minor.colleges:
            item["default_college"] = minor.default_college
            item["active_college"] = active_college
            item["colleges"] = [
                {
                    "id": col.id,
                    "label": col.label,
                    "short_label": col.short_label,
                    "total_required_summary": col.total_required_summary,
                    "note": col.note,
                }
                for col in minor.colleges
            ]
        catalog_items.append(item)
    return catalog_items
