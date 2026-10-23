"use client";

import * as React from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api-client";
import { errorMessage } from "@/lib/utils";
import type { Integration } from "@/lib/api-types";
import { INTEGRATIONS, type IntegrationDefinition } from "@/lib/integrations";
import { IntegrationCard } from "@/components/integrations/integration-card";
import { ConnectKeyDialog } from "@/components/integrations/connect-key-dialog";
import { WebsiteChatPanel } from "@/components/integrations/website-chat-panel";
import { useToast } from "@/components/ui/use-toast";

// After the Google OAuth consent screen, Google redirects the browser back to
// the API, which redirects here with ?google_connect=success|denied|error.
// useSearchParams needs a Suspense boundary in the app router, so this reads
// the query and reports back via a callback rather than living inline in the
// page (which would force the whole page under Suspense for one query param).
function GoogleConnectResultListener({ onResult }: { onResult: (result: string) => void }) {
  const router = useRouter();
  const searchParams = useSearchParams();

  React.useEffect(() => {
    const result = searchParams.get("google_connect");
    if (!result) return;
    onResult(result);
    router.replace("/settings/integrations");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  return null;
}

export default function IntegrationsSettingsPage() {
  const { toast } = useToast();
  const [integrations, setIntegrations] = React.useState<Integration[]>([]);
  const [isLoading, setIsLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [connectingProvider, setConnectingProvider] = React.useState<string | null>(null);
  // Which app's "paste your key" form is open, if any.
  const [keyDialogFor, setKeyDialogFor] = React.useState<IntegrationDefinition | null>(null);

  const load = React.useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await api.integrations.list();
      setIntegrations(data);
    } catch (err) {
      setError(
        errorMessage(err, "We couldn't load your connections. Your work is saved. Try again.")
      );
    } finally {
      setIsLoading(false);
    }
  }, []);

  React.useEffect(() => {
    load();
  }, [load]);

  function handleGoogleConnectResult(result: string) {
    if (result === "success") {
      toast({ title: "Connected", description: "Google Calendar and Gmail are ready for your agents to use." });
      load();
    } else if (result === "denied") {
      toast({ title: "Not connected", description: "The Google connection was cancelled." });
    } else {
      toast({
        title: "Couldn't connect",
        description: "We couldn't connect Google. Your work is saved. Try again.",
        variant: "destructive",
      });
    }
  }

  async function handleDisconnect(provider: string) {
    const definition = INTEGRATIONS.find((i) => i.provider === provider);
    setConnectingProvider(provider);
    try {
      await api.integrations.disconnect(provider);
      toast({
        title: "Disconnected",
        description: `Your agents can no longer use ${definition?.displayName ?? "that app"}.`,
      });
      await load();
    } catch (err) {
      toast({
        title: "Couldn't disconnect",
        description: errorMessage(err, "Nothing was changed. Try again."),
        variant: "destructive",
      });
    } finally {
      setConnectingProvider(null);
    }
  }

  async function handleConnect(provider: string) {
    // Apps with no sign-in redirect ask for a key on a form instead.
    const definition = INTEGRATIONS.find((i) => i.provider === provider);
    if (definition?.credentials) {
      setKeyDialogFor(definition);
      return;
    }
    setConnectingProvider(provider);
    try {
      const result = await api.integrations.connect(provider);
      if (result.status === "redirect" && result.redirect_url) {
        window.location.href = result.redirect_url;
        return;
      }
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
          description: "We couldn't connect. Your work is saved. Try again shortly.",
          variant: "destructive",
        });
      }
      load();
    } catch (err) {
      toast({
        title: "Couldn't connect",
        description:
          errorMessage(err, "We couldn't connect. Your work is saved. Try again."),
        variant: "destructive",
      });
    } finally {
      setConnectingProvider(null);
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <React.Suspense fallback={null}>
        <GoogleConnectResultListener onResult={handleGoogleConnectResult} />
      </React.Suspense>

      <p className="text-sm text-muted-foreground">
        Every connection below shows exactly what it lets your agents see and do before you turn it on. You
        can disconnect anything at any time.
      </p>

      {error && (
        <p className="rounded-md border border-destructive/25 bg-destructive/10 px-3.5 py-2.5 text-sm text-destructive-ink">
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
            onDisconnect={handleDisconnect}
            isConnecting={connectingProvider === def.provider || isLoading}
          />
        ))}
      </div>

      <ConnectKeyDialog
        definition={keyDialogFor}
        open={keyDialogFor !== null}
        onOpenChange={(open) => !open && setKeyDialogFor(null)}
        onConnected={(definition) => {
          toast({
            title: `${definition.displayName} connected`,
            description: "You're all set — your agents can now use it.",
          });
          load();
        }}
      />
    </div>
  );
}
