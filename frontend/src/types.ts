export type MajorMode = "none" | "cs" | "ilr";
export type IlrMatchMode = "any" | "all";

export interface User {
  id: number;
  username: string;
  role: "admin" | "user";
  priority_tier: number;
  discord_user_id: string;
  discord_ping_enabled: boolean;
  web_push_enabled: boolean;
  has_personal_webhook: boolean;
  completed_courses: string[];
  completed_course_details?: Record<string, CourseDetailMeta>;
  in_progress_courses?: string[];
  in_progress_course_details?: Record<string, CourseDetailMeta>;
  include_implied_prereqs: boolean;
  major_mode: MajorMode;
  show_cs_features: boolean;
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
  location?: string;
  location_descr?: string;
  instruction_mode: string;
  updated_at?: string | null;
}

export interface ExternalCourseLinks {
  roster: string;
  cu_reviews: string;
  coursicle: string;
  rmp_search: string;
}

export type CSRequirementMode =
  | ""
  | "cs_elective"
  | "cs_project"
  | "tech_elective"
  | "external_spec";
export type CSCurriculumMode = "current" | "pre2024";
export type AttrMatchMode = "any" | "all";

export interface CourseCSBadge {
  kind: string;
  tone: "emerald" | "sky" | "indigo" | "amber" | string;
  label: string;
}

export interface CourseCSEligibility {
  cs_elective: boolean;
  cs_elective_pre2024: boolean;
  cs_elective_warning: string;
  cs_project?: boolean;
  tech_elective: boolean;
  tech_elective_is_2000: boolean;
  tech_elective_is_research: boolean;
  tech_elective_reason: string;
  tech_elective_warning: string;
  external_spec: boolean;
  external_spec_warning: string;
  badges: CourseCSBadge[];
  prereq_status?: "none" | "met" | "unmet" | "prose";
  prereqs_met?: boolean;
  satisfied_by?: string[];
  missing_prereqs?: string;
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
  external_links?: ExternalCourseLinks;
  acad_career?: string;
  acad_group?: string;
  catalog_prereq?: string;
  catalog_coreq?: string;
  catalog_forbidden_overlaps?: string;
  catalog_num?: number;
  units_min?: number;
  units_max?: number;
  has_letter_grade?: boolean;
  crosslists?: string[];
  components?: string[];
  crse_attrs?: string[];
  cs_eligibility?: CourseCSEligibility;
  ilr_eligibility?: CourseIlrEligibility | null;
  hidden_other_location_count?: number;
  hidden_other_locations?: string[];
  subject_synced_at?: string | null;
  status_is_stale?: boolean;
}

export interface CourseIlrBadge {
  code: string;
  label: string;
  short_label: string;
  group: "main_elective" | "distribution" | "core" | "credit_pool";
  rule_summary: string;
  tone: string;
  is_main_elective: boolean;
}

export interface CourseIlrEligibility {
  qualifies_any: boolean;
  codes: string[];
  main_electives: string[];
  distributions: string[];
  credit_pools: string[];
  is_main_elective: boolean;
  is_ilr_core: boolean;
  requirement_count: number;
  also_fits_codes: string[];
  badges: CourseIlrBadge[];
  warnings: string[];
  ug_crosslist_hints: string[];
}

export interface IlrBucketCounts {
  total: number;
  open: number;
  waitlist: number;
  closed: number;
  stale: number;
}

export interface IlrRequirementSummary extends CourseIlrBadge, IlrBucketCounts {
  requires_three_credits: boolean;
}

export interface IlrSummaryResponse {
  roster: string;
  ithaca_or_virtual: boolean;
  requirements: IlrRequirementSummary[];
  presets: {
    all_il: IlrBucketCounts;
    main_three: IlrBucketCounts;
    ilr_core: IlrBucketCounts;
    multi_req: IlrBucketCounts;
  };
  curriculum_url: string;
  filtered_out_location_count: number;
  queued_subjects: string[];
  coverage: {
    synced_subjects: number;
    total_subjects: number;
    ilr_synced: number;
    ilr_total: number;
    refreshing_subjects: string[];
    warmup_active: boolean;
  };
}

export interface SearchCoursesMeta {
  total_matched: number;
  returned: number;
  filtered_out_location_count?: number;
  filtered_out_locations?: string[];
  queued_subjects: string[];
  synced_subjects: number;
  total_subjects: number;
  stem_synced: number;
  stem_total: number;
  refreshing_subjects: string[];
  warmup_active: boolean;
  implied_courses?: string[];
}

export interface PrereqCourseOption {
  code: string;
  subject: string;
  catalog_nbr: string;
  title: string;
  cr?: string;
  crosslists: string[];
}

export interface UserPrereqsResponse {
  completed_courses: string[];
  completed_course_details?: Record<string, CourseDetailMeta>;
  in_progress_courses?: string[];
  in_progress_course_details?: Record<string, CourseDetailMeta>;
  include_implied_prereqs: boolean;
  implied_courses: string[];
}

export interface CatalogStatus {
  roster: string;
  synced_subjects: number;
  total_subjects: number;
  stem_synced: number;
  stem_total: number;
  warmup_active: boolean;
  refreshing_subjects: string[];
}

export interface CatalogSubjectRefreshedSSE {
  roster: string;
  subject: string;
  synced_at: string;
  courses_count: number;
  section_statuses: Record<string, string>;
  historical_lookup?: boolean;
  resolved_courses?: string[];
  coverage?: {
    synced_subjects: number;
    total_subjects: number;
    stem_synced: number;
    stem_total: number;
  };
}

export interface CuReviewTag {
  category: string;
  label: string;
  sentiment: string;
}

export interface CuReviewItem {
  id: string;
  text: string;
  rating: number | null;
  difficulty: number | null;
  workload: number | null;
  grade: string;
  professors: string[];
  likes: number;
  date: string;
}

export interface CuReviewsData {
  found: boolean;
  status: string;
  error?: string;
  cached?: boolean;
  course_url: string;
  rating: number | null;
  difficulty: number | null;
  workload: number | null;
  summary: string;
  summary_tags: CuReviewTag[];
  semesters_offered: string[];
  review_count: number;
  reviews: CuReviewItem[];
}

export interface RmpInstructorItem {
  name: string;
  matched_name?: string;
  found: boolean;
  status: string;
  cached?: boolean;
  legacy_id: number | null;
  rmp_url: string;
  search_url: string;
  department: string;
  avg_rating: number | null;
  avg_difficulty: number | null;
  would_take_again_percent: number | null;
  num_ratings: number;
}

export interface CourseInsights {
  roster: string;
  subject: string;
  catalog_nbr: string;
  links: ExternalCourseLinks;
  cu_reviews: CuReviewsData;
  rmp: {
    instructors: RmpInstructorItem[];
    search_url: string;
  };
}

export interface WatchSectionInfo {
  ssr_component: string;
  section: string;
  open_status: string;
  meetings_summary: string;
  instructors_summary: string;
  campus?: string;
  location?: string;
  location_descr?: string;
  instruction_mode?: string;
  updated_at: string | null;
}

export interface WatchOpenSection {
  class_nbr: number;
  ssr_component: string;
  section: string;
  open_status: string;
  meetings_summary: string;
  instructors_summary: string;
  is_target?: boolean;
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
  ithaca_or_virtual?: boolean;
  cooldown_sec: number;
  last_observed_status: string | null;
  last_notified_status: string | null;
  last_notified_at: string | null;
  created_at: string;
  group_key?: string;
  section_info: WatchSectionInfo | null;
  open_sections?: WatchOpenSection[];
  turnover_summary?: {
    h24: number;
    d7: number;
    d30: number;
    all: number;
    opened_24h: number;
    opened_7d: number;
    avg_open_sec_7d: number | null;
    last_opened_at: string | null;
  };
}

export type WatchHistoryWindow = "24h" | "7d" | "30d" | "all";

export interface WatchTurnoverWindowStats {
  total_flips: number;
  opened_count: number;
  waitlisted_count: number;
  closed_count: number;
  avg_open_sec: number | null;
  median_open_sec: number | null;
  last_opened_at: string | null;
}

export interface WatchStatusEventItem {
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

export interface WatchHistoryResponse {
  watch_id: number;
  window: WatchHistoryWindow;
  windows: Record<WatchHistoryWindow, WatchTurnoverWindowStats>;
  events: WatchStatusEventItem[];
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

export type DayCode = "M" | "T" | "W" | "R" | "F" | "Sa" | "Su";

export interface SectionMeeting {
  pattern: string;
  days: DayCode[];
  time_start: string;
  time_end: string;
  start_min: number;
  end_min: number;
  start_dt: string;
  end_dt: string;
  facility_descr: string;
  building_descr: string;
  instructors: string[];
}

export interface ScheduleSection {
  class_nbr: number;
  enroll_group_idx: number;
  ssr_component: string;
  section: string;
  open_status: "O" | "C" | "W" | string;
  components_required: string[];
  meetings_summary: string;
  instructors_summary: string;
  instructors: string[];
  campus: string;
  location: string;
  location_descr: string;
  instruction_mode: string;
  is_ithaca_or_virtual: boolean;
  topic_description: string;
  updated_at: string | null;
  meetings: SectionMeeting[];
}

export interface ScheduleEnrollGroup {
  enroll_group_idx: number;
  components_required: string[];
  units_min: number;
  units_max: number;
  grading_basis: string;
  session_code: string;
  crosslists: string[];
  sections: ScheduleSection[];
}

export interface CachedCourseInsightsSummary {
  rating: number | null;
  difficulty: number | null;
  workload: number | null;
  review_count: number;
}

export interface CachedRmpSummary {
  avg_rating: number | null;
  avg_difficulty: number | null;
  num_ratings: number;
  rmp_url: string;
}

export interface ScheduleCourseItem {
  id: number;
  subject: string;
  catalog_nbr: string;
  enabled: boolean;
  selected_units: number | null;
  selected_class_nbrs: number[];
  locked_class_nbrs: number[];
  color_idx: number;
  sort_order: number;
  title_short: string;
  title_long: string;
  description: string;
  acad_career: string;
  acad_group: string;
  catalog_prereq: string;
  catalog_coreq: string;
  catalog_forbidden_overlaps: string;
  units_min: number;
  units_max: number;
  has_letter_grade: boolean;
  crosslists: string[];
  components: string[];
  enroll_groups: ScheduleEnrollGroup[];
  external_links: ExternalCourseLinks;
  cs_eligibility: CourseCSEligibility | null;
  ilr_eligibility: CourseIlrEligibility | null;
  cached_insights: CachedCourseInsightsSummary | null;
  cached_rmp: Record<string, CachedRmpSummary>;
  subject_synced_at: string | null;
  status_is_stale: boolean;
}

export interface ScheduleBlock {
  id: number;
  label: string;
  days: DayCode[];
  start_min: number;
  end_min: number;
  enabled: boolean;
}

export interface ScheduleSummary {
  id: number;
  roster: string;
  name: string;
  is_active: boolean;
  is_transcript?: boolean;
  share_enabled: boolean;
  share_token: string | null;
  share_url: string | null;
  course_count?: number;
  created_at: string;
  updated_at: string;
}

export interface HydratedSchedule {
  schedule: ScheduleSummary;
  courses: ScheduleCourseItem[];
  blocks: ScheduleBlock[];
  owner_username?: string;
}

export interface SchedulesListResponse {
  roster: string;
  schedules: ScheduleSummary[];
  active: HydratedSchedule;
  insights_fetched_count?: number;
}

export interface AttributeOption {
  code: string;
  label: string;
  group: "as_dist" | "college" | "eng_cals" | "exploratory" | "other" | string;
  count: number;
}

export interface CourseSearchPreset {
  id: number;
  label?: string;
  q?: string;
  subjects?: string[];
  level_min?: number | "";
  min_credits?: number | "";
  cs_requirement?: CSRequirementMode;
  attrs?: string[];
  attr_match?: AttrMatchMode;
  curriculum?: CSCurriculumMode;
}

export interface CsChecklistSearchHint {
  q?: string;
  subjects?: string[];
  min_credits?: number;
  cs_requirement?: CSRequirementMode;
  attrs?: string[];
  attr_match?: AttrMatchMode;
}

export interface CsChecklistSlotInput {
  course: string;
  title: string;
  cr: string;
  sem: string;
  gr: string;
  notes: string;
  pinned?: boolean;
  cleared?: boolean;
}

export interface CsChecklistQuickOption {
  code: string;
  title?: string;
  cr?: string;
}

export interface CsChecklistSlot {
  id: string;
  label: string;
  expected: string;
  filled: boolean;
  course: string;
  title: string;
  cr: string;
  sem: string;
  gr: string;
  notes: string;
  attrs: string[];
  attr_code?: string;
  warning?: string;
  source: "completed" | "in_progress" | "schedule" | "manual" | "empty" | "waived";
  waived?: boolean;
  waived_by?: string;
  search: CsChecklistSearchHint;
  quick_options?: CsChecklistQuickOption[];
}

export interface CsChecklistSection {
  id: string;
  title: string;
  subtitle: string;
  slots: CsChecklistSlot[];
}

export interface CourseDetailMeta {
  gr?: string;
  sem?: string;
  cr?: string;
}

export interface CsChecklistPayload {
  roster: string;
  college: "arts" | "engineering";
  curriculum: CSCurriculumMode;
  include_active_schedule: boolean;
  active_schedule_name: string;
  pe_completed: number;
  completed_courses: string[];
  completed_course_details?: Record<string, CourseDetailMeta>;
  in_progress_courses: string[];
  in_progress_course_details?: Record<string, CourseDetailMeta>;
  planned_courses: string[];
  missing_metadata_courses?: string[];
  as_distribution_summary: {
    covered_categories: number;
    total_categories: number;
    unique_courses: number;
    min_unique_courses: number;
  } | null;
  summary: {
    total_slots: number;
    filled_slots: number;
    completed_slots: number;
    in_progress_slots: number;
    whatif_slots: number;
    remaining_slots: number;
  };
  sections: CsChecklistSection[];
  manual_slots?: Record<string, CsChecklistSlotInput>;
}

export interface ImportTranscriptRequest {
  roster?: string;
  completed_courses: Array<{
    course: string;
    sem?: string;
    gr?: string;
    cr?: string;
  }>;
  in_progress_courses: Array<{
    course: string;
    roster: string;
    cr?: string;
  }>;
  past_schedule_courses?: Array<{
    course: string;
    roster: string;
    cr?: string;
  }>;
  sync_in_progress_to_checklist?: boolean;
  sync_completed_to_scheduler?: boolean;
  pe_completed?: number;
}

export interface SchedulerImportResult {
  roster: string;
  schedule_id: number;
  schedule_name: string;
  added: string[];
  updated: string[];
  already_present: string[];
  skipped: Array<{ course: string; reason: string }>;
}

export interface ImportTranscriptResponse {
  checklist: CsChecklistPayload;
  import_summary: {
    added_completed: string[];
    added_in_progress?: string[];
    enriched_completed: string[];
    unchanged_completed: string[];
    enriched_slots: string[];
    pe_completed: number;
    scheduler: SchedulerImportResult[];
  };
}
