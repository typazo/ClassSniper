"""Evaluation, filtering, persistence helpers, and catalog assembly for Cornell minors."""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from app.services.minors_data import (
    MINORS_BY_ID,
    MINORS_REGISTRY,
    SUBJECT_ALIASES,
    MinorCategoryDef,
    MinorDef,
    MinorVersionDef,
)

_COURSE_CODE_RE = re.compile(r"^([A-Za-z]+)\s*[- ]?\s*(\d+[A-Za-z]?)$")

_BME_EXCLUDED_NBRS = frozenset(
    {"4660", "4661", "4665", "4960", "4970", "4975", "4980", "4990", "4992", "4993"}
)
_LSJ_EXCLUDED_NBRS = frozenset(
    {"3991", "3992", "4940", "4950", "4960", "4970", "4980", "4990", "4999"}
)
_HIST_EXCLUDED_NBRS = frozenset({"2001", "3002", "4001", "4002", "8004"})
_INFOSCI_EXCLUDED_NBRS = frozenset({"1998", "4900", "4910", "4997", "4998"})
_PSYCH_NON_MINOR_NBRS = frozenset({"1104", "2091", "2801", "4720", "4910"})
_PSYCH_AREA_CAT_IDS = frozenset(
    {"psych_cognition", "psych_development", "psych_neuro", "psych_social"}
)

_MINOR_WARNINGS: dict[str, dict[str, str]] = {
    "business": {
        "AEM 3100": "ENG/ORIE students: ORIE 3300/3500 satisfies the Statistics prerequisite instead of AEM 3100.",
    },
    "psychology": {
        "PSYCH 4700": "Maximum 6 credits total across PSYCH 4700 and PSYCH 4710 can count toward the 15-credit minor.",
        "PSYCH 4710": "Maximum 6 credits total across PSYCH 4700 and PSYCH 4710 can count toward the 15-credit minor.",
    },
}


def normalize_course_code(raw: str) -> str:
    """Normalize a Cornell course code like 'pam-2300' into 'PAM 2300'."""
    text = str(raw or "").strip().upper()
    if not text:
        return ""
    match = _COURSE_CODE_RE.match(text)
    if match:
        return f"{match.group(1)} {match.group(2)}"
    parts = text.split()
    if len(parts) >= 2:
        return f"{parts[0]} {parts[1]}"
    return text


def parse_json_value(raw: Any, default: Any) -> Any:
    """Decode JSON text safely, returning native collections untouched."""
    if raw is None or raw == "":
        return default
    if isinstance(raw, (list, dict)):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except Exception:
            return default
        return parsed
    return default


def parse_catalog_num(catalog_nbr: str, fallback: Any = None) -> int:
    """Parse leading integer course number from catalog_nbr or fallback."""
    if isinstance(fallback, (int, float)) and int(fallback) > 0:
        return int(fallback)
    match = re.match(r"(\d+)", str(catalog_nbr or "").strip())
    return int(match.group(1)) if match else 0


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
    return {
        cat.id
        for ver in minor_def.versions
        for cat in ver.categories
    }


def default_minor_prefs() -> dict[str, Any]:
    """Return empty normalized minor preferences structure."""
    return {
        "selected_minor": "",
        "versions": {m.id: m.default_version for m in MINORS_REGISTRY},
        "completed_categories": {},
        "hide_completed": True,
    }


def normalize_minor_prefs(raw: Any) -> dict[str, Any]:
    """Sanitize user minor preferences (selected minor, versions, completed parts)."""
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
) -> tuple[Optional[MinorDef], Optional[MinorVersionDef]]:
    """Resolve MinorDef and MinorVersionDef with fallback to minor.default_version."""
    minor = MINORS_BY_ID.get(str(minor_id or "").strip())
    if minor is None:
        return None, None
    req_ver = str(version_id or "").strip() or minor.default_version
    ver_map = {v.id: v for v in minor.versions}
    ver = ver_map.get(req_ver) or ver_map.get(minor.default_version) or minor.versions[0]
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

    if rule == "psych_elective":
        # Avoid overlapping breadth-area courses so checking a breadth area hides it cleanly.
        if matched_static_cats & _PSYCH_AREA_CAT_IDS:
            return False
        if fields["is_fws"] or fields["units_max"] < 1.0:
            return False
        for nbr, num in _subject_numbers(fields, {"PSYCH"}):
            if not (1000 <= num < 5000) or nbr in _PSYCH_NON_MINOR_NBRS:
                continue
            is_research = nbr in {"4700", "4710"}
            if not is_research and (not fields["has_letter_grade"] or fields["is_only_ind_rsc"]):
                continue
            return True
        return False

    if rule == "infosci_elective":
        # Any 2000+ non-IND INFO course or approved concentration course (excluding 1000-level non-conc core)
        for code in fields["candidate_codes"]:
            if code in cat.courses:
                if code in {"INFO 1200", "INFO 1260", "INFO 1300"} and "is_core" in matched_static_cats:
                    continue
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


def evaluate_course_for_minor(
    course: dict[str, Any],
    minor_id: str,
    version_id: str = "",
    completed_categories: Optional[set[str]] = None,
    active_categories: Optional[set[str]] = None,
) -> Optional[dict[str, Any]]:
    """Evaluate a course against a minor version; return eligibility dict or None."""
    minor, version = resolve_minor_and_version(minor_id, version_id)
    if minor is None or version is None:
        return None

    fields = _extract_course_fields(course)
    matched = _match_course_categories(fields, version)
    if not matched:
        return None

    completed_set = completed_categories or set()
    active_set = active_categories or set()

    matched_ids = [cat.id for cat in matched]
    remaining = [cat for cat in matched if cat.id not in completed_set]
    completed_matches = [cat for cat in matched if cat.id in completed_set]

    badges_source = remaining if (completed_set and remaining) else matched
    if active_set:
        filtered_badges = [cat for cat in badges_source if cat.id in active_set]
        if filtered_badges:
            badges_source = filtered_badges

    badges = [
        {
            "category_id": cat.id,
            "tone": cat.tone,
            "label": cat.short_label,
            "completed": cat.id in completed_set,
        }
        for cat in badges_source[:4]
    ]

    warnings: list[str] = []
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


def suggest_completed_categories(
    minor_id: str,
    version_id: str,
    completed_courses: list[str],
    in_progress_courses: Optional[list[str]] = None,
    meta_by_code: Optional[dict[str, dict[str, Any]]] = None,
) -> dict[str, list[str]]:
    """Map category_id -> matching user completed/in-progress course codes for auto-fill."""
    minor, version = resolve_minor_and_version(minor_id, version_id)
    if minor is None or version is None:
        return {}

    meta_lookup = meta_by_code or {}
    suggestions: dict[str, list[str]] = {}
    ordered_courses: list[tuple[str, str]] = []
    seen_codes: set[str] = set()

    for raw_code in completed_courses or []:
        code = normalize_course_code(raw_code)
        if code and code not in seen_codes:
            seen_codes.add(code)
            ordered_courses.append((code, code))

    for raw_code in in_progress_courses or []:
        code = normalize_course_code(raw_code)
        if code and code not in seen_codes:
            seen_codes.add(code)
            ordered_courses.append((code, f"{code} (IP)"))

    for code, display_label in ordered_courses:
        row = meta_lookup.get(code)
        if row is None:
            # Try department aliases in metadata lookup too
            subj, _, nbr = code.partition(" ")
            for alias_code in expand_code_with_aliases(subj, nbr):
                if alias_code in meta_lookup:
                    row = meta_lookup[alias_code]
                    break
        if row is None:
            row = _build_minimal_meta_row(code)

        fields = _extract_course_fields(row)
        # Ensure original transcript code/aliases are always included in candidate set
        subj, _, nbr = code.partition(" ")
        for alias_code in expand_code_with_aliases(subj, nbr):
            if alias_code not in fields["candidate_code_set"]:
                fields["candidate_codes"].append(alias_code)
                fields["candidate_code_set"].add(alias_code)
                s_alias, _, n_alias = alias_code.partition(" ")
                fields["candidate_subjects"].add(s_alias)
                fields["nbrs_by_subject"].setdefault(s_alias, set()).add(n_alias)

        matched_cats = _match_course_categories(fields, version)
        for cat in matched_cats:
            suggestions.setdefault(cat.id, []).append(display_label)

    return suggestions


def build_minors_catalog(
    roster_courses: list[dict[str, Any]],
    completed_courses: Optional[list[str]] = None,
    in_progress_courses: Optional[list[str]] = None,
    meta_by_code: Optional[dict[str, dict[str, Any]]] = None,
) -> list[dict[str, Any]]:
    """Build full API payload describing all minors, versions, counts, and user auto-fill."""
    comp_list = completed_courses or []
    ip_list = in_progress_courses or []

    # Precompute course category counts per (minor_id, version_id, cat_id) across current roster.
    counts: dict[tuple[str, str, str], int] = {}
    version_totals: dict[tuple[str, str], int] = {}

    extracted_roster: list[tuple[dict[str, Any], dict[str, Any]]] = [
        (course, _extract_course_fields(course)) for course in roster_courses
    ]

    for minor in MINORS_REGISTRY:
        for version in minor.versions:
            total_matches = 0
            for _, fields in extracted_roster:
                matched = _match_course_categories(fields, version)
                if matched:
                    total_matches += 1
                    for cat in matched:
                        key = (minor.id, version.id, cat.id)
                        counts[key] = counts.get(key, 0) + 1
            version_totals[(minor.id, version.id)] = total_matches

    catalog_items: list[dict[str, Any]] = []
    for minor in MINORS_REGISTRY:
        versions_payload: list[dict[str, Any]] = []
        for version in minor.versions:
            auto_matches = suggest_completed_categories(
                minor.id,
                version.id,
                comp_list,
                ip_list,
                meta_by_code=meta_by_code,
            )
            cats_payload = [
                {
                    "id": cat.id,
                    "label": cat.label,
                    "short_label": cat.short_label,
                    "required_summary": cat.required_summary,
                    "rule_summary": cat.rule_summary,
                    "tone": cat.tone,
                    "roster_count": counts.get((minor.id, version.id, cat.id), 0),
                    "matched_user_courses": auto_matches.get(cat.id, []),
                }
                for cat in version.categories
            ]
            versions_payload.append(
                {
                    "id": version.id,
                    "label": version.label,
                    "short_label": version.short_label,
                    "description": version.description,
                    "total_required_summary": version.total_required_summary,
                    "roster_count": version_totals.get((minor.id, version.id), 0),
                    "categories": cats_payload,
                }
            )
        catalog_items.append(
            {
                "id": minor.id,
                "label": minor.label,
                "short_label": minor.short_label,
                "department": minor.department,
                "default_version": minor.default_version,
                "overview": minor.overview,
                "versions": versions_payload,
            }
        )
    return catalog_items
