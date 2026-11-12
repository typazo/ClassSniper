import React from "react";

export function StatusBadge({ status }: { status: string | null | undefined }) {
  const code = (status || "?").toUpperCase();
  if (code === "O") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 px-2.5 py-0.5 text-xs font-semibold text-emerald-300 ring-1 ring-emerald-500/30">
        <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
        OPEN
      </span>
    );
  }
  if (code === "W") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/15 px-2.5 py-0.5 text-xs font-semibold text-amber-300 ring-1 ring-amber-500/30">
        <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />
        WAITLIST
      </span>
    );
  }
  if (code === "C") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-rose-500/15 px-2.5 py-0.5 text-xs font-semibold text-rose-300 ring-1 ring-rose-500/30">
        <span className="h-1.5 w-1.5 rounded-full bg-rose-400" />
        CLOSED
      </span>
    );
  }
  return (
    <span className="inline-flex items-center rounded-full bg-zinc-700/40 px-2.5 py-0.5 text-xs font-medium text-zinc-300">
      {code}
    </span>
  );
}
