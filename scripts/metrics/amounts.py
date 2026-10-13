"""Frozen five-field numeric matcher."""
import re

AMOUNT_KEYS = (
    "transport_reimbursable",
    "hotel_reimbursable",
    "meal_allowance",
    "local_transport_allowance",
    "total_reimbursable",
)

PRED_KEYS = {
    "transport_reimbursable": ("transport",),
    "hotel_reimbursable": ("lodging",),
    "meal_allowance": ("meal_allowance",),
    "local_transport_allowance": ("local_transport",),
    "total_reimbursable": ("total_reimbursable",),
}


def numeric(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return round(float(value), 2)
    text = str(value).strip()
    match = re.fullmatch(r"[-+]?\d+(?:\.\d+)?", text)
    if match:
        return round(float(text), 2)
    return None


def predicted_amount(prediction, key):
    calculation = prediction.get("amount_calculation") or {}
    for name in PRED_KEYS[key]:
        entry = calculation.get(name)
        if isinstance(entry, dict) and "value" in entry:
            return numeric(entry.get("value"))
        if isinstance(entry, (int, float)):
            return numeric(entry)
    return None


