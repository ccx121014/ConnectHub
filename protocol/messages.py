"""
Communication Protocol Definitions
Defines all message types and JSON structures for the collaboration suite.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
import json


class MessageType(Enum):
    """Message type enumeration"""
    # Authentication
    AUTH_REQUEST = "auth_request"
    AUTH_RESPONSE = "auth_response"
    AUTH_LOGOUT = "auth_logout"

    # User Management
    USER_STATUS_UPDATE = "user_status_update"
    USER_LIST_REQUEST = "user_list_request"
    USER_LIST_RESPONSE = "user_list_response"
    CONTACT_LIST_REQUEST = "contact_list_request"
    CONTACT_LIST_RESPONSE = "contact_list_response"

    # Chat
    CHAT_MESSAGE = "chat_message"
    CHAT_HISTORY_REQUEST = "chat_history_request"
    CHAT_HISTORY_RESPONSE = "chat_history_response"

    # Group Chat
    GROUP_CREATE = "group_create"
    GROUP_CREATE_RESPONSE = "group_create_response"
    GROUP_JOIN = "group_join"
    GROUP_LEAVE = "group_leave"
    GROUP_MESSAGE = "group_message"
    GROUP_MEMBER_UPDATE = "group_member_update"

    # File Transfer
    FILE_TRANSFER_REQUEST = "file_transfer_request"
    FILE_TRANSFER_RESPONSE = "file_transfer_response"
    FILE_TRANSFER_DATA = "file_transfer_data"
    FILE_TRANSFER_COMPLETE = "file_transfer_complete"
    FILE_TRANSFER_CANCEL = "file_transfer_cancel"
    FILE_TRANSFER_PROGRESS = "file_transfer_progress"

    # Remote Desktop
    DESKTOP_SHARE_REQUEST = "desktop_share_request"
    DESKTOP_SHARE_RESPONSE = "desktop_share_response"
    DESKTOP_STOP = "desktop_stop"
    DESKTOP_CONTROL_REQUEST = "desktop_control_request"
    DESKTOP_CONTROL_RESPONSE = "desktop_control_response"
    DESKTOP_MOUSE_MOVE = "desktop_mouse_move"
    DESKTOP_MOUSE_CLICK = "desktop_mouse_click"
    DESKTOP_MOUSE_RELEASE = "desktop_mouse_release"
    DESKTOP_KEYBOARD = "desktop_keyboard"
    DESKTOP_FRAME = "desktop_frame"

    # WebRTC Signaling
    WEBRTC_OFFER = "webrtc_offer"
    WEBRTC_ANSWER = "webrtc_answer"
    WEBRTC_ICE_CANDIDATE = "webrtc_ice_candidate"

    # System
    HEARTBEAT = "heartbeat"
    HEARTBEAT_ACK = "heartbeat_ack"
    ERROR = "error"


@dataclass
class Message:
    """Base message structure"""
    type: MessageType
    sender: str
    target: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: Optional[float] = None
    message_id: Optional[str] = None

    def to_json(self) -> str:
        """Convert message to JSON string"""
        data = {
            "type": self.type.value,
            "sender": self.sender,
            "target": self.target,
            "payload": self.payload,
            "timestamp": self.timestamp,
            "message_id": self.message_id
        }
        return json.dumps(data)

    @classmethod
    def from_json(cls, json_str: str) -> "Message":
        """Create message from JSON string"""
        data = json.loads(json_str)
        return cls(
            type=MessageType(data["type"]),
            sender=data["sender"],
            target=data.get("target"),
            payload=data.get("payload", {}),
            timestamp=data.get("timestamp"),
            message_id=data.get("message_id")
        )


@dataclass
class AuthPayload:
    """Authentication payload"""
    username: str
    password: str = ""


@dataclass
class ChatMessagePayload:
    """Chat message payload"""
    content: str
    message_type: str = "text"  # text, image, file


@dataclass
class FileTransferRequestPayload:
    """File transfer request payload"""
    file_name: str
    file_size: int
    file_id: str
    chunk_count: int
    chunk_size: int


@dataclass
class FileTransferDataPayload:
    """File transfer data payload"""
    file_id: str
    chunk_index: int
    data: bytes


@dataclass
class DesktopShareRequestPayload:
    """Desktop share request payload"""
    share_type: str  # "view" or "control"
    screen_info: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WebRTCOfferPayload:
    """WebRTC offer payload"""
    target_user: str
    offer: Dict[str, Any]
    session_type: str  # "file_transfer" or "desktop"


@dataclass
class WebRTCAnswerPayload:
    """WebRTC answer payload"""
    target_user: str
    answer: Dict[str, Any]


@dataclass
class ICECandidatePayload:
    """ICE candidate payload"""
    target_user: str
    candidate: Dict[str, Any]


def create_message(msg_type: MessageType, sender: str, target: str = None, **kwargs) -> Message:
    """Helper to create a message with common fields"""
    import time
    import uuid

    return Message(
        type=msg_type,
        sender=sender,
        target=target,
        payload=kwargs,
        timestamp=time.time(),
        message_id=str(uuid.uuid4())
    )


def parse_message(json_str: str) -> Message:
    """Parse a JSON string into a Message"""
    return Message.from_json(json_str)
