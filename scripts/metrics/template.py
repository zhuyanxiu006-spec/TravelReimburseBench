"""Frozen position-invariant, atomic-record form matcher."""
import re
from collections import Counter

def normalize_value(value):
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return round(float(value), 2)
    text = str(value).strip()
    text = re.sub(
        r"(\d{4})[年/.-](\d{1,2})[月/.-](\d{1,2})日?",
        lambda m: f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}",
        text,
    )
    return text


def normalize_transport(value):
    """Normalize wording, without relaxing route, date, or amount fields."""
    value = normalize_value(value)
    if not isinstance(value, str):
        return value
    if any(token in value for token in ("火车", "高铁", "动车")):
        return "火车"
    return value


def slot_value(slot):
    return normalize_value(slot.get("slot_value")) if isinstance(slot, dict) else None


def traveler_multiset(form):
    names = []
    for slot in (form or {}).get("traveler_name_cells") or []:
        value = slot.get("slot_value") if isinstance(slot, dict) else None
        if value is None:
            continue
        if isinstance(value, list):
            pieces = value
        else:
            pieces = re.split(r"[；;、,，/\s]+", str(value).strip())
        names.extend(piece.strip() for piece in pieces if str(piece).strip())
    return Counter(names)


def transport_record(row):
    """A ticket remains one atomic record; fields cannot be matched separately."""
    if not isinstance(row, dict):
        return None
    fields = (
        slot_value(row.get("departure_date")),
        slot_value(row.get("departure_city")),
        slot_value(row.get("arrival_date")),
        slot_value(row.get("arrival_city")),
        normalize_transport((row.get("transport") or {}).get("slot_value")),
        slot_value(row.get("amount")),
    )
    return fields


def transport_multiset(form):
    records = []
    for row in (form or {}).get("transport_detail_rows") or []:
        record = transport_record(row)
        if record is not None:
            records.append(record)
    return Counter(records)


def expense_signature(form):
    groups = (form or {}).get("fixed_expense_rows") or {}
    signature = []
    for group_name in ("lodging", "meal_allowance", "local_transport_allowance"):
        group = groups.get(group_name) or {}
        signature.append(
            (
                group_name,
                slot_value(group.get("person_count")),
                slot_value(group.get("day_count")),
                slot_value(group.get("amount")),
            )
        )
    return tuple(signature)


def evaluate_case(gold, prediction):
    gold_form = gold.get("filled_template_gt") or {}
    pred_form = prediction.get("filled_template") or {}
    names_ok = traveler_multiset(pred_form) == traveler_multiset(gold_form)
    transport_ok = transport_multiset(pred_form) == transport_multiset(gold_form)
    expenses_ok = expense_signature(pred_form) == expense_signature(gold_form)
    total_ok = slot_value(pred_form.get("total")) == slot_value(gold_form.get("total"))
    case_ok = names_ok and transport_ok and expenses_ok and total_ok
    return names_ok, transport_ok, expenses_ok, total_ok, case_ok


