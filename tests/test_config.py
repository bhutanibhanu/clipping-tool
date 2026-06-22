from __future__ import annotations

from clipper.config import Settings, get_settings


def test_defaults_are_sized_for_the_8gb_air() -> None:
    s = Settings()
    assert s.whisper_model == "small"
    assert s.worker_concurrency == 1
    assert s.detector_model == "claude-opus-4-8"


def test_db_url_derives_from_storage_dir() -> None:
    s = Settings()
    assert s.db_url.startswith("sqlite:///")
    assert str(s.db_path).endswith("clipper.db")


def test_get_settings_is_cached() -> None:
    assert get_settings() is get_settings()
