"use client";

import * as React from "react";
import { UserPlus } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { api } from "@/lib/api-client";
import type { OrganizationMember } from "@/lib/api-types";
import { initials, formatRelativeTime, errorMessage } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/components/ui/use-toast";

export default function MembersSettingsPage() {
  const { organization } = useAuth();
  const { toast } = useToast();
  const [members, setMembers] = React.useState<OrganizationMember[]>([]);
  const [isLoading, setIsLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [inviteEmail, setInviteEmail] = React.useState("");
  const [dialogOpen, setDialogOpen] = React.useState(false);

  React.useEffect(() => {
    if (!organization) {
      setIsLoading(false);
      return;
    }
    api.organizations
      .members(organization.id)
      .then(setMembers)
      .catch((err) =>
        setError(errorMessage(err, "Couldn't load your team right now."))
      )
      .finally(() => setIsLoading(false));
  }, [organization]);

  function handleInvite(e: React.FormEvent) {
    e.preventDefault();
    toast({
      title: "Invite sent",
      description: `We'll email ${inviteEmail} instructions to join ${organization?.name ?? "your workspace"}.`,
    });
    setInviteEmail("");
    setDialogOpen(false);
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0">
        <div>
          <CardTitle className="text-base">Team members</CardTitle>
          <CardDescription>Everyone who can see and manage your agents.</CardDescription>
        </div>
        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogTrigger asChild>
            <Button size="sm">
              <UserPlus className="h-4 w-4" /> Invite
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Invite a teammate</DialogTitle>
              <DialogDescription>
                They&apos;ll get an email to join {organization?.name ?? "your workspace"} as a member.
              </DialogDescription>
            </DialogHeader>
            <form onSubmit={handleInvite} className="flex flex-col gap-4">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="inviteEmail">Email address</Label>
                <Input
                  id="inviteEmail"
                  type="email"
                  required
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  placeholder="teammate@yourbusiness.com"
                />
              </div>
              <DialogFooter>
                <Button type="submit" disabled={!inviteEmail}>
                  Send invite
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <p className="text-sm text-muted-foreground">Loading team…</p>
        ) : error ? (
          <p className="text-sm text-destructive">{error}</p>
        ) : members.length === 0 ? (
          <div className="rounded-md border border-dashed border-border px-4 py-8 text-center">
            <p className="text-sm text-muted-foreground">
              It&apos;s just you so far. Invite a teammate to help manage your agents.
            </p>
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Member</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Joined</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {members.map((m) => (
                <TableRow key={m.id}>
                  <TableCell>
                    <div className="flex items-center gap-2.5">
                      <Avatar className="h-7 w-7">
                        <AvatarFallback className="text-[0.65rem]">{initials(m.full_name)}</AvatarFallback>
                      </Avatar>
                      <div>
                        <p className="text-sm font-medium text-foreground">{m.full_name}</p>
                        <p className="text-xs text-muted-foreground">{m.email}</p>
                      </div>
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className="capitalize">
                      {m.role}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {formatRelativeTime(m.joined_at)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
