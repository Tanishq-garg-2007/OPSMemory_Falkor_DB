"""FastAPI dependency injection and tenant context."""
from dataclasses import dataclass
from typing import Optional
from fastapi import Header, Depends
from app.config import Settings, get_settings
from app.errors import AuthenticationError, TenantIsolationError


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


# Local development pre-seeded keys mapping
DEVELOPMENT_TENANT_KEYS = {
    "key_acme_secret": "acme",
    "key_beta_secret": "beta",
    "dev-key-acme": "acme",
    "dev-key-beta": "beta",
}


async def get_tenant_context(
    x_tenant_key: Optional[str] = Header(None, alias="X-Tenant-Key"),
    settings: Settings = Depends(get_settings),
) -> TenantContext:
    """Validate tenant key and derive tenant context."""
    if not x_tenant_key:
        raise AuthenticationError("Missing X-Tenant-Key header")

    tenant_id = DEVELOPMENT_TENANT_KEYS.get(x_tenant_key)
    if not tenant_id:
        # Check if key is formatted as tenant:<id> or direct key
        if x_tenant_key.startswith("tenant_key_"):
            tenant_id = x_tenant_key[len("tenant_key_"):]
        else:
            raise AuthenticationError("Invalid X-Tenant-Key")

    graph_name = settings.tenant_graph_name(tenant_id)
    return TenantContext(
        tenant_id=tenant_id,
        graph_name=graph_name,
        api_key_name=x_tenant_key
    )
