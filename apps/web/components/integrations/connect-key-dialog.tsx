"use client";

import * as React from "react";
import { ShieldCheck } from "lucide-react";
import { api } from "@/lib/api-client";
import { errorMessage } from "@/lib/utils";
import type { IntegrationDefinition } from "@/lib/integrations";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

/**
 * "Connect with a key" for the apps that have no sign-in redirect (WhatsApp,
 * Slack, HubSpot, Shopify). The owner makes a key in the other app and pastes
 * it here.
 *
 * Two things matter here more than looks: the server checks the key against the
 * other app before saving, so a wrong one is explained on this screen instead of
 * failing later inside a workflow; and the secret is never shown again — not in
 * this form after closing, and not on the card.
 */
export function ConnectKeyDialog({
  definition,
  open,
  onOpenChange,
  onConnected,
}: {
  definition: IntegrationDefinition | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConnected: (definition: IntegrationDefinition) => void;
}) {
  const form = definition?.credentials;
  const [values, setValues] = React.useState<Record<string, string>>({});
  const [error, setError] = React.useState<string | null>(null);
  const [isSaving, setIsSaving] = React.useState(false);

  // A fresh, empty form every time it opens: never leave a pasted secret in memory
  // after the dialog is dismissed.
  React.useEffect(() => {
    if (open) {
      setValues({});
      setError(null);
      setIsSaving(false);
    }
  }, [open, definition?.provider]);

  if (!definition || !form) return null;

  const isComplete = form.fields.every((field) => (values[field.name] ?? "").trim().length > 0);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!definition || !form || isSaving || !isComplete) return;
    setError(null);
    setIsSaving(true);
    try {
      const trimmed = Object.fromEntries(Object.entries(values).map(([key, value]) => [key, value.trim()]));
      await api.integrations.connectWithKey(definition.provider, form.tokenField, trimmed);
      setValues({});
      onOpenChange(false);
      onConnected(definition);
    } catch (err) {
      // The server's message already says what to fix ("Shopify didn't accept
      // that access token…") — show it as written.
      setError(errorMessage(err, "We couldn't connect that just now. Please check the details and try again."));
    } finally {
      setIsSaving(false);
    }
  }

  const Icon = definition.icon;

  return (
    <Dialog open={open} onOpenChange={(next) => !isSaving && onOpenChange(next)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2.5">
            <span className="flex h-8 w-8 items-center justify-center rounded-md bg-secondary text-foreground">
              <Icon className="h-4 w-4" strokeWidth={1.75} />
            </span>
            Connect {definition.displayName}
          </DialogTitle>
          <DialogDescription>{form.intro}</DialogDescription>
        </DialogHeader>

        <form onSubmit={submit} className="flex flex-col gap-4" autoComplete="off">
          {form.fields.map((field, index) => (
            <div key={field.name} className="flex flex-col gap-1.5">
              <Label htmlFor={`connect-${definition.provider}-${field.name}`}>{field.label}</Label>
              <Input
                id={`connect-${definition.provider}-${field.name}`}
                type={field.secret ? "password" : "text"}
                value={values[field.name] ?? ""}
                onChange={(e) => setValues((current) => ({ ...current, [field.name]: e.target.value }))}
                placeholder={field.placeholder}
                autoComplete="off"
                autoCapitalize="off"
                autoCorrect="off"
                spellCheck={false}
                autoFocus={index === 0}
                disabled={isSaving}
                aria-describedby={`connect-${definition.provider}-${field.name}-help`}
              />
              <p id={`connect-${definition.provider}-${field.name}-help`} className="text-xs leading-relaxed text-muted-foreground">
                {field.help}
              </p>
            </div>
          ))}

          {error && (
            <p role="alert" className="rounded-md border border-destructive/25 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {error}
            </p>
          )}

          <p className="flex items-start gap-2 text-xs leading-relaxed text-muted-foreground">
            <ShieldCheck className="mt-px h-3.5 w-3.5 shrink-0 text-primary" strokeWidth={1.75} />
            We check it works before saving it, store it encrypted, and never show it again. You can disconnect any
            time.
          </p>

          <DialogFooter>
            <Button type="button" variant="secondary" onClick={() => onOpenChange(false)} disabled={isSaving}>
              Cancel
            </Button>
            <Button type="submit" loading={isSaving} disabled={!isComplete || isSaving}>
              {isSaving ? "Checking…" : "Connect"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
