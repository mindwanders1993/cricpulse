import datetime as dt
import os

import httpx
import pytest

from src.config import Settings
from src.downloaders.match_downloader import MatchDownloader
from src.downloaders.register_downloader import RegisterDownloader


def _mock_get_recording(calls: list[str], content: bytes):
    def mock_get(self, url, **kwargs):
        calls.append(str(url))
        return httpx.Response(
            status_code=200, content=content, request=httpx.Request("GET", str(url))
        )

    return mock_get


def test_match_download_to_bronze(monkeypatch: pytest.MonkeyPatch, mock_settings: Settings):
    calls: list[str] = []
    monkeypatch.setattr(httpx.Client, "get", _mock_get_recording(calls, b"zip-bytes"))

    downloader = MatchDownloader(settings=mock_settings)
    path = downloader.download_to_bronze("recently_added_7_json", dt.date(2026, 11, 3))

    assert path == mock_settings.data_dir / "bronze/cricsheet/2026-11-03/recently_added_7_json.zip"
    assert path.read_bytes() == b"zip-bytes"
    assert calls == ["https://cricsheet.org/downloads/recently_added_7_json.zip"]


def test_register_download_to_bronze(monkeypatch: pytest.MonkeyPatch, mock_settings: Settings):
    calls: list[str] = []
    monkeypatch.setattr(httpx.Client, "get", _mock_get_recording(calls, b"identifier,name\n"))

    downloader = RegisterDownloader(settings=mock_settings)
    people_csv, names_csv = downloader.download_registers_to_bronze(dt.date(2026, 11, 3))

    reg_dir = mock_settings.data_dir / "bronze/registers/2026-11-03"
    assert (people_csv, names_csv) == (reg_dir / "people.csv", reg_dir / "names.csv")
    assert people_csv.read_bytes() == b"identifier,name\n"
    assert names_csv.exists()
    assert calls == [
        "https://cricsheet.org/register/people.csv",
        "https://cricsheet.org/register/names.csv",
    ]


@pytest.mark.live
@pytest.mark.skipif(os.environ.get("CRICPULSE_LIVE") != "1", reason="live: set CRICPULSE_LIVE=1")
@pytest.mark.parametrize("archive_name", ["recently_added_7_json", "all_json"])
def test_live_cricsheet_archive_exists(archive_name: str):
    # M0b dossier R-3: check the archive names against the live site
    url = f"{Settings().cricsheet_base_url}/downloads/{archive_name}.zip"
    response = httpx.head(url, follow_redirects=True, timeout=30.0)
    assert response.status_code == 200
