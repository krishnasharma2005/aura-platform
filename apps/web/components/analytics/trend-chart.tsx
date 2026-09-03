"use client";

import * as React from "react";
import { Table2, BarChart3 } from "lucide-react";
import type { AnalyticsDailyPoint } from "@/lib/api-types";
import { axisTickLabel, fullDayLabel } from "@/lib/analytics";
import { cn } from "@/lib/utils";

/**
 * The trend, drawn by hand.
 *
 * Deliberately inline SVG rather than a charting library: the series is at
 * most 90 points, and drawing it ourselves is the only way the marks, the
 * hairlines and the type end up wearing the product's own tokens in both
 * themes instead of a library's defaults over a theme override.
 *
 * Form: one series, one hue. Conversations per day is a magnitude over time
 * with no identity to distinguish, so this is columns in the accent hue — not
 * a categorical palette, and emphatically not two y-axes with messages on the
 * second. Messages live in their own stat tile, at their own scale.
 *
 * Everything the chart shows is reachable without a pointer: the y-axis
 * carries the scale, the tallest column is directly labelled, each column is
 * focusable with a spoken label, and the table view underneath is the full
 * set of numbers.
 */

const PLOT_HEIGHT = 168;
const AXIS_BAND = 26;
const LABEL_BAND = 18; // headroom for the direct label above the tallest column
const Y_AXIS_WIDTH = 34;
const MAX_BAR_WIDTH = 24;
const BAR_RADIUS = 4;

/** A column: rounded at the data end, square where it meets the baseline. */
function columnPath(x: number, y: number, width: number, height: number): string {
  const r = Math.min(BAR_RADIUS, width / 2, height);
  const bottom = y + height;
  return [
    `M ${x} ${bottom}`,
    `L ${x} ${y + r}`,
    `Q ${x} ${y} ${x + r} ${y}`,
    `L ${x + width - r} ${y}`,
    `Q ${x + width} ${y} ${x + width} ${y + r}`,
    `L ${x + width} ${bottom}`,
    "Z",
  ].join(" ");
}

/** Round the scale up to something a person would say out loud. */
function niceMax(value: number): number {
  if (value <= 5) return 5;
  const magnitude = Math.pow(10, Math.floor(Math.log10(value)));
  for (const step of [1, 1.5, 2, 2.5, 3, 4, 5, 7.5, 10]) {
    const candidate = step * magnitude;
    if (candidate >= value) return Math.round(candidate);
  }
  return Math.round(10 * magnitude);
}

export function TrendChart({
  points,
  seriesLabel = "Conversations",
  className,
}: {
  points: AnalyticsDailyPoint[];
  seriesLabel?: string;
  className?: string;
}) {
  const containerRef = React.useRef<HTMLDivElement>(null);
  const [width, setWidth] = React.useState(0);
  const [activeIndex, setActiveIndex] = React.useState<number | null>(null);
  const [showTable, setShowTable] = React.useState(false);

  React.useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => {
      const next = entries[0]?.contentRect.width ?? 0;
      setWidth(Math.round(next));
    });
    observer.observe(el);
    setWidth(Math.round(el.getBoundingClientRect().width));
    return () => observer.disconnect();
  }, []);

  const values = points.map((p) => p.conversations ?? 0);
  const total = values.reduce((sum, v) => sum + v, 0);
  const peakValue = Math.max(...values, 0);
  const peakCount = values.filter((v) => v === peakValue && v > 0).length;
  const scaleMax = niceMax(Math.max(...values, 1));

  const height = PLOT_HEIGHT + AXIS_BAND + LABEL_BAND;
  const plotWidth = Math.max(width - Y_AXIS_WIDTH, 1);
  const bandWidth = plotWidth / Math.max(points.length, 1);
  const barWidth = Math.max(Math.min(bandWidth * 0.58, MAX_BAR_WIDTH), 3);
  const baselineY = LABEL_BAND + PLOT_HEIGHT;

  const x = (i: number) => Y_AXIS_WIDTH + i * bandWidth + (bandWidth - barWidth) / 2;
  const barHeight = (v: number) => (v / scaleMax) * PLOT_HEIGHT;

  // Weekday names fit for a week; past that, thin the ticks so they never
  // collide rather than rotating them into unreadable diagonals.
  const tickEvery = points.length <= 10 ? 1 : Math.ceil(points.length / 7);

  /**
   * Direct-label the busiest day — but only while that stays one readable
   * mark. Over a quarter a dozen days tie for the maximum and the labels
   * pile into each other, so past two the axis, the tooltip and the table
   * carry the number instead.
   */
  const labelPeaks = peakCount > 0 && peakCount <= 2 && bandWidth >= 28;

  const active = activeIndex === null ? null : points[activeIndex];

  return (
    <div className={cn("w-full", className)}>
      <div className="mb-3 flex items-center justify-between gap-3">
        <p className="text-2xs font-medium uppercase tracking-[0.1em] text-subtle">
          {seriesLabel} per day
        </p>
        <button
          type="button"
          onClick={() => setShowTable((v) => !v)}
          className="tap-h press inline-flex items-center gap-1.5 rounded-md border border-input px-2.5 py-1 text-xs font-medium text-muted-foreground hover:bg-secondary/60 hover:text-foreground"
        >
          {showTable ? (
            <>
              <BarChart3 className="h-3.5 w-3.5" strokeWidth={1.75} /> Show chart
            </>
          ) : (
            <>
              <Table2 className="h-3.5 w-3.5" strokeWidth={1.75} /> Show numbers
            </>
          )}
        </button>
      </div>

      {showTable ? (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <caption className="sr-only">{seriesLabel} and messages sent, by day</caption>
            <thead>
              <tr className="border-b border-border text-left">
                <th scope="col" className="py-2 pr-4 text-2xs font-semibold uppercase tracking-[0.1em] text-subtle">
                  Day
                </th>
                <th scope="col" className="py-2 pr-4 text-right text-2xs font-semibold uppercase tracking-[0.1em] text-subtle">
                  {seriesLabel}
                </th>
                <th scope="col" className="py-2 text-right text-2xs font-semibold uppercase tracking-[0.1em] text-subtle">
                  Messages
                </th>
              </tr>
            </thead>
            <tbody>
              {points.map((point) => (
                <tr key={point.date} className="border-b border-border/70 last:border-0">
                  <td className="py-2 pr-4 text-muted-foreground">{fullDayLabel(point.date)}</td>
                  <td className="py-2 pr-4 text-right font-medium tabular-nums text-foreground">
                    {point.conversations.toLocaleString()}
                  </td>
                  <td className="py-2 text-right tabular-nums text-muted-foreground">
                    {point.messages.toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div ref={containerRef} className="relative w-full">
          {width > 0 && (
            <svg
              width={width}
              height={height}
              viewBox={`0 0 ${width} ${height}`}
              role="img"
              aria-label={`${seriesLabel} per day. ${total.toLocaleString()} in total across ${points.length} days, peaking at ${peakValue.toLocaleString()}.`}
              className="block overflow-visible"
            >
              {/* Recessive chrome: solid hairlines, one step off the surface. */}
              {[0, 0.5, 1].map((fraction) => {
                const y = baselineY - fraction * PLOT_HEIGHT;
                const tickValue = Math.round(scaleMax * fraction);
                return (
                  <g key={fraction}>
                    <line
                      x1={Y_AXIS_WIDTH}
                      x2={width}
                      y1={y}
                      y2={y}
                      stroke="hsl(var(--border))"
                      strokeWidth={1}
                      shapeRendering="crispEdges"
                    />
                    <text
                      x={Y_AXIS_WIDTH - 8}
                      y={y + 3.5}
                      textAnchor="end"
                      className="fill-subtle text-[10px] tabular-nums"
                    >
                      {tickValue}
                    </text>
                  </g>
                );
              })}

              {points.map((point, i) => {
                const value = point.conversations ?? 0;
                const h = barHeight(value);
                const barX = x(i);
                const barY = baselineY - h;
                const isActive = activeIndex === i;
                // Every day that ties the busiest gets the label. Marking one
                // of two identical columns reads as a mistake, not restraint.
                const isPeak = labelPeaks && value === peakValue && value > 0;

                return (
                  <g key={point.date}>
                    {value > 0 && (
                      <path
                        d={columnPath(barX, barY, barWidth, h)}
                        fill="hsl(var(--primary))"
                        opacity={activeIndex === null || isActive ? 1 : 0.55}
                        className="transition-opacity duration-150"
                      />
                    )}

                    {/* Label the extreme only — a number on every column is noise. */}
                    {isPeak && (
                      <text
                        x={barX + barWidth / 2}
                        y={barY - 7}
                        textAnchor="middle"
                        className="fill-foreground text-[11px] font-semibold tabular-nums"
                      >
                        {value.toLocaleString()}
                      </text>
                    )}

                    {i % tickEvery === 0 && (
                      <text
                        x={barX + barWidth / 2}
                        y={baselineY + 16}
                        textAnchor="middle"
                        className="fill-subtle text-[10px]"
                      >
                        {axisTickLabel(point.date, points.length)}
                      </text>
                    )}

                    {/* Hit target is the whole band, never the painted pixels. */}
                    <rect
                      x={Y_AXIS_WIDTH + i * bandWidth}
                      y={LABEL_BAND}
                      width={bandWidth}
                      height={PLOT_HEIGHT}
                      fill="transparent"
                      tabIndex={0}
                      role="button"
                      aria-label={`${fullDayLabel(point.date)}: ${value.toLocaleString()} ${seriesLabel.toLowerCase()}, ${point.messages.toLocaleString()} messages sent`}
                      onMouseEnter={() => setActiveIndex(i)}
                      onMouseLeave={() => setActiveIndex(null)}
                      onFocus={() => setActiveIndex(i)}
                      onBlur={() => setActiveIndex(null)}
                      className="cursor-default outline-none focus-visible:stroke-ring focus-visible:[stroke-width:2]"
                    />
                  </g>
                );
              })}

              <line
                x1={Y_AXIS_WIDTH}
                x2={width}
                y1={baselineY}
                y2={baselineY}
                stroke="hsl(var(--border))"
                strokeWidth={1}
                shapeRendering="crispEdges"
              />
            </svg>
          )}

          {/* Values lead, labels follow. */}
          {active && activeIndex !== null && width > 0 && (
            <div
              role="status"
              className="pointer-events-none absolute z-10 -translate-x-1/2 rounded-md border border-border bg-popover px-2.5 py-1.5 shadow-lifted"
              style={{
                left: Math.min(
                  Math.max(x(activeIndex) + barWidth / 2, 64),
                  Math.max(width - 64, 64)
                ),
                top: Math.max(baselineY - barHeight(active.conversations) - 58, 0),
              }}
            >
              <p className="whitespace-nowrap text-sm font-semibold tabular-nums text-popover-foreground">
                {active.conversations.toLocaleString()}{" "}
                <span className="font-normal text-muted-foreground">
                  {active.conversations === 1 ? "conversation" : "conversations"}
                </span>
              </p>
              <p className="whitespace-nowrap text-2xs text-subtle">{fullDayLabel(active.date)}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
