import React from "react";
import { X } from "lucide-react";

export function FloatingToast({
  message,
  tone = "info",
  onDismiss,
}: {
  message: string | null;
  tone?: "info" | "success" | "error";
  onDismiss?: () => void;
}) {
  if (!message) return null;
  const toneClass =
    tone === "error"
      ? "border-rose-500/45 bg-zinc-950/95 text-rose-200"
      : tone === "success"
        ? "border-emerald-500/45 bg-zinc-950/95 text-emerald-200"
        : "border-zinc-700 bg-zinc-950/95 text-zinc-100";

  return (
    <div className="pointer-events-none fixed bottom-20 right-4 z-50 sm:bottom-5">
      <div
        role="status"
        className={`pointer-events-auto flex max-w-md items-center gap-2.5 rounded-xl border px-3.5 py-2.5 text-xs shadow-2xl backdrop-blur-md ${toneClass}`}
      >
        <span>{message}</span>
        {onDismiss && (
          <button
            type="button"
            onClick={onDismiss}
            className="text-zinc-400 hover:text-zinc-200"
            aria-label="Dismiss notification"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}
      </div>
    </div>
  );
}
