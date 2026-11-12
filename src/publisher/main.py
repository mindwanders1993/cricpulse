import datetime as dt
import json
import shutil
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from typing import Annotated

import httpx
import polars as pl
import typer
from rich.console import Console

from src.builder.loader import DuckDBLoader
from src.config import Settings, get_settings
from src.downloaders.match_downloader import MatchDownloader
from src.downloaders.register_downloader import RegisterDownloader
from src.parsers.match_parser import PARSER_VERSION
from src.parsers.register_parser import RegisterParser
from src.publisher import manifest, silver
from src.publisher.archive import iter_changed, parse_to_staging
from src.publisher.bench import BATTER, H2H_BATTER, H2H_BOWLER, RUNS, run_bench, verdict
from src.publisher.publisher import SnapshotPublisher
from src.publisher.quality_gates import run_quality_gates
from src.publisher.rollout import RolloutError, ensure_api_on
from src.snapshot import LatestInfo, read_latest
from src.utils import compute_bytes_sha256, compute_file_sha256, setup_logging

logger = setup_logging()
console = Console()
app = typer.Typer(help="CricPulse - Data Ingestion & Lakehouse Pipeline CLI")

VERSION_FORMAT = "v%Y%m%dT%H%MZ"  # M0b dossier D-8
# M0b dossier D-12(c): written after parse_to_staging returns. It holds the run's manifest rows, so a
# leftover merged at start reaches the manifest and D-12(a)'s newer-row rule rebuilds the snapshot
PARSED_MARKER = "_parsed.parquet"

Member = tuple[str, str, bytes]  # (match_id, sha256, raw_bytes), as archive.iter_changed yields


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _report_path(settings: Settings, version: str) -> Path:
    return settings.runs_dir / f"{version}.json"


def _iter_changed_dir(matches_dir: Path, manifest_df: pl.DataFrame) -> Iterator[Member]:
    """The directory twin of archive.iter_changed: yield the .json files that are new or changed."""
    for path in sorted(matches_dir.glob("*.json")):
        raw = path.read_bytes()
        sha = compute_bytes_sha256(raw)
        # M0b dossier D-9: match id = file stem, wi_ prefix kept
        if not manifest.is_current(manifest_df, path.stem, sha, PARSER_VERSION):
            yield path.stem, sha, raw


def _recover_staging(settings: Settings) -> None:
    """Merge a leftover staging dir whose parse finished; delete one whose parse did not."""
    root = settings.silver_dir / "_staging"
    if not root.is_dir():
        return
    for leftover in sorted(p for p in root.iterdir() if p.is_dir()):
        marker = leftover / PARSED_MARKER
        if not marker.exists():
            # M0b dossier D-12(c): without the marker the parse never finished; Silver was not touched
            logger.warning("staging_deleted", staging=str(leftover))
            shutil.rmtree(leftover)
            continue
        # M0b dossier D-12(c): with the marker, finish what the crashed run started (steps 6 and 7)
        rows = pl.read_parquet(marker).to_dicts()
        silver.merge(settings.silver_dir, leftover)
        manifest.save(settings.data_dir, manifest.upsert(manifest.load(settings.data_dir), rows))
        logger.warning("staging_recovered", staging=str(leftover), matches=len(rows))


def _write_marker(staging: Path, manifest_rows: list[dict]) -> None:
    marker = staging / PARSED_MARKER
    tmp = marker.with_name(marker.name + ".tmp")
    pl.DataFrame(manifest_rows, schema=manifest.SCHEMA).write_parquet(tmp)
    tmp.replace(marker)


def _up_to_date(
    settings: Settings,
    previous: LatestInfo | None,
    files_seen: int,
    registers: dict[str, str],
    manifest_df: pl.DataFrame,
) -> bool:
    """M0b dossier D-12(a): measured against the live snapshot, so a run whose gates failed is rebuilt."""
    if files_seen or previous is None:
        return False
    # M0b dossier D-12(b): registers equal the live snapshot's run report; no report counts as changed
    report = _report_path(settings, previous.version)
    if not report.exists() or json.loads(report.read_text()).get("registers") != registers:
        return False
    # M0b dossier D-12(a): a manifest row newer than LATEST.json belongs to a run that never published
    return manifest_df.filter(pl.col("version") > previous.version).is_empty()


def _pipeline(
    settings: Settings,
    source: str,
    reparse_all: bool,
    get_registers: Callable[[dt.date], tuple[Path, Path]],
    get_members: Callable[[dt.date, pl.DataFrame], Iterable[Member]],
) -> LatestInfo | None:
    """M0b dossier §5.1 steps 1-11; returns what LATEST.json now names, or None when up to date."""
    started = _utc_now()
    version = started.strftime(VERSION_FORMAT)  # step 1
    # M0b dossier D-12(d): a second run of the same version is refused before step 2
    for existing in (
        settings.snapshots_dir / f"cricket_{version}.duckdb",
        _report_path(settings, version),
    ):
        if existing.exists():
            raise FileExistsError(f"run {version} refused, it already exists: {existing}")
    _recover_staging(settings)
    console.print(
        f"[bold green]CricPulse run {version}[/bold green] (source: [cyan]{source}[/cyan])"
    )

    people_csv, names_csv = get_registers(started.date())  # step 2
    registers = {p.name: compute_file_sha256(p) for p in (people_csv, names_csv)}
    manifest_df = manifest.load(settings.data_dir)
    items = get_members(started.date(), manifest_df)  # step 3

    # Step 4. M0b dossier §5.2: silver/_staging/<version>/; archive.py reads the version from its name
    staging = settings.silver_dir / "_staging" / version
    state = parse_to_staging(items, staging)
    if state.changed_ids:
        _write_marker(staging, state.manifest_rows)
    console.print(
        f"Changed: [cyan]{state.files_seen}[/cyan], parsed: [cyan]{len(state.changed_ids)}[/cyan], "
        f"quarantined: [cyan]{len(state.quarantined)}[/cyan]"
    )

    previous = read_latest(settings.data_dir)
    if _up_to_date(settings, previous, state.files_seen, registers, manifest_df):  # step 5
        console.print(f"[yellow]Up to date: {previous.version} stays live.[/yellow]")
        return None

    if state.changed_ids:
        silver.merge(settings.silver_dir, staging)  # step 6
        new_manifest = manifest.upsert(manifest_df, state.manifest_rows)
        manifest.save(settings.data_dir, new_manifest)  # step 7

    # Step 8. M0b dossier §5.2: build on the local tmp/, never on the mount
    temp_db = settings.tmp_dir / f"{version}.duckdb"
    temp_db.unlink(missing_ok=True)
    publisher = SnapshotPublisher(settings=settings)
    try:
        loader = DuckDBLoader(db_path=temp_db)
        try:
            register_dfs = RegisterParser().parse_registers(people_csv, names_csv)
            loader.build_from_silver(settings.silver_dir, register_dfs, settings)
            loader.build_marts()
            # Step 9. Invariant 1: every gate passes before LATEST.json is written
            run_quality_gates(
                loader.con,
                previous=previous,
                quarantined=len(state.quarantined),
                files_seen=state.files_seen,  # M0b dossier D-5: the changed members tried
            )
        finally:
            loader.close()
        info = publisher.publish(temp_db, version)  # step 10
    finally:
        temp_db.unlink(missing_ok=True)

    pruned = publisher.prune(today=started.date())  # step 11
    report = {
        "version": version,
        "source": source,
        "reparse_all": reparse_all,
        "registers": registers,  # M0b dossier D-12(b)
        "files_seen": state.files_seen,
        "changed": len(state.changed_ids),
        "quarantined": [{"match_id": m, "error": e} for m, e in state.quarantined],
        "snapshot": info.model_dump(mode="json"),
        "pruned": [p.relative_to(settings.data_dir).as_posix() for p in pruned],
    }
    path = _report_path(settings, version)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)

    console.print(
        f"[bold green]Published {version}[/bold green]: [cyan]{info.match_count}[/cyan] matches, "
        f"[cyan]{info.delivery_count}[/cyan] deliveries, data to {info.data_cutoff} → {info.path}"
    )
    return info


def _roll_out(settings: Settings) -> None:
    """M0b dossier D-13a: after a run that ends with a live snapshot, the API serves LATEST.json's."""
    version = read_latest(settings.data_dir).version
    try:
        ensure_api_on(version, settings)
    except (httpx.HTTPError, RolloutError) as e:
        # M0b dossier D-13a: a failed rollout exits non-zero so the failure alert fires; LATEST.json stays
        console.print(f"[bold red]API rollout to {version} failed:[/bold red] {e}", soft_wrap=True)
        raise typer.Exit(1) from e


@app.command()
def ingest_local(
    matches_dir: Annotated[
        Path,
        typer.Option(
            "--matches-dir",
            "-m",
            help="Directory containing Cricsheet JSON files",
            exists=True,
            file_okay=False,
        ),
    ],
    people_csv: Annotated[
        Path,
        typer.Option("--people-csv", "-p", help="Path to people.csv", exists=True, dir_okay=False),
    ],
    names_csv: Annotated[
        Path,
        typer.Option("--names-csv", "-n", help="Path to names.csv", exists=True, dir_okay=False),
    ],
) -> None:
    """The run's steps on a local directory of match JSON files and local registers (offline runs)."""
    if not any(matches_dir.glob("*.json")):
        console.print("[bold red]No .json files found in directory![/bold red]")
        raise typer.Exit(1)
    settings = get_settings()
    settings.ensure_directories()  # M0b dossier D-14a: the run makes its folders, get_settings() does not
    _pipeline(
        settings,
        source=str(matches_dir),
        reparse_all=False,
        get_registers=lambda day: (people_csv, names_csv),
        get_members=lambda day, manifest_df: _iter_changed_dir(matches_dir, manifest_df),
    )


@app.command()
def run(
    archive: Annotated[
        str | None,
        typer.Option(
            "--archive",
            help="Cricsheet archive, e.g. all_json (default: NIGHTLY_ARCHIVE, recently_added_7_json)",
        ),
    ] = None,
    reparse_all: Annotated[
        bool,
        typer.Option(
            "--reparse-all", help="Parse every member, even those the manifest has as current"
        ),
    ] = False,
) -> None:
    """Nightly job: download, parse what changed, merge into Silver, build Gold, gate, publish."""
    settings = get_settings()
    settings.ensure_directories()  # M0b dossier D-14a: the run makes its folders, get_settings() does not
    archive = archive or settings.nightly_archive  # M0b dossier D-2
    _pipeline(
        settings,
        source=archive,
        reparse_all=reparse_all,
        get_registers=RegisterDownloader(settings=settings).download_registers_to_bronze,
        get_members=lambda day, manifest_df: iter_changed(
            MatchDownloader(settings=settings).download_to_bronze(archive, day),
            manifest_df,
            PARSER_VERSION,
            reparse_all,
        ),
    )
    _roll_out(settings)  # a failed gate raised above and never gets here


@app.command()
def bench(
    batter: Annotated[
        str, typer.Option(help="Batter for the batting career and phase splits questions")
    ] = BATTER,
    h2h_batter: Annotated[
        str, typer.Option(help="Batter in the head-to-head question")
    ] = H2H_BATTER,
    h2h_bowler: Annotated[
        str, typer.Option(help="Bowler in the head-to-head question")
    ] = H2H_BOWLER,
) -> None:
    """D-3: time the five spike questions on the live snapshot, read-only; print p50/p95 and the verdict."""
    settings = get_settings()
    info = read_latest(settings.data_dir)
    if info is None:
        console.print("[bold red]No LATEST.json: no snapshot to bench.[/bold red]")
        raise typer.Exit(1)
    timings = run_bench(settings.data_dir / info.path, batter, h2h_batter, h2h_bowler)
    console.print(f"Bench on {info.version}: p50 and p95 of {RUNS} warm runs per question")
    for t in timings:
        console.print(f"{t.question:<15} p50 {t.p50_ms:8.1f} ms  p95 {t.p95_ms:8.1f} ms")
    console.print(f"D-3: {verdict(timings)}")


if __name__ == "__main__":
    app()
