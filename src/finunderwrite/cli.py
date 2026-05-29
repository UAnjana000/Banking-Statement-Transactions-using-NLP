"""Typer CLI entrypoints."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from config.settings import get_settings
from loguru import logger

from finunderwrite.inventory.profiler import profile_folder
from finunderwrite.logging import configure_logging

app = typer.Typer(
    name="finunderwrite",
    help="Bank-agnostic banking transaction intelligence platform",
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    """Initialize logging before subcommands."""
    settings = get_settings()
    configure_logging(settings.log_level)


@app.command("inventory")
def inventory_cmd(
    folder: Path = typer.Argument(..., help="Folder containing statement files"),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON instead of table"),
) -> None:
    """Profile files in *folder* (type, bank, layout, text layer)."""
    try:
        profiles = profile_folder(folder)
    except (FileNotFoundError, NotADirectoryError) as exc:
        logger.error(str(exc))
        raise typer.Exit(code=1) from exc

    if not profiles:
        typer.echo(f"No supported files found in {folder}")
        raise typer.Exit(code=0)

    if json_output:
        payload = [p.model_dump(mode="json") for p in profiles]
        typer.echo(json.dumps(payload, indent=2))
        return

    for p in profiles:
        typer.echo(
            f"{p.path.name}\t{p.file_type}\t"
            f"pdf={p.pdf_kind or '-'}\t"
            f"bank={p.detected_bank or '-'}\t"
            f"layout={p.layout_hint or '-'}\t"
            f"text_layer={p.has_text_layer}"
        )
        for err in p.errors:
            typer.echo(f"  ERROR: {err}", err=True)


@app.command("parse")
def parse_cmd(
    folder: Path = typer.Argument(..., help="Folder containing statement files"),
) -> None:
    """Parse statements (stub — full pipeline wiring in later prompt)."""
    typer.echo("parse command not yet wired to CLI output; use library API for now.")
    raise typer.Exit(code=0)


@app.command("train-categorizer")
def train_categorizer_cmd() -> None:
    """Train and persist the Tier 2 merchant categorizer model."""
    from finunderwrite.merchant.categorize import Categorizer

    path = Categorizer().train()
    typer.echo(f"Trained categorizer model persisted to {path}")


@app.command("enrich-batch")
def enrich_batch_cmd() -> None:
    """Offline: drain the enrichment queue and populate the cache (network)."""
    from finunderwrite.merchant.enrich import enrich_batch

    counts = enrich_batch()
    typer.echo(
        f"processed={counts['processed']} succeeded={counts['succeeded']} failed={counts['failed']}"
    )


@app.command("synth-generate")
def synth_generate_cmd(
    feature_table: Path = typer.Argument(..., help="CSV feature table to learn from"),
    n: int = typer.Option(100, "--n", help="Number of synthetic rows (100|1000|10000)"),
    method: str = typer.Option(
        "gaussian_copula",
        "--method",
        help="gaussian_copula | ctgan | tvae",
    ),
) -> None:
    """OFFLINE: learn distributions and generate synthetic customers.

    Requires the ML stack (pip install -r requirements-ml.txt).
    """
    from finunderwrite.synthetic import is_available

    if not is_available():
        typer.echo("ML stack not installed. Run: pip install -r requirements-ml.txt", err=True)
        raise typer.Exit(code=1)

    import pandas as pd

    from finunderwrite.synthetic.generate import learn_and_generate

    df = pd.read_csv(feature_table)
    result = learn_and_generate(df, n=n, method=method)
    typer.echo(
        f"generated {result.n} rows via {result.method} -> {result.path} "
        f"(quality={result.fidelity.get('overall_quality_score')})"
    )


def run() -> None:
    app()


if __name__ == "__main__":
    run()
