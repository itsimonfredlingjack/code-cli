# code_cli/ui/app.py

import asyncio
import logging
import re
import uuid
from difflib import unified_diff
from pathlib import Path

import aiofiles
from git import InvalidGitRepositoryError, Repo
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.widgets import Input

from code_cli.agent.loop import AgentLoop
from code_cli.config import Config
from code_cli.providers.factory import build_provider
from code_cli.tools.base import ToolRegistry
from code_cli.tools.cloud import AWSResourceLister, K8sLogFetcher
from code_cli.tools.filesystem import ReadFileTool, StrReplaceTool, WriteFileTool
from code_cli.tools.git import GitAddTool, GitCommitTool, GitStatusTool
from code_cli.tools.shell import ShellTool
from code_cli.ui.event_bus import UIEventBus
from code_cli.ui.events import UIEvent
from code_cli.ui.project_tree import FilePinMessage

from .cards import ActionCard, AgentMessageCard, DiffCard
from .header import CodenticHeader
from .layout import (
    CenterPane,
    ComposerBar,
    ContextWidget,
    DiffDrawer,
    LeftRail,
    LogsDrawer,
    PinnedActivityBar,
    TranscriptPane,
)
from .theme import CSS_VARS
from .widgets import (
    ApprovalCategoryTracker,
    ArmConfirmModal,
    ArmRequiredModal,
    CardSelected,
    ClearTranscriptModal,
    CommandPalette,
    DecisionModal,
    PaletteCommand,
    SafeArmState,
)

logger = logging.getLogger(__name__)

# Verify tool detection patterns
VERIFY_PATTERNS = re.compile(r"\b(pytest|npm\s+test|ruff|cargo\s+test|jest|vitest|mypy|tox)\b", re.IGNORECASE)


class CodeApp(App):
    """
    Main Application class for Code CLI TUI.

    Agentic cockpit UI with compact badge timeline, dual drawers (Diff + Logs),
    3-way approval flow, and agent status machine.
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

    CenterPane {
        width: 1fr;
        height: 1fr;
        background: $bg;
        overflow: hidden;
    }

    ContextWidget {
        height: 1;
        padding: 0 1;
        background: $panel;
        border-bottom: solid $border;
    }

    ContextWidget:focus {
        border-bottom: solid $accent_cyan;
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

    /* Dual drawer system */
    DiffDrawer {
        display: none;
        dock: right;
        width: 50;
        min-width: 30;
        max-width: 60;
        height: 100%;
        background: $panel;
        border-left: solid $border;
        padding: 1;
        layer: overlay;
    }

    DiffDrawer.visible {
        display: block;
    }

    DiffDrawer:focus {
        border-left: heavy $accent_cyan;
    }

    LogsDrawer {
        display: none;
        dock: right;
        width: 50;
        min-width: 30;
        max-width: 60;
        height: 100%;
        background: $panel;
        border-left: solid $border;
        padding: 1;
        layer: overlay;
    }

    LogsDrawer.visible {
        display: block;
    }

    LogsDrawer:focus {
        border-left: heavy $accent_cyan;
    }

    #logs-filter {
        height: 1;
        border: solid $border;
        background: $panel_raised;
        margin: 0 0 1 0;
    }

    /* Dim center when drawer open */
    Screen.diff-drawer-open #main-row,
    Screen.logs-drawer-open #main-row {
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

    /* Compact badge card styling */
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

    .card.success {
        border-left: tall $success;
    }

    /* Tool action cards - visually secondary */
    .card.tool-action {
        opacity: 0.8;
    }

    .card.tool-action:focus {
        opacity: 1.0;
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
        Binding("ctrl+p", "command_palette", "Palette", priority=True),
        Binding("ctrl+shift+p", "command_palette", "Palette", priority=True),
        Binding("ctrl+b", "toggle_rail", "Toggle Rail"),
        Binding("ctrl+d", "toggle_diff_drawer", "Diff Drawer", priority=True),
        Binding("ctrl+l", "toggle_logs_drawer", "Logs Drawer", priority=True),
        Binding("ctrl+x", "toggle_context_widget", "Context", priority=True),
        Binding("ctrl+shift+l", "clear_transcript", "Clear"),
        Binding("ctrl+.", "toggle_mode", "SAFE/ARMED"),
        Binding("ctrl+e", "expand_collapse_card", "Expand/Collapse"),
        Binding("ctrl+1", "focus_rail", "Rail"),
        Binding("ctrl+2", "focus_transcript", "Transcript"),
        Binding("ctrl+3", "focus_composer", "Composer"),
        Binding("tab", "focus_next", "Focus Next"),
        Binding("shift+tab", "focus_previous", "Focus Prev"),
        Binding("f", "focus_mode", "Focus Mode"),
        Binding("escape", "interrupt_or_close", "Interrupt/Close", priority=True),
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
        self._approval_tracker = ApprovalCategoryTracker()
        self._active_task_text = ""
        self._current_worker = None

    def _build_palette_commands(self) -> list[PaletteCommand]:
        return [
            PaletteCommand("toggle_mode", "Toggle SAFE/ARMED", "Enable or disable tool execution", "Ctrl+."),
            PaletteCommand("clear_transcript", "Clear transcript", "Remove all cards", "Ctrl+Shift+L"),
            PaletteCommand("toggle_diff_drawer", "Toggle Diff", "Show/Hide diff drawer", "Ctrl+D"),
            PaletteCommand("toggle_logs_drawer", "Toggle Logs", "Show/Hide logs drawer", "Ctrl+L"),
            PaletteCommand("toggle_context", "Toggle Context", "Show/Hide context widget", "Ctrl+X"),
            PaletteCommand("focus_rail", "Focus rail", "Jump to left rail", "Ctrl+1"),
            PaletteCommand("focus_transcript", "Focus transcript", "Jump to transcript", "Ctrl+2"),
            PaletteCommand("focus_composer", "Focus composer", "Jump to input", "Ctrl+3"),
            PaletteCommand("toggle_rail", "Toggle Rail", "Expand/Collapse left rail", "Ctrl+B"),
            PaletteCommand("interrupt", "Interrupt Agent", "Stop running agent", "Esc"),
            PaletteCommand("focus_mode", "Focus Mode", "Enter distraction-free mode"),
            PaletteCommand("show_keys", "Show Keys", "Display keybindings"),
        ]

    async def _handle_confirmation(self, tool_name: str, arguments: dict) -> bool:
        if self.safety_state == SafeArmState.SAFE:
            await self.push_screen_wait(ArmRequiredModal())
            return False

        # Check category tracker for auto-approval
        category = ApprovalCategoryTracker.tool_to_category(tool_name)
        if self._approval_tracker.is_approved(category):
            # Auto-approved by category - log as decision
            transcript = self.query_one(TranscriptPane)
            transcript.add_decision(tool_name, arguments, outcome="approved_category")
            return True

        self.safety_state = SafeArmState.ARMED_PENDING
        self._sync_status_bar()
        diff_text = await self._build_diff_preview(tool_name, arguments)
        reason, risk = self._tool_risk_reason(tool_name)

        # Show 3-way decision modal
        result = await self.push_screen_wait(
            DecisionModal(tool_name, arguments, diff_text, reason, risk, category)
        )

        self.safety_state = SafeArmState.ARMED
        self._sync_status_bar()

        transcript = self.query_one(TranscriptPane)

        if result == "approve_once":
            transcript.add_decision(tool_name, arguments, outcome="approved")
            if diff_text:
                self._pending_diffs.append(diff_text)
            return True
        elif result == "approve_category":
            self._approval_tracker.approve(category)
            transcript.add_decision(tool_name, arguments, outcome="approved_category")
            if diff_text:
                self._pending_diffs.append(diff_text)
            return True
        else:
            transcript.add_decision(tool_name, arguments, outcome="denied")
            return False

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
        # Mount both drawers as Screen-level overlays
        diff_drawer = DiffDrawer(id="diff-drawer")
        logs_drawer = LogsDrawer(id="logs-drawer")
        self.mount(diff_drawer)
        self.mount(logs_drawer)

        self.set_interval(10.0, self._poll_models)
        self.set_interval(0.05, self._drain_events)
        self.set_interval(0.05, self._flush_stream)
        self.set_interval(0.5, self._update_header_metrics)
        self.set_interval(1.0, self._update_activity_elapsed)
        self.run_worker(self._load_plugins(), group="plugins")
        self.run_worker(self._check_provider_health(), group="health")
        self._sync_header()
        self._sync_sessions()

        self.set_focus(self.query_one("#composer-input", Input))

        transcript = self.query_one(TranscriptPane)
        if not transcript.card_children():
            transcript.show_empty_state()

    async def _check_provider_health(self) -> None:
        try:
            models = await self.provider.get_available_models()
            if not models:
                transcript = self.query_one(TranscriptPane)
                transcript.add_system_message(
                    "No models found in Ollama. Run: ollama pull llama3", level="warning"
                )
            keep_alive = getattr(self.provider, "keep_alive", None)
            if keep_alive == 0:
                transcript = self.query_one(TranscriptPane)
                transcript.add_system_message(
                    "keep_alive=0 — model reloads from disk every request. "
                    "Set keep_alive=-1 in config.toml for faster responses.",
                    level="info",
                )
        except Exception as e:
            logger.warning("Provider health check failed: %s", e)
            transcript = self.query_one(TranscriptPane)
            transcript.add_system_message(
                f"Cannot reach LLM provider ({e}). Is it running?", level="warning"
            )

    async def _load_plugins(self) -> None:
        await asyncio.to_thread(self.tools.register_plugins, self.workspace)

    def _update_header_metrics(self) -> None:
        self._sync_header()

    def _update_activity_elapsed(self) -> None:
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
        yield CodenticHeader(id="header")
        with Container(id="layout-root"):
            with Horizontal(id="main-row"):
                yield LeftRail(self.workspace, id="left-rail")
                yield CenterPane(id="center-pane")
        yield ComposerBar(id="composer-bar")

    def _sync_sessions(self) -> None:
        pass

    def _sync_header(self) -> None:
        header = self.query_one(CodenticHeader)
        header.mode = self.safety_state.value
        header.model = getattr(self.provider, "model", "unknown")
        header.branch = self._current_branch()
        header.ctx_pct = self._context_pct()
        header.ctx_used = self.agent.conversation.total_tokens
        header.ctx_max = self.config.context.max_tokens
        header.is_active = self._processing or self._thinking

        # Agent status machine
        if self._processing:
            if self._thinking:
                header.agent_status = "thinking"
            else:
                header.agent_status = "acting"
        else:
            header.agent_status = "idle"

        # Active task
        header.active_task = self._active_task_text

        # Dirty state
        header.dirty_state = self._check_dirty()

        # Tokens/sec
        import time

        now = time.time()
        if self._stream_start_time > 0 and now - self._last_tokens_per_sec_update > 0.5:
            elapsed = now - self._stream_start_time
            if elapsed > 0:
                header.tokens_per_sec = self._tokens_received / elapsed
            self._last_tokens_per_sec_update = now
        elif self._stream_start_time == 0:
            header.tokens_per_sec = 0.0

        # Update context widget
        try:
            ctx_widget = self.query_one(ContextWidget)
            ctx_widget.update_context(self._context_pct(), self._pinned_files)
        except Exception:
            pass

    def _sync_status_bar(self) -> None:
        """Alias for _sync_header used during approval flow."""
        self._sync_header()

    def _check_dirty(self) -> bool:
        try:
            repo = Repo(self.workspace, search_parent_directories=True)
            return repo.is_dirty()
        except (InvalidGitRepositoryError, TypeError, ValueError):
            return False

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
        self._active_task_text = text.split("\n", 1)[0][:60]
        transcript = self.query_one(TranscriptPane)

        transcript.remove_empty_state()

        self._active_card = transcript.add_message("user", text)
        self._stream_card = transcript.add_message("assistant", "")
        self._stream_card.start_streaming()
        self._active_card = self._stream_card
        self._thinking = True

        import time

        self._stream_start_time = time.time()
        self._tokens_received = 0

        activity_bar = self.query_one(PinnedActivityBar)
        activity_bar.start_activity("Processing request...")

        # Update header to show thinking
        self._sync_header()

        await self.event_bus.publish(self._event("status", {"status": "processing"}, "ui"))
        self._current_worker = self.run_worker(self.process(text))

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "composer-input":
            return

    async def process(self, text: str) -> None:
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
        except asyncio.CancelledError:
            logger.info("process() cancelled (interrupted)")
            await self.event_bus.publish(self._event("stream_end", {}, "agent"))
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
            self._active_task_text = ""
            await self.event_bus.publish(self._event("stream_end", {}, "agent"))

    async def _drain_events(self) -> None:
        try:
            events_list = await self.event_bus.drain()
            if not events_list:
                return

            transcript = self.query_one(TranscriptPane)
            diff_drawer = self.query_one(DiffDrawer)
            logs_drawer = self.query_one(LogsDrawer)
            activity_bar = self.query_one(PinnedActivityBar)
            header = self.query_one(CodenticHeader)

            for event in events_list:
                if event.type == "message":
                    if event.payload.get("role") == "assistant":
                        delta = event.payload.get("delta", "")
                        self._tokens_received += len(delta.split())
                        if self._thinking and self._stream_card:
                            self._thinking = False
                            header.agent_status = "acting"
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

                    # Update header status
                    header.agent_status = "acting"

                    # System failure handling
                    if is_error and tool_name == "system" and self._stream_card:
                        self._fail_streaming(content)
                        activity_bar.stop_activity()
                        logs_drawer.append_log(f"SYSTEM ERROR: {content}", level="error")
                        continue

                    # Create ActionCard (compact merged card)
                    card = transcript.add_action_card(tool_name, arguments, content, is_error)
                    self._active_card = card
                    self._stream_card = None
                    self._thinking = False

                    activity_bar.stop_activity()

                    # Diff handling: auto-open DiffDrawer for file writes
                    diff_text = self._pending_diffs.pop(0) if self._pending_diffs else ""
                    if diff_text:
                        path = (arguments or {}).get("path", "")
                        diff_drawer.show_single_diff(diff_text, path)
                        diff_drawer.show()

                    # Route logs
                    log_level = "error" if is_error else "info"
                    logs_drawer.append_log(f"TOOL: {tool_name} -> {content[:200]}", level=log_level)

                    # Verify detection: check if command is a test runner
                    if tool_name == "run_command" and arguments:
                        command = arguments.get("command", "")
                        if VERIFY_PATTERNS.search(command):
                            header.agent_status = "verifying"
                            passed = not is_error
                            errors = []
                            if is_error and content:
                                errors = [
                                    line
                                    for line in content.splitlines()
                                    if "FAILED" in line or "Error" in line or "error" in line.lower()
                                ][:10]

                            # Parse summary
                            summary = self._parse_verify_summary(content, passed)
                            transcript.add_verify(passed, summary, errors=errors, full_output=content)
                            logs_drawer.pin_verify(summary, passed)
                            logs_drawer.show()

                            # Publish verify_result event
                            await self.event_bus.publish(
                                self._event(
                                    "verify_result",
                                    {
                                        "passed": passed,
                                        "summary": summary,
                                        "errors": errors,
                                        "full_output": content,
                                    },
                                    "agent",
                                )
                            )

                elif event.type == "stream_end":
                    self._flush_stream_buffer(transcript)
                    if self._stream_card:
                        self._stream_card.stop_streaming()
                    self._stream_card = None
                    self._thinking = False
                    activity_bar.stop_activity()
                    self._stream_start_time = 0.0
                    self._tokens_received = 0
                    header.agent_status = "idle"

                elif event.type == "status":
                    status = event.payload.get("status", "ready")
                    if status == "processing":
                        activity_bar.start_activity("Processing...")
                    elif status == "ready":
                        activity_bar.stop_activity()

                elif event.type == "context":
                    ctx_pct = event.payload.get("ctx_pct", 0)
                    pinned = event.payload.get("pinned", [])
                    try:
                        ctx_widget = self.query_one(ContextWidget)
                        ctx_widget.update_context(ctx_pct, pinned)
                    except Exception:
                        pass
                    self._sync_header()

                elif event.type == "plan":
                    content = event.payload.get("content", "")
                    if content:
                        transcript.add_plan(content)

                elif event.type == "diff":
                    diff_text = event.payload.get("diff", "")
                    if diff_text:
                        path = event.payload.get("path", "")
                        diff_drawer.show_single_diff(diff_text, path)

                elif event.type == "agent_state":
                    state = event.payload.get("state", "idle")
                    header.agent_status = state

                elif event.type == "verify_result":
                    # Already handled inline during tool_result, but handle explicit events too
                    pass

        except Exception:
            logger.exception("_drain_events failed")

    def _parse_verify_summary(self, output: str, passed: bool) -> str:
        """Parse test output for a human-readable summary."""
        # Try to find pytest-style summary
        for line in reversed(output.splitlines()):
            line = line.strip()
            if "passed" in line.lower() or "failed" in line.lower():
                if any(c.isdigit() for c in line):
                    return f"Tests: {line}"
        if passed:
            return "Tests: passed"
        return "Tests: FAILED"

    def _flush_stream_buffer(self, transcript: TranscriptPane) -> None:
        if self._stream_card and self._stream_buffer:
            self._stream_card.append(self._stream_buffer)
            self._stream_buffer = ""

    def _fail_streaming(self, error_text: str) -> None:
        if self._stream_card:
            if error_text:
                self._stream_card.append(f"\n{error_text}")
            self._stream_card.mark_error()
        self._stream_card = None
        self._thinking = False

    async def _flush_stream(self) -> None:
        try:
            if not self._stream_buffer or not self._stream_card:
                return
            transcript = self.query_one(TranscriptPane)
            self._flush_stream_buffer(transcript)
        except Exception:
            logger.exception("_flush_stream failed")

    # --- Actions ---

    async def action_clear_transcript(self) -> None:
        transcript = self.query_one(TranscriptPane)
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
            self._approval_tracker.reset()

    async def action_command_palette(self) -> None:
        selection = await self.push_screen_wait(CommandPalette(self._palette_commands))
        if selection:
            await self._execute_palette_command(selection)

    async def _execute_palette_command(self, command_id: str) -> None:
        if command_id == "toggle_mode":
            await self.action_toggle_mode()
        elif command_id == "clear_transcript":
            await self.action_clear_transcript()
        elif command_id == "toggle_diff_drawer":
            self.action_toggle_diff_drawer()
        elif command_id == "toggle_logs_drawer":
            self.action_toggle_logs_drawer()
        elif command_id == "toggle_context":
            self.action_toggle_context_widget()
        elif command_id == "focus_rail":
            self.action_focus_rail()
        elif command_id == "focus_transcript":
            self.action_focus_transcript()
        elif command_id == "focus_composer":
            self.action_focus_composer()
        elif command_id == "toggle_rail":
            self.action_toggle_rail()
        elif command_id == "interrupt":
            self.action_interrupt_agent()
        elif command_id == "focus_mode":
            self.action_focus_mode()

    def action_focus_rail(self) -> None:
        rail = self.query_one(LeftRail)
        rail.focus()

    def action_toggle_rail(self) -> None:
        rail = self.query_one(LeftRail)
        rail.toggle()

    def action_focus_navigator(self) -> None:
        rail = self.query_one(LeftRail)
        rail.focus()

    def action_focus_transcript(self) -> None:
        transcript = self.query_one(TranscriptPane)
        transcript.focus()

    def action_focus_composer(self) -> None:
        self.query_one("#composer-input", Input).focus()

    def action_toggle_diff_drawer(self) -> None:
        diff_drawer = self.query_one(DiffDrawer)
        diff_drawer.toggle()

    def action_toggle_logs_drawer(self) -> None:
        logs_drawer = self.query_one(LogsDrawer)
        logs_drawer.toggle()

    def action_toggle_context_widget(self) -> None:
        ctx_widget = self.query_one(ContextWidget)
        ctx_widget.toggle()

    def action_toggle_output(self) -> None:
        from .layout import CodeOutputPane

        pane = self.query_one(CodeOutputPane)
        pane.toggle()
        if pane.has_class("expanded"):
            pane.focus()

    async def action_toggle_mode(self) -> None:
        if self.safety_state == SafeArmState.SAFE:
            approved = await self.push_screen_wait(ArmConfirmModal())
            if approved:
                self.safety_state = SafeArmState.ARMED
        else:
            self.safety_state = SafeArmState.SAFE
            self._approval_tracker.reset()
        self._sync_header()

    def action_expand_collapse_card(self) -> None:
        if self._active_card:
            self._active_card.toggle_collapse()

    def action_interrupt_or_close(self) -> None:
        """Esc: close drawer if open, else interrupt agent if processing."""
        diff_drawer = self.query_one(DiffDrawer)
        logs_drawer = self.query_one(LogsDrawer)

        if diff_drawer._visible:
            diff_drawer.hide()
            return
        if logs_drawer._visible:
            logs_drawer.hide()
            return

        if self._processing:
            self.action_interrupt_agent()

    def action_interrupt_agent(self) -> None:
        """Cancel running worker, stop streaming, append [Interrupted]."""
        if self._current_worker and not self._current_worker.is_finished:
            self._current_worker.cancel()

        if self._stream_card:
            self._stream_card.append("\n\n[Interrupted]")
            self._stream_card.stop_streaming()
            self._stream_card = None

        self._stream_buffer = ""
        self._thinking = False
        self._processing = False
        self._active_task_text = ""

        try:
            activity_bar = self.query_one(PinnedActivityBar)
            activity_bar.stop_activity()
        except Exception:
            pass

        self._sync_header()

    def action_focus_mode(self) -> None:
        """Toggle focus mode - minimal UI."""
        self._focus_mode = not self._focus_mode
        if self._focus_mode:
            self.screen.add_class("focus-mode")
            rail = self.query_one(LeftRail)
            rail.add_class("focus-locked")
        else:
            self.screen.remove_class("focus-mode")
            rail = self.query_one(LeftRail)
            rail.remove_class("focus-locked")

    def on_card_selected(self, message: CardSelected) -> None:
        self._active_card = message.card

        # Update diff drawer if visible with relevant content
        diff_drawer = self.query_one(DiffDrawer)
        if diff_drawer._visible:

            if isinstance(message.card, DiffCard):
                diff_drawer.show_single_diff(message.card._full_diff, message.card.file_path)
            elif isinstance(message.card, ActionCard) and message.card.result_content:
                # Show tool details in logs
                pass

    def on_mouse_down(self, event: events.MouseDown) -> None:
        if event.button != 1:
            event.stop()
            return
        return

    def on_file_pin_message(self, message: FilePinMessage) -> None:
        path = message.path
        if str(path) not in self._pinned_files:
            self._pinned_files.append(str(path))
        try:
            ctx_widget = self.query_one(ContextWidget)
            ctx_widget.update_context(self._context_pct(), self._pinned_files)
        except Exception:
            pass
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
