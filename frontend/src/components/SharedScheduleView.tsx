import React, { useEffect, useMemo, useState } from "react";
import { ArrowLeft, Calendar, Crosshair, Download, Loader2 } from "lucide-react";
import { api } from "../api/client";
import type { HydratedSchedule } from "../types";
import { downloadScheduleICS } from "../utils/icsExport";
import {
  computeScheduleDiagnostics,
  getCourseColor,
} from "../utils/schedulerSolver";
import { StatusBadge } from "./StatusBadge";
import { WeeklyCalendarGrid } from "./WeeklyCalendarGrid";

interface Props {
  token: string;
  onExit: () => void;
}

export function SharedScheduleView({ token, onExit }: Props) {
  const [data, setData] = useState<HydratedSchedule | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await api.getSharedSchedule(token);
        if (!cancelled) setData(res);
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : "Shared schedule not found or sharing was disabled."
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token]);

  const diagnostics = useMemo(
    () => computeScheduleDiagnostics(data?.courses || [], data?.blocks || []),
    [data]
  );

  return (
    <div className="min-h-screen bg-zinc-950 pb-12 text-zinc-100">
      <header className="border-b border-zinc-800/80 bg-zinc-950/90 backdrop-blur-md">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-emerald-500/15 ring-1 ring-emerald-500/30">
              <Crosshair className="h-5 w-5 text-emerald-400" />
            </div>
            <div>
              <div className="text-sm font-bold text-white">ClassSniper Shared Schedule</div>
              <div className="text-[11px] text-zinc-400">Read-only snapshot</div>
            </div>
          </div>
          <button
            type="button"
            onClick={onExit}
            className="inline-flex items-center gap-1.5 rounded-xl border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-200 hover:bg-zinc-900"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Open ClassSniper
          </button>
        </div>
      </header>

      <main className="mx-auto mt-6 max-w-6xl px-4">
        {loading && (
          <div className="flex items-center justify-center rounded-2xl border border-zinc-800 bg-zinc-900/60 py-16 text-sm text-zinc-400">
            <Loader2 className="mr-2 h-4 w-4 animate-spin text-emerald-400" />
            Loading shared schedule...
          </div>
        )}

        {error && !loading && (
          <div className="rounded-2xl border border-rose-500/40 bg-rose-500/10 p-6 text-center">
            <p className="text-sm font-semibold text-rose-200">{error}</p>
            <button
              type="button"
              onClick={onExit}
              className="mt-4 rounded-xl bg-zinc-800 px-4 py-2 text-xs font-semibold text-white hover:bg-zinc-700"
            >
              Return to ClassSniper
            </button>
          </div>
        )}

        {data && !loading && (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-zinc-800 bg-zinc-900/80 p-4">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <h1 className="text-lg font-bold text-white">{data.schedule.name}</h1>
                  <span className="rounded-lg bg-emerald-500/15 px-2 py-0.5 text-xs font-semibold text-emerald-300">
                    {data.schedule.roster}
                  </span>
                </div>
                <p className="mt-0.5 text-xs text-zinc-400">
                  {data.owner_username ? `Shared by ${data.owner_username} · ` : ""}
                  <span className="inline-flex items-center gap-1 font-medium text-zinc-200">
                    <Calendar className="h-3 w-3 text-emerald-400" />
                    {diagnostics.totalCredits} Credits
                  </span>{" "}
                  &middot; {data.courses.filter((c) => c.enabled).length} courses
                </p>
              </div>

              <button
                type="button"
                onClick={() =>
                  downloadScheduleICS(data.schedule.name, data.schedule.roster, data.courses)
                }
                className="inline-flex items-center gap-1.5 rounded-xl border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-200 hover:bg-zinc-800"
              >
                <Download className="h-3.5 w-3.5" />
                Export .ics
              </button>
            </div>

            <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
              <div className="lg:col-span-8">
                <WeeklyCalendarGrid
                  courses={data.courses}
                  blocks={data.blocks}
                  diagnostics={diagnostics}
                  readOnly
                />
              </div>

              <div className="space-y-2.5 lg:col-span-4">
                {data.courses
                  .filter((c) => c.enabled)
                  .map((course) => {
                    const style = getCourseColor(course.color_idx);
                    const selSet = new Set(course.selected_class_nbrs);
                    const secs = course.enroll_groups.flatMap((eg) =>
                      eg.sections.filter((s) => selSet.has(s.class_nbr))
                    );
                    const cr =
                      course.selected_units != null
                        ? course.selected_units
                        : course.units_max || course.units_min;
                    return (
                      <div
                        key={course.id}
                        className="rounded-2xl border border-zinc-800 bg-zinc-900/80 p-3"
                      >
                        <div className="flex items-center gap-2">
                          <span className={`h-2.5 w-2.5 rounded-full ${style.dot}`} />
                          <span className="text-sm font-bold text-white">
                            {course.subject} {course.catalog_nbr}
                          </span>
                          <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] text-zinc-300">
                            {cr} cr
                          </span>
                        </div>
                        <div className="mt-0.5 text-xs text-zinc-400">{course.title_long}</div>
                        <div className="mt-2 space-y-1">
                          {secs.map((sec) => (
                            <div
                              key={sec.class_nbr}
                              className="flex items-center justify-between gap-2 rounded-lg border border-zinc-800 bg-zinc-950/80 px-2.5 py-1.5 text-xs"
                            >
                              <div className="min-w-0">
                                <div className="font-semibold text-zinc-200">
                                  {sec.ssr_component} {sec.section}{" "}
                                  <span className="font-mono text-[10px] text-zinc-500">
                                    #{sec.class_nbr}
                                  </span>
                                </div>
                                <div className="truncate text-[10px] text-zinc-400">
                                  {sec.meetings_summary}
                                </div>
                              </div>
                              <StatusBadge status={sec.open_status} />
                            </div>
                          ))}
                        </div>
                      </div>
                    );
                  })}
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
