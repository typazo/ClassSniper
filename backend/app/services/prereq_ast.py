"""Cornell catalog prerequisite sanitizer and boolean AST parser/evaluator."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

_PAREN_RECOMMENDED_RE = re.compile(r"\([^)]*\brecommend(?:ed|ation|s)?\b[^)]*\)", re.IGNORECASE)
_CLAUSE_RECOMMENDED_SPLIT_RE = re.compile(r"[.;\n]+")
_TRAILING_RECOMMENDED_RE = re.compile(
    r"(?:,\s*|\b(?:and|or)\s+)?\b(?:strongly\s+|highly\s+)?recommend(?:ed|ation|s)?\b.*$",
    re.IGNORECASE,
)
_TOKEN_CODE_RE = re.compile(r"\b(?:([A-Z]{2,8})\s+)?([1-9]\d{3}[A-Z]?)\b")
_CARRIED_EXPAND_GAP_RE = re.compile(r"^[\s,;/&()-]*(?:(?:OR|AND|AND/OR)[\s,;/&()-]*)*$")
_CANONICAL_CODE_RE = re.compile(r"\b([A-Z]{2,8})\s+([1-9]\d{3}[A-Z]?)\b")

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

_BOILERPLATE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bbackground\s+equivalent\s+to\s*:\s*", re.IGNORECASE),
    re.compile(
        r"\b(?:or\s+corequisites?|prerequisites?\s+or\s+corequisites?|corequisites?\s+or\s+prerequisites?)\s*:\s*",
        re.IGNORECASE,
    ),
    re.compile(r"\bminimum\s+(?:overall\s+|cumulative\s+)?grade\s+of\s+[A-F][+-]?\s+in\b", re.IGNORECASE),
    re.compile(r"\bwith\s+a\s+minimum\s+grade\s+of\s+[A-F][+-]?\b", re.IGNORECASE),
    re.compile(
        r"\((?:recommended|preferred|equivalent|or\s+equivalent|concurrency\s+permitted)\)",
        re.IGNORECASE,
    ),
    re.compile(r"(?:[;,]\s*|\s+)\bor\s+(?:their\s+|the\s+)?equivalents?\b", re.IGNORECASE),
    re.compile(
        r"(?:[;,]\s*|\s+)\bor\s+permission\s+of\s+(?:the\s+)?(?:instructor|department|program|director|[A-Z]{2,})\b",
        re.IGNORECASE,
    ),
    re.compile(r"(?:[;,]\s*|\s+)\bor\s+(?:instructor|department)\s+(?:permission|consent|approval)\b", re.IGNORECASE),
    re.compile(r"(?:[;,]\s*|\s+)\bor\s+(?:by\s+)?placement(?:\s+exam)?\b", re.IGNORECASE),
    re.compile(r"\bor\s+their\s+equivalents?\b", re.IGNORECASE),
)
_TRACK_SPLIT_RE = re.compile(r"(?:[.;]\s*)\b(?:Prerequisites?\s+)?for\s+[^:]{2,65}:\s*", re.IGNORECASE)
_SINGLE_TRACK_PREFIX_RE = re.compile(r"^\s*(?:Prerequisites?\s+)?for\s+[^:]{2,65}:\s*", re.IGNORECASE)
_TWO_THREE_OF_RE = re.compile(r"^(?:.*?\b)?(two|three|2|3)\s+of(?:\s+[^:]{1,80})?\s*:\s*(.+)$", re.IGNORECASE)
_ONE_ANY_OF_RE = re.compile(r"^(?:.*?\b)?(?:one|any|either|1)\s+of(?:\s+[^:]{1,80})?\s*:\s*(.+)$", re.IGNORECASE)


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
            prefix = _TRAILING_RECOMMENDED_RE.sub("", clause).strip(" ,;:")
            if prefix and len(prefix) >= 4:
                kept_clauses.append(prefix)
            continue
        kept_clauses.append(clause)
    return ". ".join(kept_clauses)


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

    and_chunks = [c.strip() for c in re.split(r"\bAND\b", text) if c.strip()]
    and_nodes: list[PrereqNode] = []
    for chunk in and_chunks:
        or_chunks = [o.strip() for o in re.split(r"\bOR\b|/", chunk) if o.strip()]
        or_nodes: list[PrereqNode] = []
        for branch in or_chunks:
            seq_chunks = [s.strip() for s in re.split(r"\s*-\s*", branch) if s.strip()]
            seq_nodes: list[PrereqNode] = []
            for leaf in seq_chunks:
                for pg in re.findall(r"__PG\d+__", leaf):
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


def _parse_comma_items(items_text: str, paren_map: dict[str, PrereqNode]) -> list[PrereqNode]:
    nodes: list[PrereqNode] = []
    for raw in items_text.split(","):
        cleaned = re.sub(r"^(?:OR|AND)\s+", "", raw.strip(" .;")).strip()
        if not cleaned:
            continue
        node = _parse_and_or_expr(cleaned, paren_map)
        if node is not None:
            nodes.append(node)
    return nodes


def _parse_semicolon_part(part: str, paren_map: dict[str, PrereqNode]) -> Optional[PrereqNode]:
    text = part.strip(" ,;.")
    if not text:
        return None

    m_quant = _TWO_THREE_OF_RE.match(text)
    if m_quant:
        req_count = 2 if m_quant.group(1).upper() in {"TWO", "2"} else 3
        items = _parse_comma_items(m_quant.group(2), paren_map)
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
    last_has_trailing_or = bool(re.match(r"^(?:OR\b|[^.]*\bOR\b)", raw_segs[-1]))
    is_serial_or = all(starts_or[1:]) or (
        not any(starts_and[1:])
        and (
            starts_or[-1]
            or (last_has_trailing_or and not any(re.search(r"\bOR\b|\bAND\b", s) for s in raw_segs[:-1]))
        )
    )

    parsed_nodes: list[PrereqNode] = []
    for seg in raw_segs:
        cleaned_seg = re.sub(r"^(?:OR|AND)\s+", "", seg).strip()
        node = _parse_and_or_expr(cleaned_seg, paren_map)
        if node is not None:
            parsed_nodes.append(node)

    return _collapse_or(parsed_nodes) if is_serial_or else _collapse_and(parsed_nodes)


def _parse_clause_ast(expr: str, paren_map: dict[str, PrereqNode]) -> Optional[PrereqNode]:
    text = expr.strip(" .;:")
    if not text:
        return None
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
    """Parse Cornell catalogPrereq text into `(mode, AST)`."""
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


def _format_missing_node(node: PrereqNode, satisfied: set[str]) -> str:
    """Render concise description of ONLY the unsatisfied portion of a failing node."""
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
                parts.append(f"({sub})" if " & " in sub and len(node.items) > 1 else sub)
        if len(parts) <= 3:
            return " / ".join(parts)
        return " / ".join(parts[:2]) + f" (+{len(parts) - 2} opts)"
    if isinstance(node, AtLeast):
        rem = [
            item.code if isinstance(item, CourseRef) else _format_missing_node(item, satisfied)
            for item in node.items
            if not _eval_node_bool(item, satisfied)
        ]
        have = sum(1 for item in node.items if _eval_node_bool(item, satisfied))
        need = max(1, node.required - have)
        return f"any {need} of ({', '.join(rem[:3])}{'...' if len(rem) > 3 else ''})"
    return ""


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
    if mode == "none" or (node is None and mode != "prose"):
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
