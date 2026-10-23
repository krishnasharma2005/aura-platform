import type { AgentSlug } from "./api-types";

/**
 * Which connected accounts each agent is scoped to use. These are the real tool
 * scopes, so the line on an agent's page and the Connections screen agree.
 * The Chief of Staff delegates to the others and has no scope of its own.
 */
export const AGENT_CONNECTIONS: Partial<Record<AgentSlug, string[]>> = {
  receptionist: ["Calendar", "Gmail", "WhatsApp"],
  sales: ["Gmail", "HubSpot", "Slack"],
  marketing: ["HubSpot", "Shopify", "Slack"],
  executive_assistant: ["Calendar", "Gmail", "Slack"],
  support: ["Gmail", "WhatsApp", "Slack"],
  ecommerce: ["Shopify", "Slack"],
};

/** What every agent shares, in plain words. Each line is true of the system. */
export const SHARED_CONTEXT = [
  {
    id: "memory",
    label: "Shared memory",
    blurb: "What one agent learns about a customer, every agent knows.",
  },
  {
    id: "knowledge",
    label: "Your documents",
    blurb: "One set of price lists, policies and FAQs answers every question.",
  },
  {
    id: "connections",
    label: "Connected accounts",
    blurb: "Your calendar, inbox and store connect once, not six times.",
  },
] as const;
