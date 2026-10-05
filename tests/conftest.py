import pytest

from bot import settings


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path, monkeypatch):
    """Every test gets its own state dir, dry-run on, and no real credentials."""
    monkeypatch.setenv("STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("DRY_RUN", "true")
    for name in (
        "THREADS_ACCESS_TOKEN", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY",
        "DISCORD_BOT_TOKEN", "DISCORD_CHANNEL_ID", "DISCORD_REVIEWER_IDS",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("THREADS_USER_ID", "123")
    monkeypatch.setenv("THREADS_USERNAME", "overlord_bot")
    settings.reload()
    yield
    settings.reload()
