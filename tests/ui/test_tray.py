from __future__ import annotations

from pathlib import Path

import httpx
import pystray
from PIL import Image
from pytest_mock import MockerFixture

from models.schema import IndexStatus
from ui.tray import TrayIcon, _load_icon_image, _notify_safely, _post_for_status, _settings_file_path


def _tray() -> TrayIcon:
    tray = TrayIcon()
    tray.setup()
    return tray


def test_setup_builds_a_menu_with_all_four_actions() -> None:
    tray = _tray()

    labels = [item.text for item in tray._icon.menu]

    assert labels == ["Pause Indexing", "Rebuild Index", "Open Settings", "Quit"]


def test_pause_resume_label_reflects_the_current_state() -> None:
    tray = _tray()
    assert tray._pause_resume_label(None) == "Pause Indexing"

    tray._is_paused = True

    assert tray._pause_resume_label(None) == "Resume Indexing"


def test_toggle_pause_calls_pause_endpoint_and_updates_state(mocker: MockerFixture) -> None:
    tray = _tray()
    mocker.patch("ui.tray._post_for_status", return_value=IndexStatus(
        total_files=0, indexed_files=0, pending=0, is_paused=True, last_error=None
    ))
    icon = mocker.Mock(spec=pystray.Icon)

    tray._toggle_pause(icon, mocker.Mock())

    assert tray._is_paused is True
    icon.update_menu.assert_called_once()


def test_toggle_pause_calls_resume_endpoint_when_already_paused(mocker: MockerFixture) -> None:
    tray = _tray()
    tray._is_paused = True
    status_spy = mocker.patch("ui.tray._post_for_status", return_value=IndexStatus(
        total_files=0, indexed_files=0, pending=0, is_paused=False, last_error=None
    ))
    icon = mocker.Mock(spec=pystray.Icon)

    tray._toggle_pause(icon, mocker.Mock())

    status_spy.assert_called_once_with("/index/resume")
    assert tray._is_paused is False


def test_toggle_pause_notifies_when_the_server_is_unreachable(mocker: MockerFixture) -> None:
    tray = _tray()
    mocker.patch("ui.tray._post_for_status", return_value=None)
    icon = mocker.Mock(spec=pystray.Icon)

    tray._toggle_pause(icon, mocker.Mock())

    icon.notify.assert_called_once()
    icon.update_menu.assert_not_called()


def test_rebuild_index_posts_to_the_rebuild_endpoint(mocker: MockerFixture) -> None:
    tray = _tray()
    post_spy = mocker.patch("ui.tray.httpx.post")
    icon = mocker.Mock(spec=pystray.Icon)

    tray._rebuild_index(icon, mocker.Mock())

    url = post_spy.call_args[0][0]
    assert url.endswith("/index/rebuild")
    icon.notify.assert_not_called()


def test_rebuild_index_notifies_on_a_connection_failure(mocker: MockerFixture) -> None:
    tray = _tray()
    mocker.patch("ui.tray.httpx.post", side_effect=httpx.ConnectError("refused"))
    icon = mocker.Mock(spec=pystray.Icon)

    tray._rebuild_index(icon, mocker.Mock())

    icon.notify.assert_called_once()


def test_open_settings_opens_the_resolved_settings_path(mocker: MockerFixture) -> None:
    tray = _tray()
    startfile = mocker.patch("ui.tray.os.startfile")
    mocker.patch("ui.tray._settings_file_path", return_value=Path("C:/Nimbus/.env"))
    icon = mocker.Mock(spec=pystray.Icon)

    tray._open_settings(icon, mocker.Mock())

    startfile.assert_called_once_with(Path("C:/Nimbus/.env"))
    icon.notify.assert_not_called()


def test_open_settings_notifies_when_the_os_cannot_open_it(mocker: MockerFixture) -> None:
    tray = _tray()
    mocker.patch("ui.tray.os.startfile", side_effect=OSError("no association"))
    mocker.patch("ui.tray._settings_file_path", return_value=Path("C:/Nimbus/.env"))
    icon = mocker.Mock(spec=pystray.Icon)

    tray._open_settings(icon, mocker.Mock())

    icon.notify.assert_called_once()


def test_quit_stops_the_icon_and_runs_the_shutdown_hook(mocker: MockerFixture) -> None:
    on_quit = mocker.Mock()
    tray = TrayIcon(on_quit=on_quit)
    tray.setup()
    icon = mocker.Mock(spec=pystray.Icon)

    tray._quit(icon, mocker.Mock())

    icon.stop.assert_called_once()
    on_quit.assert_called_once()


def test_quit_is_safe_with_no_shutdown_hook(mocker: MockerFixture) -> None:
    tray = _tray()
    icon = mocker.Mock(spec=pystray.Icon)

    tray._quit(icon, mocker.Mock())

    icon.stop.assert_called_once()


def test_post_for_status_parses_the_response_body(mocker: MockerFixture) -> None:
    fake_response = mocker.Mock()
    fake_response.json.return_value = {
        "total_files": 0, "indexed_files": 0, "pending": 0, "is_paused": True, "last_error": None
    }
    mocker.patch("ui.tray.httpx.post", return_value=fake_response)

    status = _post_for_status("/index/pause")

    assert status.is_paused is True


def test_post_for_status_returns_none_on_a_connection_failure(mocker: MockerFixture) -> None:
    mocker.patch("ui.tray.httpx.post", side_effect=httpx.ConnectError("refused"))

    assert _post_for_status("/index/pause") is None


def test_notify_safely_swallows_an_unsupported_notification(mocker: MockerFixture) -> None:
    icon = mocker.Mock(spec=pystray.Icon)
    icon.notify.side_effect = NotImplementedError

    _notify_safely(icon, "hello")  # must not raise


def test_settings_file_path_prefers_the_real_env_file_when_present() -> None:
    path = _settings_file_path()

    assert path.name == ".env"


def test_settings_file_path_falls_back_to_the_template_when_env_is_missing(mocker: MockerFixture) -> None:
    mocker.patch("ui.tray.Path.exists", return_value=False)

    path = _settings_file_path()

    assert path.name == ".env.example"


def test_load_icon_image_returns_a_real_256x256_image() -> None:
    image = _load_icon_image()

    assert isinstance(image, Image.Image)
    assert image.size == (256, 256)
