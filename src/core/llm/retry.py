import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, TypeVar

from .errors import classify_llm_error

T = TypeVar("T")
ROOT = Path(__file__).resolve().parents[3]
RETRY_PATH = ROOT / "config" / "defaults" / "llm_retry.json"


@dataclass
class RetryConfig:
    max_retries: int = 1
    initial_delay: float = 0.5
    max_delay: float = 5.0
    exponential_base: float = 2.0
    retry_on_status: tuple[int, ...] = (429,)
    retry_on_errors: tuple[str, ...] = ("timeout", "connection")


def load_retry_config() -> RetryConfig:
    if not RETRY_PATH.exists():
        return RetryConfig()
    try:
        data = json.loads(RETRY_PATH.read_text(encoding="utf-8"))
        return RetryConfig(
            max_retries=int(data.get("max_retries", 1)),
            initial_delay=float(data.get("initial_delay", 0.5)),
            max_delay=float(data.get("max_delay", 5.0)),
            exponential_base=float(data.get("exponential_base", 2.0)),
            retry_on_status=tuple(data.get("retry_on_status", [429])),
            retry_on_errors=tuple(data.get("retry_on_errors", ["timeout", "connection"])),
        )
    except Exception:
        return RetryConfig()


async def with_retry(fn: Callable[[], Awaitable[T]], cfg: RetryConfig | None = None) -> T:
    retry_cfg = cfg or load_retry_config()
    attempt = 0
    while True:
        try:
            return await fn()
        except Exception as exc:
            error = classify_llm_error(exc)
            message = str(error).lower()
            retryable_status = error.status_code in retry_cfg.retry_on_status if error.status_code else False
            retryable_text = any(value in message for value in retry_cfg.retry_on_errors)
            if attempt >= retry_cfg.max_retries or not (retryable_status or retryable_text):
                raise
            delay = min(retry_cfg.initial_delay * (retry_cfg.exponential_base ** attempt), retry_cfg.max_delay)
            attempt += 1
            await asyncio.sleep(delay)
