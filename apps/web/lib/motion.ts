import type { Transition, Variants } from "framer-motion";

/**
 * One motion vocabulary for the whole product.
 *
 * Everything here simulates mass. Nothing uses `linear` or a bare ease, and
 * nothing animates a layout-triggering property — only transform and opacity,
 * so the compositor does the work and we hold frame rate on a laptop.
 *
 * Motion here is orientation, not decoration: entrances tell you where a thing
 * came from, and state changes tell you that something real happened.
 */

/** The house curve. Heavy start, long settle. */
export const EASE_PHYSICAL = [0.32, 0.72, 0, 1] as const;
/** Softer landing, for things arriving rather than responding. */
export const EASE_SETTLE = [0.16, 1, 0.3, 1] as const;

export const springSoft: Transition = {
  type: "spring",
  stiffness: 320,
  damping: 34,
  mass: 0.9,
};

export const springSnappy: Transition = {
  type: "spring",
  stiffness: 520,
  damping: 38,
  mass: 0.7,
};

/**
 * Page and section entrance. Content rises a short distance — enough to read
 * as "this just arrived", not enough to feel like a slideshow.
 */
export const riseIn: Variants = {
  hidden: { opacity: 0, y: 10 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.5, ease: EASE_SETTLE },
  },
};

/** Parent for staggered lists and grids. */
export function stagger(staggerChildren = 0.045, delayChildren = 0.02): Variants {
  return {
    hidden: {},
    visible: { transition: { staggerChildren, delayChildren } },
  };
}

/** A message or row arriving in a feed. */
export const messageIn: Variants = {
  hidden: { opacity: 0, y: 12, scale: 0.985 },
  visible: {
    opacity: 1,
    y: 0,
    scale: 1,
    transition: springSoft,
  },
};

/** Chips and badges that appear mid-flow (tool calls, statuses). */
export const chipIn: Variants = {
  hidden: { opacity: 0, scale: 0.9, y: 4 },
  visible: { opacity: 1, scale: 1, y: 0, transition: springSnappy },
  exit: { opacity: 0, scale: 0.94, transition: { duration: 0.14 } },
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
