"""Retrieval query router and intent analyzer."""
import re
from typing import List, Optional
from pydantic import BaseModel, Field
from app.memory.signals import has_incident_signal


class QueryIntent(BaseModel):
    raw_query: str
    is_procedural: bool = False
    is_historical: bool = False
    is_current_fact: bool = False
    is_incident_query: bool = False
    target_entities: List[str] = Field(default_factory=list)
    incident_id: Optional[str] = None
    # "dependencies": what the entity depends on (outgoing DEPENDS_ON)
    # "dependents":   what depends on the entity (incoming DEPENDS_ON / blast radius)
    # "both":         unspecified, show both, each in its true direction
    dependency_direction: str = "both"


_DEPENDENTS_RE = re.compile(
    r"\b(what|which|who|any)\b\s+(?:\w+\s+)?(?:depends?|relies|rely|reliant)\s+on\b"
    r"|\b(dependents?|downstream|blast radius|impacted by|affected by|break if)\b"
)
_DEPENDENCIES_RE = re.compile(
    r"\b(depends?|relies|rely|uses?|dependenc(?:y|ies)|requires?)\b"
)


def detect_dependency_direction(query: str) -> str:
    q = query.lower()
    if _DEPENDENTS_RE.search(q):
        return "dependents"
    if _DEPENDENCIES_RE.search(q):
        return "dependencies"
    return "both"


def _has_phrase(text: str, phrases: List[str]) -> bool:
    """Phrase match anchored at a word start, so a keyword never matches in the middle of another word."""
    return any(re.search(r"\b" + re.escape(p), text) for p in phrases)


def _has_word(text: str, words: List[str]) -> bool:
    """Whole-word match (optional plural s): "now" must not match "know", "down" must not match "download"."""
    return any(re.search(r"\b" + re.escape(w) + r"s?\b", text) for w in words)


class RetrievalRouter:
    """Analyzes queries dynamically using FalkorDB semantic anchors to configure retrieval priorities."""

    def route_query(
        self,
        query: str,
        anchor_entities: Optional[List[str]] = None,
        available_entities: Optional[List[str]] = None
    ) -> QueryIntent:
        q_lower = query.lower()

        # Procedural intent
        is_procedural = _has_phrase(q_lower, [
            "how to", "procedure", "runbook", "rollback", "steps", "guide", "escalate"
        ])

        # Historical vs current
        is_historical = _has_phrase(q_lower, [
            "before", "previous", "prior", "last time", "history", "earlier", "originally"
        ])

        # Current fact
        is_current = (
            _has_phrase(q_lower, ["current", "latest", "who owns", "what version", "preference"])
            or _has_word(q_lower, ["now"])
            or (not is_historical and not is_procedural)
        )

        # Incident
        is_incident = has_incident_signal(q_lower)

        # Match incident IDs like inc-101
        inc_match = re.search(r"\binc[-_]?\d+\b", q_lower)
        incident_id = inc_match.group(0) if inc_match else None

        # Extract target entities dynamically
        target_entities: List[str] = []
        seen = set()

        # 1. Dynamically discovered anchors from FalkorDB vector / graph lookup
        if anchor_entities:
            for ent in anchor_entities:
                if ent not in seen:
                    seen.add(ent)
                    target_entities.append(ent)

        # 2. Available entity names matched against query
        if available_entities:
            for ent in available_entities:
                base = ent.split("-")[0]
                if (ent in q_lower or ent.replace("-", " ") in q_lower or (len(base) >= 4 and f" {base} " in f" {q_lower} ")) and ent not in seen:
                    seen.add(ent)
                    target_entities.append(ent)

        # 3. Dynamic token extraction for hyphenated identifiers in query (e.g., payments-api, auth-service, custom-worker)
        if not target_entities:
            hyphen_candidates = re.findall(r"\b[a-zA-Z0-9]+(?:-[a-zA-Z0-9]+)+\b", q_lower)
            for c in hyphen_candidates:
                if c not in seen:
                    seen.add(c)
                    target_entities.append(c)

        return QueryIntent(
            raw_query=query,
            is_procedural=is_procedural,
            is_historical=is_historical,
            is_current_fact=is_current,
            is_incident_query=is_incident,
            target_entities=target_entities,
            incident_id=incident_id,
            dependency_direction=detect_dependency_direction(query)
        )