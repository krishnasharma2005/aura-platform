"use client";

import { useAuth } from "@/lib/auth-context";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";

export default function GeneralSettingsPage() {
  const { organization, user } = useAuth();

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Workspace</CardTitle>
          <CardDescription>Basic details about your business.</CardDescription>
        </CardHeader>
        {/*
          Read-only on purpose. There is no save path for these yet, and an
          editable field above a permanently disabled Save button is worse
          than a locked one: it invites typing that silently goes nowhere.
          When the update endpoint lands, re-enable the field and the button
          together.
        */}
        <CardContent className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label>Business name</Label>
            <Input defaultValue={organization?.name ?? ""} readOnly disabled />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>Business type</Label>
            <Input defaultValue={organization?.business_type ?? ""} readOnly disabled />
          </div>
          <p className="text-xs leading-relaxed text-subtle">
            These were set when you created the workspace. Contact support to change them.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Your account</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label>Name</Label>
            <Input defaultValue={user?.full_name ?? ""} readOnly disabled />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>Email</Label>
            <Input defaultValue={user?.email ?? ""} readOnly disabled />
          </div>
          <p className="text-xs leading-relaxed text-subtle">
            Contact support to change the name or email on your account.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
