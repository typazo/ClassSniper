import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  CalendarCheck2,
  Check,
  CheckSquare,
  Edit3,
  Eraser,
  GraduationCap,
  ListChecks,
  Loader2,
  RotateCcw,
  Search,
  Sparkles,
  Square,
  X,
} from "lucide-react";
import { api } from "../api/client";
import type {
  AttrMatchMode,
  CourseSearchPreset,
  CSCurriculumMode,
  CsChecklistPayload,
  CsChecklistSlot,
  CsChecklistSlotInput,
  CSRequirementMode,
  Roster,
  User,
} from "../types";
import { CompletedPrereqsModal } from "./CompletedPrereqsModal";

interface Props {
  user: User;
  initialRoster?: string;
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

export function CsChecklistPage({ user, initialRoster, onUserUpdated, onLaunchSearch }: Props) {
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
  const [selectedEmptyIds, setSelectedEmptyIds] = useState<string[]>([]);
  const [multiAttrMatch, setMultiAttrMatch] = useState<AttrMatchMode>("any");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [prereqsOpen, setPrereqsOpen] = useState(false);

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
      const nextDraft: Record<string, CsChecklistSlotInput> = {};
      for (const sec of data.sections) {
        for (const sl of sec.slots) {
          if (sl.course || sl.sem || sl.gr || sl.cr || sl.notes) {
            nextDraft[sl.id] = {
              course: sl.course,
              title: sl.title,
              cr: sl.cr,
              sem: sl.sem,
              gr: sl.gr,
              notes: sl.notes,
              pinned: sl.source === "manual",
            };
          }
        }
      }
      setDraftSlots(nextDraft);
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

  const persistChecklist = async (
    nextCollege: "arts" | "engineering",
    nextCurriculum: CSCurriculumMode,
    nextIncludeSched: boolean,
    nextPe: number,
    nextSlots: Record<string, CsChecklistSlotInput>
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
        },
        selectedRoster || undefined
      );
      setChecklist(updated);
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
    const existing = draftSlots[slot.id];
    setEditForm({
      course: existing?.course || slot.course || "",
      title: existing?.title || slot.title || "",
      cr: existing?.cr || slot.cr || "",
      sem: existing?.sem || slot.sem || "",
      gr: existing?.gr || slot.gr || "",
      notes: existing?.notes || slot.notes || "",
      pinned: true,
      cleared: false,
    });
  };

  const saveEditSlot = async (slotId: string) => {
    if (!checklist) return;
    const nextSlots: Record<string, CsChecklistSlotInput> = {
      ...draftSlots,
      [slotId]: {
        ...editForm,
        course: editForm.course.trim().toUpperCase(),
        pinned: Boolean(editForm.course.trim()),
        cleared: !editForm.course.trim(),
      },
    };
    setDraftSlots(nextSlots);
    setEditingSlotId(null);
    await persistChecklist(
      checklist.college,
      checklist.curriculum,
      checklist.include_active_schedule,
      checklist.pe_completed,
      nextSlots
    );
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
              Auto-populates from your completed courses &amp; active What-If schedule. Click any{" "}
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
            {checklist.sections.map((section) => (
              <div
                key={section.id}
                className={`overflow-hidden rounded-2xl border border-zinc-800 bg-zinc-900/75 ${
                  section.id === "cs_electives" ? "lg:col-span-2" : ""
                }`}
              >
                <div className="border-b border-zinc-800/90 bg-zinc-950/70 px-4 py-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <h3 className="text-sm font-bold text-white">{section.title}</h3>
                    <span className="rounded-full bg-zinc-800 px-2 py-0.5 text-[11px] font-medium text-zinc-300">
                      {section.slots.filter((s) => s.filled).length}/{section.slots.length}
                    </span>
                  </div>
                  <p className="mt-0.5 text-[11px] text-zinc-400">{section.subtitle}</p>
                </div>

                <div className="divide-y divide-zinc-800/70">
                  {section.slots.map((slot) => {
                    const isSelected = selectedEmptyIds.includes(slot.id);
                    const isEditing = editingSlotId === slot.id;

                    if (isEditing) {
                      return (
                        <div key={slot.id} className="space-y-2 bg-zinc-950/90 p-3 text-xs">
                          <div className="flex items-center justify-between">
                            <span className="font-semibold text-white">
                              Edit Slot: {slot.label}
                            </span>
                            <span className="text-[11px] text-zinc-400">{slot.expected}</span>
                          </div>
                          <div className="grid grid-cols-2 gap-2 sm:grid-cols-6">
                            <input
                              type="text"
                              value={editForm.course}
                              onChange={(e) => setEditForm({ ...editForm, course: e.target.value })}
                              placeholder="Course (e.g. CS 4780)"
                              className="col-span-2 rounded-lg border border-zinc-700 bg-zinc-900 px-2.5 py-1.5 text-xs text-white"
                            />
                            <input
                              type="text"
                              value={editForm.cr}
                              onChange={(e) => setEditForm({ ...editForm, cr: e.target.value })}
                              placeholder="Cr (e.g. 4)"
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
                            <div className="flex justify-end gap-1.5">
                              <button
                                type="button"
                                onClick={() => setEditingSlotId(null)}
                                className="rounded-lg border border-zinc-700 px-2 py-1 text-zinc-300 hover:bg-zinc-800"
                              >
                                Cancel
                              </button>
                              <button
                                type="button"
                                onClick={() => void saveEditSlot(slot.id)}
                                className="rounded-lg bg-emerald-500 px-2.5 py-1 font-semibold text-zinc-950 hover:bg-emerald-400"
                              >
                                Save
                              </button>
                            </div>
                          </div>
                        </div>
                      );
                    }

                    const isWhatIf = slot.filled && slot.source === "schedule";

                    return (
                      <div
                        key={slot.id}
                        className={`flex flex-wrap items-center justify-between gap-2 px-4 py-2.5 text-xs transition ${
                          !slot.filled
                            ? isSelected
                              ? "bg-emerald-500/15"
                              : "hover:bg-zinc-800/40"
                            : isWhatIf
                              ? "bg-sky-500/5"
                              : ""
                        }`}
                      >
                        {/* Left: Checkbox / Slot Box */}
                        <div className="flex min-w-0 flex-1 items-center gap-2.5">
                          {!slot.filled ? (
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
                                  isWhatIf
                                    ? "border-dashed border-sky-400 bg-sky-500/20 text-sky-300"
                                    : "border-emerald-500/60 bg-emerald-500/20 text-emerald-300"
                                }`}
                              >
                                {isWhatIf ? (
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
                                  {slot.gr && (
                                    <span className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono text-[10px] text-zinc-300">
                                      {slot.gr}
                                    </span>
                                  )}
                                </div>
                              </div>
                            </div>
                          )}
                        </div>

                        {/* Right: Quick Search / Edit / Clear actions */}
                        <div className="flex items-center gap-1.5">
                          {!slot.filled && (
                            <button
                              type="button"
                              onClick={() => onLaunchSearch(buildPresetFromSlots([slot], "any"))}
                              className="inline-flex items-center gap-1 rounded-lg border border-emerald-500/35 bg-emerald-500/10 px-2 py-1 text-[11px] font-medium text-emerald-200 hover:bg-emerald-500/20"
                              title={`Find courses satisfying ${slot.label}`}
                            >
                              <Search className="h-3 w-3" />
                              Find
                            </button>
                          )}
                          <button
                            type="button"
                            onClick={() => startEditSlot(slot)}
                            className="rounded-lg border border-zinc-700/80 p-1 text-zinc-400 hover:text-white"
                            title="Manually enter or edit course, credits, semester, grade"
                          >
                            <Edit3 className="h-3 w-3" />
                          </button>
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
            ))}
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
    </div>
  );
}
