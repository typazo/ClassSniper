import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import type {
  AttributeOption,
  AttrMatchMode,
  CatalogStatus,
  CatalogSubjectRefreshedSSE,
  CourseInsights,
  CourseSearchPreset,
  CourseSummary,
  CSCurriculumMode,
  CSRequirementMode,
  HydratedSchedule,
  IlrMatchMode,
  IlrSummaryResponse,
  MajorMode,
  MinorCatalogItem,
  MinorPrefs,
  Roster,
  SearchCoursesMeta,
  Subject,
  User,
} from "../types";
import { courseCacheKey, summarizeStatuses } from "../utils/courseFormat";
import { evaluateCourseFitsSchedule } from "../utils/schedulerSolver";
import { resolveUserMinorPrefs } from "./useMinorPrefsController";

export type StatusFilter = "all" | "open" | "closed" | "waitlist";

export interface SearchOverride {
  roster?: string;
  query?: string;
  subjects?: string[];
  levelMin?: number | null;
  minCredits?: number | null;
  csRequirement?: CSRequirementMode;
  include2000TE?: boolean;
  includeResearchTE?: boolean;
  curriculum?: CSCurriculumMode;
  ilrCodes?: string[];
  ilrMatch?: IlrMatchMode;
  ilrMultiOnly?: boolean;
  attrs?: string[];
  attrMatch?: AttrMatchMode;
  minor?: string;
  minorVersion?: string;
  minorCategories?: string[];
  minorCompleted?: string[];
  minorHideCompleted?: boolean;
  onlyEligible?: boolean;
  ithacaOrVirtual?: boolean;
  majorMode?: MajorMode;
  silent?: boolean;
}

export interface ActiveCriteriaInput {
  query: string;
  subjects: string[];
  majorMode: MajorMode;
  csRequirement: CSRequirementMode;
  ilrCodes: string[];
  ilrMultiOnly: boolean;
  attrs: string[];
  minor: string;
  levelMin: number | null;
  minCredits: number | null;
  onlyEligible: boolean;
}

export function hasActiveSearchCriteria(c: ActiveCriteriaInput): boolean {
  const csActive = c.majorMode === "cs" && c.csRequirement !== "";
  const ilrActive = c.majorMode === "ilr" && (c.ilrCodes.length > 0 || c.ilrMultiOnly);
  return (
    Boolean(c.query.trim()) ||
    c.subjects.length > 0 ||
    csActive ||
    ilrActive ||
    c.attrs.length > 0 ||
    Boolean(c.minor) ||
    Boolean(c.levelMin) ||
    Boolean(c.minCredits) ||
    c.onlyEligible
  );
}

export function resolveUserMajorMode(u: User): MajorMode {
  if (u.major_mode === "none" || u.major_mode === "cs" || u.major_mode === "ilr") {
    return u.major_mode;
  }
  return u.show_cs_features === false ? "none" : "cs";
}

interface Options {
  user: User;
  lastCatalogRefresh?: CatalogSubjectRefreshedSSE | null;
  searchPreset?: CourseSearchPreset | null;
  onUserUpdated?: (user: User) => void;
  onJumpToScheduler?: () => void;
  onOpenAttrsPanel?: () => void;
}

export function useCatalogSearch({
  user,
  lastCatalogRefresh,
  searchPreset,
  onUserUpdated,
  onJumpToScheduler,
  onOpenAttrsPanel,
}: Options) {
  const [rosters, setRosters] = useState<Roster[]>([]);
  const [selectedRoster, setSelectedRoster] = useState("");
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [selectedSubjects, setSelectedSubjects] = useState<string[]>([]);
  const [query, setQuery] = useState("");

  const [majorMode, setMajorMode] = useState<MajorMode>(() => resolveUserMajorMode(user));
  const showCsFeatures = majorMode === "cs";
  const showIlrFeatures = majorMode === "ilr";

  const [csRequirement, setCsRequirement] = useState<CSRequirementMode>("");
  const [levelMin, setLevelMin] = useState<number | null>(null);
  const [curriculum, setCurriculum] = useState<CSCurriculumMode>("current");
  const [include2000TE, setInclude2000TE] = useState(true);
  const [includeResearchTE, setIncludeResearchTE] = useState(true);

  const [ilrCodes, setIlrCodes] = useState<string[]>([]);
  const [ilrMatch, setIlrMatch] = useState<IlrMatchMode>("any");
  const [ilrMultiOnly, setIlrMultiOnly] = useState(false);
  const [ilrSummary, setIlrSummary] = useState<IlrSummaryResponse | null>(null);
  const [loadingIlrSummary, setLoadingIlrSummary] = useState(false);
  const [syncingIlrPriority, setSyncingIlrPriority] = useState(false);

  const [onlyEligible, setOnlyEligible] = useState(false);
  const [ithacaOrVirtual, setIthacaOrVirtual] = useState(true);
  const [selectedAttrs, setSelectedAttrs] = useState<string[]>([]);
  const [attrMatch, setAttrMatch] = useState<AttrMatchMode>("any");
  const [attrOptions, setAttrOptions] = useState<AttributeOption[]>([]);

  const [minorPrefs, setMinorPrefs] = useState<MinorPrefs>(() => resolveUserMinorPrefs(user));
  const [minorCategories, setMinorCategories] = useState<string[]>([]);
  const [minorsCatalog, setMinorsCatalog] = useState<MinorCatalogItem[]>([]);
  const [loadingMinorsCatalog, setLoadingMinorsCatalog] = useState(false);

  const [minCredits, setMinCredits] = useState<number | null>(null);
  const [fitsActiveSchedule, setFitsActiveSchedule] = useState(false);
  const [activeSchedule, setActiveSchedule] = useState<HydratedSchedule | null>(null);
  const [loadingScheduleFit, setLoadingScheduleFit] = useState(false);

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
  const [scheduledStatus, setScheduledStatus] = useState<Record<string, "adding" | "added" | "exists">>({});

  const uncachedRequestedRef = useRef<Set<string>>(new Set());
  const hasSearchedRef = useRef(false);
  const lastProcessedRefreshRef = useRef<CatalogSubjectRefreshedSSE | null>(null);
  const searchSeqRef = useRef(0);
  const manualSearchSeqRef = useRef(0);
  const lastAppliedPresetIdRef = useRef<number | null>(null);

  // Sync user preference props
  useEffect(() => {
    const resolved = resolveUserMajorMode(user);
    setMajorMode(resolved);
    if (resolved !== "cs") setCsRequirement("");
    if (resolved !== "ilr") {
      setIlrCodes([]);
      setIlrMultiOnly(false);
    }
  }, [user.major_mode, user.show_cs_features]);

  useEffect(() => {
    if (user.minor_prefs) {
      setMinorPrefs(resolveUserMinorPrefs(user));
    }
  }, [user.minor_prefs]);

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
    let cancelled = false;
    setLoadingMinorsCatalog(true);
    api
      .getMinorsCatalog(selectedRoster)
      .then((res) => {
        if (!cancelled) setMinorsCatalog(res.minors);
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setLoadingMinorsCatalog(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedRoster, user.completed_courses, user.in_progress_courses]);

  const loadIlrSummary = useCallback(async (roster: string, ithVirt: boolean, syncPriority = false) => {
    if (!roster) return;
    if (syncPriority) setSyncingIlrPriority(true);
    else setLoadingIlrSummary(true);
    try {
      const res = await api.getIlrSummary(roster, ithVirt, syncPriority);
      setIlrSummary(res);
    } catch {
      // Non-fatal: keep existing summary if background fetch fails
    } finally {
      setLoadingIlrSummary(false);
      setSyncingIlrPriority(false);
    }
  }, []);

  useEffect(() => {
    if (!selectedRoster) return;
    let cancelled = false;
    api
      .listSubjects(selectedRoster)
      .then((res) => {
        if (!cancelled) setSubjects(res.subjects);
      })
      .catch(() => {});
    api
      .getCatalogStatus(selectedRoster)
      .then((st) => {
        if (!cancelled) setCatalogStatus(st);
      })
      .catch(() => {});
    api
      .getCourseAttributes(selectedRoster)
      .then((res) => {
        if (!cancelled) setAttrOptions(res.attributes);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [selectedRoster]);

  useEffect(() => {
    if (!selectedRoster || !fitsActiveSchedule) return;
    let cancelled = false;
    setLoadingScheduleFit(true);
    api
      .listSchedules(selectedRoster)
      .then((res) => {
        if (!cancelled) setActiveSchedule(res.active);
      })
      .catch(() => {
        if (!cancelled) setActiveSchedule(null);
      })
      .finally(() => {
        if (!cancelled) setLoadingScheduleFit(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedRoster, fitsActiveSchedule]);

  useEffect(() => {
    if (!selectedRoster || !showIlrFeatures) return;
    void loadIlrSummary(selectedRoster, ithacaOrVirtual, false);
  }, [selectedRoster, showIlrFeatures, ithacaOrVirtual, loadIlrSummary]);

  const insightsRef = useRef({ insightsMap, insightsLoading });
  insightsRef.current = { insightsMap, insightsLoading };

  const loadInsights = useCallback(async (course: CourseSummary, refresh = false) => {
    const key = courseCacheKey(course);
    if (!refresh && (insightsRef.current.insightsMap[key] || insightsRef.current.insightsLoading[key])) {
      return;
    }
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
  }, []);

  const latestRef = useRef({
    selectedRoster,
    query,
    selectedSubjects,
    majorMode,
    csRequirement,
    ilrCodes,
    ilrMatch,
    ilrMultiOnly,
    selectedAttrs,
    attrMatch,
    minorPrefs,
    minorCategories,
    levelMin,
    minCredits,
    include2000TE,
    includeResearchTE,
    curriculum,
    onlyEligible,
    ithacaOrVirtual,
  });
  latestRef.current = {
    selectedRoster,
    query,
    selectedSubjects,
    majorMode,
    csRequirement,
    ilrCodes,
    ilrMatch,
    ilrMultiOnly,
    selectedAttrs,
    attrMatch,
    minorPrefs,
    minorCategories,
    levelMin,
    minCredits,
    include2000TE,
    includeResearchTE,
    curriculum,
    onlyEligible,
    ithacaOrVirtual,
  };

  const clearSearchResults = useCallback(() => {
    searchSeqRef.current += 1;
    setCourses([]);
    setSearchMeta(null);
    setError("");
    hasSearchedRef.current = false;
  }, []);

  const resetAllSearchFilters = useCallback(() => {
    setQuery("");
    setSelectedSubjects([]);
    setLevelMin(null);
    setMinCredits(null);
    setCsRequirement("");
    setIlrCodes([]);
    setIlrMatch("any");
    setIlrMultiOnly(false);
    setSelectedAttrs([]);
    setAttrMatch("any");
    setOnlyEligible(false);
    setFitsActiveSchedule(false);
    setIthacaOrVirtual(true);
    clearSearchResults();
  }, [clearSearchResults]);

  const getCurrentCriteria = useCallback((): ActiveCriteriaInput => {
    const st = latestRef.current;
    return {
      query: st.query,
      subjects: st.selectedSubjects,
      majorMode: st.majorMode,
      csRequirement: st.csRequirement,
      ilrCodes: st.ilrCodes,
      ilrMultiOnly: st.ilrMultiOnly,
      attrs: st.selectedAttrs,
      minor: st.minorPrefs.selected_minor,
      levelMin: st.levelMin,
      minCredits: st.minCredits,
      onlyEligible: st.onlyEligible,
    };
  }, []);

  const hasNonMinorSearchCriteria = useCallback(() => {
    return hasActiveSearchCriteria({ ...getCurrentCriteria(), minor: "" });
  }, [getCurrentCriteria]);

  const executeSearch = useCallback(
    async (override?: SearchOverride) => {
      const st = latestRef.current;
      const r = override?.roster ?? st.selectedRoster;
      if (!r) return;

      const q = override?.query ?? st.query;
      const subjs = override?.subjects ?? st.selectedSubjects;
      const effMode = override?.majorMode ?? st.majorMode;
      const csEnabled = effMode === "cs";
      const ilrEnabled = effMode === "ilr";
      const req = csEnabled ? (override?.csRequirement ?? st.csRequirement) : "";
      const effIlrCodes = ilrEnabled ? (override?.ilrCodes ?? st.ilrCodes) : [];
      const effIlrMatch = override?.ilrMatch ?? st.ilrMatch;
      const effIlrMultiOnly = ilrEnabled ? (override?.ilrMultiOnly ?? st.ilrMultiOnly) : false;
      const effAttrs = override?.attrs ?? st.selectedAttrs;
      const effAttrMatch = override?.attrMatch ?? st.attrMatch;
      const effMinor = override?.minor !== undefined ? override.minor : st.minorPrefs.selected_minor;
      const effMinorVersion =
        override?.minorVersion !== undefined
          ? override.minorVersion
          : effMinor
            ? st.minorPrefs.versions[effMinor] || ""
            : "";
      const effMinorCategories = override?.minorCategories ?? st.minorCategories;
      const effMinorCompleted =
        override?.minorCompleted !== undefined
          ? override.minorCompleted
          : effMinor
            ? st.minorPrefs.completed_categories[effMinor] || []
            : [];
      const effMinorHideCompleted =
        override?.minorHideCompleted !== undefined
          ? override.minorHideCompleted
          : st.minorPrefs.hide_completed;
      const lvl = override?.levelMin !== undefined ? override.levelMin : st.levelMin;
      const minCr = override?.minCredits !== undefined ? override.minCredits : st.minCredits;
      const inc2000 = override?.include2000TE ?? st.include2000TE;
      const incRes = override?.includeResearchTE ?? st.includeResearchTE;
      const curr = override?.curriculum ?? st.curriculum;
      const eligibleOnly = override?.onlyEligible ?? st.onlyEligible;
      const ithVirt = override?.ithacaOrVirtual ?? st.ithacaOrVirtual;
      const silent = Boolean(override?.silent);
      const hasIlrCriteria = effIlrCodes.length > 0 || effIlrMultiOnly;

      if (
        !hasActiveSearchCriteria({
          query: q,
          subjects: subjs,
          majorMode: effMode,
          csRequirement: req,
          ilrCodes: effIlrCodes,
          ilrMultiOnly: effIlrMultiOnly,
          attrs: effAttrs,
          minor: effMinor,
          levelMin: lvl,
          minCredits: minCr,
          onlyEligible: eligibleOnly,
        })
      ) {
        if (!silent) {
          setError(
            ilrEnabled
              ? "Pick an ILR distribution code/preset above, select a minor/attributes/subjects, or enter a keyword."
              : csEnabled
                ? "Enter a course code, keyword, pick a minor/attributes/subjects, or select a CS requirement filter."
                : "Enter a course code, keyword, class #, pick a minor, attributes, or subjects."
          );
        }
        return;
      }

      hasSearchedRef.current = true;
      const seq = ++searchSeqRef.current;
      let manualSeq = 0;
      if (!silent) {
        manualSeq = ++manualSearchSeqRef.current;
        setError("");
        setLoading(true);
      }

      try {
        const res = await api.searchCourses(r, q, {
          subjects: subjs,
          level_min: lvl,
          min_credits: minCr,
          cs_requirement: req,
          include_2000_te: inc2000,
          include_research_te: incRes,
          curriculum: curr,
          ilr_codes: effIlrCodes,
          ilr_match: effIlrMatch,
          ilr_multi_only: effIlrMultiOnly,
          include_ilr: ilrEnabled,
          attrs: effAttrs,
          attr_match: effAttrMatch,
          minor: effMinor || undefined,
          minor_version: effMinorVersion || undefined,
          minor_categories: effMinor ? effMinorCategories : undefined,
          minor_completed: effMinor ? effMinorCompleted : undefined,
          minor_hide_completed: effMinor ? effMinorHideCompleted : undefined,
          only_eligible: eligibleOnly,
          ithaca_or_virtual: ithVirt,
          refresh_stale: true,
          limit: req || hasIlrCriteria || effAttrs.length > 0 || effMinor ? 200 : 100,
        });

        if (seq !== searchSeqRef.current) return;

        setCourses(res.courses);
        if (res.meta) setSearchMeta(res.meta);
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

        const visibleSubjSet = new Set(res.courses.map((c) => c.subject.toUpperCase()));
        const pendingMissing = new Set<string>();
        for (const s of res.meta?.queued_subjects || []) {
          if (!visibleSubjSet.has(s.toUpperCase())) pendingMissing.add(s.toUpperCase());
        }
        if (csEnabled && req === "tech_elective" && subjs.length === 0 && (res.meta?.stem_synced ?? 0) < (res.meta?.stem_total ?? 0)) {
          pendingMissing.add("__STEM_WARMUP__");
        }
        if (ilrEnabled && hasIlrCriteria) {
          pendingMissing.add("__ILR_WARMUP__");
        }
        uncachedRequestedRef.current = pendingMissing;
      } catch (err) {
        if (!silent && seq === searchSeqRef.current) {
          setError(err instanceof Error ? err.message : "Search failed");
        }
      } finally {
        if (!silent && manualSeq === manualSearchSeqRef.current) {
          setLoading(false);
        }
      }
    },
    [loadInsights]
  );

  // Live SSE handler
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
      (uncachedRequestedRef.current.has(refreshedSubj) ||
        uncachedRequestedRef.current.has("__STEM_WARMUP__") ||
        uncachedRequestedRef.current.has("__ILR_WARMUP__"))
    ) {
      uncachedRequestedRef.current.delete(refreshedSubj);
      void executeSearch({ silent: true });
    }
    if (showIlrFeatures && selectedRoster) {
      void loadIlrSummary(selectedRoster, ithacaOrVirtual, false);
    }
  }, [lastCatalogRefresh, selectedRoster, showIlrFeatures, ithacaOrVirtual, executeSearch, loadIlrSummary]);

  // Initial auto-search when user has a saved Minor preference (skip if preset drives initial search)
  useEffect(() => {
    if (selectedRoster && minorPrefs.selected_minor && !hasSearchedRef.current && !searchPreset) {
      void executeSearch();
    }
  }, [selectedRoster, minorPrefs.selected_minor, searchPreset, executeSearch]);

  // Apply CS Checklist search preset
  useEffect(() => {
    if (!searchPreset || !selectedRoster) return;
    if (lastAppliedPresetIdRef.current === searchPreset.id) return;
    lastAppliedPresetIdRef.current = searchPreset.id;

    const nextQ = searchPreset.q ?? "";
    const nextSubjs = searchPreset.subjects ?? [];
    const nextLvl =
      searchPreset.level_min === "" || searchPreset.level_min === undefined ? null : searchPreset.level_min;
    const nextMinCr =
      searchPreset.min_credits === "" || searchPreset.min_credits === undefined ? null : searchPreset.min_credits;
    const nextReq = searchPreset.cs_requirement ?? "";
    const nextAttrs = searchPreset.attrs ?? [];
    const nextAttrMatch = searchPreset.attr_match ?? "any";
    const nextCurr = searchPreset.curriculum ?? curriculum;
    const nextMode: MajorMode = nextReq ? "cs" : majorMode;

    setQuery(nextQ);
    setSelectedSubjects(nextSubjs);
    setLevelMin(nextLvl);
    setMinCredits(nextMinCr);
    setCsRequirement(nextReq);
    setSelectedAttrs(nextAttrs);
    setAttrMatch(nextAttrMatch);
    if (nextReq && majorMode !== "cs") setMajorMode("cs");
    if (nextCurr) setCurriculum(nextCurr);
    if (nextAttrs.length > 0) onOpenAttrsPanel?.();

    void executeSearch({
      query: nextQ,
      subjects: nextSubjs,
      levelMin: nextLvl,
      minCredits: nextMinCr,
      csRequirement: nextReq,
      attrs: nextAttrs,
      attrMatch: nextAttrMatch,
      curriculum: nextCurr,
      majorMode: nextMode,
    });
  }, [searchPreset, selectedRoster, curriculum, majorMode, executeSearch, onOpenAttrsPanel]);

  const handleSelectRoster = useCallback(
    (nextRoster: string) => {
      if (!nextRoster || nextRoster === selectedRoster) return;
      setSelectedRoster(nextRoster);
      setExpanded({});
      setScheduledStatus({});
      setError("");
      if (hasSearchedRef.current || hasActiveSearchCriteria(getCurrentCriteria())) {
        void executeSearch({ roster: nextRoster });
      } else {
        clearSearchResults();
      }
    },
    [selectedRoster, getCurrentCriteria, executeSearch, clearSearchResults]
  );

  const handleModeSelect = useCallback(
    (nextMode: CSRequirementMode) => {
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

      if (
        hasActiveSearchCriteria({
          ...getCurrentCriteria(),
          csRequirement: nextMode,
          subjects: nextSubjs,
          levelMin: nextLevel,
        })
      ) {
        void executeSearch({ csRequirement: nextMode, subjects: nextSubjs, levelMin: nextLevel });
      } else {
        clearSearchResults();
      }
    },
    [selectedSubjects, levelMin, getCurrentCriteria, executeSearch, clearSearchResults]
  );

  const handleChangeMajorMode = useCallback(
    (nextMode: MajorMode) => {
      if (nextMode === majorMode) return;
      setError("");
      const prevMode = majorMode;
      setMajorMode(nextMode);
      onUserUpdated?.({
        ...user,
        major_mode: nextMode,
        show_cs_features: nextMode === "cs",
      });

      const hadCsReq = prevMode === "cs" && csRequirement !== "";
      const hadIlrReq = prevMode === "ilr" && (ilrCodes.length > 0 || ilrMultiOnly);
      const nextLevel = prevMode === "cs" && csRequirement === "external_spec" && levelMin === 3000 ? null : levelMin;

      if (nextMode !== "cs" && csRequirement !== "") {
        setCsRequirement("");
        if (nextLevel !== levelMin) setLevelMin(nextLevel);
      }
      if (nextMode !== "ilr" && (ilrCodes.length > 0 || ilrMultiOnly)) {
        setIlrCodes([]);
        setIlrMultiOnly(false);
      }

      const remainingActive = hasActiveSearchCriteria({
        ...getCurrentCriteria(),
        majorMode: nextMode,
        csRequirement: nextMode === "cs" ? csRequirement : "",
        ilrCodes: nextMode === "ilr" ? ilrCodes : [],
        ilrMultiOnly: nextMode === "ilr" ? ilrMultiOnly : false,
        levelMin: nextLevel,
      });

      if (hadCsReq || hadIlrReq) {
        if (remainingActive) {
          void executeSearch({
            majorMode: nextMode,
            csRequirement: nextMode === "cs" ? csRequirement : "",
            ilrCodes: nextMode === "ilr" ? ilrCodes : [],
            ilrMultiOnly: nextMode === "ilr" ? ilrMultiOnly : false,
            levelMin: nextLevel,
          });
        } else {
          clearSearchResults();
        }
      } else if (hasSearchedRef.current && (nextMode === "ilr" || nextMode === "cs")) {
        void executeSearch({ majorMode: nextMode, silent: true });
      }

      api
        .updateUserPreferences({ major_mode: nextMode })
        .then((res) => onUserUpdated?.(res.user))
        .catch((err) => {
          setMajorMode(prevMode);
          onUserUpdated?.({
            ...user,
            major_mode: prevMode,
            show_cs_features: prevMode === "cs",
          });
          setError(err instanceof Error ? err.message : "Failed to save preference");
        });
    },
    [
      majorMode,
      user,
      csRequirement,
      ilrCodes,
      ilrMultiOnly,
      levelMin,
      getCurrentCriteria,
      executeSearch,
      clearSearchResults,
      onUserUpdated,
    ]
  );

  const applyIlrFilters = useCallback(
    (nextCodes: string[], nextMatch: IlrMatchMode, nextMultiOnly: boolean) => {
      setError("");
      setIlrCodes(nextCodes);
      setIlrMatch(nextMatch);
      setIlrMultiOnly(nextMultiOnly);

      if (
        hasActiveSearchCriteria({
          ...getCurrentCriteria(),
          majorMode: "ilr",
          ilrCodes: nextCodes,
          ilrMultiOnly: nextMultiOnly,
        })
      ) {
        void executeSearch({
          majorMode: "ilr",
          ilrCodes: nextCodes,
          ilrMatch: nextMatch,
          ilrMultiOnly: nextMultiOnly,
        });
      } else {
        clearSearchResults();
      }
    },
    [getCurrentCriteria, executeSearch, clearSearchResults]
  );

  const handleToggleIlrCode = useCallback(
    (code: string) => {
      const cleaned = ilrCodes.filter((c) => c !== "ANY_IL");
      const nextCodes = cleaned.includes(code) ? cleaned.filter((c) => c !== code) : [...cleaned, code];
      applyIlrFilters(nextCodes, ilrMatch, ilrMultiOnly);
    },
    [ilrCodes, ilrMatch, ilrMultiOnly, applyIlrFilters]
  );

  const handleToggleAttr = useCallback(
    (code: string) => {
      const nextAttrs = selectedAttrs.includes(code)
        ? selectedAttrs.filter((a) => a !== code)
        : [...selectedAttrs, code];
      setSelectedAttrs(nextAttrs);
      if (hasActiveSearchCriteria({ ...getCurrentCriteria(), attrs: nextAttrs })) {
        void executeSearch({ attrs: nextAttrs });
      } else {
        clearSearchResults();
      }
    },
    [selectedAttrs, getCurrentCriteria, executeSearch, clearSearchResults]
  );

  const handleClearAttrs = useCallback(() => {
    setSelectedAttrs([]);
    if (hasActiveSearchCriteria({ ...getCurrentCriteria(), attrs: [] })) {
      void executeSearch({ attrs: [] });
    } else {
      clearSearchResults();
    }
  }, [getCurrentCriteria, executeSearch, clearSearchResults]);

  const handleQuickAddSchedule = useCallback(
    async (course: CourseSummary) => {
      const key = courseCacheKey(course);
      if (scheduledStatus[key] === "added" || scheduledStatus[key] === "exists") {
        onJumpToScheduler?.();
        return;
      }
      setScheduledStatus((p) => ({ ...p, [key]: "adding" }));
      try {
        const res = await api.quickAddScheduleCourse({
          roster: course.roster,
          subject: course.subject,
          catalog_nbr: course.catalog_nbr,
        });
        setScheduledStatus((p) => ({
          ...p,
          [key]: res.already_present ? "exists" : "added",
        }));
      } catch (err) {
        setScheduledStatus((p) => {
          const next = { ...p };
          delete next[key];
          return next;
        });
        setError(err instanceof Error ? err.message : "Failed to add course to active schedule");
      }
    },
    [scheduledStatus, onJumpToScheduler]
  );

  const toggleCourse = useCallback(
    (course: CourseSummary) => {
      const key = courseCacheKey(course);
      const nextOpen = !expanded[key];
      setExpanded((p) => ({ ...p, [key]: nextOpen }));
      if (nextOpen) {
        void loadInsights(course);
      }
    },
    [expanded, loadInsights]
  );

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

  const scheduleFitMap = useMemo(() => {
    const out = new Map<string, { fits: boolean; compatibleClassNbrs: Set<number> }>();
    if (!fitsActiveSchedule || !activeSchedule) return out;
    for (const c of courses) {
      out.set(courseCacheKey(c), evaluateCourseFitsSchedule(c, activeSchedule));
    }
    return out;
  }, [courses, fitsActiveSchedule, activeSchedule]);

  const filteredCourses = useMemo(() => {
    return courses.filter((c) => {
      if (statusFilter !== "all" && !c.status_is_stale && summarizeStatuses(c.sections)[statusFilter] === 0) {
        return false;
      }
      if (fitsActiveSchedule && activeSchedule) {
        const fit = scheduleFitMap.get(courseCacheKey(c));
        if (!fit?.fits) return false;
      }
      return true;
    });
  }, [courses, statusFilter, fitsActiveSchedule, activeSchedule, scheduleFitMap]);

  const staleVisibleCount = useMemo(() => courses.filter((c) => c.status_is_stale).length, [courses]);

  return {
    // Catalog & filter state
    rosters,
    selectedRoster,
    subjects,
    selectedSubjects,
    setSelectedSubjects,
    query,
    setQuery,
    majorMode,
    showCsFeatures,
    showIlrFeatures,
    csRequirement,
    levelMin,
    setLevelMin,
    curriculum,
    setCurriculum,
    include2000TE,
    setInclude2000TE,
    includeResearchTE,
    setIncludeResearchTE,
    ilrCodes,
    ilrMatch,
    ilrMultiOnly,
    ilrSummary,
    loadingIlrSummary,
    syncingIlrPriority,
    onlyEligible,
    setOnlyEligible,
    ithacaOrVirtual,
    setIthacaOrVirtual,
    selectedAttrs,
    attrMatch,
    setAttrMatch,
    attrOptions,
    minorPrefs,
    setMinorPrefs,
    minorCategories,
    setMinorCategories,
    minorsCatalog,
    loadingMinorsCatalog,
    minCredits,
    setMinCredits,
    fitsActiveSchedule,
    setFitsActiveSchedule,
    activeSchedule,
    loadingScheduleFit,
    // Results & UI state
    courses,
    filteredCourses,
    searchMeta,
    catalogStatus,
    statusFilter,
    setStatusFilter,
    filterCounts,
    scheduleFitMap,
    staleVisibleCount,
    loading,
    error,
    setError,
    expanded,
    insightsMap,
    insightsLoading,
    insightsError,
    scheduledStatus,
    hasSearchedRef,
    // Actions
    getCurrentCriteria,
    hasNonMinorSearchCriteria,
    executeSearch,
    clearSearchResults,
    resetAllSearchFilters,
    handleSelectRoster,
    handleModeSelect,
    handleChangeMajorMode,
    applyIlrFilters,
    handleToggleIlrCode,
    handleToggleAttr,
    handleClearAttrs,
    handleQuickAddSchedule,
    toggleCourse,
    loadInsights,
    loadIlrSummary,
  };
}
