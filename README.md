# Code AI Agentic CLI

**Code AI Agentic CLI** is an agentic AI coding assistant with a terminal-based user interface (TUI). It lets developers work with LLMs from the terminal to perform coding tasks, run commands, and manage the workspace with built-in security controls.

## Features

- **Agentic Workflow**: Streamlined loop of reasoning, tool execution, and result analysis.
- **Terminal UI**: Three-pane interface (Navigator, Transcript, Inspector) built with Textual.
- **Security First**:
    - Path traversal protection.
    - Shell command allowlisting/blocklisting.
    - User confirmation for dangerous operations (write, delete, commit).
- **Extensible**: Plugin system for adding custom tools. Workspace plugins (`.code-cli/tools/`) are **disabled by default** for security; set `CODE_CLI_ALLOW_WORKSPACE_PLUGINS=1` to enable (loads arbitrary Python from the repo).

## Installation

1.  **Clone and Install**:
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    pip install -e ".[dev]"
    ```

## Usage

Start the application:

```bash
code-cli
```

Or using the python module directly:

```bash
python3 -m code_cli.__main__
```

## Configuration

Configuration is stored in `~/.config/code-cli/config.toml`.

**Example Configuration:**

```toml
default_provider = "ollama"

[ui]
theme = "dark"  # Options: "dark", "light"
confirm_writes = true
confirm_shell = "dangerous"  # Options: "all", "dangerous", "none"

[context]
max_tokens = 100000
compress_threshold = 0.7
checkpoint_on_tool = true

[agent]
max_iterations = 20
require_confirmation = true
auto_checkpoint = true

[shell]
allowed = ["ls", "cat", "grep", "git", "pytest", "npm", "echo", "pwd", "mkdir", "touch"]
blocked = ["rm -rf", "> /dev/", "sudo"]
timeout = 30

[providers.ollama]
type = "ollama"
model = "granite3.1-dense:2b"
base_url = "http://localhost:11434"
auto_switch = true
keep_alive = 0  # Set to -1 to keep model loaded
```

## Keybindings

| Key | Action | Description |
|-----|--------|-------------|
| `Ctrl+C` | **Quit** | Exit the application |
| `Ctrl+K` | **Command Palette** | Open menu for quick actions |
| `Ctrl+L` | **Clear Transcript** | Clear conversation history |
| `Ctrl+.` | **Toggle Mode** | Switch between SAFE and ARMED mode |
| `Ctrl+E` | **Expand/Collapse** | Toggle detail view of the selected card |
| `Tab` | **Focus Next** | Cycle focus between panes |
| `Ctrl+1` | **Focus Navigator** | Jump to file explorer (Left Pane) |
| `Ctrl+2` | **Focus Transcript** | Jump to chat/log (Middle Pane) |
| `Ctrl+3` | **Focus Inspector** | Jump to details/diff view (Right Pane) |
| `Ctrl+4` | **Focus Composer** | Jump to input bar |

## Architecture

The application uses a reactive, event-driven architecture:

- **Agent Loop**: Handles LLM interaction and tool execution.
- **Event Bus**: Decouples UI components from the agent logic.
- **Three-Pane Layout**:
    - **Navigator**: File system and session view.
    - **Transcript**: Linear history of interactions (User messages, Assistant thoughts, Tool results).
    - **Inspector**: Contextual details, diff previews, and tool outputs.

## Development

Run tests:

```bash
pytest -xvs
```
