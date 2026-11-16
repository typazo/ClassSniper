import type {
  CourseSection,
  CourseSummary,
  DayCode,
  HydratedSchedule,
  ScheduleBlock,
  ScheduleCourseItem,
  ScheduleSection,
} from "../types";
import { analyzeDayTransitions, type WalkTransitionWarning } from "./cornellBuildings";

export interface CourseColorStyle {
  name: string;
  bg: string;
  border: string;
  text: string;
  dot: string;
  ghostBg: string;
}

export const COURSE_COLORS: CourseColorStyle[] = [
  {
    name: "Emerald",
    bg: "bg-emerald-500/20",
    border: "border-emerald-400/50",
    text: "text-emerald-100",
    dot: "bg-emerald-400",
    ghostBg: "bg-emerald-400/15",
  },
  {
    name: "Sky",
    bg: "bg-sky-500/20",
    border: "border-sky-400/50",
    text: "text-sky-100",
    dot: "bg-sky-400",
    ghostBg: "bg-sky-400/15",
  },
  {
    name: "Violet",
    bg: "bg-violet-500/20",
    border: "border-violet-400/50",
    text: "text-violet-100",
    dot: "bg-violet-400",
    ghostBg: "bg-violet-400/15",
  },
  {
    name: "Amber",
    bg: "bg-amber-500/20",
    border: "border-amber-400/50",
    text: "text-amber-100",
    dot: "bg-amber-400",
    ghostBg: "bg-amber-400/15",
  },
  {
    name: "Rose",
    bg: "bg-rose-500/20",
    border: "border-rose-400/50",
    text: "text-rose-100",
    dot: "bg-rose-400",
    ghostBg: "bg-rose-400/15",
  },
  {
    name: "Cyan",
    bg: "bg-cyan-500/20",
    border: "border-cyan-400/50",
    text: "text-cyan-100",
    dot: "bg-cyan-400",
    ghostBg: "bg-cyan-400/15",
  },
  {
    name: "Indigo",
    bg: "bg-indigo-500/20",
    border: "border-indigo-400/50",
    text: "text-indigo-100",
    dot: "bg-indigo-400",
    ghostBg: "bg-indigo-400/15",
  },
  {
    name: "Fuchsia",
    bg: "bg-fuchsia-500/20",
    border: "border-fuchsia-400/50",
    text: "text-fuchsia-100",
    dot: "bg-fuchsia-400",
    ghostBg: "bg-fuchsia-400/15",
  },
  {
    name: "Teal",
    bg: "bg-teal-500/20",
    border: "border-teal-400/50",
    text: "text-teal-100",
    dot: "bg-teal-400",
    ghostBg: "bg-teal-400/15",
  },
  {
    name: "Orange",
    bg: "bg-orange-500/20",
    border: "border-orange-400/50",
    text: "text-orange-100",
    dot: "bg-orange-400",
    ghostBg: "bg-orange-400/15",
  },
];

export function getCourseColor(colorIdx: number): CourseColorStyle {
  const idx = ((colorIdx % COURSE_COLORS.length) + COURSE_COLORS.length) % COURSE_COLORS.length;
  return COURSE_COLORS[idx];
}

export const WEEKDAY_ORDER: DayCode[] = ["M", "T", "W", "R", "F"];
export const ALL_DAYS_ORDER: DayCode[] = ["M", "T", "W", "R", "F", "Sa", "Su"];

export function getCourseEffectiveUnits(course: ScheduleCourseItem): number {
  if (course.selected_units != null && course.selected_units > 0) {
    return course.selected_units;
  }
  if (course.units_max > 0) return course.units_max;
  if (course.units_min > 0) return course.units_min;
  return 0;
}

export function formatMinutesShort(totalMin: number): string {
  const h24 = Math.floor(totalMin / 60);
  const m = totalMin % 60;
  const suffix = h24 >= 12 ? "p" : "a";
  const h12 = h24 % 12 === 0 ? 12 : h24 % 12;
  return m === 0 ? `${h12}${suffix}` : `${h12}:${String(m).padStart(2, "0")}${suffix}`;
}

export function formatMinutesFull(totalMin: number): string {
  const h24 = Math.floor(totalMin / 60);
  const m = totalMin % 60;
  const suffix = h24 >= 12 ? "PM" : "AM";
  const h12 = h24 % 12 === 0 ? 12 : h24 % 12;
  return `${h12}:${String(m).padStart(2, "0")} ${suffix}`;
}

export interface TimeSlot {
  day: DayCode;
  start_min: number;
  end_min: number;
  facility_descr?: string;
  building_descr?: string;
  courseLabel: string;
}

export function extractSectionSlots(courseLabel: string, sec: ScheduleSection): TimeSlot[] {
  const slots: TimeSlot[] = [];
  const seen = new Set<string>();
  for (const mtg of sec.meetings) {
    if (mtg.end_min <= mtg.start_min) continue;
    for (const day of mtg.days) {
      // Cornell sometimes repeats the same weekly slot across multiple date-split meetings
      const key = `${day}|${mtg.start_min}|${mtg.end_min}`;
      if (seen.has(key)) continue;
      seen.add(key);
      slots.push({
        day,
        start_min: mtg.start_min,
        end_min: mtg.end_min,
        facility_descr: mtg.facility_descr,
        building_descr: mtg.building_descr,
        courseLabel,
      });
    }
  }
  return slots;
}

export function slotsOverlap(a: TimeSlot, b: TimeSlot): boolean {
  return a.day === b.day && a.start_min < b.end_min && a.end_min > b.start_min;
}

export function sectionOverlapsSlots(sec: ScheduleSection, targetSlots: TimeSlot[]): boolean {
  for (const mtg of sec.meetings) {
    for (const day of mtg.days) {
      for (const s of targetSlots) {
        if (s.day === day && mtg.start_min < s.end_min && mtg.end_min > s.start_min) {
          return true;
        }
      }
    }
  }
  return false;
}

export interface ScheduleDiagnostics {
  conflictCount: number;
  conflictingClassNbrs: Set<number>;
  conflictingBlockIds: Set<number>;
  conflictMessages: string[];
  walkWarnings: WalkTransitionWarning[];
  academicWarnings: string[];
  totalCredits: number;
  closedSelectedCount: number;
  waitlistSelectedCount: number;
}

export function getSelectedSections(course: ScheduleCourseItem): ScheduleSection[] {
  const selected = new Set(course.selected_class_nbrs);
  const out: ScheduleSection[] = [];
  for (const eg of course.enroll_groups) {
    for (const sec of eg.sections) {
      if (selected.has(sec.class_nbr)) {
        out.push(sec);
      }
    }
  }
  return out;
}

export function computeScheduleDiagnostics(
  courses: ScheduleCourseItem[],
  blocks: ScheduleBlock[]
): ScheduleDiagnostics {
  const activeCourses = courses.filter((c) => c.enabled);
  const activeBlocks = blocks.filter((b) => b.enabled);

  interface PlacedSlot extends TimeSlot {
    kind: "course" | "block";
    classNbr?: number;
    blockId?: number;
    label: string;
  }

  const allSlots: PlacedSlot[] = [];
  let totalCredits = 0;
  let closedSelectedCount = 0;
  let waitlistSelectedCount = 0;

  for (const course of activeCourses) {
    totalCredits += getCourseEffectiveUnits(course);

    const secs = getSelectedSections(course);
    for (const sec of secs) {
      if (sec.open_status === "C") closedSelectedCount += 1;
      else if (sec.open_status === "W") waitlistSelectedCount += 1;

      const label = `${course.subject} ${course.catalog_nbr} ${sec.ssr_component} ${sec.section}`;
      for (const sl of extractSectionSlots(`${course.subject} ${course.catalog_nbr}`, sec)) {
        allSlots.push({
          ...sl,
          kind: "course",
          classNbr: sec.class_nbr,
          label,
        });
      }
    }
  }

  for (const blk of activeBlocks) {
    for (const day of blk.days) {
      allSlots.push({
        kind: "block",
        blockId: blk.id,
        label: `Busy: ${blk.label}`,
        courseLabel: blk.label,
        day,
        start_min: blk.start_min,
        end_min: blk.end_min,
      });
    }
  }

  const conflictingClassNbrs = new Set<number>();
  const conflictingBlockIds = new Set<number>();
  const conflictPairs = new Set<string>();
  const conflictMessages: string[] = [];

  for (let i = 0; i < allSlots.length; i += 1) {
    for (let j = i + 1; j < allSlots.length; j += 1) {
      const a = allSlots[i];
      const b = allSlots[j];
      if (!slotsOverlap(a, b)) continue;
      if (a.kind === "block" && b.kind === "block") continue;
      if (a.kind === "course" && b.kind === "course" && a.classNbr === b.classNbr) continue;

      if (a.classNbr != null) conflictingClassNbrs.add(a.classNbr);
      if (b.classNbr != null) conflictingClassNbrs.add(b.classNbr);
      if (a.blockId != null) conflictingBlockIds.add(a.blockId);
      if (b.blockId != null) conflictingBlockIds.add(b.blockId);

      const pairKey = [a.label, b.label, a.day].sort().join("|");
      if (!conflictPairs.has(pairKey)) {
        conflictPairs.add(pairKey);
        conflictMessages.push(`${a.day}: ${a.label} overlaps ${b.label}`);
      }
    }
  }

  // Walking time analysis per day across course meetings only
  const walkWarnings: WalkTransitionWarning[] = [];
  for (const day of ALL_DAYS_ORDER) {
    const dayCourseSlots = allSlots
      .filter((s) => s.kind === "course" && s.day === day)
      .map((s) => ({
        startMin: s.start_min,
        endMin: s.end_min,
        courseLabel: s.courseLabel,
        facilityDescr: s.facility_descr,
        buildingDescr: s.building_descr,
      }));
    walkWarnings.push(...analyzeDayTransitions(day, dayCourseSlots));
  }

  // Forbidden overlaps & crosslist duplicates
  const academicWarnings: string[] = [];
  const activeCodes = activeCourses.map((c) => `${c.subject} ${c.catalog_nbr}`);
  const seenCrossCheck = new Set<string>();

  for (let i = 0; i < activeCourses.length; i += 1) {
    const c = activeCourses[i];
    const code = `${c.subject} ${c.catalog_nbr}`;
    const overlapText = (c.catalog_forbidden_overlaps || "").toUpperCase();
    for (let j = 0; j < activeCourses.length; j += 1) {
      if (i === j) continue;
      const other = activeCourses[j];
      const otherCode = `${other.subject} ${other.catalog_nbr}`;
      if (c.crosslists.includes(otherCode) && code < otherCode) {
        academicWarnings.push(`${code} and ${otherCode} are cross-listed versions of the same course.`);
      }
      if (overlapText && (overlapText.includes(otherCode) || overlapText.includes(`${other.subject}${other.catalog_nbr}`))) {
        const key = [code, otherCode].sort().join("|");
        if (!seenCrossCheck.has(key)) {
          seenCrossCheck.add(key);
          academicWarnings.push(
            `Forbidden overlap warning: ${code} notes overlap restrictions mentioning ${otherCode}.`
          );
        }
      }
    }

    if (c.catalog_coreq) {
      const coreqUpper = c.catalog_coreq.toUpperCase();
      const mentions = coreqUpper.match(/\b[A-Z]{2,6}\s+\d{4}[A-Z]?\b/g) || [];
      if (mentions.length > 0 && !mentions.some((m) => activeCodes.includes(m.replace(/\s+/, " ")))) {
        academicWarnings.push(`Corequisite reminder for ${code}: ${c.catalog_coreq}`);
      }
    }
  }

  return {
    conflictCount: conflictMessages.length,
    conflictingClassNbrs,
    conflictingBlockIds,
    conflictMessages,
    walkWarnings,
    academicWarnings,
    totalCredits: Math.round(totalCredits * 100) / 100,
    closedSelectedCount,
    waitlistSelectedCount,
  };
}

export type SolverSeatMode = "open" | "open_or_waitlist" | "all";
export type SolverRankMode = "compact" | "spread" | "late_start" | "early_end" | "fewest_closed";

export interface SectionTupleOption {
  courseItemId: number;
  subject: string;
  catalogNbr: string;
  enrollGroupIdx: number;
  sections: ScheduleSection[];
  slots: TimeSlot[];
  closedCount: number;
  waitlistCount: number;
  timeSignature: string;
}

function sectionPassesSeatMode(
  sec: ScheduleSection,
  seatMode: SolverSeatMode,
  lockedSet: Set<number>
): boolean {
  if (lockedSet.has(sec.class_nbr)) return true;
  if (seatMode === "all") return true;
  if (seatMode === "open_or_waitlist") return sec.open_status === "O" || sec.open_status === "W";
  return sec.open_status === "O";
}

function buildSectionTuplesForCourse(
  course: ScheduleCourseItem,
  seatMode: SolverSeatMode,
  ithacaOrVirtualOnly: boolean,
  dedupeIdenticalTimes: boolean
): SectionTupleOption[] {
  const lockedSet = new Set(course.locked_class_nbrs);
  const tuples: SectionTupleOption[] = [];
  const label = `${course.subject} ${course.catalog_nbr}`;

  for (const eg of course.enroll_groups) {
    const egSecs = eg.sections.filter(
      (s) =>
        (lockedSet.has(s.class_nbr) || !ithacaOrVirtualOnly || s.is_ithaca_or_virtual) &&
        sectionPassesSeatMode(s, seatMode, lockedSet)
    );
    if (egSecs.length === 0) continue;

    // Ensure every locked section in this course belongs to this enrollGroup if this enrollGroup is used
    const allSectionNbrsInEg = new Set(eg.sections.map((s) => s.class_nbr));
    if (course.locked_class_nbrs.some((ln) => !allSectionNbrsInEg.has(ln))) {
      continue;
    }

    const reqComps =
      eg.components_required.length > 0
        ? eg.components_required
        : Array.from(new Set(egSecs.map((s) => s.ssr_component).filter(Boolean)));

    const buckets: ScheduleSection[][] = [];
    let impossible = false;
    for (const comp of reqComps) {
      let matching = egSecs.filter((s) => s.ssr_component === comp);
      const lockedInComp = matching.filter((s) => lockedSet.has(s.class_nbr));
      if (lockedInComp.length > 0) {
        matching = lockedInComp;
      }
      if (matching.length === 0) {
        impossible = true;
        break;
      }
      // Sort open sections first so pruning/dedup preserves best availability
      matching.sort((a, b) => {
        const rankA = a.open_status === "O" ? 0 : a.open_status === "W" ? 1 : 2;
        const rankB = b.open_status === "O" ? 0 : b.open_status === "W" ? 1 : 2;
        return rankA - rankB || a.class_nbr - b.class_nbr;
      });
      buckets.push(matching);
    }
    if (impossible || buckets.length === 0) continue;

    // Cartesian product across required components within this enrollGroup
    const current: ScheduleSection[] = [];
    const MAX_PER_EG = 80;
    let countInEg = 0;

    const combine = (idx: number) => {
      if (countInEg >= MAX_PER_EG) return;
      if (idx === buckets.length) {
        const chosen = [...current];
        const slots: TimeSlot[] = [];
        let selfConflict = false;
        for (const sec of chosen) {
          const secSlots = extractSectionSlots(label, sec);
          // Only flag overlaps across distinct components of the same course (not date-split meetings within one section)
          if (secSlots.some((ns) => slots.some((existing) => slotsOverlap(existing, ns)))) {
            selfConflict = true;
            break;
          }
          slots.push(...secSlots);
        }
        if (selfConflict) return;

        const sig = slots
          .map((s) => `${s.day}:${s.start_min}-${s.end_min}`)
          .sort()
          .join(",");
        tuples.push({
          courseItemId: course.id,
          subject: course.subject,
          catalogNbr: course.catalog_nbr,
          enrollGroupIdx: eg.enroll_group_idx,
          sections: chosen,
          slots,
          closedCount: chosen.filter((s) => s.open_status === "C").length,
          waitlistCount: chosen.filter((s) => s.open_status === "W").length,
          timeSignature: sig || `TBA-${eg.enroll_group_idx}-${chosen.map((s) => s.class_nbr).join("-")}`,
        });
        countInEg += 1;
        return;
      }

      for (const sec of buckets[idx]) {
        current.push(sec);
        combine(idx + 1);
        current.pop();
        if (countInEg >= MAX_PER_EG) break;
      }
    };
    combine(0);
  }

  if (!dedupeIdenticalTimes) return tuples;

  // Keep best-status variant per identical time signature
  const bestBySig = new Map<string, SectionTupleOption>();
  for (const t of tuples) {
    const prev = bestBySig.get(t.timeSignature);
    if (!prev) {
      bestBySig.set(t.timeSignature, t);
      continue;
    }
    const tPenalty = t.closedCount * 10 + t.waitlistCount;
    const prevPenalty = prev.closedCount * 10 + prev.waitlistCount;
    if (tPenalty < prevPenalty) {
      bestBySig.set(t.timeSignature, t);
    }
  }
  return Array.from(bestBySig.values());
}

export interface CompatibleSectionsResult {
  compatibleClassNbrs: Set<number>;
  directConflictClassNbrs: Set<number>;
}

export function findCompatibleSectionsForCourse(
  targetCourse: ScheduleCourseItem,
  allCourses: ScheduleCourseItem[],
  blocks: ScheduleBlock[]
): CompatibleSectionsResult {
  const fixedSlots: TimeSlot[] = [];
  for (const c of allCourses) {
    if (!c.enabled || c.id === targetCourse.id) continue;
    for (const sec of getSelectedSections(c)) {
      fixedSlots.push(...extractSectionSlots(`${c.subject} ${c.catalog_nbr}`, sec));
    }
  }
  for (const blk of blocks) {
    if (!blk.enabled) continue;
    for (const day of blk.days) {
      fixedSlots.push({
        day,
        start_min: blk.start_min,
        end_min: blk.end_min,
        courseLabel: blk.label,
      });
    }
  }

  const directConflictClassNbrs = new Set<number>();
  for (const eg of targetCourse.enroll_groups) {
    for (const sec of eg.sections) {
      if (sectionOverlapsSlots(sec, fixedSlots)) {
        directConflictClassNbrs.add(sec.class_nbr);
      }
    }
  }

  const compatibleClassNbrs = new Set<number>();
  const allTuples = buildSectionTuplesForCourse(targetCourse, "all", false, false);
  for (const t of allTuples) {
    const conflicts = t.slots.some((s) => fixedSlots.some((f) => slotsOverlap(s, f)));
    if (!conflicts) {
      for (const sec of t.sections) {
        compatibleClassNbrs.add(sec.class_nbr);
      }
    }
  }

  return { compatibleClassNbrs, directConflictClassNbrs };
}

export interface GeneratedScheduleCandidate {
  id: string;
  selections: Array<{
    item_id: number;
    subject: string;
    catalog_nbr: string;
    selected_class_nbrs: number[];
    sections: ScheduleSection[];
  }>;
  closedCount: number;
  waitlistCount: number;
  openCount: number;
  tightWalkCount: number;
  totalGapMin: number;
  avgStartMin: number;
  latestEndMin: number;
  score: number;
}

export interface SolveScheduleResult {
  candidates: GeneratedScheduleCandidate[];
  totalFound: number;
  truncated: boolean;
  elapsedMs: number;
  blockingIssue: string | null;
}

export function solveSchedules(
  courses: ScheduleCourseItem[],
  blocks: ScheduleBlock[],
  options: {
    seatMode: SolverSeatMode;
    rankMode: SolverRankMode;
    ithacaOrVirtualOnly: boolean;
    avoidTightWalks: boolean;
    maxResults?: number;
  }
): SolveScheduleResult {
  const started = performance.now();
  const maxResults = options.maxResults ?? 40;
  const activeCourses = courses.filter((c) => c.enabled);

  if (activeCourses.length === 0) {
    return {
      candidates: [],
      totalFound: 0,
      truncated: false,
      elapsedMs: 0,
      blockingIssue: "Enable at least one course in your schedule to generate combinations.",
    };
  }

  const blockSlots: TimeSlot[] = [];
  for (const blk of blocks) {
    if (!blk.enabled) continue;
    for (const day of blk.days) {
      blockSlots.push({
        day,
        start_min: blk.start_min,
        end_min: blk.end_min,
        courseLabel: blk.label,
      });
    }
  }

  // Build candidate tuples for each course and filter against busy blocks up front
  const tuplesByCourse: SectionTupleOption[][] = [];
  for (const course of activeCourses) {
    const rawTuples = buildSectionTuplesForCourse(
      course,
      options.seatMode,
      options.ithacaOrVirtualOnly,
      true
    );
    if (rawTuples.length === 0) {
      return {
        candidates: [],
        totalFound: 0,
        truncated: false,
        elapsedMs: Math.round(performance.now() - started),
        blockingIssue: `No valid ${
          options.seatMode === "open"
            ? "open "
            : options.seatMode === "open_or_waitlist"
              ? "open/waitlist "
              : ""
        }sections found for ${course.subject} ${course.catalog_nbr} (check locks or seat filter).`,
      };
    }

    const nonBlocked = rawTuples.filter(
      (t) => !t.slots.some((s) => blockSlots.some((b) => slotsOverlap(s, b)))
    );
    if (nonBlocked.length === 0) {
      return {
        candidates: [],
        totalFound: 0,
        truncated: false,
        elapsedMs: Math.round(performance.now() - started),
        blockingIssue: `Every valid option for ${course.subject} ${course.catalog_nbr} overlaps a Busy Time block.`,
      };
    }
    tuplesByCourse.push(nonBlocked);
  }

  // Order most constrained courses first for fast pruning
  tuplesByCourse.sort((a, b) => a.length - b.length);

  const MAX_NODES = 150000;
  const MAX_TIME_MS = 250;
  let nodes = 0;
  let truncated = false;
  let totalFound = 0;
  const collected: GeneratedScheduleCandidate[] = [];
  const chosen: SectionTupleOption[] = [];
  const placedSlots: TimeSlot[] = [];

  const scoreAndBuild = (tuples: SectionTupleOption[]): GeneratedScheduleCandidate | null => {
    let totalGapMin = 0;
    let maxContinuousMin = 0;
    let tightWalkCount = 0;
    const dayStarts: number[] = [];
    let latestEndMin = 0;

    for (const day of ALL_DAYS_ORDER) {
      const daySlots = placedSlots
        .filter((s) => s.day === day)
        .sort((a, b) => a.start_min - b.start_min);
      if (daySlots.length === 0) continue;

      dayStarts.push(daySlots[0].start_min);
      latestEndMin = Math.max(latestEndMin, daySlots[daySlots.length - 1].end_min);

      let streak = daySlots[0].end_min - daySlots[0].start_min;
      for (let i = 0; i < daySlots.length - 1; i += 1) {
        const gap = daySlots[i + 1].start_min - daySlots[i].end_min;
        if (gap > 0) totalGapMin += gap;
        if (gap <= 20) {
          streak += Math.max(0, gap) + (daySlots[i + 1].end_min - daySlots[i + 1].start_min);
        } else {
          maxContinuousMin = Math.max(maxContinuousMin, streak);
          streak = daySlots[i + 1].end_min - daySlots[i + 1].start_min;
        }
      }
      maxContinuousMin = Math.max(maxContinuousMin, streak);

      const walks = analyzeDayTransitions(
        day,
        daySlots.map((s) => ({
          startMin: s.start_min,
          endMin: s.end_min,
          courseLabel: s.courseLabel,
          facilityDescr: s.facility_descr,
          buildingDescr: s.building_descr,
        }))
      );
      tightWalkCount += walks.length;
    }

    if (options.avoidTightWalks && tightWalkCount > 0) {
      return null;
    }

    let closedCount = 0;
    let waitlistCount = 0;
    let openCount = 0;
    for (const t of tuples) {
      closedCount += t.closedCount;
      waitlistCount += t.waitlistCount;
      openCount += t.sections.length - t.closedCount - t.waitlistCount;
    }

    const avgStartMin =
      dayStarts.length > 0
        ? Math.round(dayStarts.reduce((acc, v) => acc + v, 0) / dayStarts.length)
        : 600;

    // Lower score is better
    let score = 0;
    switch (options.rankMode) {
      case "compact":
        score = totalGapMin + tightWalkCount * 40 + closedCount * 20;
        break;
      case "spread":
        score =
          Math.max(0, maxContinuousMin - 130) * 4 -
          Math.min(totalGapMin, 300) * 0.4 +
          tightWalkCount * 60 +
          closedCount * 20;
        break;
      case "late_start":
        score = -avgStartMin * 2 + totalGapMin * 0.25 + closedCount * 15;
        break;
      case "early_end":
        score = latestEndMin * 2 + totalGapMin * 0.25 + closedCount * 15;
        break;
      case "fewest_closed":
        score = closedCount * 1000 + waitlistCount * 120 + totalGapMin * 0.2 + tightWalkCount * 25;
        break;
    }

    const selections = tuples
      .map((t) => ({
        item_id: t.courseItemId,
        subject: t.subject,
        catalog_nbr: t.catalogNbr,
        selected_class_nbrs: t.sections.map((s) => s.class_nbr),
        sections: t.sections,
      }))
      .sort((a, b) => `${a.subject} ${a.catalog_nbr}`.localeCompare(`${b.subject} ${b.catalog_nbr}`));

    return {
      id: selections.map((s) => `${s.item_id}:${s.selected_class_nbrs.join(",")}`).join("|"),
      selections,
      closedCount,
      waitlistCount,
      openCount,
      tightWalkCount,
      totalGapMin,
      avgStartMin,
      latestEndMin,
      score,
    };
  };

  const dfs = (courseIdx: number) => {
    if (truncated) return;
    nodes += 1;
    if (nodes > MAX_NODES || (nodes % 500 === 0 && performance.now() - started > MAX_TIME_MS)) {
      truncated = true;
      return;
    }

    if (courseIdx === tuplesByCourse.length) {
      const candidate = scoreAndBuild(chosen);
      if (candidate) {
        totalFound += 1;
        collected.push(candidate);
        if (collected.length > 600) {
          collected.sort((a, b) => a.score - b.score);
          collected.length = maxResults * 3;
        }
      }
      return;
    }

    const optionsForCourse = tuplesByCourse[courseIdx];
    for (const tuple of optionsForCourse) {
      let overlaps = false;
      for (const ns of tuple.slots) {
        for (const ps of placedSlots) {
          if (slotsOverlap(ns, ps)) {
            overlaps = true;
            break;
          }
        }
        if (overlaps) break;
      }
      if (overlaps) continue;

      chosen.push(tuple);
      for (const ns of tuple.slots) placedSlots.push(ns);
      dfs(courseIdx + 1);
      placedSlots.length -= tuple.slots.length;
      chosen.pop();
      if (truncated) return;
    }
  };

  dfs(0);
  collected.sort((a, b) => a.score - b.score);
  const candidates = collected.slice(0, maxResults);

  let blockingIssue: string | null = null;
  if (candidates.length === 0) {
    blockingIssue = options.avoidTightWalks
      ? "No conflict-free combinations exist without tight campus walks. Try turning off 'Avoid tight walks' or adding more section options."
      : "No conflict-free combinations exist across these courses and Busy Time blocks.";
  }

  return {
    candidates,
    totalFound,
    truncated,
    elapsedMs: Math.round(performance.now() - started),
    blockingIssue,
  };
}

export interface SimpleSlot {
  day: DayCode;
  startMin: number;
  endMin: number;
}

function parseClockMinutes(raw: string): number | null {
  const m = raw.trim().match(/^(\d{1,2}):(\d{2})\s*(AM|PM)$/i);
  if (!m) return null;
  let hh = Number(m[1]);
  const mm = Number(m[2]);
  const mer = m[3].toUpperCase();
  if (mer === "AM" && hh === 12) hh = 0;
  else if (mer === "PM" && hh !== 12) hh += 12;
  return hh * 60 + mm;
}

function parsePatternDays(pattern: string): DayCode[] {
  const days: DayCode[] = [];
  let i = 0;
  const p = pattern.trim();
  while (i < p.length) {
    const two = p.slice(i, i + 2);
    if (two === "Sa" || two === "Su") {
      days.push(two);
      i += 2;
      continue;
    }
    const ch = p[i];
    if (ch === "M" || ch === "T" || ch === "W" || ch === "R" || ch === "F") {
      days.push(ch);
    }
    i += 1;
  }
  return days;
}

export function parseMeetingsSummaryToSlots(summary: string): SimpleSlot[] {
  if (!summary || summary.trim().toUpperCase() === "TBA") return [];
  const slots: SimpleSlot[] = [];
  const seen = new Set<string>();
  for (const part of summary.split(";")) {
    const m = part
      .trim()
      .match(/^([MTWRFSau]+)\s+(\d{1,2}:\d{2}\s*(?:AM|PM))-(\d{1,2}:\d{2}\s*(?:AM|PM))/i);
    if (!m) continue;
    const days = parsePatternDays(m[1]);
    const startMin = parseClockMinutes(m[2]);
    const endMin = parseClockMinutes(m[3]);
    if (startMin === null || endMin === null || endMin <= startMin) continue;
    for (const day of days) {
      const key = `${day}|${startMin}|${endMin}`;
      if (seen.has(key)) continue;
      seen.add(key);
      slots.push({ day, startMin, endMin });
    }
  }
  return slots;
}

function simpleSlotsOverlap(a: SimpleSlot, b: SimpleSlot): boolean {
  return a.day === b.day && a.startMin < b.endMin && b.startMin < a.endMin;
}

export function buildScheduleOccupiedIntervals(
  schedule: HydratedSchedule | null | undefined,
  excludeCourseKey?: string
): SimpleSlot[] {
  if (!schedule) return [];
  const occupied: SimpleSlot[] = [];
  for (const blk of schedule.blocks) {
    if (!blk.enabled) continue;
    for (const day of blk.days) {
      occupied.push({ day, startMin: blk.start_min, endMin: blk.end_min });
    }
  }
  for (const c of schedule.courses) {
    if (!c.enabled) continue;
    const key = `${c.subject.toUpperCase()} ${c.catalog_nbr.toUpperCase()}`;
    if (excludeCourseKey && key === excludeCourseKey) continue;
    const chosenSet = new Set(c.selected_class_nbrs);
    for (const eg of c.enroll_groups) {
      for (const sec of eg.sections) {
        if (!chosenSet.has(sec.class_nbr)) continue;
        for (const sl of extractSectionSlots(key, sec)) {
          occupied.push({ day: sl.day, startMin: sl.start_min, endMin: sl.end_min });
        }
      }
    }
  }
  return occupied;
}

export function evaluateCourseFitsSchedule(
  course: CourseSummary,
  schedule: HydratedSchedule | null | undefined
): { fits: boolean; compatibleClassNbrs: Set<number> } {
  const compatibleClassNbrs = new Set<number>();
  if (!schedule) return { fits: true, compatibleClassNbrs };
  const courseKey = `${course.subject.toUpperCase()} ${course.catalog_nbr.toUpperCase()}`;
  const occupied = buildScheduleOccupiedIntervals(schedule, courseKey);

  // Check each enroll group separately
  const byGroup = new Map<number, CourseSection[]>();
  for (const s of course.sections) {
    const arr = byGroup.get(s.enroll_group_idx) || [];
    arr.push(s);
    byGroup.set(s.enroll_group_idx, arr);
  }

  let anyGroupFits = false;
  for (const secs of byGroup.values()) {
    const reqComps =
      secs[0]?.components_required && secs[0].components_required.length > 0
        ? secs[0].components_required
        : Array.from(new Set(secs.map((s) => s.ssr_component)));

    const secNonConflict: CourseSection[] = [];
    for (const sec of secs) {
      const secSlots = parseMeetingsSummaryToSlots(sec.meetings_summary);
      const hitsBusy = secSlots.some((ns) => occupied.some((os) => simpleSlotsOverlap(ns, os)));
      if (!hitsBusy) {
        secNonConflict.push(sec);
      }
    }

    // Group non-conflicting sections by component and see if every required comp has >=1 option
    const byComp = new Map<string, CourseSection[]>();
    for (const s of secNonConflict) {
      const list = byComp.get(s.ssr_component) || [];
      list.push(s);
      byComp.set(s.ssr_component, list);
    }

    const compArrays = reqComps.map((c) => byComp.get(c) || []);
    if (compArrays.some((a) => a.length === 0)) continue;

    // Quick backtracking check inside this enrollGroup so component selections don't conflict with each other
    const canPickTuple = (idx: number, pickedSlots: SimpleSlot[]): boolean => {
      if (idx === compArrays.length) return true;
      for (const sec of compArrays[idx]) {
        const sl = parseMeetingsSummaryToSlots(sec.meetings_summary);
        if (sl.some((a) => pickedSlots.some((b) => simpleSlotsOverlap(a, b)))) continue;
        if (canPickTuple(idx + 1, [...pickedSlots, ...sl])) return true;
      }
      return false;
    };

    if (canPickTuple(0, [])) {
      anyGroupFits = true;
      for (const s of secNonConflict) {
        compatibleClassNbrs.add(s.class_nbr);
      }
    }
  }

  return { fits: anyGroupFits, compatibleClassNbrs };
}

/** Compute updated selected_class_nbrs when choosing targetSection across same or different enrollGroups. */
export function selectSectionInCourse(
  course: ScheduleCourseItem,
  targetSection: ScheduleSection
): number[] {
  const targetEg = course.enroll_groups.find(
    (eg) => eg.enroll_group_idx === targetSection.enroll_group_idx
  );
  if (!targetEg) return [targetSection.class_nbr];

  const reqComps =
    targetEg.components_required.length > 0
      ? targetEg.components_required
      : Array.from(new Set(targetEg.sections.map((s) => s.ssr_component).filter(Boolean)));

  const egNbrMap = new Map<number, ScheduleSection>();
  for (const s of targetEg.sections) {
    egNbrMap.set(s.class_nbr, s);
  }

  // Keep any currently selected sections that already belong to targetEg for other components
  const byComp = new Map<string, number>();
  for (const nbr of course.selected_class_nbrs) {
    const existing = egNbrMap.get(nbr);
    if (existing && existing.ssr_component !== targetSection.ssr_component) {
      byComp.set(existing.ssr_component, existing.class_nbr);
    }
  }
  byComp.set(targetSection.ssr_component, targetSection.class_nbr);

  // Fill any missing required components in targetEg
  for (const comp of reqComps) {
    if (byComp.has(comp)) continue;
    const candidates = targetEg.sections
      .filter((s) => s.ssr_component === comp)
      .sort((a, b) => {
        const rA = a.open_status === "O" ? 0 : a.open_status === "W" ? 1 : 2;
        const rB = b.open_status === "O" ? 0 : b.open_status === "W" ? 1 : 2;
        return rA - rB || a.class_nbr - b.class_nbr;
      });
    if (candidates.length > 0) {
      byComp.set(comp, candidates[0].class_nbr);
    }
  }

  return Array.from(byComp.values());
}

/** Swap a section in a course while preserving any lock on the replaced component. */
export function swapSectionPreservingLocks(
  course: ScheduleCourseItem,
  targetSection: ScheduleSection
): { selected_class_nbrs: number[]; locked_class_nbrs: number[] } {
  const nextSelected = selectSectionInCourse(course, targetSection);
  const nextSelectedSet = new Set(nextSelected);
  const prevCompLocked = getSelectedSections(course).some(
    (s) =>
      s.ssr_component === targetSection.ssr_component &&
      course.locked_class_nbrs.includes(s.class_nbr)
  );
  const locked = new Set(
    course.locked_class_nbrs.filter((nbr) => nextSelectedSet.has(nbr))
  );
  if (prevCompLocked) {
    locked.add(targetSection.class_nbr);
  }
  return {
    selected_class_nbrs: nextSelected,
    locked_class_nbrs: Array.from(locked),
  };
}
