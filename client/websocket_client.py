"""
WebSocket Client for Online Collaboration Suite
Handles async communication with the server using websockets library.
Uses Python threading + asyncio to avoid blocking the Qt UI thread.
"""

import asyncio
import logging
import threading
import time
from typing import Optional, Callable, Dict, Any
from pathlib import Path
import sys as _sys

_project_root = Path(__file__).parent.parent.resolve()
_sys.path.insert(0, str(_project_root))
_sys.path.insert(0, str(Path(__file__).parent))

from PyQt5.QtCore import QObject, pyqtSignal

from protocol.messages import Message, MessageType, parse_message, create_message

logger = logging.getLogger(__name__)


class WebSocketClient(QObject):
    """
    WebSocket client with async message handling.
    Runs asyncio event loop in a separate Python thread.
    Qt signals are used for cross-thread communication with the UI.

    All signals use the generic 'object' type to ensure reliable delivery
    across thread boundaries (PyQt cannot serialize custom Python types
    in its meta-object system).
    """

    connected = pyqtSignal()
    disconnected = pyqtSignal()
    error_occurred = pyqtSignal(str)
    message_received = pyqtSignal(object)
    reconnecting = pyqtSignal(int)
    connection_failed = pyqtSignal(str)

    def __init__(self, host: str = "localhost", port: int = 8765, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.host = host
        self.port = port
        self.uri = f"ws://{host}:{port}"

        self._websocket = None
        self._connected = False
        self._closing = False
        self._reconnect_attempt = 0
        self._max_reconnect_attempts = 2

        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        self._username: Optional[str] = None
        self._password: Optional[str] = None

        self._state_lock = threading.Lock()

    @property
    def is_connected(self) -> bool:
        with self._state_lock:
            return self._connected

    def set_credentials(self, username: str, password: str):
        self._username = username
        self._password = password

    def start(self):
        """Start the WebSocket client in a background thread."""
        with self._state_lock:
            if self._thread and self._thread.is_alive():
                logger.warning("WebSocket client already running")
                return
            self._closing = False
            self._connected = False
            self._thread = threading.Thread(
                target=self._run_event_loop,
                name="WebSocketClient",
                daemon=True,
            )
        self._thread.start()
        logger.info(f"WebSocket client thread started for {self.uri}")

    def stop(self):
        """Stop the WebSocket client without blocking the caller."""
        logger.info("Stopping WebSocket client...")
        self._closing = True
        loop = self._loop
        if loop and loop.is_running():
            try:
                loop.call_soon_threadsafe(lambda: loop.stop())
            except Exception:
                pass

    def _run_event_loop(self):
        """Run the asyncio event loop in the background thread."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loop = loop
            loop.run_until_complete(self._main_loop())
        except Exception as e:
            logger.error(f"Event loop crashed: {e}", exc_info=True)
        finally:
            try:
                if self._loop and not self._loop.is_closed():
                    self._loop.close()
            except Exception:
                pass
            self._loop = None
            with self._state_lock:
                self._connected = False
            logger.info("WebSocket client thread stopped")

    async def _main_loop(self):
        """Main connection/reconnection loop."""
        self._reconnect_attempt = 0

        while not self._closing:
            try:
                await self._connect_and_run()
            except asyncio.CancelledError:
                logger.info("Main loop cancelled")
                break
            except Exception as e:
                logger.warning(f"Connection failed: {e}")

            if self._closing:
                break

            self._reconnect_attempt += 1
            if self._reconnect_attempt > self._max_reconnect_attempts:
                error_msg = f"连接失败：无法连接到 {self.uri}"
                logger.error(error_msg)
                self.connection_failed.emit(error_msg)
                break

            delay = min(1 * self._reconnect_attempt, 3)
            logger.info(f"Reconnecting in {delay}s (attempt {self._reconnect_attempt})")
            self.reconnecting.emit(self._reconnect_attempt)

            try:
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                break

        with self._state_lock:
            if self._connected:
                self._connected = False
                try:
                    self.disconnected.emit()
                except Exception:
                    pass

    async def _connect_and_run(self):
        """Connect to the server and process messages."""
        import websockets

        # 先尝试最简参数，再尝试带 ping 参数；每组超时 5s — 避免用户等待过久
        conn = None
        param_sets = [
            dict(),
            dict(ping_interval=30, ping_timeout=10),
        ]
        for params in param_sets:
            if self._closing:
                return
            try:
                logger.info(f"Connecting to {self.uri} (params: {list(params.keys())})")
                conn = await asyncio.wait_for(
                    websockets.connect(self.uri, **params),
                    timeout=5,
                )
                logger.info(f"Connected to {self.uri}")
                break
            except asyncio.TimeoutError:
                logger.warning("Connection timed out (5s)")
                continue
            except (TypeError, ValueError) as e:
                logger.debug(f"Params failed ({params}): {e}")
                continue
            except ConnectionRefusedError:
                logger.warning(f"Connection refused — is the server running at {self.uri}?")
                continue
            except OSError as e:
                logger.warning(f"OS error connecting: {e}")
                continue
            except Exception as e:
                logger.warning(f"Connect failed: {e}")
                continue

        if conn is None:
            raise RuntimeError(f"Could not connect to {self.uri}")

        self._websocket = conn
        with self._state_lock:
            self._connected = True
        self.connected.emit()

        try:
            async for raw_message in conn:
                if self._closing:
                    break
                try:
                    parsed = parse_message(raw_message)
                    logger.debug(f"Received: {parsed.type}")
                    self.message_received.emit(parsed)
                except Exception as e:
                    logger.warning(f"Failed to parse message: {e}")
        except websockets.exceptions.ConnectionClosed:
            logger.info("Server closed connection")
        except Exception as e:
            logger.warning(f"Message loop error: {e}")
        finally:
            with self._state_lock:
                self._connected = False
            try:
                await conn.close()
            except Exception:
                pass
            self._websocket = None
            try:
                self.disconnected.emit()
            except Exception:
                pass

    async def _send_async(self, message: Message):
        """Send a message (called within the event loop)."""
        ws = self._websocket
        if not ws:
            return
        # 跨版本兼容地检查连接是否仍可用：
        # - 旧版 websockets 使用 .open
        # - 新版使用 .closed (bool) 或 .close_code
        is_alive = True
        if hasattr(ws, "closed") and isinstance(ws.closed, bool):
            is_alive = not ws.closed
        elif hasattr(ws, "open") and isinstance(ws.open, bool):
            is_alive = ws.open
        elif hasattr(ws, "close_code"):
            is_alive = ws.close_code is None
        if not is_alive:
            return
        try:
            await asyncio.wait_for(ws.send(message.to_json()), timeout=5)
        except asyncio.TimeoutError:
            logger.warning("Send timed out")
        except Exception as e:
            logger.debug(f"Send failed: {e}")

    def send(self, message: Message):
        """Thread-safe: send a message from the Qt/UI thread."""
        loop = self._loop
        if loop and loop.is_running() and self._websocket is not None:
            try:
                # 使用 run_coroutine_threadsafe 以便有统一的异常出口
                future = asyncio.run_coroutine_threadsafe(
                    self._send_async(message), loop
                )
                # 无需等待结果，但加一个空回调避免"Future exception never retrieved"
                def _on_done(f):
                    try:
                        f.result()
                    except Exception:
                        pass
                future.add_done_callback(_on_done)
            except Exception as e:
                logger.debug(f"Failed to queue message: {e}")
        else:
            logger.debug("Cannot send: not connected or loop not running")

    def send_auth_request(self, username: str, password: str):
        self._username = username
        self._password = password
        msg = create_message(
            MessageType.AUTH_REQUEST,
            sender=username,
            username=username,
            password=password,
        )
        self.send(msg)

    def send_chat_message(self, target: str, content: str, message_type: str = "text"):
        msg = create_message(
            MessageType.CHAT_MESSAGE,
            sender=self._username or "",
            target=target,
            content=content,
            message_type=message_type,
        )
        self.send(msg)

    def send_group_message(self, group_id: str, content: str):
        msg = create_message(
            MessageType.GROUP_MESSAGE,
            sender=self._username or "",
            target=group_id,
            content=content,
        )
        self.send(msg)

    def send_status_update(self, status: str):
        msg = create_message(
            MessageType.USER_STATUS_UPDATE,
            sender=self._username or "",
            status=status,
        )
        self.send(msg)

    def request_contact_list(self):
        msg = create_message(
            MessageType.CONTACT_LIST_REQUEST,
            sender=self._username or "",
        )
        self.send(msg)

    def request_user_list(self):
        msg = create_message(
            MessageType.USER_LIST_REQUEST,
            sender=self._username or "",
        )
        self.send(msg)

    def send_file_transfer_request(self, target: str, file_name: str, file_size: int, file_id: str, chunk_count: int, chunk_size: int):
        msg = create_message(
            MessageType.FILE_TRANSFER_REQUEST,
            sender=self._username or "",
            target=target,
            file_name=file_name,
            file_size=file_size,
            file_id=file_id,
            chunk_count=chunk_count,
            chunk_size=chunk_size,
        )
        self.send(msg)

    def send_file_transfer_response(self, target: str, file_id: str, accepted: bool):
        msg = create_message(
            MessageType.FILE_TRANSFER_RESPONSE,
            sender=self._username or "",
            target=target,
            file_id=file_id,
            accepted=accepted,
        )
        self.send(msg)

    def send_desktop_share_request(self, target: str, share_type: str = "view"):
        msg = create_message(
            MessageType.DESKTOP_SHARE_REQUEST,
            sender=self._username or "",
            target=target,
            share_type=share_type,
        )
        self.send(msg)

    def send_desktop_share_response(self, target: str, accepted: bool, share_type: str = "view"):
        msg = create_message(
            MessageType.DESKTOP_SHARE_RESPONSE,
            sender=self._username or "",
            target=target,
            accepted=accepted,
            share_type=share_type,
        )
        self.send(msg)

    def send_logout(self):
        msg = create_message(
            MessageType.AUTH_LOGOUT,
            sender=self._username or "",
        )
        self.send(msg)
        self._closing = True
