"""The API rollout through the Cloud Run Admin API v2, HTTP mocked at the transport (M0b dossier D-13a, D-14c)."""

import copy
import json

import httpx
import pytest

from src.config import Settings
from src.publisher import rollout
from src.publisher.rollout import RolloutError, ensure_api_on

NAME = "projects/demo-project/locations/us-central1/services/cricpulse-api"
SERVICE_URL = f"https://run.googleapis.com/v2/{NAME}"
OLD, NEW = "v20261111T2030Z", "v20261112T2030Z"


def _revision(n: int) -> str:
    return f"{NAME}/revisions/cricpulse-api-{n:05d}-abc"


def _service(version: str | None, created: int, ready: int, reconciling: bool = False) -> dict:
    """The service as the Admin API returns it: every setting the rollout must keep, and its state."""
    env = [
        {"name": "APP_ENV", "value": "production"},
        {"name": "DATA_DIR", "value": "/mnt/data"},
        {
            "name": "GEMINI_API_KEY",
            "valueSource": {"secretKeyRef": {"secret": "GEMINI_API_KEY", "version": "latest"}},
        },
    ]
    if version is not None:
        env.insert(1, {"name": "SNAPSHOT_VERSION", "value": version})
    return {
        "name": NAME,
        "etag": '"etag-1"',
        "template": {
            "serviceAccount": "cricpulse-api@demo-project.iam.gserviceaccount.com",
            "scaling": {"maxInstanceCount": 2},
            "executionEnvironment": "EXECUTION_ENVIRONMENT_GEN2",
            "volumes": [{"name": "data", "gcs": {"bucket": "cricpulse-data", "readOnly": True}}],
            "containers": [
                {
                    "image": "us-central1-docker.pkg.dev/demo-project/cricpulse/cricpulse-api:abc",
                    "command": ["uvicorn"],
                    "args": ["src.api.app:app", "--host", "0.0.0.0", "--port", "8080"],
                    "env": env,
                    "ports": [{"containerPort": 8080}],
                    "volumeMounts": [{"name": "data", "mountPath": "/mnt/data"}],
                }
            ],
        },
        "latestCreatedRevision": _revision(created),
        "latestReadyRevision": _revision(ready),
        "reconciling": reconciling,
        "terminalCondition": {
            "type": "Ready",
            "state": "CONDITION_SUCCEEDED" if created == ready else "CONDITION_FAILED",
            "message": "" if created == ready else "The user-provided container failed to start.",
        },
    }


class CloudRun:
    """The metadata server and the Cloud Run Admin API v2, as the rollout sees them."""

    def __init__(self, *states: dict, fail: str | None = None) -> None:
        self.states = list(states)  # what each GET of the service returns; the last one repeats
        self.fail = fail  # "token", "get" or "patch": that request answers 403
        self.gets = 0
        self.patches: list[dict] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        if str(request.url) == rollout.TOKEN_URL:
            assert request.headers["Metadata-Flavor"] == "Google"
            return self._answer("token", {"access_token": "tok", "token_type": "Bearer"})
        assert str(request.url) == SERVICE_URL
        assert request.headers["Authorization"] == "Bearer tok"
        if request.method == "PATCH":
            self.patches.append(json.loads(request.content))
            return self._answer("patch", {"name": "projects/demo-project/operations/1"})
        self.gets += 1
        return self._answer("get", self.states[min(self.gets, len(self.states)) - 1])

    def _answer(self, step: str, body: dict) -> httpx.Response:
        if step == self.fail:
            return httpx.Response(403, json={"error": {"code": 403, "status": "PERMISSION_DENIED"}})
        return httpx.Response(200, json=body)


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, rollout_service=NAME)


def _roll_out(run: CloudRun, settings: Settings, timeout: float = 5.0) -> None:
    ensure_api_on(NEW, settings, transport=httpx.MockTransport(run.handle), timeout=timeout, poll=0)


def _with_version(service: dict, version: str) -> dict:
    expected = copy.deepcopy(service)
    for entry in expected["template"]["containers"][0]["env"]:
        if entry["name"] == "SNAPSHOT_VERSION":
            entry["value"] = version
    return expected


def test_empty_rollout_service_does_nothing():
    def no_requests(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"unexpected request: {request.url}")

    settings = Settings(_env_file=None, rollout_service="")

    ensure_api_on(NEW, settings, transport=httpx.MockTransport(no_requests))


def test_an_equal_version_makes_no_update(settings: Settings):
    run = CloudRun(_service(NEW, created=3, ready=3))

    _roll_out(run, settings)

    assert run.patches == []


def test_a_different_version_updates_only_that_env_var_then_waits_for_ready(settings: Settings):
    current = _service(OLD, created=3, ready=3)
    run = CloudRun(
        current,
        _service(NEW, created=3, ready=3, reconciling=True),  # the new revision is not created yet
        _service(NEW, created=4, ready=3, reconciling=True),  # created, starting
        _service(NEW, created=4, ready=4),
    )

    _roll_out(run, settings)

    assert run.patches == [_with_version(current, NEW)]  # every other env var and setting kept
    assert run.gets == 4  # waited until revision 4 was ready


def test_a_missing_env_var_is_added(settings: Settings):
    # A deploy sets every env var anew, so SNAPSHOT_VERSION is absent until the next run
    current = _service(None, created=5, ready=5)
    run = CloudRun(current, _service(NEW, created=6, ready=6))

    _roll_out(run, settings)

    expected = copy.deepcopy(current)
    expected["template"]["containers"][0]["env"].append({"name": "SNAPSHOT_VERSION", "value": NEW})
    assert run.patches == [expected]


def test_a_fixed_revision_name_is_dropped_so_cloud_run_names_the_new_one(settings: Settings):
    current = _service(OLD, created=3, ready=3)
    current["template"]["revision"] = "cricpulse-api-00003-abc"
    run = CloudRun(current, _service(NEW, created=4, ready=4))

    _roll_out(run, settings)

    (patch,) = run.patches
    assert "revision" not in patch["template"]


def test_a_revision_that_fails_raises(settings: Settings):
    run = CloudRun(_service(OLD, created=3, ready=3), _service(NEW, created=4, ready=3))

    with pytest.raises(
        RolloutError, match="cricpulse-api-00004-abc is not ready: The user-provided"
    ):
        _roll_out(run, settings)

    assert len(run.patches) == 1


def test_an_equal_version_on_a_revision_that_failed_raises(settings: Settings):
    # M0b dossier D-14c: last run's revision failed; this run stops "up to date" and must not pass
    run = CloudRun(_service(NEW, created=4, ready=3))

    with pytest.raises(RolloutError, match="is not ready"):
        _roll_out(run, settings)

    assert run.patches == []


def test_the_time_limit_raises(settings: Settings):
    run = CloudRun(
        _service(OLD, created=3, ready=3), _service(NEW, created=4, ready=3, reconciling=True)
    )

    with pytest.raises(RolloutError, match="no ready revision"):
        _roll_out(run, settings, timeout=0)


@pytest.mark.parametrize("step", ["token", "get", "patch"])
def test_an_http_error_raises(settings: Settings, step: str):
    run = CloudRun(_service(OLD, created=3, ready=3), _service(NEW, created=4, ready=4), fail=step)

    with pytest.raises(httpx.HTTPStatusError):
        _roll_out(run, settings)
