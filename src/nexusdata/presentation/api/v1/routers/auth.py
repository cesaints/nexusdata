"""Endpoints de autenticação e registro."""

from __future__ import annotations

from fastapi import APIRouter, status

from nexusdata.application.dto.auth import (
    LoginCommand,
    RegisteredTenant,
    RegisterTenantCommand,
    TokenPair,
)
from nexusdata.presentation.api.deps import AuthDep, ContainerDep
from nexusdata.presentation.api.schemas import (
    LoginRequest,
    RefreshRequest,
    RegisterTenantRequest,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    summary="Cria um tenant e seu usuário administrador",
)
async def register(body: RegisterTenantRequest, container: ContainerDep) -> RegisteredTenant:
    command = RegisterTenantCommand(
        tenant_name=body.tenant_name,
        tenant_slug=body.tenant_slug,
        admin_email=body.admin_email,
        admin_password=body.admin_password,
    )
    return await container.auth_service.register_tenant(command)


@router.post("/login", summary="Autentica e emite tokens (access + refresh)")
async def login(body: LoginRequest, container: ContainerDep) -> TokenPair:
    return await container.auth_service.login(
        LoginCommand(email=body.email, password=body.password)
    )


@router.post("/refresh", summary="Renova o par de tokens a partir do refresh")
async def refresh(body: RefreshRequest, container: ContainerDep) -> TokenPair:
    return await container.auth_service.refresh(body.refresh_token)


@router.get("/me", summary="Dados do principal autenticado")
async def me(auth: AuthDep) -> dict[str, object]:
    return {
        "user_id": str(auth.user_id) if auth.user_id else None,
        "tenant_id": str(auth.tenant_id),
        "role": auth.role.value,
        "auth_method": auth.method.value,
        "scopes": sorted(s.value for s in auth.scopes),
    }
