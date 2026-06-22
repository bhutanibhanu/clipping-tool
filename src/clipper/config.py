"""Runtime configuration.

Defaults are deliberately sized for the constraining runtime target — an
idle 8 GB MacBook Air M1 — not the 24 GB M5 Pro used for development:
`small` Whisper model and a single sequential worker so transcription and
ffmpeg never contend for the 8 GB. Override per machine via env (CLIPPER_*)
or a local .env file.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CLIPPER_", env_file=".env", extra="ignore")

    # Detection (Phase 2+): Claude behind the Detector protocol.
    detector_model: str = "claude-opus-4-8"
    detector_fallback_model: str = "claude-sonnet-4-6"
    # Sampling temperature for detection. 0.0 = deterministic eval (ADR-0001 §3).
    # NOTE: claude-opus-4-7/4.8 (and Fable) REJECT the `temperature` param with a
    # 400, so the Claude provider only forwards it when > 0; at the 0.0 default it
    # is omitted (the prompt, not a sampling knob, carries determinism there). The
    # value still applies to OpenAI-compatible/local providers (T3B).
    detector_temperature: float = 0.0

    # Transcription (Phase 1+): faster-whisper, CPU-only on Mac.
    # `small` is the accuracy floor that fits the 8 GB Air; bump on the Pro.
    whisper_model: str = "small"
    whisper_compute_type: str = "int8"

    # The 8 GB Air cannot run Whisper + heavy ffmpeg simultaneously.
    worker_concurrency: int = 1

    # Local-first storage (gitignored).
    storage_dir: Path = Path("storage")

    @property
    def db_path(self) -> Path:
        return self.storage_dir / "clipper.db"

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.db_path}"


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
