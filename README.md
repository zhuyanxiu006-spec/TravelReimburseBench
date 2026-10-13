# TravelReimburseBench

A multimodal benchmark for deciding when travel reimbursement can be processed automatically, must be rejected for a verifiable contradiction, or requires a human handoff because essential evidence remains unresolved.

This repository contains the final **540-case corpus**, **3,087 PNG evidence pages**, frozen ground truth, institutional rules, two prompts, and inference/evaluation code. It does not distribute model predictions, experiment logs, or PDF evidence.

## Dataset

Each scenario contains 180 cases: 60 Process, 60 Defer and 60 Reject. Overall there are 180 cases per action.

| Scenario | Description | Cases |
| --- | --- | ---: |
| S1 | Single person, single city | 180 |
| S2 | Single person, consecutive multiple cities | 180 |
| S3 | Multiple people, single city | 180 |

Evidence and policy materials are in Chinese. Every evidence PNG is 1191 × 794 pixels. The release includes the full evaluation corpus without a separate training or development split.

- **Process:** the evidence supports a determinate reimbursement form and monetary calculation under the supplied rules.
- **Reject:** the available evidence supports an independently verifiable contradiction.
- **Defer:** an essential field, relationship or monetary amount remains unresolved and requires supplementary material or review.

The 21 primary action codes and their counts are in [docs/action_codebook.md](docs/action_codebook.md). A primary code does not enumerate every co-occurring issue.

## Files

```text
data/
  S1|S2|S3/<case_id>/png/*.png
gt/
  cases.jsonl
standards/
  reimbursement_policy.docx
  hotel_limits.xlsx
  reimbursement_form_template.xlsx
  standards_context.txt
prompts/
  direct.txt
  structured_era.txt
  output_contract.md
  validate_contract.py
scripts/
  evaluate.py
  validate_release.py
  metrics/                 # final metric functions and error-signature rules
  runners/                 # OpenAI-compatible inference runner
  generation/              # optional standards-text extractor
  gt/                      # optional readable-GT exporter
docs/
tests/                     # metric and request-construction regression checks
release_manifest.json
LICENSE                    # code: MIT
LICENSE-DATA               # data/materials: CC BY 4.0
```

`gt/cases.jsonl` contains the final ground truth for all 540 cases.

Frozen GT SHA256:

```text
b94cb7c6a67235c56043b3b84604d17806a5be2fb33f070a38fa7660e8154f19
```

Ground truth includes annotations, structured evidence summaries, reference forms, calculations and handoffs. **Do not pass this information, primary action codes, or case IDs to the model.** Case IDs contain an action-coded segment. The release runner reads IDs only to locate images and save responses; real API requests contain the supplied policy/prompt and ordered PNG evidence, without the case ID or gold annotations. The reimbursement template and its schema are shared task resources, rather than per-case answers.

## Setup and integrity checks

Use Python 3.10 or newer. Inference, evaluation and integrity validation require only the Python standard library. Optional DOCX/XLSX helpers use the packages in `requirements.txt`.

Run these commands from the repository root:

```bash
python scripts/validate_release.py
python prompts/validate_contract.py
python -m unittest discover -s tests -v
# Optional, needed only for the DOCX/XLSX helpers:
python -m pip install -r requirements.txt
```

On Windows, `py -3.10` can replace `python`. The release validator checks all 540 case IDs, the scenario/action balance, PNG-only layout, image dimensions and manifest SHA256 checksums. After intentionally changing files, `--skip-hashes` checks only corpus structure. The prompt validator checks prompt schemas against frozen GT; it does not validate arbitrary model responses.

The distributed Office documents have identifying core properties and WPS account metadata removed. `python scripts/sanitize_office.py` cleans such properties after editing Office files while preserving every non-property archive part. It does not anonymize GitHub account names, commit history or document body text. Any intentional changes require updating the release checksum manifest.

## Inference

First check paths and output writing without calling an API:

```bash
python scripts/runners/run_models.py --mode dry-run --prompt direct --model mock-model --output-root results/dryrun --limit 3
```

**Dry-run outputs copy gold actions and artifacts for a plumbing check. They are not model predictions and must not be reported as benchmark results.**

For real inference, supply an API endpoint and model identifier compatible with multimodal OpenAI-style `/chat/completions`. Set `MODEL_API_KEY` in your environment; never commit a key. For example, in PowerShell:

```powershell
$env:MODEL_API_KEY = "YOUR_API_KEY"
python scripts/runners/run_models.py --mode real-run --prompt direct --model YOUR_MODEL_ID --base-url https://YOUR_ENDPOINT/v1 --output-root results/direct/YOUR_MODEL_ID --max-tokens 12000
Remove-Item Env:\MODEL_API_KEY
```

Use `--prompt structured_era` for the structured Evidence–Rule–Action prompt. `--case-id`, `--subset`, `--limit`, and sharding flags select cases. Omit selection flags for all 540 cases. Results are written as `<output-root>/<case_id>/parsed_response.json`, with raw responses, metadata and retry information alongside them. Successful existing outputs are skipped unless `--overwrite` is passed.

The runner sends PNGs as base64 data URLs in sorted filename order, with configurable `--image-detail` (default `high`). Defaults are temperature 0.0, `max_tokens` 12000, timeout 300 seconds, at most two retries for specified transient failures, and ten seconds between retries. `--omit-temperature` omits that parameter, and `--no-json-response-format` disables the JSON response-format request. `top_p` and reasoning-specific parameters are not sent by this runner. Adapt request fields if your provider uses a different API contract.

Retries retain the same prompt, images and token budget. The first parsable JSON object with a valid action is retained; retry selection does not depend on gold labels or scores. Invalid model-output JSON or action values fail without retry. Parsing success does not imply full schema validity: malformed downstream artifacts fail evaluation. See [scripts/runners/README.md](scripts/runners/README.md).

Runner parameters are configurable. Use the paper's runtime settings when reproducing a particular experimental condition; defaults do not imply identical settings across conditions. Hosted model availability and behavior can change.

## Evaluation

Point the evaluator at one run directory containing the per-case parsed responses:

```bash
python scripts/evaluate.py --predictions results/direct/YOUR_MODEL_ID --output results/direct_metrics.json
```

By default a missing case is an error. `--allow-missing` counts missing outputs as failures while retaining all gold-case denominators. Invalid action strings also count as failures. A zero denominator is reported as JSON `null`, with the denominator retained, rather than as a measured zero-percent score.

| Metric | Criterion and denominator |
| --- | --- |
| Action Accuracy / Macro-F1 | Correct Process, Defer or Reject decisions; all 540 cases |
| Action recall | Correct decisions for each gold action; 180 per action |
| Over-automation | Gold Defer/Reject predicted Process; 360 gold Defer/Reject cases |
| Over-conservatism | Gold Process predicted Defer/Reject; 180 gold Process cases |
| TSA | Exact match of all scored form values; correctly predicted gold Process cases |
| HC | Unresolved monetary-field coverage and amount-dependency consistency; correctly predicted gold Defer cases |
| RJ | Automated evidence-category, contradiction-marker and accepted rule-family contract; correctly predicted gold Reject cases |
| WCR | Correct action and its downstream criterion (TSA/HC/RJ); 540 overall or 180 per gold action |
| Five-amount exact match | Correct Process action and all five monetary amounts equal the reference; all 180 gold Process cases |

TSA compares traveler names as a multiset and transport rows as a multiset of **atomic six-field records** (departure/arrival date and city, mode, amount). Name-cell placement and row order can change; mixing fields from different tickets cannot pass. The three fixed expense groups and grand total must also match. Narrative explanations and provenance traces are not scored by TSA. Dates are normalized, numeric values rounded to two decimal places, and the frozen transport-wording normalization is retained.

HC permits extra unresolved fields provided they do not overlap reported known amounts. Every gold unresolved field must be present; unresolved components cannot coexist with a known total. HC does not validate every reported known amount or grade the completeness of free-text requests and human usability.

RJ is a lexical/structural proxy, not a full semantic or human assessment. It recognizes evidence categories from evidence entries, policy articles from rule identifiers/text, and generic contradiction markers in explanatory fields. The fixed rule-family contract may accept independently recoverable co-occurring contradictions. The matcher does not prove that each textual claim is factually correct; code-specific `concepts` lists are retained for provenance but are not enforced by the frozen acceptance function. See [docs/evaluation.md](docs/evaluation.md) and [scripts/metrics/downstream.py](scripts/metrics/downstream.py).

Reports also include scenario-level and primary-code summaries and the frozen observable error-signature classifier. These signatures are heuristic descriptions of outputs, not causal diagnoses of internal model behavior. Full regex patterns, field selection and priority rules are in [scripts/metrics/signatures.py](scripts/metrics/signatures.py).

## Optional helpers

To export readable GT views, install the optional dependencies and run `python scripts/gt/build_readable_gt_views.py`. These generated files are ignored by Git. To regenerate policy text, use `python scripts/generation/build_standards_prompt_context.py --output results/regenerated_standards_context.txt`; keep the frozen supplied context for evaluations of this release.

## License and attribution

- Code (`*.py`) is under the [MIT License](LICENSE).
- Dataset PNGs, GT annotations, policy/template materials, prompt texts, documentation and release metadata are under [Creative Commons Attribution 4.0 International](LICENSE-DATA), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

For data/materials, attribute **TravelReimburseBench contributors**, link to this repository and the CC BY 4.0 license, and indicate modifications. The CC BY license text was obtained from the SPDX license-list repository and corresponds to the official license linked above. Code reuse must retain the MIT copyright and permission notice. Add the published paper citation when its final bibliographic details are available; no placeholder author list or citation is asserted here.
