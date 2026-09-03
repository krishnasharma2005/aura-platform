"use client";

import * as React from "react";
import { api } from "@/lib/api-client";
import type { AuditLogEntry } from "@/lib/api-types";
import { AGENTS } from "@/lib/agents";
import { ActivityItem } from "@/components/activity/activity-item";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn, errorMessage } from "@/lib/utils";

export default function ActivityPage() {
  const [entries, setEntries] = React.useState<AuditLogEntry[]>([]);
  const [isLoading, setIsLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [filter, setFilter] = React.useState<string | undefined>(undefined);

  const load = React.useCallback(async (agentSlug?: string) => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await api.auditLogs.list(agentSlug);
      setEntries(data);
    } catch (err) {
      setError(
        errorMessage(err, "Couldn't load your activity feed right now.")
      );
    } finally {
      setIsLoading(false);
    }
  }, []);

  React.useEffect(() => {
    load(filter);
  }, [filter, load]);

  return (
    <div className="mx-auto max-w-3xl px-6 py-8">
      <div className="mb-6">
        <h1 className="font-display text-2xl font-medium text-foreground">Activity</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Every booking, reply, and action your agents have taken — in plain language, so you can spot-check
          anything at a glance.
        </p>
      </div>

      <div className="mb-5 flex flex-wrap gap-1.5">
        <button
          onClick={() => setFilter(undefined)}
          className={cn(
            "tap-h inline-flex items-center rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
            !filter
              ? "border-primary bg-primary/10 text-primary"
              : "border-border bg-card text-muted-foreground hover:text-foreground"
          )}
        >
          All agents
        </button>
        {AGENTS.map((agent) => (
          <button
            key={agent.slug}
            onClick={() => setFilter(agent.slug)}
            className={cn(
              "tap-h inline-flex items-center rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
              filter === agent.slug
                ? "border-primary bg-primary/10 text-primary"
                : "border-border bg-card text-muted-foreground hover:text-foreground"
            )}
          >
            {agent.shortLabel}
          </button>
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Recent activity</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <p className="text-sm text-muted-foreground">Loading activity…</p>
          ) : error ? (
            <p className="text-sm text-destructive">{error}</p>
          ) : entries.length === 0 ? (
            <div className="rounded-md border border-dashed border-border px-4 py-10 text-center">
              <p className="text-sm text-muted-foreground">
                Nothing to show yet. Once your agents start handling calls, messages, or orders, every
                action they take will be logged here.
              </p>
            </div>
          ) : (
            <ul className="divide-y divide-border">
              {entries.map((entry) => (
                <ActivityItem key={entry.id} entry={entry} />
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
