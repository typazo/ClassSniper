import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowLeftRight,
  BellPlus,
  Calendar,
  Check,
  Copy,
  Download,
  Edit3,
  Footprints,
  HelpCircle,
  Image,
  Link2,
  Loader2,
  Plus,
  RefreshCw,
  Search,
  Share2,
  Sparkles,
  Star,
  Trash2,
  X,
} from "lucide-react";
import { api } from "../api/client";
import type {
  CatalogSubjectRefreshedSSE,
  CourseSummary,
  DayCode,
  HydratedSchedule,
  Roster,
  ScheduleCourseItem,
  ScheduleSection,
  ScheduleSummary,
  User,
} from "../types";
import { downloadScheduleICS } from "../utils/icsExport";
import { downloadSchedulePNG } from "../utils/pngExport";
import {
  computeScheduleDiagnostics,
  type GeneratedScheduleCandidate,
} from "../utils/schedulerSolver";
import { ScheduleCourseSidebar } from "./ScheduleCourseSidebar";
import { ScheduleDiffModal } from "./ScheduleDiffModal";
import { ScheduleGeneratorPanel } from "./ScheduleGeneratorPanel";
import { WeeklyCalendarGrid } from "./WeeklyCalendarGrid";

interface Props {
  user: User;
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

  const [expandedCourseId, setExpandedCourseId] = useState<number | null>(null);
  const [swapFocus, setSwapFocus] = useState<{
    courseItemId: number;
    classNbr: number;
  } | null>(null);
  const [loadingBatchInsights, setLoadingBatchInsights] = useState(false);
  const [showDiffModal, setShowDiffModal] = useState(false);
  const [hoverPreview, setHoverPreview] = useState<{
    course: ScheduleCourseItem;
    section: ScheduleSection;
    conflicts: boolean;
  } | null>(null);

  // Auto-generator state
  const [showGenerator, setShowGenerator] = useState(false);
  const [showGeneratorHelp, setShowGeneratorHelp] = useState(false);
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
  const [copiedShareUrl, setCopiedShareUrl] = useState(false);

  // Quick course add search
  const [quickQuery, setQuickQuery] = useState("");
  const [quickResults, setQuickResults] = useState<CourseSummary[]>([]);
  const [quickLoading, setQuickLoading] = useState(false);
  const [addingCourseKey, setAddingCourseKey] = useState<string | null>(null);
  const [watchBusyKey, setWatchBusyKey] = useState<string | null>(null);
  const quickDebounceRef = useRef<number | null>(null);

  const showToast = useCallback((msg: string) => {
    setStatusToast(msg);
    window.setTimeout(() => {
      setStatusToast((cur) => (cur === msg ? null : cur));
    }, 4000);
  }, []);

  const loadSchedulesForRoster = useCallback(async (targetRoster?: string) => {
    setLoading(true);
    setErrorMsg(null);
    try {
      const res = await api.listSchedules(targetRoster);
      setRoster(res.roster);
      setSchedules(res.schedules);
      setActive(res.active);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to load schedules");
    } finally {
      setLoading(false);
    }
  }, []);

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

  // Live SSE seat status updates inside scheduler
  useEffect(() => {
    if (!lastCatalogRefresh || !active) return;
    if (lastCatalogRefresh.roster.toUpperCase() !== active.schedule.roster.toUpperCase()) {
      return;
    }
    const subjUpper = lastCatalogRefresh.subject.toUpperCase();
    if (!active.courses.some((c) => c.subject.toUpperCase() === subjUpper)) {
      return;
    }

    const statusMap = lastCatalogRefresh.section_statuses || {};
    setActive((prev) => {
      if (!prev) return prev;
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
  }, [lastCatalogRefresh]); // eslint-disable-line react-hooks/exhaustive-deps

  // Quick search debounce
  useEffect(() => {
    if (quickDebounceRef.current) {
      window.clearTimeout(quickDebounceRef.current);
    }
    const trimmed = quickQuery.trim();
    if (!trimmed || !roster) {
      setQuickResults([]);
      setQuickLoading(false);
      return;
    }
    setQuickLoading(true);
    quickDebounceRef.current = window.setTimeout(async () => {
      try {
        const res = await api.searchCourses(roster, trimmed, {
          limit: 8,
          ithaca_or_virtual: false,
          refresh_stale: true,
        });
        setQuickResults(res.courses);
      } catch {
        setQuickResults([]);
      } finally {
        setQuickLoading(false);
      }
    }, 220);
    return () => {
      if (quickDebounceRef.current) window.clearTimeout(quickDebounceRef.current);
    };
  }, [quickQuery, roster]);

  // Effective courses shown on grid (overlays auto-generator preview if open)
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

  // Average CU Reviews rating/workload across courses that have cached insights
  const insightsSummary = useMemo(() => {
    const enabled = displayedCourses.filter((c) => c.enabled);
    const ratings = enabled
      .map((c) => c.cached_insights?.rating)
      .filter((v): v is number => typeof v === "number");
    const workloads = enabled
      .map((c) => c.cached_insights?.workload)
      .filter((v): v is number => typeof v === "number");
    return {
      avgRating:
        ratings.length > 0
          ? ratings.reduce((a, b) => a + b, 0) / ratings.length
          : null,
      avgWorkload:
        workloads.length > 0
          ? workloads.reduce((a, b) => a + b, 0) / workloads.length
          : null,
    };
  }, [displayedCourses]);

  const closedOrWaitlistSelected = useMemo(() => {
    const out: Array<{ course: ScheduleCourseItem; section: ScheduleSection }> = [];
    for (const c of displayedCourses) {
      if (!c.enabled) continue;
      const sel = new Set(c.selected_class_nbrs);
      for (const eg of c.enroll_groups) {
        for (const sec of eg.sections) {
          if (sel.has(sec.class_nbr) && sec.open_status !== "O") {
            out.push({ course: c, section: sec });
          }
        }
      }
    }
    return out;
  }, [displayedCourses]);

  const handleSelectSchedule = async (scheduleId: number) => {
    try {
      const res = await api.updateSchedule(scheduleId, { is_active: true });
      setSchedules(res.schedules);
      setActive(res.active);
      setExpandedCourseId(null);
      setShowGenerator(false);
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
      setSchedules(res.schedules);
      setActive(res.active);
      setNewName("");
      setShowNewForm(false);
      setShowGenerator(false);
      showToast(`Created schedule "${res.active.schedule.name}"`);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to create schedule");
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
      setSchedules(res.schedules);
      setActive(res.active);
      setExpandedCourseId(null);
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
      setQuickQuery("");
      setQuickResults([]);
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
    const nextSelected = target.selected_class_nbrs.map((nbr) =>
      nbr === oldClassNbr ? newClassNbr : nbr
    );
    const nextLocked = target.locked_class_nbrs.includes(oldClassNbr)
      ? target.locked_class_nbrs.map((nbr) => (nbr === oldClassNbr ? newClassNbr : nbr))
      : target.locked_class_nbrs;
    setSwapFocus(null);
    await handleUpdateCourse(courseItemId, {
      selected_class_nbrs: nextSelected,
      locked_class_nbrs: nextLocked,
    });
    showToast(`Swapped ${target.subject} ${target.catalog_nbr} to #${newClassNbr}`);
  };

  const handleLoadAllInsights = async () => {
    if (!active || active.courses.length === 0) return;
    setLoadingBatchInsights(true);
    setErrorMsg(null);
    try {
      const res = await api.batchLoadScheduleInsights(active.schedule.id, false);
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
      {/* Top Toolbar: Roster + Schedule Switcher + Actions */}
      <div className="rounded-2xl border border-zinc-800 bg-zinc-900/80 p-3.5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2">
            {/* Roster Select */}
            <select
              value={roster}
              onChange={(e) => {
                setShowGenerator(false);
                void loadSchedulesForRoster(e.target.value);
              }}
              className="rounded-xl border border-zinc-700 bg-zinc-950 px-3 py-1.5 text-xs font-semibold text-zinc-100"
            >
              {rosters.map((r) => (
                <option key={r.slug} value={r.slug}>
                  {r.descr} ({r.slug})
                </option>
              ))}
            </select>

            {/* Schedule Switcher */}
            {active && !renaming && (
              <select
                value={active.schedule.id}
                onChange={(e) => void handleSelectSchedule(Number(e.target.value))}
                className="rounded-xl border border-zinc-700 bg-zinc-950 px-3 py-1.5 text-xs font-semibold text-emerald-300"
              >
                {schedules.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name} ({s.course_count ?? 0})
                  </option>
                ))}
              </select>
            )}

            {/* Rename inline */}
            {active && renaming && (
              <form onSubmit={handleRenameSubmit} className="flex items-center gap-1.5">
                <input
                  type="text"
                  value={renameText}
                  onChange={(e) => setRenameText(e.target.value)}
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
                  onClick={() => setRenaming(false)}
                  className="rounded-lg px-2 py-1 text-xs text-zinc-400"
                >
                  Cancel
                </button>
              </form>
            )}

            <button
              type="button"
              onClick={() => {
                setShowNewForm((v) => !v);
                setDuplicateCurrent(false);
              }}
              title="New schedule"
              className="inline-flex items-center gap-1 rounded-xl border border-zinc-700 px-2.5 py-1.5 text-xs text-zinc-200 hover:border-emerald-500/50 hover:text-emerald-300"
            >
              <Plus className="h-3.5 w-3.5" />
              New
            </button>

            {active && (
              <>
                <button
                  type="button"
                  onClick={() => {
                    setRenameText(active.schedule.name);
                    setRenaming(true);
                  }}
                  title="Rename schedule"
                  className="rounded-xl border border-zinc-800 p-1.5 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
                >
                  <Edit3 className="h-3.5 w-3.5" />
                </button>
                {schedules.length > 1 && (
                  <button
                    type="button"
                    onClick={handleDeleteSchedule}
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
            <div className="inline-flex items-center">
              <button
                type="button"
                onClick={() => {
                  if (!active || active.courses.length === 0) {
                    setShowGeneratorHelp(true);
                    quickInputRef.current?.focus();
                    return;
                  }
                  setShowGenerator((v) => !v);
                }}
                title={
                  !active || active.courses.length === 0
                    ? "Add at least 1 course first to auto-generate section combinations"
                    : "Find conflict-free section combinations across your courses"
                }
                className={`inline-flex items-center gap-1.5 rounded-l-xl px-3 py-1.5 text-xs font-bold transition ${
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
              <button
                type="button"
                onClick={() => setShowGeneratorHelp((v) => !v)}
                title="How Auto-Generate works"
                aria-label="How Auto-Generate works"
                className={`inline-flex items-center justify-center rounded-r-xl border border-l-0 px-2 py-1.5 text-xs transition ${
                  showGeneratorHelp
                    ? "border-sky-400/60 bg-sky-500/20 text-sky-200"
                    : showGenerator
                      ? "border-emerald-400 bg-emerald-500/20 text-emerald-300 hover:bg-emerald-500/30"
                      : "border-zinc-700 bg-zinc-950 text-zinc-400 hover:text-zinc-200"
                }`}
              >
                <HelpCircle className="h-3.5 w-3.5" />
              </button>
            </div>

            {closedOrWaitlistSelected.length > 0 && (
              <button
                type="button"
                disabled={watchBusyKey === "all-missing"}
                onClick={() => batchCreateWatches(closedOrWaitlistSelected, "all-missing")}
                className="inline-flex items-center gap-1.5 rounded-xl border border-amber-500/45 bg-amber-500/15 px-3 py-1.5 text-xs font-semibold text-amber-200 hover:bg-amber-500/25 disabled:opacity-50"
              >
                <BellPlus className="h-3.5 w-3.5" />
                {watchBusyKey === "all-missing"
                  ? "Watching..."
                  : `Watch Closed (${closedOrWaitlistSelected.length})`}
              </button>
            )}

            <button
              type="button"
              disabled={!active || displayedCourses.length === 0 || loadingBatchInsights}
              onClick={() => void handleLoadAllInsights()}
              title="Fetch CU Reviews & RateMyProfessors ratings and workload for all courses in this schedule"
              className="inline-flex items-center gap-1.5 rounded-xl border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-200 hover:border-sky-500/50 hover:text-sky-200 disabled:opacity-40"
            >
              {loadingBatchInsights ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin text-sky-400" />
              ) : (
                <Star className="h-3.5 w-3.5 text-amber-300" />
              )}
              {loadingBatchInsights ? "Loading Ratings..." : "Load Ratings"}
            </button>

            {schedules.length > 1 && (
              <button
                type="button"
                onClick={() => setShowDiffModal(true)}
                title="Compare active schedule against another saved plan"
                className="inline-flex items-center gap-1.5 rounded-xl border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-200 hover:bg-zinc-800"
              >
                <ArrowLeftRight className="h-3.5 w-3.5 text-sky-300" />
                Compare
              </button>
            )}

            <button
              type="button"
              disabled={!active || displayedCourses.length === 0}
              onClick={() =>
                active &&
                downloadSchedulePNG(active, displayedCourses, active.blocks)
              }
              title="Export calendar grid as a crisp PNG image"
              className="inline-flex items-center gap-1.5 rounded-xl border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-200 hover:bg-zinc-800 disabled:opacity-40"
            >
              <Image className="h-3.5 w-3.5" />
              PNG
            </button>

            <button
              type="button"
              disabled={!active || displayedCourses.length === 0}
              onClick={() =>
                active &&
                downloadScheduleICS(active.schedule.name, active.schedule.roster, displayedCourses)
              }
              className="inline-flex items-center gap-1.5 rounded-xl border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-200 hover:bg-zinc-800 disabled:opacity-40"
            >
              <Download className="h-3.5 w-3.5" />
              .ics
            </button>

            <button
              type="button"
              onClick={() => setShowSharePanel((v) => !v)}
              className={`inline-flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs font-medium ${
                active?.schedule.share_enabled
                  ? "border-sky-500/50 bg-sky-500/15 text-sky-200"
                  : "border-zinc-700 text-zinc-200 hover:bg-zinc-800"
              }`}
            >
              <Share2 className="h-3.5 w-3.5" />
              Share
            </button>
          </div>
        </div>

        {/* How Auto-Generate Works Info Bubble */}
        {showGeneratorHelp && (
          <div className="mt-3 rounded-xl border border-sky-500/35 bg-sky-500/10 p-3 text-xs text-zinc-200">
            <div className="flex items-start justify-between gap-2">
              <div className="space-y-1.5">
                <div className="flex items-center gap-1.5 font-bold text-sky-200">
                  <Sparkles className="h-3.5 w-3.5" />
                  How Auto-Generate Works
                </div>
                <p className="text-zinc-300">
                  Auto-Generate automatically tests every valid Lecture, Discussion, and Lab combination across the courses you&apos;ve added, avoiding conflicts and ranking the best options for you.
                </p>
                <ol className="list-inside list-decimal space-y-0.5 text-[11px] text-zinc-300">
                  <li>
                    <strong>Add your courses first</strong> using Quick-Add below or{" "}
                    <span className="font-semibold text-sky-200">+ Schedule</span> in Search (each course starts with a placeholder section until you generate or swap).
                  </li>
                  <li>
                    <strong>Optional constraints:</strong> Drag on the calendar to add{" "}
                    <strong>Busy Times</strong>, or click the <strong>Lock</strong> icon on any section you want to keep fixed.
                  </li>
                  <li>
                    <strong>Click Auto-Generate</strong> to flip through ranked conflict-free plans (Compact, Latest Start, Fewest Closed, etc.) and apply the one you like.
                  </li>
                </ol>
              </div>
              <button
                type="button"
                onClick={() => setShowGeneratorHelp(false)}
                className="rounded-lg p-1 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
                aria-label="Close help"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        )}

        {/* New Schedule Form */}
        {showNewForm && (
          <form
            onSubmit={handleCreateSchedule}
            className="mt-3 flex flex-wrap items-center gap-2 border-t border-zinc-800 pt-3"
          >
            <input
              type="text"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="Schedule name (e.g. Plan B - Late Start)"
              className="min-w-[220px] flex-1 rounded-xl border border-zinc-700 bg-zinc-950 px-3 py-1.5 text-xs text-white"
              autoFocus
            />
            <label className="flex items-center gap-1.5 text-xs text-zinc-300">
              <input
                type="checkbox"
                checked={duplicateCurrent}
                onChange={(e) => setDuplicateCurrent(e.target.checked)}
                className="rounded border-zinc-600 bg-zinc-900 text-emerald-500"
              />
              Duplicate current courses & blocks
            </label>
            <button
              type="submit"
              className="rounded-xl bg-emerald-500 px-3 py-1.5 text-xs font-bold text-zinc-950 hover:bg-emerald-400"
            >
              Create
            </button>
            <button
              type="button"
              onClick={() => setShowNewForm(false)}
              className="rounded-xl px-2.5 py-1.5 text-xs text-zinc-400 hover:text-zinc-200"
            >
              Cancel
            </button>
          </form>
        )}

        {/* Opt-In Share Link Panel */}
        {showSharePanel && active && (
          <div className="mt-3 space-y-2 rounded-xl border border-sky-500/30 bg-sky-500/5 p-3 text-xs">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <Link2 className="h-4 w-4 text-sky-300" />
                <span className="font-semibold text-white">Read-Only Share Link</span>
                <span className="text-zinc-400">
                  (Opt-in: disabled by default; viewers do not need an account)
                </span>
              </div>
              <label className="inline-flex cursor-pointer items-center gap-2">
                <input
                  type="checkbox"
                  checked={active.schedule.share_enabled}
                  onChange={(e) => void handleToggleShare(e.target.checked)}
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
                  onClick={() => {
                    navigator.clipboard?.writeText(active.schedule.share_url || "");
                    setCopiedShareUrl(true);
                    setTimeout(() => setCopiedShareUrl(false), 1500);
                  }}
                  className="inline-flex items-center gap-1 rounded-lg bg-sky-400 px-3 py-1.5 font-semibold text-zinc-950 hover:bg-sky-300"
                >
                  {copiedShareUrl ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                  {copiedShareUrl ? "Copied" : "Copy Link"}
                </button>
                <button
                  type="button"
                  onClick={handleRegenerateShare}
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
            {insightsSummary.avgRating != null && (
              <>
                <span className="text-zinc-500">&middot;</span>
                <span className="text-sky-300">
                  Avg CU Rating {insightsSummary.avgRating.toFixed(1)}
                  {insightsSummary.avgWorkload != null
                    ? ` · Workload ${insightsSummary.avgWorkload.toFixed(1)}/5`
                    : ""}
                </span>
              </>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {diagnostics.conflictCount > 0 ? (
              <span className="inline-flex items-center gap-1 rounded-lg border border-rose-500/40 bg-rose-500/15 px-2 py-0.5 font-semibold text-rose-200">
                <AlertTriangle className="h-3.5 w-3.5" />
                {diagnostics.conflictCount} Time Conflict
                {diagnostics.conflictCount === 1 ? "" : "s"}
              </span>
            ) : (
              displayedCourses.length > 0 && (
                <span className="inline-flex items-center gap-1 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-emerald-300">
                  <Check className="h-3 w-3" />
                  No Time Conflicts
                </span>
              )
            )}

            {diagnostics.walkWarnings.length > 0 && (
              <span
                title={diagnostics.walkWarnings
                  .map(
                    (w) =>
                      `${w.day}: ${w.fromCourse} (${w.fromBuilding}) → ${w.toCourse} (${w.toBuilding}): ~${w.walkMin}m walk for ${w.gapMin}m gap`
                  )
                  .join("\n")}
                className="inline-flex items-center gap-1 rounded-lg border border-amber-500/40 bg-amber-500/15 px-2 py-0.5 text-amber-200"
              >
                <Footprints className="h-3.5 w-3.5" />
                {diagnostics.walkWarnings.length} Tight Walk
                {diagnostics.walkWarnings.length === 1 ? "" : "s"}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Banners / Toasts */}
      {errorMsg && (
        <div className="rounded-xl border border-rose-500/40 bg-rose-500/15 px-3.5 py-2.5 text-xs text-rose-200">
          {errorMsg}
        </div>
      )}
      {statusToast && (
        <div className="rounded-xl border border-emerald-500/40 bg-emerald-500/15 px-3.5 py-2 text-xs font-medium text-emerald-200">
          {statusToast}
        </div>
      )}

      {/* Detailed Conflict / Walk / Forbidden Overlap Warnings */}
      {(diagnostics.conflictMessages.length > 0 ||
        diagnostics.walkWarnings.length > 0 ||
        diagnostics.academicWarnings.length > 0) && (
        <div className="space-y-1.5 rounded-2xl border border-amber-500/30 bg-amber-500/5 p-3 text-xs">
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

      {/* Auto-Schedule Generator Drawer */}
      {showGenerator && active && (
        <ScheduleGeneratorPanel
          courses={active.courses}
          blocks={active.blocks}
          onPreviewCandidate={setPreviewCandidate}
          onApplyCandidate={handleApplyGenerated}
          onClose={() => setShowGenerator(false)}
        />
      )}

      {/* Quick Course Add Bar */}
      <div className="relative rounded-2xl border border-zinc-800 bg-zinc-900/70 p-3">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative min-w-[220px] flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-500" />
            <input
              ref={quickInputRef}
              type="text"
              value={quickQuery}
              onChange={(e) => setQuickQuery(e.target.value)}
              placeholder={`Quick-add course to ${roster || "schedule"} (e.g. CS 2110, Algorithms, 6582)...`}
              className="w-full rounded-xl border border-zinc-800 bg-zinc-950 py-2 pl-9 pr-3 text-xs text-white placeholder-zinc-500 focus:border-emerald-500/60 focus:outline-none"
            />
            {quickLoading && (
              <Loader2 className="absolute right-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 animate-spin text-emerald-400" />
            )}
          </div>
          <button
            type="button"
            onClick={onJumpToSearch}
            className="rounded-xl border border-zinc-700 px-3 py-2 text-xs font-medium text-zinc-300 hover:border-emerald-500/50 hover:text-emerald-300"
          >
            Full Filter Search →
          </button>
        </div>

        {quickResults.length > 0 && (
          <div className="mt-2 max-h-64 divide-y divide-zinc-800/80 overflow-y-auto rounded-xl border border-zinc-800 bg-zinc-950">
            {quickResults.map((c) => {
              const key = `${c.subject}-${c.catalog_nbr}`;
              const alreadyAdded = active?.courses.some(
                (sc) => sc.subject === c.subject && sc.catalog_nbr === c.catalog_nbr
              );
              const openCount = c.sections.filter((s) => s.open_status === "O").length;
              return (
                <div
                  key={key}
                  className="flex items-center justify-between gap-3 px-3 py-2 text-xs hover:bg-zinc-900/80"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="font-bold text-white">
                        {c.subject} {c.catalog_nbr}
                      </span>
                      <span className="text-zinc-300">{c.title_long}</span>
                      <span className="text-[10px] text-zinc-500">
                        {openCount}/{c.sections.length} open
                      </span>
                    </div>
                  </div>
                  <button
                    type="button"
                    disabled={alreadyAdded || addingCourseKey === key}
                    onClick={() => handleAddCourse(c.subject, c.catalog_nbr)}
                    className={`shrink-0 rounded-lg px-2.5 py-1 text-[11px] font-semibold ${
                      alreadyAdded
                        ? "bg-zinc-800 text-zinc-400"
                        : "bg-emerald-500/20 text-emerald-300 ring-1 ring-emerald-500/40 hover:bg-emerald-500/30"
                    }`}
                  >
                    {alreadyAdded
                      ? "In Schedule"
                      : addingCourseKey === key
                        ? "Adding..."
                        : "+ Add"}
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Main Split View: Weekly Grid + Course Sidebar */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
        <div className="lg:col-span-8">
          <WeeklyCalendarGrid
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
            onToggleExpand={(itemId) =>
              setExpandedCourseId((cur) => (cur === itemId ? null : itemId))
            }
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
