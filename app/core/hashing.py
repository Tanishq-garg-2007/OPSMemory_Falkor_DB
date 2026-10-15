"""Hashing and idempotency key generation."""
import hashlib
import re


def slugify(text: str) -> str:
    """Normalize text into lowercase alphanumeric and hyphen slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text.strip("-")


def hash_api_key(api_key: str) -> str:
    """Hash an API key with sha256 for secure storage."""
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def memory_idempotency_key(
    tenant_id: str,
    source_id: str,
    memory_type: str,
    subtype: str,
    title: str,
    core_statement: str = ""
) -> str:
    """
    Generate deterministic idempotency key for memory:
    sha256(tenant_id | source_id | memory_type | subtype | normalized_title | normalized_core_statement)
    """
    norm_title = slugify(title)
    norm_statement = slugify(core_statement)
    raw = f"{tenant_id}|{source_id}|{memory_type}|{subtype}|{norm_title}|{norm_statement}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def task_idempotency_key(
    tenant_id: str,
    task_type: str,
    target_id_or_context: str,
    state_version: int = 1
) -> str:
    """
    Generate deterministic idempotency key for task:
    sha256(tenant_id | task_type | target_memory_id_or_context_id | relevant_state_version)
    """
    raw = f"{tenant_id}|{task_type}|{target_id_or_context}|{state_version}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
