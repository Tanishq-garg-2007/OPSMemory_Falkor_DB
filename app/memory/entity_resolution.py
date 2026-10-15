"""Entity normalization and resolution logic."""
from typing import Optional, List
from app.core.hashing import slugify
from app.core.ids import entity_id
from app.dependencies import TenantContext
from app.memory.models import EntityModel
from app.memory.repository import MemoryRepository, get_memory_repository


class EntityResolver:
    """Normalizes and resolves entity candidates within tenant scope."""
    def __init__(self, repo: Optional[MemoryRepository] = None):
        self.repo = repo or get_memory_repository()

    def normalize_name(self, name: str) -> str:
        """Slugify and clean entity name."""
        return slugify(name)

    def resolve_or_create(
        self,
        context: TenantContext,
        kind: str,
        name: str,
        aliases: Optional[List[str]] = None,
        description: Optional[str] = None
    ) -> EntityModel:
        """Resolve entity by slug or alias, or create new entity within tenant boundary."""
        slug = self.normalize_name(name)
        eid = entity_id(kind, slug, tenant_id=context.tenant_id)

        existing = self.repo.get_entity(context, eid)
        if existing:
            # Merge any new aliases
            existing_aliases = set(existing.aliases)
            if aliases:
                existing_aliases.update(self.normalize_name(a) for a in aliases)
            existing.aliases = sorted(list(existing_aliases))
            if description and not existing.description:
                existing.description = description
            upserted = self.repo.upsert_entity(context, existing)
            return upserted or existing

        # Check aliases among all entities of this kind in tenant
        all_entities = self.repo.list_entities(context, kind=kind)
        for ent in all_entities:
            if slug in ent.aliases or name.lower() == ent.name.lower():
                return ent

        # Create new entity
        clean_aliases = [self.normalize_name(a) for a in (aliases or []) if a]
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
