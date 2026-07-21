# -*- coding: utf-8 -*-
"""
远程输入执行器 —— 使用 Windows API (ctypes) 模拟鼠标 / 键盘输入。

设计目标：
  * 零外部依赖（仅用 stdlib ctypes / sys）
  * 仅在 Windows 上真正执行；其他平台记录日志但不报错
  * 线程安全（每次调用独立，无共享状态）

被 ConnectHub 的远程桌面控制功能使用：收到对端发来的
DESKTOP_MOUSE_MOVE / CLICK / RELEASE / KEYBOARD 消息后，
调用本模块在本地执行对应的输入操作。
"""

import logging
import sys

logger = logging.getLogger(__name__)

_IS_WINDOWS = sys.platform == "win32"

if _IS_WINDOWS:
    try:
        import ctypes
        _user32 = ctypes.windll.user32
        # mouse_event / keybd_event / SetCursorPos 的函数签名
        _user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
        _user32.SetCursorPos.restype = ctypes.c_int
        _user32.mouse_event.argtypes = [
            ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong,
            ctypes.c_ulong, ctypes.c_void_p,
        ]
        _user32.mouse_event.restype = None
        _user32.keybd_event.argtypes = [
            ctypes.c_byte, ctypes.c_byte, ctypes.c_ulong, ctypes.c_void_p,
        ]
        _user32.keybd_event.restype = None
    except Exception as _exc:
        logger.warning(f"input_executor: 初始化 Windows API 失败: {_exc}")
        _user32 = None
        _IS_WINDOWS = False
else:
    _user32 = None

# mouse_event flags
_MOUSEEVENTF_MOVE = 0x0001
_MOUSEEVENTF_LEFTDOWN = 0x0002
_MOUSEEVENTF_LEFTUP = 0x0004
_MOUSEEVENTF_RIGHTDOWN = 0x0008
_MOUSEEVENTF_RIGHTUP = 0x0010
_MOUSEEVENTF_MIDDLEDOWN = 0x0020
_MOUSEEVENTF_MIDDLEUP = 0x0040
_MOUSEEVENTF_ABSOLUTE = 0x8000

# keybd_event flags
_KEYEVENTF_KEYUP = 0x0002

# 按钮 → mouse_event flags 映射
_BUTTON_DOWN_FLAGS = {
    "left": _MOUSEEVENTF_LEFTDOWN,
    "right": _MOUSEEVENTF_RIGHTDOWN,
    "middle": _MOUSEEVENTF_MIDDLEDOWN,
}
_BUTTON_UP_FLAGS = {
    "left": _MOUSEEVENTF_LEFTUP,
    "right": _MOUSEEVENTF_RIGHTUP,
    "middle": _MOUSEEVENTF_MIDDLEUP,
}


def move_mouse(x: int, y: int) -> bool:
    """移动鼠标到屏幕绝对坐标 (x, y)。"""
    if not _IS_WINDOWS or _user32 is None:
        return False
    try:
        _user32.SetCursorPos(int(x), int(y))
        return True
    except Exception as exc:
        logger.debug(f"move_mouse({x},{y}) 失败: {exc}")
        return False


def mouse_down(x: int, y: int, button: str = "left") -> bool:
    """在 (x, y) 按下鼠标键。"""
    if not _IS_WINDOWS or _user32 is None:
        return False
    try:
        _user32.SetCursorPos(int(x), int(y))
        flags = _BUTTON_DOWN_FLAGS.get(button, _MOUSEEVENTF_LEFTDOWN)
        _user32.mouse_event(flags, 0, 0, 0, None)
        return True
    except Exception as exc:
        logger.debug(f"mouse_down({x},{y},{button}) 失败: {exc}")
        return False


def mouse_up(x: int, y: int, button: str = "left") -> bool:
    """在 (x, y) 释放鼠标键。"""
    if not _IS_WINDOWS or _user32 is None:
        return False
    try:
        _user32.SetCursorPos(int(x), int(y))
        flags = _BUTTON_UP_FLAGS.get(button, _MOUSEEVENTF_LEFTUP)
        _user32.mouse_event(flags, 0, 0, 0, None)
        return True
    except Exception as exc:
        logger.debug(f"mouse_up({x},{y},{button}) 失败: {exc}")
        return False


def key_event(key_code: int, is_down: bool = True) -> bool:
    """模拟键盘事件。key_code 在 Windows 上为 VK code。"""
    if not _IS_WINDOWS or _user32 is None:
        return False
    try:
        vk = int(key_code) & 0xFF
        flags = 0 if is_down else _KEYEVENTF_KEYUP
        _user32.keybd_event(vk, 0, flags, None)
        return True
    except Exception as exc:
        logger.debug(f"key_event({key_code},{is_down}) 失败: {exc}")
        return False


def is_supported() -> bool:
    """返回当前平台是否支持远程输入执行。"""
    return _IS_WINDOWS and _user32 is not None
