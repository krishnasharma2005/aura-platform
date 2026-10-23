"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api-client";
import { errorMessage } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

const MIN_LENGTH = 8;

function ResetPasswordForm() {
  const router = useRouter();
  const token = useSearchParams().get("token") ?? "";
  const [password, setPassword] = React.useState("");
  const [confirm, setConfirm] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = React.useState(false);
  // A dead link can't be fixed by retyping the password, so once the server says
  // so we stop offering the form and point at a new link instead.
  const [linkIsDead, setLinkIsDead] = React.useState(false);

  if (!token || linkIsDead) {
    return (
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>This link won&apos;t work</CardTitle>
          <CardDescription>
            {token
              ? "It has expired or has already been used. Reset links work once, for an hour."
              : "The link looks incomplete. Try opening it again from your email."}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button asChild className="w-full">
            <Link href="/forgot-password">Get a new link</Link>
          </Button>
        </CardContent>
      </Card>
    );
  }

  const mismatch = confirm.length > 0 && password !== confirm;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (password !== confirm) {
      setError("The two passwords don't match.");
      return;
    }
    setIsSubmitting(true);
    try {
      await api.auth.resetPassword(token, password);
      router.replace("/login?reset=1");
    } catch (err) {
      const message = errorMessage(err, "We couldn't change your password just now. Please try again.");
      if (/expired|already been used/i.test(message)) setLinkIsDead(true);
      else setError(message);
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <Card className="w-full max-w-sm">
      <CardHeader>
        <CardTitle>Choose a new password</CardTitle>
        <CardDescription>
          Pick something at least {MIN_LENGTH} characters long. You&apos;ll be signed out on any other device.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="password">New password</Label>
            <Input
              id="password"
              type="password"
              autoComplete="new-password"
              required
              minLength={MIN_LENGTH}
              autoFocus
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={`At least ${MIN_LENGTH} characters`}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="confirm">Type it again</Label>
            <Input
              id="confirm"
              type="password"
              autoComplete="new-password"
              required
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              aria-invalid={mismatch}
            />
            {mismatch && <p className="text-xs text-destructive-ink">These don&apos;t match yet.</p>}
          </div>
          {error && (
            <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive-ink">
              {error}
            </p>
          )}
          <Button type="submit" className="mt-1 w-full" disabled={isSubmitting || mismatch || password.length < MIN_LENGTH}>
            {isSubmitting ? "Saving…" : "Change password"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

export default function ResetPasswordPage() {
  // useSearchParams needs a Suspense boundary in the app router.
  return (
    <React.Suspense fallback={null}>
      <ResetPasswordForm />
    </React.Suspense>
  );
}
