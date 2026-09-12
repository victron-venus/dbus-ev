"""Run one HA poll at a time while the D-Bus main loop remains responsive."""

import logging
import queue
import threading
import time

logger = logging.getLogger("dbus-ev")


class PollWorker:
    """Bound outstanding work to one request and deliver only on the main loop."""

    def __init__(self, client, dispatch, clock=time.monotonic):
        self.client = client
        self.dispatch = dispatch
        self._clock = clock
        self._queue = queue.Queue(maxsize=1)
        self._stopping = threading.Event()
        self._pending = False  # accessed only by the main loop
        self._thread = threading.Thread(target=self._run, name="ha-poll", daemon=True)
        self._thread.start()

    def poll(self, callback):
        if self._pending or self._stopping.is_set():
            return False
        self._queue.put_nowait(callback)
        self._pending = True
        return True

    def _deliver(self, callback, snapshot):
        self._pending = False
        if not self._stopping.is_set():
            callback(snapshot)
        return False

    def _run(self):
        try:
            while True:
                callback = self._queue.get()
                if callback is None:
                    break
                if self._stopping.is_set():
                    continue
                started_at = self._clock()
                try:
                    snapshot = dict(self.client.poll())
                except Exception:
                    logger.exception("HA poll failed")
                    snapshot = {"ok": False}
                snapshot = dict(snapshot, _sample_started_at=started_at)
                self.dispatch(self._deliver, callback, snapshot)
        finally:
            self.client.close()

    def stop(self, timeout=5.0):
        """Drop queued work and close the Session after the active request."""
        if not self._stopping.is_set():
            self._stopping.set()
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            self._queue.put_nowait(None)
        self._thread.join(timeout)
        return not self._thread.is_alive()
