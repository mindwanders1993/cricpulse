"""Local OSS plan, card R.2: the app talks to the local model through Moonhopper's gateway."""

import json
import logging
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from src.ai.gemini_client import LOCAL_MODEL_DOWN, GeminiClient, LocalModelUnavailable
from src.api.app import create_app
from src.config import Settings

GATEWAY_KEY = "test-gateway-key"  # a stand-in, not a real key
CANNED_MOCK_TEXT = "Heinrich Klaasen"  # the start of the mock's insight reply


def _settings(temp_dir: Path, app_env: str = "development", api_key: str = GATEWAY_KEY) -> Settings:
    return Settings(_env_file=None, data_dir=temp_dir, app_env=app_env, llm_api_key=api_key)


def _answer(text: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": text}}]})


def test_settings_point_at_the_local_gateway(temp_dir: Path, monkeypatch: pytest.MonkeyPatch):
    for name in ("LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    s = Settings(_env_file=None, data_dir=temp_dir)
    assert s.llm_base_url == "http://127.0.0.1:4000/v1"
    assert s.llm_model == "cricpulse-local"
    assert s.llm_api_key == ""


def test_llm_api_key_is_read_from_the_env_file(temp_dir: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    env_file = temp_dir / ".env"
    env_file.write_text(f"LLM_API_KEY={GATEWAY_KEY}\n")
    assert Settings(_env_file=env_file, data_dir=temp_dir).llm_api_key == GATEWAY_KEY


def test_request_goes_to_the_gateway_with_model_and_key(temp_dir: Path):
    seen: list[httpx.Request] = []

    def gateway(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _answer("Kohli leads the ODI run chart.")

    client = GeminiClient(settings=_settings(temp_dir), transport=httpx.MockTransport(gateway))
    reply = client.generate_text("You are a cricket analyst.", "Who leads the ODI run chart?")

    assert reply == "Kohli leads the ODI run chart."
    assert len(seen) == 1
    request = seen[0]
    assert request.method == "POST"
    assert str(request.url) == "http://127.0.0.1:4000/v1/chat/completions"
    assert request.headers["Authorization"] == f"Bearer {GATEWAY_KEY}"
    body = json.loads(request.content)
    assert body["model"] == "cricpulse-local"
    assert body["messages"] == [
        {"role": "system", "content": "You are a cricket analyst."},
        {"role": "user", "content": "Who leads the ODI run chart?"},
    ]


def test_without_a_key_it_still_calls_the_gateway_not_the_mock(temp_dir: Path):
    seen: list[httpx.Request] = []

    def gateway(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _answer("From the local model.")

    client = GeminiClient(
        settings=_settings(temp_dir, api_key=""), transport=httpx.MockTransport(gateway)
    )
    reply = client.generate_text("system", "Synthesize a concise insight. ROWS RETURNED (0 total)")

    assert reply == "From the local model."
    assert len(seen) == 1
    assert "Authorization" not in seen[0].headers


def test_mock_runs_only_in_the_test_env(temp_dir: Path):
    def gateway(request: httpx.Request) -> httpx.Response:
        raise AssertionError("the test env must not reach the gateway")

    client = GeminiClient(
        settings=_settings(temp_dir, app_env="test"), transport=httpx.MockTransport(gateway)
    )
    reply = client.generate_text("system", "Synthesize a concise insight. ROWS RETURNED (0 total)")

    assert reply.startswith(CANNED_MOCK_TEXT)


def _gateway_down(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("[Errno 61] Connection refused", request=request)


def _no_answer_in_time(request: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout("timed out", request=request)


def _model_server_down(request: httpx.Request) -> httpx.Response:
    # What LiteLLM answers when it is up but the MLX model server behind it is not
    message = (
        "litellm.APIConnectionError: OpenAIException - Connection error. "
        "Received Model Group=cricpulse-local. No fallback model group found for "
        "original model_group=cricpulse-local."
    )
    return httpx.Response(500, json={"error": {"message": message, "code": "500"}})


@pytest.mark.parametrize(
    "gateway",
    [_gateway_down, _no_answer_in_time, _model_server_down],
    ids=["gateway down", "timeout", "model server down"],
)
def test_local_model_not_running_says_so(gateway, temp_dir: Path, caplog: pytest.LogCaptureFixture):
    client = GeminiClient(settings=_settings(temp_dir), transport=httpx.MockTransport(gateway))

    with caplog.at_level(logging.INFO), pytest.raises(LocalModelUnavailable) as raised:
        client.generate_text("system", "Synthesize a concise insight. ROWS RETURNED (0 total)")

    assert str(raised.value) == "Local model not running — run `make start` in Moonhopper"
    assert "local_model_un" in caplog.text
    assert GATEWAY_KEY not in caplog.text  # invariant 8: the key never reaches a log


def test_chat_reply_says_local_model_not_running(temp_dir: Path):
    client = GeminiClient(
        settings=_settings(temp_dir), transport=httpx.MockTransport(_gateway_down)
    )
    app = create_app(db_path=temp_dir / "no_snapshot.duckdb", gemini_client=client)

    with TestClient(app) as api:
        resp = api.post(
            "/api/v1/ai/chat", json={"message": "Who scored the most runs?", "include_chart": True}
        )

    detail = resp.json()["detail"]
    assert LOCAL_MODEL_DOWN in detail
    assert CANNED_MOCK_TEXT not in detail
    assert "Traceback" not in detail
