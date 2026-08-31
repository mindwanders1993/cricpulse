from pathlib import Path

import polars as pl

from src.utils import setup_logging

logger = setup_logging()


class RegisterParser:
    """Parses `people.csv` and `names.csv` into normalized player dimension and crosswalk DataFrames."""

    def parse_people(self, people_csv_path: Path | str) -> tuple[pl.DataFrame, pl.DataFrame]:
        """Parse `people.csv` into `dim_player` and unpivoted `player_identifiers`.

        Handles schema drift automatically (any new `key_*` columns added by Cricsheet flow through).
        """
        people_csv_path = Path(people_csv_path)
        logger.info("parsing_people_csv", path=str(people_csv_path))

        # Read all columns as string to preserve IDs and handle sparse keys
        df = pl.read_csv(
            people_csv_path,
            schema_overrides={"identifier": pl.Utf8, "name": pl.Utf8, "unique_name": pl.Utf8},
            infer_schema_length=0,
            null_values=[""],
        )

        available_cols = set(df.columns)
        key_cols = [c for c in df.columns if c.startswith("key_")]

        # Extract specific external IDs if present
        espn_col = (
            df["key_cricinfo"] if "key_cricinfo" in available_cols else pl.lit(None, dtype=pl.Utf8)
        )
        cricbuzz_col = (
            df["key_cricbuzz"] if "key_cricbuzz" in available_cols else pl.lit(None, dtype=pl.Utf8)
        )
        bcci_col = df["key_bcci"] if "key_bcci" in available_cols else pl.lit(None, dtype=pl.Utf8)

        dim_player = df.select(
            [
                pl.col("identifier").alias("player_id"),
                pl.col("name").alias("full_name"),
                pl.col("unique_name").alias("unique_name"),
                espn_col.alias("espncricinfo_id"),
                cricbuzz_col.alias("cricbuzz_id"),
                bcci_col.alias("bcci_id"),
            ]
        ).unique(subset=["player_id"])

        # Unpivot key_* columns into long-form identifiers: (player_id, key_source, key_value)
        if key_cols:
            unpivoted = df.select(
                [pl.col("identifier").alias("player_id"), *[pl.col(k) for k in key_cols]]
            ).unpivot(
                index="player_id",
                on=key_cols,
                variable_name="raw_key_source",
                value_name="key_value",
            )
            player_identifiers = (
                unpivoted.filter(pl.col("key_value").is_not_null() & (pl.col("key_value") != ""))
                .with_columns(pl.col("raw_key_source").str.replace("^key_", "").alias("key_source"))
                .select(["player_id", "key_source", "key_value"])
                .unique()
            )
        else:
            player_identifiers = pl.DataFrame(
                schema={"player_id": pl.Utf8, "key_source": pl.Utf8, "key_value": pl.Utf8}
            )

        return dim_player, player_identifiers

    def parse_names(self, names_csv_path: Path | str) -> pl.DataFrame:
        """Parse `names.csv` into deduplicated player aliases."""
        names_csv_path = Path(names_csv_path)
        logger.info("parsing_names_csv", path=str(names_csv_path))

        df = pl.read_csv(
            names_csv_path,
            schema_overrides={"identifier": pl.Utf8, "name": pl.Utf8},
            infer_schema_length=0,
            null_values=[""],
        )

        aliases = (
            df.filter(pl.col("identifier").is_not_null() & pl.col("name").is_not_null())
            .select(
                [
                    pl.col("identifier").alias("player_id"),
                    pl.col("name").alias("alias_name"),
                ]
            )
            .unique()
        )

        return aliases

    def parse_registers(
        self, people_csv_path: Path | str, names_csv_path: Path | str
    ) -> dict[str, pl.DataFrame]:
        """Parse both people and names CSVs in a single call."""
        dim_player, player_identifiers = self.parse_people(people_csv_path)
        player_aliases = self.parse_names(names_csv_path)
        return {
            "dim_player": dim_player,
            "player_identifiers": player_identifiers,
            "player_aliases": player_aliases,
        }
