"""
WebSocket Client for Online Collaboration Suite
- 关键点：
  * WebSocketClient 是纯 Python 对象（不继承 QObject）——避免 Qt 线程亲和/对象生命周期问题）
  * 所有跨线程信号由独立的 SignalBridge(QObject) 承载
  * asyncio 事件循环运行在独立的 Python daemon thread 中，与 Qt 主线程完全隔离
"""

import asyncio
import logging
import threading
import time
from pathlib import Path
from typing import Optional
import sys as _sys

_project_root = Path(__file__).parent.parent.resolve()
_sys.path.insert(0, str(_project_root))
_sys.path.insert(0, str(Path(__file__).parent))

from PyQt5.QtCore import QObject, pyqtSignal  # 仅用于 SignalBridge

from protocol.messages import Message, MessageType, parse_message, create_message

logger = logging.getLogger(__name__)


class SignalBridge(QObject):
    """
    专用于承载跨线程信号 — 仅在主线程创建并持有。
    子线程只负责 emit，槽也在主线程被 Qt 自动排队执行。
    """
    connected = pyqtSignal()
    disconnected = pyqtSignal()
    error_occurred = pyqtSignal(str)
    message_received = pyqtSignal(object)    # Message 以 object 透传
    reconnecting = pyqtSignal(int)
    connection_failed = pyqtSignal(str)


class WebSocketClient:
    """
    纯 Python WebSocket 客户端，不继承 QObject。
    通过 self.signals (SignalBridge) 与 Qt 交互。
    """

    def __init__(self, host: str = "localhost", port: int = 8765):
        self.host = host
        self.port = port
        self.uri = f"ws://{host}:{port}"

        # 唯一的 QObject 子类，必须在创建者（主线程）创建
        self.signals = SignalBridge()

        self._websocket = None
        self._connected = False
        self._closing = False
        self._reconnect_attempt = 0
        self._max_reconnect_attempts = 2

        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._main_task: Optional[asyncio.Task] = None

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

    # --- 启动/停止 ---

    def start(self):
        """在后台线程中启动事件循环。"""
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
        """停止客户端 — 通过取消主协程让事件循环优雅结束，不阻塞调用者。"""
        logger.info("Stopping WebSocket client...")
        self._closing = True
        loop = self._loop
        main_task = self._main_task
        if loop and loop.is_running() and main_task and not main_task.done():
            try:
                loop.call_soon_threadsafe(main_task.cancel)
            except Exception:
                pass

    # --- 事件循环 ---

    def _run_event_loop(self):
        """后台线程中的 asyncio 事件循环。"""
        loop = None
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loop = loop

            main_task = loop.create_task(self._main_loop())
            self._main_task = main_task
            try:
                loop.run_until_complete(main_task)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"Event loop crashed: {e}", exc_info=True)
        finally:
            self._main_task = None
            if loop is not None:
                try:
                    # 收集所有未完成任务并取消它们，避免 Task was destroyed 警告
                    pending = [
                        t for t in asyncio.all_tasks(loop)
                        if t is not main_task and not t.done()
                    ]
                    if pending:
                        for t in pending:
                            t.cancel()
                        loop.run_until_complete(
                            asyncio.gather(*pending, return_exceptions=True)
                        )
                except Exception:
                    pass
                try:
                    loop.close()
                except Exception:
                    pass
            self._loop = None
            with self._state_lock:
                self._connected = False
            logger.info("WebSocket client thread stopped")

    async def _main_loop(self):
        """主循环：连接/断线重连。"""
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
                try:
                    self.signals.connection_failed.emit(error_msg)
                except RuntimeError:
                    # QObject 已被销毁
                    pass
                break

            delay = min(1 * self._reconnect_attempt, 3)
            logger.info(f"Reconnecting in {delay}s (attempt {self._reconnect_attempt})")
            try:
                self.signals.reconnecting.emit(self._reconnect_attempt)
            except RuntimeError:
                pass

            try:
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                break

        with self._state_lock:
            if self._connected:
                self._connected = False
                try:
                    self.signals.disconnected.emit()
                except RuntimeError:
                    pass

    async def _connect_and_run(self):
        """连接并处理消息。"""
        import websockets

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
                logger.debug(f"Params failed: {e}")
                continue
            except ConnectionRefusedError:
                logger.warning(f"Connection refused — is the server running at {self.uri}?")
                continue
            except OSError as e:
                logger.warning(f"OS error: {e}")
                continue
            except Exception as e:
                logger.warning(f"Connect failed: {e}")
                continue

        if conn is None:
            raise RuntimeError(f"Could not connect to {self.uri}")

        self._websocket = conn
        with self._state_lock:
            self._connected = True

        try:
            self.signals.connected.emit()
        except RuntimeError:
            pass

        try:
            async for raw_message in conn:
                if self._closing:
                    break
                try:
                    parsed = parse_message(raw_message)
                    logger.debug(f"Received: {parsed.type}")
                    try:
                        self.signals.message_received.emit(parsed)
                    except RuntimeError:
                        break
                except Exception as e:
                    logger.warning(f"Failed to parse message: {e}")
        except websockets.exceptions.ConnectionClosed:
            logger.info("Server closed connection")
        except asyncio.CancelledError:
            raise  # 让上层 _main_loop 处理，同时触发 finally
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
                self.signals.disconnected.emit()
            except RuntimeError:
                pass

    async def _send_async(self, message: Message):
        """在事件循环内部发送消息。"""
        ws = self._websocket
        if not ws:
            return
        # 检查连接是否仍可用
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

    # --- 对外发送接口 ---

    def send(self, message: Message):
        """线程安全地从 Qt/UI 线程发送消息。"""
        loop = self._loop
        if loop and loop.is_running() and self._websocket is not None:
            try:
                future = asyncio.run_coroutine_threadsafe(
                    self._send_async(message), loop
                )
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

    def send_file_transfer_request(self, target, file_name, file_size, file_id, chunk_count, chunk_size):
        msg = create_message(
            MessageType.FILE_TRANSFER_REQUEST,
            sender=self._username or "",
            target=target,
            file_name=file_name, file_size=file_size,
            file_id=file_id, chunk_count=chunk_count, chunk_size=chunk_size,
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

    def send_file_transfer_data(self, target: str, file_id: str, chunk_index: int, data: str):
        msg = create_message(
            MessageType.FILE_TRANSFER_DATA,
            sender=self._username or "",
            target=target,
            file_id=file_id,
            chunk_index=chunk_index,
            data=data,
        )
        self.send(msg)

    def send_file_transfer_complete(self, target: str, file_id: str, total_chunks: int):
        msg = create_message(
            MessageType.FILE_TRANSFER_COMPLETE,
            sender=self._username or "",
            target=target,
            file_id=file_id,
            total_chunks=total_chunks,
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

    def send_desktop_frame(self, target: str, image_data: str, width: int, height: int):
        msg = Message(
            type=MessageType.DESKTOP_FRAME,
            sender=self._username or "",
            target=target,
            payload={"image_data": image_data, "width": width, "height": height},
            timestamp=time.time(),
            message_id=str(uuid.uuid4()),
        )
        self.send(msg)

    def send_desktop_stop(self, target: str):
        msg = create_message(
            MessageType.DESKTOP_STOP,
            sender=self._username or "",
            target=target,
        )
        self.send(msg)

    def send_logout(self):
        msg = create_message(
            MessageType.AUTH_LOGOUT,
            sender=self._username or "",
        )
        self.send(msg)
        self._closing = True
