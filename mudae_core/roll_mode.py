"""Process-local claim counts for adaptive slash rolls.

Windows start when a target is registered and retain their alignment through
reconnects. A process restart clears them; separate processes do not share them.
"""

import threading
import time
from collections import OrderedDict


class AdaptiveSlashLedger:
    def __init__(self):
        self._lock = threading.RLock()
        self._groups = {}

    def register(self, channel_id, character_name, window_minutes, now=None):
        name = str(character_name or "").strip().casefold()
        if not name:
            return
        key = (channel_id, name, max(1, int(window_minutes)))
        with self._lock:
            self._groups.setdefault(key, [time.monotonic() if now is None else now, 0, OrderedDict()])

    @staticmethod
    def _advance(group, window_minutes, now):
        length = window_minutes * 60
        elapsed = now - group[0]
        if elapsed >= length:
            group[0] += int(elapsed // length) * length
            group[1] = 0
            group[2].clear()

    def record(self, channel_id, character_name, message_id, now=None):
        if message_id is None:
            return
        name = str(character_name or "").strip().casefold()
        current = time.monotonic() if now is None else now
        with self._lock:
            for (channel, target, minutes), group in self._groups.items():
                if channel != channel_id or target != name:
                    continue
                self._advance(group, minutes, current)
                if message_id not in group[2]:
                    group[2][message_id] = None
                    # ponytail: 2,000 IDs per group; raise the cap if claim throughput makes older IDs recur.
                    if len(group[2]) > 2000:
                        group[2].popitem(last=False)
                    group[1] += 1

    def should_use_slash(self, client, now=None):
        if not getattr(client, "use_slash_rolls", False):
            return False
        target = str(getattr(client, "slash_claim_target", "") or "").strip().casefold()
        limit = getattr(client, "slash_claim_limit", 0)
        if not target or limit <= 0:
            return True
        minutes = getattr(client, "slash_claim_window_minutes", 180)
        key = (getattr(client, "target_channel_id", None), target, minutes)
        current = time.monotonic() if now is None else now
        with self._lock:
            group = self._groups.setdefault(key, [current, 0, OrderedDict()])
            self._advance(group, minutes, current)
            return group[1] < limit


adaptive_slash_ledger = AdaptiveSlashLedger()
