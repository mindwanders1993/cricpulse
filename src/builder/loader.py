from pathlib import Path

import duckdb
import polars as pl

from src.builder.schema import BUILD_MARTS_SQL, INIT_SCHEMA_SQL
from src.utils import setup_logging

logger = setup_logging()


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
        if "matches" in match_dfs and not match_dfs["matches"].is_empty():
            matches_df = match_dfs["matches"]
            self.con.register("tmp_matches", matches_df.to_arrow())
            self.con.execute("""
                INSERT OR REPLACE INTO gold.dim_match (
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
                FROM tmp_matches;
            """)
            self.con.unregister("tmp_matches")

        if "deliveries" in match_dfs and not match_dfs["deliveries"].is_empty():
            delivs_df = match_dfs["deliveries"]
            self.con.register("tmp_deliveries", delivs_df.to_arrow())
            self.con.execute("""
                INSERT OR REPLACE INTO gold.fact_delivery
                SELECT * FROM tmp_deliveries;
            """)
            self.con.unregister("tmp_deliveries")

        if "innings" in match_dfs and not match_dfs["innings"].is_empty():
            innings_df = match_dfs["innings"]
            self.con.register("tmp_innings", innings_df.to_arrow())
            self.con.execute("""
                INSERT OR REPLACE INTO gold.fact_innings
                SELECT * FROM tmp_innings;
            """)
            self.con.unregister("tmp_innings")

        if "wickets" in match_dfs and not match_dfs["wickets"].is_empty():
            wickets_df = match_dfs["wickets"]
            self.con.register("tmp_wickets", wickets_df.to_arrow())
            self.con.execute("""
                INSERT INTO gold.fact_wicket_detail
                SELECT * FROM tmp_wickets;
            """)
            self.con.unregister("tmp_wickets")

        if "match_players" in match_dfs and not match_dfs["match_players"].is_empty():
            players_df = match_dfs["match_players"]
            self.con.register("tmp_match_players", players_df.to_arrow())
            self.con.execute("""
                INSERT OR REPLACE INTO gold.fact_player_match
                SELECT * FROM tmp_match_players;
            """)
            self.con.unregister("tmp_match_players")

        # Derive dim_venue and dim_team
        self.con.execute("""
            INSERT OR REPLACE INTO gold.dim_venue (venue_id, venue_name, city, country)
            SELECT DISTINCT 
                md5(venue_name) AS venue_id,
                venue_name,
                city,
                NULL AS country
            FROM gold.dim_match
            WHERE venue_name IS NOT NULL;
        """)

        self.con.execute("""
            INSERT OR REPLACE INTO gold.dim_team (team_id, team_name)
            SELECT DISTINCT md5(team1), team1 FROM gold.dim_match WHERE team1 IS NOT NULL
            UNION
            SELECT DISTINCT md5(team2), team2 FROM gold.dim_match WHERE team2 IS NOT NULL;
        """)

        logger.info("matches_loaded_into_duckdb")

    def build_marts(self) -> None:
        """Materialize all analytical Mart tables."""
        logger.info("building_analytical_marts")
        self.con.execute(BUILD_MARTS_SQL)
        logger.info("marts_materialized_successfully")

    def close(self) -> None:
        """Close connection."""
        self.con.close()
