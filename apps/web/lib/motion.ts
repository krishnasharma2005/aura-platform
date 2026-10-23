import type { Variants } from "framer-motion";

/**
 * One motion vocabulary for the whole product, from the brandbook (p. 17-18).
 *
 * Four tempos: respond 160ms (a control answering a touch), reveal 240ms
 * (something appearing), resolve 480ms (a state settling), introduce 640ms (a
 * whole view arriving). One curve for entrances; progress is linear. No bounce,
 * overshoot, springs or elastic scaling, and nothing loops.
 *
 * Only transform and opacity animate, so the compositor does the work. Motion
 * is orientation, not decoration: entrances show where a thing came from.
 * Reduced motion keeps the same end state without the travel.
 */

export const DURATION = {
  respond: 0.16,
  reveal: 0.24,
  resolve: 0.48,
  introduce: 0.64,
} as const;

/** The entrance curve. */
export const EASE_BRAND = [0.22, 1, 0.36, 1] as const;

/** A tween with the house curve; the only transition shape components should use. */
export function tween(duration: number = DURATION.reveal) {
  return { duration, ease: EASE_BRAND } as const;
}

/** Page and section entrance: a short rise, as a view is introduced. */
export const riseIn: Variants = {
  hidden: { opacity: 0, y: 8 },
  visible: {
    opacity: 1,
    y: 0,
    transition: tween(DURATION.resolve),
  },
};

/** Parent for staggered lists and grids. */
export function stagger(staggerChildren = 0.04, delayChildren = 0.02): Variants {
  return {
    hidden: {},
    visible: { transition: { staggerChildren, delayChildren } },
  };
}

/** A message or row arriving in a feed. */
export const messageIn: Variants = {
  hidden: { opacity: 0, y: 8 },
  visible: { opacity: 1, y: 0, transition: tween(DURATION.reveal) },
};

/** Chips and badges that appear mid-flow (tool calls, statuses). */
export const chipIn: Variants = {
  hidden: { opacity: 0, y: 4 },
  visible: { opacity: 1, y: 0, transition: tween(DURATION.reveal) },
  exit: { opacity: 0, transition: tween(DURATION.respond) },
};

/**
 * Reduced-motion equivalents. Applied by swapping the variants object, so a
 * component's structure never changes — only the distance travelled.
 */
export const stillVariants: Variants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { duration: 0.15 } },
  exit: { opacity: 0, transition: { duration: 0.1 } },
};
