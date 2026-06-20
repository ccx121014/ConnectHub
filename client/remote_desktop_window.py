"""
Remote Desktop Window Module
Main window for remote desktop view and control with WebRTC streaming
"""

from typing import Optional, Dict, Any, Callable
from enum import Enum

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QSlider, QComboBox, QToolBar,
                             QStatusBar, QFrame, QSizePolicy, QMessageBox,
                             QFileDialog, QGroupBox)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot, QSize
from PyQt5.QtGui import QIcon, QFont, QPalette, QColor

from desktop_capture import DesktopCapture, CaptureConfig, CaptureState, ScreenInfo
from desktop_viewer import DesktopViewerWidget, DesktopViewerArea, ViewerConfig, ScaleMode
from desktop_control import (DesktopControl, ControlConfig, ControlPermission,
                             MouseButton, ControlPermissionManager)


class ConnectionState(Enum):
    """Connection state enumeration"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    SHARING = "sharing"
    VIEWING = "viewing"
    ERROR = "error"


class RemoteDesktopWindow(QWidget):
    """
    Main remote desktop window.
    Provides full remote view with toolbar, control toggle, and settings.
    """

    connection_state_changed = pyqtSignal(str)
    control_permission_changed = pyqtSignal(str)
    frame_captured = pyqtSignal(object)
    error_occurred = pyqtSignal(str)

    def __init__(self, mode: str = "viewer", parent: Optional[QWidget] = None):
        """
        Initialize RemoteDesktopWindow.

        Args:
            mode: "viewer" or "sharer" mode
            parent: Parent QWidget
        """
        super().__init__(parent)
        self._mode = mode

        self._capture: Optional[DesktopCapture] = None
        self._control: Optional[DesktopControl] = None
        self._viewer_area: Optional[DesktopViewerArea] = None
        self._viewer_widget: Optional[DesktopViewerWidget] = None

        self._connection_state = ConnectionState.DISCONNECTED
        self._webrtc_connection: Optional[object] = None
        self._data_channel: Optional[object] = None

        self._capture_timer: Optional[QTimer] = None
        self._stats_timer: Optional[QTimer] = None

        self._local_user_id: str = "local_user"
        self._remote_user_id: Optional[str] = None

        self._init_ui()
        self._init_capture()
        self._init_control()
        self._init_timers()

    def _init_ui(self) -> None:
        """Initialize user interface."""
        self.setWindowTitle(f"Remote Desktop - {self._mode.capitalize()}")
        self.setMinimumSize(800, 600)
        self.setStyleSheet(self._get_stylesheet())

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self._toolbar = self._create_toolbar()
        main_layout.addWidget(self._toolbar)

        self._viewer_area = DesktopViewerArea()
        main_layout.addWidget(self._viewer_area, 1)

        self._status_bar = self._create_status_bar()
        main_layout.addWidget(self._status_bar)

        self._settings_panel = self._create_settings_panel()
        self._settings_panel.setVisible(False)
        main_layout.addWidget(self._settings_panel)

        self._update_ui_state()

    def _get_stylesheet(self) -> str:
        """Get application stylesheet."""
        return """
            QWidget {
                background-color: #2b2b2b;
                color: #ffffff;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 12px;
            }
            QToolBar {
                background-color: #3c3c3c;
                border: none;
                padding: 4px;
                spacing: 8px;
            }
            QPushButton {
                background-color: #4a4a4a;
                border: 1px solid #5a5a5a;
                border-radius: 4px;
                padding: 6px 12px;
                min-width: 60px;
            }
            QPushButton:hover {
                background-color: #5a5a5a;
            }
            QPushButton:pressed {
                background-color: #3a3a3a;
            }
            QPushButton:disabled {
                background-color: #3a3a3a;
                color: #808080;
            }
            QPushButton.primary {
                background-color: #0078d4;
                border-color: #0078d4;
            }
            QPushButton.primary:hover {
                background-color: #1084d8;
            }
            QPushButton.danger {
                background-color: #d13438;
                border-color: #d13438;
            }
            QPushButton.danger:hover {
                background-color: #e04444;
            }
            QSlider::groove:horizontal {
                border: 1px solid #5a5a5a;
                height: 4px;
                background: #3a3a3a;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #0078d4;
                border: 1px solid #0078d4;
                width: 14px;
                margin: -5px 0;
                border-radius: 7px;
            }
            QComboBox {
                background-color: #4a4a4a;
                border: 1px solid #5a5a5a;
                border-radius: 4px;
                padding: 4px 8px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QStatusBar {
                background-color: #3c3c3c;
                border-top: 1px solid #4a4a4a;
            }
            QLabel {
                background-color: transparent;
            }
            QGroupBox {
                border: 1px solid #5a5a5a;
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px;
            }
        """

    def _create_toolbar(self) -> QToolBar:
        """
        Create toolbar with controls.

        Returns:
            QToolBar instance
        """
        toolbar = QToolBar()
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(24, 24))

        self._btn_connect = QPushButton("Connect")
        self._btn_connect.setObjectName("primary")
        self._btn_connect.clicked.connect(self._on_connect_clicked)
        toolbar.addWidget(self._btn_connect)

        self._btn_disconnect = QPushButton("Disconnect")
        self._btn_disconnect.setEnabled(False)
        self._btn_disconnect.clicked.connect(self._on_disconnect_clicked)
        toolbar.addWidget(self._btn_disconnect)

        toolbar.addSeparator()

        self._btn_control = QPushButton("Request Control")
        self._btn_control.setEnabled(False)
        self._btn_control.clicked.connect(self._on_control_clicked)
        toolbar.addWidget(self._btn_control)

        toolbar.addSeparator()

        self._btn_settings = QPushButton("Settings")
        self._btn_settings.clicked.connect(self._on_settings_clicked)
        toolbar.addWidget(self._btn_settings)

        toolbar.addSeparator()

        self._btn_fullscreen = QPushButton("Fullscreen")
        self._btn_fullscreen.clicked.connect(self._on_fullscreen_clicked)
        toolbar.addWidget(self._btn_fullscreen)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        toolbar.addWidget(spacer)

        self._lbl_resolution = QLabel("Resolution: --")
        toolbar.addWidget(self._lbl_resolution)

        toolbar.addSeparator()

        self._lbl_fps = QLabel("FPS: --")
        toolbar.addWidget(self._lbl_fps)

        return toolbar

    def _create_status_bar(self) -> QStatusBar:
        """
        Create status bar.

        Returns:
            QStatusBar instance
        """
        status_bar = QStatusBar()

        self._lbl_connection = QLabel("Status: Disconnected")
        status_bar.addWidget(self._lbl_connection)

        status_bar.addPermanentWidget(QLabel("|"))

        self._lbl_control_status = QLabel("Control: None")
        status_bar.addPermanentWidget(self._lbl_control_status)

        status_bar.addPermanentWidget(QLabel("|"))

        self._lbl_bandwidth = QLabel("Bandwidth: --")
        status_bar.addPermanentWidget(self._lbl_bandwidth)

        return status_bar

    def _create_settings_panel(self) -> QWidget:
        """
        Create settings panel widget.

        Returns:
            QWidget instance
        """
        panel = QFrame()
        panel.setFrameShape(QFrame.StyledPanel)
        layout = QVBoxLayout(panel)

        capture_group = QGroupBox("Capture Settings")
        capture_layout = QVBoxLayout(capture_group)

        fps_layout = QHBoxLayout()
        fps_layout.addWidget(QLabel("FPS:"))
        self._slider_fps = QSlider(Qt.Horizontal)
        self._slider_fps.setMinimum(5)
        self._slider_fps.setMaximum(30)
        self._slider_fps.setValue(15)
        self._slider_fps.setTickPosition(QSlider.TicksBelow)
        self._slider_fps.setTickInterval(5)
        self._slider_fps.valueChanged.connect(self._on_fps_changed)
        fps_layout.addWidget(self._slider_fps)
        self._lbl_fps_value = QLabel("15")
        fps_layout.addWidget(self._lbl_fps_value)
        capture_layout.addLayout(fps_layout)

        quality_layout = QHBoxLayout()
        quality_layout.addWidget(QLabel("Quality:"))
        self._slider_quality = QSlider(Qt.Horizontal)
        self._slider_quality.setMinimum(30)
        self._slider_quality.setMaximum(100)
        self._slider_quality.setValue(85)
        self._slider_quality.setTickPosition(QSlider.TicksBelow)
        self._slider_quality.setTickInterval(10)
        self._slider_quality.valueChanged.connect(self._on_quality_changed)
        quality_layout.addWidget(self._slider_quality)
        self._lbl_quality_value = QLabel("85%")
        quality_layout.addWidget(self._lbl_quality_value)
        capture_layout.addLayout(quality_layout)

        layout.addWidget(capture_group)

        display_group = QGroupBox("Display Settings")
        display_layout = QVBoxLayout(display_group)

        scale_layout = QHBoxLayout()
        scale_layout.addWidget(QLabel("Scale Mode:"))
        self._combo_scale = QComboBox()
        self._combo_scale.addItems(["Fit Window", "Stretch", "Actual Size", "25%", "50%", "100%"])
        self._combo_scale.setCurrentIndex(0)
        self._combo_scale.currentIndexChanged.connect(self._on_scale_changed)
        scale_layout.addWidget(self._combo_scale)
        scale_layout.addStretch()
        display_layout.addLayout(scale_layout)

        layout.addWidget(display_group)

        close_btn = QPushButton("Close Settings")
        close_btn.clicked.connect(lambda: self._settings_panel.setVisible(False))
        layout.addWidget(close_btn)

        return panel

    def _init_capture(self) -> None:
        """Initialize screen capture."""
        if self._mode == "sharer":
            config = CaptureConfig(fps=15, jpeg_quality=85)
            self._capture = DesktopCapture(config)
            screen_info = self._capture.get_screen_info()
            self._lbl_resolution.setText(f"Resolution: {screen_info.resolution[0]}x{screen_info.resolution[1]}")

    def _init_control(self) -> None:
        """Initialize desktop control."""
        config = ControlConfig(enabled=True, permission_level=ControlPermission.FULL)
        self._control = DesktopControl(config)
        self._control.add_event_callback('mouse_move', self._on_local_mouse_move)

    def _init_timers(self) -> None:
        """Initialize timers for capture and stats."""
        self._capture_timer = QTimer()
        self._capture_timer.timeout.connect(self._capture_frame)

        self._stats_timer = QTimer()
        self._stats_timer.timeout.connect(self._update_stats)
        self._stats_timer.start(1000)

    def _capture_frame(self) -> None:
        """Capture and send a frame."""
        if self._capture and self._connection_state == ConnectionState.SHARING:
            frame = self._capture.capture_screen()
            self.frame_captured.emit(frame)

            if self._viewer_widget:
                self._viewer_widget.display_frame(frame)

    def _update_stats(self) -> None:
        """Update statistics display."""
        if self._capture:
            stats = self._capture.get_capture_stats()
            self._lbl_fps.setText(f"FPS: {stats['current_fps']}")

        if self._control:
            control_stats = self._control.get_control_stats()
            perm = control_stats['permission']
            self._lbl_control_status.setText(f"Control: {perm}")

    def _update_ui_state(self) -> None:
        """Update UI based on connection state."""
        is_connected = self._connection_state in [ConnectionState.CONNECTED,
                                                   ConnectionState.SHARING,
                                                   ConnectionState.VIEWING]
        is_sharing = self._connection_state == ConnectionState.SHARING
        is_viewing = self._connection_state == ConnectionState.VIEWING

        self._btn_connect.setEnabled(not is_connected)
        self._btn_disconnect.setEnabled(is_connected)
        self._btn_control.setEnabled(is_viewing and self._control)
        self._btn_fullscreen.setEnabled(is_connected)

        state_text = {
            ConnectionState.DISCONNECTED: "Disconnected",
            ConnectionState.CONNECTING: "Connecting...",
            ConnectionState.CONNECTED: "Connected",
            ConnectionState.SHARING: "Sharing Desktop",
            ConnectionState.VIEWING: "Viewing Remote",
            ConnectionState.ERROR: "Error"
        }.get(self._connection_state, "Unknown")

        self._lbl_connection.setText(f"Status: {state_text}")
        self.connection_state_changed.emit(state_text)

    @pyqtSlot()
    def _on_connect_clicked(self) -> None:
        """Handle connect button click."""
        if self._mode == "sharer":
            self._start_sharing()
        else:
            self._request_view()

    @pyqtSlot()
    def _on_disconnect_clicked(self) -> None:
        """Handle disconnect button click."""
        self._disconnect()

    @pyqtSlot()
    def _on_control_clicked(self) -> None:
        """Handle control button click."""
        if self._control:
            if self._control.permission_manager.current_permission == ControlPermission.NONE:
                self._control.request_control(self._remote_user_id or "remote",
                                              ControlPermission.FULL)
                self._btn_control.setText("Waiting for Control...")
            else:
                self._control.revoke_control()
                self._btn_control.setText("Request Control")

    @pyqtSlot()
    def _on_settings_clicked(self) -> None:
        """Handle settings button click."""
        self._settings_panel.setVisible(not self._settings_panel.isVisible())

    @pyqtSlot()
    def _on_fullscreen_clicked(self) -> None:
        """Handle fullscreen button click."""
        if self.isFullScreen():
            self.showNormal()
            self._btn_fullscreen.setText("Fullscreen")
        else:
            self.showFullScreen()
            self._btn_fullscreen.setText("Exit Fullscreen")

    @pyqtSlot(int)
    def _on_fps_changed(self, value: int) -> None:
        """
        Handle FPS slider change.

        Args:
            value: New FPS value
        """
        self._lbl_fps_value.setText(str(value))
        if self._capture:
            self._capture.update_config(fps=value)

    @pyqtSlot(int)
    def _on_quality_changed(self, value: int) -> None:
        """
        Handle quality slider change.

        Args:
            value: New quality value
        """
        self._lbl_quality_value.setText(f"{value}%")
        if self._capture:
            self._capture.update_config(jpeg_quality=value)
        if self._viewer_widget:
            self._viewer_widget.update_config(jpeg_quality=value)

    @pyqtSlot(int)
    def _on_scale_changed(self, index: int) -> None:
        """
        Handle scale mode change.

        Args:
            index: Combo box index
        """
        modes = [ScaleMode.FIT_WINDOW, ScaleMode.STRETCH, ScaleMode.ACTUAL_SIZE,
                ScaleMode.ZOOM_25, ScaleMode.ZOOM_50, ScaleMode.ZOOM_100]
        if self._viewer_area and index < len(modes):
            self._viewer_area.set_scale_mode(modes[index])

    @pyqtSlot(object)
    def _on_local_mouse_move(self, event) -> None:
        """
        Handle local mouse move for remote cursor update.

        Args:
            event: Mouse event
        """
        if self._viewer_widget and self._connection_state == ConnectionState.VIEWING:
            self._viewer_widget.update_remote_cursor(event.x, event.y)

    def _start_sharing(self) -> None:
        """Start desktop sharing (sharer mode)."""
        self._connection_state = ConnectionState.CONNECTING
        self._update_ui_state()

        if self._capture:
            self._capture.start_capture()
            self._capture_timer.start(1000 // 15)

        self._connection_state = ConnectionState.SHARING
        self._update_ui_state()

    def _request_view(self) -> None:
        """Request to view remote desktop (viewer mode)."""
        self._connection_state = ConnectionState.CONNECTING
        self._update_ui_state()

        self._connection_state = ConnectionState.VIEWING
        self._update_ui_state()

    def _disconnect(self) -> None:
        """Disconnect from remote desktop."""
        if self._capture_timer:
            self._capture_timer.stop()

        if self._capture:
            self._capture.stop_capture()

        if self._control:
            self._control.stop_control()
            self._control.revoke_control()

        self._connection_state = ConnectionState.DISCONNECTED
        self._update_ui_state()

    def set_webrtc_connection(self, connection: object) -> None:
        """
        Set WebRTC connection for streaming.

        Args:
            connection: WebRTC peer connection object
        """
        self._webrtc_connection = connection

    def set_data_channel(self, channel: object) -> None:
        """
        Set WebRTC data channel for control events.

        Args:
            channel: WebRTC data channel object
        """
        self._data_channel = channel
        if self._control:
            self._control.set_data_channel(channel)

    def receive_frame(self, frame: bytes) -> None:
        """
        Receive and display a frame from remote.

        Args:
            frame: JPEG encoded frame data
        """
        if self._viewer_area:
            import numpy as np
            from PIL import Image
            import io

            try:
                image = Image.open(io.BytesIO(frame))
                frame_array = np.array(image)
                if frame_array.shape[2] == 4:
                    frame_array = frame_array[:, :, :3]
                self._viewer_area.display_frame(frame_array)
            except Exception:
                pass

    def start_viewing(self) -> None:
        """Start viewing mode."""
        self._connection_state = ConnectionState.VIEWING
        self._update_ui_state()
        if self._control:
            self._control.start_control()

    def start_sharing(self) -> None:
        """Start sharing mode."""
        self._start_sharing()

    def get_capture(self) -> Optional[DesktopCapture]:
        """Get the capture instance."""
        return self._capture

    def get_control(self) -> Optional[DesktopControl]:
        """Get the control instance."""
        return self._control

    def get_viewer(self) -> Optional[DesktopViewerArea]:
        """Get the viewer area."""
        return self._viewer_area

    def get_connection_state(self) -> ConnectionState:
        """Get current connection state."""
        return self._connection_state

    def closeEvent(self, event) -> None:
        """Handle window close event."""
        self._disconnect()
        if self._stats_timer:
            self._stats_timer.stop()
        event.accept()
