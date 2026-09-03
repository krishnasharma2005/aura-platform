"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { api } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn, errorMessage } from "@/lib/utils";

const BUSINESS_TYPES = [
  { value: "clinic", label: "Clinic or medical practice" },
  { value: "salon_spa", label: "Salon or spa" },
  { value: "home_services", label: "Contractor or home services" },
  { value: "agency", label: "Marketing or creative agency" },
  { value: "ecommerce", label: "E-commerce / online store" },
  { value: "other", label: "Something else" },
];

const GOALS = [
  { value: "missed_bookings", label: "Stop missing bookings and calls" },
  { value: "faster_replies", label: "Reply to customers faster" },
  { value: "less_admin", label: "Spend less time on admin work" },
  { value: "grow_sales", label: "Follow up on leads and grow sales" },
];

export default function OnboardingPage() {
  const router = useRouter();
  const { setOrganization, isAuthenticated, isLoading } = useAuth();
  const [businessName, setBusinessName] = React.useState("");
  const [businessType, setBusinessType] = React.useState("");
  const [goal, setGoal] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = React.useState(false);

  React.useEffect(() => {
    if (!isLoading && !isAuthenticated) router.replace("/signup");
  }, [isLoading, isAuthenticated, router]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      const org = await api.organizations.create({
        name: businessName,
        business_type: businessType,
        primary_goal: goal || undefined,
      });
      setOrganization(org);
      router.push("/");
    } catch (err) {
      setError(
        errorMessage(err, "We couldn't set up your workspace. Please try again.")
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <Card className="w-full max-w-lg">
      <CardHeader>
        <CardTitle>Tell us about your business</CardTitle>
        <CardDescription>
          Two quick questions — this shapes how your agents talk to customers. Takes under a minute.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="flex flex-col gap-6">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="businessName">Business name</Label>
            <Input
              id="businessName"
              required
              autoFocus
              value={businessName}
              onChange={(e) => setBusinessName(e.target.value)}
              placeholder="Riverside Dental"
            />
          </div>

          <div className="flex flex-col gap-2">
            <Label>What kind of business is it?</Label>
            <div className="grid grid-cols-2 gap-2">
              {BUSINESS_TYPES.map((type) => (
                <button
                  type="button"
                  key={type.value}
                  onClick={() => setBusinessType(type.value)}
                  className={cn(
                    "rounded-md border px-3 py-2.5 text-left text-sm transition-colors",
                    businessType === type.value
                      ? "border-primary bg-primary/5 text-foreground ring-1 ring-primary"
                      : "border-border bg-card text-muted-foreground hover:border-foreground/20 hover:text-foreground"
                  )}
                >
                  {type.label}
                </button>
              ))}
            </div>
          </div>

          <div className="flex flex-col gap-2">
            <Label>What&apos;s the biggest thing you want help with?</Label>
            <div className="flex flex-col gap-2">
              {GOALS.map((g) => (
                <button
                  type="button"
                  key={g.value}
                  onClick={() => setGoal(g.value)}
                  className={cn(
                    "rounded-md border px-3 py-2.5 text-left text-sm transition-colors",
                    goal === g.value
                      ? "border-primary bg-primary/5 text-foreground ring-1 ring-primary"
                      : "border-border bg-card text-muted-foreground hover:border-foreground/20 hover:text-foreground"
                  )}
                >
                  {g.label}
                </button>
              ))}
            </div>
          </div>

          {error && (
            <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {error}
            </p>
          )}

          <Button type="submit" size="lg" disabled={isSubmitting || !businessName || !businessType}>
            {isSubmitting ? "Setting up your workspace…" : "Enter my workspace"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
