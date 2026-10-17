"""Unit tests for configuration and error classes."""
import pytest
from app.config import Settings
from app.errors import (
    OpsMemoryError, AuthenticationError, TenantIsolationError,
    ResourceNotFoundError, ConflictError
)


def test_default_config():
    s = Settings()
    assert s.LLM_MODEL_ID in ("gemma-4-31b-it", "qwen/qwen3.8-27b")
    assert s.LLM_PROVIDER in ("google_genai", "groq")
    assert s.ENABLE_EMBEDDINGS in (True, False)
    assert s.RRF_K == 60


def test_tenant_graph_name():
    s = Settings()
    assert s.tenant_graph_name("acme") == "tenant_acme"
    assert s.tenant_graph_name("beta_1") == "tenant_beta_1"
    with pytest.raises(ValueError):
        s.tenant_graph_name("!@#$%^")


def test_typed_errors():
    err = AuthenticationError("Unauthorized")
    assert err.status_code == 401
    assert isinstance(err, OpsMemoryError)

    iso_err = TenantIsolationError("Blocked")
    assert iso_err.status_code == 403

    conf_err = ConflictError("Stale")
    assert conf_err.status_code == 409
