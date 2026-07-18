"""Atomic JSON persistence and shared preset validation."""

import json
import os
import re
import tempfile


_TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


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
                start_i, end_i = int(start), int(end)
            except ValueError:
                errors.append("Invalid inactive-hours window {!r}.".format(part))
                continue
            if not 0 <= start_i <= 23 or not 0 <= end_i <= 23 or start_i == end_i:
                errors.append("Inactive hours must use distinct hours from 0 to 23: {!r}.".format(part))
                continue
            result.append([start_i, end_i])
        return result, errors

    result = []
    errors = []
    for item in value or []:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            errors.append("Invalid inactive-hours entry: {!r}.".format(item))
            continue
        try:
            start_i, end_i = int(item[0]), int(item[1])
        except (TypeError, ValueError):
            errors.append("Invalid inactive-hours entry: {!r}.".format(item))
            continue
        if not 0 <= start_i <= 23 or not 0 <= end_i <= 23 or start_i == end_i:
            errors.append("Inactive hours must use distinct hours from 0 to 23: {!r}.".format(item))
            continue
        result.append([start_i, end_i])
    return result, errors


def validate_preset(data, resolved_token=None):
    """Return user-facing validation errors for a fully collected preset."""
    errors = []
    token = resolved_token if resolved_token is not None else data.get("token")
    if not str(token or "").strip():
        errors.append("Discord token is required.")
    for key, label in (("prefix", "Bot command prefix"), ("mudae_prefix", "Mudae prefix"), ("roll_command", "Roll command")):
        if not str(data.get(key, "")).strip():
            errors.append("{} is required.".format(label))
    try:
        channel_id = int(data.get("channel_id", 0))
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
    main_account_id = data.get("main_account_id")
    if main_account_id not in (None, ""):
        try:
            if int(main_account_id) <= 0:
                raise ValueError
        except (TypeError, ValueError):
            errors.append("Main Account ID must be empty or a positive number.")
    for channel in data.get("snipe_channels", []) or []:
        try:
            if int(channel) <= 0:
                raise ValueError
        except (TypeError, ValueError):
            errors.append("Snipe Channel ID {!r} must be a positive number.".format(channel))

    farm_enabled = bool(data.get("farm_character_enabled", False))
    farm_after_claim = bool(data.get("farm_forcedivorce_after_claim", False))
    if farm_enabled and not str(data.get("farm_character", "") or "").strip():
        errors.append("Kakera Farm Character is required when the farming loop is enabled.")
    if farm_after_claim and not farm_enabled:
        errors.append("Forcedivorce After Verified Claim requires the Kakera Farming Loop.")

    non_negative = [
        "min_kakera", "delay_seconds", "start_delay", "roll_speed", "snipe_delay",
        "series_snipe_delay", "kakera_snipe_threshold", "kakera_reaction_snipe_delay",
        "humanization_window_minutes", "humanization_inactivity_seconds", "reactive_snipe_delay",
        "auto_us_limit", "auto_rolls_limit", "panic_roll_minutes", "auto_divorce_max_kakera",
        "max_claim_rank", "max_like_rank", "hybrid_panic_instant_claim_min_kakera",
        "hybrid_panic_instant_claim_max_rank",
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
