"""Cornell CS Major Elective, Technical Elective, and External Specialization classifier.

Implements the official Cornell Computer Science B.S. & B.A. elective rules
using Class Roster API v2.0 metadata (catalogPrereq, catalogCoreq, enrollGroups,
simpleCombinations cross-lists, gradingBasis, and unitsMinimum/unitsMaximum).
"""

from __future__ import annotations

import json
import re
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Optional

from app.providers.cornell import LETTER_GRADE_BASES, parse_catalog_num
from app.services.common import (
    decode_json_list,
    normalize_course_code_strict,
    to_float as _to_float,
)
from app.services.prereq_ast import (
    _CANONICAL_CODE_RE,
    _CARRIED_EXPAND_GAP_RE as _CARRIED_GAP_RE,
    _CLAUSE_RECOMMENDED_SPLIT_RE,
    _CONNECTOR_WORDS,
    _NON_SUBJECT_WORDS,
    _TOKEN_CODE_RE,
    PrereqNode,
    evaluate_prereq_node,
    parse_prereq_ast,
    strip_recommended_clauses,
)

PRIORITY_STEM_SUBJECTS: tuple[str, ...] = (
    "CS",
    "MATH",
    "ORIE",
    "STSCI",
    "BTRY",
    "ECE",
    "INFO",
    "ENGRD",
    "MAE",
    "BEE",
    "CEE",
    "CHEME",
    "MSE",
    "AEP",
    "PHYS",
    "CHEM",
    "BIOMG",
    "BIOEE",
    "BIOG",
    "BIONB",
    "ECON",
    "AEM",
    "LING",
    "COGST",
    "PSYCH",
    "PHIL",
)

# Official Cornell CS list of 58 qualifying prerequisite/corequisite courses (+ any ENGRD course).
QUALIFYING_SEED_COURSES: frozenset[str] = frozenset(
    {
        "AEM 2100",
        "AEM 2240",
        "AEM 2241",
        "BEE 2510",
        "BEE 2600",
        "BIOEE 1610",
        "BIOEE 1780",
        "BIOG 1445",
        "BIOMG 2800",
        "BIOMG 3300",
        "BIOMG 3310",
        "BIOMG 3320",
        "BIOMG 3350",
        "BIONB 2220",
        "CEE 3040",
        "CHEM 1560",
        "CHEM 1570",
        "CHEM 2070",
        "CHEM 2090",
        "CHEM 2150",
        "CS 2110",
        "CS 2112",
        "CS 2800",
        "CS 2802",
        "ECON 3030",
        "ECON 3040",
        "ECON 3110",
        "ECON 3120",
        "ECON 3130",
        "INFO 2300",
        "INFO 2950",
        "INFO 3300",
        "LING 3302",
        "LING 3303",
        "MATH 1120",
        "MATH 1910",
        "MATH 1920",
        "MATH 2210",
        "MATH 2220",
        "MATH 2240",
        "MATH 2930",
        "MATH 2940",
        "ORIE 3300",
        "ORIE 3500",
        "PHIL 2310",
        "PHYS 1112",
        "PHYS 1116",
        "PHYS 2207",
        "PHYS 2208",
        "PHYS 2213",
        "PHYS 2214",
        "PHYS 2217",
        "PHYS 2218",
        "PUBPOL 2100",
        "PUBPOL 2101",
        "STSCI 2100",
        "STSCI 2200",
        "STSCI 3080",
    }
)

# CS courses excluded from CS Electives under all tracks
CS_ELECTIVE_EXCLUDED: frozenset[str] = frozenset(
    {"CS 4090", "CS 4997", "CS 4998", "CS 4999", "CS 5998", "CS 5999", "CS 7999"}
)

# Official CS Project / Practicum courses (CS 4xx1 practicums + designated project courses)
CS_PROJECT_EXPLICIT: frozenset[str] = frozenset(
    {
        "CS 3152",
        "CS 4152",
        "CS 4154",
        "CS 4752",
        "CS 5150",
        "CS 5152",
        "CS 5412",
        "CS 5414",
        "CS 5431",
        "CS 5625",
        "CS 5643",
    }
)

# Mandatory upper-level CS Core (and their direct 5000-level cross-lists)
CS_CORE_FIXED: frozenset[str] = frozenset({"CS 4410", "CS 4414", "CS 4820"})

# Choice CS Core in Post-Fall 2024: CS 3700 or CS 3780 counts as CS Elective only if not used for Core
CS_CORE_OVERFLOW_AI_ML: frozenset[str] = frozenset({"CS 3700", "CS 3780"})

# Required CS intro/core courses (and 5000-level Core equivalents) that cannot casually double-count as TE
CS_CORE_MANDATORY_ALL: frozenset[str] = frozenset(
    {
        "CS 1110",
        "CS 1112",
        "CS 1114",
        "CS 1115",
        "CS 2110",
        "CS 2112",
        "CS 2800",
        "CS 2802",
        "CS 3110",
        "CS 4410",
        "CS 4414",
        "CS 4820",
        "CS 5410",
        "CS 5820",
    }
)

# Choice-pair CS Core courses (allowed as TE/CS Elective if student used the other option for CS Core)
CS_CORE_CHOICE_PAIR: frozenset[str] = frozenset({"CS 3410", "CS 3420", "CS 3700", "CS 3780", "CS 5700", "CS 5780"})

# Explicitly banned from Technical Electives
TECH_ELECTIVE_EXCLUDED: frozenset[str] = frozenset({"CS 4090", "CS 4997", "CS 4998", "CS 5998", "CS 5999", "CS 7999"})
TECH_ELECTIVE_RESEARCH_CODES: frozenset[str] = frozenset({"CS 4999"})

NON_ACADEMIC_COMPONENTS: frozenset[str] = frozenset({"IND", "RSC", "PRJ", "TA", "TUT"})

_EXCLUDED_EXT_SPEC_TITLE_RE = re.compile(
    r"\b(?:"
    r"independent\s+(?:study|reading|research)"
    r"|directed\s+(?:reading|research|study)"
    r"|honors\s+(?:thesis|research)"
    r"|thesis\s+research"
    r"|team\s+projects?"
    r"|project\s+team"
    r"|practical\s+training"
    r"|undergraduate\s+teaching"
    r"|teaching\s+(?:assistant|in\s+[a-z]+)"
    r"|mps\s+project"
    r"|specialization\s+project"
    r")\b",
    re.IGNORECASE,
)

_ENGRD_WORD_RE = re.compile(r"\bENGRD\b", re.IGNORECASE)

# Static equivalences for renumbered/historically linked Cornell prereqs not always repeated in simpleCombinations
STATIC_EQUIVALENT_GROUPS: tuple[tuple[str, ...], ...] = (
    ("CS 2110", "ENGRD 2110"),
    ("CS 2112", "ENGRD 2112"),
    ("CS 3420", "ECE 2300", "ENGRD 2300"),
    ("CS 3700", "CS 4700"),
    ("CS 3780", "CS 4780"),
    ("ECE 2100", "ENGRD 2100"),
    ("MAE 2020", "ENGRD 2020"),
    ("STSCI 3080", "BTRY 3080"),
    ("STSCI 2100", "ILRST 2100"),
    ("STSCI 2200", "BTRY 3010"),
    ("STSCI 3740", "ORIE 3741"),
    ("ORIE 3510", "STSCI 3510"),
)

# Cornell transcript placeholder / AP / transfer codes that are never listed on live Class Rosters
TRANSCRIPT_EQUIVALENT_CATALOG: dict[str, dict[str, Any]] = {
    "ENGL 1100F": {
        "code": "ENGL 1100F",
        "subject": "ENGL",
        "catalog_nbr": "1100F",
        "title_short": "English FWS AP Credit",
        "title_long": "English FWS AP Credit (AP Lit / Lang)",
        "units_min": 3.0,
        "units_max": 3.0,
        "acad_career": "UG",
        "acad_group": "AS",
        "attrs": ["FWS"],
        "crse_attrs_json": '[{"attrDescr":"Distribution Requirements","crseAttrValues":"(FWS)"}]',
        "keywords": (
            "ap lit",
            "ap literature",
            "ap english",
            "english literature",
            "english language",
            "fws",
            "ap fws",
            "1100f",
        ),
    },
    "ENGL 1101A": {
        "code": "ENGL 1101A",
        "subject": "ENGL",
        "catalog_nbr": "1101A",
        "title_short": "English AP Credit (Score 4)",
        "title_long": "English AP Credit (Score 4 · Liberal Studies)",
        "units_min": 3.0,
        "units_max": 3.0,
        "acad_career": "UG",
        "acad_group": "AS",
        "attrs": ["LA-AG"],
        "crse_attrs_json": '[{"attrDescr":"Distribution Requirements","crseAttrValues":"(LA-AG)"}]',
        "keywords": (
            "ap english",
            "ap lang",
            "ap lit",
            "english language",
            "1101a",
        ),
    },
    "BIOG 1101F": {
        "code": "BIOG 1101F",
        "subject": "BIOG",
        "catalog_nbr": "1101F",
        "title_short": "Biology AP Credit (Score 4)",
        "title_long": "Biological Sciences AP Credit (Score 4)",
        "units_min": 4.0,
        "units_max": 4.0,
        "acad_career": "UG",
        "acad_group": "AS",
        "attrs": [],
        "crse_attrs_json": "[]",
        "keywords": (
            "ap bio",
            "ap biology",
            "biology",
            "1101f",
        ),
    },
    "BIOG 1102F": {
        "code": "BIOG 1102F",
        "subject": "BIOG",
        "catalog_nbr": "1102F",
        "title_short": "Biology AP Credit (Score 5)",
        "title_long": "Biological Sciences AP Credit (Score 5)",
        "units_min": 8.0,
        "units_max": 8.0,
        "acad_career": "UG",
        "acad_group": "AS",
        "attrs": [],
        "crse_attrs_json": "[]",
        "keywords": (
            "ap bio",
            "ap biology",
            "biology",
            "1102f",
        ),
    },
    "MATH 1710": {
        "code": "MATH 1710",
        "subject": "MATH",
        "catalog_nbr": "1710",
        "title_short": "Statistical Thry & Application",
        "title_long": "Statistical Theory & Application (AP Statistics Credit)",
        "units_min": 4.0,
        "units_max": 4.0,
        "acad_career": "UG",
        "acad_group": "AS",
        "attrs": [],
        "crse_attrs_json": "[]",
        "keywords": (
            "ap stat",
            "ap stats",
            "ap statistics",
            "statistics",
            "statistical",
            "1710",
        ),
    },
    "SPAN 1100C": {
        "code": "SPAN 1100C",
        "subject": "SPAN",
        "catalog_nbr": "1100C",
        "title_short": "Spanish AP / Exam Credit",
        "title_long": "Spanish AP / Placement Credit",
        "units_min": 3.0,
        "units_max": 3.0,
        "acad_career": "UG",
        "acad_group": "AS",
        "attrs": ["FL-AG"],
        "crse_attrs_json": '[{"attrDescr":"Distribution Requirements","crseAttrValues":"(FL-AG)"}]',
        "keywords": (
            "ap spanish",
            "spanish",
            "case",
            "1100c",
        ),
    },
    "FREN 1100C": {
        "code": "FREN 1100C",
        "subject": "FREN",
        "catalog_nbr": "1100C",
        "title_short": "French AP / Exam Credit",
        "title_long": "French AP / Placement Credit",
        "units_min": 3.0,
        "units_max": 3.0,
        "acad_career": "UG",
        "acad_group": "AS",
        "attrs": ["FL-AG"],
        "crse_attrs_json": '[{"attrDescr":"Distribution Requirements","crseAttrValues":"(FL-AG)"}]',
        "keywords": (
            "ap french",
            "french",
            "case",
            "1100c",
        ),
    },
    "ITAL 1100C": {
        "code": "ITAL 1100C",
        "subject": "ITAL",
        "catalog_nbr": "1100C",
        "title_short": "Italian AP / Exam Credit",
        "title_long": "Italian AP / Placement Credit",
        "units_min": 3.0,
        "units_max": 3.0,
        "acad_career": "UG",
        "acad_group": "AS",
        "attrs": ["FL-AG"],
        "crse_attrs_json": '[{"attrDescr":"Distribution Requirements","crseAttrValues":"(FL-AG)"}]',
        "keywords": (
            "ap italian",
            "italian",
            "case",
            "1100c",
        ),
    },
}

# Clear upward sequential intro foundations implied when a student completed the subsequent course (or placed via AP)
IMPLICIT_PREREQ_MAP: dict[str, tuple[str, ...]] = {
    "CS 2110": ("CS 1110",),
    "CS 2112": ("CS 1110",),
    "ENGRD 2110": ("CS 1110",),
    "ENGRD 2112": ("CS 1110",),
    "CS 2800": ("CS 1110",),
    "CS 2802": ("CS 1110",),
    "CS 3110": ("CS 2110", "CS 2800"),
    "CS 3410": ("CS 2110",),
    "CS 3420": ("CS 2110",),
    "ECE 2300": ("CS 1110",),
    "ENGRD 2300": ("CS 1110",),
    "CS 4410": ("CS 3410",),
    "CS 4414": ("CS 3410",),
    "CS 4820": ("CS 3110", "CS 2800"),
    "MATH 1920": ("MATH 1910",),
    "MATH 2930": ("MATH 1920",),
    "MATH 2940": ("MATH 1920",),
    "MATH 1120": ("MATH 1110",),
    "MATH 2210": ("MATH 1120",),
    "MATH 2220": ("MATH 1120", "MATH 2210"),
    "MATH 2230": ("MATH 1120",),
    "MATH 2240": ("MATH 2230",),
    "ORIE 3310": ("ORIE 3300",),
    "ORIE 3510": ("ORIE 3500",),
}

_BIO_TEXT_RE = re.compile(
    r"\b(?:college|majors?)[-\s]+level\s+(?:[a-z]+\s+){0,2}biolog(?:y|ical)\b",
    re.IGNORECASE,
)
_CALC2_TEXT_RE = re.compile(
    r"\b(?:"
    r"second[-\s]+semester(?:\s+of)?\s+calculu?s"
    r"|two\s+semesters?\s+of\s+calculu?s"
    r"|calculu?s\s*(?:ii|2)\b"
    r"|multivariable\s+calculu?s"
    r"|multicalculus"
    r"|integral\s+calculu?s"
    r"|vector\s+calculu?s"
    r")",
    re.IGNORECASE,
)
_PROB_STAT_TEXT_RE = re.compile(
    r"\b(?:probability|statistics|statistical\s+(?:methods?|analysis|reasoning))\b",
    re.IGNORECASE,
)
_NEGATED_PROB_STAT_RE = re.compile(
    r"\b(?:no|not|without|neither|never)\s+(?:prior\s+|previous\s+|formal\s+|any\s+|background\s+in\s+|knowledge\s+of\s+)?(?:probability|statistics|statistical)\b",
    re.IGNORECASE,
)


def extract_prereq_codes(clean_text: str) -> tuple[list[str], bool]:
    """Extract normalized course codes (carrying subject across 'MATH 1920 or 2220') and ENGRD mention."""
    if not clean_text:
        return [], False
    upper = clean_text.upper()
    has_engrd = bool(_ENGRD_WORD_RE.search(upper))

    codes: list[str] = []
    seen: set[str] = set()
    for clause in _CLAUSE_RECOMMENDED_SPLIT_RE.split(upper):
        clause = clause.strip()
        if not clause:
            continue
        last_subj: Optional[str] = None
        prev_end = 0
        for match in _TOKEN_CODE_RE.finditer(clause):
            subj, nbr = match.group(1), match.group(2)
            tail = clause[match.end() :]
            if tail.startswith("-LEVEL") or tail.startswith(" LEVEL"):
                last_subj = None
                prev_end = match.end()
                continue

            gap = clause[prev_end : match.start()]
            prev_end = match.end()

            resolved_subj: Optional[str] = None
            if subj is None:
                if last_subj and _CARRIED_GAP_RE.match(gap):
                    resolved_subj = last_subj
            elif subj in _CONNECTOR_WORDS:
                if last_subj and _CARRIED_GAP_RE.match(gap):
                    resolved_subj = last_subj
            elif subj not in _NON_SUBJECT_WORDS:
                resolved_subj = subj
                last_subj = subj
            else:
                last_subj = None

            if resolved_subj:
                code = f"{resolved_subj} {nbr}"
                if code not in seen:
                    seen.add(code)
                    codes.append(code)

    return codes, has_engrd


def match_qualifying_prereq_text(clean_text: str) -> list[str]:
    """Check official text-based Technical Elective rules on sanitized prerequisite/corequisite text."""
    if not clean_text:
        return []
    matches: list[str] = []
    if _BIO_TEXT_RE.search(clean_text):
        matches.append("College-level biology")
    if _CALC2_TEXT_RE.search(clean_text):
        matches.append("Second-semester+ calculus")
    if _PROB_STAT_TEXT_RE.search(clean_text) and not _NEGATED_PROB_STAT_RE.search(clean_text):
        matches.append("Probability / statistics")
    return matches


def normalize_course_code(raw: str) -> Optional[str]:
    """Normalize arbitrary course input like 'cs2110' or 'CS-2110' into 'CS 2110'."""
    return normalize_course_code_strict(raw)


def normalize_completed_courses(codes: list[str]) -> list[str]:
    """Validate, deduplicate, and canonically sort user-selected completed course codes."""
    seen: set[str] = set()
    cleaned: list[str] = []
    for raw in codes:
        norm = normalize_course_code(str(raw))
        if norm and norm not in seen:
            seen.add(norm)
            cleaned.append(norm)

    def _sort_key(c: str) -> tuple[str, int, str]:
        subj, _, nbr = c.partition(" ")
        return (subj, parse_catalog_num(nbr), nbr)

    return sorted(cleaned, key=_sort_key)


def decode_completed_courses(raw_json: Optional[str]) -> list[str]:
    """Safely parse persisted JSON completed courses array."""
    if not raw_json:
        return []
    try:
        loaded = json.loads(raw_json)
        if isinstance(loaded, list):
            return normalize_completed_courses([str(x) for x in loaded])
    except (TypeError, ValueError):
        pass
    return []


_PLACEHOLDER_SEMESTERS: frozenset[str] = frozenset({"", "DONE", "TAKING"})
_PLACEHOLDER_GRADES: frozenset[str] = frozenset({"", "IP", "INP", "NGR"})


def normalize_course_detail(raw: Any) -> dict[str, str]:
    """Normalize optional {gr, sem, cr} metadata for a completed course."""
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    gr = str(raw.get("gr") or "").strip()[:12]
    sem = str(raw.get("sem") or "").strip()[:16]
    cr = str(raw.get("cr") or "").strip()[:12]
    if gr:
        out["gr"] = gr
    if sem and sem.upper() not in ("DONE", "TAKING"):
        out["sem"] = sem
    if cr:
        out["cr"] = cr
    return out


def decode_completed_course_details(raw_json: Any) -> dict[str, dict[str, str]]:
    """Safely parse persisted JSON map of normalized course code -> {gr, sem, cr}."""
    if not raw_json:
        return {}
    try:
        loaded = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
    except (TypeError, ValueError):
        return {}
    if not isinstance(loaded, dict):
        return {}
    out: dict[str, dict[str, str]] = {}
    for raw_code, raw_val in loaded.items():
        norm = normalize_course_code(str(raw_code))
        if not norm:
            continue
        cleaned = normalize_course_detail(raw_val)
        if cleaned:
            out[norm] = cleaned
    return out


def merge_course_detail_fields(
    existing: dict[str, str],
    incoming: dict[str, str],
) -> tuple[dict[str, str], bool]:
    """Enrich missing or placeholder {gr, sem, cr} fields without clobbering existing values."""
    merged = dict(existing)
    changed = False

    inc_gr = str(incoming.get("gr") or "").strip()[:12]
    inc_sem = str(incoming.get("sem") or "").strip()[:16]
    inc_cr = str(incoming.get("cr") or "").strip()[:12]

    cur_gr = str(merged.get("gr") or "").strip()
    if inc_gr and cur_gr.upper() in _PLACEHOLDER_GRADES and inc_gr != cur_gr:
        merged["gr"] = inc_gr
        changed = True

    cur_sem = str(merged.get("sem") or "").strip()
    if (
        inc_sem
        and inc_sem.upper() not in ("DONE", "TAKING")
        and cur_sem.upper() in _PLACEHOLDER_SEMESTERS
        and inc_sem != cur_sem
    ):
        merged["sem"] = inc_sem
        changed = True

    cur_cr = str(merged.get("cr") or "").strip()
    if inc_cr and (not cur_cr or "-" in cur_cr) and inc_cr != cur_cr:
        merged["cr"] = inc_cr
        changed = True

    return merged, changed


def build_alias_lookup(crosslists_by_code: Optional[dict[str, list[str]]] = None) -> dict[str, set[str]]:
    """Build bidirectional equivalence map merging live cross-lists and static renumbering aliases."""
    aliases: dict[str, set[str]] = {}
    for group in STATIC_EQUIVALENT_GROUPS:
        gset = set(group)
        for c in group:
            aliases.setdefault(c, set()).update(gset - {c})
    if crosslists_by_code:
        for code, partners in crosslists_by_code.items():
            cu = code.upper()
            for p in partners:
                pu = p.upper()
                if pu != cu:
                    aliases.setdefault(cu, set()).add(pu)
                    aliases.setdefault(pu, set()).add(cu)
    return aliases


def expand_satisfied_courses(
    completed_courses: list[str],
    crosslists_by_code: Optional[dict[str, list[str]]] = None,
    include_implied: bool = True,
) -> tuple[set[str], list[str]]:
    """Expand completed courses across cross-lists and optional implied foundational prerequisites.

    Returns `(all_satisfied_codes, implied_only_codes)`.
    """
    base = normalize_completed_courses(completed_courses)
    aliases = build_alias_lookup(crosslists_by_code)
    satisfied: set[str] = set(base)
    implied: list[str] = []
    seen_implied: set[str] = set()
    queue: deque[str] = deque(base)

    while queue:
        curr = queue.popleft()
        for partner in aliases.get(curr, ()):
            if partner not in satisfied:
                satisfied.add(partner)
                queue.append(partner)
        if include_implied:
            for foundation in IMPLICIT_PREREQ_MAP.get(curr, ()):
                if foundation not in satisfied:
                    satisfied.add(foundation)
                    queue.append(foundation)
                    if foundation not in seen_implied:
                        seen_implied.add(foundation)
                        implied.append(foundation)

    return satisfied, implied


def _has_min_cr_letter_grade_group(row: dict[str, Any], min_credits: float = 3.0) -> bool:
    """Return True if at least one enrollGroup allows >= min_credits AND letter grading."""
    raw_egs = row.get("enroll_groups")
    if raw_egs is None and row.get("enroll_groups_json"):
        try:
            raw_egs = json.loads(row["enroll_groups_json"])
        except (TypeError, ValueError):
            raw_egs = []
    if isinstance(raw_egs, list) and raw_egs:
        any_structured = False
        for eg in raw_egs:
            if not isinstance(eg, dict):
                continue
            gb = str(eg.get("gradingBasis") or "").strip().upper()
            u_max = _to_float(eg.get("unitsMaximum"))
            if u_max is None:
                u_max = _to_float(eg.get("unitsMinimum"))
            if gb or u_max is not None:
                any_structured = True
                gb_ok = (not gb) or (gb in LETTER_GRADE_BASES)
                units_ok = (u_max is None) or (u_max >= min_credits)
                if gb_ok and units_ok:
                    return True
        if any_structured:
            return False

    units_max = float(row.get("units_max") or 0.0)
    has_letter = bool(row.get("has_letter_grade", True))
    units_ok = (units_max == 0.0) or (units_max >= min_credits)
    return units_ok and has_letter


def _has_3cr_letter_grade_group(row: dict[str, Any]) -> bool:
    """Return True if at least one enrollGroup allows >= 3 credits AND letter grading."""
    return _has_min_cr_letter_grade_group(row, min_credits=3.0)


def _parse_json_list(raw: Any) -> list[str]:
    return [str(x) for x in decode_json_list(raw)]


def _is_non_academic_only(row: dict[str, Any], allow_prj: bool = False) -> bool:
    """Detect independent study, research, project team, teaching, or PE credits."""
    subj = str(row.get("subject") or "").upper()
    if subj == "PE":
        return True
    components = _parse_json_list(row.get("components_json") or row.get("components"))
    disallowed = NON_ACADEMIC_COMPONENTS - {"PRJ"} if allow_prj else NON_ACADEMIC_COMPONENTS
    if components and set(components).issubset(disallowed):
        return True
    title = str(row.get("title_long") or row.get("title_short") or "")
    if _EXCLUDED_EXT_SPEC_TITLE_RE.search(title):
        return True
    return False


@dataclass(slots=True)
class CourseEligibility:
    cs_elective: bool = False
    cs_elective_pre2024: bool = False
    cs_elective_warning: str = ""
    cs_project: bool = False
    tech_elective: bool = False
    tech_elective_is_2000: bool = False
    tech_elective_is_research: bool = False
    tech_elective_reason: str = ""
    tech_elective_warning: str = ""
    external_spec: bool = False
    external_spec_warning: str = ""
    badges: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cs_elective": self.cs_elective,
            "cs_elective_pre2024": self.cs_elective_pre2024,
            "cs_elective_warning": self.cs_elective_warning,
            "cs_project": self.cs_project,
            "tech_elective": self.tech_elective,
            "tech_elective_is_2000": self.tech_elective_is_2000,
            "tech_elective_is_research": self.tech_elective_is_research,
            "tech_elective_reason": self.tech_elective_reason,
            "tech_elective_warning": self.tech_elective_warning,
            "external_spec": self.external_spec,
            "external_spec_warning": self.external_spec_warning,
            "badges": list(self.badges),
        }


class CSRequirementsIndex:
    """In-memory classifier for a single roster supporting BFS Technical Elective prereq chains."""

    def __init__(self, courses: list[dict[str, Any]]) -> None:
        self._by_code: dict[str, CourseEligibility] = {}
        self._crosslists_by_code: dict[str, list[str]] = {}
        self._prereq_ast_by_code: dict[str, tuple[str, Optional[PrereqNode]]] = {}
        self._build(courses)

    def has_course(self, subject: str, catalog_nbr: str) -> bool:
        code = f"{subject.upper()} {catalog_nbr.strip().upper()}"
        return code in self._by_code

    def get(self, subject: str, catalog_nbr: str) -> CourseEligibility:
        code = f"{subject.upper()} {catalog_nbr.strip().upper()}"
        return self._by_code.get(code, CourseEligibility())

    def expand_satisfied_courses(
        self,
        completed_courses: list[str],
        include_implied: bool = True,
    ) -> tuple[set[str], list[str]]:
        return expand_satisfied_courses(
            completed_courses=completed_courses,
            crosslists_by_code=self._crosslists_by_code,
            include_implied=include_implied,
        )

    def evaluate_course_prereqs(
        self,
        subject: str,
        catalog_nbr: str,
        satisfied_set: set[str],
    ) -> dict[str, Any]:
        code = f"{subject.upper()} {catalog_nbr.strip().upper()}"
        mode, node = self._prereq_ast_by_code.get(code, ("none", None))
        return evaluate_prereq_node(mode, node, satisfied_set)

    def _build(self, courses: list[dict[str, Any]]) -> None:
        course_by_code: dict[str, dict[str, Any]] = {}
        crosslists_by_code: dict[str, list[str]] = {}
        clean_prereq_text: dict[str, str] = {}
        prereq_codes_map: dict[str, list[str]] = {}
        has_engrd_map: dict[str, bool] = {}

        for row in courses:
            subj = str(row.get("subject") or "").upper()
            nbr = str(row.get("catalog_nbr") or "").strip().upper()
            if not subj or not nbr:
                continue
            code = f"{subj} {nbr}"
            course_by_code[code] = row
            cross = [c.upper() for c in _parse_json_list(row.get("crosslists_json") or row.get("crosslists"))]
            crosslists_by_code[code] = cross

        self._crosslists_by_code = crosslists_by_code

        # Precompute direct prerequisite expressions (falling back to cross-listed sibling prereqs when empty)
        for code, row in course_by_code.items():
            # Parse strict prerequisite-only text (not concurrent coreq companions like CS 4121) for user eligibility check
            prereq_only_raw = str(row.get("catalog_prereq") or "").strip()
            if not prereq_only_raw:
                for sibling_code in crosslists_by_code.get(code, ()):
                    sib = course_by_code.get(sibling_code)
                    if sib and str(sib.get("catalog_prereq") or "").strip():
                        prereq_only_raw = str(sib.get("catalog_prereq") or "").strip()
                        break
            self._prereq_ast_by_code[code] = parse_prereq_ast(prereq_only_raw)

            combined_raw = " . ".join(
                part
                for part in (
                    str(row.get("catalog_prereq") or "").strip(),
                    str(row.get("catalog_coreq") or "").strip(),
                )
                if part
            )
            if not combined_raw:
                for sibling_code in crosslists_by_code.get(code, ()):
                    sib = course_by_code.get(sibling_code)
                    if not sib:
                        continue
                    sib_raw = " . ".join(
                        part
                        for part in (
                            str(sib.get("catalog_prereq") or "").strip(),
                            str(sib.get("catalog_coreq") or "").strip(),
                        )
                        if part
                    )
                    if sib_raw:
                        combined_raw = sib_raw
                        break
            cleaned = strip_recommended_clauses(combined_raw)
            clean_prereq_text[code] = cleaned
            extracted, has_engrd = extract_prereq_codes(cleaned)
            # Expand any extracted crosslist partners to cached siblings too
            expanded: list[str] = list(extracted)
            seen_exp = set(expanded)
            for ref in extracted:
                for x in crosslists_by_code.get(ref, ()):
                    if x not in seen_exp:
                        seen_exp.add(x)
                        expanded.append(x)
            prereq_codes_map[code] = expanded
            has_engrd_map[code] = has_engrd

        # Build reverse dependency index for BFS transitive chains: prereq_code -> [dependent_codes]
        reverse_deps: dict[str, list[str]] = {}
        for code, refs in prereq_codes_map.items():
            for ref in refs:
                reverse_deps.setdefault(ref, []).append(code)

        # Cross-list seed closure: e.g. ENGRD 2110 <-> CS 2110, STSCI 3110 <-> ECON 3110
        seed_aliases: set[str] = set(QUALIFYING_SEED_COURSES)
        for seed in QUALIFYING_SEED_COURSES:
            for alias in crosslists_by_code.get(seed, ()):
                seed_aliases.add(alias)

        # Level-0 qualification map: evaluate every course's OWN prereqs first (Pass 0a),
        # then propagate across cross-listed siblings (Pass 0b) so a cross-list never shadows
        # a course's own qualifying prerequisite.
        direct_reason: dict[str, str] = {}
        bfs_chain: dict[str, tuple[list[str], int]] = {}
        queue: deque[str] = deque()
        direct_entries: list[tuple[str, str]] = []

        for code in course_by_code:
            refs = prereq_codes_map[code]
            cleaned = clean_prereq_text[code]
            reason = ""
            detail = ""
            chain: list[str] = []

            if has_engrd_map[code]:
                engrd_refs = [r for r in refs if r.startswith("ENGRD ")]
                detail = engrd_refs[0] if engrd_refs else "ENGRD course"
                reason = f"TE rule: lists {detail} prereq"
                chain = [engrd_refs[0]] if engrd_refs else []
            elif any(r in seed_aliases for r in refs):
                hit = next(r for r in refs if r in seed_aliases)
                detail = hit
                reason = f"TE rule: lists {hit} prereq"
                chain = [hit]
            else:
                text_hits = match_qualifying_prereq_text(cleaned)
                if text_hits:
                    detail = text_hits[0]
                    reason = f"TE rule: lists {detail} prereq"
                    chain = [detail]

            if reason:
                direct_reason[code] = reason
                bfs_chain[code] = ([code, *chain] if chain else [code], 1)
                queue.append(code)
                direct_entries.append((code, detail))

        for code, detail in direct_entries:
            # Propagate across cross-listed partners only when partner has no direct seed of its own
            for partner in crosslists_by_code.get(code, ()):
                if partner in course_by_code and partner not in bfs_chain:
                    direct_reason[partner] = f"TE rule: cross-listed {code} lists {detail} prereq"
                    bfs_chain[partner] = (bfs_chain[code][0], 1)
                    queue.append(partner)

        # Transitive BFS fixed-point pass (bounded to 4 hops to avoid noisy long chains)
        while queue:
            curr = queue.popleft()
            curr_path, curr_hop = bfs_chain[curr]
            if curr_hop >= 4:
                continue
            for dep in reverse_deps.get(curr, ()):
                if dep in bfs_chain or dep in curr_path:
                    continue
                new_path = [dep, *curr_path]
                bfs_chain[dep] = (new_path, curr_hop + 1)
                direct_reason[dep] = f"TE rule: prereq chain {' -> '.join(curr_path[:3])}"
                queue.append(dep)
                for partner in crosslists_by_code.get(dep, ()):
                    if partner in course_by_code and partner not in bfs_chain and partner not in new_path:
                        bfs_chain[partner] = (new_path, curr_hop + 1)
                        direct_reason[partner] = f"TE rule: cross-listed {dep} chain {' -> '.join(curr_path[:3])}"
                        queue.append(partner)

        # Evaluate final eligibility & badges for every course
        for code, row in course_by_code.items():
            subj = str(row.get("subject") or "").upper()
            nbr = str(row.get("catalog_nbr") or "").strip()
            cat_num = int(row.get("catalog_num") or parse_catalog_num(nbr))
            cross = crosslists_by_code[code]
            eligible_3cr_letter = _has_3cr_letter_grade_group(row)
            units_min = float(row.get("units_min") or 0.0)
            units_max = float(row.get("units_max") or 0.0)
            non_academic = _is_non_academic_only(row)

            elig = CourseEligibility()

            # 1) CS Electives (subject == CS)
            is_crosslisted_with_fixed_core = any(c in CS_CORE_FIXED for c in cross)
            is_core_overflow_ai_ml = (code in CS_CORE_OVERFLOW_AI_ML) or any(
                c in CS_CORE_OVERFLOW_AI_ML for c in cross
            )
            if (
                subj == "CS"
                and eligible_3cr_letter
                and code not in CS_ELECTIVE_EXCLUDED
                and code not in CS_CORE_FIXED
                and not is_crosslisted_with_fixed_core
                and not non_academic
            ):
                if cat_num >= 4000:
                    elig.cs_elective = True
                    elig.cs_elective_pre2024 = True
                    if cat_num >= 5000:
                        elig.cs_elective_warning = "5000+ Grad · Check petition/limit rules"
                if is_core_overflow_ai_ml:
                    # Post-Fall 2024 allows CS 3700/3780 (and their 5700/5780 cross-lists) if not used for Core
                    elig.cs_elective = True
                    if cat_num < 4000:
                        elig.cs_elective_pre2024 = False
                    if cat_num >= 5000:
                        elig.cs_elective_warning = "5000+ Grad · Allowed only if NOT used for CS Core"
                    else:
                        elig.cs_elective_warning = "Allowed only if NOT used for CS Core"

            eligible_2cr_letter = _has_min_cr_letter_grade_group(row, min_credits=2.0)
            is_proj_course = (
                (subj == "CS" and 4000 <= cat_num < 5000 and cat_num % 10 == 1)
                or code in CS_PROJECT_EXPLICIT
                or any(c in CS_PROJECT_EXPLICIT for c in cross)
            )
            if (
                is_proj_course
                and eligible_2cr_letter
                and not _is_non_academic_only(row, allow_prj=True)
            ):
                elig.cs_project = True

            # 2) Technical Electives (all subjects, CS 3000+ auto or prereq/chain >= 2000)
            te_excluded = (
                subj == "PE"
                or cat_num < 2000
                or code in TECH_ELECTIVE_EXCLUDED
                or code in CS_CORE_MANDATORY_ALL
                or not eligible_3cr_letter
                or (subj == "CS" and non_academic and code not in TECH_ELECTIVE_RESEARCH_CODES)
            )
            # Exclude ROTC < 3000 explicitly per handbook
            if subj in {"AIRS", "MILS", "NAVS"} and cat_num < 3000:
                te_excluded = True

            if not te_excluded:
                is_2000 = 2000 <= cat_num < 3000
                is_research = code in TECH_ELECTIVE_RESEARCH_CODES

                if code == "CS 4999":
                    elig.tech_elective = True
                    elig.tech_elective_is_research = True
                    elig.tech_elective_reason = "CS 4999 research (counts as TE if >=3 cr letter grade)"
                    elig.tech_elective_warning = "Research (CS 4999) · Needs >=3 cr & Letter Grade (max 2 research)"
                elif subj == "CS" and cat_num >= 3000 and not is_research:
                    elig.tech_elective = True
                    elig.tech_elective_reason = "CS 3000+ course (auto-qualifies as Tech Elective)"
                    if code in CS_CORE_CHOICE_PAIR:
                        elig.tech_elective_warning = "CS Core option · Counts only if not used for Core"
                    elif cat_num >= 5000:
                        elig.tech_elective_warning = "5000+ Grad · Counts toward TE if >=3 cr letter grade"
                elif code in direct_reason or (subj == "CS" and is_2000):
                    # Non-CS 2000+/3000+ with qualifying prereq/chain, or non-core CS 2000+ (e.g. CS 2770)
                    if non_academic and subj != "CS":
                        elig.tech_elective = True
                        elig.tech_elective_is_research = True
                        elig.tech_elective_is_2000 = is_2000
                        elig.tech_elective_reason = direct_reason.get(code, "")
                        elig.tech_elective_warning = "Research / Ind. Study · Needs faculty prereq confirmation"
                    else:
                        elig.tech_elective = True
                        elig.tech_elective_is_2000 = is_2000
                        elig.tech_elective_reason = direct_reason.get(code) or (
                            "CS 2000+ course (max 1 non-core allowed)" if subj == "CS" else ""
                        )
                        if is_2000:
                            elig.tech_elective_warning = "2000-level · Max 1 allowed toward Technical Electives"

            # 3) External Specialization (non-CS, non-PE, 3000+, >=3 cr, letter grade, non-research/ind/prj/teaching)
            if subj not in {"CS", "PE"} and cat_num >= 3000 and eligible_3cr_letter and not non_academic:
                elig.external_spec = True
                cs_cross = [c for c in cross if c.startswith("CS ")]
                if cs_cross:
                    elig.external_spec_warning = (
                        f"Cross-listed with {', '.join(cs_cross)} · Max 1 allowed for External Spec"
                    )

            # Variable credit warning if min < 3 while max >= 3
            var_cr_note = ""
            if eligible_3cr_letter and 0 < units_min < 3.0 <= units_max and code != "CS 4999":
                var_cr_note = f"Variable {units_min:g}-{units_max:g} cr · Select >=3 cr"

            # Assemble compact UI badges list
            badges: list[dict[str, str]] = []
            if elig.cs_elective:
                badges.append(
                    {
                        "kind": "cs_elective",
                        "tone": "amber" if is_core_overflow_ai_ml else "emerald",
                        "label": "CS Elective" + (" (If not Core)" if is_core_overflow_ai_ml else ""),
                    }
                )
            if elig.cs_project:
                badges.append(
                    {
                        "kind": "cs_project",
                        "tone": "violet",
                        "label": "CS Project",
                    }
                )
            if elig.tech_elective:
                badges.append(
                    {
                        "kind": "tech_elective",
                        "tone": "amber" if (elig.tech_elective_is_2000 or elig.tech_elective_is_research or elig.tech_elective_warning) else "sky",
                        "label": (
                            "Tech Elective (2000+ · Max 1)"
                            if elig.tech_elective_is_2000
                            else "Tech Elective (CS 4999 · >=3 cr Letter)"
                            if code == "CS 4999"
                            else "Tech Elective"
                        ),
                    }
                )
            if elig.external_spec:
                badges.append(
                    {
                        "kind": "external_spec",
                        "tone": "amber" if elig.external_spec_warning else "indigo",
                        "label": "Ext. Spec (CS Cross-list · Max 1)" if elig.external_spec_warning else "Ext. Spec",
                    }
                )
            if var_cr_note and (elig.cs_elective or elig.tech_elective or elig.external_spec):
                badges.append({"kind": "credits_warn", "tone": "amber", "label": var_cr_note})

            elig.badges = badges
            self._by_code[code] = elig
