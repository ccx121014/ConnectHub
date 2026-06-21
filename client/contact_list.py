"""
Contact List Widget for Online Collaboration Suite
Displays online users with status indicators.
"""

from typing import Dict, List, Optional, Set
from enum import Enum


# Add project root and client dir to path for module imports (cross-platform)
from pathlib import Path
_project_root = Path(__file__).parent.parent.resolve()
import sys as _sys
_sys.path.insert(0, str(_project_root))
_sys.path.insert(0, str(Path(__file__).parent))

from PyQt5.QtCore import Qt, pyqtSignal, QSize
from PyQt5.QtGui import QIcon, QColor, QBrush, QPainter, QPixmap
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QLabel,
    QMenu,
    QAction,
    QToolButton,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QStyle,
    QInputDialog,
    QMessageBox,
    QLineEdit,
    QPushButton,
)


class UserStatus(Enum):
    """User status enumeration."""
    ONLINE = "online"
    BUSY = "busy"
    OFFLINE = "offline"
    AWAY = "away"


class StatusColors:
    """Color definitions for user statuses."""
    ONLINE = "#4CAF50"
    BUSY = "#FFC107"
    OFFLINE = "#9E9E9E"
    AWAY = "#FF9800"


class ContactItem(QWidget):
    """Custom widget showing contact info + action buttons (chat / file / desktop)."""

    chat_clicked = pyqtSignal(str)
    file_clicked = pyqtSignal(str)
    desktop_clicked = pyqtSignal(str)

    def __init__(self, username: str, status: UserStatus = UserStatus.OFFLINE, parent=None):
        super().__init__(parent)
        self.username = username
        self._status = status
        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(10)

        # Status dot
        self.status_label = QLabel()
        self.status_label.setFixedSize(10, 10)
        self._update_status_indicator()
        layout.addWidget(self.status_label)

        # Avatar
        self.avatar_label = QLabel()
        self.avatar_label.setFixedSize(32, 32)
        self.avatar_label.setStyleSheet(
            "background-color: #E0E0E0; border-radius: 16px; "
            "color: #757575; font-size: 14px; font-weight: bold;"
        )
        self.avatar_label.setAlignment(Qt.AlignCenter)
        self.avatar_label.setText(self.username[:1].upper() if self.username else "?")
        layout.addWidget(self.avatar_label)

        # Text
        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)

        self.username_label = QLabel(self.username)
        self.username_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        text_layout.addWidget(self.username_label)

        self.status_text = QLabel(self._status.value)
        self.status_text.setStyleSheet("color: #757575; font-size: 11px;")
        text_layout.addWidget(self.status_text)

        layout.addLayout(text_layout, 1)

        # Action buttons
        btn_style = """
            QPushButton {
                background: white;
                border: 1px solid #D0D0D0;
                border-radius: 5px;
                padding: 3px 8px;
                font-size: 13px;
            }
            QPushButton:hover {
                background: #E3F2FD;
                border: 1px solid #2196F3;
            }
            QPushButton:pressed {
                background: #BBDEFB;
            }
        """

        self.chat_btn = QPushButton("💬")
        self.chat_btn.setToolTip("发送消息")
        self.chat_btn.setFixedSize(34, 30)
        self.chat_btn.setStyleSheet(btn_style)
        self.chat_btn.clicked.connect(lambda: self.chat_clicked.emit(self.username))
        layout.addWidget(self.chat_btn)

        self.file_btn = QPushButton("📁")
        self.file_btn.setToolTip("发送文件")
        self.file_btn.setFixedSize(34, 30)
        self.file_btn.setStyleSheet(btn_style)
        self.file_btn.clicked.connect(lambda: self.file_clicked.emit(self.username))
        layout.addWidget(self.file_btn)

        self.desktop_btn = QPushButton("🖥")
        self.desktop_btn.setToolTip("发起桌面共享")
        self.desktop_btn.setFixedSize(34, 30)
        self.desktop_btn.setStyleSheet(btn_style)
        self.desktop_btn.clicked.connect(lambda: self.desktop_clicked.emit(self.username))
        layout.addWidget(self.desktop_btn)

    def _update_status_indicator(self):
        color = getattr(StatusColors, self._status.name, StatusColors.OFFLINE)
        style = "background-color: {}; border-radius: 5px;".format(color)
        self.status_label.setStyleSheet(style)

    def set_status(self, status: UserStatus):
        self._status = status
        self._update_status_indicator()
        self.status_text.setText(status.value)

    def get_status(self) -> UserStatus:
        return self._status

    def set_username(self, username: str):
        self.username = username
        self.username_label.setText(username)
        self.avatar_label.setText(username[:1].upper() if username else "?")


class ContactListWidget(QWidget):
    """Contact list widget showing online users with status indicators."""

    contact_double_clicked = pyqtSignal(str)
    start_chat_request = pyqtSignal(str)
    start_file_transfer = pyqtSignal(str)
    start_desktop_share = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._contacts: Dict[str, Dict] = {}
        self._username: Optional[str] = None
        self._init_ui()

    def _init_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        header_layout = QHBoxLayout()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索联系人...")
        self.search_input.textChanged.connect(self._on_search_changed)
        header_layout.addWidget(self.search_input)

        self.filter_button = QToolButton()
        self.filter_button.setText("▼")
        self.filter_button.setPopupMode(QToolButton.MenuButtonPopup)
        self.filter_menu = QMenu(self.filter_button)
        self._create_filter_menu()
        self.filter_button.setMenu(self.filter_menu)
        header_layout.addWidget(self.filter_button)

        layout.addLayout(header_layout)

        self.list_widget = QListWidget()
        self.list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._on_context_menu)
        self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.list_widget.setItemDelegate(ContactItemDelegate(self.list_widget))
        layout.addWidget(self.list_widget)

        self.status_label = QLabel("离线")
        self.status_label.setStyleSheet("color: #757575; padding: 5px;")
        layout.addWidget(self.status_label)

    def _create_filter_menu(self):
        """Create the filter menu."""
        self.filter_menu.clear()

        show_all_action = QAction("全部显示", self.filter_menu)
        show_all_action.triggered.connect(lambda: self._set_filter(None))
        self.filter_menu.addAction(show_all_action)

        show_online_action = QAction("仅显示在线", self.filter_menu)
        show_online_action.triggered.connect(lambda: self._set_filter(UserStatus.ONLINE))
        self.filter_menu.addAction(show_online_action)

        show_busy_action = QAction("仅显示忙碌", self.filter_menu)
        show_busy_action.triggered.connect(lambda: self._set_filter(UserStatus.BUSY))
        self.filter_menu.addAction(show_busy_action)

    def _set_filter(self, status: Optional[UserStatus]):
        """Set the status filter."""
        self._current_filter = status
        self._refresh_list()

    def set_username(self, username: str):
        """Set the current user name."""
        self._username = username

    def _on_chat_clicked(self, username: str):
        """Handle chat button clicked on a contact."""
        self.start_chat_request.emit(username)

    def _on_file_clicked(self, username: str):
        """Handle file button clicked on a contact."""
        self.start_file_transfer.emit(username)

    def _on_desktop_clicked(self, username: str):
        """Handle desktop button clicked on a contact."""
        self.start_desktop_share.emit(username, "view")

    def _on_search_changed(self, text: str):
        """Handle search text changed."""
        self._refresh_list()

    def _on_item_double_clicked(self, item: QListWidgetItem):
        """Handle item double click."""
        username = item.data(Qt.UserRole)
        if username:
            self.contact_double_clicked.emit(username)

    def _on_context_menu(self, position):
        """Show context menu for contact."""
        item = self.list_widget.itemAt(position)
        if not item:
            return

        username = item.data(Qt.UserRole)
        if not username or username == self._username:
            return

        menu = QMenu(self)

        chat_action = QAction("发送消息", menu)
        chat_action.triggered.connect(lambda: self.start_chat_request.emit(username))
        menu.addAction(chat_action)

        menu.addSeparator()

        file_transfer_action = QAction("发送文件", menu)
        file_transfer_action.triggered.connect(lambda: self.start_file_transfer.emit(username))
        menu.addAction(file_transfer_action)

        menu.addSeparator()

        view_desktop_action = QAction("查看桌面", menu)
        view_desktop_action.triggered.connect(lambda: self.start_desktop_share.emit(username, "view"))
        menu.addAction(view_desktop_action)

        control_desktop_action = QAction("控制桌面", menu)
        control_desktop_action.triggered.connect(lambda: self.start_desktop_share.emit(username, "control"))
        menu.addAction(control_desktop_action)

        menu.exec_(self.list_widget.mapToGlobal(position))

    def add_contact(self, username: str, status: UserStatus = UserStatus.ONLINE, **kwargs):
        """Add or update a contact."""
        self._contacts[username] = {
            "status": status,
            "metadata": kwargs
        }
        self._refresh_list()

    def update_contact_status(self, username: str, status: UserStatus):
        """Update a contact status."""
        if username in self._contacts:
            self._contacts[username]["status"] = status
        else:
            self._contacts[username] = {
                "status": status,
                "metadata": {}
            }
        self._refresh_list()

    def remove_contact(self, username: str):
        """Remove a contact."""
        if username in self._contacts:
            del self._contacts[username]
            self._refresh_list()

    def clear_contacts(self):
        """Clear all contacts."""
        self._contacts.clear()
        self._refresh_list()

    def _refresh_list(self):
        """Refresh the contact list display."""
        self.list_widget.clear()

        search_text = self.search_input.text().lower()
        filter_status = getattr(self, '_current_filter', None)

        for username, contact_data in sorted(self._contacts.items()):
            if username == self._username:
                continue

            if search_text and search_text not in username.lower():
                continue

            if filter_status and contact_data["status"] != filter_status:
                continue

            item = QListWidgetItem()
            item.setData(Qt.UserRole, username)
            item.setSizeHint(QSize(0, 52))

            contact_widget = ContactItem(username, contact_data["status"])
            contact_widget.chat_clicked.connect(self._on_chat_clicked)
            contact_widget.file_clicked.connect(self._on_file_clicked)
            contact_widget.desktop_clicked.connect(self._on_desktop_clicked)

            self.list_widget.addItem(item)
            self.list_widget.setItemWidget(item, contact_widget)

        online_count = sum(
            1 for c in self._contacts.values()
            if c["status"] == UserStatus.ONLINE
        )
        self.status_label.setText("在线: {}/{}".format(online_count, len(self._contacts)))

    def get_online_contacts(self) -> List[str]:
        """Get list of online contact user names."""
        return [
            username for username, data in self._contacts.items()
            if data["status"] == UserStatus.ONLINE
        ]

    def get_contact_status(self, username: str) -> Optional[UserStatus]:
        """Get the status of a specific contact."""
        if username in self._contacts:
            return self._contacts[username]["status"]
        return None

    def set_contacts(self, contacts: List[Dict]):
        """Set the contact list from server response."""
        self._contacts.clear()
        for contact in contacts:
            username = contact.get("username", contact.get("name", ""))
            status_str = contact.get("status", "offline")
            try:
                status = UserStatus(status_str)
            except ValueError:
                status = UserStatus.OFFLINE
            self._contacts[username] = {
                "status": status,
                "metadata": contact
            }
        self._refresh_list()


class ContactItemDelegate(QStyledItemDelegate):
    """Custom delegate for contact list items."""

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        """Paint the item."""
        super().paint(painter, option, index)

    def sizeHint(self, option: QStyleOptionViewItem, index):
        """Return the size hint for the item."""
        return QSize(0, 50)
