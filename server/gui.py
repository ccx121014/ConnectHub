"""
ConnectHub Server GUI (Tkinter)
提供启动/停止、日志显示、在线用户列表等操作界面。
"""

import sys
import os
import threading
import queue
import asyncio
import logging
import time
from pathlib import Path
from typing import Optional

# --- 注入 ssl stub（PyInstaller 排除 OpenSSL 后的最小兼容层）---
if "ssl" not in sys.modules:
    from client import ssl_stub

    sys.modules["ssl"] = ssl_stub

# Ensure project root on path
_project_root = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(_project_root))
sys.path.insert(0, str(Path(__file__).parent))

import tkinter as tk
from tkinter import ttk, messagebox

from main import CollaborationServer, HOST, PORT

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Thread-safe log handler -> Tkinter
# ---------------------------------------------------------------------------
class TkLogHandler(logging.Handler):
    def __init__(self, log_queue: queue.Queue):
        super().__init__()
        self._q = log_queue

    def emit(self, record):
        try:
            msg = self.format(record)
            self._q.put(("log", msg))
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Server GUI
# ---------------------------------------------------------------------------
class ServerGUI:
    def __init__(self):
        self._root = tk.Tk()
        self._root.title("ConnectHub Server")
        self._root.geometry("720x520")
        self._root.minsize(560, 380)

        self._server: Optional[CollaborationServer] = None
        self._server_thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._stop_event = threading.Event()

        self._log_queue: "queue.Queue[tuple]" = queue.Queue()
        self._status_queue: "queue.Queue[tuple]" = queue.Queue()

        self._build_ui()
        self._setup_logging()
        self._start_polling()

        self._root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------- UI ----------
    def _build_ui(self):
        # Header
        header = tk.Frame(self._root, bg="#1976D2", height=48)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(
            header, text="ConnectHub Server", bg="#1976D2", fg="#FFFFFF",
            font=("TkDefaultFont", 14, "bold")
        ).pack(side="left", padx=12, pady=8)
        self._status_dot = tk.Canvas(header, width=14, height=14,
                                      bg="#1976D2", highlightthickness=0)
        self._status_dot.pack(side="right", padx=12, pady=8)
        self._draw_dot("#9E9E9E")

        # Controls
        ctrl = ttk.Frame(self._root, padding=8)
        ctrl.pack(fill="x")

        ttk.Label(ctrl, text="端口:").pack(side="left", padx=(0, 4))
        self._port_var = tk.StringVar(value=str(PORT))
        self._port_entry = ttk.Entry(ctrl, textvariable=self._port_var, width=8)
        self._port_entry.pack(side="left", padx=(0, 8))

        self._start_btn = ttk.Button(ctrl, text="启动服务", command=self._on_start)
        self._start_btn.pack(side="left", padx=(0, 6))

        self._stop_btn = ttk.Button(ctrl, text="停止服务", command=self._on_stop,
                                     state="disabled")
        self._stop_btn.pack(side="left", padx=(0, 6))

        self._info_label = ttk.Label(ctrl, text="就绪")
        self._info_label.pack(side="right", padx=4)

        # Paned: left = user list, right = log
        paned = ttk.PanedWindow(self._root, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        # Left: online users
        left = ttk.LabelFrame(paned, text="在线用户", padding=4)
        paned.add(left, weight=1)

        self._user_list = tk.Listbox(left, activestyle="none")
        self._user_list.pack(fill="both", expand=True, side="left")
        user_scroll = ttk.Scrollbar(left, orient="vertical",
                                    command=self._user_list.yview)
        user_scroll.pack(side="right", fill="y")
        self._user_list.configure(yscrollcommand=user_scroll.set)

        # Right: log
        right = ttk.LabelFrame(paned, text="服务器日志", padding=4)
        paned.add(right, weight=3)

        self._log_text = tk.Text(right, wrap="word", state="disabled",
                                  bg="#1E1E1E", fg="#D4D4D4",
                                  font=("Consolas", 9),
                                  highlightthickness=0,
                                  padx=6, pady=6)
        self._log_text.pack(fill="both", expand=True, side="left")
        log_scroll = ttk.Scrollbar(right, orient="vertical",
                                   command=self._log_text.yview)
        log_scroll.pack(side="right", fill="y")
        self._log_text.configure(yscrollcommand=log_scroll.set)

        # Footer
        footer = tk.Frame(self._root, bg="#EEEEEE", height=24)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)
        self._footer_label = tk.Label(
            footer, text="未运行", bg="#EEEEEE", fg="#424242",
            anchor="w", padx=10, font=("TkDefaultFont", 9)
        )
        self._footer_label.pack(side="left", fill="x", expand=True)

    def _draw_dot(self, color: str):
        self._status_dot.delete("all")
        self._status_dot.create_oval(2, 2, 12, 12, fill=color, outline="")

    # ---------- Logging ----------
    def _setup_logging(self):
        handler = TkLogHandler(self._log_queue)
        handler.setFormatter(logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s",
            datefmt="%H:%M:%S"
        ))
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)

    def _append_log(self, text: str):
        self._log_text.configure(state="normal")
        self._log_text.insert("end", text + "\n")
        self._log_text.see("end")
        # Limit lines
        lines = int(self._log_text.index("end-1c").split(".")[0])
        if lines > 500:
            self._log_text.delete("1.0", f"{lines - 400}.0")
        self._log_text.configure(state="disabled")

    def _update_users(self, users):
        self._user_list.delete(0, "end")
        for u in sorted(users):
            self._user_list.insert("end", u)

    # ---------- Polling ----------
    def _start_polling(self):
        self._poll_logs()
        self._poll_status()

    def _poll_logs(self):
        try:
            for _ in range(32):
                try:
                    kind, msg = self._log_queue.get_nowait()
                except queue.Empty:
                    break
                if kind == "log":
                    self._append_log(msg)
        except Exception:
            pass
        self._root.after(150, self._poll_logs)

    def _poll_status(self):
        try:
            for _ in range(8):
                try:
                    kind, data = self._status_queue.get_nowait()
                except queue.Empty:
                    break
                if kind == "started":
                    self._draw_dot("#4CAF50")
                    self._start_btn.configure(state="disabled")
                    self._stop_btn.configure(state="normal")
                    self._info_label.configure(text=f"监听 {data}")
                    self._footer_label.configure(text=f"运行中 — {data}")
                elif kind == "stopped":
                    self._draw_dot("#9E9E9E")
                    self._start_btn.configure(state="normal")
                    self._stop_btn.configure(state="disabled")
                    self._info_label.configure(text="已停止")
                    self._footer_label.configure(text="未运行")
                    self._update_users([])
                elif kind == "users":
                    self._update_users(data)
        except Exception:
            pass
        self._root.after(500, self._poll_status)

    # ---------- Server lifecycle ----------
    def _on_start(self):
        port_str = self._port_var.get().strip()
        if not port_str.isdigit():
            messagebox.showerror("错误", "端口号必须是数字", parent=self._root)
            return
        port = int(port_str)
        if port < 1 or port > 65535:
            messagebox.showerror("错误", "端口号必须在 1-65535 之间", parent=self._root)
            return

        self._stop_event.clear()
        self._server_thread = threading.Thread(
            target=self._server_loop, args=(port,), daemon=True
        )
        self._server_thread.start()

    def _on_stop(self):
        self._stop_event.set()
        loop = self._loop
        if loop and loop.is_running():
            try:
                loop.call_soon_threadsafe(loop.stop)
            except Exception:
                pass
        self._start_btn.configure(state="normal")
        self._stop_btn.configure(state="disabled")

    def _server_loop(self, port: int):
        """后台线程运行 asyncio 服务器。"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop

        try:
            from main import CollaborationServer
            server = CollaborationServer()
            self._server = server

            # monkey-patch port override if needed
            import main as _main_mod
            _main_mod.PORT = port

            self._status_queue.put(("started", f"0.0.0.0:{port}"))

            # User list refresh task
            async def _refresh_users():
                while not self._stop_event.is_set():
                    try:
                        users = list(server._authenticated_clients.keys())
                        self._status_queue.put(("users", users))
                    except Exception:
                        pass
                    await asyncio.sleep(2)

            async def _main():
                await server.start()

            # Run server + user refresh concurrently
            refresh_task = loop.create_task(_refresh_users())
            try:
                loop.run_until_complete(_main())
            finally:
                refresh_task.cancel()
                try:
                    loop.run_until_complete(refresh_task)
                except asyncio.CancelledError:
                    pass
        except Exception as exc:
            logger.error(f"Server error: {exc}", exc_info=True)
        finally:
            try:
                pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
                if pending:
                    for t in pending:
                        t.cancel()
                    loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )
            except Exception:
                pass
            try:
                loop.close()
            except Exception:
                pass
            self._loop = None
            self._server = None
            self._status_queue.put(("stopped", None))

    def _on_close(self):
        self._on_stop()
        self._root.destroy()

    def run(self):
        self._root.mainloop()


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------
def main():
    gui = ServerGUI()
    gui.run()


if __name__ == "__main__":
    main()
