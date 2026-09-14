"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const TABS = [
  { href: "/settings", label: "General" },
  { href: "/settings/business", label: "Business" },
  { href: "/settings/packs", label: "Packs" },
  { href: "/settings/members", label: "Members" },
  { href: "/settings/integrations", label: "Integrations" },
  { href: "/settings/api-keys", label: "API keys" },
];

export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="mx-auto max-w-4xl px-6 py-8">
      <div className="mb-6">
        <h1 className="font-display text-2xl font-medium text-foreground">Settings</h1>
        <p className="mt-1 text-sm text-muted-foreground">Manage your workspace, team, and connections.</p>
      </div>

      {/*
        Four tabs at their natural width just fit a 390px phone and just miss
        a 360px one. Rather than shrink the labels, the strip scrolls — the
        row keeps its full-size targets and nothing is ever cut off.
      */}
      <div className="scrollbar-thin mb-6 flex gap-1 overflow-x-auto border-b border-border">
        {TABS.map((tab) => {
          const active = pathname === tab.href;
          return (
            <Link
              key={tab.href}
              href={tab.href}
              className={cn(
                "tap-h inline-flex shrink-0 items-center whitespace-nowrap border-b-2 px-3 pb-2.5 text-sm font-medium transition-colors",
                active
                  ? "border-primary text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              )}
            >
              {tab.label}
            </Link>
          );
        })}
      </div>

      {children}
    </div>
  );
}
