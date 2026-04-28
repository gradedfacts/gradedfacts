"""
Source registries — static, versioned JSON files describing known sources
with tier, independence, and category metadata.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_REGISTRY_DIR = Path(__file__).parent


@lru_cache(maxsize=None)
def load_registry(filename: str) -> dict:
    """Load and cache a registry JSON file by filename (e.g. 'us_sources.json')."""
    path = _REGISTRY_DIR / filename
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def lookup_source(domain: str, registry: str = "us_sources.json") -> dict | None:
    """
    Look up a source entry by domain substring match.

    Returns the first matching entry dict, or None if no match.
    Matching is case-insensitive substring against the entry's `domain` field.
    """
    data = load_registry(registry)
    domain_lower = domain.lower()
    for entry in data.get("sources", []):
        if entry.get("domain", "").lower() in domain_lower:
            return entry
    return None
