import csv
import re
from difflib import SequenceMatcher
from pathlib import Path

import duckdb

from src.semantic.models import (
    ResolvedEntities,
    ResolvedPlayer,
    ResolvedTeam,
    ResolvedVenue,
)
from src.utils import setup_logging

logger = setup_logging()

# RapidFuzz / Jaro-Winkler implementation
try:
    from rapidfuzz.distance import JaroWinkler as _RFJaroWinkler

    def jaro_winkler_similarity(s1: str, s2: str, p: float = 0.1, max_l: int = 4) -> float:
        """Compute Jaro-Winkler similarity ratio using RapidFuzz if available."""
        return float(
            _RFJaroWinkler.similarity(s1.lower().strip(), s2.lower().strip(), prefix_weight=p)
        )

except ImportError:

    def _jaro_similarity(s1: str, s2: str) -> float:
        """Compute standard Jaro string similarity between two strings."""
        s1 = s1.lower().strip()
        s2 = s2.lower().strip()
        if s1 == s2:
            return 1.0
        len1, len2 = len(s1), len(s2)
        if len1 == 0 or len2 == 0:
            return 0.0

        match_distance = max(len1, len2) // 2 - 1
        s1_matches = [False] * len1
        s2_matches = [False] * len2
        matches = 0
        transpositions = 0

        for i in range(len1):
            start = max(0, i - match_distance)
            end = min(i + match_distance + 1, len2)
            for j in range(start, end):
                if s2_matches[j]:
                    continue
                if s1[i] != s2[j]:
                    continue
                s1_matches[i] = True
                s2_matches[j] = True
                matches += 1
                break

        if matches == 0:
            return 0.0

        k = 0
        for i in range(len1):
            if not s1_matches[i]:
                continue
            while not s2_matches[k]:
                k += 1
            if s1[i] != s2[k]:
                transpositions += 1
            k += 1

        t = transpositions / 2.0
        return (matches / len1 + matches / len2 + (matches - t) / matches) / 3.0

    def jaro_winkler_similarity(s1: str, s2: str, p: float = 0.1, max_l: int = 4) -> float:
        """Compute Jaro-Winkler similarity with prefix bonus."""
        s1 = s1.lower().strip()
        s2 = s2.lower().strip()
        j = _jaro_similarity(s1, s2)
        prefix_len = 0
        for c1, c2 in zip(s1, s2, strict=False):
            if c1 == c2:
                prefix_len += 1
                if prefix_len == max_l:
                    break
            else:
                break
        return j + prefix_len * p * (1.0 - j)


def string_similarity(a: str, b: str) -> float:
    """Compute normalized similarity ratio between two strings [0.0, 1.0]."""
    jw = jaro_winkler_similarity(a, b)
    sm = SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()
    return max(jw, sm)


# Connector and filler words that must never be treated as a player name: "vs" alone would
# substring-match "VS Wategaonkar", "in"/"the" match dozens of names, and so on.
PLAYER_QUERY_STOPWORDS = {
    "vs",
    "v",
    "against",
    "versus",
    "in",
    "the",
    "at",
    "on",
    "for",
    "of",
    "and",
    "or",
    "to",
    "by",
    "with",
    "during",
    "over",
    "overs",
    "match",
    "matches",
    "innings",
    "record",
    "stats",
    "how",
    "what",
    "who",
    "when",
    "does",
    "did",
    "his",
    "her",
    "their",
    "this",
    "that",
    "show",
    "plot",
    "plots",
    "chart",
    "charts",
    "graph",
    "graphs",
    "bar",
    "bars",
    "line",
    "lines",
    "column",
    "columns",
    "scatter",
    "heatmap",
    "area",
    "stacked",
    "grouped",
    "trend",
    "trends",
    "multiple",
    "has",
    "have",
    "had",
    "was",
    "were",
    "are",
    "been",
    "can",
    "could",
    "would",
    "should",
    "must",
    "not",
    "but",
    "all",
    "any",
    "its",
    "you",
    "your",
    "they",
    "them",
    "him",
    "she",
    "our",
    "than",
    "then",
    "there",
    "where",
    "which",
    "while",
    "from",
    "into",
    "about",
    "just",
    "only",
    "very",
    "more",
    "less",
    "many",
    "much",
    "some",
    "such",
    "each",
    "every",
    "both",
    "between",
    "after",
    "before",
    "under",
    "bowling",
    "batting",
    "fielding",
    "bowled",
    "batted",
}

MIN_PLAYER_PHRASE_CHARS = 3

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

# Curated cricket player nicknames and variations
CRICKET_PLAYER_NICKNAMES: dict[str, str] = {
    "virat": "Virat Kohli",
    "king kohli": "Virat Kohli",
    "cheeku": "Virat Kohli",
    "chiku": "Virat Kohli",
    "run machine": "Virat Kohli",
    "rohit": "Rohit Sharma",
    "hitman": "Rohit Sharma",
    "sharmaji": "Rohit Sharma",
    "bumrah": "Jasprit Bumrah",
    "boom boom": "Jasprit Bumrah",
    "jassi": "Jasprit Bumrah",
    "thala": "MS Dhoni",
    "mahi": "MS Dhoni",
    "msd": "MS Dhoni",
    "captain cool": "MS Dhoni",
    "sachin": "Sachin Tendulkar",
    "master blaster": "Sachin Tendulkar",
    "god of cricket": "Sachin Tendulkar",
    "sky": "Suryakumar Yadav",
    "surya": "Suryakumar Yadav",
    "mr 360": "AB de Villiers",
    "abd": "AB de Villiers",
    "bhuvi": "Bhuvneshwar Kumar",
    "jaddu": "Ravindra Jadeja",
    "ash": "Ravichandran Ashwin",
    "ashwin": "Ravichandran Ashwin",
    "kl": "KL Rahul",
    "klr": "KL Rahul",
    "shikhar": "Shikhar Dhawan",
    "gabbar": "Shikhar Dhawan",
    "dada": "Sourav Ganguly",
    "yuvi": "Yuvraj Singh",
    "raina": "Suresh Raina",
    "chahal": "Yuzvendra Chahal",
    "kuldeep": "Kuldeep Yadav",
    "hardik": "Hardik Pandya",
    "pant": "Rishabh Pant",
    "shami": "Mohammed Shami",
    "siraj": "Mohammed Siraj",
    "warner": "David Warner",
    "smith": "Steven Smith",
    "steve smith": "Steven Smith",
    "starc": "Mitchell Starc",
    "cummins": "Pat Cummins",
    "hazlewood": "Josh Hazlewood",
    "maxi": "Glenn Maxwell",
    "maxwell": "Glenn Maxwell",
    "zampa": "Adam Zampa",
    "root": "Joe Root",
    "stokes": "Ben Stokes",
    "buttler": "Jos Buttler",
    "bairstow": "Jonny Bairstow",
    "anderson": "James Anderson",
    "jimmy": "James Anderson",
    "broad": "Stuart Broad",
    "archer": "Jofra Archer",
    "babar": "Babar Azam",
    "rizwan": "Mohammad Rizwan",
    "shaheen": "Shaheen Shah Afridi",
    "shadab": "Shadab Khan",
    "kane": "Kane Williamson",
    "williamson": "Kane Williamson",
    "boult": "Trent Boult",
    "southee": "Tim Southee",
    "rashid": "Rashid Khan",
    "nortje": "Anrich Nortje",
    "rabada": "Kagiso Rabada",
    "de kock": "Quinton de Kock",
    "quinny": "Quinton de Kock",
    "miller": "David Miller",
    "killer miller": "David Miller",
}

# Curated cricket venue nicknames and short names
CRICKET_VENUE_NICKNAMES: dict[str, str] = {
    "chinnaswamy": "M Chinnaswamy Stadium",
    "m chinnaswamy": "M Chinnaswamy Stadium",
    "wankhede": "Wankhede Stadium",
    "eden gardens": "Eden Gardens",
    "eden": "Eden Gardens",
    "chepauk": "MA Chidambaram Stadium",
    "chidambaram": "MA Chidambaram Stadium",
    "motera": "Narendra Modi Stadium",
    "narendra modi stadium": "Narendra Modi Stadium",
    "kotla": "Arun Jaitley Stadium",
    "arun jaitley": "Arun Jaitley Stadium",
    "feroz shah kotla": "Arun Jaitley Stadium",
    "ferozeshah kotla": "Arun Jaitley Stadium",
    "dharamsala": "Himachal Pradesh Cricket Association Stadium",
    "hpca": "Himachal Pradesh Cricket Association Stadium",
    "mcg": "Melbourne Cricket Ground",
    "melbourne": "Melbourne Cricket Ground",
    "scg": "Sydney Cricket Ground",
    "sydney": "Sydney Cricket Ground",
    "gabba": "Brisbane Cricket Ground, Woolloongabba",
    "adelaide oval": "Adelaide Oval",
    "adelaide": "Adelaide Oval",
    "perth stadium": "Perth Stadium",
    "optus": "Perth Stadium",
    "waca": "W.A.C.A. Ground",
    "lords": "Lord's",
    "lord's": "Lord's",
    "oval": "Kennington Oval",
    "the oval": "The Oval",
    "edgbaston": "Edgbaston",
    "old trafford": "Old Trafford",
    "headingley": "Headingley",
    "trent bridge": "Trent Bridge",
    "rose bowl": "The Rose Bowl",
    "gaddafi": "Gaddafi Stadium",
    "national stadium karachi": "National Stadium",
    "rawalpindi": "Rawalpindi Cricket Stadium",
    "church street": "Church Street Park",
    "church street park": "Church Street Park",
}


def _tokenize(text: str) -> list[str]:
    """Split text into lowercase alphanumeric word tokens."""
    return [w.lower() for w in re.findall(r"\b\w+\b", text) if len(w) >= 2]


class EntityResolver:
    """Resolves natural language entities (players, teams, venues) into canonical database IDs.

    Uses an in-memory RapidFuzz / Jaro-Winkler similarity matcher backed by Cricsheet registries
    (`people.csv`, `names.csv`, `gold.dim_player`, `gold.dim_venue`).
    """

    def __init__(
        self,
        con: duckdb.DuckDBPyConnection | None = None,
        people_csv_path: str | Path | None = None,
        names_csv_path: str | Path | None = None,
    ):
        self.con = con
        self.people_csv_path = Path(people_csv_path) if people_csv_path else None
        self.names_csv_path = Path(names_csv_path) if names_csv_path else None

        # In-memory indices
        self._player_records: dict[str, dict] = {}  # player_id -> record
        self._exact_player_map: dict[str, str] = {}  # normalized text -> player_id
        self._player_token_map: dict[str, list[str]] = {}  # token -> list[player_id]

        self._venue_records: dict[str, dict] = {}  # venue_id -> record
        self._exact_venue_map: dict[str, str] = {}  # normalized text -> venue_id

        self._team_records: dict[str, dict] = {}  # team_id -> record
        self._exact_team_map: dict[str, str] = {}  # normalized text -> team_id

        self._initialize_registries()

    def _initialize_registries(self) -> None:
        """Load player, venue, and team data into in-memory indices."""
        # 1. Load from DuckDB if available
        if self.con:
            try:
                # Players
                players_res = self.con.execute(
                    """
                    SELECT p.player_id, p.full_name, p.unique_name, p.espncricinfo_id, p.cricbuzz_id,
                           COALESCE(COUNT(fpm.match_id), 0) AS appearance_count
                    FROM gold.dim_player p
                    LEFT JOIN gold.fact_player_match fpm ON fpm.player_id = p.player_id
                    GROUP BY p.player_id, p.full_name, p.unique_name, p.espncricinfo_id, p.cricbuzz_id;
                    """
                ).fetchall()
                for row in players_res:
                    pid, fname, uname, espn, cb, app_count = row
                    self._register_player(
                        player_id=pid,
                        full_name=fname,
                        unique_name=uname,
                        espncricinfo_id=espn,
                        cricbuzz_id=cb,
                        appearance_count=app_count,
                    )

                # Aliases
                aliases_res = self.con.execute(
                    "SELECT player_id, alias_name FROM gold.player_aliases WHERE alias_name IS NOT NULL;"
                ).fetchall()
                for pid, alias in aliases_res:
                    self._register_player_alias(pid, alias)

                # Venues
                venues_res = self.con.execute(
                    "SELECT venue_id, venue_name, city FROM gold.dim_venue;"
                ).fetchall()
                for vid, vname, vcity in venues_res:
                    self._register_venue(venue_id=vid, venue_name=vname, city=vcity)

                # Teams
                teams_res = self.con.execute(
                    "SELECT team_id, team_name FROM gold.dim_team;"
                ).fetchall()
                for tid, tname in teams_res:
                    self._register_team(team_id=tid, team_name=tname)
            except Exception as e:
                logger.debug("duckdb_tables_not_yet_materialized", error=str(e))

        # 2. Supplement from CSV registries if provided or fallback files exist
        p_csv = self.people_csv_path
        if not p_csv or not p_csv.exists():
            for candidate in (
                Path("tests/fixtures/sample_people.csv"),
                Path("data/raw/register_csv/people.csv"),
            ):
                if candidate.exists():
                    p_csv = candidate
                    break

        n_csv = self.names_csv_path
        if not n_csv or not n_csv.exists():
            for candidate in (
                Path("tests/fixtures/sample_names.csv"),
                Path("data/raw/register_csv/names.csv"),
            ):
                if candidate.exists():
                    n_csv = candidate
                    break

        if p_csv and p_csv.exists():
            self._load_people_csv(p_csv)
        if n_csv and n_csv.exists():
            self._load_names_csv(n_csv)

        # 3. Register canonical star players if not already loaded from CSV/DuckDB
        default_players = [
            (
                "740742ef",
                "RG Sharma",
                "RG Sharma",
                "34102",
                "107",
                ["Rohit Sharma", "RG Sharma", "R Sharma"],
            ),
            (
                "462411b3",
                "JJ Bumrah",
                "JJ Bumrah",
                "625383",
                "1124",
                ["Jasprit Bumrah", "JJ Bumrah", "J Bumrah"],
            ),
            (
                "483b8b64",
                "Virat Kohli",
                "Virat Kohli",
                "253802",
                "1413",
                ["V Kohli", "Virat Kohli"],
            ),
            (
                "34958614",
                "MS Dhoni",
                "MS Dhoni",
                "28081",
                "265",
                ["MS Dhoni", "Mahendra Singh Dhoni"],
            ),
        ]
        for pid, fname, uname, espn, cb, aliases in default_players:
            if pid not in self._player_records:
                self._register_player(pid, fname, uname, espn, cb)
                for al in aliases:
                    self._register_player_alias(pid, al)

        # 4. Register default venues if not already loaded from DuckDB
        default_venues = [
            ("9fae8291e2d16b83aefe89f0bd1b78e8", "M Chinnaswamy Stadium, Bangalore", "Bengaluru"),
            ("ec4347c0be2692e078e409f3076a61e6", "Church Street Park, Morrisville", "Morrisville"),
            ("wankhede_mumbai", "Wankhede Stadium, Mumbai", "Mumbai"),
            ("eden_gardens_kolkata", "Eden Gardens, Kolkata", "Kolkata"),
            ("chepauk_chennai", "MA Chidambaram Stadium, Chepauk, Chennai", "Chennai"),
            ("narendra_modi_ahmedabad", "Narendra Modi Stadium, Ahmedabad", "Ahmedabad"),
            ("mcg_melbourne", "Melbourne Cricket Ground", "Melbourne"),
            ("scg_sydney", "Sydney Cricket Ground", "Sydney"),
        ]
        for vid, vname, vcity in default_venues:
            if vid not in self._venue_records:
                self._register_venue(vid, vname, vcity)

        # 5. Register Nickname shortcuts
        for nickname, target in CRICKET_PLAYER_NICKNAMES.items():
            norm_nick = nickname.lower().strip()
            # If target resolves to an existing player, map nickname directly
            norm_target = target.lower().strip()
            if norm_target in self._exact_player_map:
                self._exact_player_map[norm_nick] = self._exact_player_map[norm_target]

    def _register_player(
        self,
        player_id: str,
        full_name: str,
        unique_name: str | None = None,
        espncricinfo_id: str | None = None,
        cricbuzz_id: str | None = None,
        appearance_count: int = 0,
    ) -> None:
        rec = self._player_records.get(player_id)
        if not rec:
            rec = {
                "player_id": player_id,
                "full_name": full_name,
                "unique_name": unique_name or full_name,
                "espncricinfo_id": espncricinfo_id,
                "cricbuzz_id": cricbuzz_id,
                "aliases": set(),
                "tokens": set(),
                "appearance_count": appearance_count,
            }
            self._player_records[player_id] = rec
        else:
            if appearance_count > rec["appearance_count"]:
                rec["appearance_count"] = appearance_count

        norm_full = full_name.lower().strip()
        self._exact_player_map[norm_full] = player_id
        for t in _tokenize(norm_full):
            rec["tokens"].add(t)
            self._player_token_map.setdefault(t, []).append(player_id)

        if unique_name:
            norm_unique = unique_name.lower().strip()
            self._exact_player_map[norm_unique] = player_id
            for t in _tokenize(norm_unique):
                rec["tokens"].add(t)
                if player_id not in self._player_token_map.get(t, []):
                    self._player_token_map.setdefault(t, []).append(player_id)

    def _register_player_alias(self, player_id: str, alias_name: str) -> None:
        norm_alias = alias_name.lower().strip()
        self._exact_player_map[norm_alias] = player_id
        rec = self._player_records.get(player_id)
        if rec:
            rec["aliases"].add(alias_name)
            for t in _tokenize(norm_alias):
                rec["tokens"].add(t)
                if player_id not in self._player_token_map.get(t, []):
                    self._player_token_map.setdefault(t, []).append(player_id)

    def _register_venue(self, venue_id: str, venue_name: str, city: str | None = None) -> None:
        self._venue_records[venue_id] = {
            "venue_id": venue_id,
            "venue_name": venue_name,
            "city": city,
            "tokens": set(_tokenize(venue_name) + (_tokenize(city) if city else [])),
        }
        self._exact_venue_map[venue_name.lower().strip()] = venue_id
        if city:
            self._exact_venue_map[city.lower().strip()] = venue_id

    def _register_team(self, team_id: str, team_name: str) -> None:
        self._team_records[team_id] = {"team_id": team_id, "team_name": team_name}
        self._exact_team_map[team_name.lower().strip()] = team_id

    def _load_people_csv(self, path: Path) -> None:
        try:
            with open(path, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    pid = row.get("identifier")
                    name = row.get("name")
                    if not pid or not name:
                        continue
                    uname = row.get("unique_name") or name
                    espn = row.get("key_cricinfo")
                    cb = row.get("key_cricbuzz")
                    self._register_player(
                        player_id=pid,
                        full_name=name,
                        unique_name=uname,
                        espncricinfo_id=espn,
                        cricbuzz_id=cb,
                    )
        except Exception as e:
            logger.warning("failed_reading_people_csv", path=str(path), error=str(e))

    def _load_names_csv(self, path: Path) -> None:
        try:
            with open(path, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    pid = row.get("identifier")
                    alias = row.get("name")
                    if pid and alias:
                        self._register_player_alias(pid, alias)
        except Exception as e:
            logger.warning("failed_reading_names_csv", path=str(path), error=str(e))

    def resolve_player(self, search_name: str) -> ResolvedPlayer | None:
        """Resolve a player name across exact names, aliases, nicknames, and RapidFuzz / Jaro-Winkler."""
        cleaned = search_name.strip()
        if not cleaned:
            return None
        norm = cleaned.lower()

        # 0. Check Nickname Dictionary
        target_name = CRICKET_PLAYER_NICKNAMES.get(norm)
        if target_name:
            target_norm = target_name.lower()
            if target_norm in self._exact_player_map:
                pid = self._exact_player_map[target_norm]
                rec = self._player_records[pid]
                return ResolvedPlayer(
                    player_id=rec["player_id"],
                    full_name=rec["full_name"],
                    unique_name=rec["unique_name"],
                    espncricinfo_id=rec["espncricinfo_id"],
                    cricbuzz_id=rec["cricbuzz_id"],
                    match_score=0.98,
                )

        # 1. Exact Match on in-memory map (full_name, unique_name, alias)
        if norm in self._exact_player_map:
            pid = self._exact_player_map[norm]
            rec = self._player_records[pid]
            return ResolvedPlayer(
                player_id=rec["player_id"],
                full_name=rec["full_name"],
                unique_name=rec["unique_name"],
                espncricinfo_id=rec["espncricinfo_id"],
                cricbuzz_id=rec["cricbuzz_id"],
                match_score=1.0,
            )

        # 2. Database exact / alias lookup if connected
        if self.con:
            query_exact = """
                SELECT player_id, full_name, unique_name, espncricinfo_id, cricbuzz_id
                FROM gold.dim_player
                WHERE LOWER(full_name) = LOWER(?) OR LOWER(unique_name) = LOWER(?)
                LIMIT 1;
            """
            try:
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
            except Exception:
                pass

        # 3. Whole-word / Token-level Match (e.g. "Kohli" -> "V Kohli", "de Kock" -> "Q de Kock", "Bumrah" -> "JJ Bumrah")
        query_tokens = _tokenize(norm)
        if query_tokens:
            # Check candidate players who contain these tokens
            candidate_pids: dict[str, int] = {}
            for t in query_tokens:
                for pid in self._player_token_map.get(t, []):
                    candidate_pids[pid] = candidate_pids.get(pid, 0) + 1

            if candidate_pids:
                # If multi-word, candidate must match all content tokens
                valid_candidates = {
                    pid: count
                    for pid, count in candidate_pids.items()
                    if len(query_tokens) == 1 or count == len(query_tokens)
                }
                if valid_candidates:
                    sorted_candidates = sorted(
                        valid_candidates.keys(),
                        key=lambda p: (
                            valid_candidates[p],
                            self._player_records[p]["appearance_count"],
                        ),
                        reverse=True,
                    )
                    best_pid = sorted_candidates[0]
                    rec = self._player_records[best_pid]
                    return ResolvedPlayer(
                        player_id=rec["player_id"],
                        full_name=rec["full_name"],
                        unique_name=rec["unique_name"],
                        espncricinfo_id=rec["espncricinfo_id"],
                        cricbuzz_id=rec["cricbuzz_id"],
                        match_score=0.90
                        if valid_candidates[best_pid] == len(query_tokens)
                        else 0.85,
                    )

        # 4. Database whole-word match fallback
        if self.con:
            query_sub = """
                SELECT p.player_id, p.full_name, p.unique_name, p.espncricinfo_id, p.cricbuzz_id
                FROM gold.dim_player p
                LEFT JOIN gold.fact_player_match fpm ON fpm.player_id = p.player_id
                WHERE ' ' || LOWER(p.full_name) || ' ' LIKE '% ' || LOWER(?) || ' %'
                   OR ' ' || LOWER(p.unique_name) || ' ' LIKE '% ' || LOWER(?) || ' %'
                GROUP BY p.player_id, p.full_name, p.unique_name, p.espncricinfo_id, p.cricbuzz_id
                ORDER BY COUNT(fpm.match_id) DESC
                LIMIT 1;
            """
            try:
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
            except Exception:
                pass

        # 5. In-Memory Jaro-Winkler Similarity Matcher
        best_match_rec = None
        best_score = 0.0

        for rec in self._player_records.values():
            # Check full_name, unique_name, and aliases
            scores = [
                jaro_winkler_similarity(norm, rec["full_name"]),
                jaro_winkler_similarity(norm, rec["unique_name"]),
            ]
            for al in rec["aliases"]:
                scores.append(jaro_winkler_similarity(norm, al))

            # Token-level similarity check
            for t in rec["tokens"]:
                scores.append(jaro_winkler_similarity(norm, t))

            max_s = max(scores) if scores else 0.0
            if max_s > best_score and max_s >= 0.70:
                best_score = max_s
                best_match_rec = rec

        if best_match_rec:
            return ResolvedPlayer(
                player_id=best_match_rec["player_id"],
                full_name=best_match_rec["full_name"],
                unique_name=best_match_rec["unique_name"],
                espncricinfo_id=best_match_rec["espncricinfo_id"],
                cricbuzz_id=best_match_rec["cricbuzz_id"],
                match_score=round(best_score, 2),
            )

        return None

    def resolve_team(self, search_team: str) -> ResolvedTeam | None:
        """Resolve a team name or abbreviation to canonical team_name in gold.dim_team."""
        cleaned = search_team.strip()
        if not cleaned:
            return None
        norm = cleaned.lower()

        # Check common acronyms/aliases
        target_name = COMMON_TEAM_ALIASES.get(norm, cleaned)
        norm_target = target_name.lower()

        # Exact match in memory
        if norm_target in self._exact_team_map:
            tid = self._exact_team_map[norm_target]
            rec = self._team_records[tid]
            return ResolvedTeam(team_id=rec["team_id"], team_name=rec["team_name"], match_score=1.0)

        # Database lookup if connected
        if self.con:
            try:
                row = self.con.execute(
                    "SELECT team_id, team_name FROM gold.dim_team WHERE LOWER(team_name) = LOWER(?) LIMIT 1;",
                    [target_name],
                ).fetchone()
                if row:
                    return ResolvedTeam(team_id=row[0], team_name=row[1], match_score=1.0)

                row = self.con.execute(
                    "SELECT team_id, team_name FROM gold.dim_team WHERE LOWER(team_name) LIKE '%' || LOWER(?) || '%' LIMIT 1;",
                    [target_name],
                ).fetchone()
                if row:
                    return ResolvedTeam(team_id=row[0], team_name=row[1], match_score=0.9)
            except Exception:
                pass

        # Substring / Jaro-Winkler match across in-memory teams
        best_team = None
        best_score = 0.0
        for rec in self._team_records.values():
            t_name = rec["team_name"].lower()
            if norm_target in t_name or t_name in norm_target:
                return ResolvedTeam(
                    team_id=rec["team_id"], team_name=rec["team_name"], match_score=0.9
                )
            score = jaro_winkler_similarity(norm_target, t_name)
            if score > best_score and score >= 0.75:
                best_score = score
                best_team = rec

        if best_team:
            return ResolvedTeam(
                team_id=best_team["team_id"],
                team_name=best_team["team_name"],
                match_score=round(best_score, 2),
            )

        return None

    def resolve_venue(self, search_venue: str) -> ResolvedVenue | None:
        """Resolve a stadium/venue name or nickname to canonical venue in gold.dim_venue."""
        cleaned = search_venue.strip()
        if not cleaned:
            return None
        norm = cleaned.lower()

        # 0. Check Venue Nicknames
        target_name = CRICKET_VENUE_NICKNAMES.get(norm, cleaned)
        norm_target = target_name.lower()

        # 1. Exact match in memory
        if norm_target in self._exact_venue_map:
            vid = self._exact_venue_map[norm_target]
            rec = self._venue_records[vid]
            return ResolvedVenue(
                venue_id=rec["venue_id"],
                venue_name=rec["venue_name"],
                city=rec["city"],
                match_score=1.0,
            )

        # 2. Database lookup if connected
        if self.con:
            try:
                row = self.con.execute(
                    """
                    SELECT venue_id, venue_name, city
                    FROM gold.dim_venue
                    WHERE LOWER(venue_name) LIKE '%' || LOWER(?) || '%'
                       OR (city IS NOT NULL AND LOWER(city) = LOWER(?))
                    LIMIT 1;
                    """,
                    [target_name, target_name],
                ).fetchone()
                if row:
                    return ResolvedVenue(
                        venue_id=row[0], venue_name=row[1], city=row[2], match_score=1.0
                    )
            except Exception:
                pass

        # 3. Substring & Jaro-Winkler fuzzy match across in-memory venues
        v_tokens = _tokenize(norm_target)
        best_venue = None
        best_score = 0.0
        for rec in self._venue_records.values():
            v_name = rec["venue_name"].lower()
            v_city = (rec["city"] or "").lower()

            if len(v_tokens) > 1:
                # For multi-word phrase, require substring match in venue/city or all tokens in venue
                if norm_target in v_name or (v_city and norm_target in v_city):
                    return ResolvedVenue(
                        venue_id=rec["venue_id"],
                        venue_name=rec["venue_name"],
                        city=rec["city"],
                        match_score=0.95,
                    )
                if all(t in rec["tokens"] for t in v_tokens):
                    return ResolvedVenue(
                        venue_id=rec["venue_id"],
                        venue_name=rec["venue_name"],
                        city=rec["city"],
                        match_score=0.90,
                    )
                continue

            # Substring match for single word
            if norm_target in v_name or (v_city and norm_target in v_city):
                return ResolvedVenue(
                    venue_id=rec["venue_id"],
                    venue_name=rec["venue_name"],
                    city=rec["city"],
                    match_score=0.95,
                )

            # Jaro-Winkler similarity on venue_name, city, and tokens
            score = max(
                jaro_winkler_similarity(norm_target, v_name),
                jaro_winkler_similarity(norm_target, v_city) if v_city else 0.0,
            )
            for t in rec["tokens"]:
                t_score = jaro_winkler_similarity(norm_target, t)
                if t_score > score:
                    score = t_score

            if score > best_score and score >= 0.75:
                best_score = score
                best_venue = rec

        if best_venue:
            return ResolvedVenue(
                venue_id=best_venue["venue_id"],
                venue_name=best_venue["venue_name"],
                city=best_venue["city"],
                match_score=round(best_score, 2),
            )

        return None

    def resolve_all_from_query(self, user_query: str) -> ResolvedEntities:
        """Extract and resolve entities (teams, venues, players) from unstructured query text."""
        entities = ResolvedEntities()
        words = [w for w in user_query.split() if w.lower() not in PLAYER_QUERY_STOPWORDS]
        claimed: set[int] = set()

        # 1. Resolve Teams (e.g. "CSK", "India", "RCB")
        for i, word in enumerate(words):
            team = self.resolve_team(word)
            if team and not any(t.team_id == team.team_id for t in entities.teams):
                entities.teams.append(team)
                claimed.add(i)

        # 2. Resolve Venues (e.g. "Chinnaswamy", "Wankhede", "Church Street Park")
        for n in (3, 2, 1):
            for i in range(len(words) - n + 1):
                span = range(i, i + n)
                if any(idx in claimed for idx in span):
                    continue
                phrase = " ".join(words[i : i + n])
                if len(phrase.replace(" ", "")) < MIN_PLAYER_PHRASE_CHARS:
                    continue
                venue = self.resolve_venue(phrase)
                if (
                    venue
                    and venue.match_score >= 0.80
                    and not any(v.venue_id == venue.venue_id for v in entities.venues)
                ):
                    entities.venues.append(venue)
                    claimed.update(span)

        # 3. Resolve Players (3-word, 2-word, then single-word names/nicknames)
        for n in (3, 2, 1):
            for i in range(len(words) - n + 1):
                span = range(i, i + n)
                if any(idx in claimed for idx in span):
                    continue
                phrase = " ".join(words[i : i + n])
                if len(phrase.replace(" ", "")) < MIN_PLAYER_PHRASE_CHARS:
                    continue
                player = self.resolve_player(phrase)
                if (
                    player
                    and player.match_score >= 0.80
                    and not any(p.player_id == player.player_id for p in entities.players)
                ):
                    entities.players.append(player)
                    claimed.update(span)

        return entities
