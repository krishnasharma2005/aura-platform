import { getAgentBySlug } from "@/lib/agents";
import type { AuditLogEntry } from "@/lib/api-types";
import { formatRelativeTime } from "@/lib/utils";

function describe(entry: AuditLogEntry): string {
  if (entry.summary) return entry.summary;
  const agent = getAgentBySlug(entry.agent_slug)?.displayName ?? entry.agent_slug;
  const who = entry.customer_name ? ` for ${entry.customer_name}` : "";
  return `${agent} recorded an action${who}: ${entry.action.replace(/_/g, " ")}`;
}

export function ActivityItem({ entry }: { entry: AuditLogEntry }) {
  const agent = getAgentBySlug(entry.agent_slug);
  const Icon = agent?.icon;

  return (
    <li className="flex gap-3 py-3.5">
      <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
        {Icon ? <Icon className="h-4 w-4" strokeWidth={1.75} /> : null}
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-sm text-foreground">{describe(entry)}</p>
        <p className="mt-0.5 text-xs text-muted-foreground">
          {agent?.displayName ?? entry.agent_slug} · {formatRelativeTime(entry.created_at)}
        </p>
      </div>
    </li>
  );
}
