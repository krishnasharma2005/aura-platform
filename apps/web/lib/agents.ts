import type { AgentSlug } from "./api-types";
import {
  PhoneCall,
  TrendingUp,
  Megaphone,
  CalendarClock,
  LifeBuoy,
  ShoppingBag,
  type LucideIcon,
} from "lucide-react";

export interface AgentDefinition {
  slug: AgentSlug;
  displayName: string;
  shortLabel: string;
  tagline: string;
  icon: LucideIcon;
  emptyStateTitle: string;
  emptyStateBody: string;
  suggestedPrompts: string[];
  composerPlaceholder: string;
}

export const AGENTS: AgentDefinition[] = [
  {
    slug: "receptionist",
    displayName: "Receptionist",
    shortLabel: "Receptionist",
    tagline: "Answers calls and messages, books appointments, never misses a request.",
    icon: PhoneCall,
    emptyStateTitle: "No conversations yet",
    emptyStateBody:
      "Once your Receptionist is live, patient and client messages from your phone line, WhatsApp, or website will show up here — with bookings and reschedules handled automatically. Try asking it something a patient might, like below.",
    suggestedPrompts: [
      "Do you have any openings this week for a cleaning?",
      "I need to reschedule my 2pm on Thursday.",
      "What are your hours on Saturday?",
    ],
    composerPlaceholder: "Message the Receptionist, as a patient or client would…",
  },
  {
    slug: "sales",
    displayName: "Sales",
    shortLabel: "Sales",
    tagline: "Qualifies leads, follows up, and keeps deals from going cold.",
    icon: TrendingUp,
    emptyStateTitle: "No conversations yet",
    emptyStateBody:
      "Your Sales agent will greet new leads, ask qualifying questions, and hand off warm ones to you. Give it a test lead below to see how it responds.",
    suggestedPrompts: [
      "Hi, I saw your ad — how much does this cost?",
      "Can someone call me back about a quote?",
      "What's included in your starter package?",
    ],
    composerPlaceholder: "Message the Sales agent, as a prospective customer would…",
  },
  {
    slug: "marketing",
    displayName: "Marketing",
    shortLabel: "Marketing",
    tagline: "Drafts campaigns, social posts, and promotions in your voice.",
    icon: Megaphone,
    emptyStateTitle: "No campaigns started yet",
    emptyStateBody:
      "Ask your Marketing agent to draft an email, a social caption, or a promo idea, and it'll write a first draft for you to review — nothing goes out without your approval.",
    suggestedPrompts: [
      "Write a short email announcing our fall promotion.",
      "Give me three Instagram caption ideas for this week.",
      "Draft a follow-up message for customers who haven't visited in 6 months.",
    ],
    composerPlaceholder: "Ask Marketing to draft something…",
  },
  {
    slug: "executive-assistant",
    displayName: "Executive Assistant",
    shortLabel: "Exec. Assistant",
    tagline: "Manages your calendar, inbox triage, and daily priorities.",
    icon: CalendarClock,
    emptyStateTitle: "No requests yet",
    emptyStateBody:
      "Your Executive Assistant can check your calendar, draft replies, and summarize what needs your attention today. Try asking it to plan your day.",
    suggestedPrompts: [
      "What's on my calendar tomorrow?",
      "Summarize my unread emails from this morning.",
      "Block two hours Friday afternoon for client calls.",
    ],
    composerPlaceholder: "Ask your Executive Assistant…",
  },
  {
    slug: "support",
    displayName: "Support",
    shortLabel: "Support",
    tagline: "Answers customer questions and resolves common issues instantly.",
    icon: LifeBuoy,
    emptyStateTitle: "No conversations yet",
    emptyStateBody:
      "Support handles common customer questions using your knowledge base and escalates anything it's unsure about to you. Test it with a real customer question.",
    suggestedPrompts: [
      "My order hasn't arrived yet — can you check on it?",
      "How do I return an item I bought last week?",
      "Is your service available in my area?",
    ],
    composerPlaceholder: "Message Support, as a customer would…",
  },
  {
    slug: "ecommerce",
    displayName: "E-Commerce Intelligence",
    shortLabel: "E-Commerce",
    tagline: "Watches your store's sales, inventory, and trends — and flags what matters.",
    icon: ShoppingBag,
    emptyStateTitle: "No insights yet",
    emptyStateBody:
      "Once connected to your store, this agent will surface things like slow-moving inventory, best sellers, and abandoned-cart trends. Ask it a question about your store to see how it responds.",
    suggestedPrompts: [
      "What were my best-selling products last week?",
      "Which items are running low on stock?",
      "How did this month's sales compare to last month?",
    ],
    composerPlaceholder: "Ask about your store's performance…",
  },
];

export function getAgentBySlug(slug: string): AgentDefinition | undefined {
  return AGENTS.find((a) => a.slug === slug);
}
