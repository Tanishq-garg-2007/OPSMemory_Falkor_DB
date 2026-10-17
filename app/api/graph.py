"""Graph inspection API endpoints for judges and UI."""
from typing import Any, Dict

from fastapi import APIRouter, Depends, Query

from app.dependencies import TenantContext, get_tenant_context
from app.memory.repository import MemoryRepository, get_memory_repository

router = APIRouter(prefix="/v1/graph", tags=["Graph"])


@router.get("/context")
async def get_graph_context(
    context: TenantContext = Depends(get_tenant_context),
    repo: MemoryRepository = Depends(get_memory_repository)
) -> Dict[str, Any]:
    """Inspect active FalkorDB graph state: active nodes, edges, turns, agent handoffs, and indexes."""
    return repo.get_graph_context(context)


@router.get("/topology")
async def get_graph_topology(
    max_nodes: int = Query(150, ge=10, le=500),
    context: TenantContext = Depends(get_tenant_context),
    repo: MemoryRepository = Depends(get_memory_repository),
) -> Dict[str, Any]:
    """Nodes and links of the tenant graph, shaped for drawing. Capped by max_nodes."""
    graph = repo._graph(context)
    tid = context.tenant_id

    node_res = repo._exec(
        graph,
        "MATCH (n {tenant_id: $tid}) "
        "WHERE n.status IS NULL OR n.status <> 'deleted' "
        "RETURN n.id, labels(n), n.name, n.title, n.task_type, n.role, n.status "
        f"LIMIT {int(max_nodes)}",
        {"tid": tid},
    )

    nodes = []
    for node_id, labels, name, title, task_type, role, status in node_res.result_set:
        nodes.append({
            "id": node_id,
            "type": labels[0] if labels else "Unknown",
            "label": name or title or task_type or role or node_id,
            "status": status or "active",
        })
    known_ids = {n["id"] for n in nodes}

    edge_res = repo._exec(
        graph,
        "MATCH (a {tenant_id: $tid})-[r]->(b {tenant_id: $tid}) "
        "RETURN a.id, b.id, type(r) LIMIT 2000",
        {"tid": tid},
    )
    links = [
        {"source": a, "target": b, "type": rel}
        for a, b, rel in edge_res.result_set
        if a in known_ids and b in known_ids
    ]

    return {
        "tenant_id": tid,
        "nodes": nodes,
        "links": links,
        "truncated": len(nodes) >= max_nodes,
    }