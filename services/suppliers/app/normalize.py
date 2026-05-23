from __future__ import annotations

import csv
import json
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation
from io import StringIO
from typing import Any

SHAPE_MAP = {
    "ROUND": "round",
    "ROUND BRILLIANT": "round",
    "PRINCESS": "princess",
    "CUSHION": "cushion",
    "CUSHION MODIFIED BRILLIANT": "cushion",
    "OVAL": "oval",
    "EMERALD": "emerald",
    "PEAR": "pear",
    "MARQUISE": "marquise",
    "RADIANT": "radiant",
    "SQUARE EMERALD (ASSCHER)": "asscher",
    "ASSCHER": "asscher",
    "HEART": "heart",
}

CLARITY_MAP = {
    "FL": "FL",
    "IF": "IF",
    "VVS1": "VVS1",
    "VVS2": "VVS2",
    "VS1": "VS1",
    "VS2": "VS2",
    "SI1": "SI1",
    "SI2": "SI2",
    "I1": "I1",
    "I2": "I2",
    "I3": "I3",
    "FLAWLESS": "FL",
    "INTERNALLY FLAWLESS": "IF",
    "VERY VERY SLIGHTLY INCLUDED 1": "VVS1",
    "VERY VERY SLIGHTLY INCLUDED 2": "VVS2",
    "VERY SLIGHTLY INCLUDED 1": "VS1",
    "VERY SLIGHTLY INCLUDED 2": "VS2",
    "SLIGHTLY INCLUDED 1": "SI1",
    "SLIGHTLY INCLUDED 2": "SI2",
    "INCLUDED 1": "I1",
    "INCLUDED 2": "I2",
    "INCLUDED 3": "I3",
}

GRADE_MAP = {
    "EXCELLENT": "Excellent",
    "EX": "Excellent",
    "VERY GOOD": "Very Good",
    "VG": "Very Good",
    "GOOD": "Good",
    "GD": "Good",
    "FAIR": "Fair",
    "POOR": "Poor",
}

LABS = {"GIA", "IGI", "HRD", "AGS", "GCAL", "GSI"}


def _clean(value: Any) -> str | None:
    value = "" if value is None else str(value).strip()
    return value or None


def _decimal(value: Any) -> Decimal | None:
    value = _clean(value)
    if value is None:
        return None
    try:
        return Decimal(value.replace(",", ""))
    except InvalidOperation:
        return None


def _required_decimal(value: Any, field: str, row_id: str) -> Decimal:
    parsed = _decimal(value)
    if parsed is None:
        raise ValueError(f"{row_id}: missing/invalid {field}")
    return parsed


def _discount(value: Any) -> Decimal | None:
    parsed = _decimal(value)
    if parsed is not None and abs(parsed) > 1:
        parsed = parsed / Decimal("100")
    return parsed


def _shape(value: Any) -> str:
    value = (_clean(value) or "").upper()
    return SHAPE_MAP.get(value, "other")


def _clarity(value: Any, row_id: str) -> str:
    value = (_clean(value) or "").upper()
    if value not in CLARITY_MAP:
        raise ValueError(f"{row_id}: unsupported clarity {value!r}")
    return CLARITY_MAP[value]


def _grade(value: Any) -> str | None:
    value = (_clean(value) or "").upper()
    return GRADE_MAP.get(value)


def _lab(value: Any) -> str:
    value = (_clean(value) or "").upper()
    return value if value in LABS else "other"


def _color(value: Any) -> tuple[str | None, str | None]:
    value = _clean(value)
    if value and len(value) == 1 and "D" <= value <= "Z":
        return value, None
    return None, value or "Unknown"


def normalize_supplier_rows(rows: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    normalized: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for idx, row in enumerate(rows, start=2):
        stone_id = _clean(row.get("stone_id") or row.get("stock_id") or row.get("stock_no"))
        row_id = f"line {idx} stone {stone_id or 'unknown'}"
        try:
            if not stone_id:
                raise ValueError(f"{row_id}: missing stone_id")
            color_scale, fancy_color = _color(row.get("color") or row.get("color_scale"))
            normalized.append(
                {
                    "stone_id": stone_id,
                    "shape": _shape(row.get("shape")),
                    "carat": _required_decimal(row.get("carat"), "carat", row_id),
                    "color_scale": color_scale,
                    "fancy_color": fancy_color,
                    "clarity": _clarity(row.get("clarity"), row_id),
                    "cut": _grade(row.get("cut")),
                    "polish": _grade(row.get("polish")),
                    "symmetry": _grade(row.get("symmetry")),
                    "cert_number": _clean(row.get("cert_number") or row.get("certificate_no")),
                    "lab": _lab(row.get("lab")),
                    "price_per_carat": _decimal(row.get("price_per_carat") or row.get("ppc")),
                    "price": _decimal(row.get("price") or row.get("total_price")),
                    "rap_price": _decimal(row.get("rap_price")),
                    "rap_discount": _discount(row.get("rap_discount") or row.get("discount")),
                    "measurements": _clean(row.get("measurements")),
                    "raw_payload_json": json.dumps(row),
                }
            )
        except Exception as exc:  # noqa: BLE001
            errors.append({"stone_id": stone_id or "", "error": str(exc)})

    return normalized, errors


def parse_supplier_csv(content: bytes) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(StringIO(text))
    return normalize_supplier_rows(reader)
