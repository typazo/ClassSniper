import React, { useMemo, useRef, useState } from "react";
import { AlertTriangle, Clock, Footprints, Lock, X } from "lucide-react";
import type {
  DayCode,
  ScheduleBlock,
  ScheduleCourseItem,
  ScheduleSection,
} from "../types";
import {
  formatMinutesFull,
  formatMinutesShort,
  getCourseColor,
  type ScheduleDiagnostics,
} from "../utils/schedulerSolver";

const WEEKDAY_LABELS: Array<{ code: DayCode; short: string; full: string }> = [
  { code: "M", short: "Mon", full: "Monday" },
  { code: "T", short: "Tue", full: "Tuesday" },
  { code: "W", short: "Wed", full: "Wednesday" },
  { code: "R", short: "Thu", full: "Thursday" },
  { code: "F", short: "Fri", full: "Friday" },
  { code: "Sa", short: "Sat", full: "Saturday" },
  { code: "Su", short: "Sun", full: "Sunday" },
];

interface GridEvent {
  uid: string;
  kind: "course" | "block";
  day: DayCode;
  startMin: number;
  endMin: number;
  title: string;
  subtitle: string;
  room: string;
  openStatus?: string;
  colorIdx: number;
  classNbr?: number;
  blockId?: number;
  courseItemId?: number;
  isLocked?: boolean;
  isConflict: boolean;
  tightWalkWarning?: string;
}

interface PositionedEvent extends GridEvent {
  col: number;
  totalCols: number;
}

function layoutDayEvents(events: GridEvent[]): PositionedEvent[] {
  if (events.length === 0) return [];
  const sorted = [...events].sort(
    (a, b) => a.startMin - b.startMin || a.endMin - b.endMin
  );

  // Connected overlap clusters
  const clusters: GridEvent[][] = [];
  let currentCluster: GridEvent[] = [];
  let clusterEnd = -1;

  for (const ev of sorted) {
    if (currentCluster.length === 0 || ev.startMin < clusterEnd) {
      currentCluster.push(ev);
      clusterEnd = Math.max(clusterEnd, ev.endMin);
    } else {
      clusters.push(currentCluster);
      currentCluster = [ev];
      clusterEnd = ev.endMin;
    }
  }
  if (currentCluster.length > 0) clusters.push(currentCluster);

  const positioned: PositionedEvent[] = [];
  for (const cluster of clusters) {
    const colEndTimes: number[] = [];
    const assigned: Array<{ ev: GridEvent; col: number }> = [];

    for (const ev of cluster) {
      let colIdx = colEndTimes.findIndex((end) => end <= ev.startMin);
      if (colIdx === -1) {
        colIdx = colEndTimes.length;
        colEndTimes.push(ev.endMin);
      } else {
        colEndTimes[colIdx] = ev.endMin;
      }
      assigned.push({ ev, col: colIdx });
    }

    const totalCols = Math.max(1, colEndTimes.length);
    for (const item of assigned) {
      positioned.push({
        ...item.ev,
        col: item.col,
        totalCols,
      });
    }
  }

  return positioned;
}

function statusDotClass(status?: string): string {
  switch ((status || "").toUpperCase()) {
    case "O":
      return "bg-emerald-400";
    case "W":
      return "bg-amber-400";
    case "C":
      return "bg-rose-400";
    default:
      return "bg-zinc-400";
  }
}

interface Props {
  courses: ScheduleCourseItem[];
  blocks: ScheduleBlock[];
  diagnostics: ScheduleDiagnostics;
  hoverPreview?: {
    course: ScheduleCourseItem;
    section: ScheduleSection;
    conflicts: boolean;
  } | null;
  readOnly?: boolean;
  onClickCourseSection?: (courseItemId: number, classNbr: number) => void;
  onDeleteBlock?: (blockId: number) => void;
  onCreateBlock?: (payload: { days: DayCode[]; startMin: number; endMin: number }) => void;
}

const HOUR_HEIGHT_PX = 54;

export function WeeklyCalendarGrid({
  courses,
  blocks,
  diagnostics,
  hoverPreview,
  readOnly = false,
  onClickCourseSection,
  onDeleteBlock,
  onCreateBlock,
}: Props) {
  const [mobileDayFilter, setMobileDayFilter] = useState<"all" | DayCode>("all");
  const [dragState, setDragState] = useState<{
    day: DayCode;
    anchorMin: number;
    currentMin: number;
  } | null>(null);
  const gridBodyRef = useRef<HTMLDivElement | null>(null);

  const {
    visibleDays,
    startHour,
    endHour,
    eventsByDay,
    tbaSections,
  } = useMemo(() => {
    const activeCourses = courses.filter((c) => c.enabled);
    const activeBlocks = blocks.filter((b) => b.enabled);
    const hasSat =
      activeCourses.some((c) =>
        c.enroll_groups.some((eg) =>
          eg.sections.some(
            (s) =>
              c.selected_class_nbrs.includes(s.class_nbr) &&
              s.meetings.some((m) => m.days.includes("Sa"))
          )
        )
      ) || activeBlocks.some((b) => b.days.includes("Sa"));
    const hasSun =
      activeCourses.some((c) =>
        c.enroll_groups.some((eg) =>
          eg.sections.some(
            (s) =>
              c.selected_class_nbrs.includes(s.class_nbr) &&
              s.meetings.some((m) => m.days.includes("Su"))
          )
        )
      ) || activeBlocks.some((b) => b.days.includes("Su"));

    const daysList = WEEKDAY_LABELS.filter(
      (d) =>
        (d.code !== "Sa" && d.code !== "Su") ||
        (d.code === "Sa" && hasSat) ||
        (d.code === "Su" && hasSun)
    );

    const rawEvents: GridEvent[] = [];
    const tba: Array<{ course: ScheduleCourseItem; section: ScheduleSection }> = [];
    let minM = 8 * 60;
    let maxM = 18 * 60;

    const walkMap = new Map<string, string>();
    for (const w of diagnostics.walkWarnings) {
      walkMap.set(
        `${w.day}|${w.toCourse}|${w.startMin}`,
        `~${w.walkMin}m walk from ${w.fromBuilding} (${w.gapMin}m gap)`
      );
    }

    for (const course of activeCourses) {
      const selectedSet = new Set(course.selected_class_nbrs);
      const lockedSet = new Set(course.locked_class_nbrs);
      for (const eg of course.enroll_groups) {
        for (const sec of eg.sections) {
          if (!selectedSet.has(sec.class_nbr)) continue;
          if (sec.meetings.length === 0) {
            tba.push({ course, section: sec });
            continue;
          }
          for (const mtg of sec.meetings) {
            minM = Math.min(minM, mtg.start_min);
            maxM = Math.max(maxM, mtg.end_min);
            for (const day of mtg.days) {
              const walkNote = walkMap.get(
                `${day}|${course.subject} ${course.catalog_nbr}|${mtg.start_min}`
              );
              rawEvents.push({
                uid: `c-${course.id}-${sec.class_nbr}-${day}-${mtg.start_min}`,
                kind: "course",
                day,
                startMin: mtg.start_min,
                endMin: mtg.end_min,
                title: `${course.subject} ${course.catalog_nbr}`,
                subtitle: `${sec.ssr_component} ${sec.section}`,
                room: mtg.facility_descr || sec.instruction_mode || "",
                openStatus: sec.open_status,
                colorIdx: course.color_idx,
                classNbr: sec.class_nbr,
                courseItemId: course.id,
                isLocked: lockedSet.has(sec.class_nbr),
                isConflict: diagnostics.conflictingClassNbrs.has(sec.class_nbr),
                tightWalkWarning: walkNote,
              });
            }
          }
        }
      }
    }

    for (const blk of activeBlocks) {
      minM = Math.min(minM, blk.start_min);
      maxM = Math.max(maxM, blk.end_min);
      for (const day of blk.days) {
        rawEvents.push({
          uid: `b-${blk.id}-${day}-${blk.start_min}`,
          kind: "block",
          day,
          startMin: blk.start_min,
          endMin: blk.end_min,
          title: blk.label,
          subtitle: "Busy Time",
          room: "",
          colorIdx: 0,
          blockId: blk.id,
          isConflict: diagnostics.conflictingBlockIds.has(blk.id),
        });
      }
    }

    if (hoverPreview) {
      for (const mtg of hoverPreview.section.meetings) {
        minM = Math.min(minM, mtg.start_min);
        maxM = Math.max(maxM, mtg.end_min);
      }
    }

    const sHour = Math.max(6, Math.floor(minM / 60));
    const eHour = Math.min(23, Math.ceil(maxM / 60));

    const map = new Map<DayCode, PositionedEvent[]>();
    for (const d of daysList) {
      const dayRaw = rawEvents.filter((ev) => ev.day === d.code);
      map.set(d.code, layoutDayEvents(dayRaw));
    }

    return {
      visibleDays: daysList,
      startHour: sHour,
      endHour: Math.max(sHour + 4, eHour),
      eventsByDay: map,
      tbaSections: tba,
    };
  }, [courses, blocks, diagnostics, hoverPreview]);

  const hours = useMemo(() => {
    const arr: number[] = [];
    for (let h = startHour; h < endHour; h += 1) arr.push(h);
    return arr;
  }, [startHour, endHour]);

  const gridStartMin = startHour * 60;
  const totalMinutes = (endHour - startHour) * 60;
  const totalHeightPx = (endHour - startHour) * HOUR_HEIGHT_PX;

  const yToMinutes = (clientY: number): number => {
    const el = gridBodyRef.current;
    if (!el) return gridStartMin;
    const rect = el.getBoundingClientRect();
    const relY = Math.max(0, Math.min(rect.height, clientY - rect.top));
    const rawMin = gridStartMin + (relY / rect.height) * totalMinutes;
    const snapped = Math.round(rawMin / 15) * 15;
    return Math.max(gridStartMin, Math.min(endHour * 60, snapped));
  };

  const handleColumnPointerDown = (day: DayCode, e: React.PointerEvent<HTMLDivElement>) => {
    if (readOnly || !onCreateBlock) return;
    if ((e.target as HTMLElement).closest("[data-grid-event='true']")) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    const start = yToMinutes(e.clientY);
    setDragState({ day, anchorMin: start, currentMin: Math.min(endHour * 60, start + 30) });
  };

  const handleColumnPointerMove = (day: DayCode, e: React.PointerEvent<HTMLDivElement>) => {
    if (!dragState || dragState.day !== day) return;
    setDragState({ ...dragState, currentMin: yToMinutes(e.clientY) });
  };

  const handleColumnPointerUp = (day: DayCode) => {
    if (!dragState || dragState.day !== day || !onCreateBlock) return;
    const s = Math.min(dragState.anchorMin, dragState.currentMin);
    const e = Math.max(dragState.anchorMin, dragState.currentMin);
    setDragState(null);
    if (e - s >= 15) {
      onCreateBlock({ days: [day], startMin: s, endMin: e });
    }
  };

  const shownDays =
    mobileDayFilter === "all"
      ? visibleDays
      : visibleDays.filter((d) => d.code === mobileDayFilter);

  return (
    <div className="space-y-3">
      {/* Mobile Day Filter Pills */}
      <div className="flex items-center justify-between gap-2 sm:hidden">
        <div className="flex flex-wrap gap-1">
          <button
            type="button"
            onClick={() => setMobileDayFilter("all")}
            className={`rounded-lg px-2.5 py-1 text-xs font-medium ${
              mobileDayFilter === "all"
                ? "bg-emerald-500/20 text-emerald-300 ring-1 ring-emerald-500/40"
                : "bg-zinc-900 text-zinc-400"
            }`}
          >
            All
          </button>
          {visibleDays.map((d) => (
            <button
              key={d.code}
              type="button"
              onClick={() => setMobileDayFilter(d.code)}
              className={`rounded-lg px-2.5 py-1 text-xs font-medium ${
                mobileDayFilter === d.code
                  ? "bg-emerald-500/20 text-emerald-300 ring-1 ring-emerald-500/40"
                  : "bg-zinc-900 text-zinc-400"
              }`}
            >
              {d.short}
            </button>
          ))}
        </div>
      </div>

      {/* Calendar Container */}
      <div className="overflow-x-auto rounded-2xl border border-zinc-800 bg-zinc-900/75 shadow-inner">
        <div className={mobileDayFilter === "all" ? "min-w-[640px]" : "min-w-full"}>
          {/* Day Headers */}
          <div
            className="grid border-b border-zinc-800 bg-zinc-950/60"
            style={{
              gridTemplateColumns: `56px repeat(${shownDays.length}, minmax(0, 1fr))`,
            }}
          >
            <div className="flex items-center justify-center border-r border-zinc-800/80 py-2 text-[10px] font-medium uppercase tracking-wider text-zinc-500">
              Time
            </div>
            {shownDays.map((d) => (
              <div
                key={d.code}
                className="border-r border-zinc-800/60 py-2 text-center text-xs font-semibold text-zinc-200 last:border-r-0"
              >
                {d.short}
              </div>
            ))}
          </div>

          {/* Grid Body */}
          <div
            ref={gridBodyRef}
            className="relative grid select-none"
            style={{
              height: `${totalHeightPx}px`,
              gridTemplateColumns: `56px repeat(${shownDays.length}, minmax(0, 1fr))`,
            }}
          >
            {/* Hour Gutter */}
            <div className="relative border-r border-zinc-800/80 bg-zinc-950/35">
              {hours.map((h) => {
                const topPx = (h - startHour) * HOUR_HEIGHT_PX;
                const label =
                  h === 12 ? "12 PM" : h > 12 ? `${h - 12} PM` : `${h} AM`;
                return (
                  <div
                    key={h}
                    className="absolute inset-x-0 flex items-start justify-end pr-2 text-[10px] font-medium text-zinc-500"
                    style={{ top: `${topPx + 2}px` }}
                  >
                    {label}
                  </div>
                );
              })}
            </div>

            {/* Day Columns */}
            {shownDays.map((d) => {
              const dayEvents = eventsByDay.get(d.code) || [];
              const ghostMeetings =
                hoverPreview?.section.meetings.filter((m) => m.days.includes(d.code)) || [];

              return (
                <div
                  key={d.code}
                  onPointerDown={(e) => handleColumnPointerDown(d.code, e)}
                  onPointerMove={(e) => handleColumnPointerMove(d.code, e)}
                  onPointerUp={() => handleColumnPointerUp(d.code)}
                  className={`relative border-r border-zinc-800/60 last:border-r-0 ${
                    !readOnly && onCreateBlock ? "cursor-crosshair" : ""
                  }`}
                >
                  {/* Hour Horizontal Lines */}
                  {hours.map((h, idx) => (
                    <React.Fragment key={h}>
                      {idx > 0 && (
                        <div
                          className="pointer-events-none absolute inset-x-0 border-t border-zinc-800/70"
                          style={{ top: `${idx * HOUR_HEIGHT_PX}px` }}
                        />
                      )}
                      <div
                        className="pointer-events-none absolute inset-x-0 border-t border-dashed border-zinc-800/35"
                        style={{ top: `${idx * HOUR_HEIGHT_PX + HOUR_HEIGHT_PX / 2}px` }}
                      />
                    </React.Fragment>
                  ))}

                  {/* Drag-to-Create Busy Block Overlay */}
                  {dragState && dragState.day === d.code && (
                    <div
                      className="pointer-events-none absolute inset-x-1 z-20 rounded-lg border-2 border-dashed border-amber-400 bg-amber-500/20 px-1.5 py-0.5 text-[10px] font-semibold text-amber-200"
                      style={{
                        top: `${
                          ((Math.min(dragState.anchorMin, dragState.currentMin) - gridStartMin) /
                            totalMinutes) *
                          100
                        }%`,
                        height: `${
                          (Math.max(15, Math.abs(dragState.currentMin - dragState.anchorMin)) /
                            totalMinutes) *
                          100
                        }%`,
                      }}
                    >
                      Busy{" "}
                      {formatMinutesShort(Math.min(dragState.anchorMin, dragState.currentMin))}–
                      {formatMinutesShort(Math.max(dragState.anchorMin, dragState.currentMin))}
                    </div>
                  )}

                  {/* Scheduled Course & Busy Blocks */}
                  {dayEvents.map((ev) => {
                    const topPct = ((ev.startMin - gridStartMin) / totalMinutes) * 100;
                    const heightPct = Math.max(
                      2.8,
                      ((ev.endMin - ev.startMin) / totalMinutes) * 100
                    );
                    const widthPct = 100 / ev.totalCols;
                    const leftPct = ev.col * widthPct;
                    const style = getCourseColor(ev.colorIdx);

                    if (ev.kind === "block") {
                      return (
                        <div
                          key={ev.uid}
                          data-grid-event="true"
                          style={{
                            top: `${topPct}%`,
                            height: `${heightPct}%`,
                            left: `calc(${leftPct}% + 2px)`,
                            width: `calc(${widthPct}% - 4px)`,
                          }}
                          className={`group absolute z-10 overflow-hidden rounded-lg border px-1.5 py-1 text-[10px] ${
                            ev.isConflict
                              ? "border-rose-400/80 bg-rose-500/20 text-rose-100"
                              : "border-zinc-600/80 bg-zinc-800/85 text-zinc-200"
                          }`}
                        >
                          <div className="flex items-start justify-between gap-1">
                            <span className="truncate font-semibold">{ev.title}</span>
                            {!readOnly && onDeleteBlock && ev.blockId != null && (
                              <button
                                type="button"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  onDeleteBlock(ev.blockId!);
                                }}
                                title="Remove busy block"
                                className="rounded p-0.5 text-zinc-400 opacity-75 hover:bg-zinc-700 hover:text-white group-hover:opacity-100"
                              >
                                <X className="h-2.5 w-2.5" />
                              </button>
                            )}
                          </div>
                          <div className="truncate text-[9px] text-zinc-400">
                            {formatMinutesShort(ev.startMin)}–{formatMinutesShort(ev.endMin)}
                          </div>
                        </div>
                      );
                    }

                    const duration = ev.endMin - ev.startMin;
                    const isCompact = duration < 60;

                    return (
                      <div
                        key={ev.uid}
                        data-grid-event="true"
                        role={onClickCourseSection ? "button" : undefined}
                        tabIndex={onClickCourseSection ? 0 : undefined}
                        onClick={() => {
                          if (onClickCourseSection && ev.courseItemId && ev.classNbr) {
                            onClickCourseSection(ev.courseItemId, ev.classNbr);
                          }
                        }}
                        title={`${ev.title} (${ev.subtitle}) #${ev.classNbr}\n${formatMinutesFull(
                          ev.startMin
                        )} – ${formatMinutesFull(ev.endMin)}${ev.room ? `\n${ev.room}` : ""}${
                          ev.tightWalkWarning ? `\n⚠ ${ev.tightWalkWarning}` : ""
                        }`}
                        style={{
                          top: `${topPct}%`,
                          height: `${heightPct}%`,
                          left: `calc(${leftPct}% + 2px)`,
                          width: `calc(${widthPct}% - 4px)`,
                        }}
                        className={`absolute z-10 flex flex-col justify-between overflow-hidden rounded-lg border px-1.5 py-1 transition-all ${
                          ev.isConflict
                            ? "border-rose-400 bg-rose-500/25 text-rose-50 ring-1 ring-rose-400/60"
                            : `${style.border} ${style.bg} ${style.text}`
                        } ${onClickCourseSection ? "cursor-pointer hover:brightness-110" : ""}`}
                      >
                        <div className="min-w-0">
                          <div className="flex items-center justify-between gap-1">
                            <span className="truncate text-[11px] font-bold leading-tight">
                              {ev.title}
                            </span>
                            <div className="flex shrink-0 items-center gap-0.5">
                              {ev.tightWalkWarning && (
                                <span title={ev.tightWalkWarning}>
                                  <Footprints className="h-2.5 w-2.5 text-amber-300" />
                                </span>
                              )}
                              {ev.isConflict && (
                                <AlertTriangle className="h-2.5 w-2.5 text-rose-300" />
                              )}
                              {ev.isLocked && <Lock className="h-2.5 w-2.5 opacity-80" />}
                              <span
                                className={`h-1.5 w-1.5 rounded-full ${statusDotClass(
                                  ev.openStatus
                                )}`}
                                title={`Status: ${ev.openStatus}`}
                              />
                            </div>
                          </div>
                          <div className="truncate text-[10px] opacity-90">
                            {ev.subtitle}
                            {isCompact ? ` · ${formatMinutesShort(ev.startMin)}` : ""}
                          </div>
                        </div>

                        {!isCompact && (
                          <div className="min-w-0 text-[9px] leading-tight opacity-80">
                            <div className="truncate">
                              {formatMinutesShort(ev.startMin)}–{formatMinutesShort(ev.endMin)}
                            </div>
                            {ev.room && <div className="truncate">{ev.room}</div>}
                          </div>
                        )}
                      </div>
                    );
                  })}

                  {/* Ghost Hover-Preview Layer */}
                  {hoverPreview &&
                    ghostMeetings.map((mtg, idx) => {
                      const topPct = ((mtg.start_min - gridStartMin) / totalMinutes) * 100;
                      const heightPct = Math.max(
                        2.8,
                        ((mtg.end_min - mtg.start_min) / totalMinutes) * 100
                      );
                      return (
                        <div
                          key={`ghost-${idx}`}
                          style={{
                            top: `${topPct}%`,
                            height: `${heightPct}%`,
                            left: "3px",
                            width: "calc(100% - 6px)",
                          }}
                          className={`pointer-events-none absolute z-20 rounded-lg border-2 border-dashed px-1.5 py-1 backdrop-blur-[1px] ${
                            hoverPreview.conflicts
                              ? "border-rose-400 bg-rose-500/25 text-rose-100"
                              : "border-emerald-300 bg-emerald-500/25 text-emerald-50"
                          }`}
                        >
                          <div className="truncate text-[11px] font-bold">
                            {hoverPreview.course.subject} {hoverPreview.course.catalog_nbr}{" "}
                            {hoverPreview.section.ssr_component} {hoverPreview.section.section}
                          </div>
                          <div className="truncate text-[9px]">
                            {hoverPreview.conflicts ? "Conflicts with schedule" : "Preview · fits cleanly"}
                          </div>
                        </div>
                      );
                    })}
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Drag Hint */}
      {!readOnly && onCreateBlock && (
        <p className="text-[11px] text-zinc-500">
          Tip: Click and drag on any empty time slot in the calendar to add a Busy / Blocked period.
        </p>
      )}

      {/* Unscheduled / TBA / Online Asynchronous Tray */}
      {tbaSections.length > 0 && (
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-3">
          <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-zinc-300">
            <Clock className="h-3.5 w-3.5 text-zinc-400" />
            TBA / Asynchronous Sections ({tbaSections.length})
          </div>
          <div className="flex flex-wrap gap-2">
            {tbaSections.map(({ course, section }) => {
              const style = getCourseColor(course.color_idx);
              return (
                <div
                  key={`${course.id}-${section.class_nbr}`}
                  className={`inline-flex items-center gap-2 rounded-lg border px-2.5 py-1.5 text-xs ${style.border} ${style.bg} ${style.text}`}
                >
                  <span className={`h-2 w-2 rounded-full ${statusDotClass(section.open_status)}`} />
                  <span className="font-semibold">
                    {course.subject} {course.catalog_nbr} {section.ssr_component} {section.section}
                  </span>
                  <span className="text-[11px] opacity-80">#{section.class_nbr}</span>
                  {section.instruction_mode && (
                    <span className="rounded bg-black/25 px-1.5 py-0.5 text-[10px]">
                      {section.instruction_mode}
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
