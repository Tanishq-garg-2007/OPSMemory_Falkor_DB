"""End-to-end: natural-language updates are captured and supersede older facts."""
from app.agents.triage import TriageAgent
from app.memory.lifecycle import MemoryLifecycle
from app.memory.signals import is_inquiry, extract_version_updates, find_services


def _active_versions(repo, ctx, service):
    return [m for m in repo.list_memories(ctx, status="active", memory_type="semantic")
            if service in m.entities and "version" in m.title.lower()]


async def test_we_upgraded_creates_memory_and_supersedes_seed(seeded_repo, context_acme):
    agent = TriageAgent(MemoryLifecycle(seeded_repo))
    before = len(seeded_repo.list_memories(context_acme))
    res = await agent.triage_message(context_acme, "We upgraded payments-api to v2.5", "c1", "m1")
    assert res["created_memories"], "natural update was silently dropped"
    assert len(seeded_repo.list_memories(context_acme)) == before + 1

    active = _active_versions(seeded_repo, context_acme, "payments-api")
    assert [m for m in active if "v2.5" in m.summary]
    assert not [m for m in active if "v2.4" in m.summary], "old v2.4 must be superseded"


async def test_questions_never_become_memories(seeded_repo, context_acme):
    agent = TriageAgent(MemoryLifecycle(seeded_repo))
    for q in [
        "Summarize the history of payments-api version changes from v2.2 to v2.4.",
        "Compare the current version of payments-api with its version during inc-101.",
        "Is payments-api currently running v2.3?",
    ]:
        res = await agent.triage_message(context_acme, q, "c2", "m2")
        assert res["created_memories"] == [], q
    assert _active_versions(seeded_repo, context_acme, "payments-api")[0].summary.endswith("v2.4, following the post-incident stabilization release.")


def test_signal_helpers():
    assert is_inquiry("Compare A with B.") and not is_inquiry("We upgraded payments-api to v2.5")
    assert extract_version_updates("We upgraded payments-api to v2.5") == [("payments-api", "v2.5")]
    assert extract_version_updates("payments-api is now on 2.6") == [("payments-api", "v2.6")]
    assert extract_version_updates("Checkout failed on 2026-09-15 after inc-101") == []


def test_unknown_service_name_is_discovered_not_version():
    text = "billing-gateway version is v3.1"
    assert "billing-gateway" in find_services(text)
    assert extract_version_updates(text) == [("billing-gateway", "v3.1")]