"""Tests for the typer CLI wiring."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from finunderwrite.cli import app

runner = CliRunner()


def test_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "inventory" in result.output


def test_inventory_missing_folder() -> None:
    result = runner.invoke(app, ["inventory", "does-not-exist-xyz"])
    assert result.exit_code == 1


def test_train_categorizer(isolated_settings, tmp_path) -> None:  # type: ignore[no-untyped-def]
    result = runner.invoke(app, ["train-categorizer"])
    assert result.exit_code == 0
    assert "persisted" in result.output.lower()


def test_synth_generate_requires_ml_stack(isolated_settings, tmp_path) -> None:  # type: ignore[no-untyped-def]
    from finunderwrite.synthetic import is_available

    csv = tmp_path / "features.csv"
    csv.write_text("a,b\n1,2\n", encoding="utf-8")
    result = runner.invoke(app, ["synth-generate", str(csv), "--n", "100"])
    if is_available():
        # ML stack present: command should attempt generation (may succeed/fail
        # on tiny input) but must not be the "not installed" error path.
        assert "not installed" not in result.output
    else:
        assert result.exit_code == 1
        assert "requirements-ml.txt" in result.output


def test_inventory_on_fixtures(fixtures_dir: Path) -> None:
    result = runner.invoke(app, ["inventory", str(fixtures_dir)])
    assert result.exit_code == 0
    assert "sbi_style.csv" in result.output
