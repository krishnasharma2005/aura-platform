"use client";

import * as React from "react";
import Link from "next/link";
import { MessageCircle, MessagesSquare, UserRound } from "lucide-react";
import { api } from "@/lib/api-client";
import type { ConversationSummary } from "@/lib/api-types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn, errorMessage, formatRelativeTime } from "@/lib/utils";

const CHANNEL_LABELS: Record<string, string> = {
  dashboard: "Dashboard",
  web_chat: "Website chat",
  whatsapp: "WhatsApp",
};

export default function ConversationsPage() {
  const [conversations, setConversations] = React.useState<ConversationSummary[]>([]);
  const [isLoading, setIsLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  const load = React.useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      setConversations(await api.conversations.list());
    } catch (err) {
      setError(errorMessage(err, "Couldn't load your conversations right now."));
    } finally {
      setIsLoading(false);
    }
  }, []);

  React.useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="mx-auto max-w-3xl px-6 py-8">
      <div className="mb-6">
        <h1 className="font-display text-2xl font-medium text-foreground">Conversations</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Every thread your agents have had with a customer. Open one to read it, or take over and reply
          yourself.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Recent conversations</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <p className="text-sm text-muted-foreground">Loading conversations…</p>
          ) : error ? (
            <p className="text-sm text-destructive">{error}</p>
          ) : conversations.length === 0 ? (
            <div className="rounded-md border border-dashed border-border px-4 py-10 text-center">
              <MessagesSquare className="mx-auto h-6 w-6 text-subtle" strokeWidth={1.5} />
              <p className="mt-3 text-sm text-muted-foreground">
                Nothing yet. Once a customer messages one of your agents, the thread shows up here.
              </p>
            </div>
          ) : (
            <ul className="divide-y divide-border">
              {conversations.map((conversation) => (
                <li key={conversation.id}>
                  <Link
                    href={`/conversations/${encodeURIComponent(conversation.id)}`}
                    className="press tap-h flex items-start gap-3 rounded-md py-3.5 hover:bg-secondary/50"
                  >
                    <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
                      <MessageCircle className="h-4 w-4" strokeWidth={1.75} />
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="truncate text-sm font-medium text-foreground">
                          {conversation.contact?.name || conversation.contact?.phone || conversation.contact?.email || "Someone"}
                        </p>
                        <Badge variant="outline">{CHANNEL_LABELS[conversation.channel] ?? conversation.channel}</Badge>
                        {conversation.mode === "human" && (
                          <Badge variant="warning">
                            <UserRound className="h-3 w-3" strokeWidth={2} /> You&rsquo;re handling this
                          </Badge>
                        )}
                      </div>
                      {conversation.preview && (
                        <p className="mt-0.5 truncate text-sm text-muted-foreground">{conversation.preview}</p>
                      )}
                      <p className={cn("mt-0.5 text-xs text-muted-foreground")}>
                        {conversation.agent_display_name} · {formatRelativeTime(conversation.last_message_at)}
                      </p>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
