import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * The AURA mark: the runtime graph reduced to its smallest true form — one
 * core, six nodes, one shared base. It is the same idea as the big 3D graph,
 * which is the point: the logo is a diagram of the product, not an ornament.
 *
 * Single geometric mark, drawn in currentColor so it works on the graphite
 * sidebar, on paper, and in dark mode without variants.
 */
export function AuraMark({ className }: { className?: string }) {
  const nodes = Array.from({ length: 6 }, (_, i) => {
    const angle = (i / 6) * Math.PI * 2 - Math.PI / 2;
    return { x: 16 + Math.cos(angle) * 10, y: 14 + Math.sin(angle) * 10 };
  });

  return (
    <svg
      viewBox="0 0 32 32"
      className={cn("h-full w-full", className)}
      fill="none"
      aria-hidden="true"
    >
      {nodes.map((n, i) => (
        <line
          key={`e${i}`}
          x1={n.x}
          y1={n.y}
          x2={16}
          y2={14}
          stroke="currentColor"
          strokeOpacity={0.4}
          strokeWidth={1}
        />
      ))}
      {nodes.map((n, i) => (
        <circle key={`n${i}`} cx={n.x} cy={n.y} r={1.9} fill="currentColor" fillOpacity={0.75} />
      ))}
      <circle cx={16} cy={14} r={4.2} fill="currentColor" />
      {/* The shared base the whole system rests on. */}
      <ellipse
        cx={16}
        cy={26}
        rx={9}
        ry={2.6}
        stroke="currentColor"
        strokeOpacity={0.5}
        strokeWidth={1}
      />
    </svg>
  );
}

/** Mark plus wordmark, used in the sidebar and on the auth screens. */
export function AuraLogo({
  className,
  tone = "default",
}: {
  className?: string;
  tone?: "default" | "onDark";
}) {
  return (
    <span className={cn("flex items-center gap-2.5", className)}>
      <span
        className={cn(
          "flex h-8 w-8 shrink-0 items-center justify-center rounded-md p-1.5",
          tone === "onDark"
            ? "bg-white/[0.07] text-primary-foreground/90 ring-1 ring-inset ring-white/10"
            : "bg-primary/[0.08] text-primary ring-1 ring-inset ring-primary/15"
        )}
      >
        <AuraMark />
      </span>
      <span
        className={cn(
          "font-display text-[1.0625rem] font-semibold tracking-[0.14em]",
          tone === "onDark" ? "text-sidebar-foreground" : "text-foreground"
        )}
      >
        AURA
      </span>
    </span>
  );
}
