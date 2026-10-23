import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Buttons are matte: flat fills and hairlines, no bevel and no glow (brandbook:
 * "no gradients, no glow"). Crimson is the one deliberate signal, so only the
 * primary action carries it. Every variant takes a small press.
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
          "hover:bg-primary/90",
        ].join(" "),
        secondary:
          "border border-border bg-card text-foreground shadow-subtle hover:bg-secondary/70 hover:border-foreground/15 active:shadow-inset",
        outline:
          "border border-border bg-transparent text-foreground hover:bg-secondary/60 hover:border-foreground/15",
        ghost: "text-foreground hover:bg-secondary/70",
        destructive:
          "bg-destructive text-destructive-foreground hover:bg-destructive/90",
        link: "text-primary-ink underline-offset-4 hover:underline",
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
