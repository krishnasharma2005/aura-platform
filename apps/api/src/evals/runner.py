"""A simple eval harness: loads scenario files from evals/cases/, runs each
through the agent runtime (with a supplied AIGateway — typically a mocked one
in CI, a real one for manual spot-checks), and asserts on expected properties.

A scenario file (YAML) looks like:

    agent: receptionist
    input: "What are your business hours?"
    expect:
      contains: ["9", "5"]        # substrings expected somewhere in the response
      tool_called: null           # or a tool name expected to have been called
      approval_requested: null    # or a tool name expected to be queued for
                                  # human approval instead of being executed
"""

import uuid
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import yaml
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.runtime.pipeline import run_agent
from src.ai_gateway.gateway import AIGateway
from src.ai_gateway.providers.base import LLMResponse, ToolCall
from src.core.exceptions import PermissionError as AuraPermissionError

CASES_DIR = Path(__file__).resolve().parent / "cases"


class EvalExpectation(BaseModel):
    contains: list[str] = []
    not_contains: list[str] = []
    tool_called: str | None = None
    approval_requested: str | None = None
    # For the "an agent must not be able to use a tool outside its
    # allowed_tools" class of scenario: the runtime is expected to reject the
    # call rather than execute it or silently drop it.
    blocked: bool = False


class MockToolCall(BaseModel):
    name: str
    arguments: dict[str, Any] = {}


class MockTurn(BaseModel):
    """One scripted `gateway.complete()` response. `content` is the model's
    text for that turn; `tool_calls`, if present, are what the runtime sees
    as requested tool calls."""

    content: str = ""
    tool_calls: list[MockToolCall] = []


class EvalScenario(BaseModel):
    name: str
    agent: str
    input: str
    expect: EvalExpectation
    # Optional scripted model turns. When present, the scenario builds its own
    # gateway and ignores whatever gateway `run_all`/`run_scenario` was given —
    # this is what makes these scenarios runnable in CI without a live AI
    # provider, deterministic, and self-contained. Omit for a scenario meant
    # to be spot-checked against a real provider instead.
    mock_turns: list[MockTurn] = []


class EvalResult(BaseModel):
    scenario_name: str
    passed: bool
    failures: list[str] = []


def load_scenarios() -> list[EvalScenario]:
    scenarios = []
    for path in sorted(CASES_DIR.glob("*.yaml")):
        with path.open() as f:
            raw = yaml.safe_load(f)
        raw.setdefault("name", path.stem)
        scenarios.append(EvalScenario.model_validate(raw))
    return scenarios


def _scripted_gateway(scenario: EvalScenario) -> AIGateway:
    """Builds a gateway that replays `scenario.mock_turns` in order (the last
    one repeats if the runtime asks for more than were scripted), so a
    scenario that needs to force a specific tool call — or a model that
    (mis)behaves and tries to use a tool it shouldn't — can do so
    deterministically."""
    responses = [
        LLMResponse(
            content=turn.content,
            tool_calls=[
                ToolCall(id=f"eval-call-{i}-{j}", name=tc.name, arguments=tc.arguments)
                for j, tc in enumerate(turn.tool_calls)
            ],
        )
        for i, turn in enumerate(scenario.mock_turns)
    ]

    async def _complete(*args: Any, **kwargs: Any) -> LLMResponse:
        if len(responses) > 1:
            return responses.pop(0)
        return responses[0]

    gateway = AsyncMock(spec=AIGateway)
    gateway.complete = AsyncMock(side_effect=_complete)
    gateway.embed = AsyncMock(return_value=[[0.0] * 1536])
    return gateway


async def run_scenario(
    db: AsyncSession, gateway: AIGateway, org_id: uuid.UUID, scenario: EvalScenario
) -> EvalResult:
    failures: list[str] = []
    effective_gateway = _scripted_gateway(scenario) if scenario.mock_turns else gateway

    blocked_error: Exception | None = None
    try:
        result = await run_agent(
            db=db,
            gateway=effective_gateway,
            org_id=org_id,
            agent_slug=scenario.agent,
            conversation_id=f"eval-{scenario.name}-{uuid.uuid4()}",
            user_message=scenario.input,
        )
    except AuraPermissionError as exc:
        blocked_error = exc
        result = None

    if scenario.expect.blocked:
        if blocked_error is None:
            failures.append(
                "Expected the runtime to refuse this tool call (outside allowed_tools), but it ran."
            )
        return EvalResult(scenario_name=scenario.name, passed=not failures, failures=failures)

    if blocked_error is not None:
        failures.append(f"Unexpected permission error: {blocked_error}")
        return EvalResult(scenario_name=scenario.name, passed=not failures, failures=failures)

    assert result is not None  # for type-checkers; guaranteed by the branches above

    for expected_substring in scenario.expect.contains:
        if expected_substring.lower() not in result.response.lower():
            failures.append(f"Expected response to contain '{expected_substring}', got: {result.response!r}")

    for unwanted_substring in scenario.expect.not_contains:
        if unwanted_substring.lower() in result.response.lower():
            failures.append(f"Expected response NOT to contain '{unwanted_substring}', got: {result.response!r}")

    if scenario.expect.tool_called is not None and scenario.expect.tool_called not in result.tool_calls_made:
        failures.append(
            f"Expected tool '{scenario.expect.tool_called}' to be called, but got: {result.tool_calls_made}"
        )

    if scenario.expect.approval_requested is not None:
        requested = [approval.tool for approval in result.pending_approvals]
        if scenario.expect.approval_requested not in requested:
            failures.append(
                f"Expected '{scenario.expect.approval_requested}' to be queued for approval, but got: {requested}"
            )
        if scenario.expect.approval_requested in result.tool_calls_made:
            failures.append(
                f"'{scenario.expect.approval_requested}' was executed without approval — it must wait for a human."
            )

    return EvalResult(scenario_name=scenario.name, passed=not failures, failures=failures)


async def run_all(db: AsyncSession, gateway: AIGateway, org_id: uuid.UUID) -> list[EvalResult]:
    return [await run_scenario(db, gateway, org_id, scenario) for scenario in load_scenarios()]
