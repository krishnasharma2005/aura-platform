import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * The base raised surface. `interactive` adds the hover lift used by anything
 * that navigates — the card rises a hair and its ambient shadow spreads,
 * which is what makes a flat light theme read as having depth.
 */
const Card = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement> & { interactive?: boolean }
>(({ className, interactive = false, ...props }, ref) => (
  <div
    ref={ref}
    className={cn(
      "rounded-lg border border-border bg-card text-card-foreground shadow-card",
      interactive &&
        "press cursor-pointer hover:-translate-y-0.5 hover:border-foreground/12 hover:shadow-lifted active:translate-y-0",
      className
    )}
    {...props}
  />
));
Card.displayName = "Card";

/**
 * A nested enclosure: an inner core seated inside an outer shell with
 * concentric radii, like a glass plate in a machined tray. Reserved for
 * surfaces that carry weight — the runtime graph, the auth panel — so it stays
 * a signal rather than a texture applied everywhere.
 */
const CardShell = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, children, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        "rounded-2xl border border-border/70 bg-foreground/[0.035] p-1.5 shadow-panel",
        className
      )}
      {...props}
    >
      <div className="rounded-xl border border-border/60 bg-card shadow-subtle">{children}</div>
    </div>
  )
);
CardShell.displayName = "CardShell";

const CardHeader = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("flex flex-col gap-1.5 p-5", className)} {...props} />
  )
);
CardHeader.displayName = "CardHeader";

const CardTitle = React.forwardRef<HTMLParagraphElement, React.HTMLAttributes<HTMLHeadingElement>>(
  ({ className, ...props }, ref) => (
    <h3
      ref={ref}
      className={cn(
        "font-display text-lg font-semibold leading-tight tracking-[-0.015em] text-foreground",
        className
      )}
      {...props}
    />
  )
);
CardTitle.displayName = "CardTitle";

const CardDescription = React.forwardRef<
  HTMLParagraphElement,
  React.HTMLAttributes<HTMLParagraphElement>
>(({ className, ...props }, ref) => (
  <p ref={ref} className={cn("text-sm leading-relaxed text-muted-foreground", className)} {...props} />
));
CardDescription.displayName = "CardDescription";

const CardContent = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => <div ref={ref} className={cn("p-5 pt-0", className)} {...props} />
);
CardContent.displayName = "CardContent";

const CardFooter = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("flex items-center p-5 pt-0", className)} {...props} />
  )
);
CardFooter.displayName = "CardFooter";

export { Card, CardShell, CardHeader, CardTitle, CardDescription, CardContent, CardFooter };
