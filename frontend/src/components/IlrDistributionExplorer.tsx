import React, { useMemo, useState } from "react";
import {
  ChevronDown,
  ChevronUp,
  ExternalLink,
  Layers,
  Loader2,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import type { IlrMatchMode, IlrRequirementSummary, IlrSummaryResponse } from "../types";
import { toneClasses } from "../utils/courseFormat";

export function ilrToneClasses(tone: string, active = false): string {
  return toneClasses(tone, active ? "pillActive" : "pill");
}

const MAIN_CODES = ["ICL-IL", "LH-IL", "QP-IL"];

interface Props {
  summary: IlrSummaryResponse | null;
  loadingSummary: boolean;
  syncingPriority: boolean;
  selectedCodes: string[];
  matchMode: IlrMatchMode;
  multiOnly: boolean;
  ithacaOrVirtual: boolean;
  onSelectPreset: (codes: string[], matchMode?: IlrMatchMode, multiOnly?: boolean) => void;
  onToggleCode: (code: string) => void;
  onChangeMatchMode: (mode: IlrMatchMode) => void;
  onToggleMultiOnly: () => void;
  onSyncPrioritySubjects: () => void;
}

function RequirementCard({
  req,
  active,
  onClick,
}: {
  req: IlrRequirementSummary;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={req.rule_summary}
      className={`text-left rounded-lg border px-2.5 py-2 transition-colors ${
        active
          ? ilrToneClasses(req.tone, true)
          : "bg-zinc-950/60 border-zinc-800 hover:border-zinc-700 text-zinc-200"
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <span
          className={`text-[11px] font-mono font-semibold px-1.5 py-0.5 rounded border ${ilrToneClasses(
            req.tone,
            active
          )}`}
        >
          {req.code}
        </span>
        <span className="text-[11px] tabular-nums text-zinc-400 shrink-0">
          <span className="text-zinc-200 font-medium">{req.total}</span>
          {" · "}
          <span className={req.open > 0 ? "text-emerald-300 font-medium" : "text-zinc-500"}>
            {req.open} open
          </span>
        </span>
      </div>
      <div className="mt-1 text-xs font-medium truncate text-zinc-200">{req.short_label}</div>
    </button>
  );
}

export const IlrDistributionExplorer: React.FC<Props> = ({
  summary,
  loadingSummary,
  syncingPriority,
  selectedCodes,
  matchMode,
  multiOnly,
  ithacaOrVirtual,
  onSelectPreset,
  onToggleCode,
  onChangeMatchMode,
  onToggleMultiOnly,
  onSyncPrioritySubjects,
}) => {
  const [expanded, setExpanded] = useState(false);

  const grouped = useMemo(() => {
    const reqs = summary?.requirements ?? [];
    return {
      main: reqs.filter((r) => r.group === "main_elective"),
      distAndCore: reqs.filter((r) => r.group === "distribution" || r.group === "core"),
      pools: reqs.filter((r) => r.group === "credit_pool"),
    };
  }, [summary]);

  const isAllCourses = selectedCodes.length === 0 && !multiOnly;
  const isAnyIlPreset = selectedCodes.length === 1 && selectedCodes[0] === "ANY_IL" && !multiOnly;
  const isMainThreePreset =
    selectedCodes.length === 3 &&
    MAIN_CODES.every((c) => selectedCodes.includes(c)) &&
    matchMode === "any" &&
    !multiOnly;
  const isCorePreset = selectedCodes.length === 1 && selectedCodes[0] === "ILR-CORE" && !multiOnly;

  const incompleteCoverage = Boolean(
    summary &&
      (summary.coverage.ilr_synced < summary.coverage.ilr_total ||
        summary.coverage.synced_subjects < summary.coverage.total_subjects)
  );

  return (
    <div className="rounded-xl border border-zinc-800/90 bg-zinc-950/60 p-3 space-y-3">
      {/* Header + Quick Presets */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-xs font-medium text-zinc-400 mr-1">ILR Presets:</span>
          <button
            type="button"
            onClick={() => onSelectPreset([], "any", false)}
            className={`px-2.5 py-1 rounded-full text-xs border transition-colors ${
              isAllCourses
                ? "bg-zinc-200 text-zinc-900 border-zinc-200 font-medium"
                : "bg-zinc-900 text-zinc-300 border-zinc-800 hover:border-zinc-700"
            }`}
          >
            All Courses
          </button>
          <button
            type="button"
            onClick={() => onSelectPreset(["ANY_IL"], "any", false)}
            className={`px-2.5 py-1 rounded-full text-xs border transition-colors ${
              isAnyIlPreset
                ? "bg-sky-500/20 text-sky-200 border-sky-400/60 font-medium"
                : "bg-zinc-900 text-zinc-300 border-zinc-800 hover:border-zinc-700"
            }`}
          >
            All ILR (-IL)
            {summary ? ` (${summary.presets.all_il.total})` : ""}
          </button>
          <button
            type="button"
            onClick={() => onSelectPreset(MAIN_CODES, "any", false)}
            className={`px-2.5 py-1 rounded-full text-xs border transition-colors inline-flex items-center gap-1 ${
              isMainThreePreset
                ? "bg-emerald-500/20 text-emerald-200 border-emerald-400/60 font-medium"
                : "bg-zinc-900 text-zinc-300 border-zinc-800 hover:border-zinc-700"
            }`}
          >
            <Sparkles className="w-3 h-3 text-emerald-300" />
            3 Main ILR Electives
            {summary ? ` (${summary.presets.main_three.total})` : ""}
          </button>
          <button
            type="button"
            onClick={() => onSelectPreset(["ILR-CORE"], "any", false)}
            className={`px-2.5 py-1 rounded-full text-xs border transition-colors ${
              isCorePreset
                ? "bg-teal-500/20 text-teal-200 border-teal-400/60 font-medium"
                : "bg-zinc-900 text-zinc-300 border-zinc-800 hover:border-zinc-700"
            }`}
          >
            ILR Core
            {summary ? ` (${summary.presets.ilr_core.total})` : ""}
          </button>
        </div>

        <div className="flex items-center gap-2">
          {loadingSummary && (
            <Loader2 className="w-3.5 h-3.5 animate-spin text-zinc-400" aria-label="Loading ILR summary" />
          )}
          <a
            href={
              summary?.curriculum_url ||
              "https://www.ilr.cornell.edu/current-students/undergraduate-student-resources/curriculum-requirements/new-curriculum-requirements"
            }
            target="_blank"
            rel="noreferrer"
            className="text-xs text-teal-300 hover:text-teal-200 inline-flex items-center gap-1"
          >
            ILR Curriculum Rules <ExternalLink className="w-3 h-3" />
          </a>
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="text-xs text-zinc-300 hover:text-zinc-100 inline-flex items-center gap-1 px-2 py-1 rounded border border-zinc-800 bg-zinc-900"
          >
            {expanded ? "Hide Codes" : `Explore Codes${selectedCodes.length ? ` (${selectedCodes.length})` : ""}`}
            {expanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
          </button>
        </div>
      </div>

      {/* Coverage Warning Banner for Uncached Semesters */}
      {incompleteCoverage && summary && (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-2.5 py-1.5 text-xs text-amber-200">
          <span>
            {summary.roster} coverage: {summary.coverage.synced_subjects}/{summary.coverage.total_subjects} subjects cached
            {" · "}
            {summary.coverage.ilr_synced}/{summary.coverage.ilr_total} priority ILR & distribution depts synced
            {summary.coverage.warmup_active ? " — warming up in background..." : ""}
          </span>
          <button
            type="button"
            onClick={onSyncPrioritySubjects}
            disabled={syncingPriority}
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-amber-500/20 hover:bg-amber-500/30 border border-amber-400/40 text-amber-100 font-medium disabled:opacity-60"
          >
            <RefreshCw className={`w-3 h-3 ${syncingPriority ? "animate-spin" : ""}`} />
            {syncingPriority ? "Queued..." : "Sync ILR & Dist Subjects"}
          </button>
        </div>
      )}

      {expanded && summary && (
        <div className="space-y-3">
          {/* Bucket A: 3 Main Electives */}
          <div>
            <div className="flex items-center justify-between text-[11px] uppercase tracking-wider text-zinc-400 mb-1.5">
              <span>3 Main ILR Advanced Electives (Need 1 each · 3–4 cr letter grade)</span>
              <span className="normal-case tracking-normal text-zinc-500">
                {ithacaOrVirtual ? "Ithaca + Virtual counts" : "All campuses"}
              </span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
              {grouped.main.map((req) => (
                <RequirementCard
                  key={req.code}
                  req={req}
                  active={selectedCodes.includes(req.code)}
                  onClick={() => onToggleCode(req.code)}
                />
              ))}
            </div>
          </div>

          {/* Bucket B + C side by side on wide screens */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-3">
            <div className="lg:col-span-7">
              <div className="text-[11px] uppercase tracking-wider text-zinc-400 mb-1.5">
                Distribution, Writing, Stats & Required Core
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                {grouped.distAndCore.map((req) => (
                  <RequirementCard
                    key={req.code}
                    req={req}
                    active={selectedCodes.includes(req.code)}
                    onClick={() => onToggleCode(req.code)}
                  />
                ))}
              </div>
            </div>

            <div className="lg:col-span-5">
              <div className="text-[11px] uppercase tracking-wider text-zinc-400 mb-1.5">
                40-Credit Elective Pools (24+ In / 16 Out)
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-1 xl:grid-cols-2 gap-2">
                {grouped.pools.map((req) => (
                  <RequirementCard
                    key={req.code}
                    req={req}
                    active={selectedCodes.includes(req.code)}
                    onClick={() => onToggleCode(req.code)}
                  />
                ))}
              </div>
            </div>
          </div>

          {/* Match Logic & Multi-req Filter Row */}
          <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-zinc-800/80 text-xs">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-zinc-400">Match Logic:</span>
              <div className="inline-flex rounded-lg border border-zinc-800 bg-zinc-900 p-0.5">
                <button
                  type="button"
                  onClick={() => onChangeMatchMode("any")}
                  className={`px-2 py-0.5 rounded text-xs transition-colors ${
                    matchMode === "any"
                      ? "bg-zinc-200 text-zinc-900 font-medium"
                      : "text-zinc-400 hover:text-zinc-200"
                  }`}
                >
                  Fits ANY selected
                </button>
                <button
                  type="button"
                  onClick={() => onChangeMatchMode("all")}
                  className={`px-2 py-0.5 rounded text-xs transition-colors ${
                    matchMode === "all"
                      ? "bg-zinc-200 text-zinc-900 font-medium"
                      : "text-zinc-400 hover:text-zinc-200"
                  }`}
                >
                  Fits ALL selected
                </button>
              </div>

              <button
                type="button"
                onClick={onToggleMultiOnly}
                className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-xs transition-colors ${
                  multiOnly
                    ? "bg-emerald-500/20 border-emerald-400/60 text-emerald-200 font-medium"
                    : "bg-zinc-900 border-zinc-800 text-zinc-300 hover:border-zinc-700"
                }`}
              >
                <Layers className="w-3.5 h-3.5" />
                Double-counts (2+ ILR reqs)
                {summary ? ` (${summary.presets.multi_req.total})` : ""}
              </button>
            </div>

            {(selectedCodes.length > 0 || multiOnly) && (
              <button
                type="button"
                onClick={() => onSelectPreset([], "any", false)}
                className="text-xs text-zinc-400 hover:text-zinc-200 underline underline-offset-2"
              >
                Clear ILR filter
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
