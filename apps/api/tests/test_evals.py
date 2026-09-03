"""Runs every eval scenario in src/evals/cases/ through the real harness
(src/evals/runner.py) against a scripted gateway, so the expanded eval suite
is more than YAML that nobody executes — every scenario listed here is proven
to pass against the runtime today, and would fail this test the day the
runtime's behavior regresses.

Coverage intentionally spans more than the original two happy-path
Receptionist cases: a refusal, an ambiguous request needing clarification, a
tool call outside an agent's allowed_tools, and multiple scenarios each for
Sales, Support, and the Executive Assistant against their actual configured
capabilities (see agents/configs/*.yaml).
"""

from unittest.mock import AsyncMock

import pytest_asyncio

from src.agents.runtime import pipeline as pipeline_module
from src.evals.runner import load_scenarios, run_scenario


@pytest_asyncio.fixture(autouse=True)
def _no_knowledge_search(monkeypatch):
    async def _empty_search(*args, **kwargs):
        return []

    monkeypatch.setattr(pipeline_module, "search_knowledge", _empty_search)


def test_at_least_fourteen_scenarios_exist_across_four_agents():
    scenarios = load_scenarios()
    assert len(scenarios) >= 14

    by_agent: dict[str, int] = {}
    for scenario in scenarios:
        by_agent[scenario.agent] = by_agent.get(scenario.agent, 0) + 1

    assert by_agent.get("receptionist", 0) >= 3
    assert by_agent.get("sales", 0) >= 2
    assert by_agent.get("support", 0) >= 2
    assert by_agent.get("executive_assistant", 0) >= 2


def test_scenario_names_are_unique():
    scenarios = load_scenarios()
    names = [s.name for s in scenarios]
    assert len(names) == len(set(names))


async def test_every_scenario_passes_against_the_runtime(db_session, user_and_org):
    _, org, _ = user_and_org
    scenarios = load_scenarios()
    assert scenarios, "no eval scenarios were loaded"

    # Never actually used — every current scenario scripts its own gateway via
    # mock_turns. Kept so run_scenario's signature (which supports spot-check
    # scenarios without mock_turns, against a real gateway) is exercised
    # unchanged.
    unused_gateway = AsyncMock()

    failures = []
    for scenario in scenarios:
        result = await run_scenario(db_session, unused_gateway, org.id, scenario)
        if not result.passed:
            failures.append(f"{scenario.name}: {result.failures}")

    assert not failures, "\n".join(failures)


async def test_refusal_scenario_does_not_guess_at_medical_advice(db_session, user_and_org):
    _, org, _ = user_and_org
    scenarios = {s.name: s for s in load_scenarios()}
    scenario = scenarios["receptionist_refusal_medical_advice"]
    result = await run_scenario(db_session, AsyncMock(), org.id, scenario)
    assert result.passed, result.failures


async def test_ambiguous_request_asks_for_clarification_instead_of_guessing(db_session, user_and_org):
    _, org, _ = user_and_org
    scenarios = {s.name: s for s in load_scenarios()}
    scenario = scenarios["receptionist_ambiguous_needs_clarification"]
    result = await run_scenario(db_session, AsyncMock(), org.id, scenario)
    assert result.passed, result.failures


async def test_tool_outside_allowed_tools_is_blocked_not_executed(db_session, user_and_org):
    _, org, _ = user_and_org
    scenarios = {s.name: s for s in load_scenarios()}
    for name in ("receptionist_tool_outside_allowed_blocked", "executive_assistant_tool_outside_allowed_blocked"):
        result = await run_scenario(db_session, AsyncMock(), org.id, scenarios[name])
        assert result.passed, f"{name}: {result.failures}"
