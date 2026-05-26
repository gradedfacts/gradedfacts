#!/usr/bin/env python3
"""
tools/registry_unknown_sources.py
==================================
Query the database for EvaluatedSource entries whose domain is not covered
by any curated registry file, then report them sorted by appearance frequency.

Frequency = number of distinct URLs from that domain stored in the database.
A domain with many distinct article URLs is a strong candidate for registry addition.

Usage (run from the project root):
    python tools/registry_unknown_sources.py
    python tools/registry_unknown_sources.py --min-count 2
    python tools/registry_unknown_sources.py --show-urls
    python tools/registry_unknown_sources.py --min-count 3 --show-urls
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

# Ensure the project root is on sys.path so backend imports resolve correctly.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))

from backend.db.models import EvaluatedSource
from backend.db.session import SessionLocal
from backend.sources.evaluator import extract_domain
from backend.sources.registries import lookup_source_all_registries


def _collect_unknown_domains(
    show_urls: bool,
) -> tuple[Counter[str], dict[str, list[str]]]:
    """
    Fetch every distinct URL from evaluated_sources, check it against all
    registry files, and collect those with no registry match.

    Returns:
        domain_counts  — Counter mapping root domain → number of distinct URLs
        domain_urls    — mapping root domain → list of example URLs (populated
                         only when show_urls is True)
    """
    domain_counts: Counter[str] = Counter()
    domain_urls: dict[str, list[str]] = defaultdict(list)

    with SessionLocal() as session:
        # DISTINCT on url: the same article can be stored across multiple claims
        # or revisions; we want unique source pages, not raw row counts.
        rows = session.query(EvaluatedSource.url).distinct().all()

    for (url,) in rows:
        if not url:
            continue
        if lookup_source_all_registries(url) is not None:
            continue  # known — skip
        domain = extract_domain(url) or url
        domain_counts[domain] += 1
        if show_urls:
            domain_urls[domain].append(url)

    return domain_counts, domain_urls


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "List source domains that appear in the GradedFacts database but are "
            "absent from all curated registry files, sorted by frequency. "
            "Use this to identify high-priority candidates for registry addition."
        )
    )
    parser.add_argument(
        "--min-count",
        type=int,
        default=1,
        metavar="N",
        help="Only show domains that appear in at least N distinct URLs (default: 1).",
    )
    parser.add_argument(
        "--show-urls",
        action="store_true",
        help="Print up to 3 example URLs beneath each domain.",
    )
    args = parser.parse_args()

    print("Querying database…", flush=True)
    domain_counts, domain_urls = _collect_unknown_domains(args.show_urls)

    ranked = [
        (domain, count)
        for domain, count in domain_counts.most_common()
        if count >= args.min_count
    ]

    if not ranked:
        suffix = f" with count ≥ {args.min_count}" if args.min_count > 1 else ""
        print(f"No unregistered domains found{suffix}.")
        return

    total_unique = len(domain_counts)
    shown = len(ranked)
    header_suffix = (
        f" — showing {shown} with count ≥ {args.min_count}" if args.min_count > 1 else ""
    )
    print(f"\nUnregistered domains: {total_unique} unique{header_suffix}\n")

    count_width = len(str(ranked[0][1]))
    for domain, count in ranked:
        print(f"  {count:>{count_width}}  {domain}")
        if args.show_urls:
            for url in domain_urls[domain][:3]:
                print(f"           {url}")


if __name__ == "__main__":
    main()
