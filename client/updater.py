"""
ConnectHub 自动更新模块
在客户端启动时检查 GitHub Release 上的版本信息，
如果有新版本则提示用户下载更新。
"""

import json
import sys
import os
import threading
import urllib.request
import urllib.error
import webbrowser
from pathlib import Path
from typing import Optional, Dict, Any


CURRENT_VERSION = "1.0.0"

# 版本检查 URL（GitHub Release 页面的 API）
# 可通过 client/config.json 自定义
_DEFAULT_UPDATE_URL = (
    "https://api.github.com/repos/ccx121014/ConnectHub/releases/latest"
)


def _project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent.parent


def _read_local_config() -> Dict[str, Any]:
    """读取客户端目录下的 config.json 配置"""
    root = _project_root()
    candidates = [
        root / "client" / "config.json",
        root / "config.json",
    ]
    for p in candidates:
        try:
            if p.exists():
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            continue
    return {}


def check_for_update(update_url: Optional[str] = None, timeout: int = 8) -> Optional[Dict[str, Any]]:
    """
    检查是否有新版本。
    返回字典: { "version": "x.x.x", "download_url": "...", "notes": "..." }
    如果没有更新或检查失败，返回 None。
    """
    cfg = _read_local_config()
    if not cfg.get("auto_update", True):
        return None

    url = update_url or _DEFAULT_UPDATE_URL
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "ConnectHub-Updater/" + CURRENT_VERSION,
            "Accept": "application/vnd.github+json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, json.JSONDecodeError):
        # 网络不可用 / API 出错，静默忽略
        return None

    tag_name = data.get("tag_name", "").strip().lstrip("v")
    if not tag_name:
        return None

    if _version_compare(tag_name, CURRENT_VERSION) > 0:
        # 有新版本
        assets = data.get("assets", []) or []
        client_zip = None
        for a in assets:
            name = (a.get("name") or "").lower()
            if "client" in name and name.endswith(".zip"):
                client_zip = a.get("browser_download_url")
                break
        if not client_zip:
            # 回退到发布页面（需要用户手动下载）
            client_zip = data.get("html_url", "")

        return {
            "version": tag_name,
            "download_url": client_zip,
            "notes": data.get("body", "") or data.get("name", ""),
            "release_page": data.get("html_url", ""),
        }
    return None


def _version_compare(v1: str, v2: str) -> int:
    """简单的 semver 比较: v1 > v2 返回 1, 小于返回 -1, 等于返回 0"""
    def parse(v: str):
        parts = []
        for p in v.split("-")[0].split("."):
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


def notify_update_async(parent_widget=None, update_url: Optional[str] = None):
    """
    异步检查更新，有新版本时弹出对话框。
    该函数立即返回，不阻塞主线程。
    """
    def worker():
        info = check_for_update(update_url)
        if not info:
            return
        # 需要回主线程展示 UI
        try:
            from PyQt5.QtCore import QMetaObject, Qt
            from PyQt5.QtWidgets import QMessageBox, QApplication

            def show_dialog():
                app = QApplication.instance()
                if app is None:
                    return
                msg = QMessageBox(parent_widget)
                msg.setIcon(QMessageBox.Information)
                msg.setWindowTitle("发现新版本")
                msg.setText(
                    f"当前版本: {CURRENT_VERSION}\n"
                    f"最新版本: {info['version']}\n\n"
                    f"是否前往下载页面获取更新？"
                )
                if info.get("notes"):
                    msg.setDetailedText(info["notes"])
                msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
                msg.button(QMessageBox.Yes).setText("去下载")
                msg.button(QMessageBox.No).setText("稍后再说")
                if msg.exec_() == QMessageBox.Yes:
                    url = info.get("release_page") or info.get("download_url") or ""
                    if url:
                        webbrowser.open(url)

            QMetaObject.invokeMethod(
                _ObjectHolder.instance,
                "_show_dialog",
                Qt.QueuedConnection,
            )
        except Exception:
            pass

    # 简单方案：直接线程化，回调时用 QTimer.singleShot(0)
    def worker_simple():
        info = check_for_update(update_url)
        if not info:
            return
        try:
            from PyQt5.QtCore import QTimer, Qt
            from PyQt5.QtWidgets import QMessageBox, QApplication

            def show_dialog():
                app = QApplication.instance()
                if app is None:
                    return
                msg = QMessageBox(parent_widget)
                msg.setIcon(QMessageBox.Information)
                msg.setWindowTitle("发现新版本 - ConnectHub")
                msg.setText(
                    f"当前版本: {CURRENT_VERSION}\n"
                    f"最新版本: {info['version']}\n\n"
                    f"是否前往下载页面获取更新？"
                )
                if info.get("notes"):
                    msg.setDetailedText(str(info["notes"]))
                msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
                btn_yes = msg.button(QMessageBox.Yes)
                btn_yes.setText("去下载")
                msg.button(QMessageBox.No).setText("稍后再说")
                if msg.exec_() == QMessageBox.Yes:
                    url = info.get("release_page") or info.get("download_url") or ""
                    if url:
                        webbrowser.open(url)

            QTimer.singleShot(0, show_dialog)
        except Exception:
            pass

    t = threading.Thread(target=worker_simple, daemon=True)
    t.start()


class _ObjectHolder:
    """占位类，用于 QMetaObject.invokeMethod 跨线程调用（可选保留）。"""
    instance = None


__all__ = ["check_for_update", "notify_update_async", "CURRENT_VERSION"]
