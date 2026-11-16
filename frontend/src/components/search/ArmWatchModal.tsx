import React, { useEffect } from "react";
import { AlertTriangle, MapPin, X } from "lucide-react";
import type { CourseSection, CourseSummary, User } from "../../types";

export interface WatchDraft {
  course: CourseSummary;
  section: CourseSection | null;
  mode: "any_section" | "exact" | "linked_group";
  componentFilter: string;
  triggerOn: "open" | "open_or_waitlist";
  priority: number;
  autoPause: boolean;
  cooldownSec: number;
  groupKey: string;
}

interface Props {
  draft: WatchDraft | null;
  user: User;
  saving: boolean;
  error?: string | null;
  ithacaOrVirtual: boolean;
  onChangeDraft: (next: WatchDraft) => void;
  onClose: () => void;
  onSubmit: (e: React.FormEvent) => void;
}

export function ArmWatchModal({
  draft,
  user,
  saving,
  error,
  ithacaOrVirtual,
  onChangeDraft,
  onClose,
  onSubmit,
}: Props) {
  useEffect(() => {
    if (!draft) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape" && !saving) {
        onClose();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [draft, saving, onClose]);

  if (!draft) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm"
      onClick={(e) => {
        if (e.target === e.currentTarget && !saving) onClose();
      }}
    >
      <form
        onSubmit={onSubmit}
        className="w-full max-w-md space-y-4 rounded-2xl border border-zinc-700 bg-zinc-900 p-5 shadow-2xl"
      >
        <div className="flex items-start justify-between gap-3">
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
          <button
            type="button"
            disabled={saving}
            onClick={onClose}
            aria-label="Close modal"
            className="rounded-lg p-1 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200 disabled:opacity-50"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {error && (
          <div className="flex items-start gap-2 rounded-xl border border-rose-500/35 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-rose-400" />
            <span>{error}</span>
          </div>
        )}

        {draft.section ? (
          <div>
            <label className="mb-1.5 block text-xs font-medium text-zinc-300">Watch Mode</label>
            <div className="space-y-2">
              <label className="flex cursor-pointer items-start gap-2.5 rounded-xl border border-zinc-700 bg-zinc-950 p-3 text-xs">
                <input
                  type="radio"
                  checked={draft.mode === "exact"}
                  onChange={() => onChangeDraft({ ...draft, mode: "exact" })}
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
                  onChange={() => onChangeDraft({ ...draft, mode: "linked_group" })}
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
              onChange={(e) => onChangeDraft({ ...draft, componentFilter: e.target.value })}
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
              onChange={(e) =>
                onChangeDraft({ ...draft, triggerOn: e.target.value as "open" | "open_or_waitlist" })
              }
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
              onChange={(e) => onChangeDraft({ ...draft, cooldownSec: Number(e.target.value) })}
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
              onChange={(e) => onChangeDraft({ ...draft, priority: e.target.checked ? 2 : 1 })}
              className="accent-emerald-500"
            />
          </div>
        )}

        <label className="flex cursor-pointer items-center justify-between rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 text-xs">
          <span className="text-zinc-300">Auto-pause watch after alert fires</span>
          <input
            type="checkbox"
            checked={draft.autoPause}
            onChange={(e) => onChangeDraft({ ...draft, autoPause: e.target.checked })}
            className="accent-emerald-500"
          />
        </label>

        <div>
          <label className="mb-1 block text-xs font-medium text-zinc-300">Pick-1 Group (optional)</label>
          <input
            type="text"
            maxLength={48}
            value={draft.groupKey}
            onChange={(e) => onChangeDraft({ ...draft, groupKey: e.target.value })}
            placeholder="e.g. FWS Pick 1 — pauses sibling watches when 1 opens"
            className="w-full rounded-xl border border-zinc-700 bg-zinc-950 px-3 py-2 text-xs text-white placeholder-zinc-500"
          />
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            disabled={saving}
            onClick={onClose}
            className="rounded-xl border border-zinc-700 px-4 py-2 text-sm text-zinc-300 hover:bg-zinc-800 disabled:opacity-50"
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
  );
}
