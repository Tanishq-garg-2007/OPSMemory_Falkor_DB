"""Retrieval query router and intent analyzer."""
import re
from typing import List, Optional
from pydantic import BaseModel, Field


class QueryIntent(BaseModel):
    raw_query: str
    is_procedural: bool = False
    is_historical: bool = False
    is_current_fact: bool = False
    is_incident_query: bool = False
    target_entities: List[str] = Field(default_factory=list)
    incident_id: Optional[str] = None


class RetrievalRouter:
    """Analyzes queries deterministically to configure retrieval priorities."""

    KNOWN_ENTITIES = [
        "payments-api", "checkout-ui", "auth-service",
        "postgres-orders", "inventory-svc", "gateway-api",
        "payments-worker", "priya"
    ]

    def route_query(self, query: str) -> QueryIntent:
        q_lower = query.lower()

        # Procedural intent
        is_procedural = any(w in q_lower for w in [
            "how to", "procedure", "runbook", "rollback", "steps", "guide", "escalate"
        ])

        # Historical vs current
        is_historical = any(w in q_lower for w in [
            "before", "previous", "prior", "last time", "history", "earlier", "originally"
        ])

        # Current fact
        is_current = any(w in q_lower for w in [
            "current", "latest", "now", "who owns", "what version", "preference"
        ]) or (not is_historical and not is_procedural)

        # Incident
        is_incident = any(w in q_lower for w in [
            "incident", "inc-", "outage", "failure", "broken", "down"
        ])

        # Match incident IDs like inc-101
        inc_match = re.search(r"\binc[-_]?\d+\b", q_lower)
        incident_id = inc_match.group(0) if inc_match else None

        # Extract target entities
        target_entities = []
        for ent in self.KNOWN_ENTITIES:
            if ent in q_lower or ent.replace("-", " ") in q_lower:
                target_entities.append(ent)

        return QueryIntent(
            raw_query=query,
            is_procedural=is_procedural,
            is_historical=is_historical,
            is_current_fact=is_current,
            is_incident_query=is_incident,
            target_entities=target_entities,
            incident_id=incident_id
        )
