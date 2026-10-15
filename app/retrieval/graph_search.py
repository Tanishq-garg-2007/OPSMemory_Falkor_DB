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

    def get_reasoning_paths(self, context: TenantContext, intent: QueryIntent) -> List[List[str]]:
        """Extract readable path chains (e.g. ['postgres-orders', 'DEPENDS_ON', 'payments-api', 'DEPENDS_ON', 'checkout-ui'])."""
        paths: List[List[str]] = []
        seen = set()
        if getattr(self.repo, "_falkor_connected", False) and self.repo._falkor_client:
            try:
                graph = self.repo._get_graph(context.graph_name)
                for ent_name in intent.target_entities:
                    eid = entity_id("service", ent_name, tenant_id=context.tenant_id)
                    cypher = """
                    MATCH (e1:Entity)
                    WHERE (e1.id = $eid OR toLower(e1.name) = toLower($ent_name)) AND e1.tenant_id = $tenant_id
                    MATCH (e1)-[r1:DEPENDS_ON]-(e2:Entity {tenant_id: $tenant_id})
                    OPTIONAL MATCH (e2)-[r2:DEPENDS_ON]-(e3:Entity {tenant_id: $tenant_id})
                    WHERE e3 IS NULL OR (e3 <> e1 AND e3 <> e2)
                    RETURN e1.name, type(r1), e2.name, type(r2), e3.name
                    """
                    res = graph.query(cypher, {"eid": eid, "ent_name": ent_name, "tenant_id": context.tenant_id})
                    for row in res.result_set:
                        n1, r1, n2, r2, n3 = row[0], row[1], row[2], row[3], row[4]
                        if n3 and r2:
                            chain = [n1, r1, n2, r2, n3]
                        else:
                            chain = [n1, r1, n2]
                        chain_key = "->".join(chain)
                        if chain_key not in seen:
                            seen.add(chain_key)
                            paths.append(chain)
                if paths:
                    return paths
            except Exception:
                pass
        return paths

    def get_dependency_paths(self, context: TenantContext, intent: QueryIntent) -> List[str]:
        """Materialize 1-hop and 2-hop dependency chains deterministically from graph edges in FalkorDB."""
        reasoning = self.get_reasoning_paths(context, intent)
        if reasoning:
            return [" -> ".join(c) for c in reasoning]
        return []
