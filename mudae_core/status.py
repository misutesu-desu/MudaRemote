"""Status freshness helpers used to minimize physical Mudae ``$tu`` queries."""

from collections import OrderedDict
from dataclasses import dataclass
import datetime
import re
import threading
import time
import unicodedata


STATUS_FIELDS = frozenset(("claim", "rolls", "rt", "power", "dk", "points"))
TU_FAILURE_BACKOFF_SECONDS = (30.0, 60.0, 120.0, 300.0, 600.0, 900.0)
TU_CACHE_TTL_SECONDS = 30.0 * 60.0


@dataclass(frozen=True)
class ServerResetSnapshot:
    server_id: int
    observed_at_utc: datetime.datetime
    claim_reset_at_utc: datetime.datetime = None
    roll_reset_at_utc: datetime.datetime = None
    observed_fields: frozenset = frozenset()


class ServerResetCoordinator:
    """Stores shared reset boundaries learned passively from server ``$tu`` output."""

    def __init__(self, message_limit=2000):
        self._lock = threading.RLock()
        self._snapshots = {}
        self._seen_messages = OrderedDict()
        self._message_limit = max(1, int(message_limit))

    def observe(
        self,
        server_id,
        message_id,
        observed_at_utc,
        claim_reset_at_utc=None,
        roll_reset_at_utc=None,
    ):
        """Record one status message and return ``(snapshot, changed)``."""
        if server_id is None or message_id is None:
            return None, False
        if claim_reset_at_utc is None and roll_reset_at_utc is None:
            return self.snapshot(server_id), False
        with self._lock:
            if message_id in self._seen_messages:
                return self._snapshots.get(server_id), False
            self._seen_messages[message_id] = None
            while len(self._seen_messages) > self._message_limit:
                self._seen_messages.popitem(last=False)

            previous = self._snapshots.get(server_id)
            observed_fields = frozenset(
                field for field, value in (
                    ("claim", claim_reset_at_utc),
                    ("rolls", roll_reset_at_utc),
                ) if value is not None
            )
            snapshot = ServerResetSnapshot(
                server_id=int(server_id),
                observed_at_utc=observed_at_utc,
                claim_reset_at_utc=(
                    claim_reset_at_utc
                    if claim_reset_at_utc is not None
                    else getattr(previous, "claim_reset_at_utc", None)
                ),
                roll_reset_at_utc=(
                    roll_reset_at_utc
                    if roll_reset_at_utc is not None
                    else getattr(previous, "roll_reset_at_utc", None)
                ),
                observed_fields=observed_fields,
            )
            self._snapshots[server_id] = snapshot
            return snapshot, True

    def snapshot(self, server_id):
        with self._lock:
            return self._snapshots.get(server_id)


_CLAIM_DENIED_COOLDOWN_RE = re.compile(
    r"(?:"
    r"can(?:not|'t)\s+(?:claim|marry)"
    r"|nao\s+pode[^\n]{0,80}?(?:casar|reclamar)"
    r"|no\s+puedes[^\n]{0,80}?(?:reclamar|casarte)"
    r"|ne\s+pouvez\s+pas[^\n]{0,80}?(?:marier|reclamer)"
    r")[^\n]{0,160}?\*{0,2}(?:(\d+)\s*h)?\s*(\d+)\*{0,2}\s*min\b",
    re.IGNORECASE,
)


def _fold_status_text(value):
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(
        character
        for character in normalized
        if not unicodedata.combining(character)
    ).casefold()


def status_message_addresses_identity(content, identities, user_id=None):
    """Return whether a Mudae status line explicitly addresses one identity."""
    text = str(content or "")
    if user_id is not None and (
        "<@{}>".format(user_id) in text
        or "<@!{}>".format(user_id) in text
    ):
        return True

    identity_keys = {
        str(identity).strip().casefold()
        for identity in identities or ()
        if str(identity or "").strip()
    }
    if not identity_keys:
        return False

    bold_match = re.match(r"^\s*\*\*([^*]+)\*\*", text)
    if bold_match:
        addressed_name = bold_match.group(1)
    else:
        plain_match = re.match(r"^\s*([^,\n]{1,80})\s*,", text)
        addressed_name = plain_match.group(1).strip(" *_`~") if plain_match else ""
    return addressed_name.strip().casefold() in identity_keys


def parse_claim_denied_cooldown(content):
    """Return minutes for an explicit localized claim denial, else ``None``."""
    match = _CLAIM_DENIED_COOLDOWN_RE.search(_fold_status_text(content))
    if not match:
        return None
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    return hours * 60 + minutes


def looks_like_tu_status_snapshot(content) -> bool:
    """Distinguish a multi-section ``$tu`` snapshot from a claim rejection."""
    text = str(content or "")
    if text.count("\n") < 2:
        return False
    lowered = text.lower()
    marker_groups = (
        ("roll", "rolls"),
        ("claim",),
        ("$rt",),
        ("$dk",),
        ("$daily",),
        ("$p",),
        ("react", "kakera"),
    )
    matched_groups = sum(
        1 for markers in marker_groups if any(marker in lowered for marker in markers)
    )
    return matched_groups >= 3


def _normalize_fields(fields):
    if fields is None:
        return set(STATUS_FIELDS)
    if isinstance(fields, str):
        fields = (fields,)
    return {str(field) for field in fields if str(field) in STATUS_FIELDS}


def initialize_status_tracking(client) -> None:
    """Initialize per-client status freshness and query backoff state."""
    client._status_dirty_fields = set()
    client._status_refresh_reasons = set()
    client._status_refresh_urgent = False
    client._tu_urgent_bypass_used = False
    client.desync_detected = False
    client._tu_failure_streak = 0
    client._tu_next_allowed_monotonic = 0.0
    client._tu_last_defer_log_monotonic = 0.0
    client.tu_query_count = 0


def status_dirty_fields(client):
    """Return a copy of dirty fields while honoring the legacy boolean flag."""
    dirty = set(getattr(client, "_status_dirty_fields", set()))
    if bool(getattr(client, "desync_detected", False)) and not dirty:
        dirty.update(STATUS_FIELDS)
        client._status_dirty_fields = set(dirty)
    return dirty


def mark_status_dirty(client, fields=None, reason=None, urgent=False) -> None:
    """Mark only the status fields whose local value may no longer be reliable."""
    dirty = status_dirty_fields(client)
    dirty.update(_normalize_fields(fields))
    client._status_dirty_fields = dirty
    client.desync_detected = bool(dirty)
    if reason:
        reasons = set(getattr(client, "_status_refresh_reasons", set()))
        is_new_reason = str(reason) not in reasons
        reasons.add(str(reason))
        client._status_refresh_reasons = reasons
    else:
        is_new_reason = False
    if urgent:
        client._status_refresh_urgent = True
        if is_new_reason:
            client._tu_urgent_bypass_used = False


def clear_status_dirty(client, fields=None) -> None:
    """Clear fields made authoritative by local evidence or a fresh ``$tu``."""
    dirty = status_dirty_fields(client)
    if fields is None:
        dirty.clear()
    else:
        dirty.difference_update(_normalize_fields(fields))
    client._status_dirty_fields = dirty
    client.desync_detected = bool(dirty)
    if not dirty:
        client._status_refresh_reasons = set()
        client._status_refresh_urgent = False
        client._tu_urgent_bypass_used = False


def status_refresh_reasons(client):
    return sorted(set(getattr(client, "_status_refresh_reasons", set())))


def tu_cache_seconds_remaining(last_query_utc, now_utc=None, ttl_seconds=TU_CACHE_TTL_SECONDS) -> float:
    """Return the bounded lifetime left for a cached ``$tu`` snapshot."""
    if last_query_utc is None:
        return 0.0
    now = now_utc or datetime.datetime.now(datetime.timezone.utc)
    try:
        elapsed = max(0.0, (now - last_query_utc).total_seconds())
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, float(ttl_seconds) - elapsed)


def consume_tu_urgent_bypass(client) -> bool:
    """Allow one urgent state change to bypass an existing failure backoff."""
    if not bool(getattr(client, "_status_refresh_urgent", False)):
        return False
    if bool(getattr(client, "_tu_urgent_bypass_used", False)):
        return False
    client._tu_urgent_bypass_used = True
    return True


def defer_tu_queries(client, seconds, now_monotonic=None) -> float:
    """Prevent repeated physical queries until a bounded monotonic deadline."""
    now = time.monotonic() if now_monotonic is None else float(now_monotonic)
    deadline = now + max(0.0, float(seconds))
    current = float(getattr(client, "_tu_next_allowed_monotonic", 0.0))
    client._tu_next_allowed_monotonic = max(current, deadline)
    return client._tu_next_allowed_monotonic


def tu_retry_wait(client, now_monotonic=None) -> float:
    now = time.monotonic() if now_monotonic is None else float(now_monotonic)
    return max(0.0, float(getattr(client, "_tu_next_allowed_monotonic", 0.0)) - now)


def record_tu_failure(client, now_monotonic=None) -> float:
    """Apply exponential retry backoff after a complete unanswered query cycle."""
    streak = int(getattr(client, "_tu_failure_streak", 0)) + 1
    client._tu_failure_streak = streak
    index = min(streak - 1, len(TU_FAILURE_BACKOFF_SECONDS) - 1)
    delay = TU_FAILURE_BACKOFF_SECONDS[index]
    defer_tu_queries(client, delay, now_monotonic=now_monotonic)
    return delay


def record_tu_success(client) -> None:
    client._tu_failure_streak = 0
    client._tu_next_allowed_monotonic = 0.0
    client._tu_urgent_bypass_used = False
