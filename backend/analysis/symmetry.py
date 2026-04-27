"""
Symmetry checker.

Enforces the Symmetry Principle: any analytical method applied to one
political actor, party, or ideology must be applied identically to all others.

Responsibilities:
    - Detect the political subject(s) of a claim (entity tagging).
    - Look up prior analyses that involved the same method on different subjects.
    - Flag or block a judgment if the same scrutiny level has not been applied
      consistently across the political spectrum.
    - Produce a SymmetryReport attached to every Judgment, documenting which
      comparable analyses exist and confirming no double standard was applied.
"""
