import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * A supporting number. Deliberately quiet: the hero figure is the only loud
 * thing on the page, and a row of tiles competing with it would turn the
 * dashboard back into the wall of counters it is trying not to be.
 */
export function StatTile({
  label,
  value,
  note,
  className,
}: {
  label: string;
  value: React.ReactNode;
  note?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("rounded-lg border border-border bg-card p-4 shadow-subtle", className)}>
      <p className="text-2xs font-medium uppercase tracking-[0.1em] text-subtle">{label}</p>
      <p className="mt-1.5 font-display text-2xl font-semibold tracking-[-0.02em] text-foreground">
        {value}
      </p>
      {note && <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{note}</p>}
    </div>
  );
}
