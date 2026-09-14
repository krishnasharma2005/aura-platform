"use client";

import * as React from "react";
import { motion, useReducedMotion } from "framer-motion";
import {
  Building2,
  CalendarCheck,
  Check,
  Loader2,
  Mail,
  MessageCircle,
  Search,
  ShoppingBag,
  Slack,
  Users,
  Wrench,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import type { ToolCall } from "@/lib/api-types";
import { chipIn, stillVariants } from "@/lib/motion";
import { cn } from "@/lib/utils";

/**
 * Tool names come back as machine strings. The owner never reads those — they
 * read "Checked your calendar". Match on the substring so a rename like
 * `calendar_find_slots` still lands on the right icon and the right verb.
 */
const TOOL_MAP: { match: string; icon: LucideIcon; label: string }[] = [
  { match: "calendar", icon: CalendarCheck, label: "Checked your calendar" },
  { match: "gmail", icon: Mail, label: "Checked your inbox" },
  { match: "email", icon: Mail, label: "Checked your inbox" },
  { match: "whatsapp", icon: MessageCircle, label: "Used WhatsApp" },
  { match: "slack", icon: Slack, label: "Posted to Slack" },
  { match: "hubspot", icon: Building2, label: "Looked up your CRM" },
  { match: "crm", icon: Building2, label: "Looked up your CRM" },
  { match: "shopify", icon: ShoppingBag, label: "Checked your store" },
  { match: "delegate", icon: Users, label: "Consulted a specialist" },
  { match: "knowledge", icon: Search, label: "Read your documents" },
  { match: "search", icon: Search, label: "Read your documents" },
];

function describe(name: string) {
  const key = name.toLowerCase();
  const hit = TOOL_MAP.find((t) => key.includes(t.match));
  if (hit) return hit;
  return { icon: Wrench, label: name.replace(/[_-]/g, " ") };
}

/**
 * What the agent actually reached for, surfaced as it happens. This is the
 * single best answer to "what is it doing with my data?" — it is not a log
 * buried in settings, it is right there in the conversation.
 */
export function ToolCallChip({ toolCall }: { toolCall: ToolCall }) {
  const reduce = useReducedMotion();
  const { icon: Icon, label } = describe(toolCall.name);
  const status = toolCall.status ?? "success";
  const text = toolCall.label ?? label;

  return (
    <motion.span
      variants={reduce ? stillVariants : chipIn}
      initial="hidden"
      animate="visible"
      exit="exit"
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-2xs font-semibold",
        status === "error"
          ? "border-destructive/25 bg-destructive/[0.08] text-destructive"
          : status === "pending"
          ? "border-border bg-secondary text-muted-foreground"
          : "border-border bg-secondary/70 text-muted-foreground"
      )}
    >
      {status === "pending" ? (
        <Loader2 className="h-3 w-3 animate-spin" strokeWidth={2.25} />
      ) : status === "error" ? (
        <XCircle className="h-3 w-3" strokeWidth={2.25} />
      ) : (
        <Icon className="h-3 w-3" strokeWidth={2} />
      )}
      <span className="capitalize">{text}</span>
      {status === "success" && <Check className="h-3 w-3 text-success" strokeWidth={2.75} />}
    </motion.span>
  );
}
