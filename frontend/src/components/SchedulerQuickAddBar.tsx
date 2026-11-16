import React, { useEffect, useRef, useState } from "react";
import { Copy, Loader2, Lock, Search } from "lucide-react";
import { api } from "../api/client";
import type { CourseSummary, ScheduleCourseItem } from "../types";

interface Props {
  roster: string;
  isTranscriptSchedule: boolean;
  courses: ScheduleCourseItem[];
  addingCourseKey: string | null;
  quickInputRef: React.RefObject<HTMLInputElement>;
  onAddCourse: (subject: string, catalogNbr: string) => void;
  onDuplicateToEditable: () => void;
  onJumpToSearch: () => void;
}

export function SchedulerQuickAddBar({
  roster,
  isTranscriptSchedule,
  courses,
  addingCourseKey,
  quickInputRef,
  onAddCourse,
  onDuplicateToEditable,
  onJumpToSearch,
}: Props) {
  const [quickQuery, setQuickQuery] = useState("");
  const [quickResults, setQuickResults] = useState<CourseSummary[]>([]);
  const [quickLoading, setQuickLoading] = useState(false);
  const debounceRef = useRef<number | null>(null);
  const reqSeqRef = useRef(0);

  useEffect(() => {
    setQuickQuery("");
    setQuickResults([]);
    setQuickLoading(false);
    reqSeqRef.current += 1;
  }, [roster, isTranscriptSchedule]);

  useEffect(() => {
    if (debounceRef.current) {
      window.clearTimeout(debounceRef.current);
    }
    const trimmed = quickQuery.trim();
    if (!trimmed || !roster || isTranscriptSchedule) {
      reqSeqRef.current += 1;
      setQuickResults([]);
      setQuickLoading(false);
      return;
    }
    const seq = ++reqSeqRef.current;
    setQuickLoading(true);
    debounceRef.current = window.setTimeout(async () => {
      try {
        const res = await api.searchCourses(roster, trimmed, {
          limit: 8,
          ithaca_or_virtual: false,
          refresh_stale: true,
        });
        if (reqSeqRef.current === seq) {
          setQuickResults(res.courses);
        }
      } catch {
        if (reqSeqRef.current === seq) {
          setQuickResults([]);
        }
      } finally {
        if (reqSeqRef.current === seq) {
          setQuickLoading(false);
        }
      }
    }, 220);

    return () => {
      if (debounceRef.current) window.clearTimeout(debounceRef.current);
    };
  }, [quickQuery, roster, isTranscriptSchedule]);

  if (isTranscriptSchedule) {
    return (
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-sky-500/30 bg-sky-500/5 px-3.5 py-2.5 text-xs">
        <div className="flex items-center gap-2 text-zinc-300">
          <Lock className="h-4 w-4 shrink-0 text-sky-400" />
          <span>
            <strong className="text-sky-200">Transcript schedule courses are locked.</strong>{" "}
            You can still swap <strong className="text-white">LEC / DIS / LAB</strong> sections, pin times, add busy blocks, and run Auto-Generate.
          </span>
        </div>
        <button
          type="button"
          onClick={onDuplicateToEditable}
          className="inline-flex shrink-0 items-center gap-1.5 rounded-xl border border-sky-500/45 bg-sky-500/15 px-3 py-1.5 font-semibold text-sky-200 hover:bg-sky-500/25"
        >
          <Copy className="h-3.5 w-3.5" />
          Duplicate to Editable Plan
        </button>
      </div>
    );
  }

  return (
    <div className="relative rounded-2xl border border-zinc-800 bg-zinc-900/70 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-[220px] flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-500" />
          <input
            ref={quickInputRef}
            type="text"
            value={quickQuery}
            onChange={(e) => setQuickQuery(e.target.value)}
            placeholder={`Quick-add course to ${roster || "schedule"} (e.g. CS 2110, Algorithms, 6582)...`}
            className="w-full rounded-xl border border-zinc-800 bg-zinc-950 py-2 pl-9 pr-3 text-xs text-white placeholder-zinc-500 focus:border-emerald-500/60 focus:outline-none"
          />
          {quickLoading && (
            <Loader2 className="absolute right-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 animate-spin text-emerald-400" />
          )}
        </div>
        <button
          type="button"
          onClick={onJumpToSearch}
          className="rounded-xl border border-zinc-700 px-3 py-2 text-xs font-medium text-zinc-300 hover:border-emerald-500/50 hover:text-emerald-300"
        >
          Full Filter Search →
        </button>
      </div>

      {quickResults.length > 0 && (
        <div className="mt-2 max-h-64 divide-y divide-zinc-800/80 overflow-y-auto rounded-xl border border-zinc-800 bg-zinc-950">
          {quickResults.map((c) => {
            const key = `${c.subject}-${c.catalog_nbr}`;
            const alreadyAdded = courses.some(
              (sc) => sc.subject === c.subject && sc.catalog_nbr === c.catalog_nbr
            );
            const openCount = c.sections.filter((s) => s.open_status === "O").length;
            return (
              <div
                key={key}
                className="flex items-center justify-between gap-3 px-3 py-2 text-xs hover:bg-zinc-900/80"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="font-bold text-white">
                      {c.subject} {c.catalog_nbr}
                    </span>
                    <span className="text-zinc-300">{c.title_long}</span>
                    <span className="text-[10px] text-zinc-500">
                      {openCount}/{c.sections.length} open
                    </span>
                  </div>
                </div>
                <button
                  type="button"
                  disabled={alreadyAdded || addingCourseKey === key}
                  onClick={() => {
                    setQuickQuery("");
                    setQuickResults([]);
                    onAddCourse(c.subject, c.catalog_nbr);
                  }}
                  className={`shrink-0 rounded-lg px-2.5 py-1 text-[11px] font-semibold ${
                    alreadyAdded
                      ? "bg-zinc-800 text-zinc-400"
                      : "bg-emerald-500/20 text-emerald-300 ring-1 ring-emerald-500/40 hover:bg-emerald-500/30"
                  }`}
                >
                  {alreadyAdded
                    ? "In Schedule"
                    : addingCourseKey === key
                      ? "Adding..."
                      : "+ Add"}
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
