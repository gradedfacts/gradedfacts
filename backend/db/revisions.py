"""
Revision history management.

Handles the lifecycle of Judgment revisions in accordance with the
Revision Principle: new evidence may change a verdict, but the prior
verdict is always preserved and publicly accessible.

Responsibilities:
    - Create a Revision record that links a new Judgment to the one it supersedes.
    - Record the triggering evidence (new source URL, correction notice, etc.).
    - Mark the prior Judgment as archived (not deleted).
    - Provide a full audit trail: given any Claim, return the ordered chain
      of all Judgments from oldest to newest with timestamps and change rationale.
    - Expose a diff view: what changed between two consecutive Judgments.
"""
