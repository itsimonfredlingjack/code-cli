# code_cli/ui/header.py

from rich.align import Align
from rich.console import RenderableType
from rich.text import Text
from textual.reactive import reactive
from textual.widget import Widget

from .theme import COLORS, get_icon
from .widgets import SafeArmState


class CodenticHeader(Widget):
    """Two-line agentic dashboard header showing agent state, branch, model, CTX bar, cost."""

    model = reactive("unknown")
    branch = reactive("main")
    mode = reactive(SafeArmState.SAFE.value)
    ctx_pct = reactive(0)
    ctx_used = reactive(0)
    ctx_max = reactive(0)
    tokens_per_sec = reactive(0.0)
    is_active = reactive(False)

    # Agent status machine: idle/thinking/acting/verifying
    agent_status = reactive("idle")
    active_task = reactive("")
    dirty_state = reactive(False)
    cost_indicator = reactive("")

    def render(self) -> RenderableType:
        # Line 1: CODENTIC title + version
        line1 = Text()
        line1.append("CODENTIC", style=f"bold {COLORS['text']}")
        line1.append(" v0.8.0", style=COLORS["text_muted"])

        # Line 2: [AGENT_STATUS_PILL] | [branch+dirty] | [active_task] | [model] | [CTX bar] | [cost] | [tks/s]
        line2 = Text()

        # Agent status pill
        status_config = {
            "idle": (COLORS["text_muted"], "IDLE", get_icon("status_idle")),
            "thinking": (COLORS["accent_cyan"], "THINKING", get_icon("status_thinking")),
            "acting": (COLORS["accent_orange"], "ACTING", get_icon("status_acting")),
            "verifying": (COLORS["success"], "VERIFYING", get_icon("status_verifying")),
        }
        s_color, s_text, s_icon = status_config.get(self.agent_status, status_config["idle"])
        line2.append(f" {s_icon} {s_text} ", style=f"on {s_color} {COLORS['bg']}")
        line2.append(" | ", style=COLORS["text_muted"])

        # Mode pill
        if self.mode == SafeArmState.SAFE.value:
            mode_bg = COLORS["accent_orange"]
            mode_text = "SAFE"
        elif self.mode == SafeArmState.ARMED.value:
            mode_bg = COLORS["success"]
            mode_text = "ARMED"
        else:
            mode_bg = COLORS["accent_cyan"]
            mode_text = "ARMED*"

        line2.append(f" {mode_text} ", style=f"on {mode_bg} {COLORS['bg']}")
        line2.append(" | ", style=COLORS["text_muted"])

        # Branch + dirty indicator
        branch_icon = get_icon("branch")
        branch_text = f"{branch_icon} {self.branch}"
        if self.dirty_state:
            branch_text += "*"
        line2.append(branch_text, style=COLORS["text"])
        line2.append(" | ", style=COLORS["text_muted"])

        # Active task (truncated)
        if self.active_task:
            task_display = self.active_task[:40] + ("..." if len(self.active_task) > 40 else "")
            line2.append(task_display, style=COLORS["text"])
            line2.append(" | ", style=COLORS["text_muted"])

        # Model
        model_icon = get_icon("model")
        line2.append(f"{model_icon} {self.model}", style=COLORS["text"])
        line2.append(" | ", style=COLORS["text_muted"])

        # CTX bar
        ctx_bar_width = 8
        ctx_filled = int((self.ctx_pct / 100) * ctx_bar_width) if self.ctx_max > 0 else 0
        ctx_bar = "\u2588" * ctx_filled + "\u2591" * (ctx_bar_width - ctx_filled)
        ctx_color = (
            COLORS["accent_cyan"]
            if self.ctx_pct < 70
            else COLORS["accent_orange"]
            if self.ctx_pct < 90
            else COLORS["danger"]
        )
        line2.append("CTX ", style=COLORS["text_muted"])
        line2.append(ctx_bar, style=ctx_color)
        line2.append(f" {self.ctx_pct}%", style=COLORS["text_muted"])

        # Cost indicator
        if self.cost_indicator:
            line2.append(" | ", style=COLORS["text_muted"])
            line2.append(self.cost_indicator, style=COLORS["text_muted"])

        # Tokens/sec (show only while streaming)
        if self.tokens_per_sec > 0:
            line2.append(" | ", style=COLORS["text_muted"])
            tokens_icon = get_icon("tokens")
            line2.append(f"{tokens_icon} {self.tokens_per_sec:.1f}/s", style=COLORS["accent_cyan"])

        content = Text()
        content.append(line1)
        content.append("\n")
        content.append(line2)

        return Align.left(content)
