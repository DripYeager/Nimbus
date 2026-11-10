from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable, Iterator

import pytest
from PyQt6.QtWidgets import QApplication
from pytest_mock import MockerFixture

import ui.single_instance as single_instance
from ui.single_instance import ASK_PREFIX, InstanceServer, notify_running_instance


def _wait_for(condition: Callable[[], bool], timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while not condition() and time.monotonic() < deadline:
        QApplication.processEvents()
        time.sleep(0.01)
    return condition()


@pytest.fixture(autouse=True)
def _unique_server_name(mocker: MockerFixture) -> None:
    """A per-test socket name, so tests never talk to a real running Nimbus (or each other)."""
    name = f"nimbus-test-{uuid.uuid4().hex}"
    mocker.patch("ui.single_instance._server_name", return_value=name)


@pytest.fixture
def server() -> Iterator[InstanceServer]:
    instance_server = InstanceServer()
    instance_server.listen()
    yield instance_server
    instance_server._server.close()


def test_server_name_is_per_user(mocker: MockerFixture) -> None:
    mocker.stopall()
    mocker.patch("ui.single_instance.getpass.getuser", return_value="alice")

    assert single_instance._server_name() == "nimbus-alice"


def test_notify_running_instance_returns_false_when_none_is_running() -> None:
    assert notify_running_instance() is False


def _knock_from_another_thread() -> list[bool]:
    """Runs the second launch's knock off the GUI thread, as a separate process would, so the
    server's event loop is free to read it."""
    answers: list[bool] = []
    threading.Thread(target=lambda: answers.append(notify_running_instance()), daemon=True).start()
    return answers


def test_notify_running_instance_returns_true_when_one_answers(server: InstanceServer) -> None:
    answers = _knock_from_another_thread()

    assert _wait_for(lambda: bool(answers))
    assert answers == [True]


def test_instance_server_emits_summon_requested_on_knock(server: InstanceServer) -> None:
    received: list[None] = []
    server.summon_requested.connect(lambda: received.append(None))

    _knock_from_another_thread()

    assert _wait_for(lambda: bool(received))


def test_instance_server_ignores_unknown_messages(server: InstanceServer, mocker: MockerFixture) -> None:
    received: list[None] = []
    server.summon_requested.connect(lambda: received.append(None))
    connection = mocker.Mock()
    connection.readAll.return_value = b"hello"

    server._read(connection)

    assert received == []
    connection.disconnectFromServer.assert_called_once()


def test_instance_server_emits_ask_requested_with_the_file(server: InstanceServer, mocker: MockerFixture) -> None:
    asked: list[str] = []
    server.ask_requested.connect(asked.append)
    connection = mocker.Mock()
    connection.readAll.return_value = ASK_PREFIX + "C:/Docs/Résumé.pdf".encode()

    server._read(connection)

    assert asked == ["C:/Docs/Résumé.pdf"]
