"""
Makes sure only one Nimbus runs per user: a second launch tells the first one to show its
window, then exits — two copies would fight over the hotkey and the API port. Owns the local
socket handshake only.
"""

from __future__ import annotations

import getpass

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

from core.logger import get_logger

logger = get_logger(__name__)

CONNECT_TIMEOUT_MS = 500
SUMMON_MESSAGE = b"summon"


def _server_name() -> str:
    """Per-user, so two people signed in to the same PC each get their own Nimbus."""
    return f"nimbus-{getpass.getuser()}"


def notify_running_instance() -> bool:
    """Asks an already-running Nimbus to show itself. True if one answered."""
    socket = QLocalSocket()
    socket.connectToServer(_server_name())
    if not socket.waitForConnected(CONNECT_TIMEOUT_MS):
        return False
    socket.write(SUMMON_MESSAGE)
    socket.flush()
    socket.waitForBytesWritten(CONNECT_TIMEOUT_MS)
    # Disconnecting waits for unsent data, but only while the socket object is alive — so wait
    # here rather than let the local socket be destroyed with the message still queued.
    socket.disconnectFromServer()
    if socket.state() != QLocalSocket.LocalSocketState.UnconnectedState:
        socket.waitForDisconnected(CONNECT_TIMEOUT_MS)
    return True


class InstanceServer(QObject):
    """Listens for later launches and emits summon_requested when one knocks."""

    summon_requested = pyqtSignal()

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
        if bytes(connection.readAll()).strip() == SUMMON_MESSAGE:
            self.summon_requested.emit()
        connection.disconnectFromServer()
