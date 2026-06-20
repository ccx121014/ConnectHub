"""
WebSocket Client for Online Collaboration Suite
Handles async communication with the server using websockets library.
Integrates with Qt using QThread and signals/slots pattern.
"""

import asyncio
import logging
import threading
from typing import Optional, Callable, Dict, Any
from datetime import datetime


# Add project root and client dir to path for module imports (cross-platform)
from pathlib import Path
_project_root = Path(__file__).parent.parent.resolve()
import sys as _sys
_sys.path.insert(0, str(_project_root))
_sys.path.insert(0, str(Path(__file__).parent))

from PyQt5.QtCore import QObject, pyqtSignal, QThread
from PyQt5.QtWidgets import QMessageBox

from protocol.messages import Message, MessageType, parse_message, create_message

logger = logging.getLogger(__name__)


class WebSocketClient(QObject):
    """
    WebSocket client with async message handling and Qt signal/slot integration.
    Uses QThread to run the asyncio event loop without blocking the Qt UI.
    """

    # Signals for Qt integration
    connected = pyqtSignal()
    disconnected = pyqtSignal()
    error_occurred = pyqtSignal(str)
    message_received = pyqtSignal(Message)
    reconnecting = pyqtSignal(int)  # attempt number
    connection_failed = pyqtSignal(str)

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8765,
        parent: Optional[QObject] = None
    ):
        super().__init__(parent)
        self.host = host
        self.port = port
        self.uri = f"ws://{host}:{port}"

        self._websocket = None
        self._connected = False
        self._closing = False
        self._reconnect_attempt = 0
        self._max_reconnect_attempts = 3
        self._base_reconnect_delay = 1
        self._max_reconnect_delay = 5

        self._thread: Optional[QThread] = None
        self._loop: Optional[asyncio.Event] = None
        self._event_thread: Optional[threading.Thread] = None

        self._username: Optional[str] = None
        self._password: Optional[str] = None

    @property
    def is_connected(self) -> bool:
        return self._connected

    def set_credentials(self, username: str, password: str):
        """Set authentication credentials."""
        self._username = username
        self._password = password

    def start(self):
        """Start the WebSocket client in a separate thread."""
        if self._thread is not None:
            logger.warning("WebSocket client already started")
            return

        self._closing = False
        self._thread = QThread()
        self._thread.started.connect(self._run_event_loop)
        self._thread.start()

    def stop(self):
        """Stop the WebSocket client and close connections."""
        self._closing = True
        if self._loop:
            asyncio.run_coroutine_threadsafe(self._shutdown(), self._loop)
        if self._thread:
            self._thread.quit()
            self._thread.wait(3000)
            self._thread = None

    def _run_event_loop(self):
        """Run asyncio event loop in a separate thread."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._main_loop())
        self._loop.close()
        self._loop = None

    async def _main_loop(self):
        """Main async loop handling connection and reconnection."""
        while not self._closing:
            try:
                await self._connect()
                self._connected = True
                self._reconnect_attempt = 0
                self.connected.emit()
                logger.info("WebSocket connection established, entering message loop")

                async for raw_message in self._websocket:
                    if self._closing:
                        break
                    try:
                        parsed_message = parse_message(raw_message)
                        logger.debug(f"Received message: {parsed_message.type}")
                        self.message_received.emit(parsed_message)
                    except Exception as e:
                        logger.error(f"Error parsing message: {e}")

                logger.info("WebSocket message loop ended")

            except asyncio.CancelledError:
                logger.info("WebSocket connection cancelled")
                break
            except Exception as e:
                logger.error(f"WebSocket connection error: {e}", exc_info=True)
                self._connected = False
                self.disconnected.emit()

            if self._closing:
                break

            # Reconnection logic with exponential backoff
            self._reconnect_attempt += 1
            if self._reconnect_attempt > self._max_reconnect_attempts:
                error_msg = f"Failed to connect after {self._max_reconnect_attempts} attempts"
                logger.error(error_msg)
                self.connection_failed.emit(error_msg)
                break

            delay = min(
                self._base_reconnect_delay * (2 ** (self._reconnect_attempt - 1)),
                self._max_reconnect_delay
            )
            logger.info(f"Reconnecting in {delay}s (attempt {self._reconnect_attempt})")
            self.reconnecting.emit(self._reconnect_attempt)
            await asyncio.sleep(delay)

    async def _connect(self):
        """Establish WebSocket connection (with version fallback and timeout)."""
        import websockets

        uri = self.uri
        logger.info(f"Connecting to WebSocket server: {uri}")

        # Try connecting with various parameter sets for version compatibility
        conn = None
        for params in [
            dict(ping_interval=30, ping_timeout=10, close_timeout=5, open_timeout=10),
            dict(ping_interval=30, ping_timeout=10),
            dict(ping_timeout=10),
            dict(),  # minimal fallback
        ]:
            try:
                conn = await websockets.connect(uri, **params)
                logger.info(f"Connected to {uri} (params: {list(params.keys())})")
                break
            except (TypeError, ValueError) as e:
                logger.debug(f"Connect params failed ({params}): {e}")
                continue
            except Exception as e:
                logger.warning(f"Connect failed with params {params}: {e}")
                if not params:
                    raise  # re-raise if even minimal params failed
                continue

        if conn is None:
            raise RuntimeError(f"Could not connect to {uri} — all parameter sets failed")

        self._websocket = conn

    async def _shutdown(self):
        """Gracefully shutdown the connection."""
        if self._websocket:
            try:
                await self._websocket.close()
            except Exception:
                pass
        self._connected = False

    async def _send_async(self, message: Message):
        """Send a message asynchronously."""
        if self._websocket and self._connected:
            try:
                await self._websocket.send(message.to_json())
            except Exception as e:
                logger.error(f"Error sending message: {e}")
                raise

    def send(self, message: Message):
        """Send a message from Qt thread."""
        if self._loop and self._connected:
            asyncio.run_coroutine_threadsafe(self._send_async(message), self._loop)
        else:
            logger.warning("Cannot send message: not connected")

    def send_auth_request(self, username: str, password: str):
        """Send authentication request."""
        self._username = username
        self._password = password
        msg = create_message(
            MessageType.AUTH_REQUEST,
            sender=username,
            username=username,
            password=password
        )
        self.send(msg)

    def send_chat_message(self, target: str, content: str, message_type: str = "text"):
        """Send a chat message."""
        msg = create_message(
            MessageType.CHAT_MESSAGE,
            sender=self._username or "",
            target=target,
            content=content,
            message_type=message_type
        )
        self.send(msg)

    def send_group_message(self, group_id: str, content: str):
        """Send a group chat message."""
        msg = create_message(
            MessageType.GROUP_MESSAGE,
            sender=self._username or "",
            target=group_id,
            content=content
        )
        self.send(msg)

    def send_status_update(self, status: str):
        """Send user status update."""
        msg = create_message(
            MessageType.USER_STATUS_UPDATE,
            sender=self._username or "",
            status=status
        )
        self.send(msg)

    def request_contact_list(self):
        """Request contact list from server."""
        msg = create_message(
            MessageType.CONTACT_LIST_REQUEST,
            sender=self._username or ""
        )
        self.send(msg)

    def request_user_list(self):
        """Request online user list from server."""
        msg = create_message(
            MessageType.USER_LIST_REQUEST,
            sender=self._username or ""
        )
        self.send(msg)

    def send_file_transfer_request(
        self,
        target: str,
        file_name: str,
        file_size: int,
        file_id: str,
        chunk_count: int,
        chunk_size: int
    ):
        """Send file transfer request."""
        msg = create_message(
            MessageType.FILE_TRANSFER_REQUEST,
            sender=self._username or "",
            target=target,
            file_name=file_name,
            file_size=file_size,
            file_id=file_id,
            chunk_count=chunk_count,
            chunk_size=chunk_size
        )
        self.send(msg)

    def send_file_transfer_response(self, target: str, file_id: str, accepted: bool):
        """Send file transfer response."""
        msg = create_message(
            MessageType.FILE_TRANSFER_RESPONSE,
            sender=self._username or "",
            target=target,
            file_id=file_id,
            accepted=accepted
        )
        self.send(msg)

    def send_desktop_share_request(self, target: str, share_type: str = "view"):
        """Send remote desktop share request."""
        msg = create_message(
            MessageType.DESKTOP_SHARE_REQUEST,
            sender=self._username or "",
            target=target,
            share_type=share_type
        )
        self.send(msg)

    def send_desktop_share_response(self, target: str, accepted: bool, share_type: str = "view"):
        """Send remote desktop share response."""
        msg = create_message(
            MessageType.DESKTOP_SHARE_RESPONSE,
            sender=self._username or "",
            target=target,
            accepted=accepted,
            share_type=share_type
        )
        self.send(msg)

    def send_logout(self):
        """Send logout message."""
        msg = create_message(
            MessageType.AUTH_LOGOUT,
            sender=self._username or ""
        )
        self.send(msg)
        self._closing = True
