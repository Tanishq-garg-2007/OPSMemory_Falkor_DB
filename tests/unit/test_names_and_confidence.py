"""Audit #9 / #10: entity name variants and evidence-derived confidence. No database needed."""
import pytest

from app.memory.signals import canonical_name_key, names_equivalent, find_services
from app.retrieval.evidence import PackedEvidenceItem, combine_confidence, evidence_confidence


@pytest.mark.parametrize("a,b", [
    ("auth-svc", "authservice"),
    ("auth-svc", "auth-service"),
    ("Auth Service", "auth_service"),
    ("postgres-orders", "postgres-order"),
])
def test_equivalent_names(a, b):
    assert names_equivalent(a, b)


@pytest.mark.parametrize("a,b", [
    ("payments-api", "payments-worker"),
    ("checkout-ui", "auth-service"),
    ("inventory-svc", "gateway-api"),
])
def test_distinct_names_stay_distinct(a, b):
    assert not names_equivalent(a, b)


def test_known_services_come_from_the_caller():
    assert find_services("billing-gateway is down", known=["billing-gateway"]) == ["billing-gateway"]
    # An explicit empty list means "this tenant has no services yet" - the built-in default must not leak in.
    assert find_services("payments-api is down", known=[]) == []


def _item(status="active", confidence=0.9):
    return PackedEvidenceItem(
        memory_id="m", memory_type="semantic", subtype="fact", title="t", summary="s",
        confidence=confidence, valid_from="2026-01-01T00:00:00Z", status=status, score=0.5,
    )


def test_confidence_follows_evidence():
    assert evidence_confidence([]) == "low"
    assert evidence_confidence([_item("active", 0.95)]) == "high"
    assert evidence_confidence([_item("active", 0.5)]) == "medium"
    assert evidence_confidence([_item("superseded")]) == "medium"
    assert evidence_confidence([_item("conflicted")]) == "low"


def test_llm_cannot_overstate_confidence():
    assert combine_confidence("high", [_item("conflicted")]) == "low"
    assert combine_confidence("low", [_item("active", 0.95)]) == "low"
    assert combine_confidence(None, [_item("active", 0.95)]) == "high"