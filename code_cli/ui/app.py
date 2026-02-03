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
from textual import events

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

from .cards import AgentMessageCard, DiffCard
from .header import CodenticHeader
from .layout import (
    CenterPane,
    ComposerBar,
    InspectorDrawer,
    LeftRail,
    PinnedActivityBar,
    TranscriptPane,
)
from .theme import CSS_VARS
from .widgets import (
    ApprovalModal,
    ArmConfirmModal,
    ArmRequiredModal,
    CardSelected,
    ClearTranscriptModal,
    CommandPalette,
    PaletteCommand,
    SafeArmState,
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

    CodenticHeader {
        dock: top;
        height: 2;
        margin: 1 2 0 2;
    }

    #layout-root {
        height: 1fr;
        width: 1fr;
        padding: 0 1 1 1;
        overflow: hidden;
    }

    #main-row {
        height: 1fr;
        width: 1fr;
        overflow: hidden;
    }

    LeftRail {
        width: 4;
        min-width: 4;
        background: $panel;
        border: solid $border;
        padding: 1;
    }

    LeftRail.expanded {
        width: 26;
        min-width: 26;
    }

    .rail-icon {
        height: 1;
        width: 100%;
        text-align: center;
        color: $text_muted;
        padding: 0;
        margin: 0;
        border-left: wide transparent;
    }

    .rail-icon:hover {
        color: $text;
        background: $panel_raised;
    }

    .rail-icon.active {
        color: $accent_cyan;
        border-left: wide $accent_cyan;
    }

    .rail-expanded {
        display: none;
    }

    LeftRail.expanded .rail-icon {
        display: none;
    }

    LeftRail.expanded .rail-expanded {
        display: block;
    }

    LeftRail.focus-locked {
        width: 4 !important;
        min-width: 4 !important;
    }

    LeftRail.focus-locked.expanded {
        width: 4 !important;
    }

    Screen.focus-mode CodenticHeader {
        /* In focus mode, header shows only essential items */
    }

    LeftRail.focus-locked {
        width: 4 !important;
        min-width: 4 !important;
    }

    LeftRail.focus-locked.expanded {
        width: 4 !important;
    }

    Screen.focus-mode CodenticHeader {
        /* Hide non-essential items in focus mode - keep only mode, model, CTX */
    }

    CenterPane {
        width: 1fr;
        height: 1fr;
        background: $bg;
        overflow: hidden;
    }

    PinnedActivityBar {
        height: 1;
        padding: 0 1;
        margin: 0;
        background: $panel;
        border-bottom: solid $border;
        display: none;
    }

    PinnedActivityBar.active {
        display: block;
    }

    PinnedActivityBar:focus {
        border-bottom: solid $accent_cyan;
    }

    TranscriptPane {
        height: 1fr;
        background: $bg;
        padding: 0 1;
        overflow-y: auto;
    }

    #transcript-list {
        width: 100%;
    }

    CodeOutputPane {
        height: 0;
        background: $panel;
        border-top: solid $border;
        display: none;
        padding: 1;
    }

    CodeOutputPane.expanded {
        height: 30%;
        min-height: 10;
        display: block;
    }

    InspectorDrawer {
        /* Overlay drawer - does not participate in layout */
        display: none;
        dock: right;
        width: 45;
        min-width: 30;
        max-width: 60;
        height: 100%;
        background: $panel;
        border-left: solid $border;
        padding: 1;
        layer: overlay;
    }

    InspectorDrawer.visible {
        display: block;
    }

    InspectorDrawer.fullscreen {
        /* Small terminal fallback: full-screen modal */
        dock: top;
        width: 100%;
        height: 100%;
    }

    InspectorDrawer:focus {
        border-left: heavy $accent_cyan;
    }

    /* Tab styling */
    TabbedContent > Tab {
        color: $text_muted;
    }

    TabbedContent > Tab.--highlight {
        color: $text;
        text-style: underline;
        background: $panel_raised;
    }

    TabbedContent > Tab:focus {
        color: $accent_cyan;
    }

    /* Dim center slightly when drawer is open (very subtle) */
    #main-row {
        opacity: 1;
    }

    Screen.drawer-open #main-row {
        opacity: 0.95;
    }

    ComposerBar {
        dock: bottom;
        height: auto;
        min-height: 3;
        border-top: solid $border;
        background: $panel_raised;
        padding: 0 1;
        margin: 0;
        overflow-x: hidden;
        overflow-y: hidden;
    }

    ComposerBar:focus-within {
        border-top: heavy $accent_cyan;
    }

    #composer-stack {
        height: auto;
        padding: 0;
    }

    #hint-strip {
        height: 1;
        color: $text;
        padding: 0;
        margin: 0;
    }

    #composer-input {
        height: 1;
        border: none;
        background: transparent;
        color: $text;
        padding: 0;
        margin: 0;
    }

    #composer-input:focus {
        background: transparent;
    }

    .section-header {
        color: $text_muted;
        text-style: bold;
        margin-top: 1;
    }

    .card {
        border: none;
        border-left: tall $border;
        background: $panel;
        margin: 0;
        padding: 0 1;
        width: 100%;
        height: auto;
    }

    .card:focus {
        border-left: tall $accent_cyan;
        background: $panel_raised;
    }

    .card.streaming {
        border-left: tall $accent_cyan;
    }

    .card.error {
        border-left: tall $danger;
    }

    .card.warning {
        border-left: tall $accent_orange;
    }

    CodeBlockWidget {
        margin: 1 0;
        border: solid $border;
    }

    CodeBlockWidget:focus {
        border: solid $accent_cyan;
    }

    /* AgentMessageCard composite structure */
    AgentMessageCard {
        border: none;
        border-left: tall $border;
        background: $panel;
        margin: 0;
        padding: 1;
        width: 100%;
        height: auto;
    }

    AgentMessageCard:focus {
        border-left: tall $accent_cyan;
        background: $panel_raised;
    }

    AgentMessageCard.streaming {
        border-left: tall $accent_cyan;
    }

    AgentMessageCard.error {
        border-left: tall $danger;
    }

    AgentMessageCard .agent-card-header {
        height: 1;
        color: $text_muted;
        padding: 0;
        margin: 0 0 1 0;
    }

    AgentMessageCard .agent-card-content {
        width: 100%;
        height: auto;
    }

    AgentMessageCard .agent-card-text {
        width: 100%;
        height: auto;
        margin: 0 0 1 0;
    }

    AgentMessageCard .agent-card-code {
        margin: 1 0;
    }
    """
    )

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit"),
        Binding("ctrl+shift+p", "command_palette", "Palette", priority=True),
        Binding("f", "focus_mode", "Focus Mode"),
        Binding("ctrl+b", "toggle_rail", "Toggle Rail"),
        Binding("ctrl+i", "toggle_inspector", "Inspector", priority=True),
        Binding("ctrl+\\", "toggle_inspector", "Inspector (alt)", priority=True),
        Binding("ctrl+alt+left", "resize_drawer_left", "Drawer ←"),
        Binding("ctrl+alt+right", "resize_drawer_right", "Drawer →"),
        Binding("tab", "focus_next", "Focus Next"),
        Binding("shift+tab", "focus_previous", "Focus Prev"),
        Binding("ctrl+1", "focus_rail", "Rail"),
        Binding("ctrl+2", "focus_transcript", "Transcript"),
        Binding("ctrl+3", "focus_inspector", "Inspector"),
        Binding("ctrl+4", "focus_composer", "Composer"),
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
        self._stream_card: AgentMessageCard | None = None
        self._active_card = None
        self._thinking = False
        self._processing = False
        self._pending_diffs: list[str] = []
        self._pinned_files: list[str] = []
        self.safety_state = SafeArmState.SAFE
        self._palette_commands = self._build_palette_commands()
        self._focus_mode = False
        self._tokens_received = 0
        self._stream_start_time = 0.0
        self._last_tokens_per_sec_update = 0.0

    def _build_palette_commands(self) -> list[PaletteCommand]:
        return [
            PaletteCommand("toggle_mode", "Toggle SAFE/ARMED", "Enable or disable tool execution"),
            PaletteCommand("clear_transcript", "Clear transcript", "Remove all cards"),
            PaletteCommand("focus_rail", "Focus rail", "Jump to left rail"),
            PaletteCommand("focus_transcript", "Focus transcript", "Jump to transcript"),
            PaletteCommand("focus_inspector", "Focus inspector", "Open inspector drawer"),
            PaletteCommand("focus_composer", "Focus composer", "Jump to input"),
            PaletteCommand("toggle_inspector", "Toggle Inspector", "Show/Hide inspector drawer"),
            PaletteCommand("toggle_rail", "Toggle Rail", "Expand/Collapse left rail"),
            PaletteCommand("focus_mode", "Focus Mode", "Enter distraction-free mode"),
            PaletteCommand("show_keys", "Show Keys", "Display keybindings"),
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
        # Mount InspectorDrawer as Screen-level overlay (not in layout tree)
        inspector = InspectorDrawer(id="inspector-drawer")
        self.mount(inspector)
        # Styles are set via CSS (dock: right, layer: overlay, display: none)
        
        self.set_interval(10.0, self._poll_models)
        self.set_interval(0.05, self._drain_events)
        self.set_interval(0.05, self._flush_stream)
        self.set_interval(0.5, self._update_header_metrics)
        self.set_interval(1.0, self._update_activity_elapsed)
        self.run_worker(self._load_plugins(), group="plugins")
        self.run_worker(self._check_provider_health(), group="health")
        self._sync_header()
        self._sync_sessions()
        
        # Force focus on input on mount
        self.set_focus(self.query_one("#composer-input", Input))
        
        # Show empty state if transcript is empty
        transcript = self.query_one(TranscriptPane)
        if not transcript.card_children():
            transcript.show_empty_state()

    async def _check_provider_health(self) -> None:
        try:
            models = await self.provider.get_available_models()
            if not models:
                transcript = self.query_one(TranscriptPane)
                transcript.add_system_message(
                    "No models found in Ollama. Run: ollama pull llama3",
                    level="warning"
                )
            keep_alive = getattr(self.provider, "keep_alive", None)
            if keep_alive == 0:
                transcript = self.query_one(TranscriptPane)
                transcript.add_system_message(
                    "keep_alive=0 — model reloads from disk every request. "
                    "Set keep_alive=-1 in config.toml for faster responses.",
                    level="info"
                )
        except Exception as e:
            logger.warning("Provider health check failed: %s", e)
            transcript = self.query_one(TranscriptPane)
            transcript.add_system_message(
                f"Cannot reach LLM provider ({e}). Is it running?",
                level="warning"
            )

    async def _load_plugins(self) -> None:
        await asyncio.to_thread(self.tools.register_plugins, self.workspace)

    def _update_header_metrics(self) -> None:
        """Update header metrics periodically."""
        self._sync_header()

    def _update_activity_elapsed(self) -> None:
        """Update activity bar elapsed time periodically."""
        try:
            activity_bar = self.query_one(PinnedActivityBar)
            activity_bar.tick_elapsed()
        except Exception:
            pass

    async def _poll_models(self) -> None:
        try:
            models = await self.provider.get_available_models()
            if models:
                new_model = models[0]
                header = self.query_one(CodenticHeader)
                if header.model != new_model:
                    header.model = new_model
                    self._sync_header()
        except Exception:
            pass

    def compose(self) -> ComposeResult:
        """
        Compose the UI layout.

        Yields:
            Widgets: The hierarchical structure of widgets (Header, LeftRail, CenterPane, Composer).
            Note: InspectorDrawer is mounted as overlay in on_mount().
        """
        yield CodenticHeader(id="header")

        with Container(id="layout-root"):
            with Horizontal(id="main-row"):
                yield LeftRail(self.workspace, id="left-rail")
                yield CenterPane(id="center-pane")
        
        yield ComposerBar(id="composer-bar")

    def _sync_sessions(self) -> None:
        # Sessions are handled in LeftRail now
        pass

    def _sync_header(self) -> None:
        """Update header with current state."""
        header = self.query_one(CodenticHeader)
        header.mode = self.safety_state.value
        header.model = getattr(self.provider, "model", "unknown")
        header.branch = self._current_branch()
        header.ctx_pct = self._context_pct()
        header.ctx_used = self.agent.conversation.total_tokens
        header.ctx_max = self.config.context.max_tokens
        header.queue_count = len(self._pending_diffs) if hasattr(self, "_pending_diffs") else 0
        header.is_active = self._processing or self._thinking
        
        # Update tokens/sec (throttled)
        import time
        now = time.time()
        if self._stream_start_time > 0 and now - self._last_tokens_per_sec_update > 0.5:
            elapsed = now - self._stream_start_time
            if elapsed > 0:
                header.tokens_per_sec = self._tokens_received / elapsed
            self._last_tokens_per_sec_update = now
        elif self._stream_start_time == 0:
            header.tokens_per_sec = 0.0
        
        # Calculate latency (time from request start to first token)
        if self._stream_start_time > 0 and self._tokens_received > 0:
            # Approximate latency as time to first token
            header.latency_ms = int((self._last_tokens_per_sec_update - self._stream_start_time) * 1000) if self._last_tokens_per_sec_update > 0 else 0
        else:
            header.latency_ms = 0

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
        
        # Remove empty state if present
        transcript.remove_empty_state()
        
        self._active_card = transcript.add_message("user", text)
        self._stream_card = transcript.add_message("assistant", "")
        self._stream_card.start_streaming()
        self._active_card = self._stream_card
        self._thinking = True
        
        # Reset streaming metrics
        import time
        self._stream_start_time = time.time()
        self._tokens_received = 0
        
        # Start activity bar
        activity_bar = self.query_one(PinnedActivityBar)
        activity_bar.start_activity("Processing request...")
        
        await self.event_bus.publish(self._event("status", {"status": "processing"}, "ui"))
        self.run_worker(self.process(text))

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "composer-input":
            return
        # Hint strip visibility is handled by ComposerBar itself
        pass

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
        - "message": Appends text to the assistant's response stream (throttled).
        - "tool_result": Adds tool execution cards to the transcript and updates the inspector.
        - "stream_end": Finalizes the current streaming response.
        - "status": Updates activity bar and header.
        - "context": Updates the context percentage usage in header and inspector.
        - "diff": Shows diff previews in the inspector.
        """
        try:
            events = await self.event_bus.drain()
            if not events:
                return

            transcript = self.query_one(TranscriptPane)
            inspector = self.query_one(InspectorDrawer)
            activity_bar = self.query_one(PinnedActivityBar)

            for event in events:
                if event.type == "message":
                    if event.payload.get("role") == "assistant":
                        delta = event.payload.get("delta", "")
                        self._tokens_received += len(delta.split())  # Rough token count
                        if self._thinking and self._stream_card:
                            self._thinking = False
                        self._stream_buffer += delta
                        if self._stream_card is None:
                            self._stream_card = transcript.add_message("assistant", "")
                            self._stream_card.start_streaming()
                            self._active_card = self._stream_card

                elif event.type == "tool_result":
                    self._flush_stream_buffer(transcript)
                    tool_name = event.payload.get("tool_name", "tool")
                    content = event.payload.get("content", "")
                    is_error = event.payload.get("is_error", False)
                    arguments = event.payload.get("arguments")
                    
                    # If this is a system failure, mark the streaming card as error
                    if is_error and tool_name == "system" and self._stream_card:
                        self._fail_streaming(content)
                        activity_bar.stop_activity()
                        inspector.append_log(f"\n--- SYSTEM ERROR ---\n{content}\n")
                        continue
                    
                    # Add tool result card
                    card = transcript.add_tool_result(tool_name, arguments, content, is_error)
                    self._active_card = card
                    self._stream_card = None
                    self._thinking = False

                    # Update activity bar
                    activity_bar.stop_activity()

                    diff_text = self._pending_diffs.pop(0) if self._pending_diffs else ""
                    if diff_text:
                        inspector.show_diff(diff_text)
                    inspector.show_tool(tool_name, arguments, content)

                    # Append to inspector logs
                    inspector.append_log(f"\n--- TOOL: {tool_name} ---\n{content}\n")

                elif event.type == "stream_end":
                    self._flush_stream_buffer(transcript)
                    if self._stream_card:
                        self._stream_card.stop_streaming()
                    self._stream_card = None
                    self._thinking = False
                    activity_bar.stop_activity()
                    self._stream_start_time = 0.0
                    self._tokens_received = 0

                elif event.type == "status":
                    status = event.payload.get("status", "ready")
                    if status == "processing":
                        activity_bar.start_activity("Processing...")
                    elif status == "ready":
                        activity_bar.stop_activity()

                elif event.type == "context":
                    ctx_pct = event.payload.get("ctx_pct", 0)
                    pinned = event.payload.get("pinned", [])
                    inspector.show_context(pinned, ctx_pct)
                    self._sync_header()

                elif event.type == "plan":
                    content = event.payload.get("content", "")
                    if content:
                        transcript.add_plan(content)

                elif event.type == "diff":
                    diff_text = event.payload.get("diff", "")
                    if diff_text:
                        inspector.show_diff(diff_text)
        except Exception:
            logger.exception("_drain_events failed")

    def _flush_stream_buffer(self, transcript: TranscriptPane) -> None:
        """Flush stream buffer to card (throttled by card's append method)."""
        if self._stream_card and self._stream_buffer:
            self._stream_card.append(self._stream_buffer)
            self._stream_buffer = ""
            # Only scroll if user is at bottom (handled by TranscriptPane)

    def _fail_streaming(self, error_text: str) -> None:
        """Mark the active streaming card as error and append error text."""
        if self._stream_card:
            if error_text:
                self._stream_card.append(f"\n{error_text}")
            self._stream_card.mark_error()
        self._stream_card = None
        self._thinking = False

    async def _flush_stream(self) -> None:
        """Periodically flush stream buffer."""
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
        # Count cards (excluding empty state)
        from .cards import EmptyStateCard
        cards = [c for c in transcript.card_children() if not isinstance(c, EmptyStateCard)]
        message_count = len(cards)

        if message_count == 0:
            return

        confirmed = await self.push_screen_wait(ClearTranscriptModal(message_count))

        if confirmed:
            transcript.clear_cards()
            transcript.show_empty_state()
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
            # Help functionality can be added later if needed
            pass

    def action_focus_rail(self) -> None:
        """Focus the left rail (bound to Ctrl+1)."""
        rail = self.query_one(LeftRail)
        rail.focus()
    
    def action_toggle_rail(self) -> None:
        """Toggle rail expansion (bound to Ctrl+B)."""
        rail = self.query_one(LeftRail)
        rail.toggle()
    
    def action_focus_navigator(self) -> None:
        # Navigator is now part of LeftRail
        rail = self.query_one(LeftRail)
        rail.focus()

    # Note: action_focus_next and action_focus_previous are inherited from textual.app.App
    # They call self.screen.focus_next() and self.screen.focus_previous() respectively

    def action_focus_transcript(self) -> None:
        transcript = self.query_one(TranscriptPane)
        transcript.focus()

    def action_focus_inspector(self) -> None:
        inspector = self.query_one(InspectorDrawer)
        if not inspector._visible:
            inspector.show()
        inspector.focus()

    def action_focus_composer(self) -> None:
        self.query_one("#composer-input", Input).focus()


    def action_toggle_output(self) -> None:
        pane = self.query_one(CodeOutputPane)
        pane.toggle()
        if pane.has_class("expanded"):
            pane.focus()

    async def action_toggle_mode(self) -> None:
        """Toggle SAFE/ARMED mode."""
        if self.safety_state == SafeArmState.SAFE:
            approved = await self.push_screen_wait(ArmConfirmModal())
            if approved:
                self.safety_state = SafeArmState.ARMED
        else:
            self.safety_state = SafeArmState.SAFE
        self._sync_header()

    def action_expand_collapse_card(self) -> None:
        """Expand/collapse active card."""
        if self._active_card:
            self._active_card.toggle_collapse()

    def on_card_selected(self, message: CardSelected) -> None:
        """Handle card selection - sets active card, updates inspector if already open."""
        self._active_card = message.card
        inspector = self.query_one(InspectorDrawer)

        # Only update inspector content if it's already visible
        # Don't auto-open it on every card click
        if not inspector._visible:
            return

        from .cards import ToolResultCard, ToolCallCard
        if isinstance(message.card, (ToolResultCard, ToolCallCard)):
            inspector.show_tool(
                message.card.tool_name,
                getattr(message.card, "arguments", None),
                getattr(message.card, "content", ""),
            )
        elif isinstance(message.card, DiffCard):
            inspector.show_diff(message.card._full_diff)
        else:
            inspector.show_context(self._pinned_files, self._context_pct())

    def on_mouse_down(self, event: events.MouseDown) -> None:
        """Global right-click prevention - stop propagation for button 3."""
        # If you want to kill right-click (or non-left clicks), stop them here.
        if event.button != 1:  # Not left-click
            event.stop()
            return
        # Do NOT call super().on_mouse_down; App has no such method.
        # Allow normal propagation by doing nothing.
        return
    
    def on_file_pin_message(self, message: FilePinMessage) -> None:
        """Handle file pin message."""
        path = message.path
        if str(path) not in self._pinned_files:
            self._pinned_files.append(str(path))
        inspector = self.query_one(InspectorDrawer)
        inspector.show_context(self._pinned_files, self._context_pct())
        self._sync_header()

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
