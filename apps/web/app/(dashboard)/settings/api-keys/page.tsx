import { KeyRound } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

export default function ApiKeysSettingsPage() {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">API keys</CardTitle>
        <CardDescription>
          For connecting AURA to your own tools directly. Most businesses won&apos;t need this — the
          Integrations tab covers the common connections.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="flex flex-col items-center gap-3 rounded-md border border-dashed border-border px-4 py-10 text-center">
          <span className="flex h-10 w-10 items-center justify-center rounded-full bg-secondary text-muted-foreground">
            <KeyRound className="h-5 w-5" strokeWidth={1.75} />
          </span>
          <div>
            <p className="text-sm font-medium text-foreground">No API keys yet</p>
            <p className="mt-1 max-w-sm text-sm text-muted-foreground">
              Generate a key if you&apos;re building a custom integration with AURA. Reach out to support if
              you&apos;re not sure whether you need one.
            </p>
          </div>
          {/*
            The control is disabled because self-serve key generation is not
            built yet. A disabled button with no explanation reads as broken,
            so the reason and the way round it sit directly underneath.
          */}
          <div className="flex flex-col items-center gap-2">
            <Button variant="secondary" disabled>
              Generate API key
            </Button>
            <p className="max-w-xs text-xs leading-relaxed text-subtle">
              Self-serve keys aren&apos;t available yet. Contact support and we&apos;ll issue one
              for your workspace.
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
