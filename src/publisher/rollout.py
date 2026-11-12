"""Bring the API service onto the live snapshot through the Cloud Run Admin API v2 (M0b dossier D-13a)."""

import time

import httpx

from src.config import Settings
from src.utils import setup_logging

logger = setup_logging()

RUN_API = "https://run.googleapis.com/v2"
# M0b dossier D-13b: the job's own token from the Cloud Run metadata server, through httpx; no google-auth
TOKEN_URL = (
    "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token"
)
ENV_NAME = "SNAPSHOT_VERSION"
HTTP_TIMEOUT_S = 30.0
WAIT_TIMEOUT_S = 600.0  # M0b dossier D-14c: the wait for the new revision has a time limit
POLL_S = 5.0


class RolloutError(RuntimeError):
    """The API service is not serving on a ready revision."""


def _get_json(client: httpx.Client, url: str, headers: dict[str, str]) -> dict:
    response = client.get(url, headers=headers)
    response.raise_for_status()
    return response.json()


def _wait_ready(
    client: httpx.Client,
    url: str,
    headers: dict[str, str],
    before: str | None,
    timeout: float,
    poll: float,
) -> str:
    """Wait until a revision newer than `before` is reconciled; return it, or raise if it is not ready."""
    deadline = time.monotonic() + timeout
    while True:
        service = _get_json(client, url, headers)
        created = service.get("latestCreatedRevision")
        if created != before and not service.get("reconciling"):
            break
        if time.monotonic() >= deadline:
            raise RolloutError(f"no ready revision of {url} after {timeout:.0f} s")
        time.sleep(poll)
    if service.get("latestReadyRevision") != created:
        reason = service.get("terminalCondition", {}).get("message", "no reason given")
        raise RolloutError(f"revision {created} is not ready: {reason}")
    return created


def ensure_api_on(
    version: str,
    settings: Settings,
    transport: httpx.BaseTransport | None = None,
    timeout: float = WAIT_TIMEOUT_S,
    poll: float = POLL_S,
) -> None:
    """Make the API service's SNAPSHOT_VERSION equal `version`, so Cloud Run starts a new revision on it.

    Waits until the service's newest revision is ready and raises RolloutError if it is not, or
    httpx.HTTPError if a request fails. An empty `settings.rollout_service` does nothing.
    """
    if not settings.rollout_service:
        return  # M0b dossier D-13a: local runs skip the rollout
    url = f"{RUN_API}/{settings.rollout_service}"
    with httpx.Client(transport=transport, timeout=HTTP_TIMEOUT_S) as client:
        token = _get_json(client, TOKEN_URL, {"Metadata-Flavor": "Google"})["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        service = _get_json(client, url, headers)
        env = service["template"]["containers"][0].setdefault("env", [])
        current = next((e for e in env if e.get("name") == ENV_NAME), None)
        before = None
        if current is None or current.get("value") != version:
            if current is None:
                env.append({"name": ENV_NAME, "value": version})
            else:
                current["value"] = version
            # A revision name in the template would clash with the revision it already named
            service["template"].pop("revision", None)
            before = service.get("latestCreatedRevision")
            # Read-modify-write: every other env var and setting goes back exactly as it was read
            client.patch(url, json=service, headers=headers).raise_for_status()
            logger.info("api_rollout_started", service=settings.rollout_service, version=version)
        # M0b dossier D-14c: wait for the revision; an equal version still needs a ready revision,
        # or a revision that failed last run would leave the API silently on an older snapshot
        revision = _wait_ready(client, url, headers, before, timeout, poll)
    logger.info("api_on_snapshot", revision=revision, version=version)
