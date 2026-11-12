export interface User {
  id: number;
  username: string;
  role: "admin" | "user";
  priority_tier: number;
  discord_user_id: string;
  discord_ping_enabled: boolean;
  web_push_enabled: boolean;
  has_personal_webhook: boolean;
}

export interface AuthStatus {
  needs_bootstrap: boolean;
  user: User | null;
  app_domain: string;
  app_origin: string;
}

export interface Roster {
  slug: string;
  descr: string;
  is_default: number;
  archive_mode: number;
  strm: string;
}

export interface Subject {
  value: string;
  descr: string;
  synced_at: string | null;
}

export interface CourseSection {
  class_nbr: number;
  enroll_group_idx: number;
  ssr_component: string;
  section: string;
  open_status: "O" | "C" | "W" | string;
  components_required: string[];
  meetings_summary: string;
  instructors_summary: string;
  campus: string;
  instruction_mode: string;
  updated_at?: string | null;
}

export interface CourseSummary {
  roster: string;
  subject: string;
  catalog_nbr: string;
  title_short: string;
  title_long: string;
  description: string;
  updated_at: string;
  sections: CourseSection[];
}

export interface WatchSectionInfo {
  ssr_component: string;
  section: string;
  open_status: string;
  meetings_summary: string;
  instructors_summary: string;
  updated_at: string | null;
}

export interface Watch {
  id: number;
  user_id: number;
  roster: string;
  subject: string;
  catalog_nbr: string;
  course_title: string;
  class_nbr: number | null;
  enroll_group_idx: number | null;
  component_filter: string | null;
  mode: "exact" | "linked_group" | "any_section";
  trigger_on: "open" | "open_or_waitlist";
  priority: number;
  active: boolean;
  auto_pause: boolean;
  cooldown_sec: number;
  last_observed_status: string | null;
  last_notified_status: string | null;
  last_notified_at: string | null;
  created_at: string;
  section_info: WatchSectionInfo | null;
}

export interface PushSubscriptionItem {
  id: number;
  endpoint: string;
  device_label: string;
  created_at: string;
}

export interface DeliveryLogItem {
  id: number;
  channel_kind: string;
  status: string;
  latency_ms: number;
  error_text: string | null;
  sent_at: string;
  roster: string | null;
  subject: string | null;
  catalog_nbr: string | null;
  class_nbr: number | null;
  section_label: string | null;
  new_status: string | null;
}

export interface NotifyPreferences {
  discord_user_id: string;
  discord_ping_enabled: boolean;
  web_push_enabled: boolean;
  personal_webhook_url: string;
  allow_custom_personal_webhooks: boolean;
  shared_discord_configured: boolean;
  push_subscriptions: PushSubscriptionItem[];
  recent_deliveries: DeliveryLogItem[];
}

export interface PollerBucket {
  roster: string;
  subject: string;
  weight: number;
  watch_count: number;
  last_polled_at: string | null;
  last_rtt_ms: number;
}

export interface PollerMetrics {
  state: string;
  total_polls: number;
  error_count: number;
  rate_limit_hits: number;
  alerts_triggered: number;
  last_poll_at: string | null;
  last_poll_subject: string | null;
  last_poll_rtt_ms: number;
  last_error: string | null;
  avg_rtt_ms: number;
  cached_sections_count: number;
  buckets: PollerBucket[];
}

export interface StatusEventItem {
  id: number;
  roster: string;
  subject: string;
  catalog_nbr: string;
  class_nbr: number;
  section_label: string;
  old_status: string | null;
  new_status: string;
  poll_rtt_ms: number;
  detected_at: string;
}

export interface MetricsResponse {
  poller: PollerMetrics;
  catalog: {
    in_progress: boolean;
    last_sync_at: string | null;
    last_error: string | null;
    rosters_count: number;
  };
  recent_events: StatusEventItem[];
}

export interface SeatAlertSSE {
  roster: string;
  subject: string;
  catalog_nbr: string;
  course_title: string;
  class_nbr: number;
  section_label: string;
  old_status: string | null;
  new_status: string;
  poll_rtt_ms: number;
  student_center_url: string;
  roster_url: string;
}

export interface InviteItem {
  code: string;
  max_uses: number;
  uses_count: number;
  note: string;
  expires_at: string | null;
  created_at: string;
  created_by_username: string;
}

export interface AdminUserItem {
  id: number;
  username: string;
  role: string;
  priority_tier: number;
  discord_user_id: string | null;
  created_at: string;
  active_watches: number;
  push_devices: number;
}

export interface AdminSettings {
  app_domain: string;
  app_origin: string;
  discord_shared_webhook_url: string;
  poll_max_rps: number;
  max_subjects_per_invited_user: number;
}
