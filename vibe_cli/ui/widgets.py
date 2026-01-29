from __future__ import annotations

import math
import random
from datetime import datetime
from typing import Optional

import pygments.styles
from rich import box
from rich.align import Align
from rich.console import RenderableType
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Button, Label, Static

from .system_metrics import SystemMetricsProvider
from .theme import COLORS, glitch_text

# Register custom neon theme
pygments.styles.STYLE_MAP["vibe_neon"] = "vibe_cli.ui.theme:VibeNeonStyle"


class StatusBar(Static):
    """Input status indicator"""

    status = reactive("ready")  # ready, typing, processing
    char_count = reactive(0)
    model_name = reactive("phi-4")
    _frame = reactive(0)

    def on_mount(self) -> None:
        self.set_interval(0.3, self._tick)

    def _tick(self) -> None:
        self._frame += 1
        if self.status == "processing":
            self.refresh()

    def render(self) -> RenderableType:
        # Animated spinner for processing
        spinners = ["◐", "◓", "◑", "◒"]
        spinner = spinners[self._frame % len(spinners)]
        model_info = f" [dim]│[/] [dim]Model:[/] [{COLORS['tertiary']}]{self.model_name}[/]"

        if self.status == "processing":
            return Text.from_markup(
                f"[dim][?] Help[/] [dim]│[/] "
                f"[{COLORS['secondary']}]{spinner}[/] [{COLORS['secondary']}]Processing...[/]{model_info}"
            )
        elif self.status == "typing":
            return Text.from_markup(
                f"[dim][?] Help[/] [dim]│[/] "
                f"[{COLORS['tertiary']}]{self.char_count}[/] [dim]chars[/] [dim]│[/] "
                f"[dim][Enter] Send[/]{model_info}"
            )
        else:  # ready
            return Text.from_markup(
                f"[dim][?] Help[/] [dim]│[/] [{COLORS['success']}]●[/] [{COLORS['text']}]Ready[/]{model_info}"
            )


class SystemBanner(Static):
    """Session info header with ASCII icons"""

    # Reactive properties for live data
    tokens_used = reactive(2400)
    tokens_total = reactive(4000)
    latency_ms = reactive(234)
    git_branch = reactive("main")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._session_start = datetime.now()

    def on_mount(self) -> None:
        self.set_interval(1.0, self.refresh)  # Update every second

    def render(self) -> RenderableType:
        time_str = datetime.now().strftime("%H:%M")

        # Session duration
        elapsed = datetime.now() - self._session_start
        minutes = int(elapsed.total_seconds() // 60)
        seconds = int(elapsed.total_seconds() % 60)
        session_str = f"{minutes}m {seconds:02d}s"

        # Token percentage with color coding
        token_pct = int((self.tokens_used / self.tokens_total) * 100)
        if token_pct < 50:
            token_color = COLORS["success"]
        elif token_pct < 80:
            token_color = COLORS["warning"]
        else:
            token_color = COLORS["error"]

        # Latency color coding
        if self.latency_ms < 500:
            lat_color = COLORS["success"]
        elif self.latency_ms < 1000:
            lat_color = COLORS["warning"]
        else:
            lat_color = COLORS["error"]

        # Build header with ASCII icons (no emojis!)
        content = Text.from_markup(
            f"[bold {COLORS['primary']}]VIBE_OS[/] [dim]│[/] "
            f"[{COLORS['text']}]{time_str}[/] [dim]│[/] "
            f"[{COLORS['secondary']}]◷[/] [{COLORS['text']}]{session_str}[/] [dim]│[/] "
            f"[{token_color}]▣[/] [{COLORS['text']}]{self.tokens_used}/{self.tokens_total}[/] "
            f"[dim]([/][{token_color}]{token_pct}%[/][dim])[/] [dim]│[/] "
            f"[{lat_color}]◈[/] [{COLORS['text']}]{self.latency_ms}ms[/] [dim]│[/] "
            f"[{COLORS['tertiary']}]⌥[/] [{COLORS['secondary']}]{self.git_branch}[/]"
        )
        return Panel(Align.center(content), style=f"on {COLORS['bg']}", border_style=COLORS["primary"])


class AICoreAvatar(Widget):
    """The Impossible ASCII Sphere"""

    state = reactive("idle")
    phase = reactive(0.0)
    model = reactive("phi-4")

    def on_mount(self) -> None:
        self.set_interval(0.05, self.tick)  # 20 FPS

    def tick(self) -> None:
        self.phase += 0.1
        self.refresh()

    def render(self) -> RenderableType:
        # Generate a 3D-ish sphere using density characters
        width, height = 16, 8  # Perfect fit for 24-col sidebar
        output_lines = []

        center_x, center_y = width / 2, height / 2

        # State modifiers
        spin_speed = 1.0
        if self.state == "thinking":
            spin_speed = 3.0
        elif self.state == "coding":
            spin_speed = 0.5

        time_offset = self.phase * spin_speed

        for y in range(height):
            line = ""
            for x in range(width):
                # Normalize coords -1 to 1
                nx = (x - center_x) / (width / 2.5)
                ny = (y - center_y) / (height / 2.5)

                # Sphere equation + rotation simulation
                # Z-depth estimation
                dist = math.sqrt(nx * nx + ny * ny)

                if dist > 1.0:
                    char = " "
                    # Random glitch pixels
                    if self.state == "coding" and random.random() < 0.05:
                        char = random.choice([".", ",", "`"])
                else:
                    # 3D rotation effect
                    z = math.sqrt(1.0 - dist * dist)
                    # Simple lighting calculation
                    angle = math.atan2(ny, nx) + time_offset
                    lighting = math.sin(angle * 3) * z

                    # Density mapping
                    if lighting > 0.8:
                        char = "█"
                    elif lighting > 0.5:
                        char = "▓"
                    elif lighting > 0.2:
                        char = "▒"
                    elif lighting > -0.2:
                        char = "░"
                    else:
                        char = "·"

                line += char
            output_lines.append(line)

        # Mood ring color based on state
        ring_color = COLORS["primary"]  # lavender for idle
        ring_style = ""
        if self.state == "thinking":
            ring_color = COLORS["secondary"]  # mint
            ring_style = "bold"
        elif self.state == "coding":
            ring_color = COLORS["tertiary"]  # peach
        elif self.state == "error":
            ring_color = COLORS["error"]  # pink
            ring_style = "bold blink"
        elif self.state == "success":
            ring_color = COLORS["success"]  # sage

        # Animated ring characters
        ring_chars = "░▒▓█▓▒"
        ring_idx = int(self.phase * 2) % len(ring_chars)
        ring_char = ring_chars[ring_idx]

        # Scanline effect overlay
        scanline_idx = int(self.phase * 5) % height
        # Build title with animated ring effect
        model_display = "DevOps Agent"
        if self.state in ("thinking", "coding"):
            title = (
                f"[{ring_style} {ring_color}]{ring_char}[/] {model_display} [{ring_style} {ring_color}]{ring_char}[/]"
            )
        else:
            title = f"[{ring_color}]●[/] {model_display} [{ring_color}]●[/]"

        # Post-process lines for scanlines
        final_lines = []
        for i, line in enumerate(output_lines):
            if i == scanline_idx:
                # Bright scanline
                final_lines.append(f"[bold {COLORS['text_bright']}]{line}[/]")
            elif i % 2 == 0:
                # Dimmed scanline
                final_lines.append(f"[dim]{line}[/]")
            else:
                final_lines.append(line)

        art = "\n".join(final_lines)

        # Glitch flicker
        panel_style = f"on {COLORS['bg']}"
        if self.state == "coding" and random.random() < 0.1:
            panel_style = f"on {COLORS['surface_glow']}"

        return Panel(
            Align.center(Text.from_markup(art, style=f"bold {ring_color}")),
            title=title,
            border_style=f"{ring_style} {ring_color}".strip(),
            style=panel_style,
            box=box.DOUBLE,
        )


class SystemMonitor(Static):
    """Live system telemetry"""

    cpu = reactive(0.0)
    ram = reactive(0.0)
    disk = reactive(0.0)
    net_up_bps = reactive(0.0)
    net_down_bps = reactive(0.0)
    vram_used_mb = reactive(None)
    vram_total_mb = reactive(None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._metrics = SystemMetricsProvider()

    def on_mount(self) -> None:
        self.set_interval(1.0, self._schedule_update)

    def _schedule_update(self) -> None:
        self.run_worker(self._update_metrics(), group="system-monitor")

    async def _update_metrics(self) -> None:
        snapshot = await self._metrics.sample()
        self.cpu = snapshot.cpu / 100.0
        self.ram = snapshot.ram / 100.0
        self.disk = snapshot.disk / 100.0
        self.net_up_bps = snapshot.net_up_bps
        self.net_down_bps = snapshot.net_down_bps
        self.vram_used_mb = snapshot.vram_used_mb
        self.vram_total_mb = snapshot.vram_total_mb
        self.refresh()

    def render(self) -> RenderableType:
        def get_bar(val: float, color: str) -> str:
            width = 12
            filled = int(max(0.0, min(1.0, val)) * width)
            bar = "█" * filled + "░" * (width - filled)
            return f"[{color}]{bar}[/]"

        vram_line = ""
        if self.vram_used_mb is not None and self.vram_total_mb:
            vram_pct = self.vram_used_mb / self.vram_total_mb
            vram_line = (
                f"[dim]VRAM[/] {get_bar(vram_pct, COLORS['tertiary'])} "
                f"[dim]{int(self.vram_used_mb)}/{int(self.vram_total_mb)}MB[/]"
            )

        lines = [
            f"[dim]CPU [/] {get_bar(self.cpu, COLORS['primary'])} [dim]{int(self.cpu * 100)}%[/]",
            f"[dim]RAM [/] {get_bar(self.ram, COLORS['secondary'])} [dim]{int(self.ram * 100)}%[/]",
            f"[dim]DISK[/] {get_bar(self.disk, COLORS['text_bright'])} [dim]{int(self.disk * 100)}%[/]",
            f"[dim]NET [/] [dim]↑{_format_rate(self.net_up_bps)} ↓{_format_rate(self.net_down_bps)}[/]",
        ]
        if vram_line:
            lines.append(vram_line)

        return Panel(
            "\n".join(lines),
            title="TELEMETRY",
            border_style=COLORS["surface_light"],
            style=f"on {COLORS['surface']}",
            box=box.SQUARE,
        )


def _format_rate(bytes_per_sec: float) -> str:
    units = ["B/s", "KB/s", "MB/s", "GB/s"]
    value = max(bytes_per_sec, 0.0)
    unit_idx = 0
    while value >= 1024.0 and unit_idx < len(units) - 1:
        value /= 1024.0
        unit_idx += 1
    return f"{value:.1f}{units[unit_idx]}"


class PowerGauge(Widget):
    """Vertical retro-grade gauge"""

    level = reactive(0.0)
    label = reactive("")

    def render(self) -> RenderableType:
        height = 10
        filled_height = int(self.level * height)

        lines = []
        for i in range(height):
            # Invert Y (draw from bottom up)
            y = (height - 1) - i

            if y < filled_height:
                # Gradient logic: Low=Green, Mid=Yellow, High=Red
                val = y / height
                if val < 0.5:
                    col = COLORS["success"]
                elif val < 0.8:
                    col = COLORS["warning"]
                else:
                    col = COLORS["error"]

                char = "█" + "▓▒░"[i % 3]  # Texture
                lines.append(f"[{col}]{char * 4}[/]")
            else:
                lines.append(f"[dim]{'░' * 4}[/]")

        return Panel(Align.center("\n".join(lines)), title=self.label, border_style=COLORS["surface_light"])


class HyperChatBubble(Widget):
    """Floating glass interaction bubble with optional typewriter effect"""

    content = reactive("")
    displayed_content = reactive("")
    _typing_task = None

    def __init__(self, role: str, content: str, timestamp: Optional[datetime] = None, typewriter: bool = False):
        super().__init__()
        self.role = role
        self.typewriter = typewriter
        self.content = content
        self.timestamp = timestamp or datetime.now()
        self._index = 0

    def on_mount(self) -> None:
        if self.typewriter and self.role == "assistant":
            self.set_interval(0.01, self._type_tick)
        else:
            self.displayed_content = self.content

    def _type_tick(self) -> None:
        if self._index < len(self.content):
            self._index += 1
            self.displayed_content = self.content[: self._index]
            self.refresh()

    def watch_content(self, new_content: str) -> None:
        if not self.typewriter:
            self.displayed_content = new_content

    def render(self) -> RenderableType:
        time_str = self.timestamp.strftime("%H:%M")

        if self.role == "user":
            header = f"[bold {COLORS['primary']}]➜ COMMAND[/]"
            content_render = Text(self.displayed_content, style=COLORS["text"])

            panel = Panel(
                content_render,
                title=header,
                title_align="right",
                subtitle=f"[dim]@{time_str}[/]",
                subtitle_align="right",
                border_style=COLORS["primary"],
                box=box.SQUARE,  # Sharp, command-line feel
                padding=(0, 1),
                style=f"on {COLORS['surface_light']}",
                expand=False,
            )
            return Align.right(panel)

        elif self.role == "assistant":
            # Glitched title for vibrant AI feel
            title_text = glitch_text("DevOps Agent", intensity=0.03)
            header = f"[bold {COLORS['tertiary']}]◈ {title_text}[/]"
            content_render = Markdown(self.displayed_content)

            # Pulsing border style
            border_color = COLORS["secondary"]
            if self.typewriter and self._index < len(self.content):
                # Pulse during typing
                pulse = (math.sin(self._index / 5) + 1) / 2
                if pulse > 0.5:
                    border_color = COLORS["primary"]

            panel = Panel(
                content_render,
                title=header,
                title_align="left",
                subtitle=f"[dim]@{time_str}[/]",
                subtitle_align="left",
                border_style=border_color,
                box=box.HEAVY_EDGE,
                padding=(0, 1),
                style=f"on {COLORS['surface']}",
                width=None,  # Auto width
            )
            return Align.left(panel)

        elif self.role == "tool":
            header = f"[bold {COLORS['warning']}]⚡ SYS_EXEC[/] [dim]@{time_str}[/]"
            content_render = self._render_tool_content()

            # Tool logs take full width (or centered)
            return Panel(
                content_render,
                title=header,
                border_style=COLORS["warning"],
                box=box.SQUARE,  # Minimal noise
                padding=(0, 1),
                style=f"on {COLORS['surface']}",
            )

        else:  # Error
            header = f"[bold {COLORS['error']}]⚠ CRITICAL[/] [dim]@{time_str}[/]"
            content_render = Text(self.content, style=COLORS["error"])

            return Panel(
                content_render,
                title=header,
                border_style=COLORS["error"],
                padding=(0, 1),
                style=f"on {COLORS['surface']}",
            )

    def _render_tool_content(self) -> RenderableType:
        stripped = self.content.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            language = "json"
        elif "Traceback (most recent call last)" in self.content:
            language = "python"
        elif stripped.startswith("STDOUT:") or stripped.startswith("STDERR:"):
            return Text(self.content, style=COLORS["text"])
        else:
            language = "text"

        return Syntax(
            self.content,
            language,
            theme="vibe_neon",
            line_numbers=False,
            word_wrap=True,
        )


class CommandHistory(Static):
    """Mini command log for sidebar"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._commands: list[tuple[str, str]] = []  # (name, status)

    def add_command(self, name: str, status: str = "pending") -> None:
        """Add a command. Status: pending, success, error"""
        self._commands.append((name, status))
        # Keep only last 5
        if len(self._commands) > 5:
            self._commands = self._commands[-5:]
        self.refresh()

    def update_last(self, status: str) -> None:
        """Update the status of the last command"""
        if self._commands:
            name, _ = self._commands[-1]
            self._commands[-1] = (name, status)
            self.refresh()

    def render(self) -> RenderableType:
        text = Text()

        if not self._commands:
            text.append("  No commands yet", style="dim")
        else:
            for i, (name, status) in enumerate(self._commands):
                icon, color = self._get_status_icon(status)
                if i > 0:
                    text.append("\n")
                text.append(" ▸ ", style="dim")
                text.append(f"{name[:8]:<8} ")  # Shorter truncation
                text.append(icon, style=color)

        return Panel(
            text,
            title="LOG",
            border_style=COLORS["surface_light"],
            style=f"on {COLORS['surface']}",
            box=box.DOUBLE,
        )

    def _get_status_icon(self, status: str) -> tuple[str, str]:
        """Return (icon, color) for status"""
        if status == "success":
            return ("✓", COLORS["success"])
        elif status == "error":
            return ("✗", COLORS["error"])
        else:  # pending
            return ("◌", COLORS["warning"])


class ShortcutsPanel(Static):
    """Keyboard shortcuts overlay"""

    def render(self) -> RenderableType:
        shortcuts = [
            ("[?]", "Toggle Help"),
            ("[Ctrl+C]", "Quit"),
            ("[Ctrl+L]", "Clear Chat"),
            ("[↑/↓]", "History"),
            ("[Enter]", "Send"),
        ]

        lines = []
        for key, desc in shortcuts:
            lines.append(f"  [{COLORS['secondary']}]{key:<10}[/] [{COLORS['text']}]{desc}[/]")

        return Panel(
            Text.from_markup("\n".join(lines)),
            title=f"[bold {COLORS['primary']}]KEYMAP[/]",
            border_style=COLORS["primary"],
            style=f"on {COLORS['surface']}",
        )


class ConfirmationModal(ModalScreen[bool]):
    """Modal for confirming dangerous actions"""

    CSS = f"""
    ConfirmationModal {{
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }}

    #dialog {{
        grid-size: 2;
        grid-gutter: 1 2;
        grid-rows: 1fr 3;
        padding: 0 1;
        width: 60;
        height: auto;
        border: thick {COLORS['warning']};
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
        height: auto;
        margin: 1 0;
    }}

    Button {{
        width: 100%;
    }}
    """

    def __init__(self, tool_name: str, arguments: dict):
        super().__init__()
        self.tool_name = tool_name
        self.arguments = arguments

    def compose(self) -> ComposeResult:
        import json

        args_json = json.dumps(self.arguments, indent=2)

        yield Container(
            Label(f"⚠ SECURITY WARNING: {self.tool_name}", id="title"),
            Syntax(
                args_json,
                "json",
                theme="vibe_neon",
                line_numbers=False,
                word_wrap=True,
                id="details",
            ),
            Button("Reject", variant="error", id="reject"),
            Button("Approve", variant="success", id="approve"),
            id="dialog",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "approve":
            self.dismiss(True)
        else:
            self.dismiss(False)
