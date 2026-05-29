"""Tests for PyYAML-backed config loading (nested list-of-dicts)."""

from __future__ import annotations

from config.settings import get_settings
from config.yaml_loader import load_yaml, parse_yaml


def test_parse_nested_list_of_dicts() -> None:
    text = """
payment_modes:
  - mode: UPI
    regex: "^UPI"
  - mode: NEFT
    regex: "^NEFT"
aliases:
  AMZN: Amazon
""".lstrip()
    data = parse_yaml(text)
    assert data["payment_modes"][0] == {"mode": "UPI", "regex": "^UPI"}
    assert data["payment_modes"][1]["mode"] == "NEFT"
    assert data["aliases"]["AMZN"] == "Amazon"


def test_merchant_rules_yaml_loads() -> None:
    rules = load_yaml(get_settings().merchant_rules_path)
    assert any(p["mode"] == "UPI" for p in rules["payment_modes"])
    assert "Amazon" in rules["canonical_merchants"]
    assert rules["aliases"]["AMZN"] == "Amazon"
    assert isinstance(rules["strip_tokens"], list)


def test_category_map_yaml_loads() -> None:
    cmap = load_yaml(get_settings().category_map_path)
    categories = {c["category"] for c in cmap["categories"]}
    # 22 canonical categories expected (matches Categorizer.CATEGORIES).
    assert len(categories) == 22
    assert "Groceries" in categories
    groceries = next(c for c in cmap["categories"] if c["category"] == "Groceries")
    assert "5411" in groceries["mcc"]
    assert cmap["merchant_overrides"]["Amazon"] == "Shopping"
