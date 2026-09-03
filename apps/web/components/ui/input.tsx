import * as React from "react";
import { cn } from "@/lib/utils";

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {}

/**
 * Inputs read as recessed — an inner shadow rather than a raised bevel — so
 * the difference between "you push this" and "you type into this" is legible
 * before you read the label.
 */
const Input = React.forwardRef<HTMLInputElement, InputProps>(({ className, type, ...props }, ref) => {
  return (
    <input
      type={type}
      ref={ref}
      className={cn(
        "tap-h flex h-9.5 w-full rounded-md border border-input bg-card px-3 py-1.5 text-sm text-foreground",
        "shadow-inset transition-[border-color,box-shadow] duration-200 ease-physical",
        "placeholder:text-subtle",
        "hover:border-foreground/18",
        "focus-visible:border-primary/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/25",
        "disabled:cursor-not-allowed disabled:bg-secondary/50 disabled:opacity-70",
        className
      )}
      {...props}
    />
  );
});
Input.displayName = "Input";

export { Input };
