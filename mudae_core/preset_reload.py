"""Saved preset polling without replacing a connected client's runtime state."""

import asyncio
import copy
import json
import math

from .config import validate_preset


# These settings establish account, channel, scheduler or loot lifecycles.
RESTART_ONLY_KEYS = frozenset({
    "channel_id", "command_channel_id", "forcedivorce_channel_id",
    "claim_interval", "roll_interval", "server_reset_minute", "rolling",
    "loot_mode", "kl_amount", "scrap_target_id", "scrap_amount",
    "loot_min_cooldown", "loot_max_cooldown", "start_delay", "skip_initial_commands",
})
PRIVATE_KEYS = frozenset({"token", "tokens", "additional_tokens", "persistent_stagger_seconds"})
LIFECYCLE_DEFAULTS = {
    "prefix": "/////////////", "mudae_prefix": "$", "roll_command": "wa",
    "min_kakera": 100, "delay_seconds": 0, "claim_interval": 180,
    "roll_interval": 60, "max_dk_power": 100,
}


def clean_preset(data):
    if not isinstance(data, dict):
        raise ValueError("Preset must be a JSON object.")
    return copy.deepcopy({
        key: value for key, value in data.items()
        if key not in PRIVATE_KEYS and not key.startswith("_")
    })


def normalize_preset(data):
    return {**LIFECYCLE_DEFAULTS, **clean_preset(data)}


def validate_live_preset(data):
    try:
        normalized = normalize_preset(data)
        errors = validate_preset(normalized, resolved_token="active-session")
        for key in (
            "wishlist", "series_wishlist", "avoid_list", "character_snipe_targets",
            "kakera_reaction_snipe_targets", "auto_divorce_series",
            "auto_divorce_blacklist", "auto_divorce_blacklist_series",
        ):
            value = normalized.get(key, [])
            if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                errors.append("{} must be a list of text values.".format(key))
        # JSON can contain NaN/Infinity in Python; neither is a usable timer or
        # threshold, even where the legacy draft validator accepts it.
        def finite(value):
            if isinstance(value, dict):
                return all(finite(item) for item in value.values())
            if isinstance(value, (list, tuple)):
                return all(finite(item) for item in value)
            return not isinstance(value, float) or math.isfinite(value)
        if not finite(normalized):
            errors.append("Preset numbers must be finite.")
        return errors
    except (TypeError, ValueError, AttributeError, OverflowError):
        return ["Preset contains invalid setting types."]


class LivePresetReload:
    """Owned by one client event loop; invalid saves never replace live state."""

    def __init__(self, client, initial, apply, log, *, path=None, name=None):
        self.client = client
        self.initial = normalize_preset(initial)
        self.seen = self.initial
        self.pending = None
        self.apply = apply
        self.log = log
        self.path = path
        self.name = name
        self.read_failed = False

    def restart_required(self, data):
        candidate = normalize_preset(data)
        return sorted(key for key in RESTART_ONLY_KEYS
                      if candidate.get(key) != self.initial.get(key))

    def offer(self, data):
        candidate = normalize_preset(data)
        if candidate != self.seen:
            self.seen = candidate
            self.pending = candidate

    def _read(self):
        with open(self.path, encoding="utf-8") as handle:
            presets = json.load(handle)
        if not isinstance(presets, dict):
            raise ValueError("Preset file must contain an object.")
        return presets.get(self.name)

    def busy(self):
        # Let current transactions complete with the settings they started with.
        if not getattr(self.client, "_live_preset_ready", False):
            return True
        loot = getattr(self.client, "loot_automation", None)
        if loot is not None and getattr(loot, "_queue", None) is not None:
            return True
        if any(getattr(self.client, name, False) for name in (
            "is_processing_cycle", "is_actively_rolling", "is_claiming",
            "_us_in_flight", "_rt_command_in_flight",
        )):
            return True
        for name in ("_sphere_game_lock", "_kakera_action_lock", "_farm_release_lock"):
            lock = getattr(self.client, name, None)
            if lock is not None and lock.locked():
                return True
        return False

    async def poll_once(self):
        if self.path:
            try:
                data = await asyncio.get_running_loop().run_in_executor(None, self._read)
                if data is not None:
                    self.offer(data)
                self.read_failed = False
            except (OSError, ValueError, TypeError):
                if not self.read_failed:
                    self.log("Preset reload: saved settings could not be read; keeping active settings.", "WARN")
                self.read_failed = True
        if self.pending is None or self.busy():
            return
        candidate, self.pending = self.pending, None
        errors = validate_live_preset(candidate)
        if errors:
            self.log("Preset reload rejected: " + " | ".join(errors), "WARN")
            return
        restart = self.restart_required(candidate)
        effective = copy.deepcopy(candidate)
        for key in RESTART_ONLY_KEYS:
            if key in self.initial:
                effective[key] = self.initial[key]
            else:
                effective.pop(key, None)
        try:
            changed = self.apply(effective)
        except (TypeError, ValueError, AttributeError, OverflowError):
            self.log("Preset reload rejected: invalid setting values; keeping active settings.", "WARN")
            return
        if changed:
            self.log("Saved preset changes applied without restarting the bot.", "INFO")
        if restart:
            self.log("These saved settings require a restart: " + ", ".join(restart), "WARN")
