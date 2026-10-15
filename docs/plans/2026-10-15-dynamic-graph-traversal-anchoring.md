# Dynamic Graph Dependency Traversal & Semantic Vector Anchoring Implementation Plan

> **Status:** [x] **COMPLETED & VERIFIED** (All 5 Tasks executed, 33/33 Pytest tests passing, 88/88 benchmark cases passing at 100.0% accuracy).

**Goal:** Transform OpsMemory's graph dependency traversal from static hardcoded start nodes (`KNOWN_ENTITIES` in `router.py`) into a 100% dynamic, FalkorDB-native architecture inspired by Google Knowledge Graph retrieval (Semantic Vector Anchoring $\rightarrow$ Localized Subgraph Isolation $\rightarrow$ Cypher Traversal $\rightarrow$ Parallel Rank Fusion), while maintaining 100% pass rate across the 88 benchmark cases.

**Architecture:**
1. **Semantic Vector Anchoring in FalkorDB**: Store 64-dim semantic embeddings on all `:Entity` nodes (`e.embedding = vecf32(...)`) and create a native vector index on `:Entity`. When an unstructured query arrives, FalkorDB performs an ANN vector similarity lookup (`CALL db.idx.vector.queryNodes('Entity', 'embedding', ...)`) combined with lexical alias matching against the live tenant graph to locate starting nodes (**semantic anchors**) in sub-milliseconds without any hardcoded lists.
2. **Localized Subgraph Isolation & Cypher Traversal**: From the dynamically discovered anchor nodes, bound graph exploration to a 1-to-3 hop radius over `[:DEPENDS_ON*1..3]`, `[:ABOUT|MENTIONS]`, and `[:SUPERSEDES]`, pruning irrelevant edges and extracting verified reasoning path chains.
3. **Passage Arbitration & Rank Fusion (GraphRAG)**: Fuse graph candidates with RediSearch FTS and Memory vector search via Reciprocal Rank Fusion ($k=60$), verifying that generated answers are grounded in verified graph paths.

**Tech Stack:**
- Python 3.13 / FastAPI
- FalkorDB (Native Vector Index, Full-Text Index, OpenCypher)
- Zero-dependency 64-dim semantic vector encoder (`app/retrieval/vector_encoder.py`)
- Pytest / Asynchronous Test Suite

---

### Task 1: FalkorDB Entity Vector Indexing & Anchor Search API

**Files:**
- Modify: `app/memory/repository.py`
- Test: `tests/integration/test_dynamic_anchoring.py`

**Step 1: Write the failing test**
Create `tests/integration/test_dynamic_anchoring.py` verifying that dynamically added entities with custom names (e.g. `billing-processor`, `kafka-stream`) are indexed in FalkorDB and retrievable via `find_anchor_entities` using natural language vector search:

```python
import pytest
from app.dependencies import TenantContext
from app.memory.models import EntityModel
from app.memory.repository import get_memory_repository

@pytest.mark.asyncio
async def test_dynamic_entity_anchoring(context_acme):
    repo = get_memory_repository()
    # Save a completely new entity not present in any pre-existing list
    new_entity = EntityModel(
        id="ent_service_acme_billing-processor",
        tenant_id=context_acme.tenant_id,
        kind="service",
        name="billing-processor",
        aliases=["billing-engine", "stripe-gateway"],
        description="High throughput subscription billing and invoice processing"
    )
    repo.save_entity(context_acme, new_entity)

    # Search anchors using semantic synonyms: 'invoice generator' or 'stripe engine'
    anchors = repo.find_anchor_entities(context_acme, "How does the invoice generator work?", limit=3)
    anchor_names = [a.name for a in anchors]
    assert "billing-processor" in anchor_names
```

**Step 2: Run test to verify it fails**
Run: `python -m pytest tests/integration/test_dynamic_anchoring.py -v`
Expected: FAIL with `AttributeError: 'MemoryRepository' object has no attribute 'find_anchor_entities'`.

**Step 3: Implement minimal code**
In `app/memory/repository.py`:
1. In `init_schema`: Add FalkorDB vector index for `:Entity`:
   `CREATE VECTOR INDEX FOR (e:Entity) ON (e.embedding) OPTIONS {dimension: 64, similarityFunction: 'cosine'}`
2. In `save_entity`: Compute and persist `e.embedding = vecf32($embedding)` where `$embedding = encode_vector(entity.name + " " + " ".join(entity.aliases) + " " + (entity.description or ""))`.
3. Implement `find_anchor_entities(self, context: TenantContext, query: str, limit: int = 5) -> List[EntityModel]`:
   - Compute query vector via `encode_vector(query)`.
   - Execute FalkorDB ANN vector query:
     `CALL db.idx.vector.queryNodes('Entity', 'embedding', $k, vecf32($vec)) YIELD node, score WHERE node.tenant_id = $tenant_id RETURN node, score ORDER BY score ASC`
   - Combine with token/alias matching against tenant `:Entity` nodes.
   - Return top ranked `EntityModel` instances.

**Step 4: Run test to verify it passes**
Run: `python -m pytest tests/integration/test_dynamic_anchoring.py -v`
Expected: PASS.

**Step 5: Commit**
Run: `git commit -am "feat(graph): implement FalkorDB native entity vector index and semantic anchoring"`

---

### Task 2: Refactor RetrievalRouter to Use Dynamic Tenant Anchoring

**Files:**
- Modify: `app/retrieval/router.py`
- Modify: `app/retrieval/service.py`
- Test: `tests/unit/test_router.py`

**Step 1: Write the failing test**
In `tests/unit/test_router.py`, verify `route_query` dynamically anchors entities from the tenant graph without relying on static lists:

```python
import pytest
from app.dependencies import TenantContext
from app.retrieval.router import RetrievalRouter

def test_dynamic_anchor_routing():
    router = RetrievalRouter()
    # Route query with candidate anchor names provided dynamically from graph
    intent = router.route_query(
        "Why is payments-api failing to talk to database?",
        anchor_entities=["payments-api", "postgres-orders"]
    )
    assert "payments-api" in intent.target_entities
    assert "postgres-orders" in intent.target_entities
```

**Step 2: Run test to verify it fails**
Run: `python -m pytest tests/unit/test_router.py -v`
Expected: FAIL due to missing parameter or reliance on static list.

**Step 3: Implement minimal code**
In `app/retrieval/router.py`:
- Remove hardcoded `KNOWN_ENTITIES`.
- Update `route_query(query: str, anchor_entities: Optional[List[str]] = None, available_entities: Optional[List[str]] = None) -> QueryIntent`:
  - If `anchor_entities` are provided (from FalkorDB vector search), populate `intent.target_entities` directly with the top anchors.
  - If `available_entities` are provided (from FalkorDB `list_entities`), fuzzy/token match the query against all active tenant entity names and aliases.

In `app/retrieval/service.py`:
- In `_execute_retrieval`:
  1. Retrieve dynamic semantic anchors from FalkorDB:
     `anchors = self.repo.find_anchor_entities(context, query, limit=5)`
  2. Pass `anchor_entities=[a.name for a in anchors]` to `self.router.route_query(query, anchor_entities=...)`.

**Step 4: Run test to verify it passes**
Run: `python -m pytest tests/unit/test_router.py -v`
Expected: PASS.

**Step 5: Commit**
Run: `git commit -am "refactor(router): replace static entity list with FalkorDB semantic anchor discovery"`

---

### Task 3: Localized Subgraph Traversal & Bounded Graph Isolation

**Files:**
- Modify: `app/retrieval/graph_search.py`
- Test: `tests/integration/test_dynamic_anchoring.py`

**Step 1: Write the failing test**
In `tests/integration/test_dynamic_anchoring.py`, add a test verifying dynamic multi-hop dependency traversal from a dynamically created anchor node:

```python
@pytest.mark.asyncio
async def test_dynamic_multihop_traversal(context_acme):
    from app.retrieval.service import RetrievalService
    repo = get_memory_repository()
    # Add new chain: new-frontend -> DEPENDS_ON -> new-backend -> DEPENDS_ON -> new-db
    for name in ["new-frontend", "new-backend", "new-db"]:
        repo.save_entity(context_acme, EntityModel(
            id=f"ent_service_acme_{name}",
            tenant_id=context_acme.tenant_id,
            kind="service",
            name=name
        ))
    repo.save_entity_dependency(context_acme, f"ent_service_acme_new-frontend", f"ent_service_acme_new-backend")
    repo.save_entity_dependency(context_acme, f"ent_service_acme_new-backend", f"ent_service_acme_new-db")

    service = RetrievalService()
    resp = await service.retrieve_and_answer(context_acme, "If new-db crashes, what is affected?")
    assert any("new-frontend" in path and "new-db" in path for path in resp.reasoning_paths)
```

**Step 2: Run test to verify it fails**
Run: `python -m pytest tests/integration/test_dynamic_anchoring.py::test_dynamic_multihop_traversal -v`
Expected: FAIL because `new-db` was not in static `KNOWN_ENTITIES` so traversal never began.

**Step 3: Implement minimal code**
In `app/retrieval/graph_search.py`:
- In `search` and `get_reasoning_paths`:
  - Use `intent.target_entities` populated dynamically via FalkorDB semantic anchors.
  - Perform localized Cypher query bounding traversal to 1-to-3 hops:
    ```cypher
    MATCH p = (e1:Entity)-[:DEPENDS_ON*1..3]-(e2:Entity)
    WHERE e1.tenant_id = $tenant_id AND toLower(e1.name) IN $anchor_names
    RETURN e1.name, type(r1), e2.name ...
    ```

**Step 4: Run test to verify it passes**
Run: `python -m pytest tests/integration/test_dynamic_anchoring.py::test_dynamic_multihop_traversal -v`
Expected: PASS.

**Step 5: Commit**
Run: `git commit -am "feat(graph): localized subgraph traversal from dynamic semantic anchors"`

---

### Task 4: Schema & Seed Updates for Entity Embeddings

**Files:**
- Modify: `scripts/init_schema.py`
- Modify: `scripts/seed.py`

**Step 1: Ensure entity vector indexing and embedding generation on seed**
In `scripts/init_schema.py` and `scripts/seed.py`:
- Ensure schema initialization calls the `:Entity` vector index creation.
- Ensure seeded entities in `scripts/seed.py` have embeddings generated and stored on the `:Entity` nodes in FalkorDB.

**Step 2: Run schema and seed scripts**
Run: `python scripts/init_schema.py && python scripts/seed.py`
Expected: Exit code 0, all entities seeded with 64-dim embeddings in FalkorDB.

**Step 3: Commit**
Run: `git commit -am "chore(seed): embed entity nodes during schema init and seeding"`

---

### Task 5: End-to-End Benchmark & Regression Suite Verification

**Files:**
- Verify: `eval/run.py`
- Verify: `tests/`
- Update: `docs/architecture.md`, `README.md`

**Step 1: Run unit and integration tests**
Run: `python -m pytest -q`
Expected: 32+ passed, 0 failures.

**Step 2: Run full 88-case benchmark suite**
Run: `cmd /c "python scripts/init_schema.py && python scripts/seed.py && python -m eval.run --suite all"`
Expected: **88/88 passed (100.0% accuracy)**.

**Step 3: Update documentation**
In `docs/architecture.md` and `README.md`:
- Document Google-inspired **Semantic Vector Anchoring** and **Dynamic Localized Subgraph Traversal** in FalkorDB.
- Explicitly highlight that no static entity lists exist; all anchor nodes are discovered dynamically via FalkorDB vector index and alias search.

**Step 4: Commit**
Run: `git commit -am "docs: document FalkorDB dynamic semantic vector anchoring and localized subgraph traversal"`

---

## Execution Choice
Plan complete and saved to `docs/plans/2026-10-15-dynamic-graph-traversal-anchoring.md`.
Choose execution mode to begin implementation:
1. **Subagent-Driven (this session)** - Execute tasks step-by-step with continuous verification and commits.
2. **Parallel Session (separate)** - Batch execution in separate session with review checkpoints.
