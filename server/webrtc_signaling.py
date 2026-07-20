"""
WebRTC Signaling Server Module
Handles WebRTC signaling for peer-to-peer connections.
"""

import asyncio

import time
from typing import Dict, Optional, Callable, Any
from dataclasses import dataclass, field
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class SignalingState(Enum):
    """WebRTC connection state"""
    IDLE = "idle"
    OFFER_SENT = "offer_sent"
    OFFER_RECEIVED = "offer_received"
    ANSWER_SENT = "answer_sent"
    ANSWER_RECEIVED = "answer_received"
    CONNECTED = "connected"
    FAILED = "failed"


@dataclass
class SignalingSession:
    """WebRTC signaling session"""
    session_id: str
    caller: str
    callee: str
    state: SignalingState = SignalingState.IDLE
    session_type: str = "file_transfer"  # "file_transfer" or "desktop"
    created_at: float = field(default_factory=time.time)
    offer: Optional[Dict] = None
    answer: Optional[Dict] = None
    ice_candidates: list = field(default_factory=list)


class SignalingServer:
    """Manages WebRTC signaling between users"""

    def __init__(self, user_manager):
        """Initialize signaling server with user manager"""
        self.user_manager = user_manager
        self._sessions: Dict[str, SignalingSession] = {}
        self._user_sessions: Dict[str, Dict[str, SignalingSession]] = {}  # user -> {session_id -> session}
        self._locks: Dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()
        self._message_handler: Optional[Callable] = None

    def set_message_handler(self, handler: Callable):
        """Set the message handler for relaying signals"""
        self._message_handler = handler

    async def _get_session_lock(self, session_id: str) -> asyncio.Lock:
        """Get or create a lock for a specific session"""
        async with self._global_lock:
            if session_id not in self._locks:
                self._locks[session_id] = asyncio.Lock()
            return self._locks[session_id]

    async def _get_user_lock(self, username: str) -> asyncio.Lock:
        """Get or create a lock for a specific user"""
        async with self._global_lock:
            if username not in self._locks:
                self._locks[username] = asyncio.Lock()
            return self._locks[username]

    def _generate_session_id(self, user1: str, user2: str) -> str:
        """Generate consistent session ID for two users"""
        users = sorted([user1, user2])
        return f"{users[0]}_{users[1]}_{int(time.time() * 1000)}"

    async def _create_session(
        self,
        caller: str,
        callee: str,
        session_type: str
    ) -> SignalingSession:
        """Create a new signaling session"""
        session_id = self._generate_session_id(caller, callee)

        session = SignalingSession(
            session_id=session_id,
            caller=caller,
            callee=callee,
            session_type=session_type
        )

        async with self._global_lock:
            self._sessions[session_id] = session

            if caller not in self._user_sessions:
                self._user_sessions[caller] = {}
            self._user_sessions[caller][session_id] = session

            if callee not in self._user_sessions:
                self._user_sessions[callee] = {}
            self._user_sessions[callee][session_id] = session

        return session

    async def handle_offer(
        self,
        caller: str,
        callee: str,
        offer: Dict[str, Any],
        session_type: str = "file_transfer"
    ) -> Optional[Dict]:
        """
        Handle WebRTC offer from a caller.
        Returns the offer message to be sent to the callee.
        """
        session = await self._create_session(caller, callee, session_type)

        lock = await self._get_session_lock(session.session_id)
        async with lock:
            session.offer = offer
            session.state = SignalingState.OFFER_SENT

        relay_message = {
            "type": "webrtc_offer",
            "sender": caller,
            "target": callee,
            "payload": {
                "session_id": session.session_id,
                "offer": offer,
                "session_type": session_type,
                "caller": caller
            },
            "timestamp": time.time()
        }

        logger.info(f"WebRTC offer from {caller} to {callee}, session: {session.session_id}")

        return relay_message

    async def handle_answer(
        self,
        callee: str,
        caller: str,
        answer: Dict[str, Any],
        session_id: str
    ) -> Optional[Dict]:
        """
        Handle WebRTC answer from the callee.
        Returns the answer message to be sent to the caller.
        """
        session = self._sessions.get(session_id)

        if not session:
            logger.warning(f"Session not found for answer: {session_id}")
            return None

        if session.callee != callee:
            logger.warning(f"Callee mismatch in answer: {callee} vs {session.callee}")
            return None

        lock = await self._get_session_lock(session_id)
        async with lock:
            session.answer = answer
            session.state = SignalingState.ANSWER_SENT

        relay_message = {
            "type": "webrtc_answer",
            "sender": callee,
            "target": caller,
            "payload": {
                "session_id": session_id,
                "answer": answer
            },
            "timestamp": time.time()
        }

        logger.info(f"WebRTC answer from {callee} to {caller}, session: {session_id}")

        return relay_message

    async def handle_ice_candidate(
        self,
        sender: str,
        target: str,
        candidate: Dict[str, Any],
        session_id: Optional[str] = None
    ) -> Optional[Dict]:
        """
        Handle ICE candidate from either party.
        Returns the candidate message to be relayed to the other peer.
        """
        if not session_id:
            session = await self._find_session_between(sender, target)
            if session:
                session_id = session.session_id
            else:
                session_id = self._generate_session_id(sender, target)

        if session_id and session_id in self._sessions:
            session = self._sessions[session_id]
            lock = await self._get_session_lock(session_id)
            async with lock:
                session.ice_candidates.append(candidate)

        relay_message = {
            "type": "webrtc_ice_candidate",
            "sender": sender,
            "target": target,
            "payload": {
                "session_id": session_id,
                "candidate": candidate
            },
            "timestamp": time.time()
        }

        logger.debug(f"ICE candidate from {sender} to {target}, session: {session_id}")

        return relay_message

    async def _find_session_between(self, user1: str, user2: str) -> Optional[SignalingSession]:
        """Find an existing session between two users"""
        async with self._global_lock:
            if user1 not in self._user_sessions:
                return None

            for session_id, session in self._user_sessions[user1].items():
                if session.caller == user2 or session.callee == user2:
                    if session.state not in [SignalingState.FAILED, SignalingState.CONNECTED]:
                        return session

        return None

    async def get_session(self, session_id: str) -> Optional[SignalingSession]:
        """Get a session by ID"""
        return self._sessions.get(session_id)

    async def get_user_sessions(self, username: str) -> list:
        """Get all sessions for a user"""
        async with self._global_lock:
            if username not in self._user_sessions:
                return []

            return [
                {
                    "session_id": s.session_id,
                    "caller": s.caller,
                    "callee": s.callee,
                    "state": s.state.value,
                    "session_type": s.session_type,
                    "created_at": s.created_at
                }
                for s in self._user_sessions[username].values()
            ]

    async def close_session(self, session_id: str) -> bool:
        """Close a signaling session"""
        session = self._sessions.get(session_id)
        if not session:
            return False

        lock = await self._get_session_lock(session_id)
        async with lock:
            session.state = SignalingState.FAILED

            async with self._global_lock:
                if session.caller in self._user_sessions:
                    self._user_sessions[session.caller].pop(session_id, None)
                if session.callee in self._user_sessions:
                    self._user_sessions[session.callee].pop(session_id, None)

                self._sessions.pop(session_id, None)

        logger.info(f"Closed signaling session: {session_id}")
        return True

    async def close_user_sessions(self, username: str):
        """Close all sessions for a user (e.g., when user disconnects)"""
        async with self._global_lock:
            if username not in self._user_sessions:
                return

            session_ids = list(self._user_sessions[username].keys())

        for session_id in session_ids:
            await self.close_session(session_id)

    async def relay_message(self, message: Dict) -> bool:
        """
        Relay a signaling message to the target user.
        Returns True if message was sent successfully.
        """
        target = message.get("target")
        if not target:
            return False

        target_ws = await self.user_manager.get_connection(target)
        if not target_ws:
            logger.warning(f"Cannot relay message to offline user: {target}")
            return False
        # 兼容不同 websockets 版本的状态属性
        is_open = getattr(target_ws, "open", None)
        if is_open is False:
            logger.warning(f"Cannot relay message to disconnected user: {target}")
            return False

        try:
            from protocol.messages import Message, MessageType

            try:
                msg_type = MessageType(message["type"])
            except (KeyError, ValueError) as e:
                logger.error(f"Invalid relay message type: {e}")
                return False

            msg = Message(
                type=msg_type,
                sender=message["sender"],
                target=target,
                payload=message.get("payload", {}),
                timestamp=message.get("timestamp"),
                message_id=None
            )
            await target_ws.send(msg.to_json())
            return True
        except Exception as e:
            logger.error(f"Failed to relay message to {target}: {e}")
            return False