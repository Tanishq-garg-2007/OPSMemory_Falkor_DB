"""Evidence packing, token budgeting, prompt-injection defense, and answer generation."""
from typing import List, Tuple, Dict, Any, Optional
from pydantic import BaseModel, Field
from app.config import get_settings
from app.memory.models import MemoryModel
from app.llm import get_llm_client
from app.llm.prompts import ANSWER_SYSTEM_PROMPT


class PackedEvidenceItem(BaseModel):
    memory_id: str
    memory_type: str
    subtype: str
    title: str
    summary: str
    confidence: float
    valid_from: str
    valid_to: Optional[str] = None
    status: str
    score: float


class AnswerResponse(BaseModel):
    answer: str
    citations: List[str] = Field(default_factory=list)
    confidence: str = "medium"
    abstained: bool = False
    follow_ups: List[str] = Field(default_factory=list)
    evidence: List[PackedEvidenceItem] = Field(default_factory=list)
    reasoning_paths: List[List[str]] = Field(default_factory=list)


_CONFIDENCE_ORDER = {"low": 0, "medium": 1, "high": 2}


def evidence_confidence(items: List["PackedEvidenceItem"]) -> str:
    """Confidence derived from the evidence itself, never a constant.

    high   : the top item is active and well supported (stored confidence >= 0.8)
    medium : the top item is active but weakly supported, or only superseded history was found
    low    : nothing usable, or the top item is conflicted / expired / otherwise not trustworthy
    """
    if not items:
        return "low"
    top = items[0]
    if top.status == "active":
        return "high" if top.confidence >= 0.8 else "medium"
    if top.status == "superseded":
        return "medium"
    return "low"


def combine_confidence(llm_value: Optional[str], items: List["PackedEvidenceItem"]) -> str:
    """The answer is never more confident than the evidence allows, whatever the LLM claims."""
    derived = evidence_confidence(items)
    given = (llm_value or "").lower()
    if given not in _CONFIDENCE_ORDER:
        return derived
    return given if _CONFIDENCE_ORDER[given] <= _CONFIDENCE_ORDER[derived] else derived


class EvidencePacker:
    """Packs top ranked memory candidates within a strict token budget."""

    def __init__(self, token_budget: Optional[int] = None):
        self.token_budget = token_budget or get_settings().EVIDENCE_TOKEN_BUDGET

    def pack_evidence(
        self,
        ranked_candidates: List[Tuple[MemoryModel, float]]
    ) -> List[PackedEvidenceItem]:
        packed: List[PackedEvidenceItem] = []
        accumulated_chars = 0
        char_budget = self.token_budget * 4

        for mem, score in ranked_candidates:
            # Drop zero or negative score candidates
            if score <= 0.05:
                continue

            item = PackedEvidenceItem(
                memory_id=mem.id,
                memory_type=mem.memory_type,
                subtype=mem.subtype,
                title=mem.title,
                summary=mem.summary,
                confidence=mem.confidence,
                valid_from=mem.valid_from,
                valid_to=mem.valid_to,
                status=mem.status,
                score=round(score, 4)
            )

            item_len = len(item.model_dump_json())
            if accumulated_chars + item_len > char_budget and len(packed) > 0:
                break

            packed.append(item)
            accumulated_chars += item_len

        return packed

    def format_untrusted_evidence_block(
        self,
        items: List[PackedEvidenceItem],
        graph_paths: Optional[List[str]] = None
    ) -> str:
        """Wrap evidence inside untrusted tags to thwart prompt injection."""
        if not items and not graph_paths:
            return "<untrusted_evidence>\nNo relevant evidence found in OpsMemory.\n</untrusted_evidence>"

        lines = ["<untrusted_evidence>"]
        if graph_paths:
            lines.append("[Materialized Dependency Graph]")
            for gp in graph_paths:
                lines.append(f"Chain: {gp}")
            lines.append("")

        for it in items:
            valid_info = f"Valid: {it.valid_from}" + (f" to {it.valid_to}" if it.valid_to else " (current)")
            lines.append(
                f"[Memory ID: {it.memory_id}] ({it.memory_type}/{it.subtype}, Status: {it.status}, Conf: {it.confidence}, {valid_info})\n"
                f"Title: {it.title}\n"
                f"Summary: {it.summary}\n"
            )
        lines.append("</untrusted_evidence>")
        return "\n".join(lines)


class RAGEngine:
    """Executes evidence packing and grounded LLM answer generation."""

    def __init__(self):
        self.packer = EvidencePacker()

    async def generate_answer(
        self,
        query: str,
        ranked_candidates: List[Tuple[MemoryModel, float]],
        graph_paths: Optional[List[str]] = None,
        reasoning_paths: Optional[List[List[str]]] = None
    ) -> AnswerResponse:
        packed_items = self.packer.pack_evidence(ranked_candidates)
        r_paths = reasoning_paths or []

        # Immediate deterministic abstention if no relevant evidence found
        if not packed_items and not graph_paths:
            return AnswerResponse(
                answer="I do not have sufficient recorded evidence in OpsMemory to answer this question accurately.",
                citations=[],
                confidence="low",
                abstained=True,
                follow_ups=["Would you like to record this information in OpsMemory?"],
                evidence=[],
                reasoning_paths=r_paths
            )

        evidence_block = self.packer.format_untrusted_evidence_block(packed_items, graph_paths=graph_paths)
        llm_prompt = f"Question: {query}\n\nEvidence Records:\n{evidence_block}\n\nProvide your grounded response in JSON:"

        llm = get_llm_client()
        try:
            raw_result = await llm.generate_json(llm_prompt, ANSWER_SYSTEM_PROMPT)
            raw_citations = raw_result.get("citations", [])
            clean_citations: List[str] = []
            for c in raw_citations:
                if isinstance(c, dict):
                    clean_citations.append(str(c.get("memory_id") or c.get("id") or c))
                else:
                    clean_citations.append(str(c))
            return AnswerResponse(
                answer=raw_result.get("answer", "No answer generated."),
                citations=clean_citations or [it.memory_id for it in packed_items[:2]],
                confidence=combine_confidence(raw_result.get("confidence"), packed_items),
                abstained=raw_result.get("abstained", False),
                follow_ups=raw_result.get("follow_ups", []),
                evidence=packed_items,
                reasoning_paths=r_paths
            )
        except Exception:
            # Fallback deterministic answer synthesis from top evidence or graph paths
            if packed_items:
                top_item = packed_items[0]
                return AnswerResponse(
                    answer=f"Based on persistent records: {top_item.summary}",
                    citations=[top_item.memory_id],
                    confidence=evidence_confidence(packed_items),
                    abstained=False,
                    follow_ups=[],
                    evidence=packed_items,
                    reasoning_paths=r_paths
                )
            elif graph_paths:
                return AnswerResponse(
                    answer=f"Based on dependency topology: {'; '.join(graph_paths)}",
                    citations=[],
                    confidence="medium",
                    abstained=False,
                    follow_ups=[],
                    evidence=[],
                    reasoning_paths=r_paths
                )
            return AnswerResponse(
                answer="OpsMemory does not have verified evidence for this question.",
                citations=[],
                confidence="low",
                abstained=True,
                follow_ups=[],
                evidence=[],
                reasoning_paths=r_paths
            )