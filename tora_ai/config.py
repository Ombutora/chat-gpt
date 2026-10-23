"""Settings for Tora AI, read from environment variables and an optional `.env` file."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# OpenAI-compatible endpoints that serve gpt-oss, and each one's name for the 20b model.
PROVIDERS = {
    "openrouter": ("https://openrouter.ai/api/v1", "openai/gpt-oss-20b", "OPENROUTER_API_KEY"),
    "groq": ("https://api.groq.com/openai/v1", "openai/gpt-oss-20b", "GROQ_API_KEY"),
    "huggingface": ("https://router.huggingface.co/v1", "openai/gpt-oss-20b", "HF_TOKEN"),
    "ollama": ("http://localhost:11434/v1", "gpt-oss:20b", None),
}
REASONING_EFFORTS = ("low", "medium", "high")
TOOL_NAMES = ("web", "python")


class ConfigError(Exception):
    pass


@dataclass
class Settings:
    provider: str = "openrouter"
    base_url: str = PROVIDERS["openrouter"][0]
    api_key: str = ""
    model: str = PROVIDERS["openrouter"][1]
    reasoning_effort: str = "medium"
    temperature: float = 1.0
    system_prompt: str | None = None
    tools: list[str] = field(default_factory=lambda: ["web"])
    python_backend: str = "docker"

    @classmethod
    def from_env(cls, env_file: str | Path | None = None) -> "Settings":
        # Values already set in the real environment win over the .env file.
        load_dotenv(env_file or Path.cwd() / ".env", override=False)
        provider = os.getenv("TORA_PROVIDER", "openrouter").strip().lower()
        if provider not in PROVIDERS and not os.getenv("TORA_BASE_URL"):
            raise ConfigError(
                f"Unknown TORA_PROVIDER {provider!r}. Use one of {', '.join(PROVIDERS)} "
                "or set TORA_BASE_URL for another OpenAI-compatible server."
            )
        default_url, default_model, key_var = PROVIDERS.get(provider, ("", "", None))
        api_key = os.getenv("TORA_API_KEY") or (os.getenv(key_var) if key_var else None)
        if not api_key:
            if provider == "ollama":
                api_key = "ollama"  # Ollama ignores the key but the client requires one.
            else:
                hint = f"TORA_API_KEY or {key_var}" if key_var else "TORA_API_KEY"
                raise ConfigError(f"No API key found. Set {hint} in your environment or .env file.")

        effort = os.getenv("TORA_REASONING_EFFORT", "medium").strip().lower()
        if effort not in REASONING_EFFORTS:
            raise ConfigError(f"TORA_REASONING_EFFORT must be one of {', '.join(REASONING_EFFORTS)}.")

        tools = [t.strip().lower() for t in os.getenv("TORA_TOOLS", "web").split(",") if t.strip()]
        unknown = [t for t in tools if t not in TOOL_NAMES]
        if unknown:
            raise ConfigError(f"Unknown tool(s) in TORA_TOOLS: {', '.join(unknown)}. Available: {', '.join(TOOL_NAMES)}.")

        return cls(
            provider=provider,
            base_url=os.getenv("TORA_BASE_URL", default_url),
            api_key=api_key,
            model=os.getenv("TORA_MODEL", default_model),
            reasoning_effort=effort,
            temperature=float(os.getenv("TORA_TEMPERATURE", "1.0")),
            system_prompt=_load_system_prompt(os.getenv("TORA_SYSTEM_PROMPT")),
            tools=tools,
            python_backend=os.getenv("TORA_PYTHON_BACKEND", "docker").strip().lower(),
        )


def _load_system_prompt(value: str | None) -> str | None:
    # TORA_SYSTEM_PROMPT may be the prompt itself or a path to a text file containing it.
    if not value:
        return None
    path = Path(value)
    if len(value) < 260 and path.is_file():
        return path.read_text(encoding="utf-8").strip()
    return value
