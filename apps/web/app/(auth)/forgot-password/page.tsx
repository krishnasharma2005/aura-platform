"use client";

import * as React from "react";
import Link from "next/link";
import { MailCheck } from "lucide-react";
import { api } from "@/lib/api-client";
import { errorMessage } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export default function ForgotPasswordPage() {
  const [email, setEmail] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = React.useState(false);
  const [sentTo, setSentTo] = React.useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await api.auth.forgotPassword(email.trim());
      setSentTo(email.trim());
    } catch (err) {
      // Only reachable for rate limiting or a connection problem — never for an
      // unknown address, which the server answers exactly like a known one.
      setError(errorMessage(err, "We couldn't send that just now. Please try again in a moment."));
    } finally {
      setIsSubmitting(false);
    }
  }

  if (sentTo) {
    return (
      <Card className="w-full max-w-sm">
        <CardHeader>
          <span className="mb-1 flex h-10 w-10 items-center justify-center rounded-full bg-primary/10 text-primary-ink">
            <MailCheck className="h-5 w-5" strokeWidth={1.5} />
          </span>
          <CardTitle>Check your email</CardTitle>
          <CardDescription>
            If <span className="font-medium text-foreground">{sentTo}</span> has an account, we&apos;ve sent a link to
            choose a new password. It works once and expires in an hour.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3 text-sm text-muted-foreground">
          <p>Nothing there? Check your spam folder, or make sure you used the address you signed up with.</p>
          <Link href="/login" className="font-medium text-primary-ink hover:underline">
            Back to sign in
          </Link>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="w-full max-w-sm">
      <CardHeader>
        <CardTitle>Reset your password</CardTitle>
        <CardDescription>Enter your email and we&apos;ll send you a link to choose a new one.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="email">Work email</Label>
            <Input
              id="email"
              type="email"
              autoComplete="email"
              required
              autoFocus
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@yourbusiness.com"
            />
          </div>
          {error && (
            <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive-ink">
              {error}
            </p>
          )}
          <Button type="submit" className="mt-1 w-full" disabled={isSubmitting || !email.trim()}>
            {isSubmitting ? "Sending…" : "Send reset link"}
          </Button>
        </form>
        <p className="mt-5 text-center text-sm text-muted-foreground">
          Remembered it?{" "}
          <Link href="/login" className="font-medium text-primary-ink hover:underline">
            Back to sign in
          </Link>
        </p>
      </CardContent>
    </Card>
  );
}
