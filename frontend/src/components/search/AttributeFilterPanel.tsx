import React from "react";
import { Filter } from "lucide-react";
import type { AttributeOption, AttrMatchMode } from "../../types";

const FALLBACK_AS_ATTRS = [
  "ALC-AS",
  "BIO-AS",
  "ETM-AS",
  "GLC-AS",
  "HST-AS",
  "PHS-AS",
  "SCD-AS",
  "SSC-AS",
  "SDS-AS",
  "SMR-AS",
  "FWS",
  "LANG",
  "PE",
].map((code) => ({ code, label: code, group: "as_dist", count: 0 }));

interface Props {
  attrOptions: AttributeOption[];
  selectedAttrs: string[];
  attrMatch: AttrMatchMode;
  onChangeAttrMatch: (mode: AttrMatchMode) => void;
  onToggleAttr: (code: string) => void;
  onClearAttrs: () => void;
}

export function AttributeFilterPanel({
  attrOptions,
  selectedAttrs,
  attrMatch,
  onChangeAttrMatch,
  onToggleAttr,
  onClearAttrs,
}: Props) {
  const asDistAndCollege =
    attrOptions.length > 0
      ? attrOptions.filter((o) => o.group === "as_dist" || o.group === "college")
      : FALLBACK_AS_ATTRS;
  const engCalsAndExploratory = attrOptions.filter(
    (o) => o.group === "eng_cals" || o.group === "exploratory"
  );

  return (
    <div className="w-full space-y-2.5 rounded-xl border border-zinc-800 bg-zinc-950/85 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wide text-violet-300">
          <Filter className="h-3.5 w-3.5" />
          <span>Distribution &amp; College Attributes</span>
        </div>
        <div className="flex items-center gap-2 text-[11px]">
          <div className="inline-flex rounded-lg border border-zinc-700 bg-zinc-900 p-0.5">
            {(["any", "all"] as const).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => onChangeAttrMatch(m)}
                className={`rounded-md px-2 py-0.5 text-[11px] font-medium ${
                  attrMatch === m ? "bg-violet-500 text-zinc-950" : "text-zinc-400 hover:text-white"
                }`}
              >
                Match {m.toUpperCase()}
              </button>
            ))}
          </div>
          {selectedAttrs.length > 0 && (
            <button type="button" onClick={onClearAttrs} className="text-zinc-400 hover:text-white">
              Clear attrs
            </button>
          )}
        </div>
      </div>

      <div className="space-y-1.5">
        <div className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
          Arts &amp; Sciences (A&amp;S) + College
        </div>
        <div className="flex flex-wrap gap-1.5">
          {asDistAndCollege.map((opt) => {
            const active = selectedAttrs.includes(opt.code);
            const displayCode = opt.code === "HST-AS" ? "HIST-AS" : opt.code;
            return (
              <button
                key={opt.code}
                type="button"
                title={opt.label}
                onClick={() => onToggleAttr(opt.code)}
                className={`inline-flex items-center gap-1 rounded-lg border px-2 py-1 text-[11px] font-medium transition ${
                  active
                    ? "border-violet-400 bg-violet-500/25 text-white"
                    : "border-zinc-800 bg-zinc-900 text-zinc-300 hover:border-violet-500/40"
                }`}
              >
                <span>{displayCode}</span>
                {opt.count > 0 && <span className="text-[10px] text-zinc-500">{opt.count}</span>}
              </button>
            );
          })}
        </div>
      </div>

      {engCalsAndExploratory.length > 0 && (
        <div className="space-y-1.5">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
            Engineering / CALS / Exploratory
          </div>
          <div className="flex flex-wrap gap-1.5">
            {engCalsAndExploratory.map((opt) => {
              const active = selectedAttrs.includes(opt.code);
              return (
                <button
                  key={opt.code}
                  type="button"
                  title={opt.label}
                  onClick={() => onToggleAttr(opt.code)}
                  className={`inline-flex items-center gap-1 rounded-lg border px-2 py-1 text-[11px] font-medium transition ${
                    active
                      ? "border-sky-400 bg-sky-500/25 text-white"
                      : "border-zinc-800 bg-zinc-900 text-zinc-300 hover:border-sky-500/40"
                  }`}
                >
                  <span>{opt.code}</span>
                  {opt.count > 0 && <span className="text-[10px] text-zinc-500">{opt.count}</span>}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
