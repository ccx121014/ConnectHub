"""
客户端 NAT 穿透模块

提供 WebRTC NAT 穿透能力，包括 ICE 候选者收集、
PeerConnection 设置和自动 TURN 回退功能。
"""

import asyncio
import logging
from typing import Optional, List, Dict, Any, Callable, Awaitable
from dataclasses import dataclass, field
from enum import Enum
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaPlayer, MediaRelay
from aiortc.rtcconfiguration import RTCConfiguration, RTCIceServer
from aiortc.rtcicetransport import RTCIceCandidate, RTCIceCandidateInit

logger = logging.getLogger(__name__)


class NATTraversalState(Enum):
    """NAT 穿透状态"""
    IDLE = "idle"
    GATHERING = "gathering"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    FAILED = "failed"
    CLOSED = "closed"


@dataclass
class WebRTCConfig:
    """WebRTC 配置"""
    ice_servers: List[Dict[str, Any]] = field(default_factory=list)
    ice_transport_policy: str = "all"  # "all", "relay", "public"
    bundle_policy: str = "balanced"  # "balanced", "maxbundle", "maxcompat"
    rtcp_mux_policy: str = "require"  # "require", "negotiate"

    def to_rtc_configuration(self) -> RTCConfiguration:
        """转换为 aiortc RTCConfiguration"""
        rtc_ice_servers = []

        for server in self.ice_servers:
            urls = server.get("urls", [])
            if isinstance(urls, str):
                urls = [urls]

            rtc_server = RTCIceServer(
                urls=urls,
                username=server.get("username"),
                credential=server.get("credential")
            )
            rtc_ice_servers.append(rtc_server)

        return RTCConfiguration(
            iceServers=rtc_ice_servers,
            iceTransportPolicy=self.ice_transport_policy,
            bundlePolicy=self.bundle_policy,
            rtcpMuxPolicy=self.rtcp_mux_policy
        )


@dataclass
class ICECandidateData:
    """ICE 候选者数据"""
    candidate: str
    sdpMid: Optional[str] = None
    sdpMLineIndex: Optional[int] = None
    usernameFragment: Optional[str] = None


@dataclass
class PeerConnectionInfo:
    """对等连接信息"""
    pc: RTCPeerConnection
    state: NATTraversalState
    local_candidates: List[ICECandidateData] = field(default_factory=list)
    remote_candidates: List[ICECandidateData] = field(default_factory=list)
    data_channel: Optional[Any] = None


class NATTraversalManager:
    """
    NAT 穿透管理器

    负责管理 WebRTC PeerConnection、ICE 候选者收集
    和 NAT 穿透逻辑
    """

    def __init__(
        self,
        ice_servers: Optional[List[Dict[str, Any]]] = None,
        ice_transport_policy: str = "all"
    ):
        """
        初始化 NAT 穿透管理器

        Args:
            ice_servers: ICE 服务器配置列表
            ice_transport_policy: ICE 传输策略
        """
        self._default_ice_servers = ice_servers or self._get_default_ice_servers()
        self._ice_transport_policy = ice_transport_policy

        # 对等连接管理
        self._connections: Dict[str, PeerConnectionInfo] = {}
        self._lock = asyncio.Lock()

        # 媒体 relay（用于转发）
        self._relay: Optional[MediaRelay] = None

        # 回调函数
        self._on_candidate_callbacks: Dict[str, Callable] = {}
        self._on_connection_state_callbacks: Dict[str, Callable] = {}
        self._on_data_channel_callbacks: Dict[str, Callable] = {}

        logger.info("NAT 穿透管理器已初始化")

    def _get_default_ice_servers(self) -> List[Dict[str, Any]]:
        """获取默认 ICE 服务器配置"""
        return [
            {"urls": ["stun:stun.l.google.com:19302"]},
            {"urls": ["stun:stun1.l.google.com:19302"]},
            {"urls": ["stun:stun2.l.google.com:19302"]},
        ]

    def set_ice_servers(self, ice_servers: List[Dict[str, Any]]) -> None:
        """设置 ICE 服务器"""
        self._default_ice_servers = ice_servers
        logger.debug(f"ICE 服务器已更新: {len(ice_servers)} 个服务器")

    def get_webrtc_config(
        self,
        ice_servers: Optional[List[Dict[str, Any]]] = None,
        ice_transport_policy: Optional[str] = None
    ) -> WebRTCConfig:
        """
        获取 WebRTC 配置

        Args:
            ice_servers: 自定义 ICE 服务器（使用默认如果为 None）
            ice_transport_policy: 自定义传输策略

        Returns:
            WebRTCConfig 实例
        """
        servers = ice_servers if ice_servers is not None else self._default_ice_servers
        policy = ice_transport_policy or self._ice_transport_policy

        return WebRTCConfig(
            ice_servers=servers,
            ice_transport_policy=policy
        )

    async def create_peer_connection(
        self,
        connection_id: str,
        webrtc_config: Optional[WebRTCConfig] = None
    ) -> RTCPeerConnection:
        """
        创建 WebRTC PeerConnection

        Args:
            connection_id: 连接 ID
            webrtc_config: WebRTC 配置

        Returns:
            RTCPeerConnection 实例
        """
        async with self._lock:
            # 如果已存在，先关闭
            if connection_id in self._connections:
                await self.close_peer_connection(connection_id)

            config = webrtc_config or self.get_webrtc_config()
            rtc_config = config.to_rtc_configuration()

            pc = RTCPeerConnection(rtc_config)

            # 创建连接信息
            conn_info = PeerConnectionInfo(
                pc=pc,
                state=NATTraversalState.GATHERING
            )

            # 设置 ICE 候选者回调
            @pc.on("icecandidate")
            def on_ice_candidate(candidate: Optional[RTCIceCandidate]):
                if candidate:
                    candidate_data = ICECandidateData(
                        candidate=candidate.candidate,
                        sdpMid=candidate.sdpMid,
                        sdpMLineIndex=candidate.sdpMLineIndex
                    )
                    conn_info.local_candidates.append(candidate_data)
                    self._notify_candidate(connection_id, candidate_data)

            # 设置连接状态回调
            @pc.on("iceconnectionstatechange")
            def on_ice_connection_state_change():
                state = pc.iceConnectionState
                logger.debug(f"ICE 连接状态变更 [{connection_id}]: {state}")

                if state == "checking":
                    conn_info.state = NATTraversalState.CONNECTING
                elif state == "connected":
                    conn_info.state = NATTraversalState.CONNECTED
                elif state == "completed":
                    conn_info.state = NATTraversalState.CONNECTED
                elif state == "failed":
                    conn_info.state = NATTraversalState.FAILED
                    logger.warning(f"ICE 连接失败 [{connection_id}]，可能需要 TURN 中继")
                elif state == "disconnected":
                    conn_info.state = NATTraversalState.FAILED
                elif state == "closed":
                    conn_info.state = NATTraversalState.CLOSED

                self._notify_connection_state(connection_id, conn_info.state)

            # 设置数据通道回调
            @pc.on("datachannel")
            def on_datachannel(channel):
                conn_info.data_channel = channel
                self._notify_data_channel(connection_id, channel)
                logger.debug(f"数据通道已创建 [{connection_id}]")

            self._connections[connection_id] = conn_info
            logger.info(f"PeerConnection 已创建 [{connection_id}]")

            return pc

    async def close_peer_connection(self, connection_id: str) -> bool:
        """
        关闭 PeerConnection

        Args:
            connection_id: 连接 ID

        Returns:
            是否成功关闭
        """
        async with self._lock:
            conn_info = self._connections.get(connection_id)
            if not conn_info:
                return False

            try:
                await conn_info.pc.close()
                conn_info.state = NATTraversalState.CLOSED
                logger.info(f"PeerConnection 已关闭 [{connection_id}]")
            except Exception as e:
                logger.error(f"关闭 PeerConnection 失败 [{connection_id}]: {e}")
            finally:
                if connection_id in self._connections:
                    del self._connections[connection_id]

            # 清理回调
            self._on_candidate_callbacks.pop(connection_id, None)
            self._on_connection_state_callbacks.pop(connection_id, None)
            self._on_data_channel_callbacks.pop(connection_id, None)

            return True

    async def create_offer(
        self,
        connection_id: str,
        webrtc_config: Optional[WebRTCConfig] = None
    ) -> RTCSessionDescription:
        """
        创建 SDP Offer

        Args:
            connection_id: 连接 ID
            webrtc_config: WebRTC 配置

        Returns:
            RTCSessionDescription (offer)
        """
        async with self._lock:
            conn_info = self._connections.get(connection_id)

            if not conn_info:
                # 自动创建连接
                await self.create_peer_connection(connection_id, webrtc_config)
                conn_info = self._connections[connection_id]

            try:
                offer = await conn_info.pc.createOffer()
                await conn_info.pc.setLocalDescription(offer)

                conn_info.state = NATTraversalState.GATHERING
                logger.info(f"Offer 已创建 [{connection_id}]")

                return conn_info.pc.localDescription

            except Exception as e:
                logger.error(f"创建 Offer 失败 [{connection_id}]: {e}")
                raise

    async def create_answer(
        self,
        connection_id: str,
        offer: RTCSessionDescription,
        webrtc_config: Optional[WebRTCConfig] = None
    ) -> RTCSessionDescription:
        """
        创建 SDP Answer

        Args:
            connection_id: 连接 ID
            offer: 收到的 offer
            webrtc_config: WebRTC 配置

        Returns:
            RTCSessionDescription (answer)
        """
        async with self._lock:
            conn_info = self._connections.get(connection_id)

            if not conn_info:
                await self.create_peer_connection(connection_id, webrtc_config)
                conn_info = self._connections[connection_id]

            try:
                await conn_info.pc.setRemoteDescription(offer)

                answer = await conn_info.pc.createAnswer()
                await conn_info.pc.setLocalDescription(answer)

                conn_info.state = NATTraversalState.GATHERING
                logger.info(f"Answer 已创建 [{connection_id}]")

                return conn_info.pc.localDescription

            except Exception as e:
                logger.error(f"创建 Answer 失败 [{connection_id}]: {e}")
                raise

    async def set_remote_description(
        self,
        connection_id: str,
        session_description: RTCSessionDescription
    ) -> None:
        """
        设置远程会话描述

        Args:
            connection_id: 连接 ID
            session_description: SDP 描述
        """
        async with self._lock:
            conn_info = self._connections.get(connection_id)
            if not conn_info:
                raise ValueError(f"连接不存在: {connection_id}")

            try:
                await conn_info.pc.setRemoteDescription(session_description)
                logger.debug(f"远程描述已设置 [{connection_id}]")
            except Exception as e:
                logger.error(f"设置远程描述失败 [{connection_id}]: {e}")
                raise

    async def add_ice_candidate(
        self,
        connection_id: str,
        candidate_data: ICECandidateData
    ) -> bool:
        """
        添加 ICE 候选者

        Args:
            connection_id: 连接 ID
            candidate_data: ICE 候选者数据

        Returns:
            是否成功添加
        """
        async with self._lock:
            conn_info = self._connections.get(connection_id)
            if not conn_info:
                logger.warning(f"连接不存在，无法添加候选者: {connection_id}")
                return False

            try:
                candidate = RTCIceCandidate(
                    candidate=candidate_data.candidate,
                    sdpMid=candidate_data.sdpMid,
                    sdpMLineIndex=candidate_data.sdpMLineIndex,
                    usernameFragment=candidate_data.usernameFragment
                )

                await conn_info.pc.addIceCandidate(candidate)
                conn_info.remote_candidates.append(candidate_data)

                logger.debug(f"ICE 候选者已添加 [{connection_id}]: "
                           f"{candidate.candidate[:50]}...")
                return True

            except Exception as e:
                logger.error(f"添加 ICE 候选者失败 [{connection_id}]: {e}")
                return False

    def get_ice_candidates(self, connection_id: str) -> List[ICECandidateData]:
        """
        获取指定连接的 ICE 候选者

        Args:
            connection_id: 连接 ID

        Returns:
            候选者列表
        """
        conn_info = self._connections.get(connection_id)
        if not conn_info:
            return []

        return conn_info.local_candidates.copy()

    def get_connection_state(self, connection_id: str) -> Optional[NATTraversalState]:
        """
        获取连接状态

        Args:
            connection_id: 连接 ID

        Returns:
            NATTraversalState 或 None
        """
        conn_info = self._connections.get(connection_id)
        return conn_info.state if conn_info else None

    async def create_data_channel(
        self,
        connection_id: str,
        label: str = "data",
        ordered: bool = True
    ) -> Any:
        """
        创建数据通道

        Args:
            connection_id: 连接 ID
            label: 通道标签
            ordered: 是否有序传输

        Returns:
            RTCDataChannel
        """
        async with self._lock:
            conn_info = self._connections.get(connection_id)
            if not conn_info:
                raise ValueError(f"连接不存在: {connection_id}")

            try:
                channel = conn_info.pc.createDataChannel(
                    label,
                    ordered=ordered
                )
                conn_info.data_channel = channel
                logger.info(f"数据通道已创建 [{connection_id}]: {label}")
                return channel

            except Exception as e:
                logger.error(f"创建数据通道失败 [{connection_id}]: {e}")
                raise

    def register_candidate_callback(
        self,
        connection_id: str,
        callback: Callable[[ICECandidateData], Awaitable]
    ) -> None:
        """注册候选者回调"""
        self._on_candidate_callbacks[connection_id] = callback

    def register_connection_state_callback(
        self,
        connection_id: str,
        callback: Callable[[NATTraversalState], Awaitable]
    ) -> None:
        """注册连接状态回调"""
        self._on_connection_state_callbacks[connection_id] = callback

    def register_data_channel_callback(
        self,
        connection_id: str,
        callback: Callable[[Any], Awaitable]
    ) -> None:
        """注册数据通道回调"""
        self._on_data_channel_callbacks[connection_id] = callback

    def _notify_candidate(self, connection_id: str, candidate: ICECandidateData) -> None:
        """通知候选者回调"""
        callback = self._on_candidate_callbacks.get(connection_id)
        if callback:
            try:
                asyncio.create_task(callback(candidate))
            except Exception as e:
                logger.error(f"调用候选者回调失败 [{connection_id}]: {e}")

    def _notify_connection_state(
        self,
        connection_id: str,
        state: NATTraversalState
    ) -> None:
        """通知连接状态回调"""
        callback = self._on_connection_state_callbacks.get(connection_id)
        if callback:
            try:
                asyncio.create_task(callback(state))
            except Exception as e:
                logger.error(f"调用连接状态回调失败 [{connection_id}]: {e}")

    def _notify_data_channel(self, connection_id: str, channel: Any) -> None:
        """通知数据通道回调"""
        callback = self._on_data_channel_callbacks.get(connection_id)
        if callback:
            try:
                asyncio.create_task(callback(channel))
            except Exception as e:
                logger.error(f"调用数据通道回调失败 [{connection_id}]: {e}")

    async def close_all(self) -> None:
        """关闭所有连接"""
        connection_ids = list(self._connections.keys())
        for connection_id in connection_ids:
            await self.close_peer_connection(connection_id)

        logger.info("所有连接已关闭")

    @property
    def connection_count(self) -> int:
        """当前连接数量"""
        return len(self._connections)


class TurnRelayManager:
    """
    TURN 中继管理器

    管理 TURN 凭证和自动回退到 TURN 中继
    """

    def __init__(self, manager: NATTraversalManager):
        self._manager = manager
        self._turn_credentials: Dict[str, tuple] = {}  # connection_id -> (username, password)
        self._turn_servers: List[Dict[str, Any]] = []

    def set_turn_servers(self, servers: List[Dict[str, Any]]) -> None:
        """设置 TURN 服务器列表"""
        self._turn_servers = servers
        logger.debug(f"TURN 服务器已设置: {len(servers)} 个")

    async def get_turn_config_for_connection(
        self,
        connection_id: str
    ) -> Optional[WebRTCConfig]:
        """
        获取使用 TURN 的配置（用于回退）

        Args:
            connection_id: 连接 ID

        Returns:
            包含 TURN 的 WebRTCConfig 或 None
        """
        if not self._turn_credentials.get(connection_id):
            return None

        username, password = self._turn_credentials[connection_id]

        # 构建包含 TURN 的 ICE 服务器列表
        ice_servers = []
        for server in self._turn_servers:
            ice_servers.append({
                "urls": server.get("urls", []),
                "username": username,
                "credential": password
            })

        # 如果没有 TURN 服务器，添加公共 TURN 服务器
        if not ice_servers:
            ice_servers.extend([
                {
                    "urls": ["turn:turn.example.com:3478"],
                    "username": username,
                    "credential": password
                }
            ])

        return WebRTCConfig(
            ice_servers=ice_servers,
            ice_transport_policy="relay"  # 只使用中继
        )

    async def fallback_to_turn(
        self,
        connection_id: str
    ) -> bool:
        """
        回退到 TURN 中继

        Args:
            connection_id: 连接 ID

        Returns:
            是否成功回退
        """
        logger.info(f"尝试回退到 TURN 中继 [{connection_id}]")

        current_state = self._manager.get_connection_state(connection_id)
        if current_state == NATTraversalState.CONNECTED:
            logger.info(f"连接已建立，无需 TURN 回退 [{connection_id}]")
            return False

        # 获取 TURN 配置
        turn_config = await self.get_turn_config_for_connection(connection_id)
        if not turn_config:
            logger.warning(f"无可用 TURN 配置 [{connection_id}]")
            return False

        # 关闭旧连接
        await self._manager.close_peer_connection(connection_id)

        # 创建新连接
        await self._manager.create_peer_connection(connection_id, turn_config)

        logger.info(f"TURN 回退已触发 [{connection_id}]")
        return True

    def set_credentials(self, connection_id: str, username: str, password: str) -> None:
        """设置 TURN 凭证"""
        self._turn_credentials[connection_id] = (username, password)
        logger.debug(f"TURN 凭证已设置 [{connection_id}]")

    def clear_credentials(self, connection_id: str) -> None:
        """清除 TURN 凭证"""
        if connection_id in self._turn_credentials:
            del self._turn_credentials[connection_id]


class ICEGatherer:
    """
    ICE 候选者收集器

    独立于 PeerConnection 的候选者收集
    """

    def __init__(self, ice_servers: List[Dict[str, Any]]):
        self._ice_servers = ice_servers
        self._candidates: List[ICECandidateData] = []
        self._gathering_complete = False
        self._lock = asyncio.Lock()

    async def gather(self) -> List[ICECandidateData]:
        """
        收集 ICE 候选者

        Returns:
            候选者列表
        """
        async with self._lock:
            self._candidates.clear()
            self._gathering_complete = False

            # 使用 RTCPeerConnection 收集候选者
            config = WebRTCConfig(ice_servers=self._ice_servers)
            pc = RTCPeerConnection(config.to_rtc_configuration())

            gathering_task = asyncio.create_task(self._wait_for_gathering(pc))

            try:
                # 创建并设置 offer
                offer = await pc.createOffer()
                await pc.setLocalDescription(offer)

                # 等待候选者收集完成
                await gathering_task

            finally:
                await pc.close()

            self._gathering_complete = True
            return self._candidates.copy()

    async def _wait_for_gathering(self, pc: RTCPeerConnection) -> None:
        """等待候选者收集完成"""
        while True:
            if pc.iceGatheringState == "complete":
                break

            async def on_candidate(candidate: Optional[RTCIceCandidate]):
                if candidate:
                    self._candidates.append(ICECandidateData(
                        candidate=candidate.candidate,
                        sdpMid=candidate.sdpMid,
                        sdpMLineIndex=candidate.sdpMLineIndex
                    ))

            @pc.on("icecandidate")
            def handler(c: Optional[RTCIceCandidate]):
                if c:
                    self._candidates.append(ICECandidateData(
                        candidate=c.candidate,
                        sdpMid=c.sdpMid,
                        sdpMLineIndex=c.sdpMLineIndex
                    ))

            await asyncio.sleep(0.1)

    @property
    def gathering_complete(self) -> bool:
        """是否收集完成"""
        return self._gathering_complete


# 便捷函数

def create_nat_traversal_manager(
    ice_servers: Optional[List[Dict[str, Any]]] = None,
    ice_transport_policy: str = "all"
) -> NATTraversalManager:
    """
    创建 NAT 穿透管理器

    Args:
        ice_servers: ICE 服务器列表
        ice_transport_policy: ICE 传输策略

    Returns:
        NATTraversalManager 实例
    """
    return NATTraversalManager(
        ice_servers=ice_servers,
        ice_transport_policy=ice_transport_policy
    )


def create_turn_relay_manager(
    manager: NATTraversalManager
) -> TurnRelayManager:
    """
    创建 TURN 中继管理器

    Args:
        manager: NATTraversalManager 实例

    Returns:
        TurnRelayManager 实例
    """
    return TurnRelayManager(manager)
