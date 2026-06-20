"""
STUN/TURN 服务器配置模块

提供 STUN/TURN 服务器设置、默认公共服务器配置、
TURN 凭证生成和端口分配功能。
"""

import secrets
import hashlib
import time
import logging
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


class ServerType(Enum):
    """服务器类型枚举"""
    STUN = "stun"
    TURN = "turn"


@dataclass
class STUNServer:
    """STUN 服务器配置"""
    host: str
    port: int
    name: str = ""

    def __post_init__(self):
        if not self.name:
            self.name = f"{self.host}:{self.port}"

    @property
    def url(self) -> str:
        """返回 STUN 服务器 URL"""
        return f"stun:{self.host}:{self.port}"


@dataclass
class TURNServer:
    """TURN 服务器配置"""
    host: str
    port: int
    username: str = ""
    password: str = ""
    realm: str = "collaboration-suite"
    name: str = ""
    use_tls: bool = False

    def __post_init__(self):
        if not self.name:
            self.name = f"{self.host}:{self.port}"

    @property
    def transport(self) -> str:
        """返回传输协议"""
        return "tls" if self.use_tls else "udp"

    @property
    def url(self) -> str:
        """返回 TURN 服务器 URL"""
        proto = "turns" if self.use_tls else "turn"
        return f"{proto}:{self.host}:{self.port}?transport={self.transport}"


@dataclass
class ICEServerConfig:
    """ICE 服务器配置"""
    stun_servers: List[STUNServer] = field(default_factory=list)
    turn_servers: List[TURNServer] = field(default_factory=list)

    def add_stun(self, host: str, port: int, name: str = "") -> None:
        """添加 STUN 服务器"""
        self.stun_servers.append(STUNServer(host, port, name))

    def add_turn(self, host: str, port: int, username: str = "",
                 password: str = "", realm: str = "collaboration-suite",
                 use_tls: bool = False) -> None:
        """添加 TURN 服务器"""
        self.turn_servers.append(TURNServer(
            host, port, username, password, realm, "", use_tls
        ))

    def get_ice_servers(self) -> List[Dict]:
        """获取 WebRTC 格式的 ICE 服务器配置"""
        ice_servers = []

        for stun in self.stun_servers:
            ice_servers.append({
                "urls": [stun.url]
            })

        for turn in self.turn_servers:
            server_config = {
                "urls": [turn.url],
                "credential": turn.password,
                "username": turn.username
            }
            ice_servers.append(server_config)

        return ice_servers


@dataclass
class TURNAllocation:
    """TURN 端口分配记录"""
    username: str
    realm: str
    nonce: str
    allocated_at: float
    expires_at: float
    port_range: Tuple[int, int]
    bandwidth_limit: int = 0  # bps, 0 表示无限制


class DefaultSTUNServers:
    """默认公共 STUN 服务器"""

    GOOGLE = [
        STUNServer("stun.l.google.com", 19302, "Google STUN 1"),
        STUNServer("stun1.l.google.com", 19302, "Google STUN 2"),
        STUNServer("stun2.l.google.com", 19302, "Google STUN 3"),
        STUNServer("stun3.l.google.com", 19302, "Google STUN 4"),
        STUNServer("stun4.l.google.com", 19302, "Google STUN 5"),
    ]

    TWILIO = [
        STUNServer("global.stun.twilio.com", 3478, "Twilio STUN"),
    ]

    MISC = [
        STUNServer("stun.stunprotocol.org", 3478, "STUN Protocol"),
        STUNServer("stun.sipgate.net", 3478, "Sipgate STUN"),
        STUNServer("stun.ideasip.com", 3478, "IdeaSIP STUN"),
    ]

    @classmethod
    def get_all(cls) -> List[STUNServer]:
        """获取所有默认 STUN 服务器"""
        return cls.GOOGLE + cls.TWILIO + cls.MISC


class TURNPortAllocator:
    """TURN 端口分配器"""

    def __init__(
        self,
        min_port: int = 49152,
        max_port: int = 65535,
        max_allocations: int = 1000
    ):
        self.min_port = min_port
        self.max_port = max_port
        self.max_allocations = max_allocations
        self._allocations: Dict[str, TURNAllocation] = {}
        self._used_ports: set = set()
        self._next_port = min_port

    def allocate(self, username: str, realm: str, lifetime: int = 3600,
                 bandwidth_limit: int = 0) -> Optional[TURNAllocation]:
        """
        分配一个新的 TURN 端口

        Args:
            username: 用户名
            realm: 认证领域
            lifetime: 分配有效期（秒）
            bandwidth_limit: 带宽限制（bps）

        Returns:
            TURNAllocation 或 None（如果无可用端口）
        """
        if len(self._allocations) >= self.max_allocations:
            logger.warning("TURN 端口分配已达上限")
            return None

        # 生成随机 nonce
        nonce = secrets.token_hex(16)

        # 分配端口
        port = self._get_next_port()
        if port is None:
            logger.error("无可用 TURN 端口")
            return None

        now = time.time()
        allocation = TURNAllocation(
            username=username,
            realm=realm,
            nonce=nonce,
            allocated_at=now,
            expires_at=now + lifetime,
            port_range=(port, port),
            bandwidth_limit=bandwidth_limit
        )

        self._allocations[f"{username}@{realm}"] = allocation
        self._used_ports.add(port)

        logger.info(f"分配 TURN 端口 {port} 给用户 {username}")
        return allocation

    def _get_next_port(self) -> Optional[int]:
        """获取下一个可用端口"""
        attempts = 0
        max_attempts = self.max_port - self.min_port + 1

        while attempts < max_attempts:
            port = self._next_port
            self._next_port = (self._next_port + 1 - self.min_port) % \
                              (self.max_port - self.min_port + 1) + self.min_port

            if port not in self._used_ports:
                return port

            attempts += 1

        return None

    def release(self, username: str, realm: str) -> bool:
        """释放用户的 TURN 分配"""
        key = f"{username}@{realm}"
        allocation = self._allocations.get(key)

        if allocation:
            for port in range(allocation.port_range[0],
                             allocation.port_range[1] + 1):
                self._used_ports.discard(port)
            del self._allocations[key]
            logger.info(f"释放用户 {username} 的 TURN 分配")
            return True

        return False

    def cleanup_expired(self) -> int:
        """清理过期的分配，返回清理的数量"""
        now = time.time()
        expired_keys = [
            key for key, alloc in self._allocations.items()
            if alloc.expires_at <= now
        ]

        for key in expired_keys:
            alloc = self._allocations[key]
            for port in range(alloc.port_range[0], alloc.port_range[1] + 1):
                self._used_ports.discard(port)
            del self._allocations[key]
            logger.debug(f"清理过期 TURN 分配: {key}")

        if expired_keys:
            logger.info(f"清理了 {len(expired_keys)} 个过期的 TURN 分配")

        return len(expired_keys)

    def get_allocation(self, username: str, realm: str) -> Optional[TURNAllocation]:
        """获取用户的当前分配"""
        return self._allocations.get(f"{username}@{realm}")

    @property
    def allocation_count(self) -> int:
        """当前分配数量"""
        return len(self._allocations)


class TURNCredentialGenerator:
    """TURN 凭证生成器"""

    def __init__(self, realm: str = "collaboration-suite"):
        self.realm = realm
        self._credentials: Dict[str, Tuple[str, float]] = {}  # username -> (password, expires_at)

    def generate_credentials(
        self,
        username: str,
        lifetime: int = 3600
    ) -> Tuple[str, str]:
        """
        生成 TURN 凭证

        Args:
            username: 用户名
            lifetime: 有效期（秒）

        Returns:
            (username, password) 元组
        """
        password = secrets.token_hex(32)
        expires_at = time.time() + lifetime

        # 包含过期时间在用户名中（RFC 5389）
        timestamp = int(expires_at)
        full_username = f"{timestamp}:{username}"

        self._credentials[full_username] = (password, expires_at)

        logger.debug(f"为用户 {username} 生成凭证，有效期至 "
                    f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(expires_at))}")

        return full_username, password

    def verify_credentials(self, username: str, password: str) -> bool:
        """验证 TURN 凭证"""
        cred = self._credentials.get(username)

        if not cred:
            logger.warning(f"未找到凭证: {username}")
            return False

        stored_password, expires_at = cred

        if time.time() > expires_at:
            del self._credentials[username]
            logger.warning(f"凭证已过期: {username}")
            return False

        if password != stored_password:
            logger.warning(f"密码不匹配: {username}")
            return False

        return True

    def cleanup_expired(self) -> int:
        """清理过期凭证"""
        now = time.time()
        expired = [
            username for username, (_, expires_at) in self._credentials.items()
            if expires_at <= now
        ]

        for username in expired:
            del self._credentials[username]

        return len(expired)


class STUNTurnConfig:
    """STUN/TURN 配置管理器"""

    def __init__(
        self,
        use_builtin_stun: bool = True,
        use_builtin_turn: bool = False,
        turn_port_start: int = 49152,
        turn_port_end: int = 65535,
        turn_max_allocations: int = 1000,
        default_turn_lifetime: int = 3600
    ):
        self.use_builtin_stun = use_builtin_stun
        self.use_builtin_turn = use_builtin_turn

        self._config = ICEServerConfig()
        self._port_allocator = TURNPortAllocator(
            min_port=turn_port_start,
            max_port=turn_port_end,
            max_allocations=turn_max_allocations
        )
        self._credential_generator = TURNCredentialGenerator()
        self.default_turn_lifetime = default_turn_lifetime

        self._setup_default_servers()

    def _setup_default_servers(self) -> None:
        """设置默认服务器"""
        if self.use_builtin_stun:
            for stun in DefaultSTUNServers.get_all():
                self._config.add_stun(stun.host, stun.port, stun.name)

    def add_stun_server(self, host: str, port: int, name: str = "") -> None:
        """添加 STUN 服务器"""
        self._config.add_stun(host, port, name)

    def add_turn_server(
        self,
        host: str,
        port: int,
        username: str = "",
        password: str = "",
        realm: str = "collaboration-suite",
        use_tls: bool = False
    ) -> None:
        """添加 TURN 服务器"""
        self._config.add_turn(host, port, username, password, realm, use_tls)

    def get_ice_config(self) -> ICEServerConfig:
        """获取 ICE 服务器配置"""
        return self._config

    def get_ice_servers_for_webRTC(self) -> List[Dict]:
        """获取 WebRTC 格式的 ICE 服务器配置"""
        return self._config.get_ice_servers()

    def allocate_turn_port(
        self,
        username: str,
        lifetime: Optional[int] = None
    ) -> Optional[TURNAllocation]:
        """为用户分配 TURN 端口"""
        if lifetime is None:
            lifetime = self.default_turn_lifetime

        realm = self._credential_generator.realm
        return self._port_allocator.allocate(username, realm, lifetime)

    def release_turn_port(self, username: str) -> bool:
        """释放用户的 TURN 端口"""
        return self._port_allocator.release(
            username,
            self._credential_generator.realm
        )

    def generate_turn_credentials(
        self,
        username: str,
        lifetime: Optional[int] = None
    ) -> Tuple[str, str]:
        """生成 TURN 凭证"""
        if lifetime is None:
            lifetime = self.default_turn_lifetime

        return self._credential_generator.generate_credentials(username, lifetime)

    def verify_turn_credentials(self, username: str, password: str) -> bool:
        """验证 TURN 凭证"""
        return self._credential_generator.verify_credentials(username, password)

    def cleanup(self) -> Tuple[int, int]:
        """清理过期的分配和凭证，返回清理的数量"""
        alloc_count = self._port_allocator.cleanup_expired()
        cred_count = self._credential_generator.cleanup_expired()
        return alloc_count, cred_count

    @property
    def turn_allocation_count(self) -> int:
        """当前 TURN 分配数量"""
        return self._port_allocator.allocation_count


# 全局配置实例
_default_config: Optional[STUNTurnConfig] = None


def get_default_config() -> STUNTurnConfig:
    """获取默认配置实例（单例）"""
    global _default_config
    if _default_config is None:
        _default_config = STUNTurnConfig()
    return _default_config


def setup_stun_turn_config(
    use_builtin_stun: bool = True,
    use_builtin_turn: bool = False,
    custom_stun_servers: List[Tuple[str, int]] = None,
    custom_turn_servers: List[Tuple[str, int, str, str]] = None
) -> STUNTurnConfig:
    """
    设置并返回 STUN/TURN 配置

    Args:
        use_builtin_stun: 是否使用内置 STUN 服务器
        use_builtin_turn: 是否使用内置 TURN 服务器
        custom_stun_servers: 自定义 STUN 服务器列表 [(host, port), ...]
        custom_turn_servers: 自定义 TURN 服务器列表 [(host, port, username, password), ...]

    Returns:
        配置好的 STUNTurnConfig 实例
    """
    config = STUNTurnConfig(
        use_builtin_stun=use_builtin_stun,
        use_builtin_turn=use_builtin_turn
    )

    if custom_stun_servers:
        for host, port in custom_stun_servers:
            config.add_stun_server(host, port)

    if custom_turn_servers:
        for host, port, username, password in custom_turn_servers:
            config.add_turn_server(host, port, username, password)

    return config
