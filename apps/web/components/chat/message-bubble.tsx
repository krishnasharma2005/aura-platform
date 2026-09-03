"use client";

import * as React from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import type { ChatMessage } from "@/lib/api-types";
import { messageIn, stillVariants } from "@/lib/motion";
import { cn, formatClockTime } from "@/lib/utils";
import { ToolCallChip } from "./tool-call-chip";
import { ApprovalCard } from "@/components/approvals/approval-card";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";

/**
 * One turn of the conversation.
 *
 * Reading order top-to-bottom inside an agent turn is deliberate:
 *   1. what it reached for (tool chips),
 *   2. what it said,
 *   3. what it wants permission to do (approval prompt).
 * That is the order the owner needs it in — the evidence arrives before the
 * answer, and the ask arrives last, after they have read both.
 */
export function MessageBubble({
  message,
  agentLabel,
  agentName,
}: {
  message: ChatMessage;
  agentLabel: string;
  agentName: string;
}) {
  const reduce = useReducedMotion();
  const isUser = message.role === "user";
  const approvals = message.pending_approvals ?? [];

  return (
    <motion.div
      variants={reduce ? stillVariants : messageIn}
      initial="hidden"
      animate="visible"
      className={cn("flex w-full gap-3", isUser && "flex-row-reverse")}
    >
      <Avatar className="mt-0.5 h-7 w-7 shrink-0">
        <AvatarFallback
          className={cn(
            "text-[0.625rem] font-semibold",
            isUser
              ? "bg-secondary text-muted-foreground"
              : "bg-primary/[0.10] text-primary ring-1 ring-inset ring-primary/15"
          )}
        >
          {isUser ? "You" : agentLabel.slice(0, 2).toUpperCase()}
        </AvatarFallback>
      </Avatar>

      <div className={cn("flex min-w-0 max-w-[min(36rem,80%)] flex-col gap-2", isUser && "items-end")}>
        {message.tool_calls && message.tool_calls.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            <AnimatePresence initial={false}>
              {message.tool_calls.map((tc, i) => (
                <ToolCallChip key={`${message.id}-${tc.name}-${i}`} toolCall={tc} />
              ))}
            </AnimatePresence>
          </div>
        )}

        <div
          className={cn(
            "rounded-lg px-3.5 py-2.5 text-sm leading-relaxed",
            isUser
              ? "rounded-tr-sm bg-primary text-primary-foreground shadow-[inset_0_1px_0_0_hsl(0_0%_100%/0.14),0_2px_8px_-4px_hsl(var(--primary)/0.5)]"
              : "rounded-tl-sm border border-border bg-card text-card-foreground shadow-subtle"
          )}
        >
          <p className="whitespace-pre-wrap break-words">
            {message.content}
            {/* Typing cursor while the reply is still arriving. */}
            {!isUser && message.content === "" && (
              <span className="inline-block h-4 w-[2px] translate-y-0.5 animate-breathe rounded-full bg-primary/60" />
            )}
          </p>
        </div>

        {approvals.length > 0 && (
          <div className="flex w-full flex-col gap-2 pt-0.5">
            {approvals.map((a) => (
              <ApprovalCard key={a.id} approval={a} agentName={agentName} compact />
            ))}
          </div>
        )}

        <span className="px-1 font-mono text-[10px] tracking-wide text-subtle">
          {formatClockTime(message.created_at)}
        </span>
      </div>
    </motion.div>
  );
}
