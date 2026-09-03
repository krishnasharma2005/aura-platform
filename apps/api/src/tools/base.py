"""Abstract Tool interface. Every tool the agent runtime can call implements
this: a name/description/JSON-schema for the LLM tool-calling format, and an
async execute() that performs the real (or stubbed-pending-credentials) action."""

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession


class ToolResult(BaseModel):
    success: bool
    data: dict[str, Any] = {}
    message: str = ""


class Tool(ABC):
    name: str
    description: str
    input_schema: dict[str, Any]

    @abstractmethod
    async def execute(self, db: AsyncSession, org_id: Any, **kwargs: Any) -> ToolResult:
        raise NotImplementedError

    def to_llm_schema(self) -> dict[str, Any]:
        """OpenAI function-calling formatted tool definition."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.input_schema,
        }

    def validate_arguments(self, arguments: Any) -> tuple[dict[str, Any], str | None]:
        """Checks model-supplied arguments against `input_schema` before they
        reach `execute()`. Returns (safe_arguments, error_message).

        Model output is untrusted input: it may omit required fields, invent
        extra ones, or not be an object at all. Anything not declared in the
        schema is dropped so it can never be splatted into `execute()` as an
        unexpected keyword, and a missing required field becomes a message the
        model can recover from rather than a 500 in the customer's chat.
        """
        if not isinstance(arguments, dict):
            return {}, f"The {self.name} tool needs its details as a set of named fields."

        properties = self.input_schema.get("properties", {})
        safe = {key: value for key, value in arguments.items() if key in properties}

        missing = [key for key in self.input_schema.get("required", []) if safe.get(key) in (None, "")]
        if missing:
            return safe, f"Missing required detail(s) for the {self.name} tool: {', '.join(missing)}."
        return safe, None
