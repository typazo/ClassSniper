import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Loader2, X } from "lucide-react";
import { api } from "../api/client";
import type {
  CatalogSubjectRefreshedSSE,
  DayCode,
  HydratedSchedule,
  Roster,
  ScheduleCourseItem,
  ScheduleSection,
  ScheduleSummary,
} from "../types";
import { downloadScheduleICS } from "../utils/icsExport";
import { copySchedulePNG } from "../utils/pngExport";
import { summarizeScheduleInsights } from "../utils/scheduleInsights";
import {
  computeScheduleDiagnostics,
  getSelectedSections,
  swapSectionPreservingLocks,
  type GeneratedScheduleCandidate,
} from "../utils/schedulerSolver";
import { FloatingToast } from "./FloatingToast";
import { ScheduleCourseSidebar } from "./ScheduleCourseSidebar";
import { ScheduleDiffModal } from "./ScheduleDiffModal";
import { ScheduleGeneratorPanel } from "./ScheduleGeneratorPanel";
import { SchedulerQuickAddBar } from "./SchedulerQuickAddBar";
import { SchedulerToolbar } from "./SchedulerToolbar";
import { WeeklyCalendarGrid } from "./WeeklyCalendarGrid";

interface Props {
  lastCatalogRefresh?: CatalogSubjectRefreshedSSE | null;
  onWatchesChanged: () => void;
  onJumpToSearch: () => void;
}

export function SchedulerPage({
  lastCatalogRefresh,
  onWatchesChanged,
  onJumpToSearch,
}: Props) {
  const [rosters, setRosters] = useState<Roster[]>([]);
  const [roster, setRoster] = useState<string>("");
  const [schedules, setSchedules] = useState<ScheduleSummary[]>([]);
  const [active, setActive] = useState<HydratedSchedule | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [statusToast, setStatusToast] = useState<string | null>(null);
  const toastTimerRef = useRef<number | null>(null);

  const [expandedCourseId, setExpandedCourseId] = useState<number | null>(null);
  const [swapFocus, setSwapFocus] = useState<{
    courseItemId: number;
    classNbr: number;
  } | null>(null);
  const [loadingBatchInsights, setLoadingBatchInsights] = useState(false);
  const [showDiffModal, setShowDiffModal] = useState(false);
  const [diagnosticsExpanded, setDiagnosticsExpanded] = useState(false);
  const [hoverPreview, setHoverPreview] = useState<{
    course: ScheduleCourseItem;
    section: ScheduleSection;
    conflicts: boolean;
  } | null>(null);

  // Auto-generator state
  const [showGenerator, setShowGenerator] = useState(false);
  const [previewCandidate, setPreviewCandidate] =
    useState<GeneratedScheduleCandidate | null>(null);
  const quickInputRef = useRef<HTMLInputElement | null>(null);

  // Schedule management UI
  const [showNewForm, setShowNewForm] = useState(false);
  const [newName, setNewName] = useState("");
  const [duplicateCurrent, setDuplicateCurrent] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [renameText, setRenameText] = useState("");
  const [showSharePanel, setShowSharePanel] = useState(false);
  const autoInsightsAttemptedRef = useRef<Set<string>>(new Set());
  const activeInsightsFetchIdRef = useRef<number | null>(null);
  const rosterLoadSeqRef = useRef(0);

  const [addingCourseKey, setAddingCourseKey] = useState<string | null>(null);
  const [watchBusyKey, setWatchBusyKey] = useState<string | null>(null);

  useEffect(() => {
    return () => {
      if (toastTimerRef.current !== null) {
        window.clearTimeout(toastTimerRef.current);
      }
    };
  }, []);

  const showToast = useCallback((msg: string) => {
    setStatusToast(msg);
    if (toastTimerRef.current !== null) {
      window.clearTimeout(toastTimerRef.current);
    }
    toastTimerRef.current = window.setTimeout(() => {
      setStatusToast(null);
      toastTimerRef.current = null;
    }, 3600);
  }, []);

  const resetTransientUiState = useCallback(() => {
    setHoverPreview(null);
    setSwapFocus(null);
    setExpandedCourseId(null);
    setPreviewCandidate(null);
    setShowGenerator(false);
    setRenaming(false);
    setShowNewForm(false);
    setDiagnosticsExpanded(false);
  }, []);

  const loadSchedulesForRoster = useCallback(
    async (targetRoster?: string) => {
      const reqSeq = ++rosterLoadSeqRef.current;
      resetTransientUiState();
      setLoading(true);
      setErrorMsg(null);
      try {
        const res = await api.listSchedules(targetRoster);
        if (reqSeq !== rosterLoadSeqRef.current) return;
        setRoster(res.roster);
        setSchedules(res.schedules);
        setActive(res.active);
      } catch (err) {
        if (reqSeq !== rosterLoadSeqRef.current) return;
        setErrorMsg(err instanceof Error ? err.message : "Failed to load schedules");
      } finally {
        if (reqSeq === rosterLoadSeqRef.current) {
          setLoading(false);
        }
      }
    },
    [resetTransientUiState]
  );

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await api.listRosters();
        if (cancelled) return;
        setRosters(res.rosters);
        const def =
          res.rosters.find((r) => r.is_default === 1) || res.rosters[0];
        await loadSchedulesForRoster(def?.slug);
      } catch (err) {
        if (!cancelled) {
          setErrorMsg(err instanceof Error ? err.message : "Failed to load rosters");
          setLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [loadSchedulesForRoster]);

  // Live SSE seat status updates inside scheduler (functional updater avoids stale active closure)
  useEffect(() => {
    if (!lastCatalogRefresh) return;
    const refreshRoster = lastCatalogRefresh.roster.toUpperCase();
    const subjUpper = lastCatalogRefresh.subject.toUpperCase();
    const statusMap = lastCatalogRefresh.section_statuses || {};

    setActive((prev) => {
      if (!prev || prev.schedule.roster.toUpperCase() !== refreshRoster) return prev;
      if (!prev.courses.some((c) => c.subject.toUpperCase() === subjUpper)) return prev;
      return {
        ...prev,
        courses: prev.courses.map((c) => {
          if (c.subject.toUpperCase() !== subjUpper) return c;
          return {
            ...c,
            subject_synced_at: lastCatalogRefresh.synced_at,
            status_is_stale: false,
            enroll_groups: c.enroll_groups.map((eg) => ({
              ...eg,
              sections: eg.sections.map((sec) => {
                const updated = statusMap[String(sec.class_nbr)];
                return updated ? { ...sec, open_status: updated } : sec;
              }),
            })),
          };
        }),
      };
    });
  }, [lastCatalogRefresh]);

  // Auto-fetch missing CU Reviews & RMP difficulty/ratings once per course when a schedule opens
  useEffect(() => {
    if (!active || active.courses.length === 0) return;
    const schedId = active.schedule.id;
    if (activeInsightsFetchIdRef.current === schedId) return;

    const missing = active.courses.filter((c) => {
      const key = `${schedId}:${c.subject}:${c.catalog_nbr}`;
      if (autoInsightsAttemptedRef.current.has(key)) return false;
      return c.cached_insights === null && Object.keys(c.cached_rmp || {}).length === 0;
    });
    if (missing.length === 0) return;

    for (const c of missing) {
      autoInsightsAttemptedRef.current.add(`${schedId}:${c.subject}:${c.catalog_nbr}`);
    }

    let cancelled = false;
    activeInsightsFetchIdRef.current = schedId;
    setLoadingBatchInsights(true);
    api
      .batchLoadScheduleInsights(schedId, false)
      .then((res) => {
        if (!cancelled) {
          setActive((cur) => (cur && cur.schedule.id === schedId ? res : cur));
        }
      })
      .catch(() => {
        // Silent background fetch; manual button remains available
      })
      .finally(() => {
        if (activeInsightsFetchIdRef.current === schedId) {
          activeInsightsFetchIdRef.current = null;
        }
        setLoadingBatchInsights(false);
      });

    return () => {
      cancelled = true;
    };
  }, [active]);

  const isTranscriptSchedule = Boolean(active?.schedule.is_transcript);
  const activeRosterObj = useMemo(
    () => rosters.find((r) => r.slug === roster) || null,
    [rosters, roster]
  );
  const isArchivedRoster = Boolean(activeRosterObj?.archive_mode === 1);

  const displayedCourses = useMemo(() => {
    if (!active) return [];
    if (!showGenerator || !previewCandidate) return active.courses;
    const byId = new Map<number, number[]>();
    for (const sel of previewCandidate.selections) {
      byId.set(sel.item_id, sel.selected_class_nbrs);
    }
    return active.courses.map((c) => {
      const override = byId.get(c.id);
      return override ? { ...c, selected_class_nbrs: override } : c;
    });
  }, [active, showGenerator, previewCandidate]);

  const diagnostics = useMemo(
    () => computeScheduleDiagnostics(displayedCourses, active?.blocks || []),
    [displayedCourses, active?.blocks]
  );

  const insightsSummary = useMemo(
    () => summarizeScheduleInsights(displayedCourses),
    [displayedCourses]
  );

  const closedOrWaitlistSelected = useMemo(() => {
    const out: Array<{ course: ScheduleCourseItem; section: ScheduleSection }> = [];
    for (const c of displayedCourses) {
      if (!c.enabled) continue;
      for (const sec of getSelectedSections(c)) {
        if (sec.open_status !== "O") {
          out.push({ course: c, section: sec });
        }
      }
    }
    return out;
  }, [displayedCourses]);

  const handleSelectSchedule = async (scheduleId: number) => {
    resetTransientUiState();
    try {
      const res = await api.updateSchedule(scheduleId, { is_active: true });
      setSchedules(res.schedules);
      setActive(res.active);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to switch schedule");
    }
  };

  const handleCreateSchedule = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!roster || !newName.trim()) return;
    try {
      const res = await api.createSchedule({
        roster,
        name: newName.trim(),
        duplicate_from_id: duplicateCurrent && active ? active.schedule.id : undefined,
      });
      resetTransientUiState();
      setSchedules(res.schedules);
      setActive(res.active);
      setNewName("");
      showToast(`Created schedule "${res.active.schedule.name}"`);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to create schedule");
    }
  };

  const handleDuplicateToEditablePlan = async () => {
    if (!active || !roster) return;
    const existingNames = new Set(schedules.map((s) => s.name.trim().toLowerCase()));
    let candidateName = !existingNames.has("main schedule")
      ? "Main Schedule"
      : "Editable Plan";
    let suffix = 2;
    while (existingNames.has(candidateName.toLowerCase())) {
      candidateName = `Editable Plan ${suffix}`;
      suffix += 1;
    }
    try {
      const res = await api.createSchedule({
        roster,
        name: candidateName,
        duplicate_from_id: active.schedule.id,
      });
      resetTransientUiState();
      setSchedules(res.schedules);
      setActive(res.active);
      showToast(`Created editable copy "${res.active.schedule.name}"`);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to duplicate schedule");
    }
  };

  const handleRenameSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!active || !renameText.trim()) return;
    try {
      const res = await api.updateSchedule(active.schedule.id, {
        name: renameText.trim(),
      });
      setSchedules(res.schedules);
      setActive(res.active);
      setRenaming(false);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to rename schedule");
    }
  };

  const handleDeleteSchedule = async () => {
    if (!active) return;
    if (schedules.length <= 1) {
      showToast("You must keep at least one schedule per roster.");
      return;
    }
    try {
      const res = await api.deleteSchedule(active.schedule.id, roster);
      resetTransientUiState();
      setSchedules(res.schedules);
      setActive(res.active);
      showToast("Schedule deleted");
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to delete schedule");
    }
  };

  const handleToggleShare = async (enabled: boolean) => {
    if (!active) return;
    try {
      const res = await api.updateSchedule(active.schedule.id, {
        share_enabled: enabled,
      });
      setSchedules(res.schedules);
      setActive(res.active);
      showToast(enabled ? "Share link enabled" : "Share link disabled");
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to update sharing");
    }
  };

  const handleRegenerateShare = async () => {
    if (!active) return;
    try {
      const res = await api.updateSchedule(active.schedule.id, {
        share_enabled: true,
        regenerate_share_token: true,
      });
      setSchedules(res.schedules);
      setActive(res.active);
      showToast("Generated new share link (old link invalidated)");
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to regenerate share link");
    }
  };

  const handleAddCourse = async (subject: string, catalogNbr: string) => {
    if (!active) return;
    const key = `${subject}-${catalogNbr}`;
    setAddingCourseKey(key);
    setErrorMsg(null);
    try {
      const updated = await api.addScheduleCourse(active.schedule.id, {
        subject,
        catalog_nbr: catalogNbr,
      });
      setActive(updated);
      const added = updated.courses.find(
        (c) => c.subject === subject && c.catalog_nbr === catalogNbr
      );
      if (added) setExpandedCourseId(added.id);
      showToast(`Added ${subject} ${catalogNbr}`);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to add course");
    } finally {
      setAddingCourseKey(null);
    }
  };

  const handleUpdateCourse = async (
    itemId: number,
    patch: {
      enabled?: boolean;
      selected_units?: number | null;
      selected_class_nbrs?: number[];
      locked_class_nbrs?: number[];
    }
  ) => {
    if (!active) return;
    try {
      const updated = await api.updateScheduleCourse(active.schedule.id, itemId, patch);
      setActive(updated);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to update course");
    }
  };

  const handleSelectAlternativeSection = async (
    courseItemId: number,
    oldClassNbr: number,
    newClassNbr: number
  ) => {
    if (!active) return;
    const target = active.courses.find((c) => c.id === courseItemId);
    if (!target) return;
    let newSection: ScheduleSection | null = null;
    for (const eg of target.enroll_groups) {
      const found = eg.sections.find((s) => s.class_nbr === newClassNbr);
      if (found) {
        newSection = found;
        break;
      }
    }
    const patch = newSection
      ? swapSectionPreservingLocks(target, newSection)
      : {
          selected_class_nbrs: target.selected_class_nbrs.map((nbr) =>
            nbr === oldClassNbr ? newClassNbr : nbr
          ),
        };
    setSwapFocus(null);
    setHoverPreview(null);
    await handleUpdateCourse(courseItemId, patch);
    showToast(`Swapped ${target.subject} ${target.catalog_nbr} to #${newClassNbr}`);
  };

  const handleLoadAllInsights = async () => {
    if (!active || active.courses.length === 0) return;
    setLoadingBatchInsights(true);
    setErrorMsg(null);
    try {
      const res = await api.batchLoadScheduleInsights(active.schedule.id, true);
      setActive(res);
      const count = res.insights_fetched_count ?? 0;
      showToast(
        count > 0
          ? `Loaded CU Reviews & RMP ratings for ${count} course${count === 1 ? "" : "s"}`
          : "All schedule course ratings already up to date"
      );
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to load course ratings");
    } finally {
      setLoadingBatchInsights(false);
    }
  };

  const handleRemoveCourse = async (itemId: number) => {
    if (!active) return;
    try {
      const updated = await api.removeScheduleCourse(active.schedule.id, itemId);
      setActive(updated);
      if (expandedCourseId === itemId) setExpandedCourseId(null);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to remove course");
    }
  };

  const handleApplyGenerated = async (candidate: GeneratedScheduleCandidate) => {
    if (!active) return;
    try {
      const updated = await api.applyGeneratedSchedule(
        active.schedule.id,
        candidate.selections.map((s) => ({
          item_id: s.item_id,
          selected_class_nbrs: s.selected_class_nbrs,
        }))
      );
      setActive(updated);
      setPreviewCandidate(null);
      showToast("Applied generated schedule!");
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to apply generated schedule");
      throw err;
    }
  };

  const handleCreateBlock = async (payload: {
    label?: string;
    days: DayCode[];
    startMin: number;
    endMin: number;
  }) => {
    if (!active) return;
    try {
      const updated = await api.createScheduleBlock(active.schedule.id, {
        label: payload.label || "Busy",
        days: payload.days,
        start_min: payload.startMin,
        end_min: payload.endMin,
      });
      setActive(updated);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to add busy block");
    }
  };

  const handleToggleBlock = async (blockId: number, enabled: boolean) => {
    if (!active) return;
    try {
      const updated = await api.updateScheduleBlock(active.schedule.id, blockId, {
        enabled,
      });
      setActive(updated);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to update busy block");
    }
  };

  const handleDeleteBlock = async (blockId: number) => {
    if (!active) return;
    try {
      const updated = await api.deleteScheduleBlock(active.schedule.id, blockId);
      setActive(updated);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to delete busy block");
    }
  };

  const batchCreateWatches = async (
    targets: Array<{ course: ScheduleCourseItem; section: ScheduleSection }>,
    busyKey: string
  ) => {
    if (!active || targets.length === 0) return;
    setWatchBusyKey(busyKey);
    setErrorMsg(null);
    let created = 0;
    let already = 0;
    let failedMsg = "";

    for (const { course, section } of targets) {
      try {
        await api.createWatch({
          roster: active.schedule.roster,
          subject: course.subject,
          catalog_nbr: course.catalog_nbr,
          class_nbr: section.class_nbr,
          enroll_group_idx: section.enroll_group_idx,
          mode: "exact",
          trigger_on: "open",
          priority: 1,
          auto_pause: false,
          ithaca_or_virtual: false,
          cooldown_sec: 60,
        });
        created += 1;
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Failed to create watch";
        if (msg.toLowerCase().includes("already watching")) {
          already += 1;
        } else {
          failedMsg = msg;
          break;
        }
      }
    }

    setWatchBusyKey(null);
    if (created > 0) onWatchesChanged();

    if (failedMsg) {
      setErrorMsg(
        `Created ${created} watch${created === 1 ? "" : "es"}, then stopped: ${failedMsg}`
      );
    } else {
      showToast(
        `Created ${created} watch${created === 1 ? "" : "es"}${
          already > 0 ? ` (${already} already watched)` : ""
        }`
      );
    }
  };

  const handleCopyPng = async (): Promise<boolean> => {
    if (!active) return false;
    const outcome = await copySchedulePNG(active, displayedCourses, active.blocks);
    if (outcome === "copied") {
      showToast("Copied schedule PNG to clipboard");
      return true;
    }
    if (outcome === "shared") {
      showToast("Opened share sheet with schedule PNG");
      return true;
    }
    if (outcome === "downloaded") {
      showToast("Downloaded schedule PNG");
      return true;
    }
    if (outcome === "failed") {
      setErrorMsg("Failed to copy schedule PNG");
    }
    return false;
  };

  if (loading && !active) {
    return (
      <div className="flex items-center justify-center rounded-2xl border border-zinc-800 bg-zinc-900/60 py-16 text-sm text-zinc-400">
        <Loader2 className="mr-2 h-4 w-4 animate-spin text-emerald-400" />
        Loading Scheduler...
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <SchedulerToolbar
        rosters={rosters}
        roster={roster}
        isArchivedRoster={isArchivedRoster}
        schedules={schedules}
        active={active}
        displayedCourses={displayedCourses}
        diagnostics={diagnostics}
        insightsSummary={insightsSummary}
        loadingBatchInsights={loadingBatchInsights}
        showGenerator={showGenerator}
        showNewForm={showNewForm}
        showSharePanel={showSharePanel}
        renaming={renaming}
        renameText={renameText}
        newName={newName}
        duplicateCurrent={duplicateCurrent}
        closedOrWaitlistCount={closedOrWaitlistSelected.length}
        watchBusyKey={watchBusyKey}
        diagnosticsExpanded={diagnosticsExpanded}
        onChangeRoster={(slug) => {
          setShowGenerator(false);
          void loadSchedulesForRoster(slug);
        }}
        onSelectSchedule={(id) => void handleSelectSchedule(id)}
        onToggleNewForm={() => {
          setShowNewForm((v) => !v);
          setDuplicateCurrent(false);
        }}
        onChangeNewName={setNewName}
        onChangeDuplicateCurrent={setDuplicateCurrent}
        onCreateSchedule={handleCreateSchedule}
        onStartRename={() => {
          if (active) {
            setRenameText(active.schedule.name);
            setRenaming(true);
          }
        }}
        onChangeRenameText={setRenameText}
        onSubmitRename={handleRenameSubmit}
        onCancelRename={() => setRenaming(false)}
        onDeleteSchedule={() => void handleDeleteSchedule()}
        onToggleGenerator={() => {
          if (!active || active.courses.length === 0) {
            quickInputRef.current?.focus();
            showToast("Add at least 1 course first to run Auto-Generate.");
            return;
          }
          setShowGenerator((v) => !v);
        }}
        onWatchClosed={() => void batchCreateWatches(closedOrWaitlistSelected, "all-missing")}
        onLoadRatings={() => void handleLoadAllInsights()}
        onOpenCompare={() => setShowDiffModal(true)}
        onCopyPng={handleCopyPng}
        onDownloadIcs={() =>
          active &&
          downloadScheduleICS(active.schedule.name, active.schedule.roster, displayedCourses)
        }
        onToggleSharePanel={() => setShowSharePanel((v) => !v)}
        onToggleShareEnabled={(enabled) => void handleToggleShare(enabled)}
        onRegenerateShare={() => void handleRegenerateShare()}
        onToggleDiagnostics={() => setDiagnosticsExpanded((v) => !v)}
      />

      {errorMsg && (
        <div className="flex items-center justify-between gap-2 rounded-xl border border-rose-500/40 bg-rose-500/15 px-3.5 py-2.5 text-xs text-rose-200">
          <span>{errorMsg}</span>
          <button type="button" onClick={() => setErrorMsg(null)} className="text-rose-300 hover:text-white">
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      )}

      <FloatingToast
        message={statusToast}
        tone="success"
        onDismiss={() => setStatusToast(null)}
      />

      {showGenerator && active && (
        <ScheduleGeneratorPanel
          courses={active.courses}
          blocks={active.blocks}
          onPreviewCandidate={setPreviewCandidate}
          onApplyCandidate={handleApplyGenerated}
          onClose={() => setShowGenerator(false)}
        />
      )}

      <SchedulerQuickAddBar
        roster={roster}
        isTranscriptSchedule={isTranscriptSchedule}
        courses={active?.courses || []}
        addingCourseKey={addingCourseKey}
        quickInputRef={quickInputRef}
        onAddCourse={(subj, nbr) => void handleAddCourse(subj, nbr)}
        onDuplicateToEditable={() => void handleDuplicateToEditablePlan()}
        onJumpToSearch={onJumpToSearch}
      />

      {/* Main Split View: Weekly Grid + Course Sidebar */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
        <div className="lg:col-span-8">
          <WeeklyCalendarGrid
            key={active?.schedule.id ?? "empty"}
            courses={displayedCourses}
            blocks={active?.blocks || []}
            diagnostics={diagnostics}
            hoverPreview={hoverPreview}
            swapFocus={swapFocus}
            onClickCourseSection={(courseItemId, classNbr) => {
              setExpandedCourseId(courseItemId);
              setSwapFocus((cur) =>
                cur && cur.courseItemId === courseItemId && cur.classNbr === classNbr
                  ? null
                  : { courseItemId, classNbr }
              );
            }}
            onSelectAlternativeSection={(courseItemId, oldClassNbr, newClassNbr) =>
              void handleSelectAlternativeSection(courseItemId, oldClassNbr, newClassNbr)
            }
            onClearSwapFocus={() => setSwapFocus(null)}
            onDeleteBlock={(blockId) => void handleDeleteBlock(blockId)}
            onCreateBlock={(blk) =>
              void handleCreateBlock({
                label: "Busy",
                days: blk.days,
                startMin: blk.startMin,
                endMin: blk.endMin,
              })
            }
          />
        </div>

        <div className="lg:col-span-4">
          <ScheduleCourseSidebar
            courses={displayedCourses}
            blocks={active?.blocks || []}
            expandedCourseId={expandedCourseId}
            watchBusyKey={watchBusyKey}
            isTranscript={isTranscriptSchedule}
            isArchivedRoster={isArchivedRoster}
            onToggleExpand={(itemId) => {
              setHoverPreview(null);
              setExpandedCourseId((cur) => (cur === itemId ? null : itemId));
            }}
            onUpdateCourse={(itemId, patch) => void handleUpdateCourse(itemId, patch)}
            onRemoveCourse={(itemId) => void handleRemoveCourse(itemId)}
            onHoverSection={setHoverPreview}
            onWatchCourseCompatible={(course, secs) =>
              void batchCreateWatches(
                secs.map((section) => ({ course, section })),
                `course-${course.id}`
              )
            }
            onCreateBlock={(blk) => void handleCreateBlock(blk)}
            onToggleBlock={(blockId, enabled) => void handleToggleBlock(blockId, enabled)}
            onDeleteBlock={(blockId) => void handleDeleteBlock(blockId)}
          />
        </div>
      </div>

      {active && (
        <ScheduleDiffModal
          isOpen={showDiffModal}
          active={active}
          schedules={schedules}
          onClose={() => setShowDiffModal(false)}
        />
      )}
    </div>
  );
}
