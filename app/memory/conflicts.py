"""Conflict detection, confidence calculation, and temporal supersession."""
from typing import List, Optional, Tuple
from app.memory.models import MemoryModel

CONFIDENCE_MAP = {
    "user_correction": 0.95,
    "user_explicit": 0.90,
    "verified_outcome": 0.85,
    "seed": 0.80,
    "user_implicit": 0.70,
    "agent_inference": 0.55,
}


def compute_combined_confidence(confidences: List[float]) -> float:
    """
    Combined confidence across independent sources:
    1 - product(1 - c_i), capped at 0.98.
    """
    if not confidences:
        return 0.5
    prod = 1.0
    for c in confidences:
        prod *= (1.0 - min(max(c, 0.0), 1.0))
    return min(1.0 - prod, 0.98)


def detect_semantic_conflict(existing: MemoryModel, incoming: MemoryModel) -> bool:
    """
    Detect if two memories represent conflicting facts on the same entity/predicate.
    Example: payments-api current version v2.3 vs v2.4.
    """
    if existing.id == incoming.id:
        return False
    if existing.memory_type != incoming.memory_type or existing.subtype != incoming.subtype:
        return False
    # If both pertain to the same entities and titles/topics match closely
    shared_entities = set(existing.entities).intersection(set(incoming.entities))
    if not shared_entities:
        return False

    # Check for version / status / owner predicate contradiction
    e_title = existing.title.lower()
    i_title = incoming.title.lower()
    if ("version" in e_title and "version" in i_title) or ("owner" in e_title and "owner" in i_title):
        if existing.summary.strip() != incoming.summary.strip():
            return True

    return False
