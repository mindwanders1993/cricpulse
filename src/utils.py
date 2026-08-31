import hashlib
import logging
from pathlib import Path

import structlog


def setup_logging(log_level: str = "INFO") -> structlog.stdlib.BoundLogger:
    """Configure structured logging for CricPulse."""
    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, log_level.upper(), logging.INFO),
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(colors=True),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    return structlog.get_logger("cricpulse")


def compute_file_sha256(file_path: Path | str, chunk_size: int = 65536) -> str:
    """Compute SHA-256 hash of a file efficiently in chunks."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(chunk_size):
            sha256.update(chunk)
    return sha256.hexdigest()


def compute_bytes_sha256(data: bytes) -> str:
    """Compute SHA-256 hash of bytes in memory."""
    return hashlib.sha256(data).hexdigest()
