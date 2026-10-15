"""Reciprocal Rank Fusion (RRF) with deterministic boosts and penalties."""
from typing import List, Tuple, Dict
from app.memory.models import MemoryModel
from app.retrieval.router import QueryIntent
from app.core.time import parse_iso, utc_now
from app.memory.signals import reference_tokens


class RankFusion:
    """Combines graph, FTS, and vector candidates via RRF and score modifiers."""

    def __init__(self, k: int = 60):
        self.k = k

    def fuse(
        self,
        intent: QueryIntent,
        graph_candidates: List[Tuple[MemoryModel, float]],
        fts_candidates: List[Tuple[MemoryModel, float]],
        vector_candidates: List[Tuple[MemoryModel, float]]
    ) -> List[Tuple[MemoryModel, float]]:
        # Map memory_id to memory instance
        memory_map: Dict[str, MemoryModel] = {}
        rrf_scores: Dict[str, float] = {}
        graph_scores: Dict[str, float] = {}

        # 1. RRF from graph candidates
        for rank, (mem, score) in enumerate(graph_candidates, start=1):
            memory_map[mem.id] = mem
            graph_scores[mem.id] = score
            rrf_scores[mem.id] = rrf_scores.get(mem.id, 0.0) + (1.0 / (self.k + rank))

        # 2. RRF from FTS candidates
        for rank, (mem, score) in enumerate(fts_candidates, start=1):
            memory_map[mem.id] = mem
            rrf_scores[mem.id] = rrf_scores.get(mem.id, 0.0) + (1.0 / (self.k + rank))

        # 3. RRF from vector candidates
        for rank, (mem, score) in enumerate(vector_candidates, start=1):
            memory_map[mem.id] = mem
            rrf_scores[mem.id] = rrf_scores.get(mem.id, 0.0) + (1.0 / (self.k + rank))

        # 4. Calculate final score with boosts and status penalties
        final_ranked: List[Tuple[MemoryModel, float]] = []
        now = utc_now()
        q_low = intent.raw_query.lower()
        query_refs = reference_tokens(q_low)
        # A query that names a specific version / incident id, or asks about change over time, targets a
        # particular past state, so superseded memories must not be penalised for it.
        is_direct_target = bool(query_refs) or any(
            term in q_low for term in ["previous", "prior", "before", "why was", "changed", "was that", "used to", "resolved"]
        )

        for mem_id, mem in memory_map.items():
            if mem.status == "deleted":
                continue

            rrf = rrf_scores[mem_id]
            confidence = mem.confidence
            graph_prox = graph_scores.get(mem_id, 0.0)

            # Recency score (decay over 30 days unless historical / direct target query)
            try:
                age_days = (now - parse_iso(mem.created_at)).total_seconds() / 86400.0
                recency_score = 1.0 if (intent.is_historical or is_direct_target) else max(0.0, 1.0 - (age_days / 30.0))
            except Exception:
                recency_score = 0.5

            # Procedural and decision intent match
            procedural_match = 1.0 if (intent.is_procedural and mem.memory_type == "procedural") else 0.0
            decision_match = 1.0 if (("decision" in q_low or "rollback" in q_low or "causal" in q_low or "resolved" in q_low) and mem.subtype == "decision") else 0.0

            # Distinctive entity / version match boost
            mem_text = (mem.title.lower() + " " + mem.summary.lower())
            distinct_match = 1.0 if (query_refs & reference_tokens(mem_text)) else 0.0

            # Target entity and ownership intent matches
            entity_match = 1.0 if any(e in intent.target_entities for e in mem.entities) else 0.0
            ownership_match = 1.0 if (("owner" in q_low or "owns" in q_low or "team" in q_low) and ("owner" in mem_text or "owned" in mem_text or "team" in mem_text)) else 0.0

            # Status penalty
            if mem.status == "active":
                status_penalty = 0.0
            elif mem.status == "superseded":
                status_penalty = 0.0 if (intent.is_historical or is_direct_target) else 0.30
            elif mem.status == "conflicted":
                status_penalty = 0.50
            elif mem.status == "expired":
                status_penalty = 0.70
            else:
                status_penalty = 0.50

            final_score = (
                rrf
                + (0.20 * confidence)
                + (0.15 * recency_score)
                + (0.20 * graph_prox)
                + (0.15 * procedural_match)
                + (0.15 * decision_match)
                + (0.25 * distinct_match)
                + (0.15 * entity_match)
                + (0.15 * ownership_match)
                - (0.30 * status_penalty)
            )

            final_ranked.append((mem, final_score))

        final_ranked.sort(key=lambda x: x[1], reverse=True)
        return final_ranked