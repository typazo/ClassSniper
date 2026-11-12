import React, { useState } from "react";
import { Crosshair, KeyRound, ShieldCheck, UserPlus } from "lucide-react";
import { api } from "../api/client";
import type { User } from "../types";

interface Props {
  needsBootstrap: boolean;
  initialInviteCode: string;
  appDomain: string;
  onAuthenticated: (user: User) => void;
}

export function AuthScreen({ needsBootstrap, initialInviteCode, appDomain, onAuthenticated }: Props) {
  const [mode, setMode] = useState<"login" | "invite">(initialInviteCode ? "invite" : "login");
  const isSignUp = needsBootstrap || mode === "invite";
  const formMode = needsBootstrap ? "bootstrap" : mode;
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [inviteCode, setInviteCode] = useState(initialInviteCode);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      if (needsBootstrap) {
        const res = await api.bootstrapAdmin(username, password);
        onAuthenticated(res.user);
      } else if (mode === "invite") {
        const res = await api.registerWithInvite(inviteCode, username, password);
        onAuthenticated(res.user);
      } else {
        const res = await api.login(username, password);
        onAuthenticated(res.user);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Authentication failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-950 px-4 py-12">
      <div className="w-full max-w-md rounded-2xl border border-zinc-800 bg-zinc-900/90 p-6 shadow-2xl">
        <div className="mb-6 flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-emerald-500/15 ring-1 ring-emerald-500/30">
            <Crosshair className="h-6 w-6 text-emerald-400" />
          </div>
          <div>
            <h1 className="text-xl font-bold tracking-tight text-white">ClassSniper</h1>
            <p className="text-xs text-zinc-400">{appDomain} &middot; Invite-Only Cornell Course Alerts</p>
          </div>
        </div>

        {needsBootstrap ? (
          <div className="mb-5 rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-3.5 text-sm text-emerald-200">
            <div className="flex items-center gap-2 font-semibold">
              <ShieldCheck className="h-4 w-4 text-emerald-400" />
              First-Run Admin Setup
            </div>
            <p className="mt-1 text-xs text-emerald-200/80">
              Create your admin account to initialize this server. You can generate invite links for friends afterward.
            </p>
          </div>
        ) : (
          <div className="mb-5 grid grid-cols-2 gap-1 rounded-xl bg-zinc-950 p-1">
            <button
              type="button"
              onClick={() => setMode("login")}
              className={`flex items-center justify-center gap-1.5 rounded-lg py-2 text-sm font-medium transition ${
                mode === "login" ? "bg-zinc-800 text-white" : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              <KeyRound className="h-4 w-4" />
              Sign In
            </button>
            <button
              type="button"
              onClick={() => setMode("invite")}
              className={`flex items-center justify-center gap-1.5 rounded-lg py-2 text-sm font-medium transition ${
                mode === "invite" ? "bg-zinc-800 text-white" : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              <UserPlus className="h-4 w-4" />
              Use Invite
            </button>
          </div>
        )}

        <form key={formMode} onSubmit={handleSubmit} autoComplete={isSignUp ? "off" : "on"} className="space-y-4">
          {!needsBootstrap && mode === "invite" && (
            <div>
              <label htmlFor="auth-invite-code" className="mb-1.5 block text-xs font-medium text-zinc-300">
                Invite Code
              </label>
              <input
                id="auth-invite-code"
                name="invite_code"
                type="text"
                required
                autoComplete="off"
                value={inviteCode}
                onChange={(e) => setInviteCode(e.target.value)}
                placeholder="Paste invite code"
                className="w-full rounded-xl border border-zinc-700 bg-zinc-950 px-3.5 py-2.5 text-sm text-white placeholder-zinc-500 focus:border-emerald-500 focus:outline-none"
              />
            </div>
          )}

          <div>
            <label htmlFor="auth-username" className="mb-1.5 block text-xs font-medium text-zinc-300">
              Username
            </label>
            <input
              id="auth-username"
              name={isSignUp ? "signup_username" : "username"}
              type="text"
              required
              autoComplete={isSignUp ? "off" : "username"}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="netid or handle"
              className="w-full rounded-xl border border-zinc-700 bg-zinc-950 px-3.5 py-2.5 text-sm text-white placeholder-zinc-500 focus:border-emerald-500 focus:outline-none"
            />
          </div>

          <div>
            <label htmlFor="auth-password" className="mb-1.5 block text-xs font-medium text-zinc-300">
              Password
            </label>
            <input
              id="auth-password"
              name={isSignUp ? "signup_password" : "password"}
              type="password"
              required
              minLength={8}
              autoComplete={isSignUp ? "off" : "current-password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="At least 8 characters"
              className="w-full rounded-xl border border-zinc-700 bg-zinc-950 px-3.5 py-2.5 text-sm text-white placeholder-zinc-500 focus:border-emerald-500 focus:outline-none"
            />
          </div>

          {error && (
            <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-3.5 py-2.5 text-xs text-rose-300">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-xl bg-emerald-500 px-4 py-2.5 text-sm font-semibold text-zinc-950 transition hover:bg-emerald-400 disabled:opacity-50"
          >
            {loading
              ? "Working..."
              : needsBootstrap
                ? "Create Admin Account"
                : mode === "invite"
                  ? "Create Account with Invite"
                  : "Sign In"}
          </button>
        </form>
      </div>
    </div>
  );
}
