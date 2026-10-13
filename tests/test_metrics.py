"""Regression checks for metric denominators, atomic records and API inputs."""
import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from evaluate import evaluate, score_case, summarize
from metrics.downstream import defer_result, reject_result
from metrics.template import evaluate_case

spec = importlib.util.spec_from_file_location("release_runner", ROOT / "scripts/runners/run_models.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class MetricTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gold = [json.loads(s) for s in (ROOT / "gt/cases.jsonl").read_text(encoding="utf-8").splitlines()]
        cls.process = next(g for g in cls.gold if g["gold_action"] == "process" and len(g["filled_template_gt"]["transport_detail_rows"]) >= 2)
        cls.defer = next(g for g in cls.gold if g["gold_action"] == "defer" and "transport_reimbursable" in g["defer_handoff_gt"]["unresolved_fields"])
        cls.reject = next(g for g in cls.gold if g["gold_action"] == "reject")

    def test_transport_permutation_passes_but_cross_ticket_mix_fails(self):
        prediction = runner.make_mock_response(self.process)
        prediction = copy.deepcopy(prediction)
        rows = prediction["filled_template"]["transport_detail_rows"]
        rows.reverse()
        self.assertTrue(evaluate_case(self.process, prediction)[-1])
        rows[0]["departure_city"], rows[1]["departure_city"] = rows[1]["departure_city"], rows[0]["departure_city"]
        self.assertFalse(evaluate_case(self.process, prediction)[-1])

    def test_handoff_total_dependency_and_extra_unresolved(self):
        prediction = copy.deepcopy(runner.make_mock_response(self.defer))
        self.assertTrue(defer_result(self.defer, prediction)["dependency_consistent"])
        prediction["defer_handoff"]["known_amounts"]["total_reimbursable"] = 123
        self.assertFalse(defer_result(self.defer, prediction)["dependency_consistent"])
        prediction["defer_handoff"]["known_amounts"].pop("total_reimbursable")
        known = prediction["defer_handoff"]["known_amounts"]
        if known:
            additional = next(iter(known))
            known.pop(additional)
            prediction["defer_handoff"]["unresolved_fields"].append(additional)
            self.assertTrue(defer_result(self.defer, prediction)["dependency_consistent"])

    def test_reject_requires_evidence_and_rule_family(self):
        prediction = {"action": "reject", "action_reason": "存在冲突", "evidence": [{"doc_id": "train_ticket_01"}, {"doc_id": "hotel_invoice_01"}], "rules": [{"rule_id": "policy_article_24"}]}
        self.assertTrue(reject_result(self.reject, prediction)["egrj"])
        prediction["rules"] = []
        self.assertFalse(reject_result(self.reject, prediction)["egrj"])
        prediction["rules"] = [{"rule_id": "policy_article_24"}]
        prediction["evidence"] = []
        self.assertFalse(reject_result(self.reject, prediction)["egrj"])

    def test_wrong_action_does_not_receive_artifact_credit(self):
        prediction = runner.make_mock_response(self.process)
        prediction["action"] = "defer"
        row = score_case(self.process, prediction)
        self.assertFalse(row["workflow_pass"])
        self.assertFalse(row["five_amounts_exact"])

    def test_missing_predictions_keep_denominators_and_zero_is_null(self):
        gold = {g["case_id"]: g for g in self.gold}
        report = evaluate(gold, {})
        self.assertEqual(report["action_accuracy"]["denominator"], 540)
        self.assertEqual(report["WCR_by_action"]["process"]["denominator"], 180)
        self.assertIsNone(report["conditional"]["TSA"]["percent"])
        self.assertEqual(report["WCR"]["percent"], 0)

    def test_malformed_artifact_fails_without_dropping_case(self):
        row = score_case(self.defer, {"action": "defer", "defer_handoff": "invalid"})
        self.assertTrue(row["correct_action"])
        self.assertFalse(row["workflow_pass"])
        self.assertTrue(row["malformed_artifact"])
        self.assertEqual(summarize([row])["conditional"]["HC"]["denominator"], 1)

    def test_api_payload_excludes_action_coded_id_and_omitted_temperature(self):
        captured = []
        class Response:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def read(self):
                return json.dumps({"choices": [{"message": {"content": '{"action":"process"}'}}]}).encode()
        def fake_urlopen(request, timeout):
            captured.append(json.loads(request.data))
            return Response()
        png = next((ROOT / "data" / self.process["subset"] / self.process["case_id"] / "png").glob("*.png"))
        with patch.object(runner.request, "urlopen", fake_urlopen):
            runner.call_openai_compatible(base_url="https://example.invalid/v1", api_key="test-only", model="test-model", rendered_prompt="TEST POLICY", record=self.process, pngs=[png], temperature=None, max_tokens=12000, timeout=5, image_detail="high", use_json_response_format=True)
        payload = captured[0]
        text = payload["messages"][0]["content"][0]["text"]
        self.assertNotIn(self.process["case_id"], text)
        self.assertNotIn("gold_action", text)
        self.assertNotIn("temperature", payload)
        self.assertEqual(payload["messages"][0]["content"][1]["image_url"]["detail"], "high")


if __name__ == "__main__":
    unittest.main()
