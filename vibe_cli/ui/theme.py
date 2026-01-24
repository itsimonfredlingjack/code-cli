# vibe_cli/ui/theme.py

from rich.style import Style
from rich.text import Text
from typing import List, Tuple
import random

COLORS = {
    # Soft Pastel Palette
    "bg": "#1a1b26",  # Deep gray-blue void
    "surface": "#24283b",  # Lighter panel
    "surface_light": "#2f334d",  # Selection highlight
    "surface_glow": "#3a3e5a",  # Glow layer
    # Pastel Accents
    "primary": "#b5b3cf",  # Soft lavender
    "secondary": "#a8e6cf",  # Mint green
    "tertiary": "#ffd3b6",  # Peach
    # State Colors (Softened)
    "error": "#ffb7b2",  # Soft pink
    "warning": "#ffaaa5",  # Soft coral
    "success": "#c1e1c1",  # Sage green
    # Text Colors
    "text": "#c0caf5",  # Muted blue-white
    "text_dim": "#7aa2f7",  # Dimmed
    "text_bright": "#e0af68",  # Accent text
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
"""


class Shader:
    """ASCII Gradient Engine"""

    SHADES = " ░▒▓█"

    @staticmethod
    def get_gradient_text(content: str, start_color: str, end_color: str) -> Text:
        """Applies a simple horizontal gradient (simulated)"""
        # Rich doesn't support true gradients on text natively without complex span work.
        # For this V2, we will use colors for the blocks.
        t = Text(content)
        t.stylize(f"bold {start_color}")
        return t

    @staticmethod
    def vertical_bar(value: float, height: int, color_low="green", color_high="red") -> str:
        """Generates a vertical bar with block characters"""
        # value 0.0 to 1.0
        # This returns a single char string, likely used in a column
        idx = int(value * (len(Shader.SHADES) - 1))
        return Shader.SHADES[idx]

    @staticmethod
    def shaded_rect(width: int, height: int, color: str) -> Text:
        """Returns a block of shaded text"""
        lines = []
        for y in range(height):
            # Dither effect
            char = "▓" if (y % 2 == 0) else "▒"
            lines.append(char * width)
        return Text("\n".join(lines), style=color)


# --- CUSTOM ASSETS ---

from rich.box import Box
from pygments.style import Style as PygmentsStyle
from pygments.token import Keyword, Name, Comment, String, Error, Number, Operator, Generic

# Custom "Glitch" Box using density characters
# Refined "Thin Glitch" - Elegant, sharp, but signal-degraded
GLITCH = Box("─░─╌\n─░─╌\n─░─╌\n─░─╌\n│░│╌\n│░│╌\n─░─╌\n─░─╌\n")

# Tech Schematic Box
TECH = Box("┌─┬┐\n├─┼┤\n├─┼┤\n└─┴┘\n│ │ \n│ │ \n├─┼┤\n├─┼┤\n")

# Retro CRT Scanline Box (Strict ASCII)
SCANLINE = Box(
    "+--+\n"  # Top
    "+--+\n"  # Head
    "+--+\n"  # Mid
    "+--+\n"  # Bottom
    "¦   \n"  # Left (Must be 4 chars!)
    "¦   \n"  # Right
    "+   \n"  # Top Divider
    "+   \n"  # Bottom Divider
)


def glitch_text(text: str, intensity: float = 0.1) -> str:
    """Adds Zalgo-like glitch effects to text"""
    # Combining diacritics
    chars = [chr(i) for i in range(0x0300, 0x036F)]
    output = ""
    for char in text:
        output += char
        # Randomly append diacritics
        if random.random() < intensity:
            for _ in range(random.randint(1, 3)):
                output += random.choice(chars)
    return output


class VibeNeonStyle(PygmentsStyle):
    """Custom Pygments style matching Vibe colors"""

    background_color = COLORS["surface"]
    highlight_color = COLORS["surface_light"]

    styles = {
        # Keywords: Lavender
        Keyword: f"bold {COLORS['primary']}",
        Keyword.Constant: f"bold {COLORS['tertiary']}",
        Keyword.Namespace: f"bold {COLORS['primary']}",
        # Names: Text / Peach
        Name: COLORS["text"],
        Name.Function: f"bold {COLORS['tertiary']}",
        Name.Class: f"bold {COLORS['tertiary']}",
        Name.Builtin: COLORS["primary"],
        # Strings: Mint
        String: COLORS["secondary"],
        String.Doc: f"italic {COLORS['text_dim']}",
        # Numbers: Peach/Coral
        Number: COLORS["warning"],
        # Operators: Lavender
        Operator: COLORS["primary"],
        # Comments: Dim Blue
        Comment: f"italic {COLORS['text_dim']}",
        # Errors: Pink
        Error: f"bold {COLORS['error']}",
        # Component stuff
        Generic.Prompt: f"bold {COLORS['primary']}",
        Generic.Output: COLORS["text"],
        Generic.Traceback: COLORS["error"],
    }
