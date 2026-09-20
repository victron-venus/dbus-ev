"""Private, durable OAuth token storage and one process per Mercedes account."""

import fcntl
import json
import os
import tempfile
from pathlib import Path


class TokenStore:
    """Atomically persist rotating credentials under an exclusive process lock."""

    def __init__(self, path):
        self.path = Path(path)
        # The operator selects the token file in local configuration, never cloud/MQTT input.
        self.data = (
            json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}
        )  # NOSONAR(S8707)
        self._lock = None

    def acquire(self):
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(str(self.path) + ".lock", os.O_CREAT | os.O_RDWR, 0o600)
        self._lock = os.fdopen(fd, "w", encoding="utf-8")
        try:
            fcntl.flock(self._lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self._lock.close()
            self._lock = None
            raise RuntimeError("Another Mercedes client owns this token file") from None
        # The previous owner may have rotated the refresh token before releasing
        # its lock. Read again only after exclusive ownership has been obtained.
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))

    def save(self, data):
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".oauth-", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(data, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            self.data = data
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def close(self):
        if self._lock:
            self._lock.close()
            self._lock = None
