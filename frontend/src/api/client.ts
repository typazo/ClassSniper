import type {
  AdminSettings,
  AdminUserItem,
  AuthStatus,
  CourseSummary,
  InviteItem,
  MetricsResponse,
  NotifyPreferences,
  Roster,
  Subject,
  User,
  Watch,
} from "../types";

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(path, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    ...init,
  });

  let payload: unknown = null;
  const text = await resp.text();
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = text;
    }
  }

  if (!resp.ok) {
    const detail =
      typeof payload === "object" && payload !== null && "detail" in payload
        ? String((payload as { detail: unknown }).detail)
        : `Request failed (HTTP ${resp.status})`;
    throw new ApiError(resp.status, detail);
  }

  return payload as T;
}

export const api = {
  authStatus: () => request<AuthStatus>("/api/auth/status"),
  bootstrapAdmin: (username: string, password: string) =>
    request<{ user: User }>("/api/auth/bootstrap", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  login: (username: string, password: string) =>
    request<{ user: User }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  registerWithInvite: (invite_code: string, username: string, password: string) =>
    request<{ user: User }>("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({ invite_code, username, password }),
    }),
  logout: () => request<{ status: string }>("/api/auth/logout", { method: "POST" }),

  listRosters: () => request<{ rosters: Roster[] }>("/api/rosters"),
  listSubjects: (roster: string) =>
    request<{ roster: string; subjects: Subject[] }>(`/api/subjects?roster=${encodeURIComponent(roster)}`),
  searchCourses: (roster: string, q: string, subject = "") => {
    const params = new URLSearchParams({ roster, q });
    if (subject) params.set("subject", subject);
    return request<{ roster: string; courses: CourseSummary[] }>(`/api/courses/search?${params.toString()}`);
  },
  syncCatalog: (roster?: string, subject?: string) =>
    request<{ status: string }>("/api/catalog/sync", {
      method: "POST",
      body: JSON.stringify({ roster, subject }),
    }),

  listWatches: () => request<{ watches: Watch[] }>("/api/watches"),
  createWatch: (payload: {
    roster: string;
    subject: string;
    catalog_nbr: string;
    class_nbr?: number | null;
    enroll_group_idx?: number | null;
    component_filter?: string | null;
    mode: "exact" | "linked_group" | "any_section";
    trigger_on: "open" | "open_or_waitlist";
    priority: number;
    auto_pause: boolean;
    cooldown_sec: number;
  }) =>
    request<{ watch: Watch }>("/api/watches", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateWatch: (
    id: number,
    patch: Partial<{ active: boolean; auto_pause: boolean; trigger_on: "open" | "open_or_waitlist"; priority: number; cooldown_sec: number }>
  ) =>
    request<{ watch: Watch }>(`/api/watches/${id}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
  rearmWatch: (id: number) => request<{ watch: Watch }>(`/api/watches/${id}/rearm`, { method: "POST" }),
  checkWatchNow: (id: number) =>
    request<{ ok: boolean; rtt_ms: number; alerts_count: number }>(`/api/watches/${id}/check-now`, {
      method: "POST",
    }),
  deleteWatch: (id: number) => request<{ status: string }>(`/api/watches/${id}`, { method: "DELETE" }),

  getVapidKey: () => request<{ public_key: string }>("/api/push/vapid-key"),
  subscribePush: (sub: PushSubscriptionJSON, device_label: string) =>
    request<{ subscription: { id: number; device_label: string } }>("/api/push/subscribe", {
      method: "POST",
      body: JSON.stringify({
        endpoint: sub.endpoint,
        keys: sub.keys,
        device_label,
      }),
    }),
  unsubscribePush: (id: number) =>
    request<{ status: string }>("/api/push/subscribe", {
      method: "DELETE",
      body: JSON.stringify({ id }),
    }),
  getNotifyPreferences: () => request<NotifyPreferences>("/api/notify/preferences"),
  updateNotifyPreferences: (patch: {
    discord_user_id?: string;
    discord_ping_enabled?: boolean;
    web_push_enabled?: boolean;
    personal_webhook_url?: string;
  }) =>
    request<{ status: string }>("/api/notify/preferences", {
      method: "PUT",
      body: JSON.stringify(patch),
    }),
  sendTestNotify: (target: "all" | "web_push" | "discord") =>
    request<{ results: Array<{ channel: string; status: string; latency_ms?: number; detail: string }> }>(
      "/api/notify/test",
      {
        method: "POST",
        body: JSON.stringify({ target }),
      }
    ),

  getMetrics: () => request<MetricsResponse>("/api/metrics"),
  listInvites: () => request<{ invites: InviteItem[] }>("/api/admin/invites"),
  createInvite: (payload: { max_uses: number; expires_hours: number | null; note: string }) =>
    request<{ invite: InviteItem; invite_url: string }>("/api/admin/invites", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  deleteInvite: (code: string) => request<{ status: string }>(`/api/admin/invites/${encodeURIComponent(code)}`, { method: "DELETE" }),
  listUsers: () => request<{ users: AdminUserItem[] }>("/api/admin/users"),
  deleteUser: (id: number) => request<{ status: string }>(`/api/admin/users/${id}`, { method: "DELETE" }),
  getAdminSettings: () => request<AdminSettings>("/api/admin/settings"),
  updateAdminSettings: (patch: { discord_shared_webhook_url?: string; poll_max_rps?: number }) =>
    request<{ status: string }>("/api/admin/settings", {
      method: "PUT",
      body: JSON.stringify(patch),
    }),
};
