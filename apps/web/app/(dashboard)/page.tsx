"use client";

import * as React from "react";
import Link from "next/link";
import { ArrowRight, BookOpen, Plug } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { useApprovals } from "@/lib/approvals-context";
import { AGENTS } from "@/lib/agents";
import { api } from "@/lib/api-client";
import type { AuditLogEntry } from "@/lib/api-types";
import { formatRelativeTime } from "@/lib/utils";
import { ApprovalCard } from "@/components/approvals/approval-card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { PageBody, Reveal, RevealGroup, RevealItem } from "@/components/layout/page-shell";

/** An agent counts as "working" if it did something in the last 30 minutes. */
const ACTIVE_WINDOW_MS = 30 * 60 * 1000;
const RECENT_COUNT = 5;
const ATTENTION_COUNT = 3;

function greetingFor(date: Date): string {
  const hour = date.getHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

/**
 * "Work": the home screen. It answers three questions in order: what needs me,
 * what is happening, and what can I ask for. Everything on it comes from the
 * real approvals queue and Activity feed; if either is unreachable the section
 * simply stays quiet rather than inventing work that did not happen.
 */
export default function DashboardHomePage() {
  const { organization, user } = useAuth();
  const { pending, count, canReview, isLoading: approvalsLoading } = useApprovals();
  const [entries, setEntries] = React.useState<AuditLogEntry[]>([]);
  const [activityLoaded, setActivityLoaded] = React.useState(false);
  // Computed after mount so the server and client never disagree about the hour.
  const [greeting, setGreeting] = React.useState("Welcome");

  React.useEffect(() => {
    setGreeting(greetingFor(new Date()));
  }, []);

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
    return new Set(
      entries
        .filter((e) => {
          const t = new Date(e.created_at).getTime();
          return !Number.isNaN(t) && t >= cutoff;
        })
        .map((e) => e.agent_slug)
    );
  }, [entries]);

  const firstName = user?.full_name?.trim().split(/\s+/)[0];
  const recent = entries.slice(0, RECENT_COUNT);

  return (
    <PageBody width="wide">
      <Reveal className="mb-8">
        <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
          {organization?.name ?? "Your workspace"}
        </p>
        <h1 className="mt-2 font-display text-4xl font-semibold tracking-[-0.03em] text-foreground">
          {greeting}
          {firstName ? `, ${firstName}.` : "."}
        </h1>
        <p className="mt-2.5 max-w-xl text-sm leading-relaxed text-muted-foreground">
          Your business, coordinated. You stay in control.
        </p>
      </Reveal>

      {/* The one deliberate signal on the page: the way in. */}
      <Reveal delay={0.04}>
        <div className="flex flex-col gap-4 rounded-lg border border-border bg-card p-5 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0">
            <h2 className="font-display text-lg font-semibold tracking-[-0.015em] text-foreground">
              Tell Mesnium what needs doing
            </h2>
            <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
              Not sure which agent to ask? Start with your Chief of Staff. It brings in the right specialist and
              returns one clear answer.
            </p>
          </div>
          <Button asChild className="shrink-0">
            <Link href="/chief-of-staff">
              Start a conversation
              <ArrowRight className="h-4 w-4" strokeWidth={1.5} />
            </Link>
          </Button>
        </div>
      </Reveal>

      {canReview && (
        <section className="mt-10" aria-labelledby="attention-heading">
          <div className="mb-4 flex items-end justify-between gap-4">
            <h2
              id="attention-heading"
              className="font-display text-xl font-semibold tracking-[-0.02em] text-foreground"
            >
              Needs your attention
            </h2>
            {count > ATTENTION_COUNT && (
              <p className="text-xs text-muted-foreground">
                Showing {ATTENTION_COUNT} of {count}. Open Approvals above for the rest.
              </p>
            )}
          </div>
          {approvalsLoading ? (
            <Skeleton className="h-28 w-full" />
          ) : pending.length > 0 ? (
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              {pending.slice(0, ATTENTION_COUNT).map((approval) => (
                <ApprovalCard key={approval.id} approval={approval} />
              ))}
            </div>
          ) : (
            <p className="rounded-lg border border-dashed border-border px-5 py-4 text-sm text-muted-foreground">
              Nothing needs your attention. Anything an agent wants to send or change will wait here for your
              approval first.
            </p>
          )}
        </section>
      )}

      <div className="mb-4 mt-10 flex items-end justify-between gap-4">
        <h2 className="font-display text-xl font-semibold tracking-[-0.02em] text-foreground">Your agents</h2>
        {activityLoaded && activeSlugs.size > 0 && (
          <p className="text-xs text-muted-foreground">
            {activeSlugs.size} active in the last half hour
          </p>
        )}
      </div>

      <RevealGroup className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {AGENTS.filter((agent) => agent.slug !== "chief-of-staff").map((agent) => {
          const Icon = agent.icon;
          const isActive = activeSlugs.has(agent.slug);
          return (
            <RevealItem key={agent.slug}>
              <Link
                href={`/${agent.slug}`}
                className="press group flex h-full flex-col rounded-lg border border-border bg-card p-5 hover:border-foreground/25"
              >
                <span className="flex h-10 w-10 items-center justify-center rounded-md bg-secondary text-foreground ring-1 ring-inset ring-border">
                  <Icon className="h-5 w-5" strokeWidth={1.5} />
                </span>
                <h3 className="mt-4 font-display text-lg font-semibold leading-tight tracking-[-0.015em] text-foreground">
                  {agent.displayName}
                </h3>
                <p className="mt-1.5 flex-1 text-sm leading-relaxed text-muted-foreground">{agent.tagline}</p>
                <span className="mt-4 flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
                  <span className={isActive ? "h-1.5 w-1.5 rounded-full bg-success" : "h-1.5 w-1.5 rounded-full bg-subtle"} />
                  {isActive ? "Active" : "Ready"}
                </span>
              </Link>
            </RevealItem>
          );
        })}
      </RevealGroup>

      <section className="mt-10" aria-labelledby="recent-heading">
        <div className="mb-4 flex items-end justify-between gap-4">
          <h2
            id="recent-heading"
            className="font-display text-xl font-semibold tracking-[-0.02em] text-foreground"
          >
            Recent activity
          </h2>
          <Link href="/activity" className="text-sm font-medium text-primary-ink hover:underline">
            View all
          </Link>
        </div>
        <div className="rounded-lg border border-border bg-card">
          {!activityLoaded ? (
            <div className="flex flex-col gap-3 p-5">
              <Skeleton className="h-3 w-3/4" />
              <Skeleton className="h-3 w-2/3" />
              <Skeleton className="h-3 w-1/2" />
            </div>
          ) : recent.length > 0 ? (
            <ul className="divide-y divide-border">
              {recent.map((entry) => (
                <li key={entry.id} className="flex items-baseline justify-between gap-4 px-5 py-3 text-sm">
                  <span className="min-w-0 truncate text-foreground">
                    {entry.summary ?? entry.action.replace(/_/g, " ")}
                    <span className="text-muted-foreground">
                      {" · "}
                      {AGENTS.find((a) => a.slug === entry.agent_slug)?.displayName ?? "Mesnium"}
                    </span>
                  </span>
                  <span className="shrink-0 font-mono text-[11px] text-muted-foreground">
                    {formatRelativeTime(entry.created_at)}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="px-5 py-4 text-sm text-muted-foreground">
              No work here yet. Tell Mesnium what needs doing, and every action will be recorded in Activity.
            </p>
          )}
        </div>
      </section>

      <RevealGroup className="mt-10 grid grid-cols-1 gap-4 sm:grid-cols-2" delay={0.05}>
        <RevealItem>
          <Link
            href="/knowledge"
            className="press group flex h-full items-start gap-4 rounded-lg border border-border bg-card p-5 hover:border-foreground/25"
          >
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-secondary text-foreground ring-1 ring-inset ring-border">
              <BookOpen className="h-5 w-5" strokeWidth={1.5} />
            </span>
            <span className="min-w-0">
              <span className="block font-display text-base font-semibold text-foreground">Knowledge</span>
              <span className="mt-1 block text-sm leading-relaxed text-muted-foreground">
                Add your price list, policies or service menu so every agent answers the way you would.
              </span>
            </span>
          </Link>
        </RevealItem>

        <RevealItem>
          <Link
            href="/settings/integrations"
            className="press group flex h-full items-start gap-4 rounded-lg border border-border bg-card p-5 hover:border-foreground/25"
          >
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-secondary text-foreground ring-1 ring-inset ring-border">
              <Plug className="h-5 w-5" strokeWidth={1.5} />
            </span>
            <span className="min-w-0">
              <span className="block font-display text-base font-semibold text-foreground">Connections</span>
              <span className="mt-1 block text-sm leading-relaxed text-muted-foreground">
                Connect your calendar, inbox and store. You see what each one allows before you turn it on.
              </span>
            </span>
          </Link>
        </RevealItem>
      </RevealGroup>
    </PageBody>
  );
}
