"""Integration tests for dynamic semantic vector anchoring and localized subgraph traversal."""
import pytest
from app.dependencies import TenantContext
from app.memory.models import EntityModel
from app.memory.repository import get_memory_repository
from app.retrieval.service import RetrievalService


@pytest.mark.asyncio
async def test_dynamic_entity_vector_anchoring(seeded_repo, context_acme):
    repo = get_memory_repository()
    # Save a completely new entity not present in any pre-existing list
    new_entity = EntityModel(
        id="ent_service_acme_billing-processor",
        tenant_id=context_acme.tenant_id,
        kind="service",
        name="billing-processor",
        aliases=["billing-engine", "stripe-gateway"],
        description="High throughput subscription billing and invoice processing"
    )
    repo.save_entity(context_acme, new_entity)

    # Search anchors using alias or semantic keywords: 'stripe-gateway' or 'billing-engine'
    anchors = repo.find_anchor_entities(context_acme, "How does the stripe-gateway invoice engine work?", limit=3)
    anchor_names = [a.name for a in anchors]
    assert "billing-processor" in anchor_names


@pytest.mark.asyncio
async def test_dynamic_multihop_graph_traversal(seeded_repo, context_acme):
    repo = get_memory_repository()
    # Create an arbitrary 3-hop chain: shop-frontend -> checkout-aggregator -> payment-ledger
    chain_names = ["shop-frontend", "checkout-aggregator", "payment-ledger"]
    for name in chain_names:
        repo.save_entity(context_acme, EntityModel(
            id=f"ent_service_acme_{name}",
            tenant_id=context_acme.tenant_id,
            kind="service",
            name=name,
            description=f"Service component {name}"
        ))

    repo.add_relationship(
        context_acme,
        "ent_service_acme_shop-frontend",
        "ent_service_acme_checkout-aggregator",
        "DEPENDS_ON"
    )
    repo.add_relationship(
        context_acme,
        "ent_service_acme_checkout-aggregator",
        "ent_service_acme_payment-ledger",
        "DEPENDS_ON"
    )

    service = RetrievalService()
    # Ask about dependency impact on the dynamically created entities
    paths = service.graph_searcher.get_reasoning_paths(
        context_acme,
        service.router.route_query(
            "If payment-ledger crashes, what downstream service is affected?",
            anchor_entities=["payment-ledger"]
        )
    )

    # Verify that the multi-hop dependency path is found dynamically
    found = any("shop-frontend" in p and "payment-ledger" in p for p in paths)
    assert found is True, f"Expected path containing shop-frontend and payment-ledger, got {paths}"
