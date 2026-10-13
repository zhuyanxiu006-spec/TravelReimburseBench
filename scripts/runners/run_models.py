import argparse
import base64
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib import error, request


PROMPTS = {
    "direct": "direct.txt",
    "structured_era": "structured_era.txt",
}


class ModelResponseParseError(RuntimeError):
    def __init__(self, parse_error: Exception, raw_content: str, usage: Dict[str, Any]) -> None:
        super().__init__(f"model output JSON parse failed: {parse_error}")
        self.raw_content = raw_content
        self.usage = usage


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def discover_pngs(data_root: Path, record: Dict[str, Any]) -> List[Path]:
    case_dir = data_root / record["subset"] / record["case_id"] / "png"
    if not case_dir.exists():
        raise FileNotFoundError(f"missing png directory: {case_dir}")
    pngs = sorted(case_dir.glob("*.png"))
    if not pngs:
        raise FileNotFoundError(f"no PNG files found: {case_dir}")
    return pngs


def render_prompt(prompt_path: Path, policy_text: str) -> str:
    source = prompt_path.read_text(encoding="utf-8")
    return source.format(policy_text=policy_text)


def image_data_url(path: Path) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def extract_json_object(text: str) -> Dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.removeprefix("```json").removeprefix("```").strip()
        if stripped.endswith("```"):
            stripped = stripped[:-3].strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        return json.loads(stripped[start : end + 1])


def make_mock_response(record: Dict[str, Any]) -> Dict[str, Any]:
    action = record["gold_action"]
    response = {
        "action": action,
        "action_reason": f"DRY-RUN mock response copied from GT action for {record['case_id']}.",
        "case_summary": {
            "traveler": "DRY-RUN",
            "itinerary": "DRY-RUN",
            "lodging": "DRY-RUN",
        },
        "evidence": [],
        "rules": [],
        "filled_template": None,
        "amount_calculation": None,
        "reasoning_steps": [
            {"step": "dry_run", "result": "No model API was called."},
        ],
        "reject_reason": None,
        "defer_reason": None,
        "defer_handoff": None,
        "defer_help_points": [],
    }

    if action == "process":
        response["filled_template"] = record["filled_template_gt"]
        calculation = record["calculation_gt"]
        response["amount_calculation"] = {
            "currency": "CNY",
            "transport": {
                "value": calculation["transport_reimbursable"],
                "calculation": "DRY-RUN copied from calculation_gt.transport_reimbursable",
            },
            "lodging": {
                "value": calculation["hotel_reimbursable"],
                "calculation": "DRY-RUN copied from calculation_gt.hotel_reimbursable",
            },
            "meal_allowance": {
                "value": calculation["meal_allowance"],
                "calculation": "DRY-RUN copied from calculation_gt.meal_allowance",
            },
            "local_transport": {
                "value": calculation["local_transport_allowance"],
                "calculation": "DRY-RUN copied from calculation_gt.local_transport_allowance",
            },
            "total_reimbursable": {
                "value": calculation["total_reimbursable"],
                "calculation": "DRY-RUN copied from calculation_gt.total_reimbursable",
            },
        }
    elif action == "reject":
        response["reject_reason"] = record["reject_reason"]
    elif action == "defer":
        response["defer_reason"] = record["defer_reason"]
        response["defer_handoff"] = record["defer_handoff_gt"]
        response["defer_help_points"] = record["defer_handoff_gt"]["required_information"]
    else:
        raise ValueError(f"unexpected gold_action: {action}")
    return response


def call_openai_compatible(
    *,
    base_url: str,
    api_key: str,
    model: str,
    rendered_prompt: str,
    record: Dict[str, Any],
    pngs: List[Path],
    temperature: Optional[float],
    max_tokens: int,
    timeout: int,
    image_detail: str,
    use_json_response_format: bool,
) -> tuple[Dict[str, Any], str, Dict[str, Any]]:
    endpoint = base_url.rstrip("/") + "/chat/completions"
    ordered_images = "\n".join(f"- {index}. {path.name}" for index, path in enumerate(pngs, 1))
    case_text = (
        f"{rendered_prompt}\n\n"
        "The case evidence images are attached below in this exact order:\n"
        f"{ordered_images}\n\n"
        "Use only the attached images and the standards embedded in the prompt. "
        "Return one valid JSON object only."
    )
    content: List[Dict[str, Any]] = [{"type": "text", "text": case_text}]
    for path in pngs:
        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": image_data_url(path),
                    "detail": image_detail,
                },
            }
        )

    payload: Dict[str, Any] = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": content,
            }
        ],
        "max_tokens": max_tokens,
    }
    if temperature is not None:
        payload["temperature"] = temperature
    if use_json_response_format:
        payload["response_format"] = {"type": "json_object"}

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    req = request.Request(endpoint, data=data, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=timeout) as response:
            raw_api = response.read().decode("utf-8")
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from model API: {body}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"model API request failed: {exc}") from exc

    api_payload = json.loads(raw_api)
    choices = api_payload.get("choices") or []
    if not choices:
        raise RuntimeError(f"model API returned no choices: {raw_api[:1000]}")
    message = choices[0].get("message") or {}
    raw_content = message.get("content")
    if not isinstance(raw_content, str) or not raw_content.strip():
        raise RuntimeError(f"model API returned empty content: {raw_api[:1000]}")
    usage = api_payload.get("usage") or {}
    try:
        parsed = extract_json_object(raw_content)
    except json.JSONDecodeError as exc:
        raise ModelResponseParseError(exc, raw_content, usage) from exc
    if not isinstance(parsed, dict) or parsed.get("action") not in {"process", "defer", "reject"}:
        raise ModelResponseParseError(ValueError("response must be a JSON object with a valid action"), raw_content, usage)
    return parsed, raw_content, usage


def get_api_key(env_name: str) -> str:
    api_key = os.environ.get(env_name)
    if not api_key:
        raise RuntimeError(f"missing API key environment variable: {env_name}")
    return api_key


def is_retryable_error(exc: Exception) -> bool:
    if isinstance(exc, ModelResponseParseError):
        return False
    if isinstance(exc, json.JSONDecodeError):
        return True
    text = str(exc)
    retryable_markers = (
        "HTTP 499",
        "HTTP 502",
        "HTTP 503",
        "HTTP 504",
        "Remote end closed connection without response",
        "read operation timed out",
        "model API request failed",
        "model API returned no choices",
        "model API returned empty content",
        "Model output became abnormal",
        "InternalError.Algo.InvalidParameter",
    )
    return any(marker in text for marker in retryable_markers)


def is_timeout_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return isinstance(exc, TimeoutError) or "timed out" in text or "timeout" in type(exc).__name__.lower()


def retry_limit_for_error(exc: Exception, retries: int, timeout_retries: Optional[int]) -> int:
    if isinstance(exc, ModelResponseParseError):
        return 0
    if is_timeout_error(exc) and timeout_retries is not None:
        return max(0, timeout_retries)
    return max(0, retries)


def short_error(exc: Exception) -> Dict[str, Any]:
    return {
        "error_type": type(exc).__name__,
        "error": str(exc)[:2000],
        "failed_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def selected_records(
    records: List[Dict[str, Any]],
    case_ids: Optional[Set[str]],
    subsets: Optional[Set[str]],
    limit: Optional[int],
    shard_index: int,
    shard_count: int,
) -> List[Dict[str, Any]]:
    if case_ids:
        selected = [record for record in records if record["case_id"] in case_ids]
        missing = sorted(case_ids - {record["case_id"] for record in selected})
        if missing:
            raise ValueError(f"case_id not found in GT: {missing}")
    else:
        selected = records
    if subsets:
        selected = [record for record in selected if record.get("subset") in subsets]
    if shard_count < 1:
        raise ValueError("--shard-count must be >= 1")
    if shard_index < 0 or shard_index >= shard_count:
        raise ValueError("--shard-index must satisfy 0 <= shard-index < shard-count")
    if shard_count > 1:
        selected = [
            record
            for index, record in enumerate(selected)
            if index % shard_count == shard_index
        ]
    if limit is not None:
        selected = selected[:limit]
    return selected


def failed_case_ids(output_root: Path, limit: Optional[int]) -> List[str]:
    case_ids = []
    if output_root.exists():
        for error_path in output_root.rglob("error.json"):
            case_dir = error_path.parent
            if not (case_dir / "parsed_response.json").exists():
                case_ids.append(case_dir.name)
    unique_ids = sorted(set(case_ids))
    if limit is not None:
        unique_ids = unique_ids[:limit]
    return unique_ids


def unseen_case_ids(
    output_root: Path,
    records: List[Dict[str, Any]],
    limit: Optional[int],
) -> List[str]:
    case_ids = []
    for record in records:
        case_dir = output_root / record["case_id"]
        if not (case_dir / "parsed_response.json").exists() and not (case_dir / "error.json").exists():
            case_ids.append(record["case_id"])
    if limit is not None:
        case_ids = case_ids[:limit]
    return case_ids


def run(args: argparse.Namespace) -> None:
    runner_path = Path(__file__).resolve()
    repo_root = runner_path.parents[2]

    # The release contains only the frozen final ground truth and PNG corpus.
    gt_path = repo_root / "gt" / "cases.jsonl"
    data_root = Path(args.data_root).resolve() if args.data_root else repo_root / "data"
    if args.mode == "real-run" and (not args.base_url or args.model == "mock-model"):
        raise ValueError("real-run requires an explicit --base-url and --model")
    standards_path = repo_root / "standards" / "standards_context.txt"
    prompt_path = repo_root / "prompts" / PROMPTS[args.prompt]
    if args.output_root:
        output_root = Path(args.output_root).resolve()
    elif args.flat_output:
        output_root = repo_root / "results" / args.results_dir / args.model
    else:
        output_root = repo_root / "results" / args.results_dir / args.run_id / args.prompt / args.model

    records = load_jsonl(gt_path)
    policy_text = standards_path.read_text(encoding="utf-8")
    rendered_prompt = render_prompt(prompt_path, policy_text)
    prompt_hash = sha256(prompt_path)
    gt_hash = sha256(gt_path)
    standards_hash = sha256(standards_path)

    if args.failed_only:
        selected_failed_ids = failed_case_ids(output_root, args.limit)
        if not selected_failed_ids:
            summary = {
                "run_id": args.run_id,
                "model": args.model,
                "prompt": args.prompt,
                "mode": args.mode,
                "selected": 0,
                "completed": 0,
                "skipped": 0,
                "failed": 0,
                "output_root": str(output_root),
                "note": "no failed cases found",
            }
            write_json(output_root / "run_summary.json", summary)
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return
        case_ids = set(selected_failed_ids)
    elif args.unseen_only:
        selected_unseen_ids = unseen_case_ids(output_root, records, args.limit)
        if not selected_unseen_ids:
            summary = {
                "run_id": args.run_id,
                "model": args.model,
                "prompt": args.prompt,
                "mode": args.mode,
                "selected": 0,
                "completed": 0,
                "skipped": 0,
                "failed": 0,
                "output_root": str(output_root),
                "note": "no unseen cases found",
            }
            write_json(output_root / "run_summary.json", summary)
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return
        case_ids = set(selected_unseen_ids)
    else:
        case_ids = set(args.case_id) if args.case_id else None
    subsets = set(args.subset) if args.subset else None
    records_to_run = selected_records(
        records,
        case_ids,
        subsets,
        None if args.failed_only or args.unseen_only else args.limit,
        args.shard_index,
        args.shard_count,
    )

    run_config = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": args.mode,
        "run_id": args.run_id,
        "model": args.model,
        "prompt": args.prompt,
        "prompt_file": str(prompt_path.relative_to(repo_root)),
        "prompt_sha256": prompt_hash,
        "gt_file": str(gt_path.relative_to(repo_root)),
        "gt_sha256": gt_hash,
        "standards_file": str(standards_path.relative_to(repo_root)),
        "standards_sha256": standards_hash,
        "temperature": None if args.omit_temperature else args.temperature,
        "max_tokens": args.max_tokens,
        "base_url": args.base_url,
        "api_key_env": args.api_key_env,
        "image_detail": args.image_detail,
        "json_response_format": not args.no_json_response_format,
        "request_timeout": args.request_timeout,
        "retries": args.retries,
        "retry_sleep": args.retry_sleep,
        "selected_subsets": sorted(subsets) if subsets else None,
        "failed_only": args.failed_only,
        "unseen_only": args.unseen_only,
        "shard_index": args.shard_index,
        "shard_count": args.shard_count,
        "selected_cases": len(records_to_run),
        "canonical_gt_records": len(records),
        "rendered_prompt_chars": len(rendered_prompt),
    }
    write_json(output_root / "run_config.json", run_config)

    completed = 0
    skipped = 0
    failed = 0
    for index, record in enumerate(records_to_run, start=1):
        case_id = record["case_id"]
        case_dir = output_root / case_id
        parsed_path = case_dir / "parsed_response.json"
        if parsed_path.exists() and not args.overwrite:
            skipped += 1
            continue

        if args.overwrite and parsed_path.exists():
            parsed_path.unlink()
        started = time.perf_counter()
        attempt_errors: List[Dict[str, Any]] = []
        configured_timeout_retries = args.retries if args.timeout_retries is None else args.timeout_retries
        max_attempts = 1 if args.mode == "dry-run" else max(args.retries, configured_timeout_retries) + 1
        for attempt in range(1, max_attempts + 1):
            try:
                pngs = discover_pngs(data_root, record)
                if args.mode == "dry-run":
                    parsed = make_mock_response(record)
                    raw_response = json.dumps(parsed, ensure_ascii=False, indent=2)
                    usage: Dict[str, Any] = {}
                else:
                    parsed, raw_response, usage = call_openai_compatible(
                        base_url=args.base_url,
                        api_key=get_api_key(args.api_key_env),
                        model=args.model,
                        rendered_prompt=rendered_prompt,
                        record=record,
                        pngs=pngs,
                        temperature=None if args.omit_temperature else args.temperature,
                        max_tokens=args.max_tokens,
                        timeout=args.request_timeout,
                        image_detail=args.image_detail,
                        use_json_response_format=not args.no_json_response_format,
                    )

                case_dir.mkdir(parents=True, exist_ok=True)
                error_path = case_dir / "error.json"
                if error_path.exists():
                    error_path.unlink()
                (case_dir / "raw_response.txt").write_text(raw_response, encoding="utf-8")
                write_json(parsed_path, parsed)
                write_json(
                    case_dir / "metadata.json",
                    {
                        "case_id": case_id,
                        "subset": record["subset"],
                        "gold_action": record["gold_action"],
                        "mode": args.mode,
                        "model": args.model,
                        "prompt": args.prompt,
                        "prompt_sha256": prompt_hash,
                        "gt_sha256": gt_hash,
                        "png_files": [path.relative_to(data_root).as_posix() for path in pngs],
                        "png_count": len(pngs),
                        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
                        "sequence_index": index,
                        "attempts": attempt,
                        "attempt_errors": attempt_errors,
                        "usage": usage,
                    },
                )
                completed += 1
                break
            except Exception as exc:
                attempt_error = short_error(exc)
                attempt_error["attempt"] = attempt
                attempt_errors.append(attempt_error)
                retry_limit = retry_limit_for_error(exc, args.retries, args.timeout_retries)
                should_retry = attempt <= retry_limit and is_retryable_error(exc)
                if should_retry:
                    time.sleep(args.retry_sleep)
                    continue
                failed += 1
                raw_failure = getattr(exc, "raw_content", None)
                failure_usage = getattr(exc, "usage", {})
                if isinstance(raw_failure, str):
                    case_dir.mkdir(parents=True, exist_ok=True)
                    (case_dir / "raw_response.txt").write_text(raw_failure, encoding="utf-8")
                write_json(
                    case_dir / "error.json",
                    {
                        "case_id": case_id,
                        "attempts": attempt,
                        "attempt_errors": attempt_errors,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                        "failed_at_utc": datetime.now(timezone.utc).isoformat(),
                        "usage": failure_usage,
                        "raw_response_saved": isinstance(raw_failure, str),
                    },
                )
                break

    summary = {
        "run_id": args.run_id,
        "model": args.model,
        "prompt": args.prompt,
        "mode": args.mode,
        "selected": len(records_to_run),
        "completed": completed,
        "skipped": skipped,
        "failed": failed,
        "output_root": str(output_root),
    }
    write_json(output_root / "run_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if failed:
        raise SystemExit(1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run or dry-run Full-540 model calls.")
    parser.add_argument("--mode", choices=["dry-run", "real-run"], default="dry-run")
    parser.add_argument("--data-root", help="Override the PNG evidence root.")
    parser.add_argument("--output-root", help="Write per-case outputs to this exact directory.")
    parser.add_argument("--prompt", choices=sorted(PROMPTS), required=True)
    parser.add_argument("--model", default="mock-model")
    parser.add_argument("--run-id", default="dryrun_dev")
    parser.add_argument("--results-dir", default="official_full540_runs")
    parser.add_argument("--subset", action="append", choices=["S1", "S2", "S3"], help="Run one subset. Repeat for multiple subsets.")
    parser.add_argument("--case-id", action="append", help="Run one case_id. Repeat for multiple cases.")
    parser.add_argument("--limit", type=int, help="Run the first N selected GT records.")
    selection_group = parser.add_mutually_exclusive_group()
    selection_group.add_argument("--failed-only", action="store_true", help="Run failed case directories from this run_id only.")
    selection_group.add_argument("--unseen-only", action="store_true", help="Run cases with neither a parsed response nor an error.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing per-case outputs.")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--omit-temperature", action="store_true", help="Omit temperature from the request.")
    parser.add_argument("--max-tokens", type=int, default=12000)
    parser.add_argument("--base-url", help="OpenAI-compatible API base URL, ending in /v1 where required.")
    parser.add_argument("--api-key-env", default="MODEL_API_KEY")
    parser.add_argument("--request-timeout", type=int, default=300)
    parser.add_argument("--image-detail", choices=["low", "high", "auto"], default="high")
    parser.add_argument("--retries", type=int, default=2, help="Retry transient real-run failures per case.")
    parser.add_argument("--timeout-retries", type=int, help="Override retries for timeout failures.")
    parser.add_argument("--retry-sleep", type=float, default=10.0, help="Seconds to wait between retries.")
    parser.add_argument("--no-json-response-format", action="store_true")
    parser.add_argument("--flat-output", action="store_true", help="Write results directly under results-dir/model.")
    parser.add_argument("--shard-index", type=int, default=0, help="Zero-based shard index for parallel runs.")
    parser.add_argument("--shard-count", type=int, default=1, help="Total shard count for parallel runs.")
    return parser.parse_args()


if __name__ == "__main__":
    run(parse_args())
