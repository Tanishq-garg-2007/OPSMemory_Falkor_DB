"""Reasoning paths must be printed in the true DEPENDS_ON direction."""
import pytest
from app.retrieval.graph_search import GraphSearcher
from app.retrieval.router import RetrievalRouter, detect_dependency_direction


@pytest.mark.parametrize("q,expected", [
    ("What does auth-service depend on?", "dependencies"),
    ("What depends on auth-service?", "dependents"),
    ("Which services are affected by a payments-api outage?", "dependents"),
    ("Tell me about auth-service", "both"),
])
def test_direction_detection(q, expected):
    assert detect_dependency_direction(q) == expected


def _chains(seeded_repo, ctx, query, entity):
    if not seeded_repo._falkor_connected:
        pytest.skip("FalkorDB not available")
    intent = RetrievalRouter().route_query(query, anchor_entities=[entity])
    return [" ".join(c) for c in GraphSearcher(seeded_repo).get_reasoning_paths(ctx, intent)]


def test_dependencies_follow_edge_direction(seeded_repo, context_acme):
    chains = _chains(seeded_repo, context_acme, "What does checkout-ui depend on?", "checkout-ui")
    assert "checkout-ui DEPENDS_ON payments-api DEPENDS_ON postgres-orders" in chains
    assert all(c.startswith("checkout-ui") for c in chains)


def test_leaf_service_has_no_phantom_dependencies(seeded_repo, context_acme):
    # auth-service has no outgoing edges in the seed; it must not "depend on" checkout-ui.
    chains = _chains(seeded_repo, context_acme, "What does auth-service depend on?", "auth-service")
    assert chains == []


def test_dependents_print_true_direction(seeded_repo, context_acme):
    chains = _chains(seeded_repo, context_acme, "What depends on auth-service?", "auth-service")
    assert "checkout-ui DEPENDS_ON auth-service" in chains