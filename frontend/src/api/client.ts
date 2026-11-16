import type {
  AdminSettings,
  AdminUserItem,
  AttributeOption,
  AttrMatchMode,
  AuthStatus,
  CatalogStatus,
  CourseInsights,
  CourseSummary,
  CSCurriculumMode,
  CsChecklistPayload,
  CsChecklistSlotInput,
  CSRequirementMode,
  DayCode,
  HydratedSchedule,
  IlrMatchMode,
  IlrSummaryResponse,
  ImportTranscriptRequest,
  ImportTranscriptResponse,
  InviteItem,
  MajorMode,
  MetricsResponse,
  MinorCatalogItem,
  MinorPrefs,
  NotifyPreferences,
  PrereqCourseOption,
  Roster,
  SchedulesListResponse,
  SearchCoursesMeta,
  Subject,
  User,
  UserPrereqsResponse,
  Watch,
  WatchHistoryResponse,
  WatchHistoryWindow,
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
  updateUserPreferences: (patch: {
    major_mode?: MajorMode;
    show_cs_features?: boolean;
    minor_prefs?: MinorPrefs;
  }) =>
    request<{ user: User }>("/api/auth/preferences", {
      method: "PUT",
      body: JSON.stringify(patch),
    }),

  listRosters: () => request<{ rosters: Roster[] }>("/api/rosters"),
  listSubjects: (roster: string) =>
    request<{ roster: string; subjects: Subject[] }>(`/api/subjects?roster=${encodeURIComponent(roster)}`),
  searchCourses: (
    roster: string,
    q: string,
    options?: {
      subject?: string;
      subjects?: string[];
      level_min?: number | null;
      min_credits?: number | null;
      cs_requirement?: CSRequirementMode;
      include_2000_te?: boolean;
      include_research_te?: boolean;
      curriculum?: CSCurriculumMode;
      ilr_codes?: string[];
      ilr_match?: IlrMatchMode;
      ilr_multi_only?: boolean;
      include_ilr?: boolean;
      attrs?: string[];
      attr_match?: AttrMatchMode;
      minor?: string;
      minor_version?: string;
      minor_categories?: string[];
      minor_completed?: string[];
      minor_hide_completed?: boolean;
      only_eligible?: boolean;
      include_implied_prereqs?: boolean;
      ithaca_or_virtual?: boolean;
      refresh_stale?: boolean;
      limit?: number;
    }
  ) => {
    const params = new URLSearchParams({ roster, q });
    if (options?.subject) params.set("subject", options.subject);
    if (options?.subjects && options.subjects.length > 0) {
      params.set("subjects", options.subjects.join(","));
    }
    if (options?.level_min) params.set("level_min", String(options.level_min));
    if (options?.min_credits) params.set("min_credits", String(options.min_credits));
    if (options?.cs_requirement) params.set("cs_requirement", options.cs_requirement);
    if (options?.include_2000_te !== undefined) {
      params.set("include_2000_te", String(options.include_2000_te));
    }
    if (options?.include_research_te !== undefined) {
      params.set("include_research_te", String(options.include_research_te));
    }
    if (options?.curriculum) params.set("curriculum", options.curriculum);
    if (options?.ilr_codes && options.ilr_codes.length > 0) {
      params.set("ilr_codes", options.ilr_codes.join(","));
    }
    if (options?.ilr_match) params.set("ilr_match", options.ilr_match);
    if (options?.ilr_multi_only !== undefined) {
      params.set("ilr_multi_only", String(options.ilr_multi_only));
    }
    if (options?.include_ilr !== undefined) {
      params.set("include_ilr", String(options.include_ilr));
    }
    if (options?.attrs && options.attrs.length > 0) {
      params.set("attrs", options.attrs.join(","));
    }
    if (options?.attr_match) params.set("attr_match", options.attr_match);
    if (options?.minor) params.set("minor", options.minor);
    if (options?.minor_version) params.set("minor_version", options.minor_version);
    if (options?.minor_categories && options.minor_categories.length > 0) {
      params.set("minor_categories", options.minor_categories.join(","));
    }
    if (options?.minor_completed !== undefined) {
      params.set("minor_completed", options.minor_completed.join(","));
    }
    if (options?.minor_hide_completed !== undefined) {
      params.set("minor_hide_completed", String(options.minor_hide_completed));
    }
    if (options?.only_eligible !== undefined) {
      params.set("only_eligible", String(options.only_eligible));
    }
    if (options?.include_implied_prereqs !== undefined) {
      params.set("include_implied_prereqs", String(options.include_implied_prereqs));
    }
    if (options?.ithaca_or_virtual !== undefined) {
      params.set("ithaca_or_virtual", String(options.ithaca_or_virtual));
    }
    if (options?.refresh_stale !== undefined) {
      params.set("refresh_stale", String(options.refresh_stale));
    }
    if (options?.limit) params.set("limit", String(options.limit));
    return request<{ roster: string; courses: CourseSummary[]; meta?: SearchCoursesMeta }>(
      `/api/courses/search?${params.toString()}`
    );
  },
  getCourseAttributes: (roster: string) =>
    request<{ roster: string; attributes: AttributeOption[] }>(
      `/api/courses/attributes?roster=${encodeURIComponent(roster)}`
    ),
  getMinorsCatalog: (roster?: string) =>
    request<{ roster: string; minors: MinorCatalogItem[] }>(
      `/api/minors/catalog${roster ? `?roster=${encodeURIComponent(roster)}` : ""}`
    ),
  getCsChecklist: (roster?: string) =>
    request<CsChecklistPayload>(
      `/api/cs/checklist${roster ? `?roster=${encodeURIComponent(roster)}` : ""}`
    ),
  updateCsChecklist: (
    payload: {
      college: "arts" | "engineering";
      curriculum: CSCurriculumMode;
      include_active_schedule: boolean;
      pe_completed: number;
      slots: Record<string, CsChecklistSlotInput>;
      sync_completed_courses?: string[];
      sync_in_progress_courses?: string[];
    },
    roster?: string
  ) =>
    request<CsChecklistPayload>(
      `/api/cs/checklist${roster ? `?roster=${encodeURIComponent(roster)}` : ""}`,
      {
        method: "PUT",
        body: JSON.stringify(payload),
      }
    ),
  importTranscript: (payload: ImportTranscriptRequest) =>
    request<ImportTranscriptResponse>("/api/cs/checklist/import-transcript", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  getCatalogStatus: (roster: string) =>
    request<CatalogStatus>(`/api/catalog/status?roster=${encodeURIComponent(roster)}`),
  getIlrSummary: (roster: string, ithacaOrVirtual = true, syncPriority = false) => {
    const params = new URLSearchParams({
      roster,
      ithaca_or_virtual: String(ithacaOrVirtual),
      sync_priority: String(syncPriority),
    });
    return request<IlrSummaryResponse>(`/api/ilr/summary?${params.toString()}`);
  },
  getCourseInsights: (roster: string, subject: string, catalogNbr: string, refresh = false) =>
    request<CourseInsights>(
      `/api/courses/${encodeURIComponent(roster)}/${encodeURIComponent(subject)}/${encodeURIComponent(catalogNbr)}/insights${
        refresh ? "?refresh=true" : ""
      }`
    ),
  syncCatalog: (roster?: string, subject?: string) =>
    request<{ status: string }>("/api/catalog/sync", {
      method: "POST",
      body: JSON.stringify({ roster, subject }),
    }),
  getUserPrereqs: (roster?: string) =>
    request<UserPrereqsResponse>(
      `/api/user/prereqs${roster ? `?roster=${encodeURIComponent(roster)}` : ""}`
    ),
  updateUserPrereqs: (
    payload: { completed_courses: string[]; include_implied_prereqs?: boolean },
    roster?: string
  ) =>
    request<UserPrereqsResponse>(
      `/api/user/prereqs${roster ? `?roster=${encodeURIComponent(roster)}` : ""}`,
      {
        method: "PUT",
        body: JSON.stringify(payload),
      }
    ),
  getPrereqOptions: (roster: string, q = "", limit = 30, mode?: MajorMode | "general") => {
    const params = new URLSearchParams({ roster, q, limit: String(limit) });
    if (mode) params.set("mode", mode === "none" ? "general" : mode);
    return request<{ roster: string; options: PrereqCourseOption[] }>(
      `/api/user/prereqs/options?${params.toString()}`
    );
  },

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
    ithaca_or_virtual?: boolean;
    cooldown_sec: number;
    group_key?: string;
  }) =>
    request<{ watch: Watch }>("/api/watches", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateWatch: (
    id: number,
    patch: Partial<{
      active: boolean;
      auto_pause: boolean;
      trigger_on: "open" | "open_or_waitlist";
      priority: number;
      cooldown_sec: number;
      group_key: string;
    }>
  ) =>
    request<{ watch: Watch }>(`/api/watches/${id}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
  batchUpdateWatchGroup: (watchIds: number[], groupKey: string) =>
    request<{ watches: Watch[]; group_key: string }>("/api/watches/group", {
      method: "POST",
      body: JSON.stringify({ watch_ids: watchIds, group_key: groupKey }),
    }),
  getWatchHistory: (watchId: number, window: WatchHistoryWindow = "7d", limit = 60) =>
    request<WatchHistoryResponse>(
      `/api/watches/${watchId}/history?window=${encodeURIComponent(window)}&limit=${limit}`
    ),
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

  listSchedules: (roster?: string) =>
    request<SchedulesListResponse>(
      `/api/schedules${roster ? `?roster=${encodeURIComponent(roster)}` : ""}`
    ),
  createSchedule: (payload: { roster: string; name: string; duplicate_from_id?: number }) =>
    request<SchedulesListResponse>("/api/schedules", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  quickAddScheduleCourse: (payload: {
    roster: string;
    subject: string;
    catalog_nbr: string;
    selected_class_nbrs?: number[];
  }) =>
    request<{ already_present: boolean; schedule_name: string; active: HydratedSchedule }>(
      "/api/schedules/quick-add",
      {
        method: "POST",
        body: JSON.stringify(payload),
      }
    ),
  getSchedule: (scheduleId: number) => request<HydratedSchedule>(`/api/schedules/${scheduleId}`),
  updateSchedule: (
    scheduleId: number,
    patch: {
      name?: string;
      is_active?: boolean;
      share_enabled?: boolean;
      regenerate_share_token?: boolean;
    }
  ) =>
    request<SchedulesListResponse>(`/api/schedules/${scheduleId}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
  deleteSchedule: (scheduleId: number, roster?: string) =>
    request<SchedulesListResponse>(
      `/api/schedules/${scheduleId}${roster ? `?roster=${encodeURIComponent(roster)}` : ""}`,
      { method: "DELETE" }
    ),
  addScheduleCourse: (
    scheduleId: number,
    payload: {
      subject: string;
      catalog_nbr: string;
      enabled?: boolean;
      selected_units?: number | null;
      selected_class_nbrs?: number[];
    }
  ) =>
    request<HydratedSchedule>(`/api/schedules/${scheduleId}/courses`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateScheduleCourse: (
    scheduleId: number,
    itemId: number,
    patch: {
      enabled?: boolean;
      selected_units?: number | null;
      selected_class_nbrs?: number[];
      locked_class_nbrs?: number[];
      color_idx?: number;
    }
  ) =>
    request<HydratedSchedule>(`/api/schedules/${scheduleId}/courses/${itemId}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
  applyGeneratedSchedule: (
    scheduleId: number,
    items: Array<{ item_id: number; selected_class_nbrs: number[] }>
  ) =>
    request<HydratedSchedule>(`/api/schedules/${scheduleId}/apply-generated`, {
      method: "PUT",
      body: JSON.stringify({ items }),
    }),
  removeScheduleCourse: (scheduleId: number, itemId: number) =>
    request<HydratedSchedule>(`/api/schedules/${scheduleId}/courses/${itemId}`, {
      method: "DELETE",
    }),
  createScheduleBlock: (
    scheduleId: number,
    payload: { label: string; days: DayCode[]; start_min: number; end_min: number; enabled?: boolean }
  ) =>
    request<HydratedSchedule>(`/api/schedules/${scheduleId}/blocks`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateScheduleBlock: (
    scheduleId: number,
    blockId: number,
    patch: { label?: string; days?: DayCode[]; start_min?: number; end_min?: number; enabled?: boolean }
  ) =>
    request<HydratedSchedule>(`/api/schedules/${scheduleId}/blocks/${blockId}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
  deleteScheduleBlock: (scheduleId: number, blockId: number) =>
    request<HydratedSchedule>(`/api/schedules/${scheduleId}/blocks/${blockId}`, {
      method: "DELETE",
    }),
  batchLoadScheduleInsights: (scheduleId: number, force = false) =>
    request<HydratedSchedule & { insights_fetched_count?: number }>(
      `/api/schedules/${scheduleId}/insights${force ? "?force=true" : ""}`,
      { method: "POST" }
    ),
  getSharedSchedule: (token: string) =>
    request<HydratedSchedule>(`/api/schedules/shared/${encodeURIComponent(token)}`),
};
