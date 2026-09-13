"""Merges an organization's activated Business Pack overrides onto a base
agent config, producing the AgentConfig the runtime actually uses for that
org + agent.

Ported from dist/mesnium-business/merge.js + projector.js in the
openclaw/claw fork, scoped to what this codebase has today: Mesnium's merge
is a four-layer chain (core defaults -> pack defaults -> customer business
context -> per-agent customer override). This codebase doesn't have the
customer-business-context layer yet (see agents/entitlements.py's docstring
— that's `context-store.js`'s port, still unbuilt), so this module only does
the two layers that currently exist:

    base agent config (core)  ->  active pack overrides (pack)

Adding the business-context layer later slots in between these two without
changing this module's public interface — get_effective_agent_config() stays
the one function callers use.

Merge semantics are deliberately additive-only, matching the principle
carried over from Mesnium ("a pack cannot grant a tool the org doesn't
already have, and customer/base intent always wins over a pack default"):

  - system_prompt: the base prompt, then one appended block per active pack
    that declares `extra_system_prompt` for this agent — never a
    replacement.
  - allowed_tools / requires_approval: the base list, extended with any
    pack-declared entries not already present. Nothing already on the base
    agent config is ever removed or shadowed by a pack.

Multiple active packs are applied in a fixed order (sorted by pack_id) so
the resulting prompt is reproducible across requests — "which pack's text
comes first" should never depend on dict/set iteration order or on when
each pack happened to be activated.

Returns a plain `AgentConfig` (not a new type), so the only caller that
matters today — agents/runtime/pipeline.py — needs no changes beyond calling
this instead of `load_agent_config()` directly. A `ConfigProvenance` is
returned alongside for anything that wants to show or audit *why* a given
prompt/tool/approval is present, mirroring Mesnium's provenance tracking;
nothing reads it yet beyond the audit event pipeline.py now attaches it to.
"""

import uuid
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from src.agents import entitlements
from src.agents.runtime.loader import AgentConfig, load_agent_config
from src.agents.runtime.pack_loader import Pack, PackNotFoundError, get_pack


@dataclass
class ConfigProvenance:
    """Which pack (if any) contributed each addition.

    `applied_pack_ids` lists packs in the order their system_prompt text was
    appended. The two `*_sources` dicts map one entry in the final
    allowed_tools / requires_approval list to the pack_id that added it — an
    entry with no key present came from the base agent config, not a pack.
    """

    applied_pack_ids: list[str] = field(default_factory=list)
    allowed_tools_sources: dict[str, str] = field(default_factory=dict)
    requires_approval_sources: dict[str, str] = field(default_factory=dict)


async def get_effective_agent_config(
    db: AsyncSession, org_id: uuid.UUID, agent_slug: str
) -> tuple[AgentConfig, ConfigProvenance]:
    base = load_agent_config(agent_slug)
    active_pack_ids = await entitlements.list_active_pack_ids(db, org_id)
    if not active_pack_ids:
        return base, ConfigProvenance()

    packs: list[Pack] = []
    for pack_id in sorted(active_pack_ids):
        try:
            packs.append(get_pack(pack_id))
        except PackNotFoundError:
            # An entitlement can outlive its pack definition (e.g. a pack
            # renamed or retired after being sold to a customer). A dangling
            # entitlement must never break the agent for the whole org — it
            # just contributes nothing, silently, until someone cleans it up.
            continue

    return _merge(base, packs)


def _merge(base: AgentConfig, packs: list[Pack]) -> tuple[AgentConfig, ConfigProvenance]:
    provenance = ConfigProvenance()
    system_prompt = base.system_prompt
    allowed_tools = list(base.allowed_tools)
    requires_approval = list(base.requires_approval)

    for pack in packs:
        override = pack.agent_overrides.get(base.slug)
        if override is None:
            continue
        provenance.applied_pack_ids.append(pack.id)

        if override.extra_system_prompt:
            system_prompt = f"{system_prompt}\n\n[{pack.name}]\n{override.extra_system_prompt.strip()}"

        for tool in override.extra_allowed_tools:
            if tool not in allowed_tools:
                allowed_tools.append(tool)
                provenance.allowed_tools_sources[tool] = pack.id

        for entry in override.extra_requires_approval:
            if entry not in requires_approval:
                requires_approval.append(entry)
                provenance.requires_approval_sources[entry] = pack.id

    if not provenance.applied_pack_ids:
        return base, provenance

    effective = base.model_copy(
        update={
            "system_prompt": system_prompt,
            "allowed_tools": allowed_tools,
            "requires_approval": requires_approval,
        }
    )
    return effective, provenance
