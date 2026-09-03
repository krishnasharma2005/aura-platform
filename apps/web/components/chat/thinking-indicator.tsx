"use client";

import * as React from "react";
import { motion, useReducedMotion } from "framer-motion";

/**
 * The wait, narrated.
 *
 * A spinner tells you nothing; this tells you roughly where the agent is. The
 * phases advance on a timer rather than from the server — the API answers in
 * one shot — so the copy is deliberately about the *kind* of work, never a
 * specific claim ("Checking your calendar" would be a lie if it didn't).
 *
 * The bars are a transform-only animation, so this costs nothing to run.
 */
const PHASES = ["Reading your message", "Checking what it knows", "Writing a reply"];

export function ThinkingIndicator({ agentLabel }: { agentLabel: string }) {
  const reduce = useReducedMotion();
  const [phase, setPhase] = React.useState(0);

  React.useEffect(() => {
    const id = window.setInterval(() => {
      setPhase((p) => Math.min(p + 1, PHASES.length - 1));
    }, 1400);
    return () => window.clearInterval(id);
  }, []);

  return (
    <motion.div
      initial={reduce ? { opacity: 0 } : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, transition: { duration: 0.15 } }}
      transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
      className="flex items-center gap-2.5 pl-10"
      role="status"
      aria-live="polite"
    >
      <span className="flex items-end gap-[3px]" aria-hidden="true">
        {[0, 1, 2].map((i) => (
          <motion.span
            key={i}
            className="h-3 w-[3px] origin-bottom rounded-full bg-primary/55"
            animate={reduce ? { scaleY: 1 } : { scaleY: [0.35, 1, 0.35] }}
            transition={{
              duration: 1.1,
              repeat: Infinity,
              ease: [0.4, 0, 0.6, 1],
              delay: i * 0.14,
            }}
          />
        ))}
      </span>
      <span className="text-xs text-muted-foreground">
        <span className="font-medium text-foreground/80">{agentLabel}</span> · {PHASES[phase]}…
      </span>
    </motion.div>
  );
}
