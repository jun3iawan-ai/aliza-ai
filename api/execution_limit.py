import math
import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from threading import BoundedSemaphore
from typing import Callable, TypeVar

from fastapi import HTTPException, status


CHAT_LLM_TIMEOUT_ENV_VAR = "ALIZA_CHAT_LLM_TIMEOUT_SECONDS"
CHAT_LLM_MAX_CONCURRENCY_ENV_VAR = "ALIZA_CHAT_LLM_MAX_CONCURRENCY"
DEFAULT_CHAT_LLM_TIMEOUT_SECONDS = 45.0
DEFAULT_CHAT_LLM_MAX_CONCURRENCY = 2
MAX_CHAT_LLM_TIMEOUT_SECONDS = 120.0
MAX_CHAT_LLM_CONCURRENCY = 8

T = TypeVar("T")


class ExecutionTimeoutError(Exception):
    pass


def get_chat_execution_config() -> tuple[float, int]:
    timeout = _positive_float_from_env(
        CHAT_LLM_TIMEOUT_ENV_VAR,
        DEFAULT_CHAT_LLM_TIMEOUT_SECONDS,
        MAX_CHAT_LLM_TIMEOUT_SECONDS,
    )
    concurrency = _positive_int_from_env(
        CHAT_LLM_MAX_CONCURRENCY_ENV_VAR,
        DEFAULT_CHAT_LLM_MAX_CONCURRENCY,
        MAX_CHAT_LLM_CONCURRENCY,
    )
    return timeout, concurrency


def _positive_float_from_env(name: str, default: float, maximum: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        value = float(raw_value.strip())
    except (AttributeError, ValueError):
        raise RuntimeError(f"{name} must be a positive number.") from None
    if not math.isfinite(value) or value <= 0 or value > maximum:
        raise RuntimeError(f"{name} must be greater than 0 and at most {maximum}.")
    return value


def _positive_int_from_env(name: str, default: int, maximum: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        value = int(raw_value.strip())
    except (AttributeError, ValueError):
        raise RuntimeError(f"{name} must be a positive integer.") from None
    if value <= 0 or value > maximum:
        raise RuntimeError(f"{name} must be greater than 0 and at most {maximum}.")
    return value


class ExecutionLimiter:
    def __init__(self, *, timeout_seconds: float, max_concurrency: int):
        if timeout_seconds <= 0 or max_concurrency <= 0:
            raise ValueError("Execution limiter settings must be positive.")
        self.timeout_seconds = timeout_seconds
        self.max_concurrency = max_concurrency
        self._slots = BoundedSemaphore(max_concurrency)
        self._executor = ThreadPoolExecutor(
            max_workers=max_concurrency,
            thread_name_prefix="aliza-chat-llm",
        )

    def run(self, function: Callable[..., T], *args, **kwargs) -> T:
        if not self._slots.acquire(blocking=False):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Chat service is busy",
            )

        try:
            future = self._executor.submit(function, *args, **kwargs)
        except Exception:
            self._slots.release()
            raise

        try:
            result = future.result(timeout=self.timeout_seconds)
        except FutureTimeoutError:
            future.add_done_callback(lambda _future: self._slots.release())
            future.cancel()
            raise ExecutionTimeoutError("Chat execution timed out.") from None
        except BaseException:
            self._slots.release()
            raise
        else:
            self._slots.release()
            return result

    def shutdown(self) -> None:
        self._executor.shutdown(wait=True, cancel_futures=True)


_timeout_seconds, _max_concurrency = get_chat_execution_config()
CHAT_LLM_EXECUTION_LIMITER = ExecutionLimiter(
    timeout_seconds=_timeout_seconds,
    max_concurrency=_max_concurrency,
)
