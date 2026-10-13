#!/usr/bin/env python3
"""Evaluate a directory of <case_id>/parsed_response.json against frozen GT."""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from metrics.amounts import AMOUNT_KEYS, numeric, predicted_amount
from metrics.downstream import defer_result, reject_result
from metrics.signatures import (
    classify, evidence_category_recall, narrative_text, trigger_seen,
)
from metrics.template import evaluate_case

ROOT = Path(__file__).resolve().parents[1]
ACTIONS = ("process", "defer", "reject")


def fraction(hits, denominator):
    return {
        "numerator": hits,
        "denominator": denominator,
        "percent": 100.0 * hits / denominator if denominator else None,
    }


def load_predictions(directory, gold, allow_missing=False):
    predictions = {}
    for path in sorted(directory.glob("*/parsed_response.json")):
        case_id = path.parent.name
        if case_id not in gold:
            raise ValueError(f"Unknown case directory: {case_id}")
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError(f"Expected a JSON object: {path}")
        predictions[case_id] = value
    missing = sorted(set(gold) - set(predictions))
    if missing and not allow_missing:
        raise ValueError(
            f"Missing {len(missing)} predictions. Use --allow-missing to count "
            "missing outputs as failures while retaining all gold denominators."
        )
    if not predictions:
        raise ValueError("No <case_id>/parsed_response.json files found")
    return predictions, missing


def score_case(gold, prediction):
    action = prediction.get("action")
    correct = action == gold["gold_action"]
    artifact = False
    malformed = False
    amount_exact = False
    if correct:
        try:
            if action == "process":
                artifact = evaluate_case(gold, prediction)[-1]
            elif action == "defer":
                artifact = defer_result(gold, prediction)["dependency_consistent"]
            else:
                artifact = reject_result(gold, prediction)["egrj"]
        except (AttributeError, KeyError, TypeError, ValueError):
            # Malformed artifacts fail without silently removing their cases.
            malformed = True
        if action == "process":
            try:
                amount_exact = all(
                    predicted_amount(prediction, key)
                    == numeric(gold["calculation_gt"][key])
                    for key in AMOUNT_KEYS
                )
            except (AttributeError, KeyError, TypeError, ValueError):
                malformed = True
    return {
        "case_id": gold["case_id"], "subset": gold["subset"],
        "action_code": gold["action_code"], "gold_action": gold["gold_action"],
        "predicted_action": action if isinstance(action, str) else None,
        "correct_action": correct, "downstream_pass": bool(artifact),
        "workflow_pass": correct and bool(artifact),
        "five_amounts_exact": amount_exact, "malformed_artifact": malformed,
    }


def summarize(rows):
    confusion = Counter((r["gold_action"], r["predicted_action"]) for r in rows)
    totals = Counter(r["gold_action"] for r in rows)
    recalls, f1s = {}, {}
    for action in ACTIONS:
        tp = confusion[action, action]
        fn = totals[action] - tp
        fp = sum(r["predicted_action"] == action and r["gold_action"] != action for r in rows)
        recalls[action] = fraction(tp, totals[action])
        f1s[action] = 100.0 * 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None
    hits = Counter(r["gold_action"] for r in rows if r["workflow_pass"])
    conditional = {
        name: fraction(hits[action], confusion[action, action])
        for name, action in (("TSA", "process"), ("HC", "defer"), ("RJ", "reject"))
    }
    return {
        "n_cases": len(rows),
        "action_accuracy": fraction(sum(r["correct_action"] for r in rows), len(rows)),
        "macro_f1_percent": sum(f1s.values()) / 3 if all(v is not None for v in f1s.values()) else None,
        "action_recall": recalls, "action_f1_percent": f1s,
        "over_automation": fraction(confusion["defer", "process"] + confusion["reject", "process"], totals["defer"] + totals["reject"]),
        "over_conservatism": fraction(confusion["process", "defer"] + confusion["process", "reject"], totals["process"]),
        "conditional": conditional,
        "WCR": fraction(sum(hits.values()), len(rows)),
        "WCR_by_action": {a: fraction(hits[a], totals[a]) for a in ACTIONS},
        "five_amounts_exact": fraction(sum(r["five_amounts_exact"] for r in rows), totals["process"]),
        "confusion_counts": {
            a: {p: confusion[a, p] for p in ACTIONS} | {
                "invalid_or_missing": sum(r["gold_action"] == a and r["predicted_action"] not in ACTIONS for r in rows)
            } for a in ACTIONS
        },
        "malformed_artifact_count": sum(r["malformed_artifact"] for r in rows),
    }


def evaluate(gold, predictions):
    rows = [score_case(g, predictions.get(cid, {})) for cid, g in gold.items()]
    report = summarize(rows)
    report["by_scenario"] = {
        s: summarize([r for r in rows if r["subset"] == s])
        for s in sorted({r["subset"] for r in rows})
    }
    report["by_action_code"] = {
        c: summarize([r for r in rows if r["action_code"] == c])
        for c in sorted({r["action_code"] for r in rows})
    }
    errors, signatures = [], Counter()
    for r in rows:
        if r["correct_action"] or r["case_id"] not in predictions:
            continue
        g, p = gold[r["case_id"]], predictions[r["case_id"]]
        text = narrative_text(p)
        seen = trigger_seen(g["action_code"], text)
        signature = classify(g["gold_action"], r["predicted_action"], g["action_code"], seen, text)
        signatures[signature] += 1
        errors.append({
            **r, "trigger_named": seen, "observable_signature": signature,
            "evidence_category_recall": evidence_category_recall(g, p),
        })
    evidence_scores = [r["evidence_category_recall"] for r in errors if r["evidence_category_recall"] is not None]
    report["error_diagnostics"] = {
        "n_observed_wrong_outputs": len(errors), "signature_counts": dict(signatures),
        "trigger_named": fraction(sum(r["trigger_named"] for r in errors), len(errors)),
        "mean_evidence_category_recall_percent": 100 * sum(evidence_scores) / len(evidence_scores) if evidence_scores else None,
        "outputs_omitting_required_category": fraction(sum(v < 1 for v in evidence_scores), len(evidence_scores)),
        "case_records": errors,
    }
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--gt", type=Path, default=ROOT / "gt/cases.jsonl")
    parser.add_argument("--output", type=Path, help="Optional JSON report path; otherwise print to stdout.")
    parser.add_argument("--allow-missing", action="store_true")
    args = parser.parse_args()
    records = [json.loads(s) for s in args.gt.read_text(encoding="utf-8").splitlines() if s.strip()]
    gold = {r["case_id"]: r for r in records}
    if len(gold) != len(records) or not gold:
        raise ValueError("Empty GT or duplicate case IDs")
    predictions, missing = load_predictions(args.predictions, gold, args.allow_missing)
    report = evaluate(gold, predictions)
    report["gt_sha256"] = hashlib.sha256(args.gt.read_bytes()).hexdigest()
    report["n_loaded_predictions"] = len(predictions)
    report["missing_case_ids"] = missing
    report["metric_contract"] = "final-case-exact-template-dependency-handoff-rule-family-reject"
    serialized = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
        print(f"Evaluated {len(predictions)}/{len(gold)} outputs; report: {args.output}")
    else:
        print(serialized, end="")


if __name__ == "__main__":
    main()
