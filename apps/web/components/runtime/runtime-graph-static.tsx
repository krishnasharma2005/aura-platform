"use client";

import * as React from "react";
import { GRAPH_NODES, SHARED_LAYERS } from "@/lib/runtime-graph";
import { cn } from "@/lib/utils";

/**
 * The non-3D runtime graph.
 *
 * This is not a placeholder or a shrug — it is the same diagram, drawn
 * flat, and it has to teach the same thing: six agents, one core, three
 * shared layers underneath. It renders in three situations:
 *
 *   1. Server-side and during the first paint, underneath the canvas, so the
 *      box is never empty and nothing shifts when WebGL arrives.
 *   2. When the visitor has asked for reduced motion.
 *   3. When WebGL is unavailable (locked-down browsers, disabled GPU).
 *
 * It is pure SVG with no animation, so it costs nothing and always works.
 *
 * Two layouts, because an SVG's type scales with its box. The wide layout is
 * an 800-unit viewBox whose 13px labels land at ~13px in a desktop card. Drop
 * that same drawing into a 340px phone column and the labels render at 5.5px
 * — unreadable. The `compact` layout is a 460-unit viewBox with larger units,
 * so the labels come out around 11px on a phone. The ring labels are dropped
 * there rather than shrunk: the legend directly below the diagram already
 * names all three layers, with a sentence each.
 */

type Layout = {
  vb: string;
  cx: number;
  cy: number;
  rx: number;
  ry: number;
  coreR: number;
  glowR: number;
  /** y of the topmost shared-layer plate, and the gap between plates. */
  plateY: number;
  plateGap: number;
  plateRx: number;
  plateGrow: number;
  agentFont: number;
  ringFont: number;
  /** Vertical clearance between a node and its label. */
  labelGap: number;
  showRingLabels: boolean;
};

const WIDE: Layout = {
  vb: "0 0 800 430",
  cx: 372,
  cy: 150,
  rx: 236,
  ry: 70,
  coreR: 26,
  glowR: 62,
  plateY: 282,
  plateGap: 46,
  plateRx: 108,
  plateGrow: 42,
  agentFont: 13,
  ringFont: 11,
  labelGap: 18,
  showRingLabels: true,
};

const COMPACT: Layout = {
  vb: "0 0 460 430",
  cx: 230,
  cy: 142,
  rx: 150,
  ry: 60,
  coreR: 24,
  glowR: 56,
  plateY: 272,
  plateGap: 44,
  plateRx: 66,
  plateGrow: 40,
  agentFont: 17,
  ringFont: 13,
  labelGap: 20,
  showRingLabels: false,
};

function orbitPoint(index: number, total: number, l: Layout) {
  const angle = (index / total) * Math.PI * 2 - Math.PI / 2;
  return {
    x: l.cx + Math.cos(angle) * l.rx,
    y: l.cy + Math.sin(angle) * l.ry,
  };
}

export function RuntimeGraphStatic({
  className,
  activeSlug,
  tone = "default",
  layout = "wide",
}: {
  className?: string;
  /** Optional agent to emphasise, kept in sync with the card grid. */
  activeSlug?: string | null;
  /** `onDark` re-tints the diagram for the graphite panel on the auth screens. */
  tone?: "default" | "onDark";
  /** `compact` is the phone-column drawing. See the note above. */
  layout?: "wide" | "compact";
}) {
  const l = layout === "compact" ? COMPACT : WIDE;
  const points = GRAPH_NODES.map((_, i) => orbitPoint(i, GRAPH_NODES.length, l));
  const onDark = tone === "onDark";
  const ink = onDark ? "hsl(var(--sidebar-fg))" : "hsl(var(--foreground))";
  const quiet = onDark ? "hsl(var(--sidebar-muted))" : "hsl(var(--muted-foreground))";
  const plate = onDark ? "hsl(var(--sidebar-bg))" : "hsl(var(--card))";
  const lastPlateY = l.plateY + (SHARED_LAYERS.length - 1) * l.plateGap;

  return (
    <svg
      viewBox={l.vb}
      className={cn("h-full w-full", className)}
      role="img"
      aria-label="Diagram: six agents connected to one shared core, which sits on shared memory, your documents, and connected accounts."
    >
      <defs>
        <radialGradient id="aura-core-glow" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="hsl(var(--primary))" stopOpacity="0.35" />
          <stop offset="100%" stopColor="hsl(var(--primary))" stopOpacity="0" />
        </radialGradient>
      </defs>

      {/* The three shared layers, drawn as plates beneath the core. */}
      {SHARED_LAYERS.map((layer, i) => {
        const y = l.plateY + i * l.plateGap;
        const rx = l.plateRx + i * l.plateGrow;
        return (
          <g key={layer.id}>
            <ellipse
              cx={l.cx}
              cy={y}
              rx={rx}
              ry={rx * 0.19}
              fill="none"
              stroke="hsl(var(--primary))"
              strokeOpacity={0.26}
              strokeWidth={1.25}
            />
            {l.showRingLabels && (
              <text
                x={l.cx + rx + 12}
                y={y + 4}
                fill={quiet}
                fontSize={l.ringFont}
                fontFamily="var(--font-mono)"
                letterSpacing="0.08em"
              >
                {layer.label}
              </text>
            )}
          </g>
        );
      })}

      {/* Core down to each shared layer — the spine of the system. */}
      <line
        x1={l.cx}
        y1={l.cy}
        x2={l.cx}
        y2={lastPlateY}
        stroke="hsl(var(--primary))"
        strokeOpacity={0.32}
        strokeWidth={1.5}
      />

      {/* Agent edges into the core. */}
      {points.map((p, i) => {
        const node = GRAPH_NODES[i];
        const dim = activeSlug ? activeSlug !== node.slug : false;
        return (
          <path
            key={`edge-${node.slug}`}
            d={`M ${p.x} ${p.y} Q ${l.cx + (p.x - l.cx) * 0.42} ${
              l.cy + (p.y - l.cy) * 0.42 + 34
            } ${l.cx} ${l.cy}`}
            fill="none"
            stroke={ink}
            strokeOpacity={dim ? 0.08 : 0.2}
            strokeWidth={1.25}
          />
        );
      })}

      {/* The shared core. */}
      <circle cx={l.cx} cy={l.cy} r={l.glowR} fill="url(#aura-core-glow)" />
      <circle
        cx={l.cx}
        cy={l.cy}
        r={l.coreR}
        fill="hsl(var(--primary))"
        fillOpacity={0.14}
        stroke="hsl(var(--primary))"
        strokeOpacity={0.55}
        strokeWidth={1.5}
      />
      <circle cx={l.cx} cy={l.cy} r={l.coreR * 0.42} fill="hsl(var(--primary))" />

      {/* Agent nodes. */}
      {points.map((p, i) => {
        const node = GRAPH_NODES[i];
        const active = activeSlug === node.slug;
        const dim = activeSlug ? !active : false;
        const anchor = p.x > l.cx + 40 ? "start" : p.x < l.cx - 40 ? "end" : "middle";
        const dx = anchor === "start" ? 16 : anchor === "end" ? -16 : 0;
        /*
         * The top and bottom nodes project onto the vertical axis, where the
         * core sits above and the shared plates sit below. Their labels go
         * outward along that axis — up for the top node, down for the bottom
         * one — and the plates start far enough below the orbit that the
         * bottom label clears the first ring. (It used to land inside it.)
         */
        const dy =
          anchor === "middle"
            ? p.y < l.cy
              ? -l.labelGap
              : l.labelGap + l.agentFont * 0.6
            : l.agentFont * 0.34;
        return (
          <g key={node.slug} opacity={dim ? 0.42 : 1}>
            <circle
              cx={p.x}
              cy={p.y}
              r={active ? 11 : 8}
              fill={plate}
              stroke="hsl(var(--primary))"
              strokeOpacity={active ? 0.9 : 0.5}
              strokeWidth={active ? 2.5 : 1.75}
            />
            <text
              x={p.x + dx}
              y={p.y + dy}
              textAnchor={anchor}
              fill={ink}
              fontSize={l.agentFont}
              fontWeight={active ? 600 : 500}
              fontFamily="var(--font-ui)"
            >
              {node.label}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
