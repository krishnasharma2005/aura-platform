"use client";

import * as React from "react";
import { api, ApiClientError } from "@/lib/api-client";
import type { Approval, ApprovalStatus } from "@/lib/api-types";

/**
 * The approval queue.
 *
 * When an agent wants to do something consequential — send an email, cancel
 * an appointment, write to the CRM — it stops and waits. This holds that
 * queue in one place so the inline prompt in a chat and the counter in the
 * top bar are always the same list, and a decision made in one place lands
 * instantly in the other.
 *
 * Failure behaviour matters here more than anywhere else in the product:
 *   · Members (not owner/admin) get a 403. That is not an error to show —
 *     they simply have no queue, so we go quiet.
 *   · A network failure leaves the last known queue on screen rather than
 *     clearing it. Silently dropping a pending approval would be worse than
 *     showing a stale one.
 */

interface ApprovalsContextValue {
  pending: Approval[];
  count: number;
  isLoading: boolean;
  /** Set when the signed-in user isn't allowed to see the queue. */
  canReview: boolean;
  refresh: () => Promise<void>;
  decide: (id: string, decision: "approve" | "reject") => Promise<Approval>;
  /** Local decisions, so a chat can show what happened to its own request. */
  decisions: Record<string, { status: ApprovalStatus; message?: string | null }>;
}

const ApprovalsContext = React.createContext<ApprovalsContextValue | undefined>(undefined);

const POLL_MS = 20_000;

export function ApprovalsProvider({ children }: { children: React.ReactNode }) {
  const [pending, setPending] = React.useState<Approval[]>([]);
  const [isLoading, setIsLoading] = React.useState(true);
  const [canReview, setCanReview] = React.useState(true);
  const [decisions, setDecisions] = React.useState<
    Record<string, { status: ApprovalStatus; message?: string | null }>
  >({});

  const refresh = React.useCallback(async () => {
    try {
      const rows = await api.approvals.listPending();
      setPending(rows);
      setCanReview(true);
    } catch (err) {
      if (err instanceof ApiClientError && (err.status === 403 || err.status === 401)) {
        setCanReview(false);
        setPending([]);
      }
      // Any other failure: keep whatever we last knew about.
    } finally {
      setIsLoading(false);
    }
  }, []);

  React.useEffect(() => {
    refresh();
    const id = window.setInterval(refresh, POLL_MS);
    return () => window.clearInterval(id);
  }, [refresh]);

  const decide = React.useCallback(
    async (id: string, decision: "approve" | "reject") => {
      const optimisticStatus: ApprovalStatus = decision === "approve" ? "approved" : "rejected";
      // Optimistic: the row leaves the queue the moment you decide, because
      // the decision is yours and there is nothing to wait for.
      setPending((prev) => prev.filter((a) => a.id !== id));
      setDecisions((prev) => ({ ...prev, [id]: { status: optimisticStatus } }));
      try {
        const result =
          decision === "approve" ? await api.approvals.approve(id) : await api.approvals.reject(id);
        setDecisions((prev) => ({
          ...prev,
          [id]: { status: result.status, message: result.result_message },
        }));
        return result;
      } catch (err) {
        // Put it back — an approval that silently vanished would be the worst
        // possible outcome for someone who is trusting this with their inbox.
        setDecisions((prev) => {
          const next = { ...prev };
          delete next[id];
          return next;
        });
        await refresh();
        throw err;
      }
    },
    [refresh]
  );

  const value = React.useMemo(
    () => ({
      pending,
      count: pending.length,
      isLoading,
      canReview,
      refresh,
      decide,
      decisions,
    }),
    [pending, isLoading, canReview, refresh, decide, decisions]
  );

  return <ApprovalsContext.Provider value={value}>{children}</ApprovalsContext.Provider>;
}

export function useApprovals() {
  const ctx = React.useContext(ApprovalsContext);
  if (!ctx) throw new Error("useApprovals must be used within ApprovalsProvider");
  return ctx;
}
