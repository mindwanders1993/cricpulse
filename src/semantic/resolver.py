from difflib import SequenceMatcher

import duckdb

from src.semantic.models import (
    ResolvedEntities,
    ResolvedPlayer,
    ResolvedTeam,
    ResolvedVenue,
)
from src.utils import setup_logging

logger = setup_logging()

COMMON_TEAM_ALIASES = {
    "csk": "Chennai Super Kings",
    "mi": "Mumbai Indians",
    "rcb": "Royal Challengers Bangalore",
    "kkr": "Kolkata Knight Riders",
    "dc": "Delhi Capitals",
    "pbks": "Punjab Kings",
    "kxip": "Kings XI Punjab",
    "rr": "Rajasthan Royals",
    "srh": "Sunrisers Hyderabad",
    "gt": "Gujarat Titans",
    "lsg": "Lucknow Super Giants",
    "ind": "India",
    "aus": "Australia",
    "eng": "England",
    "pak": "Pakistan",
    "sa": "South Africa",
    "nz": "New Zealand",
    "wi": "West Indies",
    "sl": "Sri Lanka",
    "ban": "Bangladesh",
    "afg": "Afghanistan",
}


def string_similarity(a: str, b: str) -> float:
    """Compute normalized similarity ratio between two strings [0.0, 1.0]."""
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


class EntityResolver:
    """Resolves natural language entities (players, teams, venues) into canonical database IDs."""

    def __init__(self, con: duckdb.DuckDBPyConnection):
        self.con = con

    def resolve_player(self, search_name: str) -> ResolvedPlayer | None:
        """Resolve a player name across exact names, aliases, and fuzzy similarities."""
        cleaned = search_name.strip()
        if not cleaned:
            return None

        # 1. Exact Match on full_name or unique_name
        query_exact = """
            SELECT player_id, full_name, unique_name, espncricinfo_id, cricbuzz_id
            FROM gold.dim_player
            WHERE LOWER(full_name) = LOWER(?) OR LOWER(unique_name) = LOWER(?)
            LIMIT 1;
        """
        row = self.con.execute(query_exact, [cleaned, cleaned]).fetchone()
        if row:
            return ResolvedPlayer(
                player_id=row[0],
                full_name=row[1],
                unique_name=row[2],
                espncricinfo_id=row[3],
                cricbuzz_id=row[4],
                match_score=1.0,
            )

        # 2. Match via gold.player_aliases
        query_alias = """
            SELECT p.player_id, p.full_name, p.unique_name, p.espncricinfo_id, p.cricbuzz_id
            FROM gold.player_aliases a
            JOIN gold.dim_player p ON a.player_id = p.player_id
            WHERE LOWER(a.alias_name) = LOWER(?)
            LIMIT 1;
        """
        row = self.con.execute(query_alias, [cleaned]).fetchone()
        if row:
            return ResolvedPlayer(
                player_id=row[0],
                full_name=row[1],
                unique_name=row[2],
                espncricinfo_id=row[3],
                cricbuzz_id=row[4],
                match_score=0.95,
            )

        # 3. Substring match on full_name (e.g., "Kohli" -> "Virat Kohli", "de Kock" -> "Quinton de Kock")
        query_sub = """
            SELECT player_id, full_name, unique_name, espncricinfo_id, cricbuzz_id
            FROM gold.dim_player
            WHERE LOWER(full_name) LIKE '%' || LOWER(?) || '%'
               OR LOWER(unique_name) LIKE '%' || LOWER(?) || '%'
            LIMIT 1;
        """
        row = self.con.execute(query_sub, [cleaned, cleaned]).fetchone()
        if row:
            return ResolvedPlayer(
                player_id=row[0],
                full_name=row[1],
                unique_name=row[2],
                espncricinfo_id=row[3],
                cricbuzz_id=row[4],
                match_score=0.85,
            )

        # 4. Fuzzy Match across players
        all_players = self.con.execute(
            "SELECT player_id, full_name, unique_name, espncricinfo_id, cricbuzz_id FROM gold.dim_player;"
        ).fetchall()
        best_match = None
        best_score = 0.0

        for p_row in all_players:
            score = max(
                string_similarity(cleaned, p_row[1]),
                string_similarity(cleaned, p_row[2] or ""),
            )
            if score > best_score and score >= 0.70:
                best_score = score
                best_match = p_row

        if best_match:
            return ResolvedPlayer(
                player_id=best_match[0],
                full_name=best_match[1],
                unique_name=best_match[2],
                espncricinfo_id=best_match[3],
                cricbuzz_id=best_match[4],
                match_score=round(best_score, 2),
            )

        return None

    def resolve_team(self, search_team: str) -> ResolvedTeam | None:
        """Resolve a team name or abbreviation to canonical team_name in gold.dim_team."""
        cleaned = search_team.strip().lower()
        if not cleaned:
            return None

        # Check common acronyms/aliases
        target_name = COMMON_TEAM_ALIASES.get(cleaned, search_team.strip())

        # Exact match
        row = self.con.execute(
            "SELECT team_id, team_name FROM gold.dim_team WHERE LOWER(team_name) = LOWER(?) LIMIT 1;",
            [target_name],
        ).fetchone()
        if row:
            return ResolvedTeam(team_id=row[0], team_name=row[1], match_score=1.0)

        # Substring match
        row = self.con.execute(
            "SELECT team_id, team_name FROM gold.dim_team WHERE LOWER(team_name) LIKE '%' || LOWER(?) || '%' LIMIT 1;",
            [target_name],
        ).fetchone()
        if row:
            return ResolvedTeam(team_id=row[0], team_name=row[1], match_score=0.9)

        return None

    def resolve_venue(self, search_venue: str) -> ResolvedVenue | None:
        """Resolve a stadium/venue name in gold.dim_venue."""
        cleaned = search_venue.strip()
        if not cleaned:
            return None

        # Substring / Exact match
        row = self.con.execute(
            """
            SELECT venue_id, venue_name, city
            FROM gold.dim_venue
            WHERE LOWER(venue_name) LIKE '%' || LOWER(?) || '%'
               OR (city IS NOT NULL AND LOWER(city) = LOWER(?))
            LIMIT 1;
            """,
            [cleaned, cleaned],
        ).fetchone()
        if row:
            return ResolvedVenue(venue_id=row[0], venue_name=row[1], city=row[2], match_score=1.0)

        return None

    def resolve_all_from_query(self, user_query: str) -> ResolvedEntities:
        """Extract and resolve entities from an unstructured natural language user prompt."""
        entities = ResolvedEntities()
        words = user_query.split()

        # Check teams first (e.g. "CSK", "India")
        for word in words:
            team = self.resolve_team(word)
            if team and not any(t.team_id == team.team_id for t in entities.teams):
                entities.teams.append(team)

        # Try 2-word, 3-word player combinations or single names
        for n in (3, 2, 1):
            for i in range(len(words) - n + 1):
                phrase = " ".join(words[i : i + n])
                player = self.resolve_player(phrase)
                if (
                    player
                    and player.match_score >= 0.80
                    and not any(p.player_id == player.player_id for p in entities.players)
                ):
                    entities.players.append(player)

        return entities
