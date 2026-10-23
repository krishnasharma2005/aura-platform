import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * Loading states that match the shape of what is coming, so the page does not
 * rearrange itself when data lands. Static on purpose: the brandbook allows no
 * looping or decorative motion, so the shape alone says "this is coming".
 */
export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "rounded-md bg-foreground/[0.07]",
        className
      )}
      aria-hidden="true"
      {...props}
    />
  );
}

/** Skeleton shaped like a list row with an icon tile and two lines of text. */
export function SkeletonRow({ className }: { className?: string }) {
  return (
    <div className={cn("flex items-start gap-3 py-3.5", className)}>
      <Skeleton className="h-8 w-8 shrink-0 rounded-md" />
      <div className="flex min-w-0 flex-1 flex-col gap-2 pt-0.5">
        <Skeleton className="h-3 w-[72%]" />
        <Skeleton className="h-2.5 w-[38%]" />
      </div>
    </div>
  );
}

/** Skeleton shaped like one of the agent cards on the dashboard. */
export function SkeletonCard({ className }: { className?: string }) {
  return (
    <div className={cn("rounded-lg border border-border bg-card p-5 shadow-card", className)}>
      <Skeleton className="h-9 w-9 rounded-md" />
      <Skeleton className="mt-4 h-3.5 w-1/2" />
      <Skeleton className="mt-2.5 h-2.5 w-full" />
      <Skeleton className="mt-1.5 h-2.5 w-3/4" />
    </div>
  );
}
