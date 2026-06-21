"""
Chat Widget for Online Collaboration Suite (Tkinter version)
Provides 1:1 and group chat functionality with message display and input.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# Add project root and client dir to path for module imports (cross-platform)
from pathlib import Path
import sys as _sys

_project_root = Path(__file__).parent.parent.resolve()
_sys.path.insert(0, str(_project_root))
_sys.path.insert(0, str(Path(__file__).parent))

from protocol.signals import Signal


class BubbleMessage(tk.Frame):
    """A single bubble-style message widget.

    Renders either on the left (incoming) or right (own) side.
    """

    def __init__(self, master, username: str, content: str,
                 timestamp: datetime = None, is_own: bool = False,
                 message_type: str = "text"):
        super().__init__(master, bg="#F9F9FB")
        self.username = username
        self.content = content
        self.timestamp = timestamp or datetime.now()
        self.is_own = is_own
        self.message_type = message_type

        self._init_ui()

    def _init_ui(self):
        if self.message_type == "system":
            bubble_bg = "#FFF8E1"
            border_color = "#FFE082"
            fg = "#795548"
        elif self.is_own:
            bubble_bg = "#E3F2FD"
            border_color = "#BBDEFB"
            fg = "#0D47A1"
        else:
            bubble_bg = "#FFFFFF"
            border_color = "#E0E0E0"
            fg = "#212121"

        # Outer row container (for left/right alignment of whole bubble)
        outer = tk.Frame(self, bg="#F9F9FB")
        if self.is_own:
            outer.pack(fill="x", padx=(80, 10), pady=4)
        else:
            outer.pack(fill="x", padx=(10, 80), pady=4)

        # Bubble container
        bubble = tk.Frame(outer, bg=bubble_bg,
                          highlightthickness=1,
                          highlightbackground=border_color)

        if self.is_own:
            bubble.pack(side="right", anchor="e")
        else:
            bubble.pack(side="left", anchor="w")

        # Header: username + timestamp
        header = tk.Frame(bubble, bg=bubble_bg)
        header.pack(fill="x", padx=8, pady=(6, 2))

        user_label = tk.Label(
            header, text=self.username, bg=bubble_bg, fg=fg,
            font=("TkDefaultFont", 9, "bold"), anchor="w"
        )
        if self.is_own:
            user_label.pack(side="right")
        else:
            user_label.pack(side="left")

        # Content (selectable Text widget)
        content_text = tk.Text(
            bubble, wrap="word", height=1, bd=0,
            bg=bubble_bg, fg=fg,
            font=("TkDefaultFont", 10),
            highlightthickness=0,
            padx=8, pady=2,
            cursor="xterm"
        )
        content_text.insert("1.0", self.content)
        content_text.configure(state="disabled")
        # Auto-size height based on content length
        line_count = max(1, (len(self.content) // 60) + self.content.count("\n") + 1)
        line_count = min(line_count, 15)
        content_text.configure(height=line_count)
        content_text.pack(fill="x", padx=4, pady=(0, 2))

        # Timestamp footer
        ts_text = self.timestamp.strftime("%H:%M:%S")
        ts_label = tk.Label(
            bubble, text=ts_text, bg=bubble_bg, fg="#9E9E9E",
            font=("TkDefaultFont", 7)
        )
        if self.is_own:
            ts_label.pack(side="right", padx=8, pady=(0, 6))
        else:
            ts_label.pack(side="left", padx=8, pady=(0, 6))


class ChatHistory(ttk.Frame):
    """Scrollable message list."""

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self._messages: List[BubbleMessage] = []

        # Canvas + scrollbar + inner frame for scrolling
        self.canvas = tk.Canvas(self, bg="#F9F9FB", highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical",
                                       command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        self.inner = tk.Frame(self.canvas, bg="#F9F9FB")
        self._inner_window = self.canvas.create_window(
            (0, 0), window=self.inner, anchor="nw"
        )
        self.inner.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfigure(self._inner_window, width=e.width)
        )

        # Mouse wheel
        self._bind_mousewheel(self.canvas)
        self._bind_mousewheel(self.inner)

    def _bind_mousewheel(self, widget):
        def _on_wheel(event):
            if event.num == 4:
                self.canvas.yview_scroll(-1, "units")
            elif event.num == 5:
                self.canvas.yview_scroll(1, "units")
            else:
                self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        widget.bind("<MouseWheel>", _on_wheel)
        widget.bind("<Button-4>", _on_wheel)
        widget.bind("<Button-5>", _on_wheel)

    def add_message(self, bubble: BubbleMessage):
        bubble.pack(fill="x", padx=4, pady=2)
        self._messages.append(bubble)
        self._scroll_to_bottom()

    def clear_messages(self):
        for msg in self._messages:
            msg.destroy()
        self._messages.clear()

    def _scroll_to_bottom(self):
        self.update_idletasks()
        self.canvas.yview_moveto(1.0)


class ChatWidget(ttk.Frame):
    """Single chat conversation widget.

    Signals:
        message_sent (str, str)  — (target, content)
        send_file_request (str)  — (target)

    Methods:
        set_username(username)
        set_chat_target(target, is_group=False)
        add_message(username, content, timestamp=None, message_type='text')
        add_system_message(content)
        clear_chat()
        close()
    """

    def __init__(self, master=None, **kwargs):
        super().__init__(master, **kwargs)
        self._current_target: Optional[str] = None
        self._is_group_chat: bool = False
        self._username: Optional[str] = None
        self._message_history: Dict[str, List[Tuple[str, str, datetime]]] = {}

        # Signals
        self.message_sent = Signal(str, str)
        self.send_file_request = Signal(str)

        # UI
        self._init_ui()

    # ---------- UI ----------
    def _init_ui(self):
        # Header bar
        self.header = tk.Frame(self, bg="#FAFAFA",
                               highlightthickness=1,
                               highlightbackground="#E0E0E0")
        self.header.pack(fill="x")

        self.title_label = tk.Label(
            self.header, text="聊天", bg="#FAFAFA",
            fg="#212121", font=("TkDefaultFont", 11, "bold"),
            anchor="w", padx=10, pady=6
        )
        self.title_label.pack(side="left")

        # Chat history
        self.chat_history = ChatHistory(self)
        self.chat_history.pack(fill="both", expand=True, padx=2, pady=2)

        # Input area
        input_frame = tk.Frame(self, bg="#FAFAFA",
                               highlightthickness=1,
                               highlightbackground="#E0E0E0")
        input_frame.pack(fill="x", padx=2, pady=(0, 2))

        # File button row
        file_row = tk.Frame(input_frame, bg="#FAFAFA")
        file_row.pack(fill="x", padx=6, pady=(6, 2))

        self.file_button = tk.Button(
            file_row, text="📎 发送文件", bd=0,
            bg="#FAFAFA", activebackground="#E3F2FD",
            fg="#1565C0", font=("TkDefaultFont", 9),
            command=self._on_file_button_clicked, cursor="hand2"
        )
        self.file_button.pack(side="right")

        # Message input + send button row
        msg_row = tk.Frame(input_frame, bg="#FAFAFA")
        msg_row.pack(fill="x", padx=6, pady=(2, 6))

        self.message_input = tk.Text(
            msg_row, wrap="word", height=2, bd=1,
            bg="#FFFFFF", fg="#212121",
            font=("TkDefaultFont", 10),
            highlightthickness=1,
            highlightbackground="#E0E0E0",
            highlightcolor="#2196F3",
            insertbackground="#212121",
            cursor="xterm",
            padx=6, pady=6,
        )
        self.message_input.pack(side="left", fill="both", expand=True,
                                padx=(0, 6))

        # Enter to send (Shift+Enter for newline)
        self.message_input.bind("<Return>", self._on_enter_key)
        self.message_input.bind("<Shift-Return>", lambda e: None)
        self.message_input.bind("<KeyRelease>", lambda e: self._update_send_state())

        self.send_button = tk.Button(
            msg_row, text="发送", bd=0,
            bg="#2E7D32", fg="#FFFFFF", activebackground="#388E3C",
            activeforeground="#FFFFFF",
            font=("TkDefaultFont", 10, "bold"),
            padx=16, pady=8, cursor="hand2",
            command=self._on_send_clicked
        )
        self.send_button.pack(side="right")
        self.send_button.configure(state="disabled")

    # ---------- Public API ----------
    def set_username(self, username: str):
        self._username = username

    def set_chat_target(self, target: str, is_group: bool = False):
        self._current_target = target
        self._is_group_chat = is_group
        title = f"群聊: {target}" if is_group else f"与 {target} 的聊天"
        self.title_label.configure(text=title)

    def add_message(self, username: str, content: str,
                    timestamp: datetime = None, message_type: str = "text"):
        """Add a message to the chat history (thread-safe via after())."""
        def _do():
            ts = timestamp if timestamp is not None else datetime.now()
            is_own = (username == self._username)
            bubble = BubbleMessage(
                self.chat_history.inner,
                username=username,
                content=content,
                timestamp=ts,
                is_own=is_own,
                message_type=message_type,
            )
            self.chat_history.add_message(bubble)

            # Append to history
            if self._current_target:
                if self._current_target not in self._message_history:
                    self._message_history[self._current_target] = []
                self._message_history[self._current_target].append(
                    (username, content, ts)
                )

        self._run_on_ui_thread(_do)

    def add_system_message(self, content: str):
        def _do():
            bubble = BubbleMessage(
                self.chat_history.inner,
                username="系统",
                content=content,
                timestamp=datetime.now(),
                is_own=False,
                message_type="system",
            )
            self.chat_history.add_message(bubble)
        self._run_on_ui_thread(_do)

    def clear_chat(self):
        self.chat_history.clear_messages()

    def close(self):
        self.clear_chat()

    # ---------- Internal ----------
    def _on_enter_key(self, event):
        # Plain Enter: send. Shift+Enter already default behavior in Text
        # In Tkinter, Shift+Enter does NOT automatically insert a newline
        # in a plain Text widget; we detect the modifier here.
        if event.state & 0x0001:  # Shift key
            # Let default behavior (insert newline) happen
            return None
        self._on_send_clicked()
        return "break"

    def _update_send_state(self):
        content = self.message_input.get("1.0", "end").strip()
        has_target = self._current_target is not None
        self.send_button.configure(
            state="normal" if (content and has_target) else "disabled"
        )

    def _on_send_clicked(self):
        content = self.message_input.get("1.0", "end").strip()
        if not content or not self._current_target:
            return

        # Show locally as own message
        self.add_message(self._username or "我", content)
        self.message_sent.emit(self._current_target, content)
        self.message_input.delete("1.0", "end")

    def _on_file_button_clicked(self):
        if not self._current_target:
            try:
                messagebox.showwarning("提示", "请先选择一个聊天对象")
            except Exception:
                pass
            return

        file_path = filedialog.askopenfilename(
            title="选择要发送的文件"
        )
        if file_path:
            self.send_file_request.emit(self._current_target)

    def _run_on_ui_thread(self, fn):
        """Schedule `fn` to run on the Tk main thread (safe from worker threads)."""
        root = self._get_root()
        if root is not None:
            try:
                root.after(0, fn)
            except Exception:
                fn()
        else:
            fn()

    def _get_root(self) -> Optional[tk.Misc]:
        try:
            return self.winfo_toplevel()
        except Exception:
            return None


class ChatTabWidget(ttk.Frame):
    """Tab-based chat widget. Each conversation in its own tab.

    Signals:
        message_sent (str, str)    — (target, content)

    Methods:
        set_username(username)
        open_chat(target, is_group=False)
        add_message_to_chat(target, username, content, timestamp=None)
        close_all_chats()
    """

    def __init__(self, master=None, **kwargs):
        super().__init__(master, **kwargs)
        self._chats: Dict[str, ChatWidget] = {}
        self._username: Optional[str] = None

        # Signals
        self.message_sent = Signal(str, str)

        self._init_ui()

    def _init_ui(self):
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True)

        # Bind tab close via middle-click on the tab (optional convenience)
        self.notebook.bind("<Button-2>", self._on_tab_middle_click)

    def _on_tab_middle_click(self, event):
        try:
            tab_id = self.notebook.index(f"@{event.x},{event.y}")
            if tab_id >= 0:
                target = self._target_for_tab_index(tab_id)
                if target:
                    self._close_chat(target)
        except Exception:
            pass

    def _target_for_tab_index(self, index: int) -> Optional[str]:
        try:
            widget = self.notebook.nametowidget(self.notebook.tabs()[index])
        except Exception:
            return None
        for target, chat in self._chats.items():
            if chat is widget:
                return target
        return None

    # ---------- Public API ----------
    def set_username(self, username: str):
        self._username = username
        for chat in self._chats.values():
            chat.set_username(username)

    def open_chat(self, target: str, is_group: bool = False):
        if target in self._chats:
            self.notebook.select(self._chats[target])
        else:
            self._create_chat_tab(target, is_group)

    def _create_chat_tab(self, target: str, is_group: bool = False):
        chat = ChatWidget(self.notebook)
        chat.set_username(self._username or "")
        chat.set_chat_target(target, is_group)

        # Forward message_sent to notebook-level signal
        chat.message_sent.connect(
            lambda tgt, content: self.message_sent.emit(tgt, content)
        )

        # Trim label to a reasonable width
        tab_text = target if len(target) <= 15 else target[:12] + "..."
        self.notebook.add(chat, text=tab_text)
        self.notebook.select(chat)

        self._chats[target] = chat

    def add_message_to_chat(self, target: str, username: str, content: str,
                            timestamp: datetime = None):
        if target not in self._chats:
            self._create_chat_tab(target, False)
        self._chats[target].add_message(username, content, timestamp)

    def close_all_chats(self):
        for chat in list(self._chats.values()):
            try:
                self.notebook.forget(chat)
            except Exception:
                pass
            try:
                chat.close()
            except Exception:
                pass
        self._chats.clear()

    def _close_chat(self, target: str):
        if target in self._chats:
            chat = self._chats.pop(target)
            try:
                self.notebook.forget(chat)
            except Exception:
                pass
            try:
                chat.close()
            except Exception:
                pass
