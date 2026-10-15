"""Domain models for entities, memories, sources, tasks, and conversations."""
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field, field_validator
from app.core.time import utc_now_iso


MemoryType = Literal["episodic", "semantic", "procedural"]
MemoryStatus = Literal["active", "superseded", "expired", "deleted", "conflicted"]
ExtractionMethod = Literal["user_explicit", "deterministic", "llm"]
SourceType = Literal["conversation", "user_correction", "agent_inference", "seed", "admin"]
TaskStatus = Literal["pending", "claimed", "done", "failed"]


class EntityModel(BaseModel):
    id: str
    kind: str
    name: str
    aliases: List[str] = Field(default_factory=list)
    description: Optional[str] = None
    tenant_id: str
    version: int = 1
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class SourceModel(BaseModel):
    id: str
    source_type: SourceType = "conversation"
    conversation_id: Optional[str] = None
    message_id: Optional[str] = None
    tenant_id: str
    created_at: str = Field(default_factory=utc_now_iso)
    raw_text_ref: Optional[str] = None


class MemoryModel(BaseModel):
    id: str
    tenant_id: str
    memory_type: MemoryType
    subtype: str
    title: str
    summary: str
    content_json: Optional[str] = None
    status: MemoryStatus = "active"
    confidence: float = Field(ge=0.0, le=1.0, default=0.8)
    valid_from: str = Field(default_factory=utc_now_iso)
    valid_to: Optional[str] = None
    observed_at: str = Field(default_factory=utc_now_iso)
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)
    version: int = 1
    created_by: str = "system"
    extraction_method: ExtractionMethod = "deterministic"
    idempotency_key: str

    # Direct relational metadata for ease of indexing & graph building
    entities: List[str] = Field(default_factory=list)
    source_id: Optional[str] = None
    superseded_by: Optional[str] = None
    supersedes_id: Optional[str] = None


class TaskModel(BaseModel):
    id: str
    tenant_id: str
    task_type: str
    status: TaskStatus = "pending"
    payload_json: str = "{}"
    result_json: Optional[str] = None
    idempotency_key: str
    lease_owner: Optional[str] = None
    lease_expires: Optional[str] = None
    attempts: int = 0
    version: int = 1
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class ConversationModel(BaseModel):
    id: str
    tenant_id: str
    title: Optional[str] = None
    status: Literal["active", "archived"] = "active"
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)
