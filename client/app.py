"""
Application Entry Point for Online Collaboration Suite
Main application setup with event loop integration.
"""

import sys
import logging
import signal
from typing import Optional

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QApplication,
    QMessageBox,
    QSplashScreen,
    QLabel,
    QPixmap,
)

from protocol.messages import Message, MessageType
from websocket_client import WebSocketClient
from main_window import MainWindow
from login_dialog import LoginDialog

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
        self.setApplicationVersion("1.0.0")
        self.setOrganizationName("CollaborationSuite")

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

        logger.info("Application initialized")

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

        self._server = server
        self._port = port
        self._username = username

        # Create WebSocket client
        self._ws_client = WebSocketClient(server, port)
        self._ws_client.set_credentials(username, password)

        # Connect signals
        self._ws_client.connected.connect(self._on_websocket_connected)
        self._ws_client.error_occurred.connect(self._on_websocket_error)
        self._ws_client.message_received.connect(self._on_message_received)
        self._ws_client.connection_failed.connect(self._on_connection_failed)

        # Start the WebSocket client
        self._ws_client.start()

    def _on_register_request(self, server: str, port: int, username: str, password: str):
        """Handle register request from login dialog."""
        logger.info(f"Register request: server={server}, port={port}, username={username}")

        self._server = server
        self._port = port
        self._username = username

        # Create WebSocket client for registration
        self._ws_client = WebSocketClient(server, port)
        self._ws_client.set_credentials(username, password)

        # Connect signals
        self._ws_client.connected.connect(self._on_websocket_connected_for_register)
        self._ws_client.error_occurred.connect(self._on_websocket_error)
        self._ws_client.message_received.connect(self._on_message_received)
        self._ws_client.connection_failed.connect(self._on_connection_failed)

        # Start the WebSocket client
        self._ws_client.start()

    def _on_websocket_connected(self):
        """Handle WebSocket connected event."""
        logger.info("WebSocket connected")
        if self._login_dialog:
            self._login_dialog.show_success("连接成功!")

        # Send auth request
        if self._ws_client and self._username:
            self._ws_client.send_auth_request(self._username, "")

    def _on_websocket_connected_for_register(self):
        """Handle WebSocket connected event for registration."""
        logger.info("WebSocket connected for registration")
        if self._login_dialog:
            self._login_dialog.show_success("连接成功，正在注册...")

        # Send register request - using auth_request with register flag
        if self._ws_client and self._username:
            from protocol.messages import create_message
            msg = create_message(
                MessageType.AUTH_REQUEST,
                sender=self._username,
                username=self._username,
                password="",
                register=True
            )
            self._ws_client.send(msg)

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

    def _on_message_received(self, message: Message):
        """Handle received message."""
        logger.debug(f"Message received: {message.type}")

        # Handle auth response
        if message.type == MessageType.AUTH_RESPONSE:
            success = message.payload.get("success", False)
            if success:
                logger.info("Authentication successful")
                self._on_auth_success()
            else:
                error = message.payload.get("error", "认证失败")
                logger.error(f"Authentication failed: {error}")
                if self._login_dialog:
                    self._login_dialog.show_error(error)
                # Stop the WebSocket client
                if self._ws_client:
                    self._ws_client.stop()
                    self._ws_client = None

    def _on_auth_success(self):
        """Handle successful authentication."""
        # Close login dialog
        if self._login_dialog:
            self._login_dialog.close()
            self._login_dialog = None

        # Create and show main window
        self._main_window = MainWindow()
        self._main_window.set_username(self._username)
        self._main_window.set_websocket_client(self._ws_client)
        self._main_window.logout_requested.connect(self._on_logout_requested)
        self._main_window.show()

        # Request initial data
        self._ws_client.request_contact_list()
        self._ws_client.request_user_list()

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
