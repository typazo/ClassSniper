export interface ParsedCompletedCourse {
  course: string;
  sem: string;
  gr: string;
  cr: string;
}

export interface ParsedInProgressCourse {
  course: string;
  roster: string;
  cr: string;
}

export interface ParsedExcludedCourse {
  course: string;
  sem: string;
  gr: string;
  reason: string;
}

export interface ParsedTranscriptResult {
  completed: ParsedCompletedCourse[];
  inProgress: ParsedInProgressCourse[];
  excluded: ParsedExcludedCourse[];
  detectedPeCount: number;
}

const SEASON_TO_CODE: Record<string, string> = {
  FALL: "FA",
  FA: "FA",
  SPRING: "SP",
  SP: "SP",
  WINTER: "WI",
  WI: "WI",
  SUMMER: "SU",
  SU: "SU",
};

const PASSING_GRADES = new Set([
  "A+",
  "A",
  "A-",
  "B+",
  "B",
  "B-",
  "C+",
  "C",
  "C-",
  "D+",
  "D",
  "D-",
  "S",
  "SX",
  "CR",
  "P",
]);

const IN_PROGRESS_GRADES = new Set(["IP", "INP", "NGR"]);

const EXCLUDED_GRADE_REASONS: Record<string, string> = {
  W: "Withdrawn (W)",
  F: "No credit (F)",
  U: "Unsatisfactory (U)",
  UX: "Unsatisfactory (UX)",
  NC: "No credit (NC)",
  INC: "Incomplete (INC)",
  DR: "Dropped (DR)",
  AUD: "Audit (AUD)",
  V: "Visitor/Audit (V)",
  R: "In-progress/R",
};

const VALID_GRADES_GROUP =
  "A\\+|A-|A|B\\+|B-|B|C\\+|C-|C|D\\+|D-|D|F|SX|UX|NC|CR|IP|INP|NGR|INC|AUD|DR|S|U|P|W|V|R";

const TERM_HEADER_PATTERNS: RegExp[] = [
  /^(20\d{2})\s+(Fall|Spring|Winter|Summer)\b/i,
  /^(Fall|Spring|Winter|Summer)\s+(20\d{2})\b/i,
  /^(20\d{2})(FA|SP|WI|SU)\b/i,
  /^(FA|SP|WI|SU)\s*(20\d{2}|\d{2})\b/i,
];

const TRANSFERRED_TERM_RE =
  /\bTransferred\s+to\s+Term\s+(?:(20\d{2})(FA|SP|WI|SU)|(Fall|Spring|Winter|Summer)\s+(20\d{2})|(20\d{2})\s+(Fall|Spring|Winter|Summer)|(FA|SP|WI|SU)\s*(\d{2}))\b/i;

const COURSE_START_RE = /^([A-Z]{2,8})\s+(\d{3,4}[A-Z]?)\b(.*)$/;
// Note: use (?=\s|$) instead of \b after VALID_GRADES_GROUP because "+" and "-" (A+, A-, B+, etc.) are non-word chars (\W).
const CREDITS_GRADE_TAIL_RE = new RegExp(
  `\\b(\\d{1,2}(?:\\.\\d{1,2})?)\\s*(?:\\d{1,2}(?:\\.\\d{1,2})?\\s*)?(?:\\b(${VALID_GRADES_GROUP})(?=\\s|$))?(?:\\s+0+(?:\\.0+)?)?\\s*$`
);
const PURE_SCORE_LINE_RE = /^\(\s*\d+(?:\.\d+)?\s*\)$/;

const NOISE_PREFIXES = [
  "TERM TOTALS",
  "TERM GPA",
  "CUMULATIVE",
  "CUM GPA",
  "END OF ",
  "BEGINNING OF ",
  "COURSE DESCRIPTION",
  "UNOFFICIAL TRANSCRIPT",
  "ACADEMIC STANDING",
  "DEAN'S LIST",
  "PAGE ",
  "PRINT DATE",
  "BIRTHDATE",
  "STUDENT ID",
  "EMPLID",
  "PROGRAM ",
  "PLAN ",
  "SUBPLAN",
];

const NON_COURSE_SUBJECTS = new Set([
  "FALL",
  "SPRING",
  "WINTER",
  "SUMMER",
  "TERM",
  "GPA",
  "PAGE",
  "UNIT",
  "UNITS",
  "ID",
  "CUM",
  "CUMULATIVE",
  "EARNED",
  "ATTEMPTED",
  "POINTS",
  "TOTAL",
  "DATE",
  "CAREER",
  "PROGRAM",
  "PLAN",
  "SUBPLAN",
  "DEGREE",
  "HONORS",
  "STATUS",
  "CREDITS",
  "GRADE",
  "SCORE",
  "COURSE",
  "ROOM",
  "SESSION",
  "BLDG",
]);

function toRosterSlug(yearRaw: string, seasonRaw: string): string {
  const season = SEASON_TO_CODE[seasonRaw.toUpperCase()] || "";
  if (!season) return "";
  const yy = yearRaw.length === 4 ? yearRaw.slice(2) : yearRaw.padStart(2, "0");
  return `${season}${yy}`;
}

function parseTermHeader(line: string): string | null {
  const trimmed = line.trim().replace(/^TERM\s*:?\s+/i, "");
  if (!trimmed) return null;
  for (const re of TERM_HEADER_PATTERNS) {
    const m = trimmed.match(re);
    if (!m) continue;
    const [, a, b] = m;
    if (/^\d+$/.test(a)) {
      return toRosterSlug(a, b);
    }
    return toRosterSlug(b, a);
  }
  return null;
}

function parseTransferredTerm(line: string): string | null {
  const m = line.match(TRANSFERRED_TERM_RE);
  if (!m) return null;
  if (m[1] && m[2]) return toRosterSlug(m[1], m[2]);
  if (m[3] && m[4]) return toRosterSlug(m[4], m[3]);
  if (m[5] && m[6]) return toRosterSlug(m[5], m[6]);
  if (m[7] && m[8]) return toRosterSlug(m[8], m[7]);
  return null;
}

function formatCredits(raw: string): string {
  const n = Number(raw);
  if (!Number.isFinite(n) || n <= 0 || n > 12) return "";
  return Number.isInteger(n) ? String(n) : String(Number(n.toFixed(2)));
}

function isBoundaryLine(line: string): boolean {
  const upper = line.trim().toUpperCase();
  if (!upper) return true;
  if (parseTermHeader(upper)) return true;
  const cm = upper.match(COURSE_START_RE);
  if (cm && !NON_COURSE_SUBJECTS.has(cm[1])) return true;
  if (TRANSFERRED_TERM_RE.test(line)) return true;
  if (
    upper.includes("ADVANCED PLACEMENT") ||
    upper.includes("TEST CREDIT") ||
    upper.includes("TRANSFER CREDIT") ||
    upper.includes("COURSEWORK IN PROGRESS") ||
    upper === "IN PROGRESS"
  ) {
    return true;
  }
  return NOISE_PREFIXES.some((p) => upper.startsWith(p));
}

interface PdfTextChunk {
  str: string;
  x: number;
  y: number;
  w: number;
}

function groupChunksIntoLines(chunks: PdfTextChunk[]): string[] {
  if (chunks.length === 0) return [];
  const sorted = [...chunks].sort((a, b) => b.y - a.y || a.x - b.x);
  const rows: PdfTextChunk[][] = [];
  for (const ch of sorted) {
    const last = rows[rows.length - 1];
    if (last && Math.abs(last[0].y - ch.y) <= 2.8) {
      last.push(ch);
    } else {
      rows.push([ch]);
    }
  }
  return rows.map((row) =>
    row
      .sort((a, b) => a.x - b.x)
      .map((c) => c.str)
      .join(" ")
      .replace(/\s+/g, " ")
      .trim()
  );
}

/** Extract ordered text lines purely in the browser via pdfjs-dist without network uploads. */
export async function extractTranscriptTextFromPdf(file: File): Promise<string> {
  const [pdfjsLib, workerMod] = await Promise.all([
    import("pdfjs-dist"),
    import("pdfjs-dist/build/pdf.worker.min.mjs?url"),
  ]);
  pdfjsLib.GlobalWorkerOptions.workerSrc = workerMod.default;

  const bytes = new Uint8Array(await file.arrayBuffer());
  const loadingTask = pdfjsLib.getDocument({
    data: bytes,
    useSystemFonts: true,
    disableFontFace: true,
  });
  const doc = await loadingTask.promise;

  const pageTexts: string[] = [];
  try {
    for (let pageNum = 1; pageNum <= doc.numPages; pageNum += 1) {
      const page = await doc.getPage(pageNum);
      const viewport = page.getViewport({ scale: 1 });
      const content = await page.getTextContent();
      const chunks: PdfTextChunk[] = [];
      for (const item of content.items) {
        if (!("str" in item) || typeof item.str !== "string") continue;
        const text = item.str.trim();
        if (!text) continue;
        const tr = item.transform || [1, 0, 0, 1, 0, 0];
        chunks.push({
          str: text,
          x: Number(tr[4] || 0),
          y: Number(tr[5] || 0),
          w: Number(item.width || 0),
        });
      }

      // Detect PeopleSoft two-column transcript layout via clear horizontal gutter near page midpoint
      const midX = viewport.width * 0.5;
      const crossing = chunks.filter((c) => c.x < midX - 8 && c.x + c.w > midX + 8);
      const left = chunks.filter((c) => c.x + c.w * 0.5 < midX);
      const right = chunks.filter((c) => c.x + c.w * 0.5 >= midX);
      const twoColumn =
        left.length >= 12 &&
        right.length >= 12 &&
        crossing.length <= Math.max(2, Math.floor(chunks.length * 0.03));

      const lines = twoColumn
        ? [...groupChunksIntoLines(left), ...groupChunksIntoLines(right)]
        : groupChunksIntoLines(chunks);
      pageTexts.push(lines.filter(Boolean).join("\n"));
    }
  } finally {
    await doc.destroy();
  }

  return pageTexts.join("\n");
}

interface RawParsedRow {
  course: string;
  subj: string;
  sem: string;
  gr: string;
  cr: string;
  inProgressFlag: boolean;
  isTransfer: boolean;
  orderIdx: number;
}

/** Deterministically parse Cornell Student Center unofficial transcript text into sanitized course records. */
export function parseCornellTranscriptText(rawText: string): ParsedTranscriptResult {
  const rawLines = rawText
    .split(/\r?\n/)
    .map((l) => l.replace(/\s+/g, " ").trim())
    .filter(Boolean);

  let currentTerm = "";
  let inTransferBlock = false;
  let transferPrefix = "AP";
  let inProgressSection = false;
  let latestRegularTerm = "";
  const parsedRows: RawParsedRow[] = [];

  for (let i = 0; i < rawLines.length; i += 1) {
    const line = rawLines[i];
    const upper = line.toUpperCase();

    if (upper.includes("COURSEWORK IN PROGRESS") || upper === "IN PROGRESS") {
      inProgressSection = true;
      inTransferBlock = false;
      continue;
    }

    if (upper.includes("ADVANCED PLACEMENT") || upper.includes("TEST CREDIT")) {
      inTransferBlock = true;
      transferPrefix = "AP";
      inProgressSection = false;
      continue;
    }
    if (upper.includes("TRANSFER CREDIT")) {
      inTransferBlock = true;
      transferPrefix = "TR";
      inProgressSection = false;
      continue;
    }

    const transferredTerm = parseTransferredTerm(line);
    if (transferredTerm) {
      inTransferBlock = true;
      currentTerm = transferredTerm;
      inProgressSection = false;
      continue;
    }

    const headerTerm = parseTermHeader(line);
    if (headerTerm) {
      currentTerm = headerTerm;
      latestRegularTerm = headerTerm;
      inTransferBlock = false;
      // Do not turn off inProgressSection if it is the term header directly under "Coursework in Progress"
      continue;
    }

    if (upper.startsWith("END OF ") || upper.startsWith("BEGINNING OF ")) {
      inTransferBlock = false;
      inProgressSection = false;
      continue;
    }

    if (PURE_SCORE_LINE_RE.test(line) || NOISE_PREFIXES.some((p) => upper.startsWith(p))) {
      continue;
    }

    const cm = line.match(COURSE_START_RE);
    if (!cm) continue;

    const subj = cm[1].toUpperCase();
    const nbr = cm[2].toUpperCase();
    // Skip obvious non-course numeric tokens (e.g. FALL 2024, SPRING 2025, GPA, TERM, etc.)
    if (NON_COURSE_SUBJECTS.has(subj)) {
      continue;
    }

    let combinedTail = (cm[3] || "").trim();
    let tailMatch = combinedTail.match(CREDITS_GRADE_TAIL_RE);

    // Join wrapped course lines (e.g. "PSYCH 1101 Introduction to / Psychology / 3.00 S"
    // or a title ending in a bare number like "Part 2" before "4.00 4.00 A-")
    let lookahead = 1;
    while (
      lookahead <= 4 &&
      i + lookahead < rawLines.length &&
      (!tailMatch || (!tailMatch[2] && !tailMatch[1].includes(".")))
    ) {
      const nextLine = rawLines[i + lookahead];
      if (isBoundaryLine(nextLine)) break;
      const nextCombined = `${combinedTail} ${nextLine}`.trim();
      const nextMatch = nextCombined.match(CREDITS_GRADE_TAIL_RE);
      combinedTail = nextCombined;
      if (nextMatch) {
        tailMatch = nextMatch;
      }
      lookahead += 1;
      if (tailMatch && (tailMatch[2] || tailMatch[1].includes("."))) {
        break;
      }
    }
    if (lookahead > 1 && tailMatch) {
      i += lookahead - 1;
    }

    const cr = tailMatch ? formatCredits(tailMatch[1]) : "";
    const gr = tailMatch && tailMatch[2] ? tailMatch[2].toUpperCase() : "";

    const semLabel = inTransferBlock
      ? currentTerm
        ? `${transferPrefix} ${currentTerm}`
        : transferPrefix
      : currentTerm;

    parsedRows.push({
      course: `${subj} ${nbr}`,
      subj,
      sem: semLabel,
      gr,
      cr,
      inProgressFlag: inProgressSection,
      isTransfer: inTransferBlock,
      orderIdx: parsedRows.length,
    });
  }

  // Detect whether any earlier regular terms had completed grades so ungraded final-term rows become IP
  const hasAnyCompletedGradedRow = parsedRows.some((r) => !r.isTransfer && Boolean(r.gr));

  const bestCompleted = new Map<string, ParsedCompletedCourse>();
  const bestInProgress = new Map<string, ParsedInProgressCourse>();
  const excludedMap = new Map<string, ParsedExcludedCourse>();
  const countedPe = new Set<string>();

  for (const row of parsedRows) {
    if (row.gr && EXCLUDED_GRADE_REASONS[row.gr]) {
      if (!bestCompleted.has(row.course) && !bestInProgress.has(row.course)) {
        excludedMap.set(row.course, {
          course: row.course,
          sem: row.sem,
          gr: row.gr,
          reason: EXCLUDED_GRADE_REASONS[row.gr],
        });
      }
      continue;
    }

    const termUpper = row.sem.replace(/^(AP|TR)\s+/i, "").trim().toUpperCase();
    const emptyGradeCurrentTerm =
      !row.isTransfer &&
      !row.gr &&
      Boolean(termUpper) &&
      termUpper === latestRegularTerm &&
      (hasAnyCompletedGradedRow || !parsedRows.some((r) => !r.isTransfer && r.sem && r.sem !== latestRegularTerm));

    const isIp =
      row.inProgressFlag || IN_PROGRESS_GRADES.has(row.gr) || emptyGradeCurrentTerm;

    if (isIp) {
      if (!bestCompleted.has(row.course)) {
        bestInProgress.set(row.course, {
          course: row.course,
          roster: termUpper,
          cr: row.cr,
        });
      }
      excludedMap.delete(row.course);
      continue;
    }

    if (!row.gr || PASSING_GRADES.has(row.gr)) {
      if (row.subj === "PE" && (row.gr || row.cr)) {
        countedPe.add(`${row.course}:${row.sem || row.orderIdx}`);
      }
      const existing = bestCompleted.get(row.course);
      if (!existing || (!existing.gr && row.gr) || (!existing.sem && row.sem)) {
        bestCompleted.set(row.course, {
          course: row.course,
          sem: row.sem,
          gr: row.gr,
          cr: row.cr,
        });
      }
      bestInProgress.delete(row.course);
      excludedMap.delete(row.course);
    }
  }

  return {
    completed: Array.from(bestCompleted.values()),
    inProgress: Array.from(bestInProgress.values()),
    excluded: Array.from(excludedMap.values()),
    detectedPeCount: Math.min(4, countedPe.size),
  };
}
