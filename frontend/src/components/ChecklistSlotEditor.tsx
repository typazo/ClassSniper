import React from "react";
import { Loader2, Plus } from "lucide-react";
import type {
  CsChecklistQuickOption,
  CsChecklistSlot,
  CsChecklistSlotInput,
  PrereqCourseOption,
} from "../types";
import { parseCourseInputTokens } from "../utils/courseFormat";

export type EditSaveMode = "taken" | "taking" | "box";

interface Props {
  slot: CsChecklistSlot;
  suggestions: CsChecklistQuickOption[];
  suggestionsLoading: boolean;
  completedCourses: string[];
  inProgressCourses: string[];
  editForm: CsChecklistSlotInput;
  editSaveMode: EditSaveMode;
  slotPickerFocused: boolean;
  slotSearchDirty: boolean;
  slotSearchOptions: PrereqCourseOption[];
  saving: boolean;
  onChangeForm: (next: CsChecklistSlotInput) => void;
  onChangeSaveMode: (mode: EditSaveMode) => void;
  onFocusPicker: (focused: boolean) => void;
  onMarkSearchDirty: () => void;
  onApplyCourse: (
    slotId: string,
    rawCourse: string,
    crOverride?: string,
    titleOverride?: string
  ) => void;
  onSave: (slotId: string) => void;
  onCancel: () => void;
}

export function ChecklistSlotEditor({
  slot,
  suggestions,
  suggestionsLoading,
  completedCourses,
  inProgressCourses,
  editForm,
  editSaveMode,
  slotPickerFocused,
  slotSearchDirty,
  slotSearchOptions,
  saving,
  onChangeForm,
  onChangeSaveMode,
  onFocusPicker,
  onMarkSearchDirty,
  onApplyCourse,
  onSave,
  onCancel,
}: Props) {
  return (
    <div className="space-y-2.5 bg-zinc-950/90 p-3 text-xs">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-semibold text-white">
          {slot.filled ? `Edit Box: ${slot.label}` : `Add Course: ${slot.label}`}
        </span>
        <span className="text-[11px] text-zinc-400">{slot.expected}</span>
      </div>

      {(suggestions.length > 0 || suggestionsLoading) && (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-[10px] font-medium uppercase tracking-wide text-zinc-500">
            Quick pick:
          </span>
          {suggestionsLoading && suggestions.length === 0 ? (
            <Loader2 className="h-3 w-3 animate-spin text-zinc-400" />
          ) : (
            suggestions.map((opt) => {
              const isTaken = completedCourses.includes(opt.code);
              const isTaking = inProgressCourses.includes(opt.code);
              return (
                <button
                  key={opt.code}
                  type="button"
                  disabled={saving}
                  onClick={() =>
                    onApplyCourse(slot.id, opt.code, opt.cr || "", opt.title || "")
                  }
                  title={opt.title ? `${opt.code}: ${opt.title}` : opt.code}
                  className={`inline-flex items-center gap-1 rounded-lg border px-2 py-0.5 font-mono text-[11px] font-medium transition ${
                    isTaken
                      ? "border-emerald-500/45 bg-emerald-500/15 text-emerald-200 hover:bg-emerald-500/25"
                      : isTaking
                        ? "border-amber-500/45 bg-amber-500/15 text-amber-200 hover:bg-amber-500/25"
                        : "border-sky-500/35 bg-sky-500/10 text-sky-200 hover:bg-sky-500/20"
                  }`}
                >
                  <Plus className="h-2.5 w-2.5" />
                  <span>{opt.code}</span>
                  {opt.cr && <span className="text-[10px] opacity-70">({opt.cr})</span>}
                </button>
              );
            })
          )}
        </div>
      )}

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-6">
        <div className="relative col-span-2 sm:col-span-3">
          <input
            type="text"
            autoFocus
            value={editForm.course}
            onFocus={() => onFocusPicker(true)}
            onBlur={() => setTimeout(() => onFocusPicker(false), 180)}
            onChange={(e) => {
              onMarkSearchDirty();
              onChangeForm({
                ...editForm,
                course: e.target.value,
                title: "",
              });
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                const parsed = parseCourseInputTokens(editForm.course);
                const topMatch = slotSearchOptions[0];
                if (topMatch && (parsed.length === 0 || topMatch.code === parsed[0])) {
                  onApplyCourse(
                    slot.id,
                    topMatch.code,
                    topMatch.cr || "",
                    topMatch.title || ""
                  );
                } else if (parsed.length > 0) {
                  onApplyCourse(slot.id, parsed[0]);
                } else {
                  onSave(slot.id);
                }
              } else if (e.key === "Escape") {
                onCancel();
              }
            }}
            placeholder="Search code, title, or AP (e.g. ENGL 1100F, AP Lit)..."
            className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-2.5 py-1.5 text-xs text-white placeholder-zinc-500 focus:border-sky-500 focus:outline-none"
          />

          {slotPickerFocused &&
            slotSearchDirty &&
            editForm.course.trim() &&
            slotSearchOptions.length > 0 && (
              <div className="absolute left-0 right-0 top-full z-30 mt-1 max-h-48 overflow-y-auto rounded-xl border border-zinc-700 bg-zinc-950 p-1 shadow-2xl">
                {slotSearchOptions.map((opt) => (
                  <button
                    key={opt.code}
                    type="button"
                    onMouseDown={(e) => {
                      e.preventDefault();
                      onApplyCourse(slot.id, opt.code, opt.cr || "", opt.title || "");
                    }}
                    className="flex w-full items-center justify-between gap-2 rounded-lg px-2 py-1.5 text-left text-xs text-zinc-200 hover:bg-zinc-800"
                  >
                    <span className="truncate">
                      <span className="font-mono font-semibold text-white">{opt.code}</span>
                      {opt.title ? <span className="ml-2 text-zinc-400">{opt.title}</span> : null}
                    </span>
                    <span className="flex shrink-0 items-center gap-1.5 text-[10px] text-sky-400">
                      {opt.cr ? `${opt.cr} cr` : ""}
                      <Plus className="h-3 w-3" />
                    </span>
                  </button>
                ))}
              </div>
            )}
        </div>
        <input
          type="text"
          value={editForm.cr}
          onChange={(e) => onChangeForm({ ...editForm, cr: e.target.value })}
          placeholder="Cr (auto)"
          className="rounded-lg border border-zinc-700 bg-zinc-900 px-2.5 py-1.5 text-xs text-white"
        />
        <input
          type="text"
          value={editForm.sem}
          onChange={(e) => onChangeForm({ ...editForm, sem: e.target.value })}
          placeholder="Sem (FA25)"
          className="rounded-lg border border-zinc-700 bg-zinc-900 px-2.5 py-1.5 text-xs text-white"
        />
        <input
          type="text"
          value={editForm.gr}
          onChange={(e) => onChangeForm({ ...editForm, gr: e.target.value })}
          placeholder="Gr (A)"
          className="rounded-lg border border-zinc-700 bg-zinc-900 px-2.5 py-1.5 text-xs text-white"
        />
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
          <span className="text-zinc-400">Save as:</span>
          {(
            [
              { id: "taken", label: "Taken", active: "bg-emerald-500 text-zinc-950 font-semibold" },
              {
                id: "taking",
                label: "Currently Taking",
                active: "bg-amber-500 text-zinc-950 font-semibold",
              },
              {
                id: "box",
                label: "This Box Only",
                active: "bg-zinc-200 text-zinc-950 font-semibold",
              },
            ] as const
          ).map((mode) => (
            <button
              key={mode.id}
              type="button"
              onClick={() => onChangeSaveMode(mode.id)}
              className={`rounded-md border px-2 py-0.5 transition ${
                editSaveMode === mode.id
                  ? `border-transparent ${mode.active}`
                  : "border-zinc-700 bg-zinc-900 text-zinc-300 hover:text-white"
              }`}
            >
              {mode.label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-lg border border-zinc-700 px-2 py-1 text-zinc-300 hover:bg-zinc-800"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={saving}
            onClick={() => onSave(slot.id)}
            className="rounded-lg bg-emerald-500 px-2.5 py-1 font-semibold text-zinc-950 hover:bg-emerald-400 disabled:opacity-50"
          >
            Save
          </button>
        </div>
      </div>
    </div>
  );
}
