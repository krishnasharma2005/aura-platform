"use client";

import * as React from "react";
import { api } from "@/lib/api-client";
import { errorMessage } from "@/lib/utils";
import type { Integration } from "@/lib/api-types";
import { INTEGRATIONS } from "@/lib/integrations";
import { IntegrationCard } from "@/components/integrations/integration-card";
import { WebsiteChatPanel } from "@/components/integrations/website-chat-panel";
import { useToast } from "@/components/ui/use-toast";

export default function IntegrationsSettingsPage() {
  const { toast } = useToast();
  const [integrations, setIntegrations] = React.useState<Integration[]>([]);
  const [isLoading, setIsLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [connectingProvider, setConnectingProvider] = React.useState<string | null>(null);

  const load = React.useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await api.integrations.list();
      setIntegrations(data);
    } catch (err) {
      setError(
        errorMessage(err, "Couldn't load your integrations right now.")
      );
    } finally {
      setIsLoading(false);
    }
  }, []);

  React.useEffect(() => {
    load();
  }, [load]);

  async function handleConnect(provider: string) {
    setConnectingProvider(provider);
    try {
      const result = await api.integrations.connect(provider);
      if (result.status === "connected") {
        toast({ title: "Connected", description: "You're all set — your agents can now use this." });
      } else if (result.status === "coming_soon") {
        toast({
          title: "Not available yet",
          description: "We're still setting up this connection — reach out and we'll enable it for you.",
        });
      } else {
        toast({
          title: "Couldn't connect",
          description: "Something went wrong on our end. Please try again shortly.",
          variant: "destructive",
        });
      }
      load();
    } catch (err) {
      toast({
        title: "Couldn't connect",
        description:
          errorMessage(err, "Something went wrong. Please try again."),
        variant: "destructive",
      });
    } finally {
      setConnectingProvider(null);
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <p className="text-sm text-muted-foreground">
        Every connection below shows exactly what it lets your agents see and do before you turn it on. You
        can disconnect anything at any time.
      </p>

      {error && (
        <p className="rounded-md border border-destructive/25 bg-destructive/10 px-3.5 py-2.5 text-sm text-destructive">
          {error}
        </p>
      )}

      <WebsiteChatPanel />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {INTEGRATIONS.map((def) => (
          <IntegrationCard
            key={def.provider}
            definition={def}
            integration={integrations.find((i) => i.provider === def.provider)}
            onConnect={handleConnect}
            isConnecting={connectingProvider === def.provider || isLoading}
          />
        ))}
      </div>
    </div>
  );
}
