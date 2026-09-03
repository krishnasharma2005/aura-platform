"use client";

import { useEffect } from "react";
import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function DashboardError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 px-6 text-center">
      <span className="flex h-11 w-11 items-center justify-center rounded-full bg-destructive/10 text-destructive">
        <AlertTriangle className="h-5 w-5" />
      </span>
      <p className="font-display text-lg font-medium text-foreground">Something went wrong</p>
      <p className="max-w-sm text-sm text-muted-foreground">
        This page ran into a problem. Your data is safe — try again, and contact us if it keeps happening.
      </p>
      <Button onClick={reset} className="mt-1">
        Try again
      </Button>
    </div>
  );
}
