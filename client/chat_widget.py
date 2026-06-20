"""
Chat Widget for Online Collaboration Suite
Provides 1:1 and group chat functionality with message display and input.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple


# Add project root and client dir to path for module imports (cross-platform)
from pathlib import Path
_project_root = Path(__file__).parent.parent.resolve()
import sys as _sys
_sys.path.insert(0, str(_project_root))
_sys.path.insert(0, str(Path(__file__).parent))

from PyQt5.QtCore import Qt, pyqtSignal, QSize
from PyQt5.QtGui import QFont, QColor, QTextCursor, QIcon
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTextEdit,
    QLineEdit,
    QPushButton,
    QToolButton,
    QLabel,
    QMenu,
    QScrollArea,
    QFrame,
    QFileDialog,
    QMessageBox,
    QTabWidget,
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QSizePolicy,
    QApplication,
    QAction,
)

from protocol.messages import Message, MessageType

logger = logging.getLogger(__name__)


class ChatMessage(QFrame):
    """
    Widget for displaying a single chat message.
    """

    def __init__(
        self,
        username: str,
        content: str,
        timestamp: datetime,
        is_own: bool = False,
        message_type: str = "text",
        parent=None
    ):
        super().__init__(parent)
        self.username = username
        self.content = content
        self.timestamp = timestamp
        self.is_own = is_own
        self.message_type = message_type

        self._init_ui()

    def _init_ui(self):
        """Initialize the user interface."""
        self.setFrameStyle(QFrame.StyledPanel | QFrame.Raised)
        self.setLineWidth(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(2)

        # Header with username and timestamp
        header_layout = QHBoxLayout()

        username_label = QLabel(self.username)
        username_label.setStyleSheet("font-weight: bold; color: #1976D2;")
        header_layout.addWidget(username_label)

        header_layout.addStretch()

        time_label = QLabel(self.timestamp.strftime("%H:%M:%S"))
        time_label.setStyleSheet("color: #9E9E9E; font-size: 10px;")
        header_layout.addWidget(time_label)

        layout.addLayout(header_layout)

        # Message content
        content_label = QLabel(self.content)
        content_label.setWordWrap(True)
        content_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        content_label.setStyleSheet("""
            background-color: #F5F5F5;
            padding: 8px;
            border-radius: 5px;
        """ if not self.is_own else """
            background-color: #E3F2FD;
            padding: 8px;
            border-radius: 5px;
        """)
        layout.addWidget(content_label)

        # Apply alignment based on own/other message
        if self.is_own:
            self.setStyleSheet("""
                ChatMessage {
                    background-color: #E3F2FD;
                    border-radius: 10px;
                    border: 1px solid #BBDEFB;
                }
            """)
        else:
            self.setStyleSheet("""
                ChatMessage {
                    background-color: #FFFFFF;
                    border-radius: 10px;
                    border: 1px solid #E0E0E0;
                }
            """)


class ChatHistory(QScrollArea):
    """
    Scrollable area for displaying chat messages.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._messages: List[ChatMessage] = []

        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)

        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setAlignment(Qt.AlignTop)
        self.content_layout.setSpacing(10)

        self.setWidget(self.content_widget)

    def add_message(self, message: ChatMessage):
        """Add a message to the chat history."""
        self._messages.append(message)
        self.content_layout.addWidget(message)
        self._scroll_to_bottom()

    def clear_messages(self):
        """Clear all messages."""
        for msg in self._messages:
            msg.deleteLater()
        self._messages.clear()
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _scroll_to_bottom(self):
        """Scroll to the bottom of the chat history."""
        scrollbar = self.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())


class ChatWidget(QWidget):
    """
    Chat widget for 1:1 and group chats.
    Signals:
        send_message: Emitted with (target, content, message_type) when sending a message
        send_file_request: Emitted with (target,) when file transfer is requested
        message_sent: Emitted when a message is successfully sent
    """

    send_message = pyqtSignal(str, str, str)
    send_file_request = pyqtSignal(str)
    message_sent = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_target: Optional[str] = None
        self._is_group_chat = False
        self._username: Optional[str] = None
        self._message_history: Dict[str, List[Tuple[str, str, datetime]]] = {}

        self._init_ui()

    def _init_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Chat header
        self.header_widget = QWidget()
        self.header_widget.setStyleSheet("background-color: #FAFAFA; border-bottom: 1px solid #E0E0E0;")
        header_layout = QHBoxLayout(self.header_widget)
        header_layout.setContentsMargins(10, 5, 10, 5)

        self.title_label = QLabel("聊天")
        self.title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        header_layout.addWidget(self.title_label)

        header_layout.addStretch()

        self.member_count_label = QLabel("")
        self.member_count_label.setStyleSheet("color: #757575; font-size: 12px;")
        header_layout.addWidget(self.member_count_label)

        layout.addWidget(self.header_widget)

        # Chat history
        self.chat_history = ChatHistory()
        layout.addWidget(self.chat_history)

        # Input area
        input_widget = QWidget()
        input_widget.setStyleSheet("background-color: #FAFAFA; border-top: 1px solid #E0E0E0;")
        input_layout = QVBoxLayout(input_widget)
        input_layout.setContentsMargins(10, 5, 10, 5)
        input_layout.setSpacing(5)

        # File transfer button row
        file_button_layout = QHBoxLayout()
        file_button_layout.addStretch()

        self.file_button = QToolButton()
        self.file_button.setText("📎 发送文件")
        self.file_button.clicked.connect(self._on_file_button_clicked)
        file_button_layout.addWidget(self.file_button)

        input_layout.addLayout(file_button_layout)

        # Message input row
        message_layout = QHBoxLayout()
        message_layout.setSpacing(5)

        self.message_input = QTextEdit()
        self.message_input.setPlaceholderText("输入消息...")
        self.message_input.setMaximumHeight(100)
        self.message_input.setTabChangesFocus(True)
        self.message_input.installEventFilter(self)
        message_layout.addWidget(self.message_input)

        self.send_button = QPushButton("发送")
        self.send_button.setEnabled(False)
        self.send_button.clicked.connect(self._on_send_clicked)
        self.send_button.setMinimumWidth(80)
        message_layout.addWidget(self.send_button)

        input_layout.addLayout(message_layout)

        layout.addWidget(input_widget)

        # Connect message input changes
        self.message_input.textChanged.connect(self._on_input_changed)

    def eventFilter(self, obj, event):
        """Handle event filter for Enter key sending."""
        if obj == self.message_input and event.type() == event.KeyPress:
            if event.key() == Qt.Key_Return and not event.modifiers() & Qt.ShiftModifier:
                self._on_send_clicked()
                return True
        return super().eventFilter(obj, event)

    def set_username(self, username: str):
        """Set the current username."""
        self._username = username

    def set_chat_target(self, target: str, is_group: bool = False):
        """Set the current chat target (user or group)."""
        self._current_target = target
        self._is_group_chat = is_group
        self.title_label.setText(f"与 {target} 的聊天" if not is_group else f"群聊: {target}")
        self.file_button.setEnabled(True)

    def clear_chat(self):
        """Clear the chat history."""
        self.chat_history.clear_messages()

    def add_message(self, username: str, content: str, timestamp: datetime = None, message_type: str = "text"):
        """Add a message to the chat."""
        if timestamp is None:
            timestamp = datetime.now()

        is_own = (username == self._username)
        message = ChatMessage(username, content, timestamp, is_own, message_type)
        self.chat_history.add_message(message)

        # Store in history
        if self._current_target:
            if self._current_target not in self._message_history:
                self._message_history[self._current_target] = []
            self._message_history[self._current_target].append((username, content, timestamp))

    def add_system_message(self, content: str):
        """Add a system message to the chat."""
        message = ChatMessage("系统", content, datetime.now(), False, "system")
        message.setStyleSheet("""
            ChatMessage {
                background-color: #FFF8E1;
                border-radius: 10px;
                border: 1px solid #FFE082;
            }
        """)
        self.chat_history.add_message(message)

    def _on_input_changed(self):
        """Handle input text changes."""
        text = self.message_input.toPlainText().strip()
        self.send_button.setEnabled(bool(text) and self._current_target is not None)

    def _on_send_clicked(self):
        """Handle send button click."""
        content = self.message_input.toPlainText().strip()
        if not content or not self._current_target:
            return

        message_type = "text"
        self.send_message.emit(self._current_target, content, message_type)
        self.message_input.clear()
        self.message_sent.emit()

    def _on_file_button_clicked(self):
        """Handle file button click."""
        if not self._current_target:
            QMessageBox.warning(self, "错误", "请先选择一个聊天对象")
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择要发送的文件",
            "",
            "所有文件 (*.*)"
        )

        if file_path:
            self.send_file_request.emit(self._current_target)

    def get_message_history(self, target: str) -> List[Tuple[str, str, datetime]]:
        """Get message history for a target."""
        return self._message_history.get(target, [])

    def load_message_history(self, messages: List[Dict]):
        """Load message history from server response."""
        self.chat_history.clear_messages()
        for msg in messages:
            username = msg.get("sender", msg.get("username", "未知"))
            content = msg.get("content", msg.get("message", ""))
            timestamp_str = msg.get("timestamp")
            if timestamp_str:
                try:
                    timestamp = datetime.fromtimestamp(float(timestamp_str))
                except (ValueError, TypeError):
                    timestamp = datetime.now()
            else:
                timestamp = datetime.now()
            self.add_message(username, content, timestamp)


class ChatTabWidget(QTabWidget):
    """
    Tab widget for managing multiple chat conversations.
    Signals:
        chat_started: Emitted with (target, is_group) when a new chat is started
        message_sent: Emitted with (target, content) when a message is sent
    """

    chat_started = pyqtSignal(str, bool)
    message_sent = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._chats: Dict[str, ChatWidget] = {}
        self._username: Optional[str] = None

        self.setTabsClosable(True)
        self.tabCloseRequested.connect(self._on_tab_close_requested)

    def set_username(self, username: str):
        """Set the current username."""
        self._username = username
        for chat in self._chats.values():
            chat.set_username(username)

    def open_chat(self, target: str, is_group: bool = False):
        """Open or switch to a chat with the target."""
        if target in self._chats:
            self.setCurrentWidget(self._chats[target])
        else:
            self._create_chat_tab(target, is_group)
        self.chat_started.emit(target, is_group)

    def _create_chat_tab(self, target: str, is_group: bool = False):
        """Create a new chat tab."""
        chat_widget = ChatWidget()
        chat_widget.set_username(self._username or "")
        chat_widget.set_chat_target(target, is_group)
        chat_widget.send_message.connect(self._on_send_message)
        chat_widget.message_sent.connect(lambda: self.message_sent.emit(target, ""))

        tab_text = target if len(target) <= 15 else target[:12] + "..."
        index = self.addTab(chat_widget, tab_text)
        self.setCurrentIndex(index)

        self._chats[target] = chat_widget

    def _on_send_message(self, target: str, content: str, message_type: str):
        """Handle message send from chat widget."""
        self.message_sent.emit(target, content)

    def _on_tab_close_requested(self, index: int):
        """Handle tab close request."""
        widget = self.widget(index)
        if widget:
            target = None
            for t, w in self._chats.items():
                if w == widget:
                    target = t
                    break
            if target:
                del self._chats[target]
            widget.deleteLater()
        self.removeTab(index)

    def get_chat(self, target: str) -> Optional[ChatWidget]:
        """Get the chat widget for a target."""
        return self._chats.get(target)

    def get_active_chat(self) -> Optional[str]:
        """Get the target of the currently active chat."""
        widget = self.currentWidget()
        if widget:
            for target, chat in self._chats.items():
                if chat == widget:
                    return target
        return None

    def add_message_to_chat(self, target: str, username: str, content: str, timestamp: datetime = None):
        """Add a message to a specific chat."""
        if target in self._chats:
            self._chats[target].add_message(username, content, timestamp)
        else:
            # Create chat tab if it doesn't exist
            is_group = False
            self._create_chat_tab(target, is_group)
            self._chats[target].add_message(username, content, timestamp)

    def close_all_chats(self):
        """Close all chat tabs."""
        for chat in self._chats.values():
            chat.deleteLater()
        self._chats.clear()
        while self.count():
            self.removeTab(0)
