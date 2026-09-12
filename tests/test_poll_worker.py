"""Slow HA requests must not block D-Bus or make cached telemetry fresh."""

import queue
import threading
from unittest.mock import MagicMock

from dbus_ev.main import App
from dbus_ev.service import EVEvices
from dbus_ev.worker import PollWorker


def test_slow_poll_keeps_main_loop_responsive_and_expires_connected(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr("dbus_ev.main._now", lambda: now[0])
    monkeypatch.setattr("dbus_ev.main._write_heartbeat", lambda: None)
    monkeypatch.setattr("dbus_ev.main.config.SENSOR_STALE_TIMEOUT", 120)
    entered = threading.Event()
    release = threading.Event()
    deliveries = queue.Queue()
    caller = threading.get_ident()
    poll_threads = []

    def poll():
        poll_threads.append(threading.get_ident())
        entered.set()
        assert release.wait(2)
        return {"ok": True, "soc": 60, "power": 123}

    client = MagicMock(poll=poll)
    service = EVEvices(
        ev_instance=22, version="test", product_name="test", product_id=1, connection="test"
    )
    app = App(client, service)
    app.apply_snapshot({"ok": True, "soc": 50, "power": 12})
    worker = PollWorker(client, lambda *args: deliveries.put(args), clock=lambda: now[0])
    app.worker = worker
    try:
        assert app.tick() is True
        assert entered.wait(1)
        # The worker remains blocked while repeated GLib ticks continue.
        for _ in range(5):
            assert app.tick() is True
        assert len(poll_threads) == 1
        assert poll_threads[0] != caller
        assert service.ev["/Soc"] == 50
        now[0] += 120
        assert app.tick() is True
        assert service.ev["/Connected"] == 0
        assert app.last_ok_time == 1000
        release.set()
        callback, *args = deliveries.get(timeout=1)
        assert service.ev["/Soc"] == 50  # no publication from the worker thread
        assert callback(*args) is False
        assert service.ev["/Soc"] == 50  # expired request cannot renew freshness
        assert service.ev["/Connected"] == 0
        assert app.last_ok_time == 1000
        assert app.tick() is True
        callback, *args = deliveries.get(timeout=1)
        assert callback(*args) is False
        assert service.ev["/Soc"] == 60
        assert service.ev["/Connected"] == 1
        assert app.last_ok_time == 1120
    finally:
        release.set()
        assert worker.stop(timeout=2)
    client.close.assert_called_once()


def test_worker_exception_can_retry_and_pending_shutdown_cannot_publish():
    deliveries = queue.Queue()
    client = MagicMock()
    client.poll.side_effect = [RuntimeError("bad reply"), {"ok": True, "soc": 42}]
    worker = PollWorker(client, lambda *args: deliveries.put(args))
    applied = []
    try:
        assert worker.poll(applied.append)
        callback, *args = deliveries.get(timeout=1)
        assert callback(*args) is False
        assert len(applied) == 1 and applied[0]["ok"] is False
        assert worker.poll(applied.append)
        callback, *args = deliveries.get(timeout=1)
        assert worker.stop(timeout=2)
        assert callback(*args) is False
        assert len(applied) == 1 and applied[0]["ok"] is False
        assert worker.poll(applied.append) is False
    finally:
        assert worker.stop(timeout=2)
    client.close.assert_called_once()


def test_completed_poll_cannot_become_fresh_after_delayed_delivery(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr("dbus_ev.main._now", lambda: now[0])
    monkeypatch.setattr("dbus_ev.main._write_heartbeat", lambda: None)
    monkeypatch.setattr("dbus_ev.main.config.SENSOR_STALE_TIMEOUT", 120)
    deliveries = queue.Queue()
    client = MagicMock()
    client.poll.return_value = {"ok": True, "soc": 60}
    service = EVEvices(
        ev_instance=22, version="test", product_name="test", product_id=1, connection="test"
    )
    app = App(client, service)
    worker = PollWorker(client, lambda *args: deliveries.put(args), clock=lambda: now[0])
    app.worker = worker
    try:
        app.tick()
        callback, *args = deliveries.get(timeout=1)
        now[0] += 120
        callback(*args)
        assert app.last_ok_time is None
        assert service.ev["/Connected"] == 0
        assert service.ev["/Soc"] is None
    finally:
        assert worker.stop(timeout=2)


def test_shutdown_does_not_close_session_during_active_request():
    entered = threading.Event()
    release = threading.Event()
    client = MagicMock()

    def poll():
        entered.set()
        assert release.wait(2)
        client.close.assert_not_called()
        return {"ok": False}

    client.poll.side_effect = poll
    worker = PollWorker(client, lambda *args: None)
    try:
        worker.poll(lambda snapshot: None)
        assert entered.wait(1)
        assert worker.stop(timeout=0) is False
        client.close.assert_not_called()
    finally:
        release.set()
        assert worker.stop(timeout=2)
    client.close.assert_called_once()
