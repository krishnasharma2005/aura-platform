"use client";

import * as React from "react";
import Link from "next/link";
import { ArrowUpRight, BookOpen, ListChecks, Users } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { AGENTS } from "@/lib/agents";
import { api } from "@/lib/api-client";
import type { AuditLogEntry } from "@/lib/api-types";
import { formatRelativeTime } from "@/lib/utils";
import { RuntimeGraph } from "@/components/runtime/runtime-graph";
import { CardShell } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { PageBody, Reveal, RevealGroup, RevealItem } from "@/components/layout/page-shell";
import { cn } from "@/lib/utils";

/** An agent counts as "working" if it did something in the last 30 minutes. */
const ACTIVE_WINDOW_MS = 30 * 60 * 1000;

export default function DashboardHomePage() {
  const { organization, user } = useAuth();
  const [entries, setEntries] = React.useState<AuditLogEntry[]>([]);
  const [activityLoaded, setActivityLoaded] = React.useState(false);
  const [focusedSlug, setFocusedSlug] = React.useState<string | null>(null);

  /**
   * The graph's "working now" state is driven by the real Activity feed, not
   * a timer — a lit node means that agent actually did something. If the feed
   * is unreachable the graph simply shows no activity; it never breaks the
   * page and never invents work that did not happen.
   */
  React.useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const data = await api.auditLogs.list();
        if (!cancelled) setEntries(data);
      } catch {
        if (!cancelled) setEntries([]);
      } finally {
        if (!cancelled) setActivityLoaded(true);
      }
    }
    load();
    const id = window.setInterval(load, 45_000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  const activeSlugs = React.useMemo(() => {
    const cutoff = Date.now() - ACTIVE_WINDOW_MS;
    return Array.from(
      new Set(
        entries
          .filter((e) => {
            const t = new Date(e.created_at).getTime();
            return !Number.isNaN(t) && t >= cutoff;
          })
          .map((e) => e.agent_slug)
      )
    );
  }, [entries]);

  const firstName = user?.full_name?.trim().split(/\s+/)[0];
  const latest = entries[0];

  return (
    <PageBody width="wide">
      <Reveal className="mb-6">
        <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
          {organization?.name ?? "Your workspace"}
        </p>
        <h1 className="mt-2 font-display text-4xl font-semibold tracking-[-0.03em] text-foreground">
          Six agents.{" "}
          <span className="text-primary">One shared brain.</span>
        </h1>
        <p className="mt-2.5 max-w-xl text-sm leading-relaxed text-muted-foreground">
          {firstName ? `${firstName}, everything ` : "Everything "}
          your agents learn, read, and connect to is shared between them. Explore how they fit
          together, or open one to try it.
        </p>
      </Reveal>

      {/*
        The signature surface. Nested enclosure — outer tray, inner plate — so
        it reads as a piece of instrumentation seated on the page rather than
        another card in the stack.
      */}
      <Reveal delay={0.06}>
        <CardShell>
          <div className="p-4 sm:p-5">
            <RuntimeGraph
              activeSlugs={activeSlugs}
              focusedSlug={focusedSlug}
              onFocusAgent={setFocusedSlug}
            />
          </div>
        </CardShell>
      </Reveal>

      {/*
        Not a seventh card in the grid below — the grid is deliberately "your
        six agents." This is the other way in: one chat that figures out
        which of them to consult, so a new owner never has to learn who
        handles what.
      */}
      <Reveal delay={0.08}>
        <Link
          href="/chief-of-staff"
          className="press group mt-6 flex items-center gap-4 rounded-lg border border-primary/25 bg-primary/[0.05] p-5 shadow-card hover:-translate-y-0.5 hover:shadow-lifted"
        >
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <Users className="h-4.5 w-4.5" strokeWidth={1.75} />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block font-display text-base font-semibold text-foreground">
              Ask your Chief of Staff
            </span>
            <span className="mt-1 block text-sm leading-relaxed text-muted-foreground">
              Not sure which agent to ask? Talk to one place — it delegates to the right specialist
              and brings back the answer.
            </span>
          </span>
          <ArrowUpRight
            className="h-4 w-4 shrink-0 text-subtle transition-transform duration-200 ease-physical group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-primary"
            strokeWidth={2}
          />
        </Link>
      </Reveal>

      <div className="mt-10 mb-4 flex items-end justify-between gap-4">
        <h2 className="font-display text-xl font-semibold tracking-[-0.02em] text-foreground">
          Your agents
        </h2>
        {activityLoaded && activeSlugs.length > 0 && (
          <p className="text-xs text-muted-foreground">
            <span className="mr-1.5 inline-block h-1.5 w-1.5 rounded-full bg-success align-middle" />
            {activeSlugs.length} working in the last half hour
          </p>
        )}
      </div>

      <RevealGroup className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {AGENTS.filter((agent) => agent.slug !== "chief-of-staff").map((agent) => {
          const Icon = agent.icon;
          const isActive = activeSlugs.includes(agent.slug);
          const isFocused = focusedSlug === agent.slug;
          return (
            <RevealItem key={agent.slug}>
              <Link
                href={`/${agent.slug}`}
                /*
                 * Hovering a card lights that agent's node in the graph above,
                 * and hovering a node in the graph lights this card. The two
                 * are one control, which is how you learn that the list and
                 * the diagram describe the same six things.
                 */
                onMouseEnter={() => setFocusedSlug(agent.slug)}
                onMouseLeave={() => setFocusedSlug(null)}
                onFocus={() => setFocusedSlug(agent.slug)}
                onBlur={() => setFocusedSlug(null)}
                className={cn(
                  "press group flex h-full flex-col rounded-lg border bg-card p-5 shadow-card",
                  "hover:-translate-y-0.5 hover:shadow-lifted",
                  isFocused ? "border-primary/40 shadow-lifted" : "border-border"
                )}
              >
                <div className="flex items-start justify-between">
                  <span
                    className={cn(
                      "flex h-10 w-10 items-center justify-center rounded-md transition-colors duration-200 ease-physical",
                      isFocused
                        ? "bg-primary text-primary-foreground"
                        : "bg-primary/[0.08] text-primary ring-1 ring-inset ring-primary/12"
                    )}
                  >
                    <Icon className="h-4.5 w-4.5" strokeWidth={1.75} />
                  </span>
                  <ArrowUpRight
                    className="h-4 w-4 text-subtle transition-transform duration-200 ease-physical group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-primary"
                    strokeWidth={2}
                  />
                </div>

                <h3 className="mt-4 font-display text-lg font-semibold leading-tight tracking-[-0.015em] text-foreground">
                  {agent.displayName}
                </h3>
                <p className="mt-1.5 flex-1 text-sm leading-relaxed text-muted-foreground">
                  {agent.tagline}
                </p>

                <span className="mt-4 flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
                  <span
                    className={cn(
                      "h-1.5 w-1.5 rounded-full",
                      isActive ? "animate-breathe bg-success" : "bg-subtle"
                    )}
                  />
                  {isActive ? "Working now" : "Ready"}
                </span>
              </Link>
            </RevealItem>
          );
        })}
      </RevealGroup>

      <RevealGroup className="mt-10 grid grid-cols-1 gap-4 sm:grid-cols-2" delay={0.05}>
        <RevealItem>
          <Link
            href="/knowledge"
            className="press group flex h-full items-start gap-4 rounded-lg border border-border bg-card p-5 shadow-card hover:-translate-y-0.5 hover:shadow-lifted"
          >
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-secondary text-foreground ring-1 ring-inset ring-border">
              <BookOpen className="h-4.5 w-4.5" strokeWidth={1.75} />
            </span>
            <span className="min-w-0">
              <span className="block font-display text-base font-semibold text-foreground">
                Knowledge
              </span>
              <span className="mt-1 block text-sm leading-relaxed text-muted-foreground">
                Add your price list, policies, or service menu so every agent answers the same way
                you would.
              </span>
            </span>
          </Link>
        </RevealItem>

        <RevealItem>
          <Link
            href="/activity"
            className="press group flex h-full items-start gap-4 rounded-lg border border-border bg-card p-5 shadow-card hover:-translate-y-0.5 hover:shadow-lifted"
          >
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-secondary text-foreground ring-1 ring-inset ring-border">
              <ListChecks className="h-4.5 w-4.5" strokeWidth={1.75} />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block font-display text-base font-semibold text-foreground">
                Activity
              </span>
              {!activityLoaded ? (
                <Skeleton className="mt-2 h-3 w-3/4" />
              ) : latest ? (
                <span className="mt-1 block truncate text-sm text-muted-foreground">
                  Latest: {latest.summary ?? latest.action.replace(/_/g, " ")} ·{" "}
                  {formatRelativeTime(latest.created_at)}
                </span>
              ) : (
                <span className="mt-1 block text-sm leading-relaxed text-muted-foreground">
                  Every booking, reply, and action your agents take gets logged here in plain
                  language.
                </span>
              )}
            </span>
          </Link>
        </RevealItem>
      </RevealGroup>
    </PageBody>
  );
}
