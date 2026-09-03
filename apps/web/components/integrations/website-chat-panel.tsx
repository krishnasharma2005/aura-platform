"use client";

import * as React from "react";
import { Check, Copy, Globe, RefreshCcw } from "lucide-react";
import { api } from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { useToast } from "@/components/ui/use-toast";
import { errorMessage } from "@/lib/utils";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const WEB_URL = process.env.NEXT_PUBLIC_WEB_URL ?? (typeof window !== "undefined" ? window.location.origin : "");

function scriptTagFor(publicId: string): string {
  return `<script src="${WEB_URL}/widget.js" data-org="${publicId}" data-api="${API_URL}" defer></script>`;
}

/**
 * "Add chat to your website" — the copy-paste embed panel.
 *
 * Deliberately not called "widget" or "embed" anywhere a customer sees it
 * (docs/customer-profile.md: no jargon, non-technical owner). One script
 * tag, their own public id already filled in, a copy button, and a live
 * preview so they can see what a visitor sees before they touch their site.
 */
export function WebsiteChatPanel() {
  const { organization } = useAuth();
  const { toast } = useToast();

  const [publicId, setPublicId] = React.useState<string | null>(null);
  const [enabled, setEnabled] = React.useState(true);
  const [isLoading, setIsLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [isBusy, setIsBusy] = React.useState(false);
  const [copied, setCopied] = React.useState(false);

  const load = React.useCallback(async () => {
    if (!organization?.id) return;
    setIsLoading(true);
    setError(null);
    try {
      const org = await api.organizations.get(organization.id);
      setPublicId(org.public_id ?? null);
      setEnabled(org.public_chat_enabled ?? true);
    } catch (err) {
      setError(errorMessage(err, "Couldn't load your website chat settings right now."));
    } finally {
      setIsLoading(false);
    }
  }, [organization?.id]);

  React.useEffect(() => {
    load();
  }, [load]);

  async function handleToggle(next: boolean) {
    if (!organization?.id) return;
    setIsBusy(true);
    const previous = enabled;
    setEnabled(next); // optimistic — this is a simple on/off, not a decision worth a spinner delay
    try {
      const org = next
        ? await api.organizations.enablePublicChat(organization.id)
        : await api.organizations.disablePublicChat(organization.id);
      setPublicId(org.public_id ?? null);
      setEnabled(org.public_chat_enabled ?? next);
    } catch (err) {
      setEnabled(previous);
      toast({
        title: "Couldn't update this",
        description: errorMessage(err, "Please try again."),
        variant: "destructive",
      });
    } finally {
      setIsBusy(false);
    }
  }

  async function handleGetNewCode() {
    if (!organization?.id) return;
    if (!window.confirm("This replaces your current chat code. The old one will stop working on your site — you'll need to paste the new one in its place. Continue?")) {
      return;
    }
    setIsBusy(true);
    try {
      const org = await api.organizations.rotatePublicChatId(organization.id);
      setPublicId(org.public_id ?? null);
      toast({ title: "New code ready", description: "Copy it below and replace the old one on your site." });
    } catch (err) {
      toast({ title: "Couldn't generate a new code", description: errorMessage(err, "Please try again."), variant: "destructive" });
    } finally {
      setIsBusy(false);
    }
  }

  async function handleCopy() {
    if (!publicId) return;
    try {
      await navigator.clipboard.writeText(scriptTagFor(publicId));
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      toast({ title: "Couldn't copy", description: "Select the code and copy it manually." });
    }
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-md bg-secondary text-foreground">
              <Globe className="h-5 w-5" strokeWidth={1.75} />
            </span>
            <div>
              <CardTitle className="text-base">Add chat to your website</CardTitle>
              <p className="mt-0.5 text-sm text-muted-foreground">
                Paste one line of code on your site and your Receptionist can answer visitors right there.
              </p>
            </div>
          </div>
          {!isLoading && !error && (
            <Switch checked={enabled} onCheckedChange={handleToggle} disabled={isBusy} label="Website chat on" />
          )}
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : error ? (
          <p className="text-sm text-destructive">{error}</p>
        ) : !publicId ? (
          <p className="text-sm text-muted-foreground">
            Set up your business profile first — your chat code will appear here once it&rsquo;s ready.
          </p>
        ) : (
          <div className="flex flex-col gap-5">
            <div className="flex items-center gap-2">
              <Badge variant={enabled ? "success" : "secondary"}>{enabled ? "On" : "Off"}</Badge>
              <p className="text-xs text-muted-foreground">
                {enabled
                  ? "Visitors on any page with this code can chat with your Receptionist."
                  : "Turned off — the code does nothing on your site until you switch this back on."}
              </p>
            </div>

            <div>
              <p className="mb-1.5 text-sm font-medium text-foreground">
                1. Copy this and paste it into your website (just before <code>&lt;/body&gt;</code> works on
                most site builders)
              </p>
              <div className="flex items-start gap-2">
                <pre className="scrollbar-thin flex-1 overflow-x-auto rounded-md border border-border bg-secondary/40 px-3 py-2.5 text-xs leading-relaxed text-foreground">
                  <code>{scriptTagFor(publicId)}</code>
                </pre>
                <Button variant="outline" size="icon" onClick={handleCopy} aria-label="Copy code">
                  {copied ? <Check className="h-4 w-4" strokeWidth={1.75} /> : <Copy className="h-4 w-4" strokeWidth={1.75} />}
                </Button>
              </div>
            </div>

            <div>
              <p className="mb-1.5 text-sm font-medium text-foreground">2. This is what your visitors will see</p>
              <div className="overflow-hidden rounded-md border border-border">
                <iframe
                  key={publicId}
                  src={`/widget-preview.html?org=${encodeURIComponent(publicId)}&api=${encodeURIComponent(API_URL)}`}
                  title="Website chat preview"
                  className="h-72 w-full"
                  style={{ border: "none" }}
                />
              </div>
            </div>

            <div className="flex items-center justify-between border-t border-border pt-4">
              <p className="text-xs text-muted-foreground">
                Think someone&rsquo;s misusing your chat link? Get a new code — the old one stops working immediately.
              </p>
              <Button variant="ghost" size="sm" onClick={handleGetNewCode} disabled={isBusy}>
                <RefreshCcw className="h-3.5 w-3.5" strokeWidth={1.75} /> Get a new code
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
