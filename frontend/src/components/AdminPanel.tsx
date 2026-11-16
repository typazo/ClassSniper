import React, { useEffect, useState } from "react";
import { Check, Copy, Database, Link2, Save, Trash2, Users } from "lucide-react";
import { api } from "../api/client";
import { useCopyFeedback } from "../hooks/useCopyFeedback";
import type { AdminSettings, AdminUserItem, InviteItem } from "../types";

export function AdminPanel() {
  const [invites, setInvites] = useState<InviteItem[]>([]);
  const [users, setUsers] = useState<AdminUserItem[]>([]);
  const [settings, setSettings] = useState<AdminSettings | null>(null);
  const [sharedWebhook, setSharedWebhook] = useState("");
  const [pollRps, setPollRps] = useState(0.9);
  const [inviteNote, setInviteNote] = useState("");
  const [inviteUses, setInviteUses] = useState(1);
  const [latestInviteUrl, setLatestInviteUrl] = useState("");
  const { copiedKey, copy } = useCopyFeedback<string>();
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");

  async function loadAll() {
    try {
      const [invRes, usrRes, setRes] = await Promise.all([
        api.listInvites(),
        api.listUsers(),
        api.getAdminSettings(),
      ]);
      setInvites(invRes.invites);
      setUsers(usrRes.users);
      setSettings(setRes);
      setSharedWebhook(setRes.discord_shared_webhook_url);
      setPollRps(setRes.poll_max_rps);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load admin data");
    }
  }

  useEffect(() => {
    loadAll();
  }, []);

  async function handleSaveSettings(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setMsg("");
    try {
      await api.updateAdminSettings({
        discord_shared_webhook_url: sharedWebhook,
        poll_max_rps: pollRps,
      });
      setMsg("Admin settings updated live.");
      await loadAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save settings");
    }
  }

  async function handleCreateInvite(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      const res = await api.createInvite({
        max_uses: inviteUses,
        expires_hours: 72,
        note: inviteNote,
      });
      setLatestInviteUrl(res.invite_url);
      setInviteNote("");
      await loadAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create invite");
    }
  }

  function handleCopyInvite(code: string) {
    const origin = settings?.app_origin || window.location.origin;
    void copy(`${origin}/?invite=${code}`, code);
  }

  async function handleDeleteInvite(code: string) {
    if (!window.confirm(`Revoke invite ${code}?`)) return;
    setError("");
    setBusyAction(`inv:${code}`);
    try {
      await api.deleteInvite(code);
      await loadAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete invite");
    } finally {
      setBusyAction(null);
    }
  }

  async function handleDeleteUser(u: AdminUserItem) {
    if (!window.confirm(`Remove user "${u.username}" and all their watches/schedules?`)) return;
    setError("");
    setBusyAction(`user:${u.id}`);
    try {
      await api.deleteUser(u.id);
      await loadAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to remove user");
    } finally {
      setBusyAction(null);
    }
  }

  async function handleFullSync() {
    setError("");
    setMsg("");
    try {
      const res = await api.syncCatalog();
      setMsg(`Full catalog background sync: ${res.status}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sync failed");
    }
  }

  return (
    <div className="space-y-5">
      {msg && (
        <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/15 px-4 py-3 text-sm text-emerald-200">
          {msg}
        </div>
      )}
      {error && (
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-300">
          {error}
        </div>
      )}

      {/* Server & Shared Discord Webhook Settings */}
      <form onSubmit={handleSaveSettings} className="rounded-2xl border border-zinc-800 bg-zinc-900/80 p-5 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-base font-bold text-white">Poller &amp; Shared Discord Channel</h2>
          <button
            type="button"
            onClick={handleFullSync}
            className="inline-flex items-center gap-1.5 rounded-xl border border-zinc-700 px-3 py-1.5 text-xs text-zinc-200 hover:bg-zinc-800"
          >
            <Database className="h-3.5 w-3.5" />
            Sync Full Roster Catalog
          </button>
        </div>

        <div className="grid gap-3 sm:grid-cols-3">
          <div className="sm:col-span-2">
            <label className="mb-1 block text-xs font-medium text-zinc-300">
              Shared #class-alerts Discord Webhook URL
            </label>
            <input
              type="url"
              value={sharedWebhook}
              onChange={(e) => setSharedWebhook(e.target.value)}
              placeholder="https://discord.com/api/webhooks/..."
              className="w-full rounded-xl border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-white placeholder-zinc-500"
            />
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-zinc-300">
              Max Poll Rate (req/sec)
            </label>
            <input
              type="number"
              step="0.1"
              min={0.2}
              max={3.0}
              value={pollRps}
              onChange={(e) => setPollRps(Number(e.target.value))}
              className="w-full rounded-xl border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-white"
            />
            <p className="mt-1 text-[11px] text-zinc-500">Cornell guideline: &le; 1.0 req/s</p>
          </div>
        </div>

        <div className="flex justify-end">
          <button
            type="submit"
            className="inline-flex items-center gap-1.5 rounded-xl bg-emerald-500 px-4 py-2 text-sm font-semibold text-zinc-950 hover:bg-emerald-400"
          >
            <Save className="h-4 w-4" />
            Save Server Settings
          </button>
        </div>
      </form>

      {/* Invites */}
      <div className="rounded-2xl border border-zinc-800 bg-zinc-900/80 p-5 space-y-4">
        <div className="flex items-center gap-2">
          <Link2 className="h-4 w-4 text-emerald-400" />
          <h2 className="text-base font-bold text-white">Invite Friends</h2>
        </div>

        <form onSubmit={handleCreateInvite} className="flex flex-wrap gap-2">
          <input
            type="text"
            value={inviteNote}
            onChange={(e) => setInviteNote(e.target.value)}
            placeholder="Label (e.g. Alex)"
            className="min-w-[160px] flex-1 rounded-xl border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-white"
          />
          <input
            type="number"
            min={1}
            max={50}
            value={inviteUses}
            onChange={(e) => setInviteUses(Number(e.target.value))}
            className="w-24 rounded-xl border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-white"
            title="Max uses"
          />
          <button
            type="submit"
            className="rounded-xl bg-emerald-500 px-4 py-2 text-sm font-semibold text-zinc-950 hover:bg-emerald-400"
          >
            Generate Invite
          </button>
        </form>

        {latestInviteUrl && (
          <div className="flex items-center justify-between gap-2 rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-3.5 py-2.5 text-xs text-emerald-200">
            <span className="truncate font-mono">{latestInviteUrl}</span>
            <button
              type="button"
              onClick={() => void copy(latestInviteUrl, "latest")}
              className="inline-flex shrink-0 items-center gap-1 rounded-lg bg-emerald-500/20 px-2.5 py-1 font-semibold hover:bg-emerald-500/30"
            >
              {copiedKey === "latest" ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
              {copiedKey === "latest" ? "Copied" : "Copy Link"}
            </button>
          </div>
        )}

        <div className="space-y-1.5">
          {invites.map((inv) => (
            <div
              key={inv.code}
              className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-zinc-950 px-3 py-2 text-xs"
            >
              <div>
                <span className="font-mono font-semibold text-zinc-200">{inv.code}</span>
                {inv.note && <span className="ml-2 text-zinc-400">({inv.note})</span>}
                <span className="ml-2 text-zinc-500">
                  {inv.uses_count}/{inv.max_uses} uses
                </span>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => handleCopyInvite(inv.code)}
                  className="inline-flex items-center gap-1 rounded-lg border border-zinc-700 px-2 py-1 text-zinc-300 hover:bg-zinc-800"
                >
                  {copiedKey === inv.code ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3" />}
                  {copiedKey === inv.code ? "Copied" : "Copy URL"}
                </button>
                <button
                  type="button"
                  disabled={busyAction === `inv:${inv.code}`}
                  onClick={() => void handleDeleteInvite(inv.code)}
                  className="text-rose-400 hover:text-rose-300 disabled:opacity-40"
                  aria-label={`Delete invite ${inv.code}`}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Users */}
      <div className="rounded-2xl border border-zinc-800 bg-zinc-900/80 p-5 space-y-3">
        <div className="flex items-center gap-2">
          <Users className="h-4 w-4 text-emerald-400" />
          <h2 className="text-base font-bold text-white">Users ({users.length})</h2>
        </div>

        <div className="space-y-1.5">
          {users.map((u) => (
            <div
              key={u.id}
              className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-zinc-950 px-3 py-2 text-xs"
            >
              <div>
                <span className="font-semibold text-white">{u.username}</span>
                <span className="ml-2 rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] uppercase text-zinc-300">
                  {u.role}
                </span>
                <span className="ml-2 text-zinc-500">
                  {u.active_watches} watches &middot; {u.push_devices} push devices
                </span>
              </div>
              {u.role !== "admin" && (
                <button
                  type="button"
                  disabled={busyAction === `user:${u.id}`}
                  onClick={() => void handleDeleteUser(u)}
                  className="text-rose-400 hover:text-rose-300 disabled:opacity-40"
                >
                  Remove
                </button>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
