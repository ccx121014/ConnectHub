"""
Chat History Storage Module
Handles persisting and retrieving chat messages.
"""

import json
import logging
import os
import time
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
import asyncio
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class ChatMessage:
    """Chat message structure"""
    message_id: str
    sender: str
    target: str
    content: str
    timestamp: float
    message_type: str = "text"

    def to_dict(self) -> dict:
        return {
            "message_id": self.message_id,
            "sender": self.sender,
            "target": self.target,
            "content": self.content,
            "timestamp": self.timestamp,
            "message_type": self.message_type
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ChatMessage":
        return cls(
            message_id=data["message_id"],
            sender=data["sender"],
            target=data["target"],
            content=data["content"],
            timestamp=data["timestamp"],
            message_type=data.get("message_type", "text")
        )


@dataclass
class Group:
    """Group chat structure"""
    group_id: str
    name: str
    members: Set[str] = field(default_factory=set)
    created_at: float = field(default_factory=time.time)
    created_by: str = ""

    def to_dict(self) -> dict:
        return {
            "group_id": self.group_id,
            "name": self.name,
            "members": list(self.members),
            "created_at": self.created_at,
            "created_by": self.created_by
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Group":
        return cls(
            group_id=data["group_id"],
            name=data["name"],
            members=set(data.get("members", [])),
            created_at=data.get("created_at", time.time()),
            created_by=data.get("created_by", "")
        )


class ChatHistory:
    """Manages chat history storage using JSON files"""

    def __init__(self, storage_path: str = "data/chats"):
        """Initialize chat history with storage path"""
        self.storage_path = storage_path
        self._dm_history: Dict[str, List[ChatMessage]] = defaultdict(list)
        self._group_history: Dict[str, List[ChatMessage]] = defaultdict(list)
        self._groups: Dict[str, Group] = {}
        self._lock = asyncio.Lock()

        os.makedirs(storage_path, exist_ok=True)
        os.makedirs(os.path.join(storage_path, "direct"), exist_ok=True)
        os.makedirs(os.path.join(storage_path, "groups"), exist_ok=True)

        self._load_groups()
        self._load_recent_history()

    def _get_dm_filename(self, user1: str, user2: str) -> str:
        """Generate consistent filename for direct message history"""
        users = sorted([user1, user2])
        return f"{users[0]}_{users[1]}.json"

    def _get_dm_path(self, user1: str, user2: str) -> str:
        """Get full path for direct message file"""
        filename = self._get_dm_filename(user1, user2)
        return os.path.join(self.storage_path, "direct", filename)

    def _get_group_path(self, group_id: str) -> str:
        """Get full path for group history file"""
        return os.path.join(self.storage_path, "groups", f"{group_id}.json")

    def _load_groups(self):
        """Load groups from storage"""
        groups_file = os.path.join(self.storage_path, "groups.json")
        if os.path.exists(groups_file):
            try:
                with open(groups_file, 'r') as f:
                    data = json.load(f)
                    for group_id, group_data in data.items():
                        self._groups[group_id] = Group.from_dict(group_data)
            except (json.JSONDecodeError, KeyError):
                pass

    def _save_groups(self):
        """Save groups to storage"""
        try:
            groups_file = os.path.join(self.storage_path, "groups.json")
            data = {}
            for group_id, group in self._groups.items():
                data[group_id] = group.to_dict()
            with open(groups_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as exc:
            logger.error(f"Failed to save groups: {exc}")

    def _load_recent_history(self):
        """Load recent history for active conversations"""
        direct_path = os.path.join(self.storage_path, "direct")
        if os.path.exists(direct_path):
            for filename in os.listdir(direct_path):
                if filename.endswith(".json"):
                    filepath = os.path.join(direct_path, filename)
                    try:
                        with open(filepath, 'r') as f:
                            messages = json.load(f)
                            for msg_data in messages[-100:]:
                                msg = ChatMessage.from_dict(msg_data)
                                key = self._get_dm_key(msg.sender, msg.target)
                                if key not in self._dm_history or len(self._dm_history[key]) < 100:
                                    self._dm_history[key].append(msg)
                    except (json.JSONDecodeError, KeyError):
                        pass

        groups_path = os.path.join(self.storage_path, "groups")
        if os.path.exists(groups_path):
            for filename in os.listdir(groups_path):
                if filename.endswith(".json"):
                    group_id = filename.replace(".json", "")
                    filepath = os.path.join(groups_path, filename)
                    try:
                        with open(filepath, 'r') as f:
                            messages = json.load(f)
                            for msg_data in messages[-100:]:
                                msg = ChatMessage.from_dict(msg_data)
                                if group_id not in self._group_history or len(self._group_history[group_id]) < 100:
                                    self._group_history[group_id].append(msg)
                    except (json.JSONDecodeError, KeyError):
                        pass

    def _get_dm_key(self, user1: str, user2: str) -> str:
        """Generate key for direct message history dictionary"""
        users = sorted([user1, user2])
        return f"{users[0]}:{users[1]}"

    async def save_message(self, message: ChatMessage, is_group: bool = False) -> bool:
        """Save a chat message to history"""
        async with self._lock:
            try:
                if is_group:
                    self._group_history[message.target].append(message)

                    filepath = self._get_group_path(message.target)
                    messages = [msg.to_dict() for msg in self._group_history[message.target]]

                    with open(filepath, 'w') as f:
                        json.dump(messages, f, indent=2)
                else:
                    key = self._get_dm_key(message.sender, message.target)
                    self._dm_history[key].append(message)

                    filepath = self._get_dm_path(message.sender, message.target)
                    messages = [msg.to_dict() for msg in self._dm_history[key]]

                    with open(filepath, 'w') as f:
                        json.dump(messages, f, indent=2)

                return True
            except Exception:
                return False

    async def get_history(
        self,
        user1: str,
        user2: str,
        limit: int = 100,
        before_timestamp: Optional[float] = None
    ) -> List[Dict]:
        """Get direct message history between two users"""
        async with self._lock:
            key = self._get_dm_key(user1, user2)
            messages = self._dm_history.get(key, [])

            filepath = self._get_dm_path(user1, user2)
            if os.path.exists(filepath) and len(messages) < 50:
                try:
                    with open(filepath, 'r') as f:
                        stored_messages = json.load(f)
                        messages = [ChatMessage.from_dict(m) for m in stored_messages]
                except (json.JSONDecodeError, KeyError):
                    pass

            filtered_messages = messages
            if before_timestamp:
                filtered_messages = [
                    msg for msg in messages
                    if msg.timestamp < before_timestamp
                ]

            filtered_messages = filtered_messages[-limit:]
            return [msg.to_dict() for msg in filtered_messages]

    async def get_group_history(
        self,
        group_id: str,
        limit: int = 100,
        before_timestamp: Optional[float] = None
    ) -> List[Dict]:
        """Get message history for a group"""
        async with self._lock:
            messages = self._group_history.get(group_id, [])

            filepath = self._get_group_path(group_id)
            if os.path.exists(filepath) and len(messages) < 50:
                try:
                    with open(filepath, 'r') as f:
                        stored_messages = json.load(f)
                        messages = [ChatMessage.from_dict(m) for m in stored_messages]
                except (json.JSONDecodeError, KeyError):
                    pass

            filtered_messages = messages
            if before_timestamp:
                filtered_messages = [
                    msg for msg in messages
                    if msg.timestamp < before_timestamp
                ]

            filtered_messages = filtered_messages[-limit:]
            return [msg.to_dict() for msg in filtered_messages]

    async def create_group(self, group_id: str, name: str, creator: str) -> Optional[Group]:
        """Create a new group"""
        async with self._lock:
            if group_id in self._groups:
                return None

            group = Group(
                group_id=group_id,
                name=name,
                members={creator},
                created_by=creator
            )
            self._groups[group_id] = group
            self._save_groups()

            filepath = self._get_group_path(group_id)
            try:
                with open(filepath, 'w') as f:
                    json.dump([], f)
            except Exception as exc:
                logger.error(f"Failed to create group history file: {exc}")

            return group

    async def get_group(self, group_id: str) -> Optional[Group]:
        """Get group by ID"""
        return self._groups.get(group_id)

    async def add_member_to_group(self, group_id: str, username: str) -> bool:
        """Add a member to a group"""
        async with self._lock:
            if group_id not in self._groups:
                return False

            self._groups[group_id].members.add(username)
            self._save_groups()
            return True

    async def remove_member_from_group(self, group_id: str, username: str) -> bool:
        """Remove a member from a group"""
        async with self._lock:
            if group_id not in self._groups:
                return False

            self._groups[group_id].members.discard(username)
            self._save_groups()
            return True

    async def get_group_members(self, group_id: str) -> List[str]:
        """Get list of group members"""
        group = self._groups.get(group_id)
        return list(group.members) if group else []

    async def get_user_groups(self, username: str) -> List[Dict]:
        """Get all groups a user belongs to"""
        user_groups = []
        for group_id, group in self._groups.items():
            if username in group.members:
                user_groups.append({
                    "group_id": group_id,
                    "name": group.name,
                    "members": list(group.members),
                    "created_at": group.created_at,
                    "created_by": group.created_by
                })
        return user_groups

    async def delete_group(self, group_id: str) -> bool:
        """Delete a group"""
        async with self._lock:
            if group_id not in self._groups:
                return False

            del self._groups[group_id]
            self._save_groups()

            filepath = self._get_group_path(group_id)
            if os.path.exists(filepath):
                os.remove(filepath)

            if group_id in self._group_history:
                del self._group_history[group_id]

            return True

    async def is_group_member(self, group_id: str, username: str) -> bool:
        """Check if user is a member of the group"""
        group = self._groups.get(group_id)
        return username in group.members if group else False