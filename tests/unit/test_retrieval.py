"""Unit tests for retrieval router, fusion, and evidence packing."""
from app.retrieval.router import RetrievalRouter
from app.retrieval.fusion import RankFusion
from app.retrieval.evidence import EvidencePacker
from app.memory.models import MemoryModel


def test_router_intent():
    router = RetrievalRouter()
    intent_proc = router.route_query("How to rollback payments-api?")
    assert intent_proc.is_procedural is True
    assert "payments-api" in intent_proc.target_entities

    intent_hist = router.route_query("What was the previous version before the fix?")
    assert intent_hist.is_historical is True

    intent_inc = router.route_query("Tell me about inc-101")
    assert intent_inc.incident_id == "inc-101"


def test_evidence_packing_budget():
    packer = EvidencePacker(token_budget=50)  # ~200 chars budget
    candidates = []
    for i in range(10):
        mem = MemoryModel(
            id=f"mem_{i}",
            tenant_id="acme",
            memory_type="semantic",
            subtype="fact",
            title=f"Memory Title {i}",
            summary="A detailed summary containing important factual evidence for testing.",
            idempotency_key=f"idemp_{i}"
        )
        candidates.append((mem, 1.0 - (i * 0.1)))

    packed = packer.pack_evidence(candidates)
    assert len(packed) > 0
    assert len(packed) < 10  # Token budget bounds packed items
