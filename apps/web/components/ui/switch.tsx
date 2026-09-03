"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * On/off. Hand-rolled rather than pulled in as another Radix package — it is
 * one button with `role="switch"`, and the material cues (the input-grade
 * hairline, the lit bevel, the physical press) have to match the rest of the
 * product anyway.
 *
 * The track carries a real `--input` border so its boundary clears the 3:1
 * WCAG asks of a control edge in both themes, and the knob is white-on-teal
 * when on, so the state is legible without leaning on a colour difference in
 * a washed-out track.
 *
 * The button itself is the hit target and takes `.tap`, so on a thumb it
 * grows to 44px around a track that stays 44×24 — the visual density of the
 * control is unchanged on desktop.
 */
export function Switch({
  checked,
  onCheckedChange,
  disabled = false,
  label,
  className,
}: {
  checked: boolean;
  onCheckedChange: (next: boolean) => void;
  disabled?: boolean;
  /** Spoken name — this control never ships with a visible text label. */
  label: string;
  className?: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onCheckedChange(!checked)}
      className={cn(
        "press tap group inline-flex shrink-0 items-center justify-center rounded-full",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
        "disabled:cursor-not-allowed disabled:opacity-45",
        className
      )}
    >
      <span
        aria-hidden="true"
        className={cn(
          "flex h-6 w-11 items-center rounded-full border transition-colors duration-200 ease-physical",
          checked
            ? "border-primary bg-primary shadow-[inset_0_1px_0_0_hsl(0_0%_100%/0.18)]"
            : "border-input bg-secondary shadow-inset"
        )}
      >
        <span
          className={cn(
            "block h-4 w-4 rounded-full bg-card shadow-[0_1px_2px_0_hsl(var(--foreground)/0.35)]",
            "transition-transform duration-200 ease-physical",
            checked ? "translate-x-[1.4rem]" : "translate-x-[0.175rem]"
          )}
        />
      </span>
    </button>
  );
}
