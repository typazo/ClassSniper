import React from "react";
import { Loader2, MapPin } from "lucide-react";
import type { SearchCoursesMeta } from "../../types";
import type { StatusFilter } from "../../hooks/useCatalogSearch";

interface Props {
  statusFilter: StatusFilter;
  onChangeStatusFilter: (filter: StatusFilter) => void;
  filterCounts: { all: number; open: number; waitlist: number; closed: number; pending: number };
  ithacaOrVirtual: boolean;
  searchMeta: SearchCoursesMeta | null;
  filteredCount: number;
  totalLoadedCount: number;
  staleVisibleCount: number;
  onShowAllLocations: () => void;
}

export function SearchResultsToolbar({
  statusFilter,
  onChangeStatusFilter,
  filterCounts,
  ithacaOrVirtual,
  searchMeta,
  filteredCount,
  totalLoadedCount,
  staleVisibleCount,
  onShowAllLocations,
}: Props) {
  const hiddenCount = searchMeta?.filtered_out_location_count ?? 0;
  const hiddenLocs = searchMeta?.filtered_out_locations || [];
  const totalMatched = searchMeta?.total_matched ?? totalLoadedCount;

  return (
    <div className="flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-zinc-800 bg-zinc-900/50 px-4 py-2.5">
      <div className="flex flex-wrap items-center gap-1.5">
        {(
          [
            { id: "all", label: "All", count: filterCounts.all },
            { id: "open", label: "Has Open", count: filterCounts.open },
            { id: "waitlist", label: "Has Waitlist", count: filterCounts.waitlist },
            { id: "closed", label: "Has Closed", count: filterCounts.closed },
          ] as const
        ).map((opt) => {
          const active = statusFilter === opt.id;
          return (
            <button
              key={opt.id}
              type="button"
              onClick={() => onChangeStatusFilter(opt.id)}
              className={`rounded-lg px-2.5 py-1 text-xs font-medium transition-colors ${
                active
                  ? "bg-emerald-500/20 text-emerald-300 ring-1 ring-emerald-500/40"
                  : "text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
              }`}
            >
              {opt.label} ({opt.count})
            </button>
          );
        })}
        {filterCounts.pending > 0 && statusFilter !== "all" && (
          <span className="ml-1 inline-flex items-center gap-1 rounded-md bg-amber-500/10 px-2 py-0.5 text-[11px] text-amber-200">
            <Loader2 className="h-3 w-3 animate-spin" />
            +{filterCounts.pending} loading live check
          </span>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-3 text-xs text-zinc-500">
        {ithacaOrVirtual && hiddenCount > 0 && (
          <button
            type="button"
            onClick={onShowAllLocations}
            className="inline-flex items-center gap-1 rounded-md border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-[11px] font-medium text-amber-200 hover:bg-amber-500/20"
            title={`Hidden off-campus courses (${hiddenLocs.join(", ")})`}
          >
            <MapPin className="h-3 w-3 text-amber-300" />
            {hiddenCount} off-campus hidden
            {hiddenLocs.length > 0 ? ` (${hiddenLocs.slice(0, 2).join(", ")})` : ""}
            {" · Show all"}
          </button>
        )}
        {staleVisibleCount > 0 && (
          <span className="inline-flex items-center gap-1.5 text-amber-300">
            <Loader2 className="h-3 w-3 animate-spin" />
            Updating live status in background ({staleVisibleCount})...
          </span>
        )}
        <span>
          Showing {filteredCount} of {totalMatched} course{totalMatched === 1 ? "" : "s"}
        </span>
      </div>
    </div>
  );
}
