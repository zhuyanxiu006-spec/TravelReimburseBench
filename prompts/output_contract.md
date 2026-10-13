# 模型输出契约

## 正式提示词

后续实验只使用两份 Full-540 正式提示词：

- `direct.txt`
- `structured_era.txt`

发布包仅包含这两份完整提示词。

## Process 槽位契约

`process.filled_template` 的输出契约保留以下模板层级；最终 TSA 评分允许姓名单元格位置与交通行顺序变化：

- `template_file`
- `sheet_name`
- `traveler_name_cells`
- `transport_detail_rows`
- `fixed_expense_rows`
- `unused_expense_rows`
- `total`
- `total_explanation`
- `unused_explanation_cells`

每个实际模板槽位必须包含且只包含六项：

```json
{
  "cell": "F15",
  "slot_name": "住宿费金额",
  "slot_value": 980,
  "evidence_sources": [
    {
      "doc_id": "hotel_invoice_01",
      "field": "金额",
      "value": 1080
    }
  ],
  "travel_standard_reasoning_trace": [
    {
      "standard_source": "hotel_limits.xlsx",
      "rule_id": "hotel_limit_江苏",
      "rule_text": "江苏住宿标准490元/人·天",
      "applicable_evidence": "南京住宿，1人，2晚",
      "reasoning": "1×2×490=980元，低于发票金额1080元。",
      "conclusion": "住宿费可报销980元。"
    }
  ],
  "calculation": "min(1080, 1×2×490)=980"
}
```

证据、规则 trace 和 calculation 均在槽位内保留，作为输出结构的一部分。最终 TSA 仅核对姓名多重集、不可拆分的六字段交通记录多重集、固定费用字段及总额；不评分槽位中的证据来源、规则 trace、计算文字或自由解释。顶层 `evidence` 和 `rules` 用于 Reject 的自动核验契约及错误诊断；`amount_calculation` 用于五项金额精确匹配。完整评分方法见 `scripts/evaluate.py` 与 `docs/evaluation.md`。

## Defer 人工交接契约

模型输出 `defer_handoff`，与 GT 的 `defer_handoff_gt` 同构：

```json
{
  "blocking_issue": "车票金额不可读，交通费和总额无法确定。",
  "known_facts": {
    "evidence_persons": ["吕泽涵"],
    "trip_start": "2024-11-04",
    "trip_end": "2024-11-06",
    "readable_route_cities": ["苏州"]
  },
  "known_amounts": {
    "hotel_reimbursable": 980,
    "meal_allowance": 300,
    "local_transport_allowance": 240
  },
  "unresolved_fields": [
    "transport_reimbursable",
    "total_reimbursable"
  ],
  "required_information": [
    "提供金额清晰的车票原件或官方订单记录"
  ]
}
```

一致性约束：

- `defer_reason` 必须等于 `defer_handoff.blocking_issue`。
- `defer_help_points` 必须等于 `defer_handoff.required_information`。
- `known_amounts` 只包含当前证据可独立确定的数值分项；未知字段不得写入该对象。
- `unresolved_fields` 只使用五个标准金额字段：`transport_reimbursable`、`hotel_reimbursable`、`meal_allowance`、`local_transport_allowance`、`total_reimbursable`。
- 同一字段不得同时出现在 `known_amounts` 和 `unresolved_fields`。
- 当任一必要分项未定时，不得在 `known_amounts` 中输出 `total_reimbursable`。
- `process` 和 `reject` 的 `defer_handoff` 为 `null`。
