from pathlib import Path

import duckdb
import polars as pl

from src.builder.schema import BUILD_MARTS_SQL, INIT_SCHEMA_SQL
from src.config import Settings, get_settings
from src.utils import setup_logging

logger = setup_logging()

MEMORY_LIMIT = "2GB"  # M0b spike §4 recommendation 3: DuckDB memory_limit=2GB inside a 4 GiB job

# Parsed table → the Gold INSERT that maps it, shared by load_matches (DataFrames) and
# build_from_silver (Silver Parquet). Plain INSERT, so a duplicate match fails loudly (M0b dossier D-9).
_MATCH_INSERTS = {
    "matches": """
        INSERT INTO gold.dim_match (
            match_id, match_date, match_type, gender, season, venue_name, city,
            team1, team2, toss_winner, toss_decision, winner, result_type,
            win_by_runs, win_by_wickets, player_of_match, player_of_match_id,
            is_dls_applied, overs_limit, revision
        )
        SELECT 
            match_id, match_date::DATE, match_type, gender, season, venue, city,
            team1, team2, toss_winner, toss_decision, winner, result_type,
            win_by_runs, win_by_wickets, player_of_match, player_of_match_id,
            is_dls_applied, overs_limit, revision
        FROM {source};
    """,
    "deliveries": "INSERT INTO gold.fact_delivery SELECT * FROM {source};",
    "innings": "INSERT INTO gold.fact_innings SELECT * FROM {source};",
    "wickets": "INSERT INTO gold.fact_wicket_detail SELECT * FROM {source};",
    "match_players": "INSERT INTO gold.fact_player_match SELECT * FROM {source};",
}


def _quote(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


class DuckDBLoader:
    """Loads parsed Polars DataFrames into DuckDB and materializes Star Schema Marts."""

    def __init__(self, db_path: Path | str | None = None):
        self.db_path = str(db_path) if db_path else ":memory:"
        self.con = duckdb.connect(self.db_path)
        self.init_schema()

    def init_schema(self) -> None:
        """Initialize all DDL tables and schemas."""
        self.con.execute(INIT_SCHEMA_SQL)
        logger.info("duckdb_schema_initialized", db_path=self.db_path)

    def load_registers(self, register_dfs: dict[str, pl.DataFrame]) -> None:
        """Load `dim_player`, `player_aliases`, and `player_identifiers` DataFrames."""
        if "dim_player" in register_dfs and not register_dfs["dim_player"].is_empty():
            dim_player_df = register_dfs["dim_player"]
            self.con.register("tmp_dim_player", dim_player_df.to_arrow())
            self.con.execute("""
                INSERT OR REPLACE INTO gold.dim_player (player_id, full_name, unique_name, espncricinfo_id, cricbuzz_id, bcci_id)
                SELECT player_id, full_name, unique_name, espncricinfo_id, cricbuzz_id, bcci_id
                FROM tmp_dim_player;
            """)
            self.con.unregister("tmp_dim_player")

        if "player_aliases" in register_dfs and not register_dfs["player_aliases"].is_empty():
            player_aliases_df = register_dfs["player_aliases"]
            self.con.register("tmp_player_aliases", player_aliases_df.to_arrow())
            self.con.execute("""
                INSERT OR REPLACE INTO gold.player_aliases (player_id, alias_name)
                SELECT player_id, alias_name
                FROM tmp_player_aliases;
            """)
            self.con.unregister("tmp_player_aliases")

        if (
            "player_identifiers" in register_dfs
            and not register_dfs["player_identifiers"].is_empty()
        ):
            player_identifiers_df = register_dfs["player_identifiers"]
            self.con.register("tmp_player_identifiers", player_identifiers_df.to_arrow())
            self.con.execute("""
                INSERT OR REPLACE INTO gold.player_identifiers (player_id, key_source, key_value)
                SELECT player_id, key_source, key_value
                FROM tmp_player_identifiers;
            """)
            self.con.unregister("tmp_player_identifiers")

        logger.info("registers_loaded_into_duckdb")

    def load_matches(self, match_dfs: dict[str, pl.DataFrame]) -> None:
        """Load `dim_match`, `fact_delivery`, `fact_innings`, `fact_wicket_detail`, `fact_player_match`."""
        for table, insert_sql in _MATCH_INSERTS.items():
            if table in match_dfs and not match_dfs[table].is_empty():
                view = f"tmp_{table}"
                self.con.register(view, match_dfs[table].to_arrow())
                self.con.execute(insert_sql.format(source=view))
                self.con.unregister(view)
        self._derive_venue_and_team()
        logger.info("matches_loaded_into_duckdb")

    def build_from_silver(
        self,
        silver_dir: Path,
        register_dfs: dict[str, pl.DataFrame] | None = None,
        settings: Settings | None = None,
    ) -> None:
        """Fill the Gold match tables from every row of `silver_dir/<table>.parquet` (M0b dossier §5.5)."""
        settings = settings or get_settings()
        # M0b spike §4: bounded memory, spilling to the job's local disk, never the mount (dossier §5.2)
        self.con.execute(f"SET memory_limit = '{MEMORY_LIMIT}'")
        self.con.execute(f"SET temp_directory = {_quote(settings.tmp_dir)}")
        if register_dfs:
            self.load_registers(register_dfs)
        for table, insert_sql in _MATCH_INSERTS.items():
            source = f"read_parquet({_quote(silver_dir / f'{table}.parquet')})"
            self.con.execute(insert_sql.format(source=source))
        self._derive_venue_and_team()
        logger.info("silver_loaded_into_duckdb", silver_dir=str(silver_dir))

    def _derive_venue_and_team(self) -> None:
        self.con.execute("""
            INSERT INTO gold.dim_venue (venue_id, venue_name, city, country)
            SELECT DISTINCT 
                md5(venue_name) AS venue_id,
                venue_name,
                city,
                NULL AS country
            FROM gold.dim_match
            WHERE venue_name IS NOT NULL;
        """)

        self.con.execute("""
            INSERT INTO gold.dim_team (team_id, team_name)
            SELECT DISTINCT md5(team1), team1 FROM gold.dim_match WHERE team1 IS NOT NULL
            UNION
            SELECT DISTINCT md5(team2), team2 FROM gold.dim_match WHERE team2 IS NOT NULL;
        """)

    def build_marts(self) -> None:
        """Materialize all analytical Mart tables."""
        logger.info("building_analytical_marts")
        self.con.execute(BUILD_MARTS_SQL)
        logger.info("marts_materialized_successfully")

    def close(self) -> None:
        """Close connection."""
        self.con.close()
