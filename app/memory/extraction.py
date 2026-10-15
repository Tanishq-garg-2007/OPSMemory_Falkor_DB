"""Extraction and validation of candidate memories from interaction."""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from app.llm import get_llm_client
from app.llm.prompts import TRIAGE_SYSTEM_PROMPT


class EntityCandidate(BaseModel):
    kind: str = "service"
    name: str
    aliases: List[str] = Field(default_factory=list)


class EpisodicCandidate(BaseModel):
    subtype: str = "incident"
    title: str
    summary: str
    entity_names: List[str] = Field(default_factory=list)
    severity: str = "medium"


class SemanticCandidate(BaseModel):
    subtype: str = "fact"
    subject_entity: str
    predicate: str
    object_value: str
    confidence_basis: str = "user_explicit"


class ProceduralCandidate(BaseModel):
    subtype: str = "runbook_request"
    trigger: str
    entity_names: List[str] = Field(default_factory=list)


class ExtractionResult(BaseModel):
    entities: List[EntityCandidate] = Field(default_factory=list)
    episodic_memories: List[EpisodicCandidate] = Field(default_factory=list)
    semantic_facts: List[SemanticCandidate] = Field(default_factory=list)
    procedural_requests: List[ProceduralCandidate] = Field(default_factory=list)
    missing_info: List[str] = Field(default_factory=list)


class MemoryExtractor:
    """Extracts structured memory candidates via deterministic parsing or LLM."""

    async def extract_candidates(self, user_message: str) -> ExtractionResult:
        llm = get_llm_client()
        prompt = f"Analyze the following user statement and extract entities, episodic events, semantic facts, and procedural requests:\n\n{user_message}"
        try:
            raw_json = await llm.generate_json(prompt, TRIAGE_SYSTEM_PROMPT)
            return ExtractionResult.model_validate(raw_json)
        except Exception:
            # Fallback deterministic extraction
            return self._deterministic_extract(user_message)

    def _deterministic_extract(self, text: str) -> ExtractionResult:
        """Deterministic lightweight extraction for high reliability."""
        import re
        entities = []
        services = ["payments-api", "checkout-ui", "auth-service", "postgres-orders", "inventory-svc"]
        for s in services:
            if s in text.lower():
                entities.append(EntityCandidate(kind="service", name=s))

        episodic = []
        if any(w in text.lower() for w in ["incident", "failure", "outage", "broken", "down", "error"]):
            episodic.append(EpisodicCandidate(
                subtype="incident",
                title=f"Incident: {text[:40].strip()}",
                summary=text.strip(),
                entity_names=[e.name for e in entities],
                severity="high" if "outage" in text.lower() else "medium"
            ))

        semantic = []
        versions = re.findall(r"\bv\d+(?:\.\d+)?\b", text.lower())
        for v in versions:
            subject = entities[0].name if entities else "service"
            semantic.append(SemanticCandidate(
                subtype="fact",
                subject_entity=subject,
                predicate="current_version",
                object_value=v,
                confidence_basis="user_explicit"
            ))

        procedural = []
        if any(w in text.lower() for w in ["runbook", "rollback", "procedure", "how to"]):
            procedural.append(ProceduralCandidate(
                subtype="runbook_request",
                trigger=text[:50],
                entity_names=[e.name for e in entities]
            ))

        return ExtractionResult(
            entities=entities,
            episodic_memories=episodic,
            semantic_facts=semantic,
            procedural_requests=procedural,
            missing_info=[]
        )
