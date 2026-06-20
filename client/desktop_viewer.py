"""
Desktop Viewer Module for Remote Desktop Display
PyQt5-based widget for displaying received screen frames
"""

from typing import Optional, Tuple
from dataclasses import dataclass
from enum import Enum

import numpy as np
from PyQt5.QtWidgets import QLabel, QScrollArea, QWidget, QVBoxLayout
from PyQt5.QtCore import Qt, QSize, pyqtSignal, QMutex, QMutexLocker
from PyQt5.QtGui import QImage, QPixmap, QPainter, QPen, QColor, QFont


class ScaleMode(Enum):
    """Image scaling modes"""
    FIT_WINDOW = "fit"
    STRETCH = "stretch"
    ACTUAL_SIZE = "actual"
    ZOOM_25 = "zoom_25"
    ZOOM_50 = "zoom_50"
    ZOOM_100 = "zoom_100"


@dataclass
class ViewerConfig:
    """Viewer configuration"""
    scale_mode: ScaleMode = ScaleMode.FIT_WINDOW
    jpeg_quality: int = 85
    show_cursor: bool = True
    show_connection_info: bool = True
    background_color: Tuple[int, int, int] = (40, 40, 40)
    interpolation: str = "lanczos"


class DesktopViewerWidget(QLabel):
    """
    Widget for displaying remote desktop frames.
    Supports various scaling modes and quality settings.
    """

    frame_received = pyqtSignal(np.ndarray)
    size_changed = pyqtSignal(int, int)

    def __init__(self, parent: Optional[QWidget] = None):
        """
        Initialize DesktopViewerWidget.

        Args:
            parent: Parent QWidget
        """
        super().__init__(parent)
        self._config = ViewerConfig()
        self._mutex = QMutex()
        self._current_frame: Optional[np.ndarray] = None
        self._display_fps = 0
        self._frame_count = 0
        self._last_frame_time = 0
        self._zoom_factor = 1.0
        self._cursor_position: Optional[Tuple[int, int]] = None
        self._remote_cursor_visible = False

        self.setMinimumSize(320, 240)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet(f"background-color: rgb({self._config.background_color[0]}, "
                          f"{self._config.background_color[1]}, {self._config.background_color[2]});")

        self.setScaledContents(False)
        self._update_size_policy()

    def _update_size_policy(self) -> None:
        """Update widget size policy based on scale mode."""
        if self._config.scale_mode == ScaleMode.ACTUAL_SIZE:
            self.setSizePolicy(Qt.PreferredSize, Qt.PreferredSize)
        elif self._config.scale_mode == ScaleMode.STRETCH:
            self.setSizePolicy(Qt.IgnoredSize, Qt.IgnoredSize)
        else:
            self.setSizePolicy(Qt.PreferredSize, Qt.PreferredSize)

    @property
    def config(self) -> ViewerConfig:
        """Get viewer configuration"""
        return self._config

    @property
    def current_frame(self) -> Optional[np.ndarray]:
        """Get current displayed frame"""
        with QMutexLocker(self._mutex):
            return self._current_frame.copy() if self._current_frame is not None else None

    def update_config(self, **kwargs) -> None:
        """
        Update viewer configuration.

        Args:
            **kwargs: Configuration parameters to update
        """
        if 'scale_mode' in kwargs:
            self._config.scale_mode = kwargs['scale_mode']
            self._update_size_policy()
        if 'jpeg_quality' in kwargs:
            self._config.jpeg_quality = kwargs['jpeg_quality']
        if 'show_cursor' in kwargs:
            self._config.show_cursor = kwargs['show_cursor']
        if 'show_connection_info' in kwargs:
            self._config.show_connection_info = kwargs['show_connection_info']

    def set_scale_mode(self, mode: ScaleMode) -> None:
        """
        Set the image scaling mode.

        Args:
            mode: ScaleMode enum value
        """
        self._config.scale_mode = mode
        self._update_size_policy()
        if self._current_frame is not None:
            self._display_frame(self._current_frame)

    def set_zoom(self, factor: float) -> None:
        """
        Set zoom factor for the display.

        Args:
            factor: Zoom factor (e.g., 0.5 for 50%, 2.0 for 200%)
        """
        self._zoom_factor = max(0.1, min(5.0, factor))
        if self._current_frame is not None:
            self._display_frame(self._current_frame)

    def display_frame(self, frame: np.ndarray) -> None:
        """
        Display a new frame.

        Args:
            frame: numpy.ndarray RGB image
        """
        self._display_frame(frame)

    def _display_frame(self, frame: np.ndarray) -> None:
        """
        Internal method to display a frame.

        Args:
            frame: numpy.ndarray RGB image
        """
        with QMutexLocker(self._mutex):
            self._current_frame = frame.copy()

        try:
            if frame.dtype != np.uint8:
                frame = frame.astype(np.uint8)

            height, width, channel = frame.shape
            bytes_per_line = channel * width

            q_image = QImage(frame.data, width, height, bytes_per_line, QImage.Format_RGB888)

            pixmap = self._get_scaled_pixmap(q_image, width, height)

            self._frame_count += 1
            from time import time
            current_time = time()
            if current_time - self._last_frame_time >= 1.0:
                self._display_fps = self._frame_count
                self._frame_count = 0
                self._last_frame_time = current_time

            self.setPixmap(pixmap)
            self.frame_received.emit(frame)
            self.size_changed.emit(width, height)

        except Exception as e:
            pass

    def _get_scaled_pixmap(self, q_image: QImage, width: int, height: int) -> QPixmap:
        """
        Get scaled pixmap based on current scale mode.

        Args:
            q_image: QImage to scale
            width: Original width
            height: Original height

        Returns:
            Scaled QPixmap
        """
        pixmap = QPixmap.fromImage(q_image)

        if self._config.scale_mode == ScaleMode.STRETCH:
            return pixmap.scaled(self.size(), Qt.IgnoreAspectRatio, Qt.FastTransformation)

        elif self._config.scale_mode == ScaleMode.ACTUAL_SIZE:
            return pixmap

        elif self._config.scale_mode == ScaleMode.ZOOM_25:
            return pixmap.scaled(int(width * 0.25), int(height * 0.25),
                                Qt.KeepAspectRatio, Qt.FastTransformation)

        elif self._config.scale_mode == ScaleMode.ZOOM_50:
            return pixmap.scaled(int(width * 0.5), int(height * 0.5),
                                Qt.KeepAspectRatio, Qt.FastTransformation)

        elif self._config.scale_mode == ScaleMode.ZOOM_100:
            return pixmap.scaled(int(width * 1.0), int(height * 1.0),
                                Qt.KeepAspectRatio, Qt.FastTransformation)

        else:
            return pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)

    def update_remote_cursor(self, x: int, y: int, visible: bool = True) -> None:
        """
        Update remote cursor position for overlay display.

        Args:
            x: Cursor X coordinate
            y: Cursor Y coordinate
            visible: Whether cursor is visible
        """
        self._cursor_position = (x, y)
        self._remote_cursor_visible = visible
        self.update()

    def clear_display(self) -> None:
        """Clear the display."""
        with QMutexLocker(self._mutex):
            self._current_frame = None
        self.clear()

    def get_display_info(self) -> dict:
        """
        Get display information.

        Returns:
            Dict with display statistics
        """
        with QMutexLocker(self._mutex):
            frame_shape = self._current_frame.shape if self._current_frame is not None else None

        return {
            'scale_mode': self._config.scale_mode.value,
            'zoom_factor': self._zoom_factor,
            'display_fps': self._display_fps,
            'frame_resolution': frame_shape,
            'cursor_visible': self._remote_cursor_visible,
            'cursor_position': self._cursor_position
        }


class DesktopViewerArea(QScrollArea):
    """
    Scrollable viewer area containing DesktopViewerWidget.
    Provides scroll bars for large images and better container handling.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        """
        Initialize DesktopViewerArea.

        Args:
            parent: Parent QWidget
        """
        super().__init__(parent)
        self._viewer_widget = DesktopViewerWidget(self)

        self.setWidget(self._viewer_widget)
        self.setWidgetResizable(False)
        self.setAlignment(Qt.AlignCenter)
        self.setBackgroundRole(self._viewer_widget.backgroundRole())

        self.horizontalScrollBar().setSliderTracking(True)
        self.verticalScrollBar().setSliderTracking(True)

    @property
    def viewer(self) -> DesktopViewerWidget:
        """Get the viewer widget"""
        return self._viewer_widget

    def display_frame(self, frame: np.ndarray) -> None:
        """
        Display a frame in the viewer.

        Args:
            frame: numpy.ndarray RGB image
        """
        self._viewer_widget.display_frame(frame)

    def update_config(self, **kwargs) -> None:
        """
        Update viewer configuration.

        Args:
            **kwargs: Configuration parameters
        """
        self._viewer_widget.update_config(**kwargs)

    def set_scale_mode(self, mode: ScaleMode) -> None:
        """
        Set scale mode.

        Args:
            mode: ScaleMode enum value
        """
        self._viewer_widget.set_scale_mode(mode)

    def update_remote_cursor(self, x: int, y: int, visible: bool = True) -> None:
        """
        Update remote cursor position.

        Args:
            x: Cursor X coordinate
            y: Cursor Y coordinate
            visible: Whether cursor is visible
        """
        self._viewer_widget.update_remote_cursor(x, y, visible)

    def get_display_info(self) -> dict:
        """
        Get display information.

        Returns:
            Dict with display statistics
        """
        return self._viewer_widget.get_display_info()
