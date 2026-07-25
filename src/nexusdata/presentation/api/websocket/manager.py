"""Gerenciador de conexões WebSocket, particionado por tenant.

Um cliente só recebe eventos do SEU tenant (isolamento reforçado: o tenant vem
do JWT validado, não de um parâmetro controlável pelo cliente).
"""

from __future__ import annotations

import asyncio

import structlog
from starlette.websockets import WebSocket

_log = structlog.get_logger(__name__)


_WS_TRY_AGAIN_LATER = 1013


class WebSocketConnectionManager:
    def __init__(self, *, max_per_tenant: int = 20, max_total: int = 1000) -> None:
        self._connections: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()
        self._max_per_tenant = max_per_tenant
        self._max_total = max_total

    async def connect(self, tenant_id: str, websocket: WebSocket) -> bool:
        """Aceita e registra a conexão. Retorna False (e fecha) se estourar o
        limite por tenant ou o global — proteção contra exaustão de FD/memória."""
        await websocket.accept()
        async with self._lock:
            total = sum(len(c) for c in self._connections.values())
            conns = self._connections.get(tenant_id, set())
            over_limit = len(conns) >= self._max_per_tenant or total >= self._max_total
            if not over_limit:
                self._connections.setdefault(tenant_id, set()).add(websocket)
        if over_limit:
            _log.warning("ws.limit_reached", tenant_id=tenant_id)
            await websocket.close(code=_WS_TRY_AGAIN_LATER)
            return False
        return True

    async def disconnect(self, tenant_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            conns = self._connections.get(tenant_id)
            if conns:
                conns.discard(websocket)
                if not conns:
                    self._connections.pop(tenant_id, None)

    async def broadcast(self, tenant_id: str, message: str) -> None:
        async with self._lock:
            targets = list(self._connections.get(tenant_id, set()))
        dead: list[WebSocket] = []
        for ws in targets:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(tenant_id, ws)

    @property
    def connection_count(self) -> int:
        return sum(len(c) for c in self._connections.values())
