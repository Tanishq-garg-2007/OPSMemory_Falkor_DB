"""FastAPI dependency injection and tenant context."""
import hmac
from dataclasses import dataclass
from typing import Optional
from fastapi import Header, Depends
from app.config import Settings, get_settings
from app.errors import AuthenticationError, TenantIsolationError, OpsMemoryError


@dataclass(frozen=True)
class TenantContext:
    tenant_id: str
    graph_name: str
    api_key_name: str = "default"

    def assert_same_tenant(self, other_tenant_id: str) -> None:
        """Enforce strict tenant boundary."""
        if self.tenant_id != other_tenant_id:
            raise TenantIsolationError(
                f"Tenant '{self.tenant_id}' cannot access resources belonging to '{other_tenant_id}'"
            )


def get_tenant_context(
    x_tenant_key: Optional[str] = Header(None, alias="X-Tenant-Key"),
) -> TenantContext:
    """Validate the tenant key against the tenants table (SHA-256 hashed keys only).

    No prefix shortcuts and no hardcoded dev keys: a key works only if it was
    registered via MemoryRepository.register_tenant (see scripts/init_schema.py).
    """
    if not x_tenant_key:
        raise AuthenticationError("Missing X-Tenant-Key header")

    # Imported here to avoid a circular import (repository imports TenantContext).
    from app.memory.repository import get_memory_repository

    tenant = get_memory_repository().find_tenant_by_api_key(x_tenant_key)
    if not tenant:
        raise AuthenticationError("Invalid X-Tenant-Key")

    return TenantContext(
        tenant_id=tenant["tenant_id"],
        graph_name=tenant["graph_name"],
        api_key_name="tenant_key",  # never keep the raw key around
    )


async def require_admin(
    x_admin_key: Optional[str] = Header(None, alias="X-Admin-Key"),
    settings: Settings = Depends(get_settings),
) -> None:
    """Guard for /v1/admin/*. Disabled entirely unless ADMIN_API_KEY is configured."""
    if not settings.ADMIN_API_KEY:
        raise OpsMemoryError(
            "Admin API is disabled: set ADMIN_API_KEY to enable it", status_code=403
        )
    if not x_admin_key or not hmac.compare_digest(
        x_admin_key.encode(), settings.ADMIN_API_KEY.encode()
    ):
        raise AuthenticationError("Invalid or missing X-Admin-Key")