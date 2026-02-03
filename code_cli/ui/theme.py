# code_cli/ui/theme.py

from pygments.style import Style as PygmentsStyle
from pygments.token import Comment, Error, Generic, Keyword, Name, Number, Operator, String
from rich.box import ROUNDED

# Neon HUD Palette (Crush-like)
COLORS = {
    "bg": "#0B0F14",
    "surface": "#121823",
    "surface_light": "#1C2432",
    "surface_glow": "#18202D",
    "primary": "#00E5FF",
    "secondary": "#FF9D00",
    "tertiary": "#7CFF6B",
    "error": "#FF5D5D",
    "warning": "#FFB020",
    "success": "#3CFFB5",
    "text": "#E6F0FF",
    "text_dim": "#94A3B8",
    "text_bright": "#F8FAFC",
    "focus_ring": "#00E5FF",
    "card_border": "#1F2A3A",
    "card_shadow": "#081018",
}

CSS_VARS = f"""
    $bg: {COLORS["bg"]};
    $surface: {COLORS["surface"]};
    $surface_light: {COLORS["surface_light"]};
    $surface_glow: {COLORS["surface_glow"]};

    $primary: {COLORS["primary"]};
    $secondary: {COLORS["secondary"]};
    $tertiary: {COLORS["tertiary"]};

    $error: {COLORS["error"]};
    $warning: {COLORS["warning"]};
    $success: {COLORS["success"]};

    $text: {COLORS["text"]};
    $text_dim: {COLORS["text_dim"]};
    $text_bright: {COLORS["text_bright"]};

    $focus_ring: {COLORS["focus_ring"]};
    $card_border: {COLORS["card_border"]};
    $card_shadow: {COLORS["card_shadow"]};
"""

# --- STRUCTURAL ASSETS ---

HUD = ROUNDED


class CodeNeonStyle(PygmentsStyle):
    """Neon HUD Syntax Highlighting"""

    background_color = COLORS["surface"]
    highlight_color = COLORS["surface_glow"]

    styles = {
        Keyword: f"bold {COLORS['primary']}",
        Keyword.Constant: f"bold {COLORS['tertiary']}",
        Keyword.Namespace: f"bold {COLORS['primary']}",
        Name: COLORS["text"],
        Name.Function: f"bold {COLORS['primary']}",
        Name.Class: f"bold {COLORS['tertiary']}",
        Name.Builtin: COLORS["primary"],
        String: COLORS["success"],
        String.Doc: f"italic {COLORS['text_dim']}",
        Number: COLORS["secondary"],
        Operator: COLORS["primary"],
        Comment: f"italic {COLORS['text_dim']}",
        Error: f"bold {COLORS['error']}",
        Generic.Prompt: f"bold {COLORS['primary']}",
        Generic.Output: COLORS["text"],
        Generic.Traceback: COLORS["error"],
    }
