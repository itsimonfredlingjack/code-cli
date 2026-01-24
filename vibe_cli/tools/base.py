from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from vibe_cli.models.tools import ToolDefinition, ToolResult


class Tool(ABC):
    @property
    @abstractmethod
    def definition(self) -> ToolDefinition:
        """Return tool schema for LLM"""
        ...

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """Execute the tool"""
        ...

class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.definition.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def all_definitions(self) -> List[ToolDefinition]:
        return [t.definition for t in self._tools.values()]

    async def execute(self, name: str, arguments: dict) -> ToolResult:
        tool = self._tools.get(name)
        if not tool:
            return ToolResult(
                tool_call_id="",
                content=f"Unknown tool: {name}",
                is_error=True,
            )
        return await tool.execute(**arguments)
