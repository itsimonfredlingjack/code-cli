# code_cli/ui/app.py

import asyncio
import logging
import uuid
from difflib import unified_diff
from pathlib import Path

import aiofiles
from git import InvalidGitRepositoryError, Repo
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Input, Label, ListItem, ListView

from code_cli.agent.loop import AgentLoop
from code_cli.config import AgentConfig, Config
from code_cli.providers.factory import build_provider
from code_cli.tools.base import ToolRegistry
from code_cli.tools.cloud import AWSResourceLister, K8sLogFetcher
from code_cli.tools.filesystem import ReadFileTool, StrReplaceTool, WriteFileTool
from code_cli.tools.git import GitAddTool, GitCommitTool, GitStatusTool
from code_cli.tools.shell import ShellTool
from code_cli.ui.event_bus import UIEventBus
from code_cli.ui.events import UIEvent
from code_cli.ui.project_tree import FilePinMessage

from .theme import CSS_VARS
from .widgets import (
    AgentHeader,
    ApprovalModal,
    ArmConfirmModal,
    ArmRequiredModal,
    CardSelected,
    ClearTranscriptModal,
    CommandPalette,
    ComposerBar,
    InspectorPane,
    NavigatorPane,
    OutputPane,
    PaletteCommand,
    SafeArmState,
    StatusBar,
    ToolCard,
    TranscriptPane,
)

logger = logging.getLogger(__name__)


class CodeApp(App):
    """
    Main Application class for Code CLI TUI.

    This class manages the lifecycle of the Textual application, including layout composition,
    event handling, agent loop integration, and user interaction.

    Attributes:
        workspace (Path): The root directory of the current project.
        config (Config): Loaded configuration for the application.
        tools (ToolRegistry): Registry of available tools (filesystem, git, shell, etc.).
        provider (LLMProvider): The configured LLM provider (Ollama, OpenAI, etc.).
        agent (AgentLoop): The core logic loop handling agent-user interaction.
        event_bus (UIEventBus): Bus for decoupled communication between components.
        safety_state (SafeArmState): Current security mode (SAFE or ARMED).
    """
    CSS = (
        CSS_VARS
        + """
    Screen { background: $bg; color: $text; }

    AgentHeader {
        dock: top;
        height: 2;
        margin: 1 2 0 2;
    }

    #layout-root {
        height: 1fr;
        width: 1fr;
        padding: 0 1 1 1;
    }

    #main-row {
        height: 1fr;
        width: 1fr;
    }

    NavigatorPane {
        width: 32;
        min-width: 26;
        background: $surface;
        border: solid $surface_light;
        padding: 1;
    }

    TranscriptPane {
        width: 1fr;
        background: $bg;
        border: solid $surface_light;
        padding: 1;
    }

    InspectorPane {
        width: 38;
        min-width: 32;
        background: $surface;
        border: solid $surface_light;
        padding: 1;
    }

    NavigatorPane:focus {
        border: solid $focus_ring;
    }

    TranscriptPane:focus {
        border: solid $focus_ring;
    }

    InspectorPane:focus {
        border: solid $focus_ring;
    }

    .section-header {
        color: $text_dim;
        text-style: bold;
        margin-top: 1;
    }

    .card {
        border: solid $card_border;
        background: $surface;
        margin-bottom: 1;
    }

    .card:focus {
        border: solid $focus_ring;
    }


    #output-pane {
        dock: bottom;
        height: 12;
        background: $surface;
        border-top: solid $surface_light;
        padding: 0 1;
        display: none;
    }
    
    #output-pane.visible {
        display: block;
    }

    #composer-bar {

        dock: bottom;
        height: auto;
        border-top: solid $surface_light;
        background: $surface;
        padding: 0 1;
    }

    #composer-input {
        height: 3;
        border: none;
        background: $surface_glow;
        color: $text;
    }

    #composer-input:focus {
        border: none;
    }

    StatusBar {
        color: $text_dim;
        padding: 0 1;
    }
    """
    )

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit"),
        Binding("ctrl+k", "command_palette", "Palette"),
        Binding("tab", "focus_next", "Focus Next"),
        Binding("shift+tab", "focus_previous", "Focus Prev"),
        Binding("ctrl+1", "focus_navigator", "Navigator"),
        Binding("ctrl+2", "focus_transcript", "Transcript"),
        Binding("ctrl+3", "focus_inspector", "Inspector"),
        Binding("ctrl+4", "focus_composer", "Composer"),
        Binding("ctrl+j", "toggle_output", "Output"),
        Binding("ctrl+.", "toggle_mode", "SAFE/ARMED"),
        Binding("ctrl+e", "expand_collapse_card", "Expand/Collapse"),
        Binding("ctrl+l", "clear_transcript", "Clear"),
    ]

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.workspace = Path.cwd()
        self.config = Config.load()
        self.tools = ToolRegistry(load_plugins=False)
        self.tools.register(ReadFileTool(self.workspace))
        self.tools.register(WriteFileTool(self.workspace))
        self.tools.register(StrReplaceTool(self.workspace))
        self.tools.register(GitStatusTool(self.workspace))
        self.tools.register(GitAddTool(self.workspace))
        self.tools.register(GitCommitTool(self.workspace))
        self.tools.register(AWSResourceLister())
        self.tools.register(K8sLogFetcher())
        self.tools.register(
            ShellTool(
                self.workspace,
                allowed_commands=self.config.shell.allowed,
                blocked_patterns=self.config.shell.blocked,
                timeout=self.config.shell.timeout,
            )
        )

        provider_cfg = self.config.providers.get(self.config.default_provider)
        self.provider = build_provider(provider_cfg)
        self.agent = AgentLoop(
            self.provider,
            self.tools,
            self.config.agent,
            on_confirmation=self._handle_confirmation,
            context_config=self.config.context,
        )

        self.event_bus = UIEventBus()
        self._stream_buffer = ""
        self._stream_card = None
        self._active_card = None
        self._thinking = False
        self._processing = False
        self._pending_diffs: list[str] = []
        self._pinned_files: list[str] = []
        self.safety_state = SafeArmState.SAFE
        self._palette_commands = self._build_palette_commands()

    def _build_palette_commands(self) -> list[PaletteCommand]:
        return [
            PaletteCommand("toggle_mode", "Toggle SAFE/ARMED", "Enable or disable tool execution"),
            PaletteCommand("clear_transcript", "Clear transcript", "Remove all cards"),
            PaletteCommand("focus_navigator", "Focus navigator", "Jump to left pane"),
            PaletteCommand("focus_transcript", "Focus transcript", "Jump to middle pane"),
            PaletteCommand("focus_inspector", "Focus inspector", "Jump to right pane"),
            PaletteCommand("focus_composer", "Focus composer", "Jump to input"),
            PaletteCommand("toggle_output", "Toggle Output", "Show/Hide global output drawer"),
            PaletteCommand("show_help", "Show help", "Open help tab"),
        ]

    async def _handle_confirmation(self, tool_name: str, arguments: dict) -> bool:
        if self.safety_state == SafeArmState.SAFE:
            await self.push_screen_wait(ArmRequiredModal())
            return False

        self.safety_state = SafeArmState.ARMED_PENDING
        self._sync_status_bar()
        diff_text = await self._build_diff_preview(tool_name, arguments)
        reason, risk = self._tool_risk_reason(tool_name)
        approved = await self.push_screen_wait(ApprovalModal(tool_name, arguments, diff_text, reason, risk))
        self.safety_state = SafeArmState.ARMED
        self._sync_status_bar()
        if approved:
            self._pending_diffs.append(diff_text)
        return approved

    def _tool_risk_reason(self, tool_name: str) -> tuple[str, str]:
        if tool_name in {"write_file", "str_replace"}:
            return "Modifies workspace files", "High"
        if tool_name == "run_command":
            return "Executes shell commands", "High"
        if tool_name in {"git_commit", "git_add"}:
            return "Changes repository state", "Medium"
        return "Tool execution", "Low"

    async def _build_diff_preview(self, tool_name: str, arguments: dict) -> str:
        if tool_name == "write_file":
            return await self._diff_write(arguments)
        if tool_name == "str_replace":
            return await self._diff_replace(arguments)
        return ""

    async def _diff_write(self, arguments: dict) -> str:
        path = arguments.get("path")
        content = arguments.get("content", "")
        if not path:
            return ""

        full_path = (self.workspace / path).resolve()
        if not str(full_path).startswith(str(self.workspace.resolve())):
            return ""

        old = ""
        if await asyncio.to_thread(full_path.exists):
            async with aiofiles.open(full_path, "r") as f:
                old = await f.read()

        diff = unified_diff(
            old.splitlines(),
            content.splitlines(),
            fromfile=path,
            tofile=path,
            lineterm="",
        )
        return "\n".join(diff)

    async def _diff_replace(self, arguments: dict) -> str:
        path = arguments.get("path")
        old_str = arguments.get("old_str", "")
        new_str = arguments.get("new_str", "")
        if not path:
            return ""

        full_path = (self.workspace / path).resolve()
        if not str(full_path).startswith(str(self.workspace.resolve())):
            return ""

        if not await asyncio.to_thread(full_path.exists):
            return ""

        async with aiofiles.open(full_path, "r") as f:
            content = await f.read()

        if old_str not in content:
            return ""

        updated = content.replace(old_str, new_str, 1)
        diff = unified_diff(
            content.splitlines(),
            updated.splitlines(),
            fromfile=path,
            tofile=path,
            lineterm="",
        )
        return "\n".join(diff)

    def on_mount(self) -> None:
        """
        Lifecycle hook called when the application is mounted.

        Initializes background workers for:
        - Polling available models.
        - Draining UI events from the bus.
        - Flushing the stream buffer to the UI.
        - Loading tool plugins.
        - Checking provider health.
        """
        self.set_interval(10.0, self._poll_models)
        self.set_interval(0.05, self._drain_events)
        self.set_interval(0.05, self._flush_stream)
        self.run_worker(self._load_plugins(), group="plugins")
        self.run_worker(self._check_provider_health(), group="health")
        self._sync_status_bar()
        self._sync_sessions()

    async def _check_provider_health(self) -> None:
        try:
            models = await self.provider.get_available_models()
            if not models:
                transcript = self.query_one(TranscriptPane)
                transcript.add_message(
                    "system", "Warning: No models found in Ollama. Run: ollama pull llama3"
                )
            keep_alive = getattr(self.provider, "keep_alive", None)
            if keep_alive == 0:
                transcript = self.query_one(TranscriptPane)
                transcript.add_message(
                    "system",
                    "Note: keep_alive=0 — model reloads from disk every request (slow). "
                    "Set keep_alive=-1 in config.toml for faster responses.",
                )
        except Exception as e:
            logger.warning("Provider health check failed: %s", e)
            transcript = self.query_one(TranscriptPane)
            transcript.add_message(
                "system", f"Warning: Cannot reach LLM provider ({e}). Is it running?"
            )

    async def _load_plugins(self) -> None:
        await asyncio.to_thread(self.tools.register_plugins, self.workspace)

    async def _poll_models(self) -> None:
        try:
            models = await self.provider.get_available_models()
            if models:
                new_model = models[0]
                header = self.query_one(AgentHeader)
                if header.model != new_model:
                    header.model = new_model
                    self._sync_status_bar()
        except Exception:
            pass

    def compose(self) -> ComposeResult:
        """
        Compose the UI layout.

        Yields:
            Widgets: The hierarchical structure of widgets (Header, Navigator, Transcript, Inspector, Composer).
        """
        yield AgentHeader()

        with Container(id="layout-root"):
            with Vertical():
                with Horizontal(id="main-row"):
                    yield NavigatorPane(self.workspace, id="navigator")
                    yield TranscriptPane(id="transcript")
                    yield InspectorPane(id="inspector")
                yield OutputPane(id="output-pane")
                with Container(id="composer-bar"):
                    yield ComposerBar()

    def _sync_sessions(self) -> None:
        navigator = self.query_one(NavigatorPane)
        sessions = navigator.query_one("#sessions", ListView)
        sessions.remove_children()
        sessions.mount(ListItem(Label("default")))

    def _sync_status_bar(self) -> None:
        status_bar = self.query_one(StatusBar)
        status_bar.mode = self.safety_state.value
        status_bar.provider = self.config.default_provider
        status_bar.model = getattr(self.provider, "model", "unknown")
        branch = self._current_branch()
        status_bar.branch = branch
        status_bar.ctx_pct = self._context_pct()
        header = self.query_one(AgentHeader)
        header.branch = branch
        header.model = getattr(self.provider, "model", "unknown")

    def _current_branch(self) -> str:
        try:
            repo = Repo(self.workspace, search_parent_directories=True)
            return repo.active_branch.name
        except (InvalidGitRepositoryError, TypeError, ValueError):
            return "main"

    def _context_pct(self) -> int:
        max_tokens = self.config.context.max_tokens
        used = self.agent.conversation.total_tokens
        if not max_tokens:
            return 0
        return int((used / max_tokens) * 100)

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "composer-input":
            return
        text = event.value.strip()
        if not text:
            return
        if self._processing:
            return
        event.input.value = ""

        self._processing = True
        transcript = self.query_one(TranscriptPane)
        self._active_card = transcript.add_message("user", text)
        self._stream_card = transcript.add_message("assistant", "Thinking...")
        self._active_card = self._stream_card
        self._thinking = True
        await self.event_bus.publish(self._event("status", {"status": "processing"}, "ui"))
        self.run_worker(self.process(text))

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "composer-input":
            return
        status_bar = self.query_one(StatusBar)
        if event.value:
            status_bar.status = "typing"
        else:
            status_bar.status = "ready"

    async def process(self, text: str) -> None:
        """
        Process user input by passing it to the agent loop.

        Args:
            text (str): The user's input command or message.

        This method:
        1. Publishes the user message to the UI.
        2. Sets status to "processing".
        3. Runs the agent loop.
        4. Handles streaming chunks (text deltas) and tool results.
        5. Updates context/status on completion.
        """
        logger.info("process() started: %s", text[:80])
        try:
            async for chunk in self.agent.run(text):
                if hasattr(chunk, "text") and chunk.text:
                    await self.event_bus.publish(
                        self._event(
                            "message",
                            {"role": "assistant", "delta": chunk.text},
                            "agent",
                        )
                    )
                elif hasattr(chunk, "tool_name") and chunk.tool_name:
                    await self.event_bus.publish(
                        self._event(
                            "tool_result",
                            {
                                "tool_name": chunk.tool_name,
                                "content": chunk.content,
                                "is_error": chunk.is_error,
                                "arguments": chunk.arguments or {},
                            },
                            "agent",
                        )
                    )

            await self.event_bus.publish(self._event("status", {"status": "ready"}, "ui"))
            await self.event_bus.publish(
                self._event("context", {"ctx_pct": self._context_pct(), "pinned": self._pinned_files}, "ui")
            )
        except Exception as e:
            logger.exception("process() failed: %s", e)
            await self.event_bus.publish(
                self._event(
                    "tool_result",
                    {"tool_name": "system", "content": f"CRITICAL_FAILURE: {e}", "is_error": True},
                    "system",
                )
            )
            await self.event_bus.publish(self._event("status", {"status": "ready"}, "ui"))
        finally:
            self._processing = False
            await self.event_bus.publish(self._event("stream_end", {}, "agent"))

    async def _drain_events(self) -> None:
        """
        Periodically drain events from the UIEventBus and update UI components.

        Handles:
        - "message": Appends text to the assistant's response stream.
        - "tool_result": Adds tool execution cards to the transcript and updates the inspector.
        - "stream_end": Finalizes the current streaming response.
        - "status": Updates the status bar (e.g., "processing", "ready").
        - "context": Updates the context percentage usage in the status bar and inspector.
        - "diff": Shows diff previews in the inspector.
        """
        try:
            events = await self.event_bus.drain()
            if not events:
                return

            transcript = self.query_one(TranscriptPane)
            inspector = self.query_one(InspectorPane)
            status_bar = self.query_one(StatusBar)
            navigator = self.query_one(NavigatorPane)

            for event in events:
                if event.type == "message":
                    if event.payload.get("role") == "assistant":
                        delta = event.payload.get("delta", "")
                        if self._thinking and self._stream_card:
                            self._stream_card.content = ""
                            self._thinking = False
                        self._stream_buffer += delta
                        if self._stream_card is None:
                            self._stream_card = transcript.add_message("assistant", "")
                            self._active_card = self._stream_card

                elif event.type == "tool_result":
                    self._flush_stream_buffer(transcript)
                    tool_name = event.payload.get("tool_name", "tool")
                    content = event.payload.get("content", "")
                    is_error = event.payload.get("is_error", False)
                    arguments = event.payload.get("arguments")
                    card = transcript.add_tool(tool_name, arguments, content, is_error)
                    self._active_card = card
                    self._stream_card = None
                    self._thinking = False

                    tool_runs = navigator.query_one("#tool-runs", ListView)
                    tool_runs.mount(ListItem(Label(f"{tool_name} ({'ERR' if is_error else 'OK'})")))

                    diff_text = self._pending_diffs.pop(0) if self._pending_diffs else ""
                    inspector.show_diff(diff_text)
                    inspector.show_tool(tool_name, arguments, content)

                    # Also log to output pane
                    out_pane = self.query_one(OutputPane)
                    out_pane.append(f"\n--- TOOL: {tool_name} ---\n{content}\n")


                elif event.type == "stream_end":
                    self._flush_stream_buffer(transcript)
                    self._stream_card = None
                    self._thinking = False

                elif event.type == "status":
                    status_bar.status = event.payload.get("status", "ready")

                elif event.type == "context":
                    ctx_pct = event.payload.get("ctx_pct", 0)
                    pinned = event.payload.get("pinned", [])
                    status_bar.ctx_pct = ctx_pct
                    inspector.show_context(pinned, ctx_pct)

                elif event.type == "plan":
                    content = event.payload.get("content", "")
                    if content:
                        transcript.add_plan(content)

                elif event.type == "diff":
                    inspector.show_diff(event.payload.get("diff", ""))
        except Exception:
            logger.exception("_drain_events failed")

    def _flush_stream_buffer(self, transcript: TranscriptPane) -> None:
        if self._stream_card and self._stream_buffer:
            self._stream_card.append(self._stream_buffer)
            self._stream_buffer = ""
            transcript.scroll_end(animate=False)

    async def _flush_stream(self) -> None:
        try:
            if not self._stream_buffer or not self._stream_card:
                return
            transcript = self.query_one(TranscriptPane)
            self._flush_stream_buffer(transcript)
        except Exception:
            logger.exception("_flush_stream failed")

    async def action_clear_transcript(self) -> None:
        """Clear conversation history with confirmation modal (bound to Ctrl+L)"""
        transcript = self.query_one(TranscriptPane)
        message_count = len(transcript.query("Card"))

        if message_count == 0:
            # Nothing to clear
            return

        # Show confirmation modal
        confirmed = await self.push_screen_wait(ClearTranscriptModal(message_count))

        if confirmed:
            transcript.remove_children()
            self._stream_buffer = ""
            self._stream_card = None
            self._thinking = False

    async def action_command_palette(self) -> None:
        selection = await self.push_screen_wait(CommandPalette(self._palette_commands))
        if selection:
            await self._execute_palette_command(selection)

    async def _execute_palette_command(self, command_id: str) -> None:
        if command_id == "toggle_mode":
            await self.action_toggle_mode()
        elif command_id == "clear_transcript":
            self.action_clear_transcript()
        elif command_id == "focus_navigator":
            self.action_focus_navigator()
        elif command_id == "focus_transcript":
            self.action_focus_transcript()
        elif command_id == "focus_inspector":
            self.action_focus_inspector()
        elif command_id == "focus_composer":
            self.action_focus_composer()
        elif command_id == "toggle_output":
            self.action_toggle_output()
            self.action_focus_composer()
        elif command_id == "show_help":
            inspector = self.query_one(InspectorPane)
            inspector.show_help()

    def action_focus_navigator(self) -> None:
        navigator = self.query_one(NavigatorPane)
        tree = navigator.query_one("#project-tree")
        tree.focus()

    # Note: action_focus_next and action_focus_previous are inherited from textual.app.App
    # They call self.screen.focus_next() and self.screen.focus_previous() respectively

    def action_focus_transcript(self) -> None:
        transcript = self.query_one(TranscriptPane)
        transcript.focus()

    def action_focus_inspector(self) -> None:
        inspector = self.query_one(InspectorPane)
        inspector.focus()

    def action_focus_composer(self) -> None:
        self.query_one("#composer-input", Input).focus()


    def action_toggle_output(self) -> None:
        pane = self.query_one(OutputPane)
        pane.toggle_class("visible")
        if pane.has_class("visible"):
            pane.focus()

    async def action_toggle_mode(self) -> None:
        if self.safety_state == SafeArmState.SAFE:
            approved = await self.push_screen_wait(ArmConfirmModal())
            if approved:
                self.safety_state = SafeArmState.ARMED
        else:
            self.safety_state = SafeArmState.SAFE
        self._sync_status_bar()

    def action_expand_collapse_card(self) -> None:
        if self._active_card:
            self._active_card.toggle_collapse()

    def on_card_selected(self, message: CardSelected) -> None:
        self._active_card = message.card
        inspector = self.query_one(InspectorPane)
        if isinstance(message.card, ToolCard):
            inspector.show_tool(message.card.tool_name, message.card.arguments, message.card.content)
        else:
            inspector.show_help()

    def on_file_pin_message(self, message: FilePinMessage) -> None:
        path = message.path
        if str(path) not in self._pinned_files:
            self._pinned_files.append(str(path))
        navigator = self.query_one(NavigatorPane)
        pinned = navigator.query_one("#pinned-files")
        pinned.set_pins([Path(p) for p in self._pinned_files])
        inspector = self.query_one(InspectorPane)
        inspector.show_context(self._pinned_files, self._context_pct())

    def _event(self, event_type: str, payload: dict, source: str) -> UIEvent:
        return UIEvent(
            event_id=str(uuid.uuid4()),
            type=event_type,
            session_id="default",
            payload=payload,
            source=source,
        )


if __name__ == "__main__":
    CodeApp().run()
