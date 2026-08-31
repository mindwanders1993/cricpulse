import zipfile
from pathlib import Path

import httpx
import pytest

from src.config import Settings
from src.downloaders.match_downloader import MatchDownloader
from src.downloaders.register_downloader import RegisterDownloader


def test_match_downloader_extract_skips_yaml(temp_dir: Path, mock_settings: Settings):
    # Create a mock zip with a json file and a yaml file
    zip_path = temp_dir / "mock_archive.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("1001.json", '{"meta": {"data_version": "1.0.0"}}')
        zf.writestr("1002.yaml", "info: test")
        zf.writestr("README.txt", "Cricket data")

    downloader = MatchDownloader(settings=mock_settings)
    extracted = downloader.extract_archive(zip_path, output_dir=temp_dir / "extracted")

    assert len(extracted) == 1
    assert extracted[0].name == "1001.json"
    assert not (temp_dir / "extracted" / "1002.yaml").exists()
    assert not (temp_dir / "extracted" / "README.txt").exists()


def test_match_downloader_download_archive(
    monkeypatch: pytest.MonkeyPatch, mock_settings: Settings, temp_dir: Path
):
    # Mock httpx.Client.get
    def mock_get(self, url, **kwargs):
        # Create in-memory zip
        import io

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("2001.json", '{"info": {"match_type": "T20"}}')

        response = httpx.Response(
            status_code=200,
            content=buf.getvalue(),
            request=httpx.Request("GET", str(url)),
        )
        return response

    monkeypatch.setattr(httpx.Client, "get", mock_get)

    downloader = MatchDownloader(settings=mock_settings)
    files = downloader.download_and_extract("t20s_json")

    assert len(files) == 1
    assert files[0].name == "2001.json"


def test_register_downloader(monkeypatch: pytest.MonkeyPatch, mock_settings: Settings):
    def mock_get(self, url, **kwargs):
        content = b"identifier,name,unique_name\n483b8b64,Virat Kohli,Virat Kohli\n"
        return httpx.Response(
            status_code=200,
            content=content,
            request=httpx.Request("GET", str(url)),
        )

    monkeypatch.setattr(httpx.Client, "get", mock_get)

    downloader = RegisterDownloader(settings=mock_settings)
    people_csv, names_csv = downloader.download_registers()

    assert people_csv.exists()
    assert names_csv.exists()
    assert b"Virat Kohli" in people_csv.read_bytes()
