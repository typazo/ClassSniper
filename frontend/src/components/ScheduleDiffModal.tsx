import React, { useEffect, useState } from "react";
import { ArrowLeftRight, Loader2, X } from "lucide-react";
import { api } from "../api/client";
import type { HydratedSchedule, ScheduleCourseItem, ScheduleSummary } from "../types";
import { computeScheduleDiagnostics } from "../utils/schedulerSolver";

interface Props {
  isOpen: boolean;
  active: HydratedSchedule;
  schedules: ScheduleSummary[];
  onClose: () => void;
}

function summarizePlan(sched: HydratedSchedule) {
  const enabled = sched.courses.filter((c) => c.enabled);
  const diag = computeScheduleDiagnostics(enabled, sched.blocks);
  let openSecs = 0;
  let totalSecs = 0;
  const workloads: number[] = [];
  for (const c of enabled) {
    if (c.cached_insights?.workload != null) {
      workloads.push(c.cached_insights.workload);
    }
    const sel = new Set(c.selected_class_nbrs);
    for (const eg of c.enroll_groups) {
      for (const s of eg.sections) {
        if (!sel.has(s.class_nbr)) continue;
        totalSecs += 1;
        if (s.open_status === "O") openSecs += 1;
      }
    }
  }
  const avgWorkload =
    workloads.length > 0
      ? Number((workloads.reduce((a, b) => a + b, 0) / workloads.length).toFixed(1))
      : null;
  return { enabled, diag, openSecs, totalSecs, avgWorkload };
}

function formatSelectedSections(course: ScheduleCourseItem): string {
  const chosen = new Set(course.selected_class_nbrs);
  const parts: string[] = [];
  for (const eg of course.enroll_groups) {
    for (const s of eg.sections) {
      if (chosen.has(s.class_nbr)) {
        parts.push(`${s.ssr_component} ${s.section} (#${s.class_nbr})`);
      }
    }
  }
  return parts.join(", ") || "No sections selected";
}

export function ScheduleDiffModal({ isOpen, active, schedules, onClose }: Props) {
  const others = schedules.filter((s) => s.id !== active.schedule.id);
  const [otherId, setOtherId] = useState<number>(() => others[0]?.id ?? 0);
  const [otherSchedule, setOtherSchedule] = useState<HydratedSchedule | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    if (!others.some((o) => o.id === otherId) && others.length > 0) {
      setOtherId(others[0].id);
    }
  }, [isOpen, schedules]);

  useEffect(() => {
    if (!isOpen || !otherId) {
      setOtherSchedule(null);
      return;
    }
    setLoading(true);
    api
      .getSchedule(otherId)
      .then((res) => setOtherSchedule(res))
      .catch(() => setOtherSchedule(null))
      .finally(() => setLoading(false));
  }, [isOpen, otherId]);

  if (!isOpen) return null;

  const leftStats = summarizePlan(active);
  const rightStats = otherSchedule ? summarizePlan(otherSchedule) : null;

  const leftByCode = new Map(
    leftStats.enabled.map((c) => [`${c.subject} ${c.catalog_nbr}`, c])
  );
  const rightByCode = new Map(
    (rightStats?.enabled || []).map((c) => [`${c.subject} ${c.catalog_nbr}`, c])
  );
  const allCodes = Array.from(new Set([...leftByCode.keys(), ...rightByCode.keys()])).sort();

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm">
      <div className="max-h-[88vh] w-full max-w-3xl overflow-y-auto rounded-2xl border border-zinc-800 bg-zinc-900 p-5 shadow-2xl">
        <div className="flex items-center justify-between gap-3 border-b border-zinc-800 pb-3">
          <div className="flex items-center gap-2">
            <ArrowLeftRight className="h-4 w-4 text-sky-400" />
            <h3 className="text-sm font-bold text-white">Compare Schedules</h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1 text-zinc-400 hover:bg-zinc-800 hover:text-white"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {others.length === 0 ? (
          <p className="py-8 text-center text-xs text-zinc-400">
            Create or duplicate a second schedule for {active.schedule.roster} to compare plans side by side.
          </p>
        ) : (
          <div className="mt-4 space-y-4">
            <div className="grid grid-cols-2 gap-3 text-xs">
              <div className="rounded-xl border border-emerald-500/35 bg-emerald-500/10 p-3">
                <div className="text-[10px] font-semibold uppercase tracking-wider text-emerald-300">
                  Plan A (Active)
                </div>
                <div className="mt-0.5 text-sm font-bold text-white">{active.schedule.name}</div>
              </div>
              <div className="rounded-xl border border-sky-500/35 bg-sky-500/10 p-3">
                <div className="text-[10px] font-semibold uppercase tracking-wider text-sky-300">
                  Plan B (Compare With)
                </div>
                <select
                  value={otherId}
                  onChange={(e) => setOtherId(Number(e.target.value))}
                  className="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-2.5 py-1 text-xs font-semibold text-white"
                >
                  {others.map((o) => (
                    <option key={o.id} value={o.id}>
                      {o.name}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {loading ? (
              <div className="flex items-center justify-center py-8 text-xs text-zinc-400">
                <Loader2 className="mr-2 h-4 w-4 animate-spin text-sky-400" />
                Loading comparison...
              </div>
            ) : (
              rightStats && (
                <>
                  <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 text-xs">
                    <div className="rounded-xl border border-zinc-800 bg-zinc-950 p-2.5">
                      <div className="text-[10px] text-zinc-400">Credits</div>
                      <div className="mt-0.5 font-semibold text-white">
                        {Number(leftStats.diag.totalCredits.toFixed(1))} vs{" "}
                        {Number(rightStats.diag.totalCredits.toFixed(1))}
                      </div>
                    </div>
                    <div className="rounded-xl border border-zinc-800 bg-zinc-950 p-2.5">
                      <div className="text-[10px] text-zinc-400">Open Sections</div>
                      <div className="mt-0.5 font-semibold text-white">
                        {leftStats.openSecs}/{leftStats.totalSecs} vs {rightStats.openSecs}/
                        {rightStats.totalSecs}
                      </div>
                    </div>
                    <div className="rounded-xl border border-zinc-800 bg-zinc-950 p-2.5">
                      <div className="text-[10px] text-zinc-400">Avg Workload</div>
                      <div className="mt-0.5 font-semibold text-white">
                        {leftStats.avgWorkload != null ? `${leftStats.avgWorkload}/5` : "—"} vs{" "}
                        {rightStats.avgWorkload != null ? `${rightStats.avgWorkload}/5` : "—"}
                      </div>
                    </div>
                    <div className="rounded-xl border border-zinc-800 bg-zinc-950 p-2.5">
                      <div className="text-[10px] text-zinc-400">Conflicts / Walks</div>
                      <div className="mt-0.5 font-semibold text-white">
                        {leftStats.diag.conflictCount}/{leftStats.diag.walkWarnings.length} vs{" "}
                        {rightStats.diag.conflictCount}/{rightStats.diag.walkWarnings.length}
                      </div>
                    </div>
                  </div>

                  <div className="divide-y divide-zinc-800 overflow-hidden rounded-xl border border-zinc-800 bg-zinc-950">
                    {allCodes.map((code) => {
                      const aCourse = leftByCode.get(code);
                      const bCourse = rightByCode.get(code);
                      const status =
                        aCourse && !bCourse
                          ? "Only in Plan A"
                          : !aCourse && bCourse
                            ? "Only in Plan B"
                            : formatSelectedSections(aCourse!) === formatSelectedSections(bCourse!)
                              ? "Identical"
                              : "Different sections";
                      const badgeCls =
                        status === "Only in Plan A"
                          ? "border-emerald-500/40 bg-emerald-500/15 text-emerald-300"
                          : status === "Only in Plan B"
                            ? "border-sky-500/40 bg-sky-500/15 text-sky-300"
                            : status === "Different sections"
                              ? "border-amber-500/40 bg-amber-500/15 text-amber-200"
                              : "border-zinc-700 bg-zinc-900 text-zinc-400";

                      return (
                        <div key={code} className="grid gap-2 px-3 py-2.5 text-xs sm:grid-cols-12">
                          <div className="sm:col-span-3">
                            <div className="font-bold text-white">{code}</div>
                            <span
                              className={`mt-1 inline-block rounded border px-1.5 py-0.5 text-[10px] font-medium ${badgeCls}`}
                            >
                              {status}
                            </span>
                          </div>
                          <div className="sm:col-span-4 text-[11px] text-zinc-300">
                            {aCourse ? formatSelectedSections(aCourse) : <span className="text-zinc-600">— Not in Plan A</span>}
                          </div>
                          <div className="sm:col-span-5 text-[11px] text-zinc-300">
                            {bCourse ? formatSelectedSections(bCourse) : <span className="text-zinc-600">— Not in Plan B</span>}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </>
              )
            )}
          </div>
        )}
      </div>
    </div>
  );
}
