import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  Activity,
  Bell,
  Calendar,
  Check,
  Copy,
  Crosshair,
  GraduationCap,
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
import { CsChecklistPage } from "./components/CsChecklistPage";
import { NotificationSetup } from "./components/NotificationSetup";
import { SchedulerPage } from "./components/SchedulerPage";
import { SharedScheduleView } from "./components/SharedScheduleView";
import { TelemetryPanel } from "./components/TelemetryPanel";
import { WatchList } from "./components/WatchList";
import { useCopyFeedback } from "./hooks/useCopyFeedback";
import type {
  AuthStatus,
  CatalogSubjectRefreshedSSE,
  CourseSearchPreset,
  MetricsResponse,
  PollerMetrics,
  SeatAlertSSE,
  Watch,
} from "./types";
import { playAlertChime } from "./utils/pwa";

type Tab = "watches" | "search" | "checklist" | "scheduler" | "alerts" | "telemetry" | "admin";

export default function App() {
  const [auth, setAuth] = useState<AuthStatus | null>(null);
  const [tab, setTab] = useState<Tab>("watches");
  const [visitedTabs, setVisitedTabs] = useState<Record<Tab, boolean>>({
    watches: true,
    search: false,
    checklist: false,
    scheduler: false,
    alerts: false,
    telemetry: false,
    admin: false,
  });
  const [watches, setWatches] = useState<Watch[]>([]);
  const [metrics, setMetrics] = useState<MetricsResponse | null>(null);
  const [livePoller, setLivePoller] = useState<PollerMetrics | null>(null);
  const [sseConnected, setSseConnected] = useState(false);
  const [soundEnabled, setSoundEnabled] = useState(true);
  const soundEnabledRef = useRef(true);
  soundEnabledRef.current = soundEnabled;
  const [bannerAlert, setBannerAlert] = useState<SeatAlertSSE | null>(null);
  const bannerCopy = useCopyFeedback();
  const [lastCatalogRefresh, setLastCatalogRefresh] = useState<CatalogSubjectRefreshedSSE | null>(null);
  const [searchPreset, setSearchPreset] = useState<CourseSearchPreset | null>(null);
  const [checklistRoster, setChecklistRoster] = useState<string>("");

  const selectTab = useCallback((nextTab: Tab) => {
    setTab(nextTab);
    setVisitedTabs((prev) => (prev[nextTab] ? prev : { ...prev, [nextTab]: true }));
  }, []);

  const urlParams = new URLSearchParams(window.location.search);
  const initialInvite = urlParams.get("invite") || "";
  const highlightRaw = urlParams.get("highlight");
  const highlightClassNbr = highlightRaw ? Number(highlightRaw) : null;
  const [shareToken, setShareToken] = useState<string>(() => urlParams.get("share") || "");

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
        if (soundEnabledRef.current) playAlertChime();
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

    es.addEventListener("watches_changed", () => {
      refreshWatches();
    });

    return () => {
      es.close();
      setSseConnected(false);
    };
  }, [auth?.user?.id, refreshWatches, refreshMetrics]);

  if (shareToken) {
    return (
      <SharedScheduleView
        token={shareToken}
        onExit={() => {
          setShareToken("");
          const url = new URL(window.location.href);
          url.searchParams.delete("share");
          window.history.replaceState({}, "", url.toString());
        }}
      />
    );
  }

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
  const activeTab: Tab =
    (tab === "checklist" && user.major_mode !== "cs") || (tab === "admin" && user.role !== "admin")
      ? "watches"
      : tab;

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
          <NavBtn active={activeTab === "watches"} onClick={() => selectTab("watches")} icon={<Crosshair className="h-4 w-4" />} label={`Watchlist (${watches.length})`} />
          <NavBtn active={activeTab === "search"} onClick={() => selectTab("search")} icon={<Search className="h-4 w-4" />} label="Search Classes" />
          {user.major_mode === "cs" && (
            <NavBtn active={activeTab === "checklist"} onClick={() => selectTab("checklist")} icon={<GraduationCap className="h-4 w-4" />} label="CS Checklist" />
          )}
          <NavBtn active={activeTab === "scheduler"} onClick={() => selectTab("scheduler")} icon={<Calendar className="h-4 w-4" />} label="Scheduler" />
          <NavBtn active={activeTab === "alerts"} onClick={() => selectTab("alerts")} icon={<Bell className="h-4 w-4" />} label="Alerts & Push" />
          <NavBtn
            active={activeTab === "telemetry"}
            onClick={() => {
              selectTab("telemetry");
              refreshMetrics();
            }}
            icon={<Activity className="h-4 w-4" />}
            label="Telemetry"
          />
          {user.role === "admin" && (
            <NavBtn active={activeTab === "admin"} onClick={() => selectTab("admin")} icon={<Settings className="h-4 w-4" />} label="Admin" />
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
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => bannerCopy.copy(String(bannerAlert.class_nbr), "banner")}
                className="inline-flex items-center gap-1.5 rounded-xl border border-emerald-400/60 bg-zinc-950/90 px-3 py-1.5 font-mono text-xs font-bold text-emerald-200 hover:bg-zinc-900"
              >
                {bannerCopy.copiedKey === "banner" ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                {bannerCopy.copiedKey === "banner" ? `Copied ${bannerAlert.class_nbr}` : `Copy ${bannerAlert.class_nbr}`}
              </button>
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

      {/* Main Content (visited tabs stay mounted via CSS hidden to preserve search/filter/scroll state) */}
      <main className={`mx-auto mt-5 px-4 ${activeTab === "scheduler" ? "max-w-7xl" : "max-w-5xl"}`}>
        <div className={activeTab === "watches" ? "" : "hidden"}>
          <WatchList
            watches={watches}
            highlightClassNbr={highlightClassNbr}
            onRefresh={refreshWatches}
            onJumpToSearch={() => selectTab("search")}
          />
        </div>
        {(visitedTabs.search || activeTab === "search") && (
          <div className={activeTab === "search" ? "" : "hidden"}>
            <CourseSearch
              user={user}
              lastCatalogRefresh={lastCatalogRefresh}
              searchPreset={searchPreset}
              onClearSearchPreset={() => setSearchPreset(null)}
              onOpenChecklist={(roster) => {
                if (roster) setChecklistRoster(roster);
                selectTab("checklist");
              }}
              onUserUpdated={(updatedUser) => {
                setAuth((prev) => (prev ? { ...prev, user: updatedUser } : prev));
              }}
              onWatchCreated={() => {
                refreshWatches();
                selectTab("watches");
              }}
              onJumpToScheduler={() => selectTab("scheduler")}
            />
          </div>
        )}
        {user.major_mode === "cs" && (visitedTabs.checklist || activeTab === "checklist") && (
          <div className={activeTab === "checklist" ? "" : "hidden"}>
            <CsChecklistPage
              user={user}
              initialRoster={checklistRoster}
              lastCatalogRefresh={lastCatalogRefresh}
              onUserUpdated={(updatedUser) => {
                setAuth((prev) => (prev ? { ...prev, user: updatedUser } : prev));
              }}
              onLaunchSearch={(preset) => {
                setSearchPreset(preset);
                selectTab("search");
              }}
            />
          </div>
        )}
        {(visitedTabs.scheduler || activeTab === "scheduler") && (
          <div className={activeTab === "scheduler" ? "" : "hidden"}>
            <SchedulerPage
              lastCatalogRefresh={lastCatalogRefresh}
              onWatchesChanged={refreshWatches}
              onJumpToSearch={() => selectTab("search")}
            />
          </div>
        )}
        {(visitedTabs.alerts || activeTab === "alerts") && (
          <div className={activeTab === "alerts" ? "" : "hidden"}>
            <NotificationSetup />
          </div>
        )}
        {(visitedTabs.telemetry || activeTab === "telemetry") && (
          <div className={activeTab === "telemetry" ? "" : "hidden"}>
            <TelemetryPanel
              metrics={metrics}
              livePoller={livePoller}
              sseConnected={sseConnected}
              onRefresh={refreshMetrics}
            />
          </div>
        )}
        {user.role === "admin" && (visitedTabs.admin || activeTab === "admin") && (
          <div className={activeTab === "admin" ? "" : "hidden"}>
            <AdminPanel />
          </div>
        )}
      </main>

      {/* Mobile Bottom Nav */}
      <nav className="fixed inset-x-0 bottom-0 z-30 flex border-t border-zinc-800 bg-zinc-950/95 pb-safe backdrop-blur-md sm:hidden">
        <MobileTab active={activeTab === "watches"} onClick={() => selectTab("watches")} icon={<Crosshair className="h-4 w-4" />} label="Watches" />
        <MobileTab active={activeTab === "search"} onClick={() => selectTab("search")} icon={<Search className="h-4 w-4" />} label="Search" />
        {user.major_mode === "cs" && (
          <MobileTab active={activeTab === "checklist"} onClick={() => selectTab("checklist")} icon={<GraduationCap className="h-4 w-4" />} label="Checklist" />
        )}
        <MobileTab active={activeTab === "scheduler"} onClick={() => selectTab("scheduler")} icon={<Calendar className="h-4 w-4" />} label="Schedule" />
        <MobileTab active={activeTab === "alerts"} onClick={() => selectTab("alerts")} icon={<Bell className="h-4 w-4" />} label="Alerts" />
        <MobileTab
          active={activeTab === "telemetry"}
          onClick={() => {
            selectTab("telemetry");
            refreshMetrics();
          }}
          icon={<Activity className="h-4 w-4" />}
          label="Stats"
        />
        {user.role === "admin" && (
          <MobileTab active={activeTab === "admin"} onClick={() => selectTab("admin")} icon={<Settings className="h-4 w-4" />} label="Admin" />
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
