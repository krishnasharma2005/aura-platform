"use client";

import * as React from "react";
import { api } from "@/lib/api-client";
import { errorMessage } from "@/lib/utils";
import { useAuth } from "@/lib/auth-context";
import type { BusinessBrand, BusinessContext, BusinessCustomers, BusinessIdentity } from "@/lib/api-types";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/use-toast";

const EMPTY_IDENTITY: BusinessIdentity = {};
const EMPTY_BRAND: BusinessBrand = {};
const EMPTY_CUSTOMERS: BusinessCustomers = {};

export default function BusinessSettingsPage() {
  const { organization } = useAuth();
  const { toast } = useToast();

  const [isLoading, setIsLoading] = React.useState(true);
  const [isSaving, setIsSaving] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = React.useState<string | null>(null);

  const [identity, setIdentity] = React.useState<BusinessIdentity>(EMPTY_IDENTITY);
  const [brand, setBrand] = React.useState<BusinessBrand>(EMPTY_BRAND);
  const [customers, setCustomers] = React.useState<BusinessCustomers>(EMPTY_CUSTOMERS);

  const applyContext = (context: BusinessContext) => {
    setIdentity(context.identity ?? {});
    setBrand(context.brand ?? {});
    setCustomers(context.customers ?? {});
    setUpdatedAt(context.updated_at ?? null);
  };

  React.useEffect(() => {
    if (!organization) return;
    setIsLoading(true);
    setError(null);
    api.businessContext
      .get(organization.id)
      .then(applyContext)
      .catch((err) => setError(errorMessage(err, "Couldn't load your business details right now.")))
      .finally(() => setIsLoading(false));
  }, [organization]);

  async function handleSave() {
    if (!organization) return;
    setIsSaving(true);
    try {
      const updated = await api.businessContext.update(organization.id, { identity, brand, customers });
      applyContext(updated);
      toast({ title: "Saved", description: "Your agents will use these details from now on." });
    } catch (err) {
      toast({
        title: "Couldn't save",
        description: errorMessage(
          err,
          "Something went wrong. If you're not an owner or admin, ask one of them to make this change."
        ),
        variant: "destructive",
      });
    } finally {
      setIsSaving(false);
    }
  }

  if (isLoading) {
    return (
      <div className="flex flex-col gap-6">
        <Skeleton className="h-48 w-full rounded-lg" />
        <Skeleton className="h-40 w-full rounded-lg" />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <p className="text-sm text-muted-foreground">
        What you tell us here grounds every agent&apos;s answers — the Receptionist, Sales, and the rest all
        read from this same profile instead of guessing at your business.
      </p>

      {error && (
        <p className="rounded-md border border-destructive/25 bg-destructive/10 px-3.5 py-2.5 text-sm text-destructive">
          {error}
        </p>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Business identity</CardTitle>
          <CardDescription>The basics your agents mention to customers.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label>Business name</Label>
            <Input
              value={identity.business_name ?? ""}
              onChange={(e) => setIdentity((prev) => ({ ...prev, business_name: e.target.value }))}
              placeholder="Riverside Dental"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>Industry</Label>
            <Input
              value={identity.industry ?? ""}
              onChange={(e) => setIdentity((prev) => ({ ...prev, industry: e.target.value }))}
              placeholder="Dental clinic"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>Location</Label>
            <Input
              value={identity.location ?? ""}
              onChange={(e) => setIdentity((prev) => ({ ...prev, location: e.target.value }))}
              placeholder="Riverside, CA"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>Operating hours</Label>
            <Input
              value={identity.operating_hours ?? ""}
              onChange={(e) => setIdentity((prev) => ({ ...prev, operating_hours: e.target.value }))}
              placeholder="Mon–Fri 8am–5pm"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>About</Label>
            <Input
              value={identity.description ?? ""}
              onChange={(e) => setIdentity((prev) => ({ ...prev, description: e.target.value }))}
              placeholder="A friendly neighborhood dental practice."
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Brand voice</CardTitle>
          <CardDescription>How your agents should sound.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label>Tone</Label>
            <Input
              value={brand.tone ?? ""}
              onChange={(e) => setBrand((prev) => ({ ...prev, tone: e.target.value }))}
              placeholder="Warm and reassuring"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>Communication style</Label>
            <Input
              value={brand.communication_style ?? ""}
              onChange={(e) => setBrand((prev) => ({ ...prev, communication_style: e.target.value }))}
              placeholder="Friendly, plain language"
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Customers</CardTitle>
          <CardDescription>Who your agents are talking to.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label>Target customer</Label>
            <Input
              value={customers.target_customer_description ?? ""}
              onChange={(e) =>
                setCustomers((prev) => ({ ...prev, target_customer_description: e.target.value }))
              }
              placeholder="Local families seeking a long-term dental home"
            />
          </div>
        </CardContent>
      </Card>

      <div className="flex items-center justify-between">
        <p className="text-xs text-subtle">
          {updatedAt ? `Last updated ${new Date(updatedAt).toLocaleString()}` : "Never set yet."}
        </p>
        <Button onClick={handleSave} loading={isSaving}>
          Save changes
        </Button>
      </div>
    </div>
  );
}
