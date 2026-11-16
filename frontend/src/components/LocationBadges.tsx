import React from "react";
import { Globe, MapPin } from "lucide-react";
import type { CourseSection, WatchSectionInfo } from "../types";
import {
  getSectionLocationTag,
  getSectionVirtualLabel,
  summarizeCourseLocation,
} from "../utils/location";

export function SectionLocationTags({
  section,
  showIthacaTag = false,
}: {
  section: Partial<Pick<CourseSection | WatchSectionInfo, "campus" | "location" | "location_descr" | "instruction_mode">>;
  showIthacaTag?: boolean;
}) {
  const locTag = getSectionLocationTag(section);
  const virtLabel = getSectionVirtualLabel(section.instruction_mode);

  return (
    <>
      {(locTag.isOffCampus || showIthacaTag) && (
        <span
          className={`inline-flex items-center gap-0.5 rounded px-1.5 py-0.5 text-[10px] font-medium ${
            locTag.isOffCampus
              ? "bg-amber-500/15 text-amber-300 ring-1 ring-amber-500/30"
              : "bg-zinc-800 text-zinc-400"
          }`}
        >
          <MapPin className="h-2.5 w-2.5" />
          {locTag.label}
        </span>
      )}
      {virtLabel && (
        <span className="inline-flex items-center gap-0.5 rounded bg-cyan-500/15 px-1.5 py-0.5 text-[10px] font-medium text-cyan-300 ring-1 ring-cyan-500/30">
          <Globe className="h-2.5 w-2.5" />
          {virtLabel}
        </span>
      )}
    </>
  );
}

export function CourseLocationTags({ sections }: { sections: CourseSection[] }) {
  const locSummary = summarizeCourseLocation(sections);
  if (locSummary.offCampusLabels.length === 0 && !locSummary.allVirtual && !locSummary.someVirtual) {
    return null;
  }

  return (
    <>
      {locSummary.offCampusLabels.map((lbl) => (
        <span
          key={lbl}
          className="inline-flex items-center gap-1 rounded-md border border-amber-500/35 bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-medium text-amber-300"
        >
          <MapPin className="h-2.5 w-2.5" />
          {lbl}
        </span>
      ))}
      {(locSummary.allVirtual || locSummary.someVirtual) && (
        <span className="inline-flex items-center gap-1 rounded-md border border-cyan-500/35 bg-cyan-500/10 px-1.5 py-0.5 text-[10px] font-medium text-cyan-300">
          <Globe className="h-2.5 w-2.5" />
          {locSummary.allVirtual ? "Virtual" : "Virtual opt."}
        </span>
      )}
    </>
  );
}
