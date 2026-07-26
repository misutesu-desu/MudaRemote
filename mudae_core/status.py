"""Status freshness helpers used to minimize physical Mudae ``$tu`` queries."""

import time


STATUS_FIELDS = frozenset(("claim", "rolls", "rt", "power", "dk", "points"))
TU_FAILURE_BACKOFF_SECONDS = (30.0, 60.0, 120.0, 300.0, 600.0, 900.0)


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
