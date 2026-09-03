"use client";

import * as React from "react";
import { AlertCircle, Check, ChevronDown, Clock3, Loader2, X } from "lucide-react";
import { api } from "@/lib/api-client";
import type { Workflow, WorkflowRun, WorkflowStep } from "@/lib/api-types";
import {
  failedStep,
  reliabilitySentence,
  runDuration,
  runStatusLabel,
  stepLabel,
  triggerSentence,
} from "@/lib/workflows";
import { cn, errorMessage, formatRelativeTime } from "@/lib/utils";
import { Card } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/use-toast";

/**
 * One standing automation.
 *
 * Everything on this card is written for someone who has never heard the word
 * "trigger": what it does, when it happens, whether it's on, and what
 * happened the last few times it ran. When a run stops early, the step it
 * stopped on and the reason are what the card leads with — an owner needs to
 * know that the reminder text bounced, not that something returned a 502.
 */

function StepIcon({ status }: { status: WorkflowStep["status"] }) {
  if (status === "failed") {
    return <X className="h-3 w-3 text-destructive" strokeWidth={2.5} aria-hidden="true" />;
  }
  if (status === "running") {
    return (
      <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" strokeWidth={2.5} aria-hidden="true" />
    );
  }
  return <Check className="h-3 w-3 text-success" strokeWidth={2.5} aria-hidden="true" />;
}

function RunRow({ run }: { run: WorkflowRun }) {
  const stopped = failedStep(run);
  const duration = runDuration(run);
  const steps = run.steps ?? [];

  return (
    <li className="py-3.5">
      <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
        <span
          className={cn(
            "inline-flex items-center gap-1.5 text-xs font-semibold",
            run.status === "failed" && "text-destructive",
            run.status === "success" && "text-success",
            run.status === "running" && "text-muted-foreground"
          )}
        >
          {run.status === "failed" ? (
            <AlertCircle className="h-3.5 w-3.5" strokeWidth={2} aria-hidden="true" />
          ) : run.status === "running" ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={2} aria-hidden="true" />
          ) : (
            <Check className="h-3.5 w-3.5" strokeWidth={2.5} aria-hidden="true" />
          )}
          {runStatusLabel(run.status)}
        </span>
        {/*
          `text-subtle` is the right tier for this, but the history panel sits
          on a tinted ground where it measures 4.44:1 in dark — just under AA.
          Muted-foreground is the nearest tier that clears it everywhere.
        */}
        <span className="text-xs text-muted-foreground">
          {formatRelativeTime(run.started_at)}
          {duration ? ` · took ${duration}` : ""}
        </span>
      </div>

      {/*
        A failed run is the only reason anyone opens this list, so it says what
        broke in the first line rather than making the reader scan the steps.
      */}
      {run.status === "failed" && (
        <div className="mt-2 rounded-md border border-destructive/25 bg-destructive/[0.06] px-3 py-2.5">
          <p className="text-xs font-semibold text-foreground">
            {stopped ? `Stopped at: ${stepLabel(stopped)}` : "Stopped before it finished"}
          </p>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
            {stopped?.detail?.trim() ||
              "We don't have a reason on file for this one. If it keeps happening, send us the time it ran and we'll look."}
          </p>
        </div>
      )}

      {steps.length > 0 && (
        <ol className="mt-2.5 flex flex-col gap-1.5">
          {steps.map((step, i) => (
            <li key={`${run.id}-${step.name}-${i}`} className="flex items-start gap-2">
              <span className="mt-[3px] flex h-4 w-4 shrink-0 items-center justify-center">
                <StepIcon status={step.status} />
              </span>
              <span className="min-w-0 text-xs leading-relaxed">
                <span
                  className={cn(
                    "font-medium",
                    step.status === "failed" ? "text-foreground" : "text-muted-foreground"
                  )}
                >
                  {stepLabel(step)}
                </span>
                {step.detail && step.status !== "failed" && (
                  <span className="text-muted-foreground"> — {step.detail}</span>
                )}
              </span>
            </li>
          ))}
        </ol>
      )}
    </li>
  );
}

export function WorkflowCard({
  workflow,
  onChange,
}: {
  workflow: Workflow;
  onChange: (next: Workflow) => void;
}) {
  const { toast } = useToast();
  const [isToggling, setIsToggling] = React.useState(false);
  const [isOpen, setIsOpen] = React.useState(false);
  const [runs, setRuns] = React.useState<WorkflowRun[] | null>(null);
  const [runsError, setRunsError] = React.useState<string | null>(null);
  const [isLoadingRuns, setIsLoadingRuns] = React.useState(false);

  const panelId = `workflow-runs-${workflow.id}`;

  const toggle = async (next: boolean) => {
    if (isToggling) return;
    setIsToggling(true);
    // Optimistic: the switch moves under the thumb immediately and only rolls
    // back if the server disagrees. A control that lags reads as broken.
    const previous = workflow;
    onChange({ ...workflow, enabled: next });
    try {
      const updated = next
        ? await api.workflows.enable(workflow.id)
        : await api.workflows.disable(workflow.id);
      onChange(updated ?? { ...workflow, enabled: next });
    } catch (err) {
      onChange(previous);
      toast({
        variant: "destructive",
        title: next ? "Couldn't turn that on" : "Couldn't turn that off",
        description: errorMessage(
          err,
          "We couldn't save that change. Nothing has changed on your account — try again in a moment."
        ),
      });
    } finally {
      setIsToggling(false);
    }
  };

  const loadRuns = React.useCallback(async () => {
    setIsLoadingRuns(true);
    setRunsError(null);
    try {
      const data = await api.workflows.runs(workflow.id);
      setRuns(data ?? []);
    } catch (err) {
      setRunsError(
        errorMessage(err, "We couldn't load this one's history just now. Try again in a moment.")
      );
    } finally {
      setIsLoadingRuns(false);
    }
  }, [workflow.id]);

  const openPanel = () => {
    const next = !isOpen;
    setIsOpen(next);
    if (next && runs === null && !isLoadingRuns) loadRuns();
  };

  const hasRun = (workflow.run_count ?? 0) > 0 || !!workflow.last_run_at;

  return (
    <Card className="overflow-hidden">
      <div className="flex items-start justify-between gap-4 p-5">
        <div className="min-w-0">
          <h3 className="font-display text-base font-semibold tracking-[-0.01em] text-foreground">
            {workflow.name}
          </h3>
          <p className="mt-1.5 max-w-xl text-sm leading-relaxed text-muted-foreground">
            {workflow.description}
          </p>
          <p className="mt-2.5 flex items-center gap-1.5 text-xs text-subtle">
            <Clock3 className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} aria-hidden="true" />
            {triggerSentence(workflow.trigger)}
          </p>
        </div>

        <div className="flex shrink-0 flex-col items-end gap-1.5">
          <Switch
            checked={workflow.enabled}
            onCheckedChange={toggle}
            disabled={isToggling}
            label={`${workflow.name} — ${workflow.enabled ? "on" : "off"}`}
          />
          <span
            className={cn(
              "text-2xs font-semibold uppercase tracking-[0.1em]",
              workflow.enabled ? "text-primary" : "text-subtle"
            )}
          >
            {workflow.enabled ? "On" : "Off"}
          </span>
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border px-5 py-3">
        <p className="text-xs text-muted-foreground">
          {hasRun ? (
            <>
              {reliabilitySentence(workflow)}
              {workflow.last_run_at && (
                <span className="text-subtle"> · last {formatRelativeTime(workflow.last_run_at)}</span>
              )}
            </>
          ) : workflow.enabled ? (
            <>Hasn&rsquo;t run yet — it&rsquo;s waiting for the next time this happens.</>
          ) : (
            <>Hasn&rsquo;t run yet. Turn it on and it&rsquo;ll start watching for you.</>
          )}
        </p>

        {hasRun && (
          <button
            type="button"
            onClick={openPanel}
            aria-expanded={isOpen}
            aria-controls={panelId}
            className="tap-h press inline-flex items-center gap-1 rounded-md px-1.5 py-1 text-xs font-semibold text-primary hover:underline"
          >
            {isOpen ? "Hide history" : "See what it did"}
            <ChevronDown
              className={cn("h-3.5 w-3.5 transition-transform duration-200 ease-physical", isOpen && "rotate-180")}
              strokeWidth={2}
              aria-hidden="true"
            />
          </button>
        )}
      </div>

      {isOpen && (
        <div id={panelId} className="border-t border-border bg-secondary/30 px-5 py-1">
          {isLoadingRuns && runs === null ? (
            <div className="flex flex-col gap-2 py-4">
              <Skeleton className="h-3 w-40" />
              <Skeleton className="h-3 w-64 max-w-full" />
              <Skeleton className="h-3 w-52 max-w-full" />
              <span className="sr-only" role="status">
                Loading history
              </span>
            </div>
          ) : runsError ? (
            <p className="py-5 text-sm leading-relaxed text-muted-foreground">{runsError}</p>
          ) : runs && runs.length > 0 ? (
            <ul className="divide-y divide-border">
              {runs.map((run) => (
                <RunRow key={run.id} run={run} />
              ))}
            </ul>
          ) : (
            <p className="py-5 text-sm leading-relaxed text-muted-foreground">
              Nothing in the history yet. Every time this runs, you&rsquo;ll see each step it took
              and how it went.
            </p>
          )}
        </div>
      )}
    </Card>
  );
}
