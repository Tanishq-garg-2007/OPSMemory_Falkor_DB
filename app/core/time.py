"""Time utilities adhering to ISO 8601 UTC."""
from datetime import datetime, timezone
from typing import Optional


def utc_now() -> datetime:
    """Current UTC datetime."""
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    """Current UTC datetime in ISO-8601 format."""
    return utc_now().isoformat()


def parse_iso(ts: str) -> datetime:
    """Parse ISO formatted timestamp string into UTC datetime."""
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def is_past(ts: Optional[str]) -> bool:
    """Check if given ISO timestamp is in the past."""
    if not ts:
        return False
    try:
        return parse_iso(ts) < utc_now()
    except Exception:
        return False
