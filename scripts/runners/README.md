# Portable Full-540 runner

Run from the repository root with Python 3.10 or newer. The runner uses `gt/cases.jsonl`, `data/`, the two full prompts, and the frozen `standards/standards_context.txt`.

```bash
python scripts/runners/run_models.py --mode dry-run --prompt direct --model mock-model --output-root results/dryrun --limit 3
```

Dry-run copies gold actions/artifacts solely to check paths and output writing. It makes no API calls and is not a model experiment or complete schema-validation test.

Real calls require `--mode real-run`, a provider multimodal `--model`, explicit `--base-url`, and an API key environment variable (default name `MODEL_API_KEY`). Never put keys in source files. The request contains policy/prompt text and PNG images, omitting the action-coded case ID and gold fields.

`--output-root` sets an exact run directory. Without it, the default is `results/official_full540_runs/<run_id>/<prompt>/<model>`. Each case contains `parsed_response.json`, `raw_response.txt`, and `metadata.json`; failures contain `error.json`. Output directories are ignored by Git.

Existing parsed outputs are skipped unless `--overwrite` is set. `--failed-only` selects cases with an error and no parsed response; `--unseen-only` selects cases with neither. Selection flags can restrict a scenario/case list or shard the dataset.

Retries apply to transient error markers in `is_retryable_error`; model-output parse/action errors are not retried. The first parsable response object with a valid action is retained. Requests keep the same images, prompt and budget. No score-based best-of-N selection occurs. This is not a complete arbitrary-output schema validator.

Defaults are documented in the main README. Use `--help` for configuration switches and `scripts/evaluate.py` for final scoring.
