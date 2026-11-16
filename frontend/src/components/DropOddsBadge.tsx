import React from "react";
import { TrendingUp } from "lucide-react";
import type { DropOddsSummary, DropOddsTier } from "../types";

export function formatDurationSec(sec: number | null | undefined): string {
  if (sec === null || sec === undefined) return "—";
  const rounded = Math.max(0, Math.round(sec));
  if (rounded < 60) return `${rounded}s`;
  if (rounded < 3600) {
    const m = Math.floor(rounded / 60);
    const s = rounded % 60;
    return s > 0 ? `${m}m ${s}s` : `${m}m`;
  }
  const h = Math.floor(rounded / 3600);
  const m = Math.floor((rounded % 3600) / 60);
  return m > 0 ? `${h}h ${m}m` : `${h}h`;
}

const TIER_STYLES: Record<DropOddsTier, string> = {
  high: "border-emerald-500/45 bg-emerald-500/15 text-emerald-200",
  moderate: "border-sky-500/45 bg-sky-500/15 text-sky-200",
  low: "border-amber-500/40 bg-amber-500/15 text-amber-200",
  none: "border-zinc-700/90 bg-zinc-800/80 text-zinc-400",
  untracked: "border-zinc-800 bg-zinc-900/90 text-zinc-500",
};

interface Props {
  dropOdds?: DropOddsSummary | null;
  compact?: boolean;
}

export function DropOddsBadge({ dropOdds, compact = false }: Props) {
  if (!dropOdds) return null;

  const tone = TIER_STYLES[dropOdds.tier] || TIER_STYLES.untracked;
  const medianNote =
    dropOdds.median_open_sec_7d != null
      ? ` · Median open ${formatDurationSec(dropOdds.median_open_sec_7d)}`
      : "";
  const tooltip = `${dropOdds.summary} · Tracked ${dropOdds.tracking_days.toFixed(1)}d${medianNote}`;

  const subtext =
    dropOdds.opened_7d > 0
      ? `${dropOdds.opened_7d}/7d`
      : dropOdds.opened_all > 0
        ? `${dropOdds.opened_all} all`
        : dropOdds.tier === "none" && dropOdds.tracking_days >= 1
          ? `${dropOdds.tracking_days.toFixed(0)}d`
          : "";

  return (
    <span
      title={tooltip}
      className={`inline-flex items-center gap-1 rounded-md border font-semibold ${
        compact ? "px-1.5 py-0.5 text-[10px]" : "px-2 py-0.5 text-[11px]"
      } ${tone}`}
    >
      <TrendingUp className={compact ? "h-2.5 w-2.5" : "h-3 w-3"} />
      <span>Drop Odds: {dropOdds.label}</span>
      {subtext && <span className="opacity-80">({subtext})</span>}
    </span>
  );
}
