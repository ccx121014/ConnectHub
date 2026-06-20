"""
Desktop Control Module for Remote Desktop Input Synchronization
Handles mouse and keyboard event synchronization for remote control
"""

import time
import threading
from typing import Optional, Callable, Dict, List, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import deque


class MouseButton(Enum):
    """Mouse button enumeration"""
    LEFT = 1
    MIDDLE = 2
    RIGHT = 3
    BUTTON_4 = 4
    BUTTON_5 = 5


class ControlPermission(Enum):
    """Control permission levels"""
    NONE = 0
    VIEW_ONLY = 1
    LIMITED = 2
    FULL = 3


@dataclass
class MouseEvent:
    """Mouse event data class"""
    event_type: str
    x: int
    y: int
    button: int
    timestamp: float = field(default_factory=time.time)


@dataclass
class KeyboardEvent:
    """Keyboard event data class"""
    key: str
    key_code: int
    pressed: bool
    timestamp: float = field(default_factory=time.time)
    modifiers: List[str] = field(default_factory=list)


@dataclass
class ControlConfig:
    """Control configuration"""
    enabled: bool = True
    permission_level: ControlPermission = ControlPermission.FULL
    send_rate: int = 60
    mouse_smooth: bool = True
    keyboard_enabled: bool = True
    clipboard_sync: bool = True
    clipboard_text: str = ""


class ControlPermissionManager:
    """
    Manager for control permissions.
    Handles permission requests and grants.
    """

    def __init__(self):
        self._current_permission: ControlPermission = ControlPermission.NONE
        self._permission_lock = threading.Lock()
        self._permission_callbacks: List[Callable[[ControlPermission], None]] = []
        self._pending_request: Optional[Tuple[str, float]] = None

    @property
    def current_permission(self) -> ControlPermission:
        """Get current permission level"""
        with self._permission_lock:
            return self._current_permission

    def request_permission(self, requester_id: str, level: ControlPermission) -> bool:
        """
        Request control permission.

        Args:
            requester_id: ID of the requester
            level: Requested permission level

        Returns:
            True if request is pending
        """
        with self._permission_lock:
            self._pending_request = (requester_id, level)
            return True

    def grant_permission(self, level: ControlPermission) -> None:
        """
        Grant permission level.

        Args:
            level: Permission level to grant
        """
        with self._permission_lock:
            self._current_permission = level
            for callback in self._permission_callbacks:
                try:
                    callback(level)
                except Exception:
                    pass

    def revoke_permission(self) -> None:
        """Revoke all permissions."""
        self.grant_permission(ControlPermission.NONE)

    def can_control(self) -> bool:
        """Check if current permission allows control"""
        return self._current_permission in [ControlPermission.LIMITED, ControlPermission.FULL]

    def can_view(self) -> bool:
        """Check if current permission allows viewing"""
        return self._current_permission != ControlPermission.NONE

    def add_permission_callback(self, callback: Callable[[ControlPermission], None]) -> None:
        """
        Add a permission change callback.

        Args:
            callback: Callback function
        """
        self._permission_callbacks.append(callback)

    def remove_permission_callback(self, callback: Callable[[ControlPermission], None]) -> None:
        """
        Remove a permission callback.

        Args:
            callback: Callback function to remove
        """
        if callback in self._permission_callbacks:
            self._permission_callbacks.remove(callback)


class DesktopControl:
    """
    Desktop control class for remote input synchronization.
    Sends mouse and keyboard events via WebRTC data channel.
    """

    def __init__(self, config: Optional[ControlConfig] = None):
        """
        Initialize DesktopControl instance.

        Args:
            config: ControlConfig instance
        """
        self._config = config or ControlConfig()
        self._permission_manager = ControlPermissionManager()
        self._permission_manager.add_permission_callback(self._on_permission_changed)

        self._data_channel: Optional[object] = None
        self._channel_lock = threading.Lock()

        self._mouse_event_queue: deque = deque(maxlen=100)
        self._keyboard_event_queue: deque = deque(maxlen=100)
        self._event_lock = threading.Lock()

        self._event_callbacks: Dict[str, List[Callable]] = {
            'mouse_move': [],
            'mouse_click': [],
            'mouse_release': [],
            'keyboard': [],
            'clipboard': []
        }

        self._enabled = self._config.enabled
        self._last_mouse_position: Tuple[int, int] = (0, 0)
        self._mouse_history: deque = deque(maxlen=5)

        self._is_controlling = False
        self._control_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    @property
    def config(self) -> ControlConfig:
        """Get control configuration"""
        return self._config

    @property
    def permission_manager(self) -> ControlPermissionManager:
        """Get permission manager"""
        return self._permission_manager

    @property
    def is_controlling(self) -> bool:
        """Check if currently sending control events"""
        return self._is_controlling

    @property
    def is_enabled(self) -> bool:
        """Check if control is enabled"""
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        """
        Enable or disable control.

        Args:
            enabled: Enable flag
        """
        self._enabled = enabled

    def set_data_channel(self, channel: object) -> None:
        """
        Set WebRTC data channel for sending events.

        Args:
            channel: WebRTC data channel object
        """
        with self._channel_lock:
            self._data_channel = channel

    def update_config(self, **kwargs) -> None:
        """
        Update control configuration.

        Args:
            **kwargs: Configuration parameters to update
        """
        if 'enabled' in kwargs:
            self._config.enabled = kwargs['enabled']
            self._enabled = self._config.enabled
        if 'permission_level' in kwargs:
            self._config.permission_level = kwargs['permission_level']
        if 'send_rate' in kwargs:
            self._config.send_rate = max(1, min(120, kwargs['send_rate']))
        if 'mouse_smooth' in kwargs:
            self._config.mouse_smooth = kwargs['mouse_smooth']
        if 'keyboard_enabled' in kwargs:
            self._config.keyboard_enabled = kwargs['keyboard_enabled']
        if 'clipboard_sync' in kwargs:
            self._config.clipboard_sync = kwargs['clipboard_sync']

    def start_control(self) -> None:
        """Start sending control events."""
        if self._is_controlling or not self._enabled:
            return

        self._is_controlling = True
        self._stop_event.clear()
        self._control_thread = threading.Thread(target=self._event_send_loop, daemon=True)
        self._control_thread.start()

    def stop_control(self) -> None:
        """Stop sending control events."""
        self._is_controlling = False
        self._stop_event.set()
        if self._control_thread:
            self._control_thread.join(timeout=2.0)
            self._control_thread = None

    def _on_permission_changed(self, permission: ControlPermission) -> None:
        """Callback when permission changes."""
        if permission == ControlPermission.NONE:
            self.stop_control()

    def send_mouse_move(self, x: int, y: int) -> bool:
        """
        Send mouse move event.

        Args:
            x: X coordinate
            y: Y coordinate

        Returns:
            True if event was queued
        """
        if not self._enabled or not self._permission_manager.can_control():
            return False

        if self._config.mouse_smooth and self._mouse_history:
            avg_x = int(sum(p[0] for p in self._mouse_history) / len(self._mouse_history))
            avg_y = int(sum(p[1] for p in self._mouse_history) / len(self._mouse_history))
            x = (x + avg_x) // 2
            y = (y + avg_y) // 2

        self._mouse_history.append((x, y))
        self._last_mouse_position = (x, y)

        event = MouseEvent('move', x, y, 0)
        with self._event_lock:
            self._mouse_event_queue.append(event)

        self._emit_callback('mouse_move', event)
        return True

    def send_mouse_click(self, x: int, y: int, button: MouseButton = MouseButton.LEFT) -> bool:
        """
        Send mouse click event.

        Args:
            x: X coordinate
            y: Y coordinate
            button: MouseButton enum

        Returns:
            True if event was queued
        """
        if not self._enabled or not self._permission_manager.can_control():
            return False

        event = MouseEvent('click', x, y, button.value)
        with self._event_lock:
            self._mouse_event_queue.append(event)

        self._emit_callback('mouse_click', event)
        return True

    def send_mouse_release(self, x: int, y: int, button: MouseButton = MouseButton.LEFT) -> bool:
        """
        Send mouse release event.

        Args:
            x: X coordinate
            y: Y coordinate
            button: MouseButton enum

        Returns:
            True if event was queued
        """
        if not self._enabled or not self._permission_manager.can_control():
            return False

        event = MouseEvent('release', x, y, button.value)
        with self._event_lock:
            self._mouse_event_queue.append(event)

        self._emit_callback('mouse_release', event)
        return True

    def send_mouse_scroll(self, x: int, y: int, delta_x: int, delta_y: int) -> bool:
        """
        Send mouse scroll event.

        Args:
            x: X coordinate
            y: Y coordinate
            delta_x: Horizontal scroll delta
            delta_y: Vertical scroll delta

        Returns:
            True if event was queued
        """
        if not self._enabled or not self._permission_manager.can_control():
            return False

        event = MouseEvent('scroll', x, y, 0)
        event.delta_x = delta_x
        event.delta_y = delta_y
        with self._event_lock:
            self._mouse_event_queue.append(event)

        return True

    def send_keyboard(self, key: str, pressed: bool, key_code: int = 0,
                      modifiers: Optional[List[str]] = None) -> bool:
        """
        Send keyboard event.

        Args:
            key: Key name (e.g., 'A', 'Enter', 'Space')
            pressed: True if key pressed, False if released
            key_code: Optional key code
            modifiers: List of modifier keys (e.g., ['Ctrl', 'Shift'])

        Returns:
            True if event was queued
        """
        if not self._enabled or not self._config.keyboard_enabled:
            return False

        if not self._permission_manager.can_control():
            return False

        if modifiers is None:
            modifiers = []

        event = KeyboardEvent(key, key_code, pressed, modifiers=modifiers)
        with self._event_lock:
            self._keyboard_event_queue.append(event)

        self._emit_callback('keyboard', event)
        return True

    def send_text_input(self, text: str) -> bool:
        """
        Send text input as series of keyboard events.

        Args:
            text: Text string to send

        Returns:
            True if events were queued
        """
        if not self._enabled or not self._permission_manager.can_control():
            return False

        for char in text:
            if char.isupper() or char in '!@#$%^&*()_+{}|:"<>?':
                modifiers = ['Shift']
                key = char
            else:
                modifiers = []
                key = char

            self.send_keyboard(key, True, modifiers=modifiers)
            self.send_keyboard(key, False, modifiers=modifiers)

        return True

    def send_clipboard(self, text: str) -> bool:
        """
        Send clipboard content.

        Args:
            text: Clipboard text content

        Returns:
            True if sent successfully
        """
        if not self._config.clipboard_sync:
            return False

        self._config.clipboard_text = text
        self._emit_callback('clipboard', text)
        return True

    def request_control(self, requester_id: str,
                       level: ControlPermission = ControlPermission.FULL) -> bool:
        """
        Request control permission.

        Args:
            requester_id: ID of the requesting user
            level: Requested permission level

        Returns:
            True if request was made
        """
        return self._permission_manager.request_permission(requester_id, level)

    def grant_control(self, level: ControlPermission) -> None:
        """
        Grant control permission.

        Args:
            level: Permission level to grant
        """
        self._permission_manager.grant_permission(level)

    def revoke_control(self) -> None:
        """Revoke all control permissions."""
        self._permission_manager.revoke_permission()

    def add_event_callback(self, event_type: str,
                          callback: Callable[[MouseEvent | KeyboardEvent], None]) -> None:
        """
        Add an event callback.

        Args:
            event_type: Event type ('mouse_move', 'mouse_click', etc.)
            callback: Callback function
        """
        if event_type in self._event_callbacks:
            self._event_callbacks[event_type].append(callback)

    def remove_event_callback(self, event_type: str,
                             callback: Callable[[MouseEvent | KeyboardEvent], None]) -> None:
        """
        Remove an event callback.

        Args:
            event_type: Event type
            callback: Callback function to remove
        """
        if event_type in self._event_callbacks:
            if callback in self._event_callbacks[event_type]:
                self._event_callbacks[event_type].remove(callback)

    def _emit_callback(self, event_type: str, event: MouseEvent | KeyboardEvent) -> None:
        """
        Emit event to callbacks.

        Args:
            event_type: Event type
            event: Event data
        """
        for callback in self._event_callbacks.get(event_type, []):
            try:
                callback(event)
            except Exception:
                pass

    def _event_send_loop(self) -> None:
        """Internal loop for sending events via data channel."""
        target_interval = 1.0 / self._config.send_rate

        while not self._stop_event.is_set():
            loop_start = time.time()

            with self._event_lock:
                mouse_events = list(self._mouse_event_queue)
                keyboard_events = list(self._keyboard_event_queue)
                self._mouse_event_queue.clear()
                self._keyboard_event_queue.clear()

            for event in mouse_events:
                self._send_event(self._format_mouse_event(event))

            for event in keyboard_events:
                self._send_event(self._format_keyboard_event(event))

            elapsed = time.time() - loop_start
            sleep_time = target_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    def _send_event(self, data: str) -> None:
        """
        Send event data via data channel.

        Args:
            data: JSON formatted event string
        """
        with self._channel_lock:
            if self._data_channel is not None:
                try:
                    if hasattr(self._data_channel, 'send'):
                        self._data_channel.send(data)
                except Exception:
                    pass

    def _format_mouse_event(self, event: MouseEvent) -> str:
        """
        Format mouse event as JSON string.

        Args:
            event: MouseEvent instance

        Returns:
            JSON formatted string
        """
        import json
        data = {
            'type': 'mouse',
            'event': event.event_type,
            'x': event.x,
            'y': event.y,
            'button': event.button,
            'timestamp': event.timestamp
        }
        if hasattr(event, 'delta_x'):
            data['delta_x'] = event.delta_x
            data['delta_y'] = event.delta_y
        return json.dumps(data)

    def _format_keyboard_event(self, event: KeyboardEvent) -> str:
        """
        Format keyboard event as JSON string.

        Args:
            event: KeyboardEvent instance

        Returns:
            JSON formatted string
        """
        import json
        data = {
            'type': 'keyboard',
            'key': event.key,
            'key_code': event.key_code,
            'pressed': event.pressed,
            'modifiers': event.modifiers,
            'timestamp': event.timestamp
        }
        return json.dumps(data)

    def get_control_stats(self) -> Dict:
        """
        Get control statistics.

        Returns:
            Dict with control statistics
        """
        return {
            'enabled': self._enabled,
            'is_controlling': self._is_controlling,
            'permission': self._permission_manager.current_permission.name,
            'mouse_queue_size': len(self._mouse_event_queue),
            'keyboard_queue_size': len(self._keyboard_event_queue),
            'send_rate': self._config.send_rate,
            'last_mouse_position': self._last_mouse_position,
            'keyboard_enabled': self._config.keyboard_enabled,
            'clipboard_sync': self._config.clipboard_sync
        }

    def __enter__(self) -> 'DesktopControl':
        """Context manager entry."""
        self.start_control()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.stop_control()
