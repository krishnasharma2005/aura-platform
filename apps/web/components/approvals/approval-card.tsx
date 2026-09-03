"use client";

import * as React from "react";
import { motion, useReducedMotion } from "framer-motion";
import { Check, ShieldQuestion, X } from "lucide-react";
import type { Approval, ApprovalStatus, PendingApproval } from "@/lib/api-types";
import { INTEGRATIONS } from "@/lib/integrations";
import { useApprovals } from "@/lib/approvals-context";
import { useToast } from "@/components/ui/use-toast";
import { Button } from "@/components/ui/button";
import { cn, errorMessage } from "@/lib/utils";
import { chipIn, stillVariants } from "@/lib/motion";

/** The connected account, named the way the owner named it when connecting. */
function toolLabel(tool: string): string {
  const match = INTEGRATIONS.find((i) => i.provider === tool);
  if (match) return match.displayName;
  return tool.replace(/[_-]/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/**
 * An action waiting on the owner.
 *
 * This is the most trust-critical surface in the product, so it is also the
 * calmest: no red, no alarm, no countdown. It is a receipt you sign. The
 * summary the backend writes leads; the machinery (which account, which
 * agent) is secondary and set in the micro-label style used for data
 * everywhere else.
 */
export function ApprovalCard({
  approval,
  agentName,
  compact = false,
  className,
}: {
  approval: Approval | PendingApproval;
  /** Shown when the approval doesn't carry its own agent name (inline case). */
  agentName?: string;
  compact?: boolean;
  className?: string;
}) {
  const { decide, decisions } = useApprovals();
  const { toast } = useToast();
  const reduce = useReducedMotion();
  const [busy, setBusy] = React.useState<"approve" | "reject" | null>(null);

  const decided = decisions[approval.id];
  const displayAgent =
    "agent_display_name" in approval ? approval.agent_display_name : agentName ?? "Your agent";
  const details = "details" in approval ? approval.details : undefined;

  async function handle(decision: "approve" | "reject") {
    setBusy(decision);
    try {
      await decide(approval.id, decision);
      toast({
        title: decision === "approve" ? "Approved" : "Declined",
        description:
          decision === "approve"
            ? `${displayAgent} is going ahead. You'll see it in Activity.`
            : `${displayAgent} won't do this. Nothing was changed.`,
      });
    } catch (err) {
      toast({
        title: "Couldn't record your decision",
        description:
          errorMessage(err, "Check your connection and try again — nothing has happened yet."),
        variant: "destructive",
      });
    } finally {
      setBusy(null);
    }
  }

  if (decided) {
    return <ResolvedNote status={decided.status} message={decided.message} className={className} />;
  }

  return (
    <motion.div
      variants={reduce ? stillVariants : chipIn}
      initial="hidden"
      animate="visible"
      exit="exit"
      className={cn(
        "overflow-hidden rounded-lg border border-primary/25 bg-card shadow-card",
        className
      )}
    >
      {/* A calm signal band, not a warning stripe. */}
      <div className="flex items-center gap-2 border-b border-primary/15 bg-primary/[0.055] px-3.5 py-2">
        <ShieldQuestion className="h-3.5 w-3.5 shrink-0 text-primary" strokeWidth={1.9} />
        <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-primary">
          Needs your OK
        </span>
      </div>

      <div className={cn("px-3.5", compact ? "py-3" : "py-3.5")}>
        <p className="text-sm leading-relaxed text-foreground">{approval.summary}</p>
        {details && (
          <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">{details}</p>
        )}

        <p className="mt-2.5 flex flex-wrap items-center gap-x-2 gap-y-1 font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">
          <span>{displayAgent}</span>
          <span className="text-subtle">·</span>
          <span>Using {toolLabel(approval.tool)}</span>
        </p>

        <div className="mt-3.5 flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            onClick={() => handle("approve")}
            loading={busy === "approve"}
            disabled={busy !== null}
          >
            <Check className="h-3.5 w-3.5" strokeWidth={2.25} />
            Approve
          </Button>
          <Button
            size="sm"
            variant="secondary"
            onClick={() => handle("reject")}
            loading={busy === "reject"}
            disabled={busy !== null}
          >
            <X className="h-3.5 w-3.5" strokeWidth={2.25} />
            Decline
          </Button>
          <span className="text-xs text-muted-foreground">Nothing happens until you choose.</span>
        </div>
      </div>
    </motion.div>
  );
}

/** What a decided request leaves behind, in the place it was asked. */
function ResolvedNote({
  status,
  message,
  className,
}: {
  status: ApprovalStatus;
  message?: string | null;
  className?: string;
}) {
  const approved = status === "approved";
  return (
    <div
      className={cn(
        "flex items-start gap-2 rounded-lg border px-3.5 py-2.5",
        approved ? "border-success/25 bg-success/[0.07]" : "border-border bg-secondary/50",
        className
      )}
    >
      <span
        className={cn(
          "mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full",
          approved ? "bg-success text-success-foreground" : "bg-muted-foreground text-card"
        )}
      >
        {approved ? (
          <Check className="h-2.5 w-2.5" strokeWidth={3} />
        ) : (
          <X className="h-2.5 w-2.5" strokeWidth={3} />
        )}
      </span>
      <p className={cn("text-xs leading-relaxed", approved ? "text-success" : "text-muted-foreground")}>
        {message ?? (approved ? "Approved — going ahead now." : "Declined. Nothing was changed.")}
      </p>
    </div>
  );
}
