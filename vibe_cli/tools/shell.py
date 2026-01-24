import asyncio
import shlex
from pathlib import Path

from vibe_cli.models.tools import ToolParameter
from vibe_cli.tools.base import Tool, ToolDefinition, ToolResult


class ShellTool(Tool):
    def __init__(self, workspace: Path, allowed_commands: list[str] | None = None, blocked_patterns: list[str] | None = None):
        self.workspace = workspace
        self.allowed = set(allowed_commands or ["ls", "cat", "grep", "git", "pytest", "npm", "echo", "pwd", "mkdir", "touch"])
        self.blocked = blocked_patterns or ["rm -rf", "> /dev/", "sudo"]
        self.timeout = 30

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="run_command",
            description=f"Run a shell command. Allowed: {', '.join(self.allowed)}",
            parameters=[
                ToolParameter(name="command", type="string", description="Command to execute"),
                ToolParameter(name="cwd", type="string", description="Working directory (relative)", required=False),
            ],
            dangerous=True,
        )

    async def execute(self, command: str, cwd: str | None = None) -> ToolResult:
        # Security checks
        for blocked in self.blocked:
            if blocked in command:
                return ToolResult(
                    tool_call_id="",
                    content=f"Error: Command contains blocked pattern: {blocked}",
                    is_error=True,
                )

        # Check if base command is allowed
        parts = shlex.split(command)
        if parts and parts[0] not in self.allowed:
            return ToolResult(
                tool_call_id="",
                content=f"Error: Command '{parts[0]}' not in allowed list. Allowed: {', '.join(self.allowed)}",
                is_error=True,
            )

        work_dir = self.workspace
        if cwd:
            work_dir = (self.workspace / cwd).resolve()
            if not str(work_dir).startswith(str(self.workspace.resolve())):
                return ToolResult(tool_call_id="", content="Error: cwd escapes workspace", is_error=True)

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                cwd=work_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self.timeout)
            except asyncio.TimeoutError:
                proc.kill()
                return ToolResult(
                    tool_call_id="",
                    content=f"Error: Command timed out after {self.timeout}s",
                    is_error=True,
                )

            output_parts = []
            if stdout:
                output_parts.append(f"STDOUT:\n{stdout.decode()}")
            if stderr:
                output_parts.append(f"STDERR:\n{stderr.decode()}")

            output = "\n".join(output_parts) or "(no output)"

            if proc.returncode != 0:
                return ToolResult(
                    tool_call_id="",
                    content=f"Command failed (exit {proc.returncode}):\n{output}",
                    is_error=True,
                )

            return ToolResult(tool_call_id="", content=output, is_error=False)

        except Exception as e:
            return ToolResult(tool_call_id="", content=f"Error: {e}", is_error=True)
