import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CalendarCheck2,
  Check,
  CheckSquare,
  Clock,
  Edit3,
  Eraser,
  FileUp,
  GraduationCap,
  ListChecks,
  Loader2,
  Minus,
  Plus,
  RotateCcw,
  Search,
  Sparkles,
  Square,
  X,
} from "lucide-react";
import { api } from "../api/client";
import type {
  AttrMatchMode,
  CatalogSubjectRefreshedSSE,
  CourseDetailMeta,
  CourseSearchPreset,
  CSCurriculumMode,
  CsChecklistPayload,
  CsChecklistQuickOption,
  CsChecklistSlot,
  CsChecklistSlotInput,
  CSRequirementMode,
  PrereqCourseOption,
  Roster,
  User,
} from "../types";
import { CompletedPrereqsModal } from "./CompletedPrereqsModal";
import { TranscriptImportModal } from "./TranscriptImportModal";

const COURSE_CODE_RE = /([A-Za-z]{2,8})[\s\-:]*(\d{3,4}[A-Za-z]?)/g;

function parseCourseInputTokens(raw: string): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  for (const match of raw.matchAll(COURSE_CODE_RE)) {
    const code = `${match[1].toUpperCase()} ${match[2].toUpperCase()}`;
    if (!seen.has(code)) {
      seen.add(code);
      out.push(code);
    }
  }
  return out;
}

function formatUnitsRange(unitsMin?: number | null, unitsMax?: number | null): string {
  const lo = Number(unitsMin ?? 0);
  const hi = Number(unitsMax ?? 0);
  if (lo <= 0 && hi <= 0) return "";
  if (hi <= 0 || Math.abs(lo - hi) < 1e-6) {
    const v = lo > 0 ? lo : hi;
    return Number.isInteger(v) ? String(v) : String(v);
  }
  return `${lo}-${hi}`;
}

interface Props {
  user: User;
  initialRoster?: string;
  lastCatalogRefresh?: CatalogSubjectRefreshedSSE | null;
  onUserUpdated?: (user: User) => void;
  onLaunchSearch: (preset: CourseSearchPreset) => void;
}

function buildPresetFromSlots(
  selectedSlots: CsChecklistSlot[],
  matchMode: AttrMatchMode
): CourseSearchPreset {
  const attrs = new Set<string>();
  const subjects = new Set<string>();
  let csReq: CSRequirementMode = "";
  let minCredits: number | "" = "";
  let query = "";

  for (const sl of selectedSlots) {
    for (const a of sl.search?.attrs || []) {
      attrs.add(a);
    }
    for (const su of sl.search?.subjects || []) {
      subjects.add(su);
    }
    if (!csReq && sl.search?.cs_requirement) {
      csReq = sl.search.cs_requirement;
    }
    if (!minCredits && sl.search?.min_credits) {
      minCredits = sl.search.min_credits;
    }
    if (selectedSlots.length === 1 && sl.search?.q) {
      query = sl.search.q;
    }
  }

  const label =
    selectedSlots.length === 1
      ? `${selectedSlots[0].label} (${selectedSlots[0].expected})`
      : `${selectedSlots.length} checklist boxes (${selectedSlots.map((s) => s.label).join(", ")})`;

  return {
    id: Date.now(),
    label,
    q: query,
    subjects: attrs.size > 0 && csReq === "" ? [] : Array.from(subjects),
    cs_requirement: csReq,
    attrs: Array.from(attrs),
    attr_match: matchMode,
    min_credits: minCredits,
  };
}

interface QuickAddCardProps {
  title: string;
  subtitle: string;
  icon: React.ReactNode;
  tone: "taken" | "taking";
  roster: string;
  courses: string[];
  details?: Record<string, CourseDetailMeta>;
  alreadyTakenSet: Set<string>;
  alreadyTakingSet: Set<string>;
  saving: boolean;
  placeholder: string;
  addLabel: string;
  emptyText: string;
  headerActions?: React.ReactNode;
  onAdd: (codes: string[]) => Promise<void>;
  onRemove: (code: string) => Promise<void>;
  onPromoteToTaken?: (code: string) => Promise<void>;
}

function CourseQuickAddCard({
  title,
  subtitle,
  icon,
  tone,
  roster,
  courses,
  details,
  alreadyTakenSet,
  alreadyTakingSet,
  saving,
  placeholder,
  addLabel,
  emptyText,
  headerActions,
  onAdd,
  onRemove,
  onPromoteToTaken,
}: QuickAddCardProps) {
  const [input, setInput] = useState("");
  const [options, setOptions] = useState<PrereqCourseOption[]>([]);
  const [focused, setFocused] = useState(false);

  useEffect(() => {
    const q = input.trim();
    if (!q || !roster) {
      setOptions([]);
      return;
    }
    let cancelled = false;
    const handle = setTimeout(() => {
      api
        .getPrereqOptions(roster, q, 10, "cs")
        .then((res) => {
          if (!cancelled) setOptions(res.options);
        })
        .catch(() => {
          if (!cancelled) setOptions([]);
        });
    }, 150);
    return () => {
      cancelled = true;
      clearTimeout(handle);
    };
  }, [input, roster]);

  const handleSubmitCodes = async (codes: string[]) => {
    const clean = codes.map((c) => c.trim().toUpperCase()).filter(Boolean);
    if (clean.length === 0) return;
    await onAdd(clean);
    setInput("");
    setOptions([]);
  };

  const isTakingTone = tone === "taking";
  const borderAccent = isTakingTone ? "border-amber-500/30" : "border-zinc-800";
  const chipCls = isTakingTone
    ? "border-amber-500/40 bg-amber-500/10 text-amber-200"
    : "border-emerald-500/35 bg-emerald-500/10 text-emerald-200";
  const subBadgeCls = isTakingTone
    ? "bg-amber-500/20 text-amber-100"
    : "bg-emerald-500/20 text-emerald-100";
  const btnCls = isTakingTone
    ? "bg-amber-500 text-zinc-950 hover:bg-amber-400"
    : "bg-sky-500 text-zinc-950 hover:bg-sky-400";

  return (
    <div className={`rounded-2xl border ${borderAccent} bg-zinc-900/75 p-4 space-y-3`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            {icon}
            <h3 className="text-xs font-bold uppercase tracking-wider text-zinc-200">{title}</h3>
            {saving && (
              <Loader2
                className={`h-3.5 w-3.5 animate-spin ${
                  isTakingTone ? "text-amber-400" : "text-sky-400"
                }`}
              />
            )}
          </div>
          <p className="mt-0.5 text-[11px] text-zinc-400">{subtitle}</p>
        </div>
        {headerActions && <div className="flex flex-wrap items-center gap-2">{headerActions}</div>}
      </div>

      <div className="relative flex flex-wrap gap-2">
        <div className="relative min-w-[200px] flex-1">
          <input
            type="text"
            value={input}
            onFocus={() => setFocused(true)}
            onBlur={() => setTimeout(() => setFocused(false), 180)}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                const parsed = parseCourseInputTokens(input);
                if (parsed.length > 0) {
                  void handleSubmitCodes(parsed);
                } else if (options.length > 0) {
                  void handleSubmitCodes([options[0].code]);
                }
              }
            }}
            placeholder={placeholder}
            className={`w-full rounded-xl border border-zinc-700 bg-zinc-950 px-3 py-2 text-xs text-white placeholder-zinc-500 focus:outline-none ${
              isTakingTone ? "focus:border-amber-500" : "focus:border-sky-500"
            }`}
          />

          {focused && input.trim() && options.length > 0 && (
            <div className="absolute left-0 right-0 top-full z-30 mt-1 max-h-56 overflow-y-auto rounded-xl border border-zinc-700 bg-zinc-950 p-1 shadow-2xl">
              {options.map((opt) => {
                const inTaken = alreadyTakenSet.has(opt.code);
                const inTaking = alreadyTakingSet.has(opt.code);
                const alreadyInThisList = isTakingTone ? inTaking : inTaken;
                return (
                  <button
                    key={opt.code}
                    type="button"
                    disabled={alreadyInThisList}
                    onMouseDown={(e) => {
                      e.preventDefault();
                      if (!alreadyInThisList) {
                        void handleSubmitCodes([opt.code]);
                      }
                    }}
                    className={`flex w-full items-center justify-between gap-2 rounded-lg px-2.5 py-1.5 text-left text-xs ${
                      alreadyInThisList
                        ? "cursor-default text-zinc-500"
                        : "text-zinc-200 hover:bg-zinc-800"
                    }`}
                  >
                    <span className="truncate">
                      <span className="font-mono font-semibold text-white">{opt.code}</span>
                      {opt.title ? <span className="ml-2 text-zinc-400">{opt.title}</span> : null}
                    </span>
                    {alreadyInThisList ? (
                      <span
                        className={`text-[10px] ${
                          isTakingTone ? "text-amber-300" : "text-emerald-400"
                        }`}
                      >
                        {isTakingTone ? "Taking" : "Taken"}
                      </span>
                    ) : isTakingTone && inTaken ? (
                      <span className="text-[10px] text-emerald-400">Taken</span>
                    ) : (
                      <Plus
                        className={`h-3.5 w-3.5 shrink-0 ${
                          isTakingTone ? "text-amber-400" : "text-sky-400"
                        }`}
                      />
                    )}
                  </button>
                );
              })}
            </div>
          )}
        </div>

        <button
          type="button"
          disabled={saving || (!parseCourseInputTokens(input).length && options.length === 0)}
          onClick={() => {
            const parsed = parseCourseInputTokens(input);
            if (parsed.length > 0) {
              void handleSubmitCodes(parsed);
            } else if (options.length > 0) {
              void handleSubmitCodes([options[0].code]);
            }
          }}
          className={`inline-flex items-center gap-1 rounded-xl px-3.5 py-2 text-xs font-semibold disabled:cursor-not-allowed disabled:opacity-40 ${btnCls}`}
        >
          <Plus className="h-3.5 w-3.5" />
          {addLabel}
        </button>
      </div>

      {courses.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {courses.map((code) => {
            const det = details?.[code];
            const pillText = isTakingTone ? det?.sem : det?.gr;
            return (
              <span
                key={code}
                title={
                  det
                    ? [det.sem, det.gr, det.cr ? `${det.cr} cr` : ""].filter(Boolean).join(" • ")
                    : undefined
                }
                className={`inline-flex items-center gap-1 rounded-lg border px-2 py-0.5 font-mono text-[11px] font-medium ${chipCls}`}
              >
                <span>{code}</span>
                {pillText && (
                  <span className={`rounded px-1 text-[10px] font-semibold ${subBadgeCls}`}>
                    {pillText}
                  </span>
                )}
                {onPromoteToTaken && (
                  <button
                    type="button"
                    disabled={saving}
                    onClick={() => void onPromoteToTaken(code)}
                    title={`Mark ${code} as Completed`}
                    className="rounded p-0.5 text-amber-300/80 hover:bg-emerald-500/20 hover:text-emerald-200"
                  >
                    <Check className="h-3 w-3" />
                  </button>
                )}
                <button
                  type="button"
                  disabled={saving}
                  onClick={() => void onRemove(code)}
                  title={`Remove ${code}`}
                  className={`rounded p-0.5 ${
                    isTakingTone
                      ? "text-amber-300/80 hover:bg-amber-500/20 hover:text-white"
                      : "text-emerald-300/80 hover:bg-emerald-500/20 hover:text-white"
                  }`}
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            );
          })}
        </div>
      ) : (
        <p className="text-[11px] text-zinc-500">{emptyText}</p>
      )}
    </div>
  );
}

export function CsChecklistPage({ user, initialRoster, lastCatalogRefresh, onUserUpdated, onLaunchSearch }: Props) {
  const [rosters, setRosters] = useState<Roster[]>([]);
  const [selectedRoster, setSelectedRoster] = useState(initialRoster || "");
  const [checklist, setChecklist] = useState<CsChecklistPayload | null>(null);
  const [draftSlots, setDraftSlots] = useState<Record<string, CsChecklistSlotInput>>({});
  const [editingSlotId, setEditingSlotId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<CsChecklistSlotInput>({
    course: "",
    title: "",
    cr: "",
    sem: "",
    gr: "",
    notes: "",
  });
  const [editSaveMode, setEditSaveMode] = useState<"taken" | "taking" | "box">("taken");
  const [slotPickerFocused, setSlotPickerFocused] = useState(false);
  const [slotSearchDirty, setSlotSearchDirty] = useState(false);
  const [slotSearchOptions, setSlotSearchOptions] = useState<PrereqCourseOption[]>([]);
  const [slotSuggestionsCache, setSlotSuggestionsCache] = useState<
    Record<string, CsChecklistQuickOption[]>
  >({});
  const [slotSuggestionsLoading, setSlotSuggestionsLoading] = useState(false);
  const [selectedEmptyIds, setSelectedEmptyIds] = useState<string[]>([]);
  const [multiAttrMatch, setMultiAttrMatch] = useState<AttrMatchMode>("any");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [prereqsOpen, setPrereqsOpen] = useState(false);
  const [transcriptOpen, setTranscriptOpen] = useState(false);
  const [takenSaving, setTakenSaving] = useState(false);
  const [takingSaving, setTakingSaving] = useState(false);

  useEffect(() => {
    if (initialRoster && initialRoster !== selectedRoster) {
      setSelectedRoster(initialRoster);
    }
  }, [initialRoster]);

  useEffect(() => {
    api
      .listRosters()
      .then((res) => {
        setRosters(res.rosters);
        if (!selectedRoster) {
          const def = res.rosters.find((r) => r.is_default === 1) || res.rosters[0];
          if (def) setSelectedRoster(def.slug);
        }
      })
      .catch(() => {});
  }, []);

  const loadChecklist = useCallback(async (rosterSlug: string) => {
    if (!rosterSlug) return;
    setLoading(true);
    setError("");
    try {
      const data = await api.getCsChecklist(rosterSlug);
      setChecklist(data);
      setDraftSlots(data.manual_slots || {});
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load CS Checklist");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedRoster) {
      void loadChecklist(selectedRoster);
    }
  }, [selectedRoster, loadChecklist]);

  useEffect(() => {
    if (!lastCatalogRefresh || !selectedRoster || saving || editingSlotId) return;
    const missing = checklist?.missing_metadata_courses || [];
    const subjPrefix = `${lastCatalogRefresh.subject} `;
    const relevant =
      lastCatalogRefresh.historical_lookup ||
      missing.some((code) => code.startsWith(subjPrefix));
    if (!relevant) return;

    let cancelled = false;
    api
      .getCsChecklist(selectedRoster)
      .then((data) => {
        if (!cancelled) {
          setChecklist(data);
          setDraftSlots(data.manual_slots || {});
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [lastCatalogRefresh, selectedRoster]);

  useEffect(() => {
    if (!editingSlotId || !selectedRoster || !slotSearchDirty) {
      setSlotSearchOptions([]);
      return;
    }
    const q = editForm.course.trim();
    if (!q) {
      setSlotSearchOptions([]);
      return;
    }
    let cancelled = false;
    const handle = setTimeout(() => {
      api
        .getPrereqOptions(selectedRoster, q, 10, "cs")
        .then((res) => {
          if (!cancelled) setSlotSearchOptions(res.options);
        })
        .catch(() => {
          if (!cancelled) setSlotSearchOptions([]);
        });
    }, 140);
    return () => {
      cancelled = true;
      clearTimeout(handle);
    };
  }, [editingSlotId, editForm.course, selectedRoster]);

  const updateTakenList = async (nextCompleted: string[]) => {
    setTakenSaving(true);
    setError("");
    try {
      const normalized = Array.from(new Set(nextCompleted.map((c) => c.trim().toUpperCase()).filter(Boolean))).sort();
      const res = await api.updateUserPrereqs(
        {
          completed_courses: normalized,
          include_implied_prereqs: user.include_implied_prereqs ?? true,
        },
        selectedRoster || undefined
      );
      onUserUpdated?.({
        ...user,
        completed_courses: res.completed_courses,
        include_implied_prereqs: res.include_implied_prereqs,
      });
      if (selectedRoster) {
        await loadChecklist(selectedRoster);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update completed courses");
    } finally {
      setTakenSaving(false);
    }
  };

  const addTakenCourses = async (codes: string[]) => {
    const clean = codes.map((c) => c.trim().toUpperCase()).filter(Boolean);
    if (clean.length === 0) return;
    const current = checklist?.completed_courses || user.completed_courses || [];
    await updateTakenList([...current, ...clean]);
  };

  const removeTakenCourse = async (code: string) => {
    const current = checklist?.completed_courses || user.completed_courses || [];
    await updateTakenList(current.filter((c) => c !== code));
  };

  const updateTakingList = async (nextInProgress: string[], nextCompletedOverride?: string[]) => {
    if (!checklist) return;
    setTakingSaving(true);
    setError("");
    try {
      const normalizedTaking = Array.from(
        new Set(nextInProgress.map((c) => c.trim().toUpperCase()).filter(Boolean))
      ).sort();
      const updated = await api.updateCsChecklist(
        {
          college: checklist.college,
          curriculum: checklist.curriculum,
          include_active_schedule: checklist.include_active_schedule,
          pe_completed: checklist.pe_completed,
          slots: draftSlots,
          sync_in_progress_courses: normalizedTaking,
          ...(nextCompletedOverride !== undefined
            ? { sync_completed_courses: nextCompletedOverride }
            : {}),
        },
        selectedRoster || undefined
      );
      setChecklist(updated);
      setDraftSlots(updated.manual_slots || draftSlots);
      onUserUpdated?.({
        ...user,
        completed_courses: updated.completed_courses,
        completed_course_details: updated.completed_course_details,
        in_progress_courses: updated.in_progress_courses,
        in_progress_course_details: updated.in_progress_course_details,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update currently taking courses");
    } finally {
      setTakingSaving(false);
    }
  };

  const addTakingCourses = async (codes: string[]) => {
    const clean = codes.map((c) => c.trim().toUpperCase()).filter(Boolean);
    if (clean.length === 0) return;
    const current = checklist?.in_progress_courses || user.in_progress_courses || [];
    await updateTakingList([...current, ...clean]);
  };

  const removeTakingCourse = async (code: string) => {
    const current = checklist?.in_progress_courses || user.in_progress_courses || [];
    await updateTakingList(current.filter((c) => c !== code));
  };

  const promoteTakingToTaken = async (code: string) => {
    if (!checklist) return;
    const nextTaken = Array.from(new Set([...checklist.completed_courses, code])).sort();
    const nextTaking = checklist.in_progress_courses.filter((c) => c !== code);
    await updateTakingList(nextTaking, nextTaken);
  };

  const persistChecklist = async (
    nextCollege: "arts" | "engineering",
    nextCurriculum: CSCurriculumMode,
    nextIncludeSched: boolean,
    nextPe: number,
    nextSlots: Record<string, CsChecklistSlotInput>,
    syncCompletedCourses?: string[],
    syncInProgressCourses?: string[]
  ) => {
    setSaving(true);
    setError("");
    try {
      const updated = await api.updateCsChecklist(
        {
          college: nextCollege,
          curriculum: nextCurriculum,
          include_active_schedule: nextIncludeSched,
          pe_completed: nextPe,
          slots: nextSlots,
          ...(syncCompletedCourses !== undefined
            ? { sync_completed_courses: syncCompletedCourses }
            : {}),
          ...(syncInProgressCourses !== undefined
            ? { sync_in_progress_courses: syncInProgressCourses }
            : {}),
        },
        selectedRoster || undefined
      );
      setChecklist(updated);
      setDraftSlots(updated.manual_slots || nextSlots);
      if (syncCompletedCourses !== undefined || syncInProgressCourses !== undefined) {
        onUserUpdated?.({
          ...user,
          completed_courses: updated.completed_courses,
          completed_course_details: updated.completed_course_details,
          in_progress_courses: updated.in_progress_courses,
          in_progress_course_details: updated.in_progress_course_details,
        });
      }
      setSelectedEmptyIds((prev) =>
        prev.filter((id) =>
          updated.sections.some((sec) => sec.slots.some((sl) => sl.id === id && !sl.filled))
        )
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save checklist changes");
    } finally {
      setSaving(false);
    }
  };

  const slotLookup = useMemo(() => {
    const map = new Map<string, CsChecklistSlot>();
    if (!checklist) return map;
    for (const sec of checklist.sections) {
      for (const sl of sec.slots) {
        map.set(sl.id, sl);
      }
    }
    return map;
  }, [checklist]);

  const selectedSlots = useMemo(
    () => selectedEmptyIds.map((id) => slotLookup.get(id)).filter((x): x is CsChecklistSlot => Boolean(x)),
    [selectedEmptyIds, slotLookup]
  );

  const toggleEmptySlotSelect = (slot: CsChecklistSlot) => {
    setSelectedEmptyIds((prev) =>
      prev.includes(slot.id) ? prev.filter((id) => id !== slot.id) : [...prev, slot.id]
    );
  };

  const startEditSlot = (slot: CsChecklistSlot) => {
    setEditingSlotId(slot.id);
    setSlotSearchDirty(false);
    setSlotSearchOptions([]);
    setEditSaveMode(
      slot.source === "in_progress" ? "taking" : slot.source === "schedule" ? "box" : "taken"
    );
    const existing = draftSlots[slot.id];
    const startCourse = existing?.course || slot.course || "";
    const startTitle =
      existing && existing.course === slot.course
        ? existing.title || ""
        : "";
    setEditForm({
      course: startCourse,
      title: startTitle,
      cr: existing?.cr || slot.cr || "",
      sem: existing?.sem || slot.sem || "",
      gr: existing?.gr || slot.gr || "",
      notes: existing?.notes || slot.notes || "",
      pinned: true,
      cleared: false,
    });

    const hasManyFixedQuick = (slot.quick_options?.length ?? 0) >= 4;
    const cacheKey = `${selectedRoster}:${slot.id}`;
    const hasSearchHints = Boolean(
      slot.search?.cs_requirement ||
        (slot.search?.attrs && slot.search.attrs.length > 0) ||
        (slot.search?.subjects && slot.search.subjects.length > 0)
    );
    if (!hasManyFixedQuick && hasSearchHints && selectedRoster && !slotSuggestionsCache[cacheKey]) {
      setSlotSuggestionsLoading(true);
      api
        .searchCourses(selectedRoster, "", {
          cs_requirement: slot.search?.cs_requirement,
          attrs: slot.search?.attrs,
          subjects: slot.search?.subjects,
          min_credits: slot.search?.min_credits,
          curriculum: checklist?.curriculum,
          refresh_stale: false,
          limit: 16,
        })
        .then((res) => {
          const seen = new Set<string>();
          const items: CsChecklistQuickOption[] = [];
          for (const c of res.courses) {
            const code = `${c.subject.toUpperCase()} ${c.catalog_nbr.toUpperCase()}`;
            if (seen.has(code)) continue;
            seen.add(code);
            items.push({
              code,
              title: c.title_long || c.title_short || "",
              cr: formatUnitsRange(c.units_min, c.units_max),
            });
            if (items.length >= 8) break;
          }
          setSlotSuggestionsCache((prev) => ({ ...prev, [cacheKey]: items }));
        })
        .catch(() => {})
        .finally(() => setSlotSuggestionsLoading(false));
    }
  };

  const applySlotCourse = async (
    slotId: string,
    rawCourse: string,
    crOverride?: string,
    titleOverride?: string
  ) => {
    if (!checklist) return;
    const prevSlot = slotLookup.get(slotId);
    const prevCourse = (prevSlot?.course || "").trim().toUpperCase();
    const parsed = parseCourseInputTokens(rawCourse);
    const nextCourse = (parsed[0] || rawCourse).trim().toUpperCase();
    const courseChanged = nextCourse !== prevCourse;
    const resolvedCr =
      crOverride !== undefined
        ? crOverride
        : courseChanged && editForm.cr === (prevSlot?.cr || "")
          ? ""
          : editForm.cr.trim();
    const nextSlots: Record<string, CsChecklistSlotInput> = {
      ...draftSlots,
      [slotId]: {
        ...editForm,
        course: nextCourse,
        title: titleOverride !== undefined ? titleOverride : courseChanged ? "" : editForm.title.trim(),
        cr: resolvedCr,
        pinned: Boolean(nextCourse),
        cleared: !nextCourse,
      },
    };
    let syncCompleted: string[] | undefined;
    let syncInProgress: string[] | undefined;
    if (nextCourse) {
      if (editSaveMode === "taken") {
        syncCompleted = Array.from(new Set([...checklist.completed_courses, nextCourse])).sort();
        if (checklist.in_progress_courses.includes(nextCourse)) {
          syncInProgress = checklist.in_progress_courses.filter((c) => c !== nextCourse);
        }
      } else if (editSaveMode === "taking") {
        syncInProgress = Array.from(new Set([...checklist.in_progress_courses, nextCourse])).sort();
        if (checklist.completed_courses.includes(nextCourse)) {
          syncCompleted = checklist.completed_courses.filter((c) => c !== nextCourse);
        }
      }
    }
    setDraftSlots(nextSlots);
    setEditingSlotId(null);
    setSlotSearchOptions([]);
    setSlotPickerFocused(false);
    await persistChecklist(
      checklist.college,
      checklist.curriculum,
      checklist.include_active_schedule,
      checklist.pe_completed,
      nextSlots,
      syncCompleted,
      syncInProgress
    );
  };

  const saveEditSlot = async (slotId: string) => {
    await applySlotCourse(slotId, editForm.course);
  };

  const clearSlot = async (slotId: string) => {
    if (!checklist) return;
    const nextSlots: Record<string, CsChecklistSlotInput> = {
      ...draftSlots,
      [slotId]: {
        course: "",
        title: "",
        cr: "",
        sem: "",
        gr: "",
        notes: "",
        pinned: false,
        cleared: true,
      },
    };
    setDraftSlots(nextSlots);
    await persistChecklist(
      checklist.college,
      checklist.curriculum,
      checklist.include_active_schedule,
      checklist.pe_completed,
      nextSlots
    );
  };

  const resetAllOverrides = async () => {
    if (!checklist) return;
    setDraftSlots({});
    setSelectedEmptyIds([]);
    await persistChecklist(
      checklist.college,
      checklist.curriculum,
      checklist.include_active_schedule,
      checklist.pe_completed,
      {}
    );
  };

  return (
    <div className="space-y-4">
      {/* Header & Controls Card */}
      <div className="rounded-2xl border border-zinc-800 bg-zinc-900/80 p-4 space-y-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <GraduationCap className="h-5 w-5 text-emerald-400" />
              <h2 className="text-base font-bold text-white">
                Interactive CS Major Checklist (
                {checklist?.college === "engineering" ? "Engineering BS" : "Arts & Sciences BA"})
              </h2>
              {saving && (
                <span className="inline-flex items-center gap-1 rounded-full bg-zinc-800 px-2 py-0.5 text-[11px] text-zinc-300">
                  <Loader2 className="h-3 w-3 animate-spin text-emerald-400" />
                  Saving...
                </span>
              )}
            </div>
            <p className="mt-1 text-xs text-zinc-400">
              Auto-populates from completed courses,{" "}
              <span className="font-medium text-amber-300">currently taking</span> classes, &amp;
              active What-If schedule. Click any{" "}
              <span className="text-emerald-300 font-medium">empty box</span> to select and search
              for courses that fill your missing requirements.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <select
              value={selectedRoster}
              onChange={(e) => setSelectedRoster(e.target.value)}
              className="rounded-xl border border-zinc-700 bg-zinc-950 px-3 py-1.5 text-xs text-white"
            >
              {rosters.map((r) => (
                <option key={r.slug} value={r.slug}>
                  {r.descr} ({r.slug})
                </option>
              ))}
            </select>

            <button
              type="button"
              onClick={() => setTranscriptOpen(true)}
              className="inline-flex items-center gap-1.5 rounded-xl border border-emerald-500/45 bg-emerald-500/15 px-3 py-1.5 text-xs font-semibold text-emerald-200 hover:bg-emerald-500/25"
              title="Parse Cornell Unofficial Transcript PDF/text locally in your browser"
            >
              <FileUp className="h-3.5 w-3.5" />
              Import Transcript
            </button>

            <button
              type="button"
              onClick={() => setPrereqsOpen(true)}
              className="inline-flex items-center gap-1.5 rounded-xl border border-sky-500/40 bg-sky-500/15 px-3 py-1.5 text-xs font-medium text-sky-200 hover:bg-sky-500/25"
            >
              <ListChecks className="h-3.5 w-3.5" />
              Completed Courses ({checklist?.completed_courses.length ?? 0})
            </button>

            <button
              type="button"
              onClick={() => void resetAllOverrides()}
              className="inline-flex items-center gap-1.5 rounded-xl border border-zinc-700 px-2.5 py-1.5 text-xs text-zinc-300 hover:bg-zinc-800"
              title="Reset manual edits and cleared slots back to auto-fill from Completed + What-If Schedule"
            >
              <RotateCcw className="h-3.5 w-3.5" />
              Re-auto-fill
            </button>
          </div>
        </div>

        {checklist && (
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-zinc-800/80 pt-3">
            <div className="flex flex-wrap items-center gap-2">
              <div className="inline-flex rounded-xl border border-zinc-700 bg-zinc-950 p-0.5 text-xs">
                {(["arts", "engineering"] as const).map((col) => (
                  <button
                    key={col}
                    type="button"
                    onClick={() =>
                      void persistChecklist(
                        col,
                        checklist.curriculum,
                        checklist.include_active_schedule,
                        checklist.pe_completed,
                        draftSlots
                      )
                    }
                    className={`rounded-lg px-2.5 py-1 font-semibold transition ${
                      checklist.college === col
                        ? "bg-emerald-500 text-zinc-950"
                        : "text-zinc-400 hover:text-white"
                    }`}
                  >
                    {col === "arts" ? "A&S (BA)" : "Engineering (BS)"}
                  </button>
                ))}
              </div>

              <div className="inline-flex rounded-xl border border-zinc-700 bg-zinc-950 p-0.5 text-xs">
                {(["current", "pre2024"] as const).map((cur) => (
                  <button
                    key={cur}
                    type="button"
                    onClick={() =>
                      void persistChecklist(
                        checklist.college,
                        cur,
                        checklist.include_active_schedule,
                        checklist.pe_completed,
                        draftSlots
                      )
                    }
                    className={`rounded-lg px-2.5 py-1 font-medium transition ${
                      checklist.curriculum === cur
                        ? "bg-zinc-200 text-zinc-950"
                        : "text-zinc-400 hover:text-white"
                    }`}
                  >
                    {cur === "current" ? "Fall 2024+" : "Pre-Fall 2024"}
                  </button>
                ))}
              </div>

              <label
                className={`inline-flex cursor-pointer items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs font-medium transition ${
                  checklist.include_active_schedule
                    ? "border-sky-500/50 bg-sky-500/15 text-sky-200"
                    : "border-zinc-700 bg-zinc-950 text-zinc-300"
                }`}
              >
                <input
                  type="checkbox"
                  checked={checklist.include_active_schedule}
                  onChange={(e) =>
                    void persistChecklist(
                      checklist.college,
                      checklist.curriculum,
                      e.target.checked,
                      checklist.pe_completed,
                      draftSlots
                    )
                  }
                  className="accent-sky-400"
                />
                <Sparkles className="h-3.5 w-3.5 text-sky-300" />
                <span>
                  What-If Schedule
                  {checklist.active_schedule_name ? `: ${checklist.active_schedule_name}` : ""}
                </span>
              </label>

              <div className="inline-flex items-center gap-1.5 rounded-xl border border-zinc-700/80 bg-zinc-950 px-2.5 py-1 text-xs">
                <span className="text-zinc-400">PE:</span>
                {[0, 1, 2].map((n) => (
                  <button
                    key={n}
                    type="button"
                    onClick={() =>
                      void persistChecklist(
                        checklist.college,
                        checklist.curriculum,
                        checklist.include_active_schedule,
                        n,
                        draftSlots
                      )
                    }
                    className={`rounded-md px-1.5 py-0.5 text-[11px] font-semibold ${
                      checklist.pe_completed === n
                        ? "bg-emerald-500/25 text-emerald-200 ring-1 ring-emerald-500/50"
                        : "text-zinc-400 hover:text-white"
                    }`}
                  >
                    {n}/2
                  </button>
                ))}
                <button
                  type="button"
                  onClick={() =>
                    onLaunchSearch({
                      id: Date.now(),
                      label: "PE Courses",
                      attrs: ["PE"],
                      subjects: ["PE"],
                    })
                  }
                  title="Search PE classes"
                  className="ml-1 text-[11px] text-emerald-400 hover:underline"
                >
                  Find PE
                </button>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2 text-xs">
              <span className="rounded-lg border border-emerald-500/35 bg-emerald-500/10 px-2.5 py-1 font-medium text-emerald-300">
                Done: {checklist.summary.completed_slots}
              </span>
              {checklist.summary.in_progress_slots > 0 && (
                <span className="rounded-lg border border-amber-500/40 bg-amber-500/15 px-2.5 py-1 font-medium text-amber-200">
                  Taking: +{checklist.summary.in_progress_slots}
                </span>
              )}
              {checklist.summary.whatif_slots > 0 && (
                <span className="rounded-lg border border-sky-500/35 bg-sky-500/10 px-2.5 py-1 font-medium text-sky-200">
                  What-If: +{checklist.summary.whatif_slots}
                </span>
              )}
              <span className="rounded-lg border border-zinc-700 bg-zinc-950 px-2.5 py-1 font-medium text-zinc-300">
                {checklist.summary.filled_slots}/{checklist.summary.total_slots} filled ({checklist.summary.remaining_slots} empty)
              </span>
            </div>
          </div>
        )}
      </div>

      {error && (
        <div className="rounded-xl border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">
          {error}
        </div>
      )}

      {/* Classes I've Taken & Classes Currently Taking Quick-Add Cards */}
      {checklist && (
        <div className="grid gap-4 lg:grid-cols-2">
          <CourseQuickAddCard
            title={`Classes I've Taken (${checklist.completed_courses.length})`}
            subtitle="Completed & AP courses that auto-fill checklist boxes as Done & satisfy prereqs."
            icon={<ListChecks className="h-4 w-4 text-sky-400" />}
            tone="taken"
            roster={selectedRoster}
            courses={checklist.completed_courses}
            details={checklist.completed_course_details}
            alreadyTakenSet={new Set(checklist.completed_courses)}
            alreadyTakingSet={new Set(checklist.in_progress_courses || [])}
            saving={takenSaving}
            placeholder="Type course code, title, or AP (e.g. ENGL 1100F, AP Lit)..."
            addLabel="Add Class"
            emptyText="No completed classes recorded yet. Type above, import transcript, or open Bundles."
            headerActions={
              <>
                <button
                  type="button"
                  onClick={() => setTranscriptOpen(true)}
                  className="inline-flex items-center gap-1.5 rounded-xl border border-emerald-500/45 bg-emerald-500/15 px-2.5 py-1.5 text-xs font-semibold text-emerald-200 hover:bg-emerald-500/25"
                  title="Parse Cornell Unofficial Transcript PDF/text locally in your browser"
                >
                  <FileUp className="h-3.5 w-3.5" />
                  Import Transcript
                </button>
                <button
                  type="button"
                  onClick={() => setPrereqsOpen(true)}
                  className="rounded-xl border border-zinc-700 bg-zinc-950 px-2.5 py-1.5 text-[11px] font-medium text-zinc-300 hover:border-sky-500/50 hover:text-sky-200"
                >
                  Bundles...
                </button>
              </>
            }
            onAdd={addTakenCourses}
            onRemove={removeTakenCourse}
          />

          <CourseQuickAddCard
            title={`Classes Currently Taking (${checklist.in_progress_courses?.length ?? 0})`}
            subtitle="Classes enrolled right now (e.g. CS 5306, CS 4820) — fills checklist boxes as Currently Taking & unlocks next-term prereqs."
            icon={<Clock className="h-4 w-4 text-amber-400" />}
            tone="taking"
            roster={selectedRoster}
            courses={checklist.in_progress_courses || []}
            details={checklist.in_progress_course_details}
            alreadyTakenSet={new Set(checklist.completed_courses)}
            alreadyTakingSet={new Set(checklist.in_progress_courses || [])}
            saving={takingSaving}
            placeholder="Type course taking right now (e.g. CS 5306, CS 4820)..."
            addLabel="Add Taking"
            emptyText="No currently taking classes yet. Add this semester's classes here or import your transcript."
            onAdd={addTakingCourses}
            onRemove={removeTakingCourse}
            onPromoteToTaken={promoteTakingToTaken}
          />
        </div>
      )}

      {/* Multi-Select Empty Box Search Action Bar */}
      {selectedSlots.length > 0 && (
        <div className="sticky top-14 z-20 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-emerald-500/50 bg-zinc-900/95 px-4 py-3 shadow-xl backdrop-blur">
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="font-semibold text-emerald-300">
              {selectedSlots.length} empty slot{selectedSlots.length === 1 ? "" : "s"} selected:
            </span>
            <div className="flex flex-wrap gap-1.5">
              {selectedSlots.map((sl) => (
                <span
                  key={sl.id}
                  className="inline-flex items-center gap-1 rounded-md border border-emerald-500/40 bg-emerald-500/15 px-2 py-0.5 text-[11px] text-emerald-100"
                >
                  {sl.label}
                  <button
                    type="button"
                    onClick={() => toggleEmptySlotSelect(sl)}
                    className="text-emerald-300 hover:text-white"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </span>
              ))}
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {selectedSlots.filter((s) => (s.search?.attrs?.length ?? 0) > 0).length > 1 && (
              <div className="inline-flex rounded-lg border border-zinc-700 bg-zinc-950 p-0.5 text-[11px]">
                {(["any", "all"] as const).map((m) => (
                  <button
                    key={m}
                    type="button"
                    onClick={() => setMultiAttrMatch(m)}
                    className={`rounded-md px-2 py-0.5 font-medium ${
                      multiAttrMatch === m ? "bg-violet-500 text-zinc-950" : "text-zinc-400 hover:text-white"
                    }`}
                    title={
                      m === "any"
                        ? "Show courses satisfying ANY selected distribution category"
                        : "Show double-counting courses satisfying ALL selected distribution categories"
                    }
                  >
                    {m === "any" ? "Fits Any Selected" : "Double-Dip (All)"}
                  </button>
                ))}
              </div>
            )}

            <button
              type="button"
              onClick={() => setSelectedEmptyIds([])}
              className="rounded-xl border border-zinc-700 px-3 py-1.5 text-xs text-zinc-300 hover:bg-zinc-800"
            >
              Clear
            </button>
            <button
              type="button"
              onClick={() => onLaunchSearch(buildPresetFromSlots(selectedSlots, multiAttrMatch))}
              className="inline-flex items-center gap-1.5 rounded-xl bg-emerald-500 px-3.5 py-1.5 text-xs font-semibold text-zinc-950 hover:bg-emerald-400"
            >
              <Search className="h-3.5 w-3.5" />
              Find Courses for Selected ({selectedSlots.length})
            </button>
          </div>
        </div>
      )}

      {loading && !checklist ? (
        <div className="flex items-center justify-center rounded-2xl border border-zinc-800 bg-zinc-900/60 py-14 text-sm text-zinc-400">
          <Loader2 className="mr-2 h-4 w-4 animate-spin text-emerald-400" />
          Building your interactive CS checklist...
        </div>
      ) : (
        checklist && (
          <div className="grid gap-4 lg:grid-cols-2">
            {checklist.sections.map((section) => {
              const activeSectionSlots = section.slots.filter((s) => !s.waived);
              return (
              <div
                key={section.id}
                className={`rounded-2xl border border-zinc-800 bg-zinc-900/75 ${
                  section.id === "cs_electives" ? "lg:col-span-2" : ""
                }`}
              >
                <div className="rounded-t-2xl border-b border-zinc-800/90 bg-zinc-950/70 px-4 py-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <h3 className="text-sm font-bold text-white">{section.title}</h3>
                    <span className="rounded-full bg-zinc-800 px-2 py-0.5 text-[11px] font-medium text-zinc-300">
                      {activeSectionSlots.filter((s) => s.filled).length}/{activeSectionSlots.length}
                    </span>
                  </div>
                  <p className="mt-0.5 text-[11px] text-zinc-400">{section.subtitle}</p>
                </div>

                <div className="divide-y divide-zinc-800/70">
                  {section.slots.map((slot) => {
                    const isSelected = selectedEmptyIds.includes(slot.id);
                    const isEditing = editingSlotId === slot.id;

                    if (isEditing) {
                      const placedInSectionOrCore = new Set<string>();
                      if (section.id !== "as_distribution") {
                        for (const sec of checklist.sections) {
                          if (sec.id === "as_distribution") continue;
                          for (const s of sec.slots) {
                            if (s.id !== slot.id && s.filled && s.course) {
                              placedInSectionOrCore.add(s.course);
                            }
                          }
                        }
                      }
                      const fixedQuick = slot.quick_options || [];
                      const liveQuick = slotSuggestionsCache[`${selectedRoster}:${slot.id}`] || [];
                      const mergedQuick: CsChecklistQuickOption[] = [];
                      const seenQuick = new Set<string>();
                      for (const opt of [...fixedQuick, ...liveQuick]) {
                        if (seenQuick.has(opt.code) || placedInSectionOrCore.has(opt.code)) continue;
                        seenQuick.add(opt.code);
                        mergedQuick.push(opt);
                      }
                      const suggestions = mergedQuick.slice(0, 8);
                      return (
                        <div key={slot.id} className="space-y-2.5 bg-zinc-950/90 p-3 text-xs">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <span className="font-semibold text-white">
                              {slot.filled ? `Edit Box: ${slot.label}` : `Add Course: ${slot.label}`}
                            </span>
                            <span className="text-[11px] text-zinc-400">{slot.expected}</span>
                          </div>

                          {/* One-click quick-pick chips */}
                          {(suggestions.length > 0 || slotSuggestionsLoading) && (
                            <div className="flex flex-wrap items-center gap-1.5">
                              <span className="text-[10px] font-medium uppercase tracking-wide text-zinc-500">
                                Quick pick:
                              </span>
                              {slotSuggestionsLoading && suggestions.length === 0 ? (
                                <Loader2 className="h-3 w-3 animate-spin text-zinc-400" />
                              ) : (
                                suggestions.map((opt) => {
                                  const isTaken = checklist.completed_courses.includes(opt.code);
                                  const isTaking = (checklist.in_progress_courses || []).includes(opt.code);
                                  return (
                                    <button
                                      key={opt.code}
                                      type="button"
                                      disabled={saving}
                                      onClick={() =>
                                        void applySlotCourse(
                                          slot.id,
                                          opt.code,
                                          opt.cr || "",
                                          opt.title || ""
                                        )
                                      }
                                      title={opt.title ? `${opt.code}: ${opt.title}` : opt.code}
                                      className={`inline-flex items-center gap-1 rounded-lg border px-2 py-0.5 font-mono text-[11px] font-medium transition ${
                                        isTaken
                                          ? "border-emerald-500/45 bg-emerald-500/15 text-emerald-200 hover:bg-emerald-500/25"
                                          : isTaking
                                            ? "border-amber-500/45 bg-amber-500/15 text-amber-200 hover:bg-amber-500/25"
                                            : "border-sky-500/35 bg-sky-500/10 text-sky-200 hover:bg-sky-500/20"
                                      }`}
                                    >
                                      <Plus className="h-2.5 w-2.5" />
                                      <span>{opt.code}</span>
                                      {opt.cr && (
                                        <span className="text-[10px] opacity-70">({opt.cr})</span>
                                      )}
                                    </button>
                                  );
                                })
                              )}
                            </div>
                          )}

                          <div className="grid grid-cols-2 gap-2 sm:grid-cols-6">
                            <div className="relative col-span-2 sm:col-span-3">
                              <input
                                type="text"
                                autoFocus
                                value={editForm.course}
                                onFocus={() => setSlotPickerFocused(true)}
                                onBlur={() => setTimeout(() => setSlotPickerFocused(false), 180)}
                                onChange={(e) => {
                                  setSlotSearchDirty(true);
                                  setEditForm({
                                    ...editForm,
                                    course: e.target.value,
                                    title: "",
                                  });
                                }}
                                onKeyDown={(e) => {
                                  if (e.key === "Enter") {
                                    e.preventDefault();
                                    const parsed = parseCourseInputTokens(editForm.course);
                                    const topMatch = slotSearchOptions[0];
                                    if (topMatch && (parsed.length === 0 || topMatch.code === parsed[0])) {
                                      void applySlotCourse(
                                        slot.id,
                                        topMatch.code,
                                        topMatch.cr || "",
                                        topMatch.title || ""
                                      );
                                    } else if (parsed.length > 0) {
                                      void applySlotCourse(slot.id, parsed[0]);
                                    } else {
                                      void saveEditSlot(slot.id);
                                    }
                                  } else if (e.key === "Escape") {
                                    setEditingSlotId(null);
                                  }
                                }}
                                placeholder="Search code, title, or AP (e.g. ENGL 1100F, AP Lit)..."
                                className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-2.5 py-1.5 text-xs text-white placeholder-zinc-500 focus:border-sky-500 focus:outline-none"
                              />

                              {slotPickerFocused &&
                                slotSearchDirty &&
                                editForm.course.trim() &&
                                slotSearchOptions.length > 0 && (
                                  <div className="absolute left-0 right-0 top-full z-30 mt-1 max-h-48 overflow-y-auto rounded-xl border border-zinc-700 bg-zinc-950 p-1 shadow-2xl">
                                    {slotSearchOptions.map((opt) => (
                                      <button
                                        key={opt.code}
                                        type="button"
                                        onMouseDown={(e) => {
                                          e.preventDefault();
                                          void applySlotCourse(
                                            slot.id,
                                            opt.code,
                                            opt.cr || "",
                                            opt.title || ""
                                          );
                                        }}
                                        className="flex w-full items-center justify-between gap-2 rounded-lg px-2 py-1.5 text-left text-xs text-zinc-200 hover:bg-zinc-800"
                                      >
                                        <span className="truncate">
                                          <span className="font-mono font-semibold text-white">
                                            {opt.code}
                                          </span>
                                          {opt.title ? (
                                            <span className="ml-2 text-zinc-400">{opt.title}</span>
                                          ) : null}
                                        </span>
                                        <span className="flex shrink-0 items-center gap-1.5 text-[10px] text-sky-400">
                                          {opt.cr ? `${opt.cr} cr` : ""}
                                          <Plus className="h-3 w-3" />
                                        </span>
                                      </button>
                                    ))}
                                  </div>
                                )}
                            </div>
                            <input
                              type="text"
                              value={editForm.cr}
                              onChange={(e) => setEditForm({ ...editForm, cr: e.target.value })}
                              placeholder="Cr (auto)"
                              className="rounded-lg border border-zinc-700 bg-zinc-900 px-2.5 py-1.5 text-xs text-white"
                            />
                            <input
                              type="text"
                              value={editForm.sem}
                              onChange={(e) => setEditForm({ ...editForm, sem: e.target.value })}
                              placeholder="Sem (FA25)"
                              className="rounded-lg border border-zinc-700 bg-zinc-900 px-2.5 py-1.5 text-xs text-white"
                            />
                            <input
                              type="text"
                              value={editForm.gr}
                              onChange={(e) => setEditForm({ ...editForm, gr: e.target.value })}
                              placeholder="Gr (A)"
                              className="rounded-lg border border-zinc-700 bg-zinc-900 px-2.5 py-1.5 text-xs text-white"
                            />
                          </div>

                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
                              <span className="text-zinc-400">Save as:</span>
                              {(
                                [
                                  { id: "taken", label: "Taken", active: "bg-emerald-500 text-zinc-950 font-semibold" },
                                  { id: "taking", label: "Currently Taking", active: "bg-amber-500 text-zinc-950 font-semibold" },
                                  { id: "box", label: "This Box Only", active: "bg-zinc-200 text-zinc-950 font-semibold" },
                                ] as const
                              ).map((mode) => (
                                <button
                                  key={mode.id}
                                  type="button"
                                  onClick={() => setEditSaveMode(mode.id)}
                                  className={`rounded-md border px-2 py-0.5 transition ${
                                    editSaveMode === mode.id
                                      ? `border-transparent ${mode.active}`
                                      : "border-zinc-700 bg-zinc-900 text-zinc-300 hover:text-white"
                                  }`}
                                >
                                  {mode.label}
                                </button>
                              ))}
                            </div>
                            <div className="flex items-center gap-1.5">
                              <button
                                type="button"
                                onClick={() => setEditingSlotId(null)}
                                className="rounded-lg border border-zinc-700 px-2 py-1 text-zinc-300 hover:bg-zinc-800"
                              >
                                Cancel
                              </button>
                              <button
                                type="button"
                                disabled={saving}
                                onClick={() => void saveEditSlot(slot.id)}
                                className="rounded-lg bg-emerald-500 px-2.5 py-1 font-semibold text-zinc-950 hover:bg-emerald-400 disabled:opacity-50"
                              >
                                Save
                              </button>
                            </div>
                          </div>
                        </div>
                      );
                    }

                    const isInProgress = slot.filled && slot.source === "in_progress";
                    const isWhatIf = slot.filled && slot.source === "schedule";
                    const isWaived = Boolean(slot.waived || slot.source === "waived");

                    return (
                      <div
                        key={slot.id}
                        className={`flex flex-wrap items-center justify-between gap-2 px-4 py-2.5 text-xs transition ${
                          isWaived
                            ? "bg-zinc-950/40 opacity-55"
                            : !slot.filled
                              ? isSelected
                                ? "bg-emerald-500/15"
                                : "hover:bg-zinc-800/40"
                              : isInProgress
                                ? "bg-amber-500/5"
                                : isWhatIf
                                  ? "bg-sky-500/5"
                                  : ""
                        }`}
                      >
                        {/* Left: Checkbox / Slot Box */}
                        <div className="flex min-w-0 flex-1 items-center gap-2.5">
                          {isWaived ? (
                            <div className="flex min-w-0 items-center gap-2.5">
                              <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-md border border-zinc-700 bg-zinc-800/70 text-zinc-400">
                                <Minus className="h-3 w-3" />
                              </span>
                              <div className="min-w-0">
                                <div className="font-semibold text-zinc-400 line-through">
                                  {slot.label}
                                </div>
                                <div className="text-[11px] text-zinc-500">
                                  Waived — satisfied by {slot.waived_by || "2000+ language course"}
                                </div>
                              </div>
                            </div>
                          ) : !slot.filled ? (
                            <button
                              type="button"
                              onClick={() => toggleEmptySlotSelect(slot)}
                              className={`flex items-center gap-2 text-left ${
                                isSelected ? "text-emerald-200" : "text-zinc-300"
                              }`}
                              title="Select empty requirement box to search matching courses"
                            >
                              {isSelected ? (
                                <CheckSquare className="h-4 w-4 shrink-0 text-emerald-400" />
                              ) : (
                                <Square className="h-4 w-4 shrink-0 text-zinc-500 hover:text-emerald-400" />
                              )}
                              <div>
                                <div className="font-semibold text-white">{slot.label}</div>
                                <div className="text-[11px] text-zinc-400">{slot.expected}</div>
                              </div>
                            </button>
                          ) : (
                            <div className="flex min-w-0 items-center gap-2.5">
                              <span
                                className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-md border ${
                                  isInProgress
                                    ? "border-amber-400/70 bg-amber-500/20 text-amber-300"
                                    : isWhatIf
                                      ? "border-dashed border-sky-400 bg-sky-500/20 text-sky-300"
                                      : "border-emerald-500/60 bg-emerald-500/20 text-emerald-300"
                                }`}
                              >
                                {isInProgress ? (
                                  <Clock className="h-3 w-3" />
                                ) : isWhatIf ? (
                                  <CalendarCheck2 className="h-3 w-3" />
                                ) : (
                                  <Check className="h-3.5 w-3.5" />
                                )}
                              </span>
                              <div className="min-w-0">
                                <div className="flex flex-wrap items-center gap-1.5">
                                  <span className="font-semibold text-zinc-400">{slot.label}:</span>
                                  <span className="font-bold text-white">{slot.course}</span>
                                  {slot.title && (
                                    <span className="truncate max-w-[260px] text-zinc-400">
                                      — {slot.title}
                                    </span>
                                  )}
                                  {isInProgress && (
                                    <span className="rounded border border-amber-500/40 bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-amber-200">
                                      Currently Taking
                                      {slot.sem && slot.sem.toUpperCase() !== "TAKING" ? ` (${slot.sem})` : ""}
                                    </span>
                                  )}
                                  {isWhatIf && (
                                    <span className="rounded border border-sky-500/40 bg-sky-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-sky-200">
                                      What-If ({slot.sem})
                                    </span>
                                  )}
                                  {slot.cr && (
                                    <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] text-zinc-300">
                                      {slot.cr} cr
                                    </span>
                                  )}
                                  {!isWhatIf &&
                                    !isInProgress &&
                                    slot.sem &&
                                    slot.sem.toUpperCase() !== "DONE" && (
                                      <span className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono text-[10px] text-zinc-300">
                                        {slot.sem}
                                      </span>
                                    )}
                                  {slot.gr && (
                                    <span className="rounded border border-emerald-500/30 bg-emerald-500/10 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-emerald-300">
                                      {slot.gr}
                                    </span>
                                  )}
                                </div>
                                {slot.warning && (
                                  <div className="mt-1 inline-flex items-center gap-1 rounded-md border border-amber-500/35 bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-medium text-amber-200">
                                    <AlertTriangle className="h-3 w-3 shrink-0 text-amber-300" />
                                    <span>{slot.warning}</span>
                                  </div>
                                )}
                              </div>
                            </div>
                          )}
                        </div>

                        {/* Right: Quick Search / Add Taken / Edit / Clear actions */}
                        <div className="flex items-center gap-1.5">
                          {!slot.filled && !isWaived ? (
                            <>
                              <button
                                type="button"
                                onClick={() => onLaunchSearch(buildPresetFromSlots([slot], "any"))}
                                className="inline-flex items-center gap-1 rounded-lg border border-emerald-500/35 bg-emerald-500/10 px-2 py-1 text-[11px] font-medium text-emerald-200 hover:bg-emerald-500/20"
                                title={`Find courses satisfying ${slot.label}`}
                              >
                                <Search className="h-3 w-3" />
                                Find
                              </button>
                              <button
                                type="button"
                                onClick={() => startEditSlot(slot)}
                                className="inline-flex items-center gap-1 rounded-lg border border-sky-500/35 bg-sky-500/10 px-2 py-1 text-[11px] font-medium text-sky-200 hover:bg-sky-500/20"
                                title={`Pick or add a course you took into ${slot.label}`}
                              >
                                <Plus className="h-3 w-3" />
                                Add
                              </button>
                            </>
                          ) : (
                            <button
                              type="button"
                              onClick={() => startEditSlot(slot)}
                              className="rounded-lg border border-zinc-700/80 p-1 text-zinc-400 hover:text-white"
                              title="Pick a different course or edit credits, semester, grade"
                            >
                              <Edit3 className="h-3 w-3" />
                            </button>
                          )}
                          {slot.filled && (
                            <button
                              type="button"
                              onClick={() => void clearSlot(slot.id)}
                              className="rounded-lg border border-zinc-700/80 p-1 text-zinc-400 hover:text-rose-300"
                              title="Clear this slot"
                            >
                              <Eraser className="h-3 w-3" />
                            </button>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
              );
            })}
          </div>
        )
      )}

      <CompletedPrereqsModal
        isOpen={prereqsOpen}
        roster={selectedRoster}
        initialCompleted={checklist?.completed_courses || user.completed_courses || []}
        initialIncludeImplied={user.include_implied_prereqs ?? true}
        majorMode={user.major_mode || "cs"}
        showCsFeatures={true}
        onClose={() => setPrereqsOpen(false)}
        onOpenTranscriptImport={() => {
          setPrereqsOpen(false);
          setTranscriptOpen(true);
        }}
        onSaved={(res) => {
          onUserUpdated?.({
            ...user,
            completed_courses: res.completed_courses,
            include_implied_prereqs: res.include_implied_prereqs,
          });
          if (selectedRoster) {
            void loadChecklist(selectedRoster);
          }
        }}
      />

      {transcriptOpen && (
        <TranscriptImportModal
          rosters={rosters}
          activeRoster={selectedRoster}
          existingCompleted={checklist?.completed_courses || user.completed_courses || []}
          existingDetails={checklist?.completed_course_details || user.completed_course_details || {}}
          onClose={() => setTranscriptOpen(false)}
          onImported={(_, nextChecklist) => {
            setChecklist(nextChecklist);
            setDraftSlots(nextChecklist.manual_slots || {});
            onUserUpdated?.({
              ...user,
              completed_courses: nextChecklist.completed_courses,
              completed_course_details: nextChecklist.completed_course_details,
              in_progress_courses: nextChecklist.in_progress_courses,
              in_progress_course_details: nextChecklist.in_progress_course_details,
            });
          }}
        />
      )}
    </div>
  );
}
