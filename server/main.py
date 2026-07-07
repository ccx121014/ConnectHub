"""
Main WebSocket Server for Online Collaboration Suite
Handles all WebSocket connections and message routing.
"""

import asyncio
import websockets
import logging
import json
import time
import sys
import uuid
import os
from pathlib import Path
from typing import Optional, Set, Dict, Any

# Add project root to path for module imports
_project_root = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(_project_root))
sys.path.insert(0, str(Path(__file__).parent))

from protocol.messages import Message, MessageType, create_message, parse_message
from user_manager import UserManager, UserStatus
from chat_history import ChatHistory, ChatMessage
from webrtc_signaling import SignalingServer

_config_path = Path(__file__).parent / "config.json"
_default_config = {
    "host": "0.0.0.0",
    "port": 8765,
    "heartbeat_interval": 30,
    "auth_timeout": 60,
    "log_file": "server.log",
    "log_level": "INFO",
}

# 读取配置文件（若存在则覆盖默认值）
try:
    if _config_path.exists():
        with open(_config_path, "r", encoding="utf-8") as _f:
            _cfg = json.load(_f)
            _default_config.update(_cfg)
except Exception:
    pass

HOST = _default_config["host"]
PORT = int(_default_config["port"])
HEARTBEAT_INTERVAL = int(_default_config["heartbeat_interval"])
AUTH_TIMEOUT = int(_default_config["auth_timeout"])

# 配置日志
log_handlers = [logging.StreamHandler()]
try:
    log_file = _default_config.get("log_file")
    if log_file:
        log_handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
except Exception:
    pass

logging.basicConfig(
    level=getattr(logging, str(_default_config.get("log_level", "INFO")), logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=log_handlers,
)
logger = logging.getLogger(__name__)


class CollaborationServer:
    """Main WebSocket server for the collaboration suite"""

    def __init__(self):
        self.user_manager = UserManager(storage_path="data/users")
        self.chat_history = ChatHistory(storage_path="data/chats")
        self.signaling_server = SignalingServer(self.user_manager)
        self.signaling_server.set_message_handler(self._relay_signaling_message)

        self._authenticated_clients: Dict[str, object] = {}
        self._pending_auth: Dict[str, asyncio.Queue] = {}
        self._heartbeat_tasks: Dict[str, asyncio.Task] = {}
        self._client_locks: Dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

        self._group_members: Dict[str, Set[str]] = {}

        logger.info(f"Collaboration server initialized")

    async def _get_client_lock(self, username: str) -> asyncio.Lock:
        """Get or create a lock for a specific client"""
        async with self._global_lock:
            if username not in self._client_locks:
                self._client_locks[username] = asyncio.Lock()
            return self._client_locks[username]

    async def start(self):
        """Start the WebSocket server with version-compatible parameters."""
        logger.info(f"Starting WebSocket server on {HOST}:{PORT}")

        # Try various parameter sets for websockets version compatibility
        server = None
        for params in [
            dict(ping_interval=HEARTBEAT_INTERVAL, ping_timeout=10, max_size=10*1024*1024),
            dict(ping_timeout=10, max_size=10*1024*1024),
            dict(max_size=10*1024*1024),
            dict(),
        ]:
            try:
                server = await websockets.serve(self._handle_client, HOST, PORT, **params)
                logger.info(f"Server started on ws://{HOST}:{PORT} (params: {list(params.keys())})")
                break
            except (TypeError, ValueError) as e:
                logger.debug(f"serve() params failed ({params}): {e}")
                continue

        if server is None:
            raise RuntimeError(f"Could not start WebSocket server — all parameter sets failed")

        await asyncio.Future()  # run forever

    async def _handle_client(self, websocket: object):
        """Handle a new client connection"""
        client_id = str(uuid.uuid4())
        username = None
        logger.info(f"New connection from {websocket.remote_address}, client_id: {client_id}")

        try:
            async for raw_message in websocket:
                try:
                    message = parse_message(raw_message)
                    username = await self._process_message(
                        websocket,
                        message,
                        username
                    )
                except json.JSONDecodeError as e:
                    logger.warning(f"Invalid JSON from {client_id}: {e}")
                    await self._send_error(
                        websocket,
                        "Invalid JSON format",
                        message_id=None
                    )
                except ValueError as e:
                    logger.warning(f"Invalid message type from {client_id}: {e}")
                    await self._send_error(
                        websocket,
                        f"Invalid message type: {e}",
                        message_id=None
                    )
                except Exception as e:
                    logger.error(f"Error processing message from {client_id}: {e}")
                    await self._send_error(
                        websocket,
                        f"Server error: {str(e)}",
                        message_id=message.message_id if 'message' in locals() else None
                    )

        except websockets.exceptions.ConnectionClosed as e:
            logger.info(f"Client {client_id} ({username}) disconnected: {e.code} - {e.reason}")
        except Exception as e:
            logger.error(f"Unexpected error with client {client_id} ({username}): {e}")
        finally:
            if username:
                await self._handle_disconnect(username)
            logger.info(f"Client {client_id} ({username}) cleanup complete")

    async def _process_message(
        self,
        websocket: object,
        message: Message,
        current_username: Optional[str]
    ) -> Optional[str]:
        """Process a message and return the username if authenticated"""
        msg_type = message.type
        sender = message.sender

        logger.debug(f"Received {msg_type} from {sender}")

        if msg_type == MessageType.AUTH_REQUEST:
            return await self._handle_auth_request(websocket, message)

        if msg_type not in [
            MessageType.AUTH_REQUEST,
            MessageType.HEARTBEAT,
            MessageType.HEARTBEAT_ACK
        ]:
            if current_username is None:
                await self._send_error(
                    websocket,
                    "Authentication required",
                    message_id=message.message_id
                )
                return current_username

        if msg_type == MessageType.AUTH_LOGOUT:
            return await self._handle_logout(websocket, message)

        elif msg_type == MessageType.HEARTBEAT:
            await self._handle_heartbeat(websocket, message)
            return current_username

        elif msg_type == MessageType.HEARTBEAT_ACK:
            await self._handle_heartbeat_ack(sender)
            return current_username

        elif msg_type == MessageType.USER_STATUS_UPDATE:
            await self._handle_status_update(websocket, message)

        elif msg_type == MessageType.USER_LIST_REQUEST:
            await self._handle_user_list_request(websocket, message)

        elif msg_type == MessageType.CONTACT_LIST_REQUEST:
            await self._handle_contact_list_request(websocket, message)

        elif msg_type == MessageType.CHAT_MESSAGE:
            await self._handle_chat_message(websocket, message)

        elif msg_type == MessageType.CHAT_HISTORY_REQUEST:
            await self._handle_chat_history_request(websocket, message)

        elif msg_type == MessageType.GROUP_CREATE:
            await self._handle_group_create(websocket, message)

        elif msg_type == MessageType.GROUP_JOIN:
            await self._handle_group_join(websocket, message)

        elif msg_type == MessageType.GROUP_LEAVE:
            await self._handle_group_leave(websocket, message)

        elif msg_type == MessageType.GROUP_MESSAGE:
            await self._handle_group_message(websocket, message)

        elif msg_type == MessageType.WEBRTC_OFFER:
            await self._handle_webrtc_offer(websocket, message)

        elif msg_type == MessageType.WEBRTC_ANSWER:
            await self._handle_webrtc_answer(websocket, message)

        elif msg_type == MessageType.WEBRTC_ICE_CANDIDATE:
            await self._handle_webrtc_ice_candidate(websocket, message)

        # 文件传输消息 - 直接转发给目标用户
        elif msg_type in [
            MessageType.FILE_TRANSFER_REQUEST,
            MessageType.FILE_TRANSFER_RESPONSE,
            MessageType.FILE_TRANSFER_DATA,
            MessageType.FILE_TRANSFER_COMPLETE,
            MessageType.FILE_TRANSFER_CANCEL,
            MessageType.FILE_TRANSFER_PROGRESS,
        ]:
            target = message.target
            if target:
                await self.user_manager.send_to_user(target, message.to_json())

        # 远程桌面消息 - 直接转发给目标用户
        elif msg_type in [
            MessageType.DESKTOP_SHARE_REQUEST,
            MessageType.DESKTOP_SHARE_RESPONSE,
            MessageType.DESKTOP_STOP,
            MessageType.DESKTOP_FRAME,
            MessageType.DESKTOP_CONTROL_REQUEST,
            MessageType.DESKTOP_CONTROL_RESPONSE,
            MessageType.DESKTOP_MOUSE_MOVE,
            MessageType.DESKTOP_MOUSE_CLICK,
            MessageType.DESKTOP_MOUSE_RELEASE,
            MessageType.DESKTOP_KEYBOARD,
        ]:
            target = message.target
            if target:
                await self.user_manager.send_to_user(target, message.to_json())

        return sender

    async def _handle_auth_request(
        self,
        websocket: object,
        message: Message
    ) -> Optional[str]:
        """Handle authentication request"""
        username = message.sender
        payload = message.payload
        password = payload.get("password", "")

        success = True
        if password != "":  # In production, verify against a database
            pass

        await self.user_manager.register_user(username, websocket)

        async with self._global_lock:
            self._authenticated_clients[username] = websocket

        response = create_message(
            MessageType.AUTH_RESPONSE,
            sender="server",
            target=username,
            success=success,
            message="Authentication successful" if success else "Invalid credentials",
            timestamp=time.time()
        )

        await websocket.send(response.to_json())

        user_groups = await self.chat_history.get_user_groups(username)
        if user_groups:
            for group in user_groups:
                group_id = group["group_id"]
                if group_id not in self._group_members:
                    self._group_members[group_id] = set()
                self._group_members[group_id].add(username)

                await self.user_manager.add_to_group(username, group_id)

        await self._start_heartbeat(username, websocket)

        logger.info(f"User {username} authenticated successfully")
        return username

    async def _handle_logout(
        self,
        websocket: object,
        message: Message
    ):
        """Handle logout request"""
        username = message.sender

        response = create_message(
            MessageType.AUTH_RESPONSE,
            sender="server",
            target=username,
            success=True,
            message="Logged out successfully"
        )
        await websocket.send(response.to_json())

    async def _handle_disconnect(self, username: str):
        """Handle user disconnection"""
        await self._stop_heartbeat(username)

        await self.signaling_server.close_user_sessions(username)
        await self.user_manager.unregister_user(username, "disconnect")

        async with self._global_lock:
            self._authenticated_clients.pop(username, None)

        for group_id in list(self._group_members.keys()):
            self._group_members[group_id].discard(username)

        status_msg = create_status_message(username, UserStatus.OFFLINE)
        await self.user_manager.broadcast_to_contacts(username, status_msg.to_json())

        logger.info(f"User {username} disconnected")

    async def _handle_heartbeat(
        self,
        websocket: object,
        message: Message
    ):
        """Handle heartbeat ping"""
        response = create_message(
            MessageType.HEARTBEAT_ACK,
            sender="server",
            target=message.sender,
            timestamp=time.time()
        )
        try:
            await websocket.send(response.to_json())
        except Exception as e:
            logger.warning(f"Failed to send heartbeat ack to {message.sender}: {e}")

    async def _handle_heartbeat_ack(self, username: str):
        """Handle heartbeat acknowledgment"""
        pass

    async def _start_heartbeat(self, username: str, websocket: object):
        """Start heartbeat task for a client"""
        async def heartbeat_loop():
            while True:
                await asyncio.sleep(HEARTBEAT_INTERVAL)
                try:
                    await websocket.ping()
                except Exception:
                    break

        task = asyncio.create_task(heartbeat_loop())
        async with self._global_lock:
            self._heartbeat_tasks[username] = task

    async def _stop_heartbeat(self, username: str):
        """Stop heartbeat task for a client"""
        async with self._global_lock:
            if username in self._heartbeat_tasks:
                self._heartbeat_tasks[username].cancel()
                del self._heartbeat_tasks[username]

    async def _handle_status_update(
        self,
        websocket: object,
        message: Message
    ):
        """Handle user status update"""
        username = message.sender
        new_status_str = message.payload.get("status", "online")

        try:
            new_status = UserStatus(new_status_str)
        except ValueError:
            new_status = UserStatus.ONLINE

        await self.user_manager.update_status(username, new_status)

        status_msg = create_status_message(username, new_status)
        await self.user_manager.broadcast_to_contacts(username, status_msg.to_json())

    async def _handle_user_list_request(
        self,
        websocket: object,
        message: Message
    ):
        """Handle user list request"""
        username = message.sender
        all_users = []
        try:
            for uname, u in self.user_manager._users.items():
                all_users.append({
                    "username": uname,
                    "status": u.status.value if hasattr(u, "status") else "offline",
                    "last_seen": u.last_seen if hasattr(u, "last_seen") else time.time()
                })
        except Exception:
            all_users = []

        response = create_message(
            MessageType.USER_LIST_RESPONSE,
            sender="server",
            target=username,
            users=all_users,
            timestamp=time.time()
        )
        await websocket.send(response.to_json())

    async def _handle_contact_list_request(
        self,
        websocket: object,
        message: Message
    ):
        """Handle contact list request"""
        username = message.sender
        contacts = await self.user_manager.get_contacts(username)

        response = create_message(
            MessageType.CONTACT_LIST_RESPONSE,
            sender="server",
            target=username,
            contacts=contacts,
            timestamp=time.time()
        )
        await websocket.send(response.to_json())

    async def _handle_chat_message(
        self,
        websocket: object,
        message: Message
    ):
        """Handle direct chat message"""
        sender = message.sender
        target = message.target
        content = message.payload.get("content", "")
        msg_type = message.payload.get("message_type", "text")

        chat_msg = ChatMessage(
            message_id=message.message_id or str(uuid.uuid4()),
            sender=sender,
            target=target,
            content=content,
            timestamp=message.timestamp or time.time(),
            message_type=msg_type
        )

        await self.chat_history.save_message(chat_msg, is_group=False)

        response = create_message(
            MessageType.CHAT_MESSAGE,
            sender=sender,
            target=target,
            content=content,
            message_type=msg_type,
            timestamp=chat_msg.timestamp,
            message_id=chat_msg.message_id
        )

        await self.user_manager.send_to_user(target, response.to_json())

    async def _handle_chat_history_request(
        self,
        websocket: object,
        message: Message
    ):
        """Handle chat history request"""
        username = message.sender
        target = message.payload.get("target")
        limit = message.payload.get("limit", 100)
        before = message.payload.get("before_timestamp")

        if not target:
            await self._send_error(websocket, "Target user required", message.message_id)
            return

        history = await self.chat_history.get_history(
            username,
            target,
            limit=limit,
            before_timestamp=before
        )

        response = create_message(
            MessageType.CHAT_HISTORY_RESPONSE,
            sender="server",
            target=username,
            messages=history,
            with_user=target,
            timestamp=time.time()
        )
        await websocket.send(response.to_json())

    async def _handle_group_create(
        self,
        websocket: object,
        message: Message
    ):
        """Handle group creation request"""
        creator = message.sender
        group_name = message.payload.get("name", "")
        group_id = message.payload.get("group_id", str(uuid.uuid4()))

        if not group_name:
            await self._send_error(websocket, "Group name required", message.message_id)
            return

        group = await self.chat_history.create_group(group_id, group_name, creator)

        if not group:
            await self._send_error(websocket, "Failed to create group", message.message_id)
            return

        if group_id not in self._group_members:
            self._group_members[group_id] = set()
        self._group_members[group_id].add(creator)

        await self.user_manager.add_to_group(creator, group_id)

        response = create_message(
            MessageType.GROUP_CREATE_RESPONSE,
            sender="server",
            target=creator,
            group_id=group_id,
            name=group_name,
            success=True,
            timestamp=time.time()
        )
        await websocket.send(response.to_json())

        member_update = create_message(
            MessageType.GROUP_MEMBER_UPDATE,
            sender="server",
            target=group_id,
            action="create",
            group_id=group_id,
            name=group_name,
            members=[creator],
            timestamp=time.time()
        )
        await websocket.send(member_update.to_json())

    async def _handle_group_join(
        self,
        websocket: object,
        message: Message
    ):
        """Handle group join request"""
        username = message.sender
        group_id = message.payload.get("group_id")

        if not group_id:
            await self._send_error(websocket, "Group ID required", message.message_id)
            return

        group = await self.chat_history.get_group(group_id)
        if not group:
            await self._send_error(websocket, "Group not found", message.message_id)
            return

        success = await self.chat_history.add_member_to_group(group_id, username)

        if success:
            if group_id not in self._group_members:
                self._group_members[group_id] = set()
            self._group_members[group_id].add(username)

            await self.user_manager.add_to_group(username, group_id)

            response = create_message(
                MessageType.GROUP_CREATE_RESPONSE,
                sender="server",
                target=username,
                group_id=group_id,
                name=group.name,
                success=True,
                members=list(group.members),
                timestamp=time.time()
            )
            await websocket.send(response.to_json())

            member_update = create_message(
                MessageType.GROUP_MEMBER_UPDATE,
                sender="server",
                target=group_id,
                action="join",
                group_id=group_id,
                member=username,
                members=list(group.members),
                timestamp=time.time()
            )

            await self._broadcast_to_group(group_id, member_update.to_json(), exclude_sender=username)
        else:
            await self._send_error(websocket, "Failed to join group", message.message_id)

    async def _handle_group_leave(
        self,
        websocket: object,
        message: Message
    ):
        """Handle group leave request"""
        username = message.sender
        group_id = message.payload.get("group_id")

        if not group_id:
            await self._send_error(websocket, "Group ID required", message.message_id)
            return

        group = await self.chat_history.get_group(group_id)
        if not group:
            await self._send_error(websocket, "Group not found", message.message_id)
            return

        success = await self.chat_history.remove_member_from_group(group_id, username)

        if success:
            if group_id in self._group_members:
                self._group_members[group_id].discard(username)

            await self.user_manager.remove_from_group(username, group_id)

            response = create_message(
                MessageType.GROUP_LEAVE,
                sender="server",
                target=username,
                group_id=group_id,
                success=True,
                timestamp=time.time()
            )
            await websocket.send(response.to_json())

            member_update = create_message(
                MessageType.GROUP_MEMBER_UPDATE,
                sender="server",
                target=group_id,
                action="leave",
                group_id=group_id,
                member=username,
                members=await self.chat_history.get_group_members(group_id),
                timestamp=time.time()
            )

            await self._broadcast_to_group(group_id, member_update.to_json(), exclude_sender=username)
        else:
            await self._send_error(websocket, "Failed to leave group", message.message_id)

    async def _handle_group_message(
        self,
        websocket: object,
        message: Message
    ):
        """Handle group message"""
        sender = message.sender
        group_id = message.target
        content = message.payload.get("content", "")
        msg_type = message.payload.get("message_type", "text")

        if group_id not in self._group_members:
            await self._send_error(websocket, "Not a member of this group", message.message_id)
            return

        is_member = await self.chat_history.is_group_member(group_id, sender)
        if not is_member:
            await self._send_error(websocket, "Not a member of this group", message.message_id)
            return

        chat_msg = ChatMessage(
            message_id=message.message_id or str(uuid.uuid4()),
            sender=sender,
            target=group_id,
            content=content,
            timestamp=message.timestamp or time.time(),
            message_type=msg_type
        )

        await self.chat_history.save_message(chat_msg, is_group=True)

        broadcast_msg = create_message(
            MessageType.GROUP_MESSAGE,
            sender=sender,
            target=group_id,
            content=content,
            message_type=msg_type,
            timestamp=chat_msg.timestamp,
            message_id=chat_msg.message_id
        )

        await self._broadcast_to_group(group_id, broadcast_msg.to_json(), exclude_sender=sender)
        await websocket.send(broadcast_msg.to_json())

    async def _broadcast_to_group(
        self,
        group_id: str,
        message: str,
        exclude_sender: Optional[str] = None
    ):
        """Broadcast message to all group members"""
        if group_id not in self._group_members:
            return

        tasks = []
        for member in self._group_members[group_id]:
            if member != exclude_sender:
                tasks.append(self.user_manager.send_to_user(member, message))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _handle_webrtc_offer(
        self,
        websocket: object,
        message: Message
    ):
        """Handle WebRTC offer"""
        sender = message.sender
        target = message.payload.get("target_user")
        offer = message.payload.get("offer", {})
        session_type = message.payload.get("session_type", "file_transfer")

        if not target:
            await self._send_error(websocket, "Target user required", message.message_id)
            return

        relay_msg = await self.signaling_server.handle_offer(
            sender,
            target,
            offer,
            session_type
        )

        if relay_msg:
            await self.signaling_server.relay_message(relay_msg)

            response = create_message(
                MessageType.WEBRTC_OFFER,
                sender=sender,
                target=target,
                offer=offer,
                session_type=session_type,
                timestamp=time.time()
            )
            await websocket.send(response.to_json())

    async def _handle_webrtc_answer(
        self,
        websocket: object,
        message: Message
    ):
        """Handle WebRTC answer"""
        sender = message.sender
        target = message.payload.get("target_user")
        answer = message.payload.get("answer", {})
        session_id = message.payload.get("session_id")

        if not target:
            await self._send_error(websocket, "Target user required", message.message_id)
            return

        relay_msg = await self.signaling_server.handle_answer(
            sender,
            target,
            answer,
            session_id
        )

        if relay_msg:
            await self.signaling_server.relay_message(relay_msg)

            response = create_message(
                MessageType.WEBRTC_ANSWER,
                sender=sender,
                target=target,
                answer=answer,
                session_id=session_id,
                timestamp=time.time()
            )
            await websocket.send(response.to_json())

    async def _handle_webrtc_ice_candidate(
        self,
        websocket: object,
        message: Message
    ):
        """Handle WebRTC ICE candidate"""
        sender = message.sender
        target = message.payload.get("target_user")
        candidate = message.payload.get("candidate", {})
        session_id = message.payload.get("session_id")

        if not target:
            await self._send_error(websocket, "Target user required", message.message_id)
            return

        relay_msg = await self.signaling_server.handle_ice_candidate(
            sender,
            target,
            candidate,
            session_id
        )

        if relay_msg:
            await self.signaling_server.relay_message(relay_msg)

    async def _relay_signaling_message(self, message: Dict) -> bool:
        """Relay a signaling message to the target user"""
        return await self.signaling_server.relay_message(message)

    async def _send_error(
        self,
        websocket: object,
        error_message: str,
        message_id: Optional[str] = None
    ):
        """Send error message to client"""
        response = create_message(
            MessageType.ERROR,
            sender="server",
            error=error_message,
            message_id=message_id,
            timestamp=time.time()
        )
        try:
            await websocket.send(response.to_json())
        except Exception as e:
            logger.warning(f"Failed to send error message: {e}")


def create_status_message(username: str, status: UserStatus) -> Message:
    """Helper to create a status update message"""
    return create_message(
        MessageType.USER_STATUS_UPDATE,
        sender=username,
        status=status.value,
        timestamp=time.time()
    )


async def main():
    """Main entry point"""
    server = CollaborationServer()
    await server.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server shutting down...")
    except Exception as e:
        logger.error(f"Server error: {e}")
        sys.exit(1)