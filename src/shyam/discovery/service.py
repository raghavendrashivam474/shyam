"""Asynchronous UDP-based Local Peer Discovery Service for Shyam."""

import asyncio
import json
import logging
import socket
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shyam.discovery.model import (
    Peer,
    PeerDiscoveredEvent,
    PeerLostEvent,
    PeerUpdatedEvent,
)
from shyam.events.bus import EventBus
from shyam.identity.manager import IdentityManager

logger = logging.getLogger(__name__)


class DiscoveryProtocol(asyncio.DatagramProtocol):
    """Protocol handler for incoming UDP datagrams."""

    def __init__(self, service: "DiscoveryService") -> None:
        self.service = service

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        """Process an incoming peer UDP broadcast."""
        remote_ip, _ = addr
        self.service.handle_datagram(data, remote_ip)

    def error_received(self, exc: Exception) -> None:
        """Log low-level socket protocol errors."""
        logger.warning("UDP discovery socket error: %s", exc)


class DiscoveryService:
    """Manages UDP broadcast announcements and peer life-cycle tracking."""

    def __init__(
        self,
        identity_manager: IdentityManager,
        event_bus: EventBus,
        broadcast_port: int = 54321,
        broadcast_interval: float = 2.0,
        peer_expiry_interval: float = 6.0,
        bind_host: str = "0.0.0.0",
        broadcast_host: str = "255.255.255.255",
        metadata_provider: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        self._identity_manager = identity_manager
        self._event_bus = event_bus
        self._port = broadcast_port
        self._interval = broadcast_interval
        self._expiry = peer_expiry_interval
        self._bind_host = bind_host
        self._broadcast_host = broadcast_host
        self._metadata_provider = metadata_provider

        self._peers: dict[UUID, Peer] = {}
        self._peers_lock = asyncio.Lock()
        self._transport: asyncio.DatagramTransport | None = None
        self._protocol: DiscoveryProtocol | None = None

        self._running = False
        self._tasks: list[asyncio.Task[Any]] = []

    @property
    def is_running(self) -> bool:
        """Return True if discovery service is actively listening/broadcasting."""
        return self._running

    @property
    def peers(self) -> dict[UUID, Peer]:
        """Snapshot of currently tracked live peers."""
        return dict(self._peers)

    async def start(self) -> None:
        """Start UDP broadcast advertising and peer tracking."""
        if self._running:
            return

        self._running = True
        identity = self._identity_manager.identity
        node_name = identity.node_name if identity else "uninitialized"
        node_id = identity.node_id if identity else "uninitialized"
        logger.info(
            "Starting discovery for node '%s' (%s) on port %d...",
            node_name,
            node_id,
            self._port,
        )

        loop = asyncio.get_running_loop()

        # Create dual broadcast/listen UDP socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        except OSError:
            logger.debug("Broadcast option not supported or rejected on socket")

        sock.setblocking(False)

        try:
            sock.bind((self._bind_host, self._port))
        except OSError as e:
            logger.warning(
                "Could not bind to %s:%d: %s. Falling back to loopback interface.",
                self._bind_host,
                self._port,
                e,
            )
            # Safe local fallback when 0.0.0.0 is prohibited or bound
            self._bind_host = "127.0.0.1"
            self._broadcast_host = "127.0.0.1"
            sock.bind((self._bind_host, self._port))

        # Create datagram transport and attach our custom protocol
        transport, protocol = await loop.create_datagram_endpoint(
            lambda: DiscoveryProtocol(self),
            sock=sock,
        )
        self._transport = transport
        self._protocol = protocol

        # Spawn background loops
        self._tasks.append(asyncio.create_task(self._announce_loop()))
        self._tasks.append(asyncio.create_task(self._reap_loop()))

    async def stop(self) -> None:
        """Gracefully shutdown loops and release socket resources."""
        if not self._running:
            return

        self._running = False
        logger.info("Stopping UDP discovery service...")

        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

        # Close transport/sockets
        if self._transport:
            self._transport.close()
            self._transport = None
        self._protocol = None

        async with self._peers_lock:
            self._peers.clear()

    def handle_datagram(self, data: bytes, remote_ip: str) -> None:
        """Callback to parse peer announcements."""
        try:
            payload = json.loads(data.decode("utf-8"))
            node_id_str = payload.get("node_id")
            node_name = payload.get("node_name")
            port = payload.get("port")
            protocol_version = payload.get("protocol_version", "0.2.0")
            metadata = payload.get("metadata", {})

            if not node_id_str or not node_name or port is None:
                return

            node_id = UUID(node_id_str)
        except (json.JSONDecodeError, ValueError, KeyError, TypeError):
            return  # Ignore corrupted or unrelated local network packets

        # Ignore self announcements
        local_identity = self._identity_manager.identity
        if local_identity and local_identity.node_id == node_id:
            return

        # Fire event notification in background
        asyncio.create_task(
            self._update_peer(
                node_id,
                node_name,
                remote_ip,
                port,
                protocol_version,
                metadata,
            )
        )

    async def _update_peer(
        self,
        node_id: UUID,
        node_name: str,
        ip: str,
        port: int,
        protocol_version: str,
        metadata: dict[str, Any],
    ) -> None:
        now = datetime.now(UTC)
        async with self._peers_lock:
            existing_peer = self._peers.get(node_id)
            if existing_peer is None:
                new_peer = Peer(
                    node_id=node_id,
                    node_name=node_name,
                    address=ip,
                    port=port,
                    protocol_version=protocol_version,
                    discovered_at=now,
                    last_seen=now,
                    metadata=metadata,
                )
                self._peers[node_id] = new_peer
                logger.info("Discovered new peer: %s (%s) @ %s:%d", node_name, node_id, ip, port)
                await self._event_bus.publish(PeerDiscoveredEvent(peer=new_peer))
            else:
                # Check if metadata or endpoint changed
                changed = (
                    existing_peer.node_name != node_name
                    or existing_peer.address != ip
                    or existing_peer.port != port
                    or existing_peer.protocol_version != protocol_version
                    or existing_peer.metadata != metadata
                )
                updated_peer = existing_peer.model_copy(
                    update={
                        "last_seen": now,
                        "node_name": node_name,
                        "address": ip,
                        "port": port,
                        "protocol_version": protocol_version,
                        "metadata": metadata,
                    }
                )
                self._peers[node_id] = updated_peer
                if changed:
                    logger.debug("Peer attributes updated: %s (%s)", node_name, node_id)
                    await self._event_bus.publish(PeerUpdatedEvent(peer=updated_peer))

    async def _announce_loop(self) -> None:
        """Periodically broadcast identity schema payload over UDP."""
        while self._running:
            identity = self._identity_manager.identity
            if identity and self._transport:
                extra_meta = {}
                if self._metadata_provider:
                    try:
                        extra_meta = self._metadata_provider() or {}
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("Error collecting discovery metadata: %s", exc)

                payload = {
                    "node_id": str(identity.node_id),
                    "node_name": identity.node_name,
                    "port": self._port,
                    "protocol_version": identity.protocol_version,
                    "metadata": extra_meta,
                }
                encoded = json.dumps(payload).encode("utf-8")
                try:
                    self._transport.sendto(encoded, (self._broadcast_host, self._port))
                except Exception as e:
                    logger.debug("Failed to send broadcast datagram: %s", e)

            await asyncio.sleep(self._interval)

    async def _reap_loop(self) -> None:
        """Periodically purge silent peers exceeding the expiry interval."""
        while self._running:
            await asyncio.sleep(self._interval)
            now = datetime.now(UTC)
            lost_peers: list[Peer] = []

            async with self._peers_lock:
                to_remove: list[UUID] = []
                for node_id, peer in self._peers.items():
                    if (now - peer.last_seen).total_seconds() > self._expiry:
                        to_remove.append(node_id)
                        lost_peers.append(peer)

                for node_id in to_remove:
                    del self._peers[node_id]

            for peer in lost_peers:
                logger.info("Peer expired: %s (%s)", peer.node_name, peer.node_id)
                await self._event_bus.publish(
                    PeerLostEvent(
                        node_id=peer.node_id,
                        node_name=peer.node_name,
                        last_seen=peer.last_seen,
                    )
                )
