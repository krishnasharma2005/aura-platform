"""Workflow engine: database-stored automation definitions, a scheduled and
event-driven runner, and persisted run history.

    models.py     tables (definitions, runs, per-step results)
    steps.py      step shapes, {{placeholder}} rendering, condition registry
    engine.py     the executor — including the approval gate on tool steps
    templates.py  the three pre-built templates and why they're those three
    service.py    org-scoped reads/writes + the claim/lock primitives
    runner.py     the asyncio scheduler and the event-bus bridge
"""
