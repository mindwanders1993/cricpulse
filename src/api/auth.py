from fastapi import Header, HTTPException, status

from src.config import get_settings


def verify_sync_token(x_sync_token: str | None = Header(default=None)) -> bool:
    """Verify secret token for internal cron/scheduler webhooks."""
    settings = get_settings()
    if not settings.sync_secret_token or settings.app_env == "test":
        return True

    if not x_sync_token or x_sync_token != settings.sync_secret_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Sync-Token header",
        )
    return True
