import type { CourseSection, CourseSummary } from "../types";

export function courseCacheKey(
  c: Pick<CourseSummary, "roster" | "subject" | "catalog_nbr">
): string {
  return `${c.roster}-${c.subject}-${c.catalog_nbr}`;
}

export function summarizeStatuses(
  sections: Array<Pick<CourseSection, "open_status">>
): { open: number; closed: number; waitlist: number } {
  let open = 0;
  let closed = 0;
  let waitlist = 0;
  for (const s of sections) {
    const st = (s.open_status || "").toUpperCase();
    if (st === "O") open += 1;
    else if (st === "W") waitlist += 1;
    else if (st === "C") closed += 1;
  }
  return { open, closed, waitlist };
}

export function formatCredits(min?: number, max?: number): string {
  if (!max && !min) return "";
  if (min != null && max != null && min !== max) {
    return `${Number(min.toFixed(2))}–${Number(max.toFixed(2))} cr`;
  }
  return `${Number((max || min || 0).toFixed(2))} cr`;
}

export type ToneVariant = "badge" | "pill" | "pillActive" | "highlight";

const TONE_CLASSES: Record<string, Record<ToneVariant, string>> = {
  emerald: {
    badge: "border-emerald-500/35 bg-emerald-500/15 text-emerald-300",
    pill: "bg-emerald-500/10 border-emerald-500/30 text-emerald-300",
    pillActive: "bg-emerald-500/25 border-emerald-400 text-emerald-100 ring-1 ring-emerald-400/50",
    highlight: "border-emerald-400/70 bg-emerald-500/25 text-emerald-100",
  },
  sky: {
    badge: "border-sky-500/35 bg-sky-500/15 text-sky-300",
    pill: "bg-sky-500/10 border-sky-500/30 text-sky-300",
    pillActive: "bg-sky-500/25 border-sky-400 text-sky-100 ring-1 ring-sky-400/50",
    highlight: "border-sky-400/70 bg-sky-500/25 text-sky-100",
  },
  indigo: {
    badge: "border-indigo-500/35 bg-indigo-500/15 text-indigo-300",
    pill: "bg-indigo-500/10 border-indigo-500/30 text-indigo-300",
    pillActive: "bg-indigo-500/25 border-indigo-400 text-indigo-100 ring-1 ring-indigo-400/50",
    highlight: "border-indigo-400/70 bg-indigo-500/25 text-indigo-100",
  },
  amber: {
    badge: "border-amber-500/40 bg-amber-500/15 text-amber-200",
    pill: "bg-amber-500/10 border-amber-500/30 text-amber-300",
    pillActive: "bg-amber-500/25 border-amber-400 text-amber-100 ring-1 ring-amber-400/50",
    highlight: "border-amber-400/70 bg-amber-500/25 text-amber-100",
  },
  violet: {
    badge: "border-violet-500/40 bg-violet-500/15 text-violet-200",
    pill: "bg-violet-500/10 border-violet-500/30 text-violet-300",
    pillActive: "bg-violet-500/25 border-violet-400 text-violet-100 ring-1 ring-violet-400/50",
    highlight: "border-violet-400/70 bg-violet-500/25 text-violet-100",
  },
  rose: {
    badge: "border-rose-500/40 bg-rose-500/15 text-rose-200",
    pill: "bg-rose-500/10 border-rose-500/30 text-rose-300",
    pillActive: "bg-rose-500/25 border-rose-400 text-rose-100 ring-1 ring-rose-400/50",
    highlight: "border-rose-400/70 bg-rose-500/25 text-rose-100",
  },
  cyan: {
    badge: "border-cyan-500/40 bg-cyan-500/15 text-cyan-200",
    pill: "bg-cyan-500/10 border-cyan-500/30 text-cyan-300",
    pillActive: "bg-cyan-500/25 border-cyan-400 text-cyan-100 ring-1 ring-cyan-400/50",
    highlight: "border-cyan-400/70 bg-cyan-500/25 text-cyan-100",
  },
  fuchsia: {
    badge: "border-fuchsia-500/40 bg-fuchsia-500/15 text-fuchsia-200",
    pill: "bg-fuchsia-500/10 border-fuchsia-500/30 text-fuchsia-300",
    pillActive: "bg-fuchsia-500/25 border-fuchsia-400 text-fuchsia-100 ring-1 ring-fuchsia-400/50",
    highlight: "border-fuchsia-400/70 bg-fuchsia-500/25 text-fuchsia-100",
  },
  teal: {
    badge: "border-teal-500/40 bg-teal-500/15 text-teal-200",
    pill: "bg-teal-500/10 border-teal-500/30 text-teal-300",
    pillActive: "bg-teal-500/25 border-teal-400 text-teal-100 ring-1 ring-teal-400/50",
    highlight: "border-teal-400/70 bg-teal-500/25 text-teal-100",
  },
  slate: {
    badge: "border-slate-500/35 bg-slate-500/15 text-slate-300",
    pill: "bg-slate-500/10 border-slate-500/30 text-slate-300",
    pillActive: "bg-slate-500/25 border-slate-400 text-slate-100 ring-1 ring-slate-400/50",
    highlight: "border-slate-400/70 bg-slate-500/25 text-slate-100",
  },
  zinc: {
    badge: "border-zinc-700 bg-zinc-800 text-zinc-300",
    pill: "bg-zinc-700/30 border-zinc-600/50 text-zinc-300",
    pillActive: "bg-zinc-700/70 border-zinc-400 text-zinc-100 ring-1 ring-zinc-400/50",
    highlight: "border-zinc-500/70 bg-zinc-700/60 text-zinc-100",
  },
};

export function toneClasses(tone: string, variant: ToneVariant = "badge"): string {
  const entry = TONE_CLASSES[tone] || TONE_CLASSES.zinc;
  return entry[variant];
}

const COURSE_TOKEN_RE = /([A-Za-z]{2,8})[\s\-:]*(\d{3,4}[A-Za-z]?)/g;
const EXACT_COURSE_INPUT_RE = /^\s*([A-Za-z]{2,8})[\s\-:]*(\d{3,4}[A-Za-z]?)\s*$/;

export function parseCourseInputTokens(raw: string): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  for (const match of raw.matchAll(COURSE_TOKEN_RE)) {
    const code = `${match[1].toUpperCase()} ${match[2].toUpperCase()}`;
    if (!seen.has(code)) {
      seen.add(code);
      out.push(code);
    }
  }
  return out;
}

export function normalizeCourseCodeInput(raw: string): string | null {
  const m = EXACT_COURSE_INPUT_RE.exec(raw);
  if (!m) return null;
  return `${m[1].toUpperCase()} ${m[2].toUpperCase()}`;
}

export function formatUnitsRange(unitsMin?: number | null, unitsMax?: number | null): string {
  const lo = Number(unitsMin ?? 0);
  const hi = Number(unitsMax ?? 0);
  if (lo <= 0 && hi <= 0) return "";
  if (hi <= 0 || Math.abs(lo - hi) < 1e-6) {
    const v = lo > 0 ? lo : hi;
    return String(v);
  }
  return `${lo}-${hi}`;
}
