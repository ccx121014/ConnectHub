"""
ConnectHub 主窗口（Tkinter 实现，无 PyQt5）。

负责：
  - 把 ContactListWidget / ChatTabWidget / FileTransferManager / Updater
    组合成一个完整的主窗口 UI
  - 处理来自 WebSocket 客户端的消息并分派到各子模块
  - 管理文件传输标签页与远程桌面标签页
  - 提供登出、检查更新等顶层操作的信号

所有由后台线程（WebSocket 接收线程等）触发的 UI 更新都通过
``master.after(0, callback)`` 调度到 Tk 主线程，保证线程安全。
"""

import base64
import io
import json
import logging
import os
import sys
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Dict, List, Optional

# ---- 模块导入：保证能从 protocol / client 子包导入 ----
_project_root = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(_project_root))
sys.path.insert(0, str(Path(__file__).parent))

from protocol.messages import Message, MessageType
from protocol.signals import Signal

from client.contact_list import ContactListWidget
from client.chat_widget import ChatTabWidget
from client.file_transfer import FileTransferManager
from client.updater import Updater
from client import input_executor

logger = logging.getLogger(__name__)

# =============================================================
# 工具函数
# =============================================================

def _load_version_info() -> Dict[str, Any]:
    """从 version.json 读取版本信息（兼容 onefile / onedir / 源码运行）。"""
    candidates = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "version.json")
    candidates.append(_project_root / "version.json")
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).parent / "version.json")
    for path in candidates:
        try:
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as exc:
            logger.warning(f"读取 {path} 失败: {exc}")
    return {"version": "0.0.0", "repo_owner": "ccx121014", "repo_name": "ConnectHub"}


def _human_size(num_bytes: int) -> str:
    """把字节数格式化为易读字符串。"""
    if num_bytes is None:
        return "?"
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(num_bytes)
    for u in units:
        if size < 1024 or u == units[-1]:
            return f"{size:.1f} {u}"
        size /= 1024
    return f"{num_bytes} B"


# =============================================================
# 文件传输标签页
# =============================================================

class FileTransferFrame(ttk.Frame):
    """文件传输标签页 UI：
        - 顶部下拉选择目标用户 + 选择并发送文件按钮
        - 下方滚动区域列出活跃的传输会话（进度条 + 状态）
    """

    def __init__(self, master: tk.Misc, ft_manager: FileTransferManager,
                 get_online_contacts_cb=None, **kwargs):
        super().__init__(master, **kwargs)
        self._ft = ft_manager
        self._get_online_contacts = get_online_contacts_cb or (lambda: [])

        # 存储每个 file_id 的 UI 控件引用
        self._session_widgets: Dict[str, Dict[str, Any]] = {}

        self._init_ui()
        self._connect_signals()

    # ---------------------- UI ----------------------

    def _init_ui(self):
        # 顶部：目标用户 + 发送按钮
        top = ttk.Frame(self)
        top.pack(fill="x", padx=8, pady=8)

        ttk.Label(top, text="目标用户:").pack(side="left", padx=(0, 6))
        self._target_var = tk.StringVar(value="")
        self._target_combo = ttk.Combobox(
            top, textvariable=self._target_var,
            state="readonly", width=25
        )
        self._target_combo.pack(side="left", padx=(0, 8))

        self._send_btn = ttk.Button(
            top, text="选择文件并发送", command=self._on_send_clicked
        )
        self._send_btn.pack(side="left")

        # 滚动列表区
        list_frame = ttk.LabelFrame(self, text="传输列表")
        list_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self._canvas = tk.Canvas(list_frame, bg="#FFFFFF", highlightthickness=0)
        self._scroll = ttk.Scrollbar(
            list_frame, orient="vertical", command=self._canvas.yview
        )
        self._canvas.configure(yscrollcommand=self._scroll.set)
        self._canvas.pack(side="left", fill="both", expand=True, padx=(4, 0), pady=4)
        self._scroll.pack(side="right", fill="y", pady=4)

        self._inner = ttk.Frame(self._canvas)
        self._inner_window = self._canvas.create_window(
            (0, 0), window=self._inner, anchor="nw"
        )
        self._inner.bind(
            "<Configure>",
            lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all"))
        )
        self._canvas.bind(
            "<Configure>",
            lambda e: self._canvas.itemconfigure(self._inner_window, width=e.width)
        )

        # 空状态占位
        self._empty_label = ttk.Label(
            self._inner, text="（暂无文件传输任务）", foreground="#9E9E9E",
            padding=12, anchor="center"
        )
        self._empty_label.pack(fill="x", pady=8)

        # 滚轮绑定
        self._bind_mousewheel(self._canvas)
        self._bind_mousewheel(self._inner)

    def _bind_mousewheel(self, widget):
        def _on_wheel(event):
            if event.num == 4:
                self._canvas.yview_scroll(-1, "units")
            elif event.num == 5:
                self._canvas.yview_scroll(1, "units")
            else:
                self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        widget.bind("<MouseWheel>", _on_wheel)
        widget.bind("<Button-4>", _on_wheel)
        widget.bind("<Button-5>", _on_wheel)

    # ---------------------- 信号 ----------------------

    def _connect_signals(self):
        self._ft.transfer_progress.connect(self._on_progress)
        self._ft.transfer_completed.connect(self._on_completed)
        self._ft.transfer_error.connect(self._on_error)
        self._ft.transfer_accepted.connect(self._on_accepted)
        self._ft.transfer_rejected.connect(self._on_rejected)

    # ---------------------- 外部操作 ----------------------

    def refresh_targets(self):
        """下拉菜单刷新为当前在线的联系人列表。"""
        contacts = list(self._get_online_contacts())
        self._target_combo["values"] = contacts
        if self._target_var.get() not in contacts and contacts:
            self._target_var.set(contacts[0])

    def start_transfer(self, target: str, file_path: str):
        """启动一个发送任务（由外部调用的便捷入口）。"""
        try:
            file_id = self._ft.start_transfer(target, file_path)
            # 立即创建 UI 条目
            self._ensure_session_row(file_id, target,
                                     os.path.basename(file_path),
                                     os.path.getsize(file_path),
                                     direction="send")
        except Exception as exc:
            messagebox.showerror("发送失败", f"无法发送文件: {exc}")

    # ---------------------- 内部事件 ----------------------

    def _on_send_clicked(self):
        target = self._target_var.get().strip()
        if not target:
            messagebox.showwarning("提示", "请先选择一个目标用户")
            return
        file_path = filedialog.askopenfilename(title="选择要发送的文件")
        if not file_path:
            return
        self.start_transfer(target, file_path)

    # 来自 FileTransferManager 的信号回调（可能在后台线程触发）

    def _on_progress(self, file_id: str, sent_bytes: int, total: int):
        self._run_ui(lambda: self._do_update_progress(file_id, sent_bytes, total))

    def _on_completed(self, file_id: str, local_path: str):
        self._run_ui(lambda: self._do_mark_completed(file_id, local_path))

    def _on_error(self, file_id: str, error: str):
        self._run_ui(lambda: self._do_mark_error(file_id, error))

    def _on_accepted(self, file_id: str):
        self._run_ui(lambda: self._do_set_status(file_id, "传输中"))

    def _on_rejected(self, file_id: str):
        self._run_ui(lambda: self._do_set_status(file_id, "已拒绝"))

    # ---------------------- UI 更新 ----------------------

    def _ensure_session_row(self, file_id: str, target: str, file_name: str,
                            file_size: int, direction: str = "send"):
        """为会话创建一行 UI 条目。如果已存在则忽略。"""
        if file_id in self._session_widgets:
            return

        self._empty_label.pack_forget()

        row = ttk.Frame(self._inner, relief="groove", padding=6)
        row.pack(fill="x", padx=6, pady=4)

        # 第一行：目标 + 文件名 + 方向提示
        header = ttk.Frame(row)
        header.pack(fill="x")

        arrow = "→" if direction == "send" else "←"
        title_text = f"{arrow} {target} — {file_name} ({_human_size(file_size)})"
        title = ttk.Label(header, text=title_text, anchor="w")
        title.pack(side="left", fill="x", expand=True)

        cancel_btn = ttk.Button(
            header, text="取消", width=6,
            command=lambda fid=file_id: self._cancel_and_remove(fid)
        )
        cancel_btn.pack(side="right")

        # 第二行：进度条 + 状态文字
        bar_row = ttk.Frame(row)
        bar_row.pack(fill="x", pady=(4, 0))

        status_var = tk.StringVar(value="等待对方接受")
        status_label = ttk.Label(bar_row, textvariable=status_var, width=10)
        status_label.pack(side="left", padx=(0, 8))

        progress = ttk.Progressbar(
            bar_row, orient="horizontal", mode="determinate", maximum=100
        )
        progress.pack(side="left", fill="x", expand=True)

        pct_var = tk.StringVar(value="0%")
        ttk.Label(bar_row, textvariable=pct_var, width=8, anchor="e").pack(
            side="left", padx=(8, 0)
        )

        self._session_widgets[file_id] = {
            "row": row, "progress": progress,
            "status_var": status_var, "pct_var": pct_var,
            "total": file_size, "cancel_btn": cancel_btn,
        }

    def _do_update_progress(self, file_id: str, sent_bytes: int, total: int):
        widgets = self._session_widgets.get(file_id)
        if widgets is None:
            # 可能是接收端，尚未创建 UI 条目
            session = self._ft.get_session(file_id)
            if session is None:
                return
            self._ensure_session_row(
                file_id, session.target, session.file_name or file_id,
                session.file_size, direction=session.direction
            )
            widgets = self._session_widgets.get(file_id)
            if widgets is None:
                return
        if total and total > 0:
            pct = int(min(100, (sent_bytes / total) * 100))
        else:
            pct = 0
        widgets["progress"]["value"] = pct
        widgets["pct_var"].set(f"{pct}% ({_human_size(sent_bytes)})")
        widgets["status_var"].set("传输中")

    def _do_mark_completed(self, file_id: str, local_path: str):
        widgets = self._session_widgets.get(file_id)
        if widgets is None:
            return
        widgets["progress"]["value"] = 100
        widgets["pct_var"].set("100%")
        widgets["status_var"].set("已完成")
        widgets["cancel_btn"].configure(state="disabled")
        # 把文件位置浮在按钮上作为提示
        widgets["cancel_btn"].configure(text="完成")

    def _do_mark_error(self, file_id: str, error: str):
        widgets = self._session_widgets.get(file_id)
        if widgets is None:
            return
        widgets["status_var"].set(f"失败: {error[:20]}")

    def _do_set_status(self, file_id: str, status: str):
        widgets = self._session_widgets.get(file_id)
        if widgets is None:
            return
        widgets["status_var"].set(status)

    def _cancel_and_remove(self, file_id: str):
        try:
            self._ft.cancel_transfer(file_id)
        except Exception:
            pass
        widgets = self._session_widgets.get(file_id)
        if widgets is not None:
            widgets["row"].destroy()
            del self._session_widgets[file_id]
        if not self._session_widgets:
            self._empty_label.pack(fill="x", pady=8)

    def _run_ui(self, fn):
        """把 UI 操作调度到 Tk 主线程。"""
        try:
            root = self.winfo_toplevel()
            if root is not None and hasattr(root, "after"):
                root.after(0, fn)
                return
        except Exception:
            pass
        # 回退：直接调用
        try:
            fn()
        except Exception as exc:
            logger.debug(f"FileTransferFrame UI 更新异常: {exc}")


# =============================================================
# 远程桌面标签页
# =============================================================

class DesktopFrame(ttk.Frame):
    """远程桌面标签页：
        - 顶部：目标用户下拉 + 请求共享 / 停止共享 按钮 + 状态
        - 中部：显示收到的画面帧
        - 若本机安装 Pillow，可用屏幕截图主动共享给对方
    """

    def __init__(self, master: tk.Misc, ws_client=None,
                 get_online_contacts_cb=None, **kwargs):
        super().__init__(master, **kwargs)
        self._ws = ws_client
        self._get_online_contacts = get_online_contacts_cb or (lambda: [])

        self._capturing = False
        self._capture_timer: Optional[threading.Timer] = None
        self._frame_refs: List[Any] = []  # 防止 PhotoImage 被 GC
        self._sharer_target: Optional[str] = None  # 正在请求我屏幕的用户

        # 远程控制相关
        self._viewing_target: Optional[str] = None  # 我正在查看谁的屏幕（作为查看方）
        self._allow_control = tk.BooleanVar(value=True)  # 作为被控方是否允许对方控制
        self._last_image_rect: Optional[tuple] = None  # (x, y, w, h) 图片在 canvas 上的实际显示矩形
        self._last_screen_size: tuple = (0, 0)  # 对方屏幕原始尺寸 (w, h)

        # 检测 Pillow
        self._pil_available = False
        try:
            import PIL.ImageGrab  # noqa: F401
            import PIL.Image  # noqa: F401
            import PIL.ImageTk  # noqa: F401
            self._pil_available = True
        except Exception:
            self._pil_available = False

        self._init_ui()
        self._bind_control_events()

    # ---------------------- UI ----------------------

    def _init_ui(self):
        top = ttk.Frame(self)
        top.pack(fill="x", padx=8, pady=8)

        ttk.Label(top, text="目标用户:").pack(side="left", padx=(0, 6))
        self._target_var = tk.StringVar(value="")
        self._target_combo = ttk.Combobox(
            top, textvariable=self._target_var, state="readonly", width=25
        )
        self._target_combo.pack(side="left", padx=(0, 8))

        self._request_btn = ttk.Button(
            top, text="请求共享屏幕", command=self._on_request_share
        )
        self._request_btn.pack(side="left", padx=(0, 6))

        self._stop_btn = ttk.Button(
            top, text="停止共享", command=self._on_stop, state="disabled"
        )
        self._stop_btn.pack(side="left", padx=(0, 8))

        # 允许远程控制复选框（作为被控方）
        self._control_chk = ttk.Checkbutton(
            top, text="允许远程控制", variable=self._allow_control
        )
        self._control_chk.pack(side="left")

        self._status_var = tk.StringVar(value="就绪")
        ttk.Label(self, textvariable=self._status_var,
                  anchor="w", padding=(8, 4)).pack(fill="x")

        # 显示区：大 Canvas，绑定 resize
        self._display_container = ttk.Frame(self, relief="sunken", padding=4)
        self._display_container.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self._display_canvas = tk.Canvas(
            self._display_container, bg="#1E1E1E", highlightthickness=0,
            cursor="hand1" if input_executor.is_supported() else "arrow",
        )
        self._display_canvas.pack(fill="both", expand=True)
        self._canvas_image_id = self._display_canvas.create_text(
            0, 0, anchor="nw", text="", fill="#CCCCCC",
            font=("TkDefaultFont", 11)
        )
        self._show_message("（尚无共享画面）")

        # 如果没有 Pillow，显示提示
        if not self._pil_available:
            ttk.Label(
                self,
                text="提示：未检测到 Pillow 库，屏幕共享功能不可用。"
                     "可使用 `pip install Pillow` 安装。",
                foreground="#B71C1C", padding=(8, 4), anchor="w"
            ).pack(fill="x")

        # 控制能力提示
        if not input_executor.is_supported():
            ttk.Label(
                self,
                text="提示：当前平台不支持远程控制执行（仅 Windows 可用）。",
                foreground="#E65100", padding=(8, 4), anchor="w"
            ).pack(fill="x")

    def _bind_control_events(self):
        """在显示 Canvas 上绑定鼠标/键盘事件，用于远程控制。"""
        c = self._display_canvas
        # 鼠标移动（仅在没有按键按下时）
        c.bind("<Motion>", self._on_canvas_motion)
        # 鼠标按下 / 释放
        c.bind("<Button-1>", lambda e: self._on_canvas_click(e, "left", down=True))
        c.bind("<ButtonRelease-1>", lambda e: self._on_canvas_click(e, "left", down=False))
        c.bind("<Button-3>", lambda e: self._on_canvas_click(e, "right", down=True))
        c.bind("<ButtonRelease-3>", lambda e: self._on_canvas_click(e, "right", down=False))
        c.bind("<Button-2>", lambda e: self._on_canvas_click(e, "middle", down=True))
        c.bind("<ButtonRelease-2>", lambda e: self._on_canvas_click(e, "middle", down=False))
        # 键盘
        c.bind("<KeyPress>", self._on_canvas_key_down)
        c.bind("<KeyRelease>", self._on_canvas_key_up)
        # 让 canvas 可聚焦以接收键盘
        c.configure(takefocus=True)

    def _show_message(self, text: str):
        self._display_canvas.delete("all")
        self._canvas_image_id = self._display_canvas.create_text(
            10, 10, anchor="nw", text=text, fill="#CCCCCC",
            font=("TkDefaultFont", 11)
        )

    # ---------------------- 外部操作 ----------------------

    def set_websocket_client(self, ws_client):
        self._ws = ws_client

    def refresh_targets(self):
        contacts = list(self._get_online_contacts())
        self._target_combo["values"] = contacts
        if self._target_var.get() not in contacts and contacts:
            self._target_var.set(contacts[0])

    def show_incoming_request(self, from_user: str, on_accept, on_reject):
        """弹窗提示：用户 X 想共享屏幕给你（或想请求你屏幕）。"""
        self._sharer_target = from_user
        try:
            result = messagebox.askyesno(
                "远程桌面请求",
                f"用户 {from_user} 想共享屏幕 / 或请求你的屏幕。\n是否接受？",
                parent=self
            )
        except Exception:
            try:
                root = self.winfo_toplevel()
                result = messagebox.askyesno(
                    "远程桌面请求",
                    f"用户 {from_user} 想共享屏幕给你。\n是否接受？",
                )
            except Exception:
                result = False
        if result:
            on_accept()
        else:
            on_reject()

    def display_frame(self, image_data_b64: str, width: int, height: int):
        """解码一帧画面并显示（从 WebSocket 接收帧时调用）。"""
        self._run_ui(lambda: self._do_display_frame(image_data_b64, width, height))

    def set_status(self, status: str):
        self._run_ui(lambda: self._status_var.set(status))

    def set_viewing_target(self, target: Optional[str]):
        """设置当前正在查看谁的屏幕（作为查看方 / 控制方）。"""
        self._viewing_target = target
        if target:
            try:
                self._display_canvas.focus_set()
            except Exception:
                pass

    def allow_remote_control(self) -> bool:
        """是否允许对方远程控制本机。"""
        try:
            return bool(self._allow_control.get())
        except Exception:
            return False

    def stop_all(self):
        self._stop_capture_loop()
        self._viewing_target = None
        self._last_image_rect = None
        self._run_ui(lambda: self._status_var.set("已停止"))

    # ---------------------- 控制事件 → 发送给对端 ----------------------

    def _scale_to_screen(self, canvas_x: int, canvas_y: int) -> Optional[tuple]:
        """把 Canvas 坐标换算为对端屏幕原始坐标。"""
        rect = self._last_image_rect
        if not rect:
            return None
        ix, iy, iw, ih = rect
        if iw <= 0 or ih <= 0:
            return None
        # 限制在图片范围内
        cx = max(0, min(canvas_x - ix, iw))
        cy = max(0, min(canvas_y - iy, ih))
        sw, sh = self._last_screen_size
        if sw <= 0 or sh <= 0:
            return None
        sx = int(cx * sw / iw)
        sy = int(cy * sh / ih)
        return sx, sy

    def _on_canvas_motion(self, event):
        if not self._viewing_target or self._ws is None:
            return
        scaled = self._scale_to_screen(event.x, event.y)
        if scaled is None:
            return
        try:
            self._ws.send_desktop_mouse_move(self._viewing_target, scaled[0], scaled[1])
        except Exception:
            pass

    def _on_canvas_click(self, event, button: str, down: bool):
        if not self._viewing_target or self._ws is None:
            return
        scaled = self._scale_to_screen(event.x, event.y)
        if scaled is None:
            return
        try:
            if down:
                self._ws.send_desktop_mouse_click(
                    self._viewing_target, scaled[0], scaled[1], button)
            else:
                self._ws.send_desktop_mouse_release(
                    self._viewing_target, scaled[0], scaled[1], button)
        except Exception:
            pass

    def _on_canvas_key_down(self, event):
        self._send_key(event, is_down=True)

    def _on_canvas_key_up(self, event):
        self._send_key(event, is_down=False)

    def _send_key(self, event, is_down: bool):
        if not self._viewing_target or self._ws is None:
            return
        # tkinter event.keycode 在 Windows 上即为 VK code
        key_code = int(getattr(event, "keycode", 0) or 0)
        if key_code <= 0:
            return
        key_name = str(getattr(event, "keysym", "") or "")
        try:
            self._ws.send_desktop_keyboard(
                self._viewing_target, key_code, key_name, is_down)
        except Exception:
            pass

    # ---------------------- 接收对端控制指令 → 本地执行 ----------------------

    def execute_mouse_move(self, x: int, y: int):
        if not self.allow_remote_control():
            return
        input_executor.move_mouse(x, y)

    def execute_mouse_click(self, x: int, y: int, button: str = "left"):
        if not self.allow_remote_control():
            return
        input_executor.mouse_down(x, y, button)

    def execute_mouse_release(self, x: int, y: int, button: str = "left"):
        if not self.allow_remote_control():
            return
        input_executor.mouse_up(x, y, button)

    def execute_key(self, key_code: int, is_down: bool = True):
        if not self.allow_remote_control():
            return
        input_executor.key_event(key_code, is_down)

    # ---------------------- 内部事件 ----------------------

    def _on_request_share(self):
        target = self._target_var.get().strip()
        if not target:
            messagebox.showwarning("提示", "请先选择一个目标用户")
            return
        if self._ws is None:
            messagebox.showerror("错误", "WebSocket 尚未连接")
            return
        try:
            self._ws.send_desktop_share_request(target)
        except Exception as exc:
            logger.exception(f"发送桌面共享请求失败: {exc}")
        self._status_var.set(f"正在请求 {target}...")

    def _on_stop(self):
        """停止本地屏幕抓取；也通知对方停止。"""
        self._stop_capture_loop()
        target = self._target_var.get().strip()
        if target and self._ws is not None:
            try:
                self._ws.send_desktop_stop(target)
            except Exception:
                pass
        self._status_var.set("已停止")
        self._request_btn.configure(state="normal")
        self._stop_btn.configure(state="disabled")

    def start_capture_loop(self, target: str):
        """对方接受请求后，开启定时屏幕采集并发送帧。"""
        if not self._pil_available:
            messagebox.showwarning(
                "无法共享", "未检测到 Pillow 库，无法进行屏幕捕获。"
            )
            return
        if self._capturing:
            return
        self._capturing = True
        self._sharer_target = target
        self._request_btn.configure(state="disabled")
        self._stop_btn.configure(state="normal")
        self._status_var.set(f"正在向 {target} 共享屏幕...")
        self._schedule_capture()

    def _schedule_capture(self):
        if not self._capturing:
            return
        # 先抓取一张，再安排下一次；使用 after 保证在主线程
        try:
            self._capture_and_send()
        except Exception as exc:
            logger.debug(f"屏幕截图/发送异常: {exc}")
        # 每 120ms 一帧（约 8fps，平衡流畅度与带宽）
        self.after(120, self._schedule_capture)

    def _capture_and_send(self):
        if not self._pil_available or not self._capturing:
            return
        if not self._sharer_target or self._ws is None:
            return
        try:
            from PIL import ImageGrab, Image
            screen = ImageGrab.grab()
            # 压缩尺寸，降低传输带宽（保持较高清晰度）
            max_w, max_h = 1280, 720
            orig_w, orig_h = screen.size
            ratio = min(max_w / orig_w, max_h / orig_h, 1.0)
            if ratio < 1.0:
                screen = screen.resize(
                    (int(orig_w * ratio), int(orig_h * ratio)), Image.LANCZOS
                )
            # JPEG 压缩到内存（提高 quality 让画面更清晰）
            buf = io.BytesIO()
            screen.convert("RGB").save(buf, format="JPEG", quality=82)
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
            self._ws.send_desktop_frame(self._sharer_target, b64,
                                        screen.size[0], screen.size[1])
        except Exception as exc:
            logger.debug(f"截图/发送异常: {exc}")

    def _stop_capture_loop(self):
        self._capturing = False
        if self._capture_timer is not None:
            try:
                self._capture_timer.cancel()
            except Exception:
                pass
            self._capture_timer = None

    def _do_display_frame(self, image_data_b64: str, width: int, height: int):
        try:
            img_bytes = base64.b64decode(image_data_b64)
        except Exception as exc:
            logger.debug(f"base64 解码失败: {exc}")
            return

        # 记录对端屏幕原始尺寸（用于控制坐标换算）
        if width and height:
            self._last_screen_size = (int(width), int(height))

        # 尝试用 Pillow 解码 JPEG；否则退化为二进制显示
        photo = None
        disp_w = disp_h = 0
        try:
            if self._pil_available:
                from PIL import Image, ImageTk
                pil = Image.open(io.BytesIO(img_bytes))
                # 根据 Canvas 尺寸做缩放（用 LANCZOS 提升清晰度）
                cw = max(self._display_canvas.winfo_width(), 100)
                ch = max(self._display_canvas.winfo_height(), 100)
                iw, ih = pil.size
                ratio = min(cw / iw, ch / ih, 1.0) if iw and ih else 1.0
                if ratio < 1.0:
                    pil = pil.resize((int(iw * ratio), int(ih * ratio)), Image.LANCZOS)
                disp_w, disp_h = pil.size
                photo = ImageTk.PhotoImage(pil)
        except Exception as exc:
            logger.debug(f"帧解码失败: {exc}")

        if photo is None:
            self._status_var.set("帧解码失败（需要 Pillow）")
            return

        # 更新 Canvas
        self._display_canvas.delete("all")
        cw = max(self._display_canvas.winfo_width(), 100)
        ch = max(self._display_canvas.winfo_height(), 100)
        # 居中显示
        ix = (cw - disp_w) // 2
        iy = (ch - disp_h) // 2
        self._display_canvas.create_image(ix, iy, image=photo, anchor="nw")
        # 记录图片在 canvas 上的实际矩形，用于控制坐标换算
        self._last_image_rect = (ix, iy, disp_w, disp_h)

        # 保持引用，避免被 GC
        self._frame_refs.append(photo)
        if len(self._frame_refs) > 3:
            self._frame_refs = self._frame_refs[-3:]

        self._status_var.set(f"正在接收 {width}x{height}")

    def _run_ui(self, fn):
        try:
            root = self.winfo_toplevel()
            if root is not None and hasattr(root, "after"):
                root.after(0, fn)
                return
        except Exception:
            pass
        try:
            fn()
        except Exception as exc:
            logger.debug(f"DesktopFrame UI 更新异常: {exc}")


# =============================================================
# 主窗口
# =============================================================

class MainWindow(ttk.Frame):
    """ConnectHub 主窗口。

    公共 API:
        set_websocket_client(client)
        set_username(username)
        show()            -> 确保窗口可见
        close()           -> 清理并关闭窗口

    信号 (Signal):
        logout_requested()  -> 由 app.py 处理登出
    """

    def __init__(self, master: Optional[tk.Misc] = None):
        # 如果没传 master，就创建一个隐藏的 Tk 根
        if master is None:
            try:
                master = tk.Tk()
                master.withdraw()
                self._own_root = True
            except Exception:
                master = None
                self._own_root = False
        else:
            self._own_root = False

        super().__init__(master, padding=0)
        self.master = master

        # 依赖：外部通过 setter 注入
        self._ws_client = None
        self._username: Optional[str] = None

        # 版本信息
        self._version_info = _load_version_info()
        self._version: str = self._version_info.get("version", "0.0.0")

        # 信号
        self.logout_requested = Signal()

        # 子模块管理器
        self._ft_manager = FileTransferManager(websocket_client=None,
                                               username=None)

        # 更新器（不传 version_file，让 Updater 自动查找）
        self._updater = Updater(master=self.master)

        # UI 组件引用
        self._contact_list: Optional[ContactListWidget] = None
        self._chat_tabs: Optional[ChatTabWidget] = None
        self._ft_frame: Optional[FileTransferFrame] = None
        self._desktop_frame: Optional[DesktopFrame] = None

        self._status_text: Optional[tk.StringVar] = None
        self._user_label: Optional[tk.Label] = None
        self._title_label: Optional[tk.Label] = None

        self._notebook: Optional[ttk.Notebook] = None

        # 构建 UI
        self._build_ui()

        # 配置窗口
        if self.master is not None:
            self._configure_top_level()
            self.pack(fill="both", expand=True)

    # =========================================================
    # 公共 API
    # =========================================================

    def set_websocket_client(self, client):
        """注入 WebSocket 客户端并连接其信号。"""
        self._ws_client = client
        self._ft_manager.set_websocket_client(client)
        if self._desktop_frame is not None:
            self._desktop_frame.set_websocket_client(client)

        # 连接 WebSocket 信号
        if client is not None and hasattr(client, "signals"):
            sigs = client.signals
            sigs.connected.connect(self._on_ws_connected)
            sigs.disconnected.connect(self._on_ws_disconnected)
            sigs.error_occurred.connect(self._on_ws_error)
            sigs.message_received.connect(self._on_ws_message)
            sigs.reconnecting.connect(self._on_ws_reconnecting)
            sigs.connection_failed.connect(self._on_ws_connection_failed)

        self._update_status_bar()

    def set_username(self, username: str):
        """设置当前登录用户名。"""
        self._username = username
        if self._contact_list is not None:
            self._contact_list.set_username(username)
        if self._chat_tabs is not None:
            self._chat_tabs.set_username(username)
        self._ft_manager.set_username(username)

        if self._user_label is not None:
            short = (username[:10] + "…") if len(username or "") > 10 else (username or "")
            self._user_label.configure(
                text=f"{(username or '?')[:1].upper()}  {short or '未登录'}"
            )

        self._update_status_bar()

    def set_status(self, status: str):
        """设置状态栏文本（由 app.py 调用）。"""
        self._run_ui(lambda: self._update_status_bar(status_override=status))

    def show(self):
        """显示主窗口。"""
        if self.master is not None:
            try:
                self.master.deiconify()
            except Exception:
                pass
            try:
                self.master.lift()
            except Exception:
                pass
            try:
                self.master.focus_force()
            except Exception:
                pass

    def close(self):
        """关闭并清理资源。"""
        try:
            self._stop_all()
        except Exception:
            pass
        if self._own_root and self.master is not None:
            try:
                self.master.destroy()
            except Exception:
                pass
        elif self.master is not None:
            try:
                self.master.withdraw()
            except Exception:
                pass

    # =========================================================
    # UI 构建
    # =========================================================

    def _configure_top_level(self):
        if self.master is None:
            return
        try:
            self.master.title(f"ConnectHub v{self._version}")
        except Exception:
            pass
        try:
            self.master.geometry("1024x640")
        except Exception:
            pass
        try:
            self.master.minsize(820, 520)
        except Exception:
            pass

    def _build_ui(self):
        # 顶部 Header
        header = tk.Frame(self, bg="#1976D2", height=52)
        header.pack(fill="x")
        header.pack_propagate(False)

        # 左侧：用户头像 + 用户名
        user_frame = tk.Frame(header, bg="#1976D2")
        user_frame.pack(side="left", padx=12)
        self._user_label = tk.Label(
            user_frame, text="?  未登录", bg="#1976D2", fg="#FFFFFF",
            font=("TkDefaultFont", 11, "bold"), padx=4, pady=4
        )
        self._user_label.pack(side="left")

        # 中间：应用名
        self._title_label = tk.Label(
            header, text="ConnectHub", bg="#1976D2", fg="#FFFFFF",
            font=("TkDefaultFont", 14, "bold")
        )
        self._title_label.pack(side="left", expand=True)

        # 右侧：按钮
        right_frame = tk.Frame(header, bg="#1976D2")
        right_frame.pack(side="right", padx=8)

        self._update_btn = tk.Button(
            right_frame, text="检查更新", relief="flat",
            bg="#1565C0", fg="#FFFFFF", activebackground="#0D47A1",
            activeforeground="#FFFFFF", padx=10, pady=4,
            command=self._on_check_updates, cursor="hand2"
        )
        self._update_btn.pack(side="right", padx=(6, 0))

        self._logout_btn = tk.Button(
            right_frame, text="登出", relief="flat",
            bg="#C62828", fg="#FFFFFF", activebackground="#B71C1C",
            activeforeground="#FFFFFF", padx=10, pady=4,
            command=self._on_logout_clicked, cursor="hand2"
        )
        self._logout_btn.pack(side="right")

        # 主体：PanedWindow（左侧联系人，右侧标签页）
        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)

        paned = ttk.PanedWindow(body, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=4, pady=4)

        # 左侧：联系人列表
        left_frame = ttk.Frame(paned, width=280)
        paned.add(left_frame, weight=0)

        self._contact_list = ContactListWidget(left_frame)
        self._contact_list.pack(fill="both", expand=True)

        # 右侧：Notebook
        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=3)

        self._notebook = ttk.Notebook(right_frame)
        self._notebook.pack(fill="both", expand=True)
        self._notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        # --- 聊天标签 ---
        chat_host = ttk.Frame(self._notebook)
        self._chat_tabs = ChatTabWidget(chat_host)
        self._chat_tabs.pack(fill="both", expand=True)
        self._notebook.add(chat_host, text="聊天")

        # --- 文件传输标签 ---
        self._ft_frame = FileTransferFrame(
            self._notebook, self._ft_manager,
            get_online_contacts_cb=self._get_online_usernames,
        )
        self._notebook.add(self._ft_frame, text="文件传输")

        # --- 远程桌面标签 ---
        self._desktop_frame = DesktopFrame(
            self._notebook, ws_client=self._ws_client,
            get_online_contacts_cb=self._get_online_usernames,
        )
        self._notebook.add(self._desktop_frame, text="远程桌面")

        # 底部状态栏
        status_bar = tk.Frame(self, bg="#EEEEEE", height=24)
        status_bar.pack(fill="x", side="bottom")
        status_bar.pack_propagate(False)

        self._status_text = tk.StringVar(value="未连接")
        tk.Label(
            status_bar, textvariable=self._status_text, bg="#EEEEEE",
            fg="#424242", anchor="w", padx=10,
            font=("TkDefaultFont", 9)
        ).pack(side="left", fill="x", expand=True)

        tk.Label(
            status_bar, text=f"v{self._version}", bg="#EEEEEE",
            fg="#757575", anchor="e", padx=10,
            font=("TkDefaultFont", 9)
        ).pack(side="right")

        # 把信号连到事件
        self._connect_component_signals()

    def _connect_component_signals(self):
        # 联系人列表 → 打开聊天 / 发送文件 / 请求桌面
        if self._contact_list is not None:
            self._contact_list.start_chat_request.connect(self._open_chat_with)
            self._contact_list.contact_double_clicked.connect(self._open_chat_with)
            self._contact_list.start_file_transfer.connect(
                self._start_file_transfer_with
            )
            self._contact_list.start_desktop_share.connect(
                lambda user, _type: self._request_desktop_with(user)
            )

        # 聊天 → 发送消息
        if self._chat_tabs is not None:
            self._chat_tabs.message_sent.connect(self._send_chat_message)

        # 文件传输管理器：请求来时弹窗（主线程弹窗）
        self._ft_manager.transfer_requested.connect(self._on_transfer_requested)

    # =========================================================
    # 事件：顶部按钮
    # =========================================================

    def _on_logout_clicked(self):
        """用户点击登出：通知上层 app.py，并做一次 stop 清理。"""
        try:
            if self._ws_client is not None and hasattr(self._ws_client, "send_logout"):
                try:
                    self._ws_client.send_logout()
                except Exception:
                    pass
        finally:
            self._stop_all()
            try:
                self.logout_requested.emit()
            except Exception as exc:
                logger.debug(f"logout_requested 回调异常: {exc}")

    def _on_check_updates(self):
        updater = self._updater

        # 连接 updater 信号
        if not getattr(self, "_updater_signals_connected", False):
            updater.update_available.connect(self._on_update_available)
            updater.no_update.connect(self._on_no_update)
            updater.download_progress.connect(self._on_update_download_progress)
            updater.update_ready.connect(self._on_update_ready)
            updater.update_error.connect(self._on_update_error)
            self._updater_signals_connected = True

        updater.check_for_updates(show_dialog=False)

    def _on_update_available(self, current: str, new: str, url: str):
        """发现新版本，询问是否下载。"""
        result = self._ask_yes_no(
            "发现新版本",
            f"发现新版本 v{new.lstrip('v')}\n"
            f"当前版本: v{current}\n\n"
            f"是否立即下载并安装更新？",
            yes_text="立即下载", no_text="稍后再说"
        )
        if result:
            self._show_download_dialog()
            self._updater.download_update()

    def _on_no_update(self):
        """已是最新版本。"""
        try:
            from tkinter import messagebox
            messagebox.showinfo("检查更新", "当前已是最新版本", parent=self.master)
        except Exception:
            pass

    def _show_download_dialog(self):
        """显示下载进度对话框。"""
        import tkinter as tk
        dialog = tk.Toplevel(self.master)
        dialog.title("下载更新")
        dialog.transient(self.master)
        dialog.grab_set()
        dialog.resizable(False, False)
        dialog.geometry("400x160")

        tk.Label(dialog, text="正在下载更新，请稍候...", pady=16,
                 font=("TkDefaultFont", 11, "bold")).pack()

        self._download_label = tk.Label(dialog, text="准备中...")
        self._download_label.pack(pady=4)

        self._download_progress = ttk.Progressbar(
            dialog, orient="horizontal", length=340, mode="determinate"
        )
        self._download_progress.pack(pady=8)

        self._update_dialog = dialog

    def _on_update_download_progress(self, downloaded: int, total: int):
        """更新下载进度条。"""
        if hasattr(self, "_update_dialog") and self._update_dialog is not None:
            try:
                if total > 0:
                    pct = (downloaded / total) * 100
                    self._download_progress["value"] = pct
                    mb_down = downloaded / 1024 / 1024
                    mb_total = total / 1024 / 1024
                    self._download_label.configure(
                        text=f"{mb_down:.1f} MB / {mb_total:.1f} MB"
                    )
                else:
                    mb_down = downloaded / 1024 / 1024
                    self._download_progress.configure(mode="indeterminate")
                    self._download_progress.start(10)
                    self._download_label.configure(text=f"已下载 {mb_down:.1f} MB")
            except Exception:
                pass

    def _on_update_ready(self, version: str):
        """下载完成，提示用户是否立即更新。"""
        if hasattr(self, "_update_dialog") and self._update_dialog is not None:
            try:
                self._update_dialog.destroy()
            except Exception:
                pass
            self._update_dialog = None

        result = self._ask_yes_no(
            "更新下载完成",
            f"新版本 v{version.lstrip('v')} 已下载完成。\n是否立即安装并重启？",
            yes_text="立即安装", no_text="稍后安装"
        )
        if result:
            self._apply_update_and_restart()

    def _on_update_error(self, msg: str):
        """更新出错。"""
        if hasattr(self, "_update_dialog") and self._update_dialog is not None:
            try:
                self._update_dialog.destroy()
            except Exception:
                pass
            self._update_dialog = None
        try:
            from tkinter import messagebox
            messagebox.showerror("更新失败", msg, parent=self.master)
        except Exception:
            pass

    def _apply_update_and_restart(self):
        """应用更新并重启。"""
        if self._updater.apply_update_and_restart():
            try:
                self._stop_all()
            except Exception:
                pass
            # 延迟退出，让 bat 接管
            try:
                if self.master is not None:
                    self.master.after(200, self.master.destroy)
            except Exception:
                pass

    def _ask_yes_no(self, title: str, message: str, yes_text: str = "是",
                     no_text: str = "否") -> bool:
        """简单的自定义 Yes/No 对话框。"""
        import tkinter as tk
        dialog = tk.Toplevel(self.master)
        dialog.title(title)
        dialog.transient(self.master)
        dialog.grab_set()
        dialog.resizable(False, False)
        dialog.update_idletasks()
        w, h = 380, 170
        try:
            sw = dialog.winfo_screenwidth()
            sh = dialog.winfo_screenheight()
            x = (sw - w) // 2
            y = (sh - h) // 2
            dialog.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            dialog.geometry(f"{w}x{h}")

        tk.Label(
            dialog, text=message, justify="left", padx=18, pady=18, wraplength=w - 40
        ).pack(fill="both", expand=True)

        result = {"value": False}
        def on_yes():
            result["value"] = True
            dialog.destroy()
        def on_no():
            result["value"] = False
            dialog.destroy()

        btn_frame = tk.Frame(dialog)
        btn_frame.pack(pady=10)
        tk.Button(btn_frame, text=yes_text, width=10, command=on_yes).pack(side="left", padx=8)
        tk.Button(btn_frame, text=no_text, width=10, command=on_no).pack(side="left", padx=8)

        dialog.protocol("WM_DELETE_WINDOW", on_no)
        dialog.wait_window()
        return result["value"]

    def _stop_all(self):
        if self._desktop_frame is not None:
            try:
                self._desktop_frame.stop_all()
            except Exception:
                pass
        if self._chat_tabs is not None:
            try:
                self._chat_tabs.close_all_chats()
            except Exception:
                pass
        if self._contact_list is not None:
            try:
                self._contact_list.clear_contacts()
            except Exception:
                pass
        if self._ft_manager is not None:
            try:
                sessions = self._ft_manager.get_all_sessions()
                for fid in list(sessions.keys()):
                    try:
                        self._ft_manager.cancel_transfer(fid)
                    except Exception:
                        pass
            except Exception:
                pass

    # =========================================================
    # 事件：联系人 / 聊天 / 文件传输 / 桌面
    # =========================================================

    def _open_chat_with(self, username: str):
        if not username or self._chat_tabs is None:
            return
        self._chat_tabs.open_chat(username)
        if self._notebook is not None:
            # 切换到聊天标签
            try:
                self._notebook.select(0)
            except Exception:
                pass

    def _start_file_transfer_with(self, username: str):
        if not username:
            return
        file_path = filedialog.askopenfilename(
            title=f"选择要发送给 {username} 的文件"
        )
        if not file_path:
            return
        if self._ft_frame is not None:
            # 设置目标用户并发送
            try:
                self._ft_frame._target_var.set(username)
            except Exception:
                pass
            self._ft_frame.start_transfer(username, file_path)
            # 切到文件传输标签
            if self._notebook is not None:
                try:
                    idx = list(self._notebook.tabs()).index(
                        str(self._ft_frame)
                    )
                    self._notebook.select(idx)
                except Exception:
                    try:
                        self._notebook.select(1)
                    except Exception:
                        pass

    def _request_desktop_with(self, username: str):
        if not username:
            return
        if self._desktop_frame is not None:
            try:
                self._desktop_frame._target_var.set(username)
            except Exception:
                pass
            try:
                self._desktop_frame._on_request_share()
            except Exception:
                pass
            if self._notebook is not None:
                try:
                    self._notebook.select(2)
                except Exception:
                    pass

    def _send_chat_message(self, target: str, content: str):
        if self._ws_client is None or not target or not content:
            return
        try:
            self._ws_client.send_chat_message(target, content)
        except Exception as exc:
            logger.debug(f"发送聊天消息失败: {exc}")

    def _on_transfer_requested(self, file_id: str, sender: str,
                                file_name: str, file_size: int):
        """对方请求我接收文件。弹窗：接受（选择保存路径）或拒绝。"""
        self._run_ui(
            lambda: self._do_show_transfer_dialog(file_id, sender, file_name, file_size)
        )

    def _do_show_transfer_dialog(self, file_id: str, sender: str,
                                  file_name: str, file_size: int):
        msg = (f"用户 {sender} 希望向你发送文件：\n\n"
               f"  {file_name}  ({_human_size(file_size)})\n\n"
               f"是否接受？")
        try:
            accept = messagebox.askyesno("文件传输请求", msg, parent=self)
        except Exception:
            try:
                accept = messagebox.askyesno("文件传输请求", msg)
            except Exception:
                accept = False

        if accept:
            default_name = file_name or f"received_{file_id}"
            save_path = filedialog.asksaveasfilename(
                title="选择保存位置", initialfile=default_name
            )
            if save_path:
                self._ft_manager.accept_transfer(file_id, save_path)
            else:
                self._ft_manager.reject_transfer(file_id)
        else:
            self._ft_manager.reject_transfer(file_id)

    def _on_tab_changed(self, event):
        """切换标签页时刷新目标用户下拉。"""
        selected = None
        if self._notebook is not None:
            try:
                idx = self._notebook.index(self._notebook.select())
                selected = idx
            except Exception:
                selected = None

        if selected is None:
            return
        try:
            if selected == 1 and self._ft_frame is not None:
                self._ft_frame.refresh_targets()
            elif selected == 2 and self._desktop_frame is not None:
                self._desktop_frame.refresh_targets()
        except Exception as exc:
            logger.debug(f"刷新标签页目标失败: {exc}")

    def _get_online_usernames(self) -> List[str]:
        if self._contact_list is None:
            return []
        try:
            return list(self._contact_list.get_online_contacts())
        except Exception:
            return []

    # =========================================================
    # WebSocket 信号处理（都保证在 UI 线程）
    # =========================================================

    def _on_ws_connected(self):
        self._run_ui(lambda: self._update_status_bar(status_override="已连接"))
        # 连接成功后主动请求用户列表
        self._run_ui(self._request_user_list_if_ready)

    def _on_ws_disconnected(self):
        self._run_ui(lambda: self._update_status_bar(status_override="已断开"))

    def _on_ws_error(self, err: str):
        self._run_ui(lambda: self._update_status_bar(
            status_override=f"错误: {err[:40]}"
        ))

    def _on_ws_reconnecting(self, attempt: int):
        self._run_ui(lambda: self._update_status_bar(
            status_override=f"重连中 (第 {attempt} 次)..."
        ))

    def _on_ws_connection_failed(self, reason: str):
        self._run_ui(lambda: self._update_status_bar(
            status_override=f"连接失败: {reason[:40]}"
        ))

    def _request_user_list_if_ready(self):
        if self._ws_client is None:
            return
        try:
            self._ws_client.request_user_list()
        except Exception:
            pass
        try:
            self._ws_client.request_contact_list()
        except Exception:
            pass

    def _on_ws_message(self, msg):
        """根据消息类型派发到不同子模块。"""
        try:
            mtype = getattr(msg, "type", None)
            if mtype is None:
                return

            # 消息类型可能是 MessageType 枚举或字符串
            type_value = mtype.value if isinstance(mtype, MessageType) else mtype

            handlers = {
                # 聊天
                MessageType.CHAT_MESSAGE.value: self._handle_chat_message,

                # 文件传输
                MessageType.FILE_TRANSFER_REQUEST.value:
                    self._handle_ft_request,
                MessageType.FILE_TRANSFER_RESPONSE.value:
                    self._handle_ft_response,
                MessageType.FILE_TRANSFER_DATA.value:
                    self._handle_ft_data,
                MessageType.FILE_TRANSFER_COMPLETE.value:
                    self._handle_ft_complete,

                # 远程桌面
                MessageType.DESKTOP_SHARE_REQUEST.value:
                    self._handle_desktop_request,
                MessageType.DESKTOP_SHARE_RESPONSE.value:
                    self._handle_desktop_response,
                MessageType.DESKTOP_FRAME.value:
                    self._handle_desktop_frame,
                MessageType.DESKTOP_STOP.value:
                    self._handle_desktop_stop,
                # 远程桌面控制
                MessageType.DESKTOP_MOUSE_MOVE.value:
                    self._handle_desktop_mouse_move,
                MessageType.DESKTOP_MOUSE_CLICK.value:
                    self._handle_desktop_mouse_click,
                MessageType.DESKTOP_MOUSE_RELEASE.value:
                    self._handle_desktop_mouse_release,
                MessageType.DESKTOP_KEYBOARD.value:
                    self._handle_desktop_keyboard,

                # 用户列表
                MessageType.USER_LIST_RESPONSE.value:
                    self._handle_user_list,
                MessageType.CONTACT_LIST_RESPONSE.value:
                    self._handle_contact_list,

                # 用户状态变化
                MessageType.USER_STATUS_UPDATE.value:
                    self._handle_user_status_update,
            }

            handler = handlers.get(type_value)
            if handler is not None:
                self._run_ui(lambda m=msg, h=handler: self._safe_call(h, m))
            else:
                logger.debug(f"未处理的消息类型: {type_value}")
        except Exception as exc:
            logger.debug(f"消息处理异常: {exc}")

    # ----------- 聊天 -----------

    def _handle_chat_message(self, msg: Message):
        sender = getattr(msg, "sender", "")
        payload = getattr(msg, "payload", None) or {}
        content = payload.get("content", "") if isinstance(payload, dict) else ""
        if not content:
            # 兼容：Message 的上层字段
            content = getattr(msg, "content", "")
        if self._chat_tabs is not None and sender:
            # 来自对方的消息：显示在与 sender 的会话中
            target_for_ui = sender
            self._chat_tabs.add_message_to_chat(
                target_for_ui, sender, str(content), datetime.now()
            )

    # ----------- 文件传输 -----------

    def _handle_ft_request(self, msg: Message):
        self._ft_manager.handle_incoming_request(msg)

    def _handle_ft_response(self, msg: Message):
        self._ft_manager.handle_response(msg)

    def _handle_ft_data(self, msg: Message):
        self._ft_manager.handle_incoming_data(msg)

    def _handle_ft_complete(self, msg: Message):
        self._ft_manager.handle_incoming_complete(msg)

    # ----------- 远程桌面 -----------

    def _handle_desktop_request(self, msg: Message):
        sender = getattr(msg, "sender", "")
        if not sender or self._desktop_frame is None:
            return
        payload = getattr(msg, "payload", None) or {}
        share_type = payload.get("share_type", "view") if isinstance(payload, dict) else "view"

        def _accept():
            if self._ws_client is not None:
                try:
                    self._ws_client.send_desktop_share_response(sender, True, share_type)
                except Exception:
                    pass
            # 如果我有 Pillow，则开始共享我的屏幕给对方
            if self._desktop_frame is not None:
                self._desktop_frame.start_capture_loop(sender)
            self._switch_to_desktop_tab()

        def _reject():
            if self._ws_client is not None:
                try:
                    self._ws_client.send_desktop_share_response(sender, False, share_type)
                except Exception:
                    pass
            if self._desktop_frame is not None:
                self._desktop_frame.set_status("已拒绝")

        self._desktop_frame.show_incoming_request(sender, _accept, _reject)

    def _handle_desktop_response(self, msg: Message):
        payload = getattr(msg, "payload", None) or {}
        accepted = (payload.get("accepted") if isinstance(payload, dict) else None) or \
                   getattr(msg, "accepted", False)
        sender = getattr(msg, "sender", "")
        if accepted and sender and self._desktop_frame is not None:
            # 对方接受了我的请求 → 我是查看方，记录目标以便发送控制指令
            self._desktop_frame.set_viewing_target(sender)
            self._desktop_frame.set_status(f"已连接到 {sender}，等待画面...")
            self._switch_to_desktop_tab()
        else:
            if self._desktop_frame is not None:
                self._desktop_frame.set_viewing_target(None)
                self._desktop_frame.set_status(f"{sender} 拒绝了请求")

    def _handle_desktop_frame(self, msg: Message):
        payload = getattr(msg, "payload", None) or {}
        if not isinstance(payload, dict):
            return
        image_data = payload.get("image_data", "")
        width = int(payload.get("width", 0) or 0)
        height = int(payload.get("height", 0) or 0)
        if image_data and self._desktop_frame is not None:
            self._desktop_frame.display_frame(image_data, width, height)

    def _handle_desktop_stop(self, msg: Message):
        sender = getattr(msg, "sender", "")
        if self._desktop_frame is not None:
            self._desktop_frame.set_status(f"{sender} 停止了共享")
            self._desktop_frame.stop_all()

    def _handle_desktop_mouse_move(self, msg: Message):
        if self._desktop_frame is None:
            return
        payload = getattr(msg, "payload", None) or {}
        if not isinstance(payload, dict):
            return
        x = int(payload.get("x", 0) or 0)
        y = int(payload.get("y", 0) or 0)
        try:
            self._desktop_frame.execute_mouse_move(x, y)
        except Exception as exc:
            logger.debug(f"执行鼠标移动失败: {exc}")

    def _handle_desktop_mouse_click(self, msg: Message):
        if self._desktop_frame is None:
            return
        payload = getattr(msg, "payload", None) or {}
        if not isinstance(payload, dict):
            return
        x = int(payload.get("x", 0) or 0)
        y = int(payload.get("y", 0) or 0)
        button = str(payload.get("button", "left") or "left")
        try:
            self._desktop_frame.execute_mouse_click(x, y, button)
        except Exception as exc:
            logger.debug(f"执行鼠标按下失败: {exc}")

    def _handle_desktop_mouse_release(self, msg: Message):
        if self._desktop_frame is None:
            return
        payload = getattr(msg, "payload", None) or {}
        if not isinstance(payload, dict):
            return
        x = int(payload.get("x", 0) or 0)
        y = int(payload.get("y", 0) or 0)
        button = str(payload.get("button", "left") or "left")
        try:
            self._desktop_frame.execute_mouse_release(x, y, button)
        except Exception as exc:
            logger.debug(f"执行鼠标释放失败: {exc}")

    def _handle_desktop_keyboard(self, msg: Message):
        if self._desktop_frame is None:
            return
        payload = getattr(msg, "payload", None) or {}
        if not isinstance(payload, dict):
            return
        key_code = int(payload.get("key_code", 0) or 0)
        is_down = bool(payload.get("is_down", True))
        if key_code <= 0:
            return
        try:
            self._desktop_frame.execute_key(key_code, is_down)
        except Exception as exc:
            logger.debug(f"执行键盘事件失败: {exc}")

    def _switch_to_desktop_tab(self):
        if self._notebook is None:
            return
        try:
            self._notebook.select(2)
        except Exception:
            pass

    # ----------- 用户列表 / 状态 -----------

    def _handle_user_list(self, msg: Message):
        payload = getattr(msg, "payload", None) or {}
        users = payload.get("users") if isinstance(payload, dict) else None
        if users is None:
            users = getattr(msg, "users", []) or []
        if self._contact_list is not None and isinstance(users, list):
            contacts = []
            for u in users:
                if isinstance(u, dict):
                    contacts.append({
                        "username": u.get("username", u.get("name", "")),
                        "status": u.get("status", "online"),
                    })
                elif isinstance(u, str):
                    contacts.append({"username": u, "status": "online"})
            self._contact_list.set_contacts(contacts)

    def _handle_contact_list(self, msg: Message):
        payload = getattr(msg, "payload", None) or {}
        users = payload.get("contacts") if isinstance(payload, dict) else None
        if users is None:
            users = payload.get("users") if isinstance(payload, dict) else None
        if users is None:
            users = getattr(msg, "contacts", []) or getattr(msg, "users", []) or []
        if self._contact_list is not None and isinstance(users, list):
            contacts = []
            for u in users:
                if isinstance(u, dict):
                    contacts.append({
                        "username": u.get("username", u.get("name", "")),
                        "status": u.get("status", "online"),
                    })
                elif isinstance(u, str):
                    contacts.append({"username": u, "status": "online"})
            self._contact_list.set_contacts(contacts)

    def _handle_user_status_update(self, msg: Message):
        payload = getattr(msg, "payload", None) or {}
        if isinstance(payload, dict):
            username = payload.get("username") or getattr(msg, "sender", "")
            status = payload.get("status", "online")
        else:
            username = getattr(msg, "sender", "")
            status = getattr(msg, "status", "online")
        if self._contact_list is not None and username:
            self._contact_list.update_contact_status(username, status)

    # =========================================================
    # 辅助
    # =========================================================

    def _safe_call(self, fn, *args, **kwargs):
        try:
            fn(*args, **kwargs)
        except Exception as exc:
            logger.debug(f"UI 回调异常: {exc}")

    def _update_status_bar(self, status_override: Optional[str] = None):
        if self._status_text is None:
            return
        if status_override:
            state = status_override
        else:
            try:
                connected = (self._ws_client is not None and
                             getattr(self._ws_client, "is_connected", False))
                if connected and hasattr(self._ws_client, "host") and hasattr(self._ws_client, "port"):
                    state = f"已连接到 {self._ws_client.host}:{self._ws_client.port}"
                elif connected:
                    state = "已连接"
                else:
                    state = "未连接"
            except Exception:
                state = "未连接"

        user = self._username or "未登录"
        self._status_text.set(f"{state}  ({user})")

    def _run_ui(self, fn):
        """把 UI 操作调度到 Tk 主线程。"""
        try:
            root = self.winfo_toplevel()
            if root is not None and hasattr(root, "after"):
                try:
                    root.after(0, fn)
                    return
                except Exception:
                    pass
        except Exception:
            pass
        # 回退：直接调用
        try:
            fn()
        except Exception as exc:
            logger.debug(f"UI 操作异常: {exc}")


__all__ = ["MainWindow", "FileTransferFrame", "DesktopFrame"]
