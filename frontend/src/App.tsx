import React, { useCallback, useEffect, useState } from "react";
import {
  Activity,
  Bell,
  Crosshair,
  LogOut,
  Search,
  Settings,
  Volume2,
  VolumeX,
  ExternalLink,
} from "lucide-react";
import { api } from "./api/client";
import { AdminPanel } from "./components/AdminPanel";
import { AuthScreen } from "./components/AuthScreen";
import { CourseSearch } from "./components/CourseSearch";
import { NotificationSetup } from "./components/NotificationSetup";
import { TelemetryPanel } from "./components/TelemetryPanel";
import { WatchList } from "./components/WatchList";
import type {
  AuthStatus,
  CatalogSubjectRefreshedSSE,
  MetricsResponse,
  PollerMetrics,
  SeatAlertSSE,
  Watch,
} from "./types";
import { playAlertChime } from "./utils/pwa";

type Tab = "watches" | "search" | "alerts" | "telemetry" | "admin";

export default function App() {
  const [auth, setAuth] = useState<AuthStatus | null>(null);
  const [tab, setTab] = useState<Tab>("watches");
  const [watches, setWatches] = useState<Watch[]>([]);
  const [metrics, setMetrics] = useState<MetricsResponse | null>(null);
  const [livePoller, setLivePoller] = useState<PollerMetrics | null>(null);
  const [sseConnected, setSseConnected] = useState(false);
  const [soundEnabled, setSoundEnabled] = useState(true);
  const [bannerAlert, setBannerAlert] = useState<SeatAlertSSE | null>(null);
  const [lastCatalogRefresh, setLastCatalogRefresh] = useState<CatalogSubjectRefreshedSSE | null>(null);

  const urlParams = new URLSearchParams(window.location.search);
  const initialInvite = urlParams.get("invite") || "";
  const highlightRaw = urlParams.get("highlight");
  const highlightClassNbr = highlightRaw ? Number(highlightRaw) : null;

  const refreshAuth = useCallback(async () => {
    const status = await api.authStatus();
    setAuth(status);
  }, []);

  const refreshWatches = useCallback(async () => {
    try {
      const res = await api.listWatches();
      setWatches(res.watches);
    } catch {
      // ignore if signed out
    }
  }, []);

  const refreshMetrics = useCallback(async () => {
    try {
      const res = await api.getMetrics();
      setMetrics(res);
      setLivePoller(res.poller);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    refreshAuth();
  }, [refreshAuth]);

  useEffect(() => {
    if (!auth?.user) return;
    refreshWatches();
    refreshMetrics();

    const es = new EventSource("/api/events/stream", { withCredentials: true });
    es.onopen = () => setSseConnected(true);
    es.onerror = () => setSseConnected(false);

    es.addEventListener("telemetry", (ev) => {
      try {
        setLivePoller(JSON.parse((ev as MessageEvent).data));
      } catch {
        // ignore
      }
    });

    es.addEventListener("seat_alert", (ev) => {
      try {
        const alert: SeatAlertSSE = JSON.parse((ev as MessageEvent).data);
        setBannerAlert(alert);
        if (soundEnabled) playAlertChime();
        refreshWatches();
        refreshMetrics();
      } catch {
        // ignore
      }
    });

    es.addEventListener("catalog_subject_refreshed", (ev) => {
      try {
        setLastCatalogRefresh(JSON.parse((ev as MessageEvent).data));
      } catch {
        // ignore
      }
    });

    return () => {
      es.close();
      setSseConnected(false);
    };
  }, [auth?.user, refreshWatches, refreshMetrics, soundEnabled]);

  if (!auth) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-950 text-sm text-zinc-400">
        Loading ClassSniper...
      </div>
    );
  }

  if (!auth.user) {
    return (
      <AuthScreen
        needsBootstrap={auth.needs_bootstrap}
        initialInviteCode={initialInvite}
        appDomain={auth.app_domain}
        onAuthenticated={(user) => setAuth({ ...auth, needs_bootstrap: false, user })}
      />
    );
  }

  const user = auth.user;
  const activeCount = watches.filter((w) => w.active).length;

  return (
    <div className="min-h-screen bg-zinc-950 pb-20 text-zinc-100 sm:pb-8">
      {/* Top Header */}
      <header className="sticky top-0 z-30 border-b border-zinc-800/80 bg-zinc-950/90 backdrop-blur-md">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-emerald-500/15 ring-1 ring-emerald-500/30">
              <Crosshair className="h-5 w-5 text-emerald-400" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-bold tracking-tight text-white">ClassSniper</span>
                <span
                  className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ${
                    livePoller?.state === "polling"
                      ? "bg-emerald-500/15 text-emerald-300"
                      : livePoller?.state === "backoff"
                        ? "bg-amber-500/15 text-amber-300"
                        : "bg-zinc-800 text-zinc-400"
                  }`}
                >
                  <span
                    className={`h-1.5 w-1.5 rounded-full ${
                      livePoller?.state === "polling" ? "animate-pulse bg-emerald-400" : "bg-zinc-500"
                    }`}
                  />
                  {livePoller?.state || "ready"}
                </span>
              </div>
              <p className="text-[11px] text-zinc-500">
                {user.username} ({user.role}) &middot; {activeCount} active watch{activeCount === 1 ? "" : "es"}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setSoundEnabled((s) => !s)}
              title={soundEnabled ? "Browser alert chime on" : "Browser alert chime muted"}
              className="rounded-xl border border-zinc-800 p-2 text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200"
            >
              {soundEnabled ? <Volume2 className="h-4 w-4 text-emerald-400" /> : <VolumeX className="h-4 w-4" />}
            </button>
            <button
              type="button"
              onClick={async () => {
                await api.logout();
                setAuth({ ...auth, user: null });
              }}
              title="Sign out"
              className="inline-flex items-center gap-1.5 rounded-xl border border-zinc-800 px-3 py-1.5 text-xs text-zinc-300 hover:bg-zinc-900"
            >
              <LogOut className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Sign Out</span>
            </button>
          </div>
        </div>

        {/* Desktop Nav */}
        <div className="mx-auto hidden max-w-5xl gap-1 px-4 pb-2 sm:flex">
          <NavBtn active={tab === "watches"} onClick={() => setTab("watches")} icon={<Crosshair className="h-4 w-4" />} label={`Watchlist (${watches.length})`} />
          <NavBtn active={tab === "search"} onClick={() => setTab("search")} icon={<Search className="h-4 w-4" />} label="Search Classes" />
          <NavBtn active={tab === "alerts"} onClick={() => setTab("alerts")} icon={<Bell className="h-4 w-4" />} label="Alerts & Push" />
          <NavBtn
            active={tab === "telemetry"}
            onClick={() => {
              setTab("telemetry");
              refreshMetrics();
            }}
            icon={<Activity className="h-4 w-4" />}
            label="Telemetry"
          />
          {user.role === "admin" && (
            <NavBtn active={tab === "admin"} onClick={() => setTab("admin")} icon={<Settings className="h-4 w-4" />} label="Admin" />
          )}
        </div>
      </header>

      {/* Live Alert Banner */}
      {bannerAlert && (
        <div className="mx-auto mt-4 max-w-5xl px-4">
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-emerald-400/50 bg-emerald-500/15 p-4 shadow-lg">
            <div>
              <div className="text-sm font-bold text-emerald-200">
                SEAT OPENED: {bannerAlert.subject} {bannerAlert.catalog_nbr} ({bannerAlert.section_label}) — #{bannerAlert.class_nbr}
              </div>
              <div className="text-xs text-emerald-200/80">
                {bannerAlert.course_title} &middot; Detected in {bannerAlert.poll_rtt_ms}ms
              </div>
            </div>
            <div className="flex items-center gap-2">
              <a
                href={bannerAlert.student_center_url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 rounded-xl bg-emerald-400 px-3 py-1.5 text-xs font-bold text-zinc-950 hover:bg-emerald-300"
              >
                Open Student Center
                <ExternalLink className="h-3.5 w-3.5" />
              </a>
              <button
                type="button"
                onClick={() => setBannerAlert(null)}
                className="rounded-xl border border-emerald-400/30 px-2.5 py-1.5 text-xs text-emerald-200"
              >
                Dismiss
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Main Content */}
      <main className="mx-auto mt-5 max-w-5xl px-4">
        {tab === "watches" && (
          <WatchList
            watches={watches}
            highlightClassNbr={highlightClassNbr}
            onRefresh={refreshWatches}
            onJumpToSearch={() => setTab("search")}
          />
        )}
        {tab === "search" && (
          <CourseSearch
            user={user}
            lastCatalogRefresh={lastCatalogRefresh}
            onWatchCreated={() => {
              refreshWatches();
              setTab("watches");
            }}
          />
        )}
        {tab === "alerts" && <NotificationSetup />}
        {tab === "telemetry" && (
          <TelemetryPanel metrics={metrics} livePoller={livePoller} sseConnected={sseConnected} />
        )}
        {tab === "admin" && user.role === "admin" && <AdminPanel />}
      </main>

      {/* Mobile Bottom Nav */}
      <nav className="fixed inset-x-0 bottom-0 z-30 flex border-t border-zinc-800 bg-zinc-950/95 pb-safe backdrop-blur-md sm:hidden">
        <MobileTab active={tab === "watches"} onClick={() => setTab("watches")} icon={<Crosshair className="h-4 w-4" />} label="Watches" />
        <MobileTab active={tab === "search"} onClick={() => setTab("search")} icon={<Search className="h-4 w-4" />} label="Search" />
        <MobileTab active={tab === "alerts"} onClick={() => setTab("alerts")} icon={<Bell className="h-4 w-4" />} label="Alerts" />
        <MobileTab
          active={tab === "telemetry"}
          onClick={() => {
            setTab("telemetry");
            refreshMetrics();
          }}
          icon={<Activity className="h-4 w-4" />}
          label="Stats"
        />
        {user.role === "admin" && (
          <MobileTab active={tab === "admin"} onClick={() => setTab("admin")} icon={<Settings className="h-4 w-4" />} label="Admin" />
        )}
      </nav>
    </div>
  );
}

function NavBtn({
  active,
  onClick,
  icon,
  label,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex items-center gap-2 rounded-xl px-3.5 py-2 text-xs font-semibold transition ${
        active
          ? "bg-zinc-800 text-white"
          : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200"
      }`}
    >
      {icon}
      {label}
    </button>
  );
}

function MobileTab({
  active,
  onClick,
  icon,
  label,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex flex-1 flex-col items-center justify-center gap-1 py-2.5 text-[11px] font-medium ${
        active ? "text-emerald-400" : "text-zinc-400"
      }`}
    >
      {icon}
      {label}
    </button>
  );
}
