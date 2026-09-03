"""The three pre-built automation templates.

Why *these* three. The segment deep dive (§2, §5b) is blunt about where the
money is: the wedge is not "AI agents", it is one assistant that works the
enquiry and then **keeps working the relationship** — no-show recovery and
treatment recall — with the owner able to see and approve every consequential
action. No-shows cost a 3–5 provider aesthetics practice $215k–455k a year;
that number is the whole renewal argument, and it only becomes a promise if
something chases the appointment without being asked. §4 also lists "what if it
breaks and I lose a lead?" as an open objection with *no escalation path* — the
third template exists to close it.

So:

1. **Appointment reminder → no-show recovery → rebook offer** (scheduled daily)
   The revenue story. Reads tomorrow's diary, drafts and sends a reminder,
   waits past the appointment, and if the patient never replied, offers to
   rebook. Both outbound messages route through the approval gate.

2. **Treatment recall** (scheduled weekly, configurable interval)
   The retention story. Anyone not seen for `recall_after_days` gets a warm
   "you're due" message. The interval is the configurable part — 12 weeks for
   hygiene, 16 for filler — and lives in `trigger_config`, in the database.

3. **New-enquiry escalation** (event-triggered on an inbound message)
   The trust story. An enquiry that goes unanswered past a threshold gets
   flagged to a human in the Activity feed. Deliberately does *not* need any
   integration connected: this is the safety net, and a safety net that can be
   blocked by a missing credential is not one.

Two honest limitations, both written up in `docs/needs-founder-input.md`:
there is no appointment/attendance table, so "no-show" is inferred from "never
replied to the reminder"; and the recall interval per treatment type is a
clinical decision nobody has made yet.
"""

from typing import Any

from src.workflows.models import TriggerType

APPOINTMENT_REMINDER = "appointment-reminder-rebook"
TREATMENT_RECALL = "treatment-recall"
NEW_LEAD_ESCALATION = "new-enquiry-escalation"


TEMPLATES: list[dict[str, Any]] = [
    {
        "slug": APPOINTMENT_REMINDER,
        "name": "Appointment reminders and no-show recovery",
        "description": (
            "Every morning, reminds tomorrow's patients about their appointment. If a patient "
            "never replies, offers them a new time instead of letting the slot go to waste. "
            "You approve every message before it goes out."
        ),
        "trigger_type": TriggerType.schedule,
        "trigger_config": {
            "interval_minutes": 60 * 24,
            # How long after the reminder we decide nobody is coming.
            "recheck_after_minutes": 60 * 24,
        },
        "steps": [
            {
                "id": "read_diary",
                "name": "Read tomorrow's appointments",
                "type": "tool",
                "tool": "calendar",
                "as_agent": "receptionist",
                "arguments": {"action": "list_events"},
            },
            {
                "id": "anything_booked",
                "name": "Is there anything booked?",
                "type": "branch",
                "check": "context_not_empty",
                "params": {"path": "steps.read_diary.events"},
                "on_false": "stop",
            },
            {
                "id": "draft_reminder",
                "name": "Write the reminder",
                "type": "agent",
                "agent": "receptionist",
                "conversation_key": "workflow-reminder-{{run_id}}",
                "prompt": (
                    "Write one short, warm appointment reminder to send to a patient who is booked "
                    "in tomorrow. Confirm the day and time, ask them to reply to confirm, and "
                    "mention that we need 48 working hours' notice to move it. Two sentences, no "
                    "greeting placeholders, no emoji."
                ),
            },
            {
                "id": "send_reminder",
                "name": "Send the reminder",
                "type": "tool",
                "tool": "whatsapp",
                "as_agent": "receptionist",
                "arguments": {
                    "to": "{{contact_phone}}",
                    "message": "{{steps.draft_reminder.response}}",
                },
            },
            {
                "id": "wait_for_the_day",
                "name": "Wait until after the appointment",
                "type": "wait",
                "minutes": 60 * 24,
            },
            {
                "id": "did_they_reply",
                "name": "Did they ever reply?",
                "type": "branch",
                "check": "conversation_unanswered",
                "params": {"conversation_key": "workflow-reminder-{{run_id}}", "minutes": 0},
                "on_false": "stop",
            },
            {
                "id": "draft_rebook",
                "name": "Write a rebooking offer",
                "type": "agent",
                "agent": "receptionist",
                "conversation_key": "workflow-reminder-{{run_id}}",
                "prompt": (
                    "This patient never replied to their reminder and didn't attend. Write one "
                    "short, non-judgemental message checking they're alright and offering to find "
                    "them another time. Do not mention a missed-appointment fee. Two sentences."
                ),
            },
            {
                "id": "send_rebook",
                "name": "Offer them a new time",
                "type": "tool",
                "tool": "whatsapp",
                "as_agent": "receptionist",
                "arguments": {
                    "to": "{{contact_phone}}",
                    "message": "{{steps.draft_rebook.response}}",
                },
            },
        ],
    },
    {
        "slug": TREATMENT_RECALL,
        "name": "Treatment recall follow-ups",
        "description": (
            "Once a week, finds patients you haven't seen for a while and drafts a friendly "
            "'you're due' message for each of them. The interval is yours to set."
        ),
        "trigger_type": TriggerType.schedule,
        "trigger_config": {
            "interval_minutes": 60 * 24 * 7,
            # The configurable cadence. Change this per clinic; it is data, not code.
            "recall_after_days": 90,
            "max_per_run": 25,
        },
        "steps": [
            {
                "id": "find_due",
                "name": "Find patients who are due",
                "type": "branch",
                "check": "contacts_due_for_recall",
                "params": {"days": 90, "limit": 25},
                "on_false": "stop",
            },
            {
                "id": "draft_recall",
                "name": "Write the follow-up",
                "type": "agent",
                "agent": "receptionist",
                "conversation_key": "workflow-recall-{{run_id}}",
                "prompt": (
                    "These patients are due a follow-up visit: {{steps.find_due.names}}. Write one "
                    "short, warm message we can send to a patient who hasn't been in for a while, "
                    "inviting them to book. Mention that we can usually find something within a "
                    "week or two. Two sentences, no pressure, no discount."
                ),
            },
            {
                "id": "send_recall",
                "name": "Send the follow-up",
                "type": "tool",
                "tool": "whatsapp",
                "as_agent": "receptionist",
                "arguments": {
                    "to": "{{steps.find_due.contacts.0.phone}}",
                    "message": "{{steps.draft_recall.response}}",
                },
            },
        ],
    },
    {
        "slug": NEW_LEAD_ESCALATION,
        "name": "New enquiry escalation",
        "description": (
            "Watches every new enquiry that comes in from your website or WhatsApp. If one is "
            "still sitting unanswered after 15 minutes, it's flagged in your Activity feed so "
            "nobody is left waiting."
        ),
        "trigger_type": TriggerType.event,
        "trigger_config": {
            "event": "conversation.message_received",
            "channels": ["web_chat", "whatsapp"],
            "unanswered_after_minutes": 15,
        },
        "steps": [
            {
                "id": "hold",
                "name": "Give the assistant a chance to answer",
                "type": "wait",
                "minutes": 15,
            },
            {
                "id": "still_waiting",
                "name": "Is it still unanswered?",
                "type": "branch",
                "check": "conversation_unanswered",
                "params": {"minutes": 15},
                "on_false": "stop",
            },
            {
                # Optional on purpose: if the AI provider is down, losing the
                # summary must not lose the escalation.
                "id": "summarise",
                "name": "Summarise it for whoever picks it up",
                "type": "agent",
                "agent": "support",
                "optional": True,
                "conversation_key": "workflow-escalation-{{run_id}}",
                "prompt": (
                    "A new enquiry has gone unanswered. In one sentence, tell the practice "
                    "manager what to do first when they pick it up. Here is what the person "
                    "said: {{last_message}}"
                ),
            },
            {
                "id": "flag_it",
                "name": "Flag it for a human",
                "type": "escalate",
                "reason": (
                    "A new enquiry has been waiting 15 minutes without a reply. "
                    "{{steps.summarise.response}}"
                ),
            },
        ],
    },
]


def template_by_slug(slug: str) -> dict[str, Any] | None:
    return next((template for template in TEMPLATES if template["slug"] == slug), None)
