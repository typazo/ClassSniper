import React, { useState } from "react";
import { BookOpen, ExternalLink, Loader2, RefreshCw, Star, Users } from "lucide-react";
import type { CourseInsights, CourseSummary, ExternalCourseLinks } from "../types";

interface Props {
  course: CourseSummary;
  insights?: CourseInsights;
  loading: boolean;
  error?: string;
  onRefresh: () => void;
}

function getFallbackLinks(course: CourseSummary): ExternalCourseLinks {
  if (course.external_links) return course.external_links;
  const r = encodeURIComponent(course.roster.toUpperCase());
  const s = encodeURIComponent(course.subject.toUpperCase());
  const c = encodeURIComponent(course.catalog_nbr.trim());
  return {
    roster: `https://classes.cornell.edu/browse/roster/${r}/class/${s}/${c}`,
    cu_reviews: `https://www.cureviews.org/course/${s}/${c}`,
    coursicle: `https://www.coursicle.com/cornell/courses/${s}/${c}/`,
    rmp_search: `https://www.ratemyprofessors.com/search/professors/298?q=${encodeURIComponent(course.subject.toUpperCase())}`,
  };
}

function formatScore(val: number | null): string {
  return val != null ? val.toFixed(1) : "—";
}

function formatReviewDate(raw: string): string {
  if (!raw) return "";
  const dt = new Date(raw);
  if (Number.isNaN(dt.getTime())) return "";
  return dt.toLocaleDateString(undefined, { year: "numeric", month: "short" });
}

export function CourseInsightsPanel({ course, insights, loading, error, onRefresh }: Props) {
  const [showReviews, setShowReviews] = useState(false);
  const links = insights?.links || getFallbackLinks(course);
  const cu = insights?.cu_reviews;
  const rmp = insights?.rmp;

  return (
    <div className="space-y-3 rounded-xl border border-zinc-800 bg-zinc-950/75 p-3.5">
      {/* External Resource Links Bar */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-zinc-800/80 pb-2.5">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="mr-1 text-[11px] font-semibold uppercase tracking-wide text-zinc-500">Links:</span>
          <ExtLinkChip href={links.roster} label="Class Roster" />
          <ExtLinkChip href={links.cu_reviews} label="CU Reviews" accent="emerald" />
          <ExtLinkChip href={links.rmp_search} label="RMP Search" accent="sky" />
          <ExtLinkChip href={links.coursicle} label="Coursicle" accent="indigo" />
        </div>

        <button
          type="button"
          onClick={onRefresh}
          disabled={loading}
          title="Refresh CU Reviews & RMP data"
          className="inline-flex items-center gap-1 rounded-lg border border-zinc-800 px-2 py-1 text-[11px] text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200 disabled:opacity-50"
        >
          <RefreshCw className={`h-3 w-3 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </div>

      {loading && !insights && (
        <div className="flex items-center gap-2 py-2 text-xs text-zinc-400">
          <Loader2 className="h-3.5 w-3.5 animate-spin text-emerald-400" />
          Loading CU Reviews &amp; RateMyProfessors ratings...
        </div>
      )}

      {error && !insights && (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
          {error}
        </div>
      )}

      {insights && (
        <div className="grid gap-3 md:grid-cols-2">
          {/* CU Reviews Card */}
          <div className="space-y-2.5 rounded-xl border border-zinc-800/90 bg-zinc-900/60 p-3">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-1.5 text-xs font-semibold text-white">
                <BookOpen className="h-3.5 w-3.5 text-emerald-400" />
                CU Reviews
              </div>
              <a
                href={cu?.course_url || links.cu_reviews}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 text-[11px] font-medium text-emerald-400 hover:underline"
              >
                Open page
                <ExternalLink className="h-3 w-3" />
              </a>
            </div>

            {cu?.found ? (
              <>
                <div className="grid grid-cols-3 gap-1.5 text-center">
                  <MetricBox label="Rating" value={formatScore(cu.rating)} suffix="/5" tone="emerald" />
                  <MetricBox label="Difficulty" value={formatScore(cu.difficulty)} suffix="/5" tone="amber" />
                  <MetricBox label="Workload" value={formatScore(cu.workload)} suffix="/5" tone="sky" />
                </div>

                {cu.summary_tags.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {cu.summary_tags.slice(0, 6).map((t) => (
                      <span
                        key={`${t.category}-${t.label}`}
                        className="rounded-md border border-zinc-700/80 bg-zinc-950 px-1.5 py-0.5 text-[10px] text-zinc-300"
                      >
                        <span className="text-zinc-500">{t.category}:</span> {t.label}
                      </span>
                    ))}
                  </div>
                )}

                {cu.summary && <p className="text-xs leading-relaxed text-zinc-300">{cu.summary}</p>}

                <div className="flex flex-wrap items-center justify-between gap-2 pt-0.5 text-[11px] text-zinc-400">
                  <span>
                    {cu.review_count} student review{cu.review_count === 1 ? "" : "s"}
                    {cu.semesters_offered.length > 0 ? ` · Offered ${cu.semesters_offered.slice(-4).join(", ")}` : ""}
                  </span>
                  {cu.reviews.length > 0 && (
                    <button
                      type="button"
                      onClick={() => setShowReviews((v) => !v)}
                      className="font-medium text-emerald-400 hover:underline"
                    >
                      {showReviews ? "Hide reviews" : `Read recent (${cu.reviews.length})`}
                    </button>
                  )}
                </div>

                {showReviews && cu.reviews.length > 0 && (
                  <div className="space-y-2 border-t border-zinc-800 pt-2">
                    {cu.reviews.map((rev, i) => (
                      <div key={rev.id || i} className="rounded-lg bg-zinc-950/90 p-2.5 text-[11px] space-y-1">
                        <div className="flex flex-wrap items-center justify-between gap-1 text-zinc-400">
                          <div className="flex flex-wrap items-center gap-2">
                            {rev.rating != null && <span className="font-semibold text-emerald-400">★ {rev.rating}/5</span>}
                            {rev.difficulty != null && <span>Diff {rev.difficulty}/5</span>}
                            {rev.workload != null && <span>Work {rev.workload}/5</span>}
                            {rev.grade && (
                              <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] font-medium text-zinc-200">
                                Grade {rev.grade}
                              </span>
                            )}
                          </div>
                          <span>{formatReviewDate(rev.date)}</span>
                        </div>
                        {rev.professors.length > 0 && (
                          <div className="text-[10px] text-zinc-500">Prof: {rev.professors.join(", ")}</div>
                        )}
                        <p className="leading-relaxed text-zinc-200">{rev.text}</p>
                      </div>
                    ))}
                    <a
                      href={cu.course_url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 text-[11px] font-medium text-emerald-400 hover:underline"
                    >
                      See all {cu.review_count} reviews on CU Reviews
                      <ExternalLink className="h-3 w-3" />
                    </a>
                  </div>
                )}
              </>
            ) : (
              <div className="text-xs text-zinc-400">
                {cu?.error ? cu.error : "No CU Reviews entry found for this course yet."}{" "}
                <a
                  href={cu?.course_url || links.cu_reviews}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-0.5 text-emerald-400 hover:underline"
                >
                  Check on CU Reviews
                  <ExternalLink className="h-3 w-3" />
                </a>
              </div>
            )}
          </div>

          {/* RateMyProfessors Card */}
          <div className="space-y-2.5 rounded-xl border border-zinc-800/90 bg-zinc-900/60 p-3">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-1.5 text-xs font-semibold text-white">
                <Users className="h-3.5 w-3.5 text-sky-400" />
                RateMyProfessors
              </div>
              <a
                href={rmp?.search_url || links.rmp_search}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 text-[11px] font-medium text-sky-400 hover:underline"
              >
                Search Cornell RMP
                <ExternalLink className="h-3 w-3" />
              </a>
            </div>

            {!rmp || rmp.instructors.length === 0 ? (
              <p className="text-xs text-zinc-400">
                Sections currently list <span className="text-zinc-300">Staff / TBA</span> — check Class Roster or search Cornell RMP above.
              </p>
            ) : (
              <div className="space-y-2">
                {rmp.instructors.map((prof) => (
                  <div key={prof.name} className="rounded-lg border border-zinc-800 bg-zinc-950/90 p-2.5 text-xs">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <a
                        href={prof.rmp_url}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 font-semibold text-white hover:text-sky-300 hover:underline"
                      >
                        {prof.name}
                        <ExternalLink className="h-3 w-3 text-sky-400" />
                      </a>
                      {prof.found && prof.avg_rating != null ? (
                        <span className="inline-flex items-center gap-1 rounded-md bg-sky-500/15 px-1.5 py-0.5 text-[11px] font-bold text-sky-300">
                          <Star className="h-3 w-3 fill-sky-400 text-sky-400" />
                          {prof.avg_rating.toFixed(1)} / 5
                        </span>
                      ) : (
                        <a
                          href={prof.search_url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-[11px] text-sky-400 hover:underline"
                        >
                          Search on RMP &rarr;
                        </a>
                      )}
                    </div>

                    {prof.found ? (
                      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px] text-zinc-400">
                        <span>{prof.num_ratings} rating{prof.num_ratings === 1 ? "" : "s"}</span>
                        {prof.avg_difficulty != null && <span>Difficulty {prof.avg_difficulty.toFixed(1)}/5</span>}
                        {prof.would_take_again_percent != null && <span>{prof.would_take_again_percent}% would take again</span>}
                        {prof.department && <span className="text-zinc-500">{prof.department}</span>}
                      </div>
                    ) : (
                      <div className="mt-0.5 text-[11px] text-zinc-500">
                        No rated Cornell RMP profile matched automatically.
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function ExtLinkChip({
  href,
  label,
  accent = "zinc",
}: {
  href: string;
  label: string;
  accent?: "zinc" | "emerald" | "sky" | "indigo";
}) {
  const palette = {
    zinc: "border-zinc-700 text-zinc-200 hover:border-zinc-500",
    emerald: "border-emerald-500/30 text-emerald-300 hover:bg-emerald-500/10",
    sky: "border-sky-500/30 text-sky-300 hover:bg-sky-500/10",
    indigo: "border-indigo-500/30 text-indigo-300 hover:bg-indigo-500/10",
  }[accent];

  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className={`inline-flex items-center gap-1 rounded-lg border bg-zinc-900 px-2 py-1 text-[11px] font-medium transition ${palette}`}
    >
      {label}
      <ExternalLink className="h-3 w-3 opacity-80" />
    </a>
  );
}

function MetricBox({
  label,
  value,
  suffix,
  tone,
}: {
  label: string;
  value: string;
  suffix: string;
  tone: "emerald" | "amber" | "sky";
}) {
  const color = {
    emerald: "text-emerald-300",
    amber: "text-amber-300",
    sky: "text-sky-300",
  }[tone];

  return (
    <div className="rounded-lg bg-zinc-950/90 px-2 py-1.5">
      <div className="text-[10px] text-zinc-500">{label}</div>
      <div className={`text-sm font-bold ${color}`}>
        {value}
        <span className="text-[10px] font-normal text-zinc-500">{suffix}</span>
      </div>
    </div>
  );
}
