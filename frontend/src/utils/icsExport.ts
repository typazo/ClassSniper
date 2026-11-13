import type { DayCode, ScheduleCourseItem, ScheduleSection } from "../types";

const DAY_TO_ICS: Record<DayCode, string> = {
  M: "MO",
  T: "TU",
  W: "WE",
  R: "TH",
  F: "FR",
  Sa: "SA",
  Su: "SU",
};

const DAY_TO_JS_WEEKDAY: Record<DayCode, number> = {
  Su: 0,
  M: 1,
  T: 2,
  W: 3,
  R: 4,
  F: 5,
  Sa: 6,
};

function parseCornellDate(raw: string): Date | null {
  const s = (raw || "").trim();
  if (!s) return null;
  // Cornell formats: MM/DD/YYYY or YYYY-MM-DD
  const slash = s.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
  if (slash) {
    return new Date(Number(slash[3]), Number(slash[1]) - 1, Number(slash[2]));
  }
  const iso = s.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
  if (iso) {
    return new Date(Number(iso[1]), Number(iso[2]) - 1, Number(iso[3]));
  }
  return null;
}

function formatLocalICSDateTime(date: Date, totalMinutes: number): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  const hh = String(Math.floor(totalMinutes / 60)).padStart(2, "0");
  const mm = String(totalMinutes % 60).padStart(2, "0");
  return `${y}${m}${d}T${hh}${mm}00`;
}

function escapeICS(text: string): string {
  return text
    .replace(/\\/g, "\\\\")
    .replace(/\n/g, "\\n")
    .replace(/,/g, "\\,")
    .replace(/;/g, "\\;");
}

function findFirstMatchingDate(startDate: Date, days: DayCode[]): Date {
  const targetWeekdays = new Set(days.map((d) => DAY_TO_JS_WEEKDAY[d]));
  const cursor = new Date(startDate.getFullYear(), startDate.getMonth(), startDate.getDate());
  for (let i = 0; i < 7; i += 1) {
    if (targetWeekdays.has(cursor.getDay())) {
      return cursor;
    }
    cursor.setDate(cursor.getDate() + 1);
  }
  return startDate;
}

function nextMonday(): Date {
  const now = new Date();
  const diff = (8 - now.getDay()) % 7 || 7;
  return new Date(now.getFullYear(), now.getMonth(), now.getDate() + diff);
}

export function buildScheduleICS(
  scheduleName: string,
  roster: string,
  courses: ScheduleCourseItem[]
): string {
  const lines: string[] = [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//ClassSniper//Cornell Scheduler//EN",
    "CALSCALE:GREGORIAN",
    "METHOD:PUBLISH",
    `X-WR-CALNAME:${escapeICS(`${roster} - ${scheduleName}`)}`,
    "X-WR-TIMEZONE:America/New_York",
  ];

  const stamp = new Date().toISOString().replace(/[-:]/g, "").replace(/\.\d+Z$/, "Z");

  for (const course of courses) {
    if (!course.enabled) continue;
    const selectedSet = new Set(course.selected_class_nbrs);
    const sections: ScheduleSection[] = [];
    for (const eg of course.enroll_groups) {
      for (const sec of eg.sections) {
        if (selectedSet.has(sec.class_nbr)) {
          sections.push(sec);
        }
      }
    }

    for (const sec of sections) {
      sec.meetings.forEach((mtg, mIdx) => {
        if (!mtg.days.length || mtg.end_min <= mtg.start_min) return;
        const parsedStart = parseCornellDate(mtg.start_dt) || nextMonday();
        const parsedEnd = parseCornellDate(mtg.end_dt);
        const firstDay = findFirstMatchingDate(parsedStart, mtg.days);
        const dtStart = formatLocalICSDateTime(firstDay, mtg.start_min);
        const dtEnd = formatLocalICSDateTime(firstDay, mtg.end_min);
        const byDays = mtg.days.map((d) => DAY_TO_ICS[d]).join(",");

        let rrule = `RRULE:FREQ=WEEKLY;BYDAY=${byDays}`;
        if (parsedEnd) {
          const untilStr = `${parsedEnd.getFullYear()}${String(parsedEnd.getMonth() + 1).padStart(
            2,
            "0"
          )}${String(parsedEnd.getDate()).padStart(2, "0")}T235959`;
          rrule += `;UNTIL=${untilStr}`;
        } else {
          rrule += ";COUNT=15";
        }

        const summary = `${course.subject} ${course.catalog_nbr} ${sec.ssr_component} ${sec.section}`;
        const desc = `${course.title_long}\nClass #: ${sec.class_nbr}\nInstructors: ${
          mtg.instructors.join(", ") || sec.instructors_summary || "Staff"
        }`;

        lines.push("BEGIN:VEVENT");
        lines.push(`UID:classsniper-${roster}-${sec.class_nbr}-${mIdx}@classsniper`);
        lines.push(`DTSTAMP:${stamp}`);
        lines.push(`DTSTART;TZID=America/New_York:${dtStart}`);
        lines.push(`DTEND;TZID=America/New_York:${dtEnd}`);
        lines.push(rrule);
        lines.push(`SUMMARY:${escapeICS(summary)}`);
        if (mtg.facility_descr) {
          lines.push(`LOCATION:${escapeICS(mtg.facility_descr)}`);
        }
        lines.push(`DESCRIPTION:${escapeICS(desc)}`);
        lines.push("END:VEVENT");
      });
    }
  }

  lines.push("END:VCALENDAR");
  return lines.join("\r\n");
}

export function downloadScheduleICS(
  scheduleName: string,
  roster: string,
  courses: ScheduleCourseItem[]
): void {
  const content = buildScheduleICS(scheduleName, roster, courses);
  const blob = new Blob([content], { type: "text/calendar;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  const safeName = `${roster}_${scheduleName}`.replace(/[^a-zA-Z0-9_-]+/g, "_");
  link.href = url;
  link.download = `${safeName}.ics`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
