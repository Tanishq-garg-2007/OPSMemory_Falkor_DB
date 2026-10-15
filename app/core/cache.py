"""Tenant-aware versioned cache."""
import time
from typing import Dict, Any, Optional, Tuple


class TenantVersionedCache:
    """In-memory cache keyed with tenant_id, tenant_version, and query hash."""
    def __init__(self, default_ttl_seconds: float = 60.0):
        self._cache: Dict[str, Tuple[Any, float]] = {}
        self._tenant_versions: Dict[str, int] = {}
        self.default_ttl = default_ttl_seconds

    def get_tenant_version(self, tenant_id: str) -> int:
        return self._tenant_versions.get(tenant_id, 1)

    def bump_tenant_version(self, tenant_id: str) -> int:
        """Bump tenant version to invalidate cached items on memory write."""
        new_v = self._tenant_versions.get(tenant_id, 1) + 1
        self._tenant_versions[tenant_id] = new_v
        return new_v

    def _make_key(self, tenant_id: str, key_suffix: str) -> str:
        version = self.get_tenant_version(tenant_id)
        return f"{tenant_id}:v{version}:{key_suffix}"

    def get(self, tenant_id: str, key_suffix: str) -> Optional[Any]:
        full_key = self._make_key(tenant_id, key_suffix)
        entry = self._cache.get(full_key)
        if not entry:
            return None
        value, expiry = entry
        if time.time() > expiry:
            self._cache.pop(full_key, None)
            return None
        return value

    def set(self, tenant_id: str, key_suffix: str, value: Any, ttl: Optional[float] = None) -> None:
        full_key = self._make_key(tenant_id, key_suffix)
        expiry = time.time() + (ttl if ttl is not None else self.default_ttl)
        self._cache[full_key] = (value, expiry)

    def invalidate_tenant(self, tenant_id: str) -> None:
        self.bump_tenant_version(tenant_id)

    def clear(self) -> None:
        self._cache.clear()
        self._tenant_versions.clear()


_cache = TenantVersionedCache()


def get_cache() -> TenantVersionedCache:
    return _cache
