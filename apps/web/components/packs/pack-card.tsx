"use client";

import * as React from "react";
import { ShieldCheck } from "lucide-react";
import type { Pack } from "@/lib/api-types";
import { iconForPackCategory } from "@/lib/packs";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";

export function PackCard({
  pack,
  onToggle,
  isBusy,
}: {
  pack: Pack;
  onToggle: (pack: Pack, next: boolean) => void;
  isBusy: boolean;
}) {
  const Icon = iconForPackCategory(pack.category);

  return (
    <Card className="flex h-full flex-col">
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-md bg-secondary text-foreground">
              <Icon className="h-5 w-5" strokeWidth={1.75} />
            </span>
            <div>
              <CardTitle className="text-base">{pack.name}</CardTitle>
              <Badge variant={pack.active ? "success" : "secondary"} className="mt-1">
                {pack.active ? "Active" : "Not active"}
              </Badge>
            </div>
          </div>
          <Switch
            checked={pack.active}
            onCheckedChange={(next) => onToggle(pack, next)}
            disabled={isBusy}
            label={pack.active ? `Deactivate ${pack.name}` : `Activate ${pack.name}`}
          />
        </div>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-3">
        <p className="text-sm text-muted-foreground">{pack.description}</p>
        {pack.capability_requirements.length > 0 && (
          <div className="mt-auto flex flex-col gap-2 rounded-md bg-secondary/40 p-3.5">
            <div className="flex items-center gap-1.5 text-xs font-medium text-foreground">
              <ShieldCheck className="h-3.5 w-3.5 text-primary" /> Works best with
            </div>
            <div className="flex flex-wrap gap-1.5">
              {pack.capability_requirements.map((cap) => (
                <Badge key={cap} variant="outline">
                  {cap}
                </Badge>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
