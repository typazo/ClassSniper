import React, { useEffect, useState } from "react";
import { Bell, BellRing, CheckCircle2, MessageSquare, Smartphone, Trash2 } from "lucide-react";
import { api } from "../api/client";
import type { NotifyPreferences } from "../types";
import {
  detectDeviceLabel,
  isIosDevice,
  isStandalonePwa,
  registerAndSubscribePush,
  supportsWebPush,
} from "../utils/pwa";

export function NotificationSetup() {
  const [prefs, setPrefs] = useState<NotifyPreferences | null>(null);
  const [discordUserId, setDiscordUserId] = useState("");
  const [discordPingEnabled, setDiscordPingEnabled] = useState(true);
  const [webPushEnabled, setWebPushEnabled] = useState(true);
  const [personalWebhookUrl, setPersonalWebhookUrl] = useState("");
  const [deviceLabel, setDeviceLabel] = useState(detectDeviceLabel());
  const [busy, setBusy] = useState(false);
  const [statusMsg, setStatusMsg] = useState("");
  const [error, setError] = useState("");
  const [testResults, setTestResults] = useState<
    Array<{ channel: string; status: string; latency_ms?: number; detail: string }>
  >([]);

  const onIosNonStandalone = isIosDevice() && !isStandalonePwa();

  async function loadPrefs() {
    try {
      const data = await api.getNotifyPreferences();
      setPrefs(data);
      setDiscordUserId(data.discord_user_id);
      setDiscordPingEnabled(data.discord_ping_enabled);
      setWebPushEnabled(data.web_push_enabled);
      setPersonalWebhookUrl(data.personal_webhook_url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load notification settings");
    }
  }

  useEffect(() => {
    loadPrefs();
  }, []);

  async function handleEnablePush() {
    setError("");
    setStatusMsg("");
    setBusy(true);
    try {
      const { public_key } = await api.getVapidKey();
      const sub = await registerAndSubscribePush(public_key);
      await api.subscribePush(sub, deviceLabel || detectDeviceLabel());
      setStatusMsg("Push notifications enabled on this device!");
      await loadPrefs();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to enable push notifications");
    } finally {
      setBusy(false);
    }
  }

  async function handleRemoveSub(id: number) {
    await api.unsubscribePush(id);
    await loadPrefs();
  }

  async function handleSavePrefs(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setStatusMsg("");
    setBusy(true);
    try {
      await api.updateNotifyPreferences({
        discord_user_id: discordUserId,
        discord_ping_enabled: discordPingEnabled,
        web_push_enabled: webPushEnabled,
        personal_webhook_url: personalWebhookUrl,
      });
      setStatusMsg("Notification preferences saved.");
      await loadPrefs();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save preferences");
    } finally {
      setBusy(false);
    }
  }

  async function handleTest(target: "all" | "web_push" | "discord") {
    setError("");
    setBusy(true);
    try {
      const res = await api.sendTestNotify(target);
      setTestResults(res.results);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Test alert failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5">
      {statusMsg && (
        <div className="flex items-center gap-2 rounded-xl border border-emerald-500/30 bg-emerald-500/15 px-4 py-3 text-sm text-emerald-200">
          <CheckCircle2 className="h-4 w-4 shrink-0" />
          {statusMsg}
        </div>
      )}
      {error && (
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-300">
          {error}
        </div>
      )}

      {/* PWA Web Push Card */}
      <div className="rounded-2xl border border-zinc-800 bg-zinc-900/80 p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <div className="rounded-xl bg-emerald-500/15 p-2.5 text-emerald-400">
              <Smartphone className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-white">PWA Web Push (Fastest Mobile Lockscreen Alerts)</h2>
              <p className="mt-0.5 text-xs text-zinc-400">
                Rings your phone directly via Apple APNs / Chrome Push—no extra app download and no Discord desktop idle delay.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => handleTest("web_push")}
            disabled={busy}
            className="rounded-xl border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-200 hover:bg-zinc-800"
          >
            Test Web Push
          </button>
        </div>

        {onIosNonStandalone && (
          <div className="mt-4 rounded-xl border border-amber-500/30 bg-amber-500/10 p-3.5 text-xs text-amber-200">
            <p className="font-semibold">iPhone / iPad Required Step (iOS 16.4+):</p>
            <ol className="mt-1.5 list-inside list-decimal space-y-1 text-amber-100/90">
              <li>
                Open this page in <strong>Safari</strong>, tap the <strong>Share</strong> icon, and choose{" "}
                <strong>Add to Home Screen</strong>.
              </li>
              <li>
                Launch <strong>ClassSniper</strong> from your Home Screen icon, then tap{" "}
                <strong>Enable Push on This Device</strong> below.
              </li>
            </ol>
          </div>
        )}

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <input
            type="text"
            value={deviceLabel}
            onChange={(e) => setDeviceLabel(e.target.value)}
            placeholder="Device label (e.g. Tyler's iPhone)"
            className="min-w-[200px] flex-1 rounded-xl border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-white"
          />
          <button
            type="button"
            onClick={handleEnablePush}
            disabled={busy || !supportsWebPush()}
            className="inline-flex items-center gap-1.5 rounded-xl bg-emerald-500 px-4 py-2 text-sm font-semibold text-zinc-950 hover:bg-emerald-400 disabled:opacity-50"
          >
            <BellRing className="h-4 w-4" />
            Enable Push on This Device
          </button>
        </div>

        {!supportsWebPush() && (
          <p className="mt-2 text-xs text-zinc-500">
            Web Push requires HTTPS (or localhost) and Safari Home Screen mode on iOS.
          </p>
        )}

        {prefs && prefs.push_subscriptions.length > 0 && (
          <div className="mt-4 space-y-2">
            <div className="text-xs font-medium text-zinc-400">Registered Devices</div>
            {prefs.push_subscriptions.map((sub) => (
              <div
                key={sub.id}
                className="flex items-center justify-between rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 text-xs"
              >
                <div>
                  <span className="font-semibold text-zinc-200">{sub.device_label}</span>
                  <span className="ml-2 text-zinc-500">added {new Date(sub.created_at).toLocaleDateString()}</span>
                </div>
                <button
                  type="button"
                  onClick={() => handleRemoveSub(sub.id)}
                  className="text-rose-400 hover:text-rose-300"
                  aria-label="Remove device"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Shared Discord Channel @mention Card */}
      <form onSubmit={handleSavePrefs} className="rounded-2xl border border-zinc-800 bg-zinc-900/80 p-5 space-y-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <div className="rounded-xl bg-indigo-500/15 p-2.5 text-indigo-400">
              <MessageSquare className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-white">Shared Discord Channel Pings</h2>
              <p className="mt-0.5 text-xs text-zinc-400">
                Join the shared Discord alerts channel, set its notifications to <strong>Only @mentions</strong>, and enter your Discord User ID below.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => handleTest("discord")}
            disabled={busy}
            className="rounded-xl border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-200 hover:bg-zinc-800"
          >
            Test Discord Ping
          </button>
        </div>

        <div className="rounded-xl border border-zinc-800 bg-zinc-950 p-3.5 text-xs text-zinc-300 space-y-1.5">
          <div className="font-semibold text-zinc-100">How to copy your Discord User ID (15 seconds):</div>
          <ol className="list-inside list-decimal space-y-1 text-zinc-400">
            <li>
              In Discord Settings &rarr; <strong>Advanced</strong> (Desktop or Mobile), toggle on <strong>Developer Mode</strong>.
            </li>
            <li>
              Click/tap your own profile in any server chat &rarr; <strong>Copy User ID</strong> (a 17–19 digit number).
            </li>
            <li>
              In the shared <code>#class-alerts</code> channel settings, set Notifications to <strong>Only @mentions</strong> so you only get pinged for your classes.
            </li>
          </ol>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <label className="mb-1 block text-xs font-medium text-zinc-300">Your Discord User ID</label>
            <input
              type="text"
              value={discordUserId}
              onChange={(e) => setDiscordUserId(e.target.value)}
              placeholder="e.g. 123456789012345678"
              className="w-full rounded-xl border border-zinc-700 bg-zinc-950 px-3 py-2 font-mono text-sm text-white placeholder-zinc-500"
            />
          </div>

          {prefs?.allow_custom_personal_webhooks && (
            <div>
              <label className="mb-1 block text-xs font-medium text-zinc-300">
                Optional Personal Webhook URL (Private Channel)
              </label>
              <input
                type="url"
                value={personalWebhookUrl}
                onChange={(e) => setPersonalWebhookUrl(e.target.value)}
                placeholder="https://discord.com/api/webhooks/..."
                className="w-full rounded-xl border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-white placeholder-zinc-500"
              />
            </div>
          )}
        </div>

        <div className="flex flex-wrap gap-4 text-xs text-zinc-300">
          <label className="flex cursor-pointer items-center gap-2">
            <input
              type="checkbox"
              checked={webPushEnabled}
              onChange={(e) => setWebPushEnabled(e.target.checked)}
              className="accent-emerald-500"
            />
            Send Web Push alerts
          </label>
          <label className="flex cursor-pointer items-center gap-2">
            <input
              type="checkbox"
              checked={discordPingEnabled}
              onChange={(e) => setDiscordPingEnabled(e.target.checked)}
              className="accent-emerald-500"
            />
            Ping me in shared Discord channel
            {prefs && !prefs.shared_discord_configured && (
              <span className="text-amber-400">(Shared webhook not configured by admin yet)</span>
            )}
          </label>
        </div>

        <div className="flex justify-end">
          <button
            type="submit"
            disabled={busy}
            className="rounded-xl bg-emerald-500 px-4 py-2 text-sm font-semibold text-zinc-950 hover:bg-emerald-400 disabled:opacity-50"
          >
            Save Preferences
          </button>
        </div>
      </form>

      {testResults.length > 0 && (
        <div className="rounded-2xl border border-zinc-800 bg-zinc-900/80 p-4 space-y-2">
          <div className="flex items-center gap-2 text-xs font-semibold text-zinc-200">
            <Bell className="h-4 w-4 text-emerald-400" />
            Test Dispatch Results
          </div>
          {testResults.map((r, idx) => (
            <div key={idx} className="flex items-center justify-between rounded-xl bg-zinc-950 px-3 py-2 text-xs">
              <span className="font-medium text-zinc-200">{r.channel}</span>
              <span className={r.status === "sent" ? "text-emerald-400" : "text-amber-300"}>
                {r.status} {r.latency_ms ? `(${r.latency_ms}ms)` : ""} &middot; {r.detail}
              </span>
            </div>
          ))}
        </div>
      )}

      {prefs && prefs.recent_deliveries.length > 0 && (
        <div className="rounded-2xl border border-zinc-800 bg-zinc-900/80 p-4">
          <h3 className="mb-3 text-sm font-semibold text-white">Recent Alert Deliveries</h3>
          <div className="space-y-1.5">
            {prefs.recent_deliveries.map((d) => (
              <div
                key={d.id}
                className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-zinc-950 px-3 py-2 text-xs"
              >
                <div className="text-zinc-300">
                  <span className="font-semibold">
                    {d.subject ? `${d.subject} ${d.catalog_nbr} ${d.section_label}` : d.channel_kind}
                  </span>
                  {d.class_nbr && <span className="ml-2 font-mono text-zinc-500">#{d.class_nbr}</span>}
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-zinc-500">{d.channel_kind}</span>
                  <span className={d.status === "sent" ? "text-emerald-400" : "text-rose-400"}>
                    {d.status} ({d.latency_ms}ms)
                  </span>
                  <span className="text-zinc-500">{new Date(d.sent_at).toLocaleTimeString()}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
