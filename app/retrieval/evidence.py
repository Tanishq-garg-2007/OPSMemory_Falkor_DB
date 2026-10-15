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

    def format_untrusted_evidence_block(self, items: List[PackedEvidenceItem]) -> str:
        """Wrap evidence inside untrusted tags to thwart prompt injection."""
        if not items:
            return "<untrusted_evidence>\nNo relevant evidence found in OpsMemory.\n</untrusted_evidence>"

        lines = ["<untrusted_evidence>"]
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
        ranked_candidates: List[Tuple[MemoryModel, float]]
    ) -> AnswerResponse:
        packed_items = self.packer.pack_evidence(ranked_candidates)

        # Immediate deterministic abstention if no relevant evidence found
        if not packed_items:
            return AnswerResponse(
                answer="I do not have sufficient recorded evidence in OpsMemory to answer this question accurately.",
                citations=[],
                confidence="low",
                abstained=True,
                follow_ups=["Would you like to record this information in OpsMemory?"],
                evidence=[]
            )

        evidence_block = self.packer.format_untrusted_evidence_block(packed_items)
        llm_prompt = f"Question: {query}\n\nEvidence Records:\n{evidence_block}\n\nProvide your grounded response in JSON:"

        llm = get_llm_client()
        try:
            raw_result = await llm.generate_json(llm_prompt, ANSWER_SYSTEM_PROMPT)
            return AnswerResponse(
                answer=raw_result.get("answer", "No answer generated."),
                citations=raw_result.get("citations", [it.memory_id for it in packed_items[:2]]),
                confidence=raw_result.get("confidence", "high"),
                abstained=raw_result.get("abstained", False),
                follow_ups=raw_result.get("follow_ups", []),
                evidence=packed_items
            )
        except Exception:
            # Fallback deterministic answer synthesis from top evidence
            top_item = packed_items[0]
            return AnswerResponse(
                answer=f"Based on persistent records: {top_item.summary}",
                citations=[top_item.memory_id],
                confidence="high",
                abstained=False,
                follow_ups=[],
                evidence=packed_items
            )
