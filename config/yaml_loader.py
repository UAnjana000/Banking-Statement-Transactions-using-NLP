"""YAML loading for finunderwrite config files (backed by PyYAML).

Historically this module implemented a minimal hand-rolled parser to avoid a
PyYAML dependency (ADR-002). As config files grew to need nested list-of-dicts
(merchant rules, category map), we adopted PyYAML (ADR-004). The public
``load_yaml`` / ``parse_yaml`` signatures are preserved for backward
compatibility with existing importers (e.g. schema_detection).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML mapping from *path*."""
    text = path.read_text(encoding="utf-8")
    return parse_yaml(text)


def parse_yaml(text: str) -> dict[str, Any]:
    """Parse YAML *text* into a mapping (empty text -> empty dict)."""
    data = yaml.safe_load(text)
    if data is None:
        return {}
    if not isinstance(data, dict):
        msg = f"Expected a YAML mapping at the top level, got {type(data).__name__}"
        raise ValueError(msg)
    return data
