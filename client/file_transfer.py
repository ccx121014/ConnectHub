"""
File Transfer Module for Online Collaboration Suite
Provides peer-to-peer file transfer using WebRTC DataChannel.
"""

import asyncio
import logging
import os
import uuid
import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Callable, Dict, Any, List
from pathlib import Path


# Add project root and client dir to path for module imports (cross-platform)
from pathlib import Path
_project_root = Path(__file__).parent.parent.resolve()
import sys as _sys
_sys.path.insert(0, str(_project_root))
_sys.path.insert(0, str(Path(__file__).parent))

from PyQt5.QtCore import QObject, pyqtSignal

from protocol.messages import Message, MessageType, create_message

logger = logging.getLogger(__name__)

CHUNK_SIZE = 64 * 1024  # 64KB chunks


class TransferState(Enum):
    """File transfer state"""
    PENDING = "pending"
    REQUESTED = "requested"
    ACCEPTED = "accepted"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    FAILED = "failed"


@dataclass
class TransferInfo:
    """Information about a file transfer"""
    file_id: str
    file_name: str
    file_size: int
    file_path: str
    target_user: str
    direction: str  # "send" or "receive"
    state: TransferState = TransferState.PENDING
    chunk_count: int = 0
    chunk_size: int = CHUNK_SIZE
    current_chunk: int = 0
    progress: float = 0.0
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    checksum: Optional[str] = None


class FileTransferManager(QObject):
    """
    Manages file transfers using WebRTC DataChannel.
    
    Signals:
        transfer_started: Emitted when a transfer begins (file_id)
        transfer_progress: Emitted with (file_id, progress, chunk_index, chunk_count)
        transfer_completed: Emitted when transfer completes (file_id)
        transfer_cancelled: Emitted when transfer is cancelled (file_id)
        transfer_rejected: Emitted when transfer is rejected (file_id)
        transfer_error: Emitted on error (file_id, error_message)
        incoming_request: Emitted when receiving a file request (file_id, file_name, file_size, sender)
    """

    transfer_started = pyqtSignal(str)
    transfer_progress = pyqtSignal(str, float, int, int)
    transfer_completed = pyqtSignal(str)
    transfer_cancelled = pyqtSignal(str)
    transfer_rejected = pyqtSignal(str)
    transfer_error = pyqtSignal(str, str)
    incoming_request = pyqtSignal(str, str, int, str)  # file_id, file_name, file_size, sender

    def __init__(self, parent=None):
        super().__init__(parent)
        self._transfers: Dict[str, TransferInfo] = {}
        self._data_channels: Dict[str, Any] = {}  # file_id -> DataChannel
        self._file_buffers: Dict[str, bytes] = {}  # file_id -> received data buffer
        self._peers: Dict[str, Any] = {}  # user_id -> WebRTCPeer
        self._webrtc_handler: Optional[Callable] = None
        self._username: Optional[str] = None
        self._download_dir: str = os.path.expanduser("~/Downloads")

    def set_username(self, username: str):
        """Set the current username."""
        self._username = username

    def set_webrtc_handler(self, handler: Callable):
        """Set the WebRTC handler for creating peer connections."""
        self._webrtc_handler = handler

    def set_download_dir(self, directory: str):
        """Set the download directory for incoming files."""
        self._download_dir = directory
        os.makedirs(self._download_dir, exist_ok=True)

    def _generate_file_id(self) -> str:
        """Generate a unique file ID."""
        return str(uuid.uuid4())

    def _calculate_checksum(self, data: bytes) -> str:
        """Calculate SHA256 checksum of data."""
        return hashlib.sha256(data).hexdigest()

    def _get_transfer(self, file_id: str) -> Optional[TransferInfo]:
        """Get transfer info by file ID."""
        return self._transfers.get(file_id)

    def send_file(self, file_path: str, target_user: str) -> str:
        """
        Initiate a file transfer to a target user.
        
        Args:
            file_path: Path to the file to send
            target_user: Username of the recipient
            
        Returns:
            file_id: Unique identifier for the transfer
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        if not self._username:
            raise RuntimeError("Username not set")

        file_id = self._generate_file_id()
        file_size = os.path.getsize(file_path)
        file_name = os.path.basename(file_path)
        chunk_count = (file_size + CHUNK_SIZE - 1) // CHUNK_SIZE

        transfer = TransferInfo(
            file_id=file_id,
            file_name=file_name,
            file_size=file_size,
            file_path=file_path,
            target_user=target_user,
            direction="send",
            state=TransferState.REQUESTED,
            chunk_count=chunk_count,
            chunk_size=CHUNK_SIZE
        )

        self._transfers[file_id] = transfer
        self._initiate_webrtc_connection(file_id, target_user)

        logger.info(f"File transfer initiated: {file_id} ({file_name} -> {target_user})")
        return file_id

    def _initiate_webrtc_connection(self, file_id: str, target_user: str):
        """Initiate WebRTC connection for file transfer."""
        transfer = self._get_transfer(file_id)
        if not transfer:
            return

        if self._webrtc_handler:
            peer = self._webrtc_handler(target_user, "file_transfer", file_id)
            self._peers[target_user] = peer
        else:
            logger.warning("No WebRTC handler set, using direct DataChannel")

    def accept_file(self, file_id: str) -> bool:
        """
        Accept an incoming file transfer.
        
        Args:
            file_id: Unique identifier for the transfer
            
        Returns:
            True if acceptance was successful
        """
        transfer = self._get_transfer(file_id)
        if not transfer:
            logger.error(f"Transfer not found: {file_id}")
            return False

        if transfer.state != TransferState.REQUESTED:
            logger.error(f"Transfer not in REQUESTED state: {file_id}")
            return False

        transfer.state = TransferState.ACCEPTED
        logger.info(f"File transfer accepted: {file_id}")
        return True

    def reject_file(self, file_id: str) -> bool:
        """
        Reject an incoming file transfer.
        
        Args:
            file_id: Unique identifier for the transfer
            
        Returns:
            True if rejection was successful
        """
        transfer = self._get_transfer(file_id)
        if not transfer:
            logger.error(f"Transfer not found: {file_id}")
            return False

        if transfer.state != TransferState.REQUESTED:
            logger.error(f"Transfer not in REQUESTED state: {file_id}")
            return False

        transfer.state = TransferState.REJECTED
        self.transfer_rejected.emit(file_id)
        self._cleanup_transfer(file_id)
        logger.info(f"File transfer rejected: {file_id}")
        return True

    def cancel_transfer(self, file_id: str) -> bool:
        """
        Cancel an ongoing or pending transfer.
        
        Args:
            file_id: Unique identifier for the transfer
            
        Returns:
            True if cancellation was successful
        """
        transfer = self._get_transfer(file_id)
        if not transfer:
            logger.error(f"Transfer not found: {file_id}")
            return False

        if transfer.state in [TransferState.COMPLETED, TransferState.CANCELLED, TransferState.REJECTED]:
            return False

        transfer.state = TransferState.CANCELLED
        self._cleanup_transfer(file_id)
        self.transfer_cancelled.emit(file_id)
        logger.info(f"File transfer cancelled: {file_id}")
        return True

    def get_progress(self, file_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the progress of a file transfer.
        
        Args:
            file_id: Unique identifier for the transfer
            
        Returns:
            Dictionary with progress information or None if not found
        """
        transfer = self._get_transfer(file_id)
        if not transfer:
            return None

        return {
            "file_id": file_id,
            "file_name": transfer.file_name,
            "file_size": transfer.file_size,
            "state": transfer.state.value,
            "progress": transfer.progress,
            "current_chunk": transfer.current_chunk,
            "chunk_count": transfer.chunk_count,
            "direction": transfer.direction,
            "target_user": transfer.target_user
        }

    def get_all_transfers(self) -> List[Dict[str, Any]]:
        """Get all file transfers."""
        return [self.get_progress(file_id) for file_id in self._transfers.keys()]

    def get_active_transfers(self) -> List[Dict[str, Any]]:
        """Get all active (in-progress) transfers."""
        active_states = [TransferState.REQUESTED, TransferState.ACCEPTED, TransferState.IN_PROGRESS]
        return [
            self.get_progress(file_id)
            for file_id, transfer in self._transfers.items()
            if transfer.state in active_states
        ]

    def handle_incoming_request(
        self,
        file_id: str,
        file_name: str,
        file_size: int,
        chunk_count: int,
        sender: str
    ):
        """Handle an incoming file transfer request."""
        if file_id in self._transfers:
            logger.warning(f"Duplicate file transfer request: {file_id}")
            return

        transfer = TransferInfo(
            file_id=file_id,
            file_name=file_name,
            file_size=file_size,
            file_path="",
            target_user=sender,
            direction="receive",
            state=TransferState.REQUESTED,
            chunk_count=chunk_count,
            chunk_size=CHUNK_SIZE
        )

        self._transfers[file_id] = transfer
        self.incoming_request.emit(file_id, file_name, file_size, sender)
        logger.info(f"Incoming file transfer request: {file_id} ({file_name} from {sender})")

    def handle_file_response(self, file_id: str, accepted: bool):
        """Handle response to a file transfer request."""
        transfer = self._get_transfer(file_id)
        if not transfer:
            logger.error(f"Transfer not found: {file_id}")
            return

        if accepted:
            transfer.state = TransferState.ACCEPTED
            self._start_sending(file_id)
        else:
            transfer.state = TransferState.REJECTED
            self.transfer_rejected.emit(file_id)
            self._cleanup_transfer(file_id)
            logger.info(f"File transfer rejected by recipient: {file_id}")

    def _start_sending(self, file_id: str):
        """Start sending file data."""
        transfer = self._get_transfer(file_id)
        if not transfer:
            return

        if transfer.direction != "send":
            logger.error("Cannot start sending: wrong direction")
            return

        transfer.state = TransferState.IN_PROGRESS
        self.transfer_started.emit(file_id)
        
        asyncio.create_task(self._send_chunks(file_id))

    async def _send_chunks(self, file_id: str):
        """Send file chunks via DataChannel."""
        transfer = self._get_transfer(file_id)
        if not transfer:
            return

        try:
            with open(transfer.file_path, "rb") as f:
                chunk_index = 0
                while True:
                    if transfer.state == TransferState.CANCELLED:
                        logger.info(f"Transfer cancelled, stopping: {file_id}")
                        return

                    chunk = f.read(transfer.chunk_size)
                    if not chunk:
                        break

                    checksum = self._calculate_checksum(chunk)

                    chunk_data = {
                        "file_id": file_id,
                        "chunk_index": chunk_index,
                        "data": chunk.hex(),
                        "checksum": checksum,
                        "is_last": len(chunk) < transfer.chunk_size
                    }

                    await self._send_chunk_via_datachannel(file_id, chunk_data)

                    transfer.current_chunk = chunk_index + 1
                    transfer.progress = (transfer.current_chunk / transfer.chunk_count) * 100

                    self.transfer_progress.emit(
                        file_id,
                        transfer.progress,
                        transfer.current_chunk,
                        transfer.chunk_count
                    )

                    chunk_index += 1

                transfer.state = TransferState.COMPLETED
                transfer.completed_at = time.time()
                self.transfer_completed.emit(file_id)
                logger.info(f"File transfer completed: {file_id}")

        except Exception as e:
            logger.error(f"Error sending file {file_id}: {e}")
            transfer.state = TransferState.FAILED
            transfer.error = str(e)
            self.transfer_error.emit(file_id, str(e))

        finally:
            self._cleanup_transfer(file_id)

    async def _send_chunk_via_datachannel(self, file_id: str, chunk_data: Dict):
        """Send a chunk via DataChannel."""
        dc = self._data_channels.get(file_id)
        if dc and dc.readyState == "open":
            try:
                message = {
                    "type": "file_chunk",
                    **chunk_data
                }
                dc.send(json.dumps(message))
            except Exception as e:
                logger.error(f"Error sending chunk via DataChannel: {e}")

    def handle_chunk_received(self, file_id: str, chunk_index: int, data: str, checksum: str, is_last: bool):
        """Handle a received file chunk."""
        import json
        
        transfer = self._get_transfer(file_id)
        if not transfer:
            logger.error(f"Transfer not found: {file_id}")
            return

        try:
            chunk_bytes = bytes.fromhex(data)
            
            expected_checksum = self._calculate_checksum(chunk_bytes)
            if checksum != expected_checksum:
                logger.error(f"Checksum mismatch for chunk {chunk_index} of {file_id}")
                self.transfer_error.emit(file_id, "Checksum mismatch")
                self.cancel_transfer(file_id)
                return

            if file_id not in self._file_buffers:
                self._file_buffers[file_id] = b''

            self._file_buffers[file_id] += chunk_bytes

            transfer.current_chunk = chunk_index + 1
            transfer.progress = (transfer.current_chunk / transfer.chunk_count) * 100

            self.transfer_progress.emit(
                file_id,
                transfer.progress,
                transfer.current_chunk,
                transfer.chunk_count
            )

            if is_last:
                self._complete_reception(file_id)

        except Exception as e:
            logger.error(f"Error handling chunk {chunk_index} of {file_id}: {e}")
            transfer.state = TransferState.FAILED
            transfer.error = str(e)
            self.transfer_error.emit(file_id, str(e))

    def _complete_reception(self, file_id: str):
        """Complete file reception and save the file."""
        transfer = self._get_transfer(file_id)
        if not transfer:
            return

        try:
            file_data = self._file_buffers.get(file_id, b'')
            
            os.makedirs(self._download_dir, exist_ok=True)
            output_path = os.path.join(self._download_dir, transfer.file_name)
            
            with open(output_path, "wb") as f:
                f.write(file_data)
            
            transfer.file_path = output_path
            transfer.state = TransferState.COMPLETED
            transfer.completed_at = time.time()
            
            self.transfer_completed.emit(file_id)
            logger.info(f"File received and saved: {output_path}")

        except Exception as e:
            logger.error(f"Error completing reception of {file_id}: {e}")
            transfer.state = TransferState.FAILED
            transfer.error = str(e)
            self.transfer_error.emit(file_id, str(e))

        finally:
            self._cleanup_transfer(file_id)

    def register_data_channel(self, file_id: str, data_channel: Any):
        """Register a DataChannel for a file transfer."""
        self._data_channels[file_id] = data_channel
        logger.info(f"DataChannel registered for transfer: {file_id}")

    def unregister_data_channel(self, file_id: str):
        """Unregister a DataChannel."""
        if file_id in self._data_channels:
            del self._data_channels[file_id]

    def _cleanup_transfer(self, file_id: str):
        """Clean up resources for a transfer."""
        if file_id in self._data_channels:
            del self._data_channels[file_id]
        if file_id in self._file_buffers:
            del self._file_buffers[file_id]
        if file_id in self._transfers:
            transfer = self._transfers[file_id]
            if transfer.state == TransferState.COMPLETED:
                pass
            elif transfer.state not in [TransferState.REJECTED, TransferState.CANCELLED]:
                transfer.state = TransferState.FAILED

    def get_transfer_info(self, file_id: str) -> Optional[TransferInfo]:
        """Get detailed transfer information."""
        return self._get_transfer(file_id)

    def clear_completed_transfers(self):
        """Clear all completed transfers from memory."""
        completed_ids = [
            file_id for file_id, transfer in self._transfers.items()
            if transfer.state == TransferState.COMPLETED
        ]
        for file_id in completed_ids:
            del self._transfers[file_id]
        logger.info(f"Cleared {len(completed_ids)} completed transfers")


import json
