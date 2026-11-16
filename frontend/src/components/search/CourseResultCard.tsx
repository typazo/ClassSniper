import React from "react";
import {
  AlertTriangle,
  BellPlus,
  BookMarked,
  CalendarCheck2,
  CalendarPlus,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  Loader2,
  Lock,
} from "lucide-react";
import type { CourseInsights, CourseSection, CourseSummary } from "../../types";
import { courseCacheKey, formatCredits, summarizeStatuses, toneClasses } from "../../utils/courseFormat";
import { CourseInsightsPanel } from "../CourseInsightsPanel";
import { DropOddsBadge } from "../DropOddsBadge";
import { CourseLocationTags, SectionLocationTags } from "../LocationBadges";
import { StatusBadge } from "../StatusBadge";

interface Props {
  course: CourseSummary;
  isOpen: boolean;
  showCsFeatures: boolean;
  showIlrFeatures: boolean;
  csRequirement: string;
  ilrCodes: string[];
  minorCategories: string[];
  selectedAttrs: string[];
  fitsActiveSchedule: boolean;
  scheduleFit?: { fits: boolean; compatibleClassNbrs: Set<CourseSection["class_nbr"]> };
  scheduleStatus?: "adding" | "added" | "exists";
  insights?: CourseInsights;
  insightsLoading: boolean;
  insightsError?: string;
  onToggle: (course: CourseSummary) => void;
  onQuickAddSchedule: (course: CourseSummary) => void;
  onWatchCourse: (course: CourseSummary) => void;
  onWatchSection: (course: CourseSummary, section: CourseSection) => void;
  onRefreshInsights: (course: CourseSummary) => void;
}

export function CourseResultCard({
  course,
  isOpen,
  showCsFeatures,
  showIlrFeatures,
  csRequirement,
  ilrCodes,
  minorCategories,
  selectedAttrs,
  fitsActiveSchedule,
  scheduleFit,
  scheduleStatus,
  insights,
  insightsLoading,
  insightsError,
  onToggle,
  onQuickAddSchedule,
  onWatchCourse,
  onWatchSection,
  onRefreshInsights,
}: Props) {
  const cacheKey = courseCacheKey(course);
  const statusSummary = summarizeStatuses(course.sections);
  const groups = new Map<number, CourseSection[]>();
  for (const sec of course.sections) {
    const arr = groups.get(sec.enroll_group_idx) || [];
    arr.push(sec);
    groups.set(sec.enroll_group_idx, arr);
  }

  const elig = course.cs_eligibility;
  const creditsLabel = formatCredits(course.units_min, course.units_max);
  const collegeMeta = [course.acad_career, course.acad_group].filter(Boolean).join(" · ");
  const activeWarning = !showCsFeatures
    ? ""
    : csRequirement === "cs_elective"
      ? elig?.cs_elective_warning
      : csRequirement === "tech_elective"
        ? elig?.tech_elective_warning
        : csRequirement === "external_spec"
          ? elig?.external_spec_warning
          : elig?.cs_elective_warning || elig?.tech_elective_warning || elig?.external_spec_warning;

  const matchedAttrs = (course.crse_attrs || []).filter((attr) => selectedAttrs.includes(attr));
  const ilrPrimaryWarning = showIlrFeatures ? course.ilr_eligibility?.warnings?.[0] : undefined;
  const minorPrimaryWarning = course.minor_eligibility?.warnings?.[0];

  const hasExpandedDetailsBox = Boolean(
    course.catalog_prereq ||
      course.catalog_coreq ||
      course.catalog_forbidden_overlaps ||
      showCsFeatures ||
      (showIlrFeatures &&
        course.ilr_eligibility &&
        (course.ilr_eligibility.qualifies_any || course.ilr_eligibility.ug_crosslist_hints.length > 0)) ||
      (elig?.prereq_status && elig.prereq_status !== "none")
  );

  return (
    <div className="rounded-2xl border border-zinc-800 bg-zinc-900/75">
      <div className="flex flex-wrap items-center justify-between gap-3 p-4">
        <button
          type="button"
          onClick={() => onToggle(course)}
          className="flex min-w-0 flex-1 items-start gap-3 text-left"
        >
          <div className="mt-0.5 text-zinc-400">
            {isOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </div>
          <div className="min-w-0 space-y-1">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <span className="text-base font-bold text-white">
                {course.subject} {course.catalog_nbr}
              </span>
              {(creditsLabel || course.sections.length > 0) && (
                <span className="text-xs text-zinc-400">
                  {[creditsLabel, `${course.sections.length} sec${course.sections.length === 1 ? "" : "s"}`]
                    .filter(Boolean)
                    .join(" · ")}
                </span>
              )}

              {course.status_is_stale ? (
                <span className="inline-flex items-center gap-1 text-[11px] text-zinc-400">
                  <Loader2 className="h-3 w-3 animate-spin text-emerald-400" />
                  Checking...
                </span>
              ) : (
                <span className="inline-flex items-center gap-1.5 text-xs font-medium">
                  {statusSummary.open > 0 && (
                    <span className="text-emerald-400">{statusSummary.open} Open</span>
                  )}
                  {statusSummary.waitlist > 0 && (
                    <span className="text-amber-300">{statusSummary.waitlist} Waitlist</span>
                  )}
                  {statusSummary.closed > 0 && (
                    <span className="text-rose-400">{statusSummary.closed} Closed</span>
                  )}
                </span>
              )}

              {!course.status_is_stale &&
                course.drop_odds &&
                course.drop_odds.tier !== "untracked" &&
                course.drop_odds.tier !== "none" &&
                (statusSummary.closed > 0 || statusSummary.waitlist > 0 || course.drop_odds.flips_all > 0) && (
                  <DropOddsBadge dropOdds={course.drop_odds} compact />
                )}

              <CourseLocationTags sections={course.sections} />
              {(course.hidden_other_location_count ?? 0) > 0 && (
                <span
                  className="text-[11px] text-zinc-500"
                  title={`Hidden section(s) at ${(course.hidden_other_locations || []).join(", ")}`}
                >
                  +{course.hidden_other_location_count} off-campus hidden
                </span>
              )}

              {showCsFeatures &&
                elig?.badges.map((badge, idx) => (
                  <span
                    key={`${badge.kind}-${idx}`}
                    className={`inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[10px] font-semibold ${toneClasses(
                      badge.tone,
                      "badge"
                    )}`}
                  >
                    {badge.tone === "amber" && <AlertTriangle className="h-2.5 w-2.5" />}
                    {badge.label}
                  </span>
                ))}

              {matchedAttrs.map((attr) => (
                <span
                  key={attr}
                  className="rounded-md border border-violet-400/60 bg-violet-500/20 px-1.5 py-0.5 text-[10px] font-medium text-violet-200"
                >
                  {attr === "HST-AS" ? "HIST-AS" : attr}
                </span>
              ))}

              {fitsActiveSchedule && scheduleFit?.fits && (
                <span className="inline-flex items-center gap-1 rounded-md border border-sky-500/40 bg-sky-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-sky-200">
                  <CalendarCheck2 className="h-2.5 w-2.5" />
                  Fits Schedule
                </span>
              )}

              {showIlrFeatures &&
                course.ilr_eligibility?.badges.map((badge) => {
                  const active = ilrCodes.includes(badge.code) || badge.is_main_elective;
                  return (
                    <span
                      key={badge.code}
                      title={badge.rule_summary}
                      className={`inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[10px] font-semibold ${toneClasses(
                        badge.tone,
                        active ? "highlight" : "badge"
                      )}`}
                    >
                      {badge.is_main_elective && "★ "}
                      {badge.code} · {badge.short_label}
                    </span>
                  );
                })}

              {course.minor_eligibility?.badges.map((badge) => {
                const active = minorCategories.includes(badge.category_id);
                return (
                  <span
                    key={`minor-${badge.category_id}`}
                    title={`${course.minor_eligibility?.minor_label} (${course.minor_eligibility?.version_label})`}
                    className={`inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[10px] font-semibold ${toneClasses(
                      badge.tone,
                      active ? "highlight" : "badge"
                    )} ${badge.completed ? "opacity-65 line-through" : ""}`}
                  >
                    {course.minor_eligibility?.minor_label}: {badge.label}
                  </span>
                );
              })}

              {elig?.prereq_status === "met" && (
                <span className="inline-flex items-center gap-1 text-[11px] font-medium text-emerald-400">
                  <CheckCircle2 className="h-3 w-3" />
                  Prereqs Met
                </span>
              )}
              {elig?.prereq_status === "unmet" && elig.missing_prereqs && (
                <span className="inline-flex items-center gap-1 rounded-md border border-rose-500/35 bg-rose-500/10 px-1.5 py-0.5 text-[10px] font-medium text-rose-300">
                  <Lock className="h-2.5 w-2.5" />
                  Missing: {elig.missing_prereqs}
                </span>
              )}
              {elig?.prereq_status === "prose" && (
                <span className="inline-flex items-center gap-1 text-[11px] font-medium text-amber-300">
                  <AlertTriangle className="h-3 w-3" />
                  Text prereq
                </span>
              )}
            </div>

            <p className="text-sm text-zinc-200">{course.title_long}</p>

            <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px]">
              {showCsFeatures &&
                elig?.tech_elective_reason &&
                (csRequirement === "tech_elective" || csRequirement === "") && (
                  <span className="text-sky-300/90">{elig.tech_elective_reason}</span>
                )}
              {showIlrFeatures &&
                course.ilr_eligibility &&
                ilrCodes.length > 0 &&
                !ilrCodes.includes("ANY_IL") &&
                course.ilr_eligibility.also_fits_codes.length > 0 && (
                  <span className="font-medium text-teal-300/95">
                    Also satisfies {course.ilr_eligibility.also_fits_codes.join(" + ")}
                  </span>
                )}
              {showIlrFeatures &&
                course.ilr_eligibility &&
                (ilrCodes.length === 0 || ilrCodes.includes("ANY_IL")) &&
                course.ilr_eligibility.requirement_count >= 2 && (
                  <span className="font-medium text-teal-300/95">
                    Satisfies {course.ilr_eligibility.requirement_count} ILR reqs:{" "}
                    {course.ilr_eligibility.codes.join(" + ")}
                  </span>
                )}
              {activeWarning && (
                <span className="inline-flex items-center gap-1 text-amber-300/95">
                  <AlertTriangle className="h-3 w-3 shrink-0" />
                  {activeWarning}
                </span>
              )}
              {ilrPrimaryWarning && (
                <span className="inline-flex items-center gap-1 text-amber-300/95">
                  <AlertTriangle className="h-3 w-3 shrink-0" />
                  {ilrPrimaryWarning}
                </span>
              )}
              {minorPrimaryWarning && (
                <span className="inline-flex items-center gap-1 text-amber-300/95">
                  <AlertTriangle className="h-3 w-3 shrink-0" />
                  {minorPrimaryWarning}
                </span>
              )}
              {course.crosslists && course.crosslists.length > 0 && (
                <span className="text-zinc-500">Cross-listed: {course.crosslists.join(", ")}</span>
              )}
            </div>
          </div>
        </button>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            disabled={scheduleStatus === "adding"}
            onClick={() => onQuickAddSchedule(course)}
            className={`inline-flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs font-medium transition ${
              scheduleStatus === "added" || scheduleStatus === "exists"
                ? "border-sky-500/50 bg-sky-500/15 text-sky-200 hover:bg-sky-500/25"
                : "border-zinc-700 text-zinc-200 hover:border-sky-500/50 hover:text-sky-300"
            }`}
          >
            {scheduleStatus === "added" || scheduleStatus === "exists" ? (
              <>
                <Check className="h-3.5 w-3.5" />
                {scheduleStatus === "exists" ? "In Schedule" : "Added"}
              </>
            ) : (
              <>
                <CalendarPlus className="h-3.5 w-3.5" />
                {scheduleStatus === "adding" ? "Adding..." : "+ Schedule"}
              </>
            )}
          </button>
          <button
            type="button"
            onClick={() => onWatchCourse(course)}
            className="inline-flex items-center gap-1.5 rounded-xl border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-200 hover:border-emerald-500/50 hover:text-emerald-300"
          >
            <BellPlus className="h-3.5 w-3.5" />
            Watch Any Section
          </button>
        </div>
      </div>

      {isOpen && (
        <div className="space-y-4 border-t border-zinc-800/80 p-4">
          {(collegeMeta || (course.crse_attrs && course.crse_attrs.length > 0)) && (
            <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
              {collegeMeta && (
                <span className="rounded-md bg-zinc-800 px-2 py-0.5 font-medium text-zinc-300">{collegeMeta}</span>
              )}
              {course.crse_attrs?.map((attr) => (
                <span
                  key={attr}
                  className={`rounded-md border px-1.5 py-0.5 text-[10px] font-medium ${
                    selectedAttrs.includes(attr)
                      ? "border-violet-400/60 bg-violet-500/20 text-violet-200"
                      : "border-zinc-700/80 bg-zinc-950 text-zinc-400"
                  }`}
                >
                  {attr === "HST-AS" ? "HIST-AS" : attr}
                </span>
              ))}
            </div>
          )}

          {course.description && <p className="text-xs leading-relaxed text-zinc-400">{course.description}</p>}

          {hasExpandedDetailsBox && (
            <div className="space-y-1.5 rounded-xl border border-zinc-800 bg-zinc-950/80 p-3 text-xs">
              <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] font-semibold text-zinc-300">
                <span className="inline-flex items-center gap-1.5">
                  <BookMarked className="h-3.5 w-3.5 text-emerald-400" />
                  {showCsFeatures
                    ? "Prerequisites & Degree Check"
                    : showIlrFeatures
                      ? "ILR Requirements & Prerequisites"
                      : "Prerequisites"}
                </span>
                {showCsFeatures && (
                  <a
                    href="https://catalog.cornell.edu/programs/computer-science-bs/"
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 font-normal text-emerald-400 hover:underline"
                  >
                    Cornell CS Catalog
                    <ExternalLink className="h-3 w-3" />
                  </a>
                )}
                {showIlrFeatures && (
                  <a
                    href="https://www.ilr.cornell.edu/current-students/undergraduate-student-resources/curriculum-requirements/new-curriculum-requirements"
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 font-normal text-teal-300 hover:underline"
                  >
                    ILR Curriculum Rules
                    <ExternalLink className="h-3 w-3" />
                  </a>
                )}
              </div>
              {showIlrFeatures && course.ilr_eligibility && course.ilr_eligibility.badges.length > 0 && (
                <div className="space-y-1 pb-1">
                  {course.ilr_eligibility.badges.map((badge) => (
                    <div key={badge.code} className="text-zinc-300">
                      <span className="font-mono font-semibold text-teal-300">{badge.code}</span>
                      {" — "}
                      <span className="font-medium text-zinc-100">{badge.label}</span>
                      <span className="text-zinc-400"> · {badge.rule_summary}</span>
                    </div>
                  ))}
                </div>
              )}
              {showIlrFeatures &&
                course.ilr_eligibility?.warnings.map((warn) => (
                  <div key={warn} className="text-amber-300">
                    <span className="font-medium">ILR rule check: </span>
                    {warn}
                  </div>
                ))}
              {showIlrFeatures &&
                course.ilr_eligibility?.ug_crosslist_hints.map((hint) => (
                  <div key={hint} className="text-sky-300">
                    <span className="font-medium">Cross-list note: </span>
                    {hint}
                  </div>
                ))}
              {course.minor_eligibility && course.minor_eligibility.warnings.length > 1 &&
                course.minor_eligibility.warnings.slice(1).map((warn) => (
                  <div key={warn} className="text-amber-300">
                    <span className="font-medium">Minor note: </span>
                    {warn}
                  </div>
                ))}
              {elig?.prereq_status === "met" && elig.satisfied_by && elig.satisfied_by.length > 0 && (
                <div className="text-emerald-300">
                  <span className="font-medium">Prereq check: </span>
                  Satisfied by {elig.satisfied_by.join(", ")}
                </div>
              )}
              {elig?.prereq_status === "none" && (
                <div className="text-zinc-400">
                  <span className="font-medium">Prereq check: </span>
                  No explicit course prerequisites listed.
                </div>
              )}
              {elig?.prereq_status === "unmet" && elig.missing_prereqs && (
                <div className="text-rose-300">
                  <span className="font-medium">Prereq check: </span>
                  Missing {elig.missing_prereqs}
                </div>
              )}
              {elig?.prereq_status === "prose" && (
                <div className="text-amber-200">
                  <span className="font-medium">Prereq check: </span>
                  Text-only prerequisite — verify manually against the catalog description below.
                </div>
              )}
              {course.catalog_prereq && (
                <div className="text-zinc-300">
                  <span className="font-medium text-zinc-400">Prerequisites: </span>
                  {course.catalog_prereq}
                </div>
              )}
              {course.catalog_coreq && (
                <div className="text-zinc-300">
                  <span className="font-medium text-zinc-400">Corequisites: </span>
                  {course.catalog_coreq}
                </div>
              )}
              {course.catalog_forbidden_overlaps && (
                <div className="text-zinc-400">
                  <span className="font-medium">Forbidden Overlaps: </span>
                  {course.catalog_forbidden_overlaps}
                </div>
              )}
              {showCsFeatures && elig?.tech_elective && elig.tech_elective_reason && (
                <div className="text-sky-300/95">
                  <span className="font-medium">Why it counts as CS Tech Elective: </span>
                  {elig.tech_elective_reason.replace(/^TE rule:\s*/i, "")}
                  {elig.tech_elective_reason.includes("cross-listed") &&
                    " (Cornell departments sometimes write different prerequisite text on cross-listed numbers.)"}
                </div>
              )}
              {showCsFeatures && course.acad_group && course.acad_group !== "AS" && (
                <div className="text-[11px] text-zinc-500">
                  College code <span className="text-zinc-300">{course.acad_group}</span> (B.A. A&amp;S students: non-A&amp;S course cap applies).
                </div>
              )}
            </div>
          )}

          <CourseInsightsPanel
            course={course}
            insights={insights}
            loading={insightsLoading}
            error={insightsError}
            onRefresh={() => onRefreshInsights(course)}
          />

          {Array.from(groups.entries()).map(([egIdx, secs]) => (
            <div key={egIdx} className="rounded-xl border border-zinc-800 bg-zinc-950/70 p-3">
              <div className="mb-2 flex items-center justify-between text-xs text-zinc-400">
                <span className="font-semibold text-zinc-300">Enrollment Group {egIdx + 1}</span>
                {secs[0]?.components_required?.length > 0 && (
                  <span>Required: {secs[0].components_required.join(" + ")}</span>
                )}
              </div>
              <div className="divide-y divide-zinc-800/70">
                {secs.map((sec) => (
                  <div
                    key={sec.class_nbr}
                    className="flex flex-wrap items-center justify-between gap-2 py-2.5 first:pt-1 last:pb-1"
                  >
                    <div className="min-w-0 space-y-0.5">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-semibold text-white">
                          {sec.ssr_component} {sec.section}
                        </span>
                        <span className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono text-xs text-zinc-300">
                          #{sec.class_nbr}
                        </span>
                        {course.status_is_stale ? (
                          <span className="inline-flex items-center gap-1 rounded-full bg-zinc-800 px-2.5 py-0.5 text-[11px] font-medium text-zinc-300">
                            <Loader2 className="h-3 w-3 animate-spin text-emerald-400" />
                            Loading...
                          </span>
                        ) : (
                          <StatusBadge status={sec.open_status} />
                        )}
                        <SectionLocationTags section={sec} showIthacaTag />
                        {fitsActiveSchedule && scheduleFit?.compatibleClassNbrs.has(sec.class_nbr) && (
                          <span className="inline-flex items-center gap-0.5 rounded-md border border-sky-500/40 bg-sky-500/15 px-1.5 py-0.5 text-[10px] font-medium text-sky-200">
                            <Check className="h-2.5 w-2.5" />
                            Fits
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-zinc-400">
                        {sec.meetings_summary} &middot; {sec.instructors_summary}
                      </div>
                    </div>

                    <button
                      type="button"
                      onClick={() => onWatchSection(course, sec)}
                      className="inline-flex items-center gap-1.5 rounded-xl bg-emerald-500/15 px-3 py-1.5 text-xs font-semibold text-emerald-300 ring-1 ring-emerald-500/30 hover:bg-emerald-500/25"
                    >
                      <BellPlus className="h-3.5 w-3.5" />
                      Snipe
                    </button>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
