import type { CourseSection, WatchSectionInfo } from "../types";

export interface SectionLocationTag {
  label: string;
  isIthaca: boolean;
  isTech: boolean;
  isOffCampus: boolean;
}

type LocationFields = Partial<
  Pick<CourseSection | WatchSectionInfo, "campus" | "location" | "location_descr">
>;

export function getSectionLocationTag(sec: LocationFields): SectionLocationTag {
  const loc = (sec.location || "").trim().toUpperCase();
  const camp = (sec.campus || "").trim().toUpperCase();
  const descr = (sec.location_descr || "").trim();

  if (loc === "NYCTECH" || camp === "NYT") {
    return {
      label: descr || "Cornell Tech",
      isIthaca: false,
      isTech: true,
      isOffCampus: true,
    };
  }
  if (loc === "ITH" || (!loc && (!camp || camp === "MAIN"))) {
    return {
      label: "Ithaca",
      isIthaca: true,
      isTech: false,
      isOffCampus: false,
    };
  }
  return {
    label: descr || loc || camp || "Off-campus",
    isIthaca: false,
    isTech: false,
    isOffCampus: true,
  };
}

export function isSectionPurelyVirtual(instructionMode?: string | null): boolean {
  const mode = (instructionMode || "").trim().toUpperCase();
  return (
    mode === "OL" ||
    mode === "AD" ||
    mode === "DL-AD" ||
    mode === "SD" ||
    mode === "DL-SD" ||
    mode === "ONLINE" ||
    mode === "DISTANCE LEARNING-ONLINE" ||
    mode === "DISTANCE LEARNING-ASYNCHRONOUS" ||
    mode === "DISTANCE LEARNING-SYNCHRONOUS" ||
    mode.startsWith("DL-")
  );
}

export function getSectionVirtualLabel(instructionMode?: string | null): string | null {
  const mode = (instructionMode || "").trim().toUpperCase();
  if (mode === "OL" || mode === "ONLINE" || mode === "DISTANCE LEARNING-ONLINE") {
    return "Online (OL)";
  }
  if (mode === "AD" || mode === "DL-AD" || mode === "DISTANCE LEARNING-ASYNCHRONOUS") {
    return "Virtual (DL-AD)";
  }
  if (mode === "SD" || mode === "DL-SD" || mode === "DISTANCE LEARNING-SYNCHRONOUS") {
    return "Virtual (DL-SD)";
  }
  if (mode.startsWith("DL-")) {
    return "Virtual";
  }
  if (mode === "HY" || mode === "HY-OLIP") {
    return "Hybrid";
  }
  return null;
}

export function summarizeCourseLocation(sections: CourseSection[]): {
  offCampusLabels: string[];
  allVirtual: boolean;
  someVirtual: boolean;
} {
  if (sections.length === 0) {
    return { offCampusLabels: [], allVirtual: false, someVirtual: false };
  }
  const offSet = new Set<string>();
  let virtualCount = 0;
  for (const sec of sections) {
    const tag = getSectionLocationTag(sec);
    if (tag.isOffCampus) {
      offSet.add(tag.label);
    }
    if (isSectionPurelyVirtual(sec.instruction_mode)) {
      virtualCount += 1;
    }
  }
  return {
    offCampusLabels: Array.from(offSet),
    allVirtual: virtualCount === sections.length,
    someVirtual: virtualCount > 0 && virtualCount < sections.length,
  };
}
