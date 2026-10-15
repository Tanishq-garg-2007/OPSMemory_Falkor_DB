"""Generic grounding gate: is there any evidence that the question is about something we remember?

Replaces the benchmark-specific string checks that used to live in RetrievalService
(``"detach delete"``, ``"match (n)"``). Nothing here knows about Cypher, topics or fixtures:
a query is "ungrounded" when none of its content words appear in any retrieved candidate and it
names no entity that the candidates are linked to.
"""
import re
from typing import Iterable, Set

MAX_QUERY_CHARS = 2000

_STOPWORDS = frozenset(
    "a an the of to in on at for and or is are was were be been what which who whom when where why how "
    "do does did can could should would will with from by as that this these those it its into about "
    "after before than then there their our we you i me my your not no yes any all each per if so also "
    "both other between during while have has had give tell show explain describe summarize compare "
    "list please".split()
)


def content_tokens(text: str) -> Set[str]:
    """Lowercased content words, trimmed to a 5-char stem so 'owns' / 'owned' and 'rollback' / 'rolled' line up."""
    out: Set[str] = set()
    for word in re.findall(r"[a-z0-9][a-z0-9.\-]*", text.lower()):
        word = word.strip(".-")
        if len(word) >= 3 and word not in _STOPWORDS:
            out.add(word[:5])
    return out


def is_degenerate_query(query: str) -> bool:
    """Input validation only: empty, no real characters, over-long, or one repeated character run."""
    stripped = query.strip()
    alnum = re.sub(r"[^a-zA-Z0-9]", "", stripped)
    if not stripped or len(alnum) < 2 or len(stripped) > MAX_QUERY_CHARS:
        return True
    return len(alnum) > 30 and len(set(alnum)) < 4


def has_grounding(query: str, candidate_texts: Iterable[str], entity_hit: bool = False) -> bool:
    """True if the query shares at least one content word with a candidate, or hits a known entity."""
    if entity_hit:
        return True
    q_tokens = content_tokens(query)
    if not q_tokens:
        return False
    for text in candidate_texts:
        if q_tokens & content_tokens(text):
            return True
    return False