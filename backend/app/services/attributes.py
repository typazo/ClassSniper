"""Cornell distribution, writing, language, and curriculum attribute extraction & filtering."""

from __future__ import annotations

import re
from typing import Any, Iterable, Optional

import orjson

_ATTR_TOKEN_RE = re.compile(r"\b([A-Z0-9]+(?:-[A-Z0-9]+)+)\b|\b([A-Z]{2,}LANG|[A-Z]{2,}AREA)\b")
_FWS_TITLE_RE = re.compile(r"(?:^|\b)FWS\s*[:\-–]|^\s*FWS\b", re.IGNORECASE)

# Canonicalize checklist aliases to the live Cornell Class Roster API codes.
ATTR_ALIASES: dict[str, str] = {
    "HIST-AS": "HST-AS",
}

AS_DISTRIBUTION_CODES: tuple[str, ...] = (
    "ALC-AS",
    "BIO-AS",
    "ETM-AS",
    "GLC-AS",
    "HST-AS",
    "PHS-AS",
    "SCD-AS",
    "SSC-AS",
    "SDS-AS",
    "SMR-AS",
)

ATTRIBUTE_CATALOG: tuple[dict[str, str], ...] = (
    {"code": "ALC-AS", "label": "Arts, Literature & Culture", "group": "as_dist"},
    {"code": "BIO-AS", "label": "Biological Sciences", "group": "as_dist"},
    {"code": "ETM-AS", "label": "Ethics & the Mind", "group": "as_dist"},
    {"code": "GLC-AS", "label": "Global Citizenship", "group": "as_dist"},
    {"code": "HST-AS", "label": "Historical Analysis", "group": "as_dist"},
    {"code": "PHS-AS", "label": "Physical Sciences", "group": "as_dist"},
    {"code": "SCD-AS", "label": "Social Difference", "group": "as_dist"},
    {"code": "SSC-AS", "label": "Social Sciences", "group": "as_dist"},
    {"code": "SDS-AS", "label": "Statistics & Data Science", "group": "as_dist"},
    {"code": "SMR-AS", "label": "Symbolic & Math Reasoning", "group": "as_dist"},
    {"code": "FWS", "label": "First-Year Writing Seminar", "group": "college"},
    {"code": "LANG", "label": "Foreign Language (Any)", "group": "college"},
    {"code": "PE", "label": "Physical Education", "group": "college"},
    {"code": "ENGRI", "label": "Intro to Engineering", "group": "eng_cals"},
    {"code": "ENGRD", "label": "Engineering Distribution", "group": "eng_cals"},
    {"code": "CA-AG", "label": "Cultural Analysis (CA-AG)", "group": "eng_cals"},
    {"code": "HA-AG", "label": "Historical Analysis (HA-AG)", "group": "eng_cals"},
    {"code": "KCM-AG", "label": "Knowledge, Cognition, Moral", "group": "eng_cals"},
    {"code": "LA-AG", "label": "Literature & the Arts (LA-AG)", "group": "eng_cals"},
    {"code": "SBA-AG", "label": "Social & Behavioral (SBA-AG)", "group": "eng_cals"},
    {"code": "MQL-AG", "label": "Math & Quant Reasoning", "group": "eng_cals"},
    {"code": "WRT-AG", "label": "Writing (WRT-AG)", "group": "eng_cals"},
    {"code": "CE-EN", "label": "Engr. Communications", "group": "eng_cals"},
    {"code": "FL-AG", "label": "Foreign Language (FL-AG)", "group": "eng_cals"},
    {"code": "FLOPI-AS", "label": "Language Option (FLOPI-AS)", "group": "eng_cals"},
    {"code": "CU-CEL", "label": "Community-Engaged Learning", "group": "exploratory"},
    {"code": "CU-UGR", "label": "Undergraduate Research", "group": "exploratory"},
    {"code": "CU-SBY", "label": "Sustainability", "group": "exploratory"},
)

_KNOWN_ORDER: dict[str, int] = {entry["code"]: idx for idx, entry in enumerate(ATTRIBUTE_CATALOG)}


def normalize_attr_code(raw: str) -> str:
    """Normalize an attribute filter token and map checklist aliases like HIST-AS -> HST-AS."""
    code = (raw or "").strip().upper()
    if not code:
        return ""
    return ATTR_ALIASES.get(code, code)


def _decode_attrs_raw(crse_attrs_json: Any) -> list[Any]:
    if isinstance(crse_attrs_json, list):
        return crse_attrs_json
    if isinstance(crse_attrs_json, str) and crse_attrs_json.strip():
        try:
            loaded = orjson.loads(crse_attrs_json)
            return loaded if isinstance(loaded, list) else []
        except Exception:
            return []
    return []


def _collect_attr_texts(entry: Any, out: list[str]) -> None:
    if isinstance(entry, dict):
        for key in ("crseAttrValues", "attrDescr", "attrDesc", "crseAttrValueDescr"):
            val = entry.get(key)
            if val:
                out.append(str(val))
        nested = entry.get("crseAttrValueGroups")
        if isinstance(nested, list):
            for child in nested:
                _collect_attr_texts(child, out)
    elif entry is not None:
        out.append(str(entry))


def extract_course_attributes(course: dict[str, Any]) -> list[str]:
    """Extract sorted canonical distribution/college attribute codes from course metadata."""
    found: set[str] = set()
    raw_items = _decode_attrs_raw(
        course.get("crse_attrs_json") if "crse_attrs_json" in course else course.get("crse_attrs")
    )
    texts: list[str] = []
    for entry in raw_items:
        _collect_attr_texts(entry, texts)
    for raw_text in texts:
        text = raw_text.upper()
        for m in _ATTR_TOKEN_RE.finditer(text):
            tok = normalize_attr_code(m.group(1) or m.group(2) or "")
            if tok and not tok.endswith("-IL"):
                found.add(tok)

    subject = str(course.get("subject") or "").strip().upper()
    title_long = str(course.get("title_long") or "")
    title_short = str(course.get("title_short") or "")

    if _FWS_TITLE_RE.search(title_long) or _FWS_TITLE_RE.search(title_short):
        found.add("FWS")
    if subject == "PE":
        found.add("PE")
    if subject == "ENGRI":
        found.add("ENGRI")
    if subject == "ENGRD":
        found.add("ENGRD")

    if (
        "FL-AG" in found
        or "FLOPI-AS" in found
        or any(code.endswith("LANG") for code in found)
    ):
        found.add("LANG")

    return sorted(found, key=lambda c: (_KNOWN_ORDER.get(c, 999), c))


def course_matches_attrs(
    course_attrs: Iterable[str],
    filter_codes: list[str],
    match_mode: str = "any",
) -> bool:
    """Evaluate whether extracted course attributes satisfy requested filter codes."""
    if not filter_codes:
        return True
    attr_set = {normalize_attr_code(c) for c in course_attrs if c}
    norm_filters = [normalize_attr_code(c) for c in filter_codes if normalize_attr_code(c)]
    if not norm_filters:
        return True
    if match_mode == "all":
        return all(code in attr_set for code in norm_filters)
    return any(code in attr_set for code in norm_filters)


def summarize_roster_attributes(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build sorted attribute catalog with live cached counts for UI filter chips."""
    counts: dict[str, int] = {}
    for row in rows:
        for code in extract_course_attributes(row):
            counts[code] = counts.get(code, 0) + 1

    known_by_code = {entry["code"]: entry for entry in ATTRIBUTE_CATALOG}
    options: list[dict[str, Any]] = []
    seen: set[str] = set()

    for entry in ATTRIBUTE_CATALOG:
        code = entry["code"]
        seen.add(code)
        options.append(
            {
                **entry,
                "count": counts.get(code, 0),
            }
        )

    for code in sorted(counts):
        if code in seen:
            continue
        options.append(
            {
                "code": code,
                "label": code,
                "group": "other",
                "count": counts[code],
            }
        )

    # Also include known non-empty or standard A&S/college options
    _ = known_by_code
    return options
