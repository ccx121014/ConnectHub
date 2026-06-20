"""
Application Entry Point for Online Collaboration Suite
Main application setup with event loop integration.
"""

import sys
import logging
import signal
from typing import Optional
from pathlib import Path

# Add project root and client dir to path for module imports (cross-platform)
_project_root = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(_project_root))
sys.path.insert(0, str(Path(__file__).parent))

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QPixmap
from PyQt5.QtWidgets import (
    QApplication,
    QMessageBox,
    QSplashScreen,
    QLabel,
)

from protocol.messages import Message, MessageType, create_message
from websocket_client import WebSocketClient
from main_window import MainWindow
from login_dialog import LoginDialog
from updater import notify_update_async, CURRENT_VERSION

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class CollaborationApp(QApplication):
    """
    Main application class for the collaboration suite.
    Manages application lifecycle, windows, and event handling.
    """

    def __init__(self, argv):
        super().__init__(argv)

        self.setApplicationName("在线协作套件")
        self.setApplicationVersion(CURRENT_VERSION)
        self.setOrganizationName("ConnectHub")

        # Set application font
        font = QFont()
        font.setFamily("Microsoft YaHei")
        font.setPointSize(10)
        self.setFont(font)

        # Application state
        self._username: Optional[str] = None
        self._server: Optional[str] = None
        self._port: Optional[int] = None
        self._ws_client: Optional[WebSocketClient] = None
        self._main_window: Optional[MainWindow] = None
        self._login_dialog: Optional[LoginDialog] = None

        # Handle Ctrl+C
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        logger.info("Application initialized (v%s)", CURRENT_VERSION)

    def _handle_signal(self, signum, frame):
        """Handle system signals for graceful shutdown."""
        logger.info(f"Received signal {signum}, shutting down...")
        self.quit()

    def run(self):
        """Run the application."""
        logger.info("Starting application...")

        # Create and show login dialog first
        self._show_login_dialog()

        # Start the event loop
        return self.exec_()

    def _show_login_dialog(self):
        """Show the login dialog."""
        self._login_dialog = LoginDialog()
        self._login_dialog.connect_request.connect(self._on_connect_request)
        self._login_dialog.register_request.connect(self._on_register_request)
        self._login_dialog.finished.connect(self._on_login_dialog_finished)

        self._login_dialog.show()

    def _on_connect_request(self, server: str, port: int, username: str, password: str):
        """Handle connect request from login dialog."""
        logger.info(f"Connect request: server={server}, port={port}, username={username}")
        self._start_session(server, port, username, password, mode="connect")

    def _on_register_request(self, server: str, port: int, username: str, password: str):
        """Handle register request from login dialog."""
        logger.info(f"Register request: server={server}, port={port}, username={username}")
        self._start_session(server, port, username, password, mode="register")

    def _start_session(self, server: str, port: int, username: str, password: str, mode: str):
        """Start a new WebSocket session."""
        self._server = server
        self._port = port
        self._username = username
        self._mode = mode

        self._ws_client = WebSocketClient(server, port)
        self._ws_client.set_credentials(username, password)

        # 所有信号都来自 self._ws_client.signals (SignalBridge)
        self._ws_client.signals.connected.connect(self._on_websocket_connected)
        self._ws_client.signals.error_occurred.connect(self._on_websocket_error)
        self._ws_client.signals.message_received.connect(self._on_message_received)
        self._ws_client.signals.connection_failed.connect(self._on_connection_failed)
        self._ws_client.start()

    def _on_websocket_connected(self):
        """Handle WebSocket connected event — fire auth request."""
        logger.info("WebSocket connected")
        if self._login_dialog:
            self._login_dialog.show_success("连接成功!")
        if self._ws_client and self._username:
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

    def _on_websocket_error(self, error: str):
        """Handle WebSocket error."""
        logger.error(f"WebSocket error: {error}")
        if self._login_dialog:
            self._login_dialog.show_error(error)

    def _on_connection_failed(self, error: str):
        """Handle connection failed event."""
        logger.error(f"Connection failed: {error}")
        if self._login_dialog:
            self._login_dialog.show_error(error)

    def _on_message_received(self, message):
        """Handle received message during login phase."""
        logger.debug(f"Message received: {message.type}")

        if message.type != MessageType.AUTH_RESPONSE:
            return

        success = message.payload.get("success", False)
        if success:
            logger.info("Authentication successful")
            self._on_auth_success()
        else:
            error = message.payload.get("error", "认证失败")
            logger.error(f"Authentication failed: {error}")
            if self._login_dialog:
                self._login_dialog.show_error(error)
            if self._ws_client:
                self._ws_client.stop()
                self._ws_client = None

    def _on_auth_success(self):
        """Handle successful authentication — open main window."""
        if self._login_dialog:
            # 关键：先断开 finished 信号，避免 close() 同步触发 quit()
            try:
                self._login_dialog.finished.disconnect(self._on_login_dialog_finished)
            except TypeError:
                pass  # 信号未被连接
            self._login_dialog.close()
            self._login_dialog = None

        self._main_window = MainWindow()
        self._main_window.set_username(self._username)
        self._main_window.set_websocket_client(self._ws_client)
        self._main_window.logout_requested.connect(self._on_logout_requested)
        self._main_window.show()

        self._ws_client.request_contact_list()
        self._ws_client.request_user_list()

        # 启动后异步检查是否有新版本
        try:
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(2000, lambda: notify_update_async(self._main_window))
        except Exception:
            pass

        logger.info("Main window displayed")

    def _on_login_dialog_finished(self, result):
        """Handle login dialog finished."""
        logger.info("Login dialog finished")
        if result == 0 and self._main_window is None:
            # User cancelled, quit application
            self.quit()

    def _on_logout_requested(self):
        """Handle logout request from main window."""
        logger.info("Logout requested")

        # Stop WebSocket client
        if self._ws_client:
            self._ws_client.stop()
            self._ws_client = None

        # Close main window
        if self._main_window:
            self._main_window.close()
            self._main_window = None

        # Show login dialog again
        self._show_login_dialog()


def main():
    """Main entry point."""
    # Enable high DPI scaling
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = CollaborationApp(sys.argv)

    # Set application style
    app.setStyle("Fusion")

    # Run the application
    sys.exit(app.run())


if __name__ == "__main__":
    main()
