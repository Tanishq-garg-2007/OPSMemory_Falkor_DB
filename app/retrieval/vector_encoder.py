"""Deterministic, zero-dependency 64-dimensional semantic vector encoder in pure Python."""
import hashlib
import math
import re
from typing import List

# Domain-specific synonym canonicalization for operations and cloud infrastructure
SYNONYM_MAP = {
    "postgres": "db",
    "postgresql": "db",
    "database": "db",
    "rdbms": "db",
    "sql": "db",
    "crash": "outage",
    "crashed": "outage",
    "down": "outage",
    "failure": "outage",
    "fail": "outage",
    "failing": "outage",
    "broken": "outage",
    "panic": "outage",
    "revert": "rollback",
    "reverted": "rollback",
    "rollback": "rollback",
    "downgrade": "rollback",
    "slow": "latency",
    "timeout": "latency",
    "timedout": "latency",
    "lag": "latency",
    "delay": "latency",
    "deploy": "deployment",
    "deployed": "deployment",
    "deploying": "deployment",
    "release": "deployment",
    "version": "version",
    "ver": "version",
    "v": "version",
    "incident": "incident",
    "outage": "outage",
    "sev1": "incident",
    "sev2": "incident",
    "error": "error",
    "err": "error",
    "failover": "failover",
    "replica": "replica",
    "payments": "payment",
    "payment": "payment",
    "checkout": "payment",
    "billing": "payment",
    "invoice": "payment",
    "invoices": "payment",
    "stripe": "payment",
    "ledger": "payment",
}

DIMENSION = 64


def canonicalize_text(text: str) -> str:
    """Normalize text and canonicalize domain terms."""
    # Split on hyphens and special chars but keep original terms too
    tokens = re.findall(r"[a-zA-Z0-9]+", text.lower())
    # Also add hyphenated compound words
    compounds = re.findall(r"[a-zA-Z0-9]+-[a-zA-Z0-9]+", text.lower())
    all_raw = tokens + compounds
    canonical_tokens = []
    for t in all_raw:
        canon = SYNONYM_MAP.get(t)
        if not canon:
            if t.endswith("ing") and len(t) > 5:
                canon = SYNONYM_MAP.get(t[:-3], t[:-3])
            elif t.endswith("ed") and len(t) > 4:
                canon = SYNONYM_MAP.get(t[:-2], t[:-2])
            elif t.endswith("ment") and len(t) > 6:
                canon = SYNONYM_MAP.get(t[:-4], t[:-4])
            elif t.endswith("s") and len(t) > 3:
                canon = SYNONYM_MAP.get(t[:-1], t[:-1])
            else:
                canon = t
        canonical_tokens.append(canon)
    return " ".join(canonical_tokens)


def encode_vector(text: str, dim: int = DIMENSION) -> List[float]:
    """Encode text into a normalized 64-dimensional semantic vector.
    
    Uses deterministic feature hashing of words, bigrams, and character n-grams
    with synonym canonicalization.
    """
    if not text:
        val = 1.0 / math.sqrt(dim)
        return [round(val, 6) for _ in range(dim)]

    canon = canonicalize_text(text)
    words = canon.split()
    if not words:
        val = 1.0 / math.sqrt(dim)
        return [round(val, 6) for _ in range(dim)]

    features = []
    # 1. Unigrams
    features.extend(words)

    # 2. Bigrams
    for i in range(len(words) - 1):
        features.append(f"{words[i]}_{words[i+1]}")

    # 3. Char trigrams within words
    for w in words:
        if len(w) >= 3:
            for i in range(len(w) - 2):
                features.append(w[i:i+3])

    vec = [0.0] * dim
    for feat in features:
        # Deterministic MD5 hash to bucket and sign
        digest = hashlib.md5(feat.encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:4], "big") % dim
        sign = 1.0 if (digest[4] % 2 == 0) else -1.0
        # Weight by feature type: words have higher weight than char n-grams
        weight = 2.0 if "_" in feat else (1.5 if len(feat) > 3 else 0.8)
        vec[bucket] += sign * weight

    # L2 normalize
    norm_sq = sum(v * v for v in vec)
    if norm_sq < 1e-12:
        val = 1.0 / math.sqrt(dim)
        return [round(val, 6) for _ in range(dim)]

    norm = math.sqrt(norm_sq)
    return [round(float(v / norm), 6) for v in vec]
