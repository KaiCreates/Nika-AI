"""BaseTool ABC — all tools inherit from this."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseTool(ABC):
    # Override these in subclasses
    name: str = ""
    description: str = ""
    parameters: dict[str, Any] = {}   # JSON Schema properties dict
    required: list[str] = []
    safety_level: str = "SAFE"        # SAFE | CAUTION | DANGEROUS

    @abstractmethod
    async def execute(self, **kwargs: Any) -> str:
        """Execute the tool. Returns a string result."""

    def to_manifest(self) -> str:
        """Render this tool as a markdown description for the LLM prompt."""
        params = []
        for k, v in self.parameters.items():
            typ = v.get("type", "string")
            desc = v.get("description", "")
            req = "required" if k in self.required else "optional"
            params.append(f"  - `{k}` ({typ}, {req}): {desc}")
        param_str = "\n".join(params) if params else "  (no parameters)"
        return (
            f"### `{self.name}`\n"
            f"{self.description}\n"
            f"**Parameters:**\n{param_str}\n"
            f"**Safety:** {self.safety_level}"
        )

    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": self.parameters,
                "required": self.required,
            },
            "safety_level": self.safety_level,
        }
