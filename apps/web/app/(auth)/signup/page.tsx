"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { errorMessage } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export default function SignupPage() {
  const router = useRouter();
  const { signup } = useAuth();
  const [fullName, setFullName] = React.useState("");
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = React.useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await signup(email, password, fullName);
      router.push("/onboarding");
    } catch (err) {
      setError(errorMessage(err, "We couldn't create your account. Please try again."));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <Card className="w-full max-w-sm">
      <CardHeader>
        <CardTitle>Create your account</CardTitle>
        <CardDescription>Takes about a minute — no credit card needed to try it out.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="fullName">Your name</Label>
            <Input
              id="fullName"
              required
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="Jordan Rivera"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="email">Work email</Label>
            <Input
              id="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@yourbusiness.com"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              type="password"
              autoComplete="new-password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="At least 8 characters"
            />
          </div>
          {error && (
            <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {error}
            </p>
          )}
          <Button type="submit" className="mt-1 w-full" disabled={isSubmitting}>
            {isSubmitting ? "Creating account…" : "Create account"}
          </Button>
        </form>
        <p className="mt-5 text-center text-sm text-muted-foreground">
          Already have an account?{" "}
          <Link href="/login" className="font-medium text-primary hover:underline">
            Sign in
          </Link>
        </p>
      </CardContent>
    </Card>
  );
}
