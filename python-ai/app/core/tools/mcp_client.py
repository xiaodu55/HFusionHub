"""
MCP Client — connect to external Model Context Protocol services.

Provides:
- ``MCPClientManager`` — manage connections to external MCP servers
- ``MCPToolAdapter`` — wrap external MCP tools as local ToolSpec objects
- Auto-discovery: fetch tools/list from connected servers and register with ToolRegistry

Usage::

    from app.core.tools.mcp_client import get_mcp_client_manager

    manager = get_mcp_client_manager()
    await manager.connect_all()
    tools = manager.get_all_tools()  # List[ToolSpec]

Server config (env ``MCP_SERVERS_CONFIG``)::

    [{"id":"notion","name":"Notion","url":"http://notion-mcp:8000/sse","transport":"sse"}]
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum

import httpx

from app.utils.config import config

logger = logging.getLogger(__name__)

MCP_CONFIG_ENV = "MCP_SERVERS_CONFIG"
MCP_HEARTBEAT_INTERVAL = 30  # seconds
MCP_CONNECT_TIMEOUT = 10.0
MCP_CALL_TIMEOUT = 60.0


class TransportType(str, Enum):
    SSE = "sse"
    STREAMABLE_HTTP = "streamable-http"
    STDIO = "stdio"


class ConnectionStatus(str, Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    CONNECTING = "connecting"


@dataclass
class MCPServerConnection:
    server_id: str
    name: str
    url: str
    transport: TransportType = TransportType.SSE
    api_key: Optional[str] = None
    status: ConnectionStatus = ConnectionStatus.DISCONNECTED
    tools: List[Dict[str, Any]] = field(default_factory=list)
    last_heartbeat: float = 0.0
    error_message: str = ""
    consecutive_failures: int = 0


@dataclass
class MCPToolSpec:
    """An MCP tool represented as a local ToolSpec-compatible dict."""
    name: str
    description: str
    input_schema: Dict[str, Any]
    server_id: str
    server_name: str


class MCPClientManager:
    """Manage connections to external MCP servers.

    Thread-safe.  Designed for a single asyncio event loop.
    """

    def __init__(self):
        self._servers: Dict[str, MCPServerConnection] = {}
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._http_client: Optional[httpx.AsyncClient] = None

    # ── Lifecycle ────────────────────────────────────────────────────

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(MCP_CONNECT_TIMEOUT, connect=MCP_CONNECT_TIMEOUT),
            )
        return self._http_client

    async def startup(self) -> None:
        """Load config and connect to all configured servers."""
        raw = getattr(config, "MCP_SERVERS_CONFIG", None)
        if raw:
            try:
                server_configs = json.loads(raw) if isinstance(raw, str) else raw
            except (json.JSONDecodeError, TypeError):
                logger.warning("MCP_SERVERS_CONFIG is not valid JSON; skipping MCP client startup")
                return
        else:
            # Try config file
            import os
            cfg_path = os.environ.get("MCP_SERVERS_CONFIG_FILE", "mcp_servers.json")
            if os.path.exists(cfg_path):
                try:
                    with open(cfg_path, encoding="utf-8") as f:
                        server_configs = json.load(f)
                except Exception:
                    logger.warning("Failed to load %s; skipping MCP client startup", cfg_path)
                    return
            else:
                logger.debug("No MCP servers configured; client idle")
                return

        for cfg in server_configs:
            self.add_server(cfg)

        if self._servers:
            await self.connect_all()
            self._start_heartbeat()
            logger.info("MCP client started with %d server(s)", len(self._servers))

    async def shutdown(self) -> None:
        """Disconnect all servers and stop heartbeat."""
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None
        for sid in list(self._servers):
            await self.disconnect(sid)
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    # ── Server management ────────────────────────────────────────────

    def _config_file_path(self) -> str:
        import os
        return os.environ.get("MCP_SERVERS_CONFIG_FILE", "mcp_servers.json")

    def _persist_config(self) -> None:
        """Persist the current server list to the config file (B5).

        The env-provided ``MCP_SERVERS_CONFIG`` remains the bootstrap source;
        runtime changes are written back so they survive a restart.
        """
        try:
            payload = [
                {
                    "id": conn.server_id,
                    "name": conn.name,
                    "url": conn.url,
                    "transport": conn.transport.value,
                    **({"api_key": conn.api_key} if conn.api_key else {}),
                }
                for conn in self._servers.values()
            ]
            path = self._config_file_path()
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.warning("MCP config persistence failed: %s", exc)

    def add_server(self, cfg: Dict[str, Any]) -> MCPServerConnection:
        sid = cfg["id"]
        conn = MCPServerConnection(
            server_id=sid,
            name=cfg.get("name", sid),
            url=cfg["url"],
            transport=TransportType(cfg.get("transport", "sse")),
            api_key=cfg.get("api_key"),
        )
        self._servers[sid] = conn
        self._persist_config()
        return conn

    def remove_server(self, server_id: str) -> bool:
        if server_id in self._servers:
            del self._servers[server_id]
            self._persist_config()
            return True
        return False

    def get_server(self, server_id: str) -> Optional[MCPServerConnection]:
        return self._servers.get(server_id)

    def list_servers(self) -> List[MCPServerConnection]:
        return list(self._servers.values())

    # ── Connection management ────────────────────────────────────────

    async def connect_all(self) -> None:
        """Connect to all configured servers in parallel."""
        tasks = [self._connect_one(sid) for sid in self._servers]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def connect(self, server_id: str) -> bool:
        return await self._connect_one(server_id)

    async def _connect_one(self, server_id: str) -> bool:
        conn = self._servers.get(server_id)
        if not conn:
            return False
        conn.status = ConnectionStatus.CONNECTING
        try:
            client = await self._get_client()
            resp = await client.post(
                f"{conn.url}/tools/list",
                json={},
                headers=self._headers(conn),
            )
            if resp.status_code == 200:
                data = resp.json()
                conn.tools = data.get("tools", [])
                conn.status = ConnectionStatus.CONNECTED
                conn.consecutive_failures = 0
                conn.error_message = ""
                conn.last_heartbeat = time.monotonic()
                logger.info("MCP server '%s' connected with %d tools", conn.name, len(conn.tools))
                return True
            else:
                conn.status = ConnectionStatus.ERROR
                conn.error_message = f"HTTP {resp.status_code}: {resp.text[:200]}"
                conn.consecutive_failures += 1
                logger.warning("MCP server '%s' returned %d on tools/list", conn.name, resp.status_code)
        except Exception as e:
            conn.status = ConnectionStatus.ERROR
            conn.error_message = str(e)[:200]
            conn.consecutive_failures += 1
            logger.warning("MCP server '%s' connection failed: %s", conn.name, e)
        return False

    async def disconnect(self, server_id: str) -> None:
        conn = self._servers.get(server_id)
        if conn:
            conn.status = ConnectionStatus.DISCONNECTED
            conn.tools.clear()

    async def refresh_tools(self, server_id: str) -> bool:
        """Re-discover tools from a connected server."""
        return await self._connect_one(server_id)

    # ── Tool discovery ───────────────────────────────────────────────

    def get_all_tools(self) -> List[MCPToolSpec]:
        """Return all tools from all connected servers."""
        tools: List[MCPToolSpec] = []
        for conn in self._servers.values():
            if conn.status != ConnectionStatus.CONNECTED:
                continue
            for tool in conn.tools:
                tools.append(MCPToolSpec(
                    name=f"mcp:{conn.server_id}:{tool.get('name', 'unknown')}",
                    description=tool.get("description", f"MCP tool from {conn.name}"),
                    input_schema=tool.get("inputSchema", {"type": "object", "properties": {}}),
                    server_id=conn.server_id,
                    server_name=conn.name,
                ))
        return tools

    def get_tools_for_server(self, server_id: str) -> List[MCPToolSpec]:
        conn = self._servers.get(server_id)
        if not conn or conn.status != ConnectionStatus.CONNECTED:
            return []
        return [MCPToolSpec(
            name=f"mcp:{conn.server_id}:{t.get('name', 'unknown')}",
            description=t.get("description", f"MCP tool from {conn.name}"),
            input_schema=t.get("inputSchema", {"type": "object", "properties": {}}),
            server_id=conn.server_id,
            server_name=conn.name,
        ) for t in conn.tools]

    # ── Tool execution ───────────────────────────────────────────────

    async def call_tool(
        self,
        server_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
        *,
        timeout: float = MCP_CALL_TIMEOUT,
    ) -> Dict[str, Any]:
        """Execute a tool on a remote MCP server."""
        conn = self._servers.get(server_id)
        if not conn or conn.status != ConnectionStatus.CONNECTED:
            return {"error": f"MCP server '{server_id}' is not connected"}

        client = await self._get_client()
        try:
            resp = await client.post(
                f"{conn.url}/tools/call",
                json={"name": tool_name, "arguments": arguments},
                headers=self._headers(conn),
                timeout=httpx.Timeout(timeout, connect=MCP_CONNECT_TIMEOUT),
            )
            if resp.status_code == 200:
                conn.consecutive_failures = 0
                conn.last_heartbeat = time.monotonic()
                return resp.json()
            else:
                conn.consecutive_failures += 1
                return {"error": f"MCP server returned {resp.status_code}: {resp.text[:300]}"}
        except Exception as e:
            conn.consecutive_failures += 1
            return {"error": f"MCP call failed: {e}"}

    # ── Heartbeat ────────────────────────────────────────────────────

    def _start_heartbeat(self) -> None:
        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def _heartbeat_loop(self) -> None:
        while True:
            await asyncio.sleep(MCP_HEARTBEAT_INTERVAL)
            for sid, conn in list(self._servers.items()):
                if conn.status == ConnectionStatus.CONNECTED:
                    if conn.consecutive_failures >= 5:
                        logger.warning("MCP '%s' has %d consecutive failures; disconnecting", conn.name, conn.consecutive_failures)
                        await self.disconnect(sid)
                    elif time.monotonic() - conn.last_heartbeat > 120:
                        # Reconnect if no activity for 2 minutes
                        await self._connect_one(sid)

    # ── Helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _headers(conn: MCPServerConnection) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if conn.api_key:
            headers["Authorization"] = f"Bearer {conn.api_key}"
        return headers


# ── Singleton ──────────────────────────────────────────────────────────

_mcp_client_manager: Optional[MCPClientManager] = None


def get_mcp_client_manager() -> MCPClientManager:
    global _mcp_client_manager
    if _mcp_client_manager is None:
        _mcp_client_manager = MCPClientManager()
    return _mcp_client_manager


# ── ToolRegistry integration ───────────────────────────────────────────


async def register_mcp_tools_with_registry(registry: Any) -> int:
    """Register MCP tools into a ToolRegistry instance. Returns count registered."""
    manager = get_mcp_client_manager()
    specs = manager.get_all_tools()
    count = 0
    for mspec in specs:
        try:
            from app.core.tools.spec import ToolSpec as TS, RiskLevel, Permissions
            ts = TS(
                name=mspec.name,
                description=mspec.description,
                input_schema=mspec.input_schema,
                output_schema={"type": "object"},
                risk_level=RiskLevel.EXTERNAL,
                timeout_seconds=30.0,
                required_permissions=[Permissions.EXTERNAL_HTTP],
                agent_version="1.0",
            )
            ts._mcp_server_id = mspec.server_id
            ts._mcp_tool_name = mspec.name.split(":", 2)[-1]
            registry._specs[mspec.name] = ts
            registry._instances[mspec.name] = None
            count += 1
        except Exception as e:
            logger.warning("Failed to register MCP tool %s: %s", mspec.name, e)
    if count:
        logger.info("Registered %d MCP tools with ToolRegistry", count)
    return count


__all__ = [
    "MCPClientManager",
    "MCPServerConnection",
    "MCPToolSpec",
    "TransportType",
    "ConnectionStatus",
    "get_mcp_client_manager",
    "register_mcp_tools_with_registry",
]
