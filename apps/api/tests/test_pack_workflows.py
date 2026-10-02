"""Business Packs wired into the workflow engine: the dental pack, pack
workflows installed on activation, and the "run a test" endpoint."""

import pytest
from sqlalchemy import select

from src.agents import entitlements
from src.agents.runtime.pack_loader import get_pack, list_packs
from src.workflows import engine, service
from src.workflows.models import RunStatus, StepStatus, TriggerType, WorkflowDefinition
from src.workflows.steps import check_message_matches_keywords, validate_definition
from src.workflows.templates import TEMPLATES

DENTAL = "pack_dental"
REAL_ESTATE = "pack_real_estate"


# ---------------------------------------------------------------- definitions


def test_every_builtin_template_is_runnable():
    for template in TEMPLATES:
        assert validate_definition(template) == [], template["slug"]


def test_every_pack_workflow_is_runnable():
    packs = list_packs()
    assert {pack.id for pack in packs} >= {DENTAL, REAL_ESTATE}
    for pack in packs:
        for template in pack.workflow_templates:
            assert validate_definition(template) == [], f"{pack.id}/{template['slug']}"


def test_dental_pack_tunes_the_agents_and_brings_two_workflows():
    pack = get_pack(DENTAL)
    assert set(pack.agent_overrides) == {"receptionist", "sales", "marketing", "executive_assistant", "support"}
    assert {t["slug"] for t in pack.workflow_templates} == {"dental-urgent-triage", "dental-hygiene-recall"}
    # The pack's guidance is plain text an owner or dentist could edit.
    assert "never diagnose" in pack.agent_overrides["receptionist"].extra_system_prompt.lower()


def test_a_pack_with_a_workflow_the_engine_cannot_run_is_rejected():
    from src.agents.runtime.pack_loader import Pack

    broken = {
        "id": "pack_broken",
        "name": "Broken",
        "version": "1",
        "category": "x",
        "description": "x",
        "workflow_templates": [
            {
                "slug": "bad",
                "name": "Bad",
                "description": "Bad",
                "trigger_type": "event",
                "trigger_config": {"event": "lead.received"},  # not a real event
                "steps": [{"id": "a", "type": "teleport"}],  # not a real step type
            }
        ],
    }
    with pytest.raises(ValueError) as error:
        Pack.model_validate(broken)
    assert "lead.received" in str(error.value)
    assert "teleport" in str(error.value)


async def test_keyword_check_matches_whole_words_only():
    params = {"keywords": ["pain", "knocked out"]}

    async def check(message: str):
        return await check_message_matches_keywords(None, None, {"last_message": message}, params)

    assert (await check("My tooth is KNOCKED OUT")).passed is True
    assert (await check("I have a lot of pain")).passed is True
    assert (await check("I'd like to book a clean")).passed is False
    assert (await check("I'm painting the waiting room")).passed is False  # 'pain' inside 'painting'


# ----------------------------------------------------------------- activation


async def _definitions(db_session, org_id):
    rows = (await db_session.execute(select(WorkflowDefinition).where(WorkflowDefinition.org_id == org_id))).scalars()
    return {row.slug: row for row in rows}


async def test_activating_a_pack_installs_its_workflows_switched_off(db_session, user_and_org):
    _, org, _ = user_and_org

    await entitlements.activate_pack(db_session, org.id, DENTAL)

    definitions = await _definitions(db_session, org.id)
    assert {"dental-urgent-triage", "dental-hygiene-recall"} <= set(definitions)
    for slug in ("dental-urgent-triage", "dental-hygiene-recall"):
        assert definitions[slug].enabled is False
        assert definitions[slug].trigger_config["pack_id"] == DENTAL
        assert definitions[slug].next_run_at is None
    assert definitions["dental-urgent-triage"].trigger_type is TriggerType.event
    assert definitions["dental-hygiene-recall"].trigger_type is TriggerType.schedule


async def test_reactivating_keeps_the_owners_choice_and_does_not_duplicate(db_session, user_and_org):
    _, org, _ = user_and_org
    await entitlements.activate_pack(db_session, org.id, DENTAL)
    definitions = await _definitions(db_session, org.id)
    await service.set_enabled(db_session, org.id, definitions["dental-hygiene-recall"].id, True)

    await entitlements.activate_pack(db_session, org.id, DENTAL)

    after = await _definitions(db_session, org.id)
    assert len([slug for slug in after if slug.startswith("dental-")]) == 2
    assert after["dental-hygiene-recall"].enabled is True
    assert after["dental-hygiene-recall"].next_run_at is not None


async def test_deactivating_switches_the_packs_workflows_off_but_keeps_them(db_session, user_and_org):
    _, org, _ = user_and_org
    await entitlements.activate_pack(db_session, org.id, DENTAL)
    definitions = await _definitions(db_session, org.id)
    await service.set_enabled(db_session, org.id, definitions["dental-urgent-triage"].id, True)
    await service.set_enabled(db_session, org.id, definitions["dental-hygiene-recall"].id, True)

    await entitlements.deactivate_pack(db_session, org.id, DENTAL)

    after = await _definitions(db_session, org.id)
    assert after["dental-urgent-triage"].enabled is False
    assert after["dental-hygiene-recall"].enabled is False
    assert after["dental-hygiene-recall"].next_run_at is None


async def test_deactivating_one_pack_leaves_another_packs_workflows_alone(db_session, user_and_org):
    _, org, _ = user_and_org
    await entitlements.activate_pack(db_session, org.id, DENTAL)
    await entitlements.activate_pack(db_session, org.id, REAL_ESTATE)
    definitions = await _definitions(db_session, org.id)
    await service.set_enabled(db_session, org.id, definitions["real-estate-buyer-enquiry"].id, True)

    await entitlements.deactivate_pack(db_session, org.id, DENTAL)

    after = await _definitions(db_session, org.id)
    assert after["real-estate-buyer-enquiry"].enabled is True


async def test_workflows_list_includes_standard_and_pack_workflows_even_if_a_pack_came_first(
    client, user_and_org
):
    _, org, headers = user_and_org
    activated = await client.post(f"/api/v1/organizations/{org.id}/packs/{DENTAL}/activate", headers=headers)
    assert activated.status_code == 200

    listed = await client.get("/api/v1/workflows", headers=headers)

    assert listed.status_code == 200
    body = listed.json()
    names = {w["name"] for w in body}
    assert "Appointment reminders and no-show recovery" in names  # a standard one
    assert "Urgent dental symptom alert" in names  # from the pack
    dental = next(w for w in body if w["name"] == "Urgent dental symptom alert")
    assert dental["pack_id"] == DENTAL
    assert dental["trigger_type"] == "event"
    assert dental["enabled"] is False


# ------------------------------------------------------------------- test run


async def _workflow_id(client, headers, name: str) -> str:
    listed = await client.get("/api/v1/workflows", headers=headers)
    return next(w["id"] for w in listed.json() if w["name"] == name)


async def test_a_test_run_of_urgent_triage_flags_an_urgent_message(client, user_and_org):
    _, org, headers = user_and_org
    await client.post(f"/api/v1/organizations/{org.id}/packs/{DENTAL}/activate", headers=headers)
    workflow_id = await _workflow_id(client, headers, "Urgent dental symptom alert")

    response = await client.post(
        f"/api/v1/workflows/{workflow_id}/run",
        json={"message": "Help, my tooth got knocked out and it's bleeding"},
        headers=headers,
    )

    assert response.status_code == 200
    run = response.json()
    assert run["status"] == "success"
    by_name = {step["name"]: step for step in run["steps"]}
    assert by_name["Does this sound urgent?"]["status"] == "success"
    # The alert must land even though no AI provider is configured in tests.
    assert by_name["Flag it for the team now"]["status"] == "success"
    assert "urgent dental symptom" in by_name["Flag it for the team now"]["detail"].lower()


async def test_a_test_run_ignores_an_ordinary_message(client, user_and_org):
    _, org, headers = user_and_org
    await client.post(f"/api/v1/organizations/{org.id}/packs/{DENTAL}/activate", headers=headers)
    workflow_id = await _workflow_id(client, headers, "Urgent dental symptom alert")

    response = await client.post(
        f"/api/v1/workflows/{workflow_id}/run",
        json={"message": "Hi, can I book a check-up for next month?"},
        headers=headers,
    )

    run = response.json()
    assert run["status"] == "success"
    assert [step["name"] for step in run["steps"]] == ["Does this sound urgent?"]
    assert run["steps"][0]["status"] == "skipped"


async def test_a_test_run_counts_as_a_run_and_is_visible_in_history(client, user_and_org):
    _, org, headers = user_and_org
    await client.post(f"/api/v1/organizations/{org.id}/packs/{DENTAL}/activate", headers=headers)
    workflow_id = await _workflow_id(client, headers, "Urgent dental symptom alert")

    await client.post(f"/api/v1/workflows/{workflow_id}/run", json={"message": "swelling"}, headers=headers)

    runs = (await client.get(f"/api/v1/workflows/{workflow_id}/runs", headers=headers)).json()
    assert len(runs) == 1
    listed = (await client.get("/api/v1/workflows", headers=headers)).json()
    assert next(w for w in listed if w["id"] == workflow_id)["run_count"] == 1


async def test_a_test_run_is_not_picked_up_a_second_time_by_the_background_runner(
    client, user_and_org, db_session
):
    from src.workflows import runner

    _, org, headers = user_and_org
    await client.post(f"/api/v1/organizations/{org.id}/packs/{DENTAL}/activate", headers=headers)
    workflow_id = await _workflow_id(client, headers, "Urgent dental symptom alert")
    await client.post(f"/api/v1/workflows/{workflow_id}/run", json={"message": "swelling"}, headers=headers)

    counts = await runner.tick()

    assert counts["advanced"] == 0


async def test_only_owners_and_admins_can_run_a_test(client, user_and_org, db_session):
    from src.core.security import create_access_token
    from src.identity.models import Membership, MembershipRole, User

    _, org, headers = user_and_org
    await client.post(f"/api/v1/organizations/{org.id}/packs/{DENTAL}/activate", headers=headers)
    workflow_id = await _workflow_id(client, headers, "Urgent dental symptom alert")

    member = User(email="member@example.com", hashed_password="x", name="Member")
    db_session.add(member)
    await db_session.flush()
    db_session.add(Membership(user_id=member.id, organization_id=org.id, role=MembershipRole.member, accepted=True))
    await db_session.commit()
    member_headers = {
        "Authorization": f"Bearer {create_access_token(member.id)}",
        "X-Organization-Id": str(org.id),
    }

    response = await client.post(f"/api/v1/workflows/{workflow_id}/run", json={}, headers=member_headers)

    assert response.status_code == 403


async def test_a_workflow_id_from_another_org_cannot_be_run(client, user_and_org):
    _, org, headers = user_and_org
    response = await client.post(
        "/api/v1/workflows/00000000-0000-0000-0000-000000000000/run", json={}, headers=headers
    )
    assert response.status_code == 404


# -------------------------------------------------- packs govern workflow tools


def _tool_workflow(db_session, org_id) -> WorkflowDefinition:
    definition = WorkflowDefinition(
        org_id=org_id,
        slug="book-a-showing",
        name="Book a showing",
        description="x",
        trigger_type=TriggerType.event,
        trigger_config={"event": "conversation.message_received"},
        steps=[
            {
                "id": "book",
                "name": "Book the showing",
                "type": "tool",
                "tool": "calendar",
                "as_agent": "sales",
                "arguments": {
                    "action": "create_event",
                    "summary": "Showing",
                    "start_time": "2026-10-10T10:00:00",
                    "end_time": "2026-10-10T11:00:00",
                },
            }
        ],
        enabled=True,
    )
    db_session.add(definition)
    return definition


async def _run_it(db_session, definition):
    await db_session.commit()
    run = await engine.start_run(db_session, definition, trigger_source="manual", claim_for="test")
    run = await engine.execute_run(db_session, run, definition, gateway=None)
    steps = await service.get_step_runs(db_session, [run.id])
    return run, steps[run.id]


async def test_a_workflow_tool_step_cannot_use_a_tool_the_base_agent_lacks(db_session, user_and_org):
    _, org, _ = user_and_org
    definition = _tool_workflow(db_session, org.id)

    run, steps = await _run_it(db_session, definition)

    # The base Sales agent has no calendar access and no pack is active.
    assert run.status is RunStatus.failed
    assert steps[0].status is StepStatus.failed
    assert "isn't allowed" in steps[0].detail


async def test_an_active_pack_extends_and_gates_a_workflow_tool_step(db_session, user_and_org):
    _, org, _ = user_and_org
    await entitlements.activate_pack(db_session, org.id, REAL_ESTATE)
    definition = _tool_workflow(db_session, org.id)

    run, steps = await _run_it(db_session, definition)

    # The real estate pack gives Sales the calendar *and* requires approval to
    # book — so the step must queue for the owner instead of booking.
    assert steps[0].status is StepStatus.awaiting_approval
    assert "Nothing was sent until you say so" in steps[0].detail
