import React, { useEffect, useMemo, useState } from "react";
import {
  Check,
  ChevronLeft,
  ChevronRight,
  Footprints,
  Sparkles,
  X,
} from "lucide-react";
import type { ScheduleBlock, ScheduleCourseItem } from "../types";
import {
  formatMinutesFull,
  solveSchedules,
  type GeneratedScheduleCandidate,
  type SolverRankMode,
  type SolverSeatMode,
} from "../utils/schedulerSolver";

interface Props {
  courses: ScheduleCourseItem[];
  blocks: ScheduleBlock[];
  onPreviewCandidate: (candidate: GeneratedScheduleCandidate | null) => void;
  onApplyCandidate: (candidate: GeneratedScheduleCandidate) => Promise<void>;
  onClose: () => void;
}

export function ScheduleGeneratorPanel({
  courses,
  blocks,
  onPreviewCandidate,
  onApplyCandidate,
  onClose,
}: Props) {
  const [seatMode, setSeatMode] = useState<SolverSeatMode>("all");
  const [rankMode, setRankMode] = useState<SolverRankMode>("fewest_closed");
  const [ithacaOrVirtualOnly, setIthacaOrVirtualOnly] = useState(true);
  const [avoidTightWalks, setAvoidTightWalks] = useState(false);
  const [selectedIdx, setSelectedIdx] = useState(0);
  const [applying, setApplying] = useState(false);

  const result = useMemo(
    () =>
      solveSchedules(courses, blocks, {
        seatMode,
        rankMode,
        ithacaOrVirtualOnly,
        avoidTightWalks,
        maxResults: 50,
      }),
    [courses, blocks, seatMode, rankMode, ithacaOrVirtualOnly, avoidTightWalks]
  );

  useEffect(() => {
    setSelectedIdx(0);
  }, [seatMode, rankMode, ithacaOrVirtualOnly, avoidTightWalks, courses, blocks]);

  const currentCandidate = result.candidates[selectedIdx] ?? null;

  useEffect(() => {
    onPreviewCandidate(currentCandidate);
  }, [currentCandidate, onPreviewCandidate]);

  useEffect(() => {
    return () => {
      onPreviewCandidate(null);
    };
  }, [onPreviewCandidate]);

  const handleApply = async () => {
    if (!currentCandidate) return;
    setApplying(true);
    try {
      await onApplyCandidate(currentCandidate);
      onClose();
    } finally {
      setApplying(false);
    }
  };

  return (
    <div className="rounded-2xl border border-emerald-500/40 bg-zinc-900/95 p-4 shadow-lg">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-500/15 text-emerald-300">
            <Sparkles className="h-4 w-4" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-white">Auto-Schedule Generator</h3>
            <p className="text-[11px] text-zinc-400">
              Respects pinned sections (<span className="text-amber-300">Lock</span>), Busy blocks, and enrollGroups · Runs locally in{" "}
              {result.elapsedMs}ms
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => {
            onPreviewCandidate(null);
            onClose();
          }}
          className="inline-flex items-center gap-1 rounded-lg border border-zinc-700 px-2.5 py-1 text-xs text-zinc-300 hover:bg-zinc-800"
        >
          <X className="h-3.5 w-3.5" />
          Close
        </button>
      </div>

      {/* Controls */}
      <div className="mt-3 grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-zinc-400">
            Seat Status Filter
          </label>
          <select
            value={seatMode}
            onChange={(e) => setSeatMode(e.target.value as SolverSeatMode)}
            className="w-full rounded-xl border border-zinc-700 bg-zinc-950 px-2.5 py-1.5 text-xs text-zinc-100"
          >
            <option value="all">Include Closed (Watch Ready)</option>
            <option value="open_or_waitlist">Open + Waitlist Only</option>
            <option value="open">Open Seats Only</option>
          </select>
        </div>

        <div>
          <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-zinc-400">
            Optimize For
          </label>
          <select
            value={rankMode}
            onChange={(e) => setRankMode(e.target.value as SolverRankMode)}
            className="w-full rounded-xl border border-zinc-700 bg-zinc-950 px-2.5 py-1.5 text-xs text-zinc-100"
          >
            <option value="fewest_closed">Fewest Closed Sections</option>
            <option value="compact">Compact (Least Idle Gap)</option>
            <option value="spread">Spread Out (Breaks Between)</option>
            <option value="late_start">Latest Morning Start</option>
            <option value="early_end">Earliest Finish</option>
          </select>
        </div>

        <label className="flex cursor-pointer items-center gap-2 rounded-xl border border-zinc-800 bg-zinc-950/70 px-3 py-2 text-xs text-zinc-200">
          <input
            type="checkbox"
            checked={ithacaOrVirtualOnly}
            onChange={(e) => setIthacaOrVirtualOnly(e.target.checked)}
            className="rounded border-zinc-600 bg-zinc-900 text-emerald-500"
          />
          Ithaca / Virtual only
        </label>

        <label className="flex cursor-pointer items-center gap-2 rounded-xl border border-zinc-800 bg-zinc-950/70 px-3 py-2 text-xs text-zinc-200">
          <input
            type="checkbox"
            checked={avoidTightWalks}
            onChange={(e) => setAvoidTightWalks(e.target.checked)}
            className="rounded border-zinc-600 bg-zinc-900 text-emerald-500"
          />
          <Footprints className="h-3.5 w-3.5 text-amber-300" />
          Avoid tight walks
        </label>
      </div>

      {/* Results Navigation Bar */}
      <div className="mt-3 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-zinc-800 bg-zinc-950/80 px-3 py-2.5">
        {result.blockingIssue || !currentCandidate ? (
          <div className="text-xs text-amber-300">
            {result.blockingIssue || "No valid schedule combinations found."}
          </div>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-2">
              <div className="inline-flex items-center gap-1 rounded-lg border border-zinc-700 bg-zinc-900 p-0.5">
                <button
                  type="button"
                  disabled={selectedIdx <= 0}
                  onClick={() => setSelectedIdx((i) => Math.max(0, i - 1))}
                  className="rounded-md p-1 text-zinc-300 hover:bg-zinc-800 disabled:opacity-40"
                >
                  <ChevronLeft className="h-4 w-4" />
                </button>
                <span className="px-2 text-xs font-semibold text-white">
                  Plan {selectedIdx + 1} / {result.candidates.length}
                  {result.totalFound > result.candidates.length
                    ? ` (${result.totalFound}${result.truncated ? "+" : ""} total)`
                    : ""}
                </span>
                <button
                  type="button"
                  disabled={selectedIdx >= result.candidates.length - 1}
                  onClick={() =>
                    setSelectedIdx((i) => Math.min(result.candidates.length - 1, i + 1))
                  }
                  className="rounded-md p-1 text-zinc-300 hover:bg-zinc-800 disabled:opacity-40"
                >
                  <ChevronRight className="h-4 w-4" />
                </button>
              </div>

              <div className="flex flex-wrap items-center gap-2 text-[11px] text-zinc-300">
                <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 text-emerald-300">
                  {currentCandidate.openCount} Open
                </span>
                {currentCandidate.waitlistCount > 0 && (
                  <span className="rounded bg-amber-500/15 px-1.5 py-0.5 text-amber-300">
                    {currentCandidate.waitlistCount} Waitlist
                  </span>
                )}
                {currentCandidate.closedCount > 0 && (
                  <span className="rounded bg-rose-500/15 px-1.5 py-0.5 text-rose-300">
                    {currentCandidate.closedCount} Closed
                  </span>
                )}
                <span className="text-zinc-400">
                  Avg start {formatMinutesFull(currentCandidate.avgStartMin)} · {currentCandidate.totalGapMin}m weekly gap
                </span>
                {currentCandidate.tightWalkCount > 0 && (
                  <span className="text-amber-300">
                    · {currentCandidate.tightWalkCount} tight walk{currentCandidate.tightWalkCount === 1 ? "" : "s"}
                  </span>
                )}
              </div>
            </div>

            <button
              type="button"
              disabled={applying}
              onClick={handleApply}
              className="inline-flex items-center gap-1.5 rounded-xl bg-emerald-500 px-3.5 py-1.5 text-xs font-bold text-zinc-950 hover:bg-emerald-400 disabled:opacity-50"
            >
              <Check className="h-3.5 w-3.5" />
              {applying ? "Applying..." : "Apply This Plan"}
            </button>
          </>
        )}
      </div>
    </div>
  );
}
