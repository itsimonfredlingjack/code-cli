from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import json
from pathlib import Path
from typing import Iterable

import pygments.styles
from rich.align import Align
from rich.console import RenderableType
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.containers import Container, ScrollableContainer, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Button, Input, Label, ListItem, ListView, Static, TabbedContent, TabPane

from .theme import COLORS, HUD

pygments.styles.STYLE_MAP["code_neon"] = "code_cli.ui.theme:CodeNeonStyle"


class SafeArmState(str, Enum):
    SAFE = "SAFE"
    ARMED = "ARMED"
    ARMED_PENDING = "ARMED_PENDING"


@dataclass(frozen=True)
class PaletteCommand:
    command_id: str
    title: str
    description: str


class CardSelected(Message):
    def __init__(self, card: "BaseCard") -> None:
        super().__init__()
        self.card = card


class StatusBar(Widget):
    status = reactive("ready")
    mode = reactive(SafeArmState.SAFE.value)
    provider = reactive("unknown")
    model = reactive("unknown")
    branch = reactive("main")
    ctx_pct = reactive(0)
    tool_queue = reactive(0)

    def render(self) -> RenderableType:
        text = Text()
        if self.mode == SafeArmState.SAFE.value:
            mode_style = COLORS["warning"]
            mode_label = SafeArmState.SAFE.value
        elif self.mode == SafeArmState.ARMED.value:
            mode_style = COLORS["success"]
            mode_label = SafeArmState.ARMED.value
        else:
            mode_style = COLORS["secondary"]
            mode_label = "ARMED*"

        text.append(mode_label, style=mode_style)
        text.append(" | ", style=COLORS["text_dim"])
        text.append(f"{self.provider}:{self.model}", style=COLORS["text"])
        text.append(" | ", style=COLORS["text_dim"])
        text.append(f"CTX {self.ctx_pct}%", style=COLORS["text_dim"])
        text.append(" | ", style=COLORS["text_dim"])
        text.append(f"BR {self.branch}", style=COLORS["text_dim"])
        if self.tool_queue:
            text.append(" | ", style=COLORS["text_dim"])
            text.append(f"TOOLS {self.tool_queue}", style=COLORS["secondary"])
        text.append(" | ", style=COLORS["text_dim"])
        status_style = COLORS["secondary"] if self.status == "processing" else COLORS["text_dim"]
        if self.status == "typing":
            status_style = COLORS["primary"]
        text.append(self.status.upper(), style=status_style)
        return text


class AgentHeader(Widget):
    model = reactive("granite")
    tokens = reactive(0)
    branch = reactive("main")

    def render(self) -> RenderableType:
        line1 = f" [bold {COLORS['text_bright']}]CODE CLI[/] [dim]v0.6.0[/]"
        line2 = (
            f" [dim]{self.branch}[/] [{COLORS['text_dim']}]·[/] "
            f"[{COLORS['secondary']}]{self.model}[/] [{COLORS['text_dim']}]·[/] "
            f"[dim]{self.tokens} tks[/]"
        )
        content = Text.from_markup(f"{line1}\n{line2}")
        return Align.left(content)


class SectionHeader(Static):
    def __init__(self, label: str, **kwargs: object) -> None:
        super().__init__(label, classes="section-header", **kwargs)


class ToolRunList(ListView):
    def add_run(self, label: str) -> None:
        self.mount(ListItem(Label(label)))

    def clear_runs(self) -> None:
        self.remove_children()


class SessionList(ListView):
    def set_sessions(self, sessions: Iterable[str]) -> None:
        self.remove_children()
        for name in sessions:
            self.mount(ListItem(Label(name)))


class NavigatorPane(Container):
    can_focus = True

    def __init__(self, root_path: Path, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.root_path = root_path

    def compose(self) -> ComposeResult:
        from .project_tree import PinnedFilesPanel, ProjectTree

        yield SectionHeader("NAVIGATOR")
        yield ProjectTree(self.root_path, id="project-tree")
        yield SectionHeader("PINNED")
        yield PinnedFilesPanel(id="pinned-files")
        yield SectionHeader("TOOLS")
        yield ToolRunList(id="tool-runs")
        yield SectionHeader("SESSIONS")
        yield SessionList(id="sessions")


class BaseCard(Widget):
    can_focus = True

    content = reactive("")
    collapsed = reactive(False)

    def __init__(self, title: str, content: str, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.title = title
        self.content = content
        self.timestamp = datetime.now()

    def _truncate(self, text: str, limit: int = 14) -> str:
        lines = text.splitlines()
        if len(lines) <= limit:
            return text
        return "\n".join(lines[:limit]) + "\n..."

    def toggle_collapse(self) -> None:
        self.collapsed = not self.collapsed
        self.refresh(layout=True)

    def on_click(self, event: events.Click) -> None:
        self.post_message(CardSelected(self))


class MessageCard(BaseCard):
    def __init__(self, role: str, content: str, **kwargs: object) -> None:
        self.role = role
        super().__init__(role.upper(), content, **kwargs)

    def append(self, text: str) -> None:
        self.content += text
        self.refresh(layout=False)

    def render(self) -> RenderableType:
        time_str = self.timestamp.strftime("%H:%M")
        header = f"{self.role.upper()} · {time_str}"
        body = self._truncate(self.content) if self.collapsed else self.content
        if self.role == "assistant":
            renderable = Markdown(body)
        else:
            renderable = Text(body, style=COLORS["text"])
        return Panel(
            renderable,
            title=header,
            title_align="left",
            border_style=COLORS["card_border"],
            box=HUD,
            padding=(0, 1),
            style=f"on {COLORS['surface']}",
        )


class ToolCard(BaseCard):
    def __init__(
        self,
        tool_name: str,
        arguments: dict | None,
        result: str,
        is_error: bool,
        **kwargs: object,
    ) -> None:
        title = f"TOOL {tool_name.upper()}"
        super().__init__(title, result, **kwargs)
        self.tool_name = tool_name
        self.arguments = arguments or {}
        self.is_error = is_error

    def render(self) -> RenderableType:
        time_str = self.timestamp.strftime("%H:%M")
        status = "ERROR" if self.is_error else "OK"
        header = f"{self.tool_name.upper()} · {status} · {time_str}"
        args_json = json.dumps(self.arguments, indent=2)
        body_text = f"ARGS:\n{args_json}\n\nRESULT:\n{self.content}"
        body = self._truncate(body_text, limit=18) if self.collapsed else body_text
        return Panel(
            Syntax(body, "text", theme="code_neon", word_wrap=True),
            title=header,
            title_align="left",
            border_style=COLORS["card_border"],
            box=HUD,
            padding=(0, 1),
            style=f"on {COLORS['surface']}",
        )


class PlanCard(BaseCard):
    def render(self) -> RenderableType:
        time_str = self.timestamp.strftime("%H:%M")
        header = f"PLAN · {time_str}"
        body = self._truncate(self.content, limit=18) if self.collapsed else self.content
        return Panel(
            Markdown(body),
            title=header,
            title_align="left",
            border_style=COLORS["card_border"],
            box=HUD,
            padding=(0, 1),
            style=f"on {COLORS['surface']}",
        )


class TranscriptPane(ScrollableContainer):
    can_focus = True

    def compose(self) -> ComposeResult:
        yield Static(id="transcript-top")

    def add_message(self, role: str, content: str) -> MessageCard:
        card = MessageCard(role, content, classes="card")
        self.mount(card)
        self.scroll_end(animate=False)
        return card

    def add_tool(self, tool_name: str, arguments: dict | None, result: str, is_error: bool) -> ToolCard:
        card = ToolCard(tool_name, arguments, result, is_error, classes="card")
        if len(result.splitlines()) > 18:
            card.collapsed = True
        self.mount(card)
        self.scroll_end(animate=False)
        return card

    def add_plan(self, content: str) -> PlanCard:
        card = PlanCard("PLAN", content, classes="card")
        if len(content.splitlines()) > 18:
            card.collapsed = True
        self.mount(card)
        self.scroll_end(animate=False)
        return card


class InspectorPane(Widget):
    can_focus = True

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._diff_view = Static("No diff", id="diff-view")
        self._tool_view = Static("Select a tool card", id="tool-view")
        self._context_view = Static("Pin files to show context", id="context-view")
        self._help_view = Static(self._help_text(), id="help-view")

    def compose(self) -> ComposeResult:
        with TabbedContent(id="inspector-tabs"):
            with TabPane("Diff", id="tab-diff"):
                yield self._diff_view
            with TabPane("Tool", id="tab-tool"):
                yield self._tool_view
            with TabPane("Context", id="tab-context"):
                yield self._context_view
            with TabPane("Help", id="tab-help"):
                yield self._help_view

    def show_diff(self, diff_text: str) -> None:
        text = diff_text if diff_text.strip() else "No diff"
        self._diff_view.update(Syntax(text, "diff", theme="code_neon", word_wrap=True))

    def show_tool(self, tool_name: str, arguments: dict | None, result: str) -> None:
        args_json = json.dumps(arguments or {}, indent=2)
        body = f"TOOL: {tool_name}\n\nARGS:\n{args_json}\n\nRESULT:\n{result}"
        self._tool_view.update(Syntax(body, "text", theme="code_neon", word_wrap=True))

    def show_context(self, pinned: list[str], ctx_pct: int) -> None:
        if not pinned:
            body = "Pin files to build context."
        else:
            body = "Pinned Files:\n" + "\n".join(f"- {p}" for p in pinned)
        body += f"\n\nCTX {ctx_pct}%"
        self._context_view.update(Text(body, style=COLORS["text"]))

    def show_help(self) -> None:
        self._help_view.update(Text(self._help_text(), style=COLORS["text"]))

    def _help_text(self) -> str:
        return (
            "Keybinds:\n"
            "- Ctrl+C: Quit application\n"
            "- Ctrl+K: Command palette\n"
            "- Tab / Shift+Tab: Focus cycle\n"
            "- Ctrl+1/2/3/4: Focus panes\n"
            "- Ctrl+.: Toggle SAFE/ARMED\n"
            "- Ctrl+E: Expand/Collapse card\n"
            "- Ctrl+L: Clear transcript\n"
        )



class OutputPane(ScrollableContainer):
    """
    A collapsible output drawer for global logs and raw command output.
    """
    can_focus = True
    
    def compose(self) -> ComposeResult:
        yield SectionHeader("OUTPUT / TERMINAL")
        yield Static(id="output-content")

    def append(self, text: str) -> None:
        widget = self.query_one("#output-content", Static)
        # Simple append for now, could be enhanced with a Rich Log
        # Using renderable to allow styling later if needed
        current = widget.renderable
        if isinstance(current, Text):
            current.append(text)
            widget.update(current)
        else:
            widget.update(Text(text, style=COLORS["text"]))
        self.scroll_end(animate=False)

    def clear(self) -> None:
        self.query_one("#output-content", Static).update("")


class ComposerBar(Container):
    def compose(self) -> ComposeResult:
        with Vertical(id="composer-stack"):
            yield Input(placeholder=">> COMMAND OR QUERY", id="composer-input")
            yield StatusBar(id="status-bar")


class CommandItem(ListItem):
    def __init__(self, command: PaletteCommand) -> None:
        self.command_id = command.command_id
        label = Label(f"{command.title} — {command.description}")
        super().__init__(label)


class CommandPalette(ModalScreen[str | None]):
    CSS = f"""
    CommandPalette {{
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }}

    #palette {{
        width: 80;
        height: auto;
        padding: 1 2;
        border: solid {COLORS['primary']};
        background: {COLORS['surface']};
    }}

    #palette-input {{
        height: 3;
        border: solid {COLORS['surface_light']};
        background: {COLORS['surface_glow']};
    }}
    """

    def __init__(self, commands: list[PaletteCommand]) -> None:
        super().__init__()
        self._commands = commands
        self._filtered = commands

    def compose(self) -> ComposeResult:
        with Container(id="palette"):
            yield Input(placeholder="Search commands", id="palette-input")
            yield ListView(id="palette-list")

    def on_mount(self) -> None:
        self._render_list(self._commands)
        self.query_one("#palette-input", Input).focus()

    def _render_list(self, commands: list[PaletteCommand]) -> None:
        list_view = self.query_one("#palette-list", ListView)
        list_view.remove_children()
        for command in commands:
            list_view.mount(CommandItem(command))

    def on_input_changed(self, event: Input.Changed) -> None:
        query = event.value.strip().lower()
        if not query:
            self._filtered = self._commands
        else:
            self._filtered = [
                cmd
                for cmd in self._commands
                if query in cmd.title.lower() or query in cmd.description.lower()
            ]
        self._render_list(self._filtered)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if self._filtered:
            self.dismiss(self._filtered[0].command_id)
        else:
            self.dismiss(None)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item = event.item
        if isinstance(item, CommandItem):
            self.dismiss(item.command_id)


class ApprovalModal(ModalScreen[bool]):
    CSS = f"""
    ApprovalModal {{
        align: center middle;
        background: rgba(0, 0, 0, 0.85);
    }}

    #dialog {{
        grid-size: 2;
        grid-gutter: 1 2;
        grid-rows: 1fr 4 4 1;
        padding: 1 2;
        width: 84;
        height: auto;
        border: solid {COLORS['warning']};
        background: {COLORS['surface']};
    }}

    #title {{
        column-span: 2;
        height: 1;
        width: 100%;
        content-align: center middle;
        text-style: bold;
        color: {COLORS['warning']};
    }}
    """

    def __init__(self, tool_name: str, arguments: dict, diff_text: str, reason: str, risk: str) -> None:
        super().__init__()
        self.tool_name = tool_name
        self.arguments = arguments
        self.diff_text = diff_text
        self.reason = reason
        self.risk = risk

    def compose(self) -> ComposeResult:
        args_json = json.dumps(self.arguments, indent=2)
        reason_line = f"Reason: {self.reason} | Risk: {self.risk}"

        yield Container(
            Label(f"CONFIRM TOOL: {self.tool_name}", id="title"),
            Label(reason_line, id="reason"),
            Syntax(
                self.diff_text or "No diff available",
                "diff",
                theme="code_neon",
                line_numbers=False,
                word_wrap=True,
                id="diff",
            ),
            Syntax(
                args_json,
                "json",
                theme="code_neon",
                line_numbers=False,
                word_wrap=True,
                id="details",
            ),
            Button("REJECT", variant="error", id="reject"),
            Button("APPROVE", variant="success", id="approve"),
            id="dialog",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "approve":
            self.dismiss(True)
        else:
            self.dismiss(False)


class ArmConfirmModal(ModalScreen[bool]):
    CSS = f"""
    ArmConfirmModal {{
        align: center middle;
        background: rgba(0, 0, 0, 0.85);
    }}

    #dialog {{
        grid-size: 2;
        grid-gutter: 1 2;
        grid-rows: 1fr 2 1;
        padding: 1 2;
        width: 70;
        height: auto;
        border: solid {COLORS['warning']};
        background: {COLORS['surface']};
    }}

    #title {{
        column-span: 2;
        height: 1;
        width: 100%;
        content-align: center middle;
        text-style: bold;
        color: {COLORS['warning']};
    }}
    """

    def compose(self) -> ComposeResult:
        yield Container(
            Label("ENABLE ARMED MODE", id="title"),
            Label("Tools can write files or run commands.", id="details"),
            Button("CANCEL", variant="error", id="reject"),
            Button("ARM", variant="success", id="approve"),
            id="dialog",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "approve":
            self.dismiss(True)
        else:
            self.dismiss(False)


class ArmRequiredModal(ModalScreen[bool]):
    CSS = f"""
    ArmRequiredModal {{
        align: center middle;
        background: rgba(0, 0, 0, 0.85);
    }}

    #dialog {{
        grid-size: 1;
        grid-gutter: 1 2;
        grid-rows: 1fr 2 1;
        padding: 1 2;
        width: 70;
        height: auto;
        border: solid {COLORS['warning']};
        background: {COLORS['surface']};
    }}

    #title {{
        height: 1;
        width: 100%;
        content-align: center middle;
        text-style: bold;
        color: {COLORS['warning']};
    }}
    """

    def compose(self) -> ComposeResult:
        yield Container(
            Label("ARMED REQUIRED", id="title"),
            Label("Switch to ARMED to approve tool execution.", id="details"),
            Button("OK", variant="primary", id="ok"),
            id="dialog",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(False)


class ClearTranscriptModal(ModalScreen[bool]):
    """Modal for confirming transcript clear operation"""

    CSS = f"""
    ClearTranscriptModal {{
        align: center middle;
        background: rgba(0, 0, 0, 0.85);
    }}

    #dialog {{
        grid-size: 2;
        grid-gutter: 1 2;
        grid-rows: 1fr 2 1;
        padding: 1 2;
        width: 70;
        height: auto;
        border: solid {COLORS['warning']};
        background: {COLORS['surface']};
    }}

    #title {{
        column-span: 2;
        height: 1;
        width: 100%;
        content-align: center middle;
        text-style: bold;
        color: {COLORS['warning']};
    }}

    #details {{
        column-span: 2;
        height: 2;
        width: 100%;
        content-align: center middle;
        color: {COLORS['text']};
    }}

    #shortcuts {{
        column-span: 2;
        height: 1;
        width: 100%;
        content-align: center middle;
        color: {COLORS['text_dim']};
        text-style: italic;
    }}

    Button {{
        width: 100%;
    }}
    """

    def __init__(self, message_count: int):
        super().__init__()
        self.message_count = message_count

    def compose(self) -> ComposeResult:
        count_text = f"Delete {self.message_count} message{'s' if self.message_count != 1 else ''}"
        yield Container(
            Label("CLEAR CONVERSATION HISTORY", id="title"),
            Label(count_text + " from transcript?", id="details"),
            Label("ESC=Cancel  Enter=Confirm", id="shortcuts"),
            Button("CANCEL", variant="error", id="cancel"),
            Button("CLEAR", variant="warning", id="confirm"),
            id="dialog",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm":
            self.dismiss(True)
        else:
            self.dismiss(False)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(False)
        elif event.key == "enter":
            self.dismiss(True)
