import React, { useMemo, useState } from "react";
import {
  Award,
  Check,
  CheckCircle2,
  Eye,
  EyeOff,
  Info,
  Loader2,
  RotateCcw,
  Sparkles,
  X,
} from "lucide-react";
import type { MinorCatalogItem } from "../types";

export function minorToneClasses(tone: string, highlighted = false): string {
  switch (tone) {
    case "emerald":
      return highlighted
        ? "border-emerald-400/70 bg-emerald-500/25 text-emerald-100"
        : "border-emerald-500/40 bg-emerald-500/15 text-emerald-200";
    case "sky":
      return highlighted
        ? "border-sky-400/70 bg-sky-500/25 text-sky-100"
        : "border-sky-500/40 bg-sky-500/15 text-sky-200";
    case "violet":
      return highlighted
        ? "border-violet-400/70 bg-violet-500/25 text-violet-100"
        : "border-violet-500/40 bg-violet-500/15 text-violet-200";
    case "amber":
      return highlighted
        ? "border-amber-400/70 bg-amber-500/25 text-amber-100"
        : "border-amber-500/40 bg-amber-500/15 text-amber-200";
    case "teal":
      return highlighted
        ? "border-teal-400/70 bg-teal-500/25 text-teal-100"
        : "border-teal-500/40 bg-teal-500/15 text-teal-200";
    case "rose":
      return highlighted
        ? "border-rose-400/70 bg-rose-500/25 text-rose-100"
        : "border-rose-500/40 bg-rose-500/15 text-rose-200";
    case "indigo":
      return highlighted
        ? "border-indigo-400/70 bg-indigo-500/25 text-indigo-100"
        : "border-indigo-500/40 bg-indigo-500/15 text-indigo-200";
    default:
      return "border-zinc-700 bg-zinc-800/80 text-zinc-200";
  }
}

interface Props {
  minors: MinorCatalogItem[];
  loadingCatalog: boolean;
  selectedMinor: string;
  selectedVersion: string;
  selectedCategories: string[];
  completedCategories: string[];
  hideCompleted: boolean;
  savingPrefs?: boolean;
  onSelectMinor: (minorId: string) => void;
  onSelectVersion: (versionId: string) => void;
  onToggleFilterCategory: (catId: string) => void;
  onClearFilterCategories: () => void;
  onToggleCompletedCategory: (catId: string) => void;
  onSetHideCompleted: (hide: boolean) => void;
  onApplyAutoFill: (catIds: string[]) => void;
  onClearCompleted: () => void;
}

export function MinorFilterPanel({
  minors,
  loadingCatalog,
  selectedMinor,
  selectedVersion,
  selectedCategories,
  completedCategories,
  hideCompleted,
  savingPrefs = false,
  onSelectMinor,
  onSelectVersion,
  onToggleFilterCategory,
  onClearFilterCategories,
  onToggleCompletedCategory,
  onSetHideCompleted,
  onApplyAutoFill,
  onClearCompleted,
}: Props) {
  const [infoOpen, setInfoOpen] = useState(false);

  const activeMinor = useMemo(
    () => minors.find((m) => m.id === selectedMinor) || null,
    [minors, selectedMinor]
  );

  const activeVersion = useMemo(() => {
    if (!activeMinor) return null;
    return (
      activeMinor.versions.find((v) => v.id === selectedVersion) ||
      activeMinor.versions.find((v) => v.id === activeMinor.default_version) ||
      activeMinor.versions[0] ||
      null
    );
  }, [activeMinor, selectedVersion]);

  const completedSet = useMemo(() => new Set(completedCategories), [completedCategories]);
  const filterSet = useMemo(() => new Set(selectedCategories), [selectedCategories]);

  const autoMatchedCategoryIds = useMemo(() => {
    if (!activeVersion) return [];
    return activeVersion.categories
      .filter((c) => c.matched_user_courses.length > 0)
      .map((c) => c.id);
  }, [activeVersion]);

  const unappliedAutoCount = useMemo(
    () => autoMatchedCategoryIds.filter((id) => !completedSet.has(id)).length,
    [autoMatchedCategoryIds, completedSet]
  );

  return (
    <div className="w-full space-y-3 rounded-xl border border-amber-500/30 bg-zinc-950/90 p-3">
      {/* Header Controls Row */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <div className="inline-flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-amber-300">
            <Award className="h-3.5 w-3.5" />
            <span>Cornell Minor Filter</span>
          </div>

          <select
            aria-label="Select Cornell minor"
            value={selectedMinor}
            onChange={(e) => {
              setInfoOpen(false);
              onSelectMinor(e.target.value);
            }}
            className="rounded-lg border border-zinc-700 bg-zinc-900 px-2.5 py-1.5 text-xs font-medium text-white outline-none focus:border-amber-500"
          >
            <option value="">Select a Cornell Minor ({minors.length || 7} supported)...</option>
            {minors.map((m) => (
              <option key={m.id} value={m.id}>
                {m.label} ({m.department})
              </option>
            ))}
          </select>

          {activeMinor && activeVersion && (
            <div className="relative flex items-center gap-1.5">
              {activeMinor.versions.length > 1 ? (
                <select
                  aria-label="Select minor track or version"
                  value={activeVersion.id}
                  onChange={(e) => onSelectVersion(e.target.value)}
                  className="rounded-lg border border-amber-500/40 bg-zinc-900 px-2.5 py-1.5 text-xs font-medium text-amber-100 outline-none focus:border-amber-400"
                >
                  {activeMinor.versions.map((v) => (
                    <option key={v.id} value={v.id}>
                      {v.label} ({v.roster_count})
                    </option>
                  ))}
                </select>
              ) : (
                <span className="rounded-lg border border-zinc-700 bg-zinc-900 px-2.5 py-1.5 text-xs font-medium text-zinc-200">
                  {activeVersion.label}
                </span>
              )}

              <button
                type="button"
                onClick={() => setInfoOpen((prev) => !prev)}
                aria-expanded={infoOpen}
                aria-label="Explain minor tracks and rules"
                title="View guide: when to pick each version/track and overall minor rules"
                className={`inline-flex items-center gap-1 rounded-lg border px-2 py-1.5 text-xs font-medium transition ${
                  infoOpen
                    ? "border-amber-400 bg-amber-500/20 text-amber-100"
                    : "border-zinc-700 bg-zinc-900 text-zinc-300 hover:border-amber-500/50 hover:text-white"
                }`}
              >
                <Info className="h-3.5 w-3.5 text-amber-300" />
                <span className="hidden sm:inline">Track Guide</span>
              </button>
            </div>
          )}

          {loadingCatalog && <Loader2 className="h-3.5 w-3.5 animate-spin text-amber-400" />}
          {savingPrefs && <span className="text-[11px] text-zinc-400">Saving...</span>}
        </div>

        {activeMinor && (
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => onSetHideCompleted(!hideCompleted)}
              className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-[11px] font-medium transition ${
                hideCompleted
                  ? "border-emerald-500/50 bg-emerald-500/15 text-emerald-200"
                  : "border-zinc-700 bg-zinc-900 text-zinc-300 hover:border-zinc-600"
              }`}
              title={
                hideCompleted
                  ? "Showing only courses that satisfy at least one uncompleted part"
                  : "Showing all courses in the minor, including completed parts"
              }
            >
              {hideCompleted ? <EyeOff className="h-3 w-3" /> : <Eye className="h-3 w-3" />}
              <span>{hideCompleted ? "Hiding Completed Parts" : "Showing All Parts"}</span>
            </button>

            <button
              type="button"
              disabled={autoMatchedCategoryIds.length === 0}
              onClick={() => onApplyAutoFill(autoMatchedCategoryIds)}
              className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-[11px] font-medium transition ${
                unappliedAutoCount > 0
                  ? "border-sky-500/60 bg-sky-500/20 text-sky-100 hover:bg-sky-500/30"
                  : autoMatchedCategoryIds.length > 0
                    ? "border-zinc-700 bg-zinc-900 text-zinc-300 hover:border-sky-500/40"
                    : "cursor-not-allowed border-zinc-800 bg-zinc-900/50 text-zinc-500"
              }`}
              title={
                autoMatchedCategoryIds.length > 0
                  ? `Mark ${autoMatchedCategoryIds.length} detected part(s) from your Completed/In-Progress courses`
                  : "Import your transcript or add completed courses to auto-detect parts"
              }
            >
              <Sparkles className="h-3 w-3 text-sky-300" />
              <span>
                Auto-fill
                {unappliedAutoCount > 0
                  ? ` (+${unappliedAutoCount} found)`
                  : autoMatchedCategoryIds.length > 0
                    ? ` (${autoMatchedCategoryIds.length} matched)`
                    : ""}
              </span>
            </button>

            {completedCategories.length > 0 && (
              <button
                type="button"
                onClick={onClearCompleted}
                className="inline-flex items-center gap-1 rounded-lg border border-zinc-700 bg-zinc-900 px-2 py-1 text-[11px] font-medium text-zinc-300 hover:border-zinc-500 hover:text-white"
                title="Uncheck all completed parts for this minor"
              >
                <RotateCcw className="h-3 w-3" />
                <span>Uncheck Done ({completedCategories.length})</span>
              </button>
            )}

            <button
              type="button"
              onClick={() => {
                setInfoOpen(false);
                onSelectMinor("");
              }}
              className="inline-flex items-center gap-1 rounded-lg border border-zinc-700 bg-zinc-900 px-2 py-1 text-[11px] text-zinc-300 hover:border-rose-500/50 hover:text-white"
            >
              <X className="h-3 w-3" />
              <span>Clear Minor</span>
            </button>
          </div>
        )}
      </div>

      {/* Interactive (i) Track / Version Guide Popover */}
      {activeMinor && infoOpen && (
        <div className="space-y-2 rounded-xl border border-amber-500/40 bg-zinc-900/95 p-3 text-xs">
          <div className="flex items-start justify-between gap-2">
            <div>
              <div className="font-semibold text-amber-200">
                {activeMinor.label} Minor — Track &amp; Requirement Guide
              </div>
              <p className="mt-0.5 text-[11px] text-zinc-300">{activeMinor.overview}</p>
            </div>
            <button
              type="button"
              onClick={() => setInfoOpen(false)}
              className="rounded p-1 text-zinc-400 hover:bg-zinc-800 hover:text-white"
              aria-label="Close track guide"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
          <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
            {activeMinor.versions.map((ver) => {
              const isSelected = activeVersion?.id === ver.id;
              return (
                <button
                  key={ver.id}
                  type="button"
                  onClick={() => {
                    if (activeMinor.versions.length > 1) {
                      onSelectVersion(ver.id);
                    }
                  }}
                  className={`rounded-lg border p-2.5 text-left transition ${
                    isSelected
                      ? "border-amber-400/70 bg-amber-500/10"
                      : "border-zinc-800 bg-zinc-950/70 hover:border-zinc-600"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-semibold text-white">{ver.label}</span>
                    <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] text-amber-200">
                      {ver.total_required_summary}
                    </span>
                  </div>
                  <p className="mt-1 text-[11px] leading-relaxed text-zinc-300">
                    {ver.description}
                  </p>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* Active Version Summary + Category Checklist Cards */}
      {activeMinor && activeVersion ? (
        <div className="space-y-2">
          <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-zinc-400">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium text-zinc-200">
                {activeVersion.total_required_summary}
              </span>
              <span>·</span>
              <span>{activeVersion.roster_count} matching courses in this roster</span>
              {selectedCategories.length > 0 && (
                <>
                  <span>·</span>
                  <button
                    type="button"
                    onClick={onClearFilterCategories}
                    className="text-amber-300 underline hover:text-amber-200"
                  >
                    Showing {selectedCategories.length} selected part(s) (Show all remaining)
                  </button>
                </>
              )}
            </div>
            <span className="text-[10px] text-zinc-500">
              Click card to focus part · Check Done to hide completed parts
            </span>
          </div>

          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {activeVersion.categories.map((cat) => {
              const isDone = completedSet.has(cat.id);
              const isFocused = filterSet.has(cat.id);
              return (
                <div
                  key={cat.id}
                  className={`flex flex-col justify-between gap-2 rounded-xl border p-2.5 transition ${
                    isFocused
                      ? "border-amber-400 bg-amber-500/15 ring-1 ring-amber-400/50"
                      : isDone
                        ? "border-emerald-500/30 bg-zinc-900/40 opacity-75"
                        : "border-zinc-800 bg-zinc-900/75 hover:border-zinc-700"
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <button
                      type="button"
                      onClick={() => onToggleFilterCategory(cat.id)}
                      className="flex-1 text-left"
                      title="Click to filter search specifically to this requirement category"
                    >
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span
                          className={`inline-flex items-center rounded-md border px-1.5 py-0.5 text-[10px] font-semibold ${minorToneClasses(
                            cat.tone,
                            isFocused
                          )} ${isDone && hideCompleted ? "line-through opacity-75" : ""}`}
                        >
                          {cat.short_label}
                        </span>
                        <span className="text-xs font-semibold text-white">
                          {cat.label}
                        </span>
                      </div>
                      <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[10px] text-zinc-400">
                        <span className="font-medium text-zinc-300">{cat.required_summary}</span>
                        <span>·</span>
                        <span>{cat.roster_count} offered</span>
                      </div>
                    </button>

                    <button
                      type="button"
                      onClick={() => onToggleCompletedCategory(cat.id)}
                      aria-pressed={isDone}
                      className={`inline-flex shrink-0 items-center gap-1 rounded-lg border px-2 py-1 text-[10px] font-semibold transition ${
                        isDone
                          ? "border-emerald-500/60 bg-emerald-500/20 text-emerald-200 hover:bg-emerald-500/30"
                          : "border-zinc-700 bg-zinc-950 text-zinc-300 hover:border-emerald-500/50 hover:text-emerald-200"
                      }`}
                      title={
                        isDone
                          ? "Marked completed — click to mark uncompleted"
                          : "Mark this requirement part as already completed"
                      }
                    >
                      {isDone ? (
                        <>
                          <CheckCircle2 className="h-3 w-3 text-emerald-400" />
                          <span>Done</span>
                        </>
                      ) : (
                        <>
                          <span className="flex h-3 w-3 items-center justify-center rounded border border-zinc-600">
                            <Check className="h-2 w-2 opacity-0" />
                          </span>
                          <span>Done?</span>
                        </>
                      )}
                    </button>
                  </div>

                  <p className="text-[11px] leading-snug text-zinc-400">{cat.rule_summary}</p>

                  {cat.matched_user_courses.length > 0 && (
                    <div className="flex flex-wrap items-center gap-1 pt-0.5 text-[10px]">
                      <span className="text-sky-300">Matched:</span>
                      {cat.matched_user_courses.slice(0, 3).map((code) => (
                        <span
                          key={code}
                          className="rounded border border-sky-500/40 bg-sky-500/15 px-1.5 py-0.5 font-medium text-sky-200"
                        >
                          {code}
                        </span>
                      ))}
                      {cat.matched_user_courses.length > 3 && (
                        <span className="text-zinc-400">
                          +{cat.matched_user_courses.length - 3} more
                        </span>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-2 text-[11px] text-zinc-400">
          <span>
            Pick one of Cornell&apos;s 7 supported minors above to browse qualifying courses, view tracks/concentrations, and hide parts you&apos;ve already completed:
          </span>
          <div className="flex flex-wrap gap-1.5">
            {minors.map((m) => (
              <button
                key={m.id}
                type="button"
                onClick={() => onSelectMinor(m.id)}
                className="rounded-lg border border-zinc-700 bg-zinc-900 px-2 py-0.5 text-[11px] font-medium text-zinc-200 transition hover:border-amber-500/60 hover:text-amber-200"
              >
                {m.short_label}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
