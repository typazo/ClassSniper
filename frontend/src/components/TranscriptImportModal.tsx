import React, { useMemo, useState } from "react";
import {
  AlertCircle,
  Calendar,
  Check,
  CheckCircle2,
  Eye,
  FileText,
  FileUp,
  Loader2,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react";
import { api } from "../api/client";
import type {
  CsChecklistPayload,
  ImportTranscriptRequest,
  ImportTranscriptResponse,
  Roster,
} from "../types";
import {
  extractTranscriptTextFromPdf,
  parseCornellTranscriptText,
  type ParsedExcludedCourse,
} from "../utils/transcriptParser";

interface ReviewCompletedRow {
  course: string;
  sem: string;
  gr: string;
  cr: string;
  selected: boolean;
}

interface ReviewInProgressRow {
  course: string;
  roster: string;
  cr: string;
  selected: boolean;
}

interface Props {
  rosters: Roster[];
  activeRoster: string;
  existingCompleted: string[];
  existingDetails?: Record<string, { gr?: string; sem?: string; cr?: string }>;
  onClose: () => void;
  onImported: (result: ImportTranscriptResponse, nextChecklist: CsChecklistPayload) => void;
}

const REGULAR_ROSTER_RE = /^(?:FA|SP|WI|SU)\d{2}$/;
const SEASON_ORDER: Record<string, number> = { WI: 0, SP: 1, SU: 2, FA: 3 };

function compareRostersAsc(a: string, b: string): number {
  const au = a.toUpperCase();
  const bu = b.toUpperCase();
  const ay = REGULAR_ROSTER_RE.test(au) ? Number(au.slice(2)) : 9999;
  const by = REGULAR_ROSTER_RE.test(bu) ? Number(bu.slice(2)) : 9999;
  if (ay !== by) return ay - by;
  const as = SEASON_ORDER[au.slice(0, 2)] ?? 9;
  const bs = SEASON_ORDER[bu.slice(0, 2)] ?? 9;
  if (as !== bs) return as - bs;
  return au.localeCompare(bu);
}

export const TranscriptImportModal: React.FC<Props> = ({
  rosters,
  activeRoster,
  existingCompleted,
  existingDetails = {},
  onClose,
  onImported,
}) => {
  const [pastedText, setPastedText] = useState("");
  const [parsing, setParsing] = useState(false);
  const [parseError, setParseError] = useState("");
  const [fileName, setFileName] = useState("");
  const [dragging, setDragging] = useState(false);

  const [completedRows, setCompletedRows] = useState<ReviewCompletedRow[]>([]);
  const [inProgressRows, setInProgressRows] = useState<ReviewInProgressRow[]>([]);
  const [excludedRows, setExcludedRows] = useState<ParsedExcludedCourse[]>([]);
  const [detectedPe, setDetectedPe] = useState(0);
  const [applyPe, setApplyPe] = useState(true);
  const [includeGradesAndTerms, setIncludeGradesAndTerms] = useState(true);
  const [syncInProgressToChecklist, setSyncInProgressToChecklist] = useState(true);
  const [syncPastToScheduler, setSyncPastToScheduler] = useState(true);
  const [hasParsed, setHasParsed] = useState(false);

  const [importing, setImporting] = useState(false);
  const [importError, setImportError] = useState("");
  const [importResult, setImportResult] = useState<ImportTranscriptResponse | null>(null);

  const rosterSlugs = useMemo(() => rosters.map((r) => r.slug.toUpperCase()), [rosters]);
  const existingSet = useMemo(
    () => new Set(existingCompleted.map((c) => c.toUpperCase())),
    [existingCompleted]
  );

  const applyParsedText = (text: string) => {
    const parsed = parseCornellTranscriptText(text);
    if (
      parsed.completed.length === 0 &&
      parsed.inProgress.length === 0 &&
      parsed.excluded.length === 0 &&
      parsed.detectedPeCount === 0
    ) {
      setParseError(
        "No Cornell course rows were detected. Make sure you dropped an unofficial Cornell transcript PDF or pasted text containing course codes (e.g. CS 2110, MATH 1120)."
      );
      return;
    }
    setParseError("");
    setCompletedRows(parsed.completed.map((c) => ({ ...c, selected: true })));
    setInProgressRows(
      parsed.inProgress.map((c) => ({
        ...c,
        roster: c.roster || activeRoster || rosterSlugs[0] || "",
        selected: true,
      }))
    );
    setExcludedRows(parsed.excluded);
    setDetectedPe(parsed.detectedPeCount);
    setApplyPe(parsed.detectedPeCount > 0);
    setHasParsed(true);
    setImportResult(null);
    // Discard raw pasted text from React state once parsed locally
    setPastedText("");
  };

  const handleFile = async (file: File | undefined) => {
    if (!file) return;
    setParsing(true);
    setParseError("");
    setFileName(file.name);
    try {
      const lower = file.name.toLowerCase();
      if (lower.endsWith(".pdf") || file.type === "application/pdf") {
        const text = await extractTranscriptTextFromPdf(file);
        applyParsedText(text);
      } else {
        const text = await file.text();
        applyParsedText(text);
      }
    } catch (err) {
      setParseError(
        err instanceof Error
          ? `Could not read PDF locally: ${err.message}`
          : "Could not read transcript file locally."
      );
    } finally {
      setParsing(false);
    }
  };

  const regularPastSemesters = useMemo(() => {
    const sems = new Set<string>();
    for (const r of completedRows) {
      if (!r.selected) continue;
      const semU = r.sem.trim().toUpperCase();
      if (REGULAR_ROSTER_RE.test(semU)) sems.add(semU);
    }
    return Array.from(sems).sort(compareRostersAsc);
  }, [completedRows]);

  const outgoingPayload: ImportTranscriptRequest = useMemo(() => {
    return {
      roster: activeRoster || undefined,
      completed_courses: completedRows
        .filter((r) => r.selected)
        .map((r) =>
          includeGradesAndTerms
            ? { course: r.course, sem: r.sem, gr: r.gr, cr: r.cr }
            : { course: r.course, sem: "", gr: "", cr: r.cr }
        ),
      in_progress_courses: inProgressRows
        .filter((r) => r.selected && r.roster.trim())
        .map((r) => ({
          course: r.course,
          roster: r.roster.trim().toUpperCase(),
          cr: r.cr,
        })),
      ...(syncPastToScheduler && regularPastSemesters.length > 0
        ? {
            past_schedule_courses: completedRows
              .filter((r) => r.selected && REGULAR_ROSTER_RE.test(r.sem.trim().toUpperCase()))
              .map((r) => ({
                course: r.course,
                roster: r.sem.trim().toUpperCase(),
                cr: r.cr,
              })),
          }
        : {}),
      sync_in_progress_to_checklist: syncInProgressToChecklist,
      sync_completed_to_scheduler: syncPastToScheduler,
      ...(applyPe && detectedPe > 0 ? { pe_completed: detectedPe } : {}),
    };
  }, [
    activeRoster,
    completedRows,
    inProgressRows,
    regularPastSemesters.length,
    includeGradesAndTerms,
    syncInProgressToChecklist,
    syncPastToScheduler,
    applyPe,
    detectedPe,
  ]);

  const handleImport = async () => {
    setImporting(true);
    setImportError("");
    try {
      const res = await api.importTranscript(outgoingPayload);
      setImportResult(res);
      onImported(res, res.checklist);
    } catch (err) {
      setImportError(err instanceof Error ? err.message : "Failed to import parsed courses");
    } finally {
      setImporting(false);
    }
  };

  const selectedCompletedCount = completedRows.filter((r) => r.selected).length;
  const selectedInProgressCount = inProgressRows.filter((r) => r.selected && r.roster.trim()).length;

  const groupedInProgress = useMemo(() => {
    const groups = new Map<string, Array<{ row: ReviewInProgressRow; idx: number }>>();
    inProgressRows.forEach((row, idx) => {
      const key = row.roster.trim().toUpperCase() || "UNASSIGNED";
      const list = groups.get(key) || [];
      list.push({ row, idx });
      groups.set(key, list);
    });
    return Array.from(groups.entries());
  }, [inProgressRows]);

  const targetSchedulerRosters = useMemo(() => {
    const set = new Set<string>();
    for (const r of inProgressRows) {
      if (r.selected && r.roster.trim()) set.add(r.roster.trim().toUpperCase());
    }
    return Array.from(set);
  }, [inProgressRows]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm">
      <div className="flex max-h-[90vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-zinc-800 bg-zinc-900 shadow-2xl">
        {/* Header */}
        <div className="flex items-start justify-between gap-3 border-b border-zinc-800 px-5 py-4">
          <div>
            <div className="flex items-center gap-2">
              <ShieldCheck className="h-5 w-5 text-emerald-400" />
              <h3 className="text-base font-bold text-white">
                Import Cornell Unofficial Transcript
              </h3>
            </div>
            <p className="mt-0.5 text-xs text-zinc-400">
              Auto-populate completed courses (with grades) on your CS Checklist and sync current
              courses into Scheduler.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-zinc-400 hover:bg-zinc-800 hover:text-white"
            aria-label="Close transcript importer"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4">
          {/* Privacy Callout */}
          <div className="flex items-start gap-2.5 rounded-xl border border-emerald-500/35 bg-emerald-500/10 p-3 text-xs text-emerald-200">
            <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400" />
            <div>
              <span className="font-semibold text-emerald-100">
                Processed 100% locally in your browser:
              </span>{" "}
              Your PDF, name, NetID, Student ID, GPA, and test scores never leave your device.
              Only the sanitized course codes below (plus optional grades/terms) are sent when you
              confirm.
            </div>
          </div>

          {!hasParsed ? (
            <div className="space-y-4">
              {/* PDF Dropzone */}
              <label
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragging(true);
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setDragging(false);
                  void handleFile(e.dataTransfer.files?.[0]);
                }}
                className={`flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed px-6 py-7 text-center transition ${
                  dragging
                    ? "border-emerald-400 bg-emerald-500/10"
                    : "border-zinc-700 bg-zinc-950/70 hover:border-zinc-500"
                }`}
              >
                <input
                  type="file"
                  accept=".pdf,application/pdf,.txt"
                  className="hidden"
                  onChange={(e) => void handleFile(e.target.files?.[0])}
                />
                {parsing ? (
                  <>
                    <Loader2 className="h-7 w-7 animate-spin text-emerald-400" />
                    <span className="mt-2 text-xs font-medium text-zinc-200">
                      Reading {fileName || "transcript"} locally...
                    </span>
                  </>
                ) : (
                  <>
                    <FileUp className="h-7 w-7 text-emerald-400" />
                    <span className="mt-2 text-xs font-semibold text-white">
                      Drop Cornell Unofficial Transcript PDF here, or click to select
                    </span>
                    <span className="mt-1 text-[11px] text-zinc-400">
                      Parsed directly in-browser via PDF.js — never uploaded to any server
                    </span>
                  </>
                )}
              </label>

              {/* Paste fallback */}
              <div className="space-y-2">
                <div className="flex items-center gap-1.5 text-xs font-medium text-zinc-300">
                  <FileText className="h-3.5 w-3.5 text-sky-400" />
                  <span>Or paste unofficial transcript text</span>
                </div>
                <textarea
                  rows={5}
                  value={pastedText}
                  onChange={(e) => setPastedText(e.target.value)}
                  placeholder="Paste text from Student Center Unofficial Transcript (including Fall/Spring terms, Coursework in Progress, and Advanced Placement / Transferred to Term sections)..."
                  className="w-full rounded-xl border border-zinc-700 bg-zinc-950 p-3 font-mono text-[11px] text-zinc-200 placeholder-zinc-500 focus:border-sky-500 focus:outline-none"
                />
                <div className="flex justify-end">
                  <button
                    type="button"
                    disabled={!pastedText.trim() || parsing}
                    onClick={() => applyParsedText(pastedText)}
                    className="inline-flex items-center gap-1.5 rounded-xl bg-sky-500 px-4 py-2 text-xs font-semibold text-zinc-950 hover:bg-sky-400 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    <Sparkles className="h-3.5 w-3.5" />
                    Parse Locally
                  </button>
                </div>
              </div>

              {parseError && (
                <div className="flex items-start gap-2 rounded-xl border border-red-500/40 bg-red-500/10 p-3 text-xs text-red-200">
                  <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-red-400" />
                  <span>{parseError}</span>
                </div>
              )}
            </div>
          ) : importResult ? (
            /* Success Summary */
            <div className="space-y-3 rounded-2xl border border-emerald-500/35 bg-zinc-950/70 p-4 text-xs">
              <div className="flex items-center gap-2 text-sm font-bold text-emerald-300">
                <CheckCircle2 className="h-5 w-5" />
                <span>Transcript merged cleanly!</span>
              </div>

              <ul className="space-y-1.5 text-zinc-300">
                <li>
                  • Added{" "}
                  <span className="font-semibold text-white">
                    {importResult.import_summary.added_completed.length}
                  </span>{" "}
                  new completed course(s) to Checklist &amp; Prerequisites
                  {importResult.import_summary.enriched_completed.length > 0 && (
                    <>
                      ; enriched details on{" "}
                      <span className="font-semibold text-emerald-300">
                        {importResult.import_summary.enriched_completed.length}
                      </span>{" "}
                      existing course(s) ({" "}
                      <span className="font-mono text-[11px]">
                        {importResult.import_summary.enriched_completed.join(", ")}
                      </span>
                      )
                    </>
                  )}
                  .
                </li>
                {importResult.import_summary.unchanged_completed.length > 0 && (
                  <li className="text-zinc-400">
                    • Preserved{" "}
                    <span className="font-semibold text-zinc-200">
                      {importResult.import_summary.unchanged_completed.length}
                    </span>{" "}
                    already-recorded completed course(s) without duplicates.
                  </li>
                )}
                {(importResult.import_summary.added_in_progress?.length ?? 0) > 0 && (
                  <li>
                    • Marked{" "}
                    <span className="font-semibold text-amber-300">
                      {importResult.import_summary.added_in_progress!.length}
                    </span>{" "}
                    course(s) as <span className="font-semibold text-amber-200">Currently Taking</span>{" "}
                    on your CS Checklist (
                    <span className="font-mono text-[11px]">
                      {importResult.import_summary.added_in_progress!.join(", ")}
                    </span>
                    ).
                  </li>
                )}
                {importResult.import_summary.scheduler.map((sr) => (
                  <li key={sr.roster}>
                    • Scheduler <span className="font-mono font-semibold text-sky-300">{sr.roster}</span>{" "}
                    ({sr.schedule_name}): added{" "}
                    <span className="font-semibold text-white">{sr.added.length}</span>
                    {sr.updated.length > 0 && (
                      <>, enriched {sr.updated.length} existing</>
                    )}
                    {sr.already_present.length > 0 && (
                      <>, kept {sr.already_present.length} already in schedule</>
                    )}
                    {sr.skipped.length > 0 && (
                      <span className="text-amber-300">
                        {" "}
                        ({sr.skipped.length} not found in {sr.roster} catalog:{" "}
                        {sr.skipped.map((s) => s.course).join(", ")})
                      </span>
                    )}
                    .
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            /* Review & Confirm Sanitized Courses */
            <div className="space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-xs font-medium text-zinc-300">
                  {fileName ? `Parsed locally from ${fileName}` : "Parsed locally from pasted text"}
                </span>
                <button
                  type="button"
                  onClick={() => {
                    setHasParsed(false);
                    setFileName("");
                    setParseError("");
                    setImportError("");
                  }}
                  className="text-xs text-sky-300 hover:underline"
                >
                  Choose different file / text
                </button>
              </div>

              {/* Current / In-Progress -> Scheduler */}
              {inProgressRows.length > 0 && (
                <div className="space-y-2.5 rounded-xl border border-sky-500/35 bg-sky-500/5 p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-1.5 text-xs font-bold text-sky-200">
                      <Calendar className="h-4 w-4 text-sky-400" />
                      <span>
                        {targetSchedulerRosters.length === 1
                          ? `Current Courses → ${targetSchedulerRosters[0]} Scheduler & Checklist`
                          : targetSchedulerRosters.length > 1
                            ? `In-Progress Courses → ${targetSchedulerRosters.length} Scheduler Semesters (${targetSchedulerRosters.join(", ")})`
                            : "Current / In-Progress Courses → Scheduler & Checklist"}{" "}
                        ({selectedInProgressCount}/{inProgressRows.length})
                      </span>
                    </div>
                    <label className="flex cursor-pointer items-center gap-1.5 text-[11px] text-amber-200">
                      <input
                        type="checkbox"
                        checked={syncInProgressToChecklist}
                        onChange={(e) => setSyncInProgressToChecklist(e.target.checked)}
                        className="rounded border-zinc-600 bg-zinc-950 text-amber-500"
                      />
                      <span>Also mark as &quot;Currently Taking&quot; on CS Checklist</span>
                    </label>
                  </div>
                  <p className="text-[11px] text-zinc-400">
                    Each course syncs to a dedicated Transcript schedule for its assigned semester (keeping your custom schedules untouched)
                    {syncInProgressToChecklist ? " and fills CS Checklist boxes as Currently Taking." : "."}
                  </p>

                  <div className="space-y-2">
                    {groupedInProgress.map(([groupRoster, items]) => {
                      const isKnownRoster =
                        groupRoster !== "UNASSIGNED" &&
                        (rosterSlugs.length === 0 || rosterSlugs.includes(groupRoster));
                      return (
                        <div
                          key={groupRoster}
                          className="overflow-hidden rounded-lg border border-zinc-800 bg-zinc-950/75"
                        >
                          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-zinc-800/90 bg-zinc-900/80 px-3 py-1.5 text-[11px]">
                            <span className="font-semibold text-sky-300">
                              {groupRoster === "UNASSIGNED"
                                ? "Pick target Scheduler semester"
                                : `Syncing to ${groupRoster} Scheduler · Transcript Schedule`}
                            </span>
                            <span className="text-zinc-400">
                              {items.length} course{items.length === 1 ? "" : "s"}
                              {!isKnownRoster && groupRoster !== "UNASSIGNED" && (
                                <span className="ml-1.5 text-amber-300">
                                  (not in current ClassSniper rosters)
                                </span>
                              )}
                            </span>
                          </div>
                          <div className="divide-y divide-zinc-800/80">
                            {items.map(({ row, idx }) => (
                              <div
                                key={`${row.course}-${idx}`}
                                className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-xs"
                              >
                                <label className="flex cursor-pointer items-center gap-2">
                                  <input
                                    type="checkbox"
                                    checked={row.selected}
                                    onChange={(e) =>
                                      setInProgressRows((prev) =>
                                        prev.map((it, i) =>
                                          i === idx ? { ...it, selected: e.target.checked } : it
                                        )
                                      )
                                    }
                                    className="rounded border-zinc-600 bg-zinc-950 text-sky-500"
                                  />
                                  <span className="font-mono font-bold text-white">{row.course}</span>
                                  {row.cr && (
                                    <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] text-zinc-300">
                                      {row.cr} cr
                                    </span>
                                  )}
                                </label>

                                <div className="flex items-center gap-2">
                                  <span className="text-[11px] text-zinc-400">Target semester:</span>
                                  {rosterSlugs.includes(row.roster.toUpperCase()) ||
                                  rosterSlugs.length === 0 ? (
                                    <select
                                      value={row.roster}
                                      onChange={(e) =>
                                        setInProgressRows((prev) =>
                                          prev.map((it, i) =>
                                            i === idx ? { ...it, roster: e.target.value } : it
                                          )
                                        )
                                      }
                                      className="rounded-lg border border-zinc-700 bg-zinc-900 px-2 py-1 font-mono text-[11px] text-white"
                                    >
                                      {Array.from(
                                        new Set([...rosterSlugs, row.roster].filter(Boolean))
                                      ).map((slug) => (
                                        <option key={slug} value={slug}>
                                          {slug}
                                        </option>
                                      ))}
                                    </select>
                                  ) : (
                                    <input
                                      type="text"
                                      value={row.roster}
                                      onChange={(e) =>
                                        setInProgressRows((prev) =>
                                          prev.map((it, i) =>
                                            i === idx
                                              ? { ...it, roster: e.target.value.toUpperCase() }
                                              : it
                                          )
                                        )
                                      }
                                      className="w-20 rounded-lg border border-zinc-700 bg-zinc-900 px-2 py-1 font-mono text-[11px] text-white"
                                    />
                                  )}
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Completed Courses -> CS Checklist & Past Schedulers */}
              <div className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-3 space-y-2.5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-xs font-bold text-white">
                    Completed &amp; AP Courses → CS Checklist ({selectedCompletedCount}/
                    {completedRows.length})
                  </span>
                  <div className="flex flex-wrap items-center gap-3">
                    {regularPastSemesters.length > 0 && (
                      <label className="flex cursor-pointer items-center gap-1.5 text-[11px] text-sky-200">
                        <input
                          type="checkbox"
                          checked={syncPastToScheduler}
                          onChange={(e) => setSyncPastToScheduler(e.target.checked)}
                          className="rounded border-zinc-600 bg-zinc-950 text-sky-500"
                        />
                        <span>
                          Also populate Scheduler for past semesters ({regularPastSemesters.join(", ")})
                        </span>
                      </label>
                    )}
                    <label className="flex cursor-pointer items-center gap-1.5 text-[11px] text-zinc-300">
                      <input
                        type="checkbox"
                        checked={includeGradesAndTerms}
                        onChange={(e) => setIncludeGradesAndTerms(e.target.checked)}
                        className="rounded border-zinc-600 bg-zinc-950 text-emerald-500"
                      />
                      <span>Save grades &amp; semesters on checklist</span>
                    </label>
                  </div>
                </div>

                {completedRows.length > 0 ? (
                  <div className="divide-y divide-zinc-800/80 rounded-lg border border-zinc-800 bg-zinc-950">
                    {completedRows.map((row, idx) => {
                      const already = existingSet.has(row.course);
                      const prevDet = existingDetails[row.course];
                      const willEnrich =
                        already &&
                        includeGradesAndTerms &&
                        ((!prevDet?.gr && row.gr) ||
                          (!prevDet?.sem && row.sem) ||
                          (!prevDet?.cr && row.cr));
                      return (
                        <label
                          key={`${row.course}-${idx}`}
                          className="flex cursor-pointer flex-wrap items-center justify-between gap-2 px-3 py-1.5 text-xs hover:bg-zinc-900/70"
                        >
                          <span className="flex items-center gap-2">
                            <input
                              type="checkbox"
                              checked={row.selected}
                              onChange={(e) =>
                                setCompletedRows((prev) =>
                                  prev.map((it, i) =>
                                    i === idx ? { ...it, selected: e.target.checked } : it
                                  )
                                )
                              }
                              className="rounded border-zinc-600 bg-zinc-950 text-emerald-500"
                            />
                            <span className="font-mono font-bold text-white">{row.course}</span>
                            {willEnrich ? (
                              <span className="rounded border border-sky-500/40 bg-sky-500/10 px-1.5 py-0.5 text-[10px] text-sky-200">
                                Will add details
                              </span>
                            ) : already ? (
                              <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] text-zinc-400">
                                Already added
                              </span>
                            ) : null}
                          </span>

                          <span className="flex items-center gap-1.5 font-mono text-[11px]">
                            {row.cr && (
                              <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-zinc-300">
                                {row.cr} cr
                              </span>
                            )}
                            {includeGradesAndTerms && row.sem && (
                              <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-zinc-300">
                                {row.sem}
                              </span>
                            )}
                            {includeGradesAndTerms && row.gr && (
                              <span className="rounded border border-emerald-500/30 bg-emerald-500/10 px-1.5 py-0.5 font-semibold text-emerald-300">
                                {row.gr}
                              </span>
                            )}
                          </span>
                        </label>
                      );
                    })}
                  </div>
                ) : (
                  <p className="text-[11px] text-zinc-500">
                    No completed courses found in this selection.
                  </p>
                )}

                {detectedPe > 0 && (
                  <label className="flex cursor-pointer items-center gap-2 pt-1 text-xs text-zinc-300">
                    <input
                      type="checkbox"
                      checked={applyPe}
                      onChange={(e) => setApplyPe(e.target.checked)}
                      className="rounded border-zinc-600 bg-zinc-950 text-emerald-500"
                    />
                    <span>
                      Detected <span className="font-semibold text-white">{detectedPe}</span>{" "}
                      completed PE course(s) — update PE progress (will not lower existing count)
                    </span>
                  </label>
                )}
              </div>

              {excludedRows.length > 0 && (
                <details className="rounded-xl border border-zinc-800 bg-zinc-950/40 px-3 py-2 text-[11px] text-zinc-400">
                  <summary className="cursor-pointer font-medium text-zinc-300">
                    Skipped {excludedRows.length} withdrawn / non-credit course(s) locally
                  </summary>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {excludedRows.map((ex, i) => (
                      <span
                        key={`${ex.course}-${i}`}
                        className="rounded bg-zinc-800 px-2 py-0.5 font-mono text-[10px] text-zinc-400"
                      >
                        {ex.course} ({ex.reason})
                      </span>
                    ))}
                  </div>
                </details>
              )}

              {/* Exact Payload Transparency Viewer */}
              <details className="rounded-xl border border-zinc-800 bg-zinc-950/60 px-3 py-2 text-[11px] text-zinc-400">
                <summary className="flex cursor-pointer items-center gap-1.5 font-medium text-zinc-300">
                  <Eye className="h-3.5 w-3.5 text-emerald-400" />
                  <span>Inspect exact JSON payload before sending (0 PII)</span>
                </summary>
                <pre className="mt-2 max-h-40 overflow-auto rounded-lg bg-zinc-900 p-2 font-mono text-[10px] text-zinc-300">
                  {JSON.stringify(outgoingPayload, null, 2)}
                </pre>
              </details>

              {importError && (
                <div className="flex items-start gap-2 rounded-xl border border-red-500/40 bg-red-500/10 p-3 text-xs text-red-200">
                  <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-red-400" />
                  <span>{importError}</span>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 border-t border-zinc-800 px-5 py-3">
          {importResult ? (
            <button
              type="button"
              onClick={onClose}
              className="inline-flex items-center gap-1.5 rounded-xl bg-emerald-500 px-4 py-2 text-xs font-semibold text-zinc-950 hover:bg-emerald-400"
            >
              <Check className="h-3.5 w-3.5" />
              Done
            </button>
          ) : (
            <>
              <button
                type="button"
                onClick={onClose}
                className="rounded-xl border border-zinc-700 px-4 py-2 text-xs text-zinc-300 hover:bg-zinc-800"
              >
                Cancel
              </button>
              {hasParsed && (
                <button
                  type="button"
                  disabled={
                    importing ||
                    (selectedCompletedCount === 0 &&
                      selectedInProgressCount === 0 &&
                      !(applyPe && detectedPe > 0))
                  }
                  onClick={() => void handleImport()}
                  className="inline-flex items-center gap-1.5 rounded-xl bg-emerald-500 px-4 py-2 text-xs font-semibold text-zinc-950 hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  {importing ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Check className="h-3.5 w-3.5" />
                  )}
                  Import &amp; Merge Courses
                </button>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
};
