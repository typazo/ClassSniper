import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ChevronDown,
  Clock,
  FileUp,
  GraduationCap,
  ListChecks,
  Loader2,
  RotateCcw,
  Search,
  Sparkles,
  X,
} from "lucide-react";
import { api } from "../api/client";
import { usePrereqOptions } from "../hooks/usePrereqOptions";
import type {
  AttrMatchMode,
  CatalogSubjectRefreshedSSE,
  CourseSearchPreset,
  CSCurriculumMode,
  CsChecklistPayload,
  CsChecklistQuickOption,
  CsChecklistSlot,
  CsChecklistSlotInput,
  CSRequirementMode,
  Roster,
  User,
} from "../types";
import { formatUnitsRange, parseCourseInputTokens } from "../utils/courseFormat";
import { ChecklistSlotEditor, type EditSaveMode } from "./ChecklistSlotEditor";
import { ChecklistSlotRow } from "./ChecklistSlotRow";
import { CompletedPrereqsModal } from "./CompletedPrereqsModal";
import { CourseQuickAddCard } from "./CourseQuickAddCard";
import { TranscriptImportModal } from "./TranscriptImportModal";

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

export function CsChecklistPage({ user, initialRoster, lastCatalogRefresh, onUserUpdated, onLaunchSearch }: Props) {
  const [rosters, setRosters] = useState<Roster[]>([]);
  const [selectedRoster, setSelectedRoster] = useState(initialRoster || "");
  const [checklist, setChecklist] = useState<CsChecklistPayload | null>(null);
  const [showCourseLists, setShowCourseLists] = useState<boolean | null>(null);
  const [draftSlots, setDraftSlots] = useState<Record<string, CsChecklistSlotInput>>({});
  const checklistRef = useRef<CsChecklistPayload | null>(null);
  checklistRef.current = checklist;
  const draftSlotsRef = useRef<Record<string, CsChecklistSlotInput>>({});
  draftSlotsRef.current = draftSlots;
  const userRef = useRef<User>(user);
  userRef.current = user;
  const saveChainRef = useRef<Promise<void>>(Promise.resolve());

  const [editingSlotId, setEditingSlotId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<CsChecklistSlotInput>({
    course: "",
    title: "",
    cr: "",
    sem: "",
    gr: "",
    notes: "",
  });
  const [editSaveMode, setEditSaveMode] = useState<EditSaveMode>("taken");
  const [slotPickerFocused, setSlotPickerFocused] = useState(false);
  const [slotSearchDirty, setSlotSearchDirty] = useState(false);
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

  const { options: slotSearchOptions, setOptions: setSlotSearchOptions } = usePrereqOptions(
    selectedRoster,
    editForm.course,
    "cs",
    {
      enabled: Boolean(editingSlotId && selectedRoster && slotSearchDirty),
      limit: 10,
      debounceMs: 140,
    }
  );

  const syncUserFromChecklist = useCallback(
    (updated: CsChecklistPayload) => {
      const curUser = userRef.current;
      onUserUpdated?.({
        ...curUser,
        completed_courses: updated.completed_courses,
        completed_course_details: updated.completed_course_details,
        in_progress_courses: updated.in_progress_courses,
        in_progress_course_details: updated.in_progress_course_details,
      });
    },
    [onUserUpdated]
  );

  const enqueueMutation = useCallback((task: () => Promise<void>): Promise<void> => {
    const next = saveChainRef.current.then(task, task);
    saveChainRef.current = next.catch(() => undefined);
    return next;
  }, []);

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

  const loadChecklist = useCallback(async (rosterSlug: string): Promise<CsChecklistPayload | null> => {
    if (!rosterSlug) return null;
    setLoading(true);
    setError("");
    try {
      const data = await api.getCsChecklist(rosterSlug);
      setChecklist(data);
      checklistRef.current = data;
      setDraftSlots(data.manual_slots || {});
      draftSlotsRef.current = data.manual_slots || {};
      return data;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load CS Checklist");
      return null;
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

  const updateTakenList = (computeNext: (cur: string[]) => string[]) =>
    enqueueMutation(async () => {
      setTakenSaving(true);
      setError("");
      try {
        const current =
          checklistRef.current?.completed_courses || userRef.current.completed_courses || [];
        const normalized = Array.from(
          new Set(computeNext(current).map((c) => c.trim().toUpperCase()).filter(Boolean))
        ).sort();
        const res = await api.updateUserPrereqs(
          {
            completed_courses: normalized,
            include_implied_prereqs: userRef.current.include_implied_prereqs ?? true,
          },
          selectedRoster || undefined
        );
        if (selectedRoster) {
          const refreshed = await loadChecklist(selectedRoster);
          if (refreshed) {
            syncUserFromChecklist(refreshed);
            return;
          }
        }
        onUserUpdated?.({
          ...userRef.current,
          completed_courses: res.completed_courses,
          include_implied_prereqs: res.include_implied_prereqs,
        });
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to update completed courses");
      } finally {
        setTakenSaving(false);
      }
    });

  const addTakenCourses = async (codes: string[]) => {
    const clean = codes.map((c) => c.trim().toUpperCase()).filter(Boolean);
    if (clean.length === 0) return;
    await updateTakenList((cur) => [...cur, ...clean]);
  };

  const removeTakenCourse = async (code: string) => {
    await updateTakenList((cur) => cur.filter((c) => c !== code));
  };

  const applyChecklistUpdate = (
    buildArgs: (cur: CsChecklistPayload, curSlots: Record<string, CsChecklistSlotInput>) => {
      college: "arts" | "engineering";
      curriculum: CSCurriculumMode;
      include_active_schedule: boolean;
      pe_completed: number;
      slots: Record<string, CsChecklistSlotInput>;
      sync_completed_courses?: string[];
      sync_in_progress_courses?: string[];
    },
    kind: "taking" | "checklist"
  ) =>
    enqueueMutation(async () => {
      const curChecklist = checklistRef.current;
      if (!curChecklist) return;
      if (kind === "taking") setTakingSaving(true);
      else setSaving(true);
      setError("");
      try {
        const payload = buildArgs(curChecklist, draftSlotsRef.current);
        const updated = await api.updateCsChecklist(payload, selectedRoster || undefined);
        setChecklist(updated);
        checklistRef.current = updated;
        const nextSlots = updated.manual_slots || payload.slots;
        setDraftSlots(nextSlots);
        draftSlotsRef.current = nextSlots;
        if (
          payload.sync_completed_courses !== undefined ||
          payload.sync_in_progress_courses !== undefined
        ) {
          syncUserFromChecklist(updated);
        }
        setSelectedEmptyIds((prev) =>
          prev.filter((id) =>
            updated.sections.some((sec) => sec.slots.some((sl) => sl.id === id && !sl.filled))
          )
        );
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : kind === "taking"
              ? "Failed to update currently taking courses"
              : "Failed to save checklist changes"
        );
      } finally {
        if (kind === "taking") setTakingSaving(false);
        else setSaving(false);
      }
    });

  const addTakingCourses = async (codes: string[]) => {
    const clean = codes.map((c) => c.trim().toUpperCase()).filter(Boolean);
    if (clean.length === 0) return;
    await applyChecklistUpdate(
      (cur, curSlots) => ({
        college: cur.college,
        curriculum: cur.curriculum,
        include_active_schedule: cur.include_active_schedule,
        pe_completed: cur.pe_completed,
        slots: curSlots,
        sync_in_progress_courses: Array.from(
          new Set([...cur.in_progress_courses, ...clean])
        ).sort(),
      }),
      "taking"
    );
  };

  const removeTakingCourse = async (code: string) => {
    await applyChecklistUpdate(
      (cur, curSlots) => ({
        college: cur.college,
        curriculum: cur.curriculum,
        include_active_schedule: cur.include_active_schedule,
        pe_completed: cur.pe_completed,
        slots: curSlots,
        sync_in_progress_courses: cur.in_progress_courses.filter((c) => c !== code),
      }),
      "taking"
    );
  };

  const promoteTakingToTaken = async (code: string) => {
    await applyChecklistUpdate(
      (cur, curSlots) => ({
        college: cur.college,
        curriculum: cur.curriculum,
        include_active_schedule: cur.include_active_schedule,
        pe_completed: cur.pe_completed,
        slots: curSlots,
        sync_in_progress_courses: cur.in_progress_courses.filter((c) => c !== code),
        sync_completed_courses: Array.from(new Set([...cur.completed_courses, code])).sort(),
      }),
      "taking"
    );
  };

  const persistChecklist = (
    nextCollege: "arts" | "engineering",
    nextCurriculum: CSCurriculumMode,
    nextIncludeSched: boolean,
    nextPe: number,
    nextSlots: Record<string, CsChecklistSlotInput>
  ) =>
    applyChecklistUpdate(
      () => ({
        college: nextCollege,
        curriculum: nextCurriculum,
        include_active_schedule: nextIncludeSched,
        pe_completed: nextPe,
        slots: nextSlots,
      }),
      "checklist"
    );

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

  const slotCacheKeyFor = (slotId: string) =>
    `${selectedRoster}:${checklist?.college || "arts"}:${checklist?.curriculum || "current"}:${slotId}`;

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
      existing && existing.course === slot.course ? existing.title || "" : "";
    setEditForm({
      course: startCourse,
      title: startTitle,
      cr: existing?.cr || slot.cr || "",
      sem: existing?.sem || slot.sem || "",
      gr: existing?.gr || slot.gr || "",
      notes: existing?.notes || "",
      pinned: true,
      cleared: false,
    });

    const hasManyFixedQuick = (slot.quick_options?.length ?? 0) >= 4;
    const cacheKey = slotCacheKeyFor(slot.id);
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
    const formSnap = {
      ...editForm,
      course: nextCourse,
      title: titleOverride !== undefined ? titleOverride : courseChanged ? "" : editForm.title.trim(),
      cr: resolvedCr,
      pinned: Boolean(nextCourse),
      cleared: !nextCourse,
    };
    const saveModeSnap = editSaveMode;
    setEditingSlotId(null);
    setSlotSearchOptions([]);
    setSlotPickerFocused(false);

    await applyChecklistUpdate((cur, curSlots) => {
      const nextSlots: Record<string, CsChecklistSlotInput> = {
        ...curSlots,
        [slotId]: formSnap,
      };
      let syncCompleted: string[] | undefined;
      let syncInProgress: string[] | undefined;
      if (nextCourse) {
        if (saveModeSnap === "taken") {
          syncCompleted = Array.from(new Set([...cur.completed_courses, nextCourse])).sort();
          if (cur.in_progress_courses.includes(nextCourse)) {
            syncInProgress = cur.in_progress_courses.filter((c) => c !== nextCourse);
          }
        } else if (saveModeSnap === "taking") {
          syncInProgress = Array.from(new Set([...cur.in_progress_courses, nextCourse])).sort();
          if (cur.completed_courses.includes(nextCourse)) {
            syncCompleted = cur.completed_courses.filter((c) => c !== nextCourse);
          }
        }
      }
      return {
        college: cur.college,
        curriculum: cur.curriculum,
        include_active_schedule: cur.include_active_schedule,
        pe_completed: cur.pe_completed,
        slots: nextSlots,
        ...(syncCompleted !== undefined ? { sync_completed_courses: syncCompleted } : {}),
        ...(syncInProgress !== undefined ? { sync_in_progress_courses: syncInProgress } : {}),
      };
    }, "checklist");
  };

  const clearSlot = async (slotId: string) => {
    await applyChecklistUpdate(
      (cur, curSlots) => ({
        college: cur.college,
        curriculum: cur.curriculum,
        include_active_schedule: cur.include_active_schedule,
        pe_completed: cur.pe_completed,
        slots: {
          ...curSlots,
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
        },
      }),
      "checklist"
    );
  };

  const resetAllOverrides = async () => {
    setSelectedEmptyIds([]);
    await applyChecklistUpdate(
      (cur) => ({
        college: cur.college,
        curriculum: cur.curriculum,
        include_active_schedule: cur.include_active_schedule,
        pe_completed: cur.pe_completed,
        slots: {},
      }),
      "checklist"
    );
  };

  return (
    <div className="space-y-4">
      {/* Header & Controls Card */}
      <div className="space-y-4 rounded-2xl border border-zinc-800 bg-zinc-900/80 p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <GraduationCap className="h-5 w-5 text-emerald-400" />
              <h2 className="text-base font-bold text-white">
                CS Checklist ({checklist?.college === "engineering" ? "Engineering BS" : "Arts & Sciences BA"})
              </h2>
              {saving && (
                <span className="inline-flex items-center gap-1 rounded-full bg-zinc-800 px-2 py-0.5 text-[11px] text-zinc-300">
                  <Loader2 className="h-3 w-3 animate-spin text-emerald-400" />
                  Saving...
                </span>
              )}
            </div>
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
              Completed &amp; Bundles ({checklist?.completed_courses.length ?? 0})
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

            <div className="flex flex-wrap items-center gap-2.5 text-xs">
              <span className="font-semibold text-emerald-300">
                Done {checklist.summary.completed_slots}
              </span>
              {checklist.summary.in_progress_slots > 0 && (
                <span className="font-semibold text-amber-200">
                  · Taking +{checklist.summary.in_progress_slots}
                </span>
              )}
              {checklist.summary.whatif_slots > 0 && (
                <span className="font-semibold text-sky-200">
                  · What-If +{checklist.summary.whatif_slots}
                </span>
              )}
              <span className="text-zinc-400">
                · <strong className="text-zinc-200">{checklist.summary.filled_slots}/{checklist.summary.total_slots}</strong> filled
                {checklist.summary.remaining_slots > 0 ? ` (${checklist.summary.remaining_slots} left)` : ""}
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

      {/* Collapsible Classes I've Taken & Currently Taking Drawer */}
      {checklist && (() => {
        const hasAnyCourses =
          checklist.completed_courses.length > 0 ||
          (checklist.in_progress_courses?.length ?? 0) > 0;
        const listsExpanded = showCourseLists ?? !hasAnyCourses;
        return (
          <div className="space-y-2.5">
            <button
              type="button"
              onClick={() => setShowCourseLists(!listsExpanded)}
              aria-expanded={listsExpanded}
              className="flex w-full items-center justify-between gap-3 rounded-2xl border border-zinc-800 bg-zinc-900/70 px-4 py-2.5 text-left text-xs transition hover:border-zinc-700"
            >
              <div className="flex flex-wrap items-center gap-3">
                <span className="font-semibold text-zinc-200">My Course Lists</span>
                <span className="text-zinc-400">
                  Taken: <strong className="text-sky-300">{checklist.completed_courses.length}</strong>
                  {" · "}
                  Currently Taking:{" "}
                  <strong className="text-amber-300">{checklist.in_progress_courses?.length ?? 0}</strong>
                </span>
              </div>
              <span className="inline-flex items-center gap-1 text-zinc-400">
                {listsExpanded ? "Hide" : "Quick-Add / Edit"}
                <ChevronDown
                  className={`h-3.5 w-3.5 transition-transform ${listsExpanded ? "rotate-180" : ""}`}
                />
              </span>
            </button>

            {listsExpanded && (
              <div className="grid gap-4 lg:grid-cols-2">
                <CourseQuickAddCard
                  title={`Classes I've Taken (${checklist.completed_courses.length})`}
                  subtitle="Completed & AP courses that auto-fill checklist boxes & unlock prereqs."
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
                  emptyText="No completed classes yet. Type above or use Import Transcript / Completed & Bundles."
                  onAdd={addTakenCourses}
                  onRemove={removeTakenCourse}
                />

                <CourseQuickAddCard
                  title={`Classes Currently Taking (${checklist.in_progress_courses?.length ?? 0})`}
                  subtitle="Classes enrolled right now — fills checklist boxes as Taking & satisfies prereqs."
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
                  emptyText="No currently taking classes yet. Add this semester's classes or import transcript."
                  onAdd={addTakingCourses}
                  onRemove={removeTakingCourse}
                  onPromoteToTaken={promoteTakingToTaken}
                />
              </div>
            )}
          </div>
        );
      })()}

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
                      if (editingSlotId === slot.id) {
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
                        const liveQuick = slotSuggestionsCache[slotCacheKeyFor(slot.id)] || [];
                        const mergedQuick: CsChecklistQuickOption[] = [];
                        const seenQuick = new Set<string>();
                        for (const opt of [...fixedQuick, ...liveQuick]) {
                          if (seenQuick.has(opt.code) || placedInSectionOrCore.has(opt.code)) continue;
                          seenQuick.add(opt.code);
                          mergedQuick.push(opt);
                        }
                        return (
                          <ChecklistSlotEditor
                            key={slot.id}
                            slot={slot}
                            suggestions={mergedQuick.slice(0, 8)}
                            suggestionsLoading={slotSuggestionsLoading}
                            completedCourses={checklist.completed_courses}
                            inProgressCourses={checklist.in_progress_courses || []}
                            editForm={editForm}
                            editSaveMode={editSaveMode}
                            slotPickerFocused={slotPickerFocused}
                            slotSearchDirty={slotSearchDirty}
                            slotSearchOptions={slotSearchOptions}
                            saving={saving}
                            onChangeForm={setEditForm}
                            onChangeSaveMode={setEditSaveMode}
                            onFocusPicker={setSlotPickerFocused}
                            onMarkSearchDirty={() => setSlotSearchDirty(true)}
                            onApplyCourse={(id, course, cr, title) =>
                              void applySlotCourse(id, course, cr, title)
                            }
                            onSave={(id) => void applySlotCourse(id, editForm.course)}
                            onCancel={() => setEditingSlotId(null)}
                          />
                        );
                      }

                      return (
                        <ChecklistSlotRow
                          key={slot.id}
                          slot={slot}
                          isSelected={selectedEmptyIds.includes(slot.id)}
                          onToggleSelect={toggleEmptySlotSelect}
                          onLaunchSearch={(sl) =>
                            onLaunchSearch(buildPresetFromSlots([sl], "any"))
                          }
                          onStartEdit={startEditSlot}
                          onClearSlot={(id) => void clearSlot(id)}
                        />
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
            checklistRef.current = nextChecklist;
            const nextSlots = nextChecklist.manual_slots || {};
            setDraftSlots(nextSlots);
            draftSlotsRef.current = nextSlots;
            syncUserFromChecklist(nextChecklist);
          }}
        />
      )}
    </div>
  );
}
