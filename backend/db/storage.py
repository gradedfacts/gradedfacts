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
