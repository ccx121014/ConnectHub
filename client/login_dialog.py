"""
Login Dialog for Online Collaboration Suite
Provides authentication UI with server address, username, and password fields.
"""

from typing import Optional
from pathlib import Path
import sys as _sys

# Add project root and client dir to path for module imports (cross-platform)
_project_root = Path(__file__).parent.parent.resolve()
_sys.path.insert(0, str(_project_root))
_sys.path.insert(0, str(Path(__file__).parent))

from PyQt5 import QtGui
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QMessageBox,
    QGroupBox,
    QCheckBox,
    QProgressBar,
)


class LoginDialog(QDialog):
    """
    Login dialog for user authentication.
    Signals:
        connect_request: Emitted with (server, port, username, password) when connect is clicked
        register_request: Emitted with (server, port, username, password) when register is clicked
    """

    connect_request = pyqtSignal(str, int, str, str)
    register_request = pyqtSignal(str, int, str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("登录 - 在线协作套件")
        self.setModal(True)
        self.setMinimumWidth(400)

        self._init_ui()
        self._load_settings()

    def _init_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)

        # Server settings group
        server_group = QGroupBox("服务器设置")
        server_layout = QFormLayout(server_group)

        self.server_edit = QLineEdit()
        self.server_edit.setPlaceholderText("服务器地址 (例如: localhost)")
        self.server_edit.setText("localhost")
        server_layout.addRow("服务器:", self.server_edit)

        self.port_spin = QLineEdit()
        self.port_spin.setPlaceholderText("端口")
        self.port_spin.setText("8765")
        self.port_spin.setValidator(
            QtGui.QIntValidator(1, 65535, self) if hasattr(QtGui, 'QIntValidator') else None
        )
        server_layout.addRow("端口:", self.port_spin)

        layout.addWidget(server_group)

        # Authentication group
        auth_group = QGroupBox("用户认证")
        auth_layout = QFormLayout(auth_group)

        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("用户名")
        self.username_edit.textChanged.connect(self._on_credentials_changed)
        auth_layout.addRow("用户名:", self.username_edit)

        self.password_edit = QLineEdit()
        self.password_edit.setPlaceholderText("密码")
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.password_edit.textChanged.connect(self._on_credentials_changed)
        auth_layout.addRow("密码:", self.password_edit)

        self.show_password_checkbox = QCheckBox("显示密码")
        self.show_password_checkbox.toggled.connect(self._toggle_password_visibility)
        auth_layout.addRow("", self.show_password_checkbox)

        layout.addWidget(auth_group)

        # Remember settings
        self.remember_checkbox = QCheckBox("记住设置")
        layout.addWidget(self.remember_checkbox)

        # Status label
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #666;")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)

        # Buttons
        button_layout = QHBoxLayout()

        self.register_button = QPushButton("注册")
        self.register_button.setObjectName("register_button")
        self.register_button.clicked.connect(self._on_register_clicked)
        self.register_button.setEnabled(False)
        button_layout.addWidget(self.register_button)

        self.connect_button = QPushButton("连接")
        self.connect_button.setObjectName("connect_button")
        self.connect_button.clicked.connect(self._on_connect_clicked)
        self.connect_button.setEnabled(False)
        self.connect_button.setDefault(True)
        button_layout.addWidget(self.connect_button)

        self.cancel_button = QPushButton("取消")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)

        layout.addLayout(button_layout)

        # Progress bar for connection
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

    def _on_credentials_changed(self):
        """Enable buttons when username is entered (password is optional)."""
        username = self.username_edit.text().strip()
        has_credentials = bool(username)
        self.connect_button.setEnabled(has_credentials)
        self.register_button.setEnabled(has_credentials)

    def _toggle_password_visibility(self, checked: bool):
        """Toggle password visibility."""
        self.password_edit.setEchoMode(
            QLineEdit.Normal if checked else QLineEdit.Password
        )

    def _validate_inputs(self) -> bool:
        """Validate input fields (password is optional)."""
        server = self.server_edit.text().strip()
        port = self.port_spin.text().strip()
        username = self.username_edit.text().strip()

        if not server:
            QMessageBox.warning(self, "输入错误", "请输入服务器地址")
            self.server_edit.setFocus()
            return False

        if not port or not port.isdigit():
            QMessageBox.warning(self, "输入错误", "请输入有效的端口号")
            self.port_spin.setFocus()
            return False

        port_num = int(port)
        if port_num < 1 or port_num > 65535:
            QMessageBox.warning(self, "输入错误", "端口号必须在 1-65535 之间")
            self.port_spin.setFocus()
            return False

        if not username:
            QMessageBox.warning(self, "输入错误", "请输入用户名")
            self.username_edit.setFocus()
            return False

        if len(username) < 2:
            QMessageBox.warning(self, "输入错误", "用户名至少需要2个字符")
            self.username_edit.setFocus()
            return False

        return True

    def _on_connect_clicked(self):
        """Handle connect button click."""
        if not self._validate_inputs():
            return

        server = self.server_edit.text().strip()
        port = int(self.port_spin.text().strip())
        username = self.username_edit.text().strip()
        password = self.password_edit.text()

        self._set_connecting(True)
        self.connect_request.emit(server, port, username, password)

    def _on_register_clicked(self):
        """Handle register button click."""
        if not self._validate_inputs():
            return

        server = self.server_edit.text().strip()
        port = int(self.port_spin.text().strip())
        username = self.username_edit.text().strip()
        password = self.password_edit.text()

        self._set_connecting(True)
        self.register_request.emit(server, port, username, password)

    def _set_connecting(self, connecting: bool):
        """Update UI to show connection progress."""
        self.connect_button.setEnabled(not connecting and self._has_credentials())
        self.register_button.setEnabled(not connecting and self._has_credentials())
        self.server_edit.setEnabled(not connecting)
        self.port_spin.setEnabled(not connecting)
        self.username_edit.setEnabled(not connecting)
        self.password_edit.setEnabled(not connecting)
        self.cancel_button.setText("取消" if not connecting else "等待...")

        if connecting:
            self.status_label.setText("正在连接...")
            self.status_label.setStyleSheet("color: #0066cc;")
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 0)
        else:
            self.status_label.setText("")
            self.status_label.setStyleSheet("color: #666;")
            self.progress_bar.setVisible(False)

    def _has_credentials(self) -> bool:
        """Check if username is entered."""
        username = self.username_edit.text().strip()
        return bool(username)

    def _load_settings(self):
        """Load saved settings if any."""
        # Placeholder for loading saved settings
        pass

    def _save_settings(self):
        """Save current settings if remember is checked."""
        # Placeholder for saving settings
        pass

    def show_error(self, message: str):
        """Show an error message."""
        self._set_connecting(False)
        self.status_label.setText(message)
        self.status_label.setStyleSheet("color: #cc0000;")
        QMessageBox.critical(self, "连接错误", message)

    def show_success(self, message: str):
        """Show a success message."""
        self._set_connecting(False)
        self.status_label.setText(message)
        self.status_label.setStyleSheet("color: #00cc00;")

    def reset(self):
        """Reset the dialog to initial state."""
        self._set_connecting(False)
        self.status_label.setText("")
        self.status_label.setStyleSheet("color: #666;")

    def get_server_info(self):
        """Get server address and port."""
        return self.server_edit.text().strip(), int(self.port_spin.text().strip())

    def get_credentials(self):
        """Get username and password."""
        return self.username_edit.text().strip(), self.password_edit.text()

    def accept_with_credentials(self):
        """Accept dialog and emit connect with current credentials."""
        if self._validate_inputs():
            self.accept()

    def closeEvent(self, event):
        """Handle dialog close."""
        self._save_settings()
        super().closeEvent(event)
