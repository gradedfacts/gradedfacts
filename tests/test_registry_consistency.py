"""
Permanent consistency tests for registry.json.

Runs on every test invocation to catch data rot before and after large imports.
All validation is purely structural — no network access, no pipeline logic.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

_REGISTRY_PATH = (
    Path(__file__).parent.parent / "backend" / "sources" / "registries" / "registry.json"
)

_ALLOWED_TIERS = {"primary", "secondary", "tertiary"}

# is_independent accepts both JSON booleans and legacy string forms
_ALLOWED_INDEPENDENCE = {True, False, "independent", "not_independent", "neutral"}

# Exhaustive list — adding a value here requires a corresponding schema update
_ALLOWED_INSTITUTION_TYPES = {
    "statistics_agency",
    "parliament",
    "central_bank",
    "court",
    "government",
    "audit_office",
    "election_authority",
    "media",
    "ngo",
    "think_tank",
    "academic",
    "aggregator",
    "company",
    "other",
}


@pytest.fixture(scope="module")
def registry_sources() -> list[dict]:
    with _REGISTRY_PATH.open(encoding="utf-8") as f:
        data = json.load(f)
    return data["sources"]


# ── (a) No duplicate domains ────────────────────────────────────────────────

class TestNoDuplicates:
    def test_no_duplicate_domains(self, registry_sources):
        counts = Counter(s.get("domain", "") for s in registry_sources)
        dups = {d: c for d, c in counts.items() if c > 1}
        assert not dups, f"Duplicate domains found: {dups}"


# ── (b) Subdomain collision consistency ─────────────────────────────────────

class TestSubdomainConsistency:
    def test_no_conflicting_subdomain_classifications(self, registry_sources):
        """
        A subdomain entry whose tier or is_independent contradicts its parent
        domain's entry must carry parent_override: true to make the intentional
        divergence explicit. Without the marker the registry is ambiguous.

        The more-specific (subdomain) entry always wins at lookup time; the test
        only catches unintentional contradictions.
        """
        domain_map = {s.get("domain", "").lower(): s for s in registry_sources}
        conflicts = []
        for domain, entry in domain_map.items():
            parts = domain.split(".")
            for i in range(1, len(parts) - 1):  # never strip down to bare TLD
                parent = ".".join(parts[i:])
                if parent not in domain_map:
                    continue
                parent_entry = domain_map[parent]
                tier_conflict = entry.get("tier") != parent_entry.get("tier")
                indep_conflict = (
                    entry.get("is_independent") != parent_entry.get("is_independent")
                )
                if (tier_conflict or indep_conflict) and not entry.get("parent_override"):
                    conflicts.append(
                        f"{domain} (tier={entry.get('tier')!r}, "
                        f"indep={entry.get('is_independent')!r}) contradicts parent "
                        f"{parent} (tier={parent_entry.get('tier')!r}, "
                        f"indep={parent_entry.get('is_independent')!r}) — "
                        f"add parent_override: true to suppress"
                    )
        assert not conflicts, (
            f"{len(conflicts)} subdomain conflict(s) without parent_override:\n"
            + "\n".join(f"  {c}" for c in conflicts)
        )


# ── (c) Required fields: tier and is_independent ─────────────────────────────

class TestRequiredFields:
    def test_tier_present_and_valid(self, registry_sources):
        bad = [
            (s.get("domain"), s.get("tier"))
            for s in registry_sources
            if s.get("tier") not in _ALLOWED_TIERS
        ]
        assert not bad, (
            f"Invalid or missing tier ({sorted(_ALLOWED_TIERS)}) on: {bad}"
        )

    def test_independence_present_and_valid(self, registry_sources):
        bad = [
            (s.get("domain"), repr(s.get("is_independent")))
            for s in registry_sources
            if s.get("is_independent") not in _ALLOWED_INDEPENDENCE
        ]
        assert not bad, (
            f"Invalid or missing is_independent on: {bad}"
        )


# ── (d) institution_type when present must be from the allowed list ───────────

class TestInstitutionType:
    def test_institution_type_value_when_present(self, registry_sources):
        bad = [
            (s.get("domain"), s.get("institution_type"))
            for s in registry_sources
            if "institution_type" in s
            and s.get("institution_type") not in _ALLOWED_INSTITUTION_TYPES
        ]
        assert not bad, (
            f"institution_type must be one of {sorted(_ALLOWED_INSTITUTION_TYPES)}. "
            f"Invalid entries: {bad}"
        )


# ── (e) affiliation_note non-empty string when present ───────────────────────

class TestAffiliationNote:
    def test_affiliation_note_non_empty_when_present(self, registry_sources):
        bad = [
            (s.get("domain"), repr(s.get("affiliation_note")))
            for s in registry_sources
            if "affiliation_note" in s
            and not (
                isinstance(s.get("affiliation_note"), str)
                and s["affiliation_note"].strip()
            )
        ]
        assert not bad, f"Empty or non-string affiliation_note: {bad}"


# ── (f) Domain format normalization ──────────────────────────────────────────

class TestDomainFormat:
    def test_domains_are_lowercase(self, registry_sources):
        bad = [
            s.get("domain", "")
            for s in registry_sources
            if s.get("domain", "") != s.get("domain", "").lower()
        ]
        assert not bad, f"Domain(s) contain uppercase characters: {bad}"

    def test_domains_have_no_scheme(self, registry_sources):
        bad = [
            s.get("domain", "")
            for s in registry_sources
            if "://" in s.get("domain", "")
        ]
        assert not bad, (
            f"Domain(s) must not include a URL scheme (e.g. 'https://'): {bad}"
        )

    def test_domains_have_no_path_component(self, registry_sources):
        bad = [
            s.get("domain", "")
            for s in registry_sources
            if "/" in s.get("domain", "")
        ]
        assert not bad, f"Domain(s) must not include a path: {bad}"

    def test_domains_have_no_trailing_slash(self, registry_sources):
        # Covered by the path test, but explicit for readable failure messages
        bad = [
            s.get("domain", "")
            for s in registry_sources
            if s.get("domain", "").endswith("/")
        ]
        assert not bad, f"Domain(s) with trailing slash: {bad}"

    def test_domains_have_no_whitespace(self, registry_sources):
        bad = [
            repr(s.get("domain", ""))
            for s in registry_sources
            if s.get("domain", "") != s.get("domain", "").strip()
            or " " in s.get("domain", "")
            or "\t" in s.get("domain", "")
        ]
        assert not bad, f"Domain(s) contain whitespace: {bad}"
