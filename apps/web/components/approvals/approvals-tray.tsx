"use client";

import * as React from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { ShieldCheck } from "lucide-react";
import { useApprovals } from "@/lib/approvals-context";
import { ApprovalCard } from "./approval-card";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

/**
 * The queue, always reachable from the top bar.
 *
 * An owner who misses a queued approval has an agent sitting there waiting,
 * so the count has to be visible from every screen. It is deliberately not a
 * nag: with nothing waiting the control reads as reassurance ("nothing needs
 * you"), and only takes on the accent colour when there is a real decision to
 * make. The number is the whole notification — no red dot, no toast storm.
 */
export function ApprovalsTray() {
  const { pending, count, isLoading, canReview } = useApprovals();
  const [open, setOpen] = React.useState(false);
  const reduce = useReducedMotion();

  // Members can't act on approvals, so showing them an empty tray would be
  // a dead control. Hide it entirely rather than explain a permission.
  if (!canReview) return null;

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <button
          className={cn(
            "press tap-h relative flex items-center gap-2 rounded-md border px-2.5 py-1.5 text-xs font-semibold",
            count > 0
              ? "border-primary/30 bg-primary/[0.07] text-primary hover:bg-primary/[0.11]"
              : "border-border bg-card text-muted-foreground hover:text-foreground"
          )}
          aria-label={
            count > 0
              ? `${count} action${count === 1 ? "" : "s"} waiting for your approval`
              : "Approvals — nothing waiting"
          }
        >
          <ShieldCheck className="h-3.5 w-3.5" strokeWidth={1.9} />
          <span className="hidden sm:inline">Approvals</span>
          <AnimatePresence mode="popLayout" initial={false}>
            <motion.span
              key={count}
              initial={reduce ? { opacity: 0 } : { opacity: 0, y: -6, scale: 0.8 }}
              animate={reduce ? { opacity: 1 } : { opacity: 1, y: 0, scale: 1 }}
              exit={reduce ? { opacity: 0 } : { opacity: 0, y: 6, scale: 0.8 }}
              transition={{ type: "spring", stiffness: 520, damping: 32 }}
              className={cn(
                "flex h-4.5 min-w-[1.125rem] items-center justify-center rounded-full px-1 text-[10px] font-bold tabular-nums",
                count > 0 ? "bg-primary text-primary-foreground" : "bg-secondary text-muted-foreground"
              )}
            >
              {count}
            </motion.span>
          </AnimatePresence>
        </button>
      </SheetTrigger>

      <SheetContent side="right" className="flex flex-col gap-0 p-0">
        <SheetHeader className="border-b border-border px-5 py-4">
          <SheetTitle className="font-display text-lg font-semibold tracking-[-0.015em]">
            Waiting on you
          </SheetTitle>
          <SheetDescription>
            Your agents pause before anything that affects a customer, a booking, or your inbox.
            Nothing here has happened yet.
          </SheetDescription>
        </SheetHeader>

        <div className="flex-1 overflow-y-auto px-5 py-4 scrollbar-thin">
          {isLoading ? (
            <div className="flex flex-col gap-3">
              <Skeleton className="h-32 w-full rounded-lg" />
              <Skeleton className="h-32 w-full rounded-lg" />
            </div>
          ) : count === 0 ? (
            <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed border-border px-5 py-10 text-center">
              <span className="flex h-10 w-10 items-center justify-center rounded-full bg-success/10 text-success">
                <ShieldCheck className="h-5 w-5" strokeWidth={1.75} />
              </span>
              <p className="text-sm font-semibold text-foreground">Nothing needs you</p>
              <p className="max-w-xs text-sm leading-relaxed text-muted-foreground">
                Your agents are handling the routine work on their own. Anything consequential will
                show up here first.
              </p>
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              <AnimatePresence initial={false} mode="popLayout">
                {pending.map((approval) => (
                  <ApprovalCard key={approval.id} approval={approval} />
                ))}
              </AnimatePresence>
            </div>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
