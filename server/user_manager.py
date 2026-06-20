"""
User Session Management Module
Handles user registration, status tracking, and contact lists.
"""

from enum import Enum
from typing import Dict, Set, Optional, List
from dataclasses import dataclass, field
import asyncio
import time
import json
import os


class UserStatus(Enum):
    """User online status"""
    ONLINE = "online"
    BUSY = "busy"
    OFFLINE = "offline"


@dataclass
class User:
    """User data structure"""
    username: str
    status: UserStatus = UserStatus.OFFLINE
    contacts: Set[str] = field(default_factory=set)
    last_seen: float = field(default_factory=time.time)
    groups: Set[str] = field(default_factory=set)


class UserManager:
    """Manages user sessions and online status"""

    def __init__(self, storage_path: str = "data/users"):
        """Initialize user manager with storage path"""
        self.storage_path = storage_path
        self._users: Dict[str, User] = {}
        self._connections: Dict[str, asyncio.WebSocket] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()
        self._status_subscribers: Dict[str, Set[str]] = {}  # user -> set of users who subscribed

        os.makedirs(storage_path, exist_ok=True)
        self._load_users()

    async def _get_user_lock(self, username: str) -> asyncio.Lock:
        """Get or create a lock for a specific user"""
        async with self._global_lock:
            if username not in self._locks:
                self._locks[username] = asyncio.Lock()
            return self._locks[username]

    def _load_users(self):
        """Load users from storage"""
        user_file = os.path.join(self.storage_path, "users.json")
        if os.path.exists(user_file):
            try:
                with open(user_file, 'r') as f:
                    data = json.load(f)
                    for username, user_data in data.items():
                        user = User(
                            username=username,
                            status=UserStatus(user_data.get("status", "offline")),
                            contacts=set(user_data.get("contacts", [])),
                            last_seen=user_data.get("last_seen", time.time()),
                            groups=set(user_data.get("groups", []))
                        )
                        self._users[username] = user
            except (json.JSONDecodeError, KeyError):
                pass

    def _save_users(self):
        """Save users to storage"""
        user_file = os.path.join(self.storage_path, "users.json")
        data = {}
        for username, user in self._users.items():
            data[username] = {
                "status": user.status.value,
                "contacts": list(user.contacts),
                "last_seen": user.last_seen,
                "groups": list(user.groups)
            }
        with open(user_file, 'w') as f:
            json.dump(data, f, indent=2)

    async def register_user(self, username: str, websocket: object) -> bool:
        """Register a new user connection"""
        lock = await self._get_user_lock(username)

        async with lock:
            if username in self._connections:
                old_ws = self._connections[username]
                try:
                    await old_ws.close(1000, "Replaced by new connection")
                except Exception:
                    pass

            self._connections[username] = websocket

            if username not in self._users:
                self._users[username] = User(username=username)

            self._users[username].status = UserStatus.ONLINE
            self._users[username].last_seen = time.time()
            self._save_users()

            await self._notify_status_change(username, UserStatus.ONLINE)

            return True

    async def unregister_user(self, username: str, reason: str = "disconnect"):
        """Unregister a user connection"""
        lock = await self._get_user_lock(username)

        async with lock:
            if username in self._connections:
                del self._connections[username]

            if username in self._users:
                self._users[username].status = UserStatus.OFFLINE
                self._users[username].last_seen = time.time()
                self._save_users()

                await self._notify_status_change(username, UserStatus.OFFLINE)

    async def _notify_status_change(self, username: str, status: UserStatus):
        """Notify subscribers about status change"""
        if username in self._status_subscribers:
            for subscriber in self._status_subscribers[username]:
                if subscriber in self._connections:
                    try:
                        from .main import create_status_message
                        msg = create_status_message(username, status)
                        await self._connections[subscriber].send(msg.to_json() if hasattr(msg, 'to_json') else msg)
                    except Exception:
                        pass

    async def get_user(self, username: str) -> Optional[User]:
        """Get user by username"""
        return self._users.get(username)

    async def get_online_users(self) -> List[str]:
        """Get list of online usernames"""
        return [
            username for username, user in self._users.items()
            if user.status == UserStatus.ONLINE
        ]

    async def get_user_status(self, username: str) -> UserStatus:
        """Get current status of a user"""
        user = self._users.get(username)
        return user.status if user else UserStatus.OFFLINE

    async def update_status(self, username: str, status: UserStatus) -> bool:
        """Update user status"""
        lock = await self._get_user_lock(username)

        async with lock:
            if username not in self._users:
                return False

            old_status = self._users[username].status
            self._users[username].status = status
            self._users[username].last_seen = time.time()
            self._save_users()

            if old_status != status:
                await self._notify_status_change(username, status)

            return True

    async def add_contact(self, username: str, contact: str) -> bool:
        """Add a contact for a user"""
        lock = await self._get_user_lock(username)

        async with lock:
            if username not in self._users:
                return False

            self._users[username].contacts.add(contact)
            self._save_users()
            return True

    async def remove_contact(self, username: str, contact: str) -> bool:
        """Remove a contact from a user"""
        lock = await self._get_user_lock(username)

        async with lock:
            if username not in self._users:
                return False

            self._users[username].contacts.discard(contact)
            self._save_users()
            return True

    async def get_contacts(self, username: str) -> List[Dict[str, any]]:
        """Get user's contact list with status"""
        if username not in self._users:
            return []

        contacts = []
        for contact_name in self._users[username].contacts:
            contact = self._users.get(contact_name)
            if contact:
                contacts.append({
                    "username": contact_name,
                    "status": contact.status.value,
                    "last_seen": contact.last_seen
                })
            else:
                contacts.append({
                    "username": contact_name,
                    "status": UserStatus.OFFLINE.value,
                    "last_seen": None
                })

        return contacts

    async def subscribe_to_status(self, username: str, target_user: str):
        """Subscribe to status updates for a user"""
        if target_user not in self._status_subscribers:
            self._status_subscribers[target_user] = set()
        self._status_subscribers[target_user].add(username)

    async def unsubscribe_from_status(self, username: str, target_user: str):
        """Unsubscribe from status updates"""
        if target_user in self._status_subscribers:
            self._status_subscribers[target_user].discard(username)

    async def add_to_group(self, username: str, group_id: str):
        """Add user to a group"""
        lock = await self._get_user_lock(username)

        async with lock:
            if username in self._users:
                self._users[username].groups.add(group_id)
                self._save_users()

    async def remove_from_group(self, username: str, group_id: str):
        """Remove user from a group"""
        lock = await self._get_user_lock(username)

        async with lock:
            if username in self._users:
                self._users[username].groups.discard(group_id)
                self._save_users()

    async def get_user_groups(self, username: str) -> Set[str]:
        """Get groups a user belongs to"""
        user = self._users.get(username)
        return user.groups if user else set()

    async def get_connection(self, username: str) -> Optional[asyncio.WebSocket]:
        """Get websocket connection for a user"""
        return self._connections.get(username)

    async def is_user_online(self, username: str) -> bool:
        """Check if user is online"""
        return self._connections.get(username) is not None

    async def send_to_user(self, username: str, message: str) -> bool:
        """Send message to specific user"""
        ws = await self.get_connection(username)
        if ws is None:
            return False
        try:
            await ws.send(message)
            return True
        except Exception:
            return False

    async def broadcast_to_contacts(self, username: str, message: str):
        """Broadcast message to all contacts of a user"""
        if username not in self._users:
            return

        for contact_name in self._users[username].contacts:
            await self.send_to_user(contact_name, message)