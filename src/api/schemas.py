from typing import Any

from pydantic import BaseModel, Field


class AIQueryRequest(BaseModel):
    """Natural language question for Text-to-SQL execution."""

    query: str = Field(
        ...,
        description="Natural language analytical question about cricket",
        examples=["Who has the highest strike rate in death overs?"],
    )
    include_chart: bool = Field(
        default=True, description="Whether to include a synthesized Vega-Lite chart spec"
    )
    session_id: str | None = Field(default=None, description="Optional client session identifier")


class AIQueryResponse(BaseModel):
    """Result of an AI Text-to-SQL query execution."""

    status: str = "success"
    query: str
    insight: str
    sql_executed: str
    rows: list[dict[str, Any]]
    chart_spec: dict[str, Any] | None = None


class AIScoutRequest(BaseModel):
    """Tactical player matchup scouting request."""

    batter_name: str = Field(
        ..., description="Batter display name or canonical name", examples=["Virat Kohli"]
    )
    bowler_name: str | None = Field(
        default=None, description="Opposing bowler display name", examples=["Adam Zampa"]
    )
    bowling_style: str | None = Field(
        default=None, description="Bowling profile (e.g. 'left-arm fast')"
    )
    phase: str | None = Field(
        default=None, description="Match phase: 'powerplay', 'middle', 'death'"
    )
    match_type: str = Field(default="T20", description="Match format: 'T20', 'ODI', 'Test'")


class AIScoutResponse(BaseModel):
    """Tactical scouting report and metrics."""

    status: str = "success"
    batter: str
    bowler: str
    phase: str
    match_type: str
    metrics: dict[str, Any]
    tactical_report: str


class LeaderboardEntry(BaseModel):
    """Leaderboard entry record."""

    rank: int
    player_id: str
    player_name: str
    metrics: dict[str, Any]


class LeaderboardResponse(BaseModel):
    """Paginated leaderboard response."""

    status: str = "success"
    category: str
    match_type: str
    season: str | None = None
    count: int
    offset: int
    limit: int
    data: list[dict[str, Any]]


class HealthResponse(BaseModel):
    """Service health and readiness status."""

    status: str = "healthy"
    version: str = "0.1.0"
    database_connected: bool = True
    tables_count: int = 0


class SyncDailyResponse(BaseModel):
    """Response for internal scheduled synchronization webhook."""

    status: str = "success"
    message: str = "Daily sync completed successfully"
    matches_downloaded: int = 0
    matches_ingested: int = 0
    snapshot_published: str | None = None
    duration_seconds: float = 0.0


class AIStoryRequest(BaseModel):
    """Request to generate narrative match recap and turning points."""

    match_id: str = Field(..., description="Canonical match identifier", examples=["1384400"])
    focus: str | None = Field(
        default=None,
        description="Optional editorial angle, e.g. 'clutch death overs', 'turning point', 'bowler spell'",
    )
    include_chart: bool = Field(
        default=True, description="Whether to include a Vega-Lite momentum chart"
    )


class AIStoryResponse(BaseModel):
    """Editorial match recap and momentum analytics."""

    status: str = "success"
    match_id: str
    headline: str
    editorial_recap: str
    turning_points: list[dict[str, Any]] = Field(default_factory=list)
    key_performers: list[dict[str, Any]] = Field(default_factory=list)
    chart_spec: dict[str, Any] | None = None


class AIChatRequest(BaseModel):
    """Unified conversational request routed dynamically across specialist agents."""

    message: str = Field(
        ...,
        description="Natural language cricket question, matchup query, or match recap request",
        examples=[
            "Who scored the most runs in death overs?",
            "Kohli vs Bumrah",
            "Recap match 1384400",
        ],
    )
    session_id: str | None = Field(default=None, description="Optional client session identifier")
    include_chart: bool = Field(default=True, description="Include Vega-Lite visualization")


class AIChatResponse(BaseModel):
    """Unified conversational response routed from specialist multi-agents."""

    status: str = "success"
    intent: str  # 'analytical_sql', 'tactical_scout', 'narrative_story', or 'general'
    routed_agent: str
    reply: str
    data: dict[str, Any] | list[dict[str, Any]] | None = None
    sql_executed: str | None = None
    chart_spec: dict[str, Any] | None = None
