import React, { useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowLeftRight,
  BellPlus,
  Calendar,
  Check,
  ChevronDown,
  Copy,
  Download,
  Edit3,
  Footprints,
  Image,
  Link2,
  Loader2,
  Plus,
  RefreshCw,
  Share2,
  Sparkles,
  Star,
  Trash2,
} from "lucide-react";
import { useCopyFeedback } from "../hooks/useCopyFeedback";
import type {
  HydratedSchedule,
  Roster,
  ScheduleCourseItem,
  ScheduleSummary,
} from "../types";
import type { ScheduleInsightsSummary } from "../utils/scheduleInsights";
import type { ScheduleDiagnostics } from "../utils/schedulerSolver";

interface Props {
  rosters: Roster[];
  roster: string;
  isArchivedRoster: boolean;
  schedules: ScheduleSummary[];
  active: HydratedSchedule | null;
  displayedCourses: ScheduleCourseItem[];
  diagnostics: ScheduleDiagnostics;
  insightsSummary: ScheduleInsightsSummary;
  loadingBatchInsights: boolean;
  showGenerator: boolean;
  showNewForm: boolean;
  showSharePanel: boolean;
  renaming: boolean;
  renameText: string;
  newName: string;
  duplicateCurrent: boolean;
  closedOrWaitlistCount: number;
  watchBusyKey: string | null;
  diagnosticsExpanded: boolean;
  onChangeRoster: (slug: string) => void;
  onSelectSchedule: (scheduleId: number) => void;
  onToggleNewForm: () => void;
  onChangeNewName: (val: string) => void;
  onChangeDuplicateCurrent: (val: boolean) => void;
  onCreateSchedule: (e: React.FormEvent) => void;
  onStartRename: () => void;
  onChangeRenameText: (val: string) => void;
  onSubmitRename: (e: React.FormEvent) => void;
  onCancelRename: () => void;
  onDeleteSchedule: () => void;
  onToggleGenerator: () => void;
  onWatchClosed: () => void;
  onLoadRatings: () => void;
  onOpenCompare: () => void;
  onCopyPng: () => Promise<boolean> | void;
  onDownloadIcs: () => void;
  onToggleSharePanel: () => void;
  onToggleShareEnabled: (enabled: boolean) => void;
  onRegenerateShare: () => void;
  onToggleDiagnostics: () => void;
}

export function SchedulerToolbar({
  rosters,
  roster,
  isArchivedRoster,
  schedules,
  active,
  displayedCourses,
  diagnostics,
  insightsSummary,
  loadingBatchInsights,
  showGenerator,
  showNewForm,
  showSharePanel,
  renaming,
  renameText,
  newName,
  duplicateCurrent,
  closedOrWaitlistCount,
  watchBusyKey,
  diagnosticsExpanded,
  onChangeRoster,
  onSelectSchedule,
  onToggleNewForm,
  onChangeNewName,
  onChangeDuplicateCurrent,
  onCreateSchedule,
  onStartRename,
  onChangeRenameText,
  onSubmitRename,
  onCancelRename,
  onDeleteSchedule,
  onToggleGenerator,
  onWatchClosed,
  onLoadRatings,
  onOpenCompare,
  onCopyPng,
  onDownloadIcs,
  onToggleSharePanel,
  onToggleShareEnabled,
  onRegenerateShare,
  onToggleDiagnostics,
}: Props) {
  const [exportMenuOpen, setExportMenuOpen] = useState(false);
  const [copiedPng, setCopiedPng] = useState(false);
  const shareCopy = useCopyFeedback<"share">(1500);
  const menuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!exportMenuOpen) return;
    const handleOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setExportMenuOpen(false);
      }
    };
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setExportMenuOpen(false);
    };
    document.addEventListener("mousedown", handleOutside);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("mousedown", handleOutside);
      document.removeEventListener("keydown", handleKey);
    };
  }, [exportMenuOpen]);

  const isTranscriptSchedule = Boolean(active?.schedule.is_transcript);
  const currentRosters = rosters.filter((r) => r.archive_mode !== 1);
  const archivedRosters = rosters.filter((r) => r.archive_mode === 1);
  const hasDiagnostics =
    diagnostics.conflictMessages.length > 0 ||
    diagnostics.walkWarnings.length > 0 ||
    diagnostics.academicWarnings.length > 0;

  return (
    <div className="rounded-2xl border border-zinc-800 bg-zinc-900/80 p-3.5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={roster}
            onChange={(e) => onChangeRoster(e.target.value)}
            className="rounded-xl border border-zinc-700 bg-zinc-950 px-3 py-1.5 text-xs font-semibold text-zinc-100"
          >
            {currentRosters.length > 0 && archivedRosters.length > 0 ? (
              <>
                <optgroup label="Current &amp; Upcoming">
                  {currentRosters.map((r) => (
                    <option key={r.slug} value={r.slug}>
                      {r.descr} ({r.slug})
                    </option>
                  ))}
                </optgroup>
                <optgroup label="Past Semesters">
                  {archivedRosters.map((r) => (
                    <option key={r.slug} value={r.slug}>
                      {r.descr} ({r.slug})
                    </option>
                  ))}
                </optgroup>
              </>
            ) : (
              rosters.map((r) => (
                <option key={r.slug} value={r.slug}>
                  {r.descr} ({r.slug})
                </option>
              ))
            )}
          </select>

          {isArchivedRoster && (
            <span
              title="Historical semester from Cornell Roster archive"
              className="rounded-lg border border-zinc-700 bg-zinc-900 px-2 py-1 text-[11px] font-medium text-zinc-400"
            >
              Past Term
            </span>
          )}

          {active && (!renaming || isTranscriptSchedule) && (
            <select
              value={active.schedule.id}
              onChange={(e) => onSelectSchedule(Number(e.target.value))}
              className="rounded-xl border border-zinc-700 bg-zinc-950 px-3 py-1.5 text-xs font-semibold text-emerald-300"
            >
              {schedules.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                  {s.is_transcript ? " [Locked]" : ""}
                </option>
              ))}
            </select>
          )}

          {active && renaming && !isTranscriptSchedule && (
            <form onSubmit={onSubmitRename} className="flex items-center gap-1.5">
              <input
                type="text"
                value={renameText}
                onChange={(e) => onChangeRenameText(e.target.value)}
                className="rounded-xl border border-zinc-700 bg-zinc-950 px-2.5 py-1 text-xs text-white"
                autoFocus
              />
              <button
                type="submit"
                className="rounded-lg bg-emerald-500 px-2.5 py-1 text-xs font-semibold text-zinc-950"
              >
                Save
              </button>
              <button
                type="button"
                onClick={onCancelRename}
                className="rounded-lg px-2 py-1 text-xs text-zinc-400"
              >
                Cancel
              </button>
            </form>
          )}

          <button
            type="button"
            onClick={onToggleNewForm}
            title="New schedule"
            className="inline-flex items-center gap-1 rounded-xl border border-zinc-700 px-2.5 py-1.5 text-xs text-zinc-200 hover:border-emerald-500/50 hover:text-emerald-300"
          >
            <Plus className="h-3.5 w-3.5" />
            New
          </button>

          {active && (
            <>
              {!isTranscriptSchedule && (
                <button
                  type="button"
                  onClick={onStartRename}
                  title="Rename schedule"
                  className="rounded-xl border border-zinc-800 p-1.5 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
                >
                  <Edit3 className="h-3.5 w-3.5" />
                </button>
              )}
              {schedules.length > 1 && (
                <button
                  type="button"
                  onClick={onDeleteSchedule}
                  title="Delete schedule"
                  className="rounded-xl border border-zinc-800 p-1.5 text-zinc-400 hover:bg-rose-500/15 hover:text-rose-300"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              )}
            </>
          )}
        </div>

        {/* Right Toolbar Actions */}
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={onToggleGenerator}
            title="Find conflict-free section combinations across your courses (honoring locked sections & busy blocks)"
            className={`inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-bold transition ${
              showGenerator
                ? "bg-emerald-400 text-zinc-950"
                : !active || active.courses.length === 0
                  ? "border border-zinc-700 bg-zinc-900 text-zinc-400 hover:border-zinc-600 hover:text-zinc-200"
                  : "border border-emerald-500/45 bg-emerald-500/15 text-emerald-300 hover:bg-emerald-500/25"
            }`}
          >
            <Sparkles className="h-3.5 w-3.5" />
            Auto-Generate
          </button>

          {!isArchivedRoster && closedOrWaitlistCount > 0 && (
            <button
              type="button"
              disabled={watchBusyKey === "all-missing"}
              onClick={onWatchClosed}
              className="inline-flex items-center gap-1.5 rounded-xl border border-amber-500/45 bg-amber-500/15 px-3 py-1.5 text-xs font-semibold text-amber-200 hover:bg-amber-500/25 disabled:opacity-50"
            >
              <BellPlus className="h-3.5 w-3.5" />
              {watchBusyKey === "all-missing" ? "Watching..." : `Watch Closed (${closedOrWaitlistCount})`}
            </button>
          )}

          <button
            type="button"
            disabled={!active || displayedCourses.length === 0 || loadingBatchInsights}
            onClick={onLoadRatings}
            title="Fetch CU Reviews & RateMyProfessors ratings and workload for all courses in this schedule"
            className="inline-flex items-center gap-1.5 rounded-xl border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-200 hover:border-sky-500/50 hover:text-sky-200 disabled:opacity-40"
          >
            {loadingBatchInsights ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin text-sky-400" />
            ) : (
              <Star className="h-3.5 w-3.5 text-amber-300" />
            )}
            {loadingBatchInsights ? "Loading..." : "Ratings"}
          </button>

          {schedules.length > 1 && (
            <button
              type="button"
              onClick={onOpenCompare}
              title="Compare active schedule against another saved plan"
              className="inline-flex items-center gap-1.5 rounded-xl border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-200 hover:bg-zinc-800"
            >
              <ArrowLeftRight className="h-3.5 w-3.5 text-sky-300" />
              Compare
            </button>
          )}

          <div ref={menuRef} className="relative">
            <button
              type="button"
              aria-expanded={exportMenuOpen}
              onClick={() => setExportMenuOpen((v) => !v)}
              className={`inline-flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs font-medium transition ${
                active?.schedule.share_enabled
                  ? "border-sky-500/50 bg-sky-500/15 text-sky-200"
                  : "border-zinc-700 text-zinc-200 hover:bg-zinc-800"
              }`}
            >
              <Share2 className="h-3.5 w-3.5" />
              Export
              {active?.schedule.share_enabled && (
                <span className="h-1.5 w-1.5 rounded-full bg-sky-400" title="Share link enabled" />
              )}
              <ChevronDown className="h-3 w-3 opacity-70" />
            </button>

            {exportMenuOpen && (
              <div className="absolute right-0 z-30 mt-1.5 w-48 space-y-1 rounded-xl border border-zinc-700 bg-zinc-950 p-1.5 text-xs shadow-2xl">
                <button
                  type="button"
                  disabled={!active || displayedCourses.length === 0}
                  onClick={async () => {
                    setExportMenuOpen(false);
                    const ok = await onCopyPng();
                    if (ok) {
                      setCopiedPng(true);
                      window.setTimeout(() => setCopiedPng(false), 1800);
                    }
                  }}
                  className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-zinc-200 hover:bg-zinc-800 disabled:opacity-40"
                >
                  {copiedPng ? (
                    <Check className="h-3.5 w-3.5 text-emerald-400" />
                  ) : (
                    <Image className="h-3.5 w-3.5 text-zinc-400" />
                  )}
                  <span>{copiedPng ? "Copied PNG" : "Copy Image (PNG)"}</span>
                </button>
                <button
                  type="button"
                  disabled={!active || displayedCourses.length === 0}
                  onClick={() => {
                    setExportMenuOpen(false);
                    onDownloadIcs();
                  }}
                  className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-zinc-200 hover:bg-zinc-800 disabled:opacity-40"
                >
                  <Download className="h-3.5 w-3.5 text-zinc-400" />
                  <span>Download .ics</span>
                </button>
                <button
                  type="button"
                  disabled={!active}
                  onClick={() => {
                    setExportMenuOpen(false);
                    onToggleSharePanel();
                  }}
                  className="flex w-full items-center justify-between gap-2 rounded-lg px-2.5 py-2 text-left text-zinc-200 hover:bg-zinc-800 disabled:opacity-40"
                >
                  <span className="inline-flex items-center gap-2">
                    <Link2 className="h-3.5 w-3.5 text-sky-300" />
                    <span>{showSharePanel ? "Hide Share Link" : "Share Link"}</span>
                  </span>
                  {active?.schedule.share_enabled && (
                    <span className="text-[10px] font-semibold text-sky-300">On</span>
                  )}
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* New Schedule Form */}
      {showNewForm && (
        <form
          onSubmit={onCreateSchedule}
          className="mt-3 flex flex-wrap items-center gap-2 border-t border-zinc-800 pt-3"
        >
          <input
            type="text"
            value={newName}
            onChange={(e) => onChangeNewName(e.target.value)}
            placeholder="Schedule name (e.g. Plan B - Late Start)"
            className="min-w-[220px] flex-1 rounded-xl border border-zinc-700 bg-zinc-950 px-3 py-1.5 text-xs text-white"
            autoFocus
          />
          <label className="flex items-center gap-1.5 text-xs text-zinc-300">
            <input
              type="checkbox"
              checked={duplicateCurrent}
              onChange={(e) => onChangeDuplicateCurrent(e.target.checked)}
              className="rounded border-zinc-600 bg-zinc-900 text-emerald-500"
            />
            Duplicate current courses &amp; blocks
          </label>
          <button
            type="submit"
            className="rounded-xl bg-emerald-500 px-3 py-1.5 text-xs font-bold text-zinc-950 hover:bg-emerald-400"
          >
            Create
          </button>
          <button
            type="button"
            onClick={onToggleNewForm}
            className="rounded-xl px-2.5 py-1.5 text-xs text-zinc-400 hover:text-zinc-200"
          >
            Cancel
          </button>
        </form>
      )}

      {/* Opt-In Share Link Drawer */}
      {showSharePanel && active && (
        <div className="mt-3 space-y-2 rounded-xl border border-sky-500/30 bg-sky-500/5 p-3 text-xs">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <Link2 className="h-4 w-4 text-sky-300" />
              <span className="font-semibold text-white">Read-Only Share Link</span>
              <span className="text-zinc-400">(viewers do not need an account)</span>
            </div>
            <label className="inline-flex cursor-pointer items-center gap-2">
              <input
                type="checkbox"
                checked={active.schedule.share_enabled}
                onChange={(e) => onToggleShareEnabled(e.target.checked)}
                className="rounded border-zinc-600 bg-zinc-900 text-sky-400"
              />
              <span className="font-medium text-zinc-200">
                {active.schedule.share_enabled ? "Enabled" : "Disabled"}
              </span>
            </label>
          </div>

          {active.schedule.share_enabled && active.schedule.share_url && (
            <div className="flex flex-wrap items-center gap-2">
              <input
                type="text"
                readOnly
                value={active.schedule.share_url}
                className="min-w-[240px] flex-1 rounded-lg border border-zinc-700 bg-zinc-950 px-2.5 py-1.5 font-mono text-[11px] text-sky-200"
              />
              <button
                type="button"
                onClick={() => void shareCopy.copy(active.schedule.share_url || "", "share")}
                className="inline-flex items-center gap-1 rounded-lg bg-sky-400 px-3 py-1.5 font-semibold text-zinc-950 hover:bg-sky-300"
              >
                {shareCopy.copiedKey === "share" ? (
                  <Check className="h-3.5 w-3.5" />
                ) : (
                  <Copy className="h-3.5 w-3.5" />
                )}
                {shareCopy.copiedKey === "share" ? "Copied" : "Copy Link"}
              </button>
              <button
                type="button"
                onClick={onRegenerateShare}
                title="Generate a new token and invalidate the old link"
                className="inline-flex items-center gap-1 rounded-lg border border-zinc-700 px-2.5 py-1.5 text-zinc-300 hover:bg-zinc-800"
              >
                <RefreshCw className="h-3.5 w-3.5" />
                Regenerate
              </button>
            </div>
          )}
        </div>
      )}

      {/* Metrics & Summary Strip */}
      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-zinc-800/80 pt-3 text-xs">
        <div className="flex flex-wrap items-center gap-2.5">
          <span className="inline-flex items-center gap-1.5 font-semibold text-white">
            <Calendar className="h-3.5 w-3.5 text-emerald-400" />
            {diagnostics.totalCredits} Credits
          </span>
          <span className="text-zinc-500">&middot;</span>
          <span className="text-zinc-300">
            {displayedCourses.filter((c) => c.enabled).length} Active Course
            {displayedCourses.filter((c) => c.enabled).length === 1 ? "" : "s"}
          </span>
          {insightsSummary.semesterTier && insightsSummary.semesterLoadScore != null && (
            <>
              <span className="text-zinc-500">&middot;</span>
              <span
                className={`inline-flex items-center gap-1 rounded-lg border px-2 py-0.5 font-semibold ${insightsSummary.semesterTier.badgeClass}`}
                title={`Credit-weighted diff (${insightsSummary.avgDifficulty ?? "—"}/5), work (${insightsSummary.avgWorkload ?? "—"}/5), & credits (${diagnostics.totalCredits} cr)`}
              >
                Load: {insightsSummary.semesterTier.label} ({insightsSummary.semesterLoadScore.toFixed(1)}/5)
              </span>
            </>
          )}
          {(insightsSummary.avgDifficulty != null ||
            insightsSummary.avgWorkload != null ||
            insightsSummary.avgRating != null) && (
            <span className="text-zinc-400">
              {[
                insightsSummary.avgDifficulty != null
                  ? `Diff ${insightsSummary.avgDifficulty.toFixed(1)}`
                  : null,
                insightsSummary.avgWorkload != null
                  ? `Wk ${insightsSummary.avgWorkload.toFixed(1)}`
                  : null,
                insightsSummary.avgRating != null
                  ? `★ ${insightsSummary.avgRating.toFixed(1)}`
                  : null,
              ]
                .filter(Boolean)
                .join(" · ")}
            </span>
          )}
          {loadingBatchInsights && (
            <span className="inline-flex items-center gap-1 text-zinc-400">
              <Loader2 className="h-3 w-3 animate-spin text-sky-400" />
              Loading ratings...
            </span>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {diagnostics.conflictCount > 0 ? (
            <button
              type="button"
              onClick={onToggleDiagnostics}
              className="inline-flex items-center gap-1 rounded-lg border border-rose-500/40 bg-rose-500/15 px-2 py-0.5 font-semibold text-rose-200 hover:bg-rose-500/25"
            >
              <AlertTriangle className="h-3.5 w-3.5" />
              {diagnostics.conflictCount} Conflict{diagnostics.conflictCount === 1 ? "" : "s"}
              <ChevronDown className={`h-3 w-3 transition-transform ${diagnosticsExpanded ? "rotate-180" : ""}`} />
            </button>
          ) : (
            displayedCourses.length > 0 && (
              <span className="inline-flex items-center gap-1 text-emerald-400/90">
                <Check className="h-3.5 w-3.5" />
                No conflicts
              </span>
            )
          )}

          {diagnostics.walkWarnings.length > 0 && (
            <button
              type="button"
              onClick={onToggleDiagnostics}
              className="inline-flex items-center gap-1 rounded-lg border border-amber-500/40 bg-amber-500/15 px-2 py-0.5 text-amber-200 hover:bg-amber-500/25"
            >
              <Footprints className="h-3.5 w-3.5" />
              {diagnostics.walkWarnings.length} Tight Walk
              {diagnostics.walkWarnings.length === 1 ? "" : "s"}
              <ChevronDown className={`h-3 w-3 transition-transform ${diagnosticsExpanded ? "rotate-180" : ""}`} />
            </button>
          )}

          {diagnostics.academicWarnings.length > 0 && (
            <button
              type="button"
              onClick={onToggleDiagnostics}
              className="inline-flex items-center gap-1 rounded-lg border border-amber-500/35 bg-amber-500/10 px-2 py-0.5 text-amber-300 hover:bg-amber-500/20"
            >
              <AlertTriangle className="h-3 w-3" />
              {diagnostics.academicWarnings.length} Note
              {diagnostics.academicWarnings.length === 1 ? "" : "s"}
              <ChevronDown className={`h-3 w-3 transition-transform ${diagnosticsExpanded ? "rotate-180" : ""}`} />
            </button>
          )}
        </div>
      </div>

      {/* Expandable Diagnostic Details */}
      {diagnosticsExpanded && hasDiagnostics && (
        <div className="mt-2.5 space-y-1.5 rounded-xl border border-zinc-800 bg-zinc-950/80 p-3 text-xs">
          {diagnostics.conflictMessages.map((msg) => (
            <div key={msg} className="flex items-center gap-1.5 text-rose-300">
              <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
              <span>{msg}</span>
            </div>
          ))}
          {diagnostics.walkWarnings.map((w, idx) => (
            <div key={`${w.day}-${w.toCourse}-${idx}`} className="flex items-center gap-1.5 text-amber-200">
              <Footprints className="h-3.5 w-3.5 shrink-0" />
              <span>
                <strong>{w.day}</strong>: {w.fromCourse} ({w.fromBuilding}) → {w.toCourse} (
                {w.toBuilding}) is ~{w.walkMin} min walk for a {w.gapMin} min gap
              </span>
            </div>
          ))}
          {diagnostics.academicWarnings.map((msg) => (
            <div key={msg} className="flex items-center gap-1.5 text-amber-300">
              <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
              <span>{msg}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
