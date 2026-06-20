"""
Main Window for Online Collaboration Suite
Provides tab-based interface with Contacts, Chat, File Transfer, and Remote Desktop tabs.
"""

import logging
import os
import base64
import uuid
import time
from typing import Optional, Dict, List


# Add project root and client dir to path for module imports (cross-platform)
from pathlib import Path
_project_root = Path(__file__).parent.parent.resolve()
import sys as _sys
_sys.path.insert(0, str(_project_root))
_sys.path.insert(0, str(Path(__file__).parent))

from PyQt5.QtCore import Qt, QTimer, pyqtSlot, pyqtSignal
from PyQt5.QtGui import QIcon, QCloseEvent, QPixmap, QImage
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
    QApplication,
)

from protocol.messages import Message, MessageType
from websocket_client import WebSocketClient
from contact_list import ContactListWidget, UserStatus
from chat_widget import ChatTabWidget

logger = logging.getLogger(__name__)

CHUNK_SIZE = 32 * 1024  # 32KB per chunk for file transfer


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
        """Add a new file transfer using file_name as the key (compatible with old code)."""
        transfer_id = file_name  # simple, unique key per file
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
        """Update transfer progress (accepts file_id or transfer_id)."""
        # Support looking up by file_name (key in _transfers) or directly
        key = transfer_id
        if key not in self._transfers:
            # try partial match
            for k in self._transfers:
                if k in transfer_id or transfer_id in k:
                    key = k
                    break
        if key not in self._transfers:
            return

        self._transfers[key]["progress"] = progress
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(progress)

        for i in range(self.transfer_list.count()):
            item = self.transfer_list.item(i)
            if item.data(Qt.UserRole) == key:
                file_name = self._transfers[key]["file_name"]
                target = self._transfers[key]["target"]
                direction = self._transfers[key]["direction"]
                item.setText(
                    f"📄 {file_name} → {target} ({progress}%)" if direction == "send"
                    else f"📄 {file_name} ← {target} ({progress}%)"
                )
                break

        if progress >= 100:
            QTimer.singleShot(2000, lambda: self.progress_bar.setVisible(False))

    def remove_transfer(self, transfer_id: str):
        """Remove a completed transfer (accepts file_id or transfer_id)."""
        key = transfer_id
        if key not in self._transfers:
            for k in list(self._transfers.keys()):
                if k in transfer_id or transfer_id in k:
                    key = k
                    break
        if key in self._transfers:
            del self._transfers[key]
            for i in range(self.transfer_list.count()):
                item = self.transfer_list.item(i)
                if item.data(Qt.UserRole) == key:
                    self.transfer_list.takeItem(i)
                    break


class RemoteDesktopWidget(QWidget):
    """Widget for remote desktop sharing and control."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sharing = False
        self._viewing = False
        self._current_user = ""

        self._init_ui()

    def _init_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)

        header_layout = QHBoxLayout()
        title = QLabel("远程桌面")
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        header_layout.addWidget(title)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        self.status_label = QLabel("未共享桌面")
        self.status_label.setStyleSheet("color: #757575; padding: 10px;")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)

        self.preview_label = QLabel("桌面预览区域")
        self.preview_label.setMinimumSize(600, 400)
        self.preview_label.setStyleSheet(
            "background-color: #2D2D2D; color: #757575; border-radius: 5px;"
        )
        self.preview_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.preview_label)

        button_layout = QHBoxLayout()

        self.stop_button = QPushButton("停止共享")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self._on_stop_clicked)
        button_layout.addWidget(self.stop_button)

        layout.addLayout(button_layout)

        info_text = QLabel("桌面共享：点击联系人列表中的\"桌面\"按钮发起共享。\n接受请求后，对方可以看到您的屏幕。")
        info_text.setStyleSheet("color: #9E9E9E; font-size: 11px;")
        info_text.setAlignment(Qt.AlignCenter)
        info_text.setWordWrap(True)
        layout.addWidget(info_text)

        layout.addStretch()

    def set_status(self, mode: str, user: str = ""):
        """Set widget status: idle / sharing / viewing."""
        self._current_user = user
        if mode == "sharing":
            self._sharing = True
            self._viewing = False
            self.status_label.setText(f"正在向 {user} 共享桌面...")
            self.status_label.setStyleSheet("color: #4CAF50; padding: 10px; font-weight: bold;")
            self.stop_button.setEnabled(True)
            self.preview_label.setText("正在捕获并发送桌面画面...")
            self.preview_label.setStyleSheet(
                "background-color: #1F3A1F; color: #4CAF50; border-radius: 5px; padding: 20px;"
            )
        elif mode == "viewing":
            self._sharing = False
            self._viewing = True
            self.status_label.setText(f"正在查看 {user} 的桌面...")
            self.status_label.setStyleSheet("color: #2196F3; padding: 10px; font-weight: bold;")
            self.stop_button.setEnabled(True)
            self.preview_label.setText("等待桌面画面...")
            self.preview_label.setStyleSheet(
                "background-color: #1F2A3A; color: #2196F3; border-radius: 5px; padding: 20px;"
            )
        else:
            self._sharing = False
            self._viewing = False
            self.status_label.setText("未共享桌面")
            self.status_label.setStyleSheet("color: #757575; padding: 10px;")
            self.stop_button.setEnabled(False)
            self.preview_label.setText("桌面预览区域")
            self.preview_label.setStyleSheet(
                "background-color: #2D2D2D; color: #757575; border-radius: 5px;"
            )

    def update_preview(self, pixmap, sender: str = ""):
        """Update the preview with a new screenshot from sender."""
        if pixmap.isNull():
            return
        scaled = pixmap.scaled(
            self.preview_label.width(),
            self.preview_label.height(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        self.preview_label.setPixmap(scaled)
        if sender:
            self.status_label.setText(f"正在查看 {sender} 的桌面 - 已收到画面")

    def _on_stop_clicked(self):
        """Stop sharing/viewing on user click."""
        parent = self.parent()
        # Signal MainWindow to send a desktop stop message and stop timer
        if hasattr(parent, "_desktop_share_target"):
            try:
                if parent._desktop_share_target and parent._ws_client:
                    parent._ws_client.send_desktop_stop(parent._desktop_share_target)
                if parent._desktop_viewing_from and parent._ws_client:
                    parent._ws_client.send_desktop_stop(parent._desktop_viewing_from)
            except Exception as e:
                logger.debug(f"Error sending desktop stop: {e}")
            parent._desktop_timer.stop()
            parent._desktop_share_target = None
            parent._desktop_viewing_from = None
        self.set_status("idle", "")


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

        # 文件传输状态: file_id -> {'chunks': {index: data}, 'total': N, 'sender': '...', 'name': '...', 'size': S}
        self._incoming_files: Dict[str, Dict] = {}
        # 发送中的文件: file_id -> {'target': '...', 'name': '...', 'file_path': '...', 'chunks': N}
        self._pending_sends: Dict[str, str] = {}  # file_id -> target (waiting for response)

        # 桌面共享状态
        self._desktop_share_target: Optional[str] = None  # who we are sharing with
        self._desktop_viewing_from: Optional[str] = None  # who is sharing to us
        self._desktop_timer = QTimer(self)
        self._desktop_timer.setInterval(500)  # 2 FPS
        self._desktop_timer.timeout.connect(self._send_desktop_frame)

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
        # 所有信号来自 SignalBridge (client.signals)
        client.signals.message_received.connect(self._on_message_received)
        client.signals.connected.connect(self._on_connected)
        client.signals.disconnected.connect(self._on_disconnected)
        client.signals.reconnecting.connect(self._on_reconnecting)
        client.signals.connection_failed.connect(self._on_connection_failed)

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
        """Handle file transfer request — show file dialog and send chunks."""
        if not self._ws_client:
            QMessageBox.warning(self, "未连接", "无法发送文件：WebSocket 未连接")
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择要发送的文件",
            "",
            "所有文件 (*.*)"
        )
        if not file_path:
            return

        try:
            file_size = os.path.getsize(file_path)
        except OSError as e:
            QMessageBox.critical(self, "错误", f"无法读取文件：{e}")
            return

        file_name = os.path.basename(file_path)
        file_id = str(uuid.uuid4())
        chunk_count = (file_size + CHUNK_SIZE - 1) // CHUNK_SIZE  # ceil division

        self.file_transfer_widget.add_transfer(file_name, username, "send")

        # 记录待发送文件：等待对方接受后再分块发送
        self._pending_sends[file_id] = file_path

        # 首先发送 FILE_TRANSFER_REQUEST（包含文件元信息）
        self._ws_client.send_file_transfer_request(username, file_name, file_size, file_id, chunk_count, CHUNK_SIZE)
        self.tab_widget.setCurrentWidget(self.file_transfer_widget)
        self.statusBar().showMessage(f"正在向 {username} 请求发送文件: {file_name}")

    def _handle_file_transfer_request(self, message: Message):
        """Handle incoming file transfer request from another user."""
        sender = message.sender
        file_name = message.payload.get("file_name", "未知文件")
        file_size = message.payload.get("file_size", 0)
        file_id = message.payload.get("file_id", "")

        # 显示接受/拒绝对话框
        mb = QMessageBox(self)
        mb.setIcon(QMessageBox.Question)
        mb.setWindowTitle("文件传输请求")
        mb.setText(f"用户 {sender} 向您发送文件：\n\n{file_name}\n大小: {file_size / 1024:.1f} KB\n\n是否接受？")
        mb.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        mb.setDefaultButton(QMessageBox.Yes)
        reply = mb.exec_()

        if reply == QMessageBox.Yes:
            self._ws_client.send_file_transfer_response(sender, file_id, True)
            self.file_transfer_widget.add_transfer(file_name, sender, "receive")
            self._incoming_files[file_id] = {
                "chunks": {},
                "total": message.payload.get("chunk_count", 0),
                "sender": sender,
                "name": file_name,
                "size": file_size,
                "target": self._username or "",
            }
            self.statusBar().showMessage(f"已接受来自 {sender} 的文件: {file_name}")
            self.tab_widget.setCurrentWidget(self.file_transfer_widget)
        else:
            self._ws_client.send_file_transfer_response(sender, file_id, False)

    def _handle_file_transfer_response(self, message: Message):
        """对方响应了文件传输请求 — 接受则开始分块发送。"""
        file_id = message.payload.get("file_id", "")
        accepted = message.payload.get("accepted", False)
        sender = message.sender  # 这里 sender 是响应方（即接收文件的用户）

        if not accepted:
            QMessageBox.information(self, "文件被拒绝", f"{sender} 拒绝了您的文件传输请求")
            self._pending_sends.pop(file_id, None)
            return

        file_path = self._pending_sends.pop(file_id, None)
        if not file_path or not os.path.exists(file_path):
            logger.warning(f"File not found for transfer: {file_path}")
            return

        self._send_file_chunks(sender, file_id, file_path)

    def _send_file_chunks(self, target: str, file_id: str, file_path: str):
        """将文件分块发送给目标用户。"""
        try:
            file_size = os.path.getsize(file_path)
            file_name = os.path.basename(file_path)
            total_chunks = (file_size + CHUNK_SIZE - 1) // CHUNK_SIZE

            with open(file_path, "rb") as f:
                for chunk_index in range(total_chunks):
                    chunk_data = f.read(CHUNK_SIZE)
                    # Base64 编码以便 JSON 传输
                    encoded = base64.b64encode(chunk_data).decode("ascii")
                    self._ws_client.send_file_transfer_data(target, file_id, chunk_index, encoded)

                    # 更新进度
                    progress = int((chunk_index + 1) * 100 / total_chunks)
                    self.file_transfer_widget.update_progress(file_id, progress)

            # 发送完成消息
            self._ws_client.send_file_transfer_complete(target, file_id, total_chunks)
            self.file_transfer_widget.remove_transfer(file_id)
            self.statusBar().showMessage(f"文件 {file_name} 发送完成")
            logger.info(f"File transfer completed: {file_name} -> {target}")
        except Exception as e:
            logger.error(f"Error sending file: {e}", exc_info=True)
            QMessageBox.critical(self, "发送失败", f"发送文件时出错：{e}")

    def _handle_file_transfer_data(self, message: Message):
        """接收文件数据块。"""
        file_id = message.payload.get("file_id", "")
        chunk_index = message.payload.get("chunk_index", 0)
        data = message.payload.get("data", "")

        if file_id not in self._incoming_files:
            logger.debug(f"Received data chunk for unknown file: {file_id}")
            return

        self._incoming_files[file_id]["chunks"][chunk_index] = data
        total = self._incoming_files[file_id].get("total", 0)
        received = len(self._incoming_files[file_id]["chunks"])
        if total > 0:
            progress = int(received * 100 / total)
            self.file_transfer_widget.update_progress(file_id, progress)

    def _handle_file_transfer_complete(self, message: Message):
        """文件传输完成 — 组装并保存。"""
        file_id = message.payload.get("file_id", "")
        total_chunks = message.payload.get("total_chunks", 0)

        if file_id not in self._incoming_files:
            return

        info = self._incoming_files[file_id]
        chunks = info["chunks"]

        if len(chunks) < total_chunks:
            # 尝试使用所有接收到的数据块
            logger.warning(f"Incomplete file: {len(chunks)}/{total_chunks} chunks")

        try:
            # 按顺序组装数据块
            sorted_indices = sorted(chunks.keys())
            file_data = b""
            for idx in sorted_indices:
                file_data += base64.b64decode(chunks[idx])

            # 选择保存位置
            default_name = info.get("name", f"received_{file_id}.bin")
            save_path, _ = QFileDialog.getSaveFileName(
                self,
                "保存文件",
                default_name,
                "所有文件 (*.*)"
            )
            if save_path:
                with open(save_path, "wb") as f:
                    f.write(file_data)
                self.file_transfer_widget.remove_transfer(file_id)
                self.statusBar().showMessage(f"文件已保存: {os.path.basename(save_path)}")
                logger.info(f"File saved: {save_path}")
            else:
                self.file_transfer_widget.remove_transfer(file_id)
        except Exception as e:
            logger.error(f"Error saving file: {e}", exc_info=True)
            QMessageBox.critical(self, "保存失败", f"保存文件时出错：{e}")
        finally:
            self._incoming_files.pop(file_id, None)

    def _on_desktop_share_request(self, username: str, share_type: str):
        """向用户发送桌面共享请求。"""
        if not self._ws_client:
            QMessageBox.warning(self, "未连接", "无法共享桌面：WebSocket 未连接")
            return

        self._ws_client.send_desktop_share_request(username, share_type)
        self.tab_widget.setCurrentWidget(self.remote_desktop_widget)
        self.statusBar().showMessage(f"已向 {username} 发送桌面共享请求")

    def _handle_desktop_share_request(self, message: Message):
        """收到别人的桌面共享请求。"""
        sender = message.sender
        share_type = message.payload.get("share_type", "view")

        reply = QMessageBox.question(
            self,
            "远程桌面请求",
            f"用户 {sender} 请求{'控制' if share_type == 'control' else '查看'}您的桌面。\n\n是否接受？",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self._ws_client.send_desktop_share_response(sender, True, share_type)
            # 开始共享我的桌面
            self._desktop_share_target = sender
            self._desktop_timer.start()
            self.remote_desktop_widget.set_status("sharing", sender)
            self.tab_widget.setCurrentWidget(self.remote_desktop_widget)
            self.statusBar().showMessage(f"正在向 {sender} 共享桌面")
        else:
            self._ws_client.send_desktop_share_response(sender, False, share_type)

    def _handle_desktop_share_response(self, message: Message):
        """对方响应了桌面共享请求。"""
        sender = message.sender
        accepted = message.payload.get("accepted", False)

        if accepted:
            self._desktop_viewing_from = sender
            self.remote_desktop_widget.set_status("viewing", sender)
            self.tab_widget.setCurrentWidget(self.remote_desktop_widget)
            self.statusBar().showMessage(f"正在查看 {sender} 的桌面")
        else:
            QMessageBox.information(self, "请求被拒绝", f"{sender} 拒绝了您的桌面共享请求")

    def _send_desktop_frame(self):
        """捕获当前桌面并发送给共享目标。"""
        if not self._desktop_share_target or not self._ws_client:
            return

        try:
            # 使用 QScreen/grabWindow 捕获整个屏幕
            screen = QApplication.primaryScreen()
            if screen is None:
                return
            pixmap = screen.grabWindow(0)
            if pixmap.isNull():
                return

            # 缩小到合理尺寸减少带宽
            scaled = pixmap.scaled(800, 600, Qt.KeepAspectRatio, Qt.SmoothTransformation)

            # 转换为 JPEG 再 base64 编码
            from PyQt5.QtCore import QBuffer, QByteArray
            buffer = QBuffer()
            buffer.open(QBuffer.ReadWrite)
            scaled.save(buffer, "JPG", 70)
            byte_array = buffer.data()
            image_data = base64.b64encode(bytes(byte_array)).decode("ascii")

            width = scaled.width()
            height = scaled.height()

            self._ws_client.send_desktop_frame(self._desktop_share_target, image_data, width, height)
        except Exception as e:
            logger.debug(f"Desktop capture error: {e}")

    def _handle_desktop_frame(self, message: Message):
        """显示收到的桌面屏幕截图。"""
        try:
            image_data = message.payload.get("image_data", "")
            width = message.payload.get("width", 800)
            height = message.payload.get("height", 600)
            sender = message.sender

            if not image_data:
                return

            # Base64 -> QPixmap
            raw = base64.b64decode(image_data)
            qbyte = QByteArray(raw)
            pixmap = QPixmap()
            pixmap.loadFromData(qbyte, "JPG")

            if not pixmap.isNull():
                self.remote_desktop_widget.update_preview(pixmap, sender)
        except Exception as e:
            logger.debug(f"Desktop frame display error: {e}")

    def _handle_desktop_stop(self, message: Message):
        """桌面共享停止。"""
        if self._desktop_share_target or self._desktop_viewing_from:
            self._desktop_timer.stop()
            self._desktop_share_target = None
            self._desktop_viewing_from = None
            self.remote_desktop_widget.set_status("idle", "")
            self.statusBar().showMessage("桌面共享已停止")

    def _on_message_sent(self, target: str, content: str):
        """Handle message sent event."""
        if self._ws_client and content:
            self._ws_client.send_chat_message(target, content)

    @pyqtSlot(object)
    def _on_message_received(self, message):
        """Handle incoming message from the WebSocket thread."""
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
            elif message.type == MessageType.FILE_TRANSFER_RESPONSE:
                self._handle_file_transfer_response(message)
            elif message.type == MessageType.FILE_TRANSFER_DATA:
                self._handle_file_transfer_data(message)
            elif message.type == MessageType.FILE_TRANSFER_COMPLETE:
                self._handle_file_transfer_complete(message)
            elif message.type == MessageType.DESKTOP_SHARE_REQUEST:
                self._handle_desktop_share_request(message)
            elif message.type == MessageType.DESKTOP_SHARE_RESPONSE:
                self._handle_desktop_share_response(message)
            elif message.type == MessageType.DESKTOP_FRAME:
                self._handle_desktop_frame(message)
            elif message.type == MessageType.DESKTOP_STOP:
                self._handle_desktop_stop(message)
            elif message.type == MessageType.ERROR:
                self._handle_error(message)
        except Exception as e:
            logger.error(f"Error handling message: {e}", exc_info=True)

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
        if not isinstance(contacts, list):
            contacts = []
        # Normalize: ensure each contact is a dict with "username" and "status"
        normalized = []
        for c in contacts:
            if isinstance(c, dict):
                normalized.append({
                    "username": c.get("username", ""),
                    "status": c.get("status", "offline"),
                    "last_seen": c.get("last_seen", None)
                })
            elif isinstance(c, str):
                normalized.append({"username": c, "status": "offline", "last_seen": None})
        self.contact_list_widget.set_contacts(normalized)

    def _handle_user_list_response(self, message: Message):
        """Handle user list response."""
        users = message.payload.get("users", [])
        if not isinstance(users, list):
            return
        for user_data in users:
            if isinstance(user_data, dict):
                username = user_data.get("username", "")
                status_str = user_data.get("status", "offline")
            elif isinstance(user_data, str):
                username = user_data
                status_str = "online"
            else:
                continue
            try:
                status = UserStatus(status_str)
            except ValueError:
                status = UserStatus.OFFLINE
            if username:
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

