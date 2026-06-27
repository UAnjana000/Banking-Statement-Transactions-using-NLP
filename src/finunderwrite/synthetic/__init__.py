"""Synthetic data generation (OFFLINE ONLY).

Import-light on purpose: the heavy generator lives in
``finunderwrite.synthetic.generate`` and raises at import time if the ML stack
is absent, so it must never be imported from the web runtime. Import it lazily
only from offline CLI/batch code.
"""

__all__ = ["is_available"]


def is_available() -> bool:
    """Return True if the offline ML stack (sdv + torch) is importable."""
    import importlib.util

    return all(importlib.util.find_spec(name) is not None for name in ("sdv", "torch"))
