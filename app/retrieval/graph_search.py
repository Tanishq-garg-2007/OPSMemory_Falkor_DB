"""Graph-based memory candidate search and traversal."""
from typing import List, Tuple, Set, Optional
from app.dependencies import TenantContext
from app.memory.models import MemoryModel
from app.memory.repository import MemoryRepository, get_memory_repository
from app.retrieval.router import QueryIntent
from app.core.ids import entity_id


class GraphSearcher:
    """Retrieves memory candidates using entity relationships and graph adjacency."""
    def __init__(self, repo: Optional[MemoryRepository] = None):
        self.repo = repo or get_memory_repository()

    def search(
        self,
        context: TenantContext,
        intent: QueryIntent,
        limit: int = 20
    ) -> List[Tuple[MemoryModel, float]]:
        candidates: List[Tuple[MemoryModel, float]] = []
        seen_ids: Set[str] = set()

        # 1. Collect entities and 1-2 hop dependencies
        target_entities = set(intent.target_entities)
        for ent_name in intent.target_entities:
            eid = entity_id("service", ent_name, tenant_id=context.tenant_id)
            deps = self.repo.get_entity_dependencies(context, eid, hops=2)
            for d in deps:
                target_entities.add(d.name)

        # 2. Retrieve memories linked to target entities
        all_memories = self.repo.list_memories(context)
        for mem in all_memories:
            if mem.status == "deleted":
                continue

            proximity_score = 0.0
            # Check direct entity mentions
            matches = set(mem.entities).intersection(target_entities)
            if matches:
                proximity_score += 0.5 * len(matches)

            # Check incident ID match
            if intent.incident_id and intent.incident_id in (mem.title.lower() + " " + mem.summary.lower()):
                proximity_score += 1.0

            if proximity_score > 0 and mem.id not in seen_ids:
                seen_ids.add(mem.id)
                candidates.append((mem, min(proximity_score, 1.0)))

        # Sort by graph score descending
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[:limit]
