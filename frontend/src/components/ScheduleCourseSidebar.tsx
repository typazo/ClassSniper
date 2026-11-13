import React, { useMemo, useState } from "react";
import {
  BellPlus,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Copy,
  Eye,
  EyeOff,
  Lock,
  Plus,
  Trash2,
  Unlock,
} from "lucide-react";
import type {
  DayCode,
  ScheduleBlock,
  ScheduleCourseItem,
  ScheduleSection,
} from "../types";
import { StatusBadge } from "./StatusBadge";
import { getCourseEffectiveMetrics, getDifficultyTier } from "../utils/scheduleInsights";
import {
  findCompatibleSectionsForCourse,
  formatMinutesShort,
  getCourseColor,
  selectSectionInCourse,
} from "../utils/schedulerSolver";

const ALL_DAYS: DayCode[] = ["M", "T", "W", "R", "F"];

interface Props {
  courses: ScheduleCourseItem[];
  blocks: ScheduleBlock[];
  expandedCourseId: number | null;
  watchBusyKey: string | null;
  isTranscript?: boolean;
  isArchivedRoster?: boolean;
  onToggleExpand: (itemId: number) => void;
  onUpdateCourse: (
    itemId: number,
    patch: {
      enabled?: boolean;
      selected_units?: number | null;
      selected_class_nbrs?: number[];
      locked_class_nbrs?: number[];
    }
  ) => void;
  onRemoveCourse: (itemId: number) => void;
  onHoverSection: (
    preview: { course: ScheduleCourseItem; section: ScheduleSection; conflicts: boolean } | null
  ) => void;
  onWatchCourseCompatible: (course: ScheduleCourseItem, sections: ScheduleSection[]) => void;
  onCreateBlock: (payload: { label: string; days: DayCode[]; startMin: number; endMin: number }) => void;
  onToggleBlock: (blockId: number, enabled: boolean) => void;
  onDeleteBlock: (blockId: number) => void;
}

export function ScheduleCourseSidebar({
  courses,
  blocks,
  expandedCourseId,
  watchBusyKey,
  isTranscript = false,
  isArchivedRoster = false,
  onToggleExpand,
  onUpdateCourse,
  onRemoveCourse,
  onHoverSection,
  onWatchCourseCompatible,
  onCreateBlock,
  onToggleBlock,
  onDeleteBlock,
}: Props) {
  const [copiedNbr, setCopiedNbr] = useState<number | null>(null);
  const [showBlockForm, setShowBlockForm] = useState(false);
  const [blockLabel, setBlockLabel] = useState("Busy");
  const [blockDays, setBlockDays] = useState<DayCode[]>(["M", "W", "F"]);
  const [blockStart, setBlockStart] = useState("12:00");
  const [blockEnd, setBlockEnd] = useState("13:00");

  const compatibilityByCourse = useMemo(() => {
    const map = new Map<number, ReturnType<typeof findCompatibleSectionsForCourse>>();
    for (const c of courses) {
      map.set(c.id, findCompatibleSectionsForCourse(c, courses, blocks));
    }
    return map;
  }, [courses, blocks]);

  const copyClassNbr = (nbr: number) => {
    navigator.clipboard?.writeText(String(nbr));
    setCopiedNbr(nbr);
    setTimeout(() => setCopiedNbr((cur) => (cur === nbr ? null : cur)), 1200);
  };

  const parseHHMM = (val: string): number => {
    const [h, m] = val.split(":").map(Number);
    return (h || 0) * 60 + (m || 0);
  };

  const handleAddBlockSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const s = parseHHMM(blockStart);
    const en = parseHHMM(blockEnd);
    if (blockDays.length === 0 || en <= s) return;
    onCreateBlock({
      label: blockLabel.trim() || "Busy",
      days: blockDays,
      startMin: s,
      endMin: en,
    });
    setShowBlockForm(false);
  };

  return (
    <div className="space-y-4">
      {/* Courses List */}
      <div className="space-y-2.5">
        {courses.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-zinc-800 bg-zinc-900/40 p-5 text-center text-xs text-zinc-400">
            <p className="font-medium text-zinc-300">No courses in this schedule yet</p>
            <p className="mt-1">
              Add courses using Quick-Add above or{" "}
              <span className="font-semibold text-sky-300">+ Schedule</span> in Search Classes.
              Once added, use{" "}
              <span className="font-semibold text-emerald-300">Auto-Generate</span> to find
              conflict-free lecture, discussion &amp; lab combinations.
            </p>
          </div>
        ) : (
          courses.map((course) => {
            const style = getCourseColor(course.color_idx);
            const isExpanded = expandedCourseId === course.id;
            const selectedSet = new Set(course.selected_class_nbrs);
            const lockedSet = new Set(course.locked_class_nbrs);
            const selectedSections = course.enroll_groups.flatMap((eg) =>
              eg.sections.filter((s) => selectedSet.has(s.class_nbr))
            );
            const compat = compatibilityByCourse.get(course.id);
            const compatibleWatchTargets = course.enroll_groups.flatMap((eg) =>
              eg.sections.filter(
                (s) =>
                  compat?.compatibleClassNbrs.has(s.class_nbr) &&
                  s.open_status !== "O"
              )
            );
            const variableCredits =
              course.units_max > 0 && course.units_max > course.units_min;
            const effUnits =
              course.selected_units != null
                ? course.selected_units
                : course.units_max || course.units_min;

            const creditChoices: number[] = [];
            if (variableCredits) {
              for (
                let u = course.units_min;
                u <= course.units_max + 0.01;
                u += Number.isInteger(course.units_min) && Number.isInteger(course.units_max) ? 1 : 0.5
              ) {
                creditChoices.push(Math.round(u * 100) / 100);
              }
            }

            return (
              <div
                key={course.id}
                className={`rounded-2xl border transition-colors ${
                  course.enabled
                    ? "border-zinc-800 bg-zinc-900/80"
                    : "border-zinc-800/60 bg-zinc-900/35 opacity-65"
                }`}
              >
                {/* Header */}
                <div className="p-3">
                  <div className="flex items-start justify-between gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        onHoverSection(null);
                        onToggleExpand(course.id);
                      }}
                      className="flex min-w-0 flex-1 items-start gap-2 text-left"
                    >
                      <span className={`mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full ${style.dot}`} />
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <span className="text-sm font-bold text-white">
                            {course.subject} {course.catalog_nbr}
                          </span>
                          <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] font-medium text-zinc-300">
                            {effUnits} cr
                          </span>
                          {(() => {
                            const eff = getCourseEffectiveMetrics(course);
                            const diffTier =
                              eff.difficulty != null ? getDifficultyTier(eff.difficulty) : null;
                            return (
                              <>
                                {eff.difficulty != null && diffTier && (
                                  <span
                                    className={`rounded border px-1.5 py-0.5 text-[10px] font-semibold ${diffTier.badgeClass}`}
                                    title={
                                      eff.difficultySource === "rmp"
                                        ? `RateMyProfessors Avg Difficulty (${diffTier.label})`
                                        : `CU Reviews Course Difficulty (${diffTier.label})`
                                    }
                                  >
                                    {eff.difficultySource === "rmp" ? "RMP " : ""}Diff{" "}
                                    {eff.difficulty.toFixed(1)}/5
                                  </span>
                                )}
                                {(eff.rating != null || eff.workload != null) && (
                                  <span
                                    className="rounded border border-sky-500/30 bg-sky-500/10 px-1.5 py-0.5 text-[10px] text-sky-200"
                                    title="CU Reviews Rating & Workload"
                                  >
                                    {[
                                      eff.rating != null ? `★ ${eff.rating.toFixed(1)}` : null,
                                      eff.workload != null ? `Wk ${eff.workload.toFixed(1)}` : null,
                                    ]
                                      .filter(Boolean)
                                      .join(" · ")}
                                  </span>
                                )}
                              </>
                            );
                          })()}
                          {course.cs_eligibility?.prereq_status === "unmet" && (
                            <span
                              className="rounded border border-rose-500/35 bg-rose-500/10 px-1.5 py-0.5 text-[10px] text-rose-300"
                              title={`Missing: ${course.cs_eligibility.missing_prereqs}`}
                            >
                              Prereq Unmet
                            </span>
                          )}
                          {course.cs_eligibility?.prereq_status === "met" && (
                            <span className="inline-flex items-center gap-0.5 rounded border border-emerald-500/30 bg-emerald-500/10 px-1.5 py-0.5 text-[10px] text-emerald-300">
                              <CheckCircle2 className="h-2.5 w-2.5" />
                              Prereq Met
                            </span>
                          )}
                        </div>
                        <div className="truncate text-xs text-zinc-400">{course.title_long}</div>
                      </div>
                    </button>

                    <div className="flex shrink-0 items-center gap-1">
                      {!isTranscript && (
                        <button
                          type="button"
                          onClick={() => onUpdateCourse(course.id, { enabled: !course.enabled })}
                          title={course.enabled ? "Hide from calendar" : "Show on calendar"}
                          className="rounded-lg p-1.5 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
                        >
                          {course.enabled ? (
                            <Eye className="h-3.5 w-3.5 text-emerald-400" />
                          ) : (
                            <EyeOff className="h-3.5 w-3.5" />
                          )}
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={() => onToggleExpand(course.id)}
                        title="Choose sections"
                        className="rounded-lg p-1.5 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
                      >
                        {isExpanded ? (
                          <ChevronUp className="h-3.5 w-3.5" />
                        ) : (
                          <ChevronDown className="h-3.5 w-3.5" />
                        )}
                      </button>
                      {!isTranscript && (
                        <button
                          type="button"
                          onClick={() => onRemoveCourse(course.id)}
                          title="Remove from schedule"
                          className="rounded-lg p-1.5 text-zinc-400 hover:bg-rose-500/15 hover:text-rose-300"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Selected Sections Pills */}
                  <div className="mt-2 flex flex-wrap items-center gap-1.5">
                    {selectedSections.map((sec) => {
                      const isLocked = lockedSet.has(sec.class_nbr);
                      return (
                        <div
                          key={sec.class_nbr}
                          className="inline-flex items-center gap-1 rounded-lg border border-zinc-800 bg-zinc-950/90 px-2 py-1 text-[11px]"
                        >
                          <button
                            type="button"
                            onClick={() => {
                              const nextLocked = isLocked
                                ? course.locked_class_nbrs.filter((n) => n !== sec.class_nbr)
                                : [...course.locked_class_nbrs, sec.class_nbr];
                              onUpdateCourse(course.id, { locked_class_nbrs: nextLocked });
                            }}
                            title={
                              isLocked
                                ? "Pinned for Auto-Generator (click to unpin)"
                                : "Pin this section for Auto-Generator"
                            }
                            className={`rounded p-0.5 ${
                              isLocked
                                ? "text-amber-300 hover:bg-amber-500/15"
                                : "text-zinc-500 hover:bg-zinc-800 hover:text-zinc-300"
                            }`}
                          >
                            {isLocked ? <Lock className="h-3 w-3" /> : <Unlock className="h-3 w-3" />}
                          </button>
                          <span className="font-semibold text-zinc-200">
                            {sec.ssr_component} {sec.section}
                          </span>
                          <button
                            type="button"
                            onClick={() => copyClassNbr(sec.class_nbr)}
                            title="Copy class number"
                            className="inline-flex items-center gap-0.5 font-mono text-[10px] text-zinc-400 hover:text-emerald-300"
                          >
                            #{sec.class_nbr}
                            <Copy className="h-2.5 w-2.5" />
                          </button>
                          {copiedNbr === sec.class_nbr && (
                            <span className="text-[10px] text-emerald-400">Copied</span>
                          )}
                          <StatusBadge status={sec.open_status} />
                        </div>
                      );
                    })}
                  </div>
                </div>

                {/* Expanded Section Picker */}
                {isExpanded && (
                  <div className="space-y-3 border-t border-zinc-800/80 bg-zinc-950/50 p-3">
                    {variableCredits && creditChoices.length > 1 && (
                      <div className="flex items-center justify-between gap-2 text-xs">
                        <span className="text-zinc-400">Credits for this course:</span>
                        <select
                          value={effUnits}
                          onChange={(e) =>
                            onUpdateCourse(course.id, { selected_units: Number(e.target.value) })
                          }
                          className="rounded-lg border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-100"
                        >
                          {creditChoices.map((u) => (
                            <option key={u} value={u}>
                              {u} cr
                            </option>
                          ))}
                        </select>
                      </div>
                    )}

                    {!isArchivedRoster && compatibleWatchTargets.length > 0 && (
                      <button
                        type="button"
                        disabled={watchBusyKey === `course-${course.id}`}
                        onClick={() => onWatchCourseCompatible(course, compatibleWatchTargets)}
                        className="flex w-full items-center justify-center gap-1.5 rounded-xl border border-emerald-500/35 bg-emerald-500/10 px-3 py-1.5 text-xs font-medium text-emerald-300 hover:bg-emerald-500/20 disabled:opacity-50"
                      >
                        <BellPlus className="h-3.5 w-3.5" />
                        {watchBusyKey === `course-${course.id}`
                          ? "Creating watches..."
                          : `Watch ${compatibleWatchTargets.length} Schedule-Compatible Closed/WL Section${
                              compatibleWatchTargets.length === 1 ? "" : "s"
                            }`}
                      </button>
                    )}

                    {course.enroll_groups.map((eg) => {
                      const components = Array.from(
                        new Set(eg.sections.map((s) => s.ssr_component).filter(Boolean))
                      );
                      return (
                        <div key={eg.enroll_group_idx} className="space-y-2">
                          <div className="flex items-center justify-between text-[11px] text-zinc-400">
                            <span className="font-semibold text-zinc-300">
                              Enroll Group {eg.enroll_group_idx + 1}
                              {eg.components_required.length > 0
                                ? ` (${eg.components_required.join(" + ")})`
                                : ""}
                            </span>
                            {eg.grading_basis && <span>{eg.grading_basis}</span>}
                          </div>

                          {components.map((comp) => {
                            const secs = eg.sections.filter((s) => s.ssr_component === comp);
                            return (
                              <div key={comp} className="space-y-1">
                                <div className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
                                  {comp}
                                </div>
                                {secs.map((sec) => {
                                  const isSelected = selectedSet.has(sec.class_nbr);
                                  const conflicts = Boolean(
                                    compat?.directConflictClassNbrs.has(sec.class_nbr)
                                  );
                                  const fits = Boolean(
                                    compat?.compatibleClassNbrs.has(sec.class_nbr)
                                  );

                                  return (
                                    <button
                                      key={sec.class_nbr}
                                      type="button"
                                      onMouseEnter={() =>
                                        onHoverSection({ course, section: sec, conflicts })
                                      }
                                      onMouseLeave={() => onHoverSection(null)}
                                      onClick={() => {
                                        onHoverSection(null);
                                        const nextNbrs = selectSectionInCourse(course, sec);
                                        onUpdateCourse(course.id, { selected_class_nbrs: nextNbrs });
                                      }}
                                      className={`flex w-full items-center justify-between gap-2 rounded-xl border px-2.5 py-2 text-left text-xs transition ${
                                        isSelected
                                          ? "border-emerald-500/60 bg-emerald-500/15"
                                          : conflicts
                                            ? "border-zinc-800/80 bg-zinc-900/40 opacity-60 hover:border-rose-500/40"
                                            : "border-zinc-800 bg-zinc-900/75 hover:border-zinc-700"
                                      }`}
                                    >
                                      <div className="min-w-0 flex-1">
                                        <div className="flex flex-wrap items-center gap-1.5">
                                          <span className="font-semibold text-zinc-100">
                                            {sec.ssr_component} {sec.section}
                                          </span>
                                          <span className="font-mono text-[10px] text-zinc-500">
                                            #{sec.class_nbr}
                                          </span>
                                          {!isSelected && (
                                            <span
                                              className={`rounded px-1 py-0.5 text-[9px] font-semibold ${
                                                conflicts
                                                  ? "bg-rose-500/15 text-rose-300"
                                                  : fits
                                                    ? "bg-emerald-500/15 text-emerald-300"
                                                    : "bg-zinc-800 text-zinc-400"
                                              }`}
                                            >
                                              {conflicts ? "Conflict" : fits ? "Fits" : "Group conflict"}
                                            </span>
                                          )}
                                        </div>
                                        <div className="truncate text-[11px] text-zinc-400">
                                          {sec.meetings_summary}
                                        </div>
                                        <div className="truncate text-[10px] text-zinc-500">
                                          {sec.instructors_summary}
                                        </div>
                                        {sec.instructors.some((nm) => course.cached_rmp?.[nm]) && (
                                          <div className="mt-0.5 flex flex-wrap gap-1">
                                            {sec.instructors.map((nm) => {
                                              const rmp = course.cached_rmp?.[nm];
                                              if (!rmp || (rmp.avg_rating == null && rmp.avg_difficulty == null)) {
                                                return null;
                                              }
                                              return (
                                                <span
                                                  key={nm}
                                                  className="rounded bg-zinc-800/90 px-1.5 py-0.5 text-[9px] text-amber-200/90"
                                                  title={`RateMyProfessors for ${nm} (${rmp.num_ratings} ratings)`}
                                                >
                                                  RMP:{" "}
                                                  {[
                                                    rmp.avg_rating != null ? `★ ${rmp.avg_rating.toFixed(1)}` : null,
                                                    rmp.avg_difficulty != null
                                                      ? `Diff ${rmp.avg_difficulty.toFixed(1)}/5`
                                                      : null,
                                                  ]
                                                    .filter(Boolean)
                                                    .join(" · ")}
                                                </span>
                                              );
                                            })}
                                          </div>
                                        )}
                                      </div>
                                      <StatusBadge status={sec.open_status} />
                                    </button>
                                  );
                                })}
                              </div>
                            );
                          })}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      {/* Busy / Blocked Time Slots */}
      <div className="rounded-2xl border border-zinc-800 bg-zinc-900/70 p-3">
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs font-semibold text-zinc-200">
            Busy / Blocked Times ({blocks.length})
          </span>
          <button
            type="button"
            onClick={() => setShowBlockForm((s) => !s)}
            className="inline-flex items-center gap-1 rounded-lg border border-zinc-700 px-2 py-1 text-[11px] text-zinc-300 hover:border-emerald-500/50 hover:text-emerald-300"
          >
            <Plus className="h-3 w-3" />
            Add Block
          </button>
        </div>

        {/* Quick Presets */}
        <div className="mt-2 flex flex-wrap gap-1.5">
          <button
            type="button"
            onClick={() =>
              onCreateBlock({
                label: "No Early Morning",
                days: ["M", "T", "W", "R", "F"],
                startMin: 8 * 60,
                endMin: 10 * 60 + 5,
              })
            }
            className="rounded-lg border border-zinc-800 bg-zinc-950 px-2 py-1 text-[10px] text-zinc-400 hover:border-zinc-700 hover:text-zinc-200"
          >
            + No &lt;10:10 AM
          </button>
          <button
            type="button"
            onClick={() =>
              onCreateBlock({
                label: "Lunch Break",
                days: ["M", "T", "W", "R", "F"],
                startMin: 12 * 60 + 15,
                endMin: 13 * 60 + 15,
              })
            }
            className="rounded-lg border border-zinc-800 bg-zinc-950 px-2 py-1 text-[10px] text-zinc-400 hover:border-zinc-700 hover:text-zinc-200"
          >
            + Lunch 12:15–1:15
          </button>
          <button
            type="button"
            onClick={() =>
              onCreateBlock({
                label: "Free Friday",
                days: ["F"],
                startMin: 8 * 60,
                endMin: 18 * 60,
              })
            }
            className="rounded-lg border border-zinc-800 bg-zinc-950 px-2 py-1 text-[10px] text-zinc-400 hover:border-zinc-700 hover:text-zinc-200"
          >
            + Free Fridays
          </button>
        </div>

        {showBlockForm && (
          <form onSubmit={handleAddBlockSubmit} className="mt-3 space-y-2 rounded-xl border border-zinc-800 bg-zinc-950 p-2.5">
            <input
              type="text"
              value={blockLabel}
              onChange={(e) => setBlockLabel(e.target.value)}
              placeholder="Label (e.g. Work, Gym, Lunch)"
              className="w-full rounded-lg border border-zinc-800 bg-zinc-900 px-2.5 py-1.5 text-xs text-zinc-100"
            />
            <div className="flex flex-wrap gap-1">
              {ALL_DAYS.map((d) => {
                const active = blockDays.includes(d);
                return (
                  <button
                    key={d}
                    type="button"
                    onClick={() =>
                      setBlockDays((prev) =>
                        prev.includes(d) ? prev.filter((x) => x !== d) : [...prev, d]
                      )
                    }
                    className={`rounded-md px-2 py-1 text-[11px] font-semibold ${
                      active
                        ? "bg-emerald-500/20 text-emerald-300 ring-1 ring-emerald-500/40"
                        : "bg-zinc-900 text-zinc-400"
                    }`}
                  >
                    {d}
                  </button>
                );
              })}
            </div>
            <div className="grid grid-cols-2 gap-2">
              <input
                type="time"
                value={blockStart}
                onChange={(e) => setBlockStart(e.target.value)}
                className="rounded-lg border border-zinc-800 bg-zinc-900 px-2 py-1 text-xs text-zinc-100"
              />
              <input
                type="time"
                value={blockEnd}
                onChange={(e) => setBlockEnd(e.target.value)}
                className="rounded-lg border border-zinc-800 bg-zinc-900 px-2 py-1 text-xs text-zinc-100"
              />
            </div>
            <div className="flex justify-end gap-1.5">
              <button
                type="button"
                onClick={() => setShowBlockForm(false)}
                className="rounded-lg px-2.5 py-1 text-xs text-zinc-400 hover:text-zinc-200"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="rounded-lg bg-emerald-500 px-3 py-1 text-xs font-semibold text-zinc-950 hover:bg-emerald-400"
              >
                Save Block
              </button>
            </div>
          </form>
        )}

        {blocks.length > 0 && (
          <div className="mt-2.5 space-y-1.5">
            {blocks.map((blk) => (
              <div
                key={blk.id}
                className="flex items-center justify-between gap-2 rounded-xl border border-zinc-800/80 bg-zinc-950/70 px-2.5 py-1.5 text-xs"
              >
                <div className="min-w-0 flex-1">
                  <div className={`truncate font-medium ${blk.enabled ? "text-zinc-200" : "text-zinc-500 line-through"}`}>
                    {blk.label}
                  </div>
                  <div className="text-[10px] text-zinc-500">
                    {blk.days.join("")} {formatMinutesShort(blk.start_min)}–{formatMinutesShort(blk.end_min)}
                  </div>
                </div>
                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() => onToggleBlock(blk.id, !blk.enabled)}
                    className="rounded p-1 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
                    title={blk.enabled ? "Disable block" : "Enable block"}
                  >
                    {blk.enabled ? <Eye className="h-3.5 w-3.5 text-emerald-400" /> : <EyeOff className="h-3.5 w-3.5" />}
                  </button>
                  <button
                    type="button"
                    onClick={() => onDeleteBlock(blk.id)}
                    className="rounded p-1 text-zinc-400 hover:bg-rose-500/15 hover:text-rose-300"
                    title="Delete block"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
