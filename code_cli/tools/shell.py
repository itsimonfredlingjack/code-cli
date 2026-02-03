import asyncio
import shlex
from pathlib import Path

from code_cli.models.tools import ToolParameter
from code_cli.tools.base import Tool, ToolDefinition, ToolResult


class ShellTool(Tool):
    """
    Tool for executing shell commands with security controls.

    Features:
    - Allowlist: Only commands explicitly in the allowed list are permitted.
    - Blocklist: Commands containing dangerous patterns (e.g., "rm -rf", sudo) are blocked.
    - Injection Protection: Rejects commands with shell metacharacters (|, &&, ;, etc.)
      and uses `asyncio.create_subprocess_exec` (no shell=True).
    - Timeout: Kills long-running processes automatically.
    """
    # Shell metacharacters that enable command injection
    DANGEROUS_PATTERNS = [
        "|",  # Pipe (command chaining)
        "||",  # OR operator
        "&&",  # AND operator
        ";",  # Command separator
        "$(",  # Command substitution
        "`",  # Backtick command substitution
        ">",  # Output redirection
        "<",  # Input redirection
        ">>",  # Append redirection
        "&",  # Background execution
        "\n",  # Newline (command separator)
    ]

    def __init__(
        self,
        workspace: Path,
        allowed_commands: list[str] | None = None,
        blocked_patterns: list[str] | None = None,
        timeout: int = 30,
    ):
        self.workspace = workspace
        self.allowed = set(
            allowed_commands or ["ls", "cat", "grep", "git", "pytest", "npm", "echo", "pwd", "mkdir", "touch"]
        )
        self.blocked = blocked_patterns or ["rm -rf", "sudo", "/dev/"]
        self.timeout = timeout

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
        """
        Execute a shell command securely.

        Args:
            command (str): The command string to execute.
            cwd (str, optional): The directory to execute in, relative to workspace.

        Returns:
            ToolResult: Contains stdout/stderr or error message.
        """
        # Block shell metacharacters that enable injection attacks
        for pattern in self.DANGEROUS_PATTERNS:
            if pattern in command:
                return ToolResult(
                    tool_call_id="",
                    content=f"Command blocked because it contains dangerous shell metacharacter {repr(pattern)} which can enable command injection. Try: Remove {repr(pattern)} or use filesystem tools like read_file/write_file instead.",
                    is_error=True,
                )

        # Check custom blocked patterns
        for blocked in self.blocked:
            if blocked in command:
                return ToolResult(
                    tool_call_id="",
                    content=f"Error: Command contains blocked pattern: {blocked}",
                    is_error=True,
                )

        # Parse command into arguments safely
        try:
            parts = shlex.split(command)
        except ValueError as e:
            return ToolResult(
                tool_call_id="",
                content=f"Error: Invalid command syntax: {e}",
                is_error=True,
            )

        if not parts:
            return ToolResult(
                tool_call_id="",
                content="Error: Empty command",
                is_error=True,
            )

        # Check if base command is allowed
        if parts[0] not in self.allowed:
            return ToolResult(
                tool_call_id="",
                content=f"Command '{parts[0]}' not allowed because it's not in the allowlist. Try: Use allowed commands ({', '.join(sorted(self.allowed))}) or request addition to allowlist in ~/.config/code-cli/config.toml",
                is_error=True,
            )

        work_dir = self.workspace
        if cwd:
            work_dir = (self.workspace / cwd).resolve()
            if not str(work_dir).startswith(str(self.workspace.resolve())):
                return ToolResult(tool_call_id="", content="Error: cwd escapes workspace", is_error=True)

        try:
            # Use create_subprocess_exec instead of shell to prevent injection
            proc = await asyncio.create_subprocess_exec(
                *parts,
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

        except FileNotFoundError as e:
            return ToolResult(
                tool_call_id="",
                content=f"Command '{parts[0]}' failed because executable not found. Try: Check if command exists with 'which {parts[0]}' or install the required package.",
                is_error=True,
            )
        except Exception as e:
            return ToolResult(
                tool_call_id="",
                content=f"Command '{command}' failed because: {str(e)}. Try: Verify command syntax or run 'code-cli --help' for troubleshooting.",
                is_error=True,
            )
