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

_PAREN_RECOMMENDED_RE = re.compile(r"\([^)]*\brecommend(?:ed|ation|s)?\b[^)]*\)", re.IGNORECASE)
_CLAUSE_RECOMMENDED_SPLIT_RE = re.compile(r"[.;\n]+")
_TRAILING_RECOMMENDED_RE = re.compile(
    r"(?:,\s*|\b(?:and|or)\s+)?\b(?:strongly\s+|highly\s+)?recommend(?:ed|ation|s)?\b.*$",
    re.IGNORECASE,
)
_TOKEN_CODE_RE = re.compile(r"\b(?:([A-Z]{2,8})\s+)?([1-9]\d{3}[A-Z]?)\b")
_CARRIED_GAP_RE = re.compile(r"^[\s,;/&()]*(?:(?:OR|AND|AND/OR)[\s,;/&()]*)*$")
_CONNECTOR_WORDS: frozenset[str] = frozenset({"OR", "AND", "NOR"})
_NON_SUBJECT_WORDS: frozenset[str] = frozenset(
    {
        "OR",
        "AND",
        "NOR",
        "NOT",
        "BUT",
        "THE",
        "FOR",
        "WITH",
        "FROM",
        "INTO",
        "ANY",
        "ALL",
        "ONE",
        "TWO",
        "THREE",
        "BOTH",
        "EACH",
        "SOME",
        "ONLY",
        "SUCH",
        "SAME",
        "PLUS",
        "LESS",
        "MORE",
        "MIN",
        "MAX",
        "GPA",
        "AT",
        "IN",
        "ON",
        "TO",
        "OF",
        "BY",
        "VIA",
        "PER",
        "IS",
        "ARE",
        "HAS",
        "MAY",
        "SUMMER",
        "SPRING",
        "FALL",
        "WINTER",
        "PRIOR",
        "BEYOND",
        "GRADE",
        "CREDIT",
        "CREDITS",
        "LEVEL",
        "YEAR",
        "YEARS",
    }
)
_ENGRD_WORD_RE = re.compile(r"\bENGRD\b", re.IGNORECASE)
_NORMALIZE_CODE_RE = re.compile(r"^\s*([A-Za-z]{2,8})[\s\-_]*([1-9]\d{3}[A-Za-z]?)\s*$")
_CANONICAL_CODE_RE = re.compile(r"\b([A-Z]{2,8})\s+([1-9]\d{3}[A-Z]?)\b")

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


def strip_recommended_clauses(text: str) -> str:
    """Remove 'Recommended' prerequisites/corequisites while preserving required clauses."""
    if not text:
        return ""
    cleaned = _PAREN_RECOMMENDED_RE.sub(" ", text)
    kept_clauses: list[str] = []
    for raw_clause in _CLAUSE_RECOMMENDED_SPLIT_RE.split(cleaned):
        clause = raw_clause.strip()
        if not clause:
            continue
        if re.search(r"\brecommend(?:ed|ation|s)?\b", clause, re.IGNORECASE):
            # Preserve prefix before trailing recommended note (e.g. 'MATH 2940, recommended: CS 2110')
            prefix = _TRAILING_RECOMMENDED_RE.sub("", clause).strip(" ,;:")
            if prefix and len(prefix) >= 4:
                kept_clauses.append(prefix)
            continue
        kept_clauses.append(clause)
    return ". ".join(kept_clauses)


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
    if not raw:
        return None
    m = _NORMALIZE_CODE_RE.match(raw)
    if not m:
        return None
    return f"{m.group(1).upper()} {m.group(2).upper()}"


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


@dataclass(frozen=True, slots=True)
class CourseRef:
    code: str


@dataclass(frozen=True, slots=True)
class AllOf:
    items: tuple["PrereqNode", ...]


@dataclass(frozen=True, slots=True)
class AnyOf:
    items: tuple["PrereqNode", ...]


@dataclass(frozen=True, slots=True)
class AtLeast:
    required: int
    items: tuple["PrereqNode", ...]


PrereqNode = CourseRef | AllOf | AnyOf | AtLeast

_BOILERPLATE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bbackground\s+equivalent\s+to\s*:\s*", re.IGNORECASE),
    re.compile(r"\b(?:or\s+corequisites?|prerequisites?\s+or\s+corequisites?|corequisites?\s+or\s+prerequisites?)\s*:\s*", re.IGNORECASE),
    re.compile(r"\bminimum\s+(?:overall\s+|cumulative\s+)?grade\s+of\s+[A-F][+-]?\s+in\b", re.IGNORECASE),
    re.compile(r"\bwith\s+a\s+minimum\s+grade\s+of\s+[A-F][+-]?\b", re.IGNORECASE),
    re.compile(r"\((?:recommended|preferred|equivalent|or\s+equivalent|concurrency\s+permitted)\)", re.IGNORECASE),
    re.compile(r"(?:[;,]\s*|\s+)\bor\s+(?:their\s+|the\s+)?equivalents?\b", re.IGNORECASE),
    re.compile(r"(?:[;,]\s*|\s+)\bor\s+permission\s+of\s+(?:the\s+)?(?:instructor|department|program|director|[A-Z]{2,})\b", re.IGNORECASE),
    re.compile(r"(?:[;,]\s*|\s+)\bor\s+(?:instructor|department)\s+(?:permission|consent|approval)\b", re.IGNORECASE),
    re.compile(r"(?:[;,]\s*|\s+)\bor\s+(?:by\s+)?placement(?:\s+exam)?\b", re.IGNORECASE),
    re.compile(r"\bor\s+their\s+equivalents?\b", re.IGNORECASE),
)
_TRACK_SPLIT_RE = re.compile(r"(?:[.;]\s*)\b(?:Prerequisites?\s+)?for\s+[^:]{2,65}:\s*", re.IGNORECASE)
_SINGLE_TRACK_PREFIX_RE = re.compile(r"^\s*(?:Prerequisites?\s+)?for\s+[^:]{2,65}:\s*", re.IGNORECASE)
_TWO_THREE_OF_RE = re.compile(r"^(?:.*?\b)?(two|three|2|3)\s+of(?:\s+[^:]{1,80})?\s*:\s*(.+)$", re.IGNORECASE)
_ONE_ANY_OF_RE = re.compile(r"^(?:.*?\b)?(?:one|any|either|1)\s+of(?:\s+[^:]{1,80})?\s*:\s*(.+)$", re.IGNORECASE)
_CARRIED_EXPAND_GAP_RE = re.compile(r"^[\s,;/&()-]*(?:(?:OR|AND|AND/OR)[\s,;/&()-]*)*$")
_PAREN_GROUP_REF_RE = re.compile(r"^__PG(\d+)__$")


def _expand_carried_subjects_in_text(text: str) -> str:
    """Turn 'MATH 1920, 2220 or 2940' or 'CHEM 2070-2080' into explicit SUBJ NBR tokens."""
    upper = text.upper()
    out: list[str] = []
    cursor = 0
    last_subj: Optional[str] = None
    prev_match_end = 0

    for match in _TOKEN_CODE_RE.finditer(upper):
        subj, nbr = match.group(1), match.group(2)
        tail = upper[match.end() :]
        if tail.startswith("-LEVEL") or tail.startswith(" LEVEL"):
            last_subj = None
            prev_match_end = match.end()
            continue

        gap = upper[prev_match_end : match.start()]
        prev_match_end = match.end()

        if subj is None:
            if last_subj and _CARRIED_EXPAND_GAP_RE.match(gap):
                out.append(upper[cursor : match.start()])
                out.append(f"{last_subj} {nbr}")
                cursor = match.end()
        elif subj in _CONNECTOR_WORDS:
            if last_subj and _CARRIED_EXPAND_GAP_RE.match(gap):
                out.append(upper[cursor : match.end(1)])
                out.append(" " + f"{last_subj} {nbr}")
                cursor = match.end()
        elif subj not in _NON_SUBJECT_WORDS:
            last_subj = subj
        else:
            last_subj = None

    out.append(upper[cursor:])
    return "".join(out)


def _collapse_and(nodes: list[PrereqNode]) -> Optional[PrereqNode]:
    flat: list[PrereqNode] = []
    for n in nodes:
        if isinstance(n, AllOf):
            flat.extend(n.items)
        else:
            flat.append(n)
    if not flat:
        return None
    return flat[0] if len(flat) == 1 else AllOf(tuple(flat))


def _collapse_or(nodes: list[PrereqNode]) -> Optional[PrereqNode]:
    flat: list[PrereqNode] = []
    for n in nodes:
        if isinstance(n, AnyOf):
            flat.extend(n.items)
        else:
            flat.append(n)
    if not flat:
        return None
    return flat[0] if len(flat) == 1 else AnyOf(tuple(flat))


def _resolve_paren_groups(expr: str, paren_map: dict[str, PrereqNode]) -> str:
    """Parse balanced (...) groups inside-out into paren_map placeholders."""
    curr = expr
    idx = 0
    while True:
        close_pos = curr.find(")")
        if close_pos < 0:
            break
        open_pos = curr.rfind("(", 0, close_pos)
        if open_pos < 0:
            curr = curr[:close_pos] + " " + curr[close_pos + 1 :]
            continue
        inner = curr[open_pos + 1 : close_pos].strip()
        parsed = _parse_clause_ast(inner, paren_map) if inner else None
        if parsed is not None:
            token = f"__PG{idx}__"
            idx += 1
            paren_map[token] = parsed
            curr = f"{curr[:open_pos]} {token} {curr[close_pos + 1 :]}"
        else:
            curr = f"{curr[:open_pos]} {curr[close_pos + 1 :]}"
    return curr.replace("(", " ").replace(")", " ")


def _parse_and_or_expr(expr: str, paren_map: dict[str, PrereqNode]) -> Optional[PrereqNode]:
    text = expr.strip(" ,;.")
    if not text:
        return None

    # Lowest precedence inside a comma-free chunk: 'AND', then 'OR' / '/', then '-' sequence
    and_chunks = [c.strip() for c in re.split(r"\bAND\b", text) if c.strip()]
    and_nodes: list[PrereqNode] = []
    for chunk in and_chunks:
        or_chunks = [o.strip() for o in re.split(r"\bOR\b|/", chunk) if o.strip()]
        or_nodes: list[PrereqNode] = []
        for branch in or_chunks:
            # Handle hyphenated course sequence like MATH 2230-MATH 2240
            seq_chunks = [s.strip() for s in re.split(r"\s*-\s*", branch) if s.strip()]
            seq_nodes: list[PrereqNode] = []
            for leaf in seq_chunks:
                pg_matches = re.findall(r"__PG\d+__", leaf)
                for pg in pg_matches:
                    if pg in paren_map:
                        seq_nodes.append(paren_map[pg])
                leaf_no_pg = re.sub(r"__PG\d+__", " ", leaf)
                for cm in _CANONICAL_CODE_RE.finditer(leaf_no_pg):
                    subj, nbr = cm.group(1), cm.group(2)
                    if subj not in _NON_SUBJECT_WORDS:
                        seq_nodes.append(CourseRef(f"{subj} {nbr}"))
            seq_node = _collapse_and(seq_nodes)
            if seq_node is not None:
                or_nodes.append(seq_node)
        or_node = _collapse_or(or_nodes)
        if or_node is not None:
            and_nodes.append(or_node)
    return _collapse_and(and_nodes)


def _parse_semicolon_part(part: str, paren_map: dict[str, PrereqNode]) -> Optional[PrereqNode]:
    text = part.strip(" ,;.")
    if not text:
        return None

    # Quantifier prefixes ('two of ...: A, B, C' / 'one of the following: A, B, C')
    m_quant = _TWO_THREE_OF_RE.match(text)
    if m_quant:
        req_count = 2 if m_quant.group(1).upper() in {"TWO", "2"} else 3
        items_text = m_quant.group(2)
        items = _parse_comma_items(items_text, paren_map)
        if len(items) >= req_count:
            return AtLeast(req_count, tuple(items))
        return _collapse_and(items)

    m_any = _ONE_ANY_OF_RE.match(text)
    if m_any:
        items = _parse_comma_items(m_any.group(1), paren_map)
        return _collapse_or(items)

    if "," not in text:
        return _parse_and_or_expr(text, paren_map)

    raw_segs = [s.strip() for s in text.split(",") if s.strip()]
    if len(raw_segs) <= 1:
        return _parse_and_or_expr(text, paren_map)

    starts_or = [bool(re.match(r"^OR\b", s)) for s in raw_segs]
    starts_and = [bool(re.match(r"^AND\b", s)) for s in raw_segs]
    # Serial OR ('A, B, C or D') or ', or' ('INFO 2950, or MATH 2940 and CS 2800')
    last_has_trailing_or = bool(re.match(r"^(?:OR\b|[^.]*\bOR\b)", raw_segs[-1]))
    is_serial_or = all(starts_or[1:]) or (
        not any(starts_and[1:])
        and (starts_or[-1] or (last_has_trailing_or and not any(re.search(r"\bOR\b|\bAND\b", s) for s in raw_segs[:-1])))
    )

    parsed_nodes: list[PrereqNode] = []
    for seg in raw_segs:
        cleaned_seg = re.sub(r"^(?:OR|AND)\s+", "", seg).strip()
        node = _parse_and_or_expr(cleaned_seg, paren_map)
        if node is not None:
            parsed_nodes.append(node)

    return _collapse_or(parsed_nodes) if is_serial_or else _collapse_and(parsed_nodes)


def _parse_comma_items(items_text: str, paren_map: dict[str, PrereqNode]) -> list[PrereqNode]:
    nodes: list[PrereqNode] = []
    for raw in items_text.split(","):
        cleaned = re.sub(r"^(?:OR|AND)\s+", "", raw.strip(" .;")).strip()
        if not cleaned:
            continue
        # Strip trailing 'or' inside serial items like 'BIOG 1445 or BIOEE 1610'
        node = _parse_and_or_expr(cleaned, paren_map)
        if node is not None:
            nodes.append(node)
    return nodes


def _parse_clause_ast(expr: str, paren_map: dict[str, PrereqNode]) -> Optional[PrereqNode]:
    text = expr.strip(" .;:")
    if not text:
        return None
    # Lowest precedence overall: top-level '; OR' / '. OR' separating alternative paths
    alt_blocks = [b.strip() for b in re.split(r"[;.]\s*OR\b", text) if b.strip()]
    alt_nodes: list[PrereqNode] = []
    for block in alt_blocks:
        semi_parts = [p.strip() for p in re.split(r"[;.]+", block) if p.strip()]
        part_nodes: list[PrereqNode] = []
        for part in semi_parts:
            p_node = _parse_semicolon_part(part, paren_map)
            if p_node is not None:
                part_nodes.append(p_node)
        and_block = _collapse_and(part_nodes)
        if and_block is not None:
            alt_nodes.append(and_block)
    return _collapse_or(alt_nodes)


def parse_prereq_ast(raw_prereq: str) -> tuple[str, Optional[PrereqNode]]:
    """Parse Cornell catalogPrereq text into `(mode, AST)`.

    Modes:
    - 'none': empty or only Recommended courses (no required prereqs)
    - 'ast': structured boolean AST of course codes
    - 'prose': non-empty requirement text naming no specific course codes
    """
    stripped = strip_recommended_clauses(raw_prereq).strip()
    if not stripped:
        return "none", None

    cleaned = stripped
    for pat in _BOILERPLATE_PATTERNS:
        cleaned = pat.sub(" ", cleaned)

    def _parse_track(raw_track: str) -> Optional[PrereqNode]:
        t_clean = _SINGLE_TRACK_PREFIX_RE.sub("", raw_track).strip()
        expanded = _expand_carried_subjects_in_text(t_clean)
        expanded = re.sub(r"\band\s*/\s*or\b", " OR ", expanded, flags=re.IGNORECASE)
        paren_map: dict[str, PrereqNode] = {}
        resolved = _resolve_paren_groups(expanded, paren_map)
        return _parse_clause_ast(resolved, paren_map)

    # Split multi-track requirements ('for programmers: ... Prerequisites for designers: ...')
    track_parts = [p.strip() for p in _TRACK_SPLIT_RE.split(cleaned) if p.strip()]
    if len(track_parts) > 1:
        track_nodes = [node for part in track_parts if (node := _parse_track(part)) is not None]
        merged = _collapse_or(track_nodes)
        if merged is not None:
            return "ast", merged
        return "prose", None

    node = _parse_track(cleaned)
    if node is not None:
        return "ast", node
    return "prose", None


def _format_missing_node(node: PrereqNode, satisfied: set[str]) -> str:
    """Render concise human-readable description of ONLY the unsatisfied portion of a failing node."""
    if isinstance(node, CourseRef):
        return node.code
    if isinstance(node, AllOf):
        unmet = [_format_missing_node(item, satisfied) for item in node.items if not _eval_node_bool(item, satisfied)]
        unmet = [u for u in unmet if u]
        return " & ".join(unmet[:3]) + (f" & +{len(unmet) - 3}" if len(unmet) > 3 else "")
    if isinstance(node, AnyOf):
        parts: list[str] = []
        for item in node.items:
            sub = _format_missing_node(item, satisfied)
            if sub:
                if " & " in sub and len(node.items) > 1:
                    parts.append(f"({sub})")
                else:
                    parts.append(sub)
        if len(parts) <= 3:
            return " / ".join(parts)
        return " / ".join(parts[:2]) + f" (+{len(parts) - 2} opts)"
    if isinstance(node, AtLeast):
        rem = [item.code if isinstance(item, CourseRef) else _format_missing_node(item, satisfied) for item in node.items if not _eval_node_bool(item, satisfied)]
        have = sum(1 for item in node.items if _eval_node_bool(item, satisfied))
        need = max(1, node.required - have)
        return f"any {need} of ({', '.join(rem[:3])}{'...' if len(rem) > 3 else ''})"
    return ""


def _eval_node_bool(node: PrereqNode, satisfied: set[str]) -> bool:
    if isinstance(node, CourseRef):
        return node.code in satisfied
    if isinstance(node, AllOf):
        return all(_eval_node_bool(item, satisfied) for item in node.items)
    if isinstance(node, AnyOf):
        return any(_eval_node_bool(item, satisfied) for item in node.items)
    if isinstance(node, AtLeast):
        return sum(1 for item in node.items if _eval_node_bool(item, satisfied)) >= node.required
    return False


def _collect_satisfied_refs(node: PrereqNode, satisfied: set[str], out: list[str], seen: set[str]) -> None:
    if isinstance(node, CourseRef):
        if node.code in satisfied and node.code not in seen:
            seen.add(node.code)
            out.append(node.code)
    elif isinstance(node, (AllOf, AnyOf, AtLeast)):
        for item in node.items:
            _collect_satisfied_refs(item, satisfied, out, seen)


def evaluate_prereq_node(mode: str, node: Optional[PrereqNode], satisfied: set[str]) -> dict[str, Any]:
    """Evaluate a parsed prerequisite AST against a user's expanded completed course set."""
    if mode == "none" or node is None and mode != "prose":
        return {
            "prereq_status": "none",
            "prereqs_met": True,
            "satisfied_by": [],
            "missing_prereqs": "",
        }
    if mode == "prose" or node is None:
        return {
            "prereq_status": "prose",
            "prereqs_met": False,
            "satisfied_by": [],
            "missing_prereqs": "Check catalog text prereq",
        }

    is_met = _eval_node_bool(node, satisfied)
    sat: list[str] = []
    _collect_satisfied_refs(node, satisfied, sat, set())
    if is_met:
        return {
            "prereq_status": "met",
            "prereqs_met": True,
            "satisfied_by": sat[:6],
            "missing_prereqs": "",
        }
    return {
        "prereq_status": "unmet",
        "prereqs_met": False,
        "satisfied_by": sat[:6],
        "missing_prereqs": _format_missing_node(node, satisfied),
    }


def _to_float(val: Any) -> Optional[float]:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _has_3cr_letter_grade_group(row: dict[str, Any]) -> bool:
    """Return True if at least one enrollGroup allows >= 3 credits AND letter grading."""
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
                units_ok = (u_max is None) or (u_max >= 3.0)
                if gb_ok and units_ok:
                    return True
        if any_structured:
            return False

    units_max = float(row.get("units_max") or 0.0)
    has_letter = bool(row.get("has_letter_grade", True))
    units_ok = (units_max == 0.0) or (units_max >= 3.0)
    return units_ok and has_letter


def _parse_json_list(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return [str(x) for x in raw]
    if isinstance(raw, str) and raw:
        try:
            loaded = json.loads(raw)
            if isinstance(loaded, list):
                return [str(x) for x in loaded]
        except ValueError:
            pass
    return []


def _is_non_academic_only(row: dict[str, Any]) -> bool:
    """Detect independent study, research, project team, teaching, or PE credits."""
    subj = str(row.get("subject") or "").upper()
    if subj == "PE":
        return True
    components = _parse_json_list(row.get("components_json") or row.get("components"))
    if components and set(components).issubset(NON_ACADEMIC_COMPONENTS):
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

    def get(self, subject: str, catalog_nbr: str) -> CourseEligibility:
        code = f"{subject.upper()} {catalog_nbr.strip()}"
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
        code = f"{subject.upper()} {catalog_nbr.strip()}"
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
            nbr = str(row.get("catalog_nbr") or "").strip()
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
