# code_cli/ui/cards.py

from __future__ import annotations

import json
import re
from datetime import datetime

from rich.console import RenderableType
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text
from textual import events
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from .theme import BADGE_COLORS, COLORS, HUD, get_icon


class CodeBlockWidget(Widget):
    """Syntax-highlighted code block with copy affordance."""

    can_focus = True

    BINDINGS = [
        Binding("c", "copy_code", "Copy"),
    ]

    def __init__(self, code: str, language: str = "text", **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.code = code
        self.language = language

    def render(self) -> RenderableType:
        header = Text()
        header.append(f" {self.language} ", style=f"on {COLORS['panel_raised']} {COLORS['text']}")
        header.append("  ", style=COLORS["text_muted"])
        header.append("[c]", style=f"bold {COLORS['accent_cyan']}")
        header.append("opy", style=COLORS["text_muted"])

        return Panel(
            Syntax(self.code, self.language, theme="monokai", word_wrap=True, background_color=COLORS["panel"]),
            title=header,
            title_align="left",
            border_style=COLORS["border"],
            box=HUD,
            padding=(0, 1),
            style=f"on {COLORS['panel']}",
        )

    def action_copy_code(self) -> None:
        """Copy code to clipboard."""
        import platform
        import subprocess

        try:
            if platform.system() == "Darwin":
                subprocess.run(["pbcopy"], input=self.code.encode(), check=True)
            else:
                subprocess.run(["xclip", "-selection", "clipboard"], input=self.code.encode(), check=True)
            self.app.notify("Copied to clipboard", severity="information")
        except Exception:
            self.app.notify("Copy failed - clipboard unavailable", severity="warning")


class BaseCard(Widget):
    """Base card with badge-based compact rendering.

    Cards render as a single-line badge summary when collapsed:
        [BADGE] summary [HH:MM] [expand_icon]
    And show full body content when expanded.
    """

    can_focus = True
    content = reactive("")
    collapsed = reactive(True)

    BINDINGS = [
        Binding("y", "copy_content", "Copy"),
    ]

    def __init__(self, title: str, content: str, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.title = title
        self.content = content
        self.timestamp = datetime.now()

    @property
    def badge(self) -> str:
        return self.title

    @property
    def badge_color(self) -> str:
        return BADGE_COLORS.get("system", COLORS["text_muted"])

    @property
    def summary(self) -> str:
        first_line = self.content.split("\n", 1)[0] if self.content else ""
        return first_line[:80]

    def _truncate(self, text: str, limit: int = 14) -> str:
        lines = text.splitlines()
        if len(lines) <= limit:
            return text
        return "\n".join(lines[:limit]) + "\n..."

    def _render_badge_line(self) -> Text:
        """Render the compact one-liner: [BADGE] summary [HH:MM] [icon]"""
        time_str = self.timestamp.strftime("%H:%M")
        line = Text()
        line.append(f" {self.badge} ", style=f"on {self.badge_color} {COLORS['bg']}")
        line.append(" ", style=COLORS["text_muted"])
        line.append(self.summary, style=COLORS["text"])
        line.append(f"  {time_str} ", style=COLORS["text_muted"])
        if self.collapsed:
            line.append(f" {get_icon('expand')}", style=COLORS["text_muted"])
        else:
            line.append(f" {get_icon('collapse')}", style=COLORS["text_muted"])
        return line

    def toggle_collapse(self) -> None:
        self.collapsed = not self.collapsed
        self.refresh(layout=True)

    def _update_status_class(self, status: str) -> None:
        self.remove_class("streaming", "error", "warning", "success")
        if status in ("streaming", "error", "warning", "success"):
            self.add_class(status)

    def action_copy_content(self) -> None:
        """Copy card content to clipboard."""
        import platform
        import subprocess

        try:
            text = self.content
            if platform.system() == "Darwin":
                subprocess.run(["pbcopy"], input=text.encode(), check=True)
            else:
                subprocess.run(["xclip", "-selection", "clipboard"], input=text.encode(), check=True)
            self.app.notify("Copied to clipboard", severity="information")
        except Exception:
            self.app.notify("Copy failed - clipboard unavailable", severity="warning")

    def on_click(self, event: events.Click) -> None:
        from .widgets import CardSelected

        self.post_message(CardSelected(self))


class UserMessageCard(BaseCard):
    """Card for user messages. Collapsed if >3 lines."""

    def __init__(self, content: str, **kwargs: object) -> None:
        super().__init__("USER", content, **kwargs)
        self.role = "user"
        self.collapsed = len(content.splitlines()) > 3

    @property
    def badge(self) -> str:
        return get_icon("badge_user") + " USER"

    @property
    def badge_color(self) -> str:
        return BADGE_COLORS["user"]

    @property
    def summary(self) -> str:
        first_line = self.content.split("\n", 1)[0] if self.content else ""
        return first_line[:80]

    def render(self) -> RenderableType:
        if self.collapsed:
            return self._render_badge_line()
        time_str = self.timestamp.strftime("%H:%M")
        header = f"{get_icon('badge_user')} USER \u00b7 {time_str}"
        return Panel(
            Text(self.content, style=COLORS["text"]),
            title=header,
            title_align="left",
            border_style=COLORS["border"],
            box=HUD,
            padding=(0, 0),
            style=f"on {COLORS['panel']}",
        )


class AgentMessageCard(Container):
    """Card for agent messages with streaming support. Collapsed by default - shows first 2 lines."""

    can_focus = True
    collapsed = reactive(False)
    content = reactive("")
    _streaming = reactive(False)
    _status = reactive("done")
    _stream_buffer = ""
    _last_render_time = 0.0
    _render_throttle_ms = 33
    _content_container = None

    BINDINGS = [
        Binding("y", "copy_content", "Copy"),
    ]

    def __init__(self, content: str = "", **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.role = "assistant"
        self.content = content
        self._streaming = False
        self._status = "done"
        self._stream_buffer = ""
        self._last_render_time = 0.0
        self.timestamp = datetime.now()
        self.title = "AGENT"
        self._content_container = None

    @property
    def badge(self) -> str:
        return get_icon("badge_think") + " THINK"

    @property
    def badge_color(self) -> str:
        if self._status == "streaming":
            return BADGE_COLORS["think"]
        return BADGE_COLORS["think_done"]

    @property
    def summary(self) -> str:
        first_line = self.content.split("\n", 1)[0] if self.content else "Thinking..."
        return first_line[:80]

    def compose(self):
        yield Static(self._build_header(), classes="agent-card-header", id="agent-header")
        content_container = Vertical(classes="agent-card-content", id="agent-content")
        yield content_container

    def on_mount(self) -> None:
        self._content_container = self.query_one("#agent-content", Vertical)
        self._rebuild_content()

    def _rebuild_content(self) -> None:
        if not self._content_container:
            return
        self._content_container.remove_children()

        if self.collapsed:
            # Show only first 2 lines as summary
            lines = self.content.splitlines()[:2]
            preview = "\n".join(lines)
            if len(self.content.splitlines()) > 2:
                preview += "\n..."
            if preview.strip():
                self._content_container.mount(Static(Markdown(preview), classes="agent-card-text"))
            elif self._status == "streaming":
                self._content_container.mount(Static(Markdown("*Thinking...*"), classes="agent-card-text"))
            return

        body_content = self.content
        parts = self._parse_content_with_code_blocks(body_content)

        if not parts or (len(parts) == 1 and parts[0][0] == "text" and not parts[0][1]):
            if self._status == "streaming":
                self._content_container.mount(Static(Markdown("*Thinking...*"), classes="agent-card-text"))
            else:
                self._content_container.mount(Static("", classes="agent-card-text"))
        else:
            children = []
            for part in parts:
                if part[0] == "text":
                    if part[1]:
                        children.append(Static(Markdown(part[1]), classes="agent-card-text"))
                elif part[0] == "code":
                    lang, code = part[1], part[2]
                    children.append(CodeBlockWidget(code, lang, classes="agent-card-code"))
            if children:
                self._content_container.mount(*children)

    def _build_header(self) -> Text:
        time_str = self.timestamp.strftime("%H:%M")
        if self._status == "streaming":
            status_icon = get_icon("status_thinking")
            status_text = f"{status_icon} STREAMING"
            status_color = BADGE_COLORS["think"]
        elif self._status == "error":
            status_icon = get_icon("badge_error")
            status_text = f"{status_icon} ERROR"
            status_color = BADGE_COLORS["error"]
        else:
            status_icon = get_icon("done")
            status_text = f"{status_icon} DONE"
            status_color = BADGE_COLORS["think_done"]

        header = Text()
        header.append(f"{get_icon('badge_think')} THINK \u00b7 {status_text} \u00b7 {time_str}", style=status_color)
        return header

    def _truncate(self, text: str, limit: int = 14) -> str:
        lines = text.splitlines()
        if len(lines) <= limit:
            return text
        return "\n".join(lines[:limit]) + "\n..."

    def append(self, text: str) -> None:
        self._stream_buffer += text
        self._throttled_refresh()

    def _throttled_refresh(self) -> None:
        import time

        now = time.time()
        elapsed_ms = (now - self._last_render_time) * 1000
        if elapsed_ms >= self._render_throttle_ms:
            self.content += self._stream_buffer
            self._stream_buffer = ""
            self._last_render_time = now
            self._rebuild_content()

    def start_streaming(self) -> None:
        self._streaming = True
        self._status = "streaming"
        self.collapsed = False  # Expand during streaming
        self._update_status_class("streaming")
        self._update_header()

    def stop_streaming(self) -> None:
        if self._stream_buffer:
            self.content += self._stream_buffer
            self._stream_buffer = ""
        self._streaming = False
        self._status = "done"
        self.collapsed = True  # Collapse when done
        self._update_status_class("done")
        self._rebuild_content()

    def mark_error(self) -> None:
        if self._stream_buffer:
            self.content += self._stream_buffer
            self._stream_buffer = ""
        self._streaming = False
        self._status = "error"
        self.collapsed = False  # Keep errors expanded
        self._update_status_class("error")
        self._rebuild_content()

    def _update_status_class(self, status: str) -> None:
        self.remove_class("streaming", "error", "warning", "success")
        if status in ("streaming", "error", "warning", "success"):
            self.add_class(status)

    def _update_header(self) -> None:
        try:
            header_widget = self.query_one(".agent-card-header", Static)
            if header_widget:
                header_widget.update(self._build_header())
        except Exception:
            pass

    def toggle_collapse(self) -> None:
        self.collapsed = not self.collapsed
        self._rebuild_content()

    def _parse_content_with_code_blocks(self, content: str) -> list:
        parts = []
        code_pattern = r"```(\w*)\n(.*?)```"
        last_end = 0
        for match in re.finditer(code_pattern, content, re.DOTALL):
            if match.start() > last_end:
                text_before = content[last_end : match.start()].strip()
                if text_before:
                    parts.append(("text", text_before))
            language = match.group(1) or "text"
            code = match.group(2).strip()
            parts.append(("code", language, code))
            last_end = match.end()
        if last_end < len(content):
            text_after = content[last_end:].strip()
            if text_after:
                parts.append(("text", text_after))
        return parts if parts else [("text", content)]

    def action_copy_content(self) -> None:
        import platform
        import subprocess

        try:
            text = self.content
            if platform.system() == "Darwin":
                subprocess.run(["pbcopy"], input=text.encode(), check=True)
            else:
                subprocess.run(["xclip", "-selection", "clipboard"], input=text.encode(), check=True)
            self.app.notify("Copied to clipboard", severity="information")
        except Exception:
            self.app.notify("Copy failed - clipboard unavailable", severity="warning")

    def on_click(self, event: events.Click) -> None:
        from .widgets import CardSelected

        self.post_message(CardSelected(self))


class ActionCard(BaseCard):
    """Compact card merging tool call + result. One-liner: tool_name(args) -> OK/ERR duration."""

    def __init__(
        self,
        tool_name: str,
        arguments: dict | None = None,
        tool_call_id: str = "",
        **kwargs: object,
    ) -> None:
        super().__init__("ACTION", "", **kwargs)
        self.tool_name = tool_name
        self.arguments = arguments or {}
        self.tool_call_id = tool_call_id
        self.status = "running"  # running, ok, error
        self.duration_ms: int | None = None
        self.result_content = ""
        self.collapsed = True

    @property
    def badge(self) -> str:
        return get_icon("badge_action") + " ACTION"

    @property
    def badge_color(self) -> str:
        if self.status == "running":
            return BADGE_COLORS["action"]
        elif self.status == "error":
            return BADGE_COLORS["action_error"]
        return BADGE_COLORS["action_ok"]

    @property
    def summary(self) -> str:
        # Compact one-liner: tool_name(key_arg) -> OK (info) duration
        arg_preview = ""
        if self.arguments:
            first_key = next(iter(self.arguments), "")
            first_val = self.arguments.get(first_key, "")
            if isinstance(first_val, str) and len(first_val) > 40:
                first_val = first_val[:37] + "..."
            arg_preview = f'("{first_val}")' if first_val else ""

        status_text = self.status.upper()
        result_info = ""
        if self.result_content:
            lines = self.result_content.splitlines()
            result_info = f" ({len(lines)} lines)" if len(lines) > 1 else ""

        duration_text = f" {self.duration_ms}ms" if self.duration_ms else ""
        return f"{self.tool_name}{arg_preview} \u2192 {status_text}{result_info}{duration_text}"

    def complete(self, content: str, is_error: bool = False, duration_ms: int | None = None) -> None:
        """Mark action as completed with result."""
        self.result_content = content
        self.content = content
        self.status = "error" if is_error else "ok"
        self.duration_ms = duration_ms
        if is_error:
            self._update_status_class("error")
        else:
            self._update_status_class("success")
        self.refresh(layout=True)

    def render(self) -> RenderableType:
        if self.collapsed:
            return self._render_badge_line()

        time_str = self.timestamp.strftime("%H:%M")
        status_color = self.badge_color
        duration_text = f" \u00b7 {self.duration_ms}ms" if self.duration_ms else ""
        header = f"{get_icon('badge_action')} {self.tool_name.upper()} \u00b7 {self.status.upper()}{duration_text} \u00b7 {time_str}"

        body_parts = []
        if self.arguments:
            body_parts.append(f"ARGS:\n{json.dumps(self.arguments, indent=2)}")
        if self.result_content:
            body_parts.append(f"RESULT:\n{self.result_content}")
        body = "\n\n".join(body_parts) if body_parts else "No output"

        if self.status == "error":
            renderable = Text(body, style=COLORS["danger"])
        else:
            renderable = Syntax(body, "text", theme="code_neon", word_wrap=True)

        return Panel(
            renderable,
            title=header,
            title_align="left",
            border_style=status_color,
            box=HUD,
            padding=(0, 0),
            style=f"on {COLORS['panel']}",
        )


class ToolCallCard(BaseCard):
    """Card for tool calls with status and duration (legacy, kept for compatibility)."""

    def __init__(
        self,
        tool_name: str,
        arguments: dict | None = None,
        status: str = "pending",
        duration_ms: int | None = None,
        **kwargs: object,
    ) -> None:
        title = f"TOOL {tool_name.upper()}"
        super().__init__(title, "", **kwargs)
        self.tool_name = tool_name
        self.arguments = arguments or {}
        self.status = status
        self.duration_ms = duration_ms

    @property
    def badge(self) -> str:
        return get_icon("badge_action") + " ACTION"

    @property
    def badge_color(self) -> str:
        return BADGE_COLORS.get("action", COLORS["accent_orange"])

    @property
    def summary(self) -> str:
        return f"{self.tool_name} \u00b7 {self.status.upper()}"

    def render(self) -> RenderableType:
        if self.collapsed:
            return self._render_badge_line()
        time_str = self.timestamp.strftime("%H:%M")
        status_colors = {
            "pending": COLORS["accent_orange"],
            "approved": COLORS["border"],
            "running": COLORS["accent_cyan"],
            "ok": COLORS["success"],
            "error": COLORS["danger"],
        }
        status_color = status_colors.get(self.status, COLORS["text_muted"])
        duration_text = f" \u00b7 {self.duration_ms}ms" if self.duration_ms else ""
        header = f"{self.tool_name.upper()} \u00b7 {self.status.upper()}{duration_text} \u00b7 {time_str}"
        args_json = json.dumps(self.arguments, indent=2)
        body_text = f"ARGS:\n{args_json}"
        body = self._truncate(body_text, limit=18)
        return Panel(
            Syntax(body, "json", theme="code_neon", word_wrap=True),
            title=header,
            title_align="left",
            border_style=status_color,
            box=HUD,
            padding=(0, 0),
            style=f"on {COLORS['panel']}",
        )


class ToolResultCard(BaseCard):
    """Card for tool execution results (legacy, kept for compatibility)."""

    def __init__(
        self,
        tool_name: str,
        arguments: dict | None = None,
        result: str = "",
        is_error: bool = False,
        **kwargs: object,
    ) -> None:
        title = f"RESULT {tool_name.upper()}"
        super().__init__(title, result, **kwargs)
        self.tool_name = tool_name
        self.arguments = arguments or {}
        self.is_error = is_error

    @property
    def badge(self) -> str:
        return get_icon("badge_action") + " ACTION"

    @property
    def badge_color(self) -> str:
        return BADGE_COLORS["action_error"] if self.is_error else BADGE_COLORS["action_ok"]

    @property
    def summary(self) -> str:
        status = "ERROR" if self.is_error else "OK"
        lines = len(self.content.splitlines())
        return f"{self.tool_name} \u2192 {status} ({lines} lines)"

    def render(self) -> RenderableType:
        if self.collapsed:
            return self._render_badge_line()
        time_str = self.timestamp.strftime("%H:%M")
        status = "ERROR" if self.is_error else "OK"
        status_color = COLORS["danger"] if self.is_error else COLORS["success"]
        header = f"{get_icon('badge_action')} {self.tool_name.upper()} \u00b7 {status} \u00b7 {time_str}"
        body = self._truncate(self.content, limit=18)
        if self.is_error:
            renderable = Text(body, style=COLORS["danger"])
        else:
            renderable = Syntax(body, "text", theme="code_neon", word_wrap=True)
        return Panel(
            renderable,
            title=header,
            title_align="left",
            border_style=status_color,
            box=HUD,
            padding=(0, 0),
            style=f"on {COLORS['panel']}",
        )


class DiffCard(BaseCard):
    """Card for showing diffs. Collapsed by default showing file summary."""

    def __init__(self, diff_text: str, file_path: str = "", **kwargs: object) -> None:
        super().__init__("DIFF", diff_text, **kwargs)
        self.file_path = file_path
        self._full_diff = diff_text
        self.collapsed = True

    @property
    def badge(self) -> str:
        return get_icon("badge_diff") + " DIFF"

    @property
    def badge_color(self) -> str:
        return BADGE_COLORS["diff"]

    @property
    def summary(self) -> str:
        lines = self._full_diff.splitlines()
        adds = sum(1 for ln in lines if ln.startswith("+") and not ln.startswith("+++"))
        dels = sum(1 for ln in lines if ln.startswith("-") and not ln.startswith("---"))
        path = self.file_path or "file"
        return f"{path} (+{adds} -{dels})"

    def render(self) -> RenderableType:
        if self.collapsed:
            return self._render_badge_line()
        time_str = self.timestamp.strftime("%H:%M")
        diff_icon = get_icon("badge_diff")
        header = f"{diff_icon} DIFF"
        if self.file_path:
            header += f" \u00b7 {self.file_path}"
        header += f" \u00b7 {time_str}"
        return Panel(
            Syntax(self._full_diff, "diff", theme="code_neon", word_wrap=True),
            title=header,
            title_align="left",
            border_style=COLORS["border"],
            box=HUD,
            padding=(0, 0),
            style=f"on {COLORS['panel']}",
        )


class ErrorCard(BaseCard):
    """Card for error messages. Always expanded."""

    def __init__(self, error_message: str, details: str = "", **kwargs: object) -> None:
        super().__init__("ERROR", error_message, **kwargs)
        self.details = details
        self.collapsed = False  # Errors always visible

    @property
    def badge(self) -> str:
        return get_icon("badge_error") + " ERROR"

    @property
    def badge_color(self) -> str:
        return BADGE_COLORS["error"]

    @property
    def summary(self) -> str:
        return self.content[:80]

    def render(self) -> RenderableType:
        time_str = self.timestamp.strftime("%H:%M")
        error_icon = get_icon("badge_error")
        header = f"{error_icon} ERROR \u00b7 {time_str}"
        body = self.content
        if self.details and not self.collapsed:
            body += f"\n\nDETAILS:\n{self.details}"
        elif self.collapsed:
            body = self._truncate(body, limit=10)
        return Panel(
            Text(body, style=COLORS["danger"]),
            title=header,
            title_align="left",
            border_style=COLORS["danger"],
            box=HUD,
            padding=(0, 0),
            style=f"on {COLORS['panel']}",
        )


class SystemCard(BaseCard):
    """Card for system/runtime messages."""

    def __init__(self, content: str, level: str = "info", **kwargs: object) -> None:
        super().__init__("SYSTEM", content, **kwargs)
        self.level = level
        self.collapsed = True

    @property
    def badge(self) -> str:
        return get_icon("badge_system") + " SYSTEM"

    @property
    def badge_color(self) -> str:
        if self.level == "warning":
            return BADGE_COLORS.get("decision", COLORS["accent_orange"])
        elif self.level == "error":
            return BADGE_COLORS["error"]
        return BADGE_COLORS["system"]

    @property
    def summary(self) -> str:
        return self.content.split("\n", 1)[0][:80]

    def render(self) -> RenderableType:
        if self.collapsed:
            return self._render_badge_line()
        time_str = self.timestamp.strftime("%H:%M")
        if self.level == "warning":
            level_color = COLORS["accent_orange"]
            level_text = "WARNING"
        elif self.level == "error":
            level_color = COLORS["danger"]
            level_text = "ERROR"
        else:
            level_color = COLORS["text_muted"]
            level_text = "INFO"
        header = f"{get_icon('badge_system')} SYSTEM \u00b7 {level_text} \u00b7 {time_str}"
        return Panel(
            Text(self.content, style=COLORS["text"]),
            title=header,
            title_align="left",
            border_style=level_color,
            box=HUD,
            padding=(0, 0),
            style=f"on {COLORS['panel']}",
        )


class PlanCard(BaseCard):
    """Card for showing plans. Collapsed showing step count."""

    def __init__(self, title: str = "PLAN", content: str = "", **kwargs: object) -> None:
        super().__init__(title, content, **kwargs)
        self.collapsed = True

    @property
    def badge(self) -> str:
        return get_icon("badge_plan") + " PLAN"

    @property
    def badge_color(self) -> str:
        return BADGE_COLORS["plan"]

    @property
    def summary(self) -> str:
        # Count checklist items
        checked = self.content.count("- [x]") + self.content.count("- [X]")
        unchecked = self.content.count("- [ ]")
        total = checked + unchecked
        if total > 0:
            return f"Plan: {checked}/{total} steps done"
        # Count any list items
        steps = sum(1 for line in self.content.splitlines() if line.strip().startswith(("- ", "* ", "1.")))
        if steps > 0:
            return f"Plan: {steps} steps"
        return "Plan"

    def render(self) -> RenderableType:
        if self.collapsed:
            return self._render_badge_line()
        time_str = self.timestamp.strftime("%H:%M")
        header = f"{get_icon('badge_plan')} PLAN \u00b7 {time_str}"
        return Panel(
            Markdown(self.content),
            title=header,
            title_align="left",
            border_style=BADGE_COLORS["plan"],
            box=HUD,
            padding=(0, 0),
            style=f"on {COLORS['panel']}",
        )


class VerifyCard(BaseCard):
    """Card for test/verify results. Shows pass/fail summary."""

    def __init__(
        self,
        passed: bool,
        summary_text: str,
        errors: list[str] | None = None,
        full_output: str = "",
        **kwargs: object,
    ) -> None:
        super().__init__("VERIFY", full_output, **kwargs)
        self.passed = passed
        self.summary_text = summary_text
        self.errors = errors or []
        self.full_output = full_output
        self.collapsed = True  # Collapsed by default

    @property
    def badge(self) -> str:
        return get_icon("badge_verify") + " VERIFY"

    @property
    def badge_color(self) -> str:
        return BADGE_COLORS["verify_pass"] if self.passed else BADGE_COLORS["verify_fail"]

    @property
    def summary(self) -> str:
        return self.summary_text

    def render(self) -> RenderableType:
        if self.collapsed:
            return self._render_badge_line()
        time_str = self.timestamp.strftime("%H:%M")
        status = "PASSED" if self.passed else "FAILED"
        status_color = BADGE_COLORS["verify_pass"] if self.passed else BADGE_COLORS["verify_fail"]
        header = f"{get_icon('badge_verify')} VERIFY \u00b7 {status} \u00b7 {time_str}"

        body_parts = []
        if self.errors:
            body_parts.append("ERRORS:\n" + "\n".join(f"  \u2022 {e}" for e in self.errors))
        if self.full_output:
            body_parts.append(f"OUTPUT:\n{self.full_output}")
        body = "\n\n".join(body_parts) if body_parts else self.summary_text

        if not self.passed:
            renderable = Text(body, style=COLORS["danger"])
        else:
            renderable = Text(body, style=COLORS["text"])

        return Panel(
            renderable,
            title=header,
            title_align="left",
            border_style=status_color,
            box=HUD,
            padding=(0, 0),
            style=f"on {COLORS['panel']}",
        )


class DecisionCard(BaseCard):
    """Card for approval decisions. Always expanded when pending."""

    def __init__(
        self,
        tool_name: str,
        arguments: dict | None = None,
        outcome: str = "pending",  # pending, approved, approved_category, denied
        **kwargs: object,
    ) -> None:
        super().__init__("DECISION", "", **kwargs)
        self.tool_name = tool_name
        self.arguments = arguments or {}
        self.outcome = outcome
        self.collapsed = outcome != "pending"  # Expanded when pending

    @property
    def badge(self) -> str:
        return get_icon("badge_decision") + " DECISION"

    @property
    def badge_color(self) -> str:
        if self.outcome == "pending":
            return BADGE_COLORS["decision"]
        elif self.outcome in ("approved", "approved_category"):
            return BADGE_COLORS["decision_approved"]
        return BADGE_COLORS["decision_denied"]

    @property
    def summary(self) -> str:
        outcome_map = {
            "pending": "Pending",
            "approved": "Approved",
            "approved_category": "Approved (category)",
            "denied": "Denied",
        }
        return f"{self.tool_name} \u2192 {outcome_map.get(self.outcome, self.outcome)}"

    def resolve(self, outcome: str) -> None:
        """Resolve the decision with an outcome."""
        self.outcome = outcome
        self.collapsed = True
        self.refresh(layout=True)

    def render(self) -> RenderableType:
        if self.collapsed:
            return self._render_badge_line()
        time_str = self.timestamp.strftime("%H:%M")
        header = f"{get_icon('badge_decision')} DECISION \u00b7 {self.tool_name.upper()} \u00b7 {time_str}"
        args_json = json.dumps(self.arguments, indent=2)
        body = f"Tool: {self.tool_name}\nStatus: {self.outcome.upper()}\n\nARGS:\n{args_json}"
        return Panel(
            Syntax(body, "json", theme="code_neon", word_wrap=True),
            title=header,
            title_align="left",
            border_style=self.badge_color,
            box=HUD,
            padding=(0, 0),
            style=f"on {COLORS['panel']}",
        )


class PendingToolCallCard(ToolCallCard):
    """Card for pending tool calls in SAFE mode (legacy)."""

    def __init__(
        self,
        tool_name: str,
        arguments: dict | None = None,
        on_approve: callable | None = None,
        on_reject: callable | None = None,
        on_approve_all: callable | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(tool_name, arguments, status="pending", **kwargs)
        self.on_approve = on_approve
        self.on_reject = on_reject
        self.on_approve_all = on_approve_all
        self.collapsed = False  # Pending items always expanded

    def render(self) -> RenderableType:
        time_str = self.timestamp.strftime("%H:%M")
        header = f"{get_icon('badge_decision')} {self.tool_name.upper()} \u00b7 PENDING \u00b7 {time_str}"
        args_json = json.dumps(self.arguments, indent=2)
        body_text = f"ARGS:\n{args_json}\n\n[Approve Once] [Approve All Until Idle] [Reject]"
        return Panel(
            Syntax(body_text, "json", theme="code_neon", word_wrap=True),
            title=header,
            title_align="left",
            border_style=BADGE_COLORS["decision"],
            box=HUD,
            padding=(0, 0),
            style=f"on {COLORS['panel']}",
        )


class EmptyStateCard(BaseCard):
    """Card shown when transcript is empty."""

    def __init__(self, **kwargs: object) -> None:
        super().__init__("", "", **kwargs)
        self.collapsed = False
        self.examples = [
            "Add a new feature to handle user authentication",
            "Fix the bug in the login function",
            "Refactor the database connection code",
        ]

    def render(self) -> RenderableType:
        content = Text()
        content.append("Type a request, or press ", style=COLORS["text_muted"])
        content.append("Ctrl+P", style=f"bold {COLORS['accent_cyan']}")
        content.append(" for commands\n\n", style=COLORS["text_muted"])
        content.append("Examples:\n", style=COLORS["text"])
        for i, example in enumerate(self.examples, 1):
            content.append(f"  {i}. ", style=COLORS["text_muted"])
            content.append(example, style=COLORS["text"])
            content.append("\n", style=COLORS["text_muted"])
        return Panel(
            content,
            border_style=COLORS["border"],
            box=HUD,
            padding=(1, 2),
            style=f"on {COLORS['panel']}",
        )
