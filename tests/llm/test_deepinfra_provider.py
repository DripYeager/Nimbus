from __future__ import annotations

from types import SimpleNamespace

from pytest_mock import MockerFixture

from llm.deepinfra_provider import DEEPINFRA_BASE_URL, DeepInfraProvider
from llm.openai_provider import OpenAIProvider


def test_init_points_the_openai_client_at_deepinfra(mocker: MockerFixture) -> None:
    openai_client_cls = mocker.patch("llm.openai_provider.openai.OpenAI")
    DeepInfraProvider(api_key="di-test", model="deepseek-ai/DeepSeek-V4-Flash-0731")
    openai_client_cls.assert_called_once_with(api_key="di-test", base_url=DEEPINFRA_BASE_URL)


def test_deepinfra_provider_is_an_openai_provider(mocker: MockerFixture) -> None:
    mocker.patch("llm.openai_provider.openai.OpenAI")
    provider = DeepInfraProvider(api_key="di-test", model="deepseek-ai/DeepSeek-V4-Flash-0731")
    assert isinstance(provider, OpenAIProvider)


def test_complete_reuses_openai_providers_request_logic(mocker: MockerFixture) -> None:
    mocker.patch("llm.openai_provider.openai.OpenAI")
    provider = DeepInfraProvider(api_key="di-test", model="deepseek-ai/DeepSeek-V4-Flash-0731")
    provider._client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="hello from deepseek"))]
    )
    assert provider.complete("hi") == "hello from deepseek"
