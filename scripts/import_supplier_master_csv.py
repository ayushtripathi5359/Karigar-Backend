"""
Import normalized supplier-master CSV into suppliers + supplier_master.

Recommended over PDF import because the CSV preserves each diamond as one row
with stable column names.

Usage:
    .venv/bin/python scripts/import_supplier_master_csv.py \
        --csv "/Users/mainadmin/Downloads/schemas_suppliers_master_normalized(Master).csv"
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
from collections import Counter
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import asyncpg


SHAPE_MAP = {
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
    "VERY GOOD": "Very Good",
    "GOOD": "Good",
    "FAIR": "Fair",
    "POOR": "Poor",
}

FLUORESCENCE_MAP = {
    "NONE": "None",
    "FAINT": "Faint",
    "SLIGHT": "Faint",
    "VERY SLIGHT": "Faint",
    "MEDIUM": "Medium",
    "STRONG": "Strong",
    "VERY STRONG": "Very Strong",
}

AVAILABILITY_MAP = {
    "": "available",
    "AVAILABLE": "available",
    "NEW - AVAILABLE": "available",
    "ON HOLD": "on_hold",
    "NEW - ON HOLD": "on_hold",
    "SOLD": "sold",
    "MEMO": "memo",
    "WITHDRAWN": "withdrawn",
}

LABS = {"GIA", "IGI", "HRD", "AGS", "GCAL", "GSI"}


def _clean(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


def _decimal(value: str | None) -> Decimal | None:
    value = _clean(value)
    if value is None:
        return None
    try:
        return Decimal(value.replace(",", ""))
    except InvalidOperation:
        return None


def _required_decimal(value: str | None, field: str, row_id: str) -> Decimal:
    parsed = _decimal(value)
    if parsed is None:
        raise ValueError(f"{row_id}: missing/invalid {field}")
    return parsed


def _discount(value: str | None) -> Decimal | None:
    parsed = _decimal(value)
    if parsed is not None and abs(parsed) > 1:
        parsed = parsed / Decimal("100")
    return parsed


def _date(value: str | None) -> date | None:
    value = _clean(value)
    if not value:
        return None
    for fmt in ("%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    return None


def _lab(value: str | None) -> str:
    value = (_clean(value) or "").upper()
    return value if value in LABS else "other"


def _shape(value: str | None) -> str:
    value = (_clean(value) or "").upper()
    return SHAPE_MAP.get(value, "other")


def _clarity(value: str | None, row_id: str) -> str:
    value = (_clean(value) or "").upper()
    if value not in CLARITY_MAP:
        raise ValueError(f"{row_id}: unsupported clarity {value!r}")
    return CLARITY_MAP[value]


def _grade(value: str | None) -> str | None:
    value = (_clean(value) or "").upper()
    return GRADE_MAP.get(value)


def _fluorescence(value: str | None) -> str | None:
    value = (_clean(value) or "").upper()
    return FLUORESCENCE_MAP.get(value)


def _availability(value: str | None) -> str:
    value = (_clean(value) or "").upper()
    return AVAILABILITY_MAP.get(value, "available")


def _color(value: str | None) -> tuple[str | None, str | None]:
    value = _clean(value)
    if value and len(value) == 1 and "D" <= value <= "Z":
        return value, None
    return None, value or "Unknown"


def _supplier_extras(row: dict[str, str]) -> dict[str, str]:
    keys = [
        "white_table",
        "white_side",
        "table_black",
        "side_black",
        "table_open",
        "pav_open",
        "crown_open",
    ]
    return {key: row[key] for key in keys if _clean(row.get(key))}


def parse_rows(csv_path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    parsed: list[dict[str, Any]] = []
    errors: list[str] = []
    with csv_path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader, start=2):
            row_id = f"line {idx} stone {row.get('stone_id')}"
            try:
                color_scale, fancy_color = _color(row.get("color"))
                parsed.append(
                    {
                        "supplier": (_clean(row.get("supplier")) or "UNKNOWN").upper(),
                        "stone_id": _clean(row.get("stone_id")),
                        "cert_number": _clean(row.get("cert_number")),
                        "lab": _lab(row.get("lab")),
                        "availability": _availability(row.get("availability")),
                        "location": _clean(row.get("location")),
                        "shape": _shape(row.get("shape")),
                        "carat": _required_decimal(row.get("carat"), "carat", row_id),
                        "color_scale": color_scale,
                        "fancy_color": fancy_color,
                        "clarity": _clarity(row.get("clarity"), row_id),
                        "cut": _grade(row.get("cut")),
                        "polish": _grade(row.get("polish")),
                        "symmetry": _grade(row.get("symmetry")),
                        "fluorescence": _fluorescence(row.get("fluorescence")),
                        "fluorescence_color": _clean(row.get("fluorescence_color")),
                        "rap_price": _decimal(row.get("rap_price")),
                        "rap_value": _decimal(row.get("rap_value")),
                        "rap_discount": _discount(row.get("rap_discount")),
                        "price_per_carat": _decimal(row.get("price_per_carat")),
                        "price": _decimal(row.get("price")),
                        "measurements": _clean(row.get("measurements")),
                        "length": _decimal(row.get("length")),
                        "width": _decimal(row.get("width")),
                        "depth": _decimal(row.get("depth")),
                        "table_pct": _decimal(row.get("table_pct")),
                        "depth_pct": _decimal(row.get("depth_pct")),
                        "crown_angle": _decimal(row.get("crown_angle")),
                        "crown_height": _decimal(row.get("crown_height")),
                        "pav_angle": _decimal(row.get("pav_angle")),
                        "pav_depth": _decimal(row.get("pav_depth")),
                        "ratio": _decimal(row.get("ratio")),
                        "girdle": _clean(row.get("girdle")),
                        "girdle_pct": _decimal(row.get("girdle_pct")),
                        "lower_half": _decimal(row.get("lower_half")),
                        "culet": _clean(row.get("culet")),
                        "milky": _clean(row.get("milky")),
                        "shade": _clean(row.get("shade")),
                        "bgm": _clean(row.get("bgm")),
                        "natts": _clean(row.get("natts")),
                        "hna": _clean(row.get("hna")),
                        "eye_clean": _clean(row.get("eye_clean")),
                        "inclusion_type": _clean(row.get("inclusion_type")),
                        "supplier_extras": _supplier_extras(row),
                        "origin": _clean(row.get("origin")),
                        "comments": _clean(row.get("comments")),
                        "description": _clean(row.get("description")),
                        "inscription": _clean(row.get("inscription")),
                        "cert_date": _date(row.get("cert_date")),
                        "cert_comments": _clean(row.get("cert_comments")),
                        "sheet_date": _date(row.get("sheet_date")),
                        "raw_payload": row,
                    }
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(str(exc))
    return parsed, errors


async def _supplier_id(conn: asyncpg.Connection, supplier_name: str) -> str:
    return str(
        await conn.fetchval(
            """
            INSERT INTO suppliers (supplier_code, display_name, legal_name, tier, is_active, onboarded_at)
            VALUES ($1, $2, $2, 'T2', true, now())
            ON CONFLICT (supplier_code) DO UPDATE
                SET display_name = EXCLUDED.display_name,
                    legal_name = EXCLUDED.legal_name,
                    is_active = true,
                    updated_at = now()
            RETURNING supplier_id
            """,
            supplier_name.lower(),
            supplier_name.title(),
        )
    )


INSERT_SQL = """
INSERT INTO supplier_master (
    supplier_id, stone_id, cert_number, lab, availability, location,
    shape, carat, color_scale, fancy_color, clarity, cut, polish, symmetry,
    fluorescence, fluorescence_color, rap_price, rap_value, rap_discount,
    price_per_carat, price, measurements, length, width, depth, table_pct,
    depth_pct, crown_angle, crown_height, pav_angle, pav_depth, ratio,
    girdle, girdle_pct, lower_half, culet, milky, shade, bgm, natts, hna,
    eye_clean, inclusion_type, supplier_extras, origin, comments, description,
    inscription, cert_date, cert_comments, sheet_date, raw_payload
) VALUES (
    $1, $2, $3, $4::lab_name, $5::stone_availability, $6,
    $7::stone_shape, $8, $9::stone_color_scale, $10, $11::stone_clarity,
    $12::stone_cut, $13::stone_polish, $14::stone_symmetry,
    $15::fluorescence_intensity, $16, $17, $18, $19, $20, $21, $22,
    $23, $24, $25, $26, $27, $28, $29, $30, $31, $32, $33, $34, $35,
    $36, $37, $38, $39, $40, $41, $42, $43, $44::jsonb, $45, $46,
    $47, $48, $49::date, $50, $51::date, $52::jsonb
)
ON CONFLICT (supplier_id, stone_id) WHERE deleted_at IS NULL
DO UPDATE SET
    cert_number = EXCLUDED.cert_number,
    lab = EXCLUDED.lab,
    availability = EXCLUDED.availability,
    location = EXCLUDED.location,
    shape = EXCLUDED.shape,
    carat = EXCLUDED.carat,
    color_scale = EXCLUDED.color_scale,
    fancy_color = EXCLUDED.fancy_color,
    clarity = EXCLUDED.clarity,
    cut = EXCLUDED.cut,
    polish = EXCLUDED.polish,
    symmetry = EXCLUDED.symmetry,
    fluorescence = EXCLUDED.fluorescence,
    fluorescence_color = EXCLUDED.fluorescence_color,
    rap_price = EXCLUDED.rap_price,
    rap_value = EXCLUDED.rap_value,
    rap_discount = EXCLUDED.rap_discount,
    price_per_carat = EXCLUDED.price_per_carat,
    price = EXCLUDED.price,
    measurements = EXCLUDED.measurements,
    length = EXCLUDED.length,
    width = EXCLUDED.width,
    depth = EXCLUDED.depth,
    table_pct = EXCLUDED.table_pct,
    depth_pct = EXCLUDED.depth_pct,
    crown_angle = EXCLUDED.crown_angle,
    crown_height = EXCLUDED.crown_height,
    pav_angle = EXCLUDED.pav_angle,
    pav_depth = EXCLUDED.pav_depth,
    ratio = EXCLUDED.ratio,
    girdle = EXCLUDED.girdle,
    girdle_pct = EXCLUDED.girdle_pct,
    lower_half = EXCLUDED.lower_half,
    culet = EXCLUDED.culet,
    milky = EXCLUDED.milky,
    shade = EXCLUDED.shade,
    bgm = EXCLUDED.bgm,
    natts = EXCLUDED.natts,
    hna = EXCLUDED.hna,
    eye_clean = EXCLUDED.eye_clean,
    inclusion_type = EXCLUDED.inclusion_type,
    supplier_extras = EXCLUDED.supplier_extras,
    origin = EXCLUDED.origin,
    comments = EXCLUDED.comments,
    description = EXCLUDED.description,
    inscription = EXCLUDED.inscription,
    cert_date = EXCLUDED.cert_date,
    cert_comments = EXCLUDED.cert_comments,
    sheet_date = EXCLUDED.sheet_date,
    raw_payload = EXCLUDED.raw_payload,
    updated_at = now()
"""


async def import_csv(db_url: str, csv_path: Path, dry_run: bool) -> None:
    rows, errors = parse_rows(csv_path)
    counts = Counter(row["supplier"] for row in rows)
    print(f"rows={len(rows)} errors={len(errors)} suppliers={dict(sorted(counts.items()))}")
    if errors:
        for error in errors[:10]:
            print(f"ERROR {error}")
    if dry_run:
        for row in rows[:3]:
            print({k: row[k] for k in ("supplier", "stone_id", "shape", "carat", "color_scale", "fancy_color", "clarity", "price")})
        return

    conn = await asyncpg.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    try:
        supplier_ids = {name: await _supplier_id(conn, name) for name in counts}
        async with conn.transaction():
            for row in rows:
                await conn.execute(
                    INSERT_SQL,
                    supplier_ids[row["supplier"]],
                    row["stone_id"],
                    row["cert_number"],
                    row["lab"],
                    row["availability"],
                    row["location"],
                    row["shape"],
                    row["carat"],
                    row["color_scale"],
                    row["fancy_color"],
                    row["clarity"],
                    row["cut"],
                    row["polish"],
                    row["symmetry"],
                    row["fluorescence"],
                    row["fluorescence_color"],
                    row["rap_price"],
                    row["rap_value"],
                    row["rap_discount"],
                    row["price_per_carat"],
                    row["price"],
                    row["measurements"],
                    row["length"],
                    row["width"],
                    row["depth"],
                    row["table_pct"],
                    row["depth_pct"],
                    row["crown_angle"],
                    row["crown_height"],
                    row["pav_angle"],
                    row["pav_depth"],
                    row["ratio"],
                    row["girdle"],
                    row["girdle_pct"],
                    row["lower_half"],
                    row["culet"],
                    row["milky"],
                    row["shade"],
                    row["bgm"],
                    row["natts"],
                    row["hna"],
                    row["eye_clean"],
                    row["inclusion_type"],
                    json.dumps(row["supplier_extras"]),
                    row["origin"],
                    row["comments"],
                    row["description"],
                    row["inscription"],
                    row["cert_date"],
                    row["cert_comments"],
                    row["sheet_date"],
                    json.dumps(row["raw_payload"]),
                )
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument(
        "--db-url",
        default=os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/karigar_app"),
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(import_csv(args.db_url, args.csv, args.dry_run))


if __name__ == "__main__":
    main()
