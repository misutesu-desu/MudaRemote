"""Small per-account state that must survive restarts, renames and config reloads.

Kept in its own JSON file beside the runtime data (never in the preset), keyed
by the account's stable key ``"<profile_id>#<account index>"`` (see
``totals.account_key``), so renaming a profile, reloading its settings or a
live apply on Android never loses it. Holds the «Fast setup» done marks and
the per-day count of automatic kakera gives.
"""

import datetime
import json
import os
import threading

from .config import atomic_write_json

STATE_FILE_NAME = "mudafork_account_state.json"
_STATE_VERSION = 1


def default_state_path(base_dir=None):
    """Android's runtime home (app files dir) when set, else ``base_dir`` (beside presets.json)."""
    base = os.environ.get("MUDAREMOTE_RUNTIME_HOME") or base_dir or os.getcwd()
    return os.path.join(base, STATE_FILE_NAME)


class AccountStateStore:
    """Thread-safe JSON store ``{"version": 1, "accounts": {key: {...}}}``."""

    def __init__(self, path):
        self.path = path
        self._lock = threading.Lock()
        self._data = None

    def _load_locked(self):
        if self._data is not None:
            return self._data
        data = {"version": _STATE_VERSION, "accounts": {}}
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                loaded = json.load(handle)
            if isinstance(loaded, dict) and isinstance(loaded.get("accounts"), dict):
                data["accounts"] = {
                    str(key): value for key, value in loaded["accounts"].items() if isinstance(value, dict)
                }
        except (OSError, ValueError):
            pass
        self._data = data
        return data

    def _save_locked(self):
        atomic_write_json(self.path, self._data, indent=2)

    def reload(self):
        with self._lock:
            self._data = None
            self._load_locked()

    def get(self, key, section):
        with self._lock:
            value = self._load_locked()["accounts"].get(key, {}).get(section)
            return json.loads(json.dumps(value)) if value is not None else None

    def put(self, key, section, value):
        with self._lock:
            accounts = self._load_locked()["accounts"]
            entry = accounts.setdefault(key, {})
            if value is None:
                entry.pop(section, None)
                if not entry:
                    accounts.pop(key, None)
            else:
                entry[section] = value
            self._save_locked()

    # -- daily give counter ---------------------------------------------
    def gives_today(self, key, day: datetime.date) -> int:
        record = self.get(key, "kakera_gives") or {}
        return int(record.get("count", 0)) if record.get("day") == day.isoformat() else 0

    def count_give(self, key, day: datetime.date) -> int:
        count = self.gives_today(key, day) + 1
        self.put(key, "kakera_gives", {"day": day.isoformat(), "count": count})
        return count
