import asyncio
import signal
import threading
import time

from core.graceful_shutdown import GracefulShutdownController


class FakeScheduler:
    def __init__(self):
        self.running = True
        self.calls = []

    def shutdown(self, wait=True):
        self.calls.append(wait)
        self.running = False


class FakeApplication:
    def __init__(self):
        self.job_queue = type("JobQueue", (), {"scheduler": FakeScheduler()})()
        self.stop_calls = 0

    def stop_running(self):
        self.stop_calls += 1


def test_sigterm_stops_scheduler_and_application_without_waiting():
    app = FakeApplication()
    forced = []
    controller = GracefulShutdownController(
        app,
        timeout_seconds=30.0,
        force_exit=forced.append,
    )

    started = time.monotonic()
    controller.request_shutdown(signal.SIGTERM)
    controller.mark_complete()

    assert time.monotonic() - started < 0.5
    assert app.job_queue.scheduler.calls == [False]
    assert app.stop_calls == 1
    assert controller.requested
    assert controller.completed
    assert forced == []


def test_repeated_sigterm_is_idempotent():
    app = FakeApplication()
    controller = GracefulShutdownController(
        app,
        timeout_seconds=30.0,
        force_exit=lambda code: None,
    )

    controller.request_shutdown(signal.SIGTERM)
    controller.request_shutdown(signal.SIGTERM)
    controller.mark_complete()

    assert app.job_queue.scheduler.calls == [False]
    assert app.stop_calls == 1


def test_shutdown_deadline_forces_exit_within_bound():
    app = FakeApplication()
    forced = []
    forced_event = threading.Event()

    def force_exit(code):
        forced.append(code)
        forced_event.set()

    controller = GracefulShutdownController(
        app,
        timeout_seconds=0.05,
        force_exit=force_exit,
    )
    started = time.monotonic()
    controller.request_shutdown(signal.SIGTERM)

    assert forced_event.wait(0.5)
    assert time.monotonic() - started < 0.5
    assert forced == [0]


def test_finished_cleanup_exits_immediately_instead_of_waiting_for_threads():
    app = FakeApplication()
    forced = []
    controller = GracefulShutdownController(
        app,
        timeout_seconds=30.0,
        force_exit=forced.append,
    )

    controller.request_shutdown(signal.SIGTERM)
    controller.finish_process()

    assert controller.completed
    assert forced == [0]


def test_post_shutdown_marks_cleanup_complete():
    app = FakeApplication()
    controller = GracefulShutdownController(app, timeout_seconds=0.5)

    asyncio.run(controller.post_shutdown(app))

    assert controller.completed
