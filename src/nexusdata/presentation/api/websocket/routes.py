"""Rota WebSocket para o dashboard (push de status de jobs em tempo real)."""

from __future__ import annotations

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from nexusdata.domain.exceptions import AuthenticationError
from nexusdata.infrastructure.container import Container

router = APIRouter()


@router.websocket("/ws/jobs")
async def jobs_websocket(
    websocket: WebSocket,
    token: str = Query(..., description="JWT de acesso (o navegador não envia header)"),
) -> None:
    container: Container = websocket.app.state.container

    # Autenticação ANTES do accept: token inválido => fecha com policy violation.
    try:
        claims = container.token_service.decode(token)
        if claims.token_type != "access":  # noqa: S105
            raise AuthenticationError("tipo de token inválido")
    except AuthenticationError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    tenant_id = str(claims.tenant_id)
    manager = websocket.app.state.ws_manager
    await manager.connect(tenant_id, websocket)
    try:
        # Mantém a conexão viva; ignoramos mensagens do cliente (canal só de push).
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(tenant_id, websocket)
