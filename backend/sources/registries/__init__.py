"""
Source registries — static, versioned JSON files describing known sources
with tier, independence, and category metadata.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_REGISTRY_DIR = Path(__file__).parent

_ALL_REGISTRIES: tuple[str, ...] = (
    "us_sources.json",
    "eu_sources.json",
    "ch_sources.json",
    "uk_sources.json",
    "de_sources.json",
    "fr_sources.json",
    "international_sources.json",
)


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


def lookup_source_all_registries(domain: str) -> dict | None:
    """
    Search all regional registries in order and return the first matching entry.

    Registries are searched in the order defined by _ALL_REGISTRIES.
    Returns None if the domain is not found in any registry.
    """
    for registry_file in _ALL_REGISTRIES:
        try:
            result = lookup_source(domain, registry_file)
        except FileNotFoundError:
            continue
        if result is not None:
            return result
    return None


def apply_registry_override(source: dict) -> dict:
    """
    Enrich a source dict with curated metadata from the regional registries.

    When the URL matches a known registry entry:
      - is_independent is set from the registry (ground truth overrides Claude's judgment)
      - tier is set from the registry
      - counts_for_threshold is set from the registry when present
      - country and region are added from the registry
      - affiliation_note is set from the registry for non-independent sources

    When the URL is NOT found in any registry, conservative defaults are applied:
      - tier: "tertiary"
      - is_independent: "neutral"
      - counts_for_threshold: False
    Claude's tier/independence judgment is not trusted for unregistered sources.

    The input dict is never mutated; a new dict is returned when changes are made.
    """
    url = source.get("url", "")
    entry = lookup_source_all_registries(url)
    if entry is None:
        # Unregistered source: cannot verify Claude's classification.
        # Conservative default — unknown ≠ independent; cannot count toward threshold.
        updated = dict(source)
        updated["tier"] = "tertiary"
        updated["is_independent"] = "neutral"
        updated["counts_for_threshold"] = False
        updated.pop("affiliation_note", None)
        return updated

    updated = dict(source)
    updated["is_independent"] = entry["is_independent"]
    updated["tier"] = entry["tier"]
    if "counts_for_threshold" in entry:
        updated["counts_for_threshold"] = entry["counts_for_threshold"]
    for field in ("country", "region"):
        if field in entry:
            updated[field] = entry[field]
    is_not_independent = (
        entry["is_independent"] is False or entry["is_independent"] == "not_independent"
    )
    if is_not_independent:
        updated["affiliation_note"] = entry.get("affiliation_note", "")
    elif "affiliation_note" in updated:
        # Registry says independent or neutral — remove any incorrectly assigned note
        del updated["affiliation_note"]
    return updated
