"""Deterministic and stable identifier generators."""
import uuid
from app.core.hashing import slugify


def entity_id(kind: str, name: str, tenant_id: str = "") -> str:
    """Generate deterministic entity ID: ent_{tenant}_{kind}_{slug} or ent_{kind}_{slug}"""
    if tenant_id:
        return f"ent_{slugify(tenant_id)}_{slugify(kind)}_{slugify(name)}"
    return f"ent_{slugify(kind)}_{slugify(name)}"


def memory_id(memory_type: str, tenant_id: str, subtype: str, title: str) -> str:
    """Generate deterministic memory ID: mem_{type}_{tenant}_{subtype}_{slug}"""
    slug = slugify(title)[:36]
    return f"mem_{slugify(memory_type)}_{slugify(tenant_id)}_{slugify(subtype)}_{slug}"


def task_id(task_type: str, name_or_target: str, version: int = 1) -> str:
    """Generate deterministic task ID: task_{task_type}_{slug}_{version}"""
    return f"task_{slugify(task_type)}_{slugify(name_or_target)}_{version}"


def source_id(conversation_id: str, message_id: str) -> str:
    """Generate deterministic source ID: src_{conv_id}_{msg_id}"""
    return f"src_{slugify(conversation_id)}_{slugify(message_id)}"


def conversation_id(custom_id: str = None) -> str:
    """Generate or normalize conversation ID."""
    if custom_id:
        return f"conv_{slugify(custom_id)}"
    return f"conv_{uuid.uuid4().hex[:12]}"
