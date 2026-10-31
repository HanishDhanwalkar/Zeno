from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings


class LLMModelSettings(BaseSettings):
    
    # gemini (default): google-genai API-key path.
    gemini_api_key: SecretStr = SecretStr("")
    gemini_model: str = "gemini-3.8-flash"

    # openrouter: the default ``openrouter/free`` router spreads across free models and auto-filters
    # for tool-calling, so one congested upstream cannot hard-block with 429s; pin a :free id for a
    # stricter guarantee.
    openrouter_api_key: SecretStr = SecretStr("")
    openrouter_model: str = "openrouter/free"

    ollama_model: str = "qwen2.5-coder:7b"
    ollama_endpoint_url: str = "http://127.0.0.1:11434/v1"


class Settings(BaseSettings):
    """Runtime configuration. Defaults are safe for tests, not production."""

    # --- Logging ---
    log_level: str = "INFO"

    llm_provider: Literal["gemini", "openrouter", "ollama"] = "ollama"

    # --- Tool execution / output truncation ---
    bash_timeout_s: float = 120.0
    max_output_lines: int = 2000
    max_output_bytes: int = 50_000
    # web_fetch_timeout_s: float = 30.0

    # --- Orchestration (ADR-0003 §8) ---
    # ``sleep(seconds)`` is capped to this value (never rejected) so a model cannot stall a turn.
    sleep_max_s: float = 60.0

    # --- Harness artifacts: everything zeno writes lives under <cwd>/.zeno. ---
    zeno_dir: Path = Path(".zeno")

    # --- Persistence: JSONL session log ---
    sessions_dir: Path = Path(".zeno/sessions")

    # --- Skills: project-local skills directory (ADR-0004 §3) ---
    # ``<name>/SKILL.md`` directories keyed by frontmatter ``name`` (directory name cosmetic); a
    # same-``name`` directory overrides a built-in skill. Missing dir → built-ins only.
    skills_dir: Path = Path(".zeno/skills")

    # --- LSP / code intelligence (ADR-0007) ---
    # ``lsp_enabled`` master-gates the WHOLE feature (the ``lsp`` tool, the Diagnostics Enricher, any
    # server spawn): ``False`` → no Language Server is ever launched.
    lsp_enabled: bool = True
    # The swappable stdio Language Server (default ``ty server``; ``pylsp`` is a documented drop-in).
    # The spawn is ``[lsp_server_command, *lsp_server_args]`` — keep executable and args split.
    lsp_server_command: str = "ty"
    lsp_server_args: list[str] = ["server"]
    # Gates ONLY the passive Diagnostics Enricher (post-write/edit errors block), independent of the
    # active ``lsp`` tool; both ride ``lsp_enabled``.
    lsp_diagnostics_on_edit: bool = True
    # Per-request best-effort wall-clock timeout (seconds); ``initialize`` is bounded too.
    lsp_request_timeout_s: float = Field(10.0, gt=0)

    @property
    def active_model(self) -> str:
        """The model id of the ACTIVE provider — the one :func:`zeno.agent.factory` will build."""
        pass


settings = Settings()
llm_model_settings = LLMModelSettings()