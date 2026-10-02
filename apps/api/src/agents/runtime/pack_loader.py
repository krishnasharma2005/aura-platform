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

Scope of this module: parsing and exposing pack *definitions*. How a pack takes
effect lives elsewhere:
  - agents/runtime/effective_config.py merges an active pack's agent_overrides
    onto the base agent config on every turn (and in workflow tool steps).
  - agents/entitlements.py records which packs an org has activated, and on
    activation installs the pack's `workflow_templates` as (switched-off)
    workflow definitions via workflows/service.py.
Which packs an organization has actually purchased/activated lives in
agents/entitlements.py (OrgPackEntitlement), not here — this module only
answers "what packs exist and what do they declare", the same way
agents/runtime/loader.py only answers "what agents exist and what do they
declare".
"""

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, model_validator

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
    # Workflow definitions this pack installs (switched off) when an org
    # activates it. Same shape as workflows/templates.py — steps use the
    # engine's real vocabulary — and checked against the engine's own rules at
    # load time, so a pack that couldn't run fails here, not in a customer's
    # account.
    workflow_templates: list[dict] = []

    @model_validator(mode="after")
    def _workflow_templates_are_runnable(self) -> "Pack":
        # Imported here: the workflow engine imports the agent runtime, which
        # imports this module.
        from src.workflows.steps import validate_definition

        problems = [p for template in self.workflow_templates for p in validate_definition(template)]
        if problems:
            raise ValueError(f"Pack '{self.id}' has workflows that can't run: " + " ".join(problems))
        return self


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
