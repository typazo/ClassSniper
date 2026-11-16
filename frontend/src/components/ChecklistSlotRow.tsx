import React from "react";
import {
  AlertTriangle,
  CalendarCheck2,
  Check,
  CheckSquare,
  Clock,
  Edit3,
  Eraser,
  Minus,
  Plus,
  Search,
  Square,
} from "lucide-react";
import type { CsChecklistSlot } from "../types";

interface Props {
  slot: CsChecklistSlot;
  isSelected: boolean;
  onToggleSelect: (slot: CsChecklistSlot) => void;
  onLaunchSearch: (slot: CsChecklistSlot) => void;
  onStartEdit: (slot: CsChecklistSlot) => void;
  onClearSlot: (slotId: string) => void;
}

export function ChecklistSlotRow({
  slot,
  isSelected,
  onToggleSelect,
  onLaunchSearch,
  onStartEdit,
  onClearSlot,
}: Props) {
  const isInProgress = slot.filled && slot.source === "in_progress";
  const isWhatIf = slot.filled && slot.source === "schedule";
  const isWaived = Boolean(slot.waived || slot.source === "waived");

  return (
    <div
      className={`flex flex-wrap items-center justify-between gap-2 px-4 py-2.5 text-xs transition ${
        isWaived
          ? "bg-zinc-950/40 opacity-55"
          : !slot.filled
            ? isSelected
              ? "bg-emerald-500/15"
              : "hover:bg-zinc-800/40"
            : isInProgress
              ? "bg-amber-500/5"
              : isWhatIf
                ? "bg-sky-500/5"
                : ""
      }`}
    >
      <div className="flex min-w-0 flex-1 items-center gap-2.5">
        {isWaived ? (
          <div className="flex min-w-0 items-center gap-2.5">
            <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-md border border-zinc-700 bg-zinc-800/70 text-zinc-400">
              <Minus className="h-3 w-3" />
            </span>
            <div className="min-w-0">
              <div className="font-semibold text-zinc-400 line-through">{slot.label}</div>
              <div className="text-[11px] text-zinc-500">
                Waived — satisfied by {slot.waived_by || "2000+ language course"}
              </div>
            </div>
          </div>
        ) : !slot.filled ? (
          <button
            type="button"
            onClick={() => onToggleSelect(slot)}
            className={`flex items-center gap-2 text-left ${
              isSelected ? "text-emerald-200" : "text-zinc-300"
            }`}
            title="Select empty requirement box to search matching courses"
          >
            {isSelected ? (
              <CheckSquare className="h-4 w-4 shrink-0 text-emerald-400" />
            ) : (
              <Square className="h-4 w-4 shrink-0 text-zinc-500 hover:text-emerald-400" />
            )}
            <div>
              <div className="font-semibold text-white">{slot.label}</div>
              <div className="text-[11px] text-zinc-400">{slot.expected}</div>
            </div>
          </button>
        ) : (
          <div className="flex min-w-0 items-center gap-2.5">
            <span
              className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-md border ${
                isInProgress
                  ? "border-amber-400/70 bg-amber-500/20 text-amber-300"
                  : isWhatIf
                    ? "border-dashed border-sky-400 bg-sky-500/20 text-sky-300"
                    : "border-emerald-500/60 bg-emerald-500/20 text-emerald-300"
              }`}
            >
              {isInProgress ? (
                <Clock className="h-3 w-3" />
              ) : isWhatIf ? (
                <CalendarCheck2 className="h-3 w-3" />
              ) : (
                <Check className="h-3.5 w-3.5" />
              )}
            </span>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="font-semibold text-zinc-400">{slot.label}:</span>
                <span className="font-bold text-white">{slot.course}</span>
                {slot.title && (
                  <span className="max-w-[260px] truncate text-zinc-400">
                    — {slot.title}
                  </span>
                )}
                {(isWhatIf || isInProgress) && (
                  <span
                    className={`rounded border px-1.5 py-0.5 text-[10px] font-semibold ${
                      isInProgress
                        ? "border-amber-500/40 bg-amber-500/15 text-amber-200"
                        : "border-sky-500/40 bg-sky-500/15 text-sky-200"
                    }`}
                  >
                    {isInProgress
                      ? `Taking${slot.sem && slot.sem.toUpperCase() !== "TAKING" ? ` (${slot.sem})` : ""}`
                      : `What-If (${slot.sem})`}
                  </span>
                )}
                {(slot.cr ||
                  (!isWhatIf && !isInProgress && slot.sem && slot.sem.toUpperCase() !== "DONE") ||
                  slot.gr) && (
                  <span className="font-mono text-[11px] text-zinc-400">
                    {[
                      slot.cr ? `${slot.cr} cr` : "",
                      !isWhatIf && !isInProgress && slot.sem && slot.sem.toUpperCase() !== "DONE"
                        ? slot.sem
                        : "",
                      slot.gr || "",
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                    {slot.gr ? "" : ""}
                  </span>
                )}
              </div>
              {slot.warning && (
                <div className="mt-1 inline-flex items-center gap-1 rounded-md border border-amber-500/35 bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-medium text-amber-200">
                  <AlertTriangle className="h-3 w-3 shrink-0 text-amber-300" />
                  <span>{slot.warning}</span>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      <div className="flex items-center gap-1.5">
        {!slot.filled && !isWaived ? (
          <>
            <button
              type="button"
              onClick={() => onLaunchSearch(slot)}
              className="inline-flex items-center gap-1 rounded-lg border border-emerald-500/35 bg-emerald-500/10 px-2 py-1 text-[11px] font-medium text-emerald-200 hover:bg-emerald-500/20"
              title={`Find courses satisfying ${slot.label}`}
            >
              <Search className="h-3 w-3" />
              Find
            </button>
            <button
              type="button"
              onClick={() => onStartEdit(slot)}
              className="inline-flex items-center gap-1 rounded-lg border border-sky-500/35 bg-sky-500/10 px-2 py-1 text-[11px] font-medium text-sky-200 hover:bg-sky-500/20"
              title={`Pick or add a course you took into ${slot.label}`}
            >
              <Plus className="h-3 w-3" />
              Add
            </button>
          </>
        ) : (
          <button
            type="button"
            onClick={() => onStartEdit(slot)}
            className="rounded-lg border border-zinc-700/80 p-1 text-zinc-400 hover:text-white"
            title="Pick a different course or edit credits, semester, grade"
          >
            <Edit3 className="h-3 w-3" />
          </button>
        )}
        {slot.filled && (
          <button
            type="button"
            onClick={() => onClearSlot(slot.id)}
            className="rounded-lg border border-zinc-700/80 p-1 text-zinc-400 hover:text-rose-300"
            title="Clear this slot"
          >
            <Eraser className="h-3 w-3" />
          </button>
        )}
      </div>
    </div>
  );
}
