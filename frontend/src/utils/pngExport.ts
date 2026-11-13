import type { DayCode, HydratedSchedule, ScheduleBlock, ScheduleCourseItem } from "../types";
import { summarizeScheduleInsights } from "./scheduleInsights";
import {
  computeScheduleDiagnostics,
  extractSectionSlots,
  formatMinutesShort,
} from "./schedulerSolver";

const PALETTE: Array<{ bg: string; border: string; text: string; sub: string }> = [
  { bg: "#064e3b", border: "#34d399", text: "#ecfdf5", sub: "#a7f3d0" },
  { bg: "#0c4a6e", border: "#38bdf8", text: "#f0f9ff", sub: "#bae6fd" },
  { bg: "#4c1d95", border: "#a78bfa", text: "#f5f3ff", sub: "#ddd6fe" },
  { bg: "#78350f", border: "#fbbf24", text: "#fffbeb", sub: "#fde68a" },
  { bg: "#881337", border: "#fb7185", text: "#fff1f2", sub: "#fecdd3" },
  { bg: "#164e63", border: "#22d3ee", text: "#ecfeff", sub: "#a5f3fc" },
  { bg: "#312e81", border: "#818cf8", text: "#eef2ff", sub: "#c7d2fe" },
  { bg: "#701a75", border: "#e879f9", text: "#fdf4ff", sub: "#f5d0fe" },
  { bg: "#134e4a", border: "#2dd4bf", text: "#f0fdfa", sub: "#99f6e4" },
  { bg: "#7c2d12", border: "#fb923c", text: "#fff7ed", sub: "#fed7aa" },
];

const DAY_DEFS: Array<{ code: DayCode; label: string }> = [
  { code: "M", label: "Monday" },
  { code: "T", label: "Tuesday" },
  { code: "W", label: "Wednesday" },
  { code: "R", label: "Thursday" },
  { code: "F", label: "Friday" },
  { code: "Sa", label: "Saturday" },
  { code: "Su", label: "Sunday" },
];

interface CanvasEvent {
  day: DayCode;
  startMin: number;
  endMin: number;
  title: string;
  subtitle: string;
  room: string;
  isBlock: boolean;
  colorIdx: number;
}

function drawRoundedRect(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  r: number
) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + r);
  ctx.lineTo(x + w, y + h - r);
  ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  ctx.lineTo(x + r, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - r);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
}

export type CopyPngOutcome = "copied" | "shared" | "downloaded" | "cancelled" | "failed";

/**
 * Renders the schedule calendar grid synchronously to a crisp 2x HTMLCanvasElement.
 * Kept strictly synchronous so browser clipboard writes preserve user-gesture activation on iOS/mobile.
 */
function renderScheduleCanvas(
  schedule: HydratedSchedule,
  coursesOverride?: ScheduleCourseItem[],
  blocksOverride?: ScheduleBlock[]
): HTMLCanvasElement | null {
  const courses = (coursesOverride ?? schedule.courses).filter((c) => c.enabled);
  const blocks = (blocksOverride ?? schedule.blocks).filter((b) => b.enabled);
  const diag = computeScheduleDiagnostics(courses, blocks);

  const rawEvents: CanvasEvent[] = [];
  let minMin = 8 * 60;
  let maxMin = 18 * 60;
  let hasSat = false;
  let hasSun = false;

  for (const b of blocks) {
    minMin = Math.min(minMin, b.start_min);
    maxMin = Math.max(maxMin, b.end_min);
    for (const day of b.days) {
      if (day === "Sa") hasSat = true;
      if (day === "Su") hasSun = true;
      rawEvents.push({
        day,
        startMin: b.start_min,
        endMin: b.end_min,
        title: b.label || "Busy",
        subtitle: `${formatMinutesShort(b.start_min)}-${formatMinutesShort(b.end_min)}`,
        room: "",
        isBlock: true,
        colorIdx: 0,
      });
    }
  }

  for (const c of courses) {
    const selected = new Set(c.selected_class_nbrs);
    const courseLabel = `${c.subject} ${c.catalog_nbr}`;
    for (const eg of c.enroll_groups) {
      for (const sec of eg.sections) {
        if (!selected.has(sec.class_nbr)) continue;
        for (const sl of extractSectionSlots(courseLabel, sec)) {
          minMin = Math.min(minMin, sl.start_min);
          maxMin = Math.max(maxMin, sl.end_min);
          if (sl.day === "Sa") hasSat = true;
          if (sl.day === "Su") hasSun = true;
          rawEvents.push({
            day: sl.day,
            startMin: sl.start_min,
            endMin: sl.end_min,
            title: courseLabel,
            subtitle: `${sec.ssr_component} ${sec.section} #${sec.class_nbr}`,
            room: sl.facility_descr || sec.instruction_mode || "",
            isBlock: false,
            colorIdx: c.color_idx,
          });
        }
      }
    }
  }

  const days = DAY_DEFS.filter(
    (d) => (d.code !== "Sa" && d.code !== "Su") || (d.code === "Sa" && hasSat) || (d.code === "Su" && hasSun)
  );
  const startHour = Math.max(7, Math.floor(minMin / 60));
  const endHour = Math.min(23, Math.max(startHour + 4, Math.ceil(maxMin / 60)));

  const width = 1400;
  const headerH = 82;
  const dayHeaderH = 38;
  const hourH = 62;
  const footerH = 44;
  const leftAxisW = 68;
  const padX = 24;
  const bodyH = (endHour - startHour) * hourH;
  const height = headerH + dayHeaderH + bodyH + footerH;

  const scale = 2;
  const canvas = document.createElement("canvas");
  canvas.width = width * scale;
  canvas.height = height * scale;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  ctx.scale(scale, scale);

  // Background
  ctx.fillStyle = "#09090b";
  ctx.fillRect(0, 0, width, height);

  // Header
  ctx.fillStyle = "#fafafa";
  ctx.font = "bold 24px system-ui, -apple-system, sans-serif";
  ctx.fillText(schedule.schedule.name, padX, 38);

  const insights = summarizeScheduleInsights(courses);
  const enabledCount = courses.filter((c) => c.enabled).length;
  const summaryParts = [
    schedule.schedule.roster,
    `${enabledCount} course${enabledCount === 1 ? "" : "s"}`,
    `${Number(diag.totalCredits.toFixed(1))} cr`,
    insights.avgDifficulty != null ? `Avg diff ${insights.avgDifficulty}/5` : null,
    insights.avgWorkload != null ? `Avg workload ${insights.avgWorkload}/5` : null,
  ].filter(Boolean);
  ctx.fillStyle = "#a1a1aa";
  ctx.font = "14px system-ui, -apple-system, sans-serif";
  ctx.fillText(summaryParts.join("  ·  "), padX, 64);

  const gridLeft = padX + leftAxisW;
  const gridWidth = width - gridLeft - padX;
  const colW = gridWidth / days.length;
  const gridTop = headerH + dayHeaderH;

  // Day Headers & Grid Borders
  ctx.strokeStyle = "#27272a";
  ctx.lineWidth = 1;
  ctx.fillStyle = "#18181b";
  ctx.fillRect(gridLeft, headerH, gridWidth, dayHeaderH);

  days.forEach((d, idx) => {
    const x = gridLeft + idx * colW;
    ctx.beginPath();
    ctx.moveTo(x, headerH);
    ctx.lineTo(x, gridTop + bodyH);
    ctx.stroke();

    ctx.fillStyle = "#e4e4e7";
    ctx.font = "600 13px system-ui, -apple-system, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(d.label, x + colW / 2, headerH + 24);
  });
  ctx.textAlign = "left";

  // Hour lines & labels
  for (let h = startHour; h <= endHour; h += 1) {
    const y = gridTop + (h - startHour) * hourH;
    ctx.strokeStyle = h === startHour || h === endHour ? "#3f3f46" : "#27272a";
    ctx.beginPath();
    ctx.moveTo(gridLeft, y);
    ctx.lineTo(gridLeft + gridWidth, y);
    ctx.stroke();

    if (h < endHour) {
      const hr12 = h % 12 === 0 ? 12 : h % 12;
      const suffix = h >= 12 ? "PM" : "AM";
      ctx.fillStyle = "#71717a";
      ctx.font = "12px system-ui, -apple-system, sans-serif";
      ctx.fillText(`${hr12} ${suffix}`, padX, y + 15);
    }
  }

  // Events per day (simple side-by-side column handling for overlaps)
  days.forEach((d, dayIdx) => {
    const dayEvents = rawEvents
      .filter((e) => e.day === d.code)
      .sort((a, b) => a.startMin - b.startMin);
    const colBaseX = gridLeft + dayIdx * colW;

    dayEvents.forEach((ev) => {
      const overlapSibs = dayEvents.filter(
        (other) => other.startMin < ev.endMin && ev.startMin < other.endMin
      );
      const sibIdx = overlapSibs.indexOf(ev);
      const totalCols = Math.max(1, overlapSibs.length);
      const w = (colW - 8) / totalCols;
      const x = colBaseX + 4 + sibIdx * w;
      const y = gridTop + ((ev.startMin - startHour * 60) / 60) * hourH + 1;
      const h = Math.max(22, ((ev.endMin - ev.startMin) / 60) * hourH - 2);

      const style = ev.isBlock
        ? { bg: "#27272a", border: "#71717a", text: "#e4e4e7", sub: "#a1a1aa" }
        : PALETTE[Math.abs(ev.colorIdx) % PALETTE.length];

      drawRoundedRect(ctx, x, y, w - 2, h, 7);
      ctx.fillStyle = style.bg;
      ctx.fill();
      ctx.strokeStyle = style.border;
      ctx.lineWidth = 1.5;
      ctx.stroke();

      ctx.save();
      ctx.beginPath();
      ctx.rect(x + 6, y + 3, w - 12, h - 6);
      ctx.clip();

      ctx.fillStyle = style.text;
      ctx.font = "bold 12px system-ui, -apple-system, sans-serif";
      ctx.fillText(ev.title, x + 7, y + 16);

      if (h >= 34) {
        ctx.fillStyle = style.sub;
        ctx.font = "11px system-ui, -apple-system, sans-serif";
        ctx.fillText(ev.subtitle, x + 7, y + 30);
      }
      if (h >= 50 && ev.room) {
        ctx.fillStyle = style.sub;
        ctx.font = "10px system-ui, -apple-system, sans-serif";
        ctx.fillText(ev.room, x + 7, y + 44);
      }
      ctx.restore();
    });
  });

  // Footer watermark
  ctx.fillStyle = "#52525b";
  ctx.font = "11px system-ui, -apple-system, sans-serif";
  ctx.fillText("Generated by ClassSniper Cornell Scheduler", padX, height - 16);

  return canvas;
}

function canvasToPngBlob(canvas: HTMLCanvasElement): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (blob) resolve(blob);
      else reject(new Error("Canvas toBlob returned null"));
    }, "image/png");
  });
}

function triggerPngDownload(canvas: HTMLCanvasElement, filename: string): void {
  const link = document.createElement("a");
  link.download = filename;
  link.href = canvas.toDataURL("image/png");
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

export function downloadSchedulePNG(
  schedule: HydratedSchedule,
  coursesOverride?: ScheduleCourseItem[],
  blocksOverride?: ScheduleBlock[]
): void {
  const canvas = renderScheduleCanvas(schedule, coursesOverride, blocksOverride);
  if (!canvas) return;
  const safeSlug = schedule.schedule.name.toLowerCase().replace(/[^a-z0-9]+/g, "-") || "schedule";
  triggerPngDownload(canvas, `${safeSlug}-${schedule.schedule.roster}.png`);
}

/**
 * Copies the rendered schedule PNG directly to the system clipboard using the
 * Promise-based ClipboardItem flow first (preserving synchronous user-gesture
 * activation on iOS Safari and mobile browsers for Discord/iMessage/Email),
 * falling back to resolved Blob write, Web Share API on mobile, or download.
 */
export async function copySchedulePNG(
  schedule: HydratedSchedule,
  coursesOverride?: ScheduleCourseItem[],
  blocksOverride?: ScheduleBlock[]
): Promise<CopyPngOutcome> {
  const canvas = renderScheduleCanvas(schedule, coursesOverride, blocksOverride);
  if (!canvas) return "failed";

  const safeSlug = schedule.schedule.name.toLowerCase().replace(/[^a-z0-9]+/g, "-") || "schedule";
  const filename = `${safeSlug}-${schedule.schedule.roster}.png`;

  // Start encoding synchronously inside the click handler
  const blobPromise = canvasToPngBlob(canvas);

  const canUseClipboard =
    typeof navigator !== "undefined" &&
    Boolean(navigator.clipboard?.write) &&
    typeof ClipboardItem !== "undefined";

  if (canUseClipboard) {
    // 1. Promise<Blob> ClipboardItem path: required on iOS/macOS Safari & works in modern Chrome/Firefox
    try {
      await navigator.clipboard.write([new ClipboardItem({ "image/png": blobPromise })]);
      return "copied";
    } catch {
      // 2. Fallback: await the Blob and pass it directly for browsers that reject Promise<Blob>
      try {
        const blob = await blobPromise;
        await navigator.clipboard.write([new ClipboardItem({ "image/png": blob })]);
        return "copied";
      } catch {
        // Proceed to share/download fallback below
      }
    }
  }

  // 3. Mobile Share Sheet fallback (e.g., iOS/Android over non-HTTPS or restricted WebViews)
  try {
    const blob = await blobPromise;
    const file = new File([blob], filename, { type: "image/png" });
    if (
      typeof navigator !== "undefined" &&
      typeof navigator.share === "function" &&
      navigator.canShare?.({ files: [file] })
    ) {
      try {
        await navigator.share({
          files: [file],
          title: `${schedule.schedule.name} (${schedule.schedule.roster})`,
        });
        return "shared";
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") {
          return "cancelled";
        }
      }
    }
  } catch {
    // Ignore and fall back to download
  }

  // 4. Last-resort fallback if clipboard & Web Share are both unavailable
  try {
    triggerPngDownload(canvas, filename);
    return "downloaded";
  } catch {
    return "failed";
  }
}
