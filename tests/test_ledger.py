from pathlib import Path

from src.ledger import IdempotencyLedger


def test_ledger_initialization(temp_dir: Path):
    db_path = temp_dir / "ledger.db"
    ledger = IdempotencyLedger(db_path)
    assert db_path.exists()
    assert ledger.get_processed_match_count() == 0


def test_ledger_record_and_check_match(ledger: IdempotencyLedger):
    match_id = "1384400"
    file_sha256 = "abc123hash"
    archive = "all_json.zip"

    assert not ledger.is_match_processed(match_id, file_sha256)
    assert ledger.get_max_match_revision(match_id) == 0

    ledger.record_match(match_id, file_sha256, revision=1, archive_file=archive)

    assert ledger.is_match_processed(match_id, file_sha256)
    assert ledger.get_max_match_revision(match_id) == 1
    assert ledger.get_processed_match_count() == 1

    # Same match with updated hash (revision bump)
    new_sha256 = "def456newhash"
    assert not ledger.is_match_processed(match_id, new_sha256)
    ledger.record_match(match_id, new_sha256, revision=2, archive_file=archive)

    assert ledger.is_match_processed(match_id, new_sha256)
    assert ledger.get_max_match_revision(match_id) == 2
    assert ledger.get_processed_match_count() == 1


def test_ledger_record_and_check_register(ledger: IdempotencyLedger):
    source_file = "people.csv"
    file_sha = "hash999"

    assert not ledger.is_register_processed(source_file, file_sha)

    ledger.record_register(source_file, file_sha, row_count=17700, snapshot_date="2026-08-31")

    assert ledger.is_register_processed(source_file, file_sha)
