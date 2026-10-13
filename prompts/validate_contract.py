import json
from pathlib import Path


EXPECTED_TOP_LEVEL = {
    "action",
    "action_reason",
    "case_summary",
    "evidence",
    "rules",
    "filled_template",
    "amount_calculation",
    "reasoning_steps",
    "reject_reason",
    "defer_reason",
    "defer_handoff",
    "defer_help_points",
}
SLOT_KEYS = {
    "cell",
    "slot_name",
    "slot_value",
    "evidence_sources",
    "travel_standard_reasoning_trace",
    "calculation",
}
HANDOFF_KEYS = {
    "blocking_issue",
    "known_facts",
    "known_amounts",
    "unresolved_fields",
    "required_information",
}
KNOWN_FACT_KEYS = {
    "evidence_persons",
    "trip_start",
    "trip_end",
    "readable_route_cities",
}
AMOUNT_FIELDS = {
    "transport_reimbursable",
    "hotel_reimbursable",
    "meal_allowance",
    "local_transport_allowance",
    "total_reimbursable",
}


def assert_slot(slot: dict, location: str) -> None:
    assert set(slot) == SLOT_KEYS, f"{location}: expected GT-aligned slot, got {set(slot)}"
    assert isinstance(slot["evidence_sources"], list), f"{location}: evidence_sources must be list"
    assert isinstance(slot["travel_standard_reasoning_trace"], list), (
        f"{location}: travel_standard_reasoning_trace must be list"
    )


def validate_prompt(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    rendered = source.format(policy_text="POLICY")
    schema_start = rendered.index('{\n  "action"')
    schema = json.loads(rendered[schema_start:])

    assert set(schema) == EXPECTED_TOP_LEVEL
    filled = schema["filled_template"]
    assert_slot(filled["traveler_name_cells"][0], "traveler_name_cells[0]")

    transport_row = filled["transport_detail_rows"][0]
    for name in (
        "departure_date",
        "departure_city",
        "arrival_date",
        "arrival_city",
        "transport",
        "amount",
    ):
        assert_slot(transport_row[name], f"transport_detail_rows[0].{name}")

    for group_name, group in filled["fixed_expense_rows"].items():
        for name in ("person_count", "day_count", "amount"):
            assert_slot(group[name], f"fixed_expense_rows.{group_name}.{name}")

    assert_slot(filled["total"], "total")
    assert_slot(filled["total_explanation"], "total_explanation")

    handoff = schema["defer_handoff"]
    assert set(handoff) == HANDOFF_KEYS
    assert set(handoff["known_facts"]) == KNOWN_FACT_KEYS

    print(f"PASS {path.name}")


def validate_gt_contract(repo_root: Path) -> None:
    gt_path = repo_root / "gt/cases.jsonl"
    records = [json.loads(line) for line in gt_path.read_text(encoding="utf-8").splitlines()]
    process_records = [record for record in records if record["gold_action"] == "process"]
    defer_records = [record for record in records if record["gold_action"] == "defer"]

    assert len(records) == 540
    assert len(process_records) == 180
    assert len(defer_records) == 180

    def validate_gt_slot(slot: dict, location: str) -> None:
        assert SLOT_KEYS <= set(slot), f"{location}: GT slot does not contain required six fields"

    for record in process_records:
        filled = record["filled_template_gt"]
        for index, slot in enumerate(filled["traveler_name_cells"]):
            validate_gt_slot(slot, f'{record["case_id"]}.traveler_name_cells[{index}]')
        for row_index, row in enumerate(filled["transport_detail_rows"]):
            for name in (
                "departure_date",
                "departure_city",
                "arrival_date",
                "arrival_city",
                "transport",
                "amount",
            ):
                validate_gt_slot(row[name], f'{record["case_id"]}.row[{row_index}].{name}')
        for group_name, group in filled["fixed_expense_rows"].items():
            for name in ("person_count", "day_count", "amount"):
                validate_gt_slot(group[name], f'{record["case_id"]}.{group_name}.{name}')
        validate_gt_slot(filled["total"], f'{record["case_id"]}.total')
        validate_gt_slot(filled["total_explanation"], f'{record["case_id"]}.total_explanation')

    for record in defer_records:
        handoff = record["defer_handoff_gt"]
        assert set(handoff) == HANDOFF_KEYS
        assert set(handoff["known_facts"]) == KNOWN_FACT_KEYS
        assert set(handoff["known_amounts"]) <= AMOUNT_FIELDS
        assert set(handoff["unresolved_fields"]) <= AMOUNT_FIELDS
        assert not (set(handoff["known_amounts"]) & set(handoff["unresolved_fields"]))
        assert record["defer_reason"] == handoff["blocking_issue"]

    print("PASS Full-540 GT: 180 process templates and 180 defer handoffs")


def main() -> None:
    prompt_dir = Path(__file__).resolve().parent
    repo_root = prompt_dir.parent
    paths = [prompt_dir / "direct.txt", prompt_dir / "structured_era.txt"]
    assert len(paths) == 2, f"expected 2 revised prompts, found {len(paths)}"
    for path in paths:
        validate_prompt(path)
    validate_gt_contract(repo_root)


if __name__ == "__main__":
    main()
