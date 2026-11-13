"""Cornell ILR New Curriculum classification, distribution eligibility, and summary helpers."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional, Sequence

from app.services.cs_requirements import normalize_course_code

ILR_CURRICULUM_URL = (
    "https://www.ilr.cornell.edu/current-students/"
    "undergraduate-student-resources/curriculum-requirements/"
    "new-curriculum-requirements"
)

ILR_MAIN_ELECTIVE_CODES: tuple[str, ...] = ("ICL-IL", "LH-IL", "QP-IL")

ILR_REQUIREMENT_ORDER: tuple[str, ...] = (
    "ICL-IL",
    "LH-IL",
    "QP-IL",
    "STA-IL",
    "SOW-IL",
    "SCT-IL",
    "AWI-IL",
    "ILR-CORE",
    "ICE-IL",
    "OCE-IL",
    "OCL-IL",
)

# Official ILR New Curriculum required sequence courses (typically carry no -IL roster attrs).
ILR_CORE_COURSES: dict[str, str] = {
    "ILRID 1500": "First-Year Colloquium",
    "ILRID 2500": "Sophomore Career & Life Design",
    "ILROB 1220": "Introduction to Organizational Behavior",
    "ILRGL 1100": "Introduction to US Labor History",
    "ECON 1110": "Introductory Microeconomics",
    "ECON 1120": "Introductory Macroeconomics",
    "ILRGL 2010": "Labor and Employment Law",
    "ILRHR 2600": "Human Resource Management",
    "ILRGL 2050": "Labor Relations",
    "ILRLE 2400": "Economics of Wages and Employment",
}

PRIORITY_ILR_SUBJECTS: tuple[str, ...] = (
    "ILRGL",
    "ILRHR",
    "ILRID",
    "ILRLE",
    "ILROB",
    "ILRST",
    "ECON",
    "AEM",
    "PUBPOL",
    "STSCI",
    "HIST",
    "AMST",
    "ENGL",
)

PRIORITY_ILR_PREREQ_SUBJECTS: tuple[str, ...] = (
    "ILRGL",
    "ILRHR",
    "ILRLE",
    "ILROB",
    "ILRST",
    "ILRID",
    "ECON",
    "STSCI",
    "CS",
    "MATH",
    "INFO",
    "AEM",
    "PUBPOL",
)

_IL_CODE_RE = re.compile(r"\b([A-Z0-9]+-IL)\b")
_DISTRIBUTION_CODES = frozenset({"STA-IL", "SOW-IL", "SCT-IL", "AWI-IL"})
_CREDIT_POOL_CODES = frozenset({"ICE-IL", "OCE-IL", "OCL-IL"})


@dataclass(frozen=True)
class ILRRequirementDef:
    code: str
    label: str
    short_label: str
    group: str  # "main_elective" | "distribution" | "core" | "credit_pool"
    rule_summary: str
    tone: str
    requires_three_credits: bool = False
    requires_letter_grade: bool = True

    def to_badge_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "label": self.label,
            "short_label": self.short_label,
            "group": self.group,
            "rule_summary": self.rule_summary,
            "tone": self.tone,
            "is_main_elective": self.group == "main_elective",
        }


ILR_REQUIREMENT_DEFS: dict[str, ILRRequirementDef] = {
    "ICL-IL": ILRRequirementDef(
        code="ICL-IL",
        label="International & Comparative Labor Elective",
        short_label="Intl & Comp Labor",
        group="main_elective",
        rule_summary="Counts toward the 3 Main ILR Advanced Electives (min 1 course, 3–4 cr, letter grade).",
        tone="sky",
        requires_three_credits=True,
    ),
    "LH-IL": ILRRequirementDef(
        code="LH-IL",
        label="Labor History Elective",
        short_label="Labor History",
        group="main_elective",
        rule_summary="Counts toward the 3 Main ILR Advanced Electives (min 1 course, 3–4 cr, letter grade).",
        tone="amber",
        requires_three_credits=True,
    ),
    "QP-IL": ILRRequirementDef(
        code="QP-IL",
        label="Quantitative Policy Elective",
        short_label="Quant Policy",
        group="main_elective",
        rule_summary="Counts toward the 3 Main ILR Advanced Electives (formerly Economic Policy; 3–4 cr, letter grade).",
        tone="emerald",
        requires_three_credits=True,
    ),
    "STA-IL": ILRRequirementDef(
        code="STA-IL",
        label="Statistics Requirement",
        short_label="Statistics",
        group="distribution",
        rule_summary="Approved ILR statistics/quantitative core option (Fall 2024+ students need 7 credits from STA-IL).",
        tone="violet",
        requires_three_credits=False,
    ),
    "SOW-IL": ILRRequirementDef(
        code="SOW-IL",
        label="Sophomore Writing",
        short_label="Soph Writing",
        group="distribution",
        rule_summary="Required ILR Sophomore Writing seminar (letter grade).",
        tone="rose",
        requires_three_credits=True,
    ),
    "SCT-IL": ILRRequirementDef(
        code="SCT-IL",
        label="Science & Technology Distribution",
        short_label="Sci & Tech",
        group="distribution",
        rule_summary="Required Science & Technology distribution (one 3–4 cr course, letter grade).",
        tone="cyan",
        requires_three_credits=True,
    ),
    "AWI-IL": ILRRequirementDef(
        code="AWI-IL",
        label="Advanced Writing Intensive",
        short_label="Adv Writing",
        group="distribution",
        rule_summary="Upper-level ILR Advanced Writing Intensive elective (letter grade).",
        tone="fuchsia",
        requires_three_credits=True,
    ),
    "ILR-CORE": ILRRequirementDef(
        code="ILR-CORE",
        label="ILR Required Core",
        short_label="ILR Core",
        group="core",
        rule_summary="Required ILR foundation core sequence (curated; core courses carry no -IL roster tags).",
        tone="teal",
        requires_three_credits=False,
    ),
    "ICE-IL": ILRRequirementDef(
        code="ICE-IL",
        label="In-College Advanced Elective",
        short_label="In-College",
        group="credit_pool",
        rule_summary="Counts toward the 24+ in-college elective credits within the 40-credit ILR elective requirement.",
        tone="indigo",
        requires_three_credits=False,
    ),
    "OCE-IL": ILRRequirementDef(
        code="OCE-IL",
        label="Out-of-College Advanced Elective",
        short_label="Out-of-College",
        group="credit_pool",
        rule_summary="Counts toward up to 16 out-of-college elective credits (Summer 2025+ approved list).",
        tone="slate",
        requires_three_credits=False,
    ),
    "OCL-IL": ILRRequirementDef(
        code="OCL-IL",
        label="Out-of-College Language Elective",
        short_label="Language",
        group="credit_pool",
        rule_summary="Foreign language elective; up to 12 credits count toward the 16 out-of-college elective cap.",
        tone="zinc",
        requires_three_credits=False,
    ),
}


def get_ilr_requirement_def(code: str) -> ILRRequirementDef:
    norm = code.strip().upper()
    if norm in ILR_REQUIREMENT_DEFS:
        return ILR_REQUIREMENT_DEFS[norm]
    return ILRRequirementDef(
        code=norm,
        label=f"{norm} Distribution",
        short_label=norm,
        group="credit_pool",
        rule_summary="Cornell Class Roster ILR distribution attribute.",
        tone="slate",
        requires_three_credits=False,
    )


def _safe_json_loads(raw: Any, default: Any) -> Any:
    if isinstance(raw, (list, dict)):
        return raw
    if not raw or not isinstance(raw, str):
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


def _to_float(val: Any) -> Optional[float]:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _fmt_credits(units_min: Optional[float], units_max: Optional[float]) -> str:
    lo = units_min if units_min is not None else units_max
    hi = units_max if units_max is not None else units_min
    if lo is None or hi is None:
        return "? cr"

    def _f(v: float) -> str:
        return str(int(v)) if v.is_integer() else f"{v:g}"

    return f"{_f(lo)} cr" if lo == hi else f"{_f(lo)}–{_f(hi)} cr"


def parse_ilr_codes_from_attrs(crse_attrs: Any) -> list[str]:
    """Extract sorted canonical '-IL' distribution codes from courses_meta.crse_attrs_json."""
    items = _safe_json_loads(crse_attrs, [])
    if not isinstance(items, list):
        return []

    found: set[str] = set()
    for entry in items:
        if isinstance(entry, dict):
            raw_vals = f"{entry.get('crseAttrValues') or ''} {entry.get('attrDescr') or ''}"
        else:
            raw_vals = str(entry or "")
        for m in _IL_CODE_RE.findall(raw_vals.upper()):
            found.add(m)

    if not found:
        return []

    order_index = {code: idx for idx, code in enumerate(ILR_REQUIREMENT_ORDER)}
    return sorted(found, key=lambda c: (order_index.get(c, 999), c))


def _extract_crosslist_codes(crosslists_json: Any) -> list[str]:
    items = _safe_json_loads(crosslists_json, [])
    if not isinstance(items, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        if isinstance(item, dict):
            code = normalize_course_code(
                f"{item.get('subject') or ''} {item.get('catalogNbr') or item.get('catalog_nbr') or ''}"
            )
        else:
            code = normalize_course_code(str(item or ""))
        if code and code not in seen:
            seen.add(code)
            out.append(code)
    return out


def _normalize_filter_codes(filter_codes: Sequence[str]) -> tuple[bool, list[str]]:
    has_any_il = False
    explicit: list[str] = []
    seen: set[str] = set()
    for raw in filter_codes:
        token = raw.strip().upper()
        if not token:
            continue
        if token == "ANY_IL":
            has_any_il = True
            continue
        if token == "MAIN_3":
            for mc in ILR_MAIN_ELECTIVE_CODES:
                if mc not in seen:
                    seen.add(mc)
                    explicit.append(mc)
            continue
        if token not in seen:
            seen.add(token)
            explicit.append(token)
    return has_any_il, explicit


@dataclass(frozen=True)
class CourseILREligibility:
    course_code: str
    acad_career: str
    raw_ilr_codes: tuple[str, ...]
    codes: tuple[str, ...]
    main_electives: tuple[str, ...]
    distributions: tuple[str, ...]
    credit_pools: tuple[str, ...]
    is_ilr_core: bool
    warnings: tuple[str, ...] = field(default_factory=tuple)
    ug_crosslist_hints: tuple[str, ...] = field(default_factory=tuple)

    @property
    def requirement_count(self) -> int:
        return len(self.codes)

    @property
    def is_main_elective(self) -> bool:
        return bool(self.main_electives)

    def to_dict(self, active_filter_codes: Optional[set[str]] = None) -> dict[str, Any]:
        active = {c.upper() for c in active_filter_codes} if active_filter_codes else set()
        also_fits = [c for c in self.codes if c not in active] if active else list(self.codes)
        return {
            "qualifies_any": bool(self.codes),
            "codes": list(self.codes),
            "main_electives": list(self.main_electives),
            "distributions": list(self.distributions),
            "credit_pools": list(self.credit_pools),
            "is_main_elective": self.is_main_elective,
            "is_ilr_core": self.is_ilr_core,
            "requirement_count": self.requirement_count,
            "also_fits_codes": also_fits,
            "badges": [get_ilr_requirement_def(c).to_badge_dict() for c in self.codes],
            "warnings": list(self.warnings),
            "ug_crosslist_hints": list(self.ug_crosslist_hints),
        }


class ILRRequirementsIndex:
    """In-memory per-roster index mapping course codes to ILR curriculum eligibility."""

    def __init__(self, courses: Iterable[dict[str, Any]]) -> None:
        self.by_code: dict[str, CourseILREligibility] = {}
        self._crosslists_by_code: dict[str, list[str]] = {}
        self._build(courses)

    @classmethod
    def evaluate_course_row(
        cls,
        course: dict[str, Any],
        ug_crosslist_hints: tuple[str, ...] = (),
    ) -> CourseILREligibility:
        subject = str(course.get("subject") or "").strip().upper()
        catalog_nbr = str(course.get("catalog_nbr") or "").strip().upper()
        course_code = normalize_course_code(f"{subject} {catalog_nbr}")
        acad_career = str(course.get("acad_career") or "").strip().upper()
        raw_ilr_codes = parse_ilr_codes_from_attrs(
            course.get("crse_attrs_json") if "crse_attrs_json" in course else course.get("crse_attrs")
        )
        is_ilr_core = course_code in ILR_CORE_COURSES

        all_codes = list(raw_ilr_codes)
        if is_ilr_core and "ILR-CORE" not in all_codes:
            all_codes.append("ILR-CORE")

        order_index = {code: idx for idx, code in enumerate(ILR_REQUIREMENT_ORDER)}
        all_codes.sort(key=lambda c: (order_index.get(c, 999), c))

        main_electives = tuple(c for c in all_codes if c in ILR_MAIN_ELECTIVE_CODES)
        distributions = tuple(c for c in all_codes if c in _DISTRIBUTION_CODES)
        credit_pools = tuple(
            c for c in all_codes
            if c in _CREDIT_POOL_CODES
            or (c.endswith("-IL") and c not in ILR_MAIN_ELECTIVE_CODES and c not in _DISTRIBUTION_CODES)
        )

        warnings: list[str] = []
        if all_codes:
            has_letter = course.get("has_letter_grade")
            if has_letter is not None and not bool(has_letter):
                warnings.append("S/U Only — must take Letter Grade for ILR reqs")

            units_min = _to_float(course.get("units_min"))
            units_max = _to_float(course.get("units_max"))
            if (
                units_max is not None
                and units_max > 0
                and units_max < 3.0
                and any(get_ilr_requirement_def(c).requires_three_credits for c in all_codes)
            ):
                warnings.append(
                    f"< 3 cr ({_fmt_credits(units_min, units_max)}) — check 3–4 cr requirement minimum"
                )

            if acad_career and acad_career != "UG":
                warnings.append("Grad level — verify undergraduate ILR credit")

        return CourseILREligibility(
            course_code=course_code,
            acad_career=acad_career,
            raw_ilr_codes=tuple(raw_ilr_codes),
            codes=tuple(all_codes),
            main_electives=main_electives,
            distributions=distributions,
            credit_pools=credit_pools,
            is_ilr_core=is_ilr_core,
            warnings=tuple(warnings),
            ug_crosslist_hints=ug_crosslist_hints,
        )

    def _build(self, courses: Iterable[dict[str, Any]]) -> None:
        raw_rows: list[dict[str, Any]] = []
        for row in courses:
            raw_rows.append(row)
            elig = self.evaluate_course_row(row)
            if not elig.course_code:
                continue
            self.by_code[elig.course_code] = elig
            self._crosslists_by_code[elig.course_code] = _extract_crosslist_codes(
                row.get("crosslists_json") if "crosslists_json" in row else row.get("crosslists")
            )

        # Pass 2: never copy UG -IL attributes onto grad siblings, only surface a helpful hint.
        for code, elig in list(self.by_code.items()):
            if elig.raw_ilr_codes:
                continue
            cross_codes = self._crosslists_by_code.get(code, [])
            if not cross_codes:
                continue
            hints: list[str] = []
            for sib_code in cross_codes:
                if sib_code == code:
                    continue
                sib = self.by_code.get(sib_code)
                if sib is None or not sib.raw_ilr_codes:
                    continue
                if elig.acad_career != "UG" and sib.acad_career == "UG":
                    hints.append(
                        f"UG cross-list {sib_code} carries {', '.join(sib.raw_ilr_codes)} "
                        "— enroll in UG number for ILR credit."
                    )
                elif sib.acad_career == "UG":
                    hints.append(
                        f"Cross-list {sib_code} carries {', '.join(sib.raw_ilr_codes)} "
                        f"— enroll in {sib_code} if seeking ILR distribution credit."
                    )
            if hints:
                self.by_code[code] = CourseILREligibility(
                    course_code=elig.course_code,
                    acad_career=elig.acad_career,
                    raw_ilr_codes=elig.raw_ilr_codes,
                    codes=elig.codes,
                    main_electives=elig.main_electives,
                    distributions=elig.distributions,
                    credit_pools=elig.credit_pools,
                    is_ilr_core=elig.is_ilr_core,
                    warnings=elig.warnings,
                    ug_crosslist_hints=tuple(hints),
                )

    def get(self, subject: str, catalog_nbr: str) -> Optional[CourseILREligibility]:
        return self.by_code.get(normalize_course_code(f"{subject} {catalog_nbr}"))

    @staticmethod
    def matches_filter(
        elig: CourseILREligibility,
        filter_codes: Sequence[str],
        match_mode: str = "any",
        ilr_multi_only: bool = False,
    ) -> bool:
        if ilr_multi_only and elig.requirement_count < 2:
            return False

        has_any_il, explicit = _normalize_filter_codes(filter_codes)
        if not has_any_il and not explicit:
            return True if ilr_multi_only else bool(elig.codes)

        has_il_tag = any(c.endswith("-IL") for c in elig.codes)
        if has_any_il and not explicit:
            return has_il_tag

        mode = match_mode.strip().lower()
        if mode == "all":
            if has_any_il and not has_il_tag:
                return False
            return all(code in elig.codes for code in explicit)

        if has_any_il and has_il_tag:
            return True
        return any(code in elig.codes for code in explicit)

    def build_summary(
        self,
        course_status_map: dict[str, tuple[str, bool]],
    ) -> dict[str, Any]:
        """Aggregate per-requirement course availability across location-eligible courses.

        course_status_map maps canonical course_code -> (status, is_fresh)
        where status is 'open' | 'waitlist' | 'closed'.
        """
        extra_codes = sorted(
            {
                c
                for code in course_status_map
                if (elig := self.by_code.get(code)) is not None
                for c in elig.codes
                if c not in ILR_REQUIREMENT_ORDER
            }
        )
        ordered_codes = [*ILR_REQUIREMENT_ORDER, *extra_codes]

        def _empty_bucket() -> dict[str, int]:
            return {"total": 0, "open": 0, "waitlist": 0, "closed": 0, "stale": 0}

        buckets: dict[str, dict[str, int]] = {c: _empty_bucket() for c in ordered_codes}
        all_il = _empty_bucket()
        main_three = _empty_bucket()
        multi_req = _empty_bucket()

        def _bump(bucket: dict[str, int], status: str, is_fresh: bool) -> None:
            bucket["total"] += 1
            if status == "open":
                bucket["open"] += 1
            elif status == "waitlist":
                bucket["waitlist"] += 1
            else:
                bucket["closed"] += 1
            if not is_fresh:
                bucket["stale"] += 1

        for course_code, (status, is_fresh) in course_status_map.items():
            elig = self.by_code.get(course_code)
            if elig is None or not elig.codes:
                continue
            for req_code in elig.codes:
                _bump(buckets[req_code], status, is_fresh)
            if any(c.endswith("-IL") for c in elig.codes):
                _bump(all_il, status, is_fresh)
            if elig.main_electives:
                _bump(main_three, status, is_fresh)
            if elig.requirement_count >= 2:
                _bump(multi_req, status, is_fresh)

        requirements = []
        for req_code in ordered_codes:
            defn = get_ilr_requirement_def(req_code)
            requirements.append(
                {
                    **defn.to_badge_dict(),
                    "requires_three_credits": defn.requires_three_credits,
                    **buckets[req_code],
                }
            )

        return {
            "requirements": requirements,
            "presets": {
                "all_il": all_il,
                "main_three": main_three,
                "ilr_core": dict(buckets["ILR-CORE"]),
                "multi_req": multi_req,
            },
            "curriculum_url": ILR_CURRICULUM_URL,
        }
