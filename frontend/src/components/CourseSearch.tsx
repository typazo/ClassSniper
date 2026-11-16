import React, { useCallback, useEffect, useRef, useState } from "react";
import { FileUp, MapPin } from "lucide-react";
import { api } from "../api/client";
import { hasActiveSearchCriteria, useCatalogSearch } from "../hooks/useCatalogSearch";
import { useMinorPrefsController } from "../hooks/useMinorPrefsController";
import type {
  CatalogSubjectRefreshedSSE,
  CourseSearchPreset,
  CourseSection,
  CourseSummary,
  CSCurriculumMode,
  User,
} from "../types";
import { courseCacheKey } from "../utils/courseFormat";
import { CompletedPrereqsModal } from "./CompletedPrereqsModal";
import { FloatingToast } from "./FloatingToast";
import { TranscriptImportModal } from "./TranscriptImportModal";
import { ArmWatchModal, type WatchDraft } from "./search/ArmWatchModal";
import { CourseResultCard } from "./search/CourseResultCard";
import { SearchFilterHeader } from "./search/SearchFilterHeader";
import { SearchResultsToolbar } from "./search/SearchResultsToolbar";

interface Props {
  user: User;
  lastCatalogRefresh?: CatalogSubjectRefreshedSSE | null;
  searchPreset?: CourseSearchPreset | null;
  onClearSearchPreset?: () => void;
  onOpenChecklist?: (roster?: string) => void;
  onUserUpdated?: (user: User) => void;
  onWatchCreated: () => void;
  onJumpToScheduler?: () => void;
}

export function CourseSearch({
  user,
  lastCatalogRefresh,
  searchPreset,
  onClearSearchPreset,
  onOpenChecklist,
  onUserUpdated,
  onWatchCreated,
  onJumpToScheduler,
}: Props) {
  const [attrsExpanded, setAttrsExpanded] = useState(false);
  const [minorExpanded, setMinorExpanded] = useState(false);
  const [prereqsModalOpen, setPrereqsModalOpen] = useState(false);
  const [transcriptOpen, setTranscriptOpen] = useState(false);

  const [draft, setDraft] = useState<WatchDraft | null>(null);
  const [savingWatch, setSavingWatch] = useState(false);
  const [watchModalError, setWatchModalError] = useState("");
  const [toast, setToast] = useState<{ message: string; tone: "success" | "error" | "info" } | null>(null);
  const toastTimerRef = useRef<number | null>(null);

  const showToast = useCallback((message: string, tone: "success" | "error" | "info" = "success") => {
    setToast({ message, tone });
    if (toastTimerRef.current !== null) window.clearTimeout(toastTimerRef.current);
    toastTimerRef.current = window.setTimeout(() => {
      setToast(null);
      toastTimerRef.current = null;
    }, 3800);
  }, []);

  useEffect(() => {
    return () => {
      if (toastTimerRef.current !== null) window.clearTimeout(toastTimerRef.current);
    };
  }, []);

  const search = useCatalogSearch({
    user,
    lastCatalogRefresh,
    searchPreset,
    onUserUpdated,
    onJumpToScheduler,
    onOpenAttrsPanel: () => setAttrsExpanded(true),
  });

  const minorCtrl = useMinorPrefsController({
    user,
    minorPrefs: search.minorPrefs,
    setMinorPrefs: search.setMinorPrefs,
    minorCategories: search.minorCategories,
    setMinorCategories: search.setMinorCategories,
    minorsCatalog: search.minorsCatalog,
    hasNonMinorSearchCriteria: search.hasNonMinorSearchCriteria,
    executeSearch: search.executeSearch,
    clearSearchResults: search.clearSearchResults,
    onExpandMinorPanel: () => setMinorExpanded(true),
    onUserUpdated,
    onError: (msg) => showToast(msg, "error"),
  });

  const handleSelectSubjects = useCallback(
    (nextSubjs: string[]) => {
      search.setSelectedSubjects(nextSubjs);
      if (hasActiveSearchCriteria({ ...search.getCurrentCriteria(), subjects: nextSubjs })) {
        void search.executeSearch({ subjects: nextSubjs });
      } else {
        search.clearSearchResults();
      }
    },
    [search]
  );

  const handleSelectLevelMin = useCallback(
    (val: number | null) => {
      search.setLevelMin(val);
      if (hasActiveSearchCriteria({ ...search.getCurrentCriteria(), levelMin: val })) {
        void search.executeSearch({ levelMin: val });
      } else {
        search.clearSearchResults();
      }
    },
    [search]
  );

  const handleClearMinCredits = useCallback(() => {
    search.setMinCredits(null);
    if (hasActiveSearchCriteria({ ...search.getCurrentCriteria(), minCredits: null })) {
      void search.executeSearch({ minCredits: null });
    } else {
      search.clearSearchResults();
    }
  }, [search]);

  const handleChangeCurriculum = useCallback(
    (curr: CSCurriculumMode) => {
      search.setCurriculum(curr);
      void search.executeSearch({ curriculum: curr });
    },
    [search]
  );

  const handleToggle2000TE = useCallback(
    (val: boolean) => {
      search.setInclude2000TE(val);
      void search.executeSearch({ include2000TE: val });
    },
    [search]
  );

  const handleToggleResearchTE = useCallback(
    (val: boolean) => {
      search.setIncludeResearchTE(val);
      void search.executeSearch({ includeResearchTE: val });
    },
    [search]
  );

  const handleToggleOnlyEligible = useCallback(
    (val: boolean) => {
      search.setOnlyEligible(val);
      if (hasActiveSearchCriteria({ ...search.getCurrentCriteria(), onlyEligible: val })) {
        void search.executeSearch({ onlyEligible: val });
      } else {
        search.clearSearchResults();
      }
    },
    [search]
  );

  const handleToggleIthacaOrVirtual = useCallback(
    (val: boolean) => {
      search.setIthacaOrVirtual(val);
      if (search.hasSearchedRef.current || hasActiveSearchCriteria(search.getCurrentCriteria())) {
        void search.executeSearch({ ithacaOrVirtual: val });
      }
    },
    [search]
  );

  const handleClearAllFilters = useCallback(() => {
    search.resetAllSearchFilters();
    minorCtrl.clearSelectedMinorSilent();
    onClearSearchPreset?.();
  }, [search, minorCtrl, onClearSearchPreset]);

  function openSectionDraft(course: CourseSummary, section: CourseSection) {
    const hasLinkedComp = section.components_required.length > 1;
    setWatchModalError("");
    setDraft({
      course,
      section,
      mode: hasLinkedComp ? "linked_group" : "exact",
      componentFilter: "",
      triggerOn: "open",
      autoPause: false,
      cooldownSec: 60,
      priority: user.role === "admin" ? 2 : 1,
      groupKey: "",
    });
  }

  function openCourseDraft(course: CourseSummary) {
    setWatchModalError("");
    setDraft({
      course,
      section: null,
      mode: "any_section",
      componentFilter: "",
      triggerOn: "open",
      autoPause: false,
      cooldownSec: 60,
      priority: user.role === "admin" ? 2 : 1,
      groupKey: "",
    });
  }

  async function submitWatch(e: React.FormEvent) {
    e.preventDefault();
    if (!draft) return;
    setSavingWatch(true);
    setWatchModalError("");
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
        ithaca_or_virtual: draft.mode === "any_section" ? search.ithacaOrVirtual : false,
        group_key: draft.groupKey.trim(),
      });
      const label = `${draft.course.subject} ${draft.course.catalog_nbr}${
        draft.section ? ` #${draft.section.class_nbr}` : " (any section)"
      }`;
      setDraft(null);
      showToast(`Armed watch for ${label}`, "success");
      onWatchCreated();
    } catch (err) {
      setWatchModalError(err instanceof Error ? err.message : "Failed to create watch");
    } finally {
      setSavingWatch(false);
    }
  }

  const refreshIfSearched = useCallback(() => {
    if (search.hasSearchedRef.current || hasActiveSearchCriteria(search.getCurrentCriteria())) {
      void search.executeSearch({ silent: true });
    }
  }, [search]);

  return (
    <div className="space-y-4">
      <SearchFilterHeader
        user={user}
        rosters={search.rosters}
        selectedRoster={search.selectedRoster}
        subjects={search.subjects}
        selectedSubjects={search.selectedSubjects}
        query={search.query}
        majorMode={search.majorMode}
        showCsFeatures={search.showCsFeatures}
        showIlrFeatures={search.showIlrFeatures}
        csRequirement={search.csRequirement}
        levelMin={search.levelMin}
        minCredits={search.minCredits}
        curriculum={search.curriculum}
        include2000TE={search.include2000TE}
        includeResearchTE={search.includeResearchTE}
        ilrCodes={search.ilrCodes}
        ilrMatch={search.ilrMatch}
        ilrMultiOnly={search.ilrMultiOnly}
        ilrSummary={search.ilrSummary}
        loadingIlrSummary={search.loadingIlrSummary}
        syncingIlrPriority={search.syncingIlrPriority}
        onlyEligible={search.onlyEligible}
        ithacaOrVirtual={search.ithacaOrVirtual}
        selectedAttrs={search.selectedAttrs}
        attrMatch={search.attrMatch}
        attrsExpanded={attrsExpanded}
        attrOptions={search.attrOptions}
        minorPrefs={search.minorPrefs}
        minorCategories={search.minorCategories}
        minorExpanded={minorExpanded}
        minorsCatalog={search.minorsCatalog}
        loadingMinorsCatalog={search.loadingMinorsCatalog}
        savingMinorPrefs={minorCtrl.savingMinorPrefs}
        fitsActiveSchedule={search.fitsActiveSchedule}
        activeSchedule={search.activeSchedule}
        loadingScheduleFit={search.loadingScheduleFit}
        searchMeta={search.searchMeta}
        catalogStatus={search.catalogStatus}
        searchPreset={searchPreset}
        loading={search.loading}
        onSubmitSearch={(e) => {
          e.preventDefault();
          void search.executeSearch();
        }}
        onChangeMajorMode={search.handleChangeMajorMode}
        onSelectCsRequirement={search.handleModeSelect}
        onApplyIlrFilters={search.applyIlrFilters}
        onToggleIlrCode={search.handleToggleIlrCode}
        onSyncIlrPrioritySubjects={() => {
          if (search.selectedRoster) {
            void search.loadIlrSummary(search.selectedRoster, search.ithacaOrVirtual, true);
          }
        }}
        onSelectRoster={search.handleSelectRoster}
        onSelectSubjects={handleSelectSubjects}
        onChangeQuery={search.setQuery}
        onSelectLevelMin={handleSelectLevelMin}
        onClearMinCredits={handleClearMinCredits}
        onChangeCurriculum={handleChangeCurriculum}
        onToggle2000TE={handleToggle2000TE}
        onToggleResearchTE={handleToggleResearchTE}
        onToggleOnlyEligible={handleToggleOnlyEligible}
        onToggleIthacaOrVirtual={handleToggleIthacaOrVirtual}
        onToggleFitsActiveSchedule={() => search.setFitsActiveSchedule((v) => !v)}
        onToggleAttrsExpanded={() => setAttrsExpanded((v) => !v)}
        onChangeAttrMatch={(m) => {
          search.setAttrMatch(m);
          if (search.selectedAttrs.length > 0) void search.executeSearch({ attrMatch: m });
        }}
        onToggleAttr={search.handleToggleAttr}
        onClearAttrs={search.handleClearAttrs}
        onToggleMinorExpanded={() => setMinorExpanded((v) => !v)}
        onSelectMinor={minorCtrl.handleSelectMinor}
        onSelectMinorVersion={minorCtrl.handleSelectMinorVersion}
        onToggleMinorFilterCategory={minorCtrl.handleToggleMinorFilterCategory}
        onClearMinorFilterCategories={minorCtrl.handleClearMinorFilterCategories}
        onToggleMinorCompletedCategory={minorCtrl.handleToggleMinorCompletedCategory}
        onSetMinorHideCompleted={minorCtrl.handleSetMinorHideCompleted}
        onApplyMinorAutoFill={minorCtrl.handleApplyMinorAutoFill}
        onClearMinorCompleted={minorCtrl.handleClearMinorCompleted}
        onOpenPrereqs={() => setPrereqsModalOpen(true)}
        onOpenTranscript={() => setTranscriptOpen(true)}
        onOpenChecklist={onOpenChecklist}
        onClearSearchPreset={onClearSearchPreset}
        onClearAllFilters={handleClearAllFilters}
      />

      {search.error && (
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-300">
          {search.error}
        </div>
      )}

      {search.onlyEligible && (user.completed_courses?.length ?? 0) === 0 && search.courses.length > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-sky-500/30 bg-sky-500/10 px-4 py-2.5 text-xs text-sky-200">
          <span>No completed courses saved yet — showing only classes with no explicit required prerequisites.</span>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => setPrereqsModalOpen(true)}
              className="rounded-lg border border-sky-400/40 bg-sky-500/20 px-2.5 py-1 text-[11px] font-semibold text-white hover:bg-sky-500/30"
            >
              Select My Prereqs
            </button>
            <button
              type="button"
              onClick={() => setTranscriptOpen(true)}
              className="inline-flex items-center gap-1 rounded-lg border border-emerald-500/45 bg-emerald-500/20 px-2.5 py-1 text-[11px] font-semibold text-emerald-100 hover:bg-emerald-500/30"
            >
              <FileUp className="h-3 w-3" />
              Import Transcript
            </button>
          </div>
        </div>
      )}

      {!search.loading &&
        search.courses.length === 0 &&
        search.ithacaOrVirtual &&
        (search.searchMeta?.filtered_out_location_count ?? 0) > 0 && (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
            <div className="flex items-center gap-2">
              <MapPin className="h-4 w-4 shrink-0 text-amber-300" />
              <span>
                {search.searchMeta!.filtered_out_location_count} matching course
                {search.searchMeta!.filtered_out_location_count === 1 ? " was" : "s were"} hidden because{" "}
                {search.searchMeta!.filtered_out_location_count === 1 ? "it is" : "they are"} only offered at{" "}
                <span className="font-semibold text-white">
                  {(search.searchMeta?.filtered_out_locations || []).join(", ") || "an off-campus location"}
                </span>{" "}
                (not Ithaca or purely virtual).
              </span>
            </div>
            <button
              type="button"
              onClick={() => handleToggleIthacaOrVirtual(false)}
              className="rounded-lg border border-amber-400/40 bg-amber-500/20 px-3 py-1.5 text-xs font-semibold text-white hover:bg-amber-500/30"
            >
              Show All Locations
            </button>
          </div>
        )}

      {search.courses.length > 0 && (
        <SearchResultsToolbar
          statusFilter={search.statusFilter}
          onChangeStatusFilter={search.setStatusFilter}
          filterCounts={search.filterCounts}
          ithacaOrVirtual={search.ithacaOrVirtual}
          searchMeta={search.searchMeta}
          filteredCount={search.filteredCourses.length}
          totalLoadedCount={search.courses.length}
          staleVisibleCount={search.staleVisibleCount}
          onShowAllLocations={() => handleToggleIthacaOrVirtual(false)}
        />
      )}

      <div className="space-y-3">
        {search.filteredCourses.map((course) => {
          const cacheKey = courseCacheKey(course);
          return (
            <CourseResultCard
              key={cacheKey}
              course={course}
              isOpen={Boolean(search.expanded[cacheKey])}
              showCsFeatures={search.showCsFeatures}
              showIlrFeatures={search.showIlrFeatures}
              csRequirement={search.csRequirement}
              ilrCodes={search.ilrCodes}
              minorCategories={search.minorCategories}
              selectedAttrs={search.selectedAttrs}
              fitsActiveSchedule={search.fitsActiveSchedule}
              scheduleFit={search.scheduleFitMap.get(cacheKey)}
              scheduleStatus={search.scheduledStatus[cacheKey]}
              insights={search.insightsMap[cacheKey]}
              insightsLoading={Boolean(search.insightsLoading[cacheKey])}
              insightsError={search.insightsError[cacheKey]}
              onToggle={search.toggleCourse}
              onQuickAddSchedule={(c) => void search.handleQuickAddSchedule(c)}
              onWatchCourse={openCourseDraft}
              onWatchSection={openSectionDraft}
              onRefreshInsights={(c) => void search.loadInsights(c, true)}
            />
          );
        })}
      </div>

      <ArmWatchModal
        draft={draft}
        user={user}
        saving={savingWatch}
        error={watchModalError}
        ithacaOrVirtual={search.ithacaOrVirtual}
        onChangeDraft={setDraft}
        onClose={() => {
          setDraft(null);
          setWatchModalError("");
        }}
        onSubmit={submitWatch}
      />

      <CompletedPrereqsModal
        isOpen={prereqsModalOpen}
        roster={search.selectedRoster}
        initialCompleted={user.completed_courses || []}
        initialIncludeImplied={user.include_implied_prereqs ?? true}
        majorMode={search.majorMode}
        showCsFeatures={search.showCsFeatures}
        onClose={() => setPrereqsModalOpen(false)}
        onOpenTranscriptImport={() => {
          setPrereqsModalOpen(false);
          setTranscriptOpen(true);
        }}
        onSaved={(res) => {
          onUserUpdated?.({
            ...user,
            completed_courses: res.completed_courses,
            include_implied_prereqs: res.include_implied_prereqs,
          });
          refreshIfSearched();
        }}
      />

      {transcriptOpen && (
        <TranscriptImportModal
          rosters={search.rosters}
          activeRoster={search.selectedRoster}
          existingCompleted={user.completed_courses || []}
          existingDetails={user.completed_course_details || {}}
          onClose={() => setTranscriptOpen(false)}
          onImported={(result, nextChecklist) => {
            onUserUpdated?.({
              ...user,
              completed_courses: nextChecklist.completed_courses,
              completed_course_details: nextChecklist.completed_course_details,
              in_progress_courses: nextChecklist.in_progress_courses,
              in_progress_course_details: nextChecklist.in_progress_course_details,
            });
            const summary = result.import_summary;
            const parts: string[] = [];
            if (summary.added_completed.length > 0) {
              parts.push(`${summary.added_completed.length} new completed course(s)`);
            }
            if ((summary.added_in_progress?.length ?? 0) > 0) {
              parts.push(`${summary.added_in_progress!.length} currently taking course(s)`);
            }
            if (summary.enriched_completed.length > 0) {
              parts.push(`${summary.enriched_completed.length} course detail(s) updated`);
            }
            if (summary.scheduler.length > 0) {
              const totalAdded = summary.scheduler.reduce((sum, s) => sum + s.added.length, 0);
              const totalUpdated = summary.scheduler.reduce((sum, s) => sum + s.updated.length, 0);
              parts.push(
                `${summary.scheduler.length} schedule(s) synced (${totalAdded} added, ${totalUpdated} updated)`
              );
            }
            showToast(
              parts.length > 0
                ? `Transcript imported: ${parts.join(", ")}.`
                : "Transcript checked — your completed courses & schedules are already up to date.",
              "success"
            );
            refreshIfSearched();
          }}
        />
      )}

      <FloatingToast
        message={toast?.message ?? null}
        tone={toast?.tone ?? "info"}
        onDismiss={() => setToast(null)}
      />
    </div>
  );
}
