"""Bounded graceful shutdown orchestration for long-running services."""

from __future__ import annotations

import logging
import os
import signal
import threading
import time
from collections.abc import Callable
from typing import Any


class GracefulShutdownController:
    """Stop scheduled work, ask the application to exit, and enforce a deadline."""

    def __init__(
        self,
        application: Any,
        *,
        timeout_seconds: float = 8.0,
        force_exit: Callable[[int], None] = os._exit,
        logger: logging.Logger | None = None,
    ) -> None:
        self.application = application
        self.timeout_seconds = timeout_seconds
        self._force_exit = force_exit
        self._logger = logger or logging.getLogger(__name__)
        self._requested = threading.Event()
        self._completed = threading.Event()

    @property
    def requested(self) -> bool:
        return self._requested.is_set()

    @property
    def completed(self) -> bool:
        return self._completed.is_set()

    def install_sigterm_handler(self) -> None:
        signal.signal(signal.SIGTERM, self.request_shutdown)

    def request_shutdown(self, signum: int | None = None, frame: Any = None) -> None:
        del frame
        if self._requested.is_set():
            self._logger.info("Shutdown already requested; ignoring signal=%s", signum)
            return

        self._requested.set()
        self._logger.info(
            "SIGTERM received — graceful shutdown requested (deadline %.1fs)",
            self.timeout_seconds,
        )

        job_queue = getattr(self.application, "job_queue", None)
        scheduler = getattr(job_queue, "scheduler", None)
        try:
            if scheduler is not None and scheduler.running:
                scheduler.shutdown(wait=False)
                self._logger.info("Job scheduler shutdown requested without waiting")
        except Exception:  # noqa: BLE001 - shutdown must continue on cleanup errors
            self._logger.exception("Failed to stop job scheduler during shutdown")

        watchdog = threading.Thread(
            target=self._enforce_deadline,
            name="graceful-shutdown-watchdog",
            daemon=True,
        )
        watchdog.start()

        try:
            self.application.stop_running()
        except Exception:  # noqa: BLE001 - deadline fallback still guarantees termination
            self._logger.exception("Failed to request application stop")

    def mark_complete(self) -> None:
        if self._completed.is_set():
            return
        self._completed.set()
        self._logger.info("Graceful shutdown completed")

    def finish_process(self) -> None:
        self.mark_complete()
        if not self._requested.is_set():
            return
        self._logger.info("Exiting process after graceful application cleanup")
        self._force_exit(0)

    async def post_shutdown(self, application: Any) -> None:
        del application
        self.mark_complete()

    def _enforce_deadline(self) -> None:
        time.sleep(self.timeout_seconds)
        if self._completed.is_set():
            self._logger.error(
                "Application cleanup completed but process is still alive; forcing exit"
            )
        else:
            self._logger.error(
                "Graceful shutdown exceeded %.1fs; forcing process exit",
                self.timeout_seconds,
            )
        self._force_exit(0)
