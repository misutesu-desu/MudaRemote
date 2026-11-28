"""Atomic JSON persistence and shared preset validation."""

import json
import math
import os
import re
import datetime
import uuid


_TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d)?$")


def _normalize_clock(value):
    """Return HH:MM for legacy integer hours, or the HH:MM / HH:MM:SS clock text."""
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


def clock_seconds(value):
    """Seconds after midnight for a legacy hour or HH:MM / HH:MM:SS text."""
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return (value % 24) * 3600
    match = re.fullmatch(r"\s*(\d{1,2})(?::(\d{2}))?(?::(\d{2}))?\s*", str(value or ""))
    if not match:
        return 0
    return (
        (int(match.group(1)) % 24) * 3600
        + min(59, int(match.group(2) or 0)) * 60
        + min(59, int(match.group(3) or 0))
    )


def seconds_until_window_end(start_value, end_value, now):
    """Seconds until a daily window ends, or None when ``now`` is outside it."""
    start = clock_seconds(start_value)
    end = clock_seconds(end_value)
    current = now.hour * 3600 + now.minute * 60 + now.second
    inside = start <= current < end if start <= end else current >= start or current < end
    if not inside:
        return None
    wake = now.replace(hour=end // 3600, minute=(end % 3600) // 60, second=end % 60, microsecond=0)
    if wake <= now:
        wake += datetime.timedelta(days=1)
    return (wake - now).total_seconds()


def load_json(path, default=None):
    if not os.path.exists(path):
        return {} if default is None else default
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _create_temp_file(directory):
    """Create a private temp file beside the target, trying once per name.

    ``tempfile.mkstemp`` treats a refused creation as a name clash on Windows and retries thousands of
    times, so a folder the user cannot write to (an install in Program Files) froze the app for minutes.
    Here only a real name clash is retried; a refusal raises at once."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    for _ in range(100):
        temp_path = os.path.join(directory, ".mudae-{}.tmp".format(uuid.uuid4().hex[:12]))
        try:
            return os.open(temp_path, flags, 0o600), temp_path
        except FileExistsError:
            continue
    raise FileExistsError("Could not find a free temporary file name in {}".format(directory))


def atomic_write_json(path, data, indent=4):
    """Write JSON beside its destination, fsync it, then atomically replace."""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, temp_path = _create_temp_file(directory)
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
            errors.append("Invalid scheduled time {!r}; use HH:MM or HH:MM:SS (00:00-23:59:59).".format(value))
        elif value not in result:
            result.append(value)
    return result, errors


def parse_dk_schedule_time(value):
    """Normalize optional local daily Auto $dk times, comma-separated ("06:00, 18:30")."""
    if not isinstance(value, str):
        return None, ["dk_schedule_time must be text in HH:MM format."]
    if not value.strip():
        return "", []
    parts = [part.strip() for part in value.split(",")]
    if not all(re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", part) for part in parts):
        return None, ["dk_schedule_time must be empty or valid 24-hour HH:MM times separated by commas."]
    return ", ".join(sorted(set(parts))), []


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
    _, dk_schedule_errors = parse_dk_schedule_time(data.get("dk_schedule_time", ""))
    errors.extend(dk_schedule_errors)
    loot_mode = data.get("loot_mode", "off")
    if loot_mode not in ("off", "kl", "scrap"):
        errors.append("Loot mode must be off, kl, or scrap.")

    def setting_int(key, default, minimum):
        value = data.get(key, default)
        if isinstance(value, bool) or not re.fullmatch(r"[0-9]+", str(value).strip()):
            errors.append("{} must be an integer >= {}.".format(key, minimum))
            return None
        try:
            result = int(str(value).strip())
        except ValueError:
            errors.append("{} must be an integer >= {}.".format(key, minimum))
            return None
        if result < minimum:
            errors.append("{} must be an integer >= {}.".format(key, minimum))
            return None
        return result

    slash_limit = setting_int("slash_claim_limit", 0, 0)
    setting_int("slash_claim_window_minutes", 180, 1)
    if slash_limit and not isinstance(data.get("slash_claim_target", ""), str):
        errors.append("Slash-to-text character target must be text.")
    elif slash_limit and not data.get("slash_claim_target", "").strip():
        errors.append("Slash-to-text character target is required when the claim limit is above zero.")

    if loot_mode in ("kl", "scrap"):
        if loot_mode == "kl":
            setting_int("kl_amount", 1000, 1)
            setting_int("kl_arlp_every", 0, 0)
        else:
            setting_int("scrap_amount", 500000000, 1)
            target = data.get("scrap_target_id", "")
            if not isinstance(target, str) or not re.fullmatch(r"[0-9]+", target.strip()) or not target.strip().lstrip("0"):
                errors.append("Scrap target must be a positive numeric Discord user ID.")
        cooldowns = {}
        for key, default in (("loot_min_cooldown", 30), ("loot_max_cooldown", 40)):
            value = data.get(key, default)
            try:
                if isinstance(value, bool):
                    raise ValueError
                parsed = float(value)
                if not math.isfinite(parsed) or parsed < 1:
                    raise ValueError
                cooldowns[key] = parsed
            except (TypeError, ValueError, OverflowError):
                errors.append("{} must be a finite number >= 1.".format(key))
        if len(cooldowns) == 2 and cooldowns["loot_max_cooldown"] < cooldowns["loot_min_cooldown"]:
            errors.append("Maximum loot cooldown must be >= minimum loot cooldown.")
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
    errors.extend(validate_account_role_settings(data))
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
    for key, label in (("snipe_channels", "Snipe"), ("kakera_snipe_channels", "Kakera snipe")):
        for channel in data.get(key, []) or []:
            try:
                if int(channel) <= 0:
                    raise ValueError
            except (TypeError, ValueError):
                errors.append("{} Channel ID {!r} must be a positive number.".format(label, channel))

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
        "hybrid_panic_instant_claim_max_rank", "oh_unknown_explore_clicks", "auto_dk_min_power",
        "sphere_collect_any_last", "rt_min_kakera",
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

    server_reset_minute = data.get("server_reset_minute")
    if server_reset_minute is not None and str(server_reset_minute).strip() != "":
        try:
            val = int(server_reset_minute)
            if val < 0 or val > 59:
                errors.append("server_reset_minute must be an integer between 0 and 59, or left empty.")
        except (TypeError, ValueError):
            errors.append("server_reset_minute must be an integer between 0 and 59, or left empty.")

    try:
        if float(data.get("auto_dk_min_power", 0) or 0) > float(data.get("max_dk_power", 100)):
            errors.append("auto_dk_min_power cannot exceed max_dk_power.")
    except (TypeError, ValueError):
        pass

    if data.get("kakera_filter_match_mode", "all") not in ("all", "any"):
        errors.append("Match selected filters must be All (all) or Any (any).")

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


# ---------------------------------------------------------------------------
# Profiles: stable ids, display names, and Main/Side account roles
# ---------------------------------------------------------------------------

PROFILE_NAME_MAX_LENGTH = 40
ACCOUNT_ROLE_MAIN = "main"
ACCOUNT_ROLE_SIDE = "side"
ACCOUNT_ROLES = (ACCOUNT_ROLE_MAIN, ACCOUNT_ROLE_SIDE)
SIDE_ROLLS_MAX_PER_RESET_LIMIT = 10

# Defaults for the role and hand-off settings (all hand-off options are off).
ACCOUNT_ROLE_DEFAULTS = {
    "profile_id": "",
    "account_role": ACCOUNT_ROLE_MAIN,
    "main_profile_id": "",
    "side_order": 1,
    "side_rolls_for_main": False,
    "side_rolls_max_per_reset": 1,
    "side_claim_leftovers": False,
}

_PROFILE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def new_profile_id():
    """A stable profile key that never changes when the profile is renamed."""
    return "p" + uuid.uuid4().hex[:15]


def normalize_profile_name(name):
    """Return ``(clean_name, error)``: trimmed, 1-40 characters, any script."""
    if not isinstance(name, str):
        return None, "Profile name must be text."
    clean = name.strip()
    if not clean:
        return None, "Profile name cannot be empty."
    if len(clean) > PROFILE_NAME_MAX_LENGTH:
        return None, "Profile name must be at most {} characters.".format(PROFILE_NAME_MAX_LENGTH)
    if any(ord(ch) < 32 for ch in clean):
        return None, "Profile name cannot contain control characters."
    return clean, None


def profile_name_conflict(presets, name, ignore=None):
    """The existing profile name that equals ``name`` ignoring case, else None."""
    wanted = str(name or "").casefold()
    ignored = None if ignore is None else str(ignore).casefold()
    for existing in presets or {}:
        folded = str(existing).casefold()
        if folded == wanted and folded != ignored:
            return existing
    return None


def validate_new_profile_name(presets, name, current=None):
    """Return ``(clean_name, error)`` for a new or renamed profile."""
    clean, error = normalize_profile_name(name)
    if error:
        return None, error
    clash = profile_name_conflict(presets, clean, ignore=current)
    if clash is not None:
        return None, "A profile named '{}' already exists (names ignore upper/lower case).".format(clash)
    return clean, None


def profile_id_of(data):
    value = str((data or {}).get("profile_id") or "").strip()
    return value if _PROFILE_ID_RE.match(value) else ""


def ensure_profile_ids(presets):
    """Give every profile a unique stable id and move old Main/Side settings.

    Returns True when anything changed. Old configs have no ``profile_id``;
    and ``main_account_id`` used to be the only way to mark an alt account,
    so a profile with it and no explicit role becomes a Side of that Discord
    user (the id keeps working; the Main is matched by its user id at run
    time until a Main profile is picked in the editor).
    """
    changed = False
    seen = set()
    for _name, data in (presets or {}).items():
        if not isinstance(data, dict):
            continue
        profile_id = profile_id_of(data)
        if not profile_id or profile_id in seen:
            profile_id = new_profile_id()
            while profile_id in seen:
                profile_id = new_profile_id()
            data["profile_id"] = profile_id
            changed = True
        seen.add(profile_id)
        if "account_role" not in data:
            legacy_main = str(data.get("main_account_id") or "").strip()
            data["account_role"] = ACCOUNT_ROLE_SIDE if legacy_main else ACCOUNT_ROLE_MAIN
            changed = True
        for key, default in ACCOUNT_ROLE_DEFAULTS.items():
            if key not in data:
                data[key] = default
                changed = True
    return changed


def profile_name_for_id(presets, profile_id):
    if not profile_id:
        return None
    for name, data in (presets or {}).items():
        if isinstance(data, dict) and profile_id_of(data) == profile_id:
            return name
    return None


def rename_profile(presets, old_name, new_name):
    """Rename a profile in place, keeping its order, id and every setting.

    References between profiles use the stable ``profile_id`` so nothing
    else in ``presets`` changes. Returns the clean new name; raises
    ``KeyError`` for an unknown profile and ``ValueError`` for a bad name.
    """
    if old_name not in presets:
        raise KeyError(old_name)
    clean, error = validate_new_profile_name(presets, new_name, current=old_name)
    if error:
        raise ValueError(error)
    if clean == old_name:
        return clean
    items = list(presets.items())
    presets.clear()
    for name, data in items:
        presets[clean if name == old_name else name] = data
    return clean


def _setting_int_in_range(data, key, default, minimum, maximum, errors, label):
    value = data.get(key, default)
    if isinstance(value, bool):
        errors.append("{} must be a whole number from {} to {}.".format(label, minimum, maximum))
        return None
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        errors.append("{} must be a whole number from {} to {}.".format(label, minimum, maximum))
        return None
    if not minimum <= number <= maximum:
        errors.append("{} must be a whole number from {} to {}.".format(label, minimum, maximum))
        return None
    return number


def validate_account_role_settings(data):
    """Errors in one profile's own role/hand-off fields."""
    errors = []
    role = data.get("account_role", ACCOUNT_ROLE_MAIN)
    if role not in ACCOUNT_ROLES:
        errors.append("Account role must be main or side.")
    main_profile_id = data.get("main_profile_id", "")
    if main_profile_id not in (None, "") and not _PROFILE_ID_RE.match(str(main_profile_id)):
        errors.append("Main profile must be one of your profiles.")
    if main_profile_id and main_profile_id == profile_id_of(data):
        errors.append("A side account cannot be its own main.")
    _setting_int_in_range(data, "side_order", 1, 1, 999, errors, "Side order")
    _setting_int_in_range(
        data, "side_rolls_max_per_reset", 1, 1, SIDE_ROLLS_MAX_PER_RESET_LIMIT, errors,
        "Max side accounts per reset",
    )
    return errors


def resolve_account_roles(presets):
    """Effective role of every profile, with the reason when a Side falls back.

    Returns ``{name: {"role": "main"|"side"|"ordinary", "main": name|None,
    "main_profile_id": id, "main_account_id": str, "reason": str|None,
    "error": bool}}``. A Side whose Main is missing runs as an ordinary
    account; a Side pointing at itself or at another Side is an error (and
    also runs as an ordinary account if it is started anyway). A Side with
    only a legacy ``main_account_id`` keeps that id as its Main.
    """
    presets = presets or {}
    by_id = {}
    for name, data in presets.items():
        if isinstance(data, dict) and profile_id_of(data):
            by_id[profile_id_of(data)] = name
    result = {}
    for name, data in presets.items():
        data = data if isinstance(data, dict) else {}
        role = data.get("account_role", ACCOUNT_ROLE_MAIN)
        legacy_main = str(data.get("main_account_id") or "").strip()
        entry = {"role": ACCOUNT_ROLE_MAIN, "main": None, "main_profile_id": "",
                 "main_account_id": legacy_main, "reason": None, "error": False}
        if role != ACCOUNT_ROLE_SIDE:
            result[name] = entry
            continue
        main_profile_id = str(data.get("main_profile_id") or "").strip()
        if main_profile_id:
            main_name = by_id.get(main_profile_id)
            if main_profile_id == profile_id_of(data):
                entry.update(role="ordinary", error=True,
                             reason="A side account cannot be its own main; it runs as an ordinary account.")
            elif main_name is None:
                entry.update(role="ordinary",
                             reason="Its main profile no longer exists; it runs as an ordinary account.")
            elif (presets.get(main_name) or {}).get("account_role", ACCOUNT_ROLE_MAIN) == ACCOUNT_ROLE_SIDE:
                entry.update(role="ordinary", error=True, main=main_name,
                             reason="Its main '{}' is itself a side account; pick a main account.".format(main_name))
            else:
                entry.update(role=ACCOUNT_ROLE_SIDE, main=main_name, main_profile_id=main_profile_id)
        elif legacy_main:
            entry.update(role=ACCOUNT_ROLE_SIDE)
        else:
            entry.update(role="ordinary",
                         reason="No main profile is picked; it runs as an ordinary account.")
        result[name] = entry
    return result


def account_role_errors(presets, name):
    """Blocking cross-profile errors for one profile (self or side as main)."""
    info = resolve_account_roles(presets).get(name)
    return [info["reason"]] if info and info["error"] else []


def side_profiles_for(presets, main_name):
    """The Side profile names of one Main, in their configured order."""
    main_data = (presets or {}).get(main_name) or {}
    main_id = profile_id_of(main_data)
    if not main_id:
        return []
    roles = resolve_account_roles(presets)
    sides = []
    for index, (name, data) in enumerate((presets or {}).items()):
        info = roles.get(name) or {}
        if info.get("role") == ACCOUNT_ROLE_SIDE and info.get("main_profile_id") == main_id:
            try:
                order = int((data or {}).get("side_order", 1))
            except (TypeError, ValueError):
                order = 1
            sides.append((order, index, name))
    return [name for _order, _index, name in sorted(sides)]
