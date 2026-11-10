from __future__ import annotations

import ctypes
from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest
from PyQt6.QtWidgets import QApplication
from pytest_mock import MockerFixture

import api.server as server_module
from core.app_runtime import APP_USER_MODEL_ID, AppRuntime, _build_qt_app


class Engine(SimpleNamespace):
    qt_app: MagicMock
    notify: MagicMock
    services_cls: MagicMock
    services: MagicMock
    server_cls: MagicMock
    server: MagicMock
    shell_cls: MagicMock
    shell: MagicMock


@pytest.fixture
def engine(mocker: MockerFixture) -> Iterator[Engine]:
    """Every heavy piece of start(): Qt, the engine services, uvicorn and the desktop UI."""
    qt_app = mocker.Mock()
    qt_app.exec.return_value = 0
    mocker.patch("core.app_runtime._build_qt_app", return_value=qt_app)
    services_cls = mocker.patch("core.app_runtime.AppServices")
    server_cls = mocker.patch("core.app_runtime.uvicorn.Server")
    server_cls.return_value.started = True
    mocker.patch("core.app_runtime.uvicorn.Config")
    shell_cls = mocker.patch("core.app_runtime.DesktopShell")
    mocker.patch("core.app_runtime.ApiClient")
    previous_services = getattr(server_module.app.state, "services", None)
    yield Engine(
        qt_app=qt_app,
        notify=mocker.patch("core.app_runtime.notify_running_instance", return_value=False),
        services_cls=services_cls,
        services=services_cls.build.return_value,
        server_cls=server_cls,
        server=server_cls.return_value,
        shell_cls=shell_cls,
        shell=shell_cls.return_value,
    )
    server_module.app.state.services = previous_services


def test_start_exits_early_when_nimbus_is_already_running(engine: Engine) -> None:
    engine.notify.return_value = True

    exit_code = AppRuntime().start()

    assert exit_code == 0
    engine.services_cls.build.assert_not_called()
    engine.server_cls.assert_not_called()
    engine.shell_cls.assert_not_called()


def test_start_returns_the_event_loop_exit_code(engine: Engine) -> None:
    engine.qt_app.exec.return_value = 3

    assert AppRuntime().start() == 3


def test_start_hands_the_services_to_the_api(engine: Engine) -> None:
    AppRuntime().start()

    assert server_module.app.state.services is engine.services


def test_start_brings_up_server_then_engine_then_ui(engine: Engine) -> None:
    order = Mock()

    def create_server(config: object) -> MagicMock:
        order.server_created()
        return engine.server

    engine.server_cls.side_effect = create_server
    engine.services.start.side_effect = lambda: order.services_start()
    engine.shell.start.side_effect = lambda: order.shell_start()

    AppRuntime().start()

    assert [c[0] for c in order.mock_calls] == ["server_created", "services_start", "shell_start"]


def test_start_forwards_settings_changes_to_the_shell(engine: Engine) -> None:
    AppRuntime().start()

    engine.services.add_settings_listener.assert_called_once_with(engine.shell.settings_changed.emit)


def test_start_gives_the_shell_shutdown_as_its_quit_action(engine: Engine) -> None:
    runtime = AppRuntime()

    runtime.start()

    assert engine.shell_cls.call_args.kwargs["on_quit"] == runtime.shutdown


def test_start_server_binds_to_localhost_only(mocker: MockerFixture, engine: Engine) -> None:
    config_cls = mocker.patch("core.app_runtime.uvicorn.Config")

    AppRuntime().start()

    assert config_cls.call_args.kwargs["host"] == "127.0.0.1"
    assert config_cls.call_args.kwargs["port"] == 8765


def test_start_fails_when_the_api_never_comes_up(mocker: MockerFixture, engine: Engine) -> None:
    engine.server.started = False
    logger = mocker.patch("core.app_runtime.logger")

    with pytest.raises(RuntimeError):
        AppRuntime().start()

    logger.error.assert_called_once()
    engine.shell_cls.assert_not_called()
    engine.services.stop.assert_called_once()


def test_shutdown_stops_ui_then_server_then_engine(engine: Engine) -> None:
    runtime = AppRuntime()
    runtime.start()
    order = MagicMock()
    order.attach_mock(engine.shell.stop, "shell_stop")
    order.attach_mock(engine.services.stop, "services_stop")
    order.attach_mock(engine.qt_app.quit, "qt_quit")
    runtime._server_thread = Mock(join=Mock(side_effect=lambda timeout: order.server_join(engine.server.should_exit)))

    runtime.shutdown()

    assert [c[0] for c in order.mock_calls] == ["shell_stop", "server_join", "services_stop", "qt_quit"]
    order.server_join.assert_called_once_with(True)


def test_shutdown_before_start_does_not_crash() -> None:
    AppRuntime().shutdown()


def test_build_qt_app_configures_a_tray_style_app(mocker: MockerFixture) -> None:
    set_app_id = mocker.patch.object(ctypes.windll.shell32, "SetCurrentProcessExplicitAppUserModelID")
    app = QApplication.instance() or QApplication([])
    previous_stylesheet = app.styleSheet()

    try:
        built = _build_qt_app()
        assert built is app
        assert not built.quitOnLastWindowClosed()
        assert built.applicationName() == "Nimbus"
        assert "ChatContent" in built.styleSheet()
        set_app_id.assert_called_once_with(APP_USER_MODEL_ID)
    finally:
        app.setStyleSheet(previous_stylesheet)
        app.setQuitOnLastWindowClosed(True)


def test_start_tears_everything_down_when_the_ui_fails_to_start(engine: Engine) -> None:
    engine.shell.start.side_effect = RuntimeError("no tray available")

    with pytest.raises(RuntimeError):
        AppRuntime().start()

    assert engine.server.should_exit is True
    engine.services.stop.assert_called_once()
    engine.qt_app.exec.assert_not_called()
