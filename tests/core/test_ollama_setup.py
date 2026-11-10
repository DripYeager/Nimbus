from __future__ import annotations

import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import ollama
import pytest
from pytest_mock import MockerFixture

from core.exceptions import ProviderError
from core.ollama_setup import OllamaSetup, find_ollama, same_model

HOST = "http://localhost:11434"


@pytest.fixture
def client(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("core.ollama_setup.ollama.Client").return_value


@pytest.fixture
def setup() -> OllamaSetup:
    return OllamaSetup(lambda: HOST)


def _listing(*names: str) -> SimpleNamespace:
    return SimpleNamespace(models=[SimpleNamespace(model=name) for name in names])


def test_same_model_treats_a_missing_tag_as_latest() -> None:
    assert same_model("qwen2.5:latest", "qwen2.5")


def test_same_model_tells_different_sizes_apart() -> None:
    assert not same_model("llama3.1:70b", "llama3.1:8b")


def test_find_ollama_prefers_the_one_on_path(mocker: MockerFixture) -> None:
    mocker.patch("core.ollama_setup.shutil.which", return_value="C:/bin/ollama.exe")

    assert find_ollama() == Path("C:/bin/ollama.exe")


def test_find_ollama_falls_back_to_the_per_user_install(mocker: MockerFixture, tmp_path: Path) -> None:
    exe = tmp_path / "ollama.exe"
    exe.write_text("x")
    mocker.patch("core.ollama_setup.shutil.which", return_value=None)
    mocker.patch("core.ollama_setup.ollama_install_candidates", return_value=[tmp_path / "missing.exe", exe])

    assert find_ollama() == exe


def test_find_ollama_is_none_when_not_installed(mocker: MockerFixture) -> None:
    mocker.patch("core.ollama_setup.shutil.which", return_value=None)
    mocker.patch("core.ollama_setup.ollama_install_candidates", return_value=[])

    assert find_ollama() is None


def test_status_reports_a_running_server_with_the_model(setup: OllamaSetup, client: MagicMock) -> None:
    client.list.return_value = _listing("llama3.1:8b", "qwen2.5:latest")

    status = setup.status("qwen2.5")

    assert (status.installed, status.running, status.has_model) == (True, True, True)


def test_status_reports_installed_but_not_running(setup: OllamaSetup, client: MagicMock, mocker: MockerFixture) -> None:
    client.list.side_effect = ConnectionError("refused")
    mocker.patch("core.ollama_setup.find_ollama", return_value=Path("C:/ollama.exe"))

    status = setup.status("llama3.1:8b")

    assert (status.installed, status.running, status.has_model) == (True, False, False)


def test_status_reports_not_installed(setup: OllamaSetup, client: MagicMock, mocker: MockerFixture) -> None:
    client.list.side_effect = ConnectionError("refused")
    mocker.patch("core.ollama_setup.find_ollama", return_value=None)

    assert setup.status("llama3.1:8b").installed is False


def test_start_prefers_the_tray_app(setup: OllamaSetup, mocker: MockerFixture, tmp_path: Path) -> None:
    exe = tmp_path / "ollama.exe"
    (tmp_path / "ollama app.exe").write_text("x")
    mocker.patch("core.ollama_setup.find_ollama", return_value=exe)
    popen = mocker.patch("core.ollama_setup.subprocess.Popen")

    setup.start()

    assert popen.call_args.args[0] == [str(tmp_path / "ollama app.exe")]


def test_start_falls_back_to_ollama_serve(setup: OllamaSetup, mocker: MockerFixture, tmp_path: Path) -> None:
    mocker.patch("core.ollama_setup.find_ollama", return_value=tmp_path / "ollama.exe")
    popen = mocker.patch("core.ollama_setup.subprocess.Popen")

    setup.start()

    assert popen.call_args.args[0] == [str(tmp_path / "ollama.exe"), "serve"]


def test_start_raises_when_ollama_is_not_installed(setup: OllamaSetup, mocker: MockerFixture) -> None:
    mocker.patch("core.ollama_setup.find_ollama", return_value=None)

    with pytest.raises(ProviderError, match="isn't installed"):
        setup.start()


def _run_pull_inline(mocker: MockerFixture) -> None:
    class _Inline:
        def __init__(self, target, args, name, daemon) -> None:  # noqa: ANN001
            self._run = lambda: target(*args)

        def start(self) -> None:
            self._run()

    mocker.patch.object(threading, "Thread", _Inline)


def test_pull_clears_the_progress_when_finished(setup: OllamaSetup, client: MagicMock, mocker: MockerFixture) -> None:
    _run_pull_inline(mocker)
    client.pull.return_value = iter(
        [SimpleNamespace(total=100, completed=50), SimpleNamespace(total=100, completed=100)]
    )
    client.list.return_value = _listing("qwen2.5:7b")

    setup.pull("qwen2.5:7b")

    status = setup.status("qwen2.5:7b")
    assert (status.pulling, status.has_model, status.pull_error) == (None, True, None)


def test_pull_records_a_failed_download(setup: OllamaSetup, client: MagicMock, mocker: MockerFixture) -> None:
    _run_pull_inline(mocker)
    client.pull.side_effect = ollama.ResponseError("model not found")
    client.list.return_value = _listing()

    setup.pull("nope:1b")

    assert "Couldn't download nope:1b" in setup.status("nope:1b").pull_error


def test_pull_refuses_a_second_download_at_once(setup: OllamaSetup, mocker: MockerFixture) -> None:
    mocker.patch("core.ollama_setup.threading.Thread")
    setup.pull("qwen2.5:7b")

    with pytest.raises(ProviderError, match="Already downloading"):
        setup.pull("llama3.1:8b")
