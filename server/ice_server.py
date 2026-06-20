"""
ICE/STUN/TURN 服务器模块

提供内置 STUN 服务器和 TURN 中继服务器功能，
使用 aioice 库实现 NAT 穿透能力。
"""

import asyncio
import logging
import json
from typing import Optional, List, Dict, Any, Callable, Awaitable
from dataclasses import dataclass, field
from enum import Enum
from contextlib import asynccontextmanager

import aioice
from aioice.utils import random_port

from stun_turn_config import (
    STUNTurnConfig,
    ICEServerConfig,
    STUNServer,
    TURNServer,
    get_default_config
)

logger = logging.getLogger(__name__)


class ICEConnectionState(Enum):
    """ICE 连接状态"""
    NEW = "new"
    CHECKING = "checking"
    CONNECTED = "connected"
    COMPLETED = "completed"
    FAILED = "failed"
    DISCONNECTED = "disconnected"
    CLOSED = "closed"


@dataclass
class ICECandidate:
    """ICE 候选者"""
    foundation: str
    component: int
    protocol: str  # "udp" or "tcp"
    priority: int
    host: str
    port: int
    type: str  # "host", "srflx", "prflx", "relay"
    rel_addr: str = ""
    rel_port: int = 0
    tcp_type: str = ""  # "active", "passive", "so"

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        result = {
            "foundation": self.foundation,
            "component": self.component,
            "protocol": self.protocol,
            "priority": self.priority,
            "host": self.host,
            "port": self.port,
            "type": self.type,
        }
        if self.rel_addr:
            result["relatedAddress"] = self.rel_addr
        if self.rel_port:
            result["relatedPort"] = self.rel_port
        if self.tcp_type:
            result["tcpType"] = self.tcp_type
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ICECandidate":
        """从字典创建"""
        return cls(
            foundation=data.get("foundation", ""),
            component=data.get("component", 1),
            protocol=data.get("protocol", "udp"),
            priority=data.get("priority", 0),
            host=data.get("host", ""),
            port=data.get("port", 0),
            type=data.get("type", "host"),
            rel_addr=data.get("relatedAddress", ""),
            rel_port=data.get("relatedPort", 0),
            tcp_type=data.get("tcpType", "")
        )


@dataclass
class SessionInfo:
    """ICE 会话信息"""
    session_id: str
    username: str
    created_at: float
    ice_config: ICEServerConfig
    state: ICEConnectionState = ICEConnectionState.NEW
    remote_candidates: List[ICECandidate] = field(default_factory=list)
    local_candidates: List[ICECandidate] = field(default_factory=list)


class STUNServerProtocol:
    """STUN 服务器协议处理器"""

    def __init__(self, server: "BuiltInSTUNServer"):
        self.server = server

    async def handle_binding_request(
        self,
        message: aioice.stun.Message,
        addr: tuple
    ) -> Optional[aioice.stun.Message]:
        """处理 Binding 请求"""
        # 创建响应
        response = aioice.stun.Message(
            message_type=aioice.stun.MessageType.BINDING_RESPONSE,
            transaction_id=message.transaction_id
        )

        # 添加 XOR-MAPPED-ADDRESS 属性
        response.attributes["XOR-MAPPED-ADDRESS"] = (
            aioice.stun.Attribute(
                aioice.stun.AttributeType.XOR_MAPPED_ADDRESS,
                aioice.stun.XorMappedAddress(
                    addr[0],
                    addr[1],
                    message.transaction_id
                )
            )
        )

        # 添加 MAPPED-ADDRESS 属性（兼容性）
        response.attributes["MAPPED-ADDRESS"] = (
            aioice.stun.Attribute(
                aioice.stun.AttributeType.MAPPED_ADDRESS,
                aioice.stun.MappedAddress(addr[0], addr[1])
            )
        )

        return response


class BuiltInSTUNServer:
    """
    内置 STUN 服务器

    使用 aioice 库提供 STUN 服务能力
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 3478,
        config: Optional[STUNTurnConfig] = None
    ):
        self.host = host
        self.port = port
        self.config = config or get_default_config()
        self._server: Optional[asyncio.DatagramTransport] = None
        self._protocol: Optional[STUNServerProtocol] = None
        self._running = False

    async def start(self) -> None:
        """启动 STUN 服务器"""
        if self._running:
            logger.warning("STUN 服务器已在运行")
            return

        loop = asyncio.get_event_loop()
        self._protocol = STUNServerProtocol(self)

        self._server = await loop.create_datagram_endpoint(
            lambda: STUNDatagramProtocol(self._protocol),
            local_addr=(self.host, self.port)
        )

        self._running = True
        logger.info(f"STUN 服务器已启动: {self.host}:{self.port}")

    async def stop(self) -> None:
        """停止 STUN 服务器"""
        if self._server:
            self._server[1].close()
            self._server = None
            self._running = False
            logger.info("STUN 服务器已停止")

    @property
    def is_running(self) -> bool:
        """检查服务器是否运行中"""
        return self._running


class STUNDatagramProtocol(asyncio.DatagramProtocol):
    """STUN 数据报协议"""

    def __init__(self, handler: STUNServerProtocol):
        self.handler = handler
        self._buffer = b""

    def datagram_received(self, data: bytes, addr: tuple) -> None:
        """接收数据报"""
        asyncio.create_task(self._process_datagram(data, addr))

    async def _process_datagram(self, data: bytes, addr: tuple) -> None:
        """处理数据报"""
        try:
            message = aioice.stun.parse_message(data)

            if message.message_type == aioice.stun.MessageType.BINDING_REQUEST:
                response = await self.handler.handle_binding_request(
                    message, addr
                )
                if response:
                    response_data = aioice.stun.build_message(response)
                    if self.transport:
                        self.transport.sendto(response_data, addr)

        except Exception as e:
            logger.error(f"处理 STUN 数据报失败: {e}")


class TURNAuthHandler:
    """TURN 认证处理器"""

    def __init__(self, config: Optional[STUNTurnConfig] = None):
        self.config = config or get_default_config()

    def create_permission(
        self,
        username: str,
        realm: str,
        nonce: str
    ) -> Optional[str]:
        """创建权限令牌"""
        allocation = self.config.allocate_turn_port(username)
        if allocation:
            return allocation.nonce
        return None

    def verify(self, username: str, realm: str, nonce: str) -> bool:
        """验证请求"""
        allocation = self.config._port_allocator.get_allocation(username, realm)
        if allocation and allocation.nonce == nonce:
            if allocation.expires_at > asyncio.get_event_loop().time():
                return True
        return False


class TurnChannelData:
    """TURN 通道数据"""

    def __init__(self, channel_id: int, peer_addr: tuple):
        self.channel_id = channel_id
        self.peer_addr = peer_addr
        self.data = b""
        self.last_activity = asyncio.get_event_loop().time()


class BuiltInTURNServer:
    """
    内置 TURN 中继服务器

    使用 aioice 库提供 TURN 中继服务能力
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 3478,
        config: Optional[STUNTurnConfig] = None,
        max_bandwidth: int = 10 * 1024 * 1024  # 10 Mbps
    ):
        self.host = host
        self.port = port
        self.config = config or get_default_config()
        self.max_bandwidth = max_bandwidth

        self._server: Optional[asyncio.DatagramTransport] = None
        self._running = False
        self._auth_handler = TURNAuthHandler(self.config)

        # 通道管理
        self._channels: Dict[int, TurnChannelData] = {}
        self._next_channel_id = 0x4000

        # 中继传输
        self._relay_transports: Dict[str, asyncio.DatagramTransport] = {}

    async def start(self) -> None:
        """启动 TURN 服务器"""
        if self._running:
            logger.warning("TURN 服务器已在运行")
            return

        loop = asyncio.get_event_loop()
        self._server = await loop.create_datagram_endpoint(
            lambda: TURNDatagramProtocol(self),
            local_addr=(self.host, self.port)
        )

        self._running = True
        logger.info(f"TURN 服务器已启动: {self.host}:{self.port}")

    async def stop(self) -> None:
        """停止 TURN 服务器"""
        if self._server:
            self._server[1].close()
            self._server = None

        # 关闭所有中继传输
        for transport in self._relay_transports.values():
            transport.close()

        self._relay_transports.clear()
        self._running = False
        logger.info("TURN 服务器已停止")

    @property
    def is_running(self) -> bool:
        """检查服务器是否运行中"""
        return self._running

    async def handle_allocate_request(
        self,
        username: str,
        realm: str,
        nonce: str,
        requested_port: int = 0
    ) -> Optional[Dict[str, Any]]:
        """处理 Allocate 请求"""
        if not self._auth_handler.verify(username, realm, nonce):
            return None

        allocation = self.config.allocate_turn_port(username)
        if not allocation:
            return None

        return {
            "xor_relayed_address": (self.host, allocation.port_range[0]),
            "xor_mapped_address": (self.host, random_port()),
            "lifetime": int(allocation.expires_at - asyncio.get_event_loop().time()),
            "bandwidth": allocation.bandwidth_limit or self.max_bandwidth
        }

    async def handle_create_permission(
        self,
        username: str,
        realm: str,
        nonce: str,
        peer_addr: tuple
    ) -> bool:
        """处理 CreatePermission 请求"""
        if not self._auth_handler.verify(username, realm, nonce):
            return False

        permission_key = f"{username}:{peer_addr[0]}"
        logger.debug(f"创建权限: {permission_key}")
        return True

    def allocate_channel(self, peer_addr: tuple) -> Optional[int]:
        """分配通道ID"""
        # 检查是否已有相同对等方的通道
        for channel_id, channel in self._channels.items():
            if channel.peer_addr == peer_addr:
                return channel_id

        # 创建新通道
        if self._next_channel_id > 0x7FFF:
            self._next_channel_id = 0x4000

        channel_id = self._next_channel_id
        self._next_channel_id += 1

        self._channels[channel_id] = TurnChannelData(channel_id, peer_addr)
        logger.debug(f"分配通道 {channel_id:04x} -> {peer_addr}")

        return channel_id

    def get_channel(self, channel_id: int) -> Optional[TurnChannelData]:
        """获取通道数据"""
        return self._channels.get(channel_id)


class TURNProtocolHandler:
    """TURN 协议处理器"""

    def __init__(self, server: BuiltInTURNServer):
        self.server = server

    async def handle_message(
        self,
        message: aioice.stun.Message,
        addr: tuple
    ) -> Optional[aioice.stun.Message]:
        """处理 TURN 消息"""
        # 这里需要实现完整的 TURN 协议处理
        # 简化版本，实际使用时需要完整实现 RFC 5766
        logger.debug(f"处理 TURN 消息: {message.message_type}")
        return None


class TURNDatagramProtocol(asyncio.DatagramProtocol):
    """TURN 数据报协议"""

    def __init__(self, server: BuiltInTURNServer):
        self.server = server
        self._handler = TURNProtocolHandler(server)

    def datagram_received(self, data: bytes, addr: tuple) -> None:
        """接收数据报"""
        asyncio.create_task(self._process_datagram(data, addr))

    async def _process_datagram(self, data: bytes, addr: tuple) -> None:
        """处理数据报"""
        try:
            # 检查是否为通道数据（以通道ID开头）
            if len(data) >= 4:
                channel_id = int.from_bytes(data[:4], "big")
                if 0x4000 <= channel_id <= 0x7FFF:
                    await self._handle_channel_data(data, addr, channel_id)
                    return

            # 解析 STUN/TURN 消息
            message = aioice.stun.parse_message(data)
            response = await self._handler.handle_message(message, addr)

            if response and self.transport:
                response_data = aioice.stun.build_message(response)
                self.transport.sendto(response_data, addr)

        except Exception as e:
            logger.error(f"处理 TURN 数据报失败: {e}")

    async def _handle_channel_data(
        self,
        data: bytes,
        addr: tuple,
        channel_id: int
    ) -> None:
        """处理通道数据"""
        channel = self.server.get_channel(channel_id)
        if not channel:
            logger.warning(f"未知通道: {channel_id:04x}")
            return

        # 转发数据到目标对等方
        relay_key = f"{addr[0]}:{channel.peer_addr[0]}"
        if relay_key in self.server._relay_transports:
            relay = self.server._relay_transports[relay_key]
            relay.sendto(data[4:], channel.peer_addr)


class ICEServer:
    """
    ICE 服务器主类

    整合 STUN 和 TURN 服务器，提供完整的 ICE 服务能力
    """

    def __init__(
        self,
        config: Optional[STUNTurnConfig] = None,
        stun_host: str = "0.0.0.0",
        stun_port: int = 3478,
        turn_host: str = "0.0.0.0",
        turn_port: int = 3479,
        enable_stun: bool = True,
        enable_turn: bool = False
    ):
        self.config = config or get_default_config()

        self.stun_host = stun_host
        self.stun_port = stun_port
        self.turn_host = turn_host
        self.turn_port = turn_port

        self.enable_stun = enable_stun
        self.enable_turn = enable_turn

        self._stun_server: Optional[BuiltInSTUNServer] = None
        self._turn_server: Optional[BuiltInTURNServer] = None

        # 会话管理
        self._sessions: Dict[str, SessionInfo] = {}
        self._cleanup_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """启动 ICE 服务器"""
        if self.enable_stun:
            self._stun_server = BuiltInSTUNServer(
                host=self.stun_host,
                port=self.stun_port,
                config=self.config
            )
            await self._stun_server.start()

        if self.enable_turn:
            self._turn_server = BuiltInTURNServer(
                host=self.turn_host,
                port=self.turn_port,
                config=self.config
            )
            await self._turn_server.start()

        # 启动清理任务
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

        logger.info(f"ICE 服务器已启动 (STUN: {self.enable_stun}, TURN: {self.enable_turn})")

    async def stop(self) -> None:
        """停止 ICE 服务器"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        if self._stun_server:
            await self._stun_server.stop()

        if self._turn_server:
            await self._turn_server.stop()

        self._sessions.clear()
        logger.info("ICE 服务器已停止")

    async def _cleanup_loop(self) -> None:
        """定期清理过期数据"""
        while True:
            try:
                await asyncio.sleep(60)  # 每分钟清理一次
                alloc_count, cred_count = self.config.cleanup()
                if alloc_count > 0 or cred_count > 0:
                    logger.debug(f"清理过期数据: 分配={alloc_count}, 凭证={cred_count}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"清理任务失败: {e}")

    def get_ice_servers(self) -> List[Dict[str, Any]]:
        """获取 ICE 服务器配置列表"""
        ice_servers = []

        # 内置 STUN
        if self.enable_stun and self._stun_server and self._stun_server.is_running:
            ice_servers.append({
                "urls": [f"stun:{self.stun_host}:{self.stun_port}"],
                "type": "stun"
            })

        # 内置 TURN
        if self.enable_turn and self._turn_server and self._turn_server.is_running:
            ice_servers.append({
                "urls": [f"turn:{self.turn_host}:{self.turn_port}"],
                "type": "turn"
            })

        # 添加配置的服务器
        ice_servers.extend(self.config.get_ice_servers_for_webRTC())

        return ice_servers

    def get_ice_config_for_client(self) -> Dict[str, Any]:
        """获取客户端使用的 ICE 配置"""
        return {
            "iceServers": self.get_ice_servers(),
            "iceTransportPolicy": "all"
        }

    def create_session(
        self,
        session_id: str,
        username: str,
        ice_config: Optional[ICEServerConfig] = None
    ) -> SessionInfo:
        """创建 ICE 会话"""
        session = SessionInfo(
            session_id=session_id,
            username=username,
            created_at=asyncio.get_event_loop().time(),
            ice_config=ice_config or self.config.get_ice_config()
        )
        self._sessions[session_id] = session
        logger.debug(f"创建 ICE 会话: {session_id}")
        return session

    def get_session(self, session_id: str) -> Optional[SessionInfo]:
        """获取会话"""
        return self._sessions.get(session_id)

    def remove_session(self, session_id: str) -> bool:
        """移除会话"""
        if session_id in self._sessions:
            del self._sessions[session_id]
            logger.debug(f"移除 ICE 会话: {session_id}")
            return True
        return False

    @property
    def session_count(self) -> int:
        """当前会话数量"""
        return len(self._sessions)


class ICEServerManager:
    """ICE 服务器管理器（支持外部 TURN 服务器）"""

    def __init__(self, config: Optional[STUNTurnConfig] = None):
        self.config = config or get_default_config()
        self._server: Optional[ICEServer] = None

    async def start_server(
        self,
        stun_host: str = "0.0.0.0",
        stun_port: int = 3478,
        enable_builtin_stun: bool = True,
        enable_builtin_turn: bool = False,
        external_turn_servers: List[Dict[str, Any]] = None
    ) -> ICEServer:
        """启动 ICE 服务器"""
        # 添加外部 TURN 服务器
        if external_turn_servers:
            for turn in external_turn_servers:
                self.config.add_turn_server(
                    host=turn.get("host", ""),
                    port=turn.get("port", 3478),
                    username=turn.get("username", ""),
                    password=turn.get("password", ""),
                    realm=turn.get("realm", "collaboration-suite"),
                    use_tls=turn.get("use_tls", False)
                )

        self._server = ICEServer(
            config=self.config,
            stun_host=stun_host,
            stun_port=stun_port,
            enable_stun=enable_builtin_stun,
            enable_turn=enable_builtin_turn
        )

        await self._server.start()
        return self._server

    async def stop_server(self) -> None:
        """停止 ICE 服务器"""
        if self._server:
            await self._server.stop()
            self._server = None

    def get_server(self) -> Optional[ICEServer]:
        """获取当前服务器实例"""
        return self._server

    def get_client_config(self) -> Dict[str, Any]:
        """获取客户端配置"""
        if self._server:
            return self._server.get_ice_config_for_client()
        return {"iceServers": []}


# 全局服务器管理器实例
_server_manager: Optional[ICEServerManager] = None


async def start_ice_server(
    stun_host: str = "0.0.0.0",
    stun_port: int = 3478,
    enable_builtin_stun: bool = True,
    enable_builtin_turn: bool = False,
    custom_stun_servers: List[tuple] = None,
    custom_turn_servers: List[dict] = None
) -> ICEServer:
    """
    启动 ICE 服务器的便捷函数

    Args:
        stun_host: STUN 服务器绑定地址
        stun_port: STUN 服务器端口
        enable_builtin_stun: 是否启用内置 STUN
        enable_builtin_turn: 是否启用内置 TURN
        custom_stun_servers: 自定义 STUN 服务器 [(host, port), ...]
        custom_turn_servers: 自定义 TURN 服务器配置

    Returns:
        ICEServer 实例
    """
    global _server_manager

    # 创建配置
    config = setup_stun_turn_config(
        use_builtin_stun=enable_builtin_stun,
        use_builtin_turn=enable_builtin_turn,
        custom_stun_servers=custom_stun_servers,
        custom_turn_servers=custom_turn_servers
    )

    _server_manager = ICEServerManager(config)
    return await _server_manager.start_server(
        stun_host=stun_host,
        stun_port=stun_port,
        enable_builtin_stun=enable_builtin_stun,
        enable_builtin_turn=enable_builtin_turn,
        external_turn_servers=custom_turn_servers
    )


async def stop_ice_server() -> None:
    """停止 ICE 服务器"""
    global _server_manager
    if _server_manager:
        await _server_manager.stop_server()
        _server_manager = None


def get_ice_server_manager() -> Optional[ICEServerManager]:
    """获取服务器管理器实例"""
    return _server_manager
