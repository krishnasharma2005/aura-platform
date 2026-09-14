"use client";

import * as React from "react";
import { api } from "@/lib/api-client";
import { errorMessage } from "@/lib/utils";
import { useAuth } from "@/lib/auth-context";
import type { Pack } from "@/lib/api-types";
import { PackCard } from "@/components/packs/pack-card";
import { useToast } from "@/components/ui/use-toast";
import { Skeleton } from "@/components/ui/skeleton";

export default function PacksSettingsPage() {
  const { organization } = useAuth();
  const { toast } = useToast();
  const [packs, setPacks] = React.useState<Pack[]>([]);
  const [isLoading, setIsLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [busyPackId, setBusyPackId] = React.useState<string | null>(null);

  const load = React.useCallback(async () => {
    if (!organization) return;
    setIsLoading(true);
    setError(null);
    try {
      const data = await api.packs.list(organization.id);
      setPacks(data);
    } catch (err) {
      setError(errorMessage(err, "Couldn't load your packs right now."));
    } finally {
      setIsLoading(false);
    }
  }, [organization]);

  React.useEffect(() => {
    load();
  }, [load]);

  async function handleToggle(pack: Pack, next: boolean) {
    if (!organization) return;
    setBusyPackId(pack.id);
    try {
      const updated = next
        ? await api.packs.activate(organization.id, pack.id)
        : await api.packs.deactivate(organization.id, pack.id);
      setPacks((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
      toast({
        title: next ? "Pack activated" : "Pack deactivated",
        description: next
          ? `${pack.name} is now tuning your agents.`
          : `${pack.name} no longer affects your agents.`,
      });
    } catch (err) {
      toast({
        title: "Couldn't update that pack",
        description: errorMessage(err, "Something went wrong. Please try again."),
        variant: "destructive",
      });
    } finally {
      setBusyPackId(null);
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <p className="text-sm text-muted-foreground">
        Packs tune your Receptionist, Sales, Marketing, and Executive Assistant with extra guidance for
        your industry — no new agents, nothing your base plan couldn&apos;t already do. Free to try for now;
        pricing is coming.
      </p>

      {error && (
        <p className="rounded-md border border-destructive/25 bg-destructive/10 px-3.5 py-2.5 text-sm text-destructive">
          {error}
        </p>
      )}

      {isLoading ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {[0, 1].map((i) => (
            <Skeleton key={i} className="h-56 w-full rounded-lg" />
          ))}
        </div>
      ) : packs.length === 0 ? (
        <p className="text-sm text-muted-foreground">No packs are available yet.</p>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {packs.map((pack) => (
            <PackCard key={pack.id} pack={pack} onToggle={handleToggle} isBusy={busyPackId === pack.id} />
          ))}
        </div>
      )}
    </div>
  );
}
