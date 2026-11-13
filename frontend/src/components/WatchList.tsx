import React, { useState } from "react";
import {
  AlertTriangle,
  Check,
  Copy,
  ExternalLink,
  MapPin,
  Pause,
  Play,
  RefreshCw,
  RotateCcw,
  Trash2,
} from "lucide-react";
import { api } from "../api/client";
import type { Watch } from "../types";
import { getSectionLocationTag, getSectionVirtualLabel } from "../utils/location";
import { copyText } from "../utils/pwa";
import { StatusBadge } from "./StatusBadge";

interface Props {
  watches: Watch[];
  highlightClassNbr: number | null;
  onRefresh: () => void;
  onJumpToSearch: () => void;
}

const MODE_LABELS: Record<Watch["mode"], string> = {
  exact: "Exact Section",
  linked_group: "Linked Group (LEC+DIS/LAB)",
  any_section: "Any Section",
};

export function WatchList({ watches, highlightClassNbr, onRefresh, onJumpToSearch }: Props) {
  const [copiedId, setCopiedId] = useState<number | null>(null);
  const [copiedCodeKey, setCopiedCodeKey] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [checkMsg, setCheckMsg] = useState<Record<number, string>>({});

  async function handleCopy(watch: Watch) {
    if (!watch.class_nbr) return;
    const ok = await copyText(String(watch.class_nbr));
    if (ok) {
      setCopiedId(watch.id);
      setTimeout(() => setCopiedId((cur) => (cur === watch.id ? null : cur)), 1800);
    }
  }

  async function handleCopyCode(text: string, key: string) {
    const ok = await copyText(text);
    if (ok) {
      setCopiedCodeKey(key);
      setTimeout(() => setCopiedCodeKey((cur) => (cur === key ? null : cur)), 1800);
    }
  }

  async function handleToggleActive(watch: Watch) {
    setBusyId(watch.id);
    try {
      await api.updateWatch(watch.id, { active: !watch.active });
      onRefresh();
    } finally {
      setBusyId(null);
    }
  }

  async function handleRearm(watch: Watch) {
    setBusyId(watch.id);
    try {
      await api.rearmWatch(watch.id);
      onRefresh();
    } finally {
      setBusyId(null);
    }
  }

  async function handleCheckNow(watch: Watch) {
    setBusyId(watch.id);
    try {
      const res = await api.checkWatchNow(watch.id);
      setCheckMsg((prev) => ({
        ...prev,
        [watch.id]: res.alerts_count > 0 ? `OPEN! (${res.rtt_ms}ms)` : `Checked (${res.rtt_ms}ms)`,
      }));
      onRefresh();
    } catch (err) {
      setCheckMsg((prev) => ({
        ...prev,
        [watch.id]: err instanceof Error ? err.message : "Error",
      }));
    } finally {
      setBusyId(null);
    }
  }

  async function handleDelete(watch: Watch) {
    setBusyId(watch.id);
    try {
      await api.deleteWatch(watch.id);
      onRefresh();
    } finally {
      setBusyId(null);
    }
  }

  if (watches.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-zinc-800 bg-zinc-900/40 p-10 text-center">
        <p className="text-base font-medium text-zinc-200">No active class watches yet</p>
        <p className="mt-1 text-sm text-zinc-400">
          Search Cornell courses by code, title, or 5-digit class number to arm your sniper.
        </p>
        <button
          onClick={onJumpToSearch}
          className="mt-4 rounded-xl bg-emerald-500 px-4 py-2 text-sm font-semibold text-zinc-950 hover:bg-emerald-400"
        >
          Search Classes
        </button>
      </div>
    );
  }

  const quickOpenCodes = watches.flatMap((w) =>
    (w.open_sections || []).map((sec) => ({
      watchId: w.id,
      subject: w.subject,
      catalogNbr: w.catalog_nbr,
      sec,
    }))
  );

  return (
    <div className="space-y-3">
      {quickOpenCodes.length > 0 && (
        <div className="rounded-2xl border border-emerald-500/40 bg-emerald-500/10 p-3.5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="text-xs font-bold uppercase tracking-wider text-emerald-300">
              Open Codes Ready for Student Center ({quickOpenCodes.length})
            </div>
            <a
              href="https://studentcenter.cornell.edu"
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 rounded-lg bg-emerald-400 px-2.5 py-1 text-xs font-bold text-zinc-950 hover:bg-emerald-300"
            >
              Open Student Center
              <ExternalLink className="h-3 w-3" />
            </a>
          </div>
          <div className="mt-2 flex flex-wrap gap-2">
            {quickOpenCodes.map(({ watchId, subject, catalogNbr, sec }) => {
              const key = `top-${watchId}-${sec.class_nbr}`;
              const isCopied = copiedCodeKey === key;
              return (
                <button
                  key={key}
                  type="button"
                  onClick={() => handleCopyCode(String(sec.class_nbr), key)}
                  title={`Click to copy ${sec.class_nbr} (${subject} ${catalogNbr} ${sec.ssr_component} ${sec.section})`}
                  className={`inline-flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs transition ${
                    isCopied
                      ? "border-emerald-300 bg-emerald-400 text-zinc-950 font-bold"
                      : sec.open_status === "W"
                        ? "border-amber-400/50 bg-zinc-950/90 text-amber-200 hover:border-amber-300"
                        : "border-emerald-500/50 bg-zinc-950/90 text-emerald-200 hover:border-emerald-400"
                  }`}
                >
                  {isCopied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                  <span className="font-mono text-sm font-bold tracking-wide">{sec.class_nbr}</span>
                  <span className="text-[11px] opacity-85">
                    {subject} {catalogNbr} {sec.ssr_component} {sec.section}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {watches.map((w) => {
        const isHighlighted = highlightClassNbr !== null && w.class_nbr === highlightClassNbr;
        const secInfo = w.section_info;
        const secLoc = secInfo ? getSectionLocationTag(secInfo) : null;
        const virtualLabel = secInfo ? getSectionVirtualLabel(secInfo.instruction_mode) : null;
        const rosterUrl = `https://classes.cornell.edu/browse/roster/${w.roster}/class/${w.subject}/${w.catalog_nbr}`;
        return (
          <div
            key={w.id}
            className={`rounded-2xl border p-4 transition ${
              isHighlighted
                ? "border-emerald-400 bg-emerald-950/30 ring-2 ring-emerald-500/30"
                : w.active
                  ? "border-zinc-800 bg-zinc-900/80"
                  : "border-zinc-800/60 bg-zinc-900/35 opacity-75"
            }`}
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded-md bg-zinc-800 px-2 py-0.5 text-xs font-semibold text-zinc-300">
                    {w.roster}
                  </span>
                  <h3 className="text-base font-bold text-white">
                    {w.subject} {w.catalog_nbr}
                  </h3>
                  {secInfo && <StatusBadge status={secInfo.open_status} />}
                  {secLoc?.isOffCampus && (
                    <span className="inline-flex items-center gap-1 rounded-md border border-amber-500/40 bg-amber-500/15 px-2 py-0.5 text-[11px] font-semibold text-amber-200">
                      <AlertTriangle className="h-3 w-3 text-amber-300" />
                      {secLoc.label}
                    </span>
                  )}
                  {secLoc && !secLoc.isOffCampus && (
                    <span className="inline-flex items-center gap-1 rounded-md border border-zinc-700/80 bg-zinc-900 px-2 py-0.5 text-[11px] text-zinc-400">
                      <MapPin className="h-3 w-3 text-zinc-500" />
                      {secLoc.label}
                    </span>
                  )}
                  {virtualLabel && (
                    <span className="rounded-md border border-cyan-500/35 bg-cyan-500/15 px-2 py-0.5 text-[11px] font-medium text-cyan-200">
                      {virtualLabel}
                    </span>
                  )}
                  {w.mode === "any_section" && w.ithaca_or_virtual && (
                    <span className="inline-flex items-center gap-1 rounded-md border border-emerald-500/35 bg-emerald-500/10 px-2 py-0.5 text-[11px] font-medium text-emerald-300">
                      <MapPin className="h-3 w-3" />
                      Ithaca + Virtual
                    </span>
                  )}
                  {!w.active && (
                    <span className="rounded-full bg-zinc-800 px-2 py-0.5 text-xs font-medium text-zinc-400">
                      PAUSED
                    </span>
                  )}
                </div>
                <p className="mt-1 truncate text-sm text-zinc-300">{w.course_title}</p>

                <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-zinc-400">
                  {secInfo && (
                    <span className="font-medium text-zinc-200">
                      {secInfo.ssr_component} {secInfo.section}
                    </span>
                  )}
                  <span>{MODE_LABELS[w.mode]}</span>
                  <span>
                    Alert on: {w.trigger_on === "open_or_waitlist" ? "Open or Waitlist" : "Open only"}
                  </span>
                  {secInfo?.meetings_summary && <span>{secInfo.meetings_summary}</span>}
                </div>

                {w.open_sections && w.open_sections.length > 0 && (
                  <div className="mt-2.5 rounded-xl border border-emerald-500/35 bg-emerald-500/10 p-2.5">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="text-[11px] font-bold uppercase tracking-wider text-emerald-300">
                        Open Section Codes (click to copy)
                      </span>
                      {w.open_sections.length > 1 && (
                        <button
                          type="button"
                          onClick={() =>
                            handleCopyCode(
                              w.open_sections!.map((s) => s.class_nbr).join(", "),
                              `all-${w.id}`
                            )
                          }
                          className="inline-flex items-center gap-1 rounded-md border border-emerald-500/40 bg-zinc-950/80 px-2 py-0.5 text-[10px] font-semibold text-emerald-200 hover:bg-emerald-500/20"
                        >
                          {copiedCodeKey === `all-${w.id}` ? (
                            <Check className="h-3 w-3" />
                          ) : (
                            <Copy className="h-3 w-3" />
                          )}
                          {copiedCodeKey === `all-${w.id}` ? "Copied all" : "Copy all"}
                        </button>
                      )}
                    </div>
                    <div className="mt-1.5 flex flex-wrap gap-1.5">
                      {w.open_sections.map((sec) => {
                        const key = `card-${w.id}-${sec.class_nbr}`;
                        const isCopied = copiedCodeKey === key;
                        return (
                          <button
                            key={key}
                            type="button"
                            onClick={() => handleCopyCode(String(sec.class_nbr), key)}
                            title={`${sec.ssr_component} ${sec.section} · ${sec.meetings_summary}`}
                            className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs transition ${
                              isCopied
                                ? "border-emerald-300 bg-emerald-400 text-zinc-950 font-bold"
                                : sec.open_status === "W"
                                  ? "border-amber-500/40 bg-zinc-950/90 text-amber-200 hover:border-amber-400"
                                  : "border-emerald-500/40 bg-zinc-950/90 text-emerald-200 hover:border-emerald-400"
                            }`}
                          >
                            {isCopied ? (
                              <Check className="h-3 w-3" />
                            ) : (
                              <Copy className="h-3 w-3" />
                            )}
                            <span className="font-mono font-bold">{sec.class_nbr}</span>
                            <span className="text-[11px] opacity-85">
                              {sec.ssr_component} {sec.section}
                            </span>
                            {sec.meetings_summary && sec.meetings_summary !== "TBA" && (
                              <span className="hidden text-[10px] text-zinc-400 sm:inline">
                                · {sec.meetings_summary}
                              </span>
                            )}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>

              <div className="flex flex-wrap items-center gap-2">
                {w.class_nbr && (
                  <button
                    onClick={() => handleCopy(w)}
                    title="Copy 5-digit Class Number for Student Center"
                    className="inline-flex items-center gap-1.5 rounded-xl border border-zinc-700 bg-zinc-950 px-3 py-1.5 font-mono text-xs font-semibold text-emerald-300 hover:border-emerald-500/60"
                  >
                    {copiedId === w.id ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                    #{w.class_nbr}
                  </button>
                )}

                <a
                  href="https://studentcenter.cornell.edu"
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 rounded-xl bg-emerald-500/15 px-3 py-1.5 text-xs font-semibold text-emerald-300 ring-1 ring-emerald-500/30 hover:bg-emerald-500/25"
                >
                  Student Center
                  <ExternalLink className="h-3.5 w-3.5" />
                </a>
                <a
                  href={rosterUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 rounded-xl border border-zinc-700 px-2.5 py-1.5 text-xs text-zinc-300 hover:border-zinc-500"
                >
                  Roster
                  <ExternalLink className="h-3 w-3" />
                </a>
              </div>
            </div>

            <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-zinc-800/80 pt-3">
              <div className="text-xs text-zinc-500">
                {w.last_notified_at ? (
                  <span>Last alerted: {new Date(w.last_notified_at).toLocaleString()}</span>
                ) : (
                  <span>Cooldown: {w.cooldown_sec}s {w.auto_pause ? "· Auto-pause on alert" : ""}</span>
                )}
                {checkMsg[w.id] && <span className="ml-2 text-emerald-400">&middot; {checkMsg[w.id]}</span>}
              </div>

              <div className="flex items-center gap-1.5">
                <button
                  onClick={() => handleCheckNow(w)}
                  disabled={busyId === w.id}
                  className="inline-flex items-center gap-1 rounded-lg border border-zinc-700 px-2.5 py-1 text-xs text-zinc-300 hover:bg-zinc-800 disabled:opacity-50"
                >
                  <RefreshCw className={`h-3 w-3 ${busyId === w.id ? "animate-spin" : ""}`} />
                  Check
                </button>
                {w.last_notified_at || !w.active ? (
                  <button
                    onClick={() => handleRearm(w)}
                    disabled={busyId === w.id}
                    className="inline-flex items-center gap-1 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1 text-xs text-emerald-300 hover:bg-emerald-500/20 disabled:opacity-50"
                  >
                    <RotateCcw className="h-3 w-3" />
                    Re-Arm
                  </button>
                ) : null}
                <button
                  onClick={() => handleToggleActive(w)}
                  disabled={busyId === w.id}
                  className="inline-flex items-center gap-1 rounded-lg border border-zinc-700 px-2.5 py-1 text-xs text-zinc-300 hover:bg-zinc-800 disabled:opacity-50"
                >
                  {w.active ? <Pause className="h-3 w-3" /> : <Play className="h-3 w-3" />}
                  {w.active ? "Pause" : "Resume"}
                </button>
                <button
                  onClick={() => handleDelete(w)}
                  disabled={busyId === w.id}
                  aria-label="Delete watch"
                  className="inline-flex items-center rounded-lg border border-rose-500/20 px-2 py-1 text-xs text-rose-400 hover:bg-rose-500/15 disabled:opacity-50"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
