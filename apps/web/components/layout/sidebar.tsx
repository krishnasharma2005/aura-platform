"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion, useReducedMotion } from "framer-motion";
import {
  BarChart3,
  BookOpen,
  ListChecks,
  MessagesSquare,
  Repeat,
  Settings,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";
import { AGENTS } from "@/lib/agents";
import { AuraLogo } from "@/components/runtime/aura-mark";
import { cn } from "@/lib/utils";

const WORKSPACE_LINKS = [
  // Results first: it is the answer to "was this worth it", and it should be
  // the first thing in reach every time the owner opens the product.
  { href: "/analytics", label: "Results", icon: BarChart3 },
  { href: "/conversations", label: "Conversations", icon: MessagesSquare },
  { href: "/workflows", label: "Workflows", icon: Repeat },
  { href: "/knowledge", label: "Knowledge", icon: BookOpen },
  { href: "/activity", label: "Activity", icon: ListChecks },
  { href: "/settings", label: "Settings", icon: Settings },
];

/**
 * The instrument panel. It stays graphite in both themes so the product reads
 * as one machine regardless of appearance mode, and so the paper working area
 * beside it feels like a lit surface rather than the whole screen.
 *
 * The active row is marked by a single shared indicator that physically slides
 * between items rather than one highlight switching off and another switching
 * on. That continuity is what tells you where you moved from.
 */
function NavRow({
  href,
  label,
  icon: Icon,
  active,
  onNavigate,
  layoutId,
}: {
  href: string;
  label: string;
  icon: LucideIcon;
  active: boolean;
  onNavigate?: () => void;
  layoutId: string;
}) {
  const reduce = useReducedMotion();

  return (
    <li>
      <Link
        href={href}
        onClick={onNavigate}
        aria-current={active ? "page" : undefined}
        className={cn(
          "press tap-h group relative flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm font-medium",
          active
            ? "text-sidebar-foreground"
            : "text-sidebar-muted hover:bg-white/[0.04] hover:text-sidebar-foreground"
        )}
      >
        {active && (
          <motion.span
            layoutId={reduce ? undefined : layoutId}
            className="absolute inset-0 rounded-md bg-sidebar-active shadow-[inset_0_1px_0_0_hsl(0_0%_100%/0.05)]"
            transition={{ type: "spring", stiffness: 480, damping: 40 }}
          />
        )}
        {active && (
          <span className="absolute left-0 top-1/2 h-4 w-[2px] -translate-y-1/2 rounded-full bg-primary" />
        )}
        <Icon
          className={cn(
            "relative h-4 w-4 shrink-0 transition-transform duration-200 ease-physical",
            !active && "group-hover:translate-x-0.5"
          )}
          strokeWidth={1.75}
        />
        <span className="relative truncate">{label}</span>
      </Link>
    </li>
  );
}

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();

  return (
    <nav className="flex h-full w-64 shrink-0 flex-col border-r border-sidebar-border bg-sidebar text-sidebar-foreground">
      <div className="px-4 py-5">
        <Link href="/" onClick={onNavigate} className="press tap-h inline-flex items-center rounded-md">
          <AuraLogo tone="onDark" />
        </Link>
      </div>

      <div className="flex-1 overflow-y-auto px-3 pb-4 scrollbar-thin">
        <p className="px-2.5 pb-2 pt-2 font-mono text-[10px] uppercase tracking-[0.14em] text-sidebar-muted">
          Agents
        </p>
        <ul className="flex flex-col gap-0.5">
          {AGENTS.map((agent) => (
            <NavRow
              key={agent.slug}
              href={`/${agent.slug}`}
              label={agent.shortLabel}
              icon={agent.icon}
              active={pathname === `/${agent.slug}`}
              onNavigate={onNavigate}
              layoutId="sidebar-active"
            />
          ))}
        </ul>

        <p className="px-2.5 pb-2 pt-5 font-mono text-[10px] uppercase tracking-[0.14em] text-sidebar-muted">
          Workspace
        </p>
        <ul className="flex flex-col gap-0.5">
          {WORKSPACE_LINKS.map((link) => (
            <NavRow
              key={link.href}
              href={link.href}
              label={link.label}
              icon={link.icon}
              active={pathname === link.href || pathname.startsWith(`${link.href}/`)}
              onNavigate={onNavigate}
              layoutId="sidebar-active"
            />
          ))}
        </ul>
      </div>

      {/*
        The trust line sits at the bottom of every screen in the product on
        purpose: the buyer's first objection is "what can this see?", and the
        answer should never be more than one glance away.
      */}
      <div className="border-t border-sidebar-border px-4 py-3.5">
        <Link
          href="/activity"
          onClick={onNavigate}
          className="press group flex items-start gap-2 text-xs leading-relaxed text-sidebar-muted hover:text-sidebar-foreground"
        >
          <ShieldCheck
            className="mt-px h-3.5 w-3.5 shrink-0 text-primary/80 transition-transform duration-200 ease-physical group-hover:scale-110"
            strokeWidth={1.75}
          />
          <span>
            Every action your agents take is logged in{" "}
            <span className="font-medium text-sidebar-foreground/90 underline-offset-2 group-hover:underline">
              Activity
            </span>
            .
          </span>
        </Link>
      </div>
    </nav>
  );
}
