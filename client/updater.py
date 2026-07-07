"""
ConnectHub 自动更新模块（Tkinter 版本）。
检查 GitHub Release 上的新版本，发现更新时弹窗提示用户。
- 无 PyQt5 依赖
- 网络检查在后台线程
- 版本信息与仓库信息从 /workspace/version.json 读取
"""

import ctypes
import json
import logging
import os
import sys
import threading
import webbrowser
from ctypes import wintypes
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

_project_root = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(_project_root))
sys.path.insert(0, str(Path(__file__).parent))

from protocol.signals import Signal

logger = logging.getLogger(__name__)

_DEFAULT_OWNER = "ccx121014"
_DEFAULT_REPO = "ConnectHub"
_DEFAULT_VERSION = "0.0.0"
_API_TIMEOUT = 10


# ---------------------------------------------------------------------------
# WinHTTP HTTPS GET (绕过 Python ssl/OpenSSL，使用 Windows 原生 TLS)
# ---------------------------------------------------------------------------
def _winhttp_get(url: str, timeout_ms: int = 10000) -> bytes:
    """使用 Windows WinHTTP API 发送 HTTPS GET 请求。"""
    winhttp = ctypes.windll.winhttp

    hSession = winhttp.WinHttpOpen(
        f"ConnectHub-Updater/{_DEFAULT_VERSION}",
        1,  # WINHTTP_ACCESS_TYPE_DEFAULT_PROXY
        None,
        None,
        0,
    )
    if not hSession:
        raise OSError("WinHttpOpen failed")

    try:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        port = parsed.port or (443 if parsed.scheme == "https" else 80)

        hConnect = winhttp.WinHttpConnect(hSession, host, port, 0)
        if not hConnect:
            raise OSError("WinHttpConnect failed")

        try:
            path = parsed.path or "/"
            if parsed.query:
                path += "?" + parsed.query

            flags = 0x00800000 if parsed.scheme == "https" else 0  # WINHTTP_FLAG_SECURE
            hRequest = winhttp.WinHttpOpenRequest(
                hConnect, "GET", path, None, None, None, flags
            )
            if not hRequest:
                raise OSError("WinHttpOpenRequest failed")

            try:
                # 设置超时
                if timeout_ms > 0:
                    dw = wintypes.DWORD(timeout_ms)
                    sz = ctypes.sizeof(dw)
                    winhttp.WinHttpSetOption(hRequest, 11, ctypes.byref(dw), sz)  # CONNECT
                    winhttp.WinHttpSetOption(hRequest, 5, ctypes.byref(dw), sz)   # SEND
                    winhttp.WinHttpSetOption(hRequest, 6, ctypes.byref(dw), sz)   # RECEIVE

                # 添加 Accept header
                headers = "Accept: application/vnd.github+json\r\n"
                if not winhttp.WinHttpSendRequest(
                    hRequest, headers, len(headers), None, 0, 0, 0
                ):
                    raise OSError("WinHttpSendRequest failed")

                if not winhttp.WinHttpReceiveResponse(hRequest, None):
                    raise OSError("WinHttpReceiveResponse failed")

                # 读取状态码
                status_code = wintypes.DWORD()
                status_size = wintypes.DWORD(ctypes.sizeof(status_code))
                winhttp.WinHttpQueryHeaders(
                    hRequest,
                    19,  # WINHTTP_QUERY_STATUS_CODE
                    None,
                    ctypes.byref(status_code),
                    ctypes.byref(status_size),
                    None,
                )
                code = int(status_code.value)
                if code != 200:
                    raise OSError(f"HTTP {code}")

                chunks = []
                while True:
                    avail = wintypes.DWORD()
                    if not winhttp.WinHttpQueryDataAvailable(
                        hRequest, ctypes.byref(avail)
                    ):
                        raise OSError("WinHttpQueryDataAvailable failed")
                    if avail.value == 0:
                        break
                    buf = ctypes.create_string_buffer(avail.value)
                    read = wintypes.DWORD()
                    if not winhttp.WinHttpReadData(
                        hRequest, buf, avail.value, ctypes.byref(read)
                    ):
                        raise OSError("WinHttpReadData failed")
                    chunks.append(buf.raw[: read.value])
                return b"".join(chunks)
            finally:
                winhttp.WinHttpCloseHandle(hRequest)
        finally:
            winhttp.WinHttpCloseHandle(hConnect)
    finally:
        winhttp.WinHttpCloseHandle(hSession)


def _find_version_json() -> Path:
    """查找 version.json：兼容 PyInstaller onefile / onedir / 源码运行。"""
    # PyInstaller 打包后：sys._MEIPASS 指向 bundle 目录
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        p = Path(meipass) / "version.json"
        if p.exists():
            return p
    # 源码运行
    p = _project_root / "version.json"
    if p.exists():
        return p
    # onedir 模式：exe 同级目录
    if getattr(sys, "frozen", False):
        p = Path(sys.executable).parent / "version.json"
        if p.exists():
            return p
    return _project_root / "version.json"


class Updater:
    """检查 GitHub Releases 上的更新。"""

    def __init__(self, master=None, version_file: Optional[str] = None):
        """
        :param master: Tk 主窗口（可选，用于把弹窗设置为其子窗口）
        :param version_file: version.json 路径；None 时使用默认位置
        """
        self.master = master
        self._version_file: Path = (
            Path(version_file) if version_file else _find_version_json()
        )

        cfg = self._load_version_config()
        self.current_version: str = cfg.get("version", _DEFAULT_VERSION)
        self.repo_owner: str = cfg.get("repo_owner", _DEFAULT_OWNER)
        self.repo_name: str = cfg.get("repo_name", _DEFAULT_REPO)
        self.latest_version: Optional[str] = None
        self.latest_url: Optional[str] = None
        self.latest_notes: str = ""

        # 信号
        self.update_available = Signal(str, str, str)  # (current, new, release_url)
        self.no_update = Signal()
        self.update_error = Signal(str)

    # -------- 配置 --------
    def _load_version_config(self) -> Dict[str, Any]:
        try:
            if self._version_file.exists():
                with open(self._version_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as exc:
            logger.warning(f"读取 version.json 失败: {exc}")
        return {}

    # -------- API 检查 --------
    def _build_latest_api_url(self) -> str:
        return (
            f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/releases/latest"
        )

    def _fetch_latest_release(self) -> Optional[Dict[str, Any]]:
        url = self._build_latest_api_url()
        try:
            raw = _winhttp_get(url, timeout_ms=_API_TIMEOUT * 1000)
            data = json.loads(raw.decode("utf-8"))
        except OSError as exc:
            err = str(exc).lower()
            if "403" in err or "429" in err:
                self.update_error.emit("GitHub API 访问频率超限，请稍后再试")
            elif "http" in err:
                self.update_error.emit(f"HTTP 错误: {exc}")
            else:
                self.update_error.emit(f"网络错误: {exc}")
            return None
        except (json.JSONDecodeError, ValueError) as exc:
            self.update_error.emit(f"无法解析更新信息: {exc}")
            return None

        if not isinstance(data, dict):
            self.update_error.emit("更新信息格式不正确")
            return None
        return data

    @staticmethod
    def _compare_versions(v1: str, v2: str) -> int:
        """比较语义版本号。v1 > v2 返回 1，v1 < v2 返回 -1，相等返回 0。"""
        def parse(version: str):
            # 去掉前缀 "v" 以及 pre-release 部分（如 -beta）
            cleaned = version.lstrip("vV").split("-")[0].split("+")[0]
            parts = []
            for p in cleaned.split("."):
                try:
                    parts.append(int(p))
                except ValueError:
                    parts.append(0)
            while len(parts) < 3:
                parts.append(0)
            return tuple(parts[:3])

        a, b = parse(v1), parse(v2)
        if a > b:
            return 1
        if a < b:
            return -1
        return 0

    def _run_check(self, show_dialog: bool):
        """在后台线程中执行的实际检查逻辑。"""
        data = self._fetch_latest_release()
        if not data:
            return

        tag_name = (data.get("tag_name") or "").strip()
        if not tag_name:
            self.update_error.emit("未找到版本号标签")
            return

        html_url = data.get("html_url", "") or ""

        # 优先使用 assets 中的安装包链接，否则用 release page
        download_url = html_url
        assets = data.get("assets", []) or []
        for a in assets:
            if not isinstance(a, dict):
                continue
            name = (a.get("name") or "").lower()
            # 优先选择安装/客户端压缩包
            if name.endswith(".exe") or ("client" in name and name.endswith(".zip")):
                download_url = a.get("browser_download_url") or html_url
                break

        self.latest_version = tag_name
        self.latest_url = download_url
        self.latest_notes = str(data.get("body") or data.get("name") or "")

        cmp_result = self._compare_versions(tag_name, self.current_version)
        if cmp_result > 0:
            # 有新版本
            self.update_available.emit(self.current_version, tag_name, download_url)
            if show_dialog:
                try:
                    self._show_update_dialog(tag_name, download_url)
                except Exception as exc:
                    logger.warning(f"弹窗失败: {exc}")
        else:
            self.no_update.emit()

    def check_for_updates(self, show_dialog: bool = True):
        """异步启动版本检查，立即返回。"""
        t = threading.Thread(
            target=self._run_check, args=(show_dialog,), daemon=True
        )
        t.start()

    # -------- Tk 弹窗 --------
    def _show_update_dialog(self, new_version: str, release_url: str):
        """在主线程中弹出更新提示对话框。"""
        # 如果主窗口存在，使用 after 把调用调度到 Tk 主线程
        if self.master is not None and hasattr(self.master, "after"):
            try:
                self.master.after(
                    0,
                    lambda: self._do_show_update_dialog(new_version, release_url),
                )
                return
            except Exception:
                pass
        # 否则直接创建一个临时 Tk 实例
        self._do_show_update_dialog(new_version, release_url)

    def _do_show_update_dialog(self, new_version: str, release_url: str):
        try:
            import tkinter as tk
            from tkinter import messagebox
        except Exception as exc:
            logger.error(f"无法加载 tkinter: {exc}")
            return

        # 创建临时根窗口以便弹窗有正确的图标/归属
        root = self.master
        temp_created = False
        if root is None:
            try:
                root = tk.Tk()
                root.withdraw()
                temp_created = True
            except Exception:
                root = None

        try:
            msg = (
                f"发现新版本 v{new_version.lstrip('v')}\n"
                f"当前版本: v{self.current_version}\n\n"
                "是否下载？"
            )
            title = "发现新版本 - ConnectHub"

            # 使用自定义 yes/no 按钮文字（messagebox 的按钮文字是本地化的；
            # 这里提供自定义窗口以保证中文按钮文字）
            result = self._ask_yes_no(title, msg, yes_text="下载", no_text="稍后", parent=root)
            if result:
                if release_url:
                    try:
                        webbrowser.open(release_url)
                    except Exception as exc:
                        logger.error(f"打开浏览器失败: {exc}")
        finally:
            if temp_created and root is not None:
                try:
                    root.destroy()
                except Exception:
                    pass

    def _ask_yes_no(self, title: str, message: str, yes_text: str = "是",
                    no_text: str = "否", parent=None) -> bool:
        """简单的自定义 Yes/No 对话框，避免依赖系统本地化。"""
        import tkinter as tk

        dialog = tk.Toplevel(parent)
        dialog.title(title)
        dialog.transient(parent)
        dialog.grab_set()
        dialog.resizable(False, False)

        # 居中显示
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
            dialog,
            text=message,
            justify="left",
            padx=18,
            pady=18,
            wraplength=w - 40,
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
        tk.Button(btn_frame, text=yes_text, width=10, command=on_yes).pack(
            side="left", padx=8
        )
        tk.Button(btn_frame, text=no_text, width=10, command=on_no).pack(
            side="left", padx=8
        )

        dialog.protocol("WM_DELETE_WINDOW", on_no)
        dialog.wait_window()
        return result["value"]


__all__ = ["Updater"]
