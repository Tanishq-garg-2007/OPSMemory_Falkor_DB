"""Memory Lifecycle Manager orchestrating extraction, validation, supersession, and storage."""
from typing import Optional, List, Dict, Any
from app.core.time import utc_now_iso
from app.core.ids import memory_id, source_id
from app.core.hashing import memory_idempotency_key
from app.dependencies import TenantContext
from app.memory.models import MemoryModel, SourceModel, EntityModel
from app.memory.repository import MemoryRepository, get_memory_repository
from app.memory.entity_resolution import EntityResolver
from app.memory.conflicts import CONFIDENCE_MAP, detect_semantic_conflict, should_supersede
from app.core.logging import get_logger

logger = get_logger("memory_lifecycle")


class MemoryLifecycle:
    """Orchestrates end-to-end memory lifecycle."""
    def __init__(self, repo: Optional[MemoryRepository] = None):
        self.repo = repo or get_memory_repository()
        self.resolver = EntityResolver(self.repo)

    def record_source(
        self,
        context: TenantContext,
        conversation_id: Optional[str],
        message_id: Optional[str],
        source_type: str = "conversation",
        raw_text: Optional[str] = None
    ) -> SourceModel:
        sid = source_id(conversation_id or "default", message_id or "msg")
        src = SourceModel(
            id=sid,
            source_type=source_type,
            conversation_id=conversation_id,
            message_id=message_id,
            tenant_id=context.tenant_id,
            raw_text_ref=raw_text
        )
        return self.repo.save_source(context, src)

    def store_memory(
        self,
        context: TenantContext,
        memory_type: str,
        subtype: str,
        title: str,
        summary: str,
        entity_names: List[str],
        source_id: Optional[str] = None,
        confidence_basis: str = "user_explicit",
        extraction_method: str = "deterministic",
        supersedes_id: Optional[str] = None,
        content_json: Optional[str] = None
    ) -> MemoryModel:
        """Validate, check conflicts/supersession, and persist memory."""
        # Normalize and ensure entities exist
        resolved_entities = []
        for name in entity_names:
            ent = self.resolver.resolve_or_create(context, kind="service", name=name)
            resolved_entities.append(ent.name)

        confidence = CONFIDENCE_MAP.get(confidence_basis, 0.8)
        now = utc_now_iso()
        mem_id = memory_id(memory_type, context.tenant_id, subtype, title)
        idemp_key = memory_idempotency_key(
            tenant_id=context.tenant_id,
            source_id=source_id or "direct",
            memory_type=memory_type,
            subtype=subtype,
            title=title,
            core_statement=summary
        )

        incoming = MemoryModel(
            id=mem_id,
            tenant_id=context.tenant_id,
            memory_type=memory_type,
            subtype=subtype,
            title=title,
            summary=summary,
            content_json=content_json,
            status="active",
            confidence=confidence,
            valid_from=now,
            valid_to=None,
            observed_at=now,
            created_at=now,
            updated_at=now,
            extraction_method=extraction_method,
            idempotency_key=idemp_key,
            entities=resolved_entities,
            source_id=source_id,
            supersedes_id=supersedes_id
        )

        # Check existing active memories for semantic conflict / supersession
        existing_memories = self.repo.list_memories(context, status="active", memory_type=memory_type)
        explicit_update = supersedes_id is not None or confidence_basis == "user_correction"
        for old_mem in existing_memories:
            if not detect_semantic_conflict(old_mem, incoming):
                continue
            if explicit_update or should_supersede(old_mem, incoming):
                logger.info(f"Superseding memory {old_mem.id} with new memory {incoming.id}")
                self.repo.update_memory_status(
                    context=context,
                    memory_id=old_mem.id,
                    new_status="superseded",
                    valid_to=now,
                    expected_version=old_mem.version,
                    superseded_by=incoming.id
                )
                incoming.supersedes_id = old_mem.id
            else:
                # Incoming is a clearly weaker source than what we already trust.
                incoming.status = "conflicted"

        return self.repo.save_memory(context, incoming)

    def forget_memory(self, context: TenantContext, memory_id: str, hard_delete: bool = False) -> bool:
        """Forget memory by updating status to deleted (or hard deleting) and removing from FTS."""
        return self.repo.delete_memory(context, memory_id, hard_delete=hard_delete)