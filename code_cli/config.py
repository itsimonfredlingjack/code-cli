from pathlib import Path
from typing import Literal

import platformdirs
import tomli
from pydantic import BaseModel, Field


class ProviderConfig(BaseModel):
    type: Literal["openai", "opencode", "ollama"] = "openai"
    api_key: str = ""
    model: str
    max_tokens: int = 4096
    base_url: str | None = None
    auto_switch: bool = False
    small_model: str | None = None
    large_model: str | None = None
    switch_tokens: int = 2000
    switch_keywords: list[str] = Field(
        default_factory=lambda: [
            "complex",
            "architecture",
            "refactor",
            "debug",
            "performance",
            "benchmark",
        ],
    )
    keep_alive: int | None = 0


class UIConfig(BaseModel):
    theme: str = "light"
    show_tokens: bool = True
    confirm_writes: bool = True
    confirm_shell: Literal["all", "dangerous", "none"] = "dangerous"


class ContextConfig(BaseModel):
    max_tokens: int = 100000
    compress_threshold: float = 0.7
    checkpoint_on_tool: bool = True


class ShellConfig(BaseModel):
    allowed: list[str] = Field(default_factory=lambda: ["ls", "cat", "grep", "git", "pytest", "npm"])
    blocked: list[str] = Field(default_factory=lambda: ["rm -rf", "> /dev/"])
    timeout: int = 30


class AgentConfig(BaseModel):
    max_iterations: int = 20
    require_confirmation: bool = True
    auto_checkpoint: bool = True


class Config(BaseModel):
    """
    Root configuration object for the application.

    Loaded from ~/.config/code-cli/config.toml.
    Contains settings for UI, context management, shell security, and LLM providers.
    """
    ui: UIConfig = Field(default_factory=UIConfig)
    context: ContextConfig = Field(default_factory=ContextConfig)
    shell: ShellConfig = Field(default_factory=ShellConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    providers: dict[str, ProviderConfig] = Field(default_factory=dict)
    default_provider: str = "ollama"

    @classmethod
    def load(cls, path: Path | None = None) -> "Config":
        """
        Load configuration from a TOML file.

        Args:
            path (Path, optional): Custom path to config file. Defaults to standard user config dir.

        Returns:
            Config: Loaded configuration or defaults if file missing.
        """
        if path is None:
            config_dir = Path(platformdirs.user_config_dir("code-cli"))
            path = config_dir / "config.toml"

        if not path.exists():
            return cls()

        with open(path, "rb") as f:
            data = tomli.load(f)

        return cls.model_validate(data)
