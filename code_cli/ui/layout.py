# code_cli/ui/layout.py

from __future__ import annotations

from pathlib import Path

from rich.console import RenderableType
from rich.syntax import Syntax
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, ScrollableContainer, Vertical
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Input, Label, ListItem, ListView, Static

from .cards import (
    ActionCard,
    AgentMessageCard,
    DecisionCard,
    DiffCard,
    EmptyStateCard,
    ErrorCard,
    PlanCard,
    SystemCard,
    ToolCallCard,
    ToolResultCard,
    UserMessageCard,
    VerifyCard,
)
from .theme import COLORS, get_icon


class SectionHeader(Static):
    """Section header for navigation panels."""

    def __init__(self, label: str, **kwargs: object) -> None:
        kwargs.pop("classes", None)
        super().__init__(label, **kwargs)
        self.add_class("section-header")


class LeftRail(Container):
    """Collapsible left rail: icon-only (4 chars) or expanded (26 chars)."""

    can_focus = True

    BINDINGS = [
        Binding("up", "move_up", "Up", show=False),
        Binding("down", "move_down", "Down", show=False),
        Binding("enter", "select_icon", "Select", show=False),
    ]

    _icon_ids = ["icon-files", "icon-sessions", "icon-tools", "icon-search", "icon-settings"]

    def __init__(self, root_path: Path, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.root_path = root_path
        self._expanded = False
        self._active_icon = None

    def compose(self) -> ComposeResult:
        from .project_tree import PinnedFilesPanel, ProjectTree

        yield Static(get_icon("files"), id="icon-files", classes="rail-icon active")
        yield Static(get_icon("sessions"), id="icon-sessions", classes="rail-icon")
        yield Static(get_icon("tools"), id="icon-tools", classes="rail-icon")
        yield Static(get_icon("search"), id="icon-search", classes="rail-icon")
        yield Static(get_icon("settings"), id="icon-settings", classes="rail-icon")

        nav_header = SectionHeader("NAVIGATOR", id="header-nav")
        nav_header.add_class("rail-expanded")
        yield nav_header

        yield ProjectTree(self.root_path, id="project-tree", classes="rail-expanded")

        pinned_header = SectionHeader("PINNED", id="header-pinned")
        pinned_header.add_class("rail-expanded")
        yield pinned_header

        yield PinnedFilesPanel(id="pinned-files", classes="rail-expanded")

        tools_header = SectionHeader("TOOLS", id="header-tools")
        tools_header.add_class("rail-expanded")
        yield tools_header

        yield ToolRunList(id="tool-runs", classes="rail-expanded")

        sessions_header = SectionHeader("SESSIONS", id="header-sessions")
        sessions_header.add_class("rail-expanded")
        yield sessions_header

        yield SessionList(id="sessions", classes="rail-expanded")

    def on_mount(self) -> None:
        self._update_display()
        self._active_icon = "icon-files"

    def toggle(self) -> None:
        if self.has_class("focus-locked"):
            return
        self._expanded = not self._expanded
        if self._expanded:
            self.add_class("expanded")
        else:
            self.remove_class("expanded")
        self._update_display()
        self.refresh(layout=True)

    def on_click(self, event) -> None:
        target = event.target
        if target and hasattr(target, "id"):
            icon_id = target.id
            if icon_id and icon_id.startswith("icon-"):
                if self._active_icon:
                    old_icon = self.query_one(f"#{self._active_icon}", Static)
                    if old_icon:
                        old_icon.remove_class("active")
                target.add_class("active")
                self._active_icon = icon_id
                self.focus()
                event.stop()
                return
        event.stop()

    def on_mouse_down(self, event) -> None:
        target = event.target
        if target and hasattr(target, "id") and target.id and target.id.startswith("icon-"):
            return
        if target and hasattr(target, "parent") and target.parent == self:
            event.stop()
            return
        event.stop()

    def on_focus(self) -> None:
        pass

    def _update_display(self) -> None:
        for widget in self.query(".rail-icon"):
            widget.display = not self._expanded
        for widget in self.query(".rail-expanded"):
            widget.display = self._expanded

    def _set_active_icon(self, icon_id: str) -> None:
        if self._active_icon:
            try:
                old_icon = self.query_one(f"#{self._active_icon}", Static)
                old_icon.remove_class("active")
            except Exception:
                pass
        try:
            new_icon = self.query_one(f"#{icon_id}", Static)
            new_icon.add_class("active")
            self._active_icon = icon_id
        except Exception:
            pass

    def action_move_up(self) -> None:
        if self._expanded or not self._active_icon:
            return
        try:
            idx = self._icon_ids.index(self._active_icon)
            new_idx = (idx - 1) % len(self._icon_ids)
            self._set_active_icon(self._icon_ids[new_idx])
        except ValueError:
            pass

    def action_move_down(self) -> None:
        if self._expanded or not self._active_icon:
            return
        try:
            idx = self._icon_ids.index(self._active_icon)
            new_idx = (idx + 1) % len(self._icon_ids)
            self._set_active_icon(self._icon_ids[new_idx])
        except ValueError:
            pass

    def action_select_icon(self) -> None:
        if not self._active_icon:
            return
        if not self._expanded:
            self.toggle()


class ToolRunList(ListView):
    """List of tool runs."""

    def add_run(self, label: str) -> None:
        self.mount(ListItem(Label(label)))

    def clear_runs(self) -> None:
        self.remove_children()


class SessionList(ListView):
    """List of sessions."""

    def set_sessions(self, sessions: list[str]) -> None:
        self.remove_children()
        for name in sessions:
            self.mount(ListItem(Label(name)))


class PinnedActivityBar(Widget):
    """Compact activity bar (1-2 lines max) showing current agent activity."""

    _active = reactive(False)
    _current_step = reactive("")
    _current_file = reactive("")
    _current_tool = reactive("")
    _elapsed_seconds = reactive(0)
    _start_time = 0.0

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._active = False
        self._start_time = 0.0

    def watch__active(self, active: bool) -> None:
        if active:
            self.add_class("active")
        else:
            self.remove_class("active")

    def start_activity(self, step: str, file: str = "", tool: str = "") -> None:
        import time

        self._active = True
        self._current_step = step
        self._current_file = file
        self._current_tool = tool
        self._elapsed_seconds = 0
        self._start_time = time.time()
        self.refresh()

    def stop_activity(self) -> None:
        self._active = False
        self._start_time = 0.0
        self.refresh()

    def tick_elapsed(self) -> None:
        import time

        if self._active and self._start_time > 0:
            self._elapsed_seconds = int(time.time() - self._start_time)
            self.refresh()

    def update_elapsed(self, seconds: int) -> None:
        self._elapsed_seconds = seconds
        self.refresh()

    def render(self) -> RenderableType:
        if not self._active:
            return Text("")

        text = Text()
        spinner = get_icon("spinner")
        text.append(f"{spinner} ", style=COLORS["accent_cyan"])
        text.append(self._current_step, style=COLORS["text"])

        if self._current_file:
            text.append(" \u00b7 ", style=COLORS["text_muted"])
            file_icon = get_icon("file")
            text.append(f"{file_icon} {self._current_file}", style=COLORS["text"])

        if self._current_tool:
            text.append(" \u00b7 ", style=COLORS["text_muted"])
            tool_icon = get_icon("tool")
            text.append(f"{tool_icon} {self._current_tool}", style=COLORS["text"])

        if self._elapsed_seconds > 0:
            text.append(" \u00b7 ", style=COLORS["text_muted"])
            text.append(f"{self._elapsed_seconds}s", style=COLORS["text_muted"])

        return text


class ContextWidget(Widget):
    """Collapsible context summary widget at top of TranscriptPane."""

    can_focus = True
    _collapsed = reactive(True)
    ctx_pct = reactive(0)
    pinned_count = reactive(0)
    last_update = reactive("")
    pinned_files: list[str] = []
    context_sources: list[str] = []
    ctx_delta = reactive("")

    BINDINGS = [
        Binding("ctrl+x", "toggle_context", "Toggle Context", priority=True),
    ]

    def render(self) -> RenderableType:
        if self._collapsed:
            text = Text()
            text.append("CTX ", style=COLORS["text_muted"])
            text.append(f"{self.ctx_pct}%", style=COLORS["text"])
            text.append(f" \u2022 {self.pinned_count} pinned", style=COLORS["text_muted"])
            if self.last_update:
                text.append(f" \u2022 updated {self.last_update}", style=COLORS["text_muted"])
            if self.ctx_delta:
                text.append(f" \u2022 {self.ctx_delta}", style=COLORS["accent_cyan"])
            return text

        text = Text()
        text.append("CONTEXT\n", style=f"bold {COLORS['text']}")
        text.append(f"Usage: {self.ctx_pct}%\n", style=COLORS["text"])

        if self.pinned_files:
            text.append("\nPinned Files:\n", style=f"bold {COLORS['text_muted']}")
            for f in self.pinned_files[:5]:
                text.append(f"  {get_icon('file')} {f}\n", style=COLORS["text"])
            if len(self.pinned_files) > 5:
                text.append(f"  ... and {len(self.pinned_files) - 5} more\n", style=COLORS["text_muted"])

        if self.context_sources:
            text.append("\nRecent Sources:\n", style=f"bold {COLORS['text_muted']}")
            for s in self.context_sources[:5]:
                text.append(f"  {s}\n", style=COLORS["text_muted"])

        return text

    def toggle(self) -> None:
        self._collapsed = not self._collapsed
        self.refresh(layout=True)

    def action_toggle_context(self) -> None:
        self.toggle()

    def update_context(self, ctx_pct: int, pinned: list[str], sources: list[str] | None = None) -> None:
        self.ctx_pct = ctx_pct
        self.pinned_files = pinned
        self.pinned_count = len(pinned)
        if sources:
            self.context_sources = sources
        self.refresh()


class TranscriptPane(ScrollableContainer):
    """Main transcript pane showing timeline of badge cards."""

    can_focus = True
    _user_at_bottom = reactive(True)

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._action_cards: dict[str, ActionCard] = {}

    def compose(self) -> ComposeResult:
        with Vertical(id="transcript-list"):
            yield Static(id="transcript-top")

    def _list(self) -> Vertical:
        return self.query_one("#transcript-list", Vertical)

    def _append_card(self, card: Widget) -> Widget:
        self._list().mount(card)
        if self._user_at_bottom:
            self.call_after_refresh(self.scroll_end, animate=False)
        return card

    def card_children(self) -> list[Widget]:
        return list(self._list().children)

    def has_non_empty_cards(self) -> bool:
        return any(not isinstance(c, EmptyStateCard) for c in self._list().children)

    def add_message(self, role: str, content: str) -> UserMessageCard | AgentMessageCard:
        if role == "user":
            card = UserMessageCard(content, classes="card")
        else:
            card = AgentMessageCard(content, classes="card")
            card.start_streaming()
        return self._append_card(card)

    def add_system_message(self, content: str, level: str = "info") -> SystemCard:
        card = SystemCard(content, level=level, classes="card")
        return self._append_card(card)

    def add_tool_call(
        self,
        tool_name: str,
        arguments: dict | None = None,
        status: str = "pending",
        duration_ms: int | None = None,
    ) -> ToolCallCard:
        card = ToolCallCard(tool_name, arguments, status, duration_ms, classes="card")
        return self._append_card(card)

    def add_tool_result(
        self,
        tool_name: str,
        arguments: dict | None = None,
        result: str = "",
        is_error: bool = False,
    ) -> ToolResultCard:
        card = ToolResultCard(tool_name, arguments, result, is_error, classes="card tool-action")
        if len(result.splitlines()) > 18:
            card.collapsed = True
        return self._append_card(card)

    def add_action_card(
        self,
        tool_name: str,
        arguments: dict | None = None,
        result: str = "",
        is_error: bool = False,
        tool_call_id: str = "",
    ) -> ActionCard:
        """Add a compact ActionCard (merged tool_call + tool_result)."""
        card = ActionCard(tool_name, arguments, tool_call_id=tool_call_id, classes="card tool-action")
        card.complete(result, is_error=is_error)
        if tool_call_id:
            self._action_cards[tool_call_id] = card
        return self._append_card(card)

    def add_diff(self, diff_text: str, file_path: str = "") -> DiffCard:
        card = DiffCard(diff_text, file_path, classes="card")
        return self._append_card(card)

    def add_error(self, error_message: str, details: str = "") -> ErrorCard:
        card = ErrorCard(error_message, details, classes="card")
        return self._append_card(card)

    def add_plan(self, content: str) -> PlanCard:
        card = PlanCard("PLAN", content, classes="card")
        return self._append_card(card)

    def add_verify(
        self,
        passed: bool,
        summary_text: str,
        errors: list[str] | None = None,
        full_output: str = "",
    ) -> VerifyCard:
        """Add a verification result card."""
        card = VerifyCard(passed, summary_text, errors=errors, full_output=full_output, classes="card")
        return self._append_card(card)

    def add_decision(
        self,
        tool_name: str,
        arguments: dict | None = None,
        outcome: str = "pending",
    ) -> DecisionCard:
        """Add a decision card for approval tracking."""
        card = DecisionCard(tool_name, arguments, outcome=outcome, classes="card")
        return self._append_card(card)

    def show_empty_state(self) -> None:
        if not any(isinstance(c, EmptyStateCard) for c in self._list().children):
            card = EmptyStateCard(classes="card")
            self._append_card(card)

    def remove_empty_state(self) -> None:
        for child in list(self._list().children):
            if isinstance(child, EmptyStateCard):
                child.remove()

    def clear_cards(self) -> None:
        for child in list(self._list().children):
            if child.id != "transcript-top":
                child.remove()
        self._action_cards.clear()

    def on_scroll(self) -> None:
        scroll_y = self.scroll_y
        max_scroll_y = self.max_scroll_y
        self._user_at_bottom = scroll_y >= max_scroll_y - 1


class CodeOutputPane(Container):
    """Collapsible code output pane (starts collapsed)."""

    can_focus = True
    _collapsed = reactive(True)

    def compose(self) -> ComposeResult:
        with ScrollableContainer(id="code-output-scroll"):
            yield SectionHeader("CODE OUTPUT")
            yield Static(id="code-output-content")

    def toggle(self) -> None:
        self._collapsed = not self._collapsed
        if self._collapsed:
            self.remove_class("expanded")
            self.display = False
        else:
            self.add_class("expanded")
            self.display = True
        self.refresh(layout=True)

    def show_code(self, code: str, language: str = "text") -> None:
        try:
            widget = self.query_one("#code-output-content", Static)
        except Exception:
            widget = self.query_one("#code-output-scroll", Static)
        widget.update(Syntax(code, language, theme="code_neon", word_wrap=True))
        if self._collapsed:
            self.toggle()

    def show_diff(self, diff_text: str) -> None:
        try:
            widget = self.query_one("#code-output-content", Static)
        except Exception:
            widget = self.query_one("#code-output-scroll", Static)
        widget.update(Syntax(diff_text, "diff", theme="code_neon", word_wrap=True))
        if self._collapsed:
            self.toggle()


class CenterPane(Vertical):
    """Center pane containing context widget, activity bar, transcript, and code output."""

    def on_click(self, event) -> None:
        target = getattr(event, "widget", None)
        if target == self:
            event.stop()

    def on_mouse_down(self, event) -> None:
        target = getattr(event, "widget", None)
        if target == self:
            event.stop()

    def compose(self) -> ComposeResult:
        yield ContextWidget(id="context-widget")
        yield PinnedActivityBar(id="pinned-activity")
        yield TranscriptPane(id="transcript")
        yield CodeOutputPane(id="code-output")


class DiffDrawer(Container):
    """Overlay drawer for viewing diffs. Dock right, focused on code changes."""

    can_focus = True
    _visible = reactive(False)

    BINDINGS = [
        Binding("escape", "close_drawer", "Close", priority=True),
        Binding("ctrl+d", "close_drawer", "Close", priority=True),
    ]

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._visible = False
        self._diff_entries: list[dict] = []  # {path, diff_text, change_type}

    def compose(self) -> ComposeResult:
        with ScrollableContainer(id="diff-drawer-scroll"):
            yield Static("DIFF VIEWER", id="diff-drawer-title", classes="section-header")
            yield Static("", id="diff-summary")
            yield Static("No diffs yet. File changes will appear here.", id="diff-content")

    def toggle(self) -> None:
        self._visible = not self._visible
        self._update_display()
        if self._visible:
            self.focus()
        self.refresh(layout=True)

    def show(self) -> None:
        self._visible = True
        self._update_display()
        self.focus()
        self.refresh(layout=True)

    def hide(self) -> None:
        self._visible = False
        self._update_display()
        self.refresh(layout=True)

    def _update_display(self) -> None:
        if not self._visible:
            self.display = False
            self.remove_class("visible")
            self.can_focus = False
            if self.app and hasattr(self.app, "screen"):
                self.app.screen.remove_class("diff-drawer-open")
            return
        self.display = True
        self.add_class("visible")
        self.can_focus = True
        if self.app and hasattr(self.app, "screen"):
            self.app.screen.add_class("diff-drawer-open")

    def show_diffs(self, entries: list[dict]) -> None:
        """Show multiple diff entries. Each: {path, diff_text, change_type}."""
        self._diff_entries = entries
        self._render_diffs()

    def show_single_diff(self, text: str, path: str = "") -> None:
        """Show a single diff."""
        self._diff_entries = [{"path": path, "diff_text": text, "change_type": "modify"}]
        self._render_diffs()

    def _render_diffs(self) -> None:
        try:
            summary_widget = self.query_one("#diff-summary", Static)
            content_widget = self.query_one("#diff-content", Static)
        except Exception:
            return

        if not self._diff_entries:
            summary_widget.update("")
            content_widget.update("No diffs yet.")
            return

        # Summary: file list with change types
        summary_lines = []
        for entry in self._diff_entries[:6]:
            change_icon = {"add": "+", "modify": "~", "delete": "-"}.get(entry.get("change_type", "modify"), "~")
            path = entry.get("path", "unknown")
            summary_lines.append(f"  [{change_icon}] {path}")

        summary_text = Text()
        summary_text.append(f"{len(self._diff_entries)} file(s) changed:\n", style=COLORS["text_muted"])
        for line in summary_lines:
            summary_text.append(line + "\n", style=COLORS["text"])
        summary_widget.update(summary_text)

        # Full diff content
        all_diffs = "\n\n".join(e.get("diff_text", "") for e in self._diff_entries if e.get("diff_text"))
        if all_diffs:
            content_widget.update(Syntax(all_diffs, "diff", theme="code_neon", word_wrap=True))
        else:
            content_widget.update("No diff content.")

    def action_close_drawer(self) -> None:
        self.hide()


class LogsDrawer(Container):
    """Overlay drawer for viewing logs and verify results. Dock right."""

    can_focus = True
    _visible = reactive(False)

    BINDINGS = [
        Binding("escape", "close_drawer", "Close", priority=True),
        Binding("ctrl+l", "close_drawer", "Close", priority=True),
    ]

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._visible = False
        self._log_lines: list[tuple[str, str]] = []  # (text, level)
        self._pinned_verify: str = ""

    def compose(self) -> ComposeResult:
        with ScrollableContainer(id="logs-drawer-scroll"):
            yield Static("LOGS", id="logs-drawer-title", classes="section-header")
            yield Input(placeholder="Filter logs...", id="logs-filter")
            yield Static("", id="logs-errors")
            yield Static("", id="logs-warnings")
            yield Static("No logs yet. Tool execution logs will appear here.", id="logs-content")
            yield Static("", id="logs-verify-pinned")

    def toggle(self) -> None:
        self._visible = not self._visible
        self._update_display()
        if self._visible:
            self.focus()
        self.refresh(layout=True)

    def show(self) -> None:
        self._visible = True
        self._update_display()
        self.focus()
        self.refresh(layout=True)

    def hide(self) -> None:
        self._visible = False
        self._update_display()
        self.refresh(layout=True)

    def _update_display(self) -> None:
        if not self._visible:
            self.display = False
            self.remove_class("visible")
            self.can_focus = False
            if self.app and hasattr(self.app, "screen"):
                self.app.screen.remove_class("logs-drawer-open")
            return
        self.display = True
        self.add_class("visible")
        self.can_focus = True
        if self.app and hasattr(self.app, "screen"):
            self.app.screen.add_class("logs-drawer-open")

    def append_log(self, text: str, level: str = "info") -> None:
        """Append a log line."""
        self._log_lines.append((text, level))
        self._render_logs()

    def pin_verify(self, result: str, passed: bool) -> None:
        """Pin a verify result at the bottom."""
        self._pinned_verify = result
        try:
            verify_widget = self.query_one("#logs-verify-pinned", Static)
            color = COLORS["success"] if passed else COLORS["danger"]
            verify_widget.update(Text(f"\n--- VERIFY ---\n{result}", style=color))
        except Exception:
            pass

    def filter(self, query: str) -> None:
        """Filter displayed logs."""
        self._render_logs(query)

    def _render_logs(self, filter_query: str = "") -> None:
        try:
            errors_widget = self.query_one("#logs-errors", Static)
            warnings_widget = self.query_one("#logs-warnings", Static)
            content_widget = self.query_one("#logs-content", Static)
        except Exception:
            return

        filtered = self._log_lines
        if filter_query:
            filtered = [(t, lv) for t, lv in filtered if filter_query.lower() in t.lower()]

        errors = [(t, lv) for t, lv in filtered if lv == "error"]
        warnings = [(t, lv) for t, lv in filtered if lv == "warning"]
        infos = [(t, lv) for t, lv in filtered if lv not in ("error", "warning")]

        if errors:
            err_text = Text()
            err_text.append("ERRORS:\n", style=f"bold {COLORS['danger']}")
            for t, _ in errors[-20:]:
                err_text.append(f"  {t}\n", style=COLORS["danger"])
            errors_widget.update(err_text)
        else:
            errors_widget.update("")

        if warnings:
            warn_text = Text()
            warn_text.append("WARNINGS:\n", style=f"bold {COLORS['accent_orange']}")
            for t, _ in warnings[-20:]:
                warn_text.append(f"  {t}\n", style=COLORS["accent_orange"])
            warnings_widget.update(warn_text)
        else:
            warnings_widget.update("")

        if infos:
            log_text = Text()
            for t, _ in infos[-50:]:
                log_text.append(f"{t}\n", style=COLORS["text_muted"])
            content_widget.update(log_text)
        elif not errors and not warnings:
            content_widget.update("No logs yet.")
        else:
            content_widget.update("")

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "logs-filter":
            self.filter(event.value)

    def action_close_drawer(self) -> None:
        self.hide()


# Legacy alias for backward compatibility
InspectorDrawer = DiffDrawer


class ComposerBar(Container):
    """Bottom composer bar with contextual hint strip."""

    _hint_text = "Esc interrupt  Ctrl+P commands  Ctrl+D diff  Ctrl+L logs  Ctrl+X context"

    def compose(self) -> ComposeResult:
        with Vertical(id="composer-stack"):
            yield Static(self._hint_text, id="hint-strip", classes="hint")
            yield Input(placeholder="Type a message...", id="composer-input")

    def set_hint(self, text: str) -> None:
        """Update the hint strip text (contextual hints)."""
        try:
            hint = self.query_one("#hint-strip", Static)
            hint.update(text)
        except Exception:
            pass

    def on_input_changed(self, event: Input.Changed) -> None:
        hint = self.query_one("#hint-strip", Static)
        if event.value:
            hint.update("")
        else:
            hint.update(self._hint_text)

    def on_focus(self, event) -> None:
        hint = self.query_one("#hint-strip", Static)
        hint.update("")

    def on_blur(self, event) -> None:
        try:
            input_widget = self.query_one("#composer-input", Input)
            hint = self.query_one("#hint-strip", Static)
            if not input_widget.value:
                hint.update(self._hint_text)
        except Exception:
            pass
