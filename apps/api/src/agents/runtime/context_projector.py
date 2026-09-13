"""Turns a stored BusinessContext into a compact, role-specific block of text
for one agent's system prompt.

Ported from dist/mesnium-business/projector.js in the openclaw/claw fork.
Same principles carried over:
  - No raw JSON dumps into the prompt — a human-readable Markdown-ish block.
  - Role-tailored: an agent only sees the sections relevant to it (the
    Receptionist doesn't need pipeline-forecasting language; Sales doesn't
    need FAQ scripts).
  - Bounded size: each section truncates long free-text fields rather than
    flooding the prompt with an owner's entire policy document.
  - Zero secrets, zero internal ids, zero file paths — this is genuinely
    just "what the owner told us about their business."

Returns "" when the org hasn't set any business context yet (a brand-new
org), so callers can unconditionally add this to the prompt without an empty
"[Business Context]" heading showing up for nothing.
"""

from src.agents.business_context import BusinessContext

_TRUNCATE = 120


def _clip(text: str, limit: int = _TRUNCATE) -> str:
    text = text.strip()
    return text if len(text) <= limit else f"{text[: limit - 3]}..."


def _bullets(items: list, limit: int, clip: int = 80) -> str:
    return "\n".join(f"  • {_clip(str(i), clip)}" for i in items[:limit])


def project_agent_business_context(context: BusinessContext, agent_slug: str) -> str:
    identity = context.identity or {}
    offerings = context.offerings or {}
    customers = context.customers or {}
    brand = context.brand or {}
    policies = context.policies or {}
    operations = context.operations or {}

    if not any([identity, offerings, customers, brand, policies, operations]):
        return ""

    sections: list[str] = []

    header_lines = [f"[Business Context: {identity.get('business_name', 'this business')}]"]
    industry_line = identity.get("industry")
    location = identity.get("location")
    if industry_line or location:
        header_lines.append(
            " | ".join(p for p in [f"Industry: {industry_line}" if industry_line else None, location] if p)
        )
    if identity.get("operating_hours"):
        header_lines.append(f"Operating Hours: {identity['operating_hours']}")
    if identity.get("description"):
        header_lines.append(f"About: {_clip(identity['description'])}")
    sections.append("\n".join(header_lines))

    if agent_slug == "receptionist":
        services = offerings.get("services") or []
        if services:
            lines = []
            for s in services[:3]:
                name = s.get("name", "") if isinstance(s, dict) else str(s)
                desc = _clip(s.get("description", ""), 60) if isinstance(s, dict) else ""
                price = s.get("pricing") if isinstance(s, dict) else None
                lines.append(f"  • {name}{f': {desc}' if desc else ''}{f' ({price})' if price else ''}")
            sections.append("[Services]\n" + "\n".join(lines))

        may_say = policies.get("things_agents_may_say") or []
        must_not = policies.get("things_agents_must_not_say") or []
        escalation = policies.get("escalation_rules") or []
        policy_lines = []
        if may_say:
            policy_lines.append(f"  • Guidance: {_clip(str(may_say[0]))}")
        if must_not:
            policy_lines.append(f"  • Must NOT say: {'; '.join(_clip(str(m), 60) for m in must_not[:2])}")
        if escalation:
            policy_lines.append(f"  • Escalate: {_clip(str(escalation[0]))}")
        if policy_lines:
            sections.append("[Business Policies]\n" + "\n".join(policy_lines))

    elif agent_slug == "sales":
        services = offerings.get("services") or []
        if services:
            lines = []
            for s in services[:3]:
                name = s.get("name", "") if isinstance(s, dict) else str(s)
                price = s.get("pricing") if isinstance(s, dict) else None
                lines.append(f"  • {name}{f' [{price}]' if price else ''}")
            sections.append("[Offerings & Pricing]\n" + "\n".join(lines))

        target = customers.get("target_customer_description")
        criteria = customers.get("qualification_criteria") or []
        cust_lines = []
        if target:
            cust_lines.append(f"  • Target profile: {_clip(target, 80)}")
        if criteria:
            cust_lines.append("  • Qualification criteria:\n" + _bullets(criteria, 3, 70))
        if cust_lines:
            sections.append("[Customer Qualification]\n" + "\n".join(cust_lines))

    elif agent_slug == "marketing":
        brand_lines = []
        if brand.get("tone"):
            brand_lines.append(f"  • Brand voice: {brand['tone']}")
        if brand.get("communication_style"):
            brand_lines.append(f"  • Style: {brand['communication_style']}")
        if brand_lines:
            sections.append("[Brand Identity]\n" + "\n".join(brand_lines))

        target = customers.get("target_customer_description")
        if target:
            sections.append(f"[Target Audience]\n  • {_clip(target, 100)}")

    elif agent_slug == "executive_assistant":
        priorities = operations.get("priorities") or []
        approval_rules = policies.get("approval_requirements") or []
        exec_lines = []
        if priorities:
            exec_lines.append("  • Priorities:\n" + _bullets(priorities, 3))
        if approval_rules:
            exec_lines.append("  • Approval rules:\n" + _bullets(approval_rules, 2))
        if exec_lines:
            sections.append("[Executive Priorities]\n" + "\n".join(exec_lines))

    else:
        # support, ecommerce, and anything else added later: a small, generic
        # fallback rather than an agent-specific branch for every slug.
        if brand.get("tone"):
            sections.append(f"[Tone]\n  • {brand['tone']}")
        rules = policies.get("business_rules") or []
        if rules:
            sections.append("[Business Rules]\n" + _bullets(rules, 3))

    return "\n\n".join(sections)
