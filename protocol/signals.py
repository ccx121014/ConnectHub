# -*- coding: utf-8 -*-
"""
Pure-Python signal/event system — zero external dependencies.

Drop-in replacement for PyQt5's pyqtSignal in the ConnectHub client.

Usage:
    from protocol.signals import Signal, SignalBridge

    class SignalBridge:
        def __init__(self):
            self.connected = Signal()
            self.message_received = Signal(object)
            self.error_occurred = Signal(str)

    bridge = SignalBridge()
    bridge.message_received.connect(on_msg)
    bridge.message_received.emit(some_object)
    bridge.message_received.disconnect(on_msg)

Design goals:
    * Thread-safe (threading.Lock).
    * Signal.emit(*args) dispatches to all connected callbacks.
    * Signal.connect(cb) / Signal.disconnect(cb) manage the subscriber list.
    * A failing callback is logged and does not prevent other callbacks
      from being invoked.
    * Pure Python / works with PyInstaller --onefile (no C extensions).
"""

import logging
import threading
from typing import Any, Callable, Tuple

logger = logging.getLogger(__name__)


class Signal:
    """
    Lightweight observable signal.

    The optional positional arguments (typically types like ``str``,
    ``object``, ``int``) are used purely for documentation / annotation
    purposes; they are not enforced at runtime.
    """

    def __init__(self, *arg_types: Any) -> None:
        self._arg_types: Tuple[Any, ...] = arg_types
        self._callbacks: list = []
        self._lock = threading.RLock()

    def connect(self, callback: Callable[..., Any]) -> None:
        """Register *callback* to be invoked on :meth:`emit`."""
        if not callable(callback):
            raise TypeError("Signal.connect() requires a callable")
        with self._lock:
            if callback not in self._callbacks:
                self._callbacks.append(callback)

    def disconnect(self, callback: Callable[..., Any]) -> None:
        """Remove *callback* from the subscriber list (idempotent)."""
        with self._lock:
            try:
                self._callbacks.remove(callback)
            except ValueError:
                pass

    def emit(self, *args: Any, **kwargs: Any) -> None:
        """Invoke each registered callback with the given arguments."""
        with self._lock:
            callbacks = list(self._callbacks)

        for cb in callbacks:
            try:
                cb(*args, **kwargs)
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception(
                    "Signal callback %r raised an exception: %s", cb, exc
                )

    @property
    def arg_types(self) -> Tuple[Any, ...]:
        """Return the (documentation-only) argument type hints."""
        return self._arg_types

    def __len__(self) -> int:
        with self._lock:
            return len(self._callbacks)

    def __repr__(self) -> str:
        return (
            f"Signal(arg_types={self._arg_types!r}, "
            f"subscribers={len(self._callbacks)})"
        )


class SignalBridge:
    """
    Container for the signals emitted by :class:`WebSocketClient`.

    This replaces the previous ``QObject`` subclass that used
    :func:`pyqtSignal`; the API surface is identical from the caller's
    point of view.
    """

    def __init__(self) -> None:
        self.connected = Signal()
        self.disconnected = Signal()
        self.error_occurred = Signal(str)
        self.message_received = Signal(object)
        self.reconnecting = Signal(int)
        self.connection_failed = Signal(str)

    def __repr__(self) -> str:  # pragma: no cover - convenience
        return (
            "SignalBridge("
            f"connected={len(self.connected)}, "
            f"disconnected={len(self.disconnected)}, "
            f"error_occurred={len(self.error_occurred)}, "
            f"message_received={len(self.message_received)}, "
            f"reconnecting={len(self.reconnecting)}, "
            f"connection_failed={len(self.connection_failed)})"
        )


__all__ = ["Signal", "SignalBridge"]
