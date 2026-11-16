import React, { useEffect, useMemo, useRef, useState } from "react";
import { Check, ChevronDown, Search, Sparkles, X } from "lucide-react";
import type { Subject } from "../types";

export interface SubjectPreset {
  id: string;
  label: string;
  subjects: string[];
}

export const SUBJECT_PRESETS: SubjectPreset[] = [
  {
    id: "stem_te",
    label: "Common Tech Electives",
    subjects: ["MATH", "ORIE", "STSCI", "ECE", "INFO"],
  },
  {
    id: "info_cogsci",
    label: "InfoSci / CogSci / Ling",
    subjects: ["INFO", "COGST", "LING", "PSYCH", "PHIL"],
  },
  {
    id: "quant_econ",
    label: "Quant / Econ / Finance",
    subjects: ["ECON", "AEM", "ORIE", "STSCI"],
  },
];

interface Props {
  subjects: Subject[];
  selected: string[];
  onChange: (next: string[]) => void;
  excludeSubjects?: string[];
  placeholder?: string;
}

export function MultiSubjectSelect({
  subjects,
  selected,
  onChange,
  excludeSubjects = [],
  placeholder = "All Subjects",
}: Props) {
  const [open, setOpen] = useState(false);
  const [filterText, setFilterText] = useState("");
  const containerRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  const excludedSet = useMemo(
    () => new Set(excludeSubjects.map((s) => s.toUpperCase())),
    [excludeSubjects]
  );

  const selectedSet = useMemo(() => new Set(selected.map((s) => s.toUpperCase())), [selected]);

  useEffect(() => {
    function handleClickOutside(ev: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(ev.target as Node)) {
        setOpen(false);
      }
    }
    function handleKeyDown(ev: KeyboardEvent) {
      if (ev.key === "Escape") {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, []);

  useEffect(() => {
    if (open) {
      setTimeout(() => searchInputRef.current?.focus(), 20);
    } else {
      setFilterText("");
    }
  }, [open]);

  const filteredSubjects = useMemo(() => {
    const q = filterText.trim().toLowerCase();
    const list = subjects.filter((s) => !excludedSet.has(s.value.toUpperCase()));
    if (!q) {
      // Keep selected subjects grouped near top if nothing typed
      return list;
    }
    return list.filter(
      (s) => s.value.toLowerCase().includes(q) || s.descr.toLowerCase().includes(q)
    );
  }, [subjects, excludedSet, filterText]);

  const availableValuesSet = useMemo(
    () => new Set(subjects.filter((s) => !excludedSet.has(s.value.toUpperCase())).map((s) => s.value.toUpperCase())),
    [subjects, excludedSet]
  );

  function toggleSubject(code: string) {
    const upper = code.toUpperCase();
    if (selectedSet.has(upper)) {
      onChange(selected.filter((s) => s.toUpperCase() !== upper));
    } else {
      onChange([...selected, upper]);
    }
  }

  function applyPreset(preset: SubjectPreset) {
    const valid = preset.subjects.filter((s) =>
      availableValuesSet.size > 0 ? availableValuesSet.has(s) : !excludedSet.has(s)
    );
    onChange(valid);
    setOpen(false);
  }

  const buttonSummary =
    selected.length === 0
      ? placeholder
      : selected.length <= 2
        ? selected.join(", ")
        : `${selected.slice(0, 2).join(", ")} +${selected.length - 2}`;

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="listbox"
        aria-expanded={open}
        className={`flex w-full items-center justify-between gap-2 rounded-xl border px-3 py-2.5 text-left text-sm transition focus:outline-none ${
          open
            ? "border-emerald-500 bg-zinc-950 text-white"
            : selected.length > 0
              ? "border-emerald-500/40 bg-zinc-950 text-white"
              : "border-zinc-700 bg-zinc-950 text-zinc-200 hover:border-zinc-600"
        }`}
      >
        <span className="truncate">{buttonSummary}</span>
        <span className="flex items-center gap-1">
          {selected.length > 0 && (
            <span
              role="button"
              tabIndex={0}
              title="Clear selected subjects"
              onClick={(e) => {
                e.stopPropagation();
                onChange([]);
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.stopPropagation();
                  onChange([]);
                }
              }}
              className="rounded p-0.5 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
            >
              <X className="h-3.5 w-3.5" />
            </span>
          )}
          <ChevronDown className={`h-4 w-4 text-zinc-400 transition-transform ${open ? "rotate-180" : ""}`} />
        </span>
      </button>

      {open && (
        <div className="absolute left-0 top-full z-40 mt-1.5 w-full min-w-[290px] overflow-hidden rounded-2xl border border-zinc-700 bg-zinc-950 shadow-2xl">
          {/* Quick Presets */}
          <div className="border-b border-zinc-800 bg-zinc-900/70 p-2">
            <div className="mb-1.5 flex items-center justify-between px-1 text-[10px] font-semibold uppercase tracking-wide text-zinc-400">
              <span className="inline-flex items-center gap-1">
                <Sparkles className="h-3 w-3 text-emerald-400" />
                Quick Subject Presets
              </span>
              {selected.length > 0 && (
                <button
                  type="button"
                  onClick={() => onChange([])}
                  className="text-emerald-400 hover:underline"
                >
                  Clear all ({selected.length})
                </button>
              )}
            </div>
            <div className="flex flex-wrap gap-1">
              {SUBJECT_PRESETS.map((preset) => (
                <button
                  key={preset.id}
                  type="button"
                  onClick={() => applyPreset(preset)}
                  className="rounded-lg border border-zinc-700/80 bg-zinc-950 px-2 py-1 text-[11px] font-medium text-zinc-200 hover:border-emerald-500/50 hover:text-emerald-300"
                >
                  {preset.label}
                </button>
              ))}
            </div>
          </div>

          {/* Search box */}
          <div className="border-b border-zinc-800 p-2">
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-2.5 h-3.5 w-3.5 text-zinc-500" />
              <input
                ref={searchInputRef}
                type="text"
                value={filterText}
                onChange={(e) => setFilterText(e.target.value)}
                placeholder="Filter subjects (e.g. ECON, Psych...)"
                className="w-full rounded-lg border border-zinc-800 bg-zinc-900 py-1.5 pl-8 pr-3 text-xs text-white placeholder-zinc-500 focus:border-emerald-500 focus:outline-none"
              />
            </div>
          </div>

          {/* Options List */}
          <div role="listbox" aria-multiselectable="true" className="max-h-64 overflow-y-auto p-1">
            {filteredSubjects.length === 0 ? (
              <div className="px-3 py-4 text-center text-xs text-zinc-500">No matching subjects</div>
            ) : (
              filteredSubjects.map((s) => {
                const isSelected = selectedSet.has(s.value.toUpperCase());
                return (
                  <button
                    key={s.value}
                    type="button"
                    role="option"
                    aria-selected={isSelected}
                    onClick={() => toggleSubject(s.value)}
                    className={`flex w-full items-center justify-between gap-2 rounded-lg px-2.5 py-1.5 text-left text-xs transition ${
                      isSelected
                        ? "bg-emerald-500/15 text-emerald-200"
                        : "text-zinc-300 hover:bg-zinc-900 hover:text-white"
                    }`}
                  >
                    <div className="flex min-w-0 items-center gap-2">
                      <span
                        className={`flex h-4 w-4 shrink-0 items-center justify-center rounded border ${
                          isSelected
                            ? "border-emerald-400 bg-emerald-500 text-zinc-950"
                            : "border-zinc-700 bg-zinc-900"
                        }`}
                      >
                        {isSelected && <Check className="h-3 w-3 stroke-[3]" />}
                      </span>
                      <span className="font-mono font-semibold text-white">{s.value}</span>
                      <span className="truncate text-zinc-400">{s.descr}</span>
                    </div>
                    {s.synced_at && (
                      <span
                        title="Cached locally"
                        className="h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-400/70"
                      />
                    )}
                  </button>
                );
              })
            )}
          </div>

          <div className="flex items-center justify-between border-t border-zinc-800 bg-zinc-900/60 px-3 py-1.5 text-[11px] text-zinc-400">
            <span>{selected.length === 0 ? "Searching all cached subjects" : `${selected.length} selected`}</span>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="font-semibold text-emerald-400 hover:text-emerald-300"
            >
              Done
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
