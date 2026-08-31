"""DuckDB Star Schema DDL contracts and Mart definitions for CricPulse."""

INIT_SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS gold;

-- ==========================================
-- DIMENSIONS
-- ==========================================

CREATE TABLE IF NOT EXISTS gold.dim_player (
    player_id         VARCHAR PRIMARY KEY,
    full_name         VARCHAR NOT NULL,
    unique_name       VARCHAR NOT NULL,
    espncricinfo_id   VARCHAR,
    cricbuzz_id       VARCHAR,
    bcci_id           VARCHAR,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS gold.player_aliases (
    player_id         VARCHAR NOT NULL,
    alias_name        VARCHAR NOT NULL,
    PRIMARY KEY (player_id, alias_name)
);

CREATE TABLE IF NOT EXISTS gold.player_identifiers (
    player_id         VARCHAR NOT NULL,
    key_source        VARCHAR NOT NULL,
    key_value         VARCHAR NOT NULL,
    PRIMARY KEY (player_id, key_source, key_value)
);

CREATE TABLE IF NOT EXISTS gold.dim_venue (
    venue_id          VARCHAR PRIMARY KEY,
    venue_name        VARCHAR NOT NULL,
    city              VARCHAR,
    country           VARCHAR
);

CREATE TABLE IF NOT EXISTS gold.dim_team (
    team_id           VARCHAR PRIMARY KEY,
    team_name         VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS gold.dim_match (
    match_id          VARCHAR PRIMARY KEY,
    match_date        DATE NOT NULL,
    match_type        VARCHAR NOT NULL,
    gender            VARCHAR NOT NULL,
    season            VARCHAR NOT NULL,
    venue_name        VARCHAR NOT NULL,
    city              VARCHAR,
    team1             VARCHAR NOT NULL,
    team2             VARCHAR NOT NULL,
    toss_winner       VARCHAR,
    toss_decision     VARCHAR,
    winner            VARCHAR,
    result_type       VARCHAR NOT NULL,
    win_by_runs       INTEGER,
    win_by_wickets    INTEGER,
    player_of_match   VARCHAR,
    player_of_match_id VARCHAR,
    is_dls_applied    BOOLEAN DEFAULT FALSE,
    overs_limit       INTEGER,
    revision          INTEGER DEFAULT 1
);

-- ==========================================
-- FACTS
-- ==========================================

CREATE TABLE IF NOT EXISTS gold.fact_delivery (
    delivery_id       VARCHAR PRIMARY KEY,
    match_id          VARCHAR NOT NULL,
    innings_number    INTEGER NOT NULL,
    over_number       INTEGER NOT NULL,
    delivery_number   INTEGER NOT NULL,
    phase             VARCHAR NOT NULL,
    batter_id         VARCHAR NOT NULL,
    batter_name       VARCHAR NOT NULL,
    bowler_id         VARCHAR NOT NULL,
    bowler_name       VARCHAR NOT NULL,
    non_striker_id    VARCHAR NOT NULL,
    non_striker_name  VARCHAR NOT NULL,
    runs_batter       INTEGER NOT NULL,
    runs_extras       INTEGER NOT NULL,
    total_runs        INTEGER NOT NULL,
    is_dot_ball       BOOLEAN NOT NULL,
    is_boundary_four  BOOLEAN NOT NULL,
    is_boundary_six   BOOLEAN NOT NULL,
    is_wide           BOOLEAN NOT NULL,
    is_no_ball        BOOLEAN NOT NULL,
    is_bye            BOOLEAN NOT NULL,
    is_leg_bye        BOOLEAN NOT NULL,
    is_wicket         BOOLEAN NOT NULL,
    dismissal_kind    VARCHAR,
    player_out_id     VARCHAR,
    player_out_name   VARCHAR
);

CREATE TABLE IF NOT EXISTS gold.fact_innings (
    match_id          VARCHAR NOT NULL,
    innings_number    INTEGER NOT NULL,
    batting_team      VARCHAR NOT NULL,
    total_runs        INTEGER NOT NULL,
    total_wickets     INTEGER NOT NULL,
    total_deliveries  INTEGER NOT NULL,
    PRIMARY KEY (match_id, innings_number)
);

CREATE TABLE IF NOT EXISTS gold.fact_wicket_detail (
    delivery_id       VARCHAR NOT NULL,
    match_id          VARCHAR NOT NULL,
    innings_number    INTEGER NOT NULL,
    over_number       INTEGER NOT NULL,
    delivery_number   INTEGER NOT NULL,
    player_out_id     VARCHAR NOT NULL,
    player_out_name   VARCHAR NOT NULL,
    dismissal_kind    VARCHAR NOT NULL,
    bowler_id         VARCHAR,
    bowler_name       VARCHAR,
    fielders          VARCHAR
);

CREATE TABLE IF NOT EXISTS gold.fact_player_match (
    match_id          VARCHAR NOT NULL,
    team_name         VARCHAR NOT NULL,
    player_id         VARCHAR NOT NULL,
    player_name       VARCHAR NOT NULL,
    PRIMARY KEY (match_id, player_id)
);
"""

BUILD_MARTS_SQL = """
-- ==========================================
-- AGGREGATION MARTS (AI-Ready & Instant Lookups)
-- ==========================================

-- 1. Batting Career Mart
CREATE OR REPLACE TABLE gold.mart_player_batting_career AS
SELECT 
    fd.batter_id AS player_id,
    fd.batter_name AS full_name,
    dm.match_type,
    COUNT(DISTINCT fd.match_id) AS matches_played,
    COUNT(DISTINCT (fd.match_id || '_' || fd.innings_number::VARCHAR)) AS innings_batted,
    SUM(fd.runs_batter) AS total_runs,
    COUNT(CASE WHEN fd.is_wide = FALSE THEN 1 END) AS balls_faced,
    COUNT(CASE WHEN fd.is_wicket AND fd.player_out_id = fd.batter_id THEN 1 END) AS dismissals,
    ROUND((SUM(fd.runs_batter)::DOUBLE / NULLIF(COUNT(CASE WHEN fd.is_wicket AND fd.player_out_id = fd.batter_id THEN 1 END), 0)), 2) AS batting_average,
    ROUND((SUM(fd.runs_batter)::DOUBLE / NULLIF(COUNT(CASE WHEN fd.is_wide = FALSE THEN 1 END), 0)) * 100, 2) AS strike_rate,
    SUM(CASE WHEN fd.is_boundary_four THEN 1 ELSE 0 END) AS fours,
    SUM(CASE WHEN fd.is_boundary_six THEN 1 ELSE 0 END) AS sixes,
    ROUND((COUNT(CASE WHEN fd.runs_batter = 0 AND fd.is_wide = FALSE THEN 1 END)::DOUBLE / NULLIF(COUNT(CASE WHEN fd.is_wide = FALSE THEN 1 END), 0)) * 100, 2) AS dot_ball_percentage
FROM gold.fact_delivery fd
JOIN gold.dim_match dm ON fd.match_id = dm.match_id
GROUP BY 1, 2, 3;

-- 2. Bowling Career Mart
-- Fixed: Bowler runs conceded strictly excludes byes and leg-byes!
CREATE OR REPLACE TABLE gold.mart_player_bowling_career AS
SELECT 
    fd.bowler_id AS player_id,
    fd.bowler_name AS full_name,
    dm.match_type,
    COUNT(DISTINCT fd.match_id) AS matches_played,
    COUNT(DISTINCT (fd.match_id || '_' || fd.innings_number::VARCHAR)) AS innings_bowled,
    COUNT(CASE WHEN fd.is_wide = FALSE AND fd.is_no_ball = FALSE THEN 1 END) AS legal_balls_bowled,
    ROUND(COUNT(CASE WHEN fd.is_wide = FALSE AND fd.is_no_ball = FALSE THEN 1 END) / 6.0, 1) AS overs_bowled,
    SUM(fd.runs_batter + CASE WHEN fd.is_wide OR fd.is_no_ball THEN fd.runs_extras ELSE 0 END) AS runs_conceded,
    COUNT(CASE WHEN fd.is_wicket AND fd.dismissal_kind IN ('bowled', 'caught', 'lbw', 'stumped', 'caught and bowled', 'hit wicket') THEN 1 END) AS wickets,
    ROUND((SUM(fd.runs_batter + CASE WHEN fd.is_wide OR fd.is_no_ball THEN fd.runs_extras ELSE 0 END)::DOUBLE / NULLIF(COUNT(CASE WHEN fd.is_wicket AND fd.dismissal_kind IN ('bowled', 'caught', 'lbw', 'stumped', 'caught and bowled', 'hit wicket') THEN 1 END), 0)), 2) AS bowling_average,
    ROUND((SUM(fd.runs_batter + CASE WHEN fd.is_wide OR fd.is_no_ball THEN fd.runs_extras ELSE 0 END)::DOUBLE / NULLIF(COUNT(CASE WHEN fd.is_wide = FALSE AND fd.is_no_ball = FALSE THEN 1 END) / 6.0, 0)), 2) AS economy_rate,
    ROUND((COUNT(CASE WHEN fd.is_wide = FALSE AND fd.is_no_ball = FALSE THEN 1 END)::DOUBLE / NULLIF(COUNT(CASE WHEN fd.is_wicket AND fd.dismissal_kind IN ('bowled', 'caught', 'lbw', 'stumped', 'caught and bowled', 'hit wicket') THEN 1 END), 0)), 2) AS bowling_strike_rate,
    COUNT(CASE WHEN fd.is_dot_ball THEN 1 END) AS dot_balls
FROM gold.fact_delivery fd
JOIN gold.dim_match dm ON fd.match_id = dm.match_id
GROUP BY 1, 2, 3;

-- 3. Tactical Player Matchup Matrix (Pruned with min sample filter balls_faced >= 10 to avoid row explosion)
CREATE OR REPLACE TABLE gold.mart_player_matchup_matrix AS
SELECT 
    fd.batter_id,
    fd.batter_name,
    fd.bowler_id,
    fd.bowler_name,
    fd.phase,
    dm.match_type,
    COUNT(CASE WHEN fd.is_wide = FALSE THEN 1 END) AS balls_faced,
    SUM(fd.runs_batter) AS runs_scored,
    COUNT(CASE WHEN fd.is_wicket AND fd.player_out_id = fd.batter_id THEN 1 END) AS dismissals,
    ROUND((SUM(fd.runs_batter)::DOUBLE / NULLIF(COUNT(CASE WHEN fd.is_wide = FALSE THEN 1 END), 0)) * 100, 2) AS strike_rate,
    COUNT(CASE WHEN fd.is_dot_ball THEN 1 END) AS dot_balls
FROM gold.fact_delivery fd
JOIN gold.dim_match dm ON fd.match_id = dm.match_id
GROUP BY 1, 2, 3, 4, 5, 6
HAVING COUNT(CASE WHEN fd.is_wide = FALSE THEN 1 END) >= 10;
"""
