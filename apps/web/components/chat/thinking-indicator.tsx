"use client";

import * as React from "react";
import { motion, useReducedMotion } from "framer-motion";
import { DURATION, tween } from "@/lib/motion";

/**
 * The wait, narrated.
 *
 * A spinner tells you nothing; this tells you roughly where the agent is. The
 * phases advance on a timer rather than from the server — the API answers in
 * one shot — so the copy is deliberately about the *kind* of work, never a
 * specific claim ("Checking your calendar" would be a lie if it didn't).
 *
 * Nothing loops: the brandbook asks for the current state to be named in text,
 * and the phase text advancing is the only movement.
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
      exit={{ opacity: 0, transition: tween(DURATION.respond) }}
      transition={tween(DURATION.reveal)}
      className="flex items-center gap-2.5 pl-10"
      role="status"
      aria-live="polite"
    >
      <span className="h-1.5 w-1.5 rounded-full bg-primary" aria-hidden="true" />
      <span className="text-xs text-muted-foreground">
        <span className="font-medium text-foreground/80">{agentLabel}</span> · {PHASES[phase]}…
      </span>
    </motion.div>
  );
}
