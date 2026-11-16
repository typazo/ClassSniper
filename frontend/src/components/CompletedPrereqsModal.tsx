import React, { useEffect, useMemo, useRef, useState } from "react";
import { Check, CheckCircle2, FileUp, Loader2, Plus, Search, Sparkles, Trash2, X } from "lucide-react";
import { api } from "../api/client";
import { usePrereqOptions } from "../hooks/usePrereqOptions";
import type { MajorMode, UserPrereqsResponse } from "../types";
import { normalizeCourseCodeInput } from "../utils/courseFormat";

interface Props {
  isOpen: boolean;
  roster: string;
  initialCompleted: string[];
  initialIncludeImplied: boolean;
  majorMode?: MajorMode;
  showCsFeatures?: boolean;
  onClose: () => void;
  onSaved: (res: UserPrereqsResponse) => void;
  onOpenTranscriptImport?: () => void;
}

const PRESET_BUNDLES: Array<{
  label: string;
  hint: string;
  courses: string[];
  modes?: MajorMode[];
}> = [
  {
    label: "ILR Core",
    hint: "ILROB 1220, ILRGL 1100, ECON 1110/1120, ILRGL 2010/2050, ILRHR 2600, ILRLE 2400, ILRST 2100/2110",
    courses: [
      "ILROB 1220",
      "ILRGL 1100",
      "ECON 1110",
      "ECON 1120",
      "ILRGL 2010",
      "ILRHR 2600",
      "ILRGL 2050",
      "ILRLE 2400",
      "ILRST 2100",
      "ILRST 2110",
    ],
    modes: ["ilr"],
  },
  {
    label: "Intro CS",
    hint: "CS 1110, CS 2110, CS 2800",
    courses: ["CS 1110", "CS 2110", "CS 2800"],
    modes: ["cs", "none"],
  },
  {
    label: "Upper CS Core",
    hint: "CS 3110, CS 3410, CS 4820",
    courses: ["CS 3110", "CS 3410", "CS 4820"],
    modes: ["cs"],
  },
  {
    label: "CS AI / ML",
    hint: "CS 3780, CS 4700, MATH 2940",
    courses: ["CS 3780", "CS 4700", "MATH 2940"],
    modes: ["cs"],
  },
  {
    label: "Eng Math",
    hint: "MATH 1910, MATH 1920, MATH 2940",
    courses: ["MATH 1910", "MATH 1920", "MATH 2940"],
    modes: ["cs", "none"],
  },
  {
    label: "A&S Math",
    hint: "MATH 1110, MATH 1120, MATH 2210",
    courses: ["MATH 1110", "MATH 1120", "MATH 2210"],
    modes: ["cs", "none"],
  },
  {
    label: "Eng Stats",
    hint: "ENGRD 2700, BTRY 3080",
    courses: ["ENGRD 2700", "BTRY 3080"],
    modes: ["cs", "none"],
  },
  {
    label: "ORIE Core",
    hint: "ENGRD 2700, ORIE 3300, ORIE 3500",
    courses: ["ENGRD 2700", "ORIE 3300", "ORIE 3500"],
    modes: ["cs", "none"],
  },
];

const ILR_QUICK_TOGGLE_COURSES: string[] = [
  "ILROB 1220",
  "ILRGL 1100",
  "ECON 1110",
  "ECON 1120",
  "ILRGL 2010",
  "ILRHR 2600",
  "ILRGL 2050",
  "ILRLE 2400",
  "ILRST 2100",
  "ILRST 2110",
  "STSCI 2100",
  "CS 1110",
];

const QUICK_TOGGLE_COURSES: string[] = [
  "CS 1110",
  "CS 2110",
  "CS 2800",
  "CS 3110",
  "CS 3410",
  "CS 3420",
  "CS 4820",
  "CS 3780",
  "MATH 1910",
  "MATH 1920",
  "MATH 2930",
  "MATH 2940",
  "MATH 2210",
  "ENGRD 2700",
  "BTRY 3080",
  "INFO 2950",
  "PHYS 1112",
  "PHYS 2213",
  "CHEM 2090",
];

// Lightweight client preview mirror of cs_requirements.IMPLICIT_PREREQ_MAP
const IMPLIED_PREVIEW_EDGES: Record<string, string[]> = {
  "CS 2110": ["CS 1110"],
  "CS 2112": ["CS 1110"],
  "CS 3110": ["CS 2110"],
  "CS 3410": ["CS 2110"],
  "CS 3420": ["CS 2110"],
  "ECE 3140": ["CS 2110"],
  "CS 4820": ["CS 2110", "CS 2800"],
  "CS 3780": ["CS 2110", "CS 2800", "MATH 2940"],
  "CS 4780": ["CS 2110", "CS 2800", "MATH 2940"],
  "MATH 1920": ["MATH 1910"],
  "MATH 2930": ["MATH 1920"],
  "MATH 2940": ["MATH 1920"],
  "MATH 1120": ["MATH 1110"],
  "MATH 2210": ["MATH 1120"],
  "MATH 2220": ["MATH 2210"],
  "MATH 2230": ["MATH 1120"],
  "MATH 2240": ["MATH 2230"],
  "ENGRD 2700": ["MATH 1920"],
  "ORIE 3500": ["ENGRD 2700"],
  "BTRY 3080": ["MATH 1920"],
  "ECON 3120": ["ECON 3110"],
  "PHYS 2213": ["PHYS 1112", "MATH 1920"],
  "PHYS 2214": ["PHYS 2213"],
};

function sortCourseCodes(codes: Iterable<string>): string[] {
  return Array.from(new Set(codes)).sort((a, b) => a.localeCompare(b));
}

function computeImpliedPreview(selected: string[], includeImplied: boolean): string[] {
  if (!includeImplied || selected.length === 0) return [];
  const base = new Set(selected);
  const discovered = new Set<string>();
  const queue = [...selected];
  const visited = new Set<string>(selected);

  while (queue.length > 0) {
    const cur = queue.shift()!;
    const deps = IMPLIED_PREVIEW_EDGES[cur] || [];
    for (const dep of deps) {
      if (!base.has(dep)) discovered.add(dep);
      if (!visited.has(dep)) {
        visited.add(dep);
        queue.push(dep);
      }
    }
  }
  return Array.from(discovered).sort((a, b) => a.localeCompare(b));
}

export function CompletedPrereqsModal({
  isOpen,
  roster,
  initialCompleted,
  initialIncludeImplied,
  majorMode,
  showCsFeatures = true,
  onClose,
  onSaved,
  onOpenTranscriptImport,
}: Props) {
  const effectiveMode: MajorMode = majorMode ?? (showCsFeatures ? "cs" : "none");
  const quickToggleCourses =
    effectiveMode === "ilr" ? ILR_QUICK_TOGGLE_COURSES : QUICK_TOGGLE_COURSES;
  const visibleBundles = PRESET_BUNDLES.filter(
    (bundle) => !bundle.modes || bundle.modes.includes(effectiveMode)
  );
  const [selectedCourses, setSelectedCourses] = useState<string[]>([]);
  const [includeImplied, setIncludeImplied] = useState(true);
  const [serverImplied, setServerImplied] = useState<string[]>([]);
  const [dirty, setDirty] = useState(false);
  const dirtyRef = useRef(false);
  dirtyRef.current = dirty;

  const [searchText, setSearchText] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const { options, loadingOptions } = usePrereqOptions(
    roster,
    searchText,
    effectiveMode,
    { enabled: isOpen && Boolean(roster), allowEmptyQuery: true, limit: 25, debounceMs: 160 }
  );

  useEffect(() => {
    if (!isOpen) return;
    let cancelled = false;
    setSelectedCourses(sortCourseCodes(initialCompleted));
    setIncludeImplied(initialIncludeImplied);
    setServerImplied([]);
    setDirty(false);
    dirtyRef.current = false;
    setSearchText("");
    setError("");

    api
      .getUserPrereqs(roster || undefined)
      .then((res) => {
        if (cancelled || dirtyRef.current) return;
        setSelectedCourses(sortCourseCodes(res.completed_courses));
        setIncludeImplied(res.include_implied_prereqs);
        setServerImplied(res.implied_courses);
        setDirty(false);
      })
      .catch(() => {
        // Keep initial props fallback
      });
    return () => {
      cancelled = true;
    };
  }, [isOpen, roster, initialCompleted, initialIncludeImplied]);

  useEffect(() => {
    if (!isOpen) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape" && !saving) onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isOpen, saving, onClose]);

  const selectedSet = useMemo(() => new Set(selectedCourses), [selectedCourses]);
  const customParsedCode = useMemo(() => normalizeCourseCodeInput(searchText), [searchText]);

  const impliedPreview = useMemo(() => {
    if (!dirty && serverImplied.length > 0) return serverImplied;
    return computeImpliedPreview(selectedCourses, includeImplied);
  }, [dirty, serverImplied, selectedCourses, includeImplied]);

  if (!isOpen) return null;

  function toggleCourse(code: string) {
    setDirty(true);
    setError("");
    setSelectedCourses((prev) => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return sortCourseCodes(next);
    });
  }

  function applyBundle(bundleCourses: string[]) {
    setDirty(true);
    setError("");
    setSelectedCourses((prev) => {
      const next = new Set(prev);
      const allPresent = bundleCourses.every((c) => next.has(c));
      if (allPresent) {
        for (const c of bundleCourses) next.delete(c);
      } else {
        for (const c of bundleCourses) next.add(c);
      }
      return sortCourseCodes(next);
    });
  }

  function addCustomCode(code: string) {
    if (!selectedSet.has(code)) {
      toggleCourse(code);
    }
    setSearchText("");
  }

  async function handleSave() {
    setSaving(true);
    setError("");
    try {
      const res = await api.updateUserPrereqs(
        {
          completed_courses: selectedCourses,
          include_implied_prereqs: includeImplied,
        },
        roster || undefined
      );
      onSaved(res);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save completed prerequisites");
    } finally {
      setSaving(false);
    }
  }

  const showCustomAdd =
    Boolean(customParsedCode) &&
    !options.some((o) => o.code.toUpperCase() === customParsedCode);

  return (
    <div
      onClick={(e) => {
        if (e.target === e.currentTarget && !saving) onClose();
      }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm"
    >
      <div className="flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-zinc-700 bg-zinc-900 shadow-2xl">
        {/* Header */}
        <div className="flex items-start justify-between gap-3 border-b border-zinc-800 px-5 py-4">
          <div>
            <h3 className="text-base font-bold text-white">My Completed Prerequisites</h3>
            <p className="mt-0.5 text-xs text-zinc-400">
              Saved per user account. Used to check prerequisites &amp; power the{" "}
              <span className="font-medium text-emerald-300">Only prereqs met</span> filter.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={saving}
            className="rounded-lg p-1 text-zinc-400 hover:bg-zinc-800 hover:text-white"
            aria-label="Close prerequisites dialog"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Scrollable Body */}
        <div className="space-y-4 overflow-y-auto px-5 py-4 text-xs">
          {/* Selected Courses Box */}
          <div className="space-y-2 rounded-xl border border-zinc-800 bg-zinc-950/80 p-3">
            <div className="flex items-center justify-between gap-2">
              <span className="font-semibold text-zinc-200">
                Selected Courses ({selectedCourses.length})
              </span>
              <div className="flex items-center gap-1.5">
                {onOpenTranscriptImport && (
                  <button
                    type="button"
                    onClick={onOpenTranscriptImport}
                    disabled={saving}
                    className="inline-flex items-center gap-1 rounded-md border border-emerald-500/40 bg-emerald-500/15 px-2 py-0.5 text-[11px] font-semibold text-emerald-200 hover:bg-emerald-500/25 disabled:opacity-60"
                    title="Parse Cornell Unofficial Transcript PDF/text locally in your browser"
                  >
                    <FileUp className="h-3 w-3" />
                    Import Transcript
                  </button>
                )}
                {selectedCourses.length > 0 && (
                  <button
                    type="button"
                    onClick={() => {
                      setDirty(true);
                      setSelectedCourses([]);
                    }}
                    className="inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[11px] text-zinc-400 hover:bg-zinc-800 hover:text-rose-300"
                  >
                    <Trash2 className="h-3 w-3" />
                    Clear all
                  </button>
                )}
              </div>
            </div>

            {selectedCourses.length === 0 ? (
              <p className="text-[11px] text-zinc-500">
                No courses added yet. Pick a track below, toggle common courses, or search by code/title.
              </p>
            ) : (
              <div className="flex flex-wrap gap-1.5">
                {selectedCourses.map((code) => (
                  <button
                    key={code}
                    type="button"
                    onClick={() => toggleCourse(code)}
                    className="inline-flex items-center gap-1 rounded-lg border border-emerald-500/40 bg-emerald-500/15 px-2 py-1 text-[11px] font-semibold text-emerald-200 hover:border-rose-500/40 hover:bg-rose-500/15 hover:text-rose-200"
                    title="Click to remove"
                  >
                    {code}
                    <X className="h-3 w-3" />
                  </button>
                ))}
              </div>
            )}

            <div className="border-t border-zinc-800/80 pt-2">
              <label className="flex cursor-pointer items-start gap-2 text-[11px] text-zinc-300">
                <input
                  type="checkbox"
                  checked={includeImplied}
                  onChange={(e) => {
                    setDirty(true);
                    setIncludeImplied(e.target.checked);
                  }}
                  className="mt-0.5 accent-emerald-500"
                />
                <span>
                  Assume foundational prerequisites (e.g., CS 2110 implies CS 1110; MATH 2940 implies
                  MATH 1920 &amp; 1910)
                </span>
              </label>

              {includeImplied && impliedPreview.length > 0 && (
                <div className="mt-2 flex flex-wrap items-center gap-1 text-[11px] text-zinc-400">
                  <span className="inline-flex items-center gap-1 text-sky-300">
                    <Sparkles className="h-3 w-3" />
                    Auto-satisfied:
                  </span>
                  {impliedPreview.map((code) => (
                    <span
                      key={code}
                      className="rounded-md border border-sky-500/30 bg-sky-500/10 px-1.5 py-0.5 text-[10px] font-medium text-sky-200"
                    >
                      {code}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* 1-Click Track Presets */}
          <div className="space-y-1.5">
            <div className="text-[11px] font-semibold uppercase tracking-wide text-zinc-400">
              1-Click Track Presets
            </div>
            <div className="flex flex-wrap gap-1.5">
              {visibleBundles.map((bundle) => {
                const active = bundle.courses.every((c) => selectedSet.has(c));
                return (
                  <button
                    key={bundle.label}
                    type="button"
                    title={bundle.hint}
                    onClick={() => applyBundle(bundle.courses)}
                    className={`inline-flex items-center gap-1 rounded-lg border px-2.5 py-1 text-[11px] font-medium transition ${
                      active
                        ? "border-emerald-500/50 bg-emerald-500/20 text-emerald-200"
                        : "border-zinc-700/80 bg-zinc-950 text-zinc-300 hover:border-emerald-500/40 hover:text-white"
                    }`}
                  >
                    {active ? <Check className="h-3 w-3 text-emerald-400" /> : <Plus className="h-3 w-3 text-zinc-400" />}
                    {bundle.label}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Common Cornell Prereqs */}
          <div className="space-y-1.5">
            <div className="text-[11px] font-semibold uppercase tracking-wide text-zinc-400">
              Common Cornell Prereqs
            </div>
            <div className="flex flex-wrap gap-1.5">
              {quickToggleCourses.map((code) => {
                const active = selectedSet.has(code);
                return (
                  <button
                    key={code}
                    type="button"
                    onClick={() => toggleCourse(code)}
                    className={`inline-flex items-center gap-1 rounded-lg border px-2 py-1 text-[11px] font-medium transition ${
                      active
                        ? "border-emerald-500/50 bg-emerald-500/15 text-emerald-200"
                        : "border-zinc-800 bg-zinc-950 text-zinc-400 hover:border-zinc-600 hover:text-zinc-200"
                    }`}
                  >
                    {active && <CheckCircle2 className="h-3 w-3 text-emerald-400" />}
                    {code}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Search Catalog Courses */}
          <div className="space-y-2">
            <div className="text-[11px] font-semibold uppercase tracking-wide text-zinc-400">
              Search Catalog or Add Course Code
            </div>
            <div className="relative flex gap-2">
              <div className="relative flex-1">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-zinc-500" />
                <input
                  type="text"
                  value={searchText}
                  onChange={(e) => setSearchText(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      if (customParsedCode) {
                        addCustomCode(customParsedCode);
                      } else if (options.length > 0 && !selectedSet.has(options[0].code)) {
                        toggleCourse(options[0].code);
                      }
                    }
                  }}
                  placeholder={
                    effectiveMode === "ilr"
                      ? "e.g. ECON 1110, ILRST 2100, ILROB 1220..."
                      : "e.g. CS 2110, linear algebra, AP 1110..."
                  }
                  className="w-full rounded-xl border border-zinc-700 bg-zinc-950 py-2 pl-9 pr-3 text-xs text-white placeholder-zinc-500 focus:border-emerald-500 focus:outline-none"
                />
              </div>
              {showCustomAdd && customParsedCode && (
                <button
                  type="button"
                  onClick={() => addCustomCode(customParsedCode)}
                  className="inline-flex items-center gap-1 rounded-xl border border-emerald-500/40 bg-emerald-500/15 px-3 py-2 text-xs font-semibold text-emerald-200 hover:bg-emerald-500/25"
                >
                  <Plus className="h-3.5 w-3.5" />
                  Add {customParsedCode}
                </button>
              )}
            </div>

            <div className="max-h-48 overflow-y-auto rounded-xl border border-zinc-800 bg-zinc-950/90 divide-y divide-zinc-800/70">
              {loadingOptions ? (
                <div className="flex items-center justify-center gap-2 py-5 text-xs text-zinc-400">
                  <Loader2 className="h-3.5 w-3.5 animate-spin text-emerald-400" />
                  Searching catalog...
                </div>
              ) : options.length === 0 ? (
                <div className="px-3 py-4 text-center text-[11px] text-zinc-500">
                  {customParsedCode
                    ? `Not in ${roster} cache yet — click "Add ${customParsedCode}" above to add it directly.`
                    : "No matching catalog courses cached."}
                </div>
              ) : (
                options.map((opt) => {
                  const active = selectedSet.has(opt.code);
                  return (
                    <button
                      key={opt.code}
                      type="button"
                      onClick={() => toggleCourse(opt.code)}
                      className={`flex w-full items-center justify-between gap-3 px-3 py-2 text-left transition ${
                        active ? "bg-emerald-500/10" : "hover:bg-zinc-900"
                      }`}
                    >
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <span className="font-semibold text-white">{opt.code}</span>
                          {opt.title && <span className="truncate text-zinc-300">{opt.title}</span>}
                        </div>
                        {opt.crosslists.length > 0 && (
                          <div className="text-[10px] text-zinc-500">
                            Cross-listed: {opt.crosslists.join(", ")}
                          </div>
                        )}
                      </div>
                      <span
                        className={`shrink-0 inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[11px] font-medium ${
                          active
                            ? "bg-emerald-500/20 text-emerald-300"
                            : "border border-zinc-700 bg-zinc-900 text-zinc-300"
                        }`}
                      >
                        {active ? (
                          <>
                            <Check className="h-3 w-3" />
                            Added
                          </>
                        ) : (
                          <>
                            <Plus className="h-3 w-3" />
                            Add
                          </>
                        )}
                      </span>
                    </button>
                  );
                })
              )}
            </div>
          </div>

          {error && (
            <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-xs text-rose-300">
              {error}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between gap-3 border-t border-zinc-800 px-5 py-3.5">
          <span className="text-[11px] text-zinc-400">
            {selectedCourses.length} course{selectedCourses.length === 1 ? "" : "s"} selected
          </span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onClose}
              disabled={saving}
              className="rounded-xl border border-zinc-700 px-3.5 py-2 text-xs font-medium text-zinc-300 hover:bg-zinc-800"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={saving}
              className="inline-flex items-center gap-1.5 rounded-xl bg-emerald-500 px-4 py-2 text-xs font-bold text-zinc-950 hover:bg-emerald-400 disabled:opacity-60"
            >
              {saving && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              Save Prereqs
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
