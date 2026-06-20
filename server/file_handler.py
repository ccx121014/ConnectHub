"""
Server-side File Handler for Online Collaboration Suite
Provides relay functionality for file transfers when P2P is not available.
Handles chunked file relay, metadata exchange, and transfer state management.
"""

import asyncio
import logging
import os
import time
import uuid
import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional, Any, List, Callable
from pathlib import Path

import sys
import os
from pathlib import Path

# Add project root to path for module imports
_project_root = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(_project_root))
sys.path.insert(0, str(Path(__file__).parent))

from protocol.messages import Message, MessageType, create_message

logger = logging.getLogger(__name__)

CHUNK_SIZE = 64 * 1024  # 64KB chunks
MAX_FILE_SIZE = 100 * 1024 * 1024 * 1024  # 100GB max file size
RELAY_TIMEOUT = 300  # 5 minutes timeout for relay transfers
STORAGE_PATH = "data/files"


class RelayState(Enum):
    """Relay transfer state"""
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass
class RelayTransfer:
    """Information about a relay file transfer"""
    transfer_id: str
    file_id: str
    file_name: str
    file_size: int
    chunk_count: int
    chunk_size: int = CHUNK_SIZE
    sender: str
    receiver: str
    state: RelayState = RelayState.PENDING
    current_chunk: int = 0
    progress: float = 0.0
    file_path: Optional[str] = None
    temp_path: Optional[str] = None
    received_chunks: Dict[int, bytes] = field(default_factory=dict)
    checksum: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    error: Optional[str] = None
    message_id: Optional[str] = None


@dataclass
class ChunkMetadata:
    """Metadata for a file chunk"""
    transfer_id: str
    file_id: str
    chunk_index: int
    chunk_size: int
    is_last: bool
    checksum: str


class FileHandler:
    """
    Handles server-side file transfer relay operations.
    
    When WebRTC DataChannel is not available or P2P connection fails,
    this handler manages chunked file relay through the server.
    """

    def __init__(self, storage_path: str = STORAGE_PATH):
        """
        Initialize the file handler.
        
        Args:
            storage_path: Base path for storing temporary relay files
        """
        self._storage_path = storage_path
        self._transfers: Dict[str, RelayTransfer] = {}
        self._transfer_by_file_id: Dict[str, str] = {}  # file_id -> transfer_id
        self._user_transfers: Dict[str, List[str]] = {}  # user -> [transfer_ids]
        self._message_handler: Optional[Callable] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        
        os.makedirs(self._storage_path, exist_ok=True)
        logger.info(f"FileHandler initialized with storage: {self._storage_path}")

    def set_message_handler(self, handler: Callable):
        """
        Set the message handler for sending messages to clients.
        
        Args:
            handler: Async function that takes (user, message) and sends the message
        """
        self._message_handler = handler

    async def start(self):
        """Start the file handler background tasks."""
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("FileHandler started")

    async def stop(self):
        """Stop the file handler and cleanup resources."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        async with self._lock:
            for transfer in self._transfers.values():
                await self._cleanup_transfer_files(transfer)

        logger.info("FileHandler stopped")

    async def _cleanup_loop(self):
        """Background task to cleanup stale transfers."""
        while True:
            try:
                await asyncio.sleep(60)
                await self._cleanup_stale_transfers()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")

    async def _cleanup_stale_transfers(self):
        """Cleanup transfers that have timed out or are stale."""
        current_time = time.time()
        stale_ids = []

        async with self._lock:
            for transfer_id, transfer in self._transfers.items():
                if transfer.state in [RelayState.PENDING, RelayState.ACTIVE]:
                    if current_time - transfer.created_at > RELAY_TIMEOUT:
                        stale_ids.append(transfer_id)

        for transfer_id in stale_ids:
            logger.warning(f"Transfer timed out: {transfer_id}")
            await self.cancel_transfer(transfer_id, "Transfer timed out")

    async def _generate_transfer_id(self) -> str:
        """Generate a unique transfer ID."""
        return str(uuid.uuid4())

    def _generate_temp_path(self, transfer_id: str, file_name: str) -> str:
        """Generate a temporary file path for the transfer."""
        safe_name = "".join(c for c in file_name if c.isalnum() or c in "._-")
        return os.path.join(self._storage_path, f"{transfer_id}_{safe_name}")

    async def initiate_relay(
        self,
        file_id: str,
        file_name: str,
        file_size: int,
        sender: str,
        receiver: str,
        chunk_count: int,
        message_id: Optional[str] = None
    ) -> Optional[str]:
        """
        Initiate a relay transfer.
        
        Args:
            file_id: Unique file identifier
            file_name: Name of the file
            file_size: Size of the file in bytes
            sender: Username of the sender
            receiver: Username of the receiver
            chunk_count: Number of chunks the file is divided into
            message_id: Optional message ID for tracking
            
        Returns:
            transfer_id: Unique transfer identifier, or None if failed
        """
        if file_size > MAX_FILE_SIZE:
            logger.error(f"File too large: {file_size} bytes")
            return None

        if file_id in self._transfer_by_file_id:
            logger.warning(f"Duplicate file_id: {file_id}")
            return self._transfer_by_file_id[file_id]

        transfer_id = await self._generate_transfer_id()
        
        transfer = RelayTransfer(
            transfer_id=transfer_id,
            file_id=file_id,
            file_name=file_name,
            file_size=file_size,
            chunk_count=chunk_count,
            sender=sender,
            receiver=receiver,
            state=RelayState.PENDING,
            temp_path=self._generate_temp_path(transfer_id, file_name),
            message_id=message_id
        )

        async with self._lock:
            self._transfers[transfer_id] = transfer
            self._transfer_by_file_id[file_id] = transfer_id

            if sender not in self._user_transfers:
                self._user_transfers[sender] = []
            self._user_transfers[sender].append(transfer_id)

            if receiver not in self._user_transfers:
                self._user_transfers[receiver] = []
            self._user_transfers[receiver].append(transfer_id)

        logger.info(f"Relay transfer initiated: {transfer_id} ({file_name}, {file_size} bytes)")
        return transfer_id

    async def accept_relay(self, file_id: str, receiver: str) -> bool:
        """
        Accept a relay transfer.
        
        Args:
            file_id: Unique file identifier
            receiver: Username of the receiver
            
        Returns:
            True if acceptance was successful
        """
        if file_id not in self._transfer_by_file_id:
            logger.error(f"Transfer not found: {file_id}")
            return False

        transfer_id = self._transfer_by_file_id[file_id]
        
        async with self._lock:
            if transfer_id not in self._transfers:
                return False
                
            transfer = self._transfers[transfer_id]
            
            if transfer.receiver != receiver:
                logger.error(f"Receiver mismatch: {receiver} vs {transfer.receiver}")
                return False
                
            if transfer.state != RelayState.PENDING:
                logger.error(f"Transfer not in PENDING state: {transfer_id}")
                return False

            transfer.state = RelayState.ACTIVE

        logger.info(f"Relay transfer accepted: {transfer_id}")
        
        await self._notify_sender(transfer, "accepted")
        return True

    async def reject_relay(self, file_id: str, receiver: str) -> bool:
        """
        Reject a relay transfer.
        
        Args:
            file_id: Unique file identifier
            receiver: Username of the receiver
            
        Returns:
            True if rejection was successful
        """
        if file_id not in self._transfer_by_file_id:
            logger.error(f"Transfer not found: {file_id}")
            return False

        transfer_id = self._transfer_by_file_id[file_id]
        
        async with self._lock:
            if transfer_id not in self._transfers:
                return False
                
            transfer = self._transfers[transfer_id]
            
            if transfer.receiver != receiver:
                logger.error(f"Receiver mismatch: {receiver} vs {transfer.receiver}")
                return False

            transfer.state = RelayState.FAILED
            transfer.error = "Rejected by receiver"

        logger.info(f"Relay transfer rejected: {transfer_id}")
        
        await self._notify_sender(transfer, "rejected")
        await self._cleanup_transfer(transfer)
        return True

    async def cancel_transfer(self, transfer_id: str, reason: str = "") -> bool:
        """
        Cancel a relay transfer.
        
        Args:
            transfer_id: Unique transfer identifier
            reason: Reason for cancellation
            
        Returns:
            True if cancellation was successful
        """
        async with self._lock:
            if transfer_id not in self._transfers:
                return False

            transfer = self._transfers[transfer_id]
            transfer.state = RelayState.CANCELLED
            transfer.error = reason

        logger.info(f"Relay transfer cancelled: {transfer_id} ({reason})")
        
        await self._notify_parties(transfer, "cancelled", reason)
        await self._cleanup_transfer(transfer)
        return True

    async def relay_chunk(
        self,
        file_id: str,
        chunk_index: int,
        chunk_data: str,  # hex encoded
        checksum: str,
        is_last: bool,
        sender: str
    ) -> bool:
        """
        Relay a file chunk from sender to server.
        
        Args:
            file_id: Unique file identifier
            chunk_index: Index of the chunk
            chunk_data: Hex-encoded chunk data
            checksum: SHA256 checksum of the chunk
            is_last: Whether this is the last chunk
            sender: Username of the sender
            
        Returns:
            True if chunk was received successfully
        """
        if file_id not in self._transfer_by_file_id:
            logger.error(f"Transfer not found: {file_id}")
            return False

        transfer_id = self._transfer_by_file_id[file_id]
        
        async with self._lock:
            if transfer_id not in self._transfers:
                return False

            transfer = self._transfers[transfer_id]

            if transfer.sender != sender:
                logger.error(f"Sender mismatch: {sender} vs {transfer.sender}")
                return False

            if transfer.state not in [RelayState.PENDING, RelayState.ACTIVE]:
                logger.error(f"Transfer not active: {transfer_id}")
                return False

            try:
                chunk_bytes = bytes.fromhex(chunk_data)
            except ValueError:
                logger.error(f"Invalid hex data for chunk {chunk_index}")
                return False

            expected_checksum = hashlib.sha256(chunk_bytes).hexdigest()
            if checksum != expected_checksum:
                logger.error(f"Checksum mismatch for chunk {chunk_index}")
                transfer.state = RelayState.FAILED
                transfer.error = "Checksum mismatch"
                return False

            transfer.received_chunks[chunk_index] = chunk_bytes
            transfer.current_chunk = chunk_index + 1

            with open(transfer.temp_path, "ab") as f:
                f.write(chunk_bytes)

            transfer.progress = (transfer.current_chunk / transfer.chunk_count) * 100

        await self._notify_receiver_progress(transfer, chunk_index)
        
        if is_last:
            await self._complete_transfer(transfer_id)

        return True

    async def request_chunk_from_sender(
        self,
        file_id: str,
        chunk_index: int,
        receiver: str
    ) -> bool:
        """
        Request a specific chunk from the sender (for resume support).
        
        Args:
            file_id: Unique file identifier
            chunk_index: Index of the requested chunk
            receiver: Username of the receiver
            
        Returns:
            True if request was sent successfully
        """
        if file_id not in self._transfer_by_file_id:
            return False

        transfer_id = self._transfer_by_file_id[file_id]
        
        async with self._lock:
            if transfer_id not in self._transfers:
                return False

            transfer = self._transfers[transfer_id]

            if transfer.receiver != receiver:
                return False

        if self._message_handler:
            message = create_message(
                MessageType.FILE_TRANSFER_REQUEST,
                sender="server",
                target=transfer.sender,
                file_id=file_id,
                chunk_index=chunk_index,
                resume_request=True,
                timestamp=time.time()
            )
            await self._message_handler(transfer.sender, message.to_json())

        return True

    async def get_transfer_status(self, file_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the status of a relay transfer.
        
        Args:
            file_id: Unique file identifier
            
        Returns:
            Dictionary with transfer status or None if not found
        """
        if file_id not in self._transfer_by_file_id:
            return None

        transfer_id = self._transfer_by_file_id[file_id]
        
        async with self._lock:
            if transfer_id not in self._transfers:
                return None

            transfer = self._transfers[transfer_id]

            return {
                "transfer_id": transfer_id,
                "file_id": transfer.file_id,
                "file_name": transfer.file_name,
                "file_size": transfer.file_size,
                "state": transfer.state.value,
                "progress": transfer.progress,
                "current_chunk": transfer.current_chunk,
                "chunk_count": transfer.chunk_count,
                "sender": transfer.sender,
                "receiver": transfer.receiver,
                "error": transfer.error
            }

    async def get_user_transfers(self, username: str) -> List[Dict[str, Any]]:
        """
        Get all transfers for a user.
        
        Args:
            username: Username to get transfers for
            
        Returns:
            List of transfer status dictionaries
        """
        async with self._lock:
            transfer_ids = self._user_transfers.get(username, [])

        transfers = []
        for transfer_id in transfer_ids:
            async with self._lock:
                if transfer_id in self._transfers:
                    transfer = self._transfers[transfer_id]
                    transfers.append({
                        "transfer_id": transfer_id,
                        "file_id": transfer.file_id,
                        "file_name": transfer.file_name,
                        "file_size": transfer.file_size,
                        "state": transfer.state.value,
                        "progress": transfer.progress,
                        "direction": "send" if transfer.sender == username else "receive",
                        "peer": transfer.receiver if transfer.sender == username else transfer.sender
                    })

        return transfers

    async def _complete_transfer(self, transfer_id: str):
        """Complete a relay transfer and notify parties."""
        async with self._lock:
            if transfer_id not in self._transfers:
                return

            transfer = self._transfers[transfer_id]
            transfer.state = RelayState.COMPLETED
            transfer.completed_at = time.time()

        logger.info(f"Relay transfer completed: {transfer_id}")
        
        await self._notify_parties(transfer, "completed")

    async def _notify_sender(self, transfer: RelayTransfer, status: str):
        """Notify sender about transfer status change."""
        if not self._message_handler:
            return

        message = create_message(
            MessageType.FILE_TRANSFER_RESPONSE,
            sender="server",
            target=transfer.sender,
            file_id=transfer.file_id,
            status=status,
            timestamp=time.time()
        )
        await self._message_handler(transfer.sender, message.to_json())

    async def _notify_receiver(self, transfer: RelayTransfer, status: str):
        """Notify receiver about transfer status change."""
        if not self._message_handler:
            return

        message = create_message(
            MessageType.FILE_TRANSFER_REQUEST,
            sender="server",
            target=transfer.receiver,
            file_id=transfer.file_id,
            file_name=transfer.file_name,
            file_size=transfer.file_size,
            status=status,
            timestamp=time.time()
        )
        await self._message_handler(transfer.receiver, message.to_json())

    async def _notify_receiver_progress(self, transfer: RelayTransfer, chunk_index: int):
        """Notify receiver about chunk received (for progress tracking)."""
        if not self._message_handler:
            return

        message = create_message(
            MessageType.FILE_TRANSFER_PROGRESS,
            sender="server",
            target=transfer.receiver,
            file_id=transfer.file_id,
            chunk_index=chunk_index,
            progress=transfer.progress,
            timestamp=time.time()
        )
        await self._message_handler(transfer.receiver, message.to_json())

    async def _notify_parties(self, transfer: RelayTransfer, status: str, error: str = ""):
        """Notify both parties about transfer status change."""
        await self._notify_sender(transfer, status)
        await self._notify_receiver(transfer, status)

        if error and self._message_handler:
            message = create_message(
                MessageType.ERROR,
                sender="server",
                error=error,
                timestamp=time.time()
            )
            await self._message_handler(transfer.sender, message.to_json())
            await self._message_handler(transfer.receiver, message.to_json())

    async def _cleanup_transfer(self, transfer: RelayTransfer):
        """Cleanup files and resources for a transfer."""
        if transfer.temp_path and os.path.exists(transfer.temp_path):
            try:
                os.remove(transfer.temp_path)
                logger.debug(f"Removed temp file: {transfer.temp_path}")
            except Exception as e:
                logger.error(f"Error removing temp file: {e}")

        async with self._lock:
            if transfer.file_id in self._transfer_by_file_id:
                del self._transfer_by_file_id[transfer.file_id]

            if transfer.transfer_id in self._transfers:
                del self._transfers[transfer.transfer_id]

            for user, transfers in self._user_transfers.items():
                if transfer.transfer_id in transfers:
                    transfers.remove(transfer.transfer_id)

        logger.info(f"Cleaned up transfer: {transfer.transfer_id}")

    async def get_relay_info(self, file_id: str) -> Optional[Dict[str, Any]]:
        """
        Get relay information for a file (needed for P2P fallback).
        
        Args:
            file_id: Unique file identifier
            
        Returns:
            Dictionary with relay info or None if not found
        """
        if file_id not in self._transfer_by_file_id:
            return None

        transfer_id = self._transfer_by_file_id[file_id]
        
        async with self._lock:
            if transfer_id not in self._transfers:
                return None

            transfer = self._transfers[transfer_id]

            return {
                "transfer_id": transfer_id,
                "file_id": transfer.file_id,
                "file_name": transfer.file_name,
                "file_size": transfer.file_size,
                "chunk_count": transfer.chunk_count,
                "current_chunk": transfer.current_chunk,
                "state": transfer.state.value,
                "sender": transfer.sender,
                "receiver": transfer.receiver,
                "temp_path": transfer.temp_path
            }

    async def request_file_for_relay(
        self,
        file_id: str,
        sender: str,
        receiver: str
    ) -> Optional[bytes]:
        """
        Request file data for relay from sender via server relay.
        
        Args:
            file_id: Unique file identifier
            sender: Username of the sender
            receiver: Username of the receiver
            
        Returns:
            File data as bytes, or None if not available
        """
        if file_id not in self._transfer_by_file_id:
            return None

        transfer_id = self._transfer_by_file_id[file_id]
        
        async with self._lock:
            if transfer_id not in self._transfers:
                return None

            transfer = self._transfers[transfer_id]

            if transfer.sender != sender or transfer.receiver != receiver:
                return None

            if transfer.state != RelayState.COMPLETED:
                return None

            if not transfer.temp_path or not os.path.exists(transfer.temp_path):
                return None

        try:
            with open(transfer.temp_path, "rb") as f:
                return f.read()
        except Exception as e:
            logger.error(f"Error reading relay file: {e}")
            return None

    async def deliver_relay_to_receiver(self, file_id: str) -> bool:
        """
        Deliver completed relay file to receiver.
        
        Args:
            file_id: Unique file identifier
            
        Returns:
            True if delivery was initiated successfully
        """
        if file_id not in self._transfer_by_file_id:
            return False

        transfer_id = self._transfer_by_file_id[file_id]
        
        async with self._lock:
            if transfer_id not in self._transfers:
                return False

            transfer = self._transfers[transfer_id]

            if transfer.state != RelayState.COMPLETED:
                return False

        if self._message_handler:
            message = create_message(
                MessageType.FILE_TRANSFER_COMPLETE,
                sender="server",
                target=transfer.receiver,
                file_id=transfer.file_id,
                file_name=transfer.file_name,
                file_size=transfer.file_size,
                timestamp=time.time()
            )
            await self._message_handler(transfer.receiver, message.to_json())

        return True
