import React, { useState } from "react";
import {
  Activity,
  Check,
  Copy,
  ExternalLink,
  Layers,
  Loader2,
  MapPin,
  Pause,
  Play,
  RefreshCw,
  RotateCcw,
  Trash2,
  X,
} from "lucide-react";
import { api } from "../api/client";
import { useCopyFeedback } from "../hooks/useCopyFeedback";
import type { Watch, WatchHistoryResponse, WatchHistoryWindow } from "../types";
import { DropOddsBadge, formatDurationSec } from "./DropOddsBadge";
import { SectionLocationTags } from "./LocationBadges";
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

function WatchHistoryDrawer({
  watch,
  activeWindow,
  data,
  loading,
  onSelectWindow,
}: {
  watch: Watch;
  activeWindow: WatchHistoryWindow;
  data?: WatchHistoryResponse;
  loading: boolean;
  onSelectWindow: (win: WatchHistoryWindow) => void;
}) {
  return (
    <div className="mt-3 space-y-3 rounded-xl border border-zinc-800 bg-zinc-950/85 p-3 text-xs">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 font-semibold text-sky-200">
          <Activity className="h-3.5 w-3.5" />
          <span>Seat Turnover &amp; Flip History</span>
        </div>
        <div className="inline-flex rounded-lg border border-zinc-800 bg-zinc-900 p-0.5 text-[11px]">
          {(
            [
              { id: "24h", label: "24h" },
              { id: "7d", label: "7d" },
              { id: "30d", label: "30d" },
              { id: "all", label: "All" },
            ] as const
          ).map((winOpt) => {
            const activeWin = activeWindow === winOpt.id;
            const winCnt = data?.windows?.[winOpt.id]?.total_flips;
            return (
              <button
                key={winOpt.id}
                type="button"
                onClick={() => onSelectWindow(winOpt.id)}
                className={`rounded-md px-2 py-0.5 font-medium ${
                  activeWin ? "bg-sky-500 text-zinc-950" : "text-zinc-400 hover:text-white"
                }`}
              >
                {winOpt.label}
                {winCnt !== undefined ? ` (${winCnt})` : ""}
              </button>
            );
          })}
        </div>
      </div>

      {loading && !data ? (
        <div className="flex items-center gap-2 py-3 text-zinc-400">
          <Loader2 className="h-3.5 w-3.5 animate-spin text-sky-400" />
          Loading flip statistics...
        </div>
      ) : (
        data && (
          <>
            {(() => {
              const curWin = activeWindow || data.window;
              const stats = data.windows[curWin];
              const odds = data.drop_odds || watch.drop_odds;
              return (
                <div className="space-y-2">
                  {odds && (
                    <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-zinc-400">
                      <span>{odds.summary}</span>
                      <span>
                        Tracked {odds.tracking_days.toFixed(1)}d
                        {odds.last_opened_at
                          ? ` · Last open ${new Date(odds.last_opened_at).toLocaleString()}`
                          : ""}
                      </span>
                    </div>
                  )}
                  <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
                    <div className="rounded-lg border border-zinc-800 bg-zinc-900/70 p-2">
                      <div className="text-[10px] text-zinc-400">Total Flips</div>
                      <div className="text-sm font-bold text-white">{stats.total_flips}</div>
                    </div>
                    <div className="rounded-lg border border-zinc-800 bg-zinc-900/70 p-2">
                      <div className="text-[10px] text-zinc-400">Opened (O)</div>
                      <div className="text-sm font-bold text-emerald-300">{stats.opened_count}</div>
                    </div>
                    <div className="rounded-lg border border-zinc-800 bg-zinc-900/70 p-2">
                      <div className="text-[10px] text-zinc-400">Closed (C)</div>
                      <div className="text-sm font-bold text-rose-300">{stats.closed_count}</div>
                    </div>
                    <div className="rounded-lg border border-zinc-800 bg-zinc-900/70 p-2">
                      <div className="text-[10px] text-zinc-400">Avg Open Window</div>
                      <div className="text-sm font-bold text-sky-200">
                        {formatDurationSec(stats.avg_open_sec)}
                      </div>
                    </div>
                    <div className="rounded-lg border border-zinc-800 bg-zinc-900/70 p-2">
                      <div className="text-[10px] text-zinc-400">Median Open</div>
                      <div className="text-sm font-bold text-emerald-200">
                        {formatDurationSec(stats.median_open_sec)}
                      </div>
                    </div>
                  </div>
                </div>
              );
            })()}

            {data.events.length === 0 ? (
              <p className="text-[11px] text-zinc-500">
                No recorded status flips in this time window yet. Flips are recorded automatically during live polling.
              </p>
            ) : (
              <div className="max-h-44 divide-y divide-zinc-800/80 overflow-y-auto rounded-lg border border-zinc-800 bg-zinc-900/40">
                {data.events.map((ev) => (
                  <div
                    key={ev.id}
                    className="flex flex-wrap items-center justify-between gap-2 px-2.5 py-1.5 text-[11px]"
                  >
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-zinc-300">#{ev.class_nbr}</span>
                      <span className="text-zinc-400">{ev.section_label}</span>
                      <span className="font-semibold text-white">
                        <span
                          className={
                            ev.old_status === "O"
                              ? "text-emerald-300"
                              : ev.old_status === "W"
                                ? "text-amber-300"
                                : "text-rose-300"
                          }
                        >
                          {ev.old_status || "?"}
                        </span>
                        {" → "}
                        <span
                          className={
                            ev.new_status === "O"
                              ? "text-emerald-300"
                              : ev.new_status === "W"
                                ? "text-amber-300"
                                : "text-rose-300"
                          }
                        >
                          {ev.new_status}
                        </span>
                      </span>
                    </div>
                    <span className="text-[10px] text-zinc-500">
                      {new Date(ev.detected_at).toLocaleString()}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </>
        )
      )}
    </div>
  );
}

export function WatchList({ watches, highlightClassNbr, onRefresh, onJumpToSearch }: Props) {
  const { copiedKey, copy } = useCopyFeedback<string>();
  const [busyId, setBusyId] = useState<number | null>(null);
  const [checkMsg, setCheckMsg] = useState<Record<number, string>>({});
  const [actionError, setActionError] = useState("");

  // Low-clutter Pick-1 Group batch mode
  const [groupingMode, setGroupingMode] = useState(false);
  const [selectedForGroup, setSelectedForGroup] = useState<number[]>([]);
  const [groupInputName, setGroupInputName] = useState("");
  const [savingGroup, setSavingGroup] = useState(false);

  // Per-watch expandable turnover stats & history
  const [expandedHistoryId, setExpandedHistoryId] = useState<number | null>(null);
  const [historyWindowById, setHistoryWindowById] = useState<Record<number, WatchHistoryWindow>>({});
  const [historyDataById, setHistoryDataById] = useState<Record<number, WatchHistoryResponse>>({});
  const [historyLoadingId, setHistoryLoadingId] = useState<number | null>(null);

  async function runWatchAction(watchId: number, action: () => Promise<void>, fallbackMsg: string) {
    setActionError("");
    setBusyId(watchId);
    try {
      await action();
      onRefresh();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : fallbackMsg);
    } finally {
      setBusyId(null);
    }
  }

  async function handleCheckNow(watch: Watch) {
    setActionError("");
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

  async function loadWatchHistory(watchId: number, window: WatchHistoryWindow) {
    setActionError("");
    setHistoryWindowById((p) => ({ ...p, [watchId]: window }));
    setHistoryLoadingId(watchId);
    try {
      const res = await api.getWatchHistory(watchId, window);
      setHistoryDataById((p) => ({ ...p, [watchId]: res }));
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to load watch history");
    } finally {
      setHistoryLoadingId((cur) => (cur === watchId ? null : cur));
    }
  }

  function handleToggleHistory(watchId: number) {
    if (expandedHistoryId === watchId) {
      setExpandedHistoryId(null);
      return;
    }
    setExpandedHistoryId(watchId);
    const win = historyWindowById[watchId] || "7d";
    void loadWatchHistory(watchId, win);
  }

  async function handleApplyGroup(clear = false) {
    if (selectedForGroup.length === 0) return;
    const label = clear ? "" : groupInputName.trim();
    if (!clear && !label) return;
    setActionError("");
    setSavingGroup(true);
    try {
      await api.batchUpdateWatchGroup(selectedForGroup, label);
      setGroupingMode(false);
      setSelectedForGroup([]);
      setGroupInputName("");
      onRefresh();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to update Pick-1 group");
    } finally {
      setSavingGroup(false);
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
      {actionError && (
        <div className="flex items-center justify-between gap-2 rounded-xl border border-rose-500/35 bg-rose-500/10 px-3.5 py-2.5 text-xs text-rose-200">
          <span>{actionError}</span>
          <button type="button" onClick={() => setActionError("")} className="text-rose-300 hover:text-white">
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      )}

      {watches.length >= 2 && (
        <div className="flex flex-wrap items-center justify-between gap-2">
          {groupingMode ? (
            <div className="flex w-full flex-wrap items-center justify-between gap-2 rounded-2xl border border-violet-500/40 bg-violet-500/10 px-3.5 py-2.5 text-xs">
              <div className="flex flex-wrap items-center gap-2">
                <Layers className="h-3.5 w-3.5 text-violet-300" />
                <span className="font-medium text-violet-100">
                  Select 2+ watches ({selectedForGroup.length} picked):
                </span>
                <input
                  type="text"
                  maxLength={48}
                  value={groupInputName}
                  onChange={(e) => setGroupInputName(e.target.value)}
                  placeholder="Group label (e.g. FWS Pick 1)"
                  className="rounded-lg border border-zinc-700 bg-zinc-950 px-2.5 py-1 text-xs text-white placeholder-zinc-500"
                />
              </div>
              <div className="flex items-center gap-1.5">
                <button
                  type="button"
                  disabled={savingGroup || selectedForGroup.length === 0 || !groupInputName.trim()}
                  onClick={() => void handleApplyGroup(false)}
                  className="rounded-lg bg-violet-500 px-2.5 py-1 text-xs font-semibold text-zinc-950 hover:bg-violet-400 disabled:opacity-40"
                >
                  Link Pick-1
                </button>
                <button
                  type="button"
                  disabled={savingGroup || selectedForGroup.length === 0}
                  onClick={() => void handleApplyGroup(true)}
                  className="rounded-lg border border-zinc-700 px-2.5 py-1 text-xs text-zinc-300 hover:bg-zinc-800 disabled:opacity-40"
                >
                  Unlink
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setGroupingMode(false);
                    setSelectedForGroup([]);
                  }}
                  className="rounded-lg p-1 text-zinc-400 hover:text-white"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
          ) : (
            <div className="ml-auto">
              <button
                type="button"
                onClick={() => setGroupingMode(true)}
                title="Group watches so triggering any 1 automatically pauses the rest"
                className="inline-flex items-center gap-1.5 rounded-xl border border-zinc-800 bg-zinc-900/80 px-2.5 py-1 text-[11px] font-medium text-zinc-300 hover:border-violet-500/40 hover:text-violet-200"
              >
                <Layers className="h-3 w-3 text-violet-400" />
                Link Pick-1 Group
              </button>
            </div>
          )}
        </div>
      )}

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
              const isCopied = copiedKey === key;
              return (
                <button
                  key={key}
                  type="button"
                  onClick={() => void copy(String(sec.class_nbr), key)}
                  title={`Click to copy ${sec.class_nbr} (${subject} ${catalogNbr} ${sec.ssr_component} ${sec.section})`}
                  className={`inline-flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs transition ${
                    isCopied
                      ? "border-emerald-300 bg-emerald-400 font-bold text-zinc-950"
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
        const rosterUrl = `https://classes.cornell.edu/browse/roster/${w.roster}/class/${w.subject}/${w.catalog_nbr}`;
        const showScopedLocation = w.mode === "any_section" && Boolean(w.ithaca_or_virtual);
        const extraOpenSections = (w.open_sections || []).filter((s) => s.class_nbr !== w.class_nbr);
        const win = historyWindowById[w.id] || "7d";

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
                  {groupingMode && (
                    <input
                      type="checkbox"
                      checked={selectedForGroup.includes(w.id)}
                      onChange={(e) => {
                        setSelectedForGroup((prev) =>
                          e.target.checked ? [...prev, w.id] : prev.filter((id) => id !== w.id)
                        );
                      }}
                      className="h-4 w-4 accent-violet-400"
                    />
                  )}
                  <span className="rounded-md bg-zinc-800 px-2 py-0.5 text-xs font-semibold text-zinc-300">
                    {w.roster}
                  </span>
                  <h3 className="text-base font-bold text-white">
                    {w.subject} {w.catalog_nbr}
                  </h3>
                  {secInfo && <StatusBadge status={secInfo.open_status} />}
                  <DropOddsBadge dropOdds={w.drop_odds} />
                  {showScopedLocation ? (
                    <span className="inline-flex items-center gap-1 rounded-md border border-emerald-500/35 bg-emerald-500/10 px-2 py-0.5 text-[11px] font-medium text-emerald-300">
                      <MapPin className="h-3 w-3" />
                      Ithaca + Virtual
                    </span>
                  ) : (
                    secInfo && <SectionLocationTags section={secInfo} />
                  )}
                  {w.group_key && (
                    <span
                      title="Pick Any 1 Group: when 1 watch in this group alerts, the others auto-pause"
                      className="inline-flex items-center gap-1 rounded-md border border-violet-500/40 bg-violet-500/15 px-2 py-0.5 text-[11px] font-medium text-violet-200"
                    >
                      <Layers className="h-3 w-3 text-violet-300" />
                      Pick-1: {w.group_key}
                      <button
                        type="button"
                        onClick={() =>
                          void runWatchAction(
                            w.id,
                            () => api.updateWatch(w.id, { group_key: "" }).then(() => undefined),
                            "Failed to remove group"
                          )
                        }
                        className="ml-0.5 text-violet-300 hover:text-white"
                        aria-label={`Remove ${w.group_key} group`}
                      >
                        <X className="h-2.5 w-2.5" />
                      </button>
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

                {extraOpenSections.length > 0 && (
                  <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[11px] text-emerald-300/90">
                    <span className="font-medium text-zinc-400">Matching open:</span>
                    {extraOpenSections.map((sec) => {
                      const key = `card-${w.id}-${sec.class_nbr}`;
                      const isCopied = copiedKey === key;
                      return (
                        <button
                          key={key}
                          type="button"
                          onClick={() => void copy(String(sec.class_nbr), key)}
                          title={`${sec.ssr_component} ${sec.section} · ${sec.meetings_summary}`}
                          className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 font-mono text-[11px] transition ${
                            isCopied
                              ? "border-emerald-300 bg-emerald-400 font-bold text-zinc-950"
                              : "border-emerald-500/40 bg-zinc-950/90 text-emerald-200 hover:border-emerald-400"
                          }`}
                        >
                          {isCopied ? <Check className="h-2.5 w-2.5" /> : <Copy className="h-2.5 w-2.5" />}
                          {sec.class_nbr}
                          <span className="font-sans text-[10px] opacity-80">
                            {sec.ssr_component} {sec.section}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>

              <div className="flex flex-wrap items-center gap-2">
                {w.class_nbr && (
                  <button
                    type="button"
                    onClick={() => void copy(String(w.class_nbr), `nbr-${w.id}`)}
                    title="Copy 5-digit Class Number for Student Center"
                    className="inline-flex items-center gap-1.5 rounded-xl border border-zinc-700 bg-zinc-950 px-3 py-1.5 font-mono text-xs font-semibold text-emerald-300 hover:border-emerald-500/60"
                  >
                    {copiedKey === `nbr-${w.id}` ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                    #{w.class_nbr}
                  </button>
                )}

                <a
                  href={rosterUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 rounded-xl border border-zinc-700 px-2.5 py-1.5 text-xs text-zinc-300 hover:border-zinc-500"
                >
                  Roster
                  <ExternalLink className="h-3 w-3" />
                </a>
                {quickOpenCodes.length === 0 && (
                  <a
                    href="https://studentcenter.cornell.edu"
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 rounded-xl bg-emerald-500/15 px-3 py-1.5 text-xs font-semibold text-emerald-300 ring-1 ring-emerald-500/30 hover:bg-emerald-500/25"
                  >
                    Student Center
                    <ExternalLink className="h-3.5 w-3.5" />
                  </a>
                )}
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
                  type="button"
                  onClick={() => handleToggleHistory(w.id)}
                  className={`inline-flex items-center gap-1 rounded-lg border px-2.5 py-1 text-xs transition ${
                    expandedHistoryId === w.id
                      ? "border-sky-500/50 bg-sky-500/15 text-sky-200"
                      : "border-zinc-700 text-zinc-300 hover:bg-zinc-800"
                  }`}
                  title="Inspect multi-window turnover stats and seat flip history"
                >
                  <Activity className="h-3 w-3 text-sky-300" />
                  <span>
                    {w.drop_odds && w.drop_odds.opened_7d > 0
                      ? `Drop Odds · ${w.drop_odds.label}`
                      : w.turnover_summary && w.turnover_summary.all > 0
                        ? `Drop Odds (${w.turnover_summary.all})`
                        : "Drop Odds"}
                  </span>
                </button>
                <button
                  type="button"
                  onClick={() => void handleCheckNow(w)}
                  disabled={busyId === w.id}
                  className="inline-flex items-center gap-1 rounded-lg border border-zinc-700 px-2.5 py-1 text-xs text-zinc-300 hover:bg-zinc-800 disabled:opacity-50"
                >
                  <RefreshCw className={`h-3 w-3 ${busyId === w.id ? "animate-spin" : ""}`} />
                  Check
                </button>
                {(w.last_notified_at || !w.active) && (
                  <button
                    type="button"
                    onClick={() =>
                      void runWatchAction(
                        w.id,
                        () => api.rearmWatch(w.id).then(() => undefined),
                        "Failed to re-arm watch"
                      )
                    }
                    disabled={busyId === w.id}
                    className="inline-flex items-center gap-1 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1 text-xs text-emerald-300 hover:bg-emerald-500/20 disabled:opacity-50"
                  >
                    <RotateCcw className="h-3 w-3" />
                    Re-Arm
                  </button>
                )}
                <button
                  type="button"
                  onClick={() =>
                    void runWatchAction(
                      w.id,
                      () => api.updateWatch(w.id, { active: !w.active }).then(() => undefined),
                      "Failed to update watch"
                    )
                  }
                  disabled={busyId === w.id}
                  className="inline-flex items-center gap-1 rounded-lg border border-zinc-700 px-2.5 py-1 text-xs text-zinc-300 hover:bg-zinc-800 disabled:opacity-50"
                >
                  {w.active ? <Pause className="h-3 w-3" /> : <Play className="h-3 w-3" />}
                  {w.active ? "Pause" : "Resume"}
                </button>
                <button
                  type="button"
                  onClick={() =>
                    void runWatchAction(
                      w.id,
                      () => api.deleteWatch(w.id).then(() => undefined),
                      "Failed to delete watch"
                    )
                  }
                  disabled={busyId === w.id}
                  aria-label="Delete watch"
                  className="inline-flex items-center rounded-lg border border-rose-500/20 px-2 py-1 text-xs text-rose-400 hover:bg-rose-500/15 disabled:opacity-50"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>

            {expandedHistoryId === w.id && (
              <WatchHistoryDrawer
                watch={w}
                activeWindow={win}
                data={historyDataById[w.id]}
                loading={historyLoadingId === w.id}
                onSelectWindow={(nextWin) => void loadWatchHistory(w.id, nextWin)}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}
