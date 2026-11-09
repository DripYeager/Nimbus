from __future__ import annotations

import pytest

from config.legacy_settings import DEEPINFRA_BASE_URL, migrate_legacy_values


def test_migrate_legacy_values_turns_deepinfra_into_openai_compatible() -> None:
    migrated = migrate_legacy_values({"llm_provider": "deepinfra"})

    assert migrated["llm_provider"] == "openai_compatible"
    assert migrated["compatible_base_url"] == DEEPINFRA_BASE_URL


def test_migrate_legacy_values_keeps_an_explicit_compatible_base_url() -> None:
    migrated = migrate_legacy_values({"llm_provider": "deepinfra", "compatible_base_url": "http://proxy/v1"})

    assert migrated["compatible_base_url"] == "http://proxy/v1"


def test_migrate_legacy_values_carries_the_deepinfra_model_and_key_over() -> None:
    migrated = migrate_legacy_values(
        {"llm_provider": "deepinfra", "deepinfra_model": "meta-llama/Llama-3", "deepinfra_api_key": "di-key"}
    )

    assert migrated["compatible_model"] == "meta-llama/Llama-3"
    assert migrated["compatible_api_key"] == "di-key"


def test_migrate_legacy_values_parses_watched_dirs_from_a_json_string() -> None:
    migrated = migrate_legacy_values({"watched_dirs": '["C:/Work", "C:/Notes"]'})

    assert migrated["sources"] == [{"path": "C:/Work"}, {"path": "C:/Notes"}]


def test_migrate_legacy_values_accepts_watched_dirs_as_a_list() -> None:
    migrated = migrate_legacy_values({"watched_dirs": ["C:/Work"]})

    assert migrated["sources"] == [{"path": "C:/Work"}]


def test_migrate_legacy_values_does_not_override_explicit_sources() -> None:
    migrated = migrate_legacy_values({"watched_dirs": ["C:/Old"], "sources": [{"path": "C:/New"}]})

    assert migrated["sources"] == [{"path": "C:/New"}]


def test_migrate_legacy_values_drops_the_old_v1_defaults() -> None:
    v1_defaults = {"embedding_model": "all-MiniLM-L6-v2", "max_chunk_size": "512", "chunk_overlap": 50}

    migrated = migrate_legacy_values(v1_defaults)

    assert migrated == {}


def test_migrate_legacy_values_keeps_a_chunk_size_the_user_actually_chose() -> None:
    assert migrate_legacy_values({"max_chunk_size": "200"}) == {"max_chunk_size": "200"}


def test_migrate_legacy_values_drops_every_legacy_key() -> None:
    migrated = migrate_legacy_values(
        {"llm_provider": "deepinfra", "deepinfra_api_key": "k", "deepinfra_model": "m", "watched_dirs": ["C:/A"]}
    )

    assert not {"deepinfra_api_key", "deepinfra_model", "watched_dirs"} & set(migrated)


def test_migrate_legacy_values_leaves_current_settings_untouched() -> None:
    current = {"llm_provider": "openai", "embedding_model": "BAAI/bge-small-en-v1.5"}

    assert migrate_legacy_values(current) == current


def test_migrate_legacy_values_does_not_mutate_its_input() -> None:
    original = {"llm_provider": "deepinfra", "watched_dirs": ["C:/A"]}

    migrate_legacy_values(original)

    assert original == {"llm_provider": "deepinfra", "watched_dirs": ["C:/A"]}


def test_migrate_legacy_values_raises_on_malformed_watched_dirs_json() -> None:
    with pytest.raises(ValueError):
        migrate_legacy_values({"watched_dirs": "[not json"})
