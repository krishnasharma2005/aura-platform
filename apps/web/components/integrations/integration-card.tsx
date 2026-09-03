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
  isConnecting,
}: {
  definition: IntegrationDefinition;
  integration: Integration | undefined;
  onConnect: (provider: string) => void;
  isConnecting: boolean;
}) {
  const Icon = definition.icon;
  const isConnected = integration?.status === "connected";

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
              <Icon className="h-5 w-5" strokeWidth={1.75} />
            </span>
            <div>
              <CardTitle className="text-base">{definition.displayName}</CardTitle>
              {isConnected ? (
                <Badge variant="success" className="mt-1">
                  <Check className="h-3 w-3" /> Connected
                </Badge>
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
            <ShieldCheck className="h-3.5 w-3.5 text-primary" /> What this lets your agents do
          </div>
          <ul className="flex flex-col gap-1.5">
            {definition.canDo.map((item) => (
              <li key={item} className="flex gap-2 text-xs text-muted-foreground">
                <Check className="mt-0.5 h-3 w-3 shrink-0 text-success" />
                <span>{item}</span>
              </li>
            ))}
          </ul>
          <ul className="flex flex-col gap-1.5 border-t border-border pt-2.5">
            {definition.cannotDo.map((item) => (
              <li key={item} className="flex gap-2 text-xs text-muted-foreground">
                <X className="mt-0.5 h-3 w-3 shrink-0 text-destructive/70" />
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </div>

        {definition.availableNow ? (
          <Button
            variant={isConnected ? "outline" : "default"}
            className="w-full"
            disabled={isConnecting}
            onClick={() => onConnect(definition.provider)}
          >
            {isConnecting ? "Connecting…" : isConnected ? "Reconnect" : "Connect"}
          </Button>
        ) : (
          <Button variant="secondary" className="w-full" disabled>
            Coming soon — contact us to enable
          </Button>
        )}
      </CardContent>
    </Card>
  );
}
