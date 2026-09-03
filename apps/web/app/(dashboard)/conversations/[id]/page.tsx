"use client";

import * as React from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, Send, ShieldCheck, UserRound } from "lucide-react";
import { api } from "@/lib/api-client";
import type { ConversationSummary, ConversationTurn } from "@/lib/api-types";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn, errorMessage, formatRelativeTime } from "@/lib/utils";
import { useToast } from "@/components/ui/use-toast";

const POLL_MS = 8_000;

function bubbleStyle(role: string) {
  if (role === "human") return "ml-auto bg-primary text-primary-foreground";
  if (role === "assistant") return "ml-auto bg-secondary text-foreground";
  return "mr-auto bg-card border border-border text-foreground";
}

function roleLabel(role: string) {
  if (role === "human") return "You";
  if (role === "assistant") return "Agent";
  return "Customer";
}

export default function ConversationDetailPage() {
  const params = useParams<{ id: string }>();
  const conversationId = decodeURIComponent(String(params.id));
  const router = useRouter();
  const { toast } = useToast();

  const [turns, setTurns] = React.useState<ConversationTurn[]>([]);
  const [summary, setSummary] = React.useState<ConversationSummary | null>(null);
  const [isLoading, setIsLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [isBusy, setIsBusy] = React.useState(false);
  const [draft, setDraft] = React.useState("");

  const load = React.useCallback(async () => {
    setError(null);
    try {
      const [transcript, list] = await Promise.all([
        api.conversations.transcript(conversationId),
        api.conversations.list(),
      ]);
      setTurns(transcript);
      setSummary(list.find((c) => c.id === conversationId) ?? null);
    } catch (err) {
      setError(errorMessage(err, "Couldn't load this conversation right now."));
    } finally {
      setIsLoading(false);
    }
  }, [conversationId]);

  React.useEffect(() => {
    load();
    const id = window.setInterval(load, POLL_MS);
    return () => window.clearInterval(id);
  }, [load]);

  const isHumanControlled = summary?.mode === "human";

  async function handleTakeover() {
    setIsBusy(true);
    try {
      const updated = await api.conversations.takeover(conversationId);
      setSummary((prev) => (prev ? { ...prev, mode: updated.mode } : prev));
      toast({ title: "You're handling this now", description: "The agent won't reply until you hand it back." });
    } catch (err) {
      toast({ title: "Couldn't take over", description: errorMessage(err, "Please try again."), variant: "destructive" });
    } finally {
      setIsBusy(false);
    }
  }

  async function handleHandback() {
    setIsBusy(true);
    try {
      const updated = await api.conversations.handback(conversationId);
      setSummary((prev) => (prev ? { ...prev, mode: updated.mode } : prev));
      toast({ title: "Handed back", description: `The ${summary?.agent_display_name ?? "agent"} is answering again.` });
    } catch (err) {
      toast({ title: "Couldn't hand back", description: errorMessage(err, "Please try again."), variant: "destructive" });
    } finally {
      setIsBusy(false);
    }
  }

  async function handleSend(e: React.FormEvent) {
    e.preventDefault();
    const content = draft.trim();
    if (!content) return;
    setIsBusy(true);
    try {
      const turn = await api.conversations.sendMessage(conversationId, content);
      setTurns((prev) => [...prev, turn]);
      setDraft("");
    } catch (err) {
      toast({ title: "Message not sent", description: errorMessage(err, "Please try again."), variant: "destructive" });
    } finally {
      setIsBusy(false);
    }
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4 px-6 py-8">
      <div className="flex items-center gap-2">
        <Button variant="ghost" size="icon" onClick={() => router.push("/conversations")} aria-label="Back to conversations">
          <ArrowLeft className="h-4 w-4" strokeWidth={1.75} />
        </Button>
        <div className="min-w-0 flex-1">
          <h1 className="truncate font-display text-lg font-medium text-foreground">
            {summary?.contact?.name || summary?.contact?.phone || summary?.contact?.email || "Conversation"}
          </h1>
          {summary && (
            <p className="text-xs text-muted-foreground">
              {summary.agent_display_name} · started {formatRelativeTime(summary.started_at)}
            </p>
          )}
        </div>
        {isHumanControlled ? (
          <Badge variant="warning">
            <UserRound className="h-3 w-3" strokeWidth={2} /> You&rsquo;re handling this
          </Badge>
        ) : (
          <Badge variant="secondary">
            <ShieldCheck className="h-3 w-3" strokeWidth={2} /> Agent is answering
          </Badge>
        )}
      </div>

      {error && (
        <p className="rounded-md border border-destructive/25 bg-destructive/10 px-3.5 py-2.5 text-sm text-destructive">
          {error}
        </p>
      )}

      <Card className="flex flex-col gap-3 p-4">
        {isLoading ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : turns.length === 0 ? (
          <p className="text-sm text-muted-foreground">No messages yet.</p>
        ) : (
          <div className="flex flex-col gap-2.5">
            {turns.map((turn, i) => (
              <div key={i} className={cn("max-w-[80%] rounded-lg px-3.5 py-2.5 text-sm", bubbleStyle(turn.role))}>
                <p className="mb-0.5 text-2xs font-semibold uppercase tracking-wide text-subtle">
                  {roleLabel(turn.role)}
                </p>
                <p className="whitespace-pre-wrap leading-relaxed">{turn.content}</p>
              </div>
            ))}
          </div>
        )}
      </Card>

      <div className="flex flex-col gap-3">
        {isHumanControlled ? (
          <>
            <form onSubmit={handleSend} className="flex items-end gap-2">
              <textarea
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder="Type a message to send as yourself…"
                rows={2}
                className="tap min-h-[2.5rem] flex-1 resize-none rounded-md border border-input bg-card px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    handleSend(e);
                  }
                }}
              />
              <Button type="submit" disabled={isBusy || !draft.trim()} aria-label="Send message">
                <Send className="h-4 w-4" strokeWidth={1.75} />
              </Button>
            </form>
            <Button variant="outline" onClick={handleHandback} disabled={isBusy} className="self-start">
              Hand back to {summary?.agent_display_name ?? "the agent"}
            </Button>
          </>
        ) : (
          <Button variant="outline" onClick={handleTakeover} disabled={isBusy} className="self-start">
            Take over this conversation
          </Button>
        )}
      </div>
    </div>
  );
}
