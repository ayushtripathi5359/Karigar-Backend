from decimal import Decimal

from app.modules.suppliers.normalize import normalize_supplier_rows, parse_supplier_csv


def test_normalize_supplier_rows_maps_standard_diamond_fields():
    rows = [
        {
            "stone_id": "ST-001",
            "shape": "Round Brilliant",
            "carat": "1.20",
            "color": "G",
            "clarity": "VS1",
            "cut": "EX",
            "polish": "VG",
            "symmetry": "Good",
            "lab": "GIA",
            "price": "125000",
            "rap_discount": "-25",
        }
    ]

    normalized, errors = normalize_supplier_rows(rows)

    assert errors == []
    assert normalized[0]["stone_id"] == "ST-001"
    assert normalized[0]["shape"] == "round"
    assert normalized[0]["carat"] == Decimal("1.20")
    assert normalized[0]["color_scale"] == "G"
    assert normalized[0]["clarity"] == "VS1"
    assert normalized[0]["cut"] == "Excellent"
    assert normalized[0]["polish"] == "Very Good"
    assert normalized[0]["lab"] == "GIA"
    assert normalized[0]["rap_discount"] == Decimal("-0.25")


def test_normalize_supplier_rows_keeps_valid_rows_and_reports_invalid_rows():
    rows = [
        {
            "stone_id": "BAD-001",
            "shape": "Oval",
            "carat": "1.01",
            "color": "Fancy Pink",
            "clarity": "NOPE",
        },
        {
            "stone_id": "GOOD-001",
            "shape": "Emerald",
            "carat": "2.10",
            "color": "Fancy Blue",
            "clarity": "VVS2",
        },
    ]

    normalized, errors = normalize_supplier_rows(rows)

    assert [row["stone_id"] for row in normalized] == ["GOOD-001"]
    assert normalized[0]["shape"] == "emerald"
    assert normalized[0]["color_scale"] is None
    assert normalized[0]["fancy_color"] == "Fancy Blue"
    assert errors[0]["stone_id"] == "BAD-001"
    assert "unsupported clarity" in errors[0]["error"]


def test_parse_supplier_csv_handles_utf8_bom():
    csv_content = "\ufeffstone_id,shape,carat,color,clarity\nCSV-001,Princess,0.90,H,SI1\n".encode()

    normalized, errors = parse_supplier_csv(csv_content)

    assert errors == []
    assert normalized[0]["stone_id"] == "CSV-001"
    assert normalized[0]["shape"] == "princess"
