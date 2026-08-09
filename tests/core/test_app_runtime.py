from __future__ import annotations

import time
from pathlib import Path

from pytest_mock import MockerFixture

from core.app_runtime import AppRuntime, _build_indexing_resources, _run_initial_index_in_background
from core.file_watcher import IndexingState
from core.indexer import Indexer


def test_build_indexing_resources_connects_the_store_and_returns_fresh_state(mocker: MockerFixture) -> None:
    store_cls = mocker.patch("core.app_runtime.VectorStore")
    indexer_cls = mocker.patch("core.app_runtime.Indexer")
    mocker.patch("core.app_runtime.get_embedder")

    store, indexer, state = _build_indexing_resources()

    store_cls.return_value.connect.assert_called_once()
    assert store is store_cls.return_value
    assert indexer is indexer_cls.return_value
    assert isinstance(state, IndexingState)


def test_run_initial_index_indexes_every_watched_directory_and_seeds_state(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    (tmp_path / "report.txt").write_text("hello")
    mocker.patch("core.app_runtime.get_settings", return_value=mocker.Mock(watched_dirs=[tmp_path]))
    indexer = mocker.Mock(spec=Indexer)
    state = IndexingState()

    _run_initial_index_in_background(indexer, state)
    time.sleep(0.2)

    indexer.index_directory.assert_called_once_with(tmp_path)
    assert state.indexed_files == 1


def test_run_initial_index_skips_a_watched_directory_that_does_not_exist(mocker: MockerFixture, tmp_path: Path) -> None:
    missing = tmp_path / "nope"
    mocker.patch("core.app_runtime.get_settings", return_value=mocker.Mock(watched_dirs=[missing]))
    indexer = mocker.Mock(spec=Indexer)
    state = IndexingState()

    _run_initial_index_in_background(indexer, state)
    time.sleep(0.2)

    indexer.index_directory.assert_not_called()


def test_wire_api_state_populates_app_state_with_the_shared_instances(mocker: MockerFixture) -> None:
    mocker.patch("core.app_runtime.get_embedder")
    mocker.patch("core.app_runtime.get_provider")
    server_module = mocker.patch("core.app_runtime.server_module")
    runtime = AppRuntime()
    store, indexer, state = mocker.Mock(), mocker.Mock(spec=Indexer), IndexingState()

    runtime._wire_api_state(store, indexer, state)

    assert server_module.app.state.store is store
    assert server_module.app.state.indexer is indexer
    assert server_module.app.state.indexing_state is state


def test_start_uvicorn_binds_to_loopback_only(mocker: MockerFixture) -> None:
    mocker.patch("core.app_runtime.get_settings", return_value=mocker.Mock(api_port=8765))
    mocker.patch("core.app_runtime.server_module")
    config_cls = mocker.patch("core.app_runtime.uvicorn.Config")
    mocker.patch("core.app_runtime.uvicorn.Server")
    mocker.patch("core.app_runtime.threading.Thread")
    runtime = AppRuntime()

    runtime._start_uvicorn()

    _args, kwargs = config_cls.call_args
    assert kwargs["host"] == "127.0.0.1"
    assert kwargs["port"] == 8765


def test_start_overlay_and_hotkey_wires_summoned_to_summon(mocker: MockerFixture) -> None:
    overlay_cls = mocker.patch("core.app_runtime.OverlayWindow")
    query_client_cls = mocker.patch("core.app_runtime.QueryClient")
    hotkey_cls = mocker.patch("core.app_runtime.HotkeyListener")
    mocker.patch("core.app_runtime.get_settings", return_value=mocker.Mock(hotkey="<ctrl>+<space>"))
    runtime = AppRuntime()

    runtime._start_overlay_and_hotkey()

    overlay_cls.return_value.setup.assert_called_once()
    query_client_cls.assert_called_once_with(overlay_cls.return_value)
    query_client_cls.return_value.setup.assert_called_once()
    hotkey_cls.return_value.summoned.connect.assert_called_once_with(overlay_cls.return_value.summon)
    hotkey_cls.return_value.start.assert_called_once()


def test_start_tray_wires_on_quit_to_request_shutdown(mocker: MockerFixture) -> None:
    tray_cls = mocker.patch("core.app_runtime.TrayIcon")
    runtime = AppRuntime()

    runtime._start_tray()

    tray_cls.assert_called_once_with(on_quit=runtime._request_shutdown)
    tray_cls.return_value.setup.assert_called_once()
    tray_cls.return_value.run_detached.assert_called_once()


def test_request_shutdown_stops_every_subsystem_and_emits_shutdown(mocker: MockerFixture) -> None:
    runtime = AppRuntime()
    runtime._server = mocker.Mock()
    runtime._server_thread = mocker.Mock()
    runtime._file_watcher = mocker.Mock()
    runtime._hotkey = mocker.Mock()
    received = []
    runtime._shutdown_requested.connect(lambda: received.append(1))

    runtime._request_shutdown()

    assert runtime._server.should_exit is True
    runtime._file_watcher.stop.assert_called_once()
    runtime._hotkey.stop.assert_called_once()
    runtime._server_thread.join.assert_called_once()
    assert received == [1]


def test_request_shutdown_is_safe_when_nothing_was_started() -> None:
    runtime = AppRuntime()

    runtime._request_shutdown()  # must not raise


def test_start_builds_every_subsystem_and_returns_the_qt_exit_code(mocker: MockerFixture) -> None:
    mocker.patch("core.app_runtime.get_settings", return_value=mocker.Mock(api_port=8765, hotkey="<ctrl>+<space>"))
    qt_app_cls = mocker.patch("core.app_runtime.QApplication")
    qt_app_cls.instance.return_value.exec.return_value = 0
    mocker.patch("core.app_runtime.server_module")
    mocker.patch("core.app_runtime.uvicorn.Config")
    mocker.patch("core.app_runtime.uvicorn.Server")
    mocker.patch("core.app_runtime.threading.Thread")
    mocker.patch("core.app_runtime.get_embedder")
    mocker.patch("core.app_runtime.get_provider")
    mocker.patch("core.app_runtime.VectorStore")
    mocker.patch("core.app_runtime.Indexer")
    mocker.patch("core.app_runtime.OverlayWindow")
    mocker.patch("core.app_runtime.QueryClient")
    mocker.patch("core.app_runtime.HotkeyListener")
    file_watcher_cls = mocker.patch("core.app_runtime.FileWatcher")
    tray_cls = mocker.patch("core.app_runtime.TrayIcon")
    mocker.patch("core.app_runtime._run_initial_index_in_background")
    runtime = AppRuntime()

    exit_code = runtime.start()

    file_watcher_cls.return_value.setup.assert_called_once()
    file_watcher_cls.return_value.start.assert_called_once()
    tray_cls.return_value.run_detached.assert_called_once()
    qt_app_cls.instance.return_value.exec.assert_called_once()
    assert exit_code == 0
