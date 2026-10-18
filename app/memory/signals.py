"""Lightweight text signals shared by triage, deterministic extraction and the mock LLM.

Kept free of app.llm imports so every layer can use it without circular imports.
"""
import re
from typing import Iterable, List, Optional, Tuple

# Used only as a default when the caller does not pass entities known to the graph.
DEFAULT_KNOWN_SERVICES: Tuple[str, ...] = (
    "payments-api", "checkout-ui", "auth-service", "postgres-orders",
    "inventory-svc", "gateway-api", "payments-worker",
)

_WH_RE = re.compile(r"^(what|who|whom|whose|when|where|why|how|which)\b")
_IMPERATIVE_RE = re.compile(
    r"^(?:please\s+)?(?:show|tell|list|explain|describe|identify|compare|contrast|summari[sz]e|provide|"
    r"outline|display|find|check|give\s+me|walk\s+me|look\s+up)\b(?!\s+(?:out|that|stopper)\b)"
)
_AUX_RE = re.compile(r"^(?:is|are|can|could|does|did|do|will|would|should)\b(?!\s+not\b|['\u2019]t)")


def is_inquiry(text: str) -> bool:
    """True for questions and requests for information (they must not become memories).

    Word-boundary matching: "However..." / "Whenever..." / "Do not deploy..." are statements.
    """
    t = text.strip().lower()
    return t.endswith("?") or bool(_WH_RE.match(t) or _IMPERATIVE_RE.match(t) or _AUX_RE.match(t))


_VERSION_RE = re.compile(
    r"\bv\d+(?:\.\d+){0,2}\b"
    r"|(?<![\w.-])\d+\.\d+(?:\.\d+)?\b(?!\s*(?:s|ms|sec|secs|seconds|min|mins|minutes|hours|%|gb|mb|kb|x|rps)\b)"
)

# Verbs/phrases that signal "this is the new state of a service", with or without the word "version".
_UPDATE_CUE_RE = re.compile(
    r"\b(version|upgraded?|updated?|deployed|released?|bumped|rolled\s+(?:back|out)|"
    r"migrated|now\s+(?:on|at|running)|is\s+(?:on|at|running)|running|set\s+to|pinned)\b"
)

# "upgraded billing-gateway to ..." / "billing-gateway version is ..." / "billing-gateway is now on ..."
_SERVICE_BEFORE_CUE_RE = re.compile(
    r"(?:upgraded?|updated?|deployed|released?|bumped|rolled\s+(?:back|out)|migrated|pinned)\s+(?:the\s+)?([a-z0-9][a-z0-9_-]*)"
    r"|([a-z0-9][a-z0-9_-]*)\s+(?:version|is\s+now|is\s+on|is\s+at|is\s+running|now\s+runs)"
)
_NOT_A_SERVICE = {"the", "a", "an", "it", "this", "that", "to", "our", "we", "version", "service"}


def _normalize_version(v: str) -> str:
    v = v.lower()
    return v if v.startswith("v") else f"v{v}"


def find_services(text: str, known: Optional[Iterable[str]] = None) -> List[str]:
    """Known services mentioned in text, plus unseen hyphenated names used as the subject of an update."""
    t = text.lower()
    names = list(known) if known is not None else list(DEFAULT_KNOWN_SERVICES)
    found = [s for s in names if s in t or s.replace("-", " ") in t]
    for m in _SERVICE_BEFORE_CUE_RE.finditer(t):
        cand = m.group(1) or m.group(2)
        if cand and "-" in cand and cand not in _NOT_A_SERVICE and cand not in found \
                and not re.fullmatch(r"inc[-_]?\d+", cand) and not _VERSION_RE.fullmatch(cand):
            found.append(cand)
    return found


def extract_version_updates(text: str, services: Optional[List[str]] = None) -> List[Tuple[str, str]]:
    """(service, version) pairs from declarative text. Empty for questions and for text with no update cue."""
    if is_inquiry(text):
        return []
    t = text.lower()
    if not _UPDATE_CUE_RE.search(t):
        return []
    # Strip incident ids so "inc-101" or "2026-09-15" are never read as versions.
    scrubbed = re.sub(r"\binc[-_]?\d+\b|\b\d{4}-\d{2}-\d{2}\b", " ", t)
    matches = list(_VERSION_RE.finditer(scrubbed))
    if not matches:
        return []
    svc = (services if services is not None else find_services(text))
    last = matches[-1]
    version = _normalize_version(last.group(0))
    # Subject = the service mentioned closest BEFORE the version (fallback: first service).
    subject = svc[0] if svc else "service"
    best = -1
    for name in svc:
        for form in (name.lower(), name.lower().replace("-", " ")):
            pos = scrubbed.rfind(form, 0, last.start())
            if pos > best:
                best, subject = pos, name
    return [(subject, version)]


# Whole-word incident cues. Substring matching made "download" look like "down" and "known" look like "now".
_INCIDENT_RE = re.compile(
    r"\b(incidents?|inc[-_]?\d+|outages?|failures?|failed|broken|down|errors?)\b"
)


def has_incident_signal(text: str) -> bool:
    """True when the text contains a whole-word incident cue (incident, outage, failure, broken, down, error)."""
    return bool(_INCIDENT_RE.search(text.lower()))


_INCIDENT_ID_RE = re.compile(r"\b(?:incident\s+|inc[-_]?)([a-z0-9]+(?:-[a-z0-9]+)*)\b", re.IGNORECASE)
_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")


def reference_tokens(text: str) -> set:
    """Specific things a text points at: versions (v2.3) and incident ids (inc-101), normalized.

    Used by ranking to favour memories that mention the same version / incident as the query,
    for any value, instead of a hardcoded list of fixture strings.
    """
    t = _DATE_RE.sub(" ", text.lower())
    tokens = set()
    for m in _INCIDENT_ID_RE.finditer(t):
        val = m.group(1)
        if val == "ident":
            continue
        if val.startswith("inc-") or val.startswith("inc_"):
            val = val[4:]
        if any(c.isdigit() for c in val) or "-" in val:
            tokens.add(f"inc-{val}")
    without_inc = _INCIDENT_ID_RE.sub(" ", t)
    tokens |= {_normalize_version(v) for v in _VERSION_RE.findall(without_inc)}
    return tokens


# Common short forms in service names. Kept tiny and generic on purpose.
_NAME_ABBREVIATIONS = {"svc": "service", "svcs": "services", "srv": "service"}


def canonical_name_key(name: str) -> str:
    """Separator- and abbreviation-insensitive key: 'auth-svc', 'Auth Service', 'authservice' -> 'authservice'."""
    tokens = re.split(r"[^a-z0-9]+", name.lower())
    return "".join(_NAME_ABBREVIATIONS.get(t, t) for t in tokens if t)


def names_equivalent(a: str, b: str, min_ratio: float = 0.93) -> bool:
    """True when two surface forms very likely name the same thing (same canonical key, or near-identical)."""
    from difflib import SequenceMatcher
    ka, kb = canonical_name_key(a), canonical_name_key(b)
    if not ka or not kb:
        return False
    if ka == kb:
        return True
    return min(len(ka), len(kb)) >= 8 and SequenceMatcher(None, ka, kb).ratio() >= min_ratio