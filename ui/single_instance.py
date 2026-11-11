"""
Makes sure only one Nimbus runs per user: a second launch tells the first one to show its
window (or, from File Explorer's menu, which file to ask about), then exits. Two copies would
fight over the hotkey and the API port. Owns the local socket handshake only.
"""

from __future__ import annotations

import getpass

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

from core.logger import get_logger

logger = get_logger(__name__)

CONNECT_TIMEOUT_MS = 500
SUMMON_MESSAGE = b"summon"
ASK_PREFIX = b"ask\t"


def _server_name() -> str:
    """Per-user, so two people signed in to the same PC each get their own Nimbus."""
    return f"nimbus-{getpass.getuser()}"


def notify_running_instance(ask_path: str | None = None) -> bool:
    """Asks an already-running Nimbus to show itself, about ask_path if given. True if one
    answered."""
    socket = QLocalSocket()
    socket.connectToServer(_server_name())
    if not socket.waitForConnected(CONNECT_TIMEOUT_MS):
        return False
    socket.write(ASK_PREFIX + ask_path.encode("utf-8") if ask_path else SUMMON_MESSAGE)
    socket.flush()
    socket.waitForBytesWritten(CONNECT_TIMEOUT_MS)
    # Disconnecting waits for unsent data, but only while the socket object is alive, so wait
    # here rather than let the local socket be destroyed with the message still queued.
    socket.disconnectFromServer()
    if socket.state() != QLocalSocket.LocalSocketState.UnconnectedState:
        socket.waitForDisconnected(CONNECT_TIMEOUT_MS)
    return True


class InstanceServer(QObject):
    """Listens for later launches: summon_requested when one knocks, ask_requested(path) when
    it came from File Explorer's "Ask Nimbus about this"."""

    summon_requested = pyqtSignal()
    ask_requested = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self._server = QLocalServer(self)

    def listen(self) -> None:
        # A crashed previous run can leave a stale socket behind; clear it before listening.
        QLocalServer.removeServer(_server_name())
        if not self._server.listen(_server_name()):
            logger.warning("Single-instance guard unavailable", extra={"error": self._server.errorString()})
            return
        self._server.newConnection.connect(self._accept)

    def _accept(self) -> None:
        connection = self._server.nextPendingConnection()
        if connection is not None:
            connection.readyRead.connect(lambda: self._read(connection))

    def _read(self, connection: QLocalSocket) -> None:
        message = bytes(connection.readAll()).strip()
        if message.startswith(ASK_PREFIX):
            self.ask_requested.emit(message.removeprefix(ASK_PREFIX).decode("utf-8", errors="replace"))
        elif message == SUMMON_MESSAGE:
            self.summon_requested.emit()
        connection.disconnectFromServer()
