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

    # Cypher is directed on purpose. An undirected match (-[r]-) printed edges
    # backwards, e.g. "auth-service DEPENDS_ON checkout-ui" when the stored fact
    # is "checkout-ui DEPENDS_ON auth-service".
    _DEPENDENCIES_CYPHER = """
        MATCH (e1:Entity {tenant_id: $tenant_id})
        WHERE e1.id = $eid OR toLower(e1.name) = toLower($ent_name)
        MATCH (e1)-[:DEPENDS_ON]->(e2:Entity {tenant_id: $tenant_id})
        OPTIONAL MATCH (e2)-[:DEPENDS_ON]->(e3:Entity {tenant_id: $tenant_id})
        WHERE e3 <> e1
        RETURN e1.name, e2.name, e3.name
    """
    _DEPENDENTS_CYPHER = """
        MATCH (e1:Entity {tenant_id: $tenant_id})
        WHERE e1.id = $eid OR toLower(e1.name) = toLower($ent_name)
        MATCH (e2:Entity {tenant_id: $tenant_id})-[:DEPENDS_ON]->(e1)
        OPTIONAL MATCH (e3:Entity {tenant_id: $tenant_id})-[:DEPENDS_ON]->(e2)
        WHERE e3 <> e1
        RETURN e3.name, e2.name, e1.name
    """

    def get_reasoning_paths(self, context: TenantContext, intent: QueryIntent) -> List[List[str]]:
        """Readable 1-2 hop chains, always printed in the real edge direction.

        Example: ['checkout-ui', 'DEPENDS_ON', 'payments-api', 'DEPENDS_ON', 'postgres-orders']
        means checkout-ui depends on payments-api, which depends on postgres-orders.
        """
        paths: List[List[str]] = []
        seen = set()
        direction = getattr(intent, "dependency_direction", "both")
        queries = []
        if direction in ("dependencies", "both"):
            queries.append(self._DEPENDENCIES_CYPHER)
        if direction in ("dependents", "both"):
            queries.append(self._DEPENDENTS_CYPHER)

        for ent_name in intent.target_entities:
            eid = entity_id("service", ent_name, tenant_id=context.tenant_id)
            params = {"eid": eid, "ent_name": ent_name, "tenant_id": context.tenant_id}
            for cypher in queries:
                for row in self.repo.run_query(context, cypher, params).result_set:
                    # Rows are already ordered tail -> head along real edges.
                    names = [n for n in (row[0], row[1], row[2]) if n]
                    if len(names) < 2:
                        continue
                    chain: List[str] = []
                    for i, name in enumerate(names):
                        if i:
                            chain.append("DEPENDS_ON")
                        chain.append(name)
                    key = "->".join(chain)
                    if key not in seen:
                        seen.add(key)
                        paths.append(chain)
        return paths

    def get_dependency_paths(self, context: TenantContext, intent: QueryIntent) -> List[str]:
        """Materialize 1-hop and 2-hop dependency chains deterministically from graph edges in FalkorDB."""
        reasoning = self.get_reasoning_paths(context, intent)
        if reasoning:
            return [" -> ".join(c) for c in reasoning]
        return []