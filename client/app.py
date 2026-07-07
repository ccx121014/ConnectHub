"""
Application Entry Point for Online Collaboration Suite
基于 tkinter 的主应用程序：登录 -> 认证 -> 主窗口 -> 登出循环。
替代原先依赖 PyQt5 的 QApplication 版本。

关键机制：
- WebSocket 客户端的所有 Signal 回调都在后台线程中被 emit，为保证 UI 安全，
  我们把这些回调统一通过 queue.Queue 投递到 tkinter 主线程。
- tkinter 主线程通过 after(0, ...) 轮询该队列，并在主线程执行 UI 操作。
- 主窗口 MainWindow 目前是一个极简骨架，占位实现，后续由其他子代理补完。
"""

import sys

# --- 注入 ssl stub（PyInstaller 排除 OpenSSL 后的最小兼容层）---
if "ssl" not in sys.modules:
    from client import ssl_stub

    sys.modules["ssl"] = ssl_stub

import logging
import signal as _signal
import queue
import threading
import tkinter as tk
from tkinter import ttk
from pathlib import Path

_project_root = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(_project_root))
sys.path.insert(0, str(Path(__file__).parent))

from protocol.signals import Signal, SignalBridge
from protocol.messages import Message, MessageType, create_message
from websocket_client import WebSocketClient
from login_dialog import LoginDialog
from main_window import MainWindow

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------
# 主线程封送器
# -----------------------------------------------------------------------
class TkMainThreadDispatcher:
    """
    将任意回调封送到 tkinter 主线程执行。

    用法：
        dispatcher = TkMainThreadDispatcher(root)
        # 给 Signal 连接一个包装器：
        signal.connect(dispatcher.wrap(callback))
        # 然后 start_poll() 开启 after 轮询

    它使用一个 queue.Queue 以及 after(interval, ...)，既不会阻塞 tkinter，
    也不会让后台线程直接操作 UI 组件。
    """

    def __init__(self, root: tk.Tk, interval_ms: int = 30):
        self._root = root
        self._interval_ms = interval_ms
        self._queue: "queue.Queue[tuple]" = queue.Queue()
        self._lock = threading.Lock()
        self._polling = False

    def start_poll(self):
        with self._lock:
            if self._polling:
                return
            self._polling = True
        self._schedule_next()

    def stop_poll(self):
        with self._lock:
            self._polling = False

    def _schedule_next(self):
        try:
            self._root.after(self._interval_ms, self._drain_and_reschedule)
        except Exception:
            # root 可能已销毁
            with self._lock:
                self._polling = False

    def _drain_and_reschedule(self):
        with self._lock:
            if not self._polling:
                return
            # 立刻安排下一次轮询，避免本帧 callback 抛异常导致断档
            self._schedule_next.__self__  # 占位，无实际意义
        try:
            # 从队列取出并立即运行；限单次取若干项避免拖死主循环
            for _ in range(64):
                try:
                    func, args, kwargs = self._queue.get_nowait()
                except queue.Empty:
                    break
                try:
                    func(*args, **kwargs)
                except Exception:
                    logger.exception("Dispatched callback raised")
        finally:
            # 重新安排下一轮
            try:
                self._root.after(self._interval_ms, self._drain_and_reschedule)
            except Exception:
                with self._lock:
                    self._polling = False

    def wrap(self, callback):
        """返回一个包装回调：将 callback 的执行投递到主线程。"""

        def _wrapped(*args, **kwargs):
            # 避免在自身线程内无意义封装：如果当前线程就是 tkinter 主线程，直接调
            if threading.current_thread() is threading.main_thread():
                try:
                    callback(*args, **kwargs)
                except Exception:
                    logger.exception("Direct callback raised")
                return
            try:
                self._queue.put((callback, args, kwargs))
            except Exception:
                # queue 满 / 其它异常 — 直接丢弃并记录
                logger.exception("Failed to queue callback for main thread")

        return _wrapped


# -----------------------------------------------------------------------
# 主应用
# -----------------------------------------------------------------------
class CollaborationApp:
    """
    主应用程序 —— 负责：
    1. 创建 tk.Tk 根窗口（默认隐藏）
    2. 显示 LoginDialog
    3. 处理 connect_request / register_request 并启动 WebSocket 客户端
    4. 监听 ws_client.signals 并在主线程更新 UI / 发送 AUTH
    5. 认证成功后创建 MainWindow 并显示
    6. 主窗口登出后重新显示登录对话框
    """

    def __init__(self):
        self._root = tk.Tk()
        self._root.withdraw()  # 初始隐藏
        self._root.title("ConnectHub")
        self._root.geometry("1000x700")

        # 主线程封送器
        self._dispatcher = TkMainThreadDispatcher(self._root)
        self._dispatcher.start_poll()

        # 应用状态
        self._username = None
        self._server = None
        self._port = None
        self._mode = None  # "connect" 或 "register"
        self._ws_client = None
        self._main_window = None
        self._login_dialog = None

        # 处理 Ctrl+C 以便优雅退出
        try:
            _signal.signal(_signal.SIGINT, self._handle_signal)
            _signal.signal(_signal.SIGTERM, self._handle_signal)
        except Exception:
            pass

        # tk 关闭按钮：调用 self.quit
        self._root.protocol("WM_DELETE_WINDOW", self.quit)

    # --- 公共入口 -------------------------------------------------------
    def run(self):
        """启动应用：显示登录对话，进入 tkinter 主循环。"""
        logger.info("Starting application...")
        self._show_login_dialog()
        try:
            self._root.mainloop()
        finally:
            self._dispatcher.stop_poll()

    def quit(self):
        logger.info("Quit requested, stopping ws client and exiting.")
        if self._ws_client is not None:
            try:
                self._ws_client.stop()
            except Exception:
                pass
            self._ws_client = None
        self._dispatcher.stop_poll()
        try:
            self._root.destroy()
        except Exception:
            pass

    # --- 登录流程 -------------------------------------------------------
    def _show_login_dialog(self):
        if self._login_dialog is not None:
            try:
                self._login_dialog.close()
            except Exception:
                pass
            self._login_dialog = None

        # 构造 LoginDialog —— 若没有显式 master，则用我们的 self._root
        self._login_dialog = LoginDialog(self._root)
        self._login_dialog.connect_request.connect(self._on_connect_request)
        self._login_dialog.register_request.connect(self._on_register_request)
        self._login_dialog.show()

    def _on_connect_request(self, server: str, port: int, username: str, password: str):
        logger.info("Connect request: server=%s, port=%s, username=%s", server, port, username)
        self._start_session(server, port, username, password, mode="connect")

    def _on_register_request(self, server: str, port: int, username: str, password: str):
        logger.info("Register request: server=%s, port=%s, username=%s", server, port, username)
        self._start_session(server, port, username, password, mode="register")

    def _start_session(self, server, port, username, password, mode):
        # 保存参数
        self._server = server
        self._port = port
        self._username = username
        self._mode = mode

        # 创建 WebSocketClient
        self._ws_client = WebSocketClient(server, port)
        self._ws_client.set_credentials(username, password)

        # 连接 SignalBridge 上的信号 —— 所有回调经过主线程封送
        disp = self._dispatcher
        self._ws_client.signals.connected.connect(disp.wrap(self._on_ws_connected))
        self._ws_client.signals.error_occurred.connect(disp.wrap(self._on_ws_error))
        self._ws_client.signals.connection_failed.connect(disp.wrap(self._on_connection_failed))
        self._ws_client.signals.message_received.connect(disp.wrap(self._on_message_received))
        self._ws_client.signals.disconnected.connect(disp.wrap(self._on_ws_disconnected))

        # 启动（在后台线程中运行 asyncio 事件循环）
        self._ws_client.start()

    # --- WebSocket 事件 -------------------------------------------------
    def _on_ws_connected(self):
        logger.info("WebSocket connected")
        if self._login_dialog is not None:
            self._login_dialog.show_success("连接成功!")
        if self._ws_client is None or self._username is None:
            return

        if self._mode == "register":
            msg = create_message(
                MessageType.AUTH_REQUEST,
                sender=self._username,
                username=self._username,
                password="",
                register=True,
            )
            self._ws_client.send(msg)
        else:
            self._ws_client.send_auth_request(self._username, "")

    def _on_ws_error(self, error: str):
        logger.error("WebSocket error: %s", error)
        if self._login_dialog is not None:
            self._login_dialog.show_error(error)

    def _on_connection_failed(self, error: str):
        logger.error("Connection failed: %s", error)
        if self._login_dialog is not None:
            self._login_dialog.show_error(error)
        if self._ws_client is not None:
            try:
                self._ws_client.stop()
            except Exception:
                pass
            self._ws_client = None

    def _on_ws_disconnected(self):
        logger.info("WebSocket disconnected")

    def _on_message_received(self, message: Message):
        logger.debug("Message received: %s", message.type)
        # 目前只处理 AUTH_RESPONSE，其他消息留给未来主窗口处理
        if message.type != MessageType.AUTH_RESPONSE:
            return

        success = message.payload.get("success", False) if isinstance(message.payload, dict) else False
        if success:
            logger.info("Authentication successful")
            self._on_auth_success()
        else:
            err = ""
            if isinstance(message.payload, dict):
                err = str(message.payload.get("error", "认证失败"))
            else:
                err = "认证失败"
            logger.error("Authentication failed: %s", err)
            if self._login_dialog is not None:
                self._login_dialog.show_error(err)
            if self._ws_client is not None:
                try:
                    self._ws_client.stop()
                except Exception:
                    pass
                self._ws_client = None

    # --- 认证成功 / 登出 -------------------------------------------------
    def _on_auth_success(self):
        # 关闭登录对话框
        if self._login_dialog is not None:
            try:
                self._login_dialog.close()
            except Exception:
                pass
            self._login_dialog = None

        # 创建 / 显示主窗口
        if self._main_window is None:
            self._main_window = MainWindow(self._root)
            self._main_window.logout_requested.connect(self._dispatcher.wrap(self._on_logout_requested))

        self._main_window.set_username(self._username)
        self._main_window.set_websocket_client(self._ws_client)
        self._main_window.set_status("已连接")
        self._main_window.show()

        if self._ws_client is not None:
            try:
                self._ws_client.request_contact_list()
                self._ws_client.request_user_list()
            except Exception:
                logger.exception("Failed to request contact/user list")

        logger.info("Main window displayed for user=%s", self._username)

    def _on_logout_requested(self):
        logger.info("Logout requested")
        # 停 ws
        if self._ws_client is not None:
            try:
                self._ws_client.send_logout()
            except Exception:
                pass
            try:
                self._ws_client.stop()
            except Exception:
                pass
            self._ws_client = None

        # 隐藏主窗口
        if self._main_window is not None:
            self._main_window.close()

        # 重置用户名
        self._username = None
        # 重新显示登录对话框
        self._show_login_dialog()

    # --- 信号处理 -------------------------------------------------------
    def _handle_signal(self, signum, frame):
        logger.info("Received signal %s, shutting down...", signum)
        # 使用 after 保证在主线程中执行 quit
        try:
            self._root.after(0, self.quit)
        except Exception:
            sys.exit(0)


# -----------------------------------------------------------------------
# 入口
# -----------------------------------------------------------------------
def main():
    app = CollaborationApp()
    sys.exit(app.run() or 0)


if __name__ == "__main__":
    main()
