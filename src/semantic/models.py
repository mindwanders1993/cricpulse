from typing import Any

from pydantic import BaseModel, Field


class MetricDefinition(BaseModel):
    """Canonical business metric definition for cricket calculations."""

    name: str
    description: str
    formula: str
    unit: str = "number"
    required_grain: list[str] = Field(default_factory=list)
    default_sort: str = "DESC"


class DimensionDefinition(BaseModel):
    """Dimension description and allowed enum values."""

    name: str
    description: str
    allowed_values: list[str | dict[str, str]] | None = None
    bowler_credited: list[str] | None = None
    non_bowler_credited: list[str] | None = None


class SemanticCatalogModel(BaseModel):
    """Top-level semantic catalog schema."""

    version: str
    domain: str
    description: str
    metrics: dict[str, MetricDefinition]
    dimensions: dict[str, DimensionDefinition] = Field(default_factory=dict)
    semantic_tools: dict[str, Any] = Field(default_factory=dict)


class ResolvedPlayer(BaseModel):
    """Resolved player entity with canonical and external IDs."""

    player_id: str
    full_name: str
    unique_name: str | None = None
    espncricinfo_id: str | None = None
    cricbuzz_id: str | None = None
    match_score: float = 1.0  # 1.0 = exact match, < 1.0 = fuzzy match

    @property
    def player_uid(self) -> str:
        return self.player_id


class ResolvedTeam(BaseModel):
    """Resolved team entity."""

    team_id: str
    team_name: str
    match_score: float = 1.0


class ResolvedVenue(BaseModel):
    """Resolved venue entity."""

    venue_id: str
    venue_name: str
    city: str | None = None
    match_score: float = 1.0


class ResolvedEntities(BaseModel):
    """Aggregated resolved entities for a natural language query."""

    players: list[ResolvedPlayer] = Field(default_factory=list)
    teams: list[ResolvedTeam] = Field(default_factory=list)
    venues: list[ResolvedVenue] = Field(default_factory=list)


class GoldenQuery(BaseModel):
    """Curated Golden SQL query pattern for LLM in-context learning."""

    title: str
    category: str  # e.g., "batting", "bowling", "matchup", "clutch", "head_to_head"
    question: str
    sql: str
    keywords: list[str]


class BattingPhaseSplit(BaseModel):
    """Batting statistics aggregated for a specific match phase."""

    phase: str
    matches: int = 0
    innings: int = 0
    runs: int = 0
    balls_faced: int = 0
    dismissals: int = 0
    strike_rate: float = 0.0
    batting_average: float | None = None
    dot_balls: int = 0
    dot_ball_pct: float = 0.0
    fours: int = 0
    sixes: int = 0
    boundary_run_pct: float = 0.0


class BowlingPhaseSplit(BaseModel):
    """Bowling statistics aggregated for a specific match phase."""

    phase: str
    matches: int = 0
    legal_balls: int = 0
    overs: float = 0.0
    runs_conceded: int = 0
    wickets: int = 0
    economy: float = 0.0
    bowling_average: float | None = None
    bowling_strike_rate: float | None = None
    dot_balls: int = 0
    dot_ball_pct: float = 0.0


class PlayerPhaseSplitReport(BaseModel):
    """Comprehensive phase split report for a player."""

    player_id: str
    player_name: str
    format: str
    phase: str | None = None
    batting: list[BattingPhaseSplit] = Field(default_factory=list)
    bowling: list[BowlingPhaseSplit] = Field(default_factory=list)


class HeadToHeadMatchup(BaseModel):
    """Head-to-head record between a batter and bowler."""

    batter_id: str
    batter_name: str
    bowler_id: str
    bowler_name: str
    format: str
    balls_faced: int = 0
    runs_scored: int = 0
    dismissals: int = 0
    strike_rate: float = 0.0
    batting_average: float | None = None
    dot_balls: int = 0
    dot_ball_pct: float = 0.0
    fours: int = 0
    sixes: int = 0
    boundary_pct: float = 0.0
    phase_breakdown: list[dict[str, Any]] = Field(default_factory=list)


class VenuePhaseAndTossProfile(BaseModel):
    """Comprehensive historical toss and phase profile for a venue."""

    venue_id: str
    venue_name: str
    city: str | None = None
    format: str
    total_matches: int = 0
    toss_decision: dict[str, int] = Field(default_factory=dict)
    match_outcomes: dict[str, Any] = Field(default_factory=dict)
    average_first_innings_score: float | None = None
    average_second_innings_score: float | None = None
    phase_stats: list[dict[str, Any]] = Field(default_factory=list)
