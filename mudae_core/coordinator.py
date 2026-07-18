"""Thread-safe cross-account claim and $rt reservations."""

import threading


class ClaimCoordinator:
    """Coordinates message reservations under one lock to prevent deadlocks."""

    def __init__(self):
        self._lock = threading.RLock()
        self._claims = set()
        self._restores = set()

    def is_reserved(self, message_id):
        with self._lock:
            return message_id in self._claims or message_id in self._restores

    def filter_available(self, items, id_getter=lambda item: item[0].id):
        with self._lock:
            return [item for item in items if id_getter(item) not in self._claims and id_getter(item) not in self._restores]

    def reserve_claim(self, message_id, allow_reserved_restore=False):
        with self._lock:
            if message_id in self._claims:
                return False
            if message_id in self._restores and not allow_reserved_restore:
                return False
            self._claims.add(message_id)
            if allow_reserved_restore:
                self._restores.discard(message_id)
            return True

    def reserve_restore(self, message_id):
        with self._lock:
            if message_id in self._claims or message_id in self._restores:
                return False
            self._restores.add(message_id)
            return True

    def transition_restore_to_claim(self, message_id):
        with self._lock:
            if message_id in self._claims:
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

    def snapshot(self):
        with self._lock:
            return frozenset(self._claims), frozenset(self._restores)
