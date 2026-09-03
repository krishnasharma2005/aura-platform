"use client";

import * as React from "react";
import { motion, useReducedMotion } from "framer-motion";
import { riseIn, stagger, stillVariants } from "@/lib/motion";
import { cn } from "@/lib/utils";

/**
 * Shared page furniture.
 *
 * Entrance motion here does one job: orient. Content arrives top-down in the
 * order you read it, over about half a second, so your eye is led to the
 * heading before the body. It is not a reveal effect and it never repeats —
 * navigating back to a page you have seen should feel instant, not staged.
 *
 * Every piece degrades to a plain opacity fade under prefers-reduced-motion.
 */

export function Reveal({
  children,
  className,
  delay = 0,
  as = "div",
}: {
  children: React.ReactNode;
  className?: string;
  delay?: number;
  as?: "div" | "section" | "li";
}) {
  const reduce = useReducedMotion();
  const MotionTag = motion[as];
  return (
    <MotionTag
      className={className}
      variants={reduce ? stillVariants : riseIn}
      initial="hidden"
      animate="visible"
      transition={delay ? { delay } : undefined}
    >
      {children}
    </MotionTag>
  );
}

/** Parent for staggered children; pair with `RevealItem`. */
export function RevealGroup({
  children,
  className,
  gap = 0.045,
  delay = 0.02,
}: {
  children: React.ReactNode;
  className?: string;
  gap?: number;
  delay?: number;
}) {
  const reduce = useReducedMotion();
  return (
    <motion.div
      className={className}
      variants={reduce ? stillVariants : stagger(gap, delay)}
      initial="hidden"
      animate="visible"
    >
      {children}
    </motion.div>
  );
}

export function RevealItem({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  const reduce = useReducedMotion();
  return (
    <motion.div className={className} variants={reduce ? stillVariants : riseIn}>
      {children}
    </motion.div>
  );
}

/**
 * Page heading. `eyebrow` is deliberately rare — used only where a page needs
 * a category it cannot infer from its own position in the sidebar.
 */
export function PageHeader({
  title,
  description,
  actions,
  className,
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
}) {
  return (
    <Reveal className={cn("mb-7 flex flex-wrap items-start justify-between gap-4", className)}>
      <div className="min-w-0">
        <h1 className="font-display text-3xl font-semibold tracking-[-0.025em] text-foreground">
          {title}
        </h1>
        {description && (
          <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-muted-foreground">
            {description}
          </p>
        )}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </Reveal>
  );
}

/** Consistent page gutter and measure. */
export function PageBody({
  children,
  width = "wide",
  className,
}: {
  children: React.ReactNode;
  width?: "narrow" | "medium" | "wide";
  className?: string;
}) {
  return (
    <div
      className={cn(
        "mx-auto px-5 py-8 sm:px-8 sm:py-10",
        width === "narrow" && "max-w-3xl",
        width === "medium" && "max-w-4xl",
        width === "wide" && "max-w-6xl",
        className
      )}
    >
      {children}
    </div>
  );
}
