import React, { useEffect, useRef, useState } from "react";
import {
  Award,
  CalendarCheck2,
  ChevronDown,
  FileUp,
  Filter,
  GraduationCap,
  ListChecks,
  Loader2,
  MapPin,
  Search,
  SlidersHorizontal,
  UserCheck,
  X,
} from "lucide-react";
import type {
  AttributeOption,
  AttrMatchMode,
  CatalogStatus,
  CourseSearchPreset,
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
} from "../../types";
import { IlrDistributionExplorer } from "../IlrDistributionExplorer";
import { MinorFilterPanel } from "../MinorFilterPanel";
import { MultiSubjectSelect } from "../MultiSubjectSelect";
import { AttributeFilterPanel } from "./AttributeFilterPanel";

export const CS_REQUIREMENT_MODES: Array<{ id: CSRequirementMode; label: string; hint: string }> = [
  { id: "", label: "All Courses", hint: "Full Cornell catalog" },
  { id: "cs_elective", label: "CS Electives", hint: "4000+ CS (≥3 cr, letter)" },
  { id: "cs_project", label: "CS Project", hint: "4xx1 Practicum / Project" },
  { id: "tech_elective", label: "Tech Electives", hint: "3000+ w/ qualifying prereqs" },
  { id: "external_spec", label: "External Spec", hint: "Non-CS topic area (3000+)" },
];

interface Props {
  user: User;
  rosters: Roster[];
  selectedRoster: string;
  subjects: Subject[];
  selectedSubjects: string[];
  query: string;
  majorMode: MajorMode;
  showCsFeatures: boolean;
  showIlrFeatures: boolean;
  csRequirement: CSRequirementMode;
  levelMin: number | null;
  minCredits: number | null;
  curriculum: CSCurriculumMode;
  include2000TE: boolean;
  includeResearchTE: boolean;
  ilrCodes: string[];
  ilrMatch: IlrMatchMode;
  ilrMultiOnly: boolean;
  ilrSummary: IlrSummaryResponse | null;
  loadingIlrSummary: boolean;
  syncingIlrPriority: boolean;
  onlyEligible: boolean;
  ithacaOrVirtual: boolean;
  selectedAttrs: string[];
  attrMatch: AttrMatchMode;
  attrsExpanded: boolean;
  attrOptions: AttributeOption[];
  minorPrefs: MinorPrefs;
  minorCategories: string[];
  minorExpanded: boolean;
  minorsCatalog: MinorCatalogItem[];
  loadingMinorsCatalog: boolean;
  savingMinorPrefs: boolean;
  fitsActiveSchedule: boolean;
  activeSchedule: HydratedSchedule | null;
  loadingScheduleFit: boolean;
  searchMeta: SearchCoursesMeta | null;
  catalogStatus: CatalogStatus | null;
  searchPreset?: CourseSearchPreset | null;
  loading: boolean;
  onSubmitSearch: (e: React.FormEvent) => void;
  onChangeMajorMode: (mode: MajorMode) => void;
  onSelectCsRequirement: (mode: CSRequirementMode) => void;
  onApplyIlrFilters: (codes: string[], match: IlrMatchMode, multiOnly: boolean) => void;
  onToggleIlrCode: (code: string) => void;
  onSyncIlrPrioritySubjects: () => void;
  onSelectRoster: (roster: string) => void;
  onSelectSubjects: (subjs: string[]) => void;
  onChangeQuery: (q: string) => void;
  onSelectLevelMin: (val: number | null) => void;
  onClearMinCredits: () => void;
  onChangeCurriculum: (curr: CSCurriculumMode) => void;
  onToggle2000TE: (val: boolean) => void;
  onToggleResearchTE: (val: boolean) => void;
  onToggleOnlyEligible: (val: boolean) => void;
  onToggleIthacaOrVirtual: (val: boolean) => void;
  onToggleFitsActiveSchedule: () => void;
  onToggleAttrsExpanded: () => void;
  onChangeAttrMatch: (mode: AttrMatchMode) => void;
  onToggleAttr: (code: string) => void;
  onClearAttrs: () => void;
  onToggleMinorExpanded: () => void;
  onSelectMinor: (minorId: string) => void;
  onSelectMinorVersion: (verId: string) => void;
  onSelectMinorCollege: (collegeId: string) => void;
  onToggleMinorFilterCategory: (catId: string) => void;
  onClearMinorFilterCategories: () => void;
  onToggleMinorCompletedCategory: (catId: string) => void;
  onSetMinorHideCompleted: (hide: boolean) => void;
  onApplyMinorAutoFill: (catIds: string[]) => void;
  onClearMinorCompleted: () => void;
  onOpenPrereqs: () => void;
  onOpenTranscript: () => void;
  onOpenChecklist?: (roster?: string) => void;
  onClearSearchPreset?: () => void;
  onClearAllFilters: () => void;
}

export function SearchFilterHeader(props: Props) {
  const {
    user,
    rosters,
    selectedRoster,
    subjects,
    selectedSubjects,
    query,
    majorMode,
    showCsFeatures,
    showIlrFeatures,
    csRequirement,
    levelMin,
    minCredits,
    curriculum,
    include2000TE,
    includeResearchTE,
    ilrCodes,
    ilrMatch,
    ilrMultiOnly,
    ilrSummary,
    loadingIlrSummary,
    syncingIlrPriority,
    onlyEligible,
    ithacaOrVirtual,
    selectedAttrs,
    attrMatch,
    attrsExpanded,
    attrOptions,
    minorPrefs,
    minorCategories,
    minorExpanded,
    minorsCatalog,
    loadingMinorsCatalog,
    savingMinorPrefs,
    fitsActiveSchedule,
    activeSchedule,
    loadingScheduleFit,
    searchMeta,
    catalogStatus,
    searchPreset,
    loading,
  } = props;

  const [profileMenuOpen, setProfileMenuOpen] = useState(false);
  const [moreFiltersOpen, setMoreFiltersOpen] = useState(false);
  const profileMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!profileMenuOpen) return;
    function onDocClick(ev: MouseEvent) {
      if (profileMenuRef.current && !profileMenuRef.current.contains(ev.target as Node)) {
        setProfileMenuOpen(false);
      }
    }
    function onKeyDown(ev: KeyboardEvent) {
      if (ev.key === "Escape") setProfileMenuOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [profileMenuOpen]);

  const syncedSubjectsCount = searchMeta?.synced_subjects ?? catalogStatus?.synced_subjects ?? 0;
  const totalSubjectsCount = searchMeta?.total_subjects ?? catalogStatus?.total_subjects ?? 0;
  const completedCount = user.completed_courses?.length ?? 0;
  const selectedMinorObj = minorsCatalog.find((m) => m.id === minorPrefs.selected_minor);
  const minorLabel = selectedMinorObj?.short_label || minorPrefs.selected_minor;

  const advancedCount =
    (levelMin ? 1 : 0) +
    (!ithacaOrVirtual ? 1 : 0) +
    (minCredits != null && minCredits > 0 ? 1 : 0) +
    (showCsFeatures && csRequirement === "cs_elective" && curriculum === "pre2024" ? 1 : 0);

  const hasHiddenChips =
    Boolean(searchPreset) ||
    (minCredits != null && minCredits > 0) ||
    (!moreFiltersOpen && Boolean(levelMin)) ||
    (!moreFiltersOpen && !ithacaOrVirtual);

  const hasAnyResettable =
    hasHiddenChips ||
    (showCsFeatures && csRequirement !== "") ||
    (showIlrFeatures && (ilrCodes.length > 0 || ilrMultiOnly)) ||
    selectedSubjects.length > 0 ||
    selectedAttrs.length > 0 ||
    Boolean(minorPrefs.selected_minor) ||
    onlyEligible ||
    fitsActiveSchedule ||
    Boolean(query.trim());

  return (
    <form onSubmit={props.onSubmitSearch} className="space-y-2.5 rounded-2xl border border-zinc-800 bg-zinc-900/80 p-3.5">
      {/* Row 1: Search Input + Semester + Search + Compact Mode & Profile */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-[210px] flex-1">
          <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-zinc-500" />
          <input
            type="text"
            value={query}
            onChange={(e) => props.onChangeQuery(e.target.value)}
            placeholder={
              showIlrFeatures
                ? "Search course, keyword, or class # (e.g. ILRGL 2390)..."
                : "Search course, keyword, instructor, or class # (e.g. CS 2110)..."
            }
            className="w-full rounded-xl border border-zinc-700 bg-zinc-950 py-2 pl-9 pr-3 text-sm text-white placeholder-zinc-500 focus:border-emerald-500 focus:outline-none"
          />
        </div>

        <select
          value={selectedRoster}
          onChange={(e) => props.onSelectRoster(e.target.value)}
          aria-label="Semester"
          className="rounded-xl border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-white focus:border-emerald-500 focus:outline-none"
        >
          {rosters.map((r) => (
            <option key={r.slug} value={r.slug}>
              {r.descr} ({r.slug})
            </option>
          ))}
        </select>

        <button
          type="submit"
          disabled={loading}
          className="inline-flex items-center gap-1.5 rounded-xl bg-emerald-500 px-4 py-2 text-sm font-semibold text-zinc-950 hover:bg-emerald-400 disabled:opacity-50"
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Search"}
        </button>

        {/* Compact Mode Switcher */}
        <div
          role="group"
          aria-label="Major mode"
          className="inline-flex items-center rounded-xl border border-zinc-700/80 bg-zinc-950 p-0.5"
        >
          {(
            [
              { id: "none", label: "Gen", title: "Standard Cornell search without major-specific UI" },
              { id: "cs", label: "CS", title: "CS Electives, Technical Electives, and External Spec mode" },
              { id: "ilr", label: "ILR", title: "ILR Distribution Codes, 3 Main Electives & Core mode" },
            ] as const
          ).map((opt) => {
            const active = majorMode === opt.id;
            return (
              <button
                key={opt.id}
                type="button"
                title={opt.title}
                aria-pressed={active}
                onClick={() => props.onChangeMajorMode(opt.id)}
                className={`rounded-lg px-2.5 py-1.5 text-xs font-semibold transition ${
                  active
                    ? opt.id === "ilr"
                      ? "bg-teal-500 text-zinc-950"
                      : opt.id === "cs"
                        ? "bg-emerald-500 text-zinc-950"
                        : "bg-zinc-200 text-zinc-950"
                    : "text-zinc-400 hover:text-zinc-100"
                }`}
              >
                {opt.label}
              </button>
            );
          })}
        </div>

        {/* Academic Profile Menu */}
        <div ref={profileMenuRef} className="relative">
          <button
            type="button"
            aria-expanded={profileMenuOpen}
            onClick={() => setProfileMenuOpen((v) => !v)}
            className={`inline-flex items-center gap-1.5 rounded-xl border px-3 py-2 text-xs font-medium transition ${
              completedCount > 0
                ? "border-sky-500/40 bg-sky-500/15 text-sky-200 hover:bg-sky-500/25"
                : "border-zinc-700 bg-zinc-950 text-zinc-200 hover:border-emerald-500/40"
            }`}
          >
            <UserCheck className="h-3.5 w-3.5 text-emerald-400" />
            <span>Profile ({completedCount})</span>
            <ChevronDown className={`h-3 w-3 transition-transform ${profileMenuOpen ? "rotate-180" : ""}`} />
          </button>

          {profileMenuOpen && (
            <div className="absolute right-0 z-30 mt-1.5 w-60 rounded-xl border border-zinc-700 bg-zinc-900 p-1.5 shadow-2xl">
              <button
                type="button"
                onClick={() => {
                  setProfileMenuOpen(false);
                  props.onOpenPrereqs();
                }}
                className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-xs text-zinc-200 hover:bg-zinc-800"
              >
                <ListChecks className="h-3.5 w-3.5 text-sky-400" />
                <div>
                  <div className="font-medium text-white">Completed Prereqs ({completedCount})</div>
                  <div className="text-[10px] text-zinc-400">Pick completed courses manually</div>
                </div>
              </button>
              <button
                type="button"
                onClick={() => {
                  setProfileMenuOpen(false);
                  props.onOpenTranscript();
                }}
                className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-xs text-zinc-200 hover:bg-zinc-800"
              >
                <FileUp className="h-3.5 w-3.5 text-emerald-400" />
                <div>
                  <div className="font-medium text-white">Import Transcript</div>
                  <div className="text-[10px] text-zinc-400">Local PDF/text transcript sync</div>
                </div>
              </button>
              {showCsFeatures && props.onOpenChecklist && (
                <button
                  type="button"
                  onClick={() => {
                    setProfileMenuOpen(false);
                    props.onOpenChecklist?.(selectedRoster);
                  }}
                  className="flex w-full items-center gap-2 rounded-lg border-t border-zinc-800 px-2.5 py-2 pt-2 text-left text-xs text-emerald-200 hover:bg-zinc-800"
                >
                  <GraduationCap className="h-3.5 w-3.5 text-emerald-400" />
                  <span>Open CS Major Checklist</span>
                </button>
              )}
              {totalSubjectsCount > 0 && (
                <div className="mt-1 border-t border-zinc-800 px-2.5 pt-1.5 text-[10px] text-zinc-500">
                  Catalog cache: {syncedSubjectsCount}/{totalSubjectsCount} subjects
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Mode-Specific Strips (CS Pills or ILR Presets) */}
      {showCsFeatures && (
        <div className="flex flex-wrap items-center gap-1.5">
          {CS_REQUIREMENT_MODES.map((m) => {
            const active = csRequirement === m.id;
            return (
              <button
                key={m.id || "all"}
                type="button"
                title={m.hint}
                onClick={() => props.onSelectCsRequirement(m.id)}
                className={`rounded-lg px-2.5 py-1 text-xs font-medium transition ${
                  active
                    ? "bg-emerald-500 text-zinc-950 font-semibold"
                    : "border border-zinc-800 bg-zinc-950 text-zinc-300 hover:border-emerald-500/40 hover:text-white"
                }`}
              >
                {m.label}
              </button>
            );
          })}
        </div>
      )}

      {showIlrFeatures && (
        <IlrDistributionExplorer
          summary={ilrSummary}
          loadingSummary={loadingIlrSummary}
          syncingPriority={syncingIlrPriority}
          selectedCodes={ilrCodes}
          matchMode={ilrMatch}
          multiOnly={ilrMultiOnly}
          ithacaOrVirtual={ithacaOrVirtual}
          onSelectPreset={(codes, nextMatch = "any", nextMulti = false) =>
            props.onApplyIlrFilters(codes, nextMatch, nextMulti)
          }
          onToggleCode={props.onToggleIlrCode}
          onChangeMatchMode={(nextMatch) => props.onApplyIlrFilters(ilrCodes, nextMatch, ilrMultiOnly)}
          onToggleMultiOnly={() => props.onApplyIlrFilters(ilrCodes, ilrMatch, !ilrMultiOnly)}
          onSyncPrioritySubjects={props.onSyncIlrPrioritySubjects}
        />
      )}

      {/* Row 2: Compact Core Filter Strip */}
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
        <div className="flex flex-wrap items-center gap-2">
          <div className="min-w-[180px] max-w-[240px]">
            <MultiSubjectSelect
              subjects={subjects}
              selected={selectedSubjects}
              excludeSubjects={csRequirement === "external_spec" ? ["CS", "PE"] : []}
              placeholder={
                csRequirement === "cs_elective"
                  ? "Subject: CS"
                  : csRequirement === "external_spec"
                    ? "Pick non-CS subjects..."
                    : "All Subjects"
              }
              onChange={props.onSelectSubjects}
            />
          </div>

          <button
            type="button"
            onClick={() => props.onToggleOnlyEligible(!onlyEligible)}
            aria-pressed={onlyEligible}
            className={`inline-flex items-center gap-1.5 rounded-xl border px-2.5 py-2 text-xs font-medium transition ${
              onlyEligible
                ? "border-emerald-500/50 bg-emerald-500/15 text-emerald-200"
                : "border-zinc-700/80 bg-zinc-950 text-zinc-300 hover:border-zinc-600"
            }`}
            title={
              completedCount === 0
                ? "Add completed courses in Profile to check prereqs"
                : "Only show classes whose required prerequisites you have satisfied"
            }
          >
            Prereqs met
          </button>

          <button
            type="button"
            onClick={props.onToggleFitsActiveSchedule}
            aria-pressed={fitsActiveSchedule}
            className={`inline-flex items-center gap-1.5 rounded-xl border px-2.5 py-2 text-xs font-medium transition ${
              fitsActiveSchedule
                ? "border-sky-500/60 bg-sky-500/20 text-sky-100"
                : "border-zinc-700/80 bg-zinc-950 text-zinc-300 hover:border-sky-500/40"
            }`}
            title="Only show courses fitting your active schedule without time conflicts"
          >
            {loadingScheduleFit ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin text-sky-400" />
            ) : (
              <CalendarCheck2 className={`h-3.5 w-3.5 ${fitsActiveSchedule ? "text-sky-300" : "text-zinc-400"}`} />
            )}
            <span>Fits Schedule{fitsActiveSchedule && activeSchedule ? ` (${activeSchedule.schedule.name})` : ""}</span>
          </button>

          <button
            type="button"
            onClick={props.onToggleAttrsExpanded}
            aria-expanded={attrsExpanded}
            className={`inline-flex items-center gap-1.5 rounded-xl border px-2.5 py-2 text-xs font-medium transition ${
              selectedAttrs.length > 0 || attrsExpanded
                ? "border-violet-500/60 bg-violet-500/20 text-violet-100"
                : "border-zinc-700/80 bg-zinc-950 text-zinc-300 hover:border-violet-500/40"
            }`}
          >
            <Filter className="h-3.5 w-3.5 text-violet-300" />
            <span>Attrs{selectedAttrs.length > 0 ? ` (${selectedAttrs.length})` : ""}</span>
          </button>

          <button
            type="button"
            onClick={props.onToggleMinorExpanded}
            aria-expanded={minorExpanded}
            className={`inline-flex items-center gap-1.5 rounded-xl border px-2.5 py-2 text-xs font-medium transition ${
              minorPrefs.selected_minor || minorExpanded
                ? "border-amber-500/60 bg-amber-500/20 text-amber-100"
                : "border-zinc-700/80 bg-zinc-950 text-zinc-300 hover:border-amber-500/40"
            }`}
          >
            <Award className="h-3.5 w-3.5 text-amber-300" />
            <span>Minor{minorPrefs.selected_minor ? `: ${minorLabel}` : ""}</span>
          </button>

          <button
            type="button"
            onClick={() => setMoreFiltersOpen((v) => !v)}
            aria-expanded={moreFiltersOpen}
            className={`inline-flex items-center gap-1.5 rounded-xl border px-2.5 py-2 text-xs font-medium transition ${
              moreFiltersOpen || advancedCount > 0
                ? "border-zinc-500 bg-zinc-800 text-white"
                : "border-zinc-700/80 bg-zinc-950 text-zinc-300 hover:border-zinc-600"
            }`}
          >
            <SlidersHorizontal className="h-3.5 w-3.5 text-zinc-400" />
            <span>More{advancedCount > 0 ? ` (${advancedCount})` : ""}</span>
          </button>
        </div>

        {hasAnyResettable && (
          <button
            type="button"
            onClick={props.onClearAllFilters}
            className="text-xs text-zinc-400 hover:text-white underline underline-offset-2"
          >
            Reset
          </button>
        )}
      </div>

      {/* Collapsible Secondary Filters (Level, Location Scope, Curriculum, Credits) */}
      {moreFiltersOpen && (
        <div className="flex flex-wrap items-center gap-3 rounded-xl border border-zinc-800 bg-zinc-950/80 px-3 py-2.5 text-xs">
          <div className="flex items-center gap-1.5">
            <span className="text-zinc-400">Level:</span>
            <select
              value={levelMin ?? ""}
              onChange={(e) => props.onSelectLevelMin(e.target.value ? Number(e.target.value) : null)}
              className="rounded-lg border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-white focus:border-emerald-500 focus:outline-none"
            >
              {csRequirement !== "external_spec" && <option value="">Any</option>}
              {csRequirement !== "external_spec" && <option value="2000">2000+</option>}
              <option value="3000">3000+</option>
              <option value="4000">4000+</option>
              <option value="5000">5000+</option>
            </select>
          </div>

          <button
            type="button"
            onClick={() => props.onToggleIthacaOrVirtual(!ithacaOrVirtual)}
            aria-pressed={ithacaOrVirtual}
            className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs font-medium transition ${
              ithacaOrVirtual
                ? "border-emerald-500/50 bg-emerald-500/15 text-emerald-200"
                : "border-amber-500/40 bg-amber-500/15 text-amber-200"
            }`}
          >
            <MapPin className={`h-3.5 w-3.5 ${ithacaOrVirtual ? "text-emerald-400" : "text-amber-300"}`} />
            <span>{ithacaOrVirtual ? "Ithaca + Virtual Only" : "All Campus Locations"}</span>
          </button>

          {showCsFeatures && csRequirement === "cs_elective" && (
            <div className="flex items-center gap-1 rounded-lg border border-zinc-800 bg-zinc-900 p-0.5">
              <button
                type="button"
                onClick={() => props.onChangeCurriculum("current")}
                className={`rounded-md px-2 py-0.5 text-[11px] font-medium ${
                  curriculum === "current" ? "bg-emerald-500/20 text-emerald-300" : "text-zinc-400 hover:text-white"
                }`}
              >
                Post-Fall 2024
              </button>
              <button
                type="button"
                onClick={() => props.onChangeCurriculum("pre2024")}
                className={`rounded-md px-2 py-0.5 text-[11px] font-medium ${
                  curriculum === "pre2024" ? "bg-emerald-500/20 text-emerald-300" : "text-zinc-400 hover:text-white"
                }`}
              >
                Pre-Fall 2024
              </button>
            </div>
          )}

          {showCsFeatures && csRequirement === "tech_elective" && (
            <div className="flex flex-wrap items-center gap-2.5">
              <label className="inline-flex cursor-pointer items-center gap-1.5 text-zinc-300">
                <input
                  type="checkbox"
                  checked={include2000TE}
                  onChange={(e) => props.onToggle2000TE(e.target.checked)}
                  className="accent-amber-400"
                />
                <span>Include 2000+ (warn)</span>
              </label>
              <label className="inline-flex cursor-pointer items-center gap-1.5 text-zinc-300">
                <input
                  type="checkbox"
                  checked={includeResearchTE}
                  onChange={(e) => props.onToggleResearchTE(e.target.checked)}
                  className="accent-amber-400"
                />
                <span>Include CS 4999</span>
              </label>
            </div>
          )}

          {minCredits != null && minCredits > 0 && (
            <button
              type="button"
              onClick={props.onClearMinCredits}
              className="inline-flex items-center gap-1 rounded-lg border border-emerald-500/40 bg-emerald-500/15 px-2 py-1 text-xs text-emerald-200 hover:bg-emerald-500/25"
            >
              Min {minCredits} cr <X className="h-3 w-3" />
            </button>
          )}
        </div>
      )}

      {/* Drawers */}
      {attrsExpanded && (
        <AttributeFilterPanel
          attrOptions={attrOptions}
          selectedAttrs={selectedAttrs}
          attrMatch={attrMatch}
          onChangeAttrMatch={props.onChangeAttrMatch}
          onToggleAttr={props.onToggleAttr}
          onClearAttrs={props.onClearAttrs}
        />
      )}

      {minorExpanded && (
        <MinorFilterPanel
          minors={minorsCatalog}
          loadingCatalog={loadingMinorsCatalog}
          selectedMinor={minorPrefs.selected_minor}
          selectedVersion={minorPrefs.selected_minor ? minorPrefs.versions[minorPrefs.selected_minor] || "" : ""}
          selectedCollege={
            minorPrefs.selected_minor ? minorPrefs.colleges?.[minorPrefs.selected_minor] || "" : ""
          }
          selectedCategories={minorCategories}
          completedCategories={
            minorPrefs.selected_minor ? minorPrefs.completed_categories[minorPrefs.selected_minor] || [] : []
          }
          hideCompleted={minorPrefs.hide_completed}
          savingPrefs={savingMinorPrefs}
          onSelectMinor={props.onSelectMinor}
          onSelectVersion={props.onSelectMinorVersion}
          onSelectCollege={props.onSelectMinorCollege}
          onToggleFilterCategory={props.onToggleMinorFilterCategory}
          onClearFilterCategories={props.onClearMinorFilterCategories}
          onToggleCompletedCategory={props.onToggleMinorCompletedCategory}
          onSetHideCompleted={props.onSetMinorHideCompleted}
          onApplyAutoFill={props.onApplyMinorAutoFill}
          onClearCompleted={props.onClearMinorCompleted}
        />
      )}

      {/* Hidden / Non-Obvious Filter Chips Only */}
      {hasHiddenChips && (
        <div className="flex flex-wrap items-center gap-1.5 border-t border-zinc-800/80 pt-2 text-[11px]">
          {searchPreset && (
            <HiddenFilterChip
              label={`From Checklist: ${searchPreset.label || "Preset"}`}
              tone="emerald"
              onRemove={() => props.onClearSearchPreset?.()}
            />
          )}
          {minCredits != null && minCredits > 0 && (
            <HiddenFilterChip
              label={`Min ${minCredits} cr`}
              tone="emerald"
              onRemove={props.onClearMinCredits}
            />
          )}
          {!moreFiltersOpen && levelMin && (
            <HiddenFilterChip
              label={`Level ${levelMin}+`}
              tone="zinc"
              onRemove={() => props.onSelectLevelMin(null)}
            />
          )}
          {!moreFiltersOpen && !ithacaOrVirtual && (
            <HiddenFilterChip
              label="Incl. Off-Campus"
              tone="amber"
              onRemove={() => props.onToggleIthacaOrVirtual(true)}
            />
          )}
        </div>
      )}
    </form>
  );
}

function HiddenFilterChip({
  label,
  tone,
  onRemove,
}: {
  label: string;
  tone: "emerald" | "amber" | "zinc";
  onRemove: () => void;
}) {
  const styles = {
    emerald: "border-emerald-500/35 bg-emerald-500/10 text-emerald-200",
    amber: "border-amber-500/35 bg-amber-500/10 text-amber-200",
    zinc: "border-zinc-700 bg-zinc-800/80 text-zinc-200",
  }[tone];

  return (
    <span className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 font-medium ${styles}`}>
      <span>{label}</span>
      <button
        type="button"
        onClick={onRemove}
        aria-label={`Remove ${label} filter`}
        className="rounded p-0.5 opacity-80 hover:bg-black/20 hover:opacity-100"
      >
        <X className="h-3 w-3" />
      </button>
    </span>
  );
}
