"""Tests for minimal YAML loader."""

from __future__ import annotations

from config.yaml_loader import parse_yaml


def test_parse_simple_mapping() -> None:
    data = parse_yaml("debit:\n  - withdrawal\n  - dr\ncredit:\n  - deposit\n")
    assert data["debit"] == ["withdrawal", "dr"]
    assert data["credit"] == ["deposit"]
