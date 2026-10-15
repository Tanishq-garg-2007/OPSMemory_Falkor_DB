"""Pytest shared fixtures and test configuration."""
import os
import pytest
from app.config import Settings
from app.dependencies import TenantContext
from app.memory.repository import MemoryRepository
from app.agents.coordinator import Coordinator
from app.retrieval.service import RetrievalService
from eval.dataset.fixtures import seed_fixtures_for_tenant, reset_tenant_data


@pytest.fixture(scope="session")
def test_settings(tmp_path_factory):
    temp_dir = tmp_path_factory.mktemp("db")
    db_path = str(temp_dir / "test_opsmemory.db")
    return Settings(
        SQLITE_DB_PATH=db_path,
        REAL_LLM=0,
        LLM_PROVIDER="mock",
        FALKORDB_HOST="localhost",
        FALKORDB_PORT=6379,
    )


@pytest.fixture
def repo(test_settings, context_acme, context_beta):
    repository = MemoryRepository(settings=test_settings)
    reset_tenant_data(context_acme, repository)
    reset_tenant_data(context_beta, repository)
    return repository


@pytest.fixture
def context_acme():
    return TenantContext(tenant_id="acme", graph_name="tenant_acme", api_key_name="key_acme_secret")


@pytest.fixture
def context_beta():
    return TenantContext(tenant_id="beta", graph_name="tenant_beta", api_key_name="key_beta_secret")


@pytest.fixture
def seeded_repo(repo, context_acme, context_beta):
    reset_tenant_data(context_acme, repo)
    reset_tenant_data(context_beta, repo)
    seed_fixtures_for_tenant(context_acme, repo)
    seed_fixtures_for_tenant(context_beta, repo)
    return repo
