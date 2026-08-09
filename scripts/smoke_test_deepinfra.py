"""
Manual, one-off check that DEEPINFRA_API_KEY actually works — makes one real, billed call.
Not a pytest test: run directly with `python scripts/smoke_test_deepinfra.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import get_settings  # noqa: E402
from core.exceptions import ProviderError  # noqa: E402
from llm.deepinfra_provider import DeepInfraProvider  # noqa: E402

TEST_PROMPT = "Reply with exactly one short sentence confirming you received this message."


def main() -> None:
    settings = get_settings()
    if not settings.deepinfra_api_key:
        print("DEEPINFRA_API_KEY is not set in .env — nothing to test.", file=sys.stderr)
        sys.exit(1)

    provider = DeepInfraProvider(api_key=settings.deepinfra_api_key, model=settings.deepinfra_model)
    print(f"Calling {settings.deepinfra_model} via DeepInfra...")
    try:
        response = provider.complete(TEST_PROMPT)
    except ProviderError as e:
        print(f"DeepInfra call failed: {e}", file=sys.stderr)
        sys.exit(1)

    print("Response:")
    print(response)


if __name__ == "__main__":
    main()
