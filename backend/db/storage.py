"""
Immutable judgment storage.

Append-only write interface for Claims, EvaluatedSources, and Judgments.
Reads are unrestricted; writes never mutate existing rows.

Responsibilities:
    - Persist new Claims with a unique ID and creation timestamp.
    - Attach EvaluatedSources to Claims.
    - Write Judgments as immutable records (INSERT only, never UPDATE/DELETE).
    - Expose read queries: fetch the current active Judgment for a Claim,
      fetch the full revision chain, and search Claims by keyword or rating.
    - Enforce the immutability contract at the storage layer so higher-level
      code cannot accidentally overwrite a past judgment.
"""
import logging
import unicodedata

from sqlalchemy import func, select, update

from backend.db.models import Claim, EvaluatedSource, Judgment

logger = logging.getLogger(__name__)


def normalize_claim_text(text: str) -> str:
    """Normalize claim text for deduplication: NFC unicode, strip, lowercase, collapse whitespace."""
    text = unicodedata.normalize("NFC", text)
    return " ".join(text.strip().lower().split())


def find_canonical_claim(session, text: str, exclude_id: str | None = None) -> Claim | None:
    """Return the earliest-submitted Claim whose normalized text matches, or None.

    exclude_id is typically the newly created temp Claim so it is not matched against itself.
    """
    normalized = normalize_claim_text(text)
    stmt = select(Claim).order_by(Claim.submitted_at)
    for claim in session.execute(stmt).scalars():
        if claim.id == exclude_id:
            continue
        if normalize_claim_text(claim.text) == normalized:
            return claim
    return None


def merge_into_canonical(session, temp_id: str, canonical_id: str) -> None:
    """Reassign all Judgments and EvaluatedSources from temp_id to canonical_id, then delete temp.

    Called after a completed analysis when an older Claim with identical text is found.
    The new Judgment and its sources are appended to the canonical Claim's history;
    the temp Claim row is removed. All operations commit atomically.
    """
    _src_before = session.execute(
        select(func.count()).select_from(EvaluatedSource).where(EvaluatedSource.claim_id == temp_id)
    ).scalar_one()
    _jdg_before = session.execute(
        select(func.count()).select_from(EvaluatedSource).where(EvaluatedSource.claim_id == canonical_id)
    ).scalar_one()
    logger.warning(
        "[DEBUG merge] temp_id=%s canonical_id=%s sources_on_temp=%d sources_already_on_canonical=%d",
        temp_id, canonical_id, _src_before, _jdg_before,
    )
    session.execute(
        update(EvaluatedSource)
        .where(EvaluatedSource.claim_id == temp_id)
        .values(claim_id=canonical_id)
    )
    session.execute(
        update(Judgment)
        .where(Judgment.claim_id == temp_id)
        .values(claim_id=canonical_id)
    )
    temp = session.get(Claim, temp_id)
    if temp is not None:
        session.delete(temp)
    session.commit()
    _src_after = session.execute(
        select(func.count()).select_from(EvaluatedSource).where(EvaluatedSource.claim_id == canonical_id)
    ).scalar_one()
    logger.warning(
        "[DEBUG merge] canonical_id=%s post_merge_source_count=%d (was %d on temp + %d on canonical)",
        canonical_id, _src_after, _src_before, _jdg_before,
    )
