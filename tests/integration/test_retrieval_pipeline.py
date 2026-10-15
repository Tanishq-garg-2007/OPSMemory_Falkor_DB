"""Integration tests for retrieval pipeline, temporal handling, and RAG."""
import pytest
from app.retrieval.service import RetrievalService


@pytest.mark.asyncio
async def test_current_vs_historical_retrieval(seeded_repo, context_acme):
    service = RetrievalService()

    # Query current version: must prioritize v2.4 (active) over v2.3 (superseded)
    curr_resp = await service.retrieve_and_answer(context_acme, "What is the current version of payments-api?")
    assert curr_resp.abstained is False
    assert "v2.4" in curr_resp.answer
    assert len(curr_resp.citations) > 0

    # Query historical version
    hist_resp = await service.retrieve_and_answer(context_acme, "What was the previous version of payments-api before v2.4?")
    assert hist_resp.abstained is False
    assert "v2.3" in hist_resp.answer or "2.3" in hist_resp.answer


@pytest.mark.asyncio
async def test_procedural_runbook_retrieval(seeded_repo, context_acme):
    service = RetrievalService()
    resp = await service.retrieve_and_answer(context_acme, "How to rollback payments-api?")
    assert resp.abstained is False
    assert any("runbook" in e.subtype or "rollback" in e.title.lower() for e in resp.evidence)


@pytest.mark.asyncio
async def test_abstention_on_missing_evidence(seeded_repo, context_acme):
    service = RetrievalService()
    resp = await service.retrieve_and_answer(context_acme, "What is the secret flight trajectory of Apollo 13?")
    assert resp.abstained is True
    assert len(resp.citations) == 0
