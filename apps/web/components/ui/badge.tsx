import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

/**
 * Status only. Badges never decorate — if one is on screen it is because the
 * state it names is true right now.
 */
const badgeVariants = cva(
  "inline-flex w-fit items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-2xs font-semibold leading-5 transition-colors duration-200",
  {
    variants: {
      variant: {
        default: "border-primary/20 bg-primary/[0.08] text-primary",
        secondary: "border-border bg-secondary text-muted-foreground",
        outline: "border-border text-muted-foreground",
        success: "border-success/20 bg-success/[0.09] text-success",
        warning: "border-warning/25 bg-warning/[0.10] text-warning",
        destructive: "border-destructive/20 bg-destructive/[0.09] text-destructive",
      },
    },
    defaultVariants: { variant: "default" },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
