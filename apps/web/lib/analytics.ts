import type { AnalyticsSummary } from "./api-types";

/**
 * Recovered revenue — the number this whole screen is built around.
 *
 * The buyer does not care how many messages an agent sent. They care that six
 * no-shows got chased back onto the calendar and that it was worth about four
 * thousand dollars. So the dashboard leads with money, and everything else on
 * the page exists to explain that one figure.
 *
 * The agreed API contract does not carry money, and it does not separate
 * bookings from other actions — so until it does, this is an *estimate* and
 * the UI says so out loud, next to the number, with its arithmetic shown.
 * Never present an estimate as a measurement.
 *
 * `AnalyticsSummary` already declares optional `bookings_made` and
 * `revenue_recovered`. When the backend starts sending either, it wins here
 * and the "estimated" caveat disappears on its own.
 */

/**
 * What one recovered appointment is worth. A general-dentistry visit runs
 * roughly $300–$450 depending on what's done in the chair; $375 is the middle
 * of that and is what the pricing model assumes. This is a per-business
 * number and belongs in organization settings the day we have a field for it.
 */
export const ASSUMED_VALUE_PER_BOOKING = 375;

export interface RecoveredRevenue {
  /** Whole dollars. */
  amount: number;
  /** The count the amount was derived from. */
  bookings: number;
  /** True when we multiplied rather than measured. */
  isEstimate: boolean;
}

export function recoveredRevenue(summary: AnalyticsSummary): RecoveredRevenue {
  const bookings = summary.bookings_made ?? summary.actions_taken ?? 0;

  if (typeof summary.revenue_recovered === "number") {
    return { amount: summary.revenue_recovered, bookings, isEstimate: false };
  }
  return { amount: bookings * ASSUMED_VALUE_PER_BOOKING, bookings, isEstimate: true };
}

/**
 * Money, rounded to the nearest hundred and prefixed with a "~" by the caller.
 * Precision it hasn't earned would be a lie: an estimate written as $4,125
 * claims an accuracy the arithmetic does not have.
 */
export function formatEstimatedMoney(amount: number): string {
  const rounded = amount >= 1000 ? Math.round(amount / 100) * 100 : Math.round(amount / 10) * 10;
  return `$${rounded.toLocaleString("en-US")}`;
}

export function formatMoney(amount: number): string {
  return `$${Math.round(amount).toLocaleString("en-US")}`;
}

/** "This week" reads better than "the last 7 days" to a person. */
export function rangeLabel(days: number): string {
  if (days <= 1) return "today";
  if (days === 7) return "this week";
  if (days === 30) return "this month";
  return `the last ${days} days`;
}

export function rangeLabelCapitalized(days: number): string {
  const label = rangeLabel(days);
  return label.charAt(0).toUpperCase() + label.slice(1);
}

/** Short weekday + day-of-month for an axis tick, from a `YYYY-MM-DD` string. */
export function parseDay(date: string): Date | null {
  const parsed = new Date(`${date}T00:00:00`);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

export function axisTickLabel(date: string, totalPoints: number): string {
  const parsed = parseDay(date);
  if (!parsed) return "";
  // A week fits weekday names; longer ranges only have room for the date.
  return totalPoints <= 10
    ? parsed.toLocaleDateString(undefined, { weekday: "short" })
    : parsed.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function fullDayLabel(date: string): string {
  const parsed = parseDay(date);
  if (!parsed) return date;
  return parsed.toLocaleDateString(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
  });
}
