import React, { useState } from "react";
import { Check, Loader2, Plus, X } from "lucide-react";
import { usePrereqOptions } from "../hooks/usePrereqOptions";
import type { CourseDetailMeta } from "../types";
import { parseCourseInputTokens } from "../utils/courseFormat";

export interface CourseQuickAddCardProps {
  title: string;
  subtitle: string;
  icon: React.ReactNode;
  tone: "taken" | "taking";
  roster: string;
  courses: string[];
  details?: Record<string, CourseDetailMeta>;
  alreadyTakenSet: Set<string>;
  alreadyTakingSet: Set<string>;
  saving: boolean;
  placeholder: string;
  addLabel: string;
  emptyText: string;
  onAdd: (codes: string[]) => Promise<void>;
  onRemove: (code: string) => Promise<void>;
  onPromoteToTaken?: (code: string) => Promise<void>;
}

export function CourseQuickAddCard({
  title,
  subtitle,
  icon,
  tone,
  roster,
  courses,
  details,
  alreadyTakenSet,
  alreadyTakingSet,
  saving,
  placeholder,
  addLabel,
  emptyText,
  onAdd,
  onRemove,
  onPromoteToTaken,
}: CourseQuickAddCardProps) {
  const [input, setInput] = useState("");
  const [focused, setFocused] = useState(false);
  const { options, setOptions } = usePrereqOptions(roster, input, "cs", { limit: 10 });

  const handleSubmitCodes = async (codes: string[]) => {
    const clean = codes.map((c) => c.trim().toUpperCase()).filter(Boolean);
    if (clean.length === 0) return;
    await onAdd(clean);
    setInput("");
    setOptions([]);
  };

  const isTakingTone = tone === "taking";
  const borderAccent = isTakingTone ? "border-amber-500/30" : "border-zinc-800";
  const chipCls = isTakingTone
    ? "border-amber-500/40 bg-amber-500/10 text-amber-200"
    : "border-emerald-500/35 bg-emerald-500/10 text-emerald-200";
  const subBadgeCls = isTakingTone
    ? "bg-amber-500/20 text-amber-100"
    : "bg-emerald-500/20 text-emerald-100";
  const btnCls = isTakingTone
    ? "bg-amber-500 text-zinc-950 hover:bg-amber-400"
    : "bg-sky-500 text-zinc-950 hover:bg-sky-400";

  return (
    <div className={`space-y-3 rounded-2xl border ${borderAccent} bg-zinc-900/75 p-4`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            {icon}
            <h3 className="text-xs font-bold uppercase tracking-wider text-zinc-200">{title}</h3>
            {saving && (
              <Loader2
                className={`h-3.5 w-3.5 animate-spin ${
                  isTakingTone ? "text-amber-400" : "text-sky-400"
                }`}
              />
            )}
          </div>
          <p className="mt-0.5 text-[11px] text-zinc-400">{subtitle}</p>
        </div>
      </div>

      <div className="relative flex flex-wrap gap-2">
        <div className="relative min-w-[200px] flex-1">
          <input
            type="text"
            value={input}
            onFocus={() => setFocused(true)}
            onBlur={() => setTimeout(() => setFocused(false), 180)}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                const parsed = parseCourseInputTokens(input);
                if (parsed.length > 0) {
                  void handleSubmitCodes(parsed);
                } else if (options.length > 0) {
                  void handleSubmitCodes([options[0].code]);
                }
              }
            }}
            placeholder={placeholder}
            className={`w-full rounded-xl border border-zinc-700 bg-zinc-950 px-3 py-2 text-xs text-white placeholder-zinc-500 focus:outline-none ${
              isTakingTone ? "focus:border-amber-500" : "focus:border-sky-500"
            }`}
          />

          {focused && input.trim() && options.length > 0 && (
            <div className="absolute left-0 right-0 top-full z-30 mt-1 max-h-56 overflow-y-auto rounded-xl border border-zinc-700 bg-zinc-950 p-1 shadow-2xl">
              {options.map((opt) => {
                const inTaken = alreadyTakenSet.has(opt.code);
                const inTaking = alreadyTakingSet.has(opt.code);
                const alreadyInThisList = isTakingTone ? inTaking : inTaken;
                return (
                  <button
                    key={opt.code}
                    type="button"
                    disabled={alreadyInThisList}
                    onMouseDown={(e) => {
                      e.preventDefault();
                      if (!alreadyInThisList) {
                        void handleSubmitCodes([opt.code]);
                      }
                    }}
                    className={`flex w-full items-center justify-between gap-2 rounded-lg px-2.5 py-1.5 text-left text-xs ${
                      alreadyInThisList
                        ? "cursor-default text-zinc-500"
                        : "text-zinc-200 hover:bg-zinc-800"
                    }`}
                  >
                    <span className="truncate">
                      <span className="font-mono font-semibold text-white">{opt.code}</span>
                      {opt.title ? <span className="ml-2 text-zinc-400">{opt.title}</span> : null}
                    </span>
                    {alreadyInThisList ? (
                      <span
                        className={`text-[10px] ${
                          isTakingTone ? "text-amber-300" : "text-emerald-400"
                        }`}
                      >
                        {isTakingTone ? "Taking" : "Taken"}
                      </span>
                    ) : isTakingTone && inTaken ? (
                      <span className="text-[10px] text-emerald-400">Taken</span>
                    ) : (
                      <Plus
                        className={`h-3.5 w-3.5 shrink-0 ${
                          isTakingTone ? "text-amber-400" : "text-sky-400"
                        }`}
                      />
                    )}
                  </button>
                );
              })}
            </div>
          )}
        </div>

        <button
          type="button"
          disabled={saving || (!parseCourseInputTokens(input).length && options.length === 0)}
          onClick={() => {
            const parsed = parseCourseInputTokens(input);
            if (parsed.length > 0) {
              void handleSubmitCodes(parsed);
            } else if (options.length > 0) {
              void handleSubmitCodes([options[0].code]);
            }
          }}
          className={`inline-flex items-center gap-1 rounded-xl px-3.5 py-2 text-xs font-semibold disabled:cursor-not-allowed disabled:opacity-40 ${btnCls}`}
        >
          <Plus className="h-3.5 w-3.5" />
          {addLabel}
        </button>
      </div>

      {courses.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {courses.map((code) => {
            const det = details?.[code];
            const pillText = isTakingTone ? det?.sem : det?.gr;
            return (
              <span
                key={code}
                title={
                  det
                    ? [det.sem, det.gr, det.cr ? `${det.cr} cr` : ""].filter(Boolean).join(" • ")
                    : undefined
                }
                className={`inline-flex items-center gap-1 rounded-lg border px-2 py-0.5 font-mono text-[11px] font-medium ${chipCls}`}
              >
                <span>{code}</span>
                {pillText && (
                  <span className={`rounded px-1 text-[10px] font-semibold ${subBadgeCls}`}>
                    {pillText}
                  </span>
                )}
                {onPromoteToTaken && (
                  <button
                    type="button"
                    disabled={saving}
                    onClick={() => void onPromoteToTaken(code)}
                    title={`Mark ${code} as Completed`}
                    className="rounded p-0.5 text-amber-300/80 hover:bg-emerald-500/20 hover:text-emerald-200"
                  >
                    <Check className="h-3 w-3" />
                  </button>
                )}
                <button
                  type="button"
                  disabled={saving}
                  onClick={() => void onRemove(code)}
                  title={`Remove ${code}`}
                  className={`rounded p-0.5 ${
                    isTakingTone
                      ? "text-amber-300/80 hover:bg-amber-500/20 hover:text-white"
                      : "text-emerald-300/80 hover:bg-emerald-500/20 hover:text-white"
                  }`}
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            );
          })}
        </div>
      ) : (
        <p className="text-[11px] text-zinc-500">{emptyText}</p>
      )}
    </div>
  );
}
