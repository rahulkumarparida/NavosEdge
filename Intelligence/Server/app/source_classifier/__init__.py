"""
Phase 3 — Source Classification Module.

Estimates which environmental sources or situations are most consistent
with an incoming sensor pattern, using a Decision Tree-based classifier
and graded feature-range similarity scoring.

IMPORTANT: This classifier produces *hypotheses*, not confirmed source
identities. MQ-series sensors are broad-response devices and cannot
uniquely identify a gas.  PM sensors provide aggregate mass concentration,
not chemical composition.  All scores should be interpreted as pattern-
matching evidence, not verified source attribution.
"""
