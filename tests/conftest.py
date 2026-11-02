from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "transcripts"

# Set by the environment the tests run in (an old Herdr pane or an hc terminal); they would make
# backend auto-detection depend on where pytest was started.
_HOST_ENV = ("HERDR_BACKEND", "HERDR_SOCKET_PATH", "HERDR_PLUGIN_ROOT", "HERDR_PANE_ID", "HERDR_PLUGIN_CONFIG_DIR",
             "HC_TERMINAL_ID", "HC_TERMINAL_SOCKET", "HC_SCOPE", "HC_SESSION")


@pytest.fixture(autouse=True)
def _herdr_backend(monkeypatch):
    """Tests run on the old `herdr` backend unless they opt into hc (HERDR_BACKEND=hc)."""
    for key in _HOST_ENV:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("HERDR_BACKEND", "herdr")


def load_transcript(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def transcript():
    return load_transcript
