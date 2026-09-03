"use client";

import * as React from "react";
import Link from "next/link";
import { ArrowUpRight, Info, RefreshCw } from "lucide-react";
import { api } from "@/lib/api-client";
import type { AnalyticsSummary } from "@/lib/api-types";
import {
  ASSUMED_VALUE_PER_BOOKING,
  formatEstimatedMoney,
  formatMoney,
  rangeLabel,
  rangeLabelCapitalized,
  recoveredRevenue,
} from "@/lib/analytics";
import { cn, errorMessage } from "@/lib/utils";
import { PageBody, PageHeader, Reveal } from "@/components/layout/page-shell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { StatTile } from "@/components/analytics/stat-tile";
import { TrendChart } from "@/components/analytics/trend-chart";

/**
 * Results.
 *
 * A business owner does not open this page to audit message volume. They open
 * it to find out whether the thing they are paying for made them money. So
 * the page leads with one figure — revenue recovered — and every other number
 * on it is there to make that figure believable: how many conversations it
 * came from, whether the trend is real or a single good day, and which agent
 * is doing the work.
 *
 * With no backend reachable this page still renders: a sentence explaining
 * what could not be loaded, and a way to try again.
 */

const RANGES = [
  { days: 7, label: "Last 7 days" },
  { days: 30, label: "Last 30 days" },
  { days: 90, label: "Last 90 days" },
];

function HeroSkeleton() {
  return (
    <Card className="p-6 sm:p-7">
      <Skeleton className="h-3 w-32" />
      <Skeleton className="mt-4 h-12 w-64 max-w-full" />
      <Skeleton className="mt-4 h-3.5 w-full max-w-lg" />
      <Skeleton className="mt-2 h-3.5 w-2/3 max-w-sm" />
    </Card>
  );
}

export default function AnalyticsPage() {
  const [days, setDays] = React.useState(7);
  const [summary, setSummary] = React.useState<AnalyticsSummary | null>(null);
  const [isLoading, setIsLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  const load = React.useCallback(async (rangeDays: number) => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await api.analytics.summary(rangeDays);
      setSummary(data);
    } catch (err) {
      setError(
        errorMessage(
          err,
          "We couldn't pull your results just now. Nothing is lost — your agents keep working and the numbers will be here when the connection comes back."
        )
      );
    } finally {
      setIsLoading(false);
    }
  }, []);

  React.useEffect(() => {
    load(days);
  }, [days, load]);

  const daily = summary?.daily ?? [];
  const hasAnyActivity =
    !!summary &&
    (summary.conversations_handled > 0 ||
      summary.messages_sent > 0 ||
      daily.some((d) => d.conversations > 0));

  const revenue = summary ? recoveredRevenue(summary) : null;
  // A refetch holds the previous render rather than flashing a skeleton.
  const isRefetching = isLoading && !!summary;

  return (
    <PageBody width="wide">
      <PageHeader
        title="Results"
        description="What your agents actually brought in — the money they recovered, the conversations behind it, and who did the work."
      />

      {/* One filter row, above everything it scopes. */}
      <Reveal className="mb-6 flex flex-wrap items-center gap-1.5">
        {RANGES.map((range) => (
          <button
            key={range.days}
            type="button"
            onClick={() => setDays(range.days)}
            aria-pressed={days === range.days}
            className={cn(
              "tap-h press inline-flex items-center rounded-full border px-3.5 py-1.5 text-xs font-medium",
              days === range.days
                ? "border-primary bg-primary/10 text-primary"
                : "border-border bg-card text-muted-foreground hover:text-foreground"
            )}
          >
            {range.label}
          </button>
        ))}
      </Reveal>

      {error && !summary ? (
        <Card>
          <CardContent className="px-6 py-10 text-center">
            <p className="mx-auto max-w-md text-sm leading-relaxed text-muted-foreground">{error}</p>
            <Button variant="secondary" className="mt-5" onClick={() => load(days)}>
              <RefreshCw className="h-4 w-4" strokeWidth={1.75} />
              Try again
            </Button>
          </CardContent>
        </Card>
      ) : isLoading && !summary ? (
        <div className="flex flex-col gap-5">
          <HeroSkeleton />
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-[104px] rounded-lg" />
            ))}
          </div>
          <Skeleton className="h-[300px] rounded-lg" />
          <span className="sr-only" role="status">
            Loading your results
          </span>
        </div>
      ) : summary && revenue ? (
        <div
          className={cn(
            "flex flex-col gap-5 transition-opacity duration-200",
            isRefetching && "pointer-events-none opacity-60"
          )}
        >
          {/* The hero figure. Exactly one per view. */}
          <Reveal>
            <Card className="overflow-hidden">
              <div className="p-6 sm:p-7">
                <p className="text-2xs font-medium uppercase tracking-[0.1em] text-subtle">
                  {rangeLabelCapitalized(days)}
                </p>

                {hasAnyActivity ? (
                  <>
                    <p className="mt-2 font-display text-4xl font-semibold tracking-[-0.03em] text-foreground sm:text-5xl">
                      {revenue.isEstimate
                        ? `~${formatEstimatedMoney(revenue.amount)}`
                        : formatMoney(revenue.amount)}{" "}
                      <span className="text-2xl font-medium text-muted-foreground sm:text-3xl">
                        recovered
                      </span>
                    </p>
                    <p className="mt-3 max-w-2xl text-sm leading-relaxed text-muted-foreground">
                      Your agents handled{" "}
                      <span className="font-semibold text-foreground">
                        {summary.conversations_handled.toLocaleString()}
                      </span>{" "}
                      {summary.conversations_handled === 1 ? "conversation" : "conversations"}{" "}
                      {rangeLabel(days)} and got{" "}
                      <span className="font-semibold text-foreground">
                        {revenue.bookings.toLocaleString()}
                      </span>{" "}
                      {revenue.bookings === 1 ? "appointment" : "appointments"} onto the calendar
                      that would otherwise have needed someone at the front desk.
                    </p>
                    {revenue.isEstimate && (
                      <p className="mt-3 flex max-w-2xl items-start gap-2 text-xs leading-relaxed text-subtle">
                        <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" strokeWidth={1.75} />
                        <span>
                          An estimate — {revenue.bookings.toLocaleString()}{" "}
                          {revenue.bookings === 1 ? "appointment" : "appointments"} at an average
                          visit value of {formatMoney(ASSUMED_VALUE_PER_BOOKING)}. Tell us what a
                          visit is really worth to you and we&rsquo;ll use your number instead.
                        </span>
                      </p>
                    )}
                  </>
                ) : (
                  <>
                    <p className="mt-2 font-display text-4xl font-semibold tracking-[-0.03em] text-foreground sm:text-5xl">
                      Nothing yet
                    </p>
                    <p className="mt-3 max-w-2xl text-sm leading-relaxed text-muted-foreground">
                      Your agents haven&rsquo;t handled anything {rangeLabel(days)}. Connect your
                      calendar and phone line and this is where you&rsquo;ll see the appointments
                      they save and what those appointments are worth.
                    </p>
                    <Link
                      href="/settings/integrations"
                      className="press mt-4 inline-flex items-center gap-1 text-sm font-semibold text-primary hover:underline"
                    >
                      Connect an account
                      <ArrowUpRight className="h-3.5 w-3.5" strokeWidth={2} />
                    </Link>
                  </>
                )}
              </div>
            </Card>
          </Reveal>

          <Reveal className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <StatTile
              label="Conversations"
              value={summary.conversations_handled.toLocaleString()}
              note={`Handled start to finish ${rangeLabel(days)}.`}
            />
            <StatTile
              label="Appointments"
              value={revenue.bookings.toLocaleString()}
              note="Booked, moved, or rescued from a no-show."
            />
            <StatTile
              label="Replies sent"
              value={summary.messages_sent.toLocaleString()}
              note="Calls answered, texts and emails written."
            />
            <StatTile
              label="Waiting on you"
              value={summary.approvals_pending.toLocaleString()}
              note={
                summary.approvals_pending > 0
                  ? "Your agents are holding these until you say yes."
                  : summary.approvals_approved > 0
                    ? `Nothing held up — you approved ${summary.approvals_approved.toLocaleString()} ${rangeLabel(days)}.`
                    : "Nothing is waiting on your say-so."
              }
            />
          </Reveal>

          <Reveal>
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">How {rangeLabel(days)} went</CardTitle>
              </CardHeader>
              <CardContent>
                {daily.length === 0 || daily.every((d) => d.conversations === 0) ? (
                  <div className="rounded-md border border-dashed border-border px-4 py-10 text-center">
                    <p className="text-sm leading-relaxed text-muted-foreground">
                      No day-by-day figures yet. Once your agents have been running for a few days,
                      you&rsquo;ll be able to see your busiest days at a glance here.
                    </p>
                  </div>
                ) : (
                  <TrendChart points={daily} />
                )}
              </CardContent>
            </Card>
          </Reveal>

          <Reveal>
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Which agent did the work</CardTitle>
              </CardHeader>
              <CardContent>
                <AgentBreakdown summary={summary} />
              </CardContent>
            </Card>
          </Reveal>

          {error && (
            <p className="text-xs leading-relaxed text-muted-foreground">
              These figures may be a little out of date — {error}
            </p>
          )}
        </div>
      ) : null}
    </PageBody>
  );
}

/**
 * One series, one hue: the bar length is the only thing carrying magnitude, so
 * a value ramp here would double-encode length as colour and tell the reader
 * nothing new.
 */
function AgentBreakdown({ summary }: { summary: AnalyticsSummary }) {
  const rows = [...(summary.by_agent ?? [])]
    .filter((row) => row.conversations > 0 || row.messages > 0 || row.actions > 0)
    .sort((a, b) => b.conversations - a.conversations);

  if (rows.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-border px-4 py-10 text-center">
        <p className="mx-auto max-w-md text-sm leading-relaxed text-muted-foreground">
          None of your agents have picked anything up in this period. As soon as one does, you&rsquo;ll
          see exactly how much of the load it carried.
        </p>
      </div>
    );
  }

  const max = Math.max(...rows.map((r) => r.conversations), 1);

  return (
    <ul className="flex flex-col gap-4">
      {rows.map((row) => (
        <li key={row.agent_slug}>
          <div className="flex items-baseline justify-between gap-4">
            <p className="truncate text-sm font-medium text-foreground">{row.display_name}</p>
            <p className="shrink-0 text-sm font-semibold tabular-nums text-foreground">
              {row.conversations.toLocaleString()}
              <span className="ml-1.5 text-xs font-normal text-subtle">
                {row.conversations === 1 ? "conversation" : "conversations"}
              </span>
            </p>
          </div>
          <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-primary/[0.08]">
            <div
              className="h-full rounded-full bg-primary transition-[width] duration-500 ease-physical"
              style={{ width: `${Math.max((row.conversations / max) * 100, row.conversations > 0 ? 3 : 0)}%` }}
            />
          </div>
          <p className="mt-1.5 text-xs text-muted-foreground">
            {row.actions.toLocaleString()} {row.actions === 1 ? "thing done" : "things done"} ·{" "}
            {row.messages.toLocaleString()} {row.messages === 1 ? "reply" : "replies"} sent
          </p>
        </li>
      ))}
    </ul>
  );
}
