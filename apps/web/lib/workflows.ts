import type { Workflow, WorkflowRun, WorkflowStep } from "./api-types";

/**
 * Plain language for the workflows page.
 *
 * The owner of a dental practice should never read the word "trigger",
 * "webhook", or "payload" in this product. The API speaks in machine names
 * because it has to; this file is the single place where those become
 * sentences a person can read, so no component ever prints a raw one.
 *
 * Anything we don't recognise falls back to a sentence that is still true and
 * still jargon-free, rather than leaking the raw string onto the screen.
 */

const TRIGGER_SENTENCES: Record<string, string> = {
  appointment_no_show: "When someone doesn't turn up for their appointment",
  no_show: "When someone doesn't turn up for their appointment",
  missed_call: "When a call comes in and nobody picks up",
  voicemail_received: "When someone leaves a voicemail",
  new_lead: "When a new enquiry comes in",
  lead_created: "When a new enquiry comes in",
  inbound_message: "When a patient texts or emails you",
  message_received: "When a patient texts or emails you",
  appointment_booked: "Just after an appointment is booked",
  appointment_reminder: "The day before an appointment",
  appointment_cancelled: "When someone cancels",
  recall_due: "When a patient is due for their next check-up",
  review_request: "A day after a visit",
  daily: "Every morning",
  schedule_daily: "Every morning",
  weekly: "Once a week",
  schedule_weekly: "Once a week",
  hourly: "Every hour",
  manual: "Only when you start it yourself",
};

export function triggerSentence(trigger: string): string {
  const key = trigger?.trim().toLowerCase();
  return TRIGGER_SENTENCES[key] ?? "Automatically, in the background";
}

/**
 * Turn a step's machine name into something readable. Backends tend to send
 * `send_reminder_sms`; an owner reads "Send reminder sms" happily and reads
 * `send_reminder_sms` not at all.
 */
export function stepLabel(step: WorkflowStep): string {
  const raw = (step.name ?? "").replace(/[_-]+/g, " ").trim();
  if (!raw) return "Step";
  return raw.charAt(0).toUpperCase() + raw.slice(1);
}

/** How reliable this has been, said the way a person would say it. */
export function reliabilitySentence(workflow: Workflow): string {
  const runs = workflow.run_count ?? 0;
  const successes = workflow.success_count ?? 0;

  if (runs === 0) return "Hasn't run yet";
  if (successes === runs) {
    return runs === 1 ? "Ran once, went through" : `Ran ${runs} times, all went through`;
  }
  const failures = runs - successes;
  return `Ran ${runs} times · ${failures} ${failures === 1 ? "run" : "runs"} needed a second look`;
}

export function runStatusLabel(status: WorkflowRun["status"]): string {
  switch (status) {
    case "success":
      return "Went through";
    case "failed":
      return "Stopped early";
    case "running":
      return "Working now";
    default:
      return "Unknown";
  }
}

/** The step that stopped a failed run, if the backend marked one. */
export function failedStep(run: WorkflowRun): WorkflowStep | undefined {
  return (run.steps ?? []).find((step) => step.status === "failed");
}

/** How long a run took, in words. Absent `finished_at` means still going. */
export function runDuration(run: WorkflowRun): string | null {
  if (!run.finished_at) return null;
  const start = new Date(run.started_at).getTime();
  const end = new Date(run.finished_at).getTime();
  if (Number.isNaN(start) || Number.isNaN(end) || end < start) return null;

  const seconds = Math.round((end - start) / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min`;
  return `${Math.round(minutes / 60)} hr`;
}
