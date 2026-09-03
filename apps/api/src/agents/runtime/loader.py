"""Loads agent configs (prompt, memory scope, allowed tools, permissions) from
YAML files in agents/configs/."""

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel

CONFIGS_DIR = Path(__file__).resolve().parent.parent / "configs"


class AgentConfig(BaseModel):
    slug: str
    display_name: str
    # One plain-language line shown on the agent card in the dashboard. Unlike
    # system_prompt, this is safe to send to the browser.
    description: str | None = None
    system_prompt: str
    memory_scope: str
    allowed_tools: list[str] = []
    knowledge_enabled: bool = False
    # Consequential actions that a human must approve before the runtime will
    # execute them (architecture doc: "Human approval precedes critical
    # operations"). Entries are either a whole tool ("gmail") or a single
    # action within a tool ("calendar:cancel_event"). Enforced server-side in
    # the pipeline — the system prompt is never the enforcement point.
    requires_approval: list[str] = []
    # Temporary stand-in while the real AI pipeline requires an OpenAI key
    # that isn't configured yet. "scripted" routes this agent's chat endpoint
    # through a predefined decision-tree (src/agents/scripted/) instead of
    # run_agent — see api/v1/agents.py and api/v1/public.py. Unset (None)
    # keeps the normal AI-driven behavior. Remove once a real key exists.
    chat_mode: str | None = None


class AgentNotFoundError(Exception):
    pass


@lru_cache
def _load_all_configs() -> dict[str, AgentConfig]:
    configs: dict[str, AgentConfig] = {}
    for path in sorted(CONFIGS_DIR.glob("*.yaml")):
        with path.open() as f:
            raw = yaml.safe_load(f)
        config = AgentConfig.model_validate(raw)
        configs[config.slug] = config
    return configs


def list_agent_configs() -> list[AgentConfig]:
    return list(_load_all_configs().values())


def load_agent_config(slug: str) -> AgentConfig:
    configs = _load_all_configs()
    if slug not in configs:
        raise AgentNotFoundError(f"Unknown agent: {slug}")
    return configs[slug]
