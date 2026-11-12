import React from "react";
import { Activity, AlertTriangle, Clock, Gauge } from "lucide-react";
import type { MetricsResponse, PollerMetrics } from "../types";
import { StatusBadge } from "./StatusBadge";

interface Props {
  metrics: MetricsResponse | null;
  livePoller: PollerMetrics | null;
  sseConnected: boolean;
}

export function TelemetryPanel({ metrics, livePoller, sseConnected }: Props) {
  const poller = livePoller || metrics?.poller;
  const events = metrics?.recent_events || [];

  if (!poller) {
    return (
      <div className="rounded-2xl border border-zinc-800 bg-zinc-900/70 p-8 text-center text-sm text-zinc-400">
        Loading telemetry...
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="rounded-2xl border border-zinc-800 bg-zinc-900/80 p-4">
          <div className="flex items-center gap-2 text-xs text-zinc-400">
            <Activity className="h-4 w-4 text-emerald-400" />
            Poller State
          </div>
          <div className="mt-1.5 flex items-center gap-2">
            <span className="text-lg font-bold uppercase text-white">{poller.state}</span>
            <span
              className={`h-2 w-2 rounded-full ${
                sseConnected ? "bg-emerald-400" : "bg-amber-400"
              }`}
              title={sseConnected ? "Live SSE connected" : "SSE reconnecting"}
            />
          </div>
        </div>

        <div className="rounded-2xl border border-zinc-800 bg-zinc-900/80 p-4">
          <div className="flex items-center gap-2 text-xs text-zinc-400">
            <Gauge className="h-4 w-4 text-sky-400" />
            Avg Cornell RTT
          </div>
          <div className="mt-1.5 text-lg font-bold text-white">
            {poller.avg_rtt_ms} <span className="text-xs font-normal text-zinc-400">ms</span>
          </div>
        </div>

        <div className="rounded-2xl border border-zinc-800 bg-zinc-900/80 p-4">
          <div className="flex items-center gap-2 text-xs text-zinc-400">
            <Clock className="h-4 w-4 text-indigo-400" />
            Total Polls
          </div>
          <div className="mt-1.5 text-lg font-bold text-white">
            {poller.total_polls}
            <span className="ml-2 text-xs font-normal text-zinc-400">
              ({poller.alerts_triggered} alerts)
            </span>
          </div>
        </div>

        <div className="rounded-2xl border border-zinc-800 bg-zinc-900/80 p-4">
          <div className="flex items-center gap-2 text-xs text-zinc-400">
            <AlertTriangle className="h-4 w-4 text-amber-400" />
            Errors / 429s
          </div>
          <div className="mt-1.5 text-lg font-bold text-white">
            {poller.error_count} / {poller.rate_limit_hits}
          </div>
        </div>
      </div>

      {poller.last_error && (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-xs text-amber-200">
          Last error: {poller.last_error}
        </div>
      )}

      <div className="rounded-2xl border border-zinc-800 bg-zinc-900/80 p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-semibold text-white">Active Deduplicated Subject Buckets</h3>
          <span className="text-xs text-zinc-400">
            Cached sections in RAM: {poller.cached_sections_count}
          </span>
        </div>

        {poller.buckets.length === 0 ? (
          <p className="text-xs text-zinc-500">No active subject buckets (poller sleeping cleanly until a watch is armed).</p>
        ) : (
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {poller.buckets.map((b) => (
              <div
                key={`${b.roster}-${b.subject}`}
                className="flex items-center justify-between rounded-xl border border-zinc-800 bg-zinc-950 px-3.5 py-2.5 text-xs"
              >
                <div>
                  <span className="font-bold text-white">
                    {b.roster} {b.subject}
                  </span>
                  <div className="text-zinc-500">
                    {b.watch_count} watch{b.watch_count === 1 ? "" : "es"} &middot; weight {b.weight}
                  </div>
                </div>
                <div className="text-right">
                  <div className="font-mono text-emerald-400">{b.last_rtt_ms}ms</div>
                  <div className="text-zinc-500">
                    {b.last_polled_at ? new Date(b.last_polled_at).toLocaleTimeString() : "queued"}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="rounded-2xl border border-zinc-800 bg-zinc-900/80 p-4">
        <h3 className="mb-3 text-sm font-semibold text-white">Recent Availability Transitions</h3>
        {events.length === 0 ? (
          <p className="text-xs text-zinc-500">No transitions detected yet.</p>
        ) : (
          <div className="space-y-1.5">
            {events.map((ev) => (
              <div
                key={ev.id}
                className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-zinc-950 px-3 py-2 text-xs"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-semibold text-white">
                    {ev.subject} {ev.catalog_nbr}
                  </span>
                  <span className="text-zinc-400">{ev.section_label}</span>
                  <span className="font-mono text-zinc-500">#{ev.class_nbr}</span>
                  <StatusBadge status={ev.new_status} />
                </div>
                <div className="text-zinc-500">
                  {ev.poll_rtt_ms}ms RTT &middot; {new Date(ev.detected_at).toLocaleString()}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
