"""Thread-safe cross-account claim and $rt reservations."""

from collections import OrderedDict
import threading
import time


class GlobalIntervalCoordinator:
    """Reserve process-wide command slots across clients and event loops."""

    def __init__(self):
        self._lock = threading.RLock()
        self._next_slots = {}

    def reserve(self, key, interval_seconds, now_monotonic=None):
        """Return the wait for this reservation and advance the key's next slot."""
        now = time.monotonic() if now_monotonic is None else float(now_monotonic)
        interval = max(0.0, float(interval_seconds))
        with self._lock:
            slot = max(now, self._next_slots.get(key, now))
            self._next_slots[key] = slot + interval
            return max(0.0, slot - now)

    def estimated_wait(self, key, now_monotonic=None):
        """Return the current queue delay without reserving a command slot."""
        now = time.monotonic() if now_monotonic is None else float(now_monotonic)
        with self._lock:
            return max(0.0, self._next_slots.get(key, now) - now)


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


# ---------------------------------------------------------------------------
# Main / Side accounts: a Side rolls for its Main when the Main found nothing
# ---------------------------------------------------------------------------

def _isolate(text):
    """Wrap a name in Unicode isolates so Arabic/Latin names keep their order."""
    return "⁨{}⁩".format(text)


class SideRollHandoff:
    """One Side rolling for one Main; shared by both accounts' threads.

    The Main judges every card the Side rolls with the Main's own rules and
    records its decision here, so a Side that may take leftovers waits for the
    Main first and never spends its claim on a card the Main wants.
    """

    def __init__(self, *, main_key, main_name, side_key, side_name, side_user_id,
                 channel_id, claim_leftovers, reset_key, main_claim_open, main_reset_key):
        self.main_key = main_key
        self.main_name = main_name
        self.side_key = side_key
        self.side_name = side_name
        self.side_user_id = side_user_id
        self.channel_id = channel_id
        self.claim_leftovers = bool(claim_leftovers)
        self.reset_key = reset_key
        self._main_claim_open = main_claim_open
        self._main_reset_key = main_reset_key
        self._lock = threading.Lock()
        self._decisions = {}
        self._closed = False
        self.claimed_card = None
        self.rolls_seen = 0

    def is_side_roll(self, owner_id, channel_id):
        return (
            not self._closed
            and owner_id is not None
            and owner_id == self.side_user_id
            and channel_id == self.channel_id
        )

    def note_side_roll(self):
        with self._lock:
            self.rolls_seen += 1

    def record_main_decision(self, message_id, claimed, card=None):
        with self._lock:
            self._decisions[message_id] = bool(claimed)
            if claimed and self.claimed_card is None:
                self.claimed_card = card or "a character"

    def main_decision(self, message_id):
        """True (Main claimed it), False (Main passed) or None (not judged yet)."""
        with self._lock:
            return self._decisions.get(message_id)

    @property
    def main_claimed(self):
        with self._lock:
            return self.claimed_card is not None

    def main_window_changed(self):
        try:
            return self._main_reset_key() != self.reset_key
        except Exception:
            return True

    def should_stop(self):
        """Stop rolling once the Main claimed, its claim is gone, or it reset."""
        if self._closed or self.main_claimed:
            return True
        try:
            if not self._main_claim_open():
                return True
        except Exception:
            return True
        return self.main_window_changed()

    def close(self):
        with self._lock:
            self._closed = True

    @property
    def closed(self):
        return self._closed


class SideRollCoordinator:
    """Process-wide registry of running accounts and their Side hand-offs.

    Accounts register a small handle (see ``tests/test_side_roll_handoff.py``
    for the fake used in tests). Main/Side links come from the profiles: an
    alt (an extra token of a profile, ``side_kind == "alt"``) belongs to the
    primary token of the same profile; a legacy side profile names its Main
    by stable profile id (that profile's first account) or, for old configs,
    by the Main's Discord user id. All accounts of one profile always run in
    one process, so an alt's main is found here whenever it is running.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._accounts = OrderedDict()
        self._by_main = {}
        self._by_side = {}
        self._used = {}
        self._running_mains = set()

    # -- registry -----------------------------------------------------------
    def register(self, handle):
        with self._lock:
            self._accounts[handle.key] = handle

    def unregister(self, handle):
        with self._lock:
            if self._accounts.get(handle.key) is handle:
                del self._accounts[handle.key]
            for table in (self._by_main, self._by_side):
                stale = [key for key, handoff in table.items()
                         if handle.key in (handoff.main_key, handoff.side_key)]
                for key in stale:
                    table.pop(key).close()

    def accounts(self):
        with self._lock:
            return list(self._accounts.values())

    def resolve_main(self, side):
        """The running Main handle of a Side, or None."""
        if getattr(side, "role", None) != "side":
            return None
        kind = getattr(side, "side_kind", None)
        main_profile_id = str(getattr(side, "main_profile_id", "") or "")
        legacy_main = str(getattr(side, "main_account_id", "") or "").strip()
        for handle in self.accounts():
            if handle is side or handle.key == side.key:
                continue
            if kind == "alt":
                # An alt's main is the primary token of its own profile.
                if (handle.profile_id == side.profile_id
                        and getattr(handle, "account_index", 1) == 1
                        and getattr(handle, "role", "main") == "main"):
                    return handle
                continue
            if main_profile_id:
                if (handle.profile_id == main_profile_id
                        and getattr(handle, "account_index", 1) == 1
                        and getattr(handle, "role", "main") == "main"):
                    return handle
            elif legacy_main and str(_safe(handle, "user_id") or "") == legacy_main:
                return handle
        return None

    def sides_for(self, main):
        sides = []
        for position, handle in enumerate(self.accounts()):
            if handle is main or handle.key == main.key:
                continue
            if self.resolve_main(handle) is main:
                order = getattr(handle, "side_order", 1)
                try:
                    order = int(order)
                except (TypeError, ValueError):
                    order = 1
                sides.append((order, position, getattr(handle, "account_index", 1), handle))
        return [item[-1] for item in sorted(sides, key=lambda item: item[:3])]

    def ineligible_reason(self, side, main):
        """Why a Side cannot roll for its Main now, or None when it can."""
        with self._lock:
            if side.key in self._by_side:
                return "is already rolling for a main"
        if not _safe(side, "is_ready", call=True):
            return "is not connected yet"
        if _safe(side, "channel_id") != _safe(main, "channel_id"):
            return "is not in this channel"
        if _safe(side, "is_paused", call=True):
            return "is paused"
        if _safe(side, "is_rolling", call=True):
            return "is in its own rolling session"
        try:
            rolls = int(side.rolls_left())
        except Exception:
            rolls = 0
        if rolls <= 0:
            return "has no rolls left"
        return None

    def handoff_for_main(self, main_key):
        with self._lock:
            return self._by_main.get(main_key)

    def handoff_for_side(self, side_key):
        with self._lock:
            return self._by_side.get(side_key)

    def sides_used(self, main_key, reset_key):
        with self._lock:
            used_key, count = self._used.get(main_key, (None, 0))
            return count if used_key == reset_key else 0

    def _count_side(self, main_key, reset_key):
        with self._lock:
            used_key, count = self._used.get(main_key, (None, 0))
            count = count + 1 if used_key == reset_key else 1
            self._used[main_key] = (reset_key, count)
            return count

    # -- the hand-off -------------------------------------------------------
    async def run_for_main(self, main, *, log, settle=None, timeout_seconds=900.0):
        """Ask the Main's Sides, one at a time, to roll until the Main claims.

        ``main`` must expose ``key``, ``name``, ``channel_id``, ``options()``
        (``enabled``, ``max_sides``, ``leftovers``), ``claim_open()`` and
        ``claim_reset_key()``. Each Side exposes ``run_handoff_rolls(handoff)``
        (awaitable from the Main's loop). ``log(message, level)`` writes the
        activity line; ``settle()`` is the Main's own interruptible delay used
        between Sides so a claim that is still landing is seen first.
        Returns ``{"asked": [names], "claimed": card|None, "reason": str}``.
        """
        import asyncio

        summary = {"asked": [], "claimed": None, "reason": ""}
        options = dict(main.options() or {})
        if not options.get("enabled"):
            summary["reason"] = "off"
            return summary
        try:
            max_sides = int(options.get("max_sides", 1))
        except (TypeError, ValueError):
            max_sides = 1
        max_sides = max(1, min(10, max_sides))
        if not main.claim_open():
            summary["reason"] = "claim-used"
            return summary
        reset_key = main.claim_reset_key()
        with self._lock:
            if main.key in self._running_mains:
                summary["reason"] = "already-running"
                return summary
            self._running_mains.add(main.key)
        try:
            tried = set()
            while True:
                if self.sides_used(main.key, reset_key) >= max_sides:
                    if not summary["asked"]:
                        log("Side accounts already rolled {} time(s) for this claim reset; waiting for the next one.".format(max_sides), "DEBUG")
                    summary["reason"] = summary["reason"] or "limit"
                    break
                if not main.claim_open() or main.claim_reset_key() != reset_key:
                    summary["reason"] = "claim-window-changed"
                    break
                candidate = None
                for side in self.sides_for(main):
                    if side.key in tried:
                        continue
                    reason = self.ineligible_reason(side, main)
                    if reason:
                        tried.add(side.key)
                        log("Side {} skipped: {}.".format(_isolate(side.name), reason), "INFO")
                        continue
                    candidate = side
                    break
                if candidate is None:
                    if not summary["asked"]:
                        log("Main found nothing — no side account can roll for it now.", "INFO")
                    summary["reason"] = summary["reason"] or "no-side"
                    break
                tried.add(candidate.key)
                self._count_side(main.key, reset_key)
                handoff = SideRollHandoff(
                    main_key=main.key, main_name=main.name,
                    side_key=candidate.key, side_name=candidate.name,
                    side_user_id=_safe(candidate, "user_id"),
                    channel_id=_safe(main, "channel_id"),
                    claim_leftovers=options.get("leftovers", False),
                    reset_key=reset_key,
                    main_claim_open=main.claim_open,
                    main_reset_key=main.claim_reset_key,
                )
                with self._lock:
                    self._by_main[main.key] = handoff
                    self._by_side[candidate.key] = handoff
                summary["asked"].append(candidate.name)
                log("Main found nothing — asking side {} to roll".format(_isolate(candidate.name)), "CLAIM")
                task = asyncio.ensure_future(candidate.run_handoff_rolls(handoff))
                try:
                    # Poll so a Side that disconnects (unregister closes the
                    # hand-off) or hangs never holds the Main for long.
                    deadline = asyncio.get_running_loop().time() + max(1.0, float(timeout_seconds))
                    while not task.done():
                        remaining = deadline - asyncio.get_running_loop().time()
                        if remaining <= 0 or handoff.closed:
                            break
                        await asyncio.wait({task}, timeout=min(1.0, remaining))
                    if not task.done():
                        task.cancel()
                        if handoff.closed:
                            log("Side {} stopped while rolling for the main; moving on.".format(_isolate(candidate.name)), "WARN")
                        else:
                            log("Side {} took too long rolling for the main; moving on.".format(_isolate(candidate.name)), "WARN")
                    elif not task.cancelled() and task.exception() is not None:
                        log("Side {} could not roll for the main: {}".format(_isolate(candidate.name), task.exception()), "WARN")
                except asyncio.CancelledError:
                    task.cancel()
                    raise
                finally:
                    if settle is not None and not handoff.main_claimed:
                        try:
                            await settle()
                        except asyncio.CancelledError:
                            raise
                        except Exception:
                            pass
                    with self._lock:
                        if self._by_main.get(main.key) is handoff:
                            del self._by_main[main.key]
                        if self._by_side.get(candidate.key) is handoff:
                            del self._by_side[candidate.key]
                    handoff.close()
                if handoff.main_claimed:
                    summary["claimed"] = handoff.claimed_card
                    summary["reason"] = "claimed"
                    break
                if not main.claim_open() or main.claim_reset_key() != reset_key:
                    summary["reason"] = "claim-window-changed"
                    break
                log("Side {} finished rolling; the main found nothing to claim.".format(_isolate(candidate.name)), "INFO")
        finally:
            with self._lock:
                self._running_mains.discard(main.key)
        return summary


def _safe(handle, name, call=False):
    try:
        value = getattr(handle, name)
        return value() if call else value
    except Exception:
        return None
