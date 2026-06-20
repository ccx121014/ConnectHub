"""
Desktop Capture Module for Remote Desktop Streaming
Uses PIL and numpy for screen capture with JPEG compression
"""

import io
import time
import threading
from typing import Optional, Tuple, Dict, Callable
from dataclasses import dataclass
from enum import Enum

import numpy as np
from PIL import Image, ImageGrab, PyAccess


class CaptureState(Enum):
    """Capture state enumeration"""
    IDLE = "idle"
    CAPTURING = "capturing"
    PAUSED = "paused"
    ERROR = "error"


@dataclass
class ScreenInfo:
    """Screen information data class"""
    resolution: Tuple[int, int]
    dpi: Tuple[int, int]
    monitor_count: int
    capture_area: Optional[Tuple[int, int, int, int]] = None


@dataclass
class CaptureConfig:
    """Capture configuration data class"""
    fps: int = 15
    jpeg_quality: int = 85
    capture_cursor: bool = True
    capture_area: Optional[Tuple[int, int, int, int]] = None
    downscale_factor: float = 1.0


class DesktopCapture:
    """
    Desktop capture class for screen recording and streaming.
    Uses PIL and numpy for efficient screen capture and processing.
    """

    def __init__(self, config: Optional[CaptureConfig] = None):
        """
        Initialize DesktopCapture instance.

        Args:
            config: CaptureConfig instance with capture settings
        """
        self._config = config or CaptureConfig()
        self._state = CaptureState.IDLE
        self._capture_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._frame_lock = threading.Lock()
        self._current_frame: Optional[np.ndarray] = None
        self._last_frame_time: float = 0
        self._frame_count: int = 0
        self._error_message: Optional[str] = None
        self._frame_callback: Optional[Callable[[np.ndarray], None]] = None
        self._screen_info: Optional[ScreenInfo] = None

    @property
    def config(self) -> CaptureConfig:
        """Get capture configuration"""
        return self._config

    @property
    def state(self) -> CaptureState:
        """Get current capture state"""
        return self._state

    @property
    def frame_count(self) -> int:
        """Get total frame count"""
        return self._frame_count

    @property
    def error_message(self) -> Optional[str]:
        """Get error message if any"""
        return self._error_message

    def update_config(self, **kwargs) -> None:
        """
        Update capture configuration.

        Args:
            **kwargs: Configuration parameters to update
        """
        if 'fps' in kwargs:
            self._config.fps = max(1, min(60, kwargs['fps']))
        if 'jpeg_quality' in kwargs:
            self._config.jpeg_quality = max(1, min(100, kwargs['jpeg_quality']))
        if 'capture_cursor' in kwargs:
            self._config.capture_cursor = kwargs['capture_cursor']
        if 'capture_area' in kwargs:
            self._config.capture_area = kwargs['capture_area']
        if 'downscale_factor' in kwargs:
            self._config.downscale_factor = max(0.1, min(2.0, kwargs['downscale_factor']))

    def get_screen_info(self) -> ScreenInfo:
        """
        Get information about the primary screen.

        Returns:
            ScreenInfo object containing resolution, DPI, and monitor count
        """
        try:
            width, height = ImageGrab.grab().size
            dpi_x = 96
            dpi_y = 96
            monitor_count = 1

            self._screen_info = ScreenInfo(
                resolution=(width, height),
                dpi=(dpi_x, dpi_y),
                monitor_count=monitor_count,
                capture_area=self._config.capture_area
            )
            return self._screen_info
        except Exception as e:
            self._error_message = f"Failed to get screen info: {str(e)}"
            return ScreenInfo(
                resolution=(1920, 1080),
                dpi=(96, 96),
                monitor_count=1
            )

    def capture_screen(self) -> np.ndarray:
        """
        Capture the entire screen.

        Returns:
            numpy.ndarray: RGB image array of the captured screen
        """
        try:
            if self._config.capture_area:
                x1, y1, x2, y2 = self._config.capture_area
                screenshot = ImageGrab.grab(bbox=(x1, y1, x2, y2))
            else:
                screenshot = ImageGrab.grab()

            frame = np.array(screenshot)
            frame = frame[:, :, ::-1].copy()

            if self._config.downscale_factor != 1.0:
                new_width = int(frame.shape[1] / self._config.downscale_factor)
                new_height = int(frame.shape[0] / self._config.downscale_factor)
                pil_image = Image.fromarray(frame)
                pil_image = pil_image.resize((new_width, new_height), Image.LANCZOS)
                frame = np.array(pil_image)

            with self._frame_lock:
                self._current_frame = frame
                self._last_frame_time = time.time()
                self._frame_count += 1

            self._state = CaptureState.CAPTURING
            return frame

        except Exception as e:
            self._error_message = f"Screenshot capture failed: {str(e)}"
            self._state = CaptureState.ERROR
            return np.zeros((1080, 1920, 3), dtype=np.uint8)

    def capture_region(self, x: int, y: int, width: int, height: int) -> np.ndarray:
        """
        Capture a specific region of the screen.

        Args:
            x: X coordinate of top-left corner
            y: Y coordinate of top-left corner
            width: Width of capture region
            height: Height of capture region

        Returns:
            numpy.ndarray: RGB image array of the captured region
        """
        try:
            screenshot = ImageGrab.grab(bbox=(x, y, x + width, y + height))
            frame = np.array(screenshot)
            frame = frame[:, :, ::-1].copy()

            with self._frame_lock:
                self._current_frame = frame
                self._last_frame_time = time.time()
                self._frame_count += 1

            self._state = CaptureState.CAPTURING
            return frame

        except Exception as e:
            self._error_message = f"Region capture failed: {str(e)}"
            self._state = CaptureState.ERROR
            return np.zeros((height, width, 3), dtype=np.uint8)

    def get_current_frame(self) -> Optional[np.ndarray]:
        """
        Get the most recently captured frame.

        Returns:
            numpy.ndarray or None: Last captured frame
        """
        with self._frame_lock:
            return self._current_frame.copy() if self._current_frame is not None else None

    def compress_frame_jpeg(self, frame: np.ndarray, quality: Optional[int] = None) -> bytes:
        """
        Compress a frame using JPEG encoding.

        Args:
            frame: numpy.ndarray RGB image
            quality: JPEG quality (1-100), uses config default if not specified

        Returns:
            bytes: JPEG encoded image data
        """
        if quality is None:
            quality = self._config.jpeg_quality

        try:
            if frame.dtype != np.uint8:
                frame = frame.astype(np.uint8)

            pil_image = Image.fromarray(frame)
            buffer = io.BytesIO()
            pil_image.save(buffer, format='JPEG', quality=quality, optimize=True)
            return buffer.getvalue()

        except Exception as e:
            self._error_message = f"JPEG compression failed: {str(e)}"
            return b''

    def start_capture(self, callback: Optional[Callable[[np.ndarray], None]] = None) -> None:
        """
        Start continuous screen capture in a background thread.

        Args:
            callback: Optional callback function called with each frame
        """
        if self._state == CaptureState.CAPTURING:
            return

        self._frame_callback = callback
        self._stop_event.clear()
        self._capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._capture_thread.start()
        self._state = CaptureState.CAPTURING

    def stop_capture(self) -> None:
        """Stop continuous screen capture."""
        self._stop_event.set()
        if self._capture_thread:
            self._capture_thread.join(timeout=2.0)
            self._capture_thread = None
        self._state = CaptureState.IDLE

    def pause_capture(self) -> None:
        """Pause continuous screen capture."""
        self._state = CaptureState.PAUSED

    def resume_capture(self) -> None:
        """Resume continuous screen capture."""
        if self._state == CaptureState.PAUSED:
            self._state = CaptureState.CAPTURING

    def _capture_loop(self) -> None:
        """Internal capture loop for background capture."""
        target_interval = 1.0 / self._config.fps

        while not self._stop_event.is_set():
            frame_start = time.time()

            frame = self.capture_screen()

            if self._frame_callback:
                try:
                    self._frame_callback(frame)
                except Exception as e:
                    self._error_message = f"Callback error: {str(e)}"

            elapsed = time.time() - frame_start
            sleep_time = target_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    def capture_and_encode(self) -> Tuple[bytes, float]:
        """
        Capture a frame and return JPEG-encoded data with timestamp.

        Returns:
            Tuple of (JPEG bytes, timestamp)
        """
        frame = self.capture_screen()
        encoded = self.compress_frame_jpeg(frame)
        return encoded, self._last_frame_time

    def __enter__(self) -> 'DesktopCapture':
        """Context manager entry."""
        self.start_capture()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.stop_capture()

    def get_capture_stats(self) -> Dict:
        """
        Get capture statistics.

        Returns:
            Dict with frame count, FPS, and state info
        """
        elapsed = time.time() - self._last_frame_time if self._last_frame_time > 0 else 1
        current_fps = self._frame_count / elapsed if elapsed > 0 else 0

        return {
            'frame_count': self._frame_count,
            'current_fps': round(current_fps, 2),
            'target_fps': self._config.fps,
            'state': self._state.value,
            'error': self._error_message,
            'resolution': self._screen_info.resolution if self._screen_info else None,
            'jpeg_quality': self._config.jpeg_quality
        }
