"""Frozen Defer and Reject acceptance contracts."""
import json
import re

AMOUNT_FIELDS = {
    "transport_reimbursable",
    "hotel_reimbursable",
    "meal_allowance",
    "local_transport_allowance",
    "total_reimbursable",
}

# The mapping is fixed by the benchmark action code, not selected after seeing
# an individual model answer. Article 18 and Article 24 are accepted as the
# authenticity/relevance-oriented counterparts to processing-oriented rules.
REJECT_CONTRACT = {
    "R_MUTUALLY_EXCLUSIVE_TICKETS": {
        "evidence": {"train"},
        "articles": {18, 21, 24},
        "concepts": ["互斥", "同时", "重叠", "冲突", "矛盾", "无法同时", "不可能", "overlap", "simultaneous", "mutually exclusive", "impossible", "conflict", "contradiction"],
    },
    "R_TICKET_DATE_INVERSION": {
        "evidence": {"train"},
        "articles": {18, 21, 24},
        "concepts": ["倒置", "顺序", "早于", "先于", "返程", "日期冲突", "时间矛盾", "时间冲突", "date inversion", "reversed", "before the outbound", "chronolog"],
    },
    "R_SINGLE_PERSON_TICKET_NAME_CONFLICT": {
        "evidence": {"train"},
        "articles": {18, 24},
        "concepts": ["姓名不一致", "身份不一致", "乘车人不一致", "人员不一致", "不同乘车人", "不同姓名", "身份冲突", "身份矛盾", "无关人员", "name conflict", "passenger mismatch", "identity mismatch"],
    },
    "R_DISJOINT_TICKET_HOTEL_GROUPS": {
        "evidence": {"train", "hotel"},
        "articles": {18, 19, 20, 24},
        "concepts": ["不相交", "完全不同", "人员集合", "入住人", "乘车人", "人员不一致", "身份冲突", "无关人员", "disjoint", "guest", "passenger", "person mismatch"],
    },
    "R_HOTEL_CITY_DIRECT_CONFLICT": {
        "evidence": {"train", "hotel"},
        "articles": {8, 9, 18, 19, 20, 21, 24},
        "concepts": ["城市冲突", "城市不一致", "不在行程", "地点冲突", "住宿城市", "空间直接", "空间事实", "空间上直接", "互斥城市", "不相关", "city conflict", "city mismatch", "location conflict", "outside the itinerary"],
    },
    "R_HOTEL_TIME_DIRECT_CONFLICT": {
        "evidence": {"train", "hotel"},
        "articles": {8, 9, 18, 19, 20, 21, 24},
        "concepts": ["日期冲突", "时间冲突", "时间矛盾", "时间维度", "行程区间之外", "行程之外", "不在行程", "住宿日期", "完全不相交", "完全不重叠", "无任何重叠", "早于抵达", "早于出发", "结束之后", "time conflict", "date conflict", "outside the itinerary", "outside the trip", "no overlap"],
    },
}

DIRECT_CONFLICT_MARKERS = (
    "冲突", "矛盾", "互斥", "不一致", "不相容", "不相交", "不相关", "无关",
    "不可能", "无法同时", "倒置", "完全不同", "完全无交集", "完全不重叠",
    "行程之外", "区间之外", "早于出发", "晚于行程", "conflict", "contradiction",
    "inconsistent", "incompatible", "disjoint", "irrelevant", "impossible", "mismatch",
    "outside the itinerary", "outside the trip", "mutually exclusive",
)


def normalize_field_set(values):
    if not isinstance(values, list):
        return set()
    return {str(value).strip() for value in values if value is not None and str(value).strip()}


def defer_result(gold, prediction):
    gold_handoff = gold.get("defer_handoff_gt") or {}
    pred_handoff = prediction.get("defer_handoff") or {}
    gold_fields = normalize_field_set(gold_handoff.get("unresolved_fields"))
    pred_fields = normalize_field_set(pred_handoff.get("unresolved_fields"))
    intersection = gold_fields & pred_fields

    tp = len(intersection)
    fp = len(pred_fields - gold_fields)
    fn = len(gold_fields - pred_fields)
    exact = pred_fields == gold_fields

    known = pred_handoff.get("known_amounts") or {}
    known_fields = set(known) if isinstance(known, dict) else set()
    covers_blockers = gold_fields <= pred_fields
    no_false_known = not (known_fields & gold_fields)
    internally_consistent = not (known_fields & pred_fields)
    total_dependency_ok = not (
        (gold_fields - {"total_reimbursable"})
        and "total_reimbursable" in known_fields
    )
    dependency_consistent = (
        prediction.get("action") == "defer"
        and isinstance(prediction.get("defer_handoff"), dict)
        and covers_blockers
        and no_false_known
        and internally_consistent
        and total_dependency_ok
    )
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "exact": exact,
        "covers_blockers": covers_blockers,
        "no_false_known": no_false_known,
        "internally_consistent": internally_consistent,
        "total_dependency_ok": total_dependency_ok,
        "dependency_consistent": dependency_consistent,
    }


def evidence_categories(prediction):
    categories = set()
    for item in prediction.get("evidence") or []:
        if not isinstance(item, dict):
            continue
        doc_id = str(item.get("doc_id") or "").lower()
        text = json.dumps(item, ensure_ascii=False).lower()
        if any(token in doc_id or token in text for token in ("train_ticket", "train ticket", "车票", "火车票")):
            categories.add("train")
        if any(token in doc_id or token in text for token in ("hotel_invoice", "hotel invoice", "酒店发票", "住宿发票")):
            categories.add("hotel")
    return categories


def cited_articles(prediction):
    articles = set()
    for rule in prediction.get("rules") or []:
        if not isinstance(rule, dict):
            continue
        text = " ".join(str(rule.get(key) or "") for key in ("rule_id", "rule_text")).lower()
        for match in re.finditer(r"(?:article|policy_article)[_\s-]*(\d+)", text):
            articles.add(int(match.group(1)))
        for match in re.finditer(r"第\s*([一二三四五六七八九十百零〇两]+)\s*条", text):
            chinese = match.group(1)
            ones = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
            if "十" in chinese:
                left, right = chinese.split("十", 1)
                value = (ones.get(left, 1) * 10) + ones.get(right, 0)
            else:
                value = ones.get(chinese)
            if value is not None:
                articles.add(value)
    return articles


def justification_text(prediction):
    selected = {
        "action_reason": prediction.get("action_reason"),
        "reject_reason": prediction.get("reject_reason"),
        "reasoning_steps": prediction.get("reasoning_steps"),
    }
    return json.dumps(selected, ensure_ascii=False).lower()


def parse_iso_date(value):
    if not value:
        return None
    try:
        return tuple(int(part) for part in str(value)[:10].split("-"))
    except (TypeError, ValueError):
        return None


def valid_reject_codes(gold):
    """Return primary and independently verifiable co-occurring conflicts.

    Some frozen Reject cases intentionally contain more than one sufficient
    contradiction. A justification is valid if it identifies any contradiction
    that is directly recoverable from the frozen structured evidence.
    """
    codes = {gold["action_code"]}
    trajectory = gold.get("trajectory_gt") or {}
    tickets = [ticket for ticket in trajectory.get("tickets") or [] if ticket.get("status") == "有效"]
    stays = [stay for stay in trajectory.get("stays") or [] if stay.get("status") == "有效"]
    trip_start = parse_iso_date(trajectory.get("trip_start"))
    trip_end = parse_iso_date(trajectory.get("trip_end"))
    route_cities = set(trajectory.get("route_cities") or gold.get("route_cities") or [])

    for stay in stays:
        checkin = parse_iso_date(stay.get("checkin"))
        checkout = parse_iso_date(stay.get("checkout"))
        if trip_start and trip_end and checkin and checkout and (checkout <= trip_start or checkin >= trip_end):
            codes.add("R_HOTEL_TIME_DIRECT_CONFLICT")
        if route_cities and stay.get("city") and stay.get("city") not in route_cities:
            codes.add("R_HOTEL_CITY_DIRECT_CONFLICT")

    ticket_people = {ticket.get("person") for ticket in tickets if ticket.get("person") not in (None, "不可读")}
    hotel_people = {person for stay in stays for person in (stay.get("guests") or []) if person not in (None, "不可读")}
    if gold.get("subset") in {"S1", "S2"} and len(ticket_people) > 1:
        codes.add("R_SINGLE_PERSON_TICKET_NAME_CONFLICT")
    if ticket_people and hotel_people and ticket_people.isdisjoint(hotel_people):
        codes.add("R_DISJOINT_TICKET_HOTEL_GROUPS")
    return codes


def reject_result(gold, prediction):
    categories = evidence_categories(prediction)
    articles = cited_articles(prediction)
    text = justification_text(prediction)
    action_ok = prediction.get("action") == "reject"
    contracts = [REJECT_CONTRACT[code] for code in valid_reject_codes(gold)]
    evidence_ok = any(contract["evidence"] <= categories for contract in contracts)
    conflict_ok = any(marker.lower() in text for marker in DIRECT_CONFLICT_MARKERS)
    rule_ok = any(bool(contract["articles"] & articles) for contract in contracts)
    grounded_contract_ok = any(
        contract["evidence"] <= categories
        and bool(contract["articles"] & articles)
        and conflict_ok
        for contract in contracts
    )
    egrj = action_ok and grounded_contract_ok
    return {
        "action_ok": action_ok,
        "evidence_ok": evidence_ok,
        "conflict_ok": conflict_ok,
        "rule_ok": rule_ok,
        "egrj": egrj,
        "grounded_contract_ok": grounded_contract_ok,
        "valid_reject_codes": sorted(valid_reject_codes(gold)),
        "evidence_categories": sorted(categories),
        "articles": sorted(articles),
    }


