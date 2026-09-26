import type { AgentSlug } from "./api-types";

/**
 * The topology behind the runtime graph.
 *
 * This is the one thing about AURA that a sidebar list cannot show: the six
 * agents are not six products. They are six configurations of a single
 * runtime, and they read and write the *same* memory, the *same* documents,
 * and the *same* connected accounts. Every relationship encoded below is true
 * of the actual system — the agents genuinely share these three layers, and
 * the per-agent connection lists match the tools each agent is scoped to in
 * the Phase 1 plan. Nothing here is drawn for looks.
 */

export type LayerId = "memory" | "knowledge" | "connections";

export interface SharedLayer {
  id: LayerId;
  /** Plain-language name. No jargon reaches the screen. */
  label: string;
  /** One line the owner can read without knowing what a vector store is. */
  blurb: string;
  /** Vertical position of the layer plate, in scene units. */
  y: number;
  /** Plate radius, in scene units. */
  radius: number;
}

/**
 * The three plates the core sits on. Ordered top-to-bottom as they appear in
 * the scene: what agents remember, what they read, what they can reach.
 */
export const SHARED_LAYERS: SharedLayer[] = [
  {
    id: "memory",
    label: "Shared memory",
    blurb: "What one agent learns about a customer, every agent knows.",
    y: -1.05,
    radius: 1.25,
  },
  {
    id: "knowledge",
    label: "Your documents",
    blurb: "One set of price lists, policies, and FAQs answers every question.",
    y: -1.6,
    radius: 1.62,
  },
  {
    id: "connections",
    label: "Connected accounts",
    blurb: "Your calendar, inbox, and store connect once, not six times.",
    y: -2.15,
    radius: 2.0,
  },
];

export interface GraphNode {
  slug: AgentSlug;
  /** Short label rendered against the node. */
  label: string;
  /** Which connected accounts this agent is actually scoped to use. */
  connections: string[];
}

/**
 * The six agents, in the order they orbit the core. Connection lists are the
 * Phase 1 tool scopes, not decoration.
 */
export const GRAPH_NODES: GraphNode[] = [
  { slug: "receptionist", label: "Receptionist", connections: ["Calendar", "Gmail", "WhatsApp"] },
  { slug: "sales", label: "Sales", connections: ["Gmail", "HubSpot", "Slack"] },
  { slug: "marketing", label: "Marketing", connections: ["HubSpot", "Shopify", "Slack"] },
  { slug: "executive_assistant", label: "Assistant", connections: ["Calendar", "Gmail", "Slack"] },
  { slug: "support", label: "Support", connections: ["Gmail", "WhatsApp", "Slack"] },
  { slug: "ecommerce", label: "Store", connections: ["Shopify", "Slack"] },
];

/** Radius of the agent orbit, in scene units. */
export const ORBIT_RADIUS = 2.75;

/**
 * Where each agent node sits. Evenly spaced around the orbit, with a gentle
 * sine lift so the ring reads as a three-dimensional band rather than a flat
 * dial when the scene is still.
 */
export function nodePosition(index: number, total = GRAPH_NODES.length): [number, number, number] {
  const angle = (index / total) * Math.PI * 2 - Math.PI / 2;
  return [
    Math.cos(angle) * ORBIT_RADIUS,
    Math.sin(angle * 2) * 0.34,
    Math.sin(angle) * ORBIT_RADIUS,
  ];
}

/**
 * Sample points along the curved edge from an agent node into the core. The
 * curve bows toward the shared layers below, so the line visibly reads as
 * "this agent goes down through the shared foundation to reach the core."
 */
export function edgePoints(
  from: [number, number, number],
  segments = 22
): [number, number, number][] {
  const [fx, fy, fz] = from;
  const points: [number, number, number][] = [];
  for (let i = 0; i <= segments; i++) {
    const t = i / segments;
    // Quadratic bezier toward the origin with a control point dipped below.
    const cx = fx * 0.45;
    const cy = fy * 0.3 - 0.9;
    const cz = fz * 0.45;
    const mt = 1 - t;
    points.push([
      mt * mt * fx + 2 * mt * t * cx,
      mt * mt * fy + 2 * mt * t * cy,
      mt * mt * fz + 2 * mt * t * cz,
    ]);
  }
  return points;
}

/** Position along an edge at progress `t` (0 at the node, 1 at the core). */
export function pointOnEdge(
  from: [number, number, number],
  t: number
): [number, number, number] {
  const [fx, fy, fz] = from;
  const cx = fx * 0.45;
  const cy = fy * 0.3 - 0.9;
  const cz = fz * 0.45;
  const mt = 1 - t;
  return [
    mt * mt * fx + 2 * mt * t * cx,
    mt * mt * fy + 2 * mt * t * cy,
    mt * mt * fz + 2 * mt * t * cz,
  ];
}

/**
 * Reads an `--graph-*` custom property (space-separated RGB) off the document
 * so the scene inherits the theme instead of hard-coding a colour that would
 * be wrong in one of the two themes.
 */
export function themeColor(name: string, fallback: string): string {
  if (typeof window === "undefined") return fallback;
  const raw = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  if (!raw) return fallback;
  return `rgb(${raw.replace(/\s+/g, ",")})`;
}

/**
 * WebGL availability check. Cheap, cached, and safe in every context we run
 * in — headless CI, locked-down corporate browsers, and machines with GPU
 * acceleration disabled all fall through to the static graph.
 */
let webglSupport: boolean | null = null;
export function hasWebGL(): boolean {
  if (webglSupport !== null) return webglSupport;
  if (typeof window === "undefined") return false;
  try {
    const canvas = document.createElement("canvas");
    webglSupport = Boolean(
      window.WebGLRenderingContext &&
        (canvas.getContext("webgl2") || canvas.getContext("webgl"))
    );
  } catch {
    webglSupport = false;
  }
  return webglSupport;
}
