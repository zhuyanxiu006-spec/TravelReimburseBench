"""Frozen observable error-signature rules; not latent causal attribution."""
import json
import re

TRIGGER_PATTERNS = {
    "D_HOTEL_INVOICE_MISSING_OVERNIGHT": [r"(过夜|隔夜|多日).{0,15}(无|缺少|缺失|未提供).{0,5}(酒店|住宿)", r"(酒店|住宿).{0,5}(发票|凭证).{0,5}(缺失|缺少|未提供).{0,15}(过夜|隔夜|多日)"],
    "D_HOTEL_KEY_FIELD_UNREADABLE": [r"酒店.{0,12}(金额|单价|税额|价税合计).{0,8}(不可读|无法识别|不清晰|缺失)", r"(金额|单价|税额|价税合计).{0,8}(不可读|无法识别|不清晰)"],
    "D_INCOMPLETE_ONE_WAY_CHAIN": [r"单程", r"返程.{0,6}(缺失|缺少|未提供)", r"行程链.{0,8}(不完整|中断)", r"车票.{0,8}(不完整|缺失)"],
    "D_MISSING_TICKET": [r"缺少.{0,6}(车票|火车票|交通票据)", r"(车票|火车票|交通票据).{0,6}(缺失|未提供)"],
    "D_MULTI_CITY_PARTIAL_LODGING": [r"(部分|某些).{0,8}(城市|行程段).{0,8}(无|缺少|缺失).{0,5}(住宿|酒店)", r"住宿.{0,8}(未覆盖|覆盖不全|不完整)"],
    "D_MULTI_PERSON_LODGING_ATTRIBUTION_UNCLEAR": [r"(住宿|酒店).{0,10}(归属|分摊|人员).{0,8}(不清|无法|不能)", r"无法.{0,8}(对应|确定).{0,8}(住宿|酒店|人员)"],
    "D_SUSPECTED_DUPLICATE_HOTEL_INVOICE": [r"(酒店|住宿).{0,6}(发票|票据).{0,8}(疑似重复|重复|相似)"],
    "D_SUSPECTED_DUPLICATE_TICKET": [r"(车票|火车票|交通票据).{0,8}(疑似重复|重复|相似)", r"重复.{0,6}(车票|票据)"],
    "D_TICKET_AMOUNT_UNREADABLE": [r"(车票|票面|交通票据).{0,8}金额.{0,8}(不可读|无法识别|不清晰|缺失)", r"票价.{0,8}(不可读|无法识别|不清晰|缺失)"],
    "D_TICKET_PASSENGER_UNREADABLE": [r"(乘车人|旅客|姓名).{0,8}(不可读|无法识别|不清晰|缺失)"],
    "P_COMPLETE_EVIDENCE": [r"证据.{0,5}(完整|齐全)", r"票据.{0,5}(完整|齐全)", r"无.{0,5}(缺失|冲突)"],
    "P_HOTEL_LIMIT_REDUCTION": [r"(住宿|酒店).{0,8}(超标|超限|超过.{0,5}标准|限额核减|按.{0,4}限额)"],
    "P_SAME_DAY_RETURN_NO_LODGING": [r"当日.{0,4}(往返|返回|返程)", r"当天.{0,4}(往返|返回|返程)", r"无需住宿"],
    "P_SEASONAL_LODGING_POLICY": [r"(旺季|淡季|季节|季节性).{0,8}(标准|限额)", r"(7.?9月|11.?3月).{0,8}(标准|限额)"],
    "P_SPECIAL_MEAL_POLICY": [r"(西藏|青海|新疆).{0,10}(伙食|补助|120)", r"120.{0,8}(人|天|伙食|补助)"],
    "R_DISJOINT_TICKET_HOTEL_GROUPS": [r"(车票|乘车人).{0,50}(酒店|住宿|入住人).{0,50}(不一致|不重合|无交集|不匹配|无一致|均不一致)", r"(酒店|住宿|入住人).{0,50}(车票|乘车人).{0,50}(不一致|不重合|无交集|不匹配|无一致|均不一致)", r"人员组.{0,8}(不一致|不重合|无交集)"],
    "R_HOTEL_CITY_DIRECT_CONFLICT": [r"(酒店|住宿).{0,10}(城市|地点).{0,8}(冲突|不一致|不符|不匹配)", r"城市.{0,8}(冲突|不一致|不符).{0,10}(酒店|住宿|行程)"],
    "R_HOTEL_TIME_DIRECT_CONFLICT": [r"(酒店|住宿).{0,10}(时间|日期|入住|离店).{0,8}(冲突|不一致|重叠|不符|不可能)", r"(入住|离店).{0,8}(日期|时间).{0,8}(冲突|不一致|不符)"],
    "R_MUTUALLY_EXCLUSIVE_TICKETS": [r"(车票|行程).{0,10}(时间|时段).{0,8}(冲突|重叠|互斥|不可能)", r"同一.{0,5}(时间|时段).{0,10}(两张|多张|不同).{0,5}车票"],
    "R_SINGLE_PERSON_TICKET_NAME_CONFLICT": [r"(乘车人|姓名|人员).{0,8}(不一致|冲突|不符|不匹配)", r"不同.{0,4}(姓名|乘车人)"],
    "R_TICKET_DATE_INVERSION": [r"(日期|时间).{0,8}(倒置|逆序|先于|早于|不合理|矛盾)", r"(倒序|顺序倒置|方向倒置)", r"返程.{0,8}(早于|先于).{0,8}(去程|出发)", r"先.{0,20}(返程|返回).{0,30}(再|才).{0,20}(去程|出发)"],
}

PERCEPTION_CODES = {
    "D_HOTEL_KEY_FIELD_UNREADABLE",
    "D_TICKET_AMOUNT_UNREADABLE",
    "D_TICKET_PASSENGER_UNREADABLE",
}
RECONSTRUCTION_CODES = {
    "D_HOTEL_INVOICE_MISSING_OVERNIGHT", "D_INCOMPLETE_ONE_WAY_CHAIN",
    "D_MISSING_TICKET", "D_SUSPECTED_DUPLICATE_TICKET",
    "R_MUTUALLY_EXCLUSIVE_TICKETS", "R_TICKET_DATE_INVERSION",
}
ALIGNMENT_CODES = {
    "D_MULTI_CITY_PARTIAL_LODGING", "D_MULTI_PERSON_LODGING_ATTRIBUTION_UNCLEAR",
    "D_SUSPECTED_DUPLICATE_HOTEL_INVOICE", "R_DISJOINT_TICKET_HOTEL_GROUPS",
    "R_HOTEL_CITY_DIRECT_CONFLICT", "R_HOTEL_TIME_DIRECT_CONFLICT",
    "R_SINGLE_PERSON_TICKET_NAME_CONFLICT",
}
PROCESS_POLICY_CODES = {
    "P_HOTEL_LIMIT_REDUCTION", "P_SAME_DAY_RETURN_NO_LODGING",
    "P_SEASONAL_LODGING_POLICY", "P_SPECIAL_MEAL_POLICY",
}


def narrative_text(pred):
    """Flatten explanatory fields, excluding filled templates/calculations."""
    parts = []
    for key in ("action_reason", "reject_reason", "defer_reason", "case_summary",
                "reasoning_steps", "defer_help_points"):
        value = pred.get(key)
        if value not in (None, "", [], {}):
            parts.append(json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value)
    return " ".join(parts).lower()


def norm_doc(doc_id):
    if not isinstance(doc_id, str):
        return None
    s = re.sub(r"[\s\-]+", "_", doc_id.strip().lower())
    s = re.sub(r"_?\d+$", "", s)
    aliases = {
        "train_ticket": "train_tickets", "train_tickets": "train_tickets",
        "hotel_invoice": "hotel_invoices", "hotel_invoices": "hotel_invoices",
        "hotel_limits": "hotel_standard", "hotel_standard": "hotel_standard",
        "reimbursement_policy": "policy", "policy": "policy",
        "reimbursement_form_template": "template", "template": "template",
    }
    return aliases.get(s.split("/")[-1], s.split("/")[-1])


def evidence_category_recall(g, pred):
    gold = {norm_doc(x.get("doc_id")) for x in (g.get("gold_evidence") or []) if isinstance(x, dict)}
    predicted = {norm_doc(x.get("doc_id")) for x in (pred.get("evidence") or []) if isinstance(x, dict)}
    gold.discard(None)
    predicted.discard(None)
    return len(gold & predicted) / float(len(gold)) if gold else None


def trigger_seen(code, text):
    for pattern in TRIGGER_PATTERNS.get(code, []):
        for match in re.finditer(pattern, text, flags=re.I):
            frag = match.group(0)
            # Do not turn explicit denials ("no conflict") into recognition.
            if re.search(r"(无|没有|不存在|未发现|并无).{0,6}(冲突|矛盾|不一致|不符|不匹配)", frag):
                continue
            return True
    return False


def classify_spurious_process_error(text):
    """Classify the anomaly asserted when a gold Process case is blocked."""
    if re.search(r"(不可读|无法识别|不清晰|缺失|缺少|未提供)", text):
        return "evidence/field perception"
    if re.search(r"(重复|倒序|逆序|行程链.{0,6}(不完整|中断)|时间.{0,6}(重叠|互斥))", text):
        return "itinerary reconstruction"
    if re.search(r"(姓名|人员|乘车人|入住人|城市|日期|住宿归属|分摊).{0,12}(不一致|冲突|不符|不匹配|不清|无法|不能|不唯一)", text):
        return "cross-document alignment"
    if re.search(r"(超标|超限|限额|旺季|淡季|季节|伙食|补助|当天往返|当日往返|房间数|间夜)", text):
        return "rule application"
    return "spurious anomaly detection"


def base_upstream(code):
    if code in PERCEPTION_CODES:
        return "evidence/field perception"
    if code in RECONSTRUCTION_CODES:
        return "itinerary reconstruction"
    if code in ALIGNMENT_CODES:
        return "cross-document alignment"
    if code in PROCESS_POLICY_CODES:
        return "rule application"
    if code == "P_COMPLETE_EVIDENCE":
        return "spurious anomaly detection"
    return "unclassifiable"


def classify(gold, pred, code, seen, text):
    """Return one primary observable signature for a wrong action."""
    if gold == "process":
        return classify_spurious_process_error(text)
    if seen:
        if gold in ("defer", "reject") and pred in ("defer", "reject"):
            return "action gating/priority"
        if gold in ("defer", "reject") and pred == "process":
            return "action gating"
    return base_upstream(code)


