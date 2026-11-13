import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  BellPlus,
  BookMarked,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  EyeOff,
  GraduationCap,
  ListChecks,
  Loader2,
  Lock,
  MapPin,
  Search,
} from "lucide-react";
import { api } from "../api/client";
import type {
  CatalogStatus,
  CatalogSubjectRefreshedSSE,
  CourseCSBadge,
  CourseInsights,
  CourseSection,
  CourseSummary,
  CSCurriculumMode,
  CSRequirementMode,
  Roster,
  SearchCoursesMeta,
  Subject,
  User,
} from "../types";
import { CompletedPrereqsModal } from "./CompletedPrereqsModal";
import { CourseInsightsPanel } from "./CourseInsightsPanel";
import { MultiSubjectSelect } from "./MultiSubjectSelect";
import { StatusBadge } from "./StatusBadge";
import {
  getSectionLocationTag,
  getSectionVirtualLabel,
  summarizeCourseLocation,
} from "../utils/location";

type StatusFilter = "all" | "open" | "closed" | "waitlist";

const CS_REQUIREMENT_MODES: Array<{ id: CSRequirementMode; label: string; hint: string }> = [
  { id: "", label: "All Courses", hint: "Full Cornell catalog" },
  { id: "cs_elective", label: "CS Electives", hint: "4000+ CS (≥3 cr, letter)" },
  { id: "tech_elective", label: "Technical Electives", hint: "3000+ w/ qualifying prereqs" },
  { id: "external_spec", label: "External Spec (3000+)", hint: "Non-CS topic area" },
];

function courseCacheKey(c: Pick<CourseSummary, "roster" | "subject" | "catalog_nbr">): string {
  return `${c.roster}-${c.subject}-${c.catalog_nbr}`;
}

function summarizeStatuses(sections: CourseSection[]): { open: number; closed: number; waitlist: number } {
  let open = 0;
  let closed = 0;
  let waitlist = 0;
  for (const s of sections) {
    const st = (s.open_status || "").toUpperCase();
    if (st === "O") open += 1;
    else if (st === "W") waitlist += 1;
    else if (st === "C") closed += 1;
  }
  return { open, closed, waitlist };
}

function formatCredits(min?: number, max?: number): string {
  if (!max && !min) return "";
  if (min != null && max != null && min !== max) {
    return `${Number(min.toFixed(2))}–${Number(max.toFixed(2))} cr`;
  }
  return `${Number((max || min || 0).toFixed(2))} cr`;
}

function formatBadgeTone(badge: CourseCSBadge): string {
  switch (badge.tone) {
    case "emerald":
      return "border-emerald-500/35 bg-emerald-500/15 text-emerald-300";
    case "sky":
      return "border-sky-500/35 bg-sky-500/15 text-sky-300";
    case "indigo":
      return "border-indigo-500/35 bg-indigo-500/15 text-indigo-300";
    case "amber":
      return "border-amber-500/40 bg-amber-500/15 text-amber-200";
    default:
      return "border-zinc-700 bg-zinc-800 text-zinc-300";
  }
}

interface Props {
  user: User;
  lastCatalogRefresh?: CatalogSubjectRefreshedSSE | null;
  onUserUpdated?: (user: User) => void;
  onWatchCreated: () => void;
}

interface WatchDraft {
  course: CourseSummary;
  section: CourseSection | null;
  mode: "exact" | "linked_group" | "any_section";
  componentFilter: string;
  triggerOn: "open" | "open_or_waitlist";
  autoPause: boolean;
  cooldownSec: number;
  priority: number;
}

interface SearchOverride {
  roster?: string;
  query?: string;
  subjects?: string[];
  levelMin?: number | null;
  csRequirement?: CSRequirementMode;
  include2000TE?: boolean;
  includeResearchTE?: boolean;
  curriculum?: CSCurriculumMode;
  onlyEligible?: boolean;
  ithacaOrVirtual?: boolean;
  showCsFeatures?: boolean;
  silent?: boolean;
}

export function CourseSearch({ user, lastCatalogRefresh, onUserUpdated, onWatchCreated }: Props) {
  const [rosters, setRosters] = useState<Roster[]>([]);
  const [selectedRoster, setSelectedRoster] = useState("");
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [selectedSubjects, setSelectedSubjects] = useState<string[]>([]);
  const [query, setQuery] = useState("");

  // CS Major Requirement Filters
  const [showCsFeatures, setShowCsFeatures] = useState<boolean>(user.show_cs_features ?? true);
  const [csRequirement, setCsRequirement] = useState<CSRequirementMode>("");
  const [levelMin, setLevelMin] = useState<number | null>(null);
  const [curriculum, setCurriculum] = useState<CSCurriculumMode>("current");
  const [include2000TE, setInclude2000TE] = useState(true);
  const [includeResearchTE, setIncludeResearchTE] = useState(true);
  const [onlyEligible, setOnlyEligible] = useState(false);
  const [ithacaOrVirtual, setIthacaOrVirtual] = useState(true);
  const [prereqsModalOpen, setPrereqsModalOpen] = useState(false);

  const [courses, setCourses] = useState<CourseSummary[]>([]);
  const [searchMeta, setSearchMeta] = useState<SearchCoursesMeta | null>(null);
  const [catalogStatus, setCatalogStatus] = useState<CatalogStatus | null>(null);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [insightsMap, setInsightsMap] = useState<Record<string, CourseInsights>>({});
  const [insightsLoading, setInsightsLoading] = useState<Record<string, boolean>>({});
  const [insightsError, setInsightsError] = useState<Record<string, string>>({});
  const [draft, setDraft] = useState<WatchDraft | null>(null);
  const [saving, setSaving] = useState(false);
  const [successMsg, setSuccessMsg] = useState("");

  // Track subjects that had 0 cached rows when searched so silent SSE re-search pops them in cleanly
  const uncachedRequestedRef = useRef<Set<string>>(new Set());
  const hasSearchedRef = useRef(false);
  const lastProcessedRefreshRef = useRef<CatalogSubjectRefreshedSSE | null>(null);

  useEffect(() => {
    setShowCsFeatures(user.show_cs_features ?? true);
    if (user.show_cs_features === false) {
      setCsRequirement("");
    }
  }, [user.show_cs_features]);

  useEffect(() => {
    api
      .listRosters()
      .then((res) => {
        setRosters(res.rosters);
        const def = res.rosters.find((r) => r.is_default === 1) || res.rosters[0];
        if (def) setSelectedRoster(def.slug);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load rosters"));
  }, []);

  useEffect(() => {
    if (!selectedRoster) return;
    api
      .listSubjects(selectedRoster)
      .then((res) => setSubjects(res.subjects))
      .catch(() => {});
    api
      .getCatalogStatus(selectedRoster)
      .then((st) => setCatalogStatus(st))
      .catch(() => {});
  }, [selectedRoster]);

  const loadInsights = useCallback(
    async (course: CourseSummary, refresh = false) => {
      const key = courseCacheKey(course);
      if (!refresh && (insightsMap[key] || insightsLoading[key])) return;
      setInsightsLoading((p) => ({ ...p, [key]: true }));
      setInsightsError((p) => ({ ...p, [key]: "" }));
      try {
        const data = await api.getCourseInsights(course.roster, course.subject, course.catalog_nbr, refresh);
        setInsightsMap((p) => ({ ...p, [key]: data }));
      } catch (err) {
        setInsightsError((p) => ({
          ...p,
          [key]: err instanceof Error ? err.message : "Failed to load course reviews",
        }));
      } finally {
        setInsightsLoading((p) => ({ ...p, [key]: false }));
      }
    },
    [insightsMap, insightsLoading]
  );

  const executeSearch = useCallback(
    async (override?: SearchOverride) => {
      const r = override?.roster ?? selectedRoster;
      if (!r) return;
      const q = override?.query ?? query;
      const subjs = override?.subjects ?? selectedSubjects;
      const csEnabled = override?.showCsFeatures ?? showCsFeatures;
      const req = csEnabled ? (override?.csRequirement ?? csRequirement) : "";
      const lvl = override?.levelMin !== undefined ? override.levelMin : levelMin;
      const inc2000 = override?.include2000TE ?? include2000TE;
      const incRes = override?.includeResearchTE ?? includeResearchTE;
      const curr = override?.curriculum ?? curriculum;
      const eligibleOnly = override?.onlyEligible ?? onlyEligible;
      const ithVirt = override?.ithacaOrVirtual ?? ithacaOrVirtual;
      const silent = Boolean(override?.silent);

      if (!q.trim() && subjs.length === 0 && !req && !lvl && !eligibleOnly) {
        if (!silent) {
          setError(
            csEnabled
              ? "Enter a course code, keyword, class #, pick subjects, or select a CS requirement filter."
              : "Enter a course code, keyword, class #, or pick one or more subjects."
          );
        }
        return;
      }

      hasSearchedRef.current = true;
      if (!silent) {
        setError("");
        setLoading(true);
      }

      try {
        const res = await api.searchCourses(r, q, {
          subjects: subjs,
          level_min: lvl,
          cs_requirement: req,
          include_2000_te: inc2000,
          include_research_te: incRes,
          curriculum: curr,
          only_eligible: eligibleOnly,
          ithaca_or_virtual: ithVirt,
          refresh_stale: true,
          limit: req ? 150 : 100,
        });
        setCourses(res.courses);
        if (res.meta) {
          setSearchMeta(res.meta);
        }
        if (!silent) {
          setStatusFilter("all");
          if (res.courses.length > 0 && res.courses.length <= 5) {
            const autoExp: Record<string, boolean> = {};
            res.courses.forEach((c) => {
              autoExp[courseCacheKey(c)] = true;
              void loadInsights(c);
            });
            setExpanded(autoExp);
          } else {
            setExpanded({});
          }
        }

        // Track any queued/requested subjects that currently have 0 visible rows
        const visibleSubjSet = new Set(res.courses.map((c) => c.subject.toUpperCase()));
        const pendingMissing = new Set<string>();
        for (const s of res.meta?.queued_subjects || []) {
          if (!visibleSubjSet.has(s.toUpperCase())) {
            pendingMissing.add(s.toUpperCase());
          }
        }
        if (csEnabled && req === "tech_elective" && subjs.length === 0 && (res.meta?.stem_synced ?? 0) < (res.meta?.stem_total ?? 0)) {
          pendingMissing.add("__STEM_WARMUP__");
        }
        uncachedRequestedRef.current = pendingMissing;
      } catch (err) {
        if (!silent) {
          setError(err instanceof Error ? err.message : "Search failed");
        }
      } finally {
        if (!silent) {
          setLoading(false);
        }
      }
    },
    [selectedRoster, query, selectedSubjects, showCsFeatures, csRequirement, levelMin, include2000TE, includeResearchTE, curriculum, onlyEligible, ithacaOrVirtual, loadInsights]
  );

  // Live SSE handler: flip "Loading live status..." -> Open/Waitlist/Closed smoothly in real time
  useEffect(() => {
    if (!lastCatalogRefresh || !selectedRoster) return;
    if (lastCatalogRefresh === lastProcessedRefreshRef.current) return;
    if (lastCatalogRefresh.roster.toUpperCase() !== selectedRoster.toUpperCase()) return;
    lastProcessedRefreshRef.current = lastCatalogRefresh;

    const refreshedSubj = lastCatalogRefresh.subject.toUpperCase();

    setSubjects((prev) =>
      prev.map((s) =>
        s.value.toUpperCase() === refreshedSubj ? { ...s, synced_at: lastCatalogRefresh.synced_at } : s
      )
    );

    if (lastCatalogRefresh.coverage) {
      const cov = lastCatalogRefresh.coverage;
      setCatalogStatus((prev) => ({
        roster: lastCatalogRefresh.roster,
        synced_subjects: cov.synced_subjects,
        total_subjects: cov.total_subjects,
        stem_synced: cov.stem_synced,
        stem_total: cov.stem_total,
        warmup_active: prev?.warmup_active ?? false,
        refreshing_subjects: (prev?.refreshing_subjects || []).filter((s) => s !== refreshedSubj),
      }));
      setSearchMeta((prev) =>
        prev
          ? {
              ...prev,
              synced_subjects: cov.synced_subjects,
              total_subjects: cov.total_subjects,
              stem_synced: cov.stem_synced,
              stem_total: cov.stem_total,
              refreshing_subjects: prev.refreshing_subjects.filter((s) => s !== refreshedSubj),
              queued_subjects: prev.queued_subjects.filter((s) => s !== refreshedSubj),
            }
          : prev
      );
    }

    setCourses((prevCourses) => {
      let touched = false;
      const next = prevCourses.map((c) => {
        if (c.subject.toUpperCase() !== refreshedSubj) return c;
        touched = true;
        return {
          ...c,
          status_is_stale: false,
          subject_synced_at: lastCatalogRefresh.synced_at,
          sections: c.sections.map((sec) => {
            const liveStatus = lastCatalogRefresh.section_statuses[String(sec.class_nbr)];
            return liveStatus ? { ...sec, open_status: liveStatus } : sec;
          }),
        };
      });
      return touched ? next : prevCourses;
    });

    if (
      hasSearchedRef.current &&
      lastCatalogRefresh.courses_count > 0 &&
      (uncachedRequestedRef.current.has(refreshedSubj) || uncachedRequestedRef.current.has("__STEM_WARMUP__"))
    ) {
      uncachedRequestedRef.current.delete(refreshedSubj);
      void executeSearch({ silent: true });
    }
  }, [lastCatalogRefresh, selectedRoster, executeSearch]);

  const filterCounts = useMemo(() => {
    let open = 0;
    let closed = 0;
    let waitlist = 0;
    let pending = 0;
    for (const c of courses) {
      if (c.status_is_stale) {
        pending += 1;
        continue;
      }
      const s = summarizeStatuses(c.sections);
      if (s.open > 0) open += 1;
      if (s.closed > 0) closed += 1;
      if (s.waitlist > 0) waitlist += 1;
    }
    return { all: courses.length, open, closed, waitlist, pending };
  }, [courses]);

  const filteredCourses = useMemo(() => {
    if (statusFilter === "all") return courses;
    // Keep stale/loading courses visible with a pending badge until live SSE check resolves
    return courses.filter(
      (c) => c.status_is_stale || summarizeStatuses(c.sections)[statusFilter] > 0
    );
  }, [courses, statusFilter]);

  function handleModeSelect(nextMode: CSRequirementMode) {
    setError("");
    setCsRequirement(nextMode);
    let nextSubjs = selectedSubjects;
    let nextLevel = levelMin;

    if (nextMode === "external_spec") {
      nextSubjs = selectedSubjects.filter((s) => s !== "CS" && s !== "PE");
      if (!nextLevel || nextLevel < 3000) nextLevel = 3000;
    } else if (nextMode === "cs_elective") {
      nextSubjs = [];
      nextLevel = null;
    } else if (nextMode === "tech_elective") {
      if (nextLevel === 3000) nextLevel = null;
    } else {
      nextLevel = null;
    }

    setSelectedSubjects(nextSubjs);
    setLevelMin(nextLevel);
    if (nextMode !== "" || query.trim() || nextSubjs.length > 0 || onlyEligible) {
      void executeSearch({
        csRequirement: nextMode,
        subjects: nextSubjs,
        levelMin: nextLevel,
      });
    }
  }

  function handleToggleCsFeatures(nextShow: boolean) {
    setError("");
    setShowCsFeatures(nextShow);
    onUserUpdated?.({ ...user, show_cs_features: nextShow });

    if (!nextShow) {
      const wasCsMode = csRequirement !== "";
      const nextLevel = csRequirement === "external_spec" && levelMin === 3000 ? null : levelMin;
      if (wasCsMode) {
        setCsRequirement("");
        if (nextLevel !== levelMin) setLevelMin(nextLevel);
        if (query.trim() || selectedSubjects.length > 0 || nextLevel || onlyEligible) {
          void executeSearch({
            showCsFeatures: false,
            csRequirement: "",
            subjects: selectedSubjects,
            levelMin: nextLevel,
          });
        } else {
          setCourses([]);
          setSearchMeta(null);
          hasSearchedRef.current = false;
        }
      }
    }

    api
      .updateUserPreferences({ show_cs_features: nextShow })
      .then((res) => {
        onUserUpdated?.(res.user);
      })
      .catch((err) => {
        setShowCsFeatures(!nextShow);
        onUserUpdated?.({ ...user, show_cs_features: !nextShow });
        setError(err instanceof Error ? err.message : "Failed to save preference");
      });
  }

  function toggleCourse(course: CourseSummary) {
    const key = courseCacheKey(course);
    const nextOpen = !expanded[key];
    setExpanded((p) => ({ ...p, [key]: nextOpen }));
    if (nextOpen) {
      void loadInsights(course);
    }
  }

  function runSearchForm(e: React.FormEvent) {
    e.preventDefault();
    void executeSearch();
  }

  function openSectionDraft(course: CourseSummary, section: CourseSection) {
    const hasLinkedComp = section.components_required.length > 1;
    setDraft({
      course,
      section,
      mode: hasLinkedComp ? "linked_group" : "exact",
      componentFilter: "",
      triggerOn: "open",
      autoPause: false,
      cooldownSec: 60,
      priority: user.role === "admin" ? 2 : 1,
    });
  }

  function openCourseDraft(course: CourseSummary) {
    setDraft({
      course,
      section: null,
      mode: "any_section",
      componentFilter: "",
      triggerOn: "open",
      autoPause: false,
      cooldownSec: 60,
      priority: user.role === "admin" ? 2 : 1,
    });
  }

  async function submitWatch(e: React.FormEvent) {
    e.preventDefault();
    if (!draft) return;
    setSaving(true);
    setError("");
    try {
      await api.createWatch({
        roster: draft.course.roster,
        subject: draft.course.subject,
        catalog_nbr: draft.course.catalog_nbr,
        class_nbr: draft.section ? draft.section.class_nbr : null,
        enroll_group_idx: draft.section ? draft.section.enroll_group_idx : null,
        component_filter: draft.mode === "any_section" && draft.componentFilter ? draft.componentFilter : null,
        mode: draft.mode,
        trigger_on: draft.triggerOn,
        priority: draft.priority,
        auto_pause: draft.autoPause,
        cooldown_sec: draft.cooldownSec,
        ithaca_or_virtual: draft.mode === "any_section" ? ithacaOrVirtual : false,
      });
      setSuccessMsg(
        `Armed watch for ${draft.course.subject} ${draft.course.catalog_nbr}${
          draft.section ? ` #${draft.section.class_nbr}` : " (any section)"
        }`
      );
      setDraft(null);
      onWatchCreated();
      setTimeout(() => setSuccessMsg(""), 3500);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create watch");
    } finally {
      setSaving(false);
    }
  }

  const syncedSubjectsCount = searchMeta?.synced_subjects ?? catalogStatus?.synced_subjects ?? 0;
  const totalSubjectsCount = searchMeta?.total_subjects ?? catalogStatus?.total_subjects ?? 0;
  const stemSyncedCount = searchMeta?.stem_synced ?? catalogStatus?.stem_synced ?? 0;
  const stemTotalCount = searchMeta?.stem_total ?? catalogStatus?.stem_total ?? 0;
  const staleVisibleCount = useMemo(
    () => courses.filter((c) => c.status_is_stale).length,
    [courses]
  );

  return (
    <div className="space-y-4">
      <form onSubmit={runSearchForm} className="space-y-3 rounded-2xl border border-zinc-800 bg-zinc-900/80 p-4">
        {/* CS Major Requirement Segmented Bar + Toggle */}
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-zinc-800/80 pb-3">
          {showCsFeatures ? (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="mr-1 inline-flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wide text-zinc-400">
                <GraduationCap className="h-3.5 w-3.5 text-emerald-400" />
                CS Major:
              </span>
              {CS_REQUIREMENT_MODES.map((m) => {
                const active = csRequirement === m.id;
                return (
                  <button
                    key={m.id || "all"}
                    type="button"
                    title={m.hint}
                    onClick={() => handleModeSelect(m.id)}
                    className={`rounded-xl px-3 py-1.5 text-xs font-semibold transition ${
                      active
                        ? "bg-emerald-500 text-zinc-950 shadow-sm"
                        : "border border-zinc-700/80 bg-zinc-950 text-zinc-300 hover:border-emerald-500/40 hover:text-white"
                    }`}
                  >
                    {m.label}
                  </button>
                );
              })}
            </div>
          ) : (
            <div className="text-xs font-medium text-zinc-300">Search Cornell Classes</div>
          )}

          <div className="flex flex-wrap items-center gap-2.5 text-[11px] text-zinc-400">
            {totalSubjectsCount > 0 && (
              <span>
                Cached: <strong className="text-zinc-200">{syncedSubjectsCount}</strong>/{totalSubjectsCount} subj
                {showCsFeatures && stemTotalCount > 0 && ` (STEM ${stemSyncedCount}/${stemTotalCount})`}
              </span>
            )}
            <button
              type="button"
              onClick={() => handleToggleCsFeatures(!showCsFeatures)}
              title={
                showCsFeatures
                  ? "Hide CS Electives, Technical Electives, External Spec filters, and CS degree badges"
                  : "Show CS Major requirement filters and degree badges"
              }
              className={`inline-flex items-center gap-1.5 rounded-lg border px-2 py-1 text-[11px] font-medium transition ${
                showCsFeatures
                  ? "border-zinc-700/80 bg-zinc-950 text-zinc-300 hover:border-zinc-500 hover:text-white"
                  : "border-zinc-700/80 bg-zinc-950 text-zinc-400 hover:border-emerald-500/40 hover:text-emerald-300"
              }`}
            >
              {showCsFeatures ? (
                <>
                  <EyeOff className="h-3 w-3 text-zinc-400" />
                  Hide CS Major
                </>
              ) : (
                <>
                  <GraduationCap className="h-3 w-3 text-emerald-400" />
                  Show CS Major
                </>
              )}
            </button>
          </div>
        </div>

        {/* Main Search Grid */}
        <div className="grid gap-3 sm:grid-cols-12">
          <div className="sm:col-span-3">
            <label className="mb-1 block text-xs font-medium text-zinc-400">Semester</label>
            <select
              value={selectedRoster}
              onChange={(e) => setSelectedRoster(e.target.value)}
              className="w-full rounded-xl border border-zinc-700 bg-zinc-950 px-3 py-2.5 text-sm text-white focus:border-emerald-500 focus:outline-none"
            >
              {rosters.map((r) => (
                <option key={r.slug} value={r.slug}>
                  {r.descr} ({r.slug})
                </option>
              ))}
            </select>
          </div>

          <div className="sm:col-span-4">
            <label className="mb-1 block text-xs font-medium text-zinc-400">
              {csRequirement === "external_spec"
                ? "Subjects (Multi-select External Area)"
                : "Subjects (Multi-select optional)"}
            </label>
            <MultiSubjectSelect
              subjects={subjects}
              selected={selectedSubjects}
              excludeSubjects={csRequirement === "external_spec" ? ["CS", "PE"] : []}
              placeholder={
                csRequirement === "cs_elective"
                  ? "CS (Computer Science)"
                  : csRequirement === "external_spec"
                    ? "Pick 1+ subjects (non-CS)..."
                    : "All Subjects / Pick Multi"
              }
              onChange={(nextSubjs) => {
                setSelectedSubjects(nextSubjs);
                if (nextSubjs.length > 0 || csRequirement !== "" || query.trim()) {
                  void executeSearch({ subjects: nextSubjs });
                }
              }}
            />
          </div>

          <div className="sm:col-span-5">
            <label className="mb-1 block text-xs font-medium text-zinc-400">
              Course, Keyword, Instructor, or Class #
            </label>
            <div className="flex gap-2">
              <div className="relative flex-1">
                <Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-zinc-500" />
                <input
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="e.g. cs2110, Machine Learning, Bracy"
                  className="w-full rounded-xl border border-zinc-700 bg-zinc-950 py-2.5 pl-9 pr-3 text-sm text-white placeholder-zinc-500 focus:border-emerald-500 focus:outline-none"
                />
              </div>
              <button
                type="submit"
                disabled={loading}
                className="inline-flex items-center gap-1.5 rounded-xl bg-emerald-500 px-4 py-2.5 text-sm font-semibold text-zinc-950 hover:bg-emerald-400 disabled:opacity-50"
              >
                {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Search"}
              </button>
            </div>
          </div>
        </div>

        {/* Sub-Controls Row (Level, Curriculum Rule Toggle, TE Exception Warnings) */}
        <div className="flex flex-wrap items-center justify-between gap-3 pt-1 text-xs">
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-1.5">
              <span className="text-zinc-400">Level:</span>
              <select
                value={levelMin ?? ""}
                onChange={(e) => {
                  const val = e.target.value ? Number(e.target.value) : null;
                  setLevelMin(val);
                  if (val || csRequirement || selectedSubjects.length > 0 || query.trim()) {
                    void executeSearch({ levelMin: val });
                  }
                }}
                className="rounded-lg border border-zinc-700 bg-zinc-950 px-2.5 py-1 text-xs text-white focus:border-emerald-500 focus:outline-none"
              >
                {csRequirement !== "external_spec" && <option value="">Any Level</option>}
                {csRequirement !== "external_spec" && <option value="2000">2000+</option>}
                <option value="3000">3000+</option>
                <option value="4000">4000+</option>
                <option value="5000">5000+</option>
              </select>
            </div>

            {showCsFeatures && csRequirement === "cs_elective" && (
              <div className="flex items-center gap-1 rounded-lg border border-zinc-800 bg-zinc-950 p-0.5">
                <button
                  type="button"
                  onClick={() => {
                    setCurriculum("current");
                    void executeSearch({ curriculum: "current" });
                  }}
                  className={`rounded-md px-2 py-1 text-[11px] font-medium transition ${
                    curriculum === "current"
                      ? "bg-emerald-500/20 text-emerald-300"
                      : "text-zinc-400 hover:text-white"
                  }`}
                >
                  Post-Fall 2024
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setCurriculum("pre2024");
                    void executeSearch({ curriculum: "pre2024" });
                  }}
                  className={`rounded-md px-2 py-1 text-[11px] font-medium transition ${
                    curriculum === "pre2024"
                      ? "bg-emerald-500/20 text-emerald-300"
                      : "text-zinc-400 hover:text-white"
                  }`}
                >
                  Pre-Fall 2024
                </button>
              </div>
            )}

            {showCsFeatures && csRequirement === "tech_elective" && (
              <div className="flex flex-wrap items-center gap-3">
                <label className="inline-flex cursor-pointer items-center gap-1.5 text-zinc-300">
                  <input
                    type="checkbox"
                    checked={include2000TE}
                    onChange={(e) => {
                      const nextVal = e.target.checked;
                      setInclude2000TE(nextVal);
                      void executeSearch({ include2000TE: nextVal });
                    }}
                    className="accent-amber-400"
                  />
                  <span>Show 2000+ (max 1 warning)</span>
                </label>
                <label className="inline-flex cursor-pointer items-center gap-1.5 text-zinc-300">
                  <input
                    type="checkbox"
                    checked={includeResearchTE}
                    onChange={(e) => {
                      const nextVal = e.target.checked;
                      setIncludeResearchTE(nextVal);
                      void executeSearch({ includeResearchTE: nextVal });
                    }}
                    className="accent-amber-400"
                  />
                  <span>Show CS 4999 Research (warning)</span>
                </label>
              </div>
            )}

            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => setPrereqsModalOpen(true)}
                className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs font-medium transition ${
                  (user.completed_courses?.length ?? 0) > 0
                    ? "border-sky-500/40 bg-sky-500/15 text-sky-200 hover:bg-sky-500/25"
                    : "border-zinc-700 bg-zinc-950 text-zinc-300 hover:border-emerald-500/40 hover:text-white"
                }`}
              >
                <ListChecks className="h-3.5 w-3.5 text-emerald-400" />
                My Prereqs ({user.completed_courses?.length ?? 0})
              </button>

              <label
                className={`inline-flex cursor-pointer items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs font-medium transition ${
                  onlyEligible
                    ? "border-emerald-500/50 bg-emerald-500/15 text-emerald-200"
                    : "border-zinc-700/80 bg-zinc-950 text-zinc-300 hover:border-zinc-600"
                }`}
                title={
                  (user.completed_courses?.length ?? 0) === 0
                    ? "Add your completed courses via My Prereqs to check eligibility"
                    : "Only show classes whose required prerequisites you have satisfied"
                }
              >
                <input
                  type="checkbox"
                  checked={onlyEligible}
                  onChange={(e) => {
                    const nextVal = e.target.checked;
                    setOnlyEligible(nextVal);
                    if (nextVal || csRequirement || selectedSubjects.length > 0 || query.trim() || levelMin) {
                      void executeSearch({ onlyEligible: nextVal });
                    }
                  }}
                  className="accent-emerald-500"
                />
                <span>Only prereqs met</span>
              </label>

              <button
                type="button"
                onClick={() => {
                  const nextVal = !ithacaOrVirtual;
                  setIthacaOrVirtual(nextVal);
                  if (
                    hasSearchedRef.current ||
                    csRequirement ||
                    selectedSubjects.length > 0 ||
                    query.trim() ||
                    levelMin ||
                    onlyEligible
                  ) {
                    void executeSearch({ ithacaOrVirtual: nextVal });
                  }
                }}
                aria-pressed={ithacaOrVirtual}
                className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs font-medium transition ${
                  ithacaOrVirtual
                    ? "border-emerald-500/50 bg-emerald-500/15 text-emerald-200 hover:bg-emerald-500/25"
                    : "border-amber-500/40 bg-amber-500/15 text-amber-200 hover:bg-amber-500/25"
                }`}
                title="Hide Cornell Tech (NYC) and other off-campus courses/sections; keep Ithaca campus and purely virtual (OL, DL-AD, DL-SD) offerings."
              >
                <MapPin className={`h-3.5 w-3.5 ${ithacaOrVirtual ? "text-emerald-400" : "text-amber-300"}`} />
                <span>{ithacaOrVirtual ? "Ithaca + Virtual Only" : "All Locations (incl. Cornell Tech)"}</span>
              </button>
            </div>
          </div>

          {showCsFeatures && (
            <div className="text-[11px] text-zinc-500">
              Official rules:{" "}
              <a
                href="https://catalog.cornell.edu/programs/computer-science-bs/"
                target="_blank"
                rel="noreferrer"
                className="text-emerald-400/90 hover:underline"
              >
                B.S.
              </a>{" "}
              /{" "}
              <a
                href="https://catalog.cornell.edu/programs/computer-science-ba/"
                target="_blank"
                rel="noreferrer"
                className="text-emerald-400/90 hover:underline"
              >
                B.A.
              </a>
            </div>
          )}
        </div>
      </form>

      {successMsg && (
        <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/15 px-4 py-3 text-sm text-emerald-200">
          {successMsg}
        </div>
      )}
      {error && (
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-300">
          {error}
        </div>
      )}

      {onlyEligible && (user.completed_courses?.length ?? 0) === 0 && courses.length > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-sky-500/30 bg-sky-500/10 px-4 py-2.5 text-xs text-sky-200">
          <span>
            No completed courses saved yet — showing only classes with no explicit required prerequisites.
          </span>
          <button
            type="button"
            onClick={() => setPrereqsModalOpen(true)}
            className="rounded-lg border border-sky-400/40 bg-sky-500/20 px-2.5 py-1 text-[11px] font-semibold text-white hover:bg-sky-500/30"
          >
            Select My Prereqs
          </button>
        </div>
      )}

      {!loading && courses.length === 0 && ithacaOrVirtual && (searchMeta?.filtered_out_location_count ?? 0) > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
          <div className="flex items-center gap-2">
            <MapPin className="h-4 w-4 shrink-0 text-amber-300" />
            <span>
              {searchMeta!.filtered_out_location_count} matching course
              {searchMeta!.filtered_out_location_count === 1 ? " was" : "s were"} hidden because{" "}
              {searchMeta!.filtered_out_location_count === 1 ? "it is" : "they are"} only offered at{" "}
              <span className="font-semibold text-white">
                {(searchMeta?.filtered_out_locations || []).join(", ") || "an off-campus location"}
              </span>{" "}
              (not Ithaca or purely virtual).
            </span>
          </div>
          <button
            type="button"
            onClick={() => {
              setIthacaOrVirtual(false);
              void executeSearch({ ithacaOrVirtual: false });
            }}
            className="rounded-lg border border-amber-400/40 bg-amber-500/20 px-3 py-1.5 text-xs font-semibold text-white hover:bg-amber-500/30"
          >
            Show All Locations
          </button>
        </div>
      )}

      {courses.length > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-zinc-800 bg-zinc-900/50 px-4 py-2.5">
          <div className="flex flex-wrap items-center gap-1.5">
            {(
              [
                { id: "all", label: "All", count: filterCounts.all },
                { id: "open", label: "Has Open", count: filterCounts.open },
                { id: "waitlist", label: "Has Waitlist", count: filterCounts.waitlist },
                { id: "closed", label: "Has Closed", count: filterCounts.closed },
              ] as const
            ).map((opt) => {
              const active = statusFilter === opt.id;
              return (
                <button
                  key={opt.id}
                  type="button"
                  onClick={() => setStatusFilter(opt.id)}
                  className={`rounded-lg px-2.5 py-1 text-xs font-medium transition-colors ${
                    active
                      ? "bg-emerald-500/20 text-emerald-300 ring-1 ring-emerald-500/40"
                      : "text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
                  }`}
                >
                  {opt.label} ({opt.count})
                </button>
              );
            })}
            {filterCounts.pending > 0 && statusFilter !== "all" && (
              <span className="ml-1 inline-flex items-center gap-1 rounded-md bg-amber-500/10 px-2 py-0.5 text-[11px] text-amber-200">
                <Loader2 className="h-3 w-3 animate-spin" />
                +{filterCounts.pending} loading live check
              </span>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-3 text-xs text-zinc-500">
            {ithacaOrVirtual && (searchMeta?.filtered_out_location_count ?? 0) > 0 && (
              <button
                type="button"
                onClick={() => {
                  setIthacaOrVirtual(false);
                  void executeSearch({ ithacaOrVirtual: false });
                }}
                className="inline-flex items-center gap-1 rounded-md border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-[11px] font-medium text-amber-200 hover:bg-amber-500/20"
                title={`Hidden off-campus courses (${(searchMeta?.filtered_out_locations || []).join(", ")})`}
              >
                <MapPin className="h-3 w-3 text-amber-300" />
                {searchMeta?.filtered_out_location_count} off-campus hidden
                {(searchMeta?.filtered_out_locations?.length ?? 0) > 0
                  ? ` (${searchMeta!.filtered_out_locations!.slice(0, 2).join(", ")})`
                  : ""}
                {" · Show all"}
              </button>
            )}
            {staleVisibleCount > 0 && (
              <span className="inline-flex items-center gap-1.5 text-amber-300">
                <Loader2 className="h-3 w-3 animate-spin" />
                Updating live status in background ({staleVisibleCount})...
              </span>
            )}
            <span>
              Showing {filteredCourses.length} of {searchMeta?.total_matched ?? courses.length} course
              {(searchMeta?.total_matched ?? courses.length) === 1 ? "" : "s"}
            </span>
          </div>
        </div>
      )}

      <div className="space-y-3">
        {filteredCourses.map((course) => {
          const cacheKey = courseCacheKey(course);
          const isOpen = Boolean(expanded[cacheKey]);
          const statusSummary = summarizeStatuses(course.sections);
          const groups = new Map<number, CourseSection[]>();
          for (const sec of course.sections) {
            const arr = groups.get(sec.enroll_group_idx) || [];
            arr.push(sec);
            groups.set(sec.enroll_group_idx, arr);
          }

          const elig = course.cs_eligibility;
          const locSummary = summarizeCourseLocation(course.sections);
          const creditsLabel = formatCredits(course.units_min, course.units_max);
          const collegeMeta = [course.acad_career, course.acad_group].filter(Boolean).join(" · ");
          const activeWarning = !showCsFeatures
            ? ""
            : csRequirement === "cs_elective"
              ? elig?.cs_elective_warning
              : csRequirement === "tech_elective"
                ? elig?.tech_elective_warning
                : csRequirement === "external_spec"
                  ? elig?.external_spec_warning
                  : elig?.cs_elective_warning || elig?.tech_elective_warning || elig?.external_spec_warning;

          return (
            <div key={cacheKey} className="rounded-2xl border border-zinc-800 bg-zinc-900/75">
              <div className="flex flex-wrap items-center justify-between gap-3 p-4">
                <button
                  type="button"
                  onClick={() => toggleCourse(course)}
                  className="flex min-w-0 flex-1 items-start gap-3 text-left"
                >
                  <div className="mt-0.5 text-zinc-400">
                    {isOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                  </div>
                  <div className="min-w-0 space-y-1">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="mr-0.5 text-base font-bold text-white">
                        {course.subject} {course.catalog_nbr}
                      </span>
                      {creditsLabel && (
                        <span className="rounded-md border border-zinc-700/80 bg-zinc-950 px-1.5 py-0.5 text-[11px] font-medium text-zinc-300">
                          {creditsLabel}
                        </span>
                      )}
                      {collegeMeta && (
                        <span className="rounded-md bg-zinc-800 px-1.5 py-0.5 text-[10px] font-medium text-zinc-400">
                          {collegeMeta}
                        </span>
                      )}
                      <span className="text-xs text-zinc-500">
                        {course.sections.length} sec{course.sections.length === 1 ? "" : "s"}
                      </span>

                      {course.status_is_stale ? (
                        <span className="inline-flex items-center gap-1 rounded-md border border-zinc-700 bg-zinc-800/80 px-2 py-0.5 text-[11px] font-medium text-zinc-300">
                          <Loader2 className="h-3 w-3 animate-spin text-emerald-400" />
                          Loading live status...
                        </span>
                      ) : (
                        <>
                          {statusSummary.open > 0 && (
                            <span className="rounded-md bg-emerald-500/15 px-1.5 py-0.5 text-[11px] font-medium text-emerald-300">
                              {statusSummary.open} Open
                            </span>
                          )}
                          {statusSummary.waitlist > 0 && (
                            <span className="rounded-md bg-amber-500/15 px-1.5 py-0.5 text-[11px] font-medium text-amber-300">
                              {statusSummary.waitlist} Waitlist
                            </span>
                          )}
                          {statusSummary.closed > 0 && (
                            <span className="rounded-md bg-rose-500/15 px-1.5 py-0.5 text-[11px] font-medium text-rose-300">
                              {statusSummary.closed} Closed
                            </span>
                          )}
                        </>
                      )}

                      {locSummary.offCampusLabels.map((locLabel) => (
                        <span
                          key={locLabel}
                          className="inline-flex items-center gap-1 rounded-md border border-amber-500/40 bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-amber-200"
                          title={`Offered at off-campus location: ${locLabel}`}
                        >
                          <MapPin className="h-2.5 w-2.5 text-amber-300" />
                          {locLabel}
                        </span>
                      ))}
                      {locSummary.allVirtual && (
                        <span className="rounded-md border border-cyan-500/35 bg-cyan-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-cyan-200">
                          Virtual
                        </span>
                      )}
                      {!locSummary.allVirtual && locSummary.someVirtual && (
                        <span className="rounded-md border border-cyan-500/30 bg-cyan-500/10 px-1.5 py-0.5 text-[10px] font-medium text-cyan-300">
                          Virtual avail.
                        </span>
                      )}
                      {(course.hidden_other_location_count ?? 0) > 0 && (
                        <span
                          className="inline-flex items-center gap-1 rounded-md border border-zinc-700 bg-zinc-800/80 px-1.5 py-0.5 text-[10px] text-zinc-400"
                          title={`Hidden section(s) at ${(course.hidden_other_locations || []).join(", ")}`}
                        >
                          +{course.hidden_other_location_count}{" "}
                          {(course.hidden_other_locations || []).join(", ") || "off-campus"} hidden
                        </span>
                      )}

                      {showCsFeatures &&
                        elig?.badges.map((badge, idx) => (
                          <span
                            key={`${badge.kind}-${idx}`}
                            className={`inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[10px] font-semibold ${formatBadgeTone(
                              badge
                            )}`}
                          >
                            {badge.tone === "amber" && <AlertTriangle className="h-2.5 w-2.5" />}
                            {badge.label}
                          </span>
                        ))}

                      {elig?.prereq_status === "met" && (
                        <span className="inline-flex items-center gap-1 rounded-md border border-emerald-500/35 bg-emerald-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-300">
                          <CheckCircle2 className="h-2.5 w-2.5" />
                          Prereqs Met
                        </span>
                      )}
                      {elig?.prereq_status === "none" && (
                        <span className="rounded-md border border-zinc-700/80 bg-zinc-900 px-1.5 py-0.5 text-[10px] font-medium text-zinc-400">
                          No Prereqs
                        </span>
                      )}
                      {elig?.prereq_status === "unmet" && elig.missing_prereqs && (
                        <span className="inline-flex items-center gap-1 rounded-md border border-rose-500/35 bg-rose-500/10 px-1.5 py-0.5 text-[10px] font-medium text-rose-300">
                          <Lock className="h-2.5 w-2.5" />
                          Missing: {elig.missing_prereqs}
                        </span>
                      )}
                      {elig?.prereq_status === "prose" && (
                        <span className="inline-flex items-center gap-1 rounded-md border border-amber-500/40 bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-medium text-amber-200">
                          <AlertTriangle className="h-2.5 w-2.5" />
                          Check catalog text prereq
                        </span>
                      )}
                    </div>

                    <p className="text-sm text-zinc-200">{course.title_long}</p>

                    <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px]">
                      {showCsFeatures && elig?.tech_elective_reason && (csRequirement === "tech_elective" || csRequirement === "") && (
                        <span className="text-sky-300/90">{elig.tech_elective_reason}</span>
                      )}
                      {activeWarning && (
                        <span className="inline-flex items-center gap-1 text-amber-300/95">
                          <AlertTriangle className="h-3 w-3 shrink-0" />
                          {activeWarning}
                        </span>
                      )}
                      {course.crosslists && course.crosslists.length > 0 && (
                        <span className="text-zinc-500">Cross-listed: {course.crosslists.join(", ")}</span>
                      )}
                    </div>
                  </div>
                </button>

                <button
                  type="button"
                  onClick={() => openCourseDraft(course)}
                  className="inline-flex items-center gap-1.5 rounded-xl border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-200 hover:border-emerald-500/50 hover:text-emerald-300"
                >
                  <BellPlus className="h-3.5 w-3.5" />
                  Watch Any Section
                </button>
              </div>

              {isOpen && (
                <div className="space-y-4 border-t border-zinc-800/80 p-4">
                  {course.description && <p className="text-xs leading-relaxed text-zinc-400">{course.description}</p>}

                  {/* Prerequisites / Corequisites / Overlaps Box */}
                  {(course.catalog_prereq ||
                    course.catalog_coreq ||
                    course.catalog_forbidden_overlaps ||
                    showCsFeatures ||
                    (elig?.prereq_status && elig.prereq_status !== "none")) && (
                    <div className="space-y-1.5 rounded-xl border border-zinc-800 bg-zinc-950/80 p-3 text-xs">
                      <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] font-semibold text-zinc-300">
                        <span className="inline-flex items-center gap-1.5">
                          <BookMarked className="h-3.5 w-3.5 text-emerald-400" />
                          {showCsFeatures ? "Prerequisites & Degree Check" : "Prerequisites"}
                        </span>
                        {showCsFeatures && (
                          <a
                            href="https://catalog.cornell.edu/programs/computer-science-bs/"
                            target="_blank"
                            rel="noreferrer"
                            className="inline-flex items-center gap-1 font-normal text-emerald-400 hover:underline"
                          >
                            Cornell CS Catalog
                            <ExternalLink className="h-3 w-3" />
                          </a>
                        )}
                      </div>
                      {elig?.prereq_status === "met" && elig.satisfied_by && elig.satisfied_by.length > 0 && (
                        <div className="text-emerald-300">
                          <span className="font-medium">Prereq check: </span>
                          Satisfied by {elig.satisfied_by.join(", ")}
                        </div>
                      )}
                      {elig?.prereq_status === "none" && (
                        <div className="text-zinc-400">
                          <span className="font-medium">Prereq check: </span>
                          No explicit course prerequisites listed.
                        </div>
                      )}
                      {elig?.prereq_status === "unmet" && elig.missing_prereqs && (
                        <div className="text-rose-300">
                          <span className="font-medium">Prereq check: </span>
                          Missing {elig.missing_prereqs}
                        </div>
                      )}
                      {elig?.prereq_status === "prose" && (
                        <div className="text-amber-200">
                          <span className="font-medium">Prereq check: </span>
                          Text-only prerequisite — verify manually against the catalog description below.
                        </div>
                      )}
                      {course.catalog_prereq && (
                        <div className="text-zinc-300">
                          <span className="font-medium text-zinc-400">Prerequisites: </span>
                          {course.catalog_prereq}
                        </div>
                      )}
                      {course.catalog_coreq && (
                        <div className="text-zinc-300">
                          <span className="font-medium text-zinc-400">Corequisites: </span>
                          {course.catalog_coreq}
                        </div>
                      )}
                      {course.catalog_forbidden_overlaps && (
                        <div className="text-zinc-400">
                          <span className="font-medium">Forbidden Overlaps: </span>
                          {course.catalog_forbidden_overlaps}
                        </div>
                      )}
                      {showCsFeatures && elig?.tech_elective && elig.tech_elective_reason && (
                        <div className="text-sky-300/95">
                          <span className="font-medium">Why it counts as CS Tech Elective: </span>
                          {elig.tech_elective_reason.replace(/^TE rule:\s*/i, "")}
                          {elig.tech_elective_reason.includes("cross-listed") &&
                            " (Cornell departments sometimes write different prerequisite text on cross-listed numbers.)"}
                        </div>
                      )}
                      {showCsFeatures && course.acad_group && course.acad_group !== "AS" && (
                        <div className="text-[11px] text-zinc-500">
                          College code <span className="text-zinc-300">{course.acad_group}</span> (B.A. A&amp;S students: non-A&amp;S course cap applies). Always confirm degree audit with your CS advisor.
                        </div>
                      )}
                    </div>
                  )}

                  <CourseInsightsPanel
                    course={course}
                    insights={insightsMap[cacheKey]}
                    loading={Boolean(insightsLoading[cacheKey])}
                    error={insightsError[cacheKey]}
                    onRefresh={() => {
                      void loadInsights(course, true);
                    }}
                  />

                  {Array.from(groups.entries()).map(([egIdx, secs]) => (
                    <div key={egIdx} className="rounded-xl border border-zinc-800 bg-zinc-950/70 p-3">
                      <div className="mb-2 flex items-center justify-between text-xs text-zinc-400">
                        <span className="font-semibold text-zinc-300">Enrollment Group {egIdx + 1}</span>
                        {secs[0]?.components_required?.length > 0 && (
                          <span>Required: {secs[0].components_required.join(" + ")}</span>
                        )}
                      </div>
                      <div className="divide-y divide-zinc-800/70">
                        {secs.map((sec) => {
                          const secLoc = getSectionLocationTag(sec);
                          const virtualLabel = getSectionVirtualLabel(sec.instruction_mode);
                          return (
                            <div
                              key={sec.class_nbr}
                              className="flex flex-wrap items-center justify-between gap-2 py-2.5 first:pt-1 last:pb-1"
                            >
                              <div className="min-w-0 space-y-0.5">
                                <div className="flex flex-wrap items-center gap-2">
                                  <span className="text-sm font-semibold text-white">
                                    {sec.ssr_component} {sec.section}
                                  </span>
                                  <span className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono text-xs text-zinc-300">
                                    #{sec.class_nbr}
                                  </span>
                                  {course.status_is_stale ? (
                                    <span className="inline-flex items-center gap-1 rounded-full bg-zinc-800 px-2.5 py-0.5 text-[11px] font-medium text-zinc-300">
                                      <Loader2 className="h-3 w-3 animate-spin text-emerald-400" />
                                      Loading...
                                    </span>
                                  ) : (
                                    <StatusBadge status={sec.open_status} />
                                  )}
                                  {secLoc.isOffCampus ? (
                                    <span className="inline-flex items-center gap-1 rounded-md border border-amber-500/40 bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-amber-200">
                                      <AlertTriangle className="h-2.5 w-2.5 text-amber-300" />
                                      {secLoc.label}
                                    </span>
                                  ) : (
                                    <span className="inline-flex items-center gap-1 rounded-md border border-zinc-700/80 bg-zinc-900 px-1.5 py-0.5 text-[10px] text-zinc-400">
                                      <MapPin className="h-2.5 w-2.5 text-zinc-500" />
                                      {secLoc.label}
                                    </span>
                                  )}
                                  {virtualLabel && (
                                    <span className="rounded-md border border-cyan-500/35 bg-cyan-500/15 px-1.5 py-0.5 text-[10px] font-medium text-cyan-200">
                                      {virtualLabel}
                                    </span>
                                  )}
                                </div>
                                <div className="text-xs text-zinc-400">
                                  {sec.meetings_summary} &middot; {sec.instructors_summary}
                                </div>
                              </div>

                              <button
                                type="button"
                                onClick={() => openSectionDraft(course, sec)}
                                className="inline-flex items-center gap-1.5 rounded-xl bg-emerald-500/15 px-3 py-1.5 text-xs font-semibold text-emerald-300 ring-1 ring-emerald-500/30 hover:bg-emerald-500/25"
                              >
                                <BellPlus className="h-3.5 w-3.5" />
                                Snipe
                              </button>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {draft && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm">
          <form
            onSubmit={submitWatch}
            className="w-full max-w-md space-y-4 rounded-2xl border border-zinc-700 bg-zinc-900 p-5 shadow-2xl"
          >
            <div>
              <h3 className="text-lg font-bold text-white">
                Arm Sniper: {draft.course.subject} {draft.course.catalog_nbr}
              </h3>
              <p className="text-xs text-zinc-400">
                {draft.section
                  ? `${draft.section.ssr_component} ${draft.section.section} (#${draft.section.class_nbr})`
                  : "Any section in this course"}
              </p>
            </div>

            {draft.section ? (
              <div>
                <label className="mb-1.5 block text-xs font-medium text-zinc-300">Watch Mode</label>
                <div className="space-y-2">
                  <label className="flex cursor-pointer items-start gap-2.5 rounded-xl border border-zinc-700 bg-zinc-950 p-3 text-xs">
                    <input
                      type="radio"
                      checked={draft.mode === "exact"}
                      onChange={() => setDraft({ ...draft, mode: "exact" })}
                      className="mt-0.5 accent-emerald-500"
                    />
                    <div>
                      <div className="font-semibold text-white">Exact Section Only</div>
                      <div className="text-zinc-400">
                        Alert as soon as #{draft.section.class_nbr} opens (best if already enrolled in Lecture).
                      </div>
                    </div>
                  </label>
                  <label className="flex cursor-pointer items-start gap-2.5 rounded-xl border border-zinc-700 bg-zinc-950 p-3 text-xs">
                    <input
                      type="radio"
                      checked={draft.mode === "linked_group"}
                      onChange={() => setDraft({ ...draft, mode: "linked_group" })}
                      className="mt-0.5 accent-emerald-500"
                    />
                    <div>
                      <div className="font-semibold text-white">Linked Group (LEC + DIS/LAB)</div>
                      <div className="text-zinc-400">
                        Alert only when this section AND all required companion components in its enroll group are open.
                      </div>
                    </div>
                  </label>
                </div>
              </div>
            ) : (
              <div>
                <label className="mb-1 block text-xs font-medium text-zinc-300">Component Filter (optional)</label>
                <select
                  value={draft.componentFilter}
                  onChange={(e) => setDraft({ ...draft, componentFilter: e.target.value })}
                  className="w-full rounded-xl border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-white"
                >
                  <option value="">Any Component (LEC / DIS / LAB)</option>
                  <option value="LEC">Lectures Only (LEC)</option>
                  <option value="DIS">Discussions Only (DIS)</option>
                  <option value="LAB">Labs Only (LAB)</option>
                </select>
                {ithacaOrVirtual ? (
                  <p className="mt-1.5 flex items-center gap-1 text-[11px] text-emerald-300/90">
                    <MapPin className="h-3 w-3 shrink-0" />
                    Scoped to Ithaca campus &amp; virtual sections only (ignores off-campus sections like Cornell Tech).
                  </p>
                ) : (
                  <p className="mt-1.5 flex items-center gap-1 text-[11px] text-amber-300/90">
                    <AlertTriangle className="h-3 w-3 shrink-0" />
                    Includes all campus locations (including Cornell Tech &amp; off-campus sections).
                  </p>
                )}
              </div>
            )}

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="mb-1 block text-xs font-medium text-zinc-300">Trigger Status</label>
                <select
                  value={draft.triggerOn}
                  onChange={(e) => setDraft({ ...draft, triggerOn: e.target.value as "open" | "open_or_waitlist" })}
                  className="w-full rounded-xl border border-zinc-700 bg-zinc-950 px-3 py-2 text-xs text-white"
                >
                  <option value="open">Open (O) only</option>
                  <option value="open_or_waitlist">Open (O) or Waitlist (W)</option>
                </select>
              </div>

              <div>
                <label className="mb-1 block text-xs font-medium text-zinc-300">Cooldown (sec)</label>
                <input
                  type="number"
                  min={0}
                  max={86400}
                  value={draft.cooldownSec}
                  onChange={(e) => setDraft({ ...draft, cooldownSec: Number(e.target.value) })}
                  className="w-full rounded-xl border border-zinc-700 bg-zinc-950 px-3 py-2 text-xs text-white"
                />
              </div>
            </div>

            {user.role === "admin" && (
              <div className="flex items-center justify-between rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 text-xs">
                <span className="text-zinc-300">Admin High Priority Polling</span>
                <input
                  type="checkbox"
                  checked={draft.priority === 2}
                  onChange={(e) => setDraft({ ...draft, priority: e.target.checked ? 2 : 1 })}
                  className="accent-emerald-500"
                />
              </div>
            )}

            <label className="flex cursor-pointer items-center justify-between rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 text-xs">
              <span className="text-zinc-300">Auto-pause watch after alert fires</span>
              <input
                type="checkbox"
                checked={draft.autoPause}
                onChange={(e) => setDraft({ ...draft, autoPause: e.target.checked })}
                className="accent-emerald-500"
              />
            </label>

            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setDraft(null)}
                className="rounded-xl border border-zinc-700 px-4 py-2 text-sm text-zinc-300 hover:bg-zinc-800"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={saving}
                className="rounded-xl bg-emerald-500 px-4 py-2 text-sm font-semibold text-zinc-950 hover:bg-emerald-400 disabled:opacity-50"
              >
                {saving ? "Arming..." : "Arm Watch"}
              </button>
            </div>
          </form>
        </div>
      )}
      <CompletedPrereqsModal
        isOpen={prereqsModalOpen}
        roster={selectedRoster}
        initialCompleted={user.completed_courses || []}
        initialIncludeImplied={user.include_implied_prereqs ?? true}
        showCsFeatures={showCsFeatures}
        onClose={() => setPrereqsModalOpen(false)}
        onSaved={(res) => {
          onUserUpdated?.({
            ...user,
            completed_courses: res.completed_courses,
            include_implied_prereqs: res.include_implied_prereqs,
          });
          if (hasSearchedRef.current || csRequirement || query.trim() || selectedSubjects.length > 0 || onlyEligible) {
            void executeSearch({ silent: true });
          }
        }}
      />
    </div>
  );
}
