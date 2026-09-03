"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { ApprovalsProvider } from "@/lib/approvals-context";
import { Sidebar } from "@/components/layout/sidebar";
import { Topbar } from "@/components/layout/topbar";
import { Sheet, SheetContent } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { AuraLogo } from "@/components/runtime/aura-mark";

/**
 * While we check the stored session we render the workspace's own silhouette
 * rather than a spinner, so the transition into the real thing is a fill, not
 * a swap. Nothing moves when the data arrives.
 */
function WorkspaceSkeleton() {
  return (
    <div className="flex h-screen overflow-hidden bg-background">
      <div className="hidden w-64 shrink-0 flex-col border-r border-sidebar-border bg-sidebar px-4 py-5 md:flex">
        <AuraLogo tone="onDark" />
        <div className="mt-8 flex flex-col gap-2.5">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-6 w-full bg-white/[0.06]" />
          ))}
        </div>
      </div>
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex h-14 items-center border-b border-border/80 px-5">
          <Skeleton className="h-5 w-40" />
        </div>
        <div className="mx-auto w-full max-w-6xl px-5 py-8 sm:px-8 sm:py-10">
          <Skeleton className="h-8 w-64" />
          <Skeleton className="mt-3 h-3.5 w-96 max-w-full" />
          <Skeleton className="mt-8 aspect-[2/1] w-full rounded-xl" />
        </div>
      </div>
      <span className="sr-only" role="status">
        Loading your workspace
      </span>
    </div>
  );
}

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { isAuthenticated, isLoading } = useAuth();
  const [mobileOpen, setMobileOpen] = React.useState(false);

  React.useEffect(() => {
    if (!isLoading && !isAuthenticated) router.replace("/login");
  }, [isLoading, isAuthenticated, router]);

  if (isLoading || !isAuthenticated) return <WorkspaceSkeleton />;

  return (
    <ApprovalsProvider>
      <div className="flex h-screen overflow-hidden bg-background">
        <div className="hidden md:block">
          <Sidebar />
        </div>

        <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
          <SheetContent side="left" className="w-64 border-sidebar-border bg-sidebar p-0">
            <Sidebar onNavigate={() => setMobileOpen(false)} />
          </SheetContent>
        </Sheet>

        <div className="flex min-w-0 flex-1 flex-col">
          <Topbar onMenuClick={() => setMobileOpen(true)} />
          <main className="min-w-0 flex-1 overflow-y-auto scrollbar-thin">{children}</main>
        </div>
      </div>
    </ApprovalsProvider>
  );
}
