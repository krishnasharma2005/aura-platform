"""Seed a realistic demo organization: Riverside Dental.

Run from `apps/api`:

    python -m scripts.seed_demo

A live demo against an empty account undersells the product badly, so this
creates a business that looks like a real small clinic on its third month of
using AURA: staff, patients, a knowledge base, conversations across several
agents, an activity trail, and one action sitting in the approvals queue.

Two properties matter and are deliberately engineered:

* **Idempotent.** Re-running is safe. The organization, its owner login and
  its public web-chat id are stable across runs (so a demo link keeps
  working); the demo *content* — conversations, messages, activity, pending
  approvals — is rebuilt from scratch each time so it never accumulates
  duplicates.

* **Works with no OPENAI_API_KEY.** The knowledge documents are ingested
  through the real pipeline (real .docx files, real text extraction, real
  chunking, real storage), and only the embedding call is substituted with a
  deterministic stand-in when no key is configured. Semantic *search* quality
  needs a real key; having the documents present, listed and readable does not.
"""

import asyncio
import hashlib
import io
import sys
from datetime import UTC, datetime, timedelta

from docx import Document as DocxDocument
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents import approvals as approvals_service
from src.ai_gateway.gateway import AIGateway
from src.conversations.models import (
    Contact,
    Conversation,
    ConversationChannel,
    ConversationStatus,
    Message,
)
from src.conversations import service as conversation_service
from src.core.config import get_settings
from src.core.db import async_session_factory
from src.core.security import hash_password
from src.events.audit import AuditLog
from src.identity.models import Membership, MembershipRole, Organization, User
from src.identity.public_id import generate_public_id
from src.knowledge.ingest import ingest_document
from src.memory import long_term
from src.memory.models import EMBEDDING_DIM
from src.workflows import service as workflow_service
from src.workflows.models import (
    RunStatus,
    StepStatus,
    WorkflowDefinition,
    WorkflowRun,
    WorkflowStepRun,
)
from src.workflows.templates import (
    APPOINTMENT_REMINDER,
    NEW_LEAD_ESCALATION,
    TREATMENT_RECALL,
)

ORG_NAME = "Riverside Dental"
ORG_SLUG = "riverside-dental"
OWNER_EMAIL = "sarah@riversidedental.co.uk"
OWNER_NAME = "Sarah Whitfield"
OWNER_PASSWORD = "riverside-demo-2026"


# --------------------------------------------------------------------------
# Embeddings without a key
# --------------------------------------------------------------------------


class _SeedGateway:
    """Wraps the real gateway but falls back to a deterministic embedding when
    no OpenAI key is configured, so seeding a fresh machine before the keys
    arrive produces a complete-looking knowledge base instead of a crash.

    The stand-in vectors are stable for the same text but carry no semantic
    meaning — search over them returns arbitrary neighbours. Re-run this script
    once a real key is set to replace them with real embeddings.
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._real = AIGateway() if self._settings.OPENAI_API_KEY else None

    @property
    def embeddings_are_real(self) -> bool:
        return self._real is not None

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if self._real is not None:
            return await self._real.embed(texts)
        return [_stub_embedding(text) for text in texts]

    async def complete(self, *args, **kwargs):  # pragma: no cover - never called by seeding
        raise NotImplementedError("The demo seed never calls the model; conversations are pre-written.")


def _stub_embedding(text: str) -> list[float]:
    digest = hashlib.sha256(text.encode()).digest()
    # Cycle the digest bytes into a unit-ish vector of the right dimension.
    return [((digest[i % len(digest)] / 255.0) - 0.5) for i in range(EMBEDDING_DIM)]


# --------------------------------------------------------------------------
# Knowledge base documents (written as real .docx files, ingested for real)
# --------------------------------------------------------------------------

DOCUMENTS: list[tuple[str, str]] = [
    (
        "Riverside Dental - Opening Hours and Contact.docx",
        """Riverside Dental — Opening Hours and Contact

Address: 14 Mill Lane, Riverside, Stockton-on-Tees, TS18 1AB
Phone: 01642 555 0198
Email: hello@riversidedental.co.uk

Opening hours
Monday: 8:30am – 5:30pm
Tuesday: 8:30am – 5:30pm
Wednesday: 8:30am – 7:00pm (late evening clinic)
Thursday: 8:30am – 5:30pm
Friday: 8:30am – 4:00pm
Saturday: 9:00am – 1:00pm (emergency and hygienist appointments only)
Sunday: Closed

Bank holidays
We are closed on all English bank holidays. An out-of-hours emergency number
is on the answerphone and on the front door.

Dental emergencies
If you are in severe pain, have significant swelling, or have had a tooth
knocked out, call the practice first thing in the morning. We keep two
emergency slots free every weekday morning and one on Saturday. If we are
closed, call NHS 111.

Parking and access
There are six patient parking spaces behind the practice, entered from Bridge
Street. The ground floor surgery and the waiting room are step-free; the two
upstairs surgeries are reached by stairs only, so please tell us when booking
if you need the ground floor surgery.

The team
Dr. Sarah Whitfield — Principal Dentist (practice owner)
Dr. Michael Osei — Associate Dentist, implants and oral surgery
Priya Raman — Dental Hygienist
Chloe Bennett — Practice Manager
Danny Mercer — Dental Nurse
""",
    ),
    (
        "Riverside Dental - Services and Prices.docx",
        """Riverside Dental — Services and Prices (private fee guide)

These are our private fees. We also hold a small number of NHS places for
children and for existing NHS patients; ask reception whether any are open.
All prices include VAT where applicable and were last reviewed in January 2026.

Examinations and hygiene
New patient examination (30 minutes, includes X-rays): £75
Routine examination (existing patient): £48
Hygienist appointment, 30 minutes: £62
Hygienist appointment, 45 minutes (heavier cleaning): £86
Airflow stain removal, added to a hygiene visit: £40

Fillings and general treatment
White composite filling, small: £145
White composite filling, large: £210
Root canal treatment, front tooth: £395
Root canal treatment, molar: £625
Simple extraction: £185
Surgical extraction: £320

Crowns, bridges and dentures
Porcelain-bonded crown: £695
All-ceramic crown: £795
Bridge, per unit: £695
Full acrylic denture, upper or lower: £850
Chrome cobalt partial denture: £1,150

Implants and cosmetic treatment
Single dental implant, including crown: from £2,400
Implant consultation with Dr. Osei, including CT scan: £180 (refunded against
treatment if you go ahead)
Home teeth whitening kit with custom trays: £320
In-practice whitening: £450
Composite bonding, per tooth: £220
Clear aligners (Invisalign), simple case: from £2,650
Clear aligners, complex case: from £3,900

Payment
We take card, cash and bank transfer. Payment is due on the day of treatment.
For treatment over £500 we offer 0% finance over 12 months, subject to status,
arranged through our finance provider at the treatment planning appointment.

Quotes
Any treatment plan over £300 is written up as a formal quote before we start,
and the quote is valid for 90 days.
""",
    ),
    (
        "Riverside Dental - Cancellation and Late Policy.docx",
        """Riverside Dental — Cancellation, Late Arrival and Missed Appointment Policy

Notice we ask for
Please give us at least 48 working hours' notice if you need to cancel or move
an appointment. That lets us offer the time to someone waiting, often someone
in pain.

Missed appointments and short-notice cancellations
Appointments cancelled with less than 48 working hours' notice, or not
attended at all, are charged as follows:
Examination or hygiene appointment: £30
Treatment appointment of 30–60 minutes: £60
Treatment appointment over 60 minutes, or an implant or sedation appointment: £120

Why we charge
We are a five-surgery practice and a missed hour cannot be filled at short
notice. The charge covers the clinician and nurse time that was held for you.
It is not a penalty and we would much rather have the notice than the fee.

Discretion and fairness
The first missed appointment for a patient of good standing is usually waived
— genuine emergencies, sudden illness, bereavement and childcare failures
happen, and we would rather you told us. After two missed appointments we may
ask for the fee up front when booking future appointments. After three in
twelve months we may ask you to find another practice, and we will say so in
writing first.

Late arrivals
If you arrive more than ten minutes late we will do as much of the appointment
as the remaining time allows. If there is not enough time to treat you safely
we will rebook you, and that may be treated as a short-notice cancellation.

Reminders
We text a reminder three working days before every appointment and again the
morning before. Reminders are a courtesy — not receiving one is not a reason
to waive a missed appointment fee, so please tell reception if your mobile
number changes.

Practice-initiated changes
If we have to move your appointment (clinician illness, equipment failure) we
will phone you as early as we can and offer the first suitable alternative
slot. You are never charged for an appointment we moved.
""",
    ),
]


def _docx_bytes(body: str) -> bytes:
    document = DocxDocument()
    for line in body.splitlines():
        document.add_paragraph(line)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


# --------------------------------------------------------------------------
# Demo people and conversations
# --------------------------------------------------------------------------

CONTACTS = [
    {"name": "Amina Patel", "phone": "+447700900412", "email": "amina.patel@example.co.uk",
     "notes": "New patient enquiry from the website. Wants a check-up and hygiene visit."},
    {"name": "Tom Fletcher", "phone": "+447700900187", "email": "t.fletcher@example.co.uk",
     "notes": "Existing patient. Crown fitting in progress with Dr. Whitfield."},
    {"name": "Grace Okonkwo", "phone": "+447700900733", "email": "grace.okonkwo@example.co.uk",
     "notes": "Asked about implant pricing and finance. Consultation not yet booked."},
    {"name": "Derek Sallis", "phone": "+447700900265", "email": "d.sallis@example.co.uk",
     "notes": "Missed a 45-minute hygiene appointment on 11 August. Second miss this year."},
    {"name": "Helen Cartwright", "phone": "+447700900908", "email": "helen.cartwright@example.co.uk",
     "notes": "Interested in Invisalign. Sent the treatment guide, following up next week."},
]


def _conversations(now: datetime) -> list[dict]:
    """Pre-written threads. Content reflects what actually happens at a small
    clinic: bookings, a reschedule, a pricing question, a no-show follow-up,
    and the owner using the agents herself."""
    return [
        {
            "key": "demo-web-amina-newpatient",
            "agent": "receptionist",
            "channel": ConversationChannel.web_chat,
            "contact": "Amina Patel",
            "started": now - timedelta(days=2, hours=3),
            "turns": [
                ("user", "Hi, are you taking on new patients? I've just moved to Riverside."),
                ("assistant",
                 "Hello, and welcome to the area. Yes — we're taking new private patients, and we "
                 "have a small number of NHS places for children. A new patient examination is £75 "
                 "and takes about half an hour, including X-rays. Would you like me to find you a time?"),
                ("user", "Yes please. Something after work if possible, I finish at 5."),
                ("assistant",
                 "Our late clinic runs on Wednesdays until 7pm, so that's the easiest one for a 5pm "
                 "finish. I have Wednesday the 26th at 5:45pm with Dr. Whitfield. Shall I put your "
                 "name against it?"),
                ("user", "That works. Amina Patel, and my mobile is 07700 900412."),
                ("assistant",
                 "Lovely — I've sent that to the team to confirm, and you'll get a text once it's "
                 "booked in. If anything changes before then, just message here."),
            ],
            "tools": ["calendar"],
        },
        {
            "key": "demo-whatsapp-tom-reschedule",
            "agent": "receptionist",
            "channel": ConversationChannel.whatsapp,
            "contact": "Tom Fletcher",
            "started": now - timedelta(days=1, hours=6),
            "turns": [
                ("user", "Morning - I've got a crown fitting Thursday at 2 but works sent me to Leeds that day. Can I move it?"),
                ("assistant",
                 "Morning Tom — no problem at all, and thank you for the notice. I can see the "
                 "Thursday 2pm with Dr. Whitfield. The nearest alternatives are Friday the 21st at "
                 "9:30am, or Wednesday the 26th at 6:15pm in the late clinic. Would either suit?"),
                ("user", "Friday morning is better."),
                ("assistant",
                 "Friday the 21st at 9:30am it is — I've passed that to the team to confirm and "
                 "you'll get a text shortly. Your crown is already back from the lab, so nothing "
                 "else changes."),
            ],
            "tools": ["calendar"],
        },
        {
            "key": "demo-web-grace-implant-price",
            "agent": "receptionist",
            "channel": ConversationChannel.web_chat,
            "contact": "Grace Okonkwo",
            "started": now - timedelta(days=4, hours=1),
            "turns": [
                ("user", "How much is a dental implant? And do you do payment plans?"),
                ("assistant",
                 "A single implant including the crown starts at £2,400. Before that there's an "
                 "implant consultation with Dr. Osei at £180, which includes a CT scan and is "
                 "refunded against your treatment if you go ahead. For anything over £500 we offer "
                 "0% finance over 12 months, subject to status, arranged at the treatment planning "
                 "appointment."),
                ("user", "Is the £2,400 the final price or does it go up?"),
                ("assistant",
                 "It's the starting price for a straightforward single implant. If you need a bone "
                 "graft or a sinus lift the cost is higher, and Dr. Osei will only know that after "
                 "the CT scan. Anything over £300 is written up as a formal quote before we start, "
                 "and it's held for 90 days — so you'd see the real number before committing to "
                 "anything. Would you like me to book the consultation?"),
                ("user", "Let me think about it, thanks."),
                ("assistant",
                 "Of course. I'll leave your details with the team in case you'd like a call, and "
                 "you're very welcome to message here whenever you're ready."),
            ],
            "tools": [],
        },
        {
            "key": "demo-dash-derek-noshow",
            "agent": "support",
            "channel": ConversationChannel.dashboard,
            "contact": "Derek Sallis",
            "started": now - timedelta(days=3, hours=5),
            "turns": [
                ("user", "Derek Sallis missed his 45 minute hygiene appointment on Monday. Second one this year. What do I do?"),
                ("assistant",
                 "By the practice policy, a missed treatment appointment of 30–60 minutes is charged "
                 "at £60. The first miss for a patient in good standing is usually waived, and "
                 "Derek's first was in March — so this is the second, which means the fee applies "
                 "and future bookings can be asked for up front.\n\n"
                 "Before charging him, it's worth a call rather than a text: two misses in a year "
                 "from a long-standing patient often has a reason behind it. If you'd like, I can "
                 "draft a short, friendly message asking him to get in touch."),
                ("user", "Yes, draft something. Don't send it."),
                ("assistant",
                 "Here's a draft:\n\n\"Hi Derek, it's Riverside Dental. We missed you at Monday's "
                 "hygiene appointment and wanted to check everything's alright. Could you give us a "
                 "ring on 01642 555 0198 when you have a minute so we can get you rebooked? Thanks "
                 "— Chloe\"\n\nI haven't sent anything. It's saved here for you to send whenever "
                 "you're ready."),
            ],
            "tools": [],
        },
        {
            "key": "demo-dash-helen-invisalign",
            "agent": "sales",
            "channel": ConversationChannel.dashboard,
            "contact": "Helen Cartwright",
            "started": now - timedelta(days=6),
            "turns": [
                ("user", "Helen Cartwright asked about Invisalign at her check-up. What should I follow up with?"),
                ("assistant",
                 "Helen's a good fit for a follow-up — she asked unprompted, which is the strongest "
                 "signal you get. Simple cases start at £2,650 and complex ones from £3,900, and "
                 "both qualify for the 0% finance over 12 months, which for a simple case is about "
                 "£221 a month. That monthly figure is usually what decides it.\n\n"
                 "I'd suggest: a short message in the next few days offering a free 15-minute "
                 "aligner assessment, mentioning the monthly figure rather than the total. Would you "
                 "like me to note a follow-up for Thursday?"),
                ("user", "Yes, Thursday."),
                ("assistant", "Noted for Thursday. I'll remind you on the day."),
            ],
            "tools": [],
        },
        {
            "key": "demo-dash-week-ahead",
            "agent": "executive_assistant",
            "channel": ConversationChannel.dashboard,
            "contact": None,
            "started": now - timedelta(hours=20),
            "turns": [
                ("user", "What does my week look like?"),
                ("assistant",
                 "Reasonably full. Monday and Tuesday are both fully booked with Dr. Whitfield, and "
                 "Wednesday's late clinic has two slots left at 5:45pm and 6:15pm. Thursday has a "
                 "gap between 11am and 12:30pm after a cancellation. Friday finishes at 4pm as "
                 "usual, with one implant consultation at 2pm.\n\n"
                 "Two things worth your attention: there's a booking request waiting for your "
                 "approval, and the Thursday gap is the obvious place to offer Derek Sallis a "
                 "rebooked hygiene appointment."),
            ],
            "tools": ["calendar"],
        },
    ]


# A handful of short, real-shaped threads spread across the last week. The six
# hand-written conversations above carry the story; these carry the *numbers*.
# An analytics dashboard reading "3 conversations" is worse than no dashboard,
# and a week of a five-surgery practice is dozens of enquiries, not six.
FILLER_ENQUIRIES: list[tuple[str, str, str, list[str]]] = [
    ("receptionist", "Do you do emergency appointments? I've cracked a tooth.",
     "I'm sorry — that sounds painful. We hold two emergency slots every weekday morning and one "
     "on Saturday. Can you get here for 8:45am tomorrow?", ["calendar"]),
    ("receptionist", "How much is a hygienist appointment?",
     "A 30-minute hygiene visit is £62, and a 45-minute one for heavier cleaning is £86. Airflow "
     "stain removal can be added for £40.", []),
    ("receptionist", "Are you open on Saturdays?",
     "We are — 9am to 1pm, for emergency and hygienist appointments only. Everything else runs "
     "Monday to Friday.", []),
    ("receptionist", "Can I move my appointment on the 22nd?",
     "Of course. I've passed that to the team to confirm a new time and you'll get a text "
     "shortly.", ["calendar"]),
    ("receptionist", "Do you take NHS patients?",
     "We hold a small number of NHS places for children and for existing NHS patients. I'll ask "
     "reception whether any are open and come back to you.", []),
    ("receptionist", "Is there parking?",
     "Yes — six patient spaces behind the practice, entered from Bridge Street.", []),
    ("support", "I was charged £60 for a missed appointment, is that right?",
     "That's the standard charge for a missed 30–60 minute treatment appointment, but the first "
     "miss for a patient in good standing is usually waived. Let me get someone to look at your "
     "record and come back to you.", []),
    ("receptionist", "My filling has come out, how soon can I be seen?",
     "Let's get you in quickly. There's an emergency slot tomorrow at 8:30am, or Thursday at "
     "11:15am — which suits?", ["calendar"]),
    ("sales", "What's the monthly cost for Invisalign?",
     "A simple case starts at £2,650, which on our 0% 12-month finance is about £221 a month, "
     "subject to status. A complex case starts at £3,900.", []),
    ("receptionist", "Do you offer teeth whitening?",
     "We do — a home kit with custom trays is £320, and in-practice whitening is £450.", []),
    ("receptionist", "Can I book a check-up for my two children?",
     "Yes, and back-to-back is usually easiest. I've sent two slots on Wednesday afternoon to the "
     "team to confirm.", ["calendar"]),
    ("support", "Nobody has called me back about my crown.",
     "I'm sorry about that — that shouldn't have happened. I've flagged it for the practice "
     "manager to call you today.", []),
    ("receptionist", "Where exactly are you?",
     "14 Mill Lane, Riverside, Stockton-on-Tees, TS18 1AB — the ground-floor surgery and waiting "
     "room are step-free.", []),
    ("receptionist", "How much is a new patient check-up?",
     "£75 for a 30-minute new patient examination, including X-rays.", []),
    ("executive_assistant", "Anything I need to deal with today?",
     "One booking request is waiting for your approval, and Thursday still has a gap between 11am "
     "and 12:30pm worth filling.", []),
    ("receptionist", "Do you do implants?",
     "We do — Dr. Osei handles implants and oral surgery. A single implant including the crown "
     "starts at £2,400, after a £180 consultation with a CT scan.", []),
    ("receptionist", "Can I pay in instalments?",
     "For treatment over £500 we offer 0% finance over 12 months, subject to status, arranged at "
     "the treatment planning appointment.", []),
    ("receptionist", "I need to cancel Friday, sorry.",
     "No problem, thank you for letting us know. I've passed the cancellation to the team to "
     "confirm.", ["calendar"]),
]


BUSINESS_FACTS = [
    ("opening_hours", "Mon-Tue 8:30-17:30, Wed 8:30-19:00 (late clinic), Thu 8:30-17:30, Fri 8:30-16:00, Sat 9:00-13:00 (emergency and hygiene only), Sun closed."),
    ("cancellation_notice", "48 working hours' notice is required to cancel or move an appointment."),
    ("new_patient_exam_price", "£75, 30 minutes, includes X-rays."),
    ("finance", "0% finance over 12 months on treatment over £500, subject to status."),
    ("emergency_slots", "Two emergency slots are held every weekday morning and one on Saturday."),
]


# --------------------------------------------------------------------------
# Seeding
# --------------------------------------------------------------------------


async def _upsert_org(db: AsyncSession) -> Organization:
    org = (
        await db.execute(select(Organization).where(Organization.slug == ORG_SLUG))
    ).scalar_one_or_none()
    if org is None:
        org = Organization(name=ORG_NAME, slug=ORG_SLUG)
        db.add(org)
    org.name = ORG_NAME
    org.business_type = "Dental practice"
    org.primary_goal = "Stop missing enquiries and no-shows"
    org.timezone = "Europe/London"
    org.public_chat_enabled = True
    # Kept stable across runs so an embedded demo widget keeps working.
    if not org.public_id:
        org.public_id = generate_public_id()
    await db.commit()
    await db.refresh(org)
    return org


async def _upsert_owner(db: AsyncSession, org: Organization) -> User:
    user = (await db.execute(select(User).where(User.email == OWNER_EMAIL))).scalar_one_or_none()
    if user is None:
        user = User(email=OWNER_EMAIL, name=OWNER_NAME, hashed_password=hash_password(OWNER_PASSWORD))
        db.add(user)
        await db.flush()
    else:
        user.name = OWNER_NAME
        user.hashed_password = hash_password(OWNER_PASSWORD)

    membership = (
        await db.execute(
            select(Membership).where(
                Membership.user_id == user.id, Membership.organization_id == org.id
            )
        )
    ).scalar_one_or_none()
    if membership is None:
        db.add(
            Membership(
                user_id=user.id,
                organization_id=org.id,
                role=MembershipRole.owner,
                accepted=True,
            )
        )
    await db.commit()
    await db.refresh(user)
    return user


async def _upsert_contacts(db: AsyncSession, org: Organization) -> dict[str, Contact]:
    contacts: dict[str, Contact] = {}
    for spec in CONTACTS:
        contact = await conversation_service.upsert_contact(
            db,
            org.id,
            name=spec["name"],
            phone=spec["phone"],
            email=spec["email"],
            notes=spec["notes"],
        )
        contacts[spec["name"]] = contact
    await db.commit()
    return contacts


async def _clear_demo_content(db: AsyncSession, org: Organization) -> None:
    """Wipes only the *generated* content for this org so a re-run produces the
    same demo rather than a duplicated one. The org, its owner login, its
    public web-chat id and its contacts survive."""
    conversation_ids = [
        row for row in (
            await db.execute(select(Conversation.id).where(Conversation.org_id == org.id))
        ).scalars().all()
    ]
    if conversation_ids:
        await db.execute(delete(Message).where(Message.conversation_id.in_(conversation_ids)))
    await db.execute(delete(Conversation).where(Conversation.org_id == org.id))
    await db.execute(delete(AuditLog).where(AuditLog.org_id == org.id))

    # Workflow *definitions* survive (they're upserted, and an owner may have
    # toggled one), but the run history is generated content and is rebuilt.
    run_ids = list(
        (await db.execute(select(WorkflowRun.id).where(WorkflowRun.org_id == org.id))).scalars().all()
    )
    if run_ids:
        await db.execute(delete(WorkflowStepRun).where(WorkflowStepRun.run_id.in_(run_ids)))
    await db.execute(delete(WorkflowRun).where(WorkflowRun.org_id == org.id))
    await db.execute(
        WorkflowDefinition.__table__.update()
        .where(WorkflowDefinition.org_id == org.id)
        .values(run_count=0, success_count=0, last_run_at=None)
    )

    await db.execute(
        delete(approvals_service.ToolApproval).where(approvals_service.ToolApproval.org_id == org.id)
    )
    await db.commit()


async def _seed_knowledge(db: AsyncSession, org: Organization, gateway: _SeedGateway) -> int:
    """Ingests the clinic documents through the real pipeline — real .docx
    bytes, real text extraction, real chunking — so the Knowledge screen and
    semantic search behave exactly as they would for a customer.
    Re-ingesting the same filename replaces the previous chunks, so this is
    idempotent on its own."""
    total = 0
    for filename, body in DOCUMENTS:
        chunks = await ingest_document(db, gateway, org.id, filename, _docx_bytes(body))
        total += len(chunks)
    return total


async def _seed_facts(db: AsyncSession, org: Organization) -> None:
    for key, value in BUSINESS_FACTS:
        await long_term.upsert_fact(db, org.id, "receptionist", key, value)


async def _seed_conversations(
    db: AsyncSession, org: Organization, contacts: dict[str, Contact], now: datetime
) -> int:
    message_count = 0
    for spec in _conversations(now):
        contact = contacts.get(spec["contact"]) if spec["contact"] else None
        started = spec["started"]
        conversation = Conversation(
            org_id=org.id,
            key=spec["key"],
            agent_slug=spec["agent"],
            channel=spec["channel"],
            contact_id=contact.id if contact else None,
            status=ConversationStatus.active,
            started_at=started,
            last_message_at=started + timedelta(minutes=2 * len(spec["turns"])),
        )
        db.add(conversation)
        await db.flush()

        for index, (role, content) in enumerate(spec["turns"]):
            is_last_assistant = role == "assistant" and index == len(spec["turns"]) - 1
            db.add(
                Message(
                    conversation_id=conversation.id,
                    role=role,
                    content=content,
                    tool_calls=spec["tools"] if is_last_assistant and spec["tools"] else None,
                    created_at=started + timedelta(minutes=2 * index),
                )
            )
            message_count += 1
    await db.commit()
    return message_count


async def _seed_filler_conversations(
    db: AsyncSession, org: Organization, contacts: dict[str, Contact], now: datetime
) -> int:
    """Spreads short enquiries across the last seven days so the analytics
    summary reads like a working week rather than a test fixture. Deterministic
    — no randomness, so two runs produce the same demo and the same numbers."""
    message_count = 0
    contact_list = list(contacts.values())

    for index, (agent, question, answer, tools) in enumerate(FILLER_ENQUIRIES):
        # Walk backwards through the week, two or three threads a day.
        day = index % 7
        hour = 9 + (index * 3) % 8
        started = now - timedelta(days=day, hours=hour)
        channel = (
            ConversationChannel.dashboard
            if agent in ("executive_assistant",)
            else (ConversationChannel.web_chat if index % 3 else ConversationChannel.whatsapp)
        )
        contact = contact_list[index % len(contact_list)] if contact_list and index % 4 else None

        conversation = Conversation(
            org_id=org.id,
            key=f"demo-enquiry-{index:02d}",
            agent_slug=agent,
            channel=channel,
            contact_id=contact.id if contact else None,
            status=ConversationStatus.active,
            started_at=started,
            last_message_at=started + timedelta(minutes=3),
        )
        db.add(conversation)
        await db.flush()

        db.add(Message(conversation_id=conversation.id, role="user", content=question, created_at=started))
        db.add(
            Message(
                conversation_id=conversation.id,
                role="assistant",
                content=answer,
                tool_calls=tools or None,
                created_at=started + timedelta(minutes=1),
            )
        )
        message_count += 2

    await db.commit()
    return message_count


async def _seed_workflows(db: AsyncSession, org: Organization, now: datetime) -> dict[str, int]:
    """Installs the three templates (all enabled for the demo) and writes a
    week of believable run history.

    The history is written directly rather than by executing the engine,
    because a demo machine has no Google Calendar or WhatsApp connected — every
    real run would be a row of honest failures. The shapes below are exactly
    what the engine produces: an approval-gated send ends `awaiting_approval`
    and did not send; a branch that found nothing ends `skipped`; a failure
    carries the plain-language reason.
    """
    definitions = await workflow_service.seed_templates(
        db,
        org.id,
        enable=[APPOINTMENT_REMINDER, TREATMENT_RECALL, NEW_LEAD_ESCALATION],
    )
    by_slug = {definition.slug: definition for definition in definitions}

    # (workflow slug, days ago, status, [(step name, status, detail)])
    history: list[tuple[str, float, RunStatus, list[tuple[str, StepStatus, str]]]] = [
        (
            APPOINTMENT_REMINDER, 0.4, RunStatus.running,
            [
                ("Read tomorrow's appointments", StepStatus.success, "Found 9 to work through."),
                ("Is there anything booked?", StepStatus.success, "Found 9 to work through."),
                ("Write the reminder", StepStatus.success, "Receptionist drafted a reply."),
                ("Send the reminder", StepStatus.awaiting_approval,
                 "Your Receptionist wants to send a WhatsApp message to a customer. "
                 "Nothing was sent until you say so."),
                ("Wait until after the appointment", StepStatus.waiting,
                 "Paused here — picking this back up in 1440 minutes."),
            ],
        ),
        (
            APPOINTMENT_REMINDER, 1.4, RunStatus.success,
            [
                ("Read tomorrow's appointments", StepStatus.success, "Found 7 to work through."),
                ("Is there anything booked?", StepStatus.success, "Found 7 to work through."),
                ("Write the reminder", StepStatus.success, "Receptionist drafted a reply."),
                ("Send the reminder", StepStatus.success, "Message sent."),
                ("Wait until after the appointment", StepStatus.waiting,
                 "Paused here — picking this back up in 1440 minutes."),
                ("Did they ever reply?", StepStatus.success,
                 "Still waiting for a reply after 1440 minutes."),
                ("Write a rebooking offer", StepStatus.success, "Receptionist drafted a reply."),
                ("Offer them a new time", StepStatus.awaiting_approval,
                 "Your Receptionist wants to send a WhatsApp message to a customer. "
                 "Nothing was sent until you say so."),
            ],
        ),
        (
            APPOINTMENT_REMINDER, 2.4, RunStatus.success,
            [
                ("Read tomorrow's appointments", StepStatus.success, "Found 6 to work through."),
                ("Is there anything booked?", StepStatus.success, "Found 6 to work through."),
                ("Write the reminder", StepStatus.success, "Receptionist drafted a reply."),
                ("Send the reminder", StepStatus.success, "Message sent."),
                ("Wait until after the appointment", StepStatus.waiting,
                 "Paused here — picking this back up in 1440 minutes."),
                ("Did they ever reply?", StepStatus.skipped, "It's already been answered."),
            ],
        ),
        (
            APPOINTMENT_REMINDER, 3.4, RunStatus.failed,
            [
                ("Read tomorrow's appointments", StepStatus.failed,
                 "Your calendar isn't connected yet, so we couldn't check tomorrow's appointments."),
            ],
        ),
        (
            TREATMENT_RECALL, 1.1, RunStatus.success,
            [
                ("Find patients who are due", StepStatus.success,
                 "4 due a follow-up after 90 days: Derek Sallis, Grace Okonkwo, "
                 "Helen Cartwright, Tom Fletcher"),
                ("Write the follow-up", StepStatus.success, "Receptionist drafted a reply."),
                ("Send the follow-up", StepStatus.awaiting_approval,
                 "Your Receptionist wants to send a WhatsApp message to a customer. "
                 "Nothing was sent until you say so."),
            ],
        ),
        (
            TREATMENT_RECALL, 8.1, RunStatus.success,
            [
                ("Find patients who are due", StepStatus.skipped,
                 "Nobody is due a follow-up after 90 days."),
            ],
        ),
        (
            NEW_LEAD_ESCALATION, 0.2, RunStatus.success,
            [
                ("Give the assistant a chance to answer", StepStatus.waiting,
                 "Paused here — picking this back up in 15 minutes."),
                ("Is it still unanswered?", StepStatus.skipped, "It's already been answered."),
            ],
        ),
        (
            NEW_LEAD_ESCALATION, 0.9, RunStatus.success,
            [
                ("Give the assistant a chance to answer", StepStatus.waiting,
                 "Paused here — picking this back up in 15 minutes."),
                ("Is it still unanswered?", StepStatus.success,
                 "Still waiting for a reply after 17 minutes."),
                ("Summarise it for whoever picks it up", StepStatus.success,
                 "Support drafted a reply."),
                ("Flag it for a human", StepStatus.success,
                 "A new enquiry has been waiting 15 minutes without a reply. Call this patient "
                 "back first — they're in pain and asked about an emergency slot."),
            ],
        ),
        (
            NEW_LEAD_ESCALATION, 2.6, RunStatus.success,
            [
                ("Give the assistant a chance to answer", StepStatus.waiting,
                 "Paused here — picking this back up in 15 minutes."),
                ("Is it still unanswered?", StepStatus.skipped, "It's already been answered."),
            ],
        ),
    ]

    runs = 0
    for slug, days_ago, status, steps in history:
        definition = by_slug[slug]
        started = now - timedelta(days=days_ago)
        run = WorkflowRun(
            org_id=org.id,
            workflow_id=definition.id,
            status=status,
            trigger_source="event" if slug == NEW_LEAD_ESCALATION else "schedule",
            context={"workflow": slug},
            next_step_index=len(steps),
            resume_at=(started + timedelta(days=1)) if status is RunStatus.running else None,
            error=(
                "Your calendar isn't connected yet, so we couldn't check tomorrow's appointments."
                if status is RunStatus.failed
                else None
            ),
            started_at=started,
            finished_at=None if status is RunStatus.running else started + timedelta(minutes=4),
        )
        db.add(run)
        await db.flush()

        for position, (name, step_status, detail) in enumerate(steps):
            db.add(
                WorkflowStepRun(
                    run_id=run.id,
                    position=position,
                    step_id=f"step_{position}",
                    name=name,
                    step_type=_step_type_for(name),
                    status=step_status,
                    detail=detail,
                    attempts=1,
                    started_at=started + timedelta(seconds=30 * position),
                    finished_at=started + timedelta(seconds=30 * position + 20),
                )
            )
        runs += 1

        definition.run_count = (definition.run_count or 0) + 1
        if status is RunStatus.success:
            definition.success_count = (definition.success_count or 0) + 1
        if definition.last_run_at is None or definition.last_run_at < started:
            definition.last_run_at = started

    await db.commit()
    return {"workflows": len(definitions), "runs": runs}


def _step_type_for(name: str) -> str:
    lowered = name.lower()
    if lowered.startswith(("wait", "give the assistant")):
        return "wait"
    if lowered.startswith(("is ", "did ", "find ")):
        return "branch"
    if lowered.startswith(("write", "summarise")):
        return "agent"
    if lowered.startswith("flag"):
        return "escalate"
    return "tool"


async def _seed_activity(db: AsyncSession, org: Organization, now: datetime) -> None:
    """An Activity feed that reads like three days of a real practice."""
    entries = [
        (now - timedelta(days=4, hours=1), "receptionist", "agent.response_generated",
         {"conversation_id": "demo-web-grace-implant-price", "tool_calls": [],
          "user_message": "How much is a dental implant?"}),
        (now - timedelta(days=3, hours=5), "support", "agent.response_generated",
         {"conversation_id": "demo-dash-derek-noshow", "tool_calls": []}),
        (now - timedelta(days=2, hours=3), "receptionist", "agent.response_generated",
         {"conversation_id": "demo-web-amina-newpatient", "tool_calls": [],
          "pending_approvals": ["Your Receptionist wants to book an appointment on your calendar."]}),
        (now - timedelta(days=2, hours=2), "receptionist", "agent.action_approved",
         {"conversation_id": "demo-web-amina-newpatient", "tool_calls": ["calendar"],
          "approval_summary": "Your Receptionist wants to book an appointment on your calendar.",
          "result": "Appointment created."}),
        (now - timedelta(days=1, hours=6), "receptionist", "agent.response_generated",
         {"conversation_id": "demo-whatsapp-tom-reschedule", "tool_calls": ["calendar"]}),
        (now - timedelta(days=1, hours=2), "receptionist", "agent.action_rejected",
         {"conversation_id": "demo-whatsapp-tom-reschedule", "tool_calls": [],
          "approval_summary": "Your Receptionist wants to send a WhatsApp message to a customer.",
          "result": "You declined this, so nothing was done."}),
        (now - timedelta(hours=20), "executive_assistant", "agent.response_generated",
         {"conversation_id": "demo-dash-week-ahead", "tool_calls": ["calendar"]}),
        (now - timedelta(hours=4), "sales", "agent.response_generated",
         {"conversation_id": "demo-dash-helen-invisalign", "tool_calls": []}),
    ]
    for created_at, actor, action, details in entries:
        db.add(AuditLog(org_id=org.id, actor=actor, action=action, details=details, created_at=created_at))
    await db.commit()


async def _seed_pending_approval(db: AsyncSession, org: Organization) -> None:
    """One action waiting on the owner, so the Approvals surface isn't empty in
    a demo. Created through the real service so the wording matches exactly
    what the runtime would produce."""
    await approvals_service.create_pending(
        db,
        org_id=org.id,
        agent_slug="receptionist",
        agent_display_name="Receptionist",
        conversation_id="demo-web-amina-newpatient",
        tool_name="calendar",
        arguments={
            "action": "create_event",
            "summary": "New patient examination — Amina Patel",
            "start_time": "2026-08-26T17:45:00",
            "end_time": "2026-08-26T18:15:00",
            "attendee_email": "amina.patel@example.co.uk",
        },
    )


async def seed(db: AsyncSession) -> dict[str, object]:
    now = datetime.now(UTC).replace(tzinfo=None)
    gateway = _SeedGateway()

    org = await _upsert_org(db)
    await _upsert_owner(db, org)
    contacts = await _upsert_contacts(db, org)
    await _clear_demo_content(db, org)

    chunks = await _seed_knowledge(db, org, gateway)
    await _seed_facts(db, org)
    messages = await _seed_conversations(db, org, contacts, now)
    messages += await _seed_filler_conversations(db, org, contacts, now)
    workflows = await _seed_workflows(db, org, now)
    await _seed_activity(db, org, now)
    await _seed_pending_approval(db, org)

    return {
        "org_id": org.id,
        "public_id": org.public_id,
        "contacts": len(contacts),
        "chunks": chunks,
        "messages": messages,
        "conversations": len(_conversations(now)) + len(FILLER_ENQUIRIES),
        "workflows": workflows["workflows"],
        "workflow_runs": workflows["runs"],
        "real_embeddings": gateway.embeddings_are_real,
    }


async def main() -> None:
    async with async_session_factory() as db:
        summary = await seed(db)

    print(f"\nSeeded demo organization: {ORG_NAME}")
    print(f"  Organization id : {summary['org_id']}")
    print(f"  Sign in as      : {OWNER_EMAIL} / {OWNER_PASSWORD}")
    print(f"  Contacts        : {summary['contacts']}")
    print(f"  Knowledge chunks: {summary['chunks']} across {len(DOCUMENTS)} documents")
    print(f"  Messages        : {summary['messages']} across {summary['conversations']} conversations")
    print(f"  Workflows       : {summary['workflows']} enabled, {summary['workflow_runs']} runs of history")
    print("  Pending approval: 1 (booking for Amina Patel)")
    print(f"\n  Public web chat : POST /api/v1/public/chat/{summary['public_id']}")
    if not summary["real_embeddings"]:
        print(
            "\n  NOTE: no OPENAI_API_KEY is set, so the knowledge documents were stored with\n"
            "  placeholder embeddings. Everything lists and reads correctly, but semantic\n"
            "  search will return arbitrary results until you set a key and re-run this script."
        )
    print()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:  # pragma: no cover
        sys.exit(1)
