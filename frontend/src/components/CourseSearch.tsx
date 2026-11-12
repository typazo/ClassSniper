import React, { useEffect, useState } from "react";
import { BellPlus, ChevronDown, ChevronUp, Loader2, Search } from "lucide-react";
import { api } from "../api/client";
import type { CourseSection, CourseSummary, Roster, Subject, User } from "../types";
import { StatusBadge } from "./StatusBadge";

interface Props {
  user: User;
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

export function CourseSearch({ user, onWatchCreated }: Props) {
  const [rosters, setRosters] = useState<Roster[]>([]);
  const [selectedRoster, setSelectedRoster] = useState("");
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [selectedSubject, setSelectedSubject] = useState("");
  const [query, setQuery] = useState("");
  const [courses, setCourses] = useState<CourseSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [draft, setDraft] = useState<WatchDraft | null>(null);
  const [saving, setSaving] = useState(false);
  const [successMsg, setSuccessMsg] = useState("");

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
  }, [selectedRoster]);

  async function runSearch(e?: React.FormEvent) {
    if (e) e.preventDefault();
    if (!selectedRoster) return;
    if (!query.trim() && !selectedSubject) {
      setError("Enter a course code (e.g. CS 2110), keyword, or class # or pick a subject.");
      return;
    }
    setError("");
    setLoading(true);
    try {
      const res = await api.searchCourses(selectedRoster, query, selectedSubject);
      setCourses(res.courses);
      if (res.courses.length > 0 && res.courses.length <= 5) {
        const autoExp: Record<string, boolean> = {};
        res.courses.forEach((c) => {
          autoExp[`${c.subject}-${c.catalog_nbr}`] = true;
        });
        setExpanded(autoExp);
      } else {
        setExpanded({});
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
    } finally {
      setLoading(false);
    }
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

  return (
    <div className="space-y-4">
      <form onSubmit={runSearch} className="rounded-2xl border border-zinc-800 bg-zinc-900/80 p-4">
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

          <div className="sm:col-span-3">
            <label className="mb-1 block text-xs font-medium text-zinc-400">Subject (optional)</label>
            <select
              value={selectedSubject}
              onChange={(e) => setSelectedSubject(e.target.value)}
              className="w-full rounded-xl border border-zinc-700 bg-zinc-950 px-3 py-2.5 text-sm text-white focus:border-emerald-500 focus:outline-none"
            >
              <option value="">All Subjects</option>
              {subjects.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.value} — {s.descr}
                </option>
              ))}
            </select>
          </div>

          <div className="sm:col-span-6">
            <label className="mb-1 block text-xs font-medium text-zinc-400">
              Course, Keyword, or 5-Digit Class #
            </label>
            <div className="flex gap-2">
              <div className="relative flex-1">
                <Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-zinc-500" />
                <input
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="e.g. CS 2110, Algorithms, 6582"
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
        <p className="mt-2.5 text-xs text-zinc-500">
          Tip: Typing a course code like <code className="text-zinc-300">CS 4820</code> auto-syncs that subject once from Cornell and caches it locally for &lt;5ms searches.
        </p>
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

      <div className="space-y-3">
        {courses.map((course) => {
          const key = `${course.subject}-${course.catalog_nbr}`;
          const isOpen = Boolean(expanded[key]);
          const groups = new Map<number, CourseSection[]>();
          for (const sec of course.sections) {
            const arr = groups.get(sec.enroll_group_idx) || [];
            arr.push(sec);
            groups.set(sec.enroll_group_idx, arr);
          }

          return (
            <div key={key} className="rounded-2xl border border-zinc-800 bg-zinc-900/75">
              <div className="flex flex-wrap items-center justify-between gap-3 p-4">
                <button
                  type="button"
                  onClick={() => setExpanded((p) => ({ ...p, [key]: !p[key] }))}
                  className="flex min-w-0 flex-1 items-start gap-3 text-left"
                >
                  <div className="mt-0.5 text-zinc-400">
                    {isOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                  </div>
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-base font-bold text-white">
                        {course.subject} {course.catalog_nbr}
                      </span>
                      <span className="text-xs text-zinc-500">
                        {course.sections.length} section{course.sections.length === 1 ? "" : "s"}
                      </span>
                    </div>
                    <p className="text-sm text-zinc-300">{course.title_long}</p>
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

                  {Array.from(groups.entries()).map(([egIdx, secs]) => (
                    <div key={egIdx} className="rounded-xl border border-zinc-800 bg-zinc-950/70 p-3">
                      <div className="mb-2 flex items-center justify-between text-xs text-zinc-400">
                        <span className="font-semibold text-zinc-300">Enrollment Group {egIdx + 1}</span>
                        {secs[0]?.components_required?.length > 0 && (
                          <span>Required: {secs[0].components_required.join(" + ")}</span>
                        )}
                      </div>
                      <div className="divide-y divide-zinc-800/70">
                        {secs.map((sec) => (
                          <div
                            key={sec.class_nbr}
                            className="flex flex-wrap items-center justify-between gap-2 py-2.5 first:pt-1 last:pb-1"
                          >
                            <div className="min-w-0 space-y-0.5">
                              <div className="flex flex-wrap items-center gap-2">
                                <span className="font-semibold text-sm text-white">
                                  {sec.ssr_component} {sec.section}
                                </span>
                                <span className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono text-xs text-zinc-300">
                                  #{sec.class_nbr}
                                </span>
                                <StatusBadge status={sec.open_status} />
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
                        ))}
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
                      <div className="text-zinc-400">Alert as soon as #{draft.section.class_nbr} opens (best if already enrolled in Lecture).</div>
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
                      <div className="text-zinc-400">Alert only when this section AND all required companion components in its enroll group are open.</div>
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
    </div>
  );
}
