"use client";

import * as React from "react";
import Link from "next/link";
import { ArrowUpRight, RefreshCw } from "lucide-react";
import { api } from "@/lib/api-client";
import type { Workflow } from "@/lib/api-types";
import { errorMessage } from "@/lib/utils";
import { PageBody, PageHeader, Reveal } from "@/components/layout/page-shell";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { WorkflowCard } from "@/components/workflows/workflow-card";

/**
 * Workflows — the things that happen without anyone asking.
 *
 * Written for an owner, not an operator: each one is a sentence about their
 * business ("this chases people who don't show up"), a switch, and an honest
 * record of what it has actually done. No triggers, no steps-as-code, no
 * status codes anywhere on the page.
 */

function WorkflowSkeleton() {
  return (
    <Card>
      <div className="flex items-start justify-between gap-4 p-5">
        <div className="min-w-0 flex-1">
          <Skeleton className="h-4 w-52 max-w-full" />
          <Skeleton className="mt-3 h-3 w-full max-w-md" />
          <Skeleton className="mt-2 h-3 w-2/3 max-w-xs" />
        </div>
        <Skeleton className="h-6 w-11 shrink-0 rounded-full" />
      </div>
      <div className="border-t border-border px-5 py-3.5">
        <Skeleton className="h-3 w-44" />
      </div>
    </Card>
  );
}

export default function WorkflowsPage() {
  const [workflows, setWorkflows] = React.useState<Workflow[] | null>(null);
  const [isLoading, setIsLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  const load = React.useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await api.workflows.list();
      setWorkflows(data ?? []);
    } catch (err) {
      setError(
        errorMessage(
          err,
          "We couldn't load your workflows just now. Anything already switched on keeps running — this page just can't show it at the moment."
        )
      );
    } finally {
      setIsLoading(false);
    }
  }, []);

  React.useEffect(() => {
    load();
  }, [load]);

  const handleChange = React.useCallback((next: Workflow) => {
    setWorkflows((current) =>
      (current ?? []).map((workflow) => (workflow.id === next.id ? next : workflow))
    );
  }, []);

  const onCount = (workflows ?? []).filter((w) => w.enabled).length;

  return (
    <PageBody width="medium">
      <PageHeader
        title="Workflows"
        description="Things your agents do on their own, without you asking. Switch any of them off and they stop immediately."
      />

      {isLoading && !workflows ? (
        <div className="flex flex-col gap-4">
          {Array.from({ length: 3 }).map((_, i) => (
            <WorkflowSkeleton key={i} />
          ))}
          <span className="sr-only" role="status">
            Loading your workflows
          </span>
        </div>
      ) : error && !workflows ? (
        <Card>
          <CardContent className="px-6 py-10 text-center">
            <p className="mx-auto max-w-md text-sm leading-relaxed text-muted-foreground">{error}</p>
            <Button variant="secondary" className="mt-5" onClick={load}>
              <RefreshCw className="h-4 w-4" strokeWidth={1.75} />
              Try again
            </Button>
          </CardContent>
        </Card>
      ) : workflows && workflows.length === 0 ? (
        <Card>
          <CardContent className="px-6 py-12 text-center">
            <p className="font-display text-lg font-semibold text-foreground">
              No workflows set up yet
            </p>
            <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-muted-foreground">
              Once your calendar and phone line are connected, we&rsquo;ll suggest a few to start
              with — chasing no-shows, following up on missed calls, and reminding people the day
              before a visit.
            </p>
            <Link
              href="/settings/integrations"
              className="press mt-5 inline-flex items-center gap-1 text-sm font-semibold text-primary hover:underline"
            >
              Connect an account
              <ArrowUpRight className="h-3.5 w-3.5" strokeWidth={2} />
            </Link>
          </CardContent>
        </Card>
      ) : workflows ? (
        <>
          <Reveal className="mb-4">
            <p className="text-sm text-muted-foreground">
              <span className="font-semibold text-foreground">{onCount}</span> of{" "}
              {workflows.length} switched on.
            </p>
          </Reveal>
          <div className="flex flex-col gap-4">
            {workflows.map((workflow) => (
              <WorkflowCard key={workflow.id} workflow={workflow} onChange={handleChange} />
            ))}
          </div>
        </>
      ) : null}
    </PageBody>
  );
}
