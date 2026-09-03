import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Buttons are physical. Every variant carries the same three material cues as
 * a raised surface — a lit top bevel, a tinted contact shadow, and a hairline
 * — and every one of them takes a real press: the button scales down under
 * the pointer and its shadow tightens, the way a key does.
 */
const buttonVariants = cva(
  [
    "relative inline-flex select-none items-center justify-center gap-2 whitespace-nowrap",
    "rounded-md text-sm font-semibold",
    // A 32px `sm` button is fine under a cursor and too small under a thumb.
    // `tap-h` only applies on coarse pointers and phone widths.
    "tap-h",
    "transition-[transform,box-shadow,background-color,border-color,color] duration-200 ease-physical",
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
    "disabled:pointer-events-none disabled:opacity-45",
    "active:scale-[0.975]",
  ].join(" "),
  {
    variants: {
      variant: {
        default: [
          "bg-primary text-primary-foreground",
          "shadow-[inset_0_1px_0_0_hsl(0_0%_100%/0.18),0_1px_2px_-1px_hsl(var(--foreground)/0.3),0_6px_16px_-8px_hsl(var(--primary)/0.55)]",
          "hover:bg-primary/92 hover:shadow-[inset_0_1px_0_0_hsl(0_0%_100%/0.22),0_2px_4px_-2px_hsl(var(--foreground)/0.3),0_10px_24px_-10px_hsl(var(--primary)/0.6)]",
          "active:shadow-[inset_0_1px_2px_0_hsl(var(--foreground)/0.25)]",
        ].join(" "),
        secondary:
          "border border-border bg-card text-foreground shadow-subtle hover:bg-secondary/70 hover:border-foreground/15 active:shadow-inset",
        outline:
          "border border-border bg-transparent text-foreground hover:bg-secondary/60 hover:border-foreground/15",
        ghost: "text-foreground hover:bg-secondary/70",
        destructive:
          "bg-destructive text-destructive-foreground shadow-[inset_0_1px_0_0_hsl(0_0%_100%/0.18),0_1px_2px_-1px_hsl(var(--foreground)/0.3)] hover:bg-destructive/92",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-9.5 px-4 py-2",
        sm: "h-8 rounded-md px-3 text-xs",
        lg: "h-11 rounded-md px-6 text-base",
        icon: "h-9.5 w-9.5 tap",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
  /**
   * Shows a spinner and blocks input without changing the button's width, so
   * a submitting form never reflows under the user's cursor.
   */
  loading?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, loading = false, children, disabled, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";

    if (asChild) {
      return (
        <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props}>
          {children}
        </Comp>
      );
    }

    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        disabled={disabled || loading}
        aria-busy={loading || undefined}
        {...props}
      >
        {loading && (
          <Loader2 className="absolute h-4 w-4 animate-spin" aria-hidden="true" strokeWidth={2} />
        )}
        <span
          className={cn(
            "inline-flex items-center gap-2 transition-opacity duration-200",
            loading && "opacity-0"
          )}
        >
          {children}
        </span>
      </Comp>
    );
  }
);
Button.displayName = "Button";

export { Button, buttonVariants };
