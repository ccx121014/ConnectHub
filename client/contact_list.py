# -*- coding: utf-8 -*-
"""
Contact List Widget for Online Collaboration Suite (Tkinter version)
Displays online users with status indicators.
"""

import tkinter as tk
from tkinter import ttk
from enum import Enum
from typing import Dict, List, Optional

# Add project root and client dir to path for module imports (cross-platform)
from pathlib import Path
import sys as _sys

_project_root = Path(__file__).parent.parent.resolve()
_sys.path.insert(0, str(_project_root))
_sys.path.insert(0, str(Path(__file__).parent))

from protocol.signals import Signal


class UserStatus(Enum):
    """User status enumeration."""
    ONLINE = "online"
    BUSY = "busy"
    OFFLINE = "offline"
    AWAY = "away"


class StatusColors:
    """Color definitions for user statuses."""
    ONLINE = "#4CAF50"
    BUSY = "#FFC107"
    OFFLINE = "#9E9E9E"
    AWAY = "#FF9800"


class ContactItem(tk.Frame):
    """Custom widget showing contact info + action buttons (chat / file / desktop)."""

    def __init__(self, master: tk.Misc, username: str,
                 status: UserStatus = UserStatus.OFFLINE,
                 on_chat=None, on_file=None, on_desktop=None,
                 on_double_click=None):
        super().__init__(master, bg="#FFFFFF", highlightthickness=1,
                         highlightbackground="#E0E0E0")
        self.username = username
        self._status = status
        self._on_chat = on_chat
        self._on_file = on_file
        self._on_desktop = on_desktop
        self._on_double_click = on_double_click

        self._init_ui()

    def _init_ui(self):
        # Outer container uses grid for precise alignment
        self.grid_columnconfigure(2, weight=1)  # Text area expands
        for i in range(3, 8):
            self.grid_columnconfigure(i, weight=0)

        # Status dot (colored canvas circle)
        self.status_canvas = tk.Canvas(self, width=12, height=12,
                                       bg="#FFFFFF", highlightthickness=0)
        self.status_canvas.grid(row=0, column=0, padx=(8, 4), pady=8, sticky="w")
        self._draw_status_dot()

        # Avatar: use a Label to display a letter
        avatar_text = self.username[:1].upper() if self.username else "?"
        self.avatar_label = tk.Label(
            self,
            text=avatar_text,
            bg="#E0E0E0",
            fg="#757575",
            font=("TkDefaultFont", 12, "bold"),
            width=2,
            height=1
        )
        self.avatar_label.grid(row=0, column=1, padx=4, pady=8, sticky="w")

        # Text area: username (bold) + status text (smaller)
        text_frame = tk.Frame(self, bg="#FFFFFF")
        text_frame.grid(row=0, column=2, padx=(4, 8), pady=8, sticky="we")

        self.username_label = tk.Label(
            text_frame,
            text=self.username,
            bg="#FFFFFF",
            fg="#212121",
            font=("TkDefaultFont", 10, "bold"),
            anchor="w"
        )
        self.username_label.pack(anchor="w", fill="x")

        self.status_text = tk.Label(
            text_frame,
            text=self._status.value,
            bg="#FFFFFF",
            fg="#757575",
            font=("TkDefaultFont", 8),
            anchor="w"
        )
        self.status_text.pack(anchor="w", fill="x")

        # Action buttons
        btn_font = ("TkDefaultFont", 11)
        btn_pad = 2

        self.chat_btn = tk.Button(
            self, text="💬", font=btn_font, bd=0,
            bg="#FFFFFF", activebackground="#E3F2FD",
            relief="flat", padx=btn_pad, pady=btn_pad,
            command=self._chat_clicked
        )
        self.chat_btn.grid(row=0, column=3, padx=1, pady=8, sticky="w")

        self.file_btn = tk.Button(
            self, text="📁", font=btn_font, bd=0,
            bg="#FFFFFF", activebackground="#E3F2FD",
            relief="flat", padx=btn_pad, pady=btn_pad,
            command=self._file_clicked
        )
        self.file_btn.grid(row=0, column=4, padx=1, pady=8, sticky="w")

        self.desktop_btn = tk.Button(
            self, text="🖥", font=btn_font, bd=0,
            bg="#FFFFFF", activebackground="#E3F2FD",
            relief="flat", padx=btn_pad, pady=btn_pad,
            command=self._desktop_clicked
        )
        self.desktop_btn.grid(row=0, column=5, padx=(1, 8), pady=8, sticky="w")

        # Hook double-click on the whole item
        for widget in (self, self.status_canvas, self.avatar_label,
                       self.username_label, self.status_text, text_frame,
                       self.chat_btn, self.file_btn, self.desktop_btn):
            widget.bind("<Double-Button-1>", lambda e: self._double_clicked())

    def _draw_status_dot(self):
        color = getattr(StatusColors, self._status.name, StatusColors.OFFLINE)
        self.status_canvas.delete("all")
        self.status_canvas.create_oval(
            1, 1, 11, 11, fill=color, outline=""
        )

    def _chat_clicked(self):
        if self._on_chat:
            self._on_chat(self.username)

    def _file_clicked(self):
        if self._on_file:
            self._on_file(self.username)

    def _desktop_clicked(self):
        if self._on_desktop:
            self._on_desktop(self.username)

    def _double_clicked(self):
        if self._on_double_click:
            self._on_double_click(self.username)

    def set_status(self, status: UserStatus):
        self._status = status
        self._draw_status_dot()
        self.status_text.configure(text=status.value)

    def get_status(self) -> UserStatus:
        return self._status

    def set_username(self, username: str):
        self.username = username
        self.username_label.configure(text=username)
        self.avatar_label.configure(text=username[:1].upper() if username else "?")


class ContactListWidget(ttk.Frame):
    """Contact list widget showing online users with status indicators (Tkinter).

    Signals:
        contact_double_clicked (str)   — username
        start_chat_request (str)        — username
        start_file_transfer (str)       — username
        start_desktop_share (str, str)  — username, share_type

    Methods:
        set_contacts(contacts)
        update_contact_status(username, status)
        set_username(current_username)
        get_online_contacts() -> list[str]
        remove_contact(username)
        clear_contacts()
    """

    def __init__(self, master: tk.Misc = None, **kwargs):
        super().__init__(master, **kwargs)
        self._contacts: Dict[str, Dict] = {}
        self._contact_widgets: Dict[str, ContactItem] = {}
        self._username: Optional[str] = None
        self._current_filter: Optional[UserStatus] = None

        # Pure-python signals (from protocol.signals)
        self.contact_double_clicked = Signal(str)
        self.start_chat_request = Signal(str)
        self.start_file_transfer = Signal(str)
        self.start_desktop_share = Signal(str, str)

        self._init_ui()

    # ----------------- UI -----------------
    def _init_ui(self):
        # Outer layout — a labeled frame similar to original
        self.main_frame = ttk.LabelFrame(self, text="联系人")
        self.main_frame.pack(fill="both", expand=True, padx=4, pady=4)

        # Top row: search entry + filter button
        top = ttk.Frame(self.main_frame)
        top.pack(fill="x", padx=6, pady=(6, 4))

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._on_search_changed())
        self.search_entry = ttk.Entry(top, textvariable=self.search_var)
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        try:
            self.search_entry.insert(0, "搜索联系人...")
            # Light hint behavior
            self._placeholder_text = "搜索联系人..."
            self.search_entry.bind("<FocusIn>", self._on_search_focus_in)
            self.search_entry.bind("<FocusOut>", self._on_search_focus_out)
        except Exception:
            pass

        self.filter_btn = ttk.Menubutton(top, text="▼", direction="below")
        self.filter_btn.pack(side="right")

        # Filter menu
        self.filter_menu = tk.Menu(self.filter_btn, tearoff=0)
        self.filter_menu.add_command(label="全部显示",
                                     command=lambda: self._set_filter(None))
        self.filter_menu.add_command(label="仅显示在线",
                                     command=lambda: self._set_filter(UserStatus.ONLINE))
        self.filter_menu.add_command(label="仅显示忙碌",
                                     command=lambda: self._set_filter(UserStatus.BUSY))
        self.filter_btn["menu"] = self.filter_menu

        # Scrollable list area
        list_container = ttk.Frame(self.main_frame)
        list_container.pack(fill="both", expand=True, padx=4, pady=2)

        self.canvas = tk.Canvas(list_container, bg="#FFFFFF",
                                highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(list_container, orient="vertical",
                                       command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        self.list_inner = ttk.Frame(self.canvas)
        self._inner_window = self.canvas.create_window(
            (0, 0), window=self.list_inner, anchor="nw"
        )
        self.list_inner.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfigure(
                self._inner_window, width=e.width
            )
        )
        # Mouse wheel scrolling
        self._bind_mousewheel(self.canvas)
        self._bind_mousewheel(self.list_inner)

        # Footer: count label
        self.status_label = ttk.Label(
            self.main_frame, text="在线: 0/0", anchor="center"
        )
        self.status_label.pack(fill="x", padx=6, pady=(4, 6))

        # Empty placeholder
        self._empty_label = ttk.Label(
            self.list_inner,
            text="（暂无联系人）",
            foreground="#9E9E9E",
            anchor="center",
            padding=10
        )
        self._empty_label.pack(fill="x", pady=10)

    def _bind_mousewheel(self, widget):
        def _on_wheel(event):
            # Platform differences
            if event.num == 4:
                self.canvas.yview_scroll(-1, "units")
            elif event.num == 5:
                self.canvas.yview_scroll(1, "units")
            else:
                self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        widget.bind("<MouseWheel>", _on_wheel)
        widget.bind("<Button-4>", _on_wheel)
        widget.bind("<Button-5>", _on_wheel)

    # ------------- Search placeholder -------------
    def _on_search_focus_in(self, event):
        if self.search_var.get() == self._placeholder_text:
            self.search_entry.delete(0, "end")

    def _on_search_focus_out(self, event):
        if not self.search_var.get().strip():
            self.search_entry.insert(0, self._placeholder_text)

    # ------------- Signal handlers from items -------------
    def _on_chat_clicked(self, username: str):
        self.start_chat_request.emit(username)

    def _on_file_clicked(self, username: str):
        self.start_file_transfer.emit(username)

    def _on_desktop_clicked(self, username: str):
        self.start_desktop_share.emit(username, "view")

    def _on_item_double_clicked(self, username: str):
        self.contact_double_clicked.emit(username)

    def _on_search_changed(self):
        # Refresh the list display when search text changes
        self._refresh_list()

    def _set_filter(self, status: Optional[UserStatus]):
        self._current_filter = status
        self._refresh_list()

    # ------------- Public API -------------
    def set_username(self, username: str):
        self._username = username

    def add_contact(self, username: str, status: UserStatus = UserStatus.ONLINE,
                    **kwargs):
        self._contacts[username] = {
            "status": status,
            "metadata": kwargs
        }
        self._refresh_list()

    def update_contact_status(self, username: str, status):
        """Update a contact status. Accepts UserStatus enum or str."""
        if isinstance(status, str):
            try:
                status_enum = UserStatus(status)
            except ValueError:
                status_enum = UserStatus.OFFLINE
        else:
            status_enum = status

        if username in self._contacts:
            self._contacts[username]["status"] = status_enum
        else:
            self._contacts[username] = {
                "status": status_enum,
                "metadata": {}
            }
        self._refresh_list()

    def remove_contact(self, username: str):
        if username in self._contacts:
            del self._contacts[username]
            self._refresh_list()

    def clear_contacts(self):
        self._contacts.clear()
        self._refresh_list()

    def get_online_contacts(self) -> List[str]:
        return [
            username for username, data in self._contacts.items()
            if data["status"] == UserStatus.ONLINE
        ]

    def get_contact_status(self, username: str) -> Optional[UserStatus]:
        if username in self._contacts:
            return self._contacts[username]["status"]
        return None

    def set_contacts(self, contacts: List[Dict]):
        """Set contact list from server response (list of dicts)."""
        self._contacts.clear()
        for contact in contacts:
            if isinstance(contact, dict):
                username = contact.get("username", contact.get("name", ""))
                status_str = contact.get("status", "offline")
                try:
                    status = UserStatus(status_str)
                except ValueError:
                    status = UserStatus.OFFLINE
                self._contacts[username] = {
                    "status": status,
                    "metadata": contact
                }
            elif isinstance(contact, str):
                self._contacts[contact] = {
                    "status": UserStatus.OFFLINE,
                    "metadata": {}
                }
        self._refresh_list()

    # ------------- Private helpers -------------
    def _refresh_list(self):
        """Rebuild the visual list of contacts applying search + status filter."""
        # Remove existing contact widgets
        for w in self._contact_widgets.values():
            w.destroy()
        self._contact_widgets.clear()

        # Unpack empty placeholder first, repack later if empty
        self._empty_label.pack_forget()

        search_text = ""
        try:
            raw = self.search_var.get()
            if raw != self._placeholder_text:
                search_text = raw.lower()
        except Exception:
            pass

        filter_status = self._current_filter

        visible_count = 0
        row_index = 0
        for username in sorted(self._contacts.keys()):
            if username == self._username:
                continue
            if search_text and search_text not in username.lower():
                continue
            contact_data = self._contacts[username]
            if filter_status and contact_data["status"] != filter_status:
                continue

            item = ContactItem(
                self.list_inner,
                username=username,
                status=contact_data["status"],
                on_chat=self._on_chat_clicked,
                on_file=self._on_file_clicked,
                on_desktop=self._on_desktop_clicked,
                on_double_click=self._on_item_double_clicked,
            )
            item.pack(fill="x", padx=2, pady=1)
            self._contact_widgets[username] = item
            visible_count += 1
            row_index += 1

        if visible_count == 0:
            self._empty_label.pack(fill="x", pady=10)

        # Update footer count
        online_count = sum(
            1 for c in self._contacts.values()
            if c["status"] == UserStatus.ONLINE
        )
        self.status_label.configure(
            text=f"在线: {online_count}/{len(self._contacts)}"
        )

        # Refresh scroll region
        self.list_inner.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
