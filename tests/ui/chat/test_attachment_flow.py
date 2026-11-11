from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest
from PyQt6.QtGui import QGuiApplication
from pytest_mock import MockerFixture

from models.chat import Attachment
from ui.chat.attachment_bar import COPIED_TEXT_NAME, SCREENSHOT_NAME, AttachmentBar
from ui.chat.attachment_flow import MIN_CLIPBOARD_CHARS, AttachmentFlow
from ui.chat.chat_session import ChatSession

COPIED = "The quarterly numbers are attached below for review."


@pytest.fixture
def bar(qapp: object) -> AttachmentBar:
    return AttachmentBar()


@pytest.fixture
def session(mocker: MockerFixture) -> Mock:
    return mocker.Mock(spec=ChatSession)


@pytest.fixture
def clipboard(mocker: MockerFixture) -> Mock:
    fake = mocker.Mock()
    fake.text.return_value = COPIED
    fake.ownsClipboard.return_value = False
    mocker.patch.object(QGuiApplication, "clipboard", return_value=fake)
    return fake


def test_offer_clipboard_offers_fresh_copied_text(bar: AttachmentBar, session: Mock, clipboard: Mock) -> None:
    AttachmentFlow(bar, session).offer_clipboard()

    assert bar.is_offering()


def test_offer_clipboard_offers_the_same_text_only_once(bar: AttachmentBar, session: Mock, clipboard: Mock) -> None:
    flow = AttachmentFlow(bar, session)
    flow.offer_clipboard()
    bar.clear()

    flow.offer_clipboard()

    assert not bar.is_offering()


def test_offer_clipboard_skips_short_text(bar: AttachmentBar, session: Mock, clipboard: Mock) -> None:
    clipboard.text.return_value = "x" * (MIN_CLIPBOARD_CHARS - 1)

    AttachmentFlow(bar, session).offer_clipboard()

    assert not bar.is_offering()


def test_offer_clipboard_skips_text_nimbus_copied_itself(bar: AttachmentBar, session: Mock, clipboard: Mock) -> None:
    clipboard.ownsClipboard.return_value = True

    AttachmentFlow(bar, session).offer_clipboard()

    assert not bar.is_offering()


def test_offer_clipboard_waits_while_something_is_attached(bar: AttachmentBar, session: Mock, clipboard: Mock) -> None:
    flow = AttachmentFlow(bar, session)
    flow._show(Attachment(name="report.pdf", path="C:/report.pdf"))

    flow.offer_clipboard()

    assert not bar.is_offering()


def test_accepting_the_offer_attaches_the_copied_text(bar: AttachmentBar, session: Mock, clipboard: Mock) -> None:
    flow = AttachmentFlow(bar, session)
    flow.offer_clipboard()

    flow._accept_offer()

    session.attach.assert_called_once_with(Attachment(name=COPIED_TEXT_NAME, text=COPIED))


def test_attach_file_attaches_it_by_name_and_path(bar: AttachmentBar, session: Mock) -> None:
    AttachmentFlow(bar, session).attach_file("C:/Docs/Q3.pdf")

    session.attach.assert_called_once_with(Attachment(name="Q3.pdf", path="C:/Docs/Q3.pdf"))


def test_attach_screenshot_names_it_screenshot(bar: AttachmentBar, session: Mock) -> None:
    shot = Path("C:/shots/a.png")

    AttachmentFlow(bar, session).attach_screenshot(shot)

    session.attach.assert_called_once_with(Attachment(name=SCREENSHOT_NAME, path=str(shot)))
