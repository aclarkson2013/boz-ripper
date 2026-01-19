"""Tests for configuration loading."""

import pytest

from boz_agent.core.config import Settings


def test_default_settings():
    """Test that default settings load correctly."""
    settings = Settings()

    assert settings.agent.name == "Boz Agent"
    assert settings.server.url == "http://localhost:8000"
    assert settings.disc_detection.enabled is True
    assert settings.worker.enabled is False


def test_settings_from_env(monkeypatch):
    """Test loading settings from environment variables."""
    monkeypatch.setenv("BOZ_SERVER__URL", "http://custom:9000")
    monkeypatch.setenv("BOZ_AGENT__NAME", "Test Agent")

    settings = Settings()

    assert settings.server.url == "http://custom:9000"
    assert settings.agent.name == "Test Agent"
