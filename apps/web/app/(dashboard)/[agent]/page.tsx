"use client";

import { notFound, useParams } from "next/navigation";
import { getAgentBySlug } from "@/lib/agents";
import { ChatInterface } from "@/components/chat/chat-interface";
import { GRAPH_NODES } from "@/lib/runtime-graph";

export default function AgentPage() {
  const params = useParams<{ agent: string }>();
  const agent = getAgentBySlug(params.agent);

  if (!agent) {
    notFound();
  }

  const Icon = agent.icon;
  const node = GRAPH_NODES.find((n) => n.slug === agent.slug);

  return (
    <div className="flex h-full flex-col">
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-x-6 gap-y-3 border-b border-border bg-card/40 px-5 py-3.5 sm:px-6">
        <div className="flex min-w-0 items-center gap-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-primary/[0.08] text-primary ring-1 ring-inset ring-primary/15">
            <Icon className="h-4.5 w-4.5" strokeWidth={1.75} />
          </span>
          <div className="min-w-0">
            <h1 className="truncate font-display text-lg font-semibold leading-tight tracking-[-0.015em] text-foreground">
              {agent.displayName}
            </h1>
            {/*
              On a phone the tagline was truncating mid-word ("books
              appointments, n…"), which reads as a rendering fault rather than
              as elision. Let it wrap to two lines there; keep the single-line
              truncation once the header has the width for it.
            */}
            <p className="line-clamp-2 text-xs text-muted-foreground sm:truncate">
              {agent.tagline}
            </p>
          </div>
        </div>

        {/*
          The same fact the runtime graph makes visually: this agent is not a
          silo. It reads the same documents and memory as the other five, and
          reaches your accounts through the same connections.
        */}
        {node && (
          <p className="hidden items-center gap-2 font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground lg:flex">
            <span>Shares your documents and memory</span>
            <span className="text-subtle">·</span>
            <span>Uses {node.connections.join(", ")}</span>
          </p>
        )}
      </div>

      <div className="min-h-0 flex-1">
        <ChatInterface agent={agent} />
      </div>
    </div>
  );
}
