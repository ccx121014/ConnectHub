"""
File Transfer Module for ConnectHub
纯 Python 实现：管理文件传输会话（发送/接收），使用 threading 与信号系统。
无 PyQt5，无 tkinter，无 UI 代码。
"""

import base64
import logging
import os
import sys
import threading
import uuid
from pathlib import Path
from typing import Dict, Optional

_project_root = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(_project_root))
sys.path.insert(0, str(Path(__file__).parent))

from protocol.signals import Signal, SignalBridge

logger = logging.getLogger(__name__)

CHUNK_SIZE = 32 * 1024  # 32KB


class FileTransferSession:
    """单个文件传输会话的状态管理。"""

    def __init__(
        self,
        file_id: str,
        target: str,
        direction: str,
        file_path: str = "",
        file_name: str = "",
        file_size: int = 0,
        sender: str = "",
        receiver: str = "",
    ):
        self.file_id = file_id
        self.target = target
        self.direction = direction  # "send" | "receive"
        self.file_path = file_path
        self.file_name = file_name or (os.path.basename(file_path) if file_path else "")
        self.file_size = file_size
        self.total_chunks = (file_size + CHUNK_SIZE - 1) // CHUNK_SIZE if file_size > 0 else 0
        self.received_chunks: Dict[int, bytes] = {}
        self.sent_chunks: int = 0
        self.status: str = "pending"  # pending | accepted | rejected | in_progress | complete | error
        self.sender = sender
        self.receiver = receiver
        self.error_message: str = ""


class FileTransferManager(SignalBridge):
    """文件传输管理器。

    对外信号：
      transfer_requested(file_id, sender, file_name, file_size)
      transfer_progress(file_id, sent_bytes, total_bytes)
      transfer_completed(file_id, final_path)
      transfer_error(file_id, error_msg)
      transfer_accepted(file_id)
      transfer_rejected(file_id)
    """

    def __init__(self, websocket_client=None, username: Optional[str] = None):
        super().__init__()
        self._ws_client = websocket_client
        self._username: Optional[str] = username
        self._sessions: Dict[str, FileTransferSession] = {}
        self._lock = threading.RLock()

        # 覆盖 SignalBridge 中默认信号：这里使用扩展信号集合
        self.transfer_requested = Signal(str, str, str, int)
        self.transfer_progress = Signal(str, int, int)
        self.transfer_completed = Signal(str, str)
        self.transfer_error = Signal(str, str)
        self.transfer_accepted = Signal(str)
        self.transfer_rejected = Signal(str)

    # -------- 基础配置 --------
    def set_websocket_client(self, ws_client):
        self._ws_client = ws_client

    def set_username(self, username: str):
        self._username = username

    # -------- Session 管理 --------
    def get_all_sessions(self) -> Dict[str, FileTransferSession]:
        with self._lock:
            return dict(self._sessions)

    def get_session(self, file_id: str) -> Optional[FileTransferSession]:
        with self._lock:
            return self._sessions.get(file_id)

    def _add_session(self, session: FileTransferSession):
        with self._lock:
            self._sessions[session.file_id] = session

    def _remove_session(self, file_id: str):
        with self._lock:
            self._sessions.pop(file_id, None)

    # -------- 发送方 --------
    def start_transfer(self, target: str, file_path: str) -> str:
        """发起一个文件发送请求。返回 file_id。"""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        file_id = str(uuid.uuid4())
        file_size = os.path.getsize(file_path)
        file_name = os.path.basename(file_path)
        total_chunks = (file_size + CHUNK_SIZE - 1) // CHUNK_SIZE

        session = FileTransferSession(
            file_id=file_id,
            target=target,
            direction="send",
            file_path=file_path,
            file_name=file_name,
            file_size=file_size,
            sender=self._username or "",
            receiver=target,
        )
        session.status = "pending"
        self._add_session(session)

        logger.info(f"[FileTransfer] start_transfer: {file_id} {file_name} ({file_size}B) -> {target}")

        if self._ws_client and hasattr(self._ws_client, "send_file_transfer_request"):
            self._ws_client.send_file_transfer_request(
                target,
                file_name,
                file_size,
                file_id,
                total_chunks,
                CHUNK_SIZE,
            )
        else:
            logger.warning("WebSocket client 未设置，无法发送请求消息")

        return file_id

    def _send_chunks_thread(self, file_id: str):
        """后台线程读取文件并分块发送。"""
        session = self.get_session(file_id)
        if session is None:
            return
        if session.direction != "send":
            return

        try:
            total_chunks = session.total_chunks
            file_size = session.file_size
            target = session.target

            with self._lock:
                session.status = "in_progress"

            with open(session.file_path, "rb") as f:
                chunk_index = 0
                while True:
                    current = None
                    with self._lock:
                        current = self._sessions.get(file_id)
                        if current is None or current.status in ("rejected", "error"):
                            logger.info(f"[FileTransfer] 会话终止，停止发送: {file_id}")
                            return

                    chunk = f.read(CHUNK_SIZE)
                    if not chunk:
                        break

                    encoded = base64.b64encode(chunk).decode("ascii")
                    if self._ws_client and hasattr(self._ws_client, "send_file_transfer_data"):
                        self._ws_client.send_file_transfer_data(
                            target, file_id, chunk_index, encoded
                        )

                    with self._lock:
                        current = self._sessions.get(file_id)
                        if current is None:
                            return
                        current.sent_chunks = chunk_index + 1

                    sent_bytes = min(file_size, (chunk_index + 1) * CHUNK_SIZE)
                    self.transfer_progress.emit(file_id, sent_bytes, file_size)
                    chunk_index += 1

            # 发送完成消息
            if self._ws_client and hasattr(self._ws_client, "send_file_transfer_complete"):
                self._ws_client.send_file_transfer_complete(target, file_id, total_chunks)

            session.status = "complete"
            self.transfer_completed.emit(file_id, session.file_path)
            logger.info(f"[FileTransfer] 发送完成: {file_id}")
        except Exception as exc:
            logger.exception(f"[FileTransfer] 发送失败 {file_id}: {exc}")
            session.status = "error"
            session.error_message = str(exc)
            self.transfer_error.emit(file_id, str(exc))

    # -------- 接收方 --------
    def handle_incoming_request(self, msg_obj):
        """处理接收到的文件传输请求消息。"""
        payload = getattr(msg_obj, "payload", None) or {}
        # 兼容：某些调用者也可能把字段放在 Message 的上层
        file_id = payload.get("file_id") or getattr(msg_obj, "file_id", None)
        file_name = payload.get("file_name") or getattr(msg_obj, "file_name", "")
        file_size = payload.get("file_size", 0) or getattr(msg_obj, "file_size", 0)
        sender = payload.get("sender") or getattr(msg_obj, "sender", "") or (
            msg_obj.sender if hasattr(msg_obj, "sender") else ""
        )

        if not file_id:
            logger.warning("收到无 file_id 的文件请求，忽略")
            return

        with self._lock:
            if file_id in self._sessions:
                logger.warning(f"重复的文件请求: {file_id}")
                return

        session = FileTransferSession(
            file_id=file_id,
            target=sender,
            direction="receive",
            file_path="",
            file_name=file_name,
            file_size=file_size,
            sender=sender,
            receiver=self._username or "",
        )
        session.status = "pending"
        self._add_session(session)

        logger.info(f"[FileTransfer] 收到请求: {file_id} {file_name} ({file_size}B) from {sender}")
        self.transfer_requested.emit(file_id, sender, file_name, file_size)

    def accept_transfer(self, file_id: str, save_path: str):
        """接受一个传入的文件传输，并开始准备接收数据。"""
        session = self.get_session(file_id)
        if session is None:
            logger.error(f"未找到会话: {file_id}")
            self.transfer_error.emit(file_id, "会话不存在")
            return

        if session.direction != "receive":
            logger.error(f"accept_transfer 只能用于接收方向: {file_id}")
            return

        session.file_path = save_path
        session.status = "accepted"

        # 通知对方已接受
        if self._ws_client and hasattr(self._ws_client, "send_file_transfer_response"):
            self._ws_client.send_file_transfer_response(session.target, file_id, True)

        logger.info(f"[FileTransfer] 接受文件: {file_id} -> {save_path}")
        self.transfer_accepted.emit(file_id)

    def reject_transfer(self, file_id: str):
        session = self.get_session(file_id)
        if session is None:
            logger.error(f"未找到会话: {file_id}")
            return

        session.status = "rejected"
        if session.direction == "receive" and self._ws_client and hasattr(
            self._ws_client, "send_file_transfer_response"
        ):
            self._ws_client.send_file_transfer_response(session.target, file_id, False)

        logger.info(f"[FileTransfer] 拒绝文件: {file_id}")
        self.transfer_rejected.emit(file_id)
        self._remove_session(file_id)

    def cancel_transfer(self, file_id: str):
        session = self.get_session(file_id)
        if session is None:
            return
        session.status = "error"
        session.error_message = "cancelled"
        self.transfer_error.emit(file_id, "cancelled")
        self._remove_session(file_id)
        logger.info(f"[FileTransfer] 取消传输: {file_id}")

    def handle_incoming_data(self, msg_obj):
        """处理接收到的文件数据消息（base64 编码的 chunk）。"""
        payload = getattr(msg_obj, "payload", None) or {}
        file_id = payload.get("file_id") or getattr(msg_obj, "file_id", None)
        chunk_index = payload.get("chunk_index") if payload is not None else None
        if chunk_index is None:
            chunk_index = getattr(msg_obj, "chunk_index", None)
        data_b64 = payload.get("data") if payload is not None else None
        if data_b64 is None:
            data_b64 = getattr(msg_obj, "data", "")

        if file_id is None:
            return

        session = self.get_session(file_id)
        if session is None:
            logger.warning(f"收到未知会话的数据 chunk: {file_id}")
            return
        if session.status == "rejected":
            return

        try:
            chunk_bytes = base64.b64decode(data_b64)
        except Exception as exc:
            logger.error(f"base64 解码失败: {file_id} chunk {chunk_index}: {exc}")
            self.transfer_error.emit(file_id, f"base64 解码失败: {exc}")
            return

        session.received_chunks[int(chunk_index)] = chunk_bytes
        received_count = len(session.received_chunks)
        received_bytes = sum(len(b) for b in session.received_chunks.values())

        session.status = "in_progress"
        self.transfer_progress.emit(file_id, received_bytes, session.file_size)

        # 如果所有 chunk 都到齐，提前完成写盘
        if session.total_chunks > 0 and received_count >= session.total_chunks:
            self._finalize_received(file_id)

    def handle_incoming_complete(self, msg_obj):
        """处理接收到的文件传输完成消息。"""
        payload = getattr(msg_obj, "payload", None) or {}
        file_id = payload.get("file_id") or getattr(msg_obj, "file_id", None)
        if file_id is None:
            return

        self._finalize_received(file_id)

    def _finalize_received(self, file_id: str):
        session = self.get_session(file_id)
        if session is None:
            return
        if session.direction != "receive":
            return

        try:
            save_path = session.file_path
            if not save_path:
                save_path = os.path.join(
                    os.path.expanduser("~"), "Downloads", session.file_name or file_id
                )

            # 确保目录存在
            save_dir = os.path.dirname(save_path)
            if save_dir:
                os.makedirs(save_dir, exist_ok=True)

            # 按 chunk_index 顺序写入
            with open(save_path, "wb") as f:
                for idx in sorted(session.received_chunks.keys()):
                    f.write(session.received_chunks[idx])

            session.status = "complete"
            session.file_path = save_path
            self.transfer_completed.emit(file_id, save_path)
            logger.info(f"[FileTransfer] 接收完成: {file_id} -> {save_path}")
        except Exception as exc:
            logger.exception(f"[FileTransfer] 写文件失败 {file_id}: {exc}")
            session.status = "error"
            session.error_message = str(exc)
            self.transfer_error.emit(file_id, str(exc))

    # -------- 作为发送方：处理响应消息（对方接受/拒绝） --------
    def handle_response(self, msg_obj):
        payload = getattr(msg_obj, "payload", None) or {}
        file_id = payload.get("file_id") or getattr(msg_obj, "file_id", None)
        accepted = payload.get("accepted") if payload is not None else None
        if accepted is None:
            accepted = getattr(msg_obj, "accepted", False)

        if file_id is None:
            return

        session = self.get_session(file_id)
        if session is None or session.direction != "send":
            return

        if accepted:
            session.status = "accepted"
            self.transfer_accepted.emit(file_id)
            t = threading.Thread(
                target=self._send_chunks_thread, args=(file_id,), daemon=True
            )
            t.start()
        else:
            session.status = "rejected"
            self.transfer_rejected.emit(file_id)
            logger.info(f"[FileTransfer] 对方拒绝了文件: {file_id}")
            self._remove_session(file_id)


__all__ = ["FileTransferSession", "FileTransferManager", "CHUNK_SIZE"]
