import type { ScheduleCourseItem } from "../types";

export interface CourseEffectiveMetrics {
  rating: number | null;
  difficulty: number | null;
  difficultySource: "cu" | "rmp" | null;
  workload: number | null;
  reviewCount: number;
}

export interface DifficultyTier {
  label: "Light" | "Moderate" | "Challenging" | "Very Hard";
  badgeClass: string;
  textClass: string;
}

export interface ScheduleInsightsSummary {
  enabledCount: number;
  ratedDifficultyCount: number;
  avgDifficulty: number | null;
  avgWorkload: number | null;
  avgRating: number | null;
  semesterLoadScore: number | null;
  semesterTier: DifficultyTier | null;
  difficultyTier: DifficultyTier | null;
}

export function getCourseEffectiveUnits(course: ScheduleCourseItem): number {
  if (course.selected_units != null && course.selected_units > 0) {
    return course.selected_units;
  }
  if (course.units_max > 0) return course.units_max;
  if (course.units_min > 0) return course.units_min;
  return 0;
}

export function getDifficultyTier(score: number): DifficultyTier {
  if (score < 2.2) {
    return {
      label: "Light",
      badgeClass: "border-emerald-500/40 bg-emerald-500/15 text-emerald-200",
      textClass: "text-emerald-300",
    };
  }
  if (score < 3.0) {
    return {
      label: "Moderate",
      badgeClass: "border-sky-500/40 bg-sky-500/15 text-sky-200",
      textClass: "text-sky-300",
    };
  }
  if (score < 3.7) {
    return {
      label: "Challenging",
      badgeClass: "border-amber-500/45 bg-amber-500/15 text-amber-200",
      textClass: "text-amber-300",
    };
  }
  return {
    label: "Very Hard",
    badgeClass: "border-rose-500/45 bg-rose-500/15 text-rose-200",
    textClass: "text-rose-300",
  };
}

/**
 * Extracts effective CU Reviews rating/difficulty/workload for a schedule course,
 * falling back to selected-section instructors' RateMyProfessors difficulty if needed.
 */
export function getCourseEffectiveMetrics(
  course: ScheduleCourseItem
): CourseEffectiveMetrics {
  const cu = course.cached_insights;
  const rating = cu?.rating ?? null;
  const workload = cu?.workload ?? null;
  const reviewCount = cu?.review_count ?? 0;

  if (cu?.difficulty != null) {
    return {
      rating,
      difficulty: cu.difficulty,
      difficultySource: "cu",
      workload,
      reviewCount,
    };
  }

  // Fallback to RateMyProfessors average difficulty for instructors of selected (or any) sections
  const rmpMap = course.cached_rmp || {};
  const selectedSet = new Set(course.selected_class_nbrs || []);
  const selectedInstrs = new Set<string>();
  const allInstrs = new Set<string>();

  for (const eg of course.enroll_groups || []) {
    for (const sec of eg.sections || []) {
      for (const nm of sec.instructors || []) {
        allInstrs.add(nm);
        if (selectedSet.has(sec.class_nbr)) {
          selectedInstrs.add(nm);
        }
      }
    }
  }

  const candidateNames =
    selectedInstrs.size > 0 ? Array.from(selectedInstrs) : Array.from(allInstrs);
  const rmpDiffs: number[] = [];
  for (const nm of candidateNames) {
    const d = rmpMap[nm]?.avg_difficulty;
    if (typeof d === "number") {
      rmpDiffs.push(d);
    }
  }

  if (rmpDiffs.length > 0) {
    const avg = rmpDiffs.reduce((a, b) => a + b, 0) / rmpDiffs.length;
    return {
      rating,
      difficulty: Number(avg.toFixed(2)),
      difficultySource: "rmp",
      workload,
      reviewCount,
    };
  }

  return {
    rating,
    difficulty: null,
    difficultySource: null,
    workload,
    reviewCount,
  };
}

export function summarizeScheduleInsights(
  courses: ScheduleCourseItem[]
): ScheduleInsightsSummary {
  const enabled = courses.filter((c) => c.enabled);
  let totalCredits = 0;

  let diffWeightedSum = 0;
  let diffWeightTotal = 0;
  let ratedDifficultyCount = 0;

  let wkWeightedSum = 0;
  let wkWeightTotal = 0;

  const ratings: number[] = [];

  for (const c of enabled) {
    const credits = getCourseEffectiveUnits(c);
    totalCredits += credits;
    const weight = credits > 0 ? credits : 1;

    const metrics = getCourseEffectiveMetrics(c);
    if (metrics.difficulty != null) {
      diffWeightedSum += metrics.difficulty * weight;
      diffWeightTotal += weight;
      ratedDifficultyCount += 1;
    }
    if (metrics.workload != null) {
      wkWeightedSum += metrics.workload * weight;
      wkWeightTotal += weight;
    }
    if (metrics.rating != null) {
      ratings.push(metrics.rating);
    }
  }

  const avgDifficulty =
    diffWeightTotal > 0 ? Number((diffWeightedSum / diffWeightTotal).toFixed(1)) : null;
  const avgWorkload =
    wkWeightTotal > 0 ? Number((wkWeightedSum / wkWeightTotal).toFixed(1)) : null;
  const avgRating =
    ratings.length > 0
      ? Number((ratings.reduce((a, b) => a + b, 0) / ratings.length).toFixed(1))
      : null;

  // Holistic semester difficulty factors in credit-weighted difficulty, workload, and total credit load vs 15 cr.
  let semesterLoadScore: number | null = null;
  if (avgDifficulty != null || avgWorkload != null) {
    const d = avgDifficulty ?? avgWorkload!;
    const w = avgWorkload ?? d;
    const base = 0.65 * d + 0.35 * w;
    const effCredits = totalCredits > 0 ? totalCredits : 15;
    const creditFactor = 0.75 + 0.25 * (effCredits / 15);
    semesterLoadScore = Number(Math.min(5, Math.max(1, base * creditFactor)).toFixed(1));
  }

  return {
    enabledCount: enabled.length,
    ratedDifficultyCount,
    avgDifficulty,
    avgWorkload,
    avgRating,
    semesterLoadScore,
    semesterTier: semesterLoadScore != null ? getDifficultyTier(semesterLoadScore) : null,
    difficultyTier: avgDifficulty != null ? getDifficultyTier(avgDifficulty) : null,
  };
}
