"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Menu, ChevronsUpDown, LogOut, Plug, UserRound } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { getAgentBySlug } from "@/lib/agents";
import { initials } from "@/lib/utils";
import { ApprovalsTray } from "@/components/approvals/approvals-tray";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

const SECTION_LABELS: Record<string, string> = {
  // The route is /analytics; the word the owner sees is "Results".
  analytics: "Results",
  conversations: "Conversations",
  workflows: "Workflows",
  knowledge: "Knowledge",
  activity: "Activity",
  settings: "Settings",
};

/** Names the current location in the same words the sidebar uses. */
function useCurrentSection(): string | null {
  const pathname = usePathname();
  const first = pathname.split("/").filter(Boolean)[0];
  if (!first) return null;
  return getAgentBySlug(first)?.displayName ?? SECTION_LABELS[first] ?? null;
}

export function Topbar({ onMenuClick }: { onMenuClick?: () => void }) {
  const { user, organization, logout } = useAuth();
  const section = useCurrentSection();

  return (
    <header className="sticky top-0 z-30 flex h-14 shrink-0 items-center justify-between border-b border-border/80 bg-background/85 px-3 backdrop-blur-md sm:px-5">
      <div className="flex min-w-0 items-center gap-1">
        <Button
          variant="ghost"
          size="icon"
          className="md:hidden"
          onClick={onMenuClick}
          aria-label="Open menu"
        >
          <Menu className="h-5 w-5" strokeWidth={1.75} />
        </Button>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button className="press tap-h flex min-w-0 items-center gap-1.5 rounded-md px-2 py-1.5 text-sm font-semibold text-foreground hover:bg-secondary/70">
              <span className="max-w-[9rem] truncate sm:max-w-xs">
                {organization?.name ?? "Your workspace"}
              </span>
              <ChevronsUpDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start">
            <DropdownMenuLabel>Workspace</DropdownMenuLabel>
            <DropdownMenuItem disabled>{organization?.name ?? "Not set up yet"}</DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem asChild>
              <Link href="/settings">Manage workspace</Link>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        {section && (
          <span className="hidden min-w-0 items-center gap-2 sm:flex">
            <span className="text-subtle">/</span>
            <span className="truncate text-sm text-muted-foreground">{section}</span>
          </span>
        )}
      </div>

      <div className="flex items-center gap-2">
        <ApprovalsTray />

        <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            className="press tap flex items-center justify-center rounded-full ring-offset-background transition-shadow hover:shadow-ringed"
            aria-label="Account menu"
          >
            <Avatar className="h-8 w-8">
              <AvatarFallback className="text-2xs font-semibold">
                {user ? initials(user.full_name || user.email) : "?"}
              </AvatarFallback>
            </Avatar>
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-60">
          <DropdownMenuLabel className="font-normal">
            <p className="truncate text-sm font-semibold text-foreground">
              {user?.full_name || "Your account"}
            </p>
            <p className="truncate text-xs text-muted-foreground">{user?.email}</p>
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem asChild>
            <Link href="/settings" className="flex items-center gap-2">
              <UserRound className="h-4 w-4" strokeWidth={1.75} /> Account
            </Link>
          </DropdownMenuItem>
          <DropdownMenuItem asChild>
            <Link href="/settings/integrations" className="flex items-center gap-2">
              <Plug className="h-4 w-4" strokeWidth={1.75} /> Connections
            </Link>
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            onClick={logout}
            className="flex items-center gap-2 text-destructive focus:text-destructive"
          >
            <LogOut className="h-4 w-4" strokeWidth={1.75} /> Sign out
          </DropdownMenuItem>
        </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
