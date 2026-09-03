"""The Receptionist's predefined decision tree.

This is the entire content of the temporary scripted flow, written for the
Riverside Dental demo narrative (docs/customer-profile.md). It's plain data
on purpose — this whole module goes away once the real AI-driven pipeline
takes over (see agents/runtime/pipeline.py, agents/configs/receptionist.yaml).

Each node is `node_id -> {"message": str, "options": [{"id", "label", "next"}]}`.
`next` must always point at another key in this same dict.

Honesty rule (per docs/customer-profile.md): every "I've noted/passed/flagged
this" line describes exactly what the scripted flow does — write an Activity
entry — and nothing more. It never claims a booking was made or a human was
actually notified.
"""

RECEPTIONIST_FLOW: dict[str, dict] = {
    "start": {
        "message": "Hi! I'm the Riverside Dental assistant. How can I help today?",
        "options": [
            {"id": "book", "label": "Book an appointment", "next": "book"},
            {"id": "hours", "label": "Check opening hours", "next": "hours"},
            {"id": "pricing", "label": "Ask about pricing", "next": "pricing"},
            {"id": "reschedule", "label": "Reschedule or cancel a booking", "next": "reschedule"},
            {"id": "human", "label": "Talk to a person", "next": "human"},
        ],
    },
    "hours": {
        "message": (
            "We're open Mon–Fri 8am–6pm and Sat 9am–2pm. Closed Sundays and public holidays."
        ),
        "options": [
            {"id": "book", "label": "Book an appointment", "next": "book"},
            {"id": "start", "label": "Back to main menu", "next": "start"},
        ],
    },
    "pricing": {
        "message": (
            "Here's a quick idea of cost: Check-up & clean from $120 · Filling from $180 · "
            "Whitening from $350 · Emergency visit from $150. Exact pricing depends on what "
            "you need — happy to book you in for a proper assessment."
        ),
        "options": [
            {"id": "book", "label": "Book an appointment", "next": "book"},
            {"id": "start", "label": "Back to main menu", "next": "start"},
        ],
    },
    "book": {
        "message": "Great — what's this appointment for?",
        "options": [
            {"id": "book_checkup", "label": "Check-up & clean", "next": "book_checkup"},
            {"id": "book_emergency", "label": "Emergency / in pain", "next": "book_emergency"},
            {"id": "book_other", "label": "Something else", "next": "book_other"},
        ],
    },
    "book_checkup": {
        "message": (
            "Got it — a check-up & clean. I've noted your request and passed it to our front "
            "desk. Someone will confirm your exact time by phone or WhatsApp shortly."
        ),
        "options": [
            {"id": "start", "label": "Back to main menu", "next": "start"},
            {"id": "human", "label": "Talk to a person now", "next": "human"},
        ],
    },
    "book_emergency": {
        "message": (
            "I'm sorry to hear that. I've flagged this as urgent and passed it straight to our "
            "team — someone will call you back as soon as possible. If this is a medical "
            "emergency, please call us directly or go to A&E."
        ),
        "options": [
            {"id": "start", "label": "Back to main menu", "next": "start"},
        ],
    },
    "book_other": {
        "message": (
            "No problem — I've passed your request to our front desk and someone will follow "
            "up to sort out the details."
        ),
        "options": [
            {"id": "start", "label": "Back to main menu", "next": "start"},
            {"id": "human", "label": "Talk to a person now", "next": "human"},
        ],
    },
    "reschedule": {
        "message": (
            "No problem. Since this touches an existing booking, I'll connect you with our "
            "front desk to make sure nothing gets mixed up."
        ),
        "options": [
            {"id": "human", "label": "Talk to a person now", "next": "human"},
            {"id": "start", "label": "Back to main menu", "next": "start"},
        ],
    },
    "human": {
        "message": (
            "I've flagged this conversation for the team — someone from Riverside Dental will "
            "follow up with you directly. Thanks for your patience!"
        ),
        "options": [
            {"id": "start", "label": "Back to main menu", "next": "start"},
        ],
    },
}

START_NODE_ID = "start"

# Keyed by agent slug so more agents can opt into a scripted flow later
# without touching the runtime module below.
FLOWS: dict[str, dict[str, dict]] = {
    "receptionist": RECEPTIONIST_FLOW,
}
