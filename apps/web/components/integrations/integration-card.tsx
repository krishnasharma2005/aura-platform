"use client";

import * as React from "react";
import { Check, ShieldCheck, X } from "lucide-react";
import type { IntegrationDefinition } from "@/lib/integrations";
import type { Integration } from "@/lib/api-types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

export function IntegrationCard({
  definition,
  integration,
  onConnect,
  onDisconnect,
  isConnecting,
}: {
  definition: IntegrationDefinition;
  integration: Integration | undefined;
  onConnect: (provider: string) => void;
  onDisconnect: (provider: string) => void;
  isConnecting: boolean;
}) {
  const Icon = definition.icon;
  const isConnected = integration?.status === "connected";
  // Disconnecting stops agents using the account straight away, so it takes two
  // deliberate clicks rather than one.
  const [confirmingDisconnect, setConfirmingDisconnect] = React.useState(false);
  const isGoogle = definition.provider === "google_calendar" || definition.provider === "gmail";

  return (
    /*
      The permission lists are different lengths per provider, so side-by-side
      cards used to end at different heights and their Connect buttons sat on
      different baselines — the row read as misaligned rather than as a set.
      The card fills the grid row and the button is pushed to the bottom.
    */
    <Card className="flex h-full flex-col">
      <CardHeader>
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-md bg-secondary text-foreground">
              <Icon className="h-5 w-5" strokeWidth={1.5} />
            </span>
            <div>
              <CardTitle className="text-base">{definition.displayName}</CardTitle>
              {isConnected ? (
                <div className="mt-1 flex flex-col gap-0.5">
                  <Badge variant="success">
                    <Check className="h-3 w-3" /> Connected
                  </Badge>
                  {integration?.account_label && (
                    <span className="text-xs text-muted-foreground">{integration.account_label}</span>
                  )}
                </div>
              ) : definition.availableNow ? (
                <Badge variant="secondary" className="mt-1">Not connected</Badge>
              ) : (
                <Badge variant="outline" className="mt-1">Coming soon</Badge>
              )}
            </div>
          </div>
        </div>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col">
        <div className="mb-4 flex flex-1 flex-col gap-2.5 rounded-md bg-secondary/40 p-3.5">
          <div className="flex items-center gap-1.5 text-xs font-medium text-foreground">
            <ShieldCheck className="h-3.5 w-3.5 text-primary-ink" /> What this lets your agents do
          </div>
          <ul className="flex flex-col gap-1.5">
            {definition.canDo.map((item) => (
              <li key={item} className="flex gap-2 text-xs text-muted-foreground">
                <Check className="mt-0.5 h-3 w-3 shrink-0 text-success-ink" />
                <span>{item}</span>
              </li>
            ))}
          </ul>
          <ul className="flex flex-col gap-1.5 border-t border-border pt-2.5">
            {definition.cannotDo.map((item) => (
              <li key={item} className="flex gap-2 text-xs text-muted-foreground">
                <X className="mt-0.5 h-3 w-3 shrink-0 text-destructive-ink/70" />
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </div>

        {definition.availableNow ? (
          <div className="flex flex-col gap-2">
            <Button
              variant={isConnected ? "outline" : "default"}
              className="w-full"
              disabled={isConnecting}
              onClick={() => onConnect(definition.provider)}
            >
              {isConnecting ? "Connecting…" : isConnected ? "Reconnect" : "Connect"}
            </Button>

            {isConnected &&
              (confirmingDisconnect ? (
                <div className="flex flex-col gap-2 rounded-md border border-border bg-secondary/40 p-3">
                  <p className="text-xs leading-relaxed text-muted-foreground">
                    {isGoogle
                      ? "This disconnects both Calendar and Gmail, and your agents lose access straight away."
                      : `Your agents lose access to ${definition.displayName} straight away.`}
                  </p>
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      variant="destructive"
                      className="flex-1"
                      onClick={() => {
                        setConfirmingDisconnect(false);
                        onDisconnect(definition.provider);
                      }}
                    >
                      Yes, disconnect
                    </Button>
                    <Button
                      size="sm"
                      variant="secondary"
                      className="flex-1"
                      onClick={() => setConfirmingDisconnect(false)}
                    >
                      Keep it
                    </Button>
                  </div>
                </div>
              ) : (
                <Button
                  size="sm"
                  variant="ghost"
                  className="w-full text-muted-foreground"
                  onClick={() => setConfirmingDisconnect(true)}
                >
                  Disconnect
                </Button>
              ))}
          </div>
        ) : (
          <Button variant="secondary" className="w-full" disabled>
            Coming soon — contact us to enable
          </Button>
        )}
      </CardContent>
    </Card>
  );
}
