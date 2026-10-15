"""Audit #7 (false incident detection) and #8 (memory ID truncation collisions). No database needed."""
import pytest

from app.core.ids import memory_id
from app.memory.signals import has_incident_signal
from app.retrieval.router import RetrievalRouter


@pytest.mark.parametrize("text", [
    "We finished the download of the quarterly report",
    "How do I download the report?",
    "We know the answer already",
    "markdown rendering looks fine",
])
def test_no_false_incident_signal(text):
    assert not has_incident_signal(text)
    assert not RetrievalRouter().route_query(text).is_incident_query


@pytest.mark.parametrize("text", [
    "payments-api is down",
    "INC-101 checkout failure",
    "Errors in checkout since the deploy",
    "There were two outages last week",
])
def test_real_incident_signal(text):
    assert has_incident_signal(text)
    assert RetrievalRouter().route_query(text).is_incident_query


def test_router_now_is_whole_word():
    assert RetrievalRouter().route_query("who owns payments-api now").is_current_fact
    assert not RetrievalRouter().route_query("what was the previous owner, I know it changed").is_current_fact


def test_long_titles_with_same_prefix_get_distinct_ids():
    a = memory_id("semantic", "acme", "fact", "payments-api current version is v2.4 and rollback target")
    b = memory_id("semantic", "acme", "fact", "payments-api current version is v2.5 and rollback target")
    assert a != b


def test_memory_id_is_deterministic_and_short_titles_unchanged():
    t = "payments-api current version is v2.4 and rollback target"
    assert memory_id("semantic", "acme", "fact", t) == memory_id("semantic", "acme", "fact", t)
    assert memory_id("semantic", "acme", "fact", "current version") == "mem_semantic_acme_fact_current-version"