# Evaluation contract

The supported evaluator is `scripts/evaluate.py`. It reads one directory of per-case `parsed_response.json` files and the frozen `gt/cases.jsonl`; it does not read model-result directories from the paper workspace.

- **TSA** uses the position-invariant, content-strict Process form matcher in `scripts/metrics/template.py`. It compares traveler names as a multiset, transport rows as atomic six-field records, three fixed expense groups and the total. Its conditional denominator is correctly predicted gold Process cases.
- **HC** uses `scripts/metrics/downstream.py::defer_result`. Every gold unresolved monetary field must be present; known and unresolved fields may not overlap; an unresolved component forbids a known total. Extra unresolved fields are allowed when they do not conflict. Its denominator is correctly predicted gold Defer cases.
- **RJ** checks the Reject contract in `scripts/metrics/downstream.py`: required evidence categories, a contradiction marker and an accepted policy article family. It accepts independently recoverable co-occurring contradictions. Its denominator is correctly predicted gold Reject cases.
- **WCR** requires the correct action and the corresponding downstream criterion.

The error-signature rules in `scripts/metrics/signatures.py` inspect selected narrative fields with fixed regexes. They describe observable output signatures, not latent model causes.

Narrative fields are `action_reason`, `reject_reason`, `defer_reason`, `case_summary`, `reasoning_steps`, and `defer_help_points`; `evidence`, `rules`, monetary calculations, forms and handoff objects are excluded from trigger recognition. Trigger regexes are code-specific, with a local negation filter. For incorrect gold Defer/Reject decisions, a named trigger followed by Process is labeled action gating, and a named trigger followed by the other stopping action is labeled gating/priority. When no trigger is named, the fixed action-code family supplies the upstream signature.

Gold Process errors use an ordered text classifier: perception keywords, then itinerary keywords, then cross-document alignment keywords, then rule/policy keywords; otherwise spurious anomaly detection. The exact patterns, code groups, ordering and fallback are in the executable source. The classifier is applied only to wrong-action outputs; missing predictions are excluded from textual diagnostics while remaining failures in benchmark metrics.

Evidence-category recall is computed per erroneous output against the gold evidence categories and then averaged over those outputs with a nonempty gold category set. Outputs omitting any gold category are counted separately with that same diagnostic denominator. These values cannot be reconstructed from an action-confusion table alone.
