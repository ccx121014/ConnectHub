"""
Login Dialog for Online Collaboration Suite
提供服务器地址、用户名、密码输入的认证界面。
基于 tkinter / ttk 实现，不依赖 PyQt5。
对外暴露与原 PyQt5 版本相同的 Signal API（使用 protocol/signals.py 的 SignalBridge）。
"""

import sys
import tkinter as tk
from tkinter import ttk, messagebox as tk_messagebox
from pathlib import Path

_project_root = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(_project_root))
sys.path.insert(0, str(Path(__file__).parent))

from protocol.signals import Signal


class LoginDialog:
    """
    Login dialog for user authentication.

    与原来的 QDialog 版本兼容的 API:
    - 构造时可选传入 master (tk.Tk 或 tk.Toplevel)，如未传入则内部创建
    - 信号: connect_request / register_request (str, int, str, str)
    - show() / close() / show_error(message) / show_success(message)
    - 连接过程中输入框/按钮禁用，状态标签实时更新
    """

    def __init__(self, master=None):
        # 信号：与旧的 pyqtSignal 签名一致
        self.connect_request = Signal(str, int, str, str)
        self.register_request = Signal(str, int, str, str)

        # master 可以是主 Tk 或其他 Toplevel；如果没有则自己创建一个隐藏 Tk
        if master is None:
            master = tk._default_root if tk._default_root is not None else tk.Tk()
            if not master.winfo_ismapped() and not getattr(master, "_login_root_placeholder", False):
                master.withdraw()
                master._login_root_placeholder = True

        self.master = master
        self._window = tk.Toplevel(master)
        self._window.title("登录 - ConnectHub")
        self._window.geometry("420x390")
        self._window.resizable(False, False)

        # 窗口关闭行为：触发 cancel
        self._window.protocol("WM_DELETE_WINDOW", self._on_cancel)

        # 根据原始 PyQt5 版本：初始按钮状态
        self._connecting = False

        self._init_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _init_ui(self):
        root = ttk.Frame(self._window, padding=12)
        root.pack(fill="both", expand=True)

        # -------- 服务器设置 --------
        server_frame = ttk.LabelFrame(root, text="服务器设置", padding=8)
        server_frame.pack(fill="x", pady=(0, 8))

        server_grid = ttk.Frame(server_frame)
        server_grid.pack(fill="x")
        server_grid.columnconfigure(1, weight=1)

        ttk.Label(server_grid, text="服务器:").grid(row=0, column=0, sticky="e", padx=(0, 6), pady=4)
        self.server_var = tk.StringVar(value="localhost")
        self.server_edit = ttk.Entry(server_grid, textvariable=self.server_var)
        self.server_edit.grid(row=0, column=1, sticky="ew", pady=4)

        ttk.Label(server_grid, text="端口:").grid(row=1, column=0, sticky="e", padx=(0, 6), pady=4)
        self.port_var = tk.StringVar(value="8765")
        self.port_edit = ttk.Entry(server_grid, textvariable=self.port_var)
        self.port_edit.grid(row=1, column=1, sticky="ew", pady=4)

        # -------- 用户认证 --------
        auth_frame = ttk.LabelFrame(root, text="用户认证", padding=8)
        auth_frame.pack(fill="x", pady=(0, 8))

        auth_grid = ttk.Frame(auth_frame)
        auth_grid.pack(fill="x")
        auth_grid.columnconfigure(1, weight=1)

        ttk.Label(auth_grid, text="用户名:").grid(row=0, column=0, sticky="e", padx=(0, 6), pady=4)
        self.username_var = tk.StringVar(value="")
        self.username_edit = ttk.Entry(auth_grid, textvariable=self.username_var)
        self.username_edit.grid(row=0, column=1, sticky="ew", pady=4)

        ttk.Label(auth_grid, text="密码:").grid(row=1, column=0, sticky="e", padx=(0, 6), pady=4)
        self.password_var = tk.StringVar(value="")
        self.password_edit = ttk.Entry(auth_grid, textvariable=self.password_var, show="*")
        self.password_edit.grid(row=1, column=1, sticky="ew", pady=4)

        # 显示密码
        self.show_password_var = tk.BooleanVar(value=False)
        self.show_password_check = ttk.Checkbutton(
            auth_grid,
            text="显示密码",
            variable=self.show_password_var,
            command=self._toggle_password_visibility,
        )
        self.show_password_check.grid(row=2, column=0, columnspan=2, sticky="w", pady=(4, 0))

        # 用户名变化 -> 启用/禁用按钮
        self.username_var.trace_add("write", lambda *a: self._on_credentials_changed())

        # -------- 状态标签 --------
        self.status_label = tk.Label(
            root,
            text="",
            fg="#666666",
            anchor="center",
            justify="center",
        )
        self.status_label.pack(fill="x", pady=(6, 6))

        # -------- 按钮 --------
        btn_frame = ttk.Frame(root)
        btn_frame.pack(fill="x", pady=(4, 0))

        self.register_button = tk.Button(
            btn_frame,
            text="注册",
            width=10,
            command=self._on_register_clicked,
            bg="#616161",
            fg="white",
            activebackground="#757575",
            activeforeground="white",
            relief="flat",
            bd=0,
            pady=6,
            disabledforeground="#EEEEEE",
        )
        self.register_button.pack(side="left", padx=4)

        self.connect_button = tk.Button(
            btn_frame,
            text="连接",
            width=10,
            command=self._on_connect_clicked,
            bg="#2E7D32",
            fg="white",
            activebackground="#388E3C",
            activeforeground="white",
            relief="flat",
            bd=0,
            pady=6,
            disabledforeground="#EEEEEE",
        )
        self.connect_button.pack(side="left", padx=4)

        self.cancel_button = tk.Button(
            btn_frame,
            text="取消",
            width=10,
            command=self._on_cancel,
            bg="#F5F5F5",
            fg="#424242",
            activebackground="#E0E0E0",
            relief="flat",
            bd=0,
            pady=6,
        )
        self.cancel_button.pack(side="right", padx=4)

        # 初始禁用
        self.connect_button.configure(state="disabled")
        self.register_button.configure(state="disabled")

        # 让用户名输入框获得焦点
        self.username_edit.focus_set()

        # 回车 = 连接
        self._window.bind("<Return>", lambda e: self._on_connect_clicked())

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------
    def show(self):
        """显示对话框。"""
        try:
            self._window.deiconify()
        except Exception:
            pass
        self._window.lift()
        self._window.focus_force()
        try:
            self._window.grab_set()
        except Exception:
            pass

    def close(self):
        """关闭对话框。"""
        try:
            self._window.grab_release()
        except Exception:
            pass
        try:
            self._window.destroy()
        except Exception:
            pass

    def show_error(self, message: str):
        """显示错误信息（状态栏红字 + 消息框）。"""
        self._set_connecting(False)
        self.status_label.configure(text=str(message), fg="#cc0000")
        try:
            tk_messagebox.showerror("连接错误", message, parent=self._window)
        except Exception:
            pass

    def show_success(self, message: str):
        """显示成功信息（状态栏绿字）。"""
        self._set_connecting(False)
        self.status_label.configure(text=str(message), fg="#00aa00")

    # ------------------------------------------------------------------
    # 内部逻辑
    # ------------------------------------------------------------------
    def _toggle_password_visibility(self):
        if self.show_password_var.get():
            self.password_edit.configure(show="")
        else:
            self.password_edit.configure(show="*")

    def _on_credentials_changed(self):
        """用户名变化时，启用/禁用连接与注册按钮（仅在非连接状态下）。"""
        if self._connecting:
            return
        has_username = bool(self.username_var.get().strip())
        state = "normal" if has_username else "disabled"
        self.connect_button.configure(state=state)
        self.register_button.configure(state=state)

    def _validate_inputs(self) -> bool:
        server = self.server_var.get().strip()
        port_str = self.port_var.get().strip()
        username = self.username_var.get().strip()

        if not server:
            tk_messagebox.showwarning("输入错误", "请输入服务器地址", parent=self._window)
            self.server_edit.focus_set()
            return False

        if not port_str or not port_str.isdigit():
            tk_messagebox.showwarning("输入错误", "请输入有效的端口号", parent=self._window)
            self.port_edit.focus_set()
            return False

        port_num = int(port_str)
        if port_num < 1 or port_num > 65535:
            tk_messagebox.showwarning("输入错误", "端口号必须在 1-65535 之间", parent=self._window)
            self.port_edit.focus_set()
            return False

        if not username:
            tk_messagebox.showwarning("输入错误", "请输入用户名", parent=self._window)
            self.username_edit.focus_set()
            return False

        if len(username) < 2:
            tk_messagebox.showwarning("输入错误", "用户名至少需要2个字符", parent=self._window)
            self.username_edit.focus_set()
            return False

        return True

    def _on_connect_clicked(self):
        if not self._validate_inputs():
            return
        server = self.server_var.get().strip()
        port = int(self.port_var.get().strip())
        username = self.username_var.get().strip()
        password = self.password_var.get()

        self._set_connecting(True)
        self.connect_request.emit(server, port, username, password)

    def _on_register_clicked(self):
        if not self._validate_inputs():
            return
        server = self.server_var.get().strip()
        port = int(self.port_var.get().strip())
        username = self.username_var.get().strip()
        password = self.password_var.get()

        self._set_connecting(True)
        self.register_request.emit(server, port, username, password)

    def _on_cancel(self):
        # 取消时关闭；应用层的 finished/cancelled 处理由 CollaborationApp 决定
        self.status_label.configure(text="已取消", fg="#666666")
        self.close()

    def _set_connecting(self, connecting: bool):
        self._connecting = connecting
        has_username = bool(self.username_var.get().strip())
        if connecting:
            self.connect_button.configure(state="disabled")
            self.register_button.configure(state="disabled")
            self.server_edit.configure(state="disabled")
            self.port_edit.configure(state="disabled")
            self.username_edit.configure(state="disabled")
            self.password_edit.configure(state="disabled")
            self.cancel_button.configure(text="等待...")
            self.status_label.configure(text="正在连接...", fg="#0066cc")
        else:
            state = "normal" if has_username else "disabled"
            self.connect_button.configure(state=state)
            self.register_button.configure(state=state)
            self.server_edit.configure(state="normal")
            self.port_edit.configure(state="normal")
            self.username_edit.configure(state="normal")
            self.password_edit.configure(state="normal")
            self.cancel_button.configure(text="取消")
            self.status_label.configure(text="", fg="#666666")

    # 与原版本保持一致的一些辅助方法：
    def get_server_info(self):
        return self.server_var.get().strip(), int(self.port_var.get().strip())

    def get_credentials(self):
        return self.username_var.get().strip(), self.password_var.get()


__all__ = ["LoginDialog"]
