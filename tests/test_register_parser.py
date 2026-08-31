from pathlib import Path

from src.parsers.register_parser import RegisterParser


def test_parse_people_and_names():
    people_csv = Path("tests/fixtures/sample_people.csv")
    names_csv = Path("tests/fixtures/sample_names.csv")

    parser = RegisterParser()
    result = parser.parse_registers(people_csv, names_csv)

    dim_player = result["dim_player"]
    player_identifiers = result["player_identifiers"]
    player_aliases = result["player_aliases"]

    # Check dim_player
    assert len(dim_player) == 6
    assert "player_id" in dim_player.columns
    assert "full_name" in dim_player.columns
    assert "espncricinfo_id" in dim_player.columns
    assert "483b8b64" in dim_player["player_id"].to_list()

    # Check player_identifiers unpivoting
    assert len(player_identifiers) > 0
    assert "key_source" in player_identifiers.columns
    assert "key_value" in player_identifiers.columns
    assert "cricinfo" in player_identifiers["key_source"].to_list()

    # Check player_aliases
    assert len(player_aliases) > 0
    assert "alias_name" in player_aliases.columns
    assert "V Kohli" in player_aliases["alias_name"].to_list()
