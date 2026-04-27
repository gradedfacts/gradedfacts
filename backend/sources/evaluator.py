"""
Source quality evaluator.

Scores each fetched source on independence, reliability, and relevance,
producing an EvaluatedSource that carries a trust tier and independence flag.

Responsibilities:
    - Classify sources as Primary, Secondary, or Tertiary based on proximity
      to the original event or data.
    - Assess editorial independence: flag sources with known political funding,
      ownership ties, or documented bias.
    - Score relevance: how directly does this source address the specific claim?
    - Reject anonymous sources unless an explicit justification is recorded.
    - Output an EvaluatedSource list consumed by the analysis engine.
"""
