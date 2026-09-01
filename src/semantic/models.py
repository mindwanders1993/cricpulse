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


class ResolvedPlayer(BaseModel):
    """Resolved player entity with canonical and external IDs."""

    player_id: str
    full_name: str
    unique_name: str | None = None
    espncricinfo_id: str | None = None
    cricbuzz_id: str | None = None
    match_score: float = 1.0  # 1.0 = exact match, < 1.0 = fuzzy match


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
