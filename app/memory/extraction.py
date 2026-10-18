"""Extraction and validation of candidate memories from interaction."""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from app.llm import get_llm_client
from app.core.logging import get_logger

logger = get_logger("extraction")
from app.llm.prompts import TRIAGE_SYSTEM_PROMPT
from app.memory.signals import find_services, extract_version_updates, has_incident_signal, is_inquiry


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

    async def extract_candidates(
        self, user_message: str, known_services: Optional[List[str]] = None
    ) -> ExtractionResult:
        """known_services: service names already in the tenant graph (None = unknown, use the built-in default)."""
        llm = get_llm_client()
        known_line = f"Known services in this tenant: {', '.join(known_services)}\n\n" if known_services else ""
        prompt = (
            "Analyze the following user statement and extract entities, episodic events, semantic facts, "
            f"and procedural requests:\n\n{known_line}{user_message}"
        )
        try:
            raw_json = await llm.generate_json(prompt, TRIAGE_SYSTEM_PROMPT)
            result = ExtractionResult.model_validate(raw_json)
            if not (result.episodic_memories or result.semantic_facts or result.procedural_requests):
                # LLM found nothing: double-check with the deterministic extractor before dropping the message.
                fallback = self._deterministic_extract(user_message, known_services)
                if fallback.episodic_memories or fallback.semantic_facts or fallback.procedural_requests:
                    return fallback
            return result
        except Exception as e:
            logger.warning(f"LLM extraction failed, using deterministic fallback: {e}")
            # Fallback deterministic extraction
            return self._deterministic_extract(user_message, known_services)

    def _deterministic_extract(self, text: str, known_services: Optional[List[str]] = None) -> ExtractionResult:
        """Deterministic lightweight extraction for high reliability."""
        import re
        service_names = find_services(text, known_services)
        entities = [EntityCandidate(kind="service", name=n) for n in service_names]

        episodic = []
        if has_incident_signal(text) and not is_inquiry(text):
            episodic.append(EpisodicCandidate(
                subtype="incident",
                title=f"Incident: {text[:40].strip()}",
                summary=text.strip(),
                entity_names=[e.name for e in entities],
                severity="high" if re.search(r"\boutages?\b", text.lower()) else "medium"
            ))

        semantic = []
        for subject, version in extract_version_updates(text, service_names):
            semantic.append(SemanticCandidate(
                subtype="fact",
                subject_entity=subject,
                predicate="current_version",
                object_value=version,
                confidence_basis="user_explicit"
            ))

        procedural = []
        if re.search(r"\b(runbook|rollback|procedure|how to)", text.lower()):
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