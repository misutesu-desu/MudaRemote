"""Atomic JSON persistence and shared preset validation."""

import json
import os
import re
import tempfile


_TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


def _normalize_clock(value):
    """Return HH:MM for legacy integer hours or minute-precise clock text."""
    if isinstance(value, bool):
        raise ValueError
    if isinstance(value, int):
        if not 0 <= value <= 23:
            raise ValueError
        return "{:02d}:00".format(value)
    text = str(value or "").strip()
    if text.isdigit():
        hour = int(text)
        if not 0 <= hour <= 23:
            raise ValueError
        return "{:02d}:00".format(hour)
    if not _TIME_RE.match(text):
        raise ValueError
    return text


def load_json(path, default=None):
    if not os.path.exists(path):
        return {} if default is None else default
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def atomic_write_json(path, data, indent=4):
    """Write JSON beside its destination, fsync it, then atomically replace."""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=".mudae-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, indent=indent, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except Exception:
        try:
            os.remove(temp_path)
        except OSError:
            pass
        raise


def parse_scheduled_times(values):
    if isinstance(values, str):
        values = [part.strip() for part in values.split(",") if part.strip()]
    result = []
    errors = []
    for value in values or []:
        value = str(value).strip()
        if not _TIME_RE.match(value):
            errors.append("Invalid scheduled time {!r}; use HH:MM (00:00-23:59).".format(value))
        elif value not in result:
            result.append(value)
    return result, errors


def parse_inactive_hours(value):
    if isinstance(value, str):
        result = []
        errors = []
        for part in [item.strip() for item in value.split(",") if item.strip()]:
            if "-" not in part:
                errors.append("Invalid inactive-hours window {!r}; use START-END.".format(part))
                continue
            start, end = [item.strip() for item in part.split("-", 1)]
            try:
                start_clock, end_clock = _normalize_clock(start), _normalize_clock(end)
            except ValueError:
                errors.append("Invalid inactive-hours window {!r}.".format(part))
                continue
            if start_clock == end_clock:
                errors.append("Inactive hours must use distinct start and end times: {!r}.".format(part))
                continue
            result.append([start_clock, end_clock])
        return result, errors

    result = []
    errors = []
    for item in value or []:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            errors.append("Invalid inactive-hours entry: {!r}.".format(item))
            continue
        try:
            start_clock, end_clock = _normalize_clock(item[0]), _normalize_clock(item[1])
        except (TypeError, ValueError):
            errors.append("Invalid inactive-hours entry: {!r}.".format(item))
            continue
        if start_clock == end_clock:
            errors.append("Inactive hours must use distinct hours from 0 to 23: {!r}.".format(item))
            continue
        result.append([start_clock, end_clock])
    return result, errors


def validate_preset(data, resolved_token=None, require_runtime=True):
    """Return validation errors, optionally allowing an incomplete editor draft."""
    errors = []
    token = resolved_token if resolved_token is not None else data.get("token")
    token_values = token if isinstance(token, (list, tuple)) else [token]
    if require_runtime and not any(str(item or "").strip() for item in token_values):
        errors.append("Discord token is required.")
    for key, label in (("prefix", "Bot command prefix"), ("mudae_prefix", "Mudae prefix"), ("roll_command", "Roll command")):
        if not str(data.get(key, "")).strip():
            errors.append("{} is required.".format(label))
    channel_id = data.get("channel_id")
    if require_runtime or channel_id not in (None, ""):
        try:
            channel_id = int(channel_id or 0)
            if channel_id <= 0:
                raise ValueError
        except (TypeError, ValueError):
            errors.append("Discord Channel ID must be a positive number.")
    command_channel = data.get("command_channel_id")
    if command_channel not in (None, ""):
        try:
            if int(command_channel) <= 0:
                raise ValueError
        except (TypeError, ValueError):
            errors.append("Command Channel ID must be empty or a positive number.")
    forcedivorce_channel = data.get("forcedivorce_channel_id")
    if forcedivorce_channel not in (None, ""):
        try:
            if int(forcedivorce_channel) <= 0:
                raise ValueError
        except (TypeError, ValueError):
            errors.append("Forcedivorce Channel ID must be empty or a positive number.")
    main_account_id = data.get("main_account_id")
    if main_account_id not in (None, ""):
        try:
            if int(main_account_id) <= 0:
                raise ValueError
        except (TypeError, ValueError):
            errors.append("Main Account ID must be empty or a positive number.")
    webhook_url = str(data.get("webhook_url", "") or "").strip()
    if webhook_url and not re.match(r"^https://(?:canary\.|ptb\.)?discord(?:app)?\.com/api/webhooks/", webhook_url):
        errors.append("Remote Log Webhook URL must be a Discord HTTPS webhook URL.")
    allowed_webhook_types = {"ALL", "ERROR", "WARN", "CLAIM", "KAKERA", "INFO", "CHECK", "RESET", "DEBUG"}
    invalid_webhook_types = [
        item for item in (data.get("webhook_log_types") or [])
        if str(item).strip().upper() not in allowed_webhook_types
    ]
    if invalid_webhook_types:
        errors.append("Unknown webhook log type(s): {}.".format(", ".join(map(str, invalid_webhook_types))))
    allowed_debug_categories = {"all", "claim", "kakera", "roll", "status", "sphere", "coordination", "other"}
    invalid_debug_categories = [
        item for item in (data.get("debug_log_categories") or [])
        if str(item).strip().casefold() not in allowed_debug_categories
    ]
    if invalid_debug_categories:
        errors.append("Unknown Expert Log category/categories: {}.".format(", ".join(map(str, invalid_debug_categories))))
    for channel in data.get("snipe_channels", []) or []:
        try:
            if int(channel) <= 0:
                raise ValueError
        except (TypeError, ValueError):
            errors.append("Snipe Channel ID {!r} must be a positive number.".format(channel))

    farm_enabled = bool(data.get("farm_character_enabled", False))
    farm_characters = [
        str(item or "").strip()
        for item in (data.get("farm_characters") or [])
        if str(item or "").strip()
    ]
    if str(data.get("farm_character", "") or "").strip():
        farm_characters.insert(0, str(data.get("farm_character")).strip())
    farm_after_claim = bool(data.get("farm_forcedivorce_after_claim", False))
    farm_after_other_claim = bool(data.get("farm_forcedivorce_after_other_claim", False))
    farm_before_roll = bool(data.get(
        "farm_forcedivorce_before_roll",
        farm_enabled and not farm_after_claim and not farm_after_other_claim,
    ))
    if farm_enabled and not farm_characters:
        errors.append("At least one Kakera Farm Character is required when the farming loop is enabled.")
    if farm_after_claim and not farm_enabled:
        errors.append("Forcedivorce After Verified Claim requires the Kakera Farming Loop.")
    if farm_after_other_claim and not farm_enabled:
        errors.append("Forcedivorce After Another Account Claim requires the Kakera Farming Loop.")
    if farm_before_roll and not farm_enabled:
        errors.append("Forcedivorce Before Rolling requires the Kakera Farming Loop.")
    if farm_enabled and not (farm_before_roll or farm_after_claim or farm_after_other_claim):
        errors.append("Kakera Farming Loop requires at least one forcedivorce timing option.")

    non_negative = [
        "min_kakera", "delay_seconds", "start_delay", "roll_speed", "snipe_delay",
        "series_snipe_delay", "kakera_snipe_threshold", "kakera_reaction_snipe_delay",
        "humanization_window_minutes", "humanization_inactivity_seconds", "reactive_snipe_delay",
        "auto_us_limit", "auto_rolls_limit", "panic_roll_minutes", "auto_divorce_max_kakera",
        "max_claim_rank", "max_like_rank", "hybrid_panic_instant_claim_min_kakera",
        "hybrid_panic_instant_claim_max_rank", "oh_unknown_explore_clicks",
    ]
    for key in non_negative:
        if key in data and data[key] is not None:
            try:
                if float(data[key]) < 0:
                    errors.append("{} cannot be negative.".format(key))
            except (TypeError, ValueError):
                errors.append("{} must be numeric.".format(key))

    for key in ("claim_interval", "roll_interval", "max_dk_power"):
        try:
            if float(data.get(key, 0)) <= 0:
                errors.append("{} must be greater than zero.".format(key))
        except (TypeError, ValueError):
            errors.append("{} must be numeric.".format(key))

    if data.get("only_chaos", False) and data.get("chaos_emojis") == []:
        errors.append("Chaos Kakera Only cannot be used with an explicitly empty Chaos Emojis list.")
    if data.get("kakera_reaction_snipe_mode", False) and data.get("kakera_emojis") == []:
        errors.append("Auto-Collect Kakera cannot use an explicitly empty Kakera Emojis list.")

    delay_range = data.get("reactive_kakera_delay_range", [0.3, 1.0])
    if not isinstance(delay_range, (list, tuple)) or len(delay_range) != 2:
        errors.append("Reactive Kakera delay must contain minimum and maximum values.")
    else:
        try:
            minimum, maximum = float(delay_range[0]), float(delay_range[1])
            if minimum < 0 or maximum < 0 or minimum > maximum:
                errors.append("Reactive Kakera delay must satisfy 0 <= minimum <= maximum.")
        except (TypeError, ValueError):
            errors.append("Reactive Kakera delay values must be numeric.")

    _, schedule_errors = parse_scheduled_times(data.get("scheduled_roll_times", []))
    _, inactive_errors = parse_inactive_hours(data.get("inactive_hours", []))
    errors.extend(schedule_errors)
    errors.extend(inactive_errors)

    for name, threshold in (data.get("kakera_power_thresholds") or {}).items():
        try:
            value = int(threshold)
            if value < 0 or value > int(data.get("max_dk_power", 100)):
                errors.append("Power threshold {} must be between 0 and max_dk_power.".format(name))
        except (TypeError, ValueError):
            errors.append("Power threshold {} must be an integer.".format(name))
    for round_data in data.get("claim_rounds_thresholds", []) or []:
        try:
            round_number = int(round_data.get("round", 0))
            if round_number <= 0:
                raise ValueError
        except (AttributeError, TypeError, ValueError):
            errors.append("Every dynamic claim round must have a positive round number.")
            continue
        for key in ("min_kakera", "max_claim_rank", "max_like_rank"):
            if key in round_data:
                try:
                    if int(round_data[key]) < 0:
                        raise ValueError
                except (TypeError, ValueError):
                    errors.append("Round {} {} must be a non-negative integer.".format(round_number, key))
    return errors
