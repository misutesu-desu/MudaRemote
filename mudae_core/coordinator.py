"""Thread-safe cross-account claim and $rt reservations."""

from collections import OrderedDict
import threading


class ClaimCoordinator:
    """Coordinates message reservations under one lock to prevent deadlocks."""

    def __init__(self, completed_limit=2000):
        self._lock = threading.RLock()
        self._claims = set()
        self._restores = set()
        self._completed = OrderedDict()
        self._completed_limit = max(1, int(completed_limit))

    def is_reserved(self, message_id):
        with self._lock:
            return (
                message_id in self._claims
                or message_id in self._restores
                or message_id in self._completed
            )

    def filter_available(self, items, id_getter=lambda item: item[0].id):
        with self._lock:
            return [
                item for item in items
                if id_getter(item) not in self._claims
                and id_getter(item) not in self._restores
                and id_getter(item) not in self._completed
            ]

    def reserve_claim(self, message_id, allow_reserved_restore=False):
        with self._lock:
            if message_id in self._claims or message_id in self._completed:
                return False
            if message_id in self._restores and not allow_reserved_restore:
                return False
            self._claims.add(message_id)
            if allow_reserved_restore:
                self._restores.discard(message_id)
            return True

    def reserve_restore(self, message_id):
        with self._lock:
            if (
                message_id in self._claims
                or message_id in self._restores
                or message_id in self._completed
            ):
                return False
            self._restores.add(message_id)
            return True

    def transition_restore_to_claim(self, message_id):
        with self._lock:
            if message_id in self._claims or message_id in self._completed:
                return False
            self._restores.discard(message_id)
            self._claims.add(message_id)
            return True

    def release_claim(self, message_id):
        with self._lock:
            self._claims.discard(message_id)

    def release_restore(self, message_id):
        with self._lock:
            self._restores.discard(message_id)

    def release_all(self, message_id):
        with self._lock:
            self._claims.discard(message_id)
            self._restores.discard(message_id)

    def mark_completed(self, message_id):
        """Keep a bounded terminal record so late clients cannot retry a resolved roll."""
        if message_id is None:
            return
        with self._lock:
            self._claims.discard(message_id)
            self._restores.discard(message_id)
            self._completed.pop(message_id, None)
            self._completed[message_id] = None
            while len(self._completed) > self._completed_limit:
                self._completed.popitem(last=False)

    def completed_snapshot(self):
        with self._lock:
            return frozenset(self._completed)

    def snapshot(self):
        with self._lock:
            return frozenset(self._claims), frozenset(self._restores)
