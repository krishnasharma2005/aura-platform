"""Predefined, menu-driven chat flows.

Temporary stand-in for agents whose config sets `chat_mode: scripted` (see
agents/runtime/loader.py). Used today by the Receptionist only, while
OPENAI_API_KEY is unset — the real AI pipeline (agents/runtime/pipeline.py)
is untouched and takes over again the moment `chat_mode` is removed from an
agent's YAML.
"""
