import pytest

from aievograph.config.settings import AppSettings


def test_settings_reads_environment_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("NEO4J_PASSWORD", "test-password")
    monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")
    monkeypatch.setenv("NEO4J_USER", "neo4j")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    settings = AppSettings()

    assert settings.openai_api_key == "test-key"
    assert settings.neo4j_password == "test-password"
    assert settings.log_level == "DEBUG"
