"""
Main Window for Online Collaboration Suite
Provides tab-based interface with Contacts, Chat, File Transfer, and Remote Desktop tabs.
"""

import logging
import os
from typing import Optional


# Add project root and client dir to path for module imports (cross-platform)
from pathlib import Path
_project_root = Path(__file__).parent.parent.resolve()
import sys as _sys
_sys.path.insert(0, str(_project_root))
_sys.path.insert(0, str(Path(__file__).parent))

from PyQt5.QtCore import Qt, QTimer, pyqtSlot, pyqtSignal
from PyQt5.QtGui import QIcon, QCloseEvent
from PyQt5.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QStatusBar,
    QMenuBar,
    QMenu,
    QAction,
    QLabel,
    QMessageBox,
    QToolBar,
    QDockWidget,
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QFrame,
    QFileDialog,
    QProgressBar,
    QTextEdit,
    QGroupBox,
    QPushButton,
)

from protocol.messages import Message, MessageType
from websocket_client import WebSocketClient
from contact_list import ContactListWidget, UserStatus
from chat_widget import ChatTabWidget

logger = logging.getLogger(__name__)


class ConnectionStatusIndicator(QWidget):
    """
    Widget showing connection status with color indicator.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._status = "disconnected"

        self._init_ui()

    def _init_ui(self):
        """Initialize the user interface."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 0, 5, 0)
        layout.setSpacing(5)

        self.status_dot = QLabel()
        self.status_dot.setFixedSize(10, 10)
        self.status_dot.setStyleSheet("background-color: #9E9E9E; border-radius: 5px;")
        layout.addWidget(self.status_dot)

        self.status_text = QLabel("未连接")
        self.status_text.setStyleSheet("color: #757575; font-size: 12px;")
        layout.addWidget(self.status_text)

    def set_status(self, status: str):
        """Set the connection status."""
        self._status = status

        if status == "connected":
            self.status_dot.setStyleSheet("background-color: #4CAF50; border-radius: 5px;")
            self.status_text.setText("已连接")
            self.status_text.setStyleSheet("color: #4CAF50; font-size: 12px;")
        elif status == "connecting":
            self.status_dot.setStyleSheet("background-color: #FFC107; border-radius: 5px;")
            self.status_text.setText("连接中...")
            self.status_text.setStyleSheet("color: #FFC107; font-size: 12px;")
        elif status == "reconnecting":
            self.status_dot.setStyleSheet("background-color: #FF9800; border-radius: 5px;")
            self.status_text.setText("重新连接中...")
            self.status_text.setStyleSheet("color: #FF9800; font-size: 12px;")
        else:
            self.status_dot.setStyleSheet("background-color: #9E9E9E; border-radius: 5px;")
            self.status_text.setText("未连接")
            self.status_text.setStyleSheet("color: #757575; font-size: 12px;")


class FileTransferWidget(QWidget):
    """
    Widget for managing file transfers.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._transfers: Dict[str, Dict] = {}

        self._init_ui()

    def _init_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)

        # Header
        header_layout = QHBoxLayout()
        title = QLabel("文件传输")
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        header_layout.addWidget(title)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # Transfer list
        self.transfer_list = QListWidget()
        layout.addWidget(self.transfer_list)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

    def add_transfer(self, file_name: str, target: str, direction: str = "send"):
        """Add a new file transfer."""
        transfer_id = f"{file_name}_{target}_{direction}"
        self._transfers[transfer_id] = {
            "file_name": file_name,
            "target": target,
            "direction": direction,
            "progress": 0
        }

        item = QListWidgetItem(f"📄 {file_name} → {target}" if direction == "send" else f"📄 {file_name} ← {target}")
        item.setData(Qt.UserRole, transfer_id)
        self.transfer_list.addItem(item)

    def update_progress(self, transfer_id: str, progress: int):
        """Update transfer progress."""
        if transfer_id in self._transfers:
            self._transfers[transfer_id]["progress"] = progress
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(progress)

            # Find and update the list item
            for i in range(self.transfer_list.count()):
                item = self.transfer_list.item(i)
                if item.data(Qt.UserRole) == transfer_id:
                    file_name = self._transfers[transfer_id]["file_name"]
                    target = self._transfers[transfer_id]["target"]
                    direction = self._transfers[transfer_id]["direction"]
                    item.setText(
                        f"📄 {file_name} → {target} ({progress}%)" if direction == "send"
                        else f"📄 {file_name} ← {target} ({progress}%)"
                    )
                    break

            if progress >= 100:
                QTimer.singleShot(2000, lambda: self.progress_bar.setVisible(False))

    def remove_transfer(self, transfer_id: str):
        """Remove a completed transfer."""
        if transfer_id in self._transfers:
            del self._transfers[transfer_id]

            for i in range(self.transfer_list.count()):
                item = self.transfer_list.item(i)
                if item.data(Qt.UserRole) == transfer_id:
                    self.transfer_list.takeItem(i)
                    break


class RemoteDesktopWidget(QWidget):
    """
    Widget for remote desktop sharing and control.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sharing = False
        self._viewing = False

        self._init_ui()

    def _init_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)

        # Header
        header_layout = QHBoxLayout()
        title = QLabel("远程桌面")
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        header_layout.addWidget(title)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # Status
        self.status_label = QLabel("未共享桌面")
        self.status_label.setStyleSheet("color: #757575; padding: 10px;")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)

        # Desktop preview placeholder
        self.preview_label = QLabel("桌面预览区域")
        self.preview_label.setMinimumSize(400, 300)
        self.preview_label.setStyleSheet(
            "background-color: #2D2D2D; color: #757575; border-radius: 5px;"
        )
        self.preview_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.preview_label)

        # Control buttons
        button_layout = QHBoxLayout()

        self.share_button = QPushButton("共享我的桌面")
        self.share_button.clicked.connect(self._on_share_clicked)
        button_layout.addWidget(self.share_button)

        self.view_button = QPushButton("查看对方桌面")
        self.view_button.setEnabled(False)
        button_layout.addWidget(self.view_button)

        self.stop_button = QPushButton("停止")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self._on_stop_clicked)
        button_layout.addWidget(self.stop_button)

        layout.addLayout(button_layout)

        # Info text
        info_text = QLabel("共享桌面允许其他人查看或控制您的屏幕。\n收到共享请求时，点击'查看对方桌面'接受。")
        info_text.setStyleSheet("color: #9E9E9E; font-size: 11px;")
        info_text.setAlignment(Qt.AlignCenter)
        info_text.setWordWrap(True)
        layout.addWidget(info_text)

        layout.addStretch()

    def _on_share_clicked(self):
        """Handle share button click."""
        if not self._sharing:
            self._sharing = True
            self.share_button.setEnabled(False)
            self.view_button.setEnabled(True)
            self.stop_button.setEnabled(True)
            self.status_label.setText("正在共享桌面...")
            self.status_label.setStyleSheet("color: #4CAF50; padding: 10px;")
            logger.info("Desktop sharing started")

    def _on_stop_clicked(self):
        """Handle stop button click."""
        self._sharing = False
        self._viewing = False
        self.share_button.setEnabled(True)
        self.view_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self.status_label.setText("未共享桌面")
        self.status_label.setStyleSheet("color: #757575; padding: 10px;")
        self.preview_label.setText("桌面预览区域")
        logger.info("Desktop sharing stopped")

    def request_view_desktop(self, username: str):
        """Handle desktop view request from another user."""
        reply = QMessageBox.question(
            self,
            "桌面共享请求",
            f"用户 {username} 请求查看您的桌面。",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self._on_share_clicked()


class MainWindow(QMainWindow):
    """
    Main application window with tab-based interface.
    Signals:
        logout_requested: Emitted when user logs out
    """

    logout_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._username: Optional[str] = None
        self._ws_client: Optional[WebSocketClient] = None

        self._init_ui()
        self._create_menus()
        self._create_toolbars()
        self._create_status_bar()

    def _init_ui(self):
        """Initialize the user interface."""
        self.setWindowTitle("在线协作套件")
        self.setMinimumSize(900, 600)

        # Central widget with tab interface
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        main_layout = QVBoxLayout(self.central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Create splitter for contact list + chat area
        splitter = QSplitter(Qt.Horizontal)

        # Left side - Contact list in a dock
        self.contact_list_widget = ContactListWidget()
        self.contact_list_widget.contact_double_clicked.connect(self._on_contact_double_clicked)
        self.contact_list_widget.start_chat_request.connect(self._on_start_chat)
        self.contact_list_widget.start_file_transfer.connect(self._on_file_transfer_request)
        self.contact_list_widget.start_desktop_share.connect(self._on_desktop_share_request)

        contacts_dock = QDockWidget("联系人", self)
        contacts_dock.setWidget(self.contact_list_widget)
        contacts_dock.setMaximumWidth(250)
        self.addDockWidget(Qt.LeftDockWidgetArea, contacts_dock)

        # Right side - Tab widget for chats and other features
        self.tab_widget = QTabWidget()

        # Chat tab
        self.chat_tab = ChatTabWidget()
        self.chat_tab.message_sent.connect(self._on_message_sent)
        self.tab_widget.addTab(self.chat_tab, "💬 聊天")

        # File transfer tab
        self.file_transfer_widget = FileTransferWidget()
        self.tab_widget.addTab(self.file_transfer_widget, "📁 文件传输")

        # Remote desktop tab
        self.remote_desktop_widget = RemoteDesktopWidget()
        self.tab_widget.addTab(self.remote_desktop_widget, "🖥️ 远程桌面")

        splitter.addWidget(self.tab_widget)
        splitter.setSizes([700, 200])

        main_layout.addWidget(splitter)

        # Connection status indicator
        self.connection_indicator = ConnectionStatusIndicator()

    def _create_menus(self):
        """Create the menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("文件(&F)")

        logout_action = QAction("退出登录(&L)", self)
        logout_action.setShortcut("Ctrl+Q")
        logout_action.triggered.connect(self._on_logout)
        file_menu.addAction(logout_action)

        file_menu.addSeparator()

        exit_action = QAction("退出(&X)", self)
        exit_action.setShortcut("Ctrl+Shift+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Edit menu
        edit_menu = menubar.addMenu("编辑(&E)")

        copy_action = QAction("复制(&C)", self)
        copy_action.setShortcut("Ctrl+C")
        edit_menu.addAction(copy_action)

        paste_action = QAction("粘贴(&V)", self)
        paste_action.setShortcut("Ctrl+V")
        edit_menu.addAction(paste_action)

        # View menu
        view_menu = menubar.addMenu("视图(&V)")

        contacts_action = QAction("显示/隐藏联系人", self)
        contacts_action.setShortcut("Ctrl+T")
        view_menu.addAction(contacts_action)

        fullscreen_action = QAction("全屏", self)
        fullscreen_action.setShortcut("F11")
        fullscreen_action.triggered.connect(self._toggle_fullscreen)
        view_menu.addAction(fullscreen_action)

        # Help menu
        help_menu = menubar.addMenu("帮助(&H)")

        about_action = QAction("关于", self)
        about_action.triggered.connect(self._on_about)
        help_menu.addAction(about_action)

        help_action = QAction("使用帮助", self)
        help_action.setShortcut("F1")
        help_menu.addAction(help_action)

    def _create_toolbars(self):
        """Create toolbars."""
        # Main toolbar
        main_toolbar = QToolBar("主工具栏")
        main_toolbar.setMovable(False)
        self.addToolBar(main_toolbar)

        # Connection status to toolbar
        main_toolbar.addWidget(QLabel("状态: "))
        main_toolbar.addWidget(self.connection_indicator)

        main_toolbar.addSeparator()

        # Quick actions
        refresh_action = QAction("刷新联系人", self)
        refresh_action.triggered.connect(self._refresh_contacts)
        main_toolbar.addAction(refresh_action)

    def _create_status_bar(self):
        """Create the status bar."""
        self.statusBar().showMessage("就绪")

    def set_websocket_client(self, client: WebSocketClient):
        """Set the WebSocket client for communication."""
        self._ws_client = client
        client.message_received.connect(self._on_message_received)
        client.connected.connect(self._on_connected)
        client.disconnected.connect(self._on_disconnected)
        client.reconnecting.connect(self._on_reconnecting)
        client.connection_failed.connect(self._on_connection_failed)

    def set_username(self, username: str):
        """Set the current username."""
        self._username = username
        self.setWindowTitle(f"在线协作套件 - {username}")
        self.contact_list_widget.set_username(username)
        self.chat_tab.set_username(username)

    def _on_contact_double_clicked(self, username: str):
        """Handle contact double click - start chat."""
        self.chat_tab.open_chat(username, is_group=False)

    def _on_start_chat(self, username: str):
        """Handle start chat request."""
        self.chat_tab.open_chat(username, is_group=False)
        self.tab_widget.setCurrentWidget(self.chat_tab)

    def _on_file_transfer_request(self, username: str):
        """Handle file transfer request."""
        self.tab_widget.setCurrentWidget(self.file_transfer_widget)
        QMessageBox.information(
            self,
            "文件传输",
            f"文件传输功能将连接到 {username}"
        )

    def _on_desktop_share_request(self, username: str, share_type: str):
        """Handle desktop share request."""
        if self._ws_client:
            self._ws_client.send_desktop_share_request(username, share_type)
            self.tab_widget.setCurrentWidget(self.remote_desktop_widget)
            QMessageBox.information(
                self,
                "远程桌面",
                f"已向 {username} 发送桌面共享请求"
            )

    def _on_message_sent(self, target: str, content: str):
        """Handle message sent event."""
        if self._ws_client and content:
            self._ws_client.send_chat_message(target, content)

    @pyqtSlot(Message)
    def _on_message_received(self, message: Message):
        """Handle incoming message."""
        try:
            if message.type == MessageType.AUTH_RESPONSE:
                self._handle_auth_response(message)
            elif message.type == MessageType.CHAT_MESSAGE:
                self._handle_chat_message(message)
            elif message.type == MessageType.GROUP_MESSAGE:
                self._handle_group_message(message)
            elif message.type == MessageType.USER_STATUS_UPDATE:
                self._handle_status_update(message)
            elif message.type == MessageType.CONTACT_LIST_RESPONSE:
                self._handle_contact_list_response(message)
            elif message.type == MessageType.USER_LIST_RESPONSE:
                self._handle_user_list_response(message)
            elif message.type == MessageType.FILE_TRANSFER_REQUEST:
                self._handle_file_transfer_request(message)
            elif message.type == MessageType.DESKTOP_SHARE_REQUEST:
                self._handle_desktop_share_request(message)
            elif message.type == MessageType.ERROR:
                self._handle_error(message)
        except Exception as e:
            logger.error(f"Error handling message: {e}")

    def _handle_auth_response(self, message: Message):
        """Handle authentication response."""
        success = message.payload.get("success", False)
        if success:
            self.statusBar().showMessage(f"登录成功: {self._username}")
        else:
            error = message.payload.get("error", "认证失败")
            self.statusBar().showMessage(f"登录失败: {error}")

    def _handle_chat_message(self, message: Message):
        """Handle incoming chat message."""
        sender = message.sender
        content = message.payload.get("content", "")
        timestamp = message.timestamp

        from datetime import datetime
        ts = datetime.fromtimestamp(timestamp) if timestamp else datetime.now()

        self.chat_tab.add_message_to_chat(sender, sender, content, ts)

    def _handle_group_message(self, message: Message):
        """Handle incoming group message."""
        sender = message.sender
        target = message.target
        content = message.payload.get("content", "")
        timestamp = message.timestamp

        from datetime import datetime
        ts = datetime.fromtimestamp(timestamp) if timestamp else datetime.now()

        self.chat_tab.add_message_to_chat(target, sender, content, ts)

    def _handle_status_update(self, message: Message):
        """Handle user status update."""
        user = message.sender
        status_str = message.payload.get("status", "offline")
        try:
            status = UserStatus(status_str)
        except ValueError:
            status = UserStatus.OFFLINE
        self.contact_list_widget.update_contact_status(user, status)

    def _handle_contact_list_response(self, message: Message):
        """Handle contact list response."""
        contacts = message.payload.get("contacts", [])
        self.contact_list_widget.set_contacts(contacts)

    def _handle_user_list_response(self, message: Message):
        """Handle user list response."""
        users = message.payload.get("users", [])
        for user_data in users:
            username = user_data.get("username", "")
            status_str = user_data.get("status", "offline")
            try:
                status = UserStatus(status_str)
            except ValueError:
                status = UserStatus.OFFLINE
            self.contact_list_widget.update_contact_status(username, status)

    def _handle_file_transfer_request(self, message: Message):
        """Handle file transfer request."""
        sender = message.sender
        file_name = message.payload.get("file_name", "未知文件")
        file_size = message.payload.get("file_size", 0)

        reply = QMessageBox.question(
            self,
            "文件传输请求",
            f"用户 {sender} 请求发送文件:\n{file_name} ({file_size} bytes)\n\n是否接受?",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self._ws_client.send_file_transfer_response(sender, message.payload.get("file_id", ""), True)
            self.file_transfer_widget.add_transfer(file_name, sender, "receive")
        else:
            self._ws_client.send_file_transfer_response(sender, message.payload.get("file_id", ""), False)

    def _handle_desktop_share_request(self, message: Message):
        """Handle desktop share request."""
        sender = message.sender
        share_type = message.payload.get("share_type", "view")

        reply = QMessageBox.question(
            self,
            "远程桌面请求",
            f"用户 {sender} 请求{('控制' if share_type == 'control' else '查看')}您的桌面。\n\n是否接受?",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self._ws_client.send_desktop_share_response(sender, True, share_type)
            self.remote_desktop_widget.request_view_desktop(sender)
        else:
            self._ws_client.send_desktop_share_response(sender, False, share_type)

    def _handle_error(self, message: Message):
        """Handle error message."""
        error = message.payload.get("error", "未知错误")
        self.statusBar().showMessage(f"错误: {error}")
        QMessageBox.warning(self, "错误", error)

    def _on_connected(self):
        """Handle connected event."""
        self.connection_indicator.set_status("connected")
        self.statusBar().showMessage("已连接到服务器")
        if self._username:
            self._ws_client.request_contact_list()
            self._ws_client.request_user_list()

    def _on_disconnected(self):
        """Handle disconnected event."""
        self.connection_indicator.set_status("disconnected")
        self.statusBar().showMessage("已断开连接")

    def _on_reconnecting(self, attempt: int):
        """Handle reconnecting event."""
        self.connection_indicator.set_status("reconnecting")
        self.statusBar().showMessage(f"正在重新连接 (尝试 {attempt})...")

    def _on_connection_failed(self, error: str):
        """Handle connection failed event."""
        self.connection_indicator.set_status("disconnected")
        self.statusBar().showMessage("连接失败")
        QMessageBox.critical(self, "连接失败", error)

    def _refresh_contacts(self):
        """Refresh contact list."""
        if self._ws_client:
            self._ws_client.request_contact_list()
            self._ws_client.request_user_list()

    def _toggle_fullscreen(self):
        """Toggle fullscreen mode."""
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _on_logout(self):
        """Handle logout."""
        reply = QMessageBox.question(
            self,
            "退出登录",
            "确定要退出登录吗?",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            if self._ws_client:
                self._ws_client.send_logout()
            self.logout_requested.emit()

    def _on_about(self):
        """Show about dialog."""
        QMessageBox.about(
            self,
            "关于",
            "在线协作套件 v1.0\n\n"
            "提供即时通讯、文件传输和远程桌面功能。"
        )

    def closeEvent(self, event: QCloseEvent):
        """Handle window close event."""
        if self._ws_client:
            self._ws_client.stop()
        self.chat_tab.close_all_chats()
        event.accept()

