"""Entity normalization and resolution logic."""
from typing import Optional, List
from app.core.hashing import slugify
from app.core.ids import entity_id
from app.dependencies import TenantContext
from app.memory.models import EntityModel
from app.memory.repository import MemoryRepository, get_memory_repository
from app.memory.signals import names_equivalent
from app.retrieval.vector_encoder import encode_vector


class EntityResolver:
    """Normalizes and resolves entity candidates within tenant scope."""
    def __init__(self, repo: Optional[MemoryRepository] = None):
        self.repo = repo or get_memory_repository()

    def normalize_name(self, name: str) -> str:
        """Slugify and clean entity name."""
        return slugify(name)

    def _sim(self, v1: List[float], v2: List[float]) -> float:
        return sum(x * y for x, y in zip(v1, v2))

    def resolve_or_create(
        self,
        context: TenantContext,
        kind: str,
        name: str,
        aliases: Optional[List[str]] = None,
        description: Optional[str] = None
    ) -> EntityModel:
        """Resolve entity by name, aliases, or vector similarity, or create new entity."""
        norm = name.strip().lower()
        slug = self.normalize_name(name)
        eid = entity_id(kind, slug, tenant_id=context.tenant_id)
        norm_vec = encode_vector(norm)

        # 1. Match against existing entities in the tenant graph
        existing_entities = self.repo.list_entities(context)
        best_match: Optional[EntityModel] = None
        best_sim: float = 0.0

        for ent in existing_entities:
            ent_norm = ent.name.strip().lower()
            ent_aliases = [a.strip().lower() for a in ent.aliases]
            # Exact name or alias match
            if ent_norm == norm or norm in ent_aliases or slug in ent_aliases:
                best_match = ent
                break
            # Same-kind surface-form variants ('auth-svc' vs 'authservice') that the hash vector misses
            if ent.kind == kind and names_equivalent(name, ent.name):
                best_match = ent
                break
            # Vector/token similarity
            ent_vec = encode_vector(ent_norm)
            sim = self._sim(norm_vec, ent_vec)
            if sim > 0.88 and sim > best_sim:
                best_match = ent
                best_sim = sim

        if best_match:
            # Merge new surface form and aliases into existing entity
            existing_aliases = set(best_match.aliases)
            existing_aliases.add(norm)
            existing_aliases.add(slug)
            if aliases:
                for a in aliases:
                    existing_aliases.add(self.normalize_name(a))
            best_match.aliases = sorted(list(existing_aliases))
            if description and not best_match.description:
                best_match.description = description
            upserted = self.repo.upsert_entity(context, best_match)
            return upserted or best_match

        # 2. No match found: create new entity
        clean_aliases = sorted(list(set([slug] + [self.normalize_name(a) for a in (aliases or []) if a])))
        new_entity = EntityModel(
            id=eid,
            kind=kind,
            name=name,
            aliases=clean_aliases,
            description=description,
            tenant_id=context.tenant_id
        )
        upserted = self.repo.upsert_entity(context, new_entity)
        return upserted or new_entity