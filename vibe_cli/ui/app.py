# vibe_cli/ui/app.py

import asyncio
import logging
from pathlib import Path

import aiofiles
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, ScrollableContainer, Vertical
from textual.widgets import Collapsible, Input, Static


from vibe_cli.agent.loop import AgentLoop
from vibe_cli.config import AgentConfig, Config
from vibe_cli.providers.factory import build_provider
from vibe_cli.tools.base import ToolRegistry
from vibe_cli.tools.cloud import AWSResourceLister, K8sLogFetcher
from vibe_cli.tools.filesystem import ReadFileTool, StrReplaceTool, WriteFileTool
from vibe_cli.tools.git import GitAddTool, GitCommitTool, GitStatusTool
from vibe_cli.tools.shell import ShellTool

from .project_tree import FilePinMessage, PinnedFilesPanel, ProjectTree
from .theme import CSS_VARS
from .widgets import (
    AICoreAvatar,
    CommandHistory,
    ConfirmationModal,
    HyperChatBubble,
    ShortcutsPanel,
    StatusBar,
    SystemBanner,
    SystemMonitor,
)


logger = logging.getLogger(__name__)

# Minimal fallback CSS in case the main CSS fails to parse
DEFAULT_CSS = """
Screen { background: #1e1e2e; }
#layout-root { height: 1fr; width: 1fr; }
#header-area { dock: top; height: 3; }
#sidebar { dock: left; width: 32; background: #252839; }
#chat-area { height: 100%; }
#chat-view { height: 1fr; }
#input-container { dock: bottom; height: auto; }
"""


class ChatView(ScrollableContainer):
    def compose(self) -> ComposeResult:
        yield Static(id="top-spacer")

    def add_message(self, role: str, content: str) -> None:
        typewriter = role == "assistant" and len(content) > 10
        self.mount(HyperChatBubble(role, content, typewriter=typewriter))
        self.scroll_end(animate=False)

    def stream_append(self, text: str) -> None:
        if self.children:
            last = self.children[-1]
            if isinstance(last, HyperChatBubble) and last.role == "assistant":
                last.content += text
                last.refresh(layout=True)
                self.scroll_end(animate=False)


class VibeApp(App):
    CSS = (
        CSS_VARS
        + """
    Screen { background: $bg; }
    
    /* === Main Layout Structure === */
    #layout-root {
        height: 1fr;
        width: 1fr;
    }
    
    /* Header Area */
    #header-area {
        dock: top;
        height: 3;
    }
    
    /* Sidebar (Left) */
    #sidebar {
        dock: left;
        width: 24;
        background: $surface;
        border-right: heavy $primary;
        height: 100%;
        padding: 0 1;
        scrollbar-gutter: stable;
    }

    #sidebar-content {
        height: auto;
    }

    #sidebar Collapsible {
        padding-left: 0;
        padding-bottom: 0;
        border-top: none;
        background: $surface;
    }

    #sidebar Collapsible > Contents {
        padding-left: 0;
    }

    /* Chat Area (Main) */
    #chat-area {
        height: 100%;
        background: $bg;
        margin-left: 1;
    }
    
    #chat-view {
        height: 1fr;
        padding: 0 2;
        scrollbar-gutter: stable;
    }
    
    /* Input Box */
    #input-container {
        dock: bottom;
        height: auto;
        border-top: double $secondary;
        background: $surface;
        padding: 1 2;
    }
    
    Input {
        border: none;
        background: $surface;
        color: $primary;
        width: 100%;
    }
    Input:focus { border: none; }

    /* === Widget Specifics === */

    #avatar-container {
        height: 10;
        margin-bottom: 1;
    }
    
    #gauges-container {
        height: auto;
        layout: horizontal;
        align: center middle;
    }
    
    PowerGauge {
        width: 10;
        height: 12;
        margin: 0 1;
    }

    /* Project Tree */
    #project-tree {
        height: auto;
        min-height: 8;
        border: none;
        padding: 0;
    }

    /* Pinned Files */
    PinnedFilesPanel {
        height: auto;
        margin-top: 0;
        border: none;
        padding: 0;
    }

    /* StatusBar */
    StatusBar {
        background: $surface;
        border-top: solid $surface_glow;
        padding: 0 1;
        margin-top: 1;
    }

    /* Chat Bubbles */
    HyperChatBubble {
        width: 100%;
        height: auto;
        padding: 0 1;
        margin-bottom: 1;
    }

    /* CommandHistory */
    CommandHistory {
        height: auto;
        margin-top: 0;
    }

    /* SystemMonitor */
    SystemMonitor {
        height: auto;
        margin-top: 0;
    }

    /* ShortcutsPanel Overlay */
    #shortcuts-panel {
        dock: bottom;
        height: auto;
        margin: 1 2;
        display: none;
    }
    #shortcuts-panel.visible {
        display: block;
    }

    /* Zen mode */
    Screen.zen #header-area {
        display: none;
    }
    Screen.zen #sidebar {
        display: none;
    }
    Screen.zen #chat-area {
        margin-left: 0;
    }
    Screen.zen #chat-view {
        padding: 0 1;
    }
    """
    )

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit"),
        Binding("question_mark", "toggle_help", "Help", key_display="?"),
        Binding("ctrl+z", "toggle_zen", "Zen"),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.workspace = Path.cwd()
        self.config = Config.load()
        self.pinned_files: set[Path] = set()
        self.tools = ToolRegistry(load_plugins=False)
        self.tools.register(ReadFileTool(self.workspace))
        self.tools.register(WriteFileTool(self.workspace))
        self.tools.register(StrReplaceTool(self.workspace))
        self.tools.register(GitStatusTool(self.workspace))
        self.tools.register(GitAddTool(self.workspace))
        self.tools.register(GitCommitTool(self.workspace))
        self.tools.register(AWSResourceLister())
        self.tools.register(K8sLogFetcher())
        self.tools.register(ShellTool(self.workspace, allowed_commands=self.config.shell.allowed))

        provider_cfg = self.config.providers.get(self.config.default_provider)
        self.provider = build_provider(provider_cfg)
        self.agent = AgentLoop(self.provider, self.tools, AgentConfig(), on_confirmation=self._handle_confirmation)

    async def _handle_confirmation(self, tool_name: str, arguments: dict) -> bool:
        """Handle confirmation requests from the agent"""
        return await self.push_screen_wait(ConfirmationModal(tool_name, arguments))

    def on_mount(self) -> None:
        self.set_interval(10.0, self._poll_models)
        status_bar = self.query_one("#status-bar", StatusBar)
        status_bar.model_name = self.provider.model
        self.run_worker(self._load_plugins(), group="plugins")

    async def _load_plugins(self) -> None:
        await asyncio.to_thread(self.tools.register_plugins, self.workspace)

    async def _poll_models(self) -> None:
        """Poll for active models"""
        try:
            models = await self.provider.get_available_models()
            if models:
                # Update if different (taking the first one as active)
                new_model = models[0]
                avatar = self.query_one("#avatar", AICoreAvatar)
                status_bar = self.query_one("#status-bar", StatusBar)
                if avatar.model != new_model:
                    avatar.model = new_model
                    status_bar.model_name = new_model
        except Exception:
            pass  # Silent fail on polling errors

    def compose(self) -> ComposeResult:
        # Heavily layered layout

        # 1. Top System Header
        yield Container(SystemBanner(), id="header-area")

        with Container(id="layout-root"):
            # 2. Sidebar (AI Core)
            with ScrollableContainer(id="sidebar"):
                with Vertical(id="sidebar-content"):
                    avatar = AICoreAvatar(id="avatar")
                    avatar.model = self.provider.model
                    yield Container(avatar, id="avatar-container")

                    yield Collapsible(
                        ProjectTree(self.workspace, id="project-tree"),
                        title="PROJECT",
                        collapsed=False,
                        id="sidebar-project",
                    )

                    yield Collapsible(
                        PinnedFilesPanel(id="pinned-files"),
                        title="PINNED",
                        collapsed=True,
                        id="sidebar-pinned",
                    )

                    yield Collapsible(
                        SystemMonitor(id="system-monitor"),
                        title="SYSTEM",
                        collapsed=True,
                        id="sidebar-system",
                    )

                    yield Collapsible(
                        CommandHistory(id="cmd-history"),
                        title="LOG",
                        collapsed=True,
                        id="sidebar-log",
                    )

            # 3. Main Chat View
            with Vertical(id="chat-area"):
                yield ChatView(id="chat-view")
                yield ShortcutsPanel(id="shortcuts-panel")
                with Container(id="input-container"):
                    yield Input(placeholder=">> INITIATE_OVERRIDE_COMMAND", id="input")
                    yield StatusBar(id="status-bar")

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        event.input.value = ""

        status_bar = self.query_one("#status-bar", StatusBar)
        status_bar.status = "processing"
        status_bar.char_count = 0

        chat = self.query_one("#chat-view", ChatView)
        chat.add_message("user", text)
        self.run_worker(self.process(text))

    def on_input_changed(self, event: Input.Changed) -> None:
        """Update status bar when user types"""
        status_bar = self.query_one("#status-bar", StatusBar)
        if event.value:
            status_bar.status = "typing"
            status_bar.char_count = len(event.value)
        else:
            status_bar.status = "ready"
            status_bar.char_count = 0

    async def process(self, text: str) -> None:
        chat = self.query_one("#chat-view", ChatView)
        avatar = self.query_one("#avatar", AICoreAvatar)
        status_bar = self.query_one("#status-bar", StatusBar)
        cmd_history = self.query_one("#cmd-history", CommandHistory)

        chat.add_message("assistant", "")
        avatar.state = "thinking"
        status_bar.status = "processing"

        # start_time = time.time()
        agent_input = await self._inject_pinned_context(text)

        try:
            async for chunk in self.agent.run(agent_input):
                if hasattr(chunk, "text") and chunk.text:
                    chat.stream_append(chunk.text)
                elif hasattr(chunk, "tool_name") and chunk.tool_name:
                    # This is a ToolResult - add to command history
                    status = "error" if chunk.is_error else "success"
                    cmd_history.add_command(chunk.tool_name, status)
                    if chunk.is_error:
                        try:
                            log_section = self.query_one("#sidebar-log", Collapsible)
                            log_section.collapsed = False
                        except Exception:
                            pass
                    avatar.state = "coding"
                    chat.add_message("tool", chunk.content)
                    chat.add_message("assistant", "")

            # latency = time.time() - start_time

            avatar.state = "success"
            status_bar.status = "ready"
            # Return to idle after delay
            self.set_timer(3.0, lambda: setattr(avatar, "state", "idle"))

        except Exception as e:
            chat.add_message("system", f"CRITICAL_FAILURE: {e}")
            avatar.state = "error"
            status_bar.status = "ready"

    def action_toggle_help(self) -> None:
        """Toggle the shortcuts help panel visibility"""
        panel = self.query_one("#shortcuts-panel", ShortcutsPanel)
        panel.toggle_class("visible")

    def action_toggle_zen(self) -> None:
        """Toggle Zen mode to focus on chat/code"""
        self.screen.toggle_class("zen")

    async def on_file_pin_message(self, message: FilePinMessage) -> None:
        path = message.path
        if not str(path.resolve()).startswith(str(self.workspace.resolve())):
            return
        rel = path.relative_to(self.workspace)
        if rel in self.pinned_files:
            self.pinned_files.remove(rel)
        else:
            self.pinned_files.add(rel)
        panel = self.query_one("#pinned-files", PinnedFilesPanel)
        panel.set_pins(sorted(self.pinned_files))
        if self.pinned_files:
            try:
                pinned_section = self.query_one("#sidebar-pinned", Collapsible)
                pinned_section.collapsed = False
            except Exception:
                pass

    async def _inject_pinned_context(self, text: str) -> str:
        if not self.pinned_files:
            return text

        blocks: list[str] = []
        total_chars = 0
        max_total = 20000
        max_per_file = 6000

        for rel_path in sorted(self.pinned_files):
            path = self.workspace / rel_path
            try:
                async with aiofiles.open(path, "r") as f:
                    content = await f.read(max_per_file + 1)
            except Exception:
                continue

            truncated = ""
            if len(content) > max_per_file:
                content = content[:max_per_file]
                truncated = "\n[...truncated]\n"

            block = f"## Pinned: {rel_path}\n{content}{truncated}\n"
            if total_chars + len(block) > max_total:
                break
            blocks.append(block)
            total_chars += len(block)

        if not blocks:
            return text

        context = "\n".join(blocks)
        return f"{text}\n\n---\nPinned context:\n{context}"


if __name__ == "__main__":
    VibeApp().run()
