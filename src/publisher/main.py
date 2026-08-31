import time
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from src.builder.loader import DuckDBLoader
from src.config import get_settings
from src.downloaders.match_downloader import MatchDownloader
from src.downloaders.register_downloader import RegisterDownloader
from src.ledger import IdempotencyLedger
from src.parsers.match_parser import MatchParser
from src.parsers.register_parser import RegisterParser
from src.publisher.publisher import SnapshotPublisher
from src.utils import compute_file_sha256, setup_logging

logger = setup_logging()
console = Console()
app = typer.Typer(help="CricPulse - Data Ingestion & Lakehouse Pipeline CLI")


@app.command()
def ingest_local(
    matches_dir: Annotated[
        Path, typer.Option("--matches-dir", "-m", help="Directory containing Cricsheet JSON files")
    ],
    people_csv: Annotated[
        Path | None, typer.Option("--people-csv", "-p", help="Path to people.csv")
    ] = None,
    names_csv: Annotated[
        Path | None, typer.Option("--names-csv", "-n", help="Path to names.csv")
    ] = None,
    export_parquet: Annotated[
        bool, typer.Option("--export-parquet", help="Export Gold Parquets")
    ] = False,
) -> None:
    """Ingest match JSON files from a local directory (useful for testing and offline runs)."""
    start_time = time.time()
    settings = get_settings()
    console.print(f"[bold green]Starting CricPulse Local Ingestion[/bold green] from {matches_dir}")

    json_files = list(matches_dir.glob("*.json"))
    if not json_files:
        console.print("[bold red]No .json files found in directory![/bold red]")
        raise typer.Exit(1)

    console.print(f"Found [cyan]{len(json_files)}[/cyan] match JSON files.")

    # 1. Parse Register if provided
    register_dfs = {}
    if people_csv and names_csv and people_csv.exists() and names_csv.exists():
        console.print("Parsing player registers...")
        reg_parser = RegisterParser()
        register_dfs = reg_parser.parse_registers(people_csv, names_csv)
        console.print(
            f"Loaded [cyan]{len(register_dfs['dim_player'])}[/cyan] unique player identities."
        )

    # 2. Parse Matches
    console.print("Parsing match documents in parallel/batch...")
    match_parser = MatchParser()
    match_dfs = match_parser.parse_batch(json_files)
    console.print(
        f"Parsed [cyan]{len(match_dfs['matches'])}[/cyan] matches and [cyan]{len(match_dfs['deliveries'])}[/cyan] ball deliveries."
    )

    # 3. Build DuckDB Star Schema
    temp_db_path = settings.data_dir / "temp_build.duckdb"
    if temp_db_path.exists():
        temp_db_path.unlink()

    console.print(f"Building Star Schema in DuckDB: {temp_db_path}...")
    loader = DuckDBLoader(db_path=temp_db_path)
    if register_dfs:
        loader.load_registers(register_dfs)
    loader.load_matches(match_dfs)
    loader.build_marts()
    loader.close()

    # 4. Run DQ Gates and Publish Snapshot
    console.print("Running automated Data Quality assertions...")
    publisher = SnapshotPublisher(settings=settings)
    snap_path, latest_path = publisher.publish_snapshot(temp_db_path)

    if export_parquet:
        console.print("Exporting Gold Parquets...")
        publisher.export_gold_parquets(snap_path)

    elapsed = round(time.time() - start_time, 2)
    console.print(f"[bold green]Ingestion Complete in {elapsed}s![/bold green]")
    console.print(f"Serving Snapshot: [yellow]{latest_path}[/yellow]")


@app.command()
def run(
    mode: Annotated[
        str, typer.Option("--mode", help="Ingestion mode: 'full' or 'incremental'")
    ] = "incremental",
    archive: Annotated[
        str | None,
        typer.Option("--archive", help="Specific archive name (e.g. 't20s_json', 'all_json')"),
    ] = None,
    force: Annotated[bool, typer.Option("--force", help="Bypass idempotency ledger")] = False,
    export_parquet: Annotated[
        bool, typer.Option("--export-parquet", help="Export Gold Parquet files")
    ] = True,
) -> None:
    """Run full or incremental ingestion pipeline from Cricsheet.org."""
    start_time = time.time()
    settings = get_settings()
    ledger = IdempotencyLedger(settings.ledger_db_path)

    target_archive = archive or ("all_json" if mode == "full" else "recently_added_2_json")
    console.print(
        f"[bold green]Starting CricPulse Pipeline[/bold green] (Mode: [cyan]{mode}[/cyan], Archive: [cyan]{target_archive}[/cyan])"
    )

    # 1. Download and Parse Registers
    reg_downloader = RegisterDownloader(settings=settings, ledger=ledger)
    people_csv, names_csv = reg_downloader.download_registers()
    reg_parser = RegisterParser()
    register_dfs = reg_parser.parse_registers(people_csv, names_csv)

    # 2. Download Matches
    match_downloader = MatchDownloader(settings=settings, ledger=ledger)
    extracted_files = match_downloader.download_and_extract(target_archive)

    # 3. Filter via Ledger (Skip already processed unchanged files unless force=True)
    files_to_process: list[Path] = []
    for p in extracted_files:
        match_id = p.stem.replace("wi_", "")
        file_sha = compute_file_sha256(p)
        if force or not ledger.is_match_processed(match_id, file_sha):
            files_to_process.append(p)

    console.print(
        f"Total archive files: [cyan]{len(extracted_files)}[/cyan]. New / modified to process: [cyan]{len(files_to_process)}[/cyan]"
    )

    if not files_to_process:
        console.print("[yellow]No new matches to ingest. Snapshot is up-to-date.[/yellow]")
        return

    # 4. Parse Matches
    match_parser = MatchParser()
    match_dfs = match_parser.parse_batch(files_to_process)

    # 5. Build DuckDB Star Schema
    temp_db_path = settings.data_dir / "temp_build.duckdb"
    if temp_db_path.exists():
        temp_db_path.unlink()

    loader = DuckDBLoader(db_path=temp_db_path)
    loader.load_registers(register_dfs)
    loader.load_matches(match_dfs)
    loader.build_marts()
    loader.close()

    # 6. Publish Snapshot
    publisher = SnapshotPublisher(settings=settings)
    snap_path, latest_path = publisher.publish_snapshot(temp_db_path)

    if export_parquet:
        publisher.export_gold_parquets(snap_path)

    # 7. Record to Ledger
    for p in files_to_process:
        match_id = p.stem.replace("wi_", "")
        file_sha = compute_file_sha256(p)
        current_max_rev = ledger.get_max_match_revision(match_id)
        ledger.record_match(
            match_id=match_id,
            file_sha256=file_sha,
            revision=current_max_rev + 1,
            archive_file=target_archive,
            status="SUCCESS",
        )

    elapsed = round(time.time() - start_time, 2)
    console.print(f"[bold green]Pipeline finished successfully in {elapsed}s![/bold green]")
    console.print(f"Published Snapshot: [cyan]{latest_path}[/cyan]")


if __name__ == "__main__":
    app()
