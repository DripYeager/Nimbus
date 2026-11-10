from __future__ import annotations

import pytest

from config.legacy_settings import LEGACY_KEYS
from config.settings import Settings


@pytest.fixture(autouse=True)
def _no_developer_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """magika (pulled in by markitdown) runs load_dotenv() on import, copying the developer's real
    .env into os.environ for the rest of the session, so settings tests clear those vars first."""
    for name in [*Settings.model_fields, *LEGACY_KEYS]:
        monkeypatch.delenv(name.upper(), raising=False)
