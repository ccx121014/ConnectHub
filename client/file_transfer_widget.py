"""
File Transfer Widget for Online Collaboration Suite
Provides UI for managing file transfers with progress tracking.
"""

import logging
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from PyQt5.QtCore import Qt, pyqtSignal, QSize, QTimer
from PyQt5.QtGui import QFont, QColor, QIcon
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QFrame,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QScrollArea,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QAbstractItemView,
    QToolButton,
    QMenu,
    QAction,
    QMessageBox,
    QFileDialog,
    QStyledItemDelegate,
    QStyleOptionProgressBar,
    QStyle,
)

from protocol.messages import Message, MessageType

logger = logging.getLogger(__name__)


class TransferListItem(QWidget):
    """
    Widget for displaying a file transfer item in the list.
    """

    def __init__(
        self,
        file_id: str,
        file_name: str,
        file_size: int,
        target_user: str,
        direction: str,
        parent=None
    ):
        super().__init__(parent)
        self.file_id = file_id
        self.file_name = file_name
        self.file_size = file_size
        self.target_user = target_user
        self.direction = direction

        self._init_ui()

    def _init_ui(self):
        """Initialize the user interface."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)

        icon_label = QLabel("📄" if self.direction == "send" else "📥")
        icon_label.setFont(QFont("Segoe UI Emoji", 16))
        layout.addWidget(icon_label)

        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)

        name_label = QLabel(self.file_name)
        name_label.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        name_label.setStyleSheet("color: #333;")
        name_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        info_layout.addWidget(name_label)

        details_text = f"{self.target_user} • {self._format_size(self.file_size)}"
        details_label = QLabel(details_text)
        details_label.setFont(QFont("Microsoft YaHei", 9))
        details_label.setStyleSheet("color: #757575;")
        info_layout.addWidget(details_label)

        layout.addLayout(info_layout, 1)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setMaximumHeight(6)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: none;
                background-color: #E0E0E0;
                border-radius: 3px;
            }
            QProgressBar::chunk {
                background-color: #4CAF50;
                border-radius: 3px;
            }
        """)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("等待中")
        self.status_label.setFont(QFont("Microsoft YaHei", 9))
        self.status_label.setStyleSheet("color: #9E9E9E; min-width: 60px;")
        self.status_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(self.status_label)

    def _format_size(self, size: int) -> str:
        """Format file size to human readable string."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    def update_progress(self, progress: float, current_chunk: int = 0, chunk_count: int = 0):
        """Update transfer progress."""
        self.progress_bar.setValue(int(progress))
        self.status_label.setText(f"{int(progress)}%")
        
        if progress >= 100:
            self.status_label.setText("完成")
            self.status_label.setStyleSheet("color: #4CAF50; min-width: 60px;")
        elif progress > 0:
            self.status_label.setStyleSheet("color: #1976D2; min-width: 60px;")

    def set_status(self, status: str):
        """Set transfer status text."""
        self.status_label.setText(status)


class FileRequestDialog(QDialog):
    """
    Dialog for incoming file transfer requests.
    """

    def __init__(
        self,
        file_id: str,
        file_name: str,
        file_size: int,
        sender: str,
        parent=None
    ):
        super().__init__(parent)
        self.file_id = file_id
        self.file_name = file_name
        self.file_size = file_size
        self.sender = sender
        self._response = False

        self._init_ui()

    def _init_ui(self):
        """Initialize the user interface."""
        self.setWindowTitle("文件传输请求")
        self.setMinimumWidth(400)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        icon_label = QLabel("📁")
        icon_label.setFont(QFont("Segoe UI Emoji", 48))
        icon_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon_label)

        title_label = QLabel("收到文件传输请求")
        title_label.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        info_group = QGroupBox()
        info_layout = QVBoxLayout(info_group)

        info_layout.addWidget(QLabel(f"<b>发送者:</b> {self.sender}"))
        info_layout.addWidget(QLabel(f"<b>文件名:</b> {self.file_name}"))
        info_layout.addWidget(QLabel(f"<b>大小:</b> {self._format_size(self.file_size)}"))

        layout.addWidget(info_group)

        button_box = QDialogButtonBox(
            QDialogButtonBox.Yes | QDialogButtonBox.No
        )
        button_box.button(QDialogButtonBox.Yes).setText("接受")
        button_box.button(QDialogButtonBox.No).setText("拒绝")
        button_box.button(QDialogButtonBox.Yes).setDefault(True)
        
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self._on_reject)

        layout.addWidget(button_box)

    def _format_size(self, size: int) -> str:
        """Format file size to human readable string."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    def _on_accept(self):
        """Handle accept button click."""
        self._response = True
        self.accept()

    def _on_reject(self):
        """Handle reject button click."""
        self._response = False
        self.reject()

    def get_response(self) -> bool:
        """Get the user's response."""
        return self._response


class TransferHistoryWidget(QWidget):
    """
    Widget for displaying transfer history.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._history: List[Dict] = []

        self._init_ui()

    def _init_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["文件名", "方向", "大小", "状态", "时间"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: white;
                alternate-background-color: #FAFAFA;
            }
            QTableWidget::item {
                padding: 5px;
            }
        """)

        layout.addWidget(self.table)

    def add_history_entry(self, entry: Dict):
        """Add a transfer to history."""
        self._history.append(entry)
        self._update_table()

    def _update_table(self):
        """Update the history table."""
        self.table.setRowCount(len(self._history))
        
        for row, entry in enumerate(self._history):
            self.table.setItem(row, 0, QTableWidgetItem(entry.get("file_name", "")))
            self.table.setItem(row, 1, QTableWidgetItem(entry.get("direction", "")))
            self.table.setItem(row, 2, QTableWidgetItem(entry.get("size", "")))
            self.table.setItem(row, 3, QTableWidgetItem(entry.get("status", "")))
            self.table.setItem(row, 4, QTableWidgetItem(entry.get("time", "")))

    def clear_history(self):
        """Clear transfer history."""
        self._history.clear()
        self.table.setRowCount(0)


class FileTransferWidget(QWidget):
    """
    File transfer widget with active transfers and history.
    
    Signals:
        transfer_requested: Emitted with (target_user, file_path) when user requests a transfer
        transfer_accepted: Emitted with (file_id) when transfer is accepted
        transfer_rejected: Emitted with (file_id) when transfer is rejected
        transfer_cancelled: Emitted with (file_id) when transfer is cancelled
        open_folder_requested: Emitted with (file_path) when user wants to open containing folder
    """

    transfer_requested = pyqtSignal(str, str)
    transfer_accepted = pyqtSignal(str)
    transfer_rejected = pyqtSignal(str)
    transfer_cancelled = pyqtSignal(str)
    open_folder_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._transfers: Dict[str, TransferListItem] = {}
        self._transfer_info: Dict[str, Dict] = {}
        self._username: Optional[str] = None

        self._init_ui()

    def _init_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        header_layout = QHBoxLayout()
        
        title = QLabel("文件传输")
        title.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
        title.setStyleSheet("color: #333;")
        header_layout.addWidget(title)

        header_layout.addStretch()

        self.clear_button = QPushButton("清除已完成")
        self.clear_button.setFont(QFont("Microsoft YaHei", 9))
        self.clear_button.clicked.connect(self._on_clear_completed)
        header_layout.addWidget(self.clear_button)

        layout.addLayout(header_layout)

        self.tabs = QTabWidget()
        
        active_tab = QWidget()
        active_layout = QVBoxLayout(active_tab)
        active_layout.setContentsMargins(0, 5, 0, 0)

        self.active_list = QListWidget()
        self.active_list.setFrameShape(QListWidget.NoFrame)
        self.active_list.setStyleSheet("""
            QListWidget {
                background-color: #FAFAFA;
                border: 1px solid #E0E0E0;
                border-radius: 5px;
            }
            QListWidget::item {
                background-color: white;
                border-bottom: 1px solid #F0F0F0;
                border-radius: 0;
            }
            QListWidget::item:selected {
                background-color: #E3F2FD;
            }
        """)
        active_layout.addWidget(self.active_list)

        self.tabs.addTab(active_tab, "进行中")

        history_tab = TransferHistoryWidget()
        self.history_widget = history_tab
        self.tabs.addTab(history_tab, "传输历史")

        layout.addWidget(self.tabs)

        info_label = QLabel("双击传输记录打开文件夹位置")
        info_label.setFont(QFont("Microsoft YaHei", 9))
        info_label.setStyleSheet("color: #9E9E9E;")
        info_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(info_label)

        self.active_list.itemDoubleClicked.connect(self._on_item_double_clicked)

    def set_username(self, username: str):
        """Set the current username."""
        self._username = username

    def add_transfer(
        self,
        file_id: str,
        file_name: str,
        file_size: int,
        target_user: str,
        direction: str
    ) -> TransferListItem:
        """Add a new file transfer to the active list."""
        if file_id in self._transfers:
            logger.warning(f"Transfer already exists: {file_id}")
            return self._transfers[file_id]

        item_widget = TransferListItem(
            file_id=file_id,
            file_name=file_name,
            file_size=file_size,
            target_user=target_user,
            direction=direction
        )

        list_item = QListWidgetItem()
        list_item.setData(Qt.UserRole, file_id)
        list_item.setSizeHint(QSize(0, 60))
        
        self.active_list.addItem(list_item)
        self.active_list.setItemWidget(list_item, item_widget)

        self._transfers[file_id] = item_widget
        self._transfer_info[file_id] = {
            "file_id": file_id,
            "file_name": file_name,
            "file_size": file_size,
            "target_user": target_user,
            "direction": direction,
            "start_time": datetime.now()
        }

        logger.info(f"Transfer added to widget: {file_id} ({file_name})")
        return item_widget

    def update_progress(self, file_id: str, progress: float, current_chunk: int = 0, chunk_count: int = 0):
        """Update transfer progress."""
        if file_id not in self._transfers:
            logger.warning(f"Transfer not found for progress update: {file_id}")
            return

        item = self._transfers[file_id]
        item.update_progress(progress, current_chunk, chunk_count)

        if progress >= 100:
            self._on_transfer_completed(file_id)

    def set_transfer_status(self, file_id: str, status: str):
        """Set transfer status text."""
        if file_id in self._transfers:
            self._transfers[file_id].set_status(status)

    def remove_transfer(self, file_id: str):
        """Remove a transfer from the active list."""
        if file_id not in self._transfers:
            return

        for i in range(self.active_list.count()):
            item = self.active_list.item(i)
            if item.data(Qt.UserRole) == file_id:
                self.active_list.takeItem(i)
                break

        del self._transfers[file_id]
        
        if file_id in self._transfer_info:
            del self._transfer_info[file_id]

        logger.info(f"Transfer removed from widget: {file_id}")

    def _on_transfer_completed(self, file_id: str):
        """Handle transfer completion."""
        if file_id not in self._transfer_info:
            return

        info = self._transfer_info[file_id]
        info["status"] = "completed"
        info["end_time"] = datetime.now()
        info["duration"] = (info["end_time"] - info["start_time"]).total_seconds()

        self.history_widget.add_history_entry({
            "file_name": info["file_name"],
            "direction": "发送" if info["direction"] == "send" else "接收",
            "size": self._format_size(info["file_size"]),
            "status": "完成",
            "time": info["start_time"].strftime("%Y-%m-%d %H:%M")
        })

        QTimer.singleShot(2000, lambda: self.remove_transfer(file_id))

    def _on_clear_completed(self):
        """Clear all completed transfers."""
        completed_ids = []
        for file_id, item in self._transfers.items():
            if item.progress_bar.value() >= 100:
                completed_ids.append(file_id)

        for file_id in completed_ids:
            self.remove_transfer(file_id)

        self.history_widget.clear_history()
        logger.info("Cleared all transfers")

    def _on_item_double_clicked(self, item: QListWidgetItem):
        """Handle item double click."""
        file_id = item.data(Qt.UserRole)
        if file_id in self._transfer_info:
            info = self._transfer_info[file_id]
            self.open_folder_requested.emit(info.get("file_path", ""))

    def _format_size(self, size: int) -> str:
        """Format file size to human readable string."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    def show_file_request(
        self,
        file_id: str,
        file_name: str,
        file_size: int,
        sender: str
    ) -> bool:
        """Show a file request dialog and return True if accepted."""
        dialog = FileRequestDialog(file_id, file_name, file_size, sender, self)
        result = dialog.exec_()
        
        response = dialog.get_response()
        if response:
            self.transfer_accepted.emit(file_id)
            self.add_transfer(file_id, file_name, file_size, sender, "receive")
        else:
            self.transfer_rejected.emit(file_id)
        
        return response

    def get_transfer_info(self, file_id: str) -> Optional[Dict]:
        """Get transfer information."""
        return self._transfer_info.get(file_id)

    def get_all_transfers(self) -> List[Dict]:
        """Get all active transfers."""
        return list(self._transfer_info.values())


class FileTransferPanel(QWidget):
    """
    Complete file transfer panel with send functionality.
    
    Signals:
        send_file_requested: Emitted with (target_user, file_path)
    """

    send_file_requested = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._username: Optional[str] = None

        self._init_ui()

    def _init_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)

        header_layout = QHBoxLayout()
        
        title = QLabel("发送文件")
        title.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        header_layout.addWidget(title)

        layout.addLayout(header_layout)

        button_layout = QHBoxLayout()

        self.send_button = QPushButton("选择文件发送")
        self.send_button.setFont(QFont("Microsoft YaHei", 10))
        self.send_button.setStyleSheet("""
            QPushButton {
                background-color: #1976D2;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 10px 20px;
            }
            QPushButton:hover {
                background-color: #1565C0;
            }
            QPushButton:disabled {
                background-color: #BDBDBD;
            }
        """)
        button_layout.addWidget(self.send_button)

        layout.addLayout(button_layout)

        layout.addStretch()

    def set_username(self, username: str):
        """Set the current username."""
        self._username = username

    def set_target_user(self, target_user: str):
        """Set the target user for file transfer."""
        self._target_user = target_user

    def request_file_send(self):
        """Open file dialog and emit send request."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择要发送的文件",
            "",
            "所有文件 (*.*)"
        )

        if file_path and hasattr(self, "_target_user"):
            self.send_file_requested.emit(self._target_user, file_path)
