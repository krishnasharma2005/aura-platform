"""Loads Business Pack definitions (id, capability requirements, per-agent
overrides) from YAML files in agents/packs/.

A pack is *purchasable configuration*, not a new agent or a new runtime —
same principle the reference Mesnium implementation used
(dist/mesnium-business/packs-registry.js in the openclaw/claw fork this was
ported from): "Real Estate Pack" tunes the existing Receptionist/Sales/
Marketing/Executive Assistant agents with industry-specific prompt fragments,
tool access, and approval requirements. It never introduces executable code —
a pack is validated YAML, exactly like the base agent configs in
agents/configs/, and is loaded the same way (see agents/runtime/loader.py).

Scope of this module: parsing and exposing pack *definitions*. Two things are
deliberately NOT done here yet, and shouldn't be assumed to work:
  1. Merging a pack's agent_overrides onto the base AgentConfig at runtime
     (the "context merge engine" — a separate, larger piece of work).
  2. Seeding a pack's workflow_templates into workflow_definitions on
     activation.
Which packs an organization has actually purchased/activated lives in
agents/entitlements.py (OrgPackEntitlement), not here — this module only
answers "what packs exist and what do they declare", the same way
agents/runtime/loader.py only answers "what agents exist and what do they
declare".
"""

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel

PACKS_DIR = Path(__file__).resolve().parent.parent / "packs"


class PackAgentOverride(BaseModel):
    """Additive tuning for one base agent when this pack is active.

    Every field here is additive, never a replacement: extra_system_prompt is
    appended to the base agent's system_prompt (not substituted for it), and
    extra_allowed_tools / extra_requires_approval extend the base agent's
    lists. A pack cannot grant a tool the org's base plan doesn't already
    have server-side access to — matching the Mesnium principle it was
    ported from ("declares capability requirements, but CANNOT grant tools").
    """

    extra_system_prompt: str | None = None
    extra_allowed_tools: list[str] = []
    extra_requires_approval: list[str] = []


class Pack(BaseModel):
    id: str
    name: str
    version: str
    category: str
    description: str
    # Advisory declaration of what an org needs connected for this pack to be
    # useful (e.g. "calendar", "crm") — checked against the org's connected
    # integrations when surfacing the pack in a checkout/settings UI, not
    # used to grant tool access by itself.
    capability_requirements: list[str] = []
    # Keyed by agent slug (must match an AgentConfig.slug in agents/configs/).
    agent_overrides: dict[str, PackAgentOverride] = {}
    # Raw workflow-definition-shaped dicts (see workflows/models.py) this pack
    # would seed on activation. Not yet wired to anything — seeding on
    # activation is future work, tracked separately from this schema.
    workflow_templates: list[dict] = []


class PackNotFoundError(Exception):
    pass


@lru_cache
def _load_all_packs() -> dict[str, Pack]:
    packs: dict[str, Pack] = {}
    for path in sorted(PACKS_DIR.glob("*.yaml")):
        with path.open() as f:
            raw = yaml.safe_load(f)
        pack = Pack.model_validate(raw)
        packs[pack.id] = pack
    return packs


def list_packs() -> list[Pack]:
    return list(_load_all_packs().values())


def get_pack(pack_id: str) -> Pack:
    packs = _load_all_packs()
    if pack_id not in packs:
        raise PackNotFoundError(f"Unknown pack: {pack_id}")
    return packs[pack_id]
