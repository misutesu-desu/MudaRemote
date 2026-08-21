import sys
import asyncio
import discord
from discord.ext import commands
import re
import json
import threading
import datetime
from datetime import timezone
import logging
import time
import random
import os
import requests
import subprocess
import traceback
import hashlib
import tempfile
import shutil
from typing import Tuple


def _bootstrap_modular_core():
    """Bridge legacy two-file updaters to the first modular release."""
    base_path = os.path.dirname(os.path.abspath(__file__))
    manifest_response = requests.get(
        "https://raw.githubusercontent.com/misutesu-desu/MudaRemote/refs/heads/main/version.json",
        timeout=15,
    )
    manifest_response.raise_for_status()
    entries = list(manifest_response.json().get("source_files", []))
    required = {
        "mudae_bot.py", "mudae_preset_editor.py", "mudae_core/__init__.py",
        "mudae_core/claiming.py", "mudae_core/config.py", "mudae_core/coordinator.py",
        "mudae_core/kakera.py", "mudae_core/runtime.py", "mudae_core/secrets.py",
        "mudae_core/status.py", "mudae_core/spheres.py", "mudae_core/filters.py",
        "mudae_core/webhooks.py", "mudae_core/updater.py", "mudae_core/versioning.py",
    }
    if not required.issubset({entry.get("path") for entry in entries}):
        raise RuntimeError("The modular core manifest is incomplete.")

    stage_dir = tempfile.mkdtemp(prefix="mudae-bootstrap-", dir=base_path)
    try:
        for entry in entries:
            relative_path = os.path.normpath(str(entry["path"]).replace("/", os.sep))
            if os.path.isabs(relative_path) or os.pardir in relative_path.split(os.sep):
                raise RuntimeError("Unsafe source path in update manifest.")
            content_response = requests.get(entry["url"], timeout=30)
            content_response.raise_for_status()
            content = content_response.content
            if hashlib.sha256(content).hexdigest().lower() != str(entry.get("sha256", "")).lower():
                raise RuntimeError("Core checksum verification failed for {}.".format(relative_path))
            staged_path = os.path.join(stage_dir, relative_path)
            os.makedirs(os.path.dirname(staged_path), exist_ok=True)
            with open(staged_path, "wb") as handle:
                handle.write(content)
        backup_dir = tempfile.mkdtemp(prefix="mudae-bootstrap-backup-", dir=base_path)
        replaced = []
        try:
            for entry in entries:
                relative_path = os.path.normpath(str(entry["path"]).replace("/", os.sep))
                destination = os.path.join(base_path, relative_path)
                backup = os.path.join(backup_dir, relative_path)
                os.makedirs(os.path.dirname(destination), exist_ok=True)
                if os.path.exists(destination):
                    os.makedirs(os.path.dirname(backup), exist_ok=True)
                    shutil.copy2(destination, backup)
                os.replace(os.path.join(stage_dir, relative_path), destination)
                replaced.append(relative_path)
        except Exception:
            for relative_path in reversed(replaced):
                destination = os.path.join(base_path, relative_path)
                backup = os.path.join(backup_dir, relative_path)
                if os.path.exists(backup):
                    os.replace(backup, destination)
                elif os.path.exists(destination):
                    os.remove(destination)
            raise
        finally:
            shutil.rmtree(backup_dir, ignore_errors=True)
    finally:
        shutil.rmtree(stage_dir, ignore_errors=True)


try:
    from mudae_core import (
        ClaimCoordinator, ClaimOutcome, CommandPacer, GlobalIntervalCoordinator, SecretStore, ServerResetCoordinator, UpdateError, apply_update,
        active_stagger_seconds, can_resume_claim_interrupted_rolls, can_spend_restore_on_character, calculate_kakera_power_cost, classify_claim_owner, classify_claim_text, clear_status_dirty,
        consume_tu_urgent_bypass,
        cooldown_deadline, defer_tu_queries, format_update_changelog, harvest_reveal_is_free, has_free_claim_button, initialize_status_tracking,
        is_claim_announcement_for_character,
        is_newer_version, looks_like_tu_status_snapshot,
        humanized_claim_refresh_deadline, mark_status_dirty, pause_interruptible_sleep, prepare_active_presets, record_tu_failure,
        record_tu_success, reconcile_shared_claim_deadline, reconcile_shared_roll_deadline, roll_reset_wait_minutes, rolls_usage_is_active, set_client_paused, status_dirty_fields, parse_claim_denied_cooldown,
        status_message_addresses_identity, status_refresh_reasons, split_command_batches, tu_cache_seconds_remaining, tu_retry_wait, has_perk_eight_discount,
        find_refreshed_component_button, get_kakera_emoji_targets, get_regular_kakera_filter_reason, has_op_perk_five_marker,
        has_purple_kakera_button, is_character_sphere_emoji, kakera_embed_text,
        KakeraPowerLedger, mudae_command_ack_matches, normalize_character_sphere_emoji, parse_kakera_result, queued_kakera_sort_key,
        should_refill_kakera_power, sphere_target_matches,
        choose_chest_position, choose_harvest_position, count_harvest_bonus_clicks,
        normalize_sphere_emoji, parse_sphere_game_status, WebhookDispatcher,
        character_series_line, name_or_series_is_configured_wish, series_line_has_emoji,
    )
    from mudae_core.config import atomic_write_json, load_json, validate_preset
except (ModuleNotFoundError, ImportError) as core_error:
    missing_module = str(getattr(core_error, "name", ""))
    if missing_module and not missing_module.startswith("mudae_core"):
        raise
    if not missing_module and "mudae_core" not in str(core_error):
        raise
    _bootstrap_modular_core()
    import importlib
    importlib.invalidate_caches()
    for loaded_module in list(sys.modules):
        if loaded_module == "mudae_core" or loaded_module.startswith("mudae_core."):
            sys.modules.pop(loaded_module, None)
    from mudae_core import (
        ClaimCoordinator, ClaimOutcome, CommandPacer, GlobalIntervalCoordinator, SecretStore, ServerResetCoordinator, UpdateError, apply_update,
        active_stagger_seconds, can_resume_claim_interrupted_rolls, can_spend_restore_on_character, calculate_kakera_power_cost, classify_claim_owner, classify_claim_text, clear_status_dirty,
        consume_tu_urgent_bypass,
        cooldown_deadline, defer_tu_queries, format_update_changelog, harvest_reveal_is_free, has_free_claim_button, initialize_status_tracking,
        is_claim_announcement_for_character,
        is_newer_version, looks_like_tu_status_snapshot,
        humanized_claim_refresh_deadline, mark_status_dirty, pause_interruptible_sleep, prepare_active_presets, record_tu_failure,
        record_tu_success, reconcile_shared_claim_deadline, reconcile_shared_roll_deadline, roll_reset_wait_minutes, rolls_usage_is_active, set_client_paused, status_dirty_fields, parse_claim_denied_cooldown,
        status_message_addresses_identity, status_refresh_reasons, split_command_batches, tu_cache_seconds_remaining, tu_retry_wait, has_perk_eight_discount,
        find_refreshed_component_button, get_kakera_emoji_targets, get_regular_kakera_filter_reason, has_op_perk_five_marker,
        has_purple_kakera_button, is_character_sphere_emoji, kakera_embed_text,
        KakeraPowerLedger, mudae_command_ack_matches, normalize_character_sphere_emoji, parse_kakera_result, queued_kakera_sort_key,
        should_refill_kakera_power, sphere_target_matches,
        choose_chest_position, choose_harvest_position, count_harvest_bonus_clicks,
        normalize_sphere_emoji, parse_sphere_game_status, WebhookDispatcher,
        character_series_line, name_or_series_is_configured_wish, series_line_has_emoji,
    )
    from mudae_core.config import atomic_write_json, load_json, validate_preset

if os.name == 'nt':
    import msvcrt
from discord.utils import time_snowflake

try:
    from discord.http import Route
except ImportError:
    Route = None

# Bot Identification
BOT_NAME = "MudaRemote"
CURRENT_VERSION = "4.9.0-beta.6"

IS_TERMUX = "TERMUX_VERSION" in os.environ or ("PREFIX" in os.environ and "com.termux" in os.environ["PREFIX"])

# Global Pause State
_global_paused = False
_active_clients = []
_active_clients_lock = threading.Lock()
_menu_active = threading.Event()
_original_terminal_settings = None

_claim_coordinator = ClaimCoordinator()
_server_reset_coordinator = ServerResetCoordinator()
_tu_interval_coordinator = GlobalIntervalCoordinator()
TU_GLOBAL_INTERVAL_SECONDS = 20.0

def _apply_shared_reset_snapshot(client, snapshot):
    """Apply only server-wide reset boundaries, never another user's private state."""
    observed_at = getattr(snapshot, "observed_at_utc", None)
    claim_deadline = getattr(snapshot, "claim_reset_at_utc", None)
    roll_deadline = getattr(snapshot, "roll_reset_at_utc", None)

    if observed_at is None:
        return

    previous_observation = getattr(client, "_shared_reset_observed_at_utc", None)
    if previous_observation is not None and observed_at < previous_observation:
        return
    client._shared_reset_observed_at_utc = observed_at

    observed_fields = getattr(snapshot, "observed_fields", frozenset())
    previous_roll_deadline = getattr(client, "roll_reset_at_utc", None)
    if "rolls" in observed_fields and roll_deadline is not None:
        client.roll_reset_at_utc, roll_boundary_advanced = reconcile_shared_roll_deadline(
            previous_roll_deadline,
            observed_at,
            roll_deadline,
        )
        if roll_boundary_advanced:
            # Saved-roll limits are private account state, but their cycle is
            # the shared server roll hour. A peer may advance this deadline
            # before this account's own $tu arrives, so reset the local usage
            # counters at the observed boundary instead of waiting for a later
            # deadline comparison that will now look unchanged.
            client.us_pulled_this_cycle = 0
            client.us_failed_this_cycle = False
            client._us_retry_after = 0.0
        # A server peer can tell us that a new roll hour has started, but it
        # cannot tell us this account's private roll count.  If this account
        # had already exhausted its rolls at the old boundary, its cached zero
        # must not be carried into the newly announced hour.
        if (
            getattr(client, "rolling_enabled", False)
            and
            roll_boundary_advanced
            and int(getattr(client, "rolls_left", 0) or 0) <= 0
        ):
            mark_status_dirty(client, {"rolls"}, reason="shared-roll-boundary", urgent=True)
            event = getattr(client, "_immediate_check_event", None)
            if event is not None:
                event.set()

    if "claim" not in observed_fields or claim_deadline is None or getattr(client, "pending_claim", None) is not None:
        return

    current_deadline = getattr(client, "next_claim_reset_at_utc", None)
    claimed_character = getattr(client, "last_successfully_claimed_character", None)
    if (
        current_deadline is not None
        and claimed_character
        and current_deadline > claim_deadline + datetime.timedelta(minutes=1)
    ):
        # This account claimed after the shared snapshot was produced. Its
        # later local deadline must not be moved backwards by stale evidence.
        return

    claim_deadline, claim_boundary_elapsed = reconcile_shared_claim_deadline(
        current_deadline,
        observed_at,
        claim_deadline,
        getattr(client, "claim_right_available", False),
    )
    if claim_boundary_elapsed:
        mark_status_dirty(client, {"claim"}, reason="shared-claim-boundary", urgent=True)

    client.next_claim_reset_at_utc = claim_deadline
    if not getattr(client, "claim_right_available", False):
        client.claim_cooldown_until_utc = claim_deadline

    old_handle = getattr(client, "_shared_claim_reset_handle", None)
    if old_handle is not None and not old_handle.cancelled():
        old_handle.cancel()

    def unlock_at_shared_boundary():
        client._shared_claim_reset_handle = None
        if getattr(client, "pending_claim", None) is not None:
            return
        current = getattr(client, "next_claim_reset_at_utc", None)
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        if current is None or abs((current - claim_deadline).total_seconds()) > 1.0 or now_utc < current:
            return
        mark_status_dirty(client, {"claim"}, reason="shared-claim-boundary", urgent=True)
        # A shared reset tells us only that the server boundary has passed.
        # Do not wake a sleeping status loop here: in snipe-only mode that
        # would cut short the configured post-reset humanization delay and
        # send $tu at the exact reset.  The already scheduled local refresh
        # will consume this dirty state at its intended time.

    loop = getattr(client, "loop", None)
    if loop is not None and loop.is_running():
        delay = max(
            0.0,
            (claim_deadline - datetime.datetime.now(datetime.timezone.utc)).total_seconds(),
        )
        client._shared_claim_reset_handle = loop.call_later(delay, unlock_at_shared_boundary)

class BotLogger:
    _file_lock = threading.Lock()
    _max_log_bytes = 5 * 1024 * 1024
    _backup_count = 3
    COLORS = {
        "INFO": "\033[94m", "CLAIM": "\033[92m", "KAKERA": "\033[93m",
        "ERROR": "\033[91m", "CHECK": "\033[95m", "RESET": "\033[36m",
        "WARN": "\033[33m", "ENDC": "\033[0m"
    }
    PREFIXES = {
        "INFO":   "ℹ️  [INFO]   ", "CLAIM":  "💖 [CLAIM]  ", "KAKERA": "💎 [KAKERA] ",
        "ERROR":  "❌ [ERROR]  ", "CHECK":  "🔍 [CHECK]  ", "RESET":  "🔄 [RESET]  ",
        "WARN":   "⚠️  [WARN]   "
    }
    DEBUG_CATEGORY_PATTERNS = {
        "claim": ("claim", "wishlist", "wish", "divorce", "$rt", "forcedivorce"),
        "kakera": ("kakera", "$mk", "$dk", "power", "react"),
        "roll": ("roll", "$us", "key mode", "panic"),
        "status": ("$tu", "status", "reset", "cooldown", "available"),
        "sphere": ("sphere", "$oh", "$oc", "harvest", "chest"),
        "coordination": ("coordinator", "stagger", "preset", "account"),
    }

    @classmethod
    def _debug_category(cls, message):
        lowered = str(message or "").casefold()
        for category, markers in cls.DEBUG_CATEGORY_PATTERNS.items():
            if any(marker in lowered for marker in markers):
                return category
        return "other"

    @classmethod
    def log(cls, message, preset_name="MudaRemote", log_type="INFO", client=None):
        original_log_type = str(log_type or "INFO").upper()
        if original_log_type == "DEBUG" and not getattr(client, 'debug_mode', False):
            return
        if original_log_type == "DEBUG":
            allowed_categories = set(getattr(client, "debug_log_categories", ()) or ())
            category = cls._debug_category(message)
            if allowed_categories and "all" not in allowed_categories and category not in allowed_categories:
                return
        log_type_upper = original_log_type
        msg_clean = re.sub(r"^\[[^\]]+\]\s*", "", message)
        if log_type_upper == "DEBUG":
            msg_clean = f"[DEBUG] {msg_clean}"
            log_type_upper = "INFO"

        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        preset_aligned = f"[{preset_name[:12]:<12}]"
        prefix = cls.PREFIXES.get(log_type_upper, "ℹ️  [INFO]   ")
        formatted = f"[{timestamp}] {preset_aligned} {prefix} {msg_clean}"

        color_code = cls.COLORS.get(log_type_upper, cls.COLORS["INFO"])
        console_line = f"{color_code}{formatted}{cls.COLORS['ENDC']}"
        try:
            print(console_line)
        except UnicodeEncodeError:
            encoding = getattr(sys.stdout, "encoding", None) or "ascii"
            print(console_line.encode(encoding, errors="replace").decode(encoding, errors="replace"))
        try:
            logs_path = os.path.join(get_base_path(), "logs.txt")
            with cls._file_lock:
                if os.path.exists(logs_path) and os.path.getsize(logs_path) >= cls._max_log_bytes:
                    for index in range(cls._backup_count, 0, -1):
                        source = logs_path if index == 1 else "{}.{}".format(logs_path, index - 1)
                        destination = "{}.{}".format(logs_path, index)
                        if os.path.exists(source):
                            os.replace(source, destination)
                with open(logs_path, "a", encoding='utf-8') as f:
                    f.write(formatted + "\n")
        except Exception:
            pass
        webhook_types = set(getattr(client, "webhook_log_types", ()) or ())
        if (
            getattr(client, "webhook_url", "")
            and (not webhook_types or "ALL" in webhook_types or original_log_type in webhook_types)
        ):
            WebhookDispatcher.enqueue(client.webhook_url, formatted)

REGEX_PATTERNS = {
    "KEYS": r'(?:🔑|<:(?:chaos)?key:\d+>)\s*\(\*?\*?([\d,.]+)\*?\*?\)',
    "OWNER": r'(?:[Bb]elongs to|[Pp]ertence a|[Pp]ertenece a|[Aa]ppartient [àa])\s+(.+?)$',
    "CLAIMS_RANK": r"Claims:\s*#\s*([\d,.]+)",
    "LIKES_RANK": r"Likes:\s*#\s*([\d,.]+)",
    "DK_STOCK": r"\**(\d+)\**\s*\$dk\s*(?:available|dispon[ií]ve(?:l|is)|no estoque|disponible|en stock|disponibles?)",
    "DK_READY": r"\$dk.*?(?:ready|pronto|disponible|prêt|dispon[ií]vel|listo)",
    "DK_COOLDOWN": r"(?:next \$dk|próximo \$dk|siguiente \$dk|prochain \$dk).*?\*{0,2}(\d+h)?\s*(\d+)\*{0,2}\s*min",
    "DK_POWER": r"(?:power|poder):\s*\*{0,2}(\d+)%\*{0,2}",
    "DK_CONSUMPTION": r"(?:each kakera (?:reaction|button) consumes|cada (?:reação|botão|botón) de kakera consume|chaque bouton kakera consomme)\s*(\d+)%",
    "P_COOLDOWN": r"(?:next \$p|próximo \$p|prochain \$p).*?\*{0,2}(\d+h)?\s*(\d+)\*{0,2}\s*min",
    "RT_RESET": r"(?:\$rt|recarga|enfriamiento|cool).*?(?:\:|in|em|en|dans|left|restante|restam|falta|tiempo|temps|tempo|restantes|restant)\s*:?\s*\*{0,2}(\d+h)?\s*(\d+)\*{0,2}\s*min",
    "CLAIM_READY": r"(?:(?:you\s+)?_{0,2}(?:can|pode|puedes|pouvez)_{0,2}\s+(?:claim|se casar|reclamar|vous (?:re)?marier)|(?:claim|marry|casamento|reclamo|mariage).*?(?:is\s+)?(?:ready|available|pronto|dispon[ií]vel|disponible|prêt))",
    "CLAIM_RESET": r"(?:next claim|próximo|siguiente|prochain|tempo|temps|falta)\s+(?:reset|reclamo|tempo|temps|um tempo).*?(?:in|em|en|dans|left|restante|restant|falta|dentro de)\s*:?\s*\*{0,2}(\d+h)?\s*(\d+)\*{0,2}\s*min",
    "CLAIM_COOLDOWN": r"(?:can't|não pode|no puedes|avant de|falta\s+um\s+tempo).*?(?:claim|casar|reclamar|remarier).*?\*{0,2}(\d+h)?\s*(\d+)\*{0,2}\s*min",
    "CLAIM_INTERVAL_COOLDOWN": r"(?:next interval begins in|intervalo comienza en|intervalo começa em|intervalle commence dans)\s*\*{0,2}(\d+h)?\s*(\d+)\*{0,2}\s*min",
    "GENERIC_COOLDOWN": r"\*{0,2}(\d+h)?\s*(\d+)\*{0,2}\s*min",
    "ROLL_RESET": r"(?:reset in|reinicialização é em|siguiente reinicio.*?en|prochain rolls reset dans)\s+\*{0,2}(\d+h)?\*{0,2}\s*\*{0,2}(\d+)\*{0,2}\s*min",
    "KAKERA_COOLDOWN": r"(?:react|pegar|reaccionar).*?\*{0,2}(\d+h)?\s*(\d+)\*{0,2}\s*min",
    "MK_BONUS": r"\(\+\*{0,2}([\d,.]+)\*{0,2}\s+\$mk\)",
    "ROLLS_COUNT": r"(?:you have|vous avez|tienes|você tem)\s+\*{0,2}([\d,.]+)\*{0,2}\s+rolls?(.*?)(?:left|restantes?|restants?\b)",
    "BONUS_ROLLS": r"\(\+\*{0,2}([\d,.]+)\*{0,2}\s+\$(us|mk)\)",
    "ROLL_RESET_TU": r"(?:reset|reinicialização|reinicio).*?(?:in|em|en|dans)\s+(?:.*?)\*{0,2}(\d+h)?\*{0,2}\s*\*{0,2}(\d+)\*{0,2}\s*min",
    "KAKERA_EARNED": r"\+(\d+)\s*<:kakera:",
    "BOLD_TEXT": r"\*\*(.+?)\*\*",
    "KAKERA_VALUE": r"\**([\d,.]+)\**<:kakera:",
    "MAINTENANCE": r"For\s+(?:some|(\d+))\s+minutes",
    "EXTRA_ROLLS": r"\+\**(\d+)\**\s*rolls?",
    "USER_BOLD": r"^\s*\*\*([^*]+)\*\*"
}

def parse_hm(m):
    if not m: return 0, 0
    h_s, m_s = m.groups(default="")
    return (int(re.sub(r"\D", "", h_s)) if h_s else 0), (int(re.sub(r"\D", "", m_s)) if m_s else 0)

def parse_timer_minutes(pattern_name, text):
    m = re.search(REGEX_PATTERNS[pattern_name], text, re.IGNORECASE)
    if not m: return None
    h, m_val = parse_hm(m)
    return h * 60 + m_val

def first_configured(mapping, *keys):
    """Return the first explicitly configured value, preserving valid zeroes."""
    for key in keys:
        if key in mapping:
            return mapping[key]
    return None

def print_log(message, preset_name, log_type="INFO"):
    BotLogger.log(message, preset_name, log_type)

def print_system_log(message, log_type="INFO"):
    BotLogger.log(message, BOT_NAME, log_type)

def _debug_log_global(client_ref, log_func, preset, message):
    BotLogger.log(message, preset, "DEBUG", client_ref)

def get_base_path():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


MUDAE_EMOJI_ASSET_DIR = os.path.join(get_base_path(), "mudae_emoji_assets")
_mudae_emoji_asset_tasks = set()


async def cache_mudae_emoji_asset(emoji):
    """Store a real Mudae custom emoji locally for the preset editor."""
    name = str(getattr(emoji, "name", "") or "")
    emoji_id = getattr(emoji, "id", None)
    if not emoji_id or not re.fullmatch(r"(?:kakera|sp)[A-Za-z0-9]*", name):
        return

    destination = os.path.join(MUDAE_EMOJI_ASSET_DIR, f"{name}.png")
    if os.path.isfile(destination):
        return

    os.makedirs(MUDAE_EMOJI_ASSET_DIR, exist_ok=True)
    url = f"https://cdn.discordapp.com/emojis/{emoji_id}.png?size=64&quality=lossless"

    def download():
        response = requests.get(url, timeout=(3.05, 10))
        response.raise_for_status()
        temporary = f"{destination}.tmp"
        with open(temporary, "wb") as handle:
            handle.write(response.content)
        os.replace(temporary, destination)

    try:
        await asyncio.to_thread(download)
    except Exception:
        # The picker retains its built-in colour fallback if Discord's CDN is
        # unavailable or a custom emoji has been removed.
        return


def schedule_mudae_emoji_asset_cache(client, message):
    """Cache real button artwork without delaying roll/claim handling."""
    for component in getattr(message, "components", ()) or ():
        for button in getattr(component, "children", ()) or ():
            emoji = getattr(button, "emoji", None)
            name = str(getattr(emoji, "name", "") or "")
            if not re.fullmatch(r"(?:kakera|sp)[A-Za-z0-9]*", name):
                continue
            task_key = (getattr(emoji, "id", None), name)
            if not task_key[0] or task_key in _mudae_emoji_asset_tasks:
                continue
            _mudae_emoji_asset_tasks.add(task_key)
            task = client.loop.create_task(cache_mudae_emoji_asset(emoji))
            task.add_done_callback(lambda _task, key=task_key: _mudae_emoji_asset_tasks.discard(key))

def _toggle_global_pause():
    global _global_paused
    _global_paused = not _global_paused
    with _active_clients_lock:
        for c in _active_clients:
            set_client_paused(c, _global_paused)
    print_system_log("⏸️  Bot paused. Press 'p' again to resume." if _global_paused else "▶️  Bot resumed. Operations continuing.", "WARN" if _global_paused else "INFO")

def _keyboard_listener_thread():
    if os.name == 'nt':
        while True:
            try:
                if _menu_active.is_set():
                    time.sleep(0.2)
                    continue
                if not msvcrt.kbhit():
                    time.sleep(0.05)
                    continue
                ch = msvcrt.getch()
                if ch in (b'\xe0', b'\x00'):
                    if msvcrt.kbhit(): msvcrt.getch()
                    continue
                if ch in (b'p', b'P'):
                    _toggle_global_pause()
            except Exception:
                time.sleep(5)
    else:
        if IS_TERMUX:
            return
        import tty, termios, select
        global _original_terminal_settings
        try:
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            _original_terminal_settings = old_settings
            try:
                tty.setcbreak(fd)
                while True:
                    if _menu_active.is_set():
                        while _menu_active.is_set():
                            time.sleep(0.1)
                        try:
                            termios.tcflush(fd, termios.TCIFLUSH)
                            tty.setcbreak(fd)
                        except Exception: pass
                        continue
                    if select.select([sys.stdin], [], [], 0.1)[0]:
                        if _menu_active.is_set(): continue
                        ch = sys.stdin.read(1)
                        if ch == '\x1b':
                            while select.select([sys.stdin], [], [], 0.01)[0]: sys.stdin.read(1)
                            continue
                        if ch.lower() == 'p': _toggle_global_pause()
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        except Exception:
            while True: time.sleep(5)

def _start_keyboard_listener():
    t = threading.Thread(target=_keyboard_listener_thread, daemon=True)
    t.start()

try:
    _start_keyboard_listener()
except Exception:
    pass

UPDATE_URL = "https://raw.githubusercontent.com/misutesu-desu/MudaRemote/refs/heads/main/"

def _confirm_update_in_console(latest_version, changelog):
    print(f"\nMudaRemote v{latest_version} is available.\n")
    print("Changelog:")
    print(changelog)
    print()
    if not getattr(sys.stdin, "isatty", lambda: False)():
        print_system_log("Update confirmation is unavailable in this session. Update skipped.", "WARN")
        return False
    try:
        answer = input("Install this update now? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return answer in {"y", "yes"}


def check_for_updates(confirm_update=None):
    if not UPDATE_URL:
        return "disabled"
    is_frozen = getattr(sys, 'frozen', False)
    is_android = os.environ.get("TERMUX_VERSION") == "MudaRemote-Android" or bool(os.environ.get("MUDAREMOTE_RUNTIME_HOME"))
    print_system_log(f"Checking for updates... (Current: v{CURRENT_VERSION}, Mode: {'Android' if is_android else ('EXE' if is_frozen else 'Script')})", "RESET")
    try:
        response = requests.get(f"{UPDATE_URL}version.json", timeout=(3.05, 8.0))
        response.raise_for_status()
        data = response.json()
        latest_version = data.get("version")
        if not latest_version or not is_newer_version(latest_version, CURRENT_VERSION):
            print_system_log("You are up to date.", "INFO")
            return "current"

        changelog = format_update_changelog(data)
        base_path = get_base_path()
        if not is_frozen and not is_android and os.path.isdir(os.path.join(base_path, ".git")):
            print(f"\nChangelog for v{latest_version}:\n{changelog}\n")
            print_system_log(f"v{latest_version} is available. This is a Git checkout; run 'git pull' so local changes are never overwritten.", "WARN")
            return "git"

        confirmation = confirm_update or (
            (lambda v, c: True) if is_android else _confirm_update_in_console
        )
        print_system_log(f"v{latest_version} is available. Waiting for update confirmation.", "RESET")
        if not confirmation(latest_version, changelog):
            print_system_log(f"Update to v{latest_version} was skipped. Your current files and presets were not changed.", "INFO")
            return "skipped"

        if is_android:
            runtime_home = os.environ.get("MUDAREMOTE_RUNTIME_HOME") or os.environ.get("HOME") or base_path
            target_path = os.path.join(runtime_home, "python_code")
            os.makedirs(target_path, exist_ok=True)
            result = apply_update(
                requests,
                data,
                CURRENT_VERSION,
                target_path,
                frozen=False,
                executable=sys.executable,
            )
            with open(os.path.join(target_path, ".version"), "w", encoding="utf-8") as vh:
                vh.write(str(latest_version))
            print_system_log(f"Verified Python source update v{latest_version} applied to Android storage. Will be used on next start.", "INFO")
            return "source"

        result = apply_update(
            requests,
            data,
            CURRENT_VERSION,
            base_path,
            frozen=is_frozen,
            executable=sys.executable,
        )
        if result == "frozen":
            print_system_log("Verified update staged. Restarting via updater...", "RESET")
            os._exit(0)
        print_system_log("Verified full source update applied. Restarting...", "RESET")
        if os.name == 'nt':
            subprocess.Popen([sys.executable] + sys.argv, creationflags=subprocess.CREATE_NEW_CONSOLE)
            sys.exit()
        os.execv(sys.executable, [sys.executable] + sys.argv)
    except UpdateError as e:
        print_system_log(f"Update was not applied safely: {e}", "WARN")
        return "failed"
    except Exception as e:
        print_system_log(f"Update failed: {e}", "ERROR")
        return "failed"

def cleanup_after_update():
    """Compatibility hook retained for older launchers; updates are now transactional."""

presets = {}
presets_path = os.path.join(get_base_path(), "presets.json")
if not os.path.exists(presets_path):
    try:
        atomic_write_json(presets_path, {})
        print_system_log(f"Created missing {presets_path}", "INFO")
    except Exception as e:
        print_system_log(f"Error creating {presets_path}: {e}", "ERROR")

try:
    presets = load_json(presets_path, {})
    _secret_store = SecretStore(get_base_path())
    for _preset_name, _preset_data in presets.items():
        _preset_data["tokens"] = _secret_store.get_tokens(
            _preset_name,
            _preset_data.get("tokens") or _preset_data.get("token", ""),
        )
        _preset_data["token"] = _preset_data["tokens"][0] if _preset_data["tokens"] else ""
except Exception as e:
    print_system_log(f"Failed to load {presets_path}: {e}", "ERROR")
    sys.exit(1)

if os.name == 'nt': os.system('')

TARGET_BOT_ID = 432610292342587392
CLAIM_EMOJIS = ['💖', '💗', '💘', '❤️', '💓', '💕', '♥️']
KAKERA_EMOJIS = ['kakeraY', 'kakeraO', 'kakeraR', 'kakeraW', 'kakeraL', 'kakeraP', 'kakeraD', 'kakeraC', 'kakera']
CHAOS_KAKERA_EMOJIS = ['kakeraY', 'kakeraO', 'kakeraR', 'kakeraW', 'kakeraL', 'kakeraP', 'kakeraD', 'kakeraC', 'kakera']
SPHERE_EMOJIS = ['spP', 'spB', 'spT', 'spG', 'spY', 'spO', 'spR', 'sp', 'spW', 'spL', 'spD', 'spM', 'spP2', 'spB2', 'spT2', 'spG2', 'spY2', 'spO2', 'spR2', 'spW2', 'spL2', 'spD2', 'spU']

async def detect_roll_owner(client, message) -> tuple:
    """
    Detects the owner of a roll message.
    Returns a tuple of (user_id, username_lowercase).
    """
    # 1. If it was rolled via a Slash Command (Interaction)
    interaction = getattr(message, "interaction_metadata", None) or getattr(message, "interaction", None)
    user = getattr(interaction, "user", None)
    if user is not None:
        return user.id, str(user.name).casefold()

    # 2. Fallback for text commands: scan channel history right before this message
    # We look for: $w, $h, $m, $wx, $mx, $hx, $wa, $ha, $ma, $mg, $hg, $wg
    commands = {"w", "h", "m", "wx", "mx", "hx", "wa", "ha", "ma", "mg", "hg", "wg", str(getattr(client, "roll_command", "") or "").strip().lower()}
    commands.discard("")
    pattern = re.compile(r"^\s*" + re.escape(client.mudae_prefix) + r"(?:" + "|".join(map(re.escape, sorted(commands, key=len, reverse=True))) + r")\s*$", re.IGNORECASE)

    try:
        async for msg in message.channel.history(limit=8, before=message):
            if message.created_at and msg.created_at and (message.created_at - msg.created_at).total_seconds() > 10:
                break
            if pattern.fullmatch((msg.content or "").strip()):
                return msg.author.id, msg.author.name.casefold()
    except Exception:
        pass

    # 3. Last fallback: Check embed footer for Mudae ownership text if present
    owner_username = None
    if message.embeds:
        embed = message.embeds[0]
        if embed.footer and embed.footer.text:
            m = re.search(REGEX_PATTERNS["OWNER"], embed.footer.text)
            if m:
                owner_username = m.group(1).strip().casefold()

    return None, owner_username

def check_is_green(b):
    s = getattr(b, 'style', None)
    return s is not None and (getattr(s, 'value', None) == 3 or str(s).endswith('success') or str(s) == '3')

def is_character_embed(embed):
    return bool(embed and embed.author and embed.author.name and embed.image and embed.image.url and not (embed.thumbnail and embed.thumbnail.url))

def is_free_event(embed):
    if not embed or not embed.description: return False
    desc = embed.description.lower()
    return any(k in desc for k in ["it's free!", "é de graça!", "¡es gratis!", "christmas art contest", "new year's contest"])

def has_claim_option(message, embed, claim_emojis):
    if not message.components: return not get_character_owner(embed)
    return any(not getattr(btn, "disabled", False) and getattr(getattr(btn, "emoji", None), "name", None) in claim_emojis for comp in message.components for btn in comp.children)

def count_chaos_keys(embed):
    if not embed or not embed.description: return 0
    matches = re.findall(REGEX_PATTERNS["KEYS"], embed.description, re.IGNORECASE)
    return sum(1 for m in matches if int(re.sub(r"[^\d]", "", m)) >= 10)

def get_character_owner(embed):
    if not embed or not embed.footer or not embed.footer.text: return None
    m = re.search(REGEX_PATTERNS["OWNER"], embed.footer.text)
    return m.group(1).strip().lower() if m else None

def is_wished_by_self(message, client_user_id: int) -> bool:
    return bool(message and message.content and "wished by" in message.content.lower() and client_user_id in [m.id for m in message.mentions])

def parse_mudae_ranks(embed_description: str) -> Tuple[int, int]:
    if not embed_description: return 0, 0
    def get_rank(pattern_name):
        m = re.search(REGEX_PATTERNS[pattern_name], embed_description, re.IGNORECASE)
        return int(m.group(1).replace(",", "").replace(".", "")) if m else 0
    return get_rank("CLAIMS_RANK"), get_rank("LIKES_RANK")

def run_bot(token, prefix, target_channel_id, roll_command, min_kakera, delay_seconds, mudae_prefix,
            log_function, preset_name, key_mode, start_delay, snipe_mode, snipe_delay,
            snipe_ignore_min_kakera_reset, wishlist,
            series_snipe_mode, series_snipe_delay, series_wishlist, roll_speed,
            kakera_snipe_mode_preset, kakera_snipe_threshold_preset,
            enable_reactive_self_snipe_preset, rolling_enabled,
            kakera_reaction_snipe_mode_preset, kakera_reaction_snipe_delay_preset,
            kakera_reaction_snipe_targets,
            character_snipe_targets=None,
            humanization_enabled=False, humanization_window_minutes=0, humanization_inactivity_seconds=0,
            dk_power_management=True, skip_initial_commands=False, use_slash_rolls=False, only_chaos=False,
            reactive_snipe_delay=0.5, time_rolls_to_claim_reset_preset=False,
            rt_ignore_min_kakera_for_wishlist_preset=False,
            claim_emojis_preset=None, kakera_emojis_preset=None, chaos_emojis_preset=None, sphere_perk_emojis_preset=None,
            rt_only_self_rolls_preset=False, reactive_kakera_delay_range_preset=None,
            claim_interval_preset=180, roll_interval_preset=60, avoid_list=None,
            inactive_hours_preset=None,
            auto_us_enabled=False, auto_us_limit=10, auto_us_stop_on_claim=True,
            kakera_power_thresholds=None, debug_mode=False, auto_mk_enabled_preset=False,
            auto_rolls_enabled=False, auto_rolls_limit=10, auto_rolls_in_key_mode=False,
            auto_rolls_only_claim_hour_preset=False,
            panic_roll_minutes_preset=5, lurker_mode_preset=False,
            bulk_us_enabled_preset=False,
            max_dk_power_preset=100,
            randomized_claim_reactions_preset=None,
            main_account_id_preset="",
            scheduled_roll_times_preset=None,
            kakera_priority_order_preset=None,
            auto_rt_after_claim_preset=False,
            mk_only_preset=False,
            auto_dk_enabled_preset=True,
            command_channel_id_preset="",
            enable_snipe_chat_reactions_preset=False,
            snipe_chat_messages_preset=None,
            farm_character_preset="",
            op_perk_5_only_preset=False,
            farm_character_enabled_preset=False,
            auto_divorce_enabled_preset=False,
            auto_divorce_max_kakera_preset=50,
            auto_divorce_series_preset=None,
            auto_divorce_blacklist_preset=None,
            auto_divorce_blacklist_series_preset=None,
            mk_bypass_power_check=False,
            snipe_channels_preset=None,
            max_claim_rank_preset=0,
            max_like_rank_preset=0,
            auto_p_enabled=True,
            enable_hybrid_panic_claim_preset=False,
            hybrid_panic_instant_claim_min_kakera_preset=300,
            hybrid_panic_instant_claim_max_rank_preset=200,
            claim_rounds_thresholds_preset=None,
            persistent_stagger_seconds_preset=0,
            sphere_click_targets_preset=None,
            immediate_kakera_click_preset=True,
            farm_forcedivorce_after_claim_preset=False,
            farm_forcedivorce_before_roll_preset=True,
            farm_forcedivorce_after_other_claim_preset=False,
            auto_oh_enabled_preset=False,
            auto_oc_enabled_preset=False,
            series_snipe_only_self_rolls_preset=False,
            forcedivorce_channel_id_preset="",
            wish_starwish_kakera_only_preset=False,
            auto_mk_full_power_only_preset=False,
            auto_divorce_protect_wishes_preset=True,
            farm_characters_preset=None,
            enable_kakera_snipe_chat_reactions_preset=False,
            kakera_snipe_chat_messages_preset=None,
            oh_priority_order_preset=None,
            oh_unknown_explore_clicks_preset=3,
            oc_reward_priority_order_preset=None,
            oc_collect_after_red_preset=True,
            webhook_url_preset="",
            webhook_log_types_preset=None,
            debug_log_categories_preset=None,
            auto_free_claim_preset=True,
            collect_purple_kakera_preset=True,
            oh_use_individually_preset=False,
            auto_dk_min_power_preset=0,
            kakera_snipe_channels_preset=None):

    client = commands.Bot(command_prefix=prefix, chunk_guilds_at_startup=False, self_bot=True)
    client.is_paused = _global_paused
    client._pause_generation = 1 if _global_paused else 0
    client.command_pacer = CommandPacer(0.6, 0.8)
    with _active_clients_lock: _active_clients.append(client)

    discord_logger = logging.getLogger('discord')
    discord_logger.propagate = False
    handlers = [h for h in discord_logger.handlers if isinstance(h, logging.StreamHandler)]
    for h in handlers:
        discord_logger.removeHandler(h)

    # Bind preset configs
    client.preset_name = preset_name
    client.min_kakera = min_kakera
    client.snipe_mode = snipe_mode
    client.snipe_delay = snipe_delay
    client.snipe_ignore_min_kakera_reset = snipe_ignore_min_kakera_reset
    client.wishlist = set([w.lower() for w in wishlist])
    client.series_snipe_mode = series_snipe_mode
    client.series_snipe_only_self_rolls = bool(series_snipe_only_self_rolls_preset)
    client.series_snipe_delay = series_snipe_delay
    client.series_wishlist = set([sw.lower() for sw in series_wishlist])
    client.avoid_list = set([a.lower() for a in (avoid_list or [])])

    client.snipe_channels = set()
    for ch in snipe_channels_preset or []:
        try: client.snipe_channels.add(int(ch))
        except (TypeError, ValueError): pass
    client.kakera_snipe_channels = set()
    configured_kakera_snipe_channels = kakera_snipe_channels_preset or snipe_channels_preset or []
    for ch in configured_kakera_snipe_channels:
        try: client.kakera_snipe_channels.add(int(ch))
        except (TypeError, ValueError): pass

    client.max_claim_rank = int(max_claim_rank_preset or 0)
    client.max_like_rank = int(max_like_rank_preset or 0)
    client.muda_name = BOT_NAME
    client.claim_right_available = False
    # Presets may store Discord snowflakes as strings, while Discord exposes
    # message.channel.id as an int. Keep the runtime value normalized so
    # own-roll messages are recognized by on_message.
    try:
        client.target_channel_id = int(target_channel_id)
    except (TypeError, ValueError):
        client.target_channel_id = target_channel_id
    client.roll_command = str(roll_command or "wa").strip().lstrip("/") or "wa"
    client.command_channel_id_preset = str(command_channel_id_preset or "").strip()
    client.forcedivorce_channel_id_preset = str(forcedivorce_channel_id_preset or "").strip()
    client.roll_speed = roll_speed
    client.mudae_prefix = mudae_prefix
    client.key_mode = key_mode
    client.delay_seconds = delay_seconds
    client.sniped_messages = set()
    client.snipe_happened = False
    client.series_sniped_messages = set()
    client.series_snipe_happened = False
    client.kakera_value_sniped_messages = set()
    client.is_actively_rolling = False
    client.active_cycle_id = 0
    client.tu_lock = None
    client.interrupt_rolling = False
    client._roll_interrupt_reason = None
    client.current_min_kakera_for_roll_claim = client.min_kakera
    client.kakera_snipe_mode_active = kakera_snipe_mode_preset
    client.kakera_snipe_threshold = kakera_snipe_threshold_preset
    client.enable_reactive_self_snipe = enable_reactive_self_snipe_preset
    client.auto_free_claim_enabled = bool(auto_free_claim_preset)
    client.reactive_snipe_delay = reactive_snipe_delay
    client.rolling_enabled = rolling_enabled
    client.rt_available = False
    client.rt_available_at_utc = None
    client.kakera_reaction_snipe_mode_active = kakera_reaction_snipe_mode_preset
    client.kakera_reaction_snipe_delay_value = kakera_reaction_snipe_delay_preset
    client.kakera_reaction_snipe_targets = set([t.lower() for t in kakera_reaction_snipe_targets])
    client.character_snipe_targets = set([t.lower().strip() for t in (character_snipe_targets or []) if t.strip()])
    client.kakera_reaction_sniped_messages = set()
    client.kakera_react_available = None
    client.kakera_react_cooldown_until_utc = None

    client.humanization_enabled = humanization_enabled
    client.humanization_window_minutes = humanization_window_minutes
    client.inactive_hours = inactive_hours_preset or []
    client.humanization_inactivity_seconds = humanization_inactivity_seconds

    client.auto_dk_enabled = auto_dk_enabled_preset
    client.dk_power_management = dk_power_management
    client.skip_initial_commands = skip_initial_commands
    client.dk_stock_count = 0
    client.max_dk_power = max_dk_power_preset
    client.auto_dk_min_power = max(0, int(auto_dk_min_power_preset or 0))
    client.maintenance_until = None
    client.only_chaos = only_chaos
    client.mk_only = mk_only_preset

    client.auto_us_enabled = auto_us_enabled
    client.auto_us_limit = auto_us_limit
    client.auto_us_stop_on_claim = auto_us_stop_on_claim
    client.bulk_us_enabled = bulk_us_enabled_preset
    client.us_pulled_this_cycle = 0
    client.mk_rolls_left = 0
    client.auto_mk_enabled = auto_mk_enabled_preset
    client.auto_mk_full_power_only = bool(auto_mk_full_power_only_preset)
    client._mk_full_power_refresh_at = None

    client.auto_rolls_enabled = auto_rolls_enabled
    client.auto_rolls_limit = auto_rolls_limit
    client.auto_rolls_in_key_mode = auto_rolls_in_key_mode
    client.auto_rolls_only_claim_hour = auto_rolls_only_claim_hour_preset
    client.rolls_item_used_count = 0
    client.rolls_used_this_interval_utc = None
    client.panic_roll_minutes = panic_roll_minutes_preset if panic_roll_minutes_preset is not None else 5
    client.lurker_mode = lurker_mode_preset
    client.auto_rt_after_claim = auto_rt_after_claim_preset

    client.randomized_claim_reactions = randomized_claim_reactions_preset or ["💖", "💗", "💘", "❤️", "👍", "🔥"]
    client.main_account_id = str(main_account_id_preset or "").strip()
    client.scheduled_roll_times = scheduled_roll_times_preset or []
    client.kakera_priority_order = kakera_priority_order_preset or [
        'kakeraP', 'kakeraC', 'kakeraL', 'kakeraW', 'kakeraR', 'kakeraO', 'kakeraD', 'kakeraY', 'kakeraG', 'kakeraT', 'kakera'
    ]
    sphere_click_targets = (
        ["spG", "spY", "spO", "spR", "spW", "spL", "spD", "spM", "spU"]
        if sphere_click_targets_preset is None
        else sphere_click_targets_preset
    )
    client.sphere_click_targets = {
        normalize_character_sphere_emoji(target).casefold()
        for target in sphere_click_targets
        if str(target or "").strip()
    }
    client.immediate_kakera_click = immediate_kakera_click_preset
    # Purple Kakera is free, but in a shared channel every account may race
    # for it. Keep legacy presets opt-in by default while allowing each preset
    # to opt out independently.
    client.collect_purple_kakera = bool(collect_purple_kakera_preset)
    client.auto_oh_enabled = bool(auto_oh_enabled_preset)
    client.auto_oc_enabled = bool(auto_oc_enabled_preset)
    client.oh_use_individually = bool(oh_use_individually_preset)
    client.oh_priority_order = [
        str(item).strip() for item in (oh_priority_order_preset or []) if str(item).strip()
    ]
    client.oh_unknown_explore_clicks = max(0, int(oh_unknown_explore_clicks_preset or 0))
    client.oc_reward_priority_order = [
        str(item).strip() for item in (oc_reward_priority_order_preset or []) if str(item).strip()
    ]
    client.oc_collect_after_red = bool(oc_collect_after_red_preset)
    client.sphere_game_counts = {"oh": 0, "oc": 0, "oq": 0, "ot": 0}
    client.sphere_game_refill_at_utc = None
    # run_bot is entered from a worker thread before discord.py creates that
    # thread's event loop. Bind per-client locks lazily from their first async task.
    client._sphere_game_lock = None
    client._kakera_action_lock = None
    client._sphere_game_response_future = None
    client._sphere_game_response_channel_id = None
    client._sphere_game_response_kind = None
    client._sphere_game_bonus_clicks = 0
    client._sphere_game_bonus_event = None
    client._sphere_game_bonus_counts = {}
    client._sphere_game_retry_after = {"oh": 0.0, "oc": 0.0}
    client._sphere_board_update_events = {}
    client._kakera_power_reconcile_handle = None
    client.kakera_power_ledger = KakeraPowerLedger()
    client._mudae_command_ack_waiters = {}
    client._recent_mudae_command_acks = {}
    client._rolls_ack_retry_after = 0.0
    client._confirmed_kakera_c_bonus_until = 0.0
    client.collected_kakera_rolls = []

    client.enable_snipe_chat_reactions = enable_snipe_chat_reactions_preset
    client.snipe_chat_messages = snipe_chat_messages_preset or ["omg", "ezz"]
    client.enable_kakera_snipe_chat_reactions = bool(enable_kakera_snipe_chat_reactions_preset)
    client.kakera_snipe_chat_messages = kakera_snipe_chat_messages_preset or ["nice", "free kakera"]
    configured_farm_characters = list(farm_characters_preset or [])
    if farm_character_preset:
        configured_farm_characters.insert(0, farm_character_preset)
    client.farm_characters = []
    seen_farm_characters = set()
    for farm_name in configured_farm_characters:
        cleaned_farm_name = str(farm_name or "").strip()
        normalized_farm_name = cleaned_farm_name.casefold()
        if cleaned_farm_name and normalized_farm_name not in seen_farm_characters:
            seen_farm_characters.add(normalized_farm_name)
            client.farm_characters.append(cleaned_farm_name)
    client.farm_character = client.farm_characters[0] if client.farm_characters else ""
    client.farm_character_enabled = farm_character_enabled_preset
    client.farm_forcedivorce_after_claim = bool(farm_forcedivorce_after_claim_preset)
    client.farm_forcedivorce_before_roll = bool(farm_forcedivorce_before_roll_preset)
    client.farm_forcedivorce_after_other_claim = bool(farm_forcedivorce_after_other_claim_preset)
    client.forcedivorce_channel = None
    client._farm_release_recent = {}
    client._farm_release_lock = None
    client.op_perk_5_only = op_perk_5_only_preset
    client.auto_divorce_protect_wishes = bool(auto_divorce_protect_wishes_preset)
    client.wish_starwish_kakera_only = bool(wish_starwish_kakera_only_preset)

    client.next_claim_reset_at_utc = None
    client.roll_reset_at_utc = None
    client.claim_cooldown_until_utc = None
    client.is_claiming = False
    client.snipe_watch = {}
    client.snipe_watch_expiry_seconds = 180
    client.snipe_globally_disabled_until = None

    client.current_dk_power = None
    client.dk_power_revision = 0
    client._us_lock = None
    client._us_in_flight = False
    client._us_pending_amount = 0
    client._us_retry_after = 0.0
    client.us_failed_this_cycle = False
    client.dk_consumption = 35
    client.kakera_reacted_messages = set()
    client._kakera_result_waiters = {}
    client.processed_claim_messages = set()
    client._rt_failed_message_ids = set()
    client.claim_retry_counts = {}
    client.last_successfully_claimed_character = None
    client._has_initialized = False
    client._main_loop_task = None
    client._immediate_check_event = None
    client._runtime_state_event = None
    client.scheduled_roll_due = False
    client.pending_claim = None
    client._claim_evidence_event = None
    client._claim_text_evidence = None
    client._claim_reset_refresh_requested = False
    client._status_cycle_not_before_monotonic = 0.0
    client._shared_reset_observed_at_utc = None
    client._shared_claim_reset_handle = None
    client._snipe_claim_refresh_reset_at_utc = None
    client._snipe_claim_refresh_at_utc = None
    client._snipe_claim_refresh_completed_for = None

    client.use_slash_rolls = bool(use_slash_rolls and Route is not None)
    client.slash_fallback_active = False
    client.mudae_slash_cache = {}
    client.mudae_slash_missing = set()
    client.mudae_session_id = None
    client.slash_fail_streak = 0
    client.slash_fail_threshold = 3
    client.slash_min_interval = max(1.0, float(roll_speed)) if roll_speed else 1.0
    client.slash_max_backoff = 6.0
    client.last_slash_attempt = 0.0
    client.slash_rate_limited_until = 0.0

    client.auto_divorce_enabled = auto_divorce_enabled_preset
    client.auto_divorce_max_kakera = auto_divorce_max_kakera_preset if auto_divorce_max_kakera_preset is not None else 50
    client.auto_divorce_series = [s.lower().strip() for s in (auto_divorce_series_preset or []) if s.strip()]
    client.auto_divorce_blacklist = set([c.lower().strip() for c in (auto_divorce_blacklist_preset or []) if c.strip()])
    client.auto_divorce_blacklist_series = [s.lower().strip() for s in (auto_divorce_blacklist_series_preset or []) if s.strip()]
    client.mk_bypass_power_check = mk_bypass_power_check
    client.auto_p_enabled = auto_p_enabled
    client.enable_hybrid_panic_claim = enable_hybrid_panic_claim_preset
    client.hybrid_panic_instant_claim_min_kakera = int(hybrid_panic_instant_claim_min_kakera_preset or 300)
    client.hybrid_panic_instant_claim_max_rank = int(hybrid_panic_instant_claim_max_rank_preset or 200)
    client.claim_rounds_thresholds = claim_rounds_thresholds_preset or []
    client.base_min_kakera = min_kakera
    client.base_max_claim_rank = int(max_claim_rank_preset or 0)
    client.base_max_like_rank = int(max_like_rank_preset or 0)
    client.p_available = False
    client.next_p_claim_at_utc = None
    client.key_limit_hit = False
    client.time_rolls_to_claim_reset = time_rolls_to_claim_reset_preset
    client.is_timing_mode_active = False
    client.rt_ignore_min_kakera_for_wishlist = rt_ignore_min_kakera_for_wishlist_preset

    client.last_tu_query_utc = None
    initialize_status_tracking(client)
    client.last_tu_snapshot_complete = False
    client._tu_response_future = None
    client._tu_response_channel_id = None
    client._tu_request_started_at = None
    client._local_extra_rolls_pending = 0
    client.rolls_left = 0
    client._last_normal_roll_count = 0
    client._claim_reset_rolls_pending = False
    client._rolls_sent = 0
    client._rolls_received = 0
    client.collected_rolls = []
    client.rt_only_self_rolls = rt_only_self_rolls_preset

    if reactive_kakera_delay_range_preset and isinstance(reactive_kakera_delay_range_preset, (list, tuple)) and len(reactive_kakera_delay_range_preset) == 2:
        client.reactive_kakera_delay_range = (float(reactive_kakera_delay_range_preset[0]), float(reactive_kakera_delay_range_preset[1]))
    else:
        client.reactive_kakera_delay_range = (0.3, 1.0)

    client.claim_interval = claim_interval_preset or 180
    client.roll_interval = roll_interval_preset or 60

    client.claim_emojis = claim_emojis_preset if claim_emojis_preset is not None else CLAIM_EMOJIS
    client.kakera_emojis = kakera_emojis_preset if kakera_emojis_preset is not None else KAKERA_EMOJIS
    # Context-specific lists are overrides. If omitted, inherit the preset's
    # regular selection instead of silently re-enabling every default colour.
    client.chaos_emojis = chaos_emojis_preset if chaos_emojis_preset is not None else list(client.kakera_emojis)
    client.sphere_perk_emojis = sphere_perk_emojis_preset if sphere_perk_emojis_preset is not None else list(client.kakera_emojis)
    client.sphere_emojis = SPHERE_EMOJIS
    client.kakera_power_thresholds = kakera_power_thresholds or {}
    client.debug_mode = debug_mode
    client.debug_log_categories = {
        str(item).strip().casefold()
        for item in (debug_log_categories_preset or ["all"])
        if str(item).strip()
    }
    client.webhook_url = str(webhook_url_preset or "").strip()
    client.webhook_log_types = {
        str(item).strip().upper()
        for item in (webhook_log_types_preset or ["ERROR", "WARN", "CLAIM", "KAKERA"])
        if str(item).strip()
    }
    client.persistent_stagger_seconds = max(0.0, float(persistent_stagger_seconds_preset or 0.0))
    account_index = int(client.persistent_stagger_seconds // active_stagger_seconds(1))

    BotLogger.log(
        f"Automated Staggering: Assigned active index {account_index} (Preset: '{preset_name}') -> "
        f"+{client.persistent_stagger_seconds}s persistent sleep offset applied.",
        preset_name, "INFO"
    )

    def inactive_minute(value) -> int:
        if isinstance(value, int):
            return (value % 24) * 60
        match = re.fullmatch(r"\s*(\d{1,2})(?::(\d{2}))?\s*", str(value or ""))
        if not match:
            return 0
        return (int(match.group(1)) % 24) * 60 + min(59, int(match.group(2) or 0))

    def is_inactive_hour() -> bool:
        if not client.inactive_hours: return False
        now = datetime.datetime.now()
        now_minute = now.hour * 60 + now.minute
        for start_value, end_value in client.inactive_hours:
            start_minute = inactive_minute(start_value)
            end_minute = inactive_minute(end_value)
            if start_minute <= end_minute:
                if start_minute <= now_minute < end_minute: return True
            else:
                if now_minute >= start_minute or now_minute < end_minute: return True
        return False

    def seconds_until_active() -> float:
        if not is_inactive_hour(): return 0
        now = datetime.datetime.now()
        now_minute = now.hour * 60 + now.minute
        best = float('inf')
        for start_value, end_value in client.inactive_hours:
            start_minute = inactive_minute(start_value)
            end_minute = inactive_minute(end_value)
            in_this = (
                start_minute <= now_minute < end_minute
                if start_minute <= end_minute
                else now_minute >= start_minute or now_minute < end_minute
            )
            if in_this:
                wake = now.replace(
                    hour=end_minute // 60,
                    minute=end_minute % 60,
                    second=0,
                    microsecond=0,
                )
                if wake <= now: wake += datetime.timedelta(days=1)
                best = min(best, (wake - now).total_seconds())
        return best if best != float('inf') else 0

    def wake_status_loop():
        event = getattr(client, '_immediate_check_event', None)
        if event is not None:
            event.set()

    def request_status_refresh(fields=None, reason="state-change", urgent=False):
        mark_status_dirty(client, fields=fields, reason=reason, urgent=urgent)
        wake_status_loop()

    def invalidate_rt_after_failed_attempt(message_id=None, reason="rt-attempt-inconclusive"):
        """Stop reusing a stale RT snapshot after Mudae gives no usable result."""
        client.rt_available = False
        client.rt_available_at_utc = None
        if message_id is not None:
            failed_ids = getattr(client, "_rt_failed_message_ids", set())
            failed_ids.add(message_id)
            if len(failed_ids) > 1000:
                failed_ids.clear()
        request_status_refresh({"claim", "rt"}, reason=reason, urgent=True)

    def schedule_external_kakera_power_reconcile():
        """Release losing external-click reservations without starting a global $tu wave."""
        handle = getattr(client, "_kakera_power_reconcile_handle", None)
        if handle is not None and not handle.cancelled():
            return

        def reconcile():
            client._kakera_power_reconcile_handle = None
            pending_count = client.kakera_power_ledger.pending_count
            if pending_count <= 0:
                return
            client.kakera_power_ledger.clear()
            mark_dk_power_changed()
            BotLogger.log(
                f"No account-specific Kakera result for {pending_count} click(s); "
                "released reserved power without $tu.",
                preset_name,
                "DEBUG",
                client,
            )

        client._kakera_power_reconcile_handle = client.loop.call_later(8.0, reconcile)

    def cancel_external_kakera_power_reconcile():
        """Cancel the reservation timeout after Mudae confirms every pending click."""
        handle = getattr(client, "_kakera_power_reconcile_handle", None)
        if handle is None or handle.cancelled():
            return False
        handle.cancel()
        client._kakera_power_reconcile_handle = None
        return True

    def schedule_points_refresh(deadline):
        if deadline is None:
            return
        delay = max(
            5.0,
            (deadline - datetime.datetime.now(datetime.timezone.utc)).total_seconds() + 2.0,
        )
        client.loop.call_later(
            delay,
            request_status_refresh,
            {"points"},
            "p-reset",
        )

    def set_claim_cooldown(minutes, source="Mudae", wake=False):
        cooldown_minutes = max(0, int(minutes or 0))
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        deadline = cooldown_deadline(now_utc, cooldown_minutes)
        client.claim_right_available = False
        client.next_claim_reset_at_utc = deadline
        client.claim_cooldown_until_utc = deadline
        client._claim_reset_refresh_requested = False
        if wake:
            wake_status_loop()
        return deadline

    def claim_identities(guild=None):
        user = getattr(client, 'user', None)
        if user is None:
            return []
        identities = [getattr(user, 'name', ''), getattr(user, 'display_name', '')]
        user_id = getattr(user, 'id', None)
        member = guild.get_member(user_id) if guild is not None and user_id is not None else None
        member_display_name = getattr(member, 'display_name', '')
        if member_display_name:
            identities.append(member_display_name)
        return identities

    def message_addresses_self(message):
        """Match the addressed account exactly instead of by unsafe substring."""
        user = getattr(client, 'user', None)
        if user is None:
            return False
        user_id = getattr(user, 'id', None)
        guild = getattr(message, 'guild', None)
        identities = claim_identities(guild)
        return status_message_addresses_identity(
            getattr(message, 'content', ''),
            identities,
            user_id=user_id,
        )

    def is_farm_character_name(name):
        normalized = str(name or "").strip().casefold()
        return any(normalized == item.casefold() for item in client.farm_characters)

    def is_wish_or_starwish(message, embed):
        name = getattr(getattr(embed, "author", None), "name", "")
        series = character_series_line(getattr(embed, "description", ""))
        return (
            name_or_series_is_configured_wish(
                name,
                series,
                client.wishlist,
                client.series_wishlist,
            )
            or is_wished_by_self(message, getattr(getattr(client, "user", None), "id", 0))
            or series_line_has_emoji(getattr(embed, "description", ""))
        )

    def is_tu_response_for_self(message):
        if getattr(getattr(message, 'author', None), 'id', None) != TARGET_BOT_ID:
            return False
        text = str(getattr(message, 'content', '') or '')
        match = re.match(REGEX_PATTERNS["USER_BOLD"], text)
        if not match:
            return False
        identities = [identity.lower() for identity in claim_identities() if identity]
        if match.group(1).strip().lower() not in identities:
            return False
        lowered = text.lower()
        status_markers = ("roll", "$rt", "$dk", "$daily", "$p", "$us", "claim", "react")
        return any(marker in lowered for marker in status_markers)

    def capture_tu_response(message):
        future = getattr(client, '_tu_response_future', None)
        if future is None or future.done():
            return False
        expected_channel_id = getattr(client, '_tu_response_channel_id', None)
        if expected_channel_id is not None and getattr(message.channel, 'id', None) != expected_channel_id:
            return False
        if not is_tu_response_for_self(message):
            return False
        future.set_result(message.content)
        return True

    def observe_shared_tu_resets(message):
        """Share only claim/roll reset boundaries from any visible server $tu."""
        if getattr(getattr(message, 'author', None), 'id', None) != TARGET_BOT_ID:
            return False
        guild = getattr(message, 'guild', None)
        if guild is None or not looks_like_tu_status_snapshot(getattr(message, 'content', '')):
            return False

        content = str(message.content or '')
        lowered = content.lower()
        observed_at = datetime.datetime.now(datetime.timezone.utc)

        claim_minutes = None
        claim_match = re.search(REGEX_PATTERNS["CLAIM_RESET"], lowered)
        if claim_match and not any(marker in claim_match.group(0) for marker in ("$daily", "$dk", "$rt")):
            claim_hours, claim_mins = parse_hm(claim_match)
            claim_minutes = claim_hours * 60 + claim_mins
        if claim_minutes is None:
            claim_minutes = parse_claim_denied_cooldown(lowered)
        if claim_minutes is None:
            claim_minutes = parse_timer_minutes("CLAIM_COOLDOWN", lowered)

        roll_minutes = None
        rolls_match = re.search(REGEX_PATTERNS["ROLLS_COUNT"], lowered, re.DOTALL)
        if rolls_match:
            roll_minutes = parse_timer_minutes("ROLL_RESET_TU", lowered[rolls_match.end():])
        if roll_minutes is None:
            roll_minutes = parse_timer_minutes("ROLL_RESET", lowered)

        claim_deadline = (
            cooldown_deadline(observed_at, claim_minutes)
            if claim_minutes is not None
            else None
        )
        roll_deadline = (
            cooldown_deadline(observed_at, roll_minutes)
            if roll_minutes is not None
            else None
        )
        snapshot, changed = _server_reset_coordinator.observe(
            getattr(guild, 'id', None),
            getattr(message, 'id', None),
            observed_at,
            claim_reset_at_utc=claim_deadline,
            roll_reset_at_utc=roll_deadline,
        )
        if not changed or snapshot is None:
            return False

        with _active_clients_lock:
            active_clients = list(_active_clients)
        for active_client in active_clients:
            try:
                if active_client.get_guild(guild.id) is None:
                    continue
                active_loop = getattr(active_client, 'loop', None)
                if active_loop is not None and active_loop.is_running():
                    active_loop.call_soon_threadsafe(
                        _apply_shared_reset_snapshot,
                        active_client,
                        snapshot,
                    )
            except Exception:
                continue
        return True

    def is_tu_status_snapshot_for_self(message):
        if not is_tu_response_for_self(message):
            return False
        interaction = (
            getattr(message, 'interaction_metadata', None)
            or getattr(message, 'interaction', None)
        )
        command_name = str(getattr(interaction, 'name', '') or '').strip().lower().lstrip('/')
        return command_name == "tu" or looks_like_tu_status_snapshot(message.content)

    def sphere_game_kind(message):
        interaction = (
            getattr(message, 'interaction_metadata', None)
            or getattr(message, 'interaction', None)
        )
        command_name = str(getattr(interaction, 'name', '') or '').strip().lower().lstrip('/')
        if command_name in {"oh", "oc"}:
            return command_name
        text = str(getattr(message, 'content', '') or '').lower()
        if "1 red sphere" in text and "never at the center" in text:
            return "oc"
        if "blue spheres unveil 3 buttons" in text and "multiplier:" in text:
            return "oh"
        return None

    def sphere_game_buttons(message):
        buttons = []
        for component in getattr(message, 'components', None) or []:
            buttons.extend(getattr(component, 'children', None) or [])
        return buttons

    def sphere_game_belongs_to_self(message):
        interaction = (
            getattr(message, 'interaction', None)
            or getattr(message, 'interaction_metadata', None)
        )
        interaction_user = getattr(interaction, 'user', None)
        interaction_user_id = getattr(interaction_user, 'id', None)
        client_user_id = getattr(getattr(client, 'user', None), 'id', None)
        return interaction_user_id is None or interaction_user_id == client_user_id

    def capture_sphere_game_response(message):
        future = getattr(client, '_sphere_game_response_future', None)
        if future is None or future.done():
            return False
        if getattr(getattr(message, 'author', None), 'id', None) != TARGET_BOT_ID:
            return False
        expected_channel_id = getattr(client, '_sphere_game_response_channel_id', None)
        if expected_channel_id is not None and getattr(message.channel, 'id', None) != expected_channel_id:
            return False
        buttons = sphere_game_buttons(message)
        if len(buttons) != 25:
            return False
        expected_kind = getattr(client, '_sphere_game_response_kind', None)
        detected_kind = sphere_game_kind(message)
        # Text-command boards do not expose the command name, and their
        # descriptions are localized. While a specific game response is
        # pending, a fresh 25-button Mudae board in that channel is sufficient.
        if detected_kind is not None and detected_kind != expected_kind:
            return False
        if detected_kind is None and expected_kind not in {"oh", "oc"}:
            return False
        if not sphere_game_belongs_to_self(message):
            return False
        future.set_result(message)
        return True

    def capture_sphere_game_bonus(message):
        if getattr(getattr(message, 'author', None), 'id', None) != TARGET_BOT_ID:
            return False
        if getattr(client, '_sphere_game_response_kind', None) != "oh":
            return False
        expected_channel_id = getattr(client, '_sphere_game_response_channel_id', None)
        if expected_channel_id is not None and getattr(message.channel, 'id', None) != expected_channel_id:
            return False
        bonus_text = [str(getattr(message, 'content', '') or '')]
        for embed in getattr(message, 'embeds', ()) or ():
            bonus_text.append(str(getattr(embed, 'description', '') or ''))
            for field in getattr(embed, 'fields', ()) or ():
                bonus_text.append(str(getattr(field, 'name', '') or ''))
                bonus_text.append(str(getattr(field, 'value', '') or ''))
        total_bonus_clicks = count_harvest_bonus_clicks("\n".join(bonus_text))
        message_id = getattr(message, 'id', None)
        previous_bonus_clicks = client._sphere_game_bonus_counts.get(message_id, 0)
        bonus_clicks = max(0, total_bonus_clicks - previous_bonus_clicks)
        if bonus_clicks <= 0:
            return False
        client._sphere_game_bonus_counts[message_id] = total_bonus_clicks
        client._sphere_game_bonus_clicks += bonus_clicks
        bonus_event = getattr(client, '_sphere_game_bonus_event', None)
        if bonus_event is not None:
            bonus_event.set()
        BotLogger.log(
            f"$oh: spD turned into spP; added {bonus_clicks} extra click(s).",
            preset_name,
            "KAKERA",
        )
        return True

    def record_claim_text_evidence(message):
        pending = getattr(client, 'pending_claim', None)
        if not pending or not getattr(message, 'content', None):
            return
        evidence = classify_claim_text(
            message.content,
            pending['character_name'],
            claim_identities(),
            user_id=getattr(getattr(client, 'user', None), 'id', None),
        )
        if evidence.outcome == ClaimOutcome.INCONCLUSIVE:
            return
        client._claim_text_evidence = evidence
        event = getattr(client, '_claim_evidence_event', None)
        if event is not None:
            event.set()

    def process_claim_cooldown_message(message):
        if not getattr(message, 'content', None) or getattr(message, 'embeds', None):
            return False
        # A manual /tu (or another MudaRemote instance's /tu) is already an
        # authoritative status snapshot, not a rejected claim. Refreshing in
        # response makes two running instances trigger each other forever.
        if is_tu_status_snapshot_for_self(message):
            return False
        c_low = message.content.lower()
        if not message_addresses_self(message):
            return False
        cooldown_minutes = parse_claim_denied_cooldown(c_low)
        match = None
        if cooldown_minutes is None:
            match = re.search(REGEX_PATTERNS["CLAIM_COOLDOWN"], c_low, re.IGNORECASE)
            if not match:
                match = re.search(REGEX_PATTERNS["CLAIM_INTERVAL_COOLDOWN"], c_low, re.IGNORECASE)
        if cooldown_minutes is None and not match:
            return False
        if cooldown_minutes is None:
            hours, minutes = parse_hm(match)
            cooldown_minutes = hours * 60 + minutes
        BotLogger.log(f"Detected claim cooldown message from Mudae: {cooldown_minutes}m left. Locking claim.", preset_name, "WARN")
        set_claim_cooldown(cooldown_minutes, source="Mudae message", wake=False)
        pending = getattr(client, 'pending_claim', None)
        if pending and pending.get("consumes_claim"):
            # This is explicit rejection evidence, not proof that the click
            # consumed a claim. Keep the roll pending until $tu confirms
            # whether it can be retried with a claim right or $rt.
            pending["rejected_by_cooldown"] = True
            request_status_refresh({"claim", "rt"}, reason="claim-rejected-cooldown", urgent=True)
            event = getattr(client, '_claim_evidence_event', None)
            if event is not None:
                event.set()
        else:
            # The rejection itself authoritatively locks a manual claim. There
            # is no pending automated click to resolve, so another $tu would
            # only repeat the same cooldown and can fan out across many alts.
            clear_status_dirty(client, {"claim"})
            wake_status_loop()
        return True

    def process_kakera_reaction_cooldown_message(message):
        """Record Mudae's immediate $ku rejection before another click is sent."""
        if not getattr(message, 'content', None) or getattr(message, 'embeds', None):
            return False
        if not message_addresses_self(message):
            return False
        c_low = message.content.lower()
        if not any(phrase in c_low for phrase in ("can't react to kakera", "nÃ£o pode reagir", "no puedes reaccionar")):
            return False

        cooldown_minutes = parse_timer_minutes("KAKERA_COOLDOWN", c_low)
        client.kakera_react_available = False
        if cooldown_minutes is not None:
            client.kakera_react_cooldown_until_utc = (
                datetime.datetime.now(datetime.timezone.utc)
                + datetime.timedelta(minutes=cooldown_minutes)
            )
        else:
            client.kakera_react_cooldown_until_utc = None
        remaining = f" ({cooldown_minutes}m left)" if cooldown_minutes is not None else ""
        BotLogger.log(
            f"Detected Kakera reaction cooldown from Mudae{remaining}. Blocking further Kakera clicks.",
            preset_name,
            "WARN",
        )
        return True

    async def paced_mudae_action(action):
        return await client.command_pacer.run(
            action,
            lambda seconds: pause_interruptible_sleep(client, seconds, abort_on_pause=True),
            lambda: not client.is_paused and not is_maintenance_active(),
        )

    async def guarded_send(channel, content):
        return await paced_mudae_action(lambda: channel.send(content))

    async def send_mudae_reaction_command(channel, content, timeout=6.0):
        """Send a command whose successful execution is acknowledged with ✅."""
        sent = await guarded_send(channel, content)
        message_id = getattr(sent, 'id', None)
        if not sent or message_id is None:
            return False

        loop = asyncio.get_running_loop()
        waiter = loop.create_future()
        client._mudae_command_ack_waiters[message_id] = waiter
        if message_id in client._recent_mudae_command_acks and not waiter.done():
            waiter.set_result(True)
        try:
            await asyncio.wait_for(asyncio.shield(waiter), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            BotLogger.log(
                f"No Mudae ✅ acknowledgement for {content}; leaving cached state unchanged.",
                preset_name,
                "WARN",
            )
            return False
        finally:
            client._mudae_command_ack_waiters.pop(message_id, None)
            client._recent_mudae_command_acks.pop(message_id, None)
            if not waiter.done():
                waiter.cancel()

    def apply_rt_acknowledgement():
        """A ✅ on $rt proves it was consumed and a temporary claim was restored."""
        client.rt_available = False
        client.rt_available_at_utc = None
        client.claim_right_available = True
        client.claim_cooldown_until_utc = None
        client.last_successfully_claimed_character = None
        clear_status_dirty(client, {"claim", "rt"})

    async def guarded_click(target):
        if client.is_paused or is_maintenance_active():
            return False
        await target.click()
        return True

    def register_kakera_result_waiter(emoji_name):
        """Register before clicking so a fast account-specific result cannot be missed."""
        key = str(emoji_name or "").rstrip("2").casefold()
        waiter = client.loop.create_future()
        client._kakera_result_waiters.setdefault(key, set()).add(waiter)
        return key, waiter

    def discard_kakera_result_waiter(key, waiter):
        waiters = client._kakera_result_waiters.get(key)
        if waiters is not None:
            waiters.discard(waiter)
            if not waiters:
                client._kakera_result_waiters.pop(key, None)
        if not waiter.done():
            waiter.cancel()

    def resolve_kakera_result_waiters(emoji_name, amount):
        key = str(emoji_name or "").rstrip("2").casefold()
        waiters = client._kakera_result_waiters.pop(key, set())
        for waiter in waiters:
            if not waiter.done():
                waiter.set_result(amount)
        return bool(waiters)

    async def click_kakera_with_confirmation(
        channel,
        msg,
        button,
        *,
        custom_id,
        position,
        emoji_name,
        character_name,
    ):
        """Retry an enabled Kakera button only while this account has no result."""
        is_purple = str(emoji_name or "").rstrip("2").casefold() == "kakerap"
        attempt_limit = 3 if is_purple else 2
        label = "Purple Kakera" if is_purple else str(emoji_name or "Kakera")
        current_button = button
        for attempt in range(attempt_limit):
            waiter_key, waiter = register_kakera_result_waiter(emoji_name)
            try:
                if not await guarded_click(current_button):
                    return False
                try:
                    amount = await asyncio.wait_for(asyncio.shield(waiter), timeout=2.5)
                    BotLogger.log(
                        f"{label} confirmed for {character_name} (+{amount}).",
                        preset_name,
                        "KAKERA",
                    )
                    return True
                except asyncio.TimeoutError:
                    pass
            finally:
                discard_kakera_result_waiter(waiter_key, waiter)

            if attempt >= attempt_limit - 1 or not await active_delay(0.35):
                break
            try:
                msg = await channel.fetch_message(msg.id)
                current_button = find_refreshed_component_button(
                    msg.components,
                    custom_id=custom_id,
                    position=position,
                    emoji_name=emoji_name,
                )
            except Exception:
                current_button = None
            if current_button is None or getattr(current_button, "disabled", False):
                break
            BotLogger.log(
                f"{label} was not confirmed for {character_name}; retrying "
                f"({attempt + 2}/{attempt_limit}).",
                preset_name,
                "WARN",
            )

        BotLogger.log(
            f"{label} was not confirmed for {character_name} after {attempt_limit} attempts.",
            preset_name,
            "WARN",
        )
        return False

    async def guarded_reaction(message, emoji):
        if client.is_paused or is_maintenance_active():
            return False
        await message.add_reaction(emoji)
        return True

    async def active_delay(seconds):
        return await pause_interruptible_sleep(client, seconds, abort_on_pause=True)

    def sphere_board_snapshot(message):
        buttons = sphere_game_buttons(message)
        emojis = [str(getattr(getattr(button, 'emoji', None), 'name', '') or '') for button in buttons]
        disabled = [bool(getattr(button, 'disabled', False)) for button in buttons]
        styles = [str(getattr(button, 'style', '')) for button in buttons]
        return buttons, emojis, disabled, tuple(zip(emojis, disabled, styles))

    async def wait_for_sphere_board_update(channel, message_id, previous_snapshot, update_event=None):
        latest = None
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            if client.is_paused or is_maintenance_active():
                return None
            if update_event is not None:
                try:
                    await asyncio.wait_for(update_event.wait(), timeout=0.75)
                    update_event.clear()
                except asyncio.TimeoutError:
                    pass
            elif not await active_delay(0.75):
                return None
            try:
                latest = await channel.fetch_message(message_id)
            except Exception:
                continue
            if sphere_board_snapshot(latest)[3] != previous_snapshot:
                return latest
        return latest

    async def play_sphere_game(channel, message, kind):
        clicked_positions = set()
        current = message
        game_label = "$oh" if kind == "oh" else "$oc"

        paid_clicks = 0
        total_clicks = 0
        red_found = False
        while total_clicks < 25:
            paid_limit = 5 + int(getattr(client, '_sphere_game_bonus_clicks', 0) or 0)
            if paid_clicks >= paid_limit:
                break
            buttons, emojis, disabled, snapshot = sphere_board_snapshot(current)
            if len(buttons) != 25:
                BotLogger.log(f"{game_label}: Expected 25 sphere buttons but received {len(buttons)}.", preset_name, "WARN")
                return False
            if all(disabled):
                break

            if kind == "oc":
                position = choose_chest_position(
                    emojis,
                    disabled,
                    reward_priority_order=client.oc_reward_priority_order,
                )
            else:
                position = choose_harvest_position(
                    emojis,
                    disabled,
                    paid_clicks=paid_clicks,
                    priority_order=client.oh_priority_order,
                    unknown_explore_clicks=client.oh_unknown_explore_clicks,
                )
            if position is None or position < 0 or position >= len(buttons):
                BotLogger.log(f"{game_label}: No safe enabled sphere button remains.", preset_name, "WARN")
                break

            if not await active_delay(random.uniform(0.45, 0.85)):
                return False
            bonus_before_click = int(getattr(client, '_sphere_game_bonus_clicks', 0) or 0)
            bonus_event = getattr(client, '_sphere_game_bonus_event', None)
            if bonus_event is not None:
                bonus_event.clear()
            refreshed = None
            for click_attempt in range(2):
                update_event = asyncio.Event()
                client._sphere_board_update_events[current.id] = update_event
                try:
                    if not click_attempt:
                        BotLogger.log(
                            f"{game_label}: Clicking row {position // 5 + 1}, column {position % 5 + 1} ({emojis[position]}).",
                            preset_name,
                            "INFO",
                        )
                    else:
                        BotLogger.log(f"{game_label}: No board edit received; retrying the click once.", preset_name, "WARN")
                    if not await guarded_click(buttons[position]):
                        return False
                    refreshed = await wait_for_sphere_board_update(
                        channel,
                        current.id,
                        snapshot,
                        update_event=update_event,
                    )
                except Exception as error:
                    BotLogger.log(f"{game_label}: Sphere click failed: {error}", preset_name, "WARN")
                    return False
                finally:
                    if client._sphere_board_update_events.get(current.id) is update_event:
                        client._sphere_board_update_events.pop(current.id, None)
                if refreshed is not None and sphere_board_snapshot(refreshed)[3] != snapshot:
                    break

            if refreshed is None or sphere_board_snapshot(refreshed)[3] == snapshot:
                BotLogger.log(f"{game_label}: Board did not update after two click attempts; stopping safely.", preset_name, "WARN")
                return False

            clicked_positions.add(position)
            total_clicks += 1
            current = refreshed
            _, revealed_emojis, _, _ = sphere_board_snapshot(current)
            revealed = normalize_sphere_emoji(
                revealed_emojis[position] if position < len(revealed_emojis) else ""
            )
            if kind != "oh" or not harvest_reveal_is_free(revealed):
                paid_clicks += 1
            if kind == "oh" and revealed == "spD" and bonus_event is not None:
                if int(getattr(client, '_sphere_game_bonus_clicks', 0) or 0) == bonus_before_click:
                    try:
                        await asyncio.wait_for(bonus_event.wait(), timeout=5.0)
                    except asyncio.TimeoutError:
                        pass
            paid_limit = 5 + int(getattr(client, '_sphere_game_bonus_clicks', 0) or 0)
            BotLogger.log(
                f"{game_label}: Click {total_clicks} ({paid_clicks}/{paid_limit} used) at row {position // 5 + 1}, column {position % 5 + 1}"
                + (f" revealed {revealed}." if revealed else "."),
                preset_name,
                "INFO",
            )
            if kind == "oc" and revealed == "sp" and position in clicked_positions:
                if not red_found:
                    BotLogger.log(
                        f"$oc: Red sphere found with {5 - paid_clicks} paid click(s) remaining; collecting bonus spheres.",
                        preset_name,
                        "KAKERA",
                    )
                red_found = True
                if not client.oc_collect_after_red:
                    BotLogger.log("$oc: Configured to stop immediately after finding red.", preset_name, "INFO")
                    break

        if kind == "oh":
            BotLogger.log(f"$oh: Harvest finished after {len(clicked_positions)} click(s).", preset_name, "KAKERA")
        elif red_found:
            BotLogger.log("$oc: Chest finished after finding red and using all available clicks.", preset_name, "KAKERA")
        else:
            BotLogger.log("$oc: Board finished without finding the red sphere.", preset_name, "WARN")
        return bool(clicked_positions)

    async def find_recent_sphere_game(channel, kind, started_at):
        try:
            async for candidate in channel.history(limit=15):
                created_at = getattr(candidate, 'created_at', None)
                if created_at is not None and created_at < started_at - datetime.timedelta(seconds=1):
                    continue
                if (getattr(getattr(candidate, 'author', None), 'id', None) == TARGET_BOT_ID
                        and sphere_game_kind(candidate) in (None, kind)
                        and sphere_game_belongs_to_self(candidate)
                        and len(sphere_game_buttons(candidate)) == 25):
                    return candidate
        except Exception:
            return None
        return None

    async def run_sphere_game(channel, kind, uses):
        uses = max(1, int(uses or 1))
        if client._sphere_game_lock is None:
            client._sphere_game_lock = asyncio.Lock()
        async with client._sphere_game_lock:
            started_at = datetime.datetime.now(timezone.utc)
            response_future = asyncio.get_running_loop().create_future()
            client._sphere_game_response_future = response_future
            client._sphere_game_response_channel_id = getattr(channel, 'id', None)
            client._sphere_game_response_kind = kind
            client._sphere_game_bonus_clicks = 0
            client._sphere_game_bonus_event = asyncio.Event()
            client._sphere_game_bonus_counts = {}
            try:
                BotLogger.log(f"{kind.upper()}: Starting with {uses} available use(s).", preset_name, "INFO")
                if not await guarded_send(channel, f"{client.mudae_prefix}{kind} {uses}"):
                    return False
                try:
                    game_message = await asyncio.wait_for(asyncio.shield(response_future), timeout=8.0)
                except asyncio.TimeoutError:
                    game_message = await find_recent_sphere_game(channel, kind, started_at)
                if game_message is None:
                    BotLogger.log(f"${kind}: Game board did not arrive; retrying later.", preset_name, "WARN")
                    return False
                await play_sphere_game(channel, game_message, kind)
                # Starting the board consumes the selected stock even if the chest is lost.
                return True
            finally:
                if client._sphere_game_response_future is response_future:
                    client._sphere_game_response_future = None
                    client._sphere_game_response_channel_id = None
                    client._sphere_game_response_kind = None
                    client._sphere_game_bonus_clicks = 0
                    client._sphere_game_bonus_event = None
                    client._sphere_game_bonus_counts = {}
                if not response_future.done():
                    response_future.cancel()

    async def run_available_sphere_games(channel, status):
        available_oh = status.available_for("oh")
        available_oc = status.available_for("oc")
        client.sphere_game_counts = {
            "oh": available_oh,
            "oc": available_oc,
            "oq": status.available_for("oq"),
            "ot": status.available_for("ot"),
        }
        if status.refill_minutes is not None:
            previous_refill = client.sphere_game_refill_at_utc
            client.sphere_game_refill_at_utc = (
                datetime.datetime.now(timezone.utc) + datetime.timedelta(minutes=status.refill_minutes)
            ).replace(second=0, microsecond=0)
            if previous_refill != client.sphere_game_refill_at_utc:
                client.loop.call_later(max(5.0, status.refill_minutes * 60.0 + 2.0), wake_status_loop)

        enabled_games = (
            ("oh", client.auto_oh_enabled, available_oh),
            ("oc", client.auto_oc_enabled, available_oc),
        )
        for kind, enabled, available in enabled_games:
            if not enabled or available <= 0:
                continue
            now_monotonic = time.monotonic()
            if now_monotonic < client._sphere_game_retry_after.get(kind, 0.0):
                continue
            remaining = available
            completed_all = True
            batch_sizes = (
                [1] * available
                if kind == "oh" and client.oh_use_individually
                else split_command_batches(available, 10)
            )
            if kind == "oh" and client.oh_use_individually and available > 1:
                BotLogger.log(
                    f"OH: Individual-use mode will play {available} separate board(s).",
                    preset_name,
                    "INFO",
                )
            for batch_size in batch_sizes:
                if not await run_sphere_game(channel, kind, batch_size):
                    completed_all = False
                    break
                remaining -= batch_size
                client.sphere_game_counts[kind] = remaining
            if completed_all:
                refill_seconds = max(300.0, float(status.refill_minutes or 60) * 60.0)
                client._sphere_game_retry_after[kind] = time.monotonic() + refill_seconds
            else:
                client._sphere_game_retry_after[kind] = time.monotonic() + 300.0
                client.loop.call_later(302.0, wake_status_loop)

    async def series_wishlist_matches(message, series, known_self_roll=None):
        if not client.series_snipe_mode or not client.series_wishlist:
            return False
        if not any(entry in series for entry in client.series_wishlist):
            return False
        if not client.series_snipe_only_self_rolls:
            return True
        if known_self_roll is not None:
            return bool(known_self_roll)

        owner_id, owner_name = await detect_roll_owner(client, message)
        client_names = {
            str(getattr(client.user, "name", "") or "").lower(),
            str(getattr(client.user, "display_name", "") or "").lower(),
        }
        return owner_id == client.user.id or bool(owner_name and owner_name in client_names)

    def is_character_snipe_allowed(is_external_snipe: bool = False) -> bool:
        refresh_predicted_claim_and_rt()

        rt_usable = client.rt_available and not (is_external_snipe and client.rt_only_self_rolls)
        return client.claim_right_available or rt_usable

    def refresh_predicted_claim_and_rt():
        """Use known cooldown deadlines during long rolls without waiting for another $tu."""
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        if (
            not client.claim_right_available
            and client.next_claim_reset_at_utc
            and now_utc >= client.next_claim_reset_at_utc - datetime.timedelta(seconds=0.5)
        ):
            client.claim_right_available = True
            client.claim_cooldown_until_utc = None
            client.last_successfully_claimed_character = None
            client._claim_reset_refresh_requested = True
            mark_status_dirty(client, {"claim"}, reason="predicted-claim-reset")
            BotLogger.log(
                "Predicted claim reset reached. Claims are enabled while status refreshes in the background.",
                preset_name,
                "CHECK",
            )

        if (
            not client.rt_available
            and client.rt_available_at_utc
            and now_utc >= client.rt_available_at_utc
        ):
            client.rt_available = True
            client.rt_available_at_utc = None
            mark_status_dirty(client, {"rt"}, reason="predicted-rt-reset")
            BotLogger.log(
                "Predicted $rt reset reached. RT is available for new claim targets.",
                preset_name,
                "CHECK",
            )

    def is_key_mode_kakera_only() -> bool:
        refresh_predicted_claim_and_rt()
        return client.key_mode and not client.claim_right_available and not client.rt_available

    def is_kakera_reaction_allowed(*, is_free_purple=False) -> bool:
        if is_free_purple and client.collect_purple_kakera:
            return True
        now = datetime.datetime.now(datetime.timezone.utc)
        if client.kakera_react_available: return True
        if client.kakera_react_cooldown_until_utc and now >= client.kakera_react_cooldown_until_utc:
            client.kakera_react_available = True
            client.kakera_react_cooldown_until_utc = None
            return True
        return False

    def mark_dk_power_changed():
        client.dk_power_revision += 1

    def get_regenerated_dk_power():
        p = client.current_dk_power
        if p is None:
            return None
        if not hasattr(client, 'last_dk_power_update_utc'): return p
        now = datetime.datetime.now(datetime.timezone.utc)
        el = int((now - client.last_dk_power_update_utc).total_seconds() / 180)
        if el > 0:
            p = min(client.max_dk_power, p + el)
            client.current_dk_power = p
            mark_dk_power_changed()
            client.last_dk_power_update_utc += datetime.timedelta(minutes=3 * el)
        return p

    def get_current_dk_power():
        return client.kakera_power_ledger.available_power(get_regenerated_dk_power())

    def reserve_kakera_power_click(emoji_name, cost):
        token = client.kakera_power_ledger.reserve(emoji_name, cost)
        mark_dk_power_changed()
        schedule_external_kakera_power_reconcile()
        return token

    def cancel_kakera_power_click(token):
        if token is None or not client.kakera_power_ledger.cancel(token):
            return False
        mark_dk_power_changed()
        if not client.kakera_power_ledger.has_pending:
            cancel_external_kakera_power_reconcile()
        return True

    def confirm_kakera_power_click(emoji_name):
        cost = client.kakera_power_ledger.confirm(emoji_name)
        if cost is None:
            return None
        base_power = get_regenerated_dk_power()
        if base_power is not None:
            client.current_dk_power = max(0, base_power - cost)
        mark_dk_power_changed()
        if not client.kakera_power_ledger.has_pending:
            cancel_external_kakera_power_reconcile()
        return cost

    def should_auto_refill_dk(current_power, required_power):
        return should_refill_kakera_power(
            current_power,
            required_power,
            power_is_confirmed=not client.kakera_power_ledger.has_pending,
            configured_trigger=client.auto_dk_min_power,
        )

    def get_kakera_action_lock():
        if client._kakera_action_lock is None:
            client._kakera_action_lock = asyncio.Lock()
        return client._kakera_action_lock

    def is_maintenance_active() -> bool:
        if client.maintenance_until is None: return False
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        if now_utc >= client.maintenance_until:
            if client.humanization_enabled and not getattr(client, '_maintenance_jitter_applied', False):
                jitter = random.uniform(0, client.humanization_window_minutes * 60)
                client.maintenance_until = now_utc + datetime.timedelta(seconds=jitter)
                client._maintenance_jitter_applied = True
                BotLogger.log(f"Maintenance ended. Humanized re-entry: waiting {jitter/60:.1f}m before resuming.", preset_name, "RESET")
                return True
            client.maintenance_until = None
            client._maintenance_jitter_applied = False
            client._post_maintenance_inactivity_needed = True
            client._post_maint_last_msg_utc = None
            BotLogger.log("Maintenance period ended. Waiting for channel inactivity before resuming.", preset_name, "INFO")
            return False
        return True

    def update_dynamic_thresholds():
        import math
        claim_reset_minutes = None
        if client.next_claim_reset_at_utc:
            now_utc = datetime.datetime.now(timezone.utc)
            claim_reset_minutes = (client.next_claim_reset_at_utc - now_utc).total_seconds() / 60.0

        # Determine total rounds based on the preset's claim interval
        total_rounds = max(1, math.ceil(client.claim_interval / 60))

        if claim_reset_minutes is None or claim_reset_minutes <= 0:
            round_num = total_rounds
        else:
            # Calculate remaining hours
            remaining_hours = math.ceil(claim_reset_minutes / 60)
            # Determine active current round (1-indexed)
            round_num = max(1, total_rounds - remaining_hours + 1)

        active_threshold = None
        if hasattr(client, 'claim_rounds_thresholds') and client.claim_rounds_thresholds:
            for rt in client.claim_rounds_thresholds:
                if rt.get("round") == round_num:
                    active_threshold = rt
                    break

        old_min_kakera = client.min_kakera
        old_max_claim_rank = client.max_claim_rank
        old_max_like_rank = client.max_like_rank

        if active_threshold:
            client.min_kakera = int(active_threshold.get("min_kakera", client.base_min_kakera))
            client.max_claim_rank = int(active_threshold.get("max_claim_rank", client.base_max_claim_rank))
            client.max_like_rank = int(active_threshold.get("max_like_rank", client.base_max_like_rank))
        else:
            client.min_kakera = client.base_min_kakera
            client.max_claim_rank = client.base_max_claim_rank
            client.max_like_rank = client.base_max_like_rank

        if client.current_min_kakera_for_roll_claim != 0:
            client.current_min_kakera_for_roll_claim = client.min_kakera

        if (client.min_kakera != old_min_kakera or
            client.max_claim_rank != old_max_claim_rank or
            client.max_like_rank != old_max_like_rank):
            override_status = "Overrides applied" if active_threshold else "Default settings restored"
            BotLogger.log(
                f"[CLAIM] Interval: {client.claim_interval}m | Round: {round_num}/{total_rounds} active | {override_status} "
                f"(Min Kakera: {client.min_kakera}, Max Claim Rank: {client.max_claim_rank}, Max Like Rank: {client.max_like_rank})",
                preset_name, "RESET"
            )

    async def scheduled_roll_task(channel):
        BotLogger.log(f"Scheduled roll mode active. Times: {client.scheduled_roll_times}", preset_name, "INFO")
        while not client.is_closed():
            try:
                if client.is_paused:
                    await pause_interruptible_sleep(client, 1)
                    continue
                now = datetime.datetime.now()
                min_wait = float('inf')
                next_time = None
                for t_str in client.scheduled_roll_times:
                    try:
                        pts = t_str.strip().split(':')
                        target = now.replace(hour=int(pts[0]), minute=int(pts[1]) if len(pts)>1 else 0, second=0, microsecond=0)
                        if target <= now: target += datetime.timedelta(days=1)
                        wait = (target - now).total_seconds()
                        if wait < min_wait:
                            min_wait, next_time = wait, target
                    except (ValueError, IndexError): pass
                if next_time is None:
                    await pause_interruptible_sleep(client, 60)
                    continue
                BotLogger.log(f"Next scheduled roll at {next_time.strftime('%H:%M')} (in {min_wait/60:.1f}m)", preset_name, "RESET")
                if not await active_delay(min_wait):
                    continue

                if client.humanization_enabled and client.humanization_window_minutes > 0:
                    jitter = random.uniform(0, client.humanization_window_minutes * 60)
                    BotLogger.log(f"Humanized delay: waiting {jitter/60:.1f}m before scheduled roll.", preset_name, "INFO")
                    if not await active_delay(jitter):
                        continue
                if client.is_paused or is_maintenance_active() or is_inactive_hour(): continue
                BotLogger.log("Executing scheduled roll.", preset_name, "INFO")
                client.scheduled_roll_due = True
                if client._immediate_check_event: client._immediate_check_event.set()
            except asyncio.CancelledError: break
            except Exception as e:
                BotLogger.log(f"Scheduled roll error: {e}", preset_name, "ERROR")
                await pause_interruptible_sleep(client, 60)

    async def _fetch_mudae_slash_commands(channel):
        guild = getattr(channel, 'guild', None)
        if not guild: return None
        ckey = (guild.id, channel.id)
        if ckey in client.mudae_slash_cache: return client.mudae_slash_cache[ckey]
        http = getattr(client, "http", None)
        if not http or Route is None: return None
        commands_map = {}
        try:
            route = Route("GET", "/channels/{channel_id}/application-commands/search", channel_id=channel.id)
            resp = await http.request(route, params={"type": 1, "application_id": str(TARGET_BOT_ID), "limit": 25})
            cmd_list = resp.get("application_commands", []) if isinstance(resp, dict) else (resp if isinstance(resp, list) else [])
            for cmd in cmd_list:
                name = str(cmd.get("name", "")).lower()
                if name: commands_map[name] = cmd
            if commands_map:
                client.mudae_slash_cache[ckey] = commands_map
                return commands_map
        except discord.HTTPException as e:
            if getattr(e, 'status', 0) in (401, 403):
                BotLogger.log(f"Slash: Cannot access commands in #{channel.name} (HTTP {e.status}). Check 'Use Application Commands' permission.", preset_name, "ERROR")
                return None
        except Exception: pass
        try:
            route = Route("GET", "/guilds/{guild_id}/application-command-index", guild_id=guild.id)
            resp = await http.request(route)
            cmd_list = resp.get("application_commands", []) if isinstance(resp, dict) else (resp if isinstance(resp, list) else [])
            for cmd in cmd_list:
                if str(cmd.get("application_id", "")) == str(TARGET_BOT_ID):
                    name = str(cmd.get("name", "")).lower()
                    if name: commands_map[name] = cmd
            if commands_map:
                client.mudae_slash_cache[ckey] = commands_map
                return commands_map
        except Exception: pass
        return None

    def _check_slash_permissions(channel) -> tuple:
        g = getattr(channel, 'guild', None)
        if not g or not g.me: return False, "No guild or me context"
        p = channel.permissions_for(g.me)
        if not p.send_messages: return False, "Missing 'Send Messages' permission"
        if hasattr(p, 'use_application_commands') and not p.use_application_commands: return False, "Missing 'Use Application Commands'"
        if not p.read_messages: return False, "Missing 'View Channel'"
        return True, "OK"

    async def _trigger_mudae_slash(channel, command_text):
        cmd_display = f"/{command_text.strip().lstrip('/')}"
        if client.is_paused or is_maintenance_active(): return False
        if not client.use_slash_rolls: return False
        if not channel or not getattr(channel, "guild", None): return False
        stripped = command_text.strip()
        if not stripped: return False

        can_slash, perm_reason = _check_slash_permissions(channel)
        if not can_slash:
            if not client.slash_fallback_active:
                BotLogger.log(f"Slash {cmd_display}: FAIL - {perm_reason}. Activating text fallback.", preset_name, "ERROR")
                client.slash_fallback_active = True
            return False

        now_ts = time.time()
        if client.slash_rate_limited_until and now_ts < client.slash_rate_limited_until: return False
        if client.last_slash_attempt:
            el = now_ts - client.last_slash_attempt
            if el < client.slash_min_interval and not await active_delay(client.slash_min_interval - el):
                return False
        client.last_slash_attempt = time.time()

        if " " in stripped:
            client.mudae_slash_missing.add(f"mixed:{stripped.split(' ', 1)[0].lower()}")
            return False

        base_name = stripped.lstrip("/").lower()
        cmd_map = await _fetch_mudae_slash_commands(channel)
        if not cmd_map or base_name not in cmd_map: return False
        cmd_data = cmd_map[base_name]

        sid = getattr(client.ws, "session_id", None) or client.mudae_session_id
        if not sid: return False
        nonce_val = str(time_snowflake(datetime.datetime.now(datetime.timezone.utc)))
        payload = {
            "type": 2, "application_id": str(TARGET_BOT_ID), "guild_id": str(channel.guild.id),
            "channel_id": str(channel.id), "session_id": sid, "nonce": nonce_val,
            "analytics_location": "slash_ui",
            "data": {
                "version": str(cmd_data.get("version", "")), "id": str(cmd_data.get("id", "")),
                "name": cmd_data.get("name"), "type": cmd_data.get("type", 1), "attachments": [],
                "application_command": {
                    "id": str(cmd_data.get("id", "")), "application_id": str(TARGET_BOT_ID),
                    "version": str(cmd_data.get("version", "")), "type": cmd_data.get("type", 1),
                    "name": cmd_data.get("name"), "description": cmd_data.get("description", ""),
                    "dm_permission": cmd_data.get("dm_permission", True), "options": cmd_data.get("options", []),
                    "name_localized": cmd_data.get("name", ""), "description_localized": cmd_data.get("description", "")
                }
            }
        }
        try:
            if client.is_paused or is_maintenance_active(): return False

            async def post_interaction():
                # Discord may successfully accept an interaction while returning
                # an empty payload. The command was sent as long as this request
                # completed without raising; do not treat that payload as False.
                await client.http.request(Route("POST", "/interactions"), json=payload)
                return True

            if not await paced_mudae_action(
                post_interaction
            ):
                return False
            client.slash_fail_streak = 0
            client.slash_rate_limited_until = 0.0
            return True
        except discord.HTTPException as e:
            if getattr(e, "retry_after", None):
                client.slash_rate_limited_until = time.time() + min(e.retry_after, client.slash_max_backoff)
                if not await active_delay(e.retry_after):
                    return False
            elif getattr(e, "status", 0) in (401, 403):
                BotLogger.log(f"Slash {cmd_display}: FAIL - HTTP {e.status} (Permission Denied). Switching to text fallback.", preset_name, "ERROR")
                client.slash_fallback_active = True
            client.slash_fail_streak += 1
        except Exception:
            client.slash_fail_streak += 1
        client.mudae_slash_cache.pop((channel.guild.id, channel.id), None)
        if client.slash_fail_streak >= client.slash_fail_threshold and not client.slash_fallback_active:
            client.slash_fallback_active = True
            BotLogger.log(f"Slash: {client.slash_fail_streak} failures. Switching to text commands ({client.mudae_prefix}).", preset_name, "WARN")
        return False

    async def send_roll_command(channel, command_name):
        if channel.id != client.target_channel_id:
            channel = client.get_channel(client.target_channel_id) or client._main_channel or channel
        cmd = (command_name or "").strip().lstrip('/')
        if not cmd or client.is_paused or is_maintenance_active(): return False
        if client.use_slash_rolls and not client.slash_fallback_active:
            override = {"w": "wx", "h": "hx", "m": "mx"}.get(cmd.lower(), cmd)
            if await _trigger_mudae_slash(channel, f"/{override}"):
                return True
            # Do not return here if fallback is not yet active. Let it fall through to text commands.
        return await guarded_send(channel, f"{client.mudae_prefix}{cmd}")

    async def wait_for_tu_inactivity(channel):
        """Wait until both the configured active period and channel quiet window allow $tu."""
        waited = False
        while True:
            if client.is_paused or is_maintenance_active():
                return False, waited

            if is_inactive_hour():
                wait_seconds = max(1.0, seconds_until_active())
                if client.humanization_enabled and client.humanization_window_minutes > 0:
                    wait_seconds += random.uniform(0, client.humanization_window_minutes * 60)
                BotLogger.log(
                    f"$tu deferred by inactive hours for {wait_seconds / 60:.1f}m.",
                    preset_name,
                    "RESET",
                )
                waited = True
                if not await active_delay(wait_seconds):
                    return False, waited
                continue

            quiet_seconds = (
                max(0.0, float(client.humanization_inactivity_seconds))
                if client.humanization_enabled
                else 0.0
            )
            if quiet_seconds <= 0:
                return True, waited

            try:
                last_message = None
                async for recent_message in channel.history(limit=1):
                    last_message = recent_message
                    break
                if last_message is None:
                    return True, waited

                created_at = getattr(last_message, "created_at", None)
                if created_at is None:
                    return True, waited
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
                quiet_for = max(
                    0.0,
                    (datetime.datetime.now(timezone.utc) - created_at).total_seconds(),
                )
                remaining = quiet_seconds - quiet_for
                if remaining <= 0:
                    return True, waited

                BotLogger.log(
                    f"$tu inactivity check: waiting {remaining:.1f}s for a quiet channel.",
                    preset_name,
                    "INFO",
                )
                waited = True
                if not await active_delay(remaining + 0.5):
                    return False, waited
            except Exception as exc:
                BotLogger.log(
                    f"$tu inactivity check unavailable ({type(exc).__name__}); continuing.",
                    preset_name,
                    "DEBUG",
                )
                return True, waited

    async def send_tu_command(channel):
        if client.is_paused or is_maintenance_active(): return False
        async def wait_for_global_tu_slot():
            guild_id = getattr(getattr(channel, "guild", None), "id", None)
            pacing_key = guild_id if guild_id is not None else getattr(channel, "id", None)
            global_wait = _tu_interval_coordinator.reserve(pacing_key, TU_GLOBAL_INTERVAL_SECONDS)
            if global_wait <= 0:
                return True
            BotLogger.log(f"Global $tu pacing: waiting {global_wait:.1f}s for this account's slot.", preset_name, "INFO")
            return await active_delay(global_wait)

        async def wait_for_tu_send_window():
            ready, _ = await wait_for_tu_inactivity(channel)
            if not ready:
                return False
            while True:
                if not await wait_for_global_tu_slot():
                    return False
                ready, inactivity_delayed = await wait_for_tu_inactivity(channel)
                if not ready:
                    return False
                if not inactivity_delayed:
                    return True
                # The reserved global slot expired while channel activity was
                # settling. Reserve a new slot so another account cannot send
                # $tu too close to this one.

        if client.use_slash_rolls and not client.slash_fallback_active:
            for attempt in range(1, 4):
                if not await wait_for_tu_send_window(): return False
                if await _trigger_mudae_slash(channel, "tu"): return True
                if client.slash_fallback_active: break
                if attempt < 3 and not await active_delay(5.0): return False
            if not client.slash_fallback_active:
                client.slash_fallback_active = True
                BotLogger.log("/tu failed after 3 attempts. Switching to text $tu so status tracking can continue.", preset_name, "WARN")
        if not await wait_for_tu_send_window(): return False
        return await guarded_send(channel, f"{client.mudae_prefix}tu")

    def _get_command_channel():
        configured = getattr(client, "command_channel", None)
        main = getattr(client, "_main_channel", None)
        if configured is not None and (main is None or same_guild(configured, main)):
            return configured
        try:
            if client.command_channel_id_preset:
                c = client.get_channel(int(client.command_channel_id_preset))
                if c and (main is None or same_guild(c, main)):
                    client.command_channel = c
                    return c
        except Exception: pass
        return main

    def same_guild(a, b):
        return a is not None and b is not None and getattr(getattr(a, "guild", None), "id", None) == getattr(getattr(b, "guild", None), "id", None)

    def _get_forcedivorce_channel(fallback_channel=None):
        configured = getattr(client, "forcedivorce_channel", None)
        if configured is not None:
            return configured
        try:
            if client.forcedivorce_channel_id_preset:
                configured = client.get_channel(int(client.forcedivorce_channel_id_preset))
                if configured is not None:
                    return configured
        except Exception:
            pass
        return fallback_channel or getattr(client, "_main_channel", None)

    async def main_status_loop(client, channel):
        BotLogger.log("Main status loop started.", preset_name, "INFO")
        while not client.is_closed():
            try:
                if client.is_paused:
                    await pause_interruptible_sleep(client, 1)
                    continue
                if is_maintenance_active():
                    await asyncio.sleep(15)  # Quietly sleep during maintenance
                    continue
                await check_status(client, channel, client.mudae_prefix, current_cycle_id=None)
                await asyncio.sleep(1.5)
            except asyncio.CancelledError: break
            except Exception as e:
                BotLogger.log(f"Main loop error: {e}. Retrying in 60s.", preset_name, "ERROR")
                await asyncio.sleep(60)

    @client.event
    async def on_ready():
        ws = getattr(client, "ws", None)
        if ws and getattr(ws, "session_id", None): client.mudae_session_id = ws.session_id

        if client._has_initialized:
            BotLogger.log(f"Reconnected: {client.user}. Checking health...", preset_name, "INFO")
            request_status_refresh(reason="discord-reconnect", urgent=True)
            task = client._main_loop_task
            if task is None or task.done():
                c = getattr(client, '_main_channel', None)
                if c:
                    client._main_loop_task = client.loop.create_task(main_status_loop(client, c) if client.rolling_enabled else snipe_only_status_loop(client, c))
            else:
                if client._immediate_check_event: client._immediate_check_event.set()
            return

        client._has_initialized = True
        client.is_processing_cycle = False
        client._immediate_check_event = asyncio.Event()
        client._runtime_state_event = asyncio.Event()
        client._claim_evidence_event = asyncio.Event()
        BotLogger.log(f"Ready: {client.user}", preset_name, "INFO")
        client.loop.create_task(health_monitor_task())

        try: target_ch_id = int(target_channel_id)
        except Exception:
            BotLogger.log(f"Err: Invalid channel ID format: {target_channel_id}", preset_name, "ERROR"); await client.close(); return

        channel = client.get_channel(target_ch_id) or await client.fetch_channel(target_ch_id)
        if not channel or not isinstance(channel, (discord.TextChannel, discord.Thread, discord.VoiceChannel)):
            BotLogger.log(f"Err: Target channel {target_ch_id} not available or not text-like", preset_name, "ERROR"); await client.close(); return

        client._main_channel = channel

        # Command channel resolution
        if client.command_channel_id_preset:
            try:
                cmd_ch = client.get_channel(int(client.command_channel_id_preset)) or await client.fetch_channel(int(client.command_channel_id_preset))
                if cmd_ch and isinstance(cmd_ch, (discord.TextChannel, discord.Thread, discord.VoiceChannel)):
                    client.command_channel = cmd_ch
                    BotLogger.log(f"Command channel set: #{cmd_ch.name} ({cmd_ch.id})", preset_name, "INFO")
            except Exception:
                BotLogger.log("Command channel config failed. Falling back to main channel.", preset_name, "WARN")

        if client.forcedivorce_channel_id_preset:
            try:
                forcedivorce_ch = (
                    client.get_channel(int(client.forcedivorce_channel_id_preset))
                    or await client.fetch_channel(int(client.forcedivorce_channel_id_preset))
                )
                if forcedivorce_ch and isinstance(forcedivorce_ch, (discord.TextChannel, discord.Thread, discord.VoiceChannel)):
                    client.forcedivorce_channel = forcedivorce_ch
                    BotLogger.log(
                        f"Forcedivorce channel set: #{forcedivorce_ch.name} ({forcedivorce_ch.id})",
                        preset_name,
                        "INFO",
                    )
                else:
                    BotLogger.log("Forcedivorce channel is not text-like. Falling back to roll channel.", preset_name, "WARN")
            except Exception:
                BotLogger.log("Forcedivorce channel config failed. Falling back to roll channel.", preset_name, "WARN")

        if client.rolling_enabled:
            if not channel.permissions_for(channel.guild.me).send_messages:
                BotLogger.log("No Send Permissions in roll channel", preset_name, "ERROR"); await client.close(); return

        manual_start_delay = max(0.0, float(start_delay))
        automated_startup_stagger = max(
            0.0,
            float(getattr(client, "persistent_stagger_seconds", 0)),
        )
        total_start_delay = manual_start_delay + automated_startup_stagger
        BotLogger.log(
            f"Starting in {total_start_delay:.1f}s "
            f"(manual: {manual_start_delay:.1f}s, automated stagger: {automated_startup_stagger:.1f}s)...",
            preset_name,
            "INFO",
        )
        await pause_interruptible_sleep(client, total_start_delay + random.uniform(0.1, 0.5))

        if is_inactive_hour():
            wait_s = seconds_until_active() + (random.uniform(0, client.humanization_window_minutes * 60) if client.humanization_enabled else 0)
            BotLogger.log(f"Inactive hours active. Sleeping {wait_s/60:.0f}m.", preset_name, "RESET")
            await pause_interruptible_sleep(client, wait_s)

        if client.rolling_enabled:
            if not client.skip_initial_commands:
                cmd_ch = _get_command_channel() or channel
                try:
                    if not await guarded_send(cmd_ch, f"{client.mudae_prefix}limroul 1 1 1 1"):
                        return
                    if not await active_delay(1.0 + random.uniform(0.1, 0.4)):
                        return
                except Exception as e:
                    BotLogger.log(f"Setup error: {e}", preset_name, "ERROR"); await client.close(); return
            client._main_loop_task = client.loop.create_task(main_status_loop(client, channel))
            if client.scheduled_roll_times: client.loop.create_task(scheduled_roll_task(channel))
        else:
            client._main_loop_task = client.loop.create_task(snipe_only_status_loop(client, channel))

    async def health_monitor_task():
        unhealthy = 0
        while not client.is_closed():
            await asyncio.sleep(60)
            if client.latency == float('inf'):
                unhealthy += 1
                BotLogger.log(f"Connection lost ({unhealthy}/3).", preset_name, "ERROR")
            else:
                if unhealthy > 0: BotLogger.log(f"Reconnected. Ping: {client.latency * 1000:.0f}ms.", preset_name, "INFO")
                unhealthy = 0
            if unhealthy >= 3:
                BotLogger.log("Connection dead. Restarting.", preset_name, "ERROR")
                try: await client.close()
                except Exception: pass
                return

    async def handle_dk_power_management(client, channel, tu_content):
        c_low = tu_content.lower()
        stock_match = re.search(REGEX_PATTERNS["DK_STOCK"], c_low)
        if stock_match: client.dk_stock_count = int(stock_match.group(1))
        elif re.search(REGEX_PATTERNS["DK_READY"], c_low): client.dk_stock_count = 1
        else: client.dk_stock_count = 0

        if client.dk_stock_count == 0: return

        try:
            power_match = re.search(REGEX_PATTERNS["DK_POWER"], c_low)
            consumption_match = re.search(REGEX_PATTERNS["DK_CONSUMPTION"], c_low)
            if not power_match or not consumption_match: return

            cur_power = int(power_match.group(1))
            cost = int(consumption_match.group(1))
            if getattr(client, 'only_chaos', False):
                cost = calculate_kakera_power_cost(cost, has_chaos_discount=True)

            trigger_power = client.auto_dk_min_power or cost
            if cur_power < trigger_power:
                BotLogger.log(f"DK: Activating. ({cur_power}% < {trigger_power}%)", preset_name, "KAKERA")
                if not await guarded_send(channel, f"{client.mudae_prefix}dk"):
                    return
                if not await active_delay(1.5 + random.uniform(0.1, 0.4)):
                    return
                client.dk_stock_count = max(0, client.dk_stock_count - 1)
                client.current_dk_power = client.max_dk_power
                client.kakera_power_ledger.clear()
                mark_dk_power_changed()
                client.last_dk_power_update_utc = datetime.datetime.now(datetime.timezone.utc)
                request_status_refresh({"power"}, reason="auto-dk-used")
        except Exception as e:
            BotLogger.log(f"DK logic error: {e}", preset_name, "ERROR")

    async def snipe_only_status_loop(client, channel):
        BotLogger.log("Snipe-only: Performing initial handshake...", preset_name, "INFO")
        handshake = False
        while not client.is_closed():
            if client.is_paused:
                await pause_interruptible_sleep(client, 1)
                continue
            if is_maintenance_active():
                await asyncio.sleep(15)
                continue
            try:
                await check_status(client, channel, client.mudae_prefix, proceed_to_rolls=False)
                if client.claim_right_available or client.next_claim_reset_at_utc:
                    handshake = True
                    break
                await _interruptible_sleep(30)
            except Exception:
                await _interruptible_sleep(30)
        if not handshake: return
        BotLogger.log("Snipe-only: Handshake complete. Entering Ghost Mode.", preset_name, "INFO")
        while not client.is_closed():
            if client.is_paused:
                await pause_interruptible_sleep(client, 1)
                continue
            if client.desync_detected:
                await check_status(client, channel, client.mudae_prefix, proceed_to_rolls=False)
                await active_delay(1)
                continue
            now = datetime.datetime.now(datetime.timezone.utc)
            reset_at = client.next_claim_reset_at_utc
            cached_reset = getattr(client, "_snipe_claim_refresh_reset_at_utc", None)
            if reset_at and cached_reset != reset_at:
                refresh_at = humanized_claim_refresh_deadline(
                    reset_at,
                    client.humanization_enabled,
                    client.humanization_window_minutes,
                )
                client._snipe_claim_refresh_reset_at_utc = reset_at
                client._snipe_claim_refresh_at_utc = refresh_at
                client._snipe_claim_refresh_completed_for = None
                delay_seconds = max(0.0, (refresh_at - reset_at).total_seconds())
                if delay_seconds > 0:
                    BotLogger.log(
                        f"Snipe-only: Humanized claim status refresh scheduled {delay_seconds/60:.1f}m after reset.",
                        preset_name,
                        "RESET",
                    )

            refresh_at = getattr(client, "_snipe_claim_refresh_at_utc", None)
            refresh_completed_for = getattr(client, "_snipe_claim_refresh_completed_for", None)
            if reset_at and refresh_at and refresh_completed_for != reset_at:
                if refresh_at > now:
                    wait_s = max(1.0, (refresh_at - now).total_seconds())
                    BotLogger.log(f"Snipe-only: Silent. Sleeping {wait_s/60:.1f}m.", preset_name, "RESET")
                    try: await _interruptible_sleep(wait_s)
                    except asyncio.CancelledError: break
                    continue

                client._snipe_claim_refresh_completed_for = reset_at
                client._claim_reset_refresh_requested = True
                request_status_refresh({"claim"}, reason="snipe-claim-reset", urgent=True)
                await check_status(client, channel, client.mudae_prefix, proceed_to_rolls=False)
                continue

            await _interruptible_sleep(10)

    async def _interruptible_sleep(seconds):
        evt = client._immediate_check_event
        if evt is None:
            await pause_interruptible_sleep(client, seconds)
            return
        try:
            await asyncio.wait_for(evt.wait(), timeout=max(0.0, seconds))
            evt.clear()
        except asyncio.TimeoutError:
            pass

    def pending_roll_work(proceed_to_rolls=True):
        if not client.rolling_enabled or not proceed_to_rolls:
            return False, False, False
        pending_rolls = False
        if client.auto_rolls_enabled:
            limit_ok = client.auto_rolls_limit == 0 or client.rolls_item_used_count < client.auto_rolls_limit
            claim_ok = client.claim_right_available or (client.key_mode and client.auto_rolls_in_key_mode)
            if not rolls_usage_is_active(client.rolls_used_this_interval_utc):
                client.rolls_used_this_interval_utc = None
            used, reset = client.rolls_used_this_interval_utc, client.roll_reset_at_utc
            hour_ok = not client.auto_rolls_only_claim_hour or bool(client.next_claim_reset_at_utc and reset and client.next_claim_reset_at_utc <= reset)
            ack_retry_ready = time.monotonic() >= client._rolls_ack_retry_after
            pending_rolls = limit_ok and used is None and claim_ok and hour_ok and ack_retry_ready
        power = get_current_dk_power()
        pending_us = (client.auto_us_enabled and not client._us_in_flight
                      and time.monotonic() >= client._us_retry_after
                      and not (client.auto_us_stop_on_claim and not client.claim_right_available)
                      and not (client.auto_us_limit > 0 and client.us_pulled_this_cycle >= client.auto_us_limit)
                      and not client.us_failed_this_cycle)
        pending_mk = (client.auto_mk_enabled and client.mk_rolls_left > 0 and power is not None and
                      (client.mk_bypass_power_check or (power >= client.max_dk_power if client.auto_mk_full_power_only else power >= client.dk_consumption)))
        return pending_rolls, pending_us, pending_mk

    async def check_status(client, channel, mudae_prefix, proceed_to_rolls: bool = True, current_cycle_id=None):
        if client.is_paused or is_maintenance_active(): return
        if getattr(client, 'is_claiming', False): return
        if getattr(client, 'is_processing_cycle', False): return
        if (
            float(getattr(client, '_status_cycle_not_before_monotonic', 0.0) or 0.0) > time.monotonic()
            and not status_dirty_fields(client)
            and not client.scheduled_roll_due
            and not getattr(client, '_local_extra_rolls_pending', 0)
            and not getattr(client, '_claim_reset_rolls_pending', False)
        ):
            return
        client._status_cycle_not_before_monotonic = 0.0
        client.is_processing_cycle = True

        can_claim = False
        claim_ready = False
        wait_time = 0

        update_dynamic_thresholds()

        try:
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            if current_cycle_id is None:
                current_cycle_id = time.time()
                client.active_cycle_id = current_cycle_id
            cmd_channel = _get_command_channel() or channel

            local_extra_rolls = int(getattr(client, '_local_extra_rolls_pending', 0))
            if local_extra_rolls > 0 and client.rolls_left <= 0:
                client._local_extra_rolls_pending = 0
            elif (local_extra_rolls > 0 and client.rolling_enabled and proceed_to_rolls
                  and not status_dirty_fields(client) and not client.scheduled_roll_due):
                client._local_extra_rolls_pending = 0
                BotLogger.log(f"Rolling {client.rolls_left} locally confirmed bonus roll(s) without another $tu.", preset_name, "INFO")
                await start_roll_commands(
                    client,
                    channel,
                    client.rolls_left,
                    client.current_min_kakera_for_roll_claim == 0,
                    client.key_mode and not client.rt_available and not client.claim_right_available,
                    current_cycle_id,
                )
                return

            can_bypass = False
            cache_seconds_remaining = 0.0
            known_idle_boundary = False
            if client.last_tu_snapshot_complete and client.last_tu_query_utc is not None and not status_dirty_fields(client) and not client.scheduled_roll_due:
                cache_seconds_remaining = tu_cache_seconds_remaining(
                    client.last_tu_query_utc,
                    now_utc,
                )
                is_before_claim = client.next_claim_reset_at_utc is None or now_utc < client.next_claim_reset_at_utc
                is_before_roll = client.roll_reset_at_utc is None or now_utc < client.roll_reset_at_utc
                known_idle_boundary = bool(
                    (client.next_claim_reset_at_utc and is_before_claim)
                    or (client.roll_reset_at_utc and is_before_roll)
                )
                # When the account has no rolls or pending work, the reset
                # deadlines are the next moments its state can become useful.
                # Trust those explicit boundaries beyond the generic cache TTL
                # instead of issuing an otherwise identical $tu every 30m.
                if cache_seconds_remaining > 0 or known_idle_boundary:
                    if is_before_claim and is_before_roll and client.rolls_left <= 0:
                        can_bypass = True
                        claim_reset_m_check = (
                            max(0.0, (client.next_claim_reset_at_utc - now_utc).total_seconds() / 60.0)
                            if client.next_claim_reset_at_utc
                            else None
                        )
                        if (
                            client.time_rolls_to_claim_reset
                            and not client.claim_right_available
                            and claim_reset_m_check is not None
                            and claim_reset_m_check <= 60.0
                        ):
                            can_bypass = False
                        pending_rolls, pending_us, pending_mk = pending_roll_work(proceed_to_rolls)
                        if pending_rolls or pending_us or pending_mk:
                            can_bypass = False
                        sphere_retry_due = any(
                            enabled
                            and client.sphere_game_counts.get(kind, 0) > 0
                            and time.monotonic() >= client._sphere_game_retry_after.get(kind, 0.0)
                            for kind, enabled in (
                                ("oh", client.auto_oh_enabled),
                                ("oc", client.auto_oc_enabled),
                            )
                        )
                        sphere_refill_due = bool(
                            (client.auto_oh_enabled or client.auto_oc_enabled)
                            and client.sphere_game_refill_at_utc is not None
                            and now_utc >= client.sphere_game_refill_at_utc
                        )
                        if sphere_retry_due or sphere_refill_due:
                            can_bypass = False

            if can_bypass:
                BotLogger.log("Skipping $tu (using cached status).", preset_name, "CHECK")
                claim_reset_m = max(0.0, (client.next_claim_reset_at_utc - now_utc).total_seconds() / 60.0) if client.next_claim_reset_at_utc else 0.0
                roll_reset_m = max(0.0, (client.roll_reset_at_utc - now_utc).total_seconds() / 60.0) if client.roll_reset_at_utc else 0.0
                wait_time = claim_reset_m if not client.claim_right_available else 0
                if client.rolling_enabled and proceed_to_rolls:
                    choices = []
                    if not known_idle_boundary:
                        choices.append((
                            max(0.05, cache_seconds_remaining / 60.0),
                            "cached status refresh",
                        ))
                    if wait_time > 0: choices.append((float(wait_time), "claim cooldown"))
                    if client.time_rolls_to_claim_reset and not client.claim_right_available and claim_reset_m > 60: choices.append((float(claim_reset_m - 60), "timing threshold arrival"))
                    if roll_reset_m > 0: choices.append((float(roll_reset_m), "rolls replenishment"))
                    if choices:
                        choices.sort(key=lambda x: x[0])
                        selected_wait_minutes, selected_reason = choices[0]
                        client._status_cycle_not_before_monotonic = time.monotonic() + max(
                            3.0,
                            selected_wait_minutes * 60.0,
                        )
                        await humanized_wait_and_proceed(
                            client,
                            channel,
                            max(0.05, selected_wait_minutes),
                            selected_reason,
                        )
                    else:
                        client._status_cycle_not_before_monotonic = time.monotonic() + max(
                            3.0,
                            float(client.roll_interval) * 60.0,
                        )
                        await humanized_wait_and_proceed(client, channel, client.roll_interval, "configured roll interval")
                return

            retry_wait = tu_retry_wait(client)
            if retry_wait > 0 and consume_tu_urgent_bypass(client):
                BotLogger.log("Urgent claim/status evidence is bypassing the current $tu backoff once.", preset_name, "CHECK")
                retry_wait = 0
            if retry_wait > 0:
                now_mono = time.monotonic()
                if now_mono - getattr(client, '_tu_last_defer_log_monotonic', 0.0) >= 15.0:
                    dirty = ", ".join(sorted(status_dirty_fields(client))) or "scheduled status"
                    BotLogger.log(f"Deferring $tu for {retry_wait:.0f}s after an incomplete status update ({dirty}).", preset_name, "INFO")
                    client._tu_last_defer_log_monotonic = now_mono
                return

            if client.delay_seconds > 0:
                await _interruptible_sleep(client.delay_seconds)
            reasons = status_refresh_reasons(client)
            reason_text = ", ".join(reasons) if reasons else ("scheduled-roll" if client.scheduled_roll_due else "status-boundary")
            tu_may_reconcile_pending_power = any(
                reason == "external-kakera-result-reconcile"
                for reason in reasons
            )
            BotLogger.log(f"Checking $tu... (reason: {reason_text})", preset_name, "CHECK")
            tu_content = None
            tu_power_revision = None
            if client.tu_lock is None: client.tu_lock = asyncio.Lock()
            if client.tu_lock.locked(): return

            async with client.tu_lock:
                request_started_at = datetime.datetime.now(timezone.utc)
                response_future = asyncio.get_running_loop().create_future()
                client._tu_response_future = response_future
                client._tu_response_channel_id = getattr(cmd_channel, 'id', None)
                client._tu_request_started_at = request_started_at
                try:
                    for attempt in range(2):
                        if not await send_tu_command(cmd_channel):
                            return
                        if tu_power_revision is None:
                            # A later local click makes this response unsafe for
                            # automatic DK decisions, even if the response
                            # arrives after that click.
                            tu_power_revision = client.dk_power_revision
                        client.tu_query_count += 1
                        timeout = 5.5 if attempt == 0 else 8.0
                        try:
                            tu_content = await asyncio.wait_for(asyncio.shield(response_future), timeout=timeout)
                        except asyncio.TimeoutError:
                            async for msg in cmd_channel.history(limit=15):
                                created_at = getattr(msg, 'created_at', None)
                                if created_at is not None and created_at < request_started_at - datetime.timedelta(seconds=1):
                                    continue
                                if is_tu_response_for_self(msg):
                                    tu_content = msg.content
                                    break
                        if tu_content:
                            break
                        if attempt == 0 and not await active_delay(2.0):
                            return
                finally:
                    if client._tu_response_future is response_future:
                        client._tu_response_future = None
                        client._tu_response_channel_id = None
                        client._tu_request_started_at = None
                    if not response_future.done():
                        response_future.cancel()

                if not tu_content:
                    backoff = record_tu_failure(client)
                    BotLogger.log(f"Failed to get $tu response. Retrying in {backoff:.0f}s (2-command limit).", preset_name, "ERROR")
                    return

                record_tu_success(client)
                c_lower = tu_content.lower()

            # Validate $tu response categories and log warnings if essential sections are missing
            explicit_claim_cooldown = parse_claim_denied_cooldown(c_lower)
            if not ((
                        explicit_claim_cooldown is None
                        and re.search(REGEX_PATTERNS["CLAIM_READY"], c_lower)
                    ) or
                    re.search(REGEX_PATTERNS["CLAIM_RESET"], c_lower) or
                    explicit_claim_cooldown is not None or
                    re.search(REGEX_PATTERNS["CLAIM_COOLDOWN"], c_lower)):
                BotLogger.log("Your $tu response is missing the 'claim' category. Run '$tuarrange' in Discord to include it.", preset_name, "WARN")

            if not re.search(REGEX_PATTERNS["ROLLS_COUNT"], c_lower, re.DOTALL):
                BotLogger.log("Your $tu response is missing the 'rolls' or 'rollsreset' category. Run '$tuarrange' in Discord to include it.", preset_name, "WARN")

            v_rt_ready = any(x in c_lower for x in ["$rt is available", "$rt está pronto", "$rt esta pronto", "$rt está disponível", "$rt está disponible", "$rt est disponible", "$rt est prêt", "$rt is ready"])
            v_rt_reset = parse_timer_minutes("RT_RESET", c_lower)
            v_rt_present = bool(v_rt_ready or v_rt_reset is not None or "$rt" in c_lower or re.search(r'\brt\b', c_lower))
            missing_tu_categories = getattr(client, "_tu_missing_categories", set())
            missing_tu_category_warnings = getattr(client, "_tu_missing_category_warnings", set())
            if v_rt_present:
                missing_tu_categories.discard("rt")
                missing_tu_category_warnings.discard("rt")
            else:
                missing_tu_categories.add("rt")
                if "rt" not in missing_tu_category_warnings:
                    BotLogger.log("Your $tu response is missing the 'rt' category. Run '$tuarrange' in Discord to include it. RT automation will stay disabled until it appears.", preset_name, "WARN")
                    missing_tu_category_warnings.add("rt")
                # Repeating the same $tu query cannot make an unconfigured
                # optional category authoritative; clear stale RT dirtiness.
                clear_status_dirty(client, {"rt"})

            if not (re.search(REGEX_PATTERNS["DK_POWER"], c_lower) or
                    re.search(REGEX_PATTERNS["DK_CONSUMPTION"], c_lower)):
                BotLogger.log("Your $tu response is missing the 'kakerapower' or 'kakerainfo' category. Run '$tuarrange' in Discord to include it.", preset_name, "WARN")

            if not ("$dk" in c_lower or
                    re.search(REGEX_PATTERNS["DK_STOCK"], c_lower) or
                    re.search(REGEX_PATTERNS["DK_READY"], c_lower) or
                    re.search(REGEX_PATTERNS["DK_COOLDOWN"], c_lower)):
                BotLogger.log("Your $tu response is missing the 'dk' category. Run '$tuarrange' in Discord to include it.", preset_name, "WARN")

            power_snapshot_is_authoritative = False
            try:
                power_match = re.search(REGEX_PATTERNS["DK_POWER"], c_lower)
                if power_match:
                    power_snapshot_is_authoritative = (
                        tu_power_revision is not None
                        and tu_power_revision == client.dk_power_revision
                        and (
                            not client.kakera_power_ledger.has_pending
                            or tu_may_reconcile_pending_power
                        )
                    )
                    if power_snapshot_is_authoritative:
                        client.current_dk_power = int(power_match.group(1))
                        client.kakera_power_ledger.clear()
                        cancel_external_kakera_power_reconcile()
                        client.last_dk_power_update_utc = datetime.datetime.now(timezone.utc)
                    else:
                        request_status_refresh(
                            {"power"},
                            reason="power-changed-during-tu",
                        )
                        BotLogger.log(
                            "Ignoring $tu power for automatic DK: a paid Kakera click is still awaiting its result "
                            "or power changed while the query was in flight.",
                            preset_name,
                            "DEBUG",
                            client,
                        )
                consumption_match = re.search(REGEX_PATTERNS["DK_CONSUMPTION"], c_lower)
                if consumption_match:
                    client.dk_consumption = int(consumption_match.group(1))
                dk_stock_match = re.search(REGEX_PATTERNS["DK_STOCK"], c_lower)
                if dk_stock_match: client.dk_stock_count = int(dk_stock_match.group(1))
                elif re.search(REGEX_PATTERNS["DK_READY"], c_lower): client.dk_stock_count = 1
                else: client.dk_stock_count = 0
            except Exception as e:
                BotLogger.log(f"Error parsing Power/DK state: {e}", preset_name, "WARN")

            if (client.auto_dk_enabled and client.dk_power_management and client.rolling_enabled
                    and power_snapshot_is_authoritative):
                await handle_dk_power_management(client, cmd_channel, tu_content)

            if client.rolling_enabled:
                if any(x in c_lower for x in [
                    "$daily is available",
                    "$daily está disponível",
                    "$daily está pronto",
                    "$daily esta pronto",
                    "$daily está disponible",
                    "$daily est disponible",
                ]):
                    BotLogger.log("$daily is available! Sending command...", preset_name, "INFO")
                    if not await guarded_send(cmd_channel, f"{client.mudae_prefix}daily"):
                        return
                    if not await active_delay(2.0 + random.uniform(0.1, 0.5)):
                        return

                if client.auto_dk_enabled and not client.dk_power_management:
                    if re.search(r"\$dk.*?(?:ready|pronto|disponible|prêt|dispon[ií]vel|listo)", c_lower):
                        BotLogger.log("$dk is ready! Sending command...", preset_name, "INFO")
                        if not await guarded_send(cmd_channel, f"{client.mudae_prefix}dk"):
                            return
                        if not await active_delay(2.0 + random.uniform(0.1, 0.5)):
                            return

                if client.auto_p_enabled:
                    p_on_cooldown = client.next_p_claim_at_utc and now_utc < client.next_p_claim_at_utc
                    if not p_on_cooldown:
                        p_ready = any(x in c_lower for x in [
                            "$p is available", "$p is ready",
                            "$p está disponível", "$p está pronto", "$p esta pronto",
                            "$p está disponible", "$p est disponible",
                        ])
                        p_cooldown_mins = parse_timer_minutes("P_COOLDOWN", c_lower)
                        if p_cooldown_mins is not None:
                            client.p_available = False
                            client.next_p_claim_at_utc = (now_utc + datetime.timedelta(minutes=p_cooldown_mins)).replace(second=0, microsecond=0)
                            schedule_points_refresh(client.next_p_claim_at_utc)
                            BotLogger.log(f"Points ($p): Cooldown ({int(p_cooldown_mins/60)}h {p_cooldown_mins%60}m)", preset_name, "INFO")
                        elif p_ready:
                            client.p_available = True
                            client.next_p_claim_at_utc = None
                            BotLogger.log("Points ($p): Ready", preset_name, "INFO")

                        if client.p_available:
                            BotLogger.log("$p is available! Sending command...", preset_name, "INFO")
                            if not await guarded_send(cmd_channel, f"{client.mudae_prefix}p"):
                                return
                            client.p_available = False
                            client.next_p_claim_at_utc = (datetime.datetime.now(timezone.utc) + datetime.timedelta(hours=2)).replace(second=0, microsecond=0)
                            schedule_points_refresh(client.next_p_claim_at_utc)
                            if not await active_delay(2.0 + random.uniform(0.1, 0.5)):
                                return

            rt_ready = any(x in c_lower for x in ["$rt is available", "$rt está pronto", "$rt esta pronto", "$rt está disponível", "$rt está disponible", "$rt est disponible", "$rt est prêt", "$rt is ready"])
            sphere_status = parse_sphere_game_status(tu_content)
            if sphere_status is not None:
                if client.auto_oh_enabled or client.auto_oc_enabled:
                    BotLogger.log(
                        f"Sphere games: $oh {sphere_status.available_for('oh')}"
                        + (f" ({sphere_status.oh} daily + {sphere_status.oh_stored} stored)" if sphere_status.oh_stored else "")
                        + f", $oc {sphere_status.available_for('oc')}"
                        + (f" ({sphere_status.oc} daily + {sphere_status.oc_stored} stored)" if sphere_status.oc_stored else "")
                        + (f", refill in {sphere_status.refill_minutes}m." if sphere_status.refill_minutes is not None else "."),
                        preset_name,
                        "INFO",
                    )
                await run_available_sphere_games(cmd_channel, sphere_status)
            elif client.auto_oh_enabled or client.auto_oc_enabled:
                BotLogger.log(
                    "Auto $oh/$oc is enabled but sphere-game stocks are missing from $tu.",
                    preset_name,
                    "WARN",
                )

            rt_reset_minutes = parse_timer_minutes("RT_RESET", c_lower)
            if rt_reset_minutes is not None:
                client.rt_available = False
                client.rt_available_at_utc = cooldown_deadline(now_utc, rt_reset_minutes)
                BotLogger.log(f"RT: Cooldown ({int(rt_reset_minutes/60)}h {rt_reset_minutes%60}m)", preset_name, "INFO")
            elif rt_ready:
                client.rt_available = True
                client.rt_available_at_utc = None
                BotLogger.log("RT: Ready", preset_name, "INFO")
            else:
                client.rt_available = False
                client.rt_available_at_utc = None
            wait_time = 0
            can_claim = False
            claim_ready = bool(
                explicit_claim_cooldown is None
                and re.search(REGEX_PATTERNS["CLAIM_READY"], c_lower)
            )

            claim_reset_minutes = None
            m_reset = re.search(REGEX_PATTERNS["CLAIM_RESET"], c_lower)
            if m_reset and not any(kw in m_reset.group(0) for kw in ["$daily", "$dk", "$rt"]):
                h_c, m_c = parse_hm(m_reset)
                claim_reset_minutes = h_c * 60 + m_c
            else:
                claim_reset_minutes = explicit_claim_cooldown
                if claim_reset_minutes is None:
                    claim_reset_minutes = parse_timer_minutes("CLAIM_COOLDOWN", c_lower)

            if claim_reset_minutes is not None:
                wait_time = claim_reset_minutes

            if claim_ready:
                client.claim_right_available = True
                client.last_successfully_claimed_character = None
                client.claim_cooldown_until_utc = None
                client._claim_reset_refresh_requested = False
                BotLogger.log("Claim: Ready", preset_name, "INFO")
                client.current_min_kakera_for_roll_claim = client.min_kakera
                if client.snipe_ignore_min_kakera_reset and claim_reset_minutes is not None and claim_reset_minutes <= 60:
                    client.current_min_kakera_for_roll_claim = 0
                    BotLogger.log(f"Reset soon ({claim_reset_minutes}m). Ignoring Min Kakera.", preset_name, "WARN")
                client.next_claim_reset_at_utc = cooldown_deadline(now_utc, claim_reset_minutes) if claim_reset_minutes is not None else None
                can_claim = True
                await resolve_pending_claim_from_status(claim_available=True, channel=channel)
                if getattr(client, '_claim_reset_rolls_pending', False) and client.collected_rolls:
                    deferred_rolls = list(client.collected_rolls)
                    client.collected_rolls.clear()
                    client._claim_reset_rolls_pending = False
                    BotLogger.log(
                        f"Processing {len(deferred_rolls)} roll(s) saved at the claim reset boundary.",
                        preset_name,
                        "CLAIM",
                    )
                    await handle_mudae_messages(
                        client,
                        channel,
                        deferred_rolls,
                        client.current_min_kakera_for_roll_claim == 0,
                        client.key_mode and not client.rt_available and not client.claim_right_available,
                    )
            elif claim_reset_minutes is not None:
                client.current_min_kakera_for_roll_claim = client.min_kakera
                BotLogger.log(f"Claim: Cooldown ({int(claim_reset_minutes/60)}h {claim_reset_minutes%60}m)", preset_name, "INFO")
                set_claim_cooldown(claim_reset_minutes, source="$tu")
                await resolve_pending_claim_from_status(claim_available=False, channel=channel)
            else:
                wait_g = parse_timer_minutes("GENERIC_COOLDOWN", c_lower.split('\n')[0])
                if wait_g is not None:
                    wait_time = wait_g
                    claim_reset_minutes = wait_time
                    BotLogger.log(f"Claim: Cooldown ({int(wait_time/60)}h {wait_time%60}m) (Generic)", preset_name, "INFO")
                    set_claim_cooldown(wait_time, source="$tu generic timer")
                    await resolve_pending_claim_from_status(claim_available=False, channel=channel)
                else:
                    can_claim = client.claim_right_available
                    BotLogger.log("Claim state was not present in $tu; keeping the last verified state.", preset_name, "WARN")
                    await resolve_pending_claim_from_status(claim_available=None, channel=channel)

            if client.pending_claim:
                mark_status_dirty(client, {"claim"}, reason="pending-claim-unresolved", urgent=True)
                defer_tu_queries(client, 45.0)
                return

            roll_reset_minutes = parse_timer_minutes("ROLL_RESET", c_lower)
            if roll_reset_minutes is not None:
                # This account's complete $tu is authoritative. Keep the
                # parsed boundary if the narrower roll-count parser misses
                # the same localized reset phrase below.
                client.roll_reset_at_utc = cooldown_deadline(now_utc, roll_reset_minutes)

            if any(x in c_lower for x in ["you __can__ react", "pode reagir", "pegar kakera", "puedes__ reaccionar", "puedes reaccionar", "pouvez__ réagir", "pouvez réagir"]):
                client.kakera_react_available = True
                client.kakera_react_cooldown_until_utc = None
            elif any(x in c_lower for x in ["can't react", "não pode", "no puedes"]):
                client.kakera_react_available = False
                k_cooldown = parse_timer_minutes("KAKERA_COOLDOWN", c_lower)
                if k_cooldown is not None:
                    client.kakera_react_cooldown_until_utc = now_utc + datetime.timedelta(minutes=k_cooldown)

            fresh_fields = set()
            if claim_ready or claim_reset_minutes is not None:
                fresh_fields.add("claim")
            if re.search(REGEX_PATTERNS["ROLLS_COUNT"], c_lower, re.DOTALL) and roll_reset_minutes is not None:
                fresh_fields.add("rolls")
            if rt_ready or rt_reset_minutes is not None:
                fresh_fields.add("rt")
            if power_match and power_snapshot_is_authoritative:
                fresh_fields.add("power")
            if dk_stock_match or re.search(REGEX_PATTERNS["DK_READY"], c_lower) or re.search(REGEX_PATTERNS["DK_COOLDOWN"], c_lower):
                fresh_fields.add("dk")
            if "$p" in c_lower or "$daily" in c_lower:
                fresh_fields.add("points")
            clear_status_dirty(client, fresh_fields)
            required_fields = {"claim", "rolls"} if proceed_to_rolls else {"claim"}
            if "rt" not in getattr(client, "_tu_missing_categories", set()):
                required_fields.add("rt")
            core_complete = required_fields.issubset(fresh_fields)
            client.last_tu_snapshot_complete = core_complete
            client.last_tu_query_utc = datetime.datetime.now(timezone.utc) if core_complete else None
            if not core_complete:
                mark_status_dirty(client, required_fields - fresh_fields, reason="partial-tu-response")
                defer_tu_queries(client, 30.0)
            else:
                if not any(r == "power-changed-during-tu" for r in status_refresh_reasons(client)):
                    clear_status_dirty(client)
                else:
                    client._status_refresh_reasons.discard("mudae-maintenance")
                    client._status_refresh_reasons.discard("discord-reconnect")
            if client.key_limit_hit:
                BotLogger.log("Recovering from key limit. Skipping rolls.", preset_name, "INFO")
                client.key_limit_hit = False
                return

            is_timing_window = bool(client.time_rolls_to_claim_reset and claim_reset_minutes is not None and claim_reset_minutes <= 60)
            is_panic_window = is_lurking = False
            if client.lurker_mode and client.claim_right_available and claim_reset_minutes is not None:
                if claim_reset_minutes <= client.panic_roll_minutes:
                    is_panic_window = True
                    client.current_min_kakera_for_roll_claim = 0
                    BotLogger.log(f"Panic Roll Mode: Reset soon ({claim_reset_minutes}m). Dumping everything.", preset_name, "CLAIM")
                else:
                    is_lurking = True
                    BotLogger.log(f"Lurking Mode: Waiting. Panic in {claim_reset_minutes - client.panic_roll_minutes}m.", preset_name, "INFO")

            immediate_roll = (client.rolling_enabled and proceed_to_rolls and
                             (client.scheduled_roll_due or (can_claim and not is_lurking) or client.key_mode or client.rt_available or is_timing_window or is_panic_window))

            mk_match = re.search(REGEX_PATTERNS["MK_BONUS"], c_lower)
            client.mk_rolls_left = int(re.sub(r"[^\d]", "", mk_match.group(1))) if mk_match else 0

            if client.rolling_enabled and proceed_to_rolls and not immediate_roll:
                if pending_roll_work(proceed_to_rolls)[2]:
                    await process_mk_rolls(client, channel, current_cycle_id)
                    if not await active_delay(2): return
                    return

            pending_rolls, pending_us, _ = pending_roll_work(proceed_to_rolls)
            should_evaluate_roll_state = immediate_roll or pending_rolls or pending_us
            if should_evaluate_roll_state:
                scheduled_trigger = client.scheduled_roll_due
                client.scheduled_roll_due = False
                if scheduled_trigger:
                    BotLogger.log("Scheduled trigger is forcing an available-roll check.", preset_name, "RESET")
                await check_rolls_left_tu(client, channel, mudae_prefix, log_function, preset_name,
                                          tu_content, (client.current_min_kakera_for_roll_claim == 0),
                                          (client.key_mode and not client.rt_available and not client.claim_right_available),
                                          current_cycle_id)
            elif client.rolling_enabled and proceed_to_rolls:
                sleep_choices = []
                if wait_time > 0: sleep_choices.append((float(wait_time), "claim cooldown"))
                if client.time_rolls_to_claim_reset and not client.claim_right_available and claim_reset_minutes is not None and claim_reset_minutes > 60:
                    sleep_choices.append((float(claim_reset_minutes - 60), "timing threshold arrival"))
                if is_lurking and claim_reset_minutes is not None:
                    sleep_choices.append((float(claim_reset_minutes - client.panic_roll_minutes), "panic roll window arrival"))
                if rt_reset_minutes is not None and rt_reset_minutes > 0:
                    sleep_choices.append((float(rt_reset_minutes), "$rt reset"))
                if roll_reset_minutes is not None and roll_reset_minutes > 0:
                    sleep_choices.append((float(roll_reset_minutes), "rolls replenishment"))

                if sleep_choices:
                    sleep_choices.sort(key=lambda x: x[0])
                    await humanized_wait_and_proceed(client, channel, max(0.05, sleep_choices[0][0]), sleep_choices[0][1])
                else:
                    await humanized_wait_and_proceed(client, channel, 30, "default status cycle")
        finally:
            client.is_processing_cycle = False

    async def send_auto_us(amount, fallback_channel):
        if client._us_lock is None:
            client._us_lock = asyncio.Lock()
        async with client._us_lock:
            if client._us_in_flight:
                return False
            cmd_channel = _get_command_channel() or fallback_channel
            chunks = [amount]
            if client.bulk_us_enabled and amount > 20:
                chunks = [20] * (amount // 20) + ([amount % 20] if amount % 20 else [])
            sent = 0
            for chunk in chunks:
                if not await guarded_send(cmd_channel, f"{client.mudae_prefix}us {chunk}"):
                    if sent == 0:
                        client._us_retry_after = time.monotonic() + 30
                        return False
                    break
                sent += chunk
                if len(chunks) > 1 and sent < amount:
                    if not await active_delay(random.uniform(1.5, 2.5)):
                        break
            if sent == 0:
                return False
            client._us_in_flight = True
            client._us_pending_amount = sent
            mode = " in bulk mode" if len(chunks) > 1 else ""
            BotLogger.log(f"Auto $us: requested {sent} saved roll(s){mode}; awaiting $tu confirmation.", preset_name, "INFO")
            await active_delay(1.5)
            request_status_refresh({"rolls"}, reason="auto-us-sent", urgent=True)
            return True

    async def check_rolls_left_tu(client, channel, mudae_prefix, log_function, preset_name,
                                  tu_message_content_for_rolls, ignore_limit_for_post_roll, key_mode_only_kakera_for_post_roll, current_cycle_id):
        content_lower = tu_message_content_for_rolls.lower()
        rolls_left = us_rolls_left = reset_time_r = 0
        now_utc = datetime.datetime.now(timezone.utc)

        main_match = re.search(REGEX_PATTERNS["ROLLS_COUNT"], content_lower, re.DOTALL)
        if main_match:
            rolls_left = int(re.sub(r"[^\d]", "", main_match.group(1)))
            if rolls_left > 0:
                # Keep the normal roll count separate from any ``(+N $us)``
                # bonus.  A successful ``$rolls`` acknowledgement can then
                # resume the same normal-roll batch without another ``$tu``.
                client._last_normal_roll_count = rolls_left
            for bonus_match in re.finditer(REGEX_PATTERNS["BONUS_ROLLS"], main_match.group(2)):
                amt = int(re.sub(r"[^\d]", "", bonus_match.group(1)))
                if bonus_match.group(2).lower() == "us": us_rolls_left += amt
                else: client.mk_rolls_left = amt

            reported_reset_time_r = parse_timer_minutes("ROLL_RESET_TU", content_lower[main_match.end():])
            known_roll_deadline = getattr(client, 'roll_reset_at_utc', None)
            reset_time_r = roll_reset_wait_minutes(
                reported_reset_time_r,
                known_roll_deadline,
                now_utc,
            )
            if reported_reset_time_r is not None:
                new_reset = (now_utc + datetime.timedelta(minutes=reset_time_r)).replace(second=0, microsecond=0)
                if getattr(client, 'roll_reset_at_utc', None) and (new_reset - client.roll_reset_at_utc).total_seconds() > 600:
                    client.us_pulled_this_cycle = 0
                    client.us_failed_this_cycle = False
                client.roll_reset_at_utc = new_reset
            elif known_roll_deadline is None or known_roll_deadline <= now_utc:
                client.roll_reset_at_utc = (now_utc + datetime.timedelta(minutes=reset_time_r)).replace(second=0, microsecond=0)

            total_rolls = rolls_left + us_rolls_left
            client.rolls_left = total_rolls
            if client._us_in_flight:
                requested = client._us_pending_amount
                if us_rolls_left > 0:
                    client.us_pulled_this_cycle += min(requested, us_rolls_left)
                    client._us_in_flight = False
                    client._us_pending_amount = 0
                else:
                    # A $tu response can race the saved-roll command and still
                    # report normal rolls, or the command can be rejected while
                    # those rolls remain.  Either way this request is no longer
                    # in flight.  Keeping the flag set here permanently disables
                    # Auto $us until the process is restarted.
                    client._us_in_flight = False
                    client._us_pending_amount = 0
                    client._us_retry_after = (
                        0.0 if total_rolls > 0 else time.monotonic() + 30
                    )
                    if total_rolls > 0:
                        BotLogger.log(
                            "Auto $us was not acknowledged while normal rolls remain; "
                            "it will retry after they finish.",
                            preset_name,
                            "INFO",
                        )

            if total_rolls == 0:
                if is_inactive_hour():
                    wait_s = seconds_until_active() + (random.uniform(0, client.humanization_window_minutes * 60) if client.humanization_enabled else 0)
                    BotLogger.log("Sleeping until active period (Auto rolls interrupted).", preset_name, "RESET")
                    await _interruptible_sleep(wait_s)
                    return

                rolls_did_execute = False
                if getattr(client, 'auto_rolls_enabled', False):
                    lim_ok = client.auto_rolls_limit == 0 or client.rolls_item_used_count < client.auto_rolls_limit
                    if not rolls_usage_is_active(client.rolls_used_this_interval_utc, now_utc):
                        client.rolls_used_this_interval_utc = None
                    claim_ok = client.claim_right_available or (client.key_mode and client.auto_rolls_in_key_mode)
                    ack_retry_ready = time.monotonic() >= client._rolls_ack_retry_after
                    if lim_ok and client.rolls_used_this_interval_utc is None and claim_ok and ack_retry_ready:
                        ch_hour = True
                        if client.auto_rolls_only_claim_hour:
                            ch_hour = bool(client.next_claim_reset_at_utc and client.roll_reset_at_utc and client.next_claim_reset_at_utc <= client.roll_reset_at_utc)

                        if ch_hour:
                            BotLogger.log("Auto $rolls triggered.", preset_name, "INFO")
                            rolls_cmd_ch = _get_command_channel() or channel
                            if not await send_mudae_reaction_command(rolls_cmd_ch, f"{client.mudae_prefix}rolls"):
                                client._rolls_ack_retry_after = time.monotonic() + 30.0
                                return
                            rolls_did_execute = True
                            client._rolls_ack_retry_after = 0.0
                            client.rolls_item_used_count += 1
                            client.rolls_used_this_interval_utc = client.roll_reset_at_utc
                            normal_roll_count = int(getattr(client, "_last_normal_roll_count", 0) or 0)
                            if normal_roll_count > 0:
                                BotLogger.log(
                                    f"$rolls acknowledged; continuing with {normal_roll_count} normal roll(s) without another $tu.",
                                    preset_name,
                                    "INFO",
                                )
                                await start_roll_commands(
                                    client,
                                    channel,
                                    normal_roll_count,
                                    ignore_limit_for_post_roll,
                                    key_mode_only_kakera_for_post_roll,
                                    current_cycle_id,
                                )
                            else:
                                request_status_refresh({"rolls"}, reason="auto-rolls-command-acknowledged")
                            return

                if not rolls_did_execute and pending_roll_work()[1]:
                    remaining = client.auto_us_limit - client.us_pulled_this_cycle if client.auto_us_limit > 0 else 20
                    amount = remaining if client.bulk_us_enabled else min(20, remaining)
                    if await send_auto_us(amount, channel):
                        return

                sleep_candidates = [(float(reset_time_r or 60), "rolls reset")]
                m_c = re.search(REGEX_PATTERNS["CLAIM_RESET"], content_lower)
                if m_c and any(kw in m_c.group(0) for kw in ["$daily", "$dk", "$rt"]): m_c = None

                c_min = None
                if m_c:
                    h, m = parse_hm(m_c)
                    c_min = h * 60 + m
                else:
                    c_min = parse_claim_denied_cooldown(content_lower)
                    if c_min is None:
                        c_min = parse_timer_minutes("CLAIM_COOLDOWN", content_lower)

                if c_min is not None:
                    if not client.claim_right_available:
                        sleep_candidates.append((max(0.05, float(c_min)), "claim reset verification"))
                    if client.time_rolls_to_claim_reset and c_min > 60: sleep_candidates.append((float(c_min - 60), "timing window arrival"))
                    if client.claim_right_available and c_min > client.panic_roll_minutes: sleep_candidates.append((float(c_min - client.panic_roll_minutes), "panic roll arrival"))
                sleep_candidates.sort(key=lambda x: x[0])
                await humanized_wait_and_proceed(client, channel, max(0.05, sleep_candidates[0][0]), sleep_candidates[0][1])
            else:
                BotLogger.log(f"Rolls: {total_rolls}" + (f" (+{us_rolls_left} $us)" if us_rolls_left > 0 else "") + f". Reset: {reset_time_r}m", preset_name, "INFO")
                await start_roll_commands(client, channel, total_rolls, ignore_limit_for_post_roll, key_mode_only_kakera_for_post_roll, current_cycle_id)
        else:
            BotLogger.log("Could not parse roll count.", preset_name, "ERROR")
            await asyncio.sleep(30)

    async def process_mk_rolls(client, channel, current_cycle_id):
        if channel.id != client.target_channel_id:
            channel = client.get_channel(client.target_channel_id) or client._main_channel or channel
        if client.is_paused or not getattr(client, 'auto_mk_enabled', True) or client.mk_rolls_left <= 0: return

        current_power = get_current_dk_power()
        if current_power is None:
            request_status_refresh({"power"}, reason="mk-power-unknown", urgent=True)
            return
        if client.auto_mk_full_power_only and current_power < client.max_dk_power:
            missing_power = client.max_dk_power - current_power
            full_power_delay = max(60.0, missing_power * 180.0 + 5.0)
            if client.roll_reset_at_utc:
                reset_delay = (
                    client.roll_reset_at_utc - datetime.datetime.now(timezone.utc)
                ).total_seconds() + 2.0
                full_power_delay = min(full_power_delay, max(60.0, reset_delay))
            refresh_at = time.monotonic() + full_power_delay
            if (
                client._mk_full_power_refresh_at is None
                or client._mk_full_power_refresh_at <= time.monotonic()
                or refresh_at < client._mk_full_power_refresh_at - 30
            ):
                client._mk_full_power_refresh_at = refresh_at
                client.loop.call_later(full_power_delay, request_status_refresh, {"power", "rolls"}, "mk-full-power")
            BotLogger.log(
                f"Skipping $mk until full power ({current_power}%/{client.max_dk_power}%). "
                f"Status refresh scheduled in about {max(1, int(full_power_delay / 60))}m.",
                preset_name,
                "INFO",
            )
            return

        if get_current_dk_power() >= client.dk_consumption or client.mk_bypass_power_check:
            used = 0
            while (
                client.mk_rolls_left > 0
                and (get_current_dk_power() >= client.dk_consumption or client.mk_bypass_power_check)
                and (not client.auto_mk_full_power_only or get_current_dk_power() >= client.max_dk_power)
            ):
                if client.is_paused or is_maintenance_active() or client.interrupt_rolling:
                    break
                command_label = "/mk" if client.use_slash_rolls and not client.slash_fallback_active else f"{client.mudae_prefix}mk"
                BotLogger.log(f"Using {command_label} ({client.mk_rolls_left} left, Power: {get_current_dk_power()}%)", preset_name, "KAKERA")
                if not await send_roll_command(channel, "mk"):
                    break
                client.mk_rolls_left -= 1
                used += 1
                if not await active_delay(3):
                    break
                async for msg in channel.history(limit=5, oldest_first=False):
                    if msg.author.id == TARGET_BOT_ID and msg.embeds and is_character_embed(msg.embeds[0]) and msg.components:
                        await claim_character(client, channel, msg, is_kakera=True, is_mk_roll=True)
                        break
                if not await active_delay(1):
                    break
            if used > 0: BotLogger.log(f"Used {used} MK rolls.", preset_name, "KAKERA")
        else:
            BotLogger.log(f"Skipping $mk: Insufficient power ({get_current_dk_power()}% < {client.dk_consumption}%).", preset_name, "INFO")

    async def execute_farm_forcedivorce(client, channel, char_name, reason):
        """Release the configured farm character and confirm through the shared command queue."""
        if client.is_paused or is_maintenance_active():
            return False
        channel = _get_forcedivorce_channel(channel)
        if channel is None:
            BotLogger.log("Kakera Farm: No channel is available for forcedivorce.", preset_name, "WARN")
            return False
        # Each configured phase is independent. A before-roll cleanup attempt
        # must not suppress the post-claim release of the same character.
        release_key = (
            str(char_name or "").strip().casefold(),
            str(reason or "").strip().casefold(),
        )
        now_monotonic = time.monotonic()
        last_release = client._farm_release_recent.get(release_key, 0.0)
        if release_key and now_monotonic - last_release < 15.0:
            BotLogger.log(f"Kakera Farm: Skipping duplicate forcedivorce for {char_name}.", preset_name, "DEBUG", client)
            return True
        if release_key:
            client._farm_release_recent[release_key] = now_monotonic
        if client._farm_release_lock is None:
            client._farm_release_lock = asyncio.Lock()
        # Mudae accepts only one interactive harem command per account. Keep
        # the command, its confirmation, and the short processing grace period
        # atomic when several edited farm claims arrive almost simultaneously.
        async with client._farm_release_lock:
            for attempt in range(3):
                BotLogger.log(f"Kakera Farm: Forcedivorcing {char_name} {reason}.", preset_name, "INFO")
                if not await guarded_send(channel, f"{client.mudae_prefix}forcedivorce {char_name}"):
                    client._farm_release_recent.pop(release_key, None)
                    BotLogger.log(f"Kakera Farm: Could not send forcedivorce for {char_name}.", preset_name, "WARN")
                    return False
                if not await active_delay(1.5 + random.uniform(0.1, 0.4)):
                    return False

                harem_busy = False
                async for msg in channel.history(limit=5):
                    if msg.author.id == TARGET_BOT_ID and msg.content:
                        c_low = msg.content.lower()
                        if "harem" in c_low and any(phrase in c_low for phrase in ("being processed", "en cours", "procesando", "processando")):
                            harem_busy = True
                            break
                if harem_busy:
                    if attempt < 2:
                        BotLogger.log(f"Kakera Farm: Harem command busy, retrying in 3s (attempt {attempt + 1}/3)...", preset_name, "WARN")
                        if not await active_delay(3.0 + random.uniform(0.2, 0.5)):
                            return False
                        continue
                    else:
                        BotLogger.log(f"Kakera Farm: Harem command still busy after 3 attempts.", preset_name, "WARN")
                        client._farm_release_recent.pop(release_key, None)
                        return False

                if not await guarded_send(channel, "y"):
                    client._farm_release_recent.pop(release_key, None)
                    BotLogger.log(f"Kakera Farm: Could not confirm forcedivorce for {char_name}.", preset_name, "WARN")
                    return False
                BotLogger.log(f"Kakera Farm: Confirmed forcedivorce for {char_name}.", preset_name, "INFO")
                if str(getattr(client, 'last_successfully_claimed_character', '') or '').casefold() == str(char_name or '').casefold():
                    # The duplicate-claim guard is no longer valid once Mudae confirms
                    # that the farm character was released.
                    client.last_successfully_claimed_character = None
                return await active_delay(1.0 + random.uniform(0.1, 0.4))
            return False

    async def start_roll_commands(client, channel, rolls_left, ignore_limit_for_post_roll, key_mode_only_kakera_for_post_roll, current_cycle_id, is_us_pull: bool = False):
        if client.is_paused or is_maintenance_active(): return
        client.interrupt_rolling = False
        client._roll_interrupt_reason = None
        if channel.id != client.target_channel_id:
            channel = client.get_channel(client.target_channel_id) or client._main_channel or channel

        if (client.farm_character_enabled and client.farm_characters and client.claim_right_available
                and client.farm_forcedivorce_before_roll):
            for farm_name in client.farm_characters:
                if client.is_paused or is_maintenance_active() or client.interrupt_rolling: return
                if not await execute_farm_forcedivorce(
                    client,
                    channel,
                    farm_name,
                    "before rolling (configured timing)",
                ):
                    return

        if client.is_paused or is_maintenance_active() or client.interrupt_rolling: return
        await process_mk_rolls(client, channel, current_cycle_id)

        reset_soon = False
        if client.next_claim_reset_at_utc:
            diff = (client.next_claim_reset_at_utc - datetime.datetime.now(timezone.utc)).total_seconds()
            if 0 < diff <= 3600: reset_soon = True

        is_timing_mode_active = False
        if not is_us_pull and client.time_rolls_to_claim_reset and not client.claim_right_available and reset_soon:
            now_utc = datetime.datetime.now(timezone.utc)
            if client.next_claim_reset_at_utc and client.next_claim_reset_at_utc > now_utc:
                actual_speed = (max(2.0, client.roll_speed) if client.use_slash_rolls else client.roll_speed) + random.uniform(0.05, 0.25)
                total_duration = rolls_left * actual_speed
                target_start = client.next_claim_reset_at_utc + datetime.timedelta(seconds=1) - datetime.timedelta(seconds=total_duration)
                wait_s = (target_start - now_utc).total_seconds()

                if client.roll_reset_at_utc:
                    max_wait = (client.roll_reset_at_utc - now_utc).total_seconds() - total_duration - 5
                    wait_s = min(wait_s, max_wait)

                if wait_s > 2:
                    BotLogger.log(f"Timing rolls to finish after reset. Waiting {wait_s/60:.1f}m.", preset_name, "RESET")
                    if not await active_delay(wait_s):
                        mark_status_dirty(client, {"rolls"}, reason="timed-roll-wait-interrupted")
                        return
                is_timing_mode_active = True
        client.is_timing_mode_active = is_timing_mode_active

        BotLogger.log(f"Rolling {rolls_left} times" + (" (Reactive)" if client.enable_reactive_self_snipe else ""), preset_name, "INFO")
        client.is_actively_rolling = True
        client.interrupt_rolling = False
        client._rolls_sent = client._rolls_received = 0
        client.collected_rolls = []
        client.collected_kakera_rolls = []

        client.rolls_left = rolls_left
        consecutive_failures = 0
        while client.rolls_left > 0:
            if client.is_paused or is_maintenance_active():
                mark_status_dirty(client, {"rolls"}, reason="rolling-interrupted")
                break
            if client.interrupt_rolling:
                interrupt_reason = getattr(client, "_roll_interrupt_reason", None)
                if interrupt_reason == "claim-attempt":
                    while (
                        getattr(client, "is_claiming", False)
                        and not client.is_paused
                        and not is_maintenance_active()
                    ):
                        await asyncio.sleep(0.05)
                    if can_resume_claim_interrupted_rolls(client):
                        client.interrupt_rolling = False
                        client._roll_interrupt_reason = None
                        BotLogger.log(
                            f"Claim attempt finished. Resuming {client.rolls_left} locally tracked roll(s) without $tu.",
                            preset_name,
                            "INFO",
                        )
                        continue
                    if (
                        getattr(client, "pending_claim", None) is None
                        and not client.is_paused
                        and not is_maintenance_active()
                        and not client.key_limit_hit
                    ):
                        # The claim outcome is settled and the unsent roll count
                        # is still exact. Stop intentionally when no claim path
                        # remains, without turning that known count into a $tu
                        # reconciliation request.
                        client._roll_interrupt_reason = None
                        break
                mark_status_dirty(client, {"rolls"}, reason="rolling-interrupted")
                client._roll_interrupt_reason = None
                break
            try:
                if not await send_roll_command(channel, roll_command):
                    mark_status_dirty(client, {"rolls"}, reason="roll-send-blocked")
                    break
                client._rolls_sent += 1
                client.rolls_left = max(0, client.rolls_left - 1)
                consecutive_failures = 0
                roll_delay = (max(2.0, client.roll_speed) if client.use_slash_rolls else client.roll_speed) + random.uniform(0.05, 0.25)
                if not await active_delay(roll_delay):
                    mark_status_dirty(client, {"rolls"}, reason="roll-delay-interrupted")
                    break
            except Exception as exc:
                consecutive_failures += 1
                BotLogger.log(f"Roll send failed ({consecutive_failures}/5): {exc}", preset_name, "WARN")
                if consecutive_failures >= 5:
                    mark_status_dirty(client, {"rolls"}, reason="roll-send-failures")
                    BotLogger.log("Rolling stopped after repeated send failures; status will be refreshed.", preset_name, "ERROR")
                    break
                if not await active_delay(min(8.0, 2 ** (consecutive_failures - 1)) + random.uniform(0.1, 0.3)):
                    mark_status_dirty(client, {"rolls"}, reason="roll-retry-interrupted")
                    break

        timeout, poll_start = 5.0, time.time()
        while not client.is_paused and time.time() - poll_start < timeout and client._rolls_received < client._rolls_sent:
            await asyncio.sleep(0.05)

        client.is_actively_rolling = False
        if client.is_paused:
            mark_status_dirty(client, {"rolls"}, reason="pause-during-roll")
            return
        if client.rolls_left <= 0 and client._rolls_received >= client._rolls_sent:
            clear_status_dirty(client, {"rolls"})
            # The locally tracked batch is complete, but the cached $tu still
            # describes the rolls that were just sent.  When Auto $us is
            # enabled, refresh now so check_rolls_left_tu can see zero normal
            # rolls and immediately pull the configured saved rolls instead
            # of sleeping until the cache expires.
            if pending_roll_work()[1]:
                request_status_refresh(
                    {"rolls"},
                    reason="normal-rolls-complete-auto-us",
                    urgent=True,
                )
        elif client.rolls_left <= 0:
            # Discord can drop one or more roll embeds even though every local
            # roll command was sent. Never trust the pre-roll cache in that
            # state: it can sleep past the reset and skip Auto $us entirely.
            request_status_refresh(
                {"rolls"},
                reason="normal-roll-responses-missing",
                urgent=True,
            )

        if not getattr(client, 'immediate_kakera_click', True) and getattr(client, 'collected_kakera_rolls', []):
            BotLogger.log("Processing collected rolls for Kakera priority collection...", preset_name, "INFO")

            prio_map = {k.strip(): (idx + 1) * 10 for idx, k in enumerate(reversed(client.kakera_priority_order))}
            for s in client.sphere_emojis: prio_map[s] = 999
            if client.collect_purple_kakera:
                prio_map['kakeraP'] = 999

            clickable_buttons = []
            for msg in client.collected_kakera_rolls:
                if not msg.embeds or not msg.components:
                    continue
                embed = msg.embeds[0]
                chaos_count = count_chaos_keys(embed)
                has_sp_perk = has_perk_eight_discount(kakera_embed_text(embed))
                filter_reason = regular_kakera_filter_reason(
                    client,
                    msg,
                    embed,
                    is_mk_roll=False,
                    is_external_roll=False,
                )

                target_list = get_kakera_emoji_targets(
                    client.kakera_emojis,
                    client.chaos_emojis,
                    client.sphere_perk_emojis,
                    has_chaos_discount=chaos_count > 0,
                    has_perk_eight_discount=has_sp_perk,
                )

                for row_idx, comp in enumerate(msg.components):
                    for child_idx, btn in enumerate(comp.children):
                        if hasattr(btn.emoji, 'name') and btn.emoji.name:
                            name = btn.emoji.name
                            name_clean = name.rstrip('2')

                            if name_clean == 'kakeraP' and not client.collect_purple_kakera:
                                continue

                            is_sphere = is_character_sphere_emoji(name)
                            is_free = name_clean == 'kakeraP' or is_sphere or check_is_green(btn)

                            is_clickable = False
                            if is_sphere:
                                if sphere_target_matches(name, client.sphere_click_targets):
                                    is_clickable = True
                            else:
                                regular_match = (name in target_list or name_clean in target_list) or ("kakera" in name.lower() and check_is_green(btn))
                                if name_clean == 'kakeraP' or (filter_reason is None and regular_match):
                                    is_clickable = True

                            if is_clickable:
                                prio = prio_map.get(name_clean, 0)
                                if is_sphere or name_clean == 'kakeraP' or check_is_green(btn):
                                    prio = 999

                                clickable_buttons.append({
                                    'btn': btn,
                                    'custom_id': btn.custom_id,
                                    'pos': (row_idx, child_idx),
                                    'emoji_name': name,
                                    'priority': prio,
                                    'message': msg,
                                    'is_sphere': is_sphere,
                                    'is_free': is_free,
                                    'chaos_count': chaos_count,
                                    'has_reaction_cooldown_bypass': (
                                        chaos_count > 0 or has_sp_perk or is_free
                                    ),
                                    'cost': calculate_kakera_power_cost(
                                        client.dk_consumption,
                                        has_chaos_discount=chaos_count > 0,
                                        has_perk_eight_discount=has_sp_perk,
                                        is_free=is_free,
                                    ),
                                    'char_name': (embed.author.name if embed.author else "Unknown").strip()
                                })

            # Keep the user's Kakera priority order globally, then prefer a
            # same-priority Perk 8/Chaos click that can bypass the cooldown.
            clickable_buttons.sort(
                key=lambda item: queued_kakera_sort_key(
                    item['priority'], item['has_reaction_cooldown_bypass']
                ),
                reverse=True,
            )

            for item in clickable_buttons:
                msg = item['message']
                custom_id = item['custom_id']
                pos = item['pos']
                name = item['emoji_name']
                is_free = item['is_free']
                cost = item['cost']
                chaos_count = item['chaos_count']
                has_reaction_cooldown_bypass = item['has_reaction_cooldown_bypass']
                char_name = item['char_name']

                msg_id = msg.id
                # Update target message reference to avoid stale element exceptions
                try:
                    msg = await channel.fetch_message(msg_id)
                    btn = find_refreshed_component_button(
                        msg.components,
                        custom_id=custom_id,
                        position=pos,
                        emoji_name=name,
                    )
                    if btn is None:
                        continue
                except Exception:
                    continue

                if getattr(btn, 'disabled', False):
                    continue

                async with get_kakera_action_lock():
                    is_free_purple = name.rstrip('2') == 'kakeraP'
                    if not is_kakera_reaction_allowed(is_free_purple=is_free_purple) and not has_reaction_cooldown_bypass and not is_free:
                        BotLogger.log(
                            f"Kakera skipped for {char_name}: reaction is on cooldown before queued {name} click.",
                            preset_name,
                            "DEBUG",
                            client,
                        )
                        continue
                    current_pow = get_current_dk_power()
                    if cost > 0 and current_pow is None:
                        request_status_refresh({"power"}, reason="power-unknown", urgent=True)
                        continue
                    if cost > 0 and current_pow < cost:
                        if (client.auto_dk_enabled and client.dk_power_management and client.dk_stock_count > 0
                                and should_auto_refill_dk(current_pow, cost)):
                            log_name = name
                            BotLogger.log(f"Dynamic DK Refill: Power too low ({current_pow}% < {cost}%). Sending $dk for {log_name}...", preset_name, "KAKERA")
                            try:
                                cmd_ch = _get_command_channel() or channel
                                if not await guarded_send(cmd_ch, f"{client.mudae_prefix}dk"):
                                    return
                                client.dk_stock_count = max(0, client.dk_stock_count - 1)
                                client.current_dk_power = client.max_dk_power
                                client.kakera_power_ledger.clear()
                                mark_dk_power_changed()
                                client.last_dk_power_update_utc = datetime.datetime.now(timezone.utc)
                                request_status_refresh({"power"}, reason="dynamic-dk-used")
                                if not await active_delay(1.2 + random.uniform(0.1, 0.4)):
                                    return
                                current_pow = get_current_dk_power()
                            except Exception as e:
                                BotLogger.log(f"Dynamic DK Refill failed: {e}", preset_name, "ERROR")

                    if cost > 0 and current_pow < cost:
                        log_name = name
                        if not hasattr(client, 'last_power_warn') or (time.time() - getattr(client, 'last_power_warn', 0) > 60):
                            BotLogger.log(f"Insufficient Power ({current_pow}% < {cost}%). Skipping {log_name}.", preset_name, "WARN")
                            client.last_power_warn = time.time()
                        continue

                    if cost > 0 and client.kakera_power_thresholds:
                        base_name = name.rstrip('2')
                        spec_name = f"chaos_{base_name}" if chaos_count > 0 else base_name
                        threshold = first_configured(client.kakera_power_thresholds, spec_name, base_name, name)
                        if threshold is not None and current_pow < threshold:
                            BotLogger.log(f"Power ({current_pow}%) below threshold ({threshold}%) for {spec_name}. Waiting.", preset_name, "INFO")
                            continue

                    if client.debug_mode:
                        ws_ref = getattr(client, 'ws', None)
                        sid = getattr(ws_ref, 'session_id', None) if ws_ref else None
                        BotLogger.log(f"Kakera Click: custom_id={getattr(btn, 'custom_id', 'N/A')} | name={name} | session_id={sid}", preset_name, "DEBUG", client)

                    power_token = reserve_kakera_power_click(name, cost) if cost > 0 else None
                    try:
                        click_ok = await click_kakera_with_confirmation(
                            channel,
                            msg,
                            btn,
                            custom_id=custom_id,
                            position=pos,
                            emoji_name=name,
                            character_name=char_name,
                        )
                        if not click_ok:
                            cancel_kakera_power_click(power_token)
                            continue
                        client.kakera_reacted_messages.add(msg_id)
                        estimated_power = get_current_dk_power()
                        power_text = f"{estimated_power}%" if estimated_power is not None else "unknown"
                        BotLogger.log(f"Kakera click sent: {char_name} [{name}] (Estimated Pw: {power_text})", preset_name, "KAKERA")
                        client._last_kakera_click_ts = time.time()
                        if not await active_delay(0.6):
                            return
                    except discord.HTTPException as e:
                        cancel_kakera_power_click(power_token)
                        BotLogger.log(f"Kakera click failed (HTTP {getattr(e, 'status', '?')}): {getattr(e, 'text', str(e))[:100]}", preset_name, "ERROR")
                    except Exception as e:
                        cancel_kakera_power_click(power_token)
                        BotLogger.log(f"Kakera click error: {e}", preset_name, "ERROR")

            client.collected_kakera_rolls.clear()

        if is_timing_mode_active:
            now_utc = datetime.datetime.now(timezone.utc)
            if client.next_claim_reset_at_utc and client.next_claim_reset_at_utc > now_utc:
                remaining_s = (client.next_claim_reset_at_utc - now_utc).total_seconds()
                if 0 < remaining_s <= 120:
                    BotLogger.log(f"Waiting {remaining_s:.1f}s for claim reset boundary...", preset_name, "RESET")
                    await active_delay(remaining_s + 0.5)
            client.claim_right_available = True
            client.claim_cooldown_until_utc = None
            client.last_successfully_claimed_character = None
            refresh_predicted_claim_and_rt()
            claimed = False
            if client.collected_rolls:
                BotLogger.log(f"Smart Timing: Processing {len(client.collected_rolls)} collected roll(s) at claim reset.", preset_name, "CLAIM")
                try:
                    claimed = await handle_mudae_messages(
                        client,
                        channel,
                        client.collected_rolls,
                        ignore_limit_for_post_roll or client.current_min_kakera_for_roll_claim == 0,
                        False,
                    )
                except Exception as e:
                    BotLogger.log(f"Smart Timing post-roll processing error: {e}", preset_name, "ERROR")
                if claimed:
                    client.collected_rolls.clear()
                    client._claim_reset_rolls_pending = False
                else:
                    client._claim_reset_rolls_pending = True
            request_status_refresh({"claim"}, reason="timing-reset-boundary", urgent=True)
            BotLogger.log("Reset passed. Verifying claim status with $tu.", preset_name, "CHECK")
        else:
            in_panic_hour = False
            if client.next_claim_reset_at_utc:
                now_utc = datetime.datetime.now(timezone.utc)
                claim_reset_mins = (client.next_claim_reset_at_utc - now_utc).total_seconds() / 60.0
                if claim_reset_mins <= getattr(client, 'panic_roll_minutes', 5) or claim_reset_mins <= 60:
                    in_panic_hour = True

            should_process_collected = False
            if not getattr(client, 'enable_reactive_self_snipe', True):
                should_process_collected = True
            elif getattr(client, 'enable_hybrid_panic_claim', False) and in_panic_hour:
                should_process_collected = True

            if should_process_collected and client.collected_rolls:
                BotLogger.log(f"Processing {len(client.collected_rolls)} collected rolls immediately.", preset_name, "INFO")
                try:
                    await handle_mudae_messages(client, channel, client.collected_rolls, ignore_limit_for_post_roll, key_mode_only_kakera_for_post_roll)
                except Exception as e:
                    BotLogger.log(f"Defer-roll processing error: {e}", preset_name, "ERROR")
                client.collected_rolls.clear()
        client.is_timing_mode_active = False
        await active_delay(1.0 + random.uniform(0.1, 0.5))

    async def execute_auto_divorce(client, channel, char_name):
        try:
            if not await active_delay(random.uniform(1.5, 2.5)): return False
            if not await guarded_send(channel, f"{client.mudae_prefix}divorce {char_name}"): return False
            BotLogger.log(f"Auto-Divorce: Initiating divorce for {char_name}...", preset_name, "INFO")
            if not await active_delay(random.uniform(1.5, 2.5)): return False

            char_tag = f"**{char_name.lower()}**"
            confirm = False
            async for msg in channel.history(limit=8):
                if msg.author.id == TARGET_BOT_ID and msg.content:
                    c = msg.content.lower()
                    if char_tag in c and ("(y/n" in c or "yes/no" in c or "(y /" in c):
                        confirm = True
                        break
            if not confirm: return False

            if not await active_delay(random.uniform(1.5, 2.5)): return False
            if not await guarded_send(channel, "y"): return False
            if not await active_delay(random.uniform(1.5, 2.5)): return False

            bot_u = client.user.name.lower()
            bot_d = (client.user.display_name or client.user.name).lower()
            success = False
            earned = None
            async for msg in channel.history(limit=8):
                if msg.author.id == TARGET_BOT_ID and msg.content:
                    c = msg.content.lower()
                    if char_tag in c and (f"**{bot_u}**" in c or f"**{bot_d}**" in c):
                        success = True
                        m_k = re.search(REGEX_PATTERNS["KAKERA_EARNED"], msg.content)
                        if m_k: earned = int(m_k.group(1))
                        break
            if success:
                BotLogger.log(f"Auto-Divorce: Divorced {char_name}" + (f" (+{earned} kakera)" if earned else ""), preset_name, "KAKERA")
                return True
        except Exception as e:
            BotLogger.log(f"Auto-Divorce error: {e}", preset_name, "ERROR")
        return False

    def prepare_pending_claim(msg, char_name, is_snipe_action, character_kakera, character_series, consumes_claim, is_rt_claim=False):
        pending = {
            "message_id": getattr(msg, 'id', None),
            "channel": getattr(msg, 'channel', None),
            "character_name": char_name,
            "is_snipe_action": bool(is_snipe_action),
            "character_kakera": int(character_kakera or 0),
            "character_series": character_series or "",
            "consumes_claim": bool(consumes_claim),
            "claim_was_available": bool(client.claim_right_available),
            "is_rt_claim": bool(is_rt_claim),
            "protect_from_auto_divorce": bool(
                msg.embeds
                and is_wish_or_starwish(msg, msg.embeds[0])
            ),
            "created_monotonic": time.monotonic(),
            "finalized": False,
        }
        client.pending_claim = pending
        client._claim_text_evidence = None
        event = getattr(client, '_claim_evidence_event', None)
        if event is not None:
            event.clear()
        return pending

    def clear_pending_claim(pending=None):
        if pending is not None and client.pending_claim is not pending:
            return
        client.pending_claim = None
        client._claim_text_evidence = None
        event = getattr(client, '_claim_evidence_event', None)
        if event is not None:
            event.clear()

    def release_failed_claim(message_id, pending=None):
        clear_pending_claim(pending)
        client.processed_claim_messages.discard(message_id)
        _claim_coordinator.release_all(message_id)

    async def finalize_successful_claim(pending, channel, verification_source):
        if pending.get("finalized"):
            return
        pending["finalized"] = True
        _claim_coordinator.mark_completed(pending.get("message_id"))
        client.claim_retry_counts.pop(pending.get("message_id"), None)
        char_name = pending["character_name"]
        character_kakera = pending["character_kakera"]
        character_series = pending["character_series"]
        consumes_claim = pending["consumes_claim"]
        is_snipe_action = pending["is_snipe_action"]
        lbl = "Snipe Verification" if is_snipe_action else "Claim Verification"
        BotLogger.log(f"{lbl}: SUCCESS! We got {char_name}. ({verification_source})", preset_name, "CLAIM")

        now = datetime.datetime.now(timezone.utc)
        if consumes_claim:
            client.claim_right_available = False
            client.last_successfully_claimed_character = char_name.lower()
            base = client.next_claim_reset_at_utc
            delta = datetime.timedelta(minutes=client.claim_interval)
            if base is None:
                base = cooldown_deadline(now, client.claim_interval)
            while base <= now:
                base += delta
            client.next_claim_reset_at_utc = base
            client.claim_cooldown_until_utc = base
            client._claim_reset_refresh_requested = False
            clear_status_dirty(client, {"claim"})

        if client.is_paused:
            BotLogger.log("Post-claim actions skipped because the bot is paused.", preset_name, "INFO")
            return

        farm_character_claimed = (
            client.farm_character_enabled
            and is_farm_character_name(char_name)
        )
        post_claim_farm_mode = farm_character_claimed and client.farm_forcedivorce_after_claim
        farm_release_sent = False

        if post_claim_farm_mode:
            farm_release_sent = await execute_farm_forcedivorce(
                client,
                channel,
                char_name,
                "after verified claim (configured timing)",
            )

        if client.auto_divorce_enabled and not farm_character_claimed:
            is_blacklisted = bool(
                client.auto_divorce_protect_wishes
                and pending.get("protect_from_auto_divorce")
            )
            if is_blacklisted:
                BotLogger.log(
                    f"Auto-Divorce: {char_name} is wished/starwished. Keeping character.",
                    preset_name,
                    "INFO",
                )
            elif char_name.lower() in getattr(client, 'auto_divorce_blacklist', set()):
                is_blacklisted = True
                BotLogger.log(f"Auto-Divorce: {char_name} is in the blacklist. Keeping character.", preset_name, "INFO")
            elif character_series and getattr(client, 'auto_divorce_blacklist_series', []):
                for series_keyword in client.auto_divorce_blacklist_series:
                    if series_keyword in character_series.lower():
                        is_blacklisted = True
                        BotLogger.log(f"Auto-Divorce: {char_name} series ({character_series[:60]}) matches blacklist series keyword '{series_keyword}'. Keeping character.", preset_name, "INFO")
                        break
            if not is_blacklisted:
                should_divorce = character_kakera > 0 and character_kakera <= client.auto_divorce_max_kakera
                reason = f"kakera {character_kakera} <= {client.auto_divorce_max_kakera}" if should_divorce else ""
                if not should_divorce and character_series and client.auto_divorce_series:
                    should_divorce = any(series_keyword in character_series.lower() for series_keyword in client.auto_divorce_series)
                    if should_divorce:
                        reason = f"series match in '{character_series[:60]}'"
                if should_divorce:
                    BotLogger.log(f"Auto-Divorce: {char_name} qualifies ({reason}).", preset_name, "INFO")
                    await execute_auto_divorce(client, channel, char_name)

        if (consumes_claim and client.auto_rt_after_claim and client.rt_available
                and not client.is_paused and not farm_character_claimed):
            mins_to_reset = ((client.next_claim_reset_at_utc - now).total_seconds() / 60.0) if client.next_claim_reset_at_utc else None
            if mins_to_reset is not None and mins_to_reset < 60:
                BotLogger.log(f"Auto $rt: SKIPPED — resets soon ({mins_to_reset:.0f}m).", preset_name, "INFO")
            elif client.rolling_enabled and not client.is_actively_rolling:
                BotLogger.log("Auto $rt: SKIPPED — rolling sequence finished.", preset_name, "INFO")
            else:
                BotLogger.log(f"Auto $rt: Sending $rt after claiming {char_name}.", preset_name, "CLAIM")
                try:
                    if await send_mudae_reaction_command(channel, f"{client.mudae_prefix}rt"):
                        apply_rt_acknowledgement()
                except Exception as e:
                    BotLogger.log(f"Auto $rt failed: {e}", preset_name, "ERROR")

        if farm_character_claimed and consumes_claim and client.auto_rt_after_claim and client.rt_available:
            if post_claim_farm_mode:
                if farm_release_sent and await send_mudae_reaction_command(channel, f"{client.mudae_prefix}rt"):
                    apply_rt_acknowledgement()
                    BotLogger.log(f"Kakera Farm: $rt restored after releasing {char_name}.", preset_name, "CLAIM")
            elif await send_mudae_reaction_command(channel, f"{client.mudae_prefix}rt"):
                apply_rt_acknowledgement()
                await execute_farm_forcedivorce(
                    client,
                    channel,
                    char_name,
                    "after $rt (solo/key mode)",
                )

        if is_snipe_action and client.enable_snipe_chat_reactions and client.snipe_chat_messages:
            try:
                if await active_delay(random.uniform(2.0, 5.0)):
                    await guarded_send(channel, random.choice(client.snipe_chat_messages))
            except Exception as e:
                BotLogger.log(f"Snipe chat reaction failed: {e}", preset_name, "ERROR")

    def retry_pending_claim_from_cached_state(pending, pending_channel):
        """Retry one unconfirmed click without spending time on a redundant $tu."""
        message_id = pending.get("message_id")
        retry_count = client.claim_retry_counts.get(message_id, 0)
        if (
            message_id is None
            or retry_count >= 1
            or client.is_paused
            or pending.get("rejected_by_cooldown")
            or not pending.get("claim_was_available")
            or not client.claim_right_available
        ):
            return False

        # The click was made while a verified claim right was cached.  Do not
        # block a live snipe window on a round trip to $tu just to rediscover
        # that same state.  The retry helper refetches the roll and only clicks
        # again if its claim button is still present.
        clear_pending_claim(pending)
        client.processed_claim_messages.discard(message_id)
        client.claim_retry_counts[message_id] = retry_count + 1
        client.loop.create_task(retry_pending_claim_after_release(
            pending,
            pending_channel,
            f"Retrying {pending['character_name']} once from the cached ready claim state.",
        ))
        return True

    async def retry_pending_claim_after_release(pending, pending_channel, retry_log):
        message_id = pending.get("message_id")
        try:
            for _ in range(30):
                if not client.is_claiming and not _claim_coordinator.is_reserved(message_id):
                    break
                if not await active_delay(0.1):
                    return
            if client.is_claiming or _claim_coordinator.is_reserved(message_id):
                BotLogger.log(f"Claim retry timed out while releasing {pending['character_name']}.", preset_name, "WARN")
                return
            retry_message = await pending_channel.fetch_message(message_id)
            retry_embed = retry_message.embeds[0] if retry_message.embeds else None
            if retry_embed and has_claim_option(retry_message, retry_embed, client.claim_emojis):
                BotLogger.log(retry_log, preset_name, "CLAIM")
                await claim_character(
                    client,
                    pending_channel,
                    retry_message,
                    is_snipe=pending.get("is_snipe_action", False),
                    kakera_value=pending.get("character_kakera", 0),
                )
        except Exception as exc:
            BotLogger.log(f"Claim retry check failed: {exc}", preset_name, "WARN")

    async def resolve_pending_claim_from_status(claim_available, channel):
        pending = getattr(client, 'pending_claim', None)
        if not pending or not pending.get("consumes_claim"):
            return
        if time.monotonic() - pending["created_monotonic"] > 45:
            BotLogger.log("Expired unresolved claim verification; status is now synchronized from $tu.", preset_name, "WARN")
            client.claim_retry_counts.pop(pending.get("message_id"), None)
            clear_pending_claim(pending)
            return
        pending_channel = pending.get("channel") or channel
        if claim_available is None:
            return
        if pending.get("rejected_by_cooldown"):
            message_id = pending.get("message_id")
            retry_count = client.claim_retry_counts.get(message_id, 0)
            can_retry = bool(claim_available or client.rt_available)
            clear_pending_claim(pending)
            if message_id is not None and retry_count < 1 and can_retry and not client.is_paused:
                # Only release the message when a real retry path exists.
                # Otherwise the same stale roll can be picked up again and
                # trigger another rejection -> $tu cycle.
                client.processed_claim_messages.discard(message_id)
                client.claim_retry_counts[message_id] = retry_count + 1
                retry_method = "claim right" if claim_available else "$rt"
                client.loop.create_task(retry_pending_claim_after_release(
                    pending,
                    pending_channel,
                    f"Retrying {pending['character_name']} once with {retry_method} after Mudae rejected the stale claim state.",
                ))
            elif not can_retry:
                BotLogger.log(
                    f"Claim Verification: FAILED. {pending['character_name']} was not claimed and neither a claim right nor $rt is ready.",
                    preset_name,
                    "WARN",
                )
            return
        if claim_available:
            BotLogger.log(f"Claim Verification: FAILED. {pending['character_name']} was not claimed; claim right is still ready.", preset_name, "WARN")
            clear_pending_claim(pending)
            message_id = pending.get("message_id")
            retry_count = client.claim_retry_counts.get(message_id, 0)
            client.processed_claim_messages.discard(message_id)
            if message_id is not None and retry_count < 1 and not client.is_paused:
                client.claim_retry_counts[message_id] = retry_count + 1
                client.loop.create_task(retry_pending_claim_after_release(
                    pending,
                    pending_channel,
                    f"Retrying {pending['character_name']} once after $tu confirmed the claim was not consumed.",
                ))
            return
        if pending.get("claim_was_available"):
            await finalize_successful_claim(pending, pending_channel, "$tu cooldown confirmation")
        else:
            BotLogger.log("Claim Verification remains inconclusive after $tu because the attempt used $rt/cooldown state.", preset_name, "WARN")
        clear_pending_claim(pending)

    async def verify_snipe_outcome(client, channel, msg, pending):
        char_name = pending["character_name"]
        lbl = "Snipe Verification" if pending["is_snipe_action"] else "Claim Verification"
        evidence = None
        # A cached ready claim is enough to make one safe, immediate retry.
        # Keep its grace period short so a lost interaction cannot consume the
        # whole external-snipe window before the retry is sent.  $rt/cooldown
        # claims keep the longer confirmation period because their cached
        # state is not independently retryable.
        verification_seconds = (
            3.5
            if pending.get("consumes_claim")
            and pending.get("claim_was_available")
            and client.claim_right_available
            else 5.0
        )
        deadline = time.monotonic() + verification_seconds

        while time.monotonic() < deadline:
            if client.pending_claim is not pending:
                return ClaimOutcome.SUCCESS if pending.get("finalized") else ClaimOutcome.INCONCLUSIVE
            text_evidence = getattr(client, '_claim_text_evidence', None)
            if text_evidence is not None and text_evidence.outcome != ClaimOutcome.INCONCLUSIVE:
                evidence = text_evidence
                break
            try:
                refreshed = await channel.fetch_message(msg.id)
                if refreshed.embeds:
                    owner = get_character_owner(refreshed.embeds[0])
                    owner_evidence = classify_claim_owner(
                        owner,
                        claim_identities(),
                        user_id=getattr(client.user, 'id', None),
                    )
                    if owner_evidence.outcome != ClaimOutcome.INCONCLUSIVE:
                        evidence = owner_evidence
                        break
            except Exception:
                pass

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            event = getattr(client, '_claim_evidence_event', None)
            if event is None:
                await asyncio.sleep(min(0.75, remaining))
            else:
                event.clear()
                try:
                    await asyncio.wait_for(event.wait(), timeout=min(0.75, remaining))
                except asyncio.TimeoutError:
                    pass

        if client.pending_claim is not pending:
            return ClaimOutcome.SUCCESS if pending.get("finalized") else ClaimOutcome.INCONCLUSIVE

        if evidence is None:
            try:
                async for history_message in channel.history(limit=20):
                    if history_message.author.id != TARGET_BOT_ID or not history_message.content:
                        continue
                    if getattr(history_message, 'id', 0) < getattr(msg, 'id', 0):
                        continue
                    candidate = classify_claim_text(
                        history_message.content,
                        char_name,
                        claim_identities(),
                        user_id=getattr(client.user, 'id', None),
                    )
                    if candidate.outcome != ClaimOutcome.INCONCLUSIVE:
                        evidence = candidate
                        break
            except Exception:
                pass

        if evidence is not None and evidence.outcome == ClaimOutcome.SUCCESS:
            await finalize_successful_claim(pending, channel, evidence.source)
            clear_pending_claim(pending)
            return ClaimOutcome.SUCCESS
        if evidence is not None and evidence.outcome == ClaimOutcome.FAILURE:
            BotLogger.log(f"{lbl}: FAILED. Taken by {evidence.winner or 'someone else'}.", preset_name, "WARN")
            client.claim_retry_counts.pop(pending.get("message_id"), None)
            _claim_coordinator.mark_completed(pending.get("message_id"))
            clear_pending_claim(pending)
            clear_status_dirty(client, {"claim"})
            return ClaimOutcome.FAILURE

        if pending.get("consumes_claim") and retry_pending_claim_from_cached_state(pending, channel):
            BotLogger.log(
                f"{lbl}: Inconclusive after {verification_seconds:.1f}s; "
                "claim is still cached as ready, retrying the live roll once without $tu.",
                preset_name,
                "WARN",
            )
            return ClaimOutcome.INCONCLUSIVE

        BotLogger.log(f"{lbl}: Inconclusive. Refreshing $tu before changing claim state.", preset_name, "WARN")
        if pending.get("consumes_claim"):
            request_status_refresh({"claim"}, reason="claim-verification-inconclusive", urgent=True)
        else:
            clear_pending_claim(pending)
        return ClaimOutcome.INCONCLUSIVE

    async def handle_mudae_messages(client, channel, mudae_messages, ignore_limit_param, key_mode_only_kakera_param):
        char_claims = []
        wl_claims = []
        min_kak_post = 0 if ignore_limit_param else client.min_kakera

        attempted = set()
        for msg in mudae_messages:
            if not msg.embeds: continue
            embed = msg.embeds[0]
            if not is_character_embed(embed): continue

            has_claim = is_free_event(embed) or has_claim_option(msg, embed, client.claim_emojis)
            if not has_claim:
                continue

            c_name = embed.author.name.lower()
            if is_free_event(embed):
                print_log(f"Detected free event card: {c_name}", preset_name, "CLAIM")
                await claim_character(client, channel, msg, is_free_claim=True)
                continue

            k_v = 0
            m_k = re.search(REGEX_PATTERNS["KAKERA_VALUE"], embed.description or "")
            if m_k: k_v = int(re.sub(r"[^\d]", "", m_k.group(1)))

            description_lines = (embed.description or "").splitlines()
            series = description_lines[0].lower() if description_lines else ""
            claims_r, likes_r = parse_mudae_ranks(embed.description or "")
            is_ranked = (client.max_claim_rank > 0 and 0 < claims_r <= client.max_claim_rank) or (client.max_like_rank > 0 and 0 < likes_r <= client.max_like_rank)
            is_series_wl = await series_wishlist_matches(msg, series)
            is_wl = c_name in client.wishlist or is_series_wl or is_wished_by_self(msg, client.user.id) or is_ranked
            is_avoided = c_name in client.avoid_list

            if is_wl and not is_avoided: wl_claims.append((msg, c_name, k_v, series))
            elif k_v >= min_kak_post and not is_avoided: char_claims.append((msg, c_name, k_v, series))

        # Filter claims to exclude messages already claimed/in progress globally
        wl_claims = _claim_coordinator.filter_available(wl_claims)
        char_claims = _claim_coordinator.filter_available(char_claims)

        msg_claimed_id = -1
        if key_mode_only_kakera_param or is_key_mode_kakera_only():
            BotLogger.log("Key mode active, no claim/RT. Skipping character claims.", preset_name, "INFO")
        elif is_character_snipe_allowed(is_external_snipe=False):
            if client.claim_right_available:
                if wl_claims:
                    wl_claims.sort(key=lambda x: (x[2], x[0].id), reverse=True)
                    m_c, n, v, _ = wl_claims[0]
                    if await claim_character(client, channel, m_c, is_kakera=False, kakera_value=v):
                        msg_claimed_id = m_c.id
                        attempted.add(n)
                elif char_claims:
                    char_claims.sort(key=lambda x: (x[2], x[0].id), reverse=True)
                    m_c, n, v, _ = char_claims[0]
                    if await claim_character(client, channel, m_c, is_kakera=False, kakera_value=v):
                        msg_claimed_id = m_c.id
                        attempted.add(n)
            elif client.key_mode and not client.rt_available:
                valid_chars = [x for x in char_claims if x[2] >= client.min_kakera]
                if wl_claims:
                    wl_claims.sort(key=lambda x: (x[2], x[0].id), reverse=True)
                    m_c, n, v, _ = wl_claims[0]
                    if await claim_character(client, channel, m_c, is_kakera=False, kakera_value=v):
                        msg_claimed_id = m_c.id
                        attempted.add(n)
                elif valid_chars:
                    valid_chars.sort(key=lambda x: (x[2], x[0].id), reverse=True)
                    m_c, n, v, _ = valid_chars[0]
                    if await claim_character(client, channel, m_c, is_kakera=False, kakera_value=v):
                        msg_claimed_id = m_c.id
                        attempted.add(n)

        if client.rt_available and not is_key_mode_kakera_only():
            rt_targets = []
            failed_rt_messages = getattr(client, "_rt_failed_message_ids", set())
            for msg, n, v, s in (wl_claims + char_claims):
                if (msg.id == msg_claimed_id
                        or msg.id in client.processed_claim_messages
                        or msg.id in failed_rt_messages
                        or n == getattr(client, 'last_successfully_claimed_character', '')):
                    continue
                claims_r, likes_r = parse_mudae_ranks(msg.embeds[0].description or "")
                is_ranked = (client.max_claim_rank > 0 and 0 < claims_r <= client.max_claim_rank) or (client.max_like_rank > 0 and 0 < likes_r <= client.max_like_rank)
                is_series_wl_rt = await series_wishlist_matches(msg, s)
                is_wl_rt = n in client.wishlist or is_series_wl_rt or is_wished_by_self(msg, client.user.id) or is_ranked

                if (is_wl_rt and client.rt_ignore_min_kakera_for_wishlist) or v >= client.min_kakera:
                    rt_targets.append((msg, n, v))

            rt_targets = _claim_coordinator.filter_available(rt_targets)

            rt_targets.sort(key=lambda x: (x[2], x[0].id), reverse=True)
            for msg_rt, n_rt, v_rt in rt_targets:
                if n_rt in attempted: continue

                # Check and register in global RT tracker
                rt_locked_successfully = _claim_coordinator.reserve_restore(msg_rt.id)

                if not rt_locked_successfully:
                    continue

                try:
                    with _active_clients_lock:
                        account_index = _active_clients.index(client)
                except ValueError:
                    account_index = 0

                rt_delay = random.uniform(0.1, 0.5) * account_index
                if rt_delay > 0:
                    BotLogger.log(f"Staggering $rt send by {rt_delay:.2f}s for account index {account_index}", preset_name, "INFO")
                    if not await active_delay(rt_delay):
                        break

                # Fast validation check before sending $rt
                try:
                    msg_rt = await channel.fetch_message(msg_rt.id)
                except Exception:
                    pass

                already_claimed = False
                if msg_rt.embeds:
                    if get_character_owner(msg_rt.embeds[0]) is not None:
                        already_claimed = True
                if msg_rt.components:
                    claim_buttons = []
                    for comp in msg_rt.components:
                        for btn in comp.children:
                            if hasattr(btn.emoji, 'name') and btn.emoji.name and btn.emoji.name in client.claim_emojis:
                                claim_buttons.append(btn)
                    if not claim_buttons or all(getattr(btn, 'disabled', False) for btn in claim_buttons):
                        already_claimed = True

                if already_claimed:
                    BotLogger.log(f"Aborting RT attempt: {n_rt} has already been claimed/interacted with.", preset_name, "WARN")
                    invalidate_rt_after_failed_attempt(msg_rt.id, reason="rt-target-stale")
                    _claim_coordinator.release_restore(msg_rt.id)
                    continue

                BotLogger.log(f"Attempting RT on {n_rt} ({v_rt})", preset_name, "CLAIM")
                try:
                    if not await send_mudae_reaction_command(channel, f"{client.mudae_prefix}rt"):
                        invalidate_rt_after_failed_attempt(msg_rt.id)
                        break
                    apply_rt_acknowledgement()
                    attempted.add(n_rt)
                    await claim_character(client, channel, msg_rt, is_rt_claim=True, kakera_value=v_rt)
                    break
                except Exception:
                    pass
                finally:
                    _claim_coordinator.release_all(msg_rt.id)
        return bool(msg_claimed_id != -1)

    def regular_kakera_filter_reason(client, msg, embed, *, is_mk_roll=False, is_external_roll=False):
        """Explain why ordinary Kakera is blocked without blocking spheres or purple."""
        chaos_count = count_chaos_keys(embed)
        marker_text = kakera_embed_text(embed)
        return get_regular_kakera_filter_reason(
            wish_only=client.wish_starwish_kakera_only,
            is_wish=is_wish_or_starwish(msg, embed),
            op5_only=client.op_perk_5_only,
            has_op5=has_op_perk_five_marker(marker_text),
            mk_only=client.mk_only,
            is_mk_roll=is_mk_roll,
            chaos_only=client.only_chaos,
            is_external_roll=is_external_roll,
            has_chaos_discount=chaos_count > 0,
            has_perk_eight_discount=has_perk_eight_discount(marker_text),
        )

    def has_targeted_sphere_button(components):
        for component in components or ():
            for button in getattr(component, "children", ()) or ():
                name = str(getattr(getattr(button, "emoji", None), "name", "") or "")
                if is_character_sphere_emoji(name) and sphere_target_matches(
                    name,
                    client.sphere_click_targets,
                ):
                    return True
        return False

    def has_collectible_kakera_button(components, allowed_emojis):
        """Return whether this preset may click at least one Kakera button."""
        allowed = set(allowed_emojis or ())
        for component in components or ():
            for button in getattr(component, "children", ()) or ():
                if kakera_button_is_eligible(button, allowed, None):
                    return True
        return False

    def kakera_button_is_eligible(button, target_list, filter_reason):
        if getattr(button, "disabled", False):
            return False
        name = str(getattr(getattr(button, "emoji", None), "name", "") or "")
        clean = name.rstrip("2")
        if is_character_sphere_emoji(name):
            return sphere_target_matches(name, client.sphere_click_targets)
        if clean == "kakeraP":
            return client.collect_purple_kakera
        allowed = {str(item) for item in target_list or ()}
        return filter_reason is None and (name in allowed or clean in allowed)

    async def send_claim_click(button, timeout=2.0):
        """Start a claim immediately without treating a missing Discord ACK as a failed send."""
        task = client.loop.create_task(guarded_click(button))
        try:
            return bool(await asyncio.wait_for(asyncio.shield(task), timeout=timeout)), True
        except asyncio.TimeoutError:
            # discord.py-self can raise its own "no response" error much later,
            # after Discord already received the interaction. Verification is
            # safer than issuing a delayed duplicate click.
            def consume_late_result(done_task):
                try:
                    done_task.exception()
                except (asyncio.CancelledError, Exception):
                    pass

            task.add_done_callback(consume_late_result)
            return True, False

    async def collect_refreshed_purple_after_claim(channel, msg, is_snipe=False):
        """Collect a purple button that appears only after Mudae updates a claimed roll."""
        if not client.collect_purple_kakera or client.is_paused:
            return False
        refreshed = None
        for attempt in range(8):
            try:
                refreshed = await channel.fetch_message(msg.id)
            except Exception:
                refreshed = None
            if refreshed is not None and has_purple_kakera_button(refreshed.components):
                BotLogger.log(
                    "Post-claim Purple Kakera detected on the refreshed roll.",
                    preset_name,
                    "KAKERA",
                )
                return await claim_character(
                    client,
                    channel,
                    refreshed,
                    is_kakera=True,
                    is_snipe=is_snipe,
                )
            if attempt < 7 and not await active_delay(0.5):
                return False
        BotLogger.log(
            "Post-claim Purple Kakera not present after refreshing the roll.",
            preset_name,
            "DEBUG",
            client,
        )
        return False

    async def claim_character(client, channel, msg, is_kakera=False, is_rt_claim=False, is_snipe=False, is_free_claim=False, kakera_value=None, is_mk_roll=False):
        if client.is_paused or not msg or not msg.embeds: return False
        if not is_kakera and getattr(client, 'is_claiming', False): return False

        rt_registered = False
        claim_registered = False
        if not is_kakera and msg.id in client.processed_claim_messages: return False

        embed = msg.embeds[0]
        char_name = (embed.author.name if embed.author else "Unknown").strip()
        BotLogger.log(f"claim_character: '{char_name}' | k={is_kakera} rt={is_rt_claim} s={is_snipe} f={is_free_claim}", preset_name, "DEBUG", client)

        if not is_kakera and not is_free_claim and char_name.lower() == getattr(client, 'last_successfully_claimed_character', ''):
            return False

        kakera_str = ""
        if not is_kakera and not is_free_claim:
            val = kakera_value
            if val is None:
                m = re.search(REGEX_PATTERNS["KAKERA_VALUE"], embed.description or "")
                val = re.sub(r"[^\d]", "", m.group(1)) if m else None
            if val is not None: kakera_str = f" ({val} ka)"

        if not is_kakera and not is_rt_claim and not is_free_claim and not is_character_snipe_allowed(is_external_snipe=is_snipe):
            return False

        if not is_kakera:
            # Check lock and register
            needs_rt = (not is_free_claim and not is_rt_claim and not client.claim_right_available and client.rt_available and not (is_snipe and client.rt_only_self_rolls))
            if needs_rt:
                rt_locked_successfully = _claim_coordinator.reserve_restore(msg.id)
                rt_registered = rt_locked_successfully
                if not rt_locked_successfully:
                    return False
            else:
                claim_locked_successfully = _claim_coordinator.reserve_claim(msg.id, allow_reserved_restore=is_rt_claim)
                claim_registered = claim_locked_successfully

                if not claim_locked_successfully:
                    return False

            client.is_claiming = True
            client.processed_claim_messages.add(msg.id)
            if len(client.processed_claim_messages) > 1000:
                client.processed_claim_messages.clear()
        try:
            if not is_kakera and not is_free_claim and not is_rt_claim:
                if not client.claim_right_available and client.rt_available and not (is_snipe and client.rt_only_self_rolls):
                    try:
                        with _active_clients_lock:
                            account_index = _active_clients.index(client)
                    except ValueError:
                        account_index = 0

                    rt_delay = random.uniform(0.1, 0.5) * account_index
                    if rt_delay > 0:
                        BotLogger.log(f"Staggering $rt send by {rt_delay:.2f}s for account index {account_index}", preset_name, "INFO")
                        if not await active_delay(rt_delay): return False

                    # Fast validation check before sending $rt
                    try:
                        msg = await channel.fetch_message(msg.id)
                    except Exception:
                        pass

                    already_claimed = False
                    if msg.embeds:
                        if get_character_owner(msg.embeds[0]) is not None:
                            already_claimed = True
                    if msg.components:
                        claim_buttons = []
                        for comp in msg.components:
                            for btn in comp.children:
                                if hasattr(btn.emoji, 'name') and btn.emoji.name and btn.emoji.name in client.claim_emojis:
                                    claim_buttons.append(btn)
                        if not claim_buttons or all(getattr(btn, 'disabled', False) for btn in claim_buttons):
                            already_claimed = True

                    if already_claimed:
                        BotLogger.log(f"Aborting $rt command: {char_name} has already been claimed/interacted with.", preset_name, "WARN")
                        invalidate_rt_after_failed_attempt(msg.id, reason="rt-target-stale")
                        return False

                    BotLogger.log(f"Using RT for {char_name}", preset_name, "CLAIM")
                    try:
                        if not await send_mudae_reaction_command(channel, f"{client.mudae_prefix}rt"):
                            invalidate_rt_after_failed_attempt(msg.id)
                            return False
                        apply_rt_acknowledgement()
                    except Exception as e:
                        BotLogger.log(f"RT Failed: {e}", preset_name, "ERROR")
                        invalidate_rt_after_failed_attempt(msg.id)
                        return False

                    # Transition to claim lock
                    claim_locked_successfully = _claim_coordinator.transition_restore_to_claim(msg.id)
                    claim_registered = claim_locked_successfully
                    rt_registered = False

                    if not claim_locked_successfully:
                        return False

            if is_free_claim and not await active_delay(random.uniform(1.0, 2.5)): return False

            if is_kakera:
                chaos_count = count_chaos_keys(embed)
                has_sp_perk = has_perk_eight_discount(kakera_embed_text(embed))
                has_purple_kakera = (
                    client.collect_purple_kakera
                    and has_purple_kakera_button(msg.components)
                )
                has_targeted_sphere = has_targeted_sphere_button(msg.components)
                filter_reason = regular_kakera_filter_reason(
                    client,
                    msg,
                    embed,
                    is_mk_roll=is_mk_roll,
                    is_external_roll=is_snipe,
                )
                if filter_reason and not has_purple_kakera and not has_targeted_sphere:
                    BotLogger.log(f"Kakera skipped for {char_name}: {filter_reason}.", preset_name, "DEBUG", client)
                    return False
                if filter_reason:
                    BotLogger.log(
                        f"Regular Kakera filtered for {char_name}: {filter_reason}; collecting eligible sphere/purple buttons only.",
                        preset_name,
                        "DEBUG",
                        client,
                    )

                target_list = get_kakera_emoji_targets(
                    client.kakera_emojis,
                    client.chaos_emojis,
                    client.sphere_perk_emojis,
                    has_chaos_discount=chaos_count > 0,
                    has_perk_eight_discount=has_sp_perk,
                    is_external_roll=is_snipe,
                )

                # The 10+ key discount and cooldown bypass only applies to self-rolls (when is_snipe is False)
                has_reaction_cooldown_bypass = (chaos_count > 0 and not is_snipe) or has_sp_perk
                if not is_kakera_reaction_allowed(is_free_purple=has_purple_kakera) and not has_reaction_cooldown_bypass and not has_targeted_sphere:
                    BotLogger.log(
                        f"Kakera skipped for {char_name}: reaction is on cooldown and no valid discount bypass applies.",
                        preset_name,
                        "DEBUG",
                        client,
                    )
                    return False

                if msg.id in client.kakera_reacted_messages: return False
                if len(client.kakera_reacted_messages) > 2000: client.kakera_reacted_messages.clear()

                clicked = False
                if msg.components:
                    all_btns_tracked = []
                    for row_idx, comp in enumerate(msg.components):
                        for child_idx, btn in enumerate(comp.children):
                            if hasattr(btn.emoji, 'name') and btn.emoji.name:
                                name = btn.emoji.name
                                name_clean = name.rstrip('2')
                                if kakera_button_is_eligible(btn, target_list, filter_reason):
                                    all_btns_tracked.append({
                                        'btn': btn, 'custom_id': btn.custom_id,
                                        'pos': (row_idx, child_idx), 'emoji_name': name
                                    })

                    prio_map = {k.strip(): (idx + 1) * 10 for idx, k in enumerate(reversed(client.kakera_priority_order))}
                    for s in client.sphere_emojis: prio_map[s] = 999
                    if client.collect_purple_kakera:
                        prio_map['kakeraP'] = 999

                    all_btns_tracked.sort(key=lambda item: prio_map.get(item['emoji_name'].rstrip('2'), 0), reverse=True)

                    buttons_to_click = all_btns_tracked

                    if not buttons_to_click:
                        available = [
                            getattr(getattr(button, "emoji", None), "name", "?")
                            for component in msg.components
                            for button in component.children
                            if getattr(getattr(button, "emoji", None), "name", None)
                        ]
                        BotLogger.log(
                            f"Kakera skipped for {char_name}: no enabled button matches this roll's emoji list "
                            f"(available: {', '.join(available) or 'none'}).",
                            preset_name,
                            "DEBUG",
                            client,
                        )

                    clicked_count = 0
                    for item in buttons_to_click:
                        btn = item['btn']
                        custom_id = item['custom_id']
                        pos = item['pos']
                        name = item['emoji_name']

                        if clicked_count > 0:
                            try:
                                msg = await channel.fetch_message(msg.id)
                                btn = find_refreshed_component_button(
                                    msg.components,
                                    custom_id=custom_id,
                                    position=pos,
                                    emoji_name=name,
                                )
                                if btn is None:
                                    continue
                            except Exception: break

                        if getattr(btn, 'disabled', False):
                            continue

                        name_clean = name.rstrip('2')
                        is_sphere = is_character_sphere_emoji(name)
                        is_free = name_clean == 'kakeraP' or is_sphere or check_is_green(btn)
                        if client.only_chaos and (is_snipe or (chaos_count == 0 and not has_sp_perk)) and not is_free:
                            continue
                        cost = calculate_kakera_power_cost(
                            client.dk_consumption,
                            has_chaos_discount=chaos_count > 0,
                            has_perk_eight_discount=has_sp_perk,
                            is_external_roll=is_snipe,
                            is_free=is_free,
                        )
                        async with get_kakera_action_lock():
                            # Recheck after serializing clicks: another account may
                            # have just received a $ku rejection for this preset.
                            is_free_purple = name_clean == 'kakeraP'
                            if not is_kakera_reaction_allowed(is_free_purple=is_free_purple) and not has_reaction_cooldown_bypass and not is_free:
                                BotLogger.log(
                                    f"Kakera skipped for {char_name}: reaction became unavailable before {name} could be clicked.",
                                    preset_name,
                                    "DEBUG",
                                    client,
                                )
                                continue
                            current_pow = get_current_dk_power()

                            if cost > 0 and current_pow is None:
                                request_status_refresh({"power"}, reason="power-unknown", urgent=True)
                                continue
                            if cost > 0 and current_pow < cost:
                                if (client.auto_dk_enabled and client.dk_power_management and client.dk_stock_count > 0
                                        and should_auto_refill_dk(current_pow, cost)):
                                    log_name = btn.emoji.name if hasattr(btn.emoji, 'name') else 'Kakera'
                                    BotLogger.log(f"Dynamic DK Refill: Power too low ({current_pow}% < {cost}%). Sending $dk for {log_name}...", preset_name, "KAKERA")
                                    try:
                                        cmd_ch = _get_command_channel() or channel
                                        if not await guarded_send(cmd_ch, f"{client.mudae_prefix}dk"):
                                            return clicked
                                        client.dk_stock_count = max(0, client.dk_stock_count - 1)
                                        client.current_dk_power = client.max_dk_power
                                        client.kakera_power_ledger.clear()
                                        mark_dk_power_changed()
                                        client.last_dk_power_update_utc = datetime.datetime.now(timezone.utc)
                                        request_status_refresh({"power"}, reason="dynamic-dk-used")
                                        if not await active_delay(1.2 + random.uniform(0.1, 0.4)):
                                            return clicked
                                        current_pow = get_current_dk_power()
                                    except Exception as e:
                                        BotLogger.log(f"Dynamic DK Refill failed: {e}", preset_name, "ERROR")

                            if cost > 0 and current_pow < cost:
                                log_name = btn.emoji.name if hasattr(btn.emoji, 'name') else 'Kakera'
                                if not hasattr(client, 'last_power_warn') or (time.time() - getattr(client, 'last_power_warn', 0) > 60):
                                    BotLogger.log(f"Insufficient Power ({current_pow}% < {cost}%). Skipping {log_name}.", preset_name, "WARN")
                                    client.last_power_warn = time.time()
                                continue

                            if cost > 0 and client.kakera_power_thresholds:
                                base_name = name.rstrip('2')
                                # The 10+ key discount only applies to self-rolls (when is_snipe is False)
                                spec_name = f"chaos_{base_name}" if (chaos_count > 0 and not is_snipe) else base_name
                                threshold = first_configured(client.kakera_power_thresholds, spec_name, base_name, name)
                                if threshold is not None and current_pow < threshold:
                                    BotLogger.log(f"Power ({current_pow}%) below threshold ({threshold}%) for {spec_name}. Waiting.", preset_name, "INFO")
                                    continue

                            if client.debug_mode:
                                ws_ref = getattr(client, 'ws', None)
                                sid = getattr(ws_ref, 'session_id', None) if ws_ref else None
                                BotLogger.log(f"Kakera Click: custom_id={getattr(btn, 'custom_id', 'N/A')} | name={name} | session_id={sid}", preset_name, "DEBUG", client)

                            power_token = reserve_kakera_power_click(name, cost) if cost > 0 else None
                            try:
                                click_ok = await click_kakera_with_confirmation(
                                    channel,
                                    msg,
                                    btn,
                                    custom_id=custom_id,
                                    position=pos,
                                    emoji_name=name,
                                    character_name=char_name,
                                )
                                if not click_ok:
                                    cancel_kakera_power_click(power_token)
                                    continue
                                client.kakera_reacted_messages.add(msg.id)
                                estimated_power = get_current_dk_power()
                                power_text = f"{estimated_power}%" if estimated_power is not None else "unknown"
                                BotLogger.log(f"Kakera click sent: {char_name} [{name}] (Estimated Pw: {power_text})", preset_name, "KAKERA")
                                clicked = True
                                clicked_count += 1
                                client._last_kakera_click_ts = time.time()
                                if not await active_delay(0.6):
                                    return clicked
                            except discord.HTTPException as e:
                                cancel_kakera_power_click(power_token)
                                BotLogger.log(f"Kakera click failed (HTTP {getattr(e, 'status', '?')}): {getattr(e, 'text', str(e))[:100]}", preset_name, "ERROR")
                            except Exception as e:
                                cancel_kakera_power_click(power_token)
                                BotLogger.log(f"Kakera click error: {e}", preset_name, "ERROR")
                if (
                    clicked
                    and is_snipe
                    and client.enable_kakera_snipe_chat_reactions
                    and client.kakera_snipe_chat_messages
                ):
                    try:
                        if await active_delay(random.uniform(2.0, 5.0)):
                            await guarded_send(
                                channel,
                                random.choice(client.kakera_snipe_chat_messages),
                            )
                    except Exception as error:
                        BotLogger.log(
                            f"Kakera snipe chat reaction failed: {error}",
                            preset_name,
                            "ERROR",
                        )
                return clicked

            clicked_claim = False
            if msg.components:
                for comp in msg.components:
                    if clicked_claim: break
                    for btn in comp.children:
                        has_emoji = hasattr(btn.emoji, 'name') and btn.emoji.name is not None
                        is_claim_button = has_emoji and btn.emoji.name in client.claim_emojis
                        is_verified_free_button = is_claim_button and (is_free_event(embed) or check_is_green(btn))
                        if (is_free_claim and is_verified_free_button) or (not is_free_claim and is_claim_button):
                            if client.debug_mode:
                                ws_ref = getattr(client, 'ws', None)
                                sid = getattr(ws_ref, 'session_id', None) if ws_ref else None
                                BotLogger.log(f"Claim Click: custom_id={getattr(btn, 'custom_id', 'N/A')} | session_id={sid}", preset_name, "DEBUG", client)

                            _claim_kv = kakera_value or 0
                            _claim_series = embed.description.splitlines()[0] if embed and embed.description else ""
                            pending = prepare_pending_claim(
                                msg, char_name, is_snipe, _claim_kv, _claim_series,
                                consumes_claim=not is_free_claim, is_rt_claim=is_rt_claim,
                            )
                            claim_success = False
                            BotLogger.log(f"Claim attempt: {char_name}{kakera_str}", preset_name, "CLAIM" if not is_free_claim else "INFO")
                            for attempt in range(3):
                                try:
                                    click_sent, acknowledged = await send_claim_click(btn)
                                    if not click_sent:
                                        break
                                    claim_success = True
                                    if not acknowledged:
                                        BotLogger.log(
                                            f"Claim click sent for {char_name}; Discord ACK is delayed, verifying without a duplicate click.",
                                            preset_name,
                                            "WARN",
                                        )
                                    break
                                except Exception as e:
                                    if attempt < 2:
                                        BotLogger.log(f"Claim click failed (attempt {attempt+1}/3): {e}. Retrying...", preset_name, "WARN")
                                        if not await active_delay(0.5):
                                            break
                                    else:
                                        BotLogger.log(f"Claim click failed after 3 attempts: {e}", preset_name, "ERROR")

                            if claim_success:
                                BotLogger.log(f"Claiming {char_name}{kakera_str}", preset_name, "CLAIM" if not is_free_claim else "INFO")
                                clicked_claim = True
                                claim_outcome = await verify_snipe_outcome(client, channel, msg, pending)
                                if claim_outcome == ClaimOutcome.SUCCESS:
                                    await collect_refreshed_purple_after_claim(channel, msg, is_snipe=is_snipe)
                                return True
                            release_failed_claim(getattr(msg, "id", None), pending)

            if not clicked_claim and has_claim_option(msg, embed, client.claim_emojis):
                try:
                    if client.is_paused:
                        return False
                    reaction_emoji = random.choice(client.randomized_claim_reactions)
                    _react_kv = kakera_value or 0
                    _react_series = embed.description.splitlines()[0] if embed and embed.description else ""
                    pending = prepare_pending_claim(
                        msg, char_name, is_snipe, _react_kv, _react_series,
                        consumes_claim=not is_free_claim, is_rt_claim=is_rt_claim,
                    )
                    if not await guarded_reaction(msg, reaction_emoji):
                        release_failed_claim(getattr(msg, "id", None), pending)
                        return False
                    BotLogger.log(f"Claiming {char_name}{kakera_str} (Reaction: {reaction_emoji})", preset_name, "CLAIM")
                    claim_outcome = await verify_snipe_outcome(client, channel, msg, pending)
                    if claim_outcome == ClaimOutcome.SUCCESS:
                        await collect_refreshed_purple_after_claim(channel, msg, is_snipe=is_snipe)
                    return True
                except Exception as e:
                    release_failed_claim(getattr(msg, "id", None), locals().get('pending'))
                    BotLogger.log(f"Reaction fallback FAILED: {e}", preset_name, "ERROR")
                    return False
            return False
        finally:
            if not is_kakera:
                client.is_claiming = False
                if claim_registered or rt_registered:
                    _claim_coordinator.release_all(msg.id)

    async def humanized_wait_and_proceed(client, channel, base_reset_minutes, reason="reset"):
        min_wait = max(0.0, base_reset_minutes * 60)
        if min_wait <= 0: min_wait = max(client.delay_seconds + 60, 240)
        is_cache_refresh = "cached status refresh" in reason.lower()
        precision_wait = (
            "claim reset" in reason.lower()
            or is_cache_refresh
        )
        human_jitter = random.uniform(0, max(0.0, client.humanization_window_minutes * 60)) if client.humanization_enabled and not precision_wait else 0
        persistent_stagger = 0 if is_cache_refresh else getattr(client, 'persistent_stagger_seconds', 0)
        wait_seconds = min_wait + human_jitter + persistent_stagger

        BotLogger.log(f"{'Humanized ' if client.humanization_enabled else ''}Waiting {wait_seconds/60:.1f}m ({reason}).", preset_name, "RESET")
        deadline = time.monotonic() + wait_seconds
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            await _interruptible_sleep(remaining)
            if client.is_paused:
                return
            if time.monotonic() >= deadline:
                break
            # A stale wake event used to abort the visible wait, while the
            # status loop still observed only the shorter base deadline. That
            # allowed a cached roll reset to be scheduled again before a
            # fresh $tu. Only real work should interrupt this wait.
            if status_dirty_fields(client) or client.scheduled_roll_due:
                return

        if is_inactive_hour():
            wait_s = seconds_until_active() + (random.uniform(0, client.humanization_window_minutes * 60) if client.humanization_enabled else 0)
            BotLogger.log(f"Inactive hours. Sleeping {wait_s/60:.0f}m.", preset_name, "RESET")
            await _interruptible_sleep(wait_s)
            if client.is_paused:
                return

        if client.humanization_enabled and not is_cache_refresh:
            while True:
                try:
                    last_msg = None
                    async for m in channel.history(limit=1): last_msg = m
                    if not last_msg: break
                    diff = (datetime.datetime.now(timezone.utc) - last_msg.created_at).total_seconds()
                    if diff >= client.humanization_inactivity_seconds: break
                    await _interruptible_sleep(client.humanization_inactivity_seconds - diff + 0.5)
                    if client.is_paused:
                        return
                except Exception: break

    async def handle_birthday_candle(msg):
        if not await active_delay(random.uniform(0.5, 2.0)):
            return
        if msg.components:
            for comp in msg.components:
                for btn in comp.children:
                    if hasattr(btn.emoji, 'name') and btn.emoji.name == '🕯️':
                        try:
                            if not await guarded_click(btn):
                                return
                            c_name = msg.embeds[0].author.name if msg.embeds and msg.embeds[0].author else "Unknown"
                            BotLogger.log(f"🕯️ Clicked candle for {c_name}", preset_name, "CLAIM")
                        except Exception: pass
                        return

    def schedule_farm_release_after_other_claim(message, previous_message=None):
        """Release farm targets claimed by a peer, including owner-only embed edits."""
        if (
            client.is_paused
            or is_maintenance_active()
            or is_inactive_hour()
            or getattr(getattr(message, "author", None), "id", None) != TARGET_BOT_ID
            or not client.farm_character_enabled
            or not client.farm_characters
            or not client.farm_forcedivorce_after_other_claim
        ):
            return False

        channel_id = getattr(getattr(message, "channel", None), "id", None)
        watched_channel = (
            channel_id == client.target_channel_id
            or (client.snipe_mode and channel_id in client.snipe_channels)
            or (
                client.kakera_reaction_snipe_mode_active
                and channel_id in client.kakera_snipe_channels
            )
        )
        if not watched_channel:
            return False

        if getattr(message, "embeds", None):
            embed = message.embeds[0]
            char_name = getattr(getattr(embed, "author", None), "name", "")
            if is_farm_character_name(char_name):
                owner = get_character_owner(embed)
                previous_owner = None
                if previous_message is not None and getattr(previous_message, "embeds", None):
                    previous_owner = get_character_owner(previous_message.embeds[0])
                if owner and owner != previous_owner:
                    owner_evidence = classify_claim_owner(
                        owner,
                        claim_identities(getattr(message, "guild", None)),
                        user_id=getattr(getattr(client, "user", None), "id", None),
                    )
                    if owner_evidence.outcome == ClaimOutcome.FAILURE:
                        client.loop.create_task(execute_farm_forcedivorce(
                            client,
                            message.channel,
                            char_name,
                            "after another account claimed it (configured timing)",
                        ))
                        return True

        for farm_name in client.farm_characters:
            if not is_claim_announcement_for_character(getattr(message, "content", ""), farm_name):
                continue
            farm_claim_evidence = classify_claim_text(
                message.content,
                farm_name,
                claim_identities(getattr(message, "guild", None)),
                user_id=getattr(getattr(client, "user", None), "id", None),
            )
            if farm_claim_evidence.outcome != ClaimOutcome.SUCCESS:
                client.loop.create_task(execute_farm_forcedivorce(
                    client,
                    message.channel,
                    farm_name,
                    "after another account claimed it (configured timing)",
                ))
                return True
            break
        return False

    @client.event
    async def on_message_edit(before, after):
        update_event = client._sphere_board_update_events.get(getattr(after, 'id', None))
        if update_event is not None:
            update_event.set()
        capture_sphere_game_bonus(after)
        schedule_farm_release_after_other_claim(after, previous_message=before)

    @client.event
    async def on_raw_reaction_add(payload):
        message_id = getattr(payload, 'message_id', None)
        if not mudae_command_ack_matches(payload, message_id, TARGET_BOT_ID):
            return
        client._recent_mudae_command_acks[message_id] = time.monotonic()
        while len(client._recent_mudae_command_acks) > 500:
            client._recent_mudae_command_acks.pop(next(iter(client._recent_mudae_command_acks)))
        waiter = client._mudae_command_ack_waiters.get(message_id)
        if waiter is not None and not waiter.done():
            waiter.set_result(True)

    @client.event
    async def on_raw_message_edit(payload):
        update_event = client._sphere_board_update_events.get(getattr(payload, 'message_id', None))
        if update_event is not None:
            update_event.set()

    @client.event
    async def on_command_error(ctx, error):
        if isinstance(error, commands.CommandNotFound):
            return
        BotLogger.log(f"Control command failed: {error}", preset_name, "WARN")

    @client.event
    async def on_message(message):
        update_dynamic_thresholds()
        observe_shared_tu_resets(message)
        capture_tu_response(message)
        capture_sphere_game_response(message)
        capture_sphere_game_bonus(message)
        is_roll = (message.channel.id == client.target_channel_id)
        is_snipe = (client.snipe_mode and message.channel.id in client.snipe_channels)
        is_kakera_snipe_channel = (
            client.kakera_reaction_snipe_mode_active
            and message.channel.id in client.kakera_snipe_channels
        )

        if message.author.id != TARGET_BOT_ID or not (is_roll or is_snipe or is_kakera_snipe_channel):
            if not client.is_paused and client.rolling_enabled: await client.process_commands(message)
            return

        record_claim_text_evidence(message)
        process_claim_cooldown_message(message)
        process_kakera_reaction_cooldown_message(message)
        schedule_mudae_emoji_asset_cache(client, message)

        kakera_result = parse_kakera_result(
            message.content,
            claim_identities(getattr(message, 'guild', None)),
        )
        if kakera_result is not None:
            resolve_kakera_result_waiters(kakera_result.emoji_name, kakera_result.amount)
            confirmed_cost = confirm_kakera_power_click(kakera_result.emoji_name)
            if confirmed_cost is not None:
                if kakera_result.emoji_name.rstrip("2").casefold() == "kakerac":
                    client._confirmed_kakera_c_bonus_until = time.monotonic() + 10.0
                remaining = get_current_dk_power()
                BotLogger.log(
                    f"Kakera result confirmed (+{kakera_result.amount}); "
                    f"committed {confirmed_cost}% power (Estimated Pw: {remaining}%).",
                    preset_name,
                    "KAKERA",
                )

        if message.content and "under maintenance" in message.content.lower():
            m_match = re.search(REGEX_PATTERNS["MAINTENANCE"], message.content, re.IGNORECASE)
            m_mins = 10
            if m_match and m_match.group(1):
                try:
                    m_mins = int(m_match.group(1))
                except ValueError:
                    pass
            client.maintenance_until = datetime.datetime.now(timezone.utc) + datetime.timedelta(minutes=m_mins)
            client.interrupt_rolling = True
            client._roll_interrupt_reason = "maintenance"
            request_status_refresh(reason="mudae-maintenance", urgent=True)
            BotLogger.log(f"Mudae is under maintenance! Pausing for {m_mins} minutes.", preset_name, "ERROR")
            return

        if is_maintenance_active(): return
        if client.is_paused:
            return

        if getattr(client, '_post_maintenance_inactivity_needed', False):
            if client.humanization_enabled and client.humanization_inactivity_seconds > 0:
                now_utc = datetime.datetime.now(timezone.utc)
                last_seen = getattr(client, '_post_maint_last_msg_utc', None)
                client._post_maint_last_msg_utc = now_utc
                if last_seen is None: return
                gap = (now_utc - last_seen).total_seconds()
                if gap < client.humanization_inactivity_seconds: return
                BotLogger.log(f"Post-maintenance: Channel inactive for {gap:.0f}s. Resuming.", preset_name, "INFO")
            client._post_maintenance_inactivity_needed = False

        if message.components:
            for comp in message.components:
                for btn in comp.children:
                    if hasattr(btn.emoji, 'name') and btn.emoji.name == '🕯️':
                        client.loop.create_task(handle_birthday_candle(message))
                        break

        if is_inactive_hour(): return

        schedule_farm_release_after_other_claim(message)

        if client.main_account_id:
            try: main_id = int(client.main_account_id)
            except ValueError: main_id = None
            if main_id is not None and message.embeds:
                embed_ma = message.embeds[0]
                if is_character_embed(embed_ma) and is_wished_by_self(message, main_id):
                    c_name = embed_ma.author.name.lower()
                    if c_name not in client.avoid_list and has_claim_option(message, embed_ma, client.claim_emojis):
                        already_in_progress = _claim_coordinator.is_reserved(message.id)
                        if not already_in_progress and is_character_snipe_allowed(is_external_snipe=True):
                            BotLogger.log(f"Main Account Sync (wished by Main): {c_name}! Priority claiming.", preset_name, "CLAIM")
                            if not await active_delay(0.1 + random.uniform(0.01, 0.05)): return
                            if await claim_character(client, message.channel, message, is_snipe=True): return

        if message.content and not message.embeds and client.rolling_enabled:
            m_bonus = re.search(REGEX_PATTERNS["EXTRA_ROLLS"], message.content)
            bonus_from_confirmed_kakera_c = (
                time.monotonic() <= client._confirmed_kakera_c_bonus_until
            )
            if (m_bonus and bonus_from_confirmed_kakera_c
                    and (time.time() - getattr(client, '_last_kakera_click_ts', 0)) <= 10):
                bonus_amt = int(m_bonus.group(1))
                client._confirmed_kakera_c_bonus_until = 0.0
                client.rolls_left += bonus_amt
                client._local_extra_rolls_pending += bonus_amt
                BotLogger.log(f"Gained +{bonus_amt} extra rolls from Kakera! rolls_left is now {client.rolls_left}.", preset_name, "KAKERA")
                wake_status_loop()

        if not message.embeds: return
        embed = message.embeds[0]

        if (
            message.components
            and has_purple_kakera_button(message.components)
            and not client.collect_purple_kakera
        ):
            BotLogger.log(
                "Purple Kakera skipped: Collect Purple Kakera is disabled for this preset.",
                preset_name,
                "DEBUG",
                client,
            )

        if not is_character_embed(embed):
            if client.kakera_reaction_snipe_mode_active and message.id not in client.kakera_reaction_sniped_messages:
                all_k = client.kakera_emojis + client.chaos_emojis + client.sphere_emojis + client.sphere_perk_emojis
                has_btn = has_collectible_kakera_button(message.components, all_k)
                if has_btn:
                    if client.kakera_reaction_snipe_targets:
                        owner_id, owner_name = await detect_roll_owner(client, message)
                        is_target = False
                        if owner_id and str(owner_id) in client.kakera_reaction_snipe_targets:
                            is_target = True
                        if owner_name and owner_name in client.kakera_reaction_snipe_targets:
                            is_target = True
                        if not is_target:
                            return
                    client.kakera_reaction_sniped_messages.add(message.id)
                    if not await active_delay(client.kakera_reaction_snipe_delay_value + random.uniform(0.05, 0.25)): return
                    await claim_character(client, message.channel, message, is_kakera=True, is_snipe=True)
            return

        if client.auto_free_claim_enabled and has_free_claim_button(message.components, client.claim_emojis):
            c_name = embed.author.name.lower()
            if c_name not in client.avoid_list and not _claim_coordinator.is_reserved(message.id):
                BotLogger.log(f"Free Claim: green claim button detected for {c_name}.", preset_name, "CLAIM")
                if await claim_character(client, message.channel, message, is_free_claim=True):
                    return

        owner_id, owner_name = await detect_roll_owner(client, message)
        self_names = {
            str(getattr(client.user, "name", "") or "").casefold(),
            str(getattr(client.user, "display_name", "") or "").casefold(),
        }
        is_self_roll = owner_id == client.user.id or bool(owner_name and owner_name in self_names)
        if client.rolling_enabled and client.is_actively_rolling and is_self_roll:
            client._rolls_received += 1
            desc = embed.description or ""
            if any(limit in desc for limit in ["limit of 1,000 keys", "limite de 1.000 chaves", "límite de 1.000 llaves"]):
                client.interrupt_rolling = True
                client._roll_interrupt_reason = "key-limit"
                client.key_limit_hit = True
                BotLogger.log("Key Limit Hit. Pausing 1h.", preset_name, "ERROR")
                async def _key_limit_recovery():
                    await asyncio.sleep(3600 + random.randint(0, 600))
                    if client._immediate_check_event: client._immediate_check_event.set()
                client.loop.create_task(_key_limit_recovery())
                return

            c_name = embed.author.name.lower()
            series = desc.splitlines()[0].lower() if desc else ""
            k_val = 0
            m_k = re.search(REGEX_PATTERNS["KAKERA_VALUE"], desc)
            if m_k: k_val = int(re.sub(r"[^\d]", "", m_k.group(1)))

            claims_r, likes_r = parse_mudae_ranks(desc)
            is_ranked = (client.max_claim_rank > 0 and 0 < claims_r <= client.max_claim_rank) or (client.max_like_rank > 0 and 0 < likes_r <= client.max_like_rank)
            is_series_wl = await series_wishlist_matches(message, series)
            is_wl = c_name in client.wishlist or is_series_wl or is_wished_by_self(message, client.user.id) or is_ranked
            is_avoided = c_name in client.avoid_list

            in_panic_hour = False
            if client.next_claim_reset_at_utc:
                now_utc = datetime.datetime.now(timezone.utc)
                claim_reset_mins = (client.next_claim_reset_at_utc - now_utc).total_seconds() / 60.0
                if claim_reset_mins <= getattr(client, 'panic_roll_minutes', 5) or claim_reset_mins <= 60:
                    in_panic_hour = True

            process = True
            use_hybrid = getattr(client, 'enable_hybrid_panic_claim', False) and in_panic_hour

            if use_hybrid:
                is_instant_kakera = (k_val >= getattr(client, 'hybrid_panic_instant_claim_min_kakera', 300))
                is_instant_rank = False
                max_rank = getattr(client, 'hybrid_panic_instant_claim_max_rank', 200)
                if max_rank > 0:
                    is_instant_rank = ((0 < claims_r <= max_rank) or (0 < likes_r <= max_rank))

                is_high_value = (is_wl or is_instant_kakera or is_instant_rank)

                already_in_progress = _claim_coordinator.is_reserved(message.id)

                if is_high_value and not is_avoided and has_claim_option(message, embed, client.claim_emojis) and not already_in_progress:
                    if is_key_mode_kakera_only():
                        pass
                    else:
                        client.interrupt_rolling = True
                        client._roll_interrupt_reason = "claim-attempt"
                        BotLogger.log(f"Hybrid Smart Instant Claim triggered for {c_name} ({k_val} ka)!", preset_name, "CLAIM")
                        if client.reactive_snipe_delay > 0:
                            if not await active_delay(client.reactive_snipe_delay + random.uniform(0.05, 0.25)): return
                        if await claim_character(client, message.channel, message, kakera_value=k_val):
                            process = False
                elif k_val >= client.current_min_kakera_for_roll_claim and not is_avoided:
                    client.collected_rolls.append(message)

                # Hybrid panic still needs real-time Kakera handling. The
                # post-roll backlog above is only for character claims.
                all_k = client.kakera_emojis + client.chaos_emojis + client.sphere_emojis + client.sphere_perk_emojis
                has_btn = has_collectible_kakera_button(message.components, all_k)
                if has_btn:
                    if getattr(client, 'immediate_kakera_click', True):
                        d_min, d_max = client.reactive_kakera_delay_range
                        if d_max > 0 and not await active_delay(random.uniform(d_min, d_max)): return
                        await claim_character(client, message.channel, message, is_kakera=True)
                    else:
                        client.collected_kakera_rolls.append(message)
            else:
                refresh_predicted_claim_and_rt()
                if not client.claim_right_available and not client.rt_available:
                    is_val = k_val >= client.current_min_kakera_for_roll_claim
                    if (is_wl or is_val) and not is_avoided and has_claim_option(message, embed, client.claim_emojis):
                        if getattr(client, 'is_timing_mode_active', False):
                            if message.id not in {getattr(item, "id", None) for item in client.collected_rolls}:
                                client.collected_rolls.append(message)
                            BotLogger.log(f"Smart Timing: Saved {c_name} for claim at reset.", preset_name, "CLAIM")
                        else:
                            t_to_r = (client.next_claim_reset_at_utc - datetime.datetime.now(timezone.utc)).total_seconds() if client.next_claim_reset_at_utc else 999
                            if 0 < t_to_r <= 15:
                                BotLogger.log(f"Claim reset is in {t_to_r:.1f}s. Waiting for reset...", preset_name, "INFO")
                                if message.id not in {getattr(item, "id", None) for item in client.collected_rolls}:
                                    client.collected_rolls.append(message)
                                client._claim_reset_rolls_pending = True
                                client.interrupt_rolling = True
                                client._roll_interrupt_reason = "claim-reset-boundary"
                                if not await active_delay(t_to_r + 0.2): return
                                request_status_refresh({"claim"}, reason="near-claim-reset-boundary", urgent=True)
                                return
                elif not getattr(client, 'enable_reactive_self_snipe', True):
                    client.collected_rolls.append(message)
                else:
                    is_val = k_val >= client.current_min_kakera_for_roll_claim
                    already_in_progress = _claim_coordinator.is_reserved(message.id)
                    if (is_wl or is_val) and not is_avoided and has_claim_option(message, embed, client.claim_emojis) and not already_in_progress:
                        can_spend_rt = can_spend_restore_on_character(
                            k_val,
                            client.min_kakera,
                            is_wl,
                            client.rt_ignore_min_kakera_for_wishlist,
                        )
                        if (
                            is_key_mode_kakera_only()
                            or (not client.claim_right_available and not can_spend_rt)
                        ):
                            pass
                        else:
                            client.interrupt_rolling = True
                            client._roll_interrupt_reason = "claim-attempt"
                            BotLogger.log(f"Real-time Claim: Halting rolls for claim attempt on {c_name}", preset_name, "CLAIM")
                            if client.reactive_snipe_delay > 0:
                                if not await active_delay(client.reactive_snipe_delay + random.uniform(0.05, 0.25)): return
                            if await claim_character(client, message.channel, message, kakera_value=k_val):
                                process = False

                all_k = client.kakera_emojis + client.chaos_emojis + client.sphere_emojis + client.sphere_perk_emojis
                has_btn = has_collectible_kakera_button(message.components, all_k)
                if has_btn:
                    if getattr(client, 'immediate_kakera_click', True):
                        d_min, d_max = client.reactive_kakera_delay_range
                        if d_max > 0 and not await active_delay(random.uniform(d_min, d_max)): return
                        await claim_character(client, message.channel, message, is_kakera=True)
                    else:
                        client.collected_kakera_rolls.append(message)
        else:
            c_name = embed.author.name.lower()
            process = True

            # Determine roll owner
            client_names = {
                str(getattr(client.user, 'name', '') or '').lower(),
                str(getattr(client.user, 'display_name', '') or '').lower(),
            }
            is_manual_self_roll = owner_id == client.user.id or bool(owner_name and owner_name in client_names)
            if process and is_manual_self_roll and client.enable_reactive_self_snipe:
                desc = embed.description or ""
                series = desc.splitlines()[0].lower() if desc else ""
                k_val = 0
                m_k = re.search(REGEX_PATTERNS["KAKERA_VALUE"], desc)
                if m_k: k_val = int(re.sub(r"[^\d]", "", m_k.group(1)))
                claims_r, likes_r = parse_mudae_ranks(desc)
                is_ranked = (client.max_claim_rank > 0 and 0 < claims_r <= client.max_claim_rank) or (client.max_like_rank > 0 and 0 < likes_r <= client.max_like_rank)
                is_series_wl = await series_wishlist_matches(message, series, known_self_roll=True)
                is_wanted = c_name in client.wishlist or is_series_wl or is_wished_by_self(message, client.user.id) or is_ranked or k_val >= client.current_min_kakera_for_roll_claim
                is_avoided = c_name in client.avoid_list
                already_in_progress = _claim_coordinator.is_reserved(message.id)
                if is_wanted and not is_avoided and has_claim_option(message, embed, client.claim_emojis) and not already_in_progress:
                    can_spend_rt = can_spend_restore_on_character(
                        k_val,
                        client.min_kakera,
                        c_name in client.wishlist or is_series_wl or is_wished_by_self(message, client.user.id) or is_ranked,
                        client.rt_ignore_min_kakera_for_wishlist,
                    )
                    if (
                        not is_key_mode_kakera_only()
                        and is_character_snipe_allowed(is_external_snipe=False)
                        and (client.claim_right_available or can_spend_rt)
                    ):
                        BotLogger.log(f"Manual Self-Roll Claim: {c_name} ({k_val} ka)", preset_name, "CLAIM")
                        if client.reactive_snipe_delay > 0:
                            if not await active_delay(client.reactive_snipe_delay + random.uniform(0.05, 0.25)): return
                        if await claim_character(client, message.channel, message, kakera_value=k_val):
                            process = False

            if client.kakera_reaction_snipe_mode_active and message.id not in client.kakera_reaction_sniped_messages:
                 all_k = client.kakera_emojis + client.chaos_emojis + client.sphere_emojis + client.sphere_perk_emojis
                 has_purple_kakera = client.collect_purple_kakera and has_purple_kakera_button(message.components)
                 has_btn = has_collectible_kakera_button(message.components, all_k)
                 if has_btn:
                    target_ok = True
                    if client.kakera_reaction_snipe_targets and not has_purple_kakera and not is_manual_self_roll:
                        is_target = False
                        if owner_id and str(owner_id) in client.kakera_reaction_snipe_targets:
                            is_target = True
                        if owner_name and owner_name in client.kakera_reaction_snipe_targets:
                            is_target = True
                        if not is_target:
                            target_ok = False
                    if target_ok:
                        client.kakera_reaction_sniped_messages.add(message.id)
                        reaction_delay = 0 if is_manual_self_roll else client.kakera_reaction_snipe_delay_value
                        if reaction_delay > 0 and not await active_delay(reaction_delay): return
                        await claim_character(
                            client,
                            message.channel,
                            message,
                            is_kakera=True,
                            is_snipe=not is_manual_self_roll,
                        )

            # Target validation for character sniping
            is_snipe_target_ok = True
            if client.character_snipe_targets and owner_id != client.user.id:
                is_target = False
                if owner_id is not None and str(owner_id) in client.character_snipe_targets:
                    is_target = True
                if owner_name is not None and owner_name in client.character_snipe_targets:
                    is_target = True
                if not is_target:
                    is_snipe_target_ok = False

            if is_snipe_target_ok:
                if process and client.series_snipe_mode and client.series_wishlist:
                    desc = embed.description or ""
                    series = desc.splitlines()[0].lower() if desc else ""
                    is_avoided = c_name in client.avoid_list
                    already_in_progress = _claim_coordinator.is_reserved(message.id)
                    is_series_wl = await series_wishlist_matches(
                        message,
                        series,
                        known_self_roll=is_manual_self_roll,
                    )
                    if is_series_wl and not is_avoided and has_claim_option(message, embed, client.claim_emojis) and not already_in_progress:
                        is_external_series_roll = not is_manual_self_roll
                        if is_key_mode_kakera_only() or not is_character_snipe_allowed(is_external_snipe=is_external_series_roll): pass
                        else:
                            if not await active_delay(client.series_snipe_delay + random.uniform(0.05, 0.25)): return
                            if await claim_character(client, message.channel, message, is_snipe=is_external_series_roll):
                                 client.series_snipe_happened = True; process = False

                claims_r, likes_r = parse_mudae_ranks(embed.description or "")
                is_ranked = (client.max_claim_rank > 0 and 0 < claims_r <= client.max_claim_rank) or (client.max_like_rank > 0 and 0 < likes_r <= client.max_like_rank)
                is_on_wishlist = c_name in client.wishlist or is_wished_by_self(message, client.user.id) or is_ranked
                is_avoided = c_name in client.avoid_list
                already_in_progress = _claim_coordinator.is_reserved(message.id)
                if process and client.snipe_mode and is_on_wishlist and not is_avoided and has_claim_option(message, embed, client.claim_emojis) and not already_in_progress:
                    if is_key_mode_kakera_only() or not is_character_snipe_allowed(is_external_snipe=True): pass
                    else:
                        if not await active_delay(client.snipe_delay + random.uniform(0.05, 0.25)): return
                        if await claim_character(client, message.channel, message, is_snipe=True):
                            client.snipe_happened = True; process = False

                if process and client.kakera_snipe_mode_active:
                    desc = embed.description or ""
                    k_val = 0
                    m_k = re.search(REGEX_PATTERNS["KAKERA_VALUE"], desc)
                    if m_k: k_val = int(re.sub(r"[^\d]", "", m_k.group(1)))
                    is_avoided = c_name in client.avoid_list
                    already_in_progress = _claim_coordinator.is_reserved(message.id)
                    if k_val >= client.kakera_snipe_threshold and not is_avoided and has_claim_option(message, embed, client.claim_emojis) and not already_in_progress:
                        if is_key_mode_kakera_only() or not is_character_snipe_allowed(is_external_snipe=True): pass
                        else:
                            if not await active_delay(client.snipe_delay + random.uniform(0.05, 0.25)): return
                            if await claim_character(client, message.channel, message, is_snipe=True, kakera_value=k_val):
                                client.snipe_happened = True; process = False

            if process and is_free_event(embed):
                print_log(f"Sniping free event card: {c_name}", preset_name, "CLAIM")
                if await claim_character(client, message.channel, message, is_free_claim=True): process = False

    try:
        client.run(token, reconnect=True)
    except Exception as e:
        if isinstance(e, getattr(discord, "LoginFailure", ())):
            raise
        if "set_wakeup_fd" not in str(e):
            BotLogger.log(f"Crash: {e}\n{traceback.format_exc()}", preset_name, "ERROR")
    finally:
        with _active_clients_lock:
            if client in _active_clients: _active_clients.remove(client)

def bot_lifecycle_wrapper(preset_name, preset_data):
    normalized = {
        "prefix": "/////////////", "mudae_prefix": "$", "roll_command": "wa",
        "min_kakera": 100, "delay_seconds": 0, "claim_interval": 180,
        "roll_interval": 60, "max_dk_power": 100,
    }
    normalized.update(preset_data)
    preset_data = normalized
    validation_errors = validate_preset(preset_data, resolved_token=preset_data.get("token"))
    if validation_errors:
        print_log("Preset validation failed: " + " | ".join(validation_errors), preset_name, "ERROR")
        return
    while True:
        try:
            run_bot(
                preset_data["token"], preset_data["prefix"], preset_data["channel_id"],
                preset_data["roll_command"], preset_data["min_kakera"], preset_data["delay_seconds"],
                preset_data["mudae_prefix"], print_log, preset_name,
                preset_data.get("key_mode", False), preset_data.get("start_delay", 0),
                preset_data.get("snipe_mode", False), preset_data.get("snipe_delay", 2),
                preset_data.get("snipe_ignore_min_kakera_reset", False), preset_data.get("wishlist", []),
                preset_data.get("series_snipe_mode", False), preset_data.get("series_snipe_delay", 3),
                preset_data.get("series_wishlist", []), preset_data.get("roll_speed", 0.4),
                preset_data.get("kakera_snipe_mode", False), preset_data.get("kakera_snipe_threshold", 0),
                preset_data.get("reactive_snipe_on_own_rolls", True), preset_data.get("rolling", True),
                preset_data.get("kakera_reaction_snipe_mode", False), preset_data.get("kakera_reaction_snipe_delay", 0.75),
                preset_data.get("kakera_reaction_snipe_targets", []),
                preset_data.get("character_snipe_targets", []),
                preset_data.get("humanization_enabled", False), preset_data.get("humanization_window_minutes", 40),
                preset_data.get("humanization_inactivity_seconds", 5),
                preset_data.get("dk_power_management", False), preset_data.get("skip_initial_commands", False),
                preset_data.get("use_slash_rolls", False), preset_data.get("only_chaos", False),
                preset_data.get("reactive_snipe_delay", 0), preset_data.get("time_rolls_to_claim_reset", False),
                preset_data.get("rt_ignore_min_kakera_for_wishlist", False),
                preset_data.get("claim_emojis", None), preset_data.get("kakera_emojis", None),
                preset_data.get("chaos_emojis", None), preset_data.get("sphere_perk_emojis", None),
                preset_data.get("rt_only_self_rolls", False), preset_data.get("reactive_kakera_delay_range", [0.3, 1.0]),
                preset_data.get("claim_interval", 180), preset_data.get("roll_interval", 60),
                preset_data.get("avoid_list", []), preset_data.get("inactive_hours", []),
                preset_data.get("auto_us_enabled", False), preset_data.get("auto_us_limit", 0),
                preset_data.get("auto_us_stop_on_claim", True), preset_data.get("kakera_power_thresholds", {}),
                preset_data.get("debug_mode", False), preset_data.get("auto_mk_enabled", True),
                preset_data.get("auto_rolls_enabled", False), preset_data.get("auto_rolls_limit", 0),
                preset_data.get("auto_rolls_in_key_mode", False), preset_data.get("auto_rolls_only_claim_hour", False),
                preset_data.get("panic_roll_minutes", 5), preset_data.get("lurker_mode", False),
                preset_data.get("bulk_us_enabled", False), preset_data.get("max_dk_power", 100),
                preset_data.get("randomized_claim_reactions", None), preset_data.get("main_account_id", ""),
                preset_data.get("scheduled_roll_times", None), preset_data.get("kakera_priority_order", None),
                preset_data.get("auto_rt_after_claim", False), preset_data.get("mk_only", False),
                preset_data.get("auto_dk_enabled", True), preset_data.get("command_channel_id", ""),
                preset_data.get("enable_snipe_chat_reactions", False), preset_data.get("snipe_chat_messages", None),
                preset_data.get("farm_character", ""), preset_data.get("op_perk_5_only", False),
                preset_data.get("farm_character_enabled", False), preset_data.get("auto_divorce_enabled", False),
                preset_data.get("auto_divorce_max_kakera", 50), preset_data.get("auto_divorce_series", []),
                preset_data.get("auto_divorce_blacklist", []), preset_data.get("auto_divorce_blacklist_series", []),
                preset_data.get("mk_bypass_power_check", False), preset_data.get("snipe_channels", []),
                preset_data.get("max_claim_rank", 0), preset_data.get("max_like_rank", 0),
                preset_data.get("auto_p_enabled", True),
                preset_data.get("enable_hybrid_panic_claim", False),
                preset_data.get("hybrid_panic_instant_claim_min_kakera", 300),
                preset_data.get("hybrid_panic_instant_claim_max_rank", 200),
                preset_data.get("claim_rounds_thresholds", None),
                preset_data.get("persistent_stagger_seconds", 0),
                preset_data.get("sphere_click_targets", None),
                preset_data.get("immediate_kakera_click", True),
                preset_data.get("farm_forcedivorce_after_claim", False),
                preset_data.get(
                    "farm_forcedivorce_before_roll",
                    bool(preset_data.get("farm_character_enabled", False))
                    and not preset_data.get("farm_forcedivorce_after_claim", False)
                    and not preset_data.get("farm_forcedivorce_after_other_claim", False),
                ),
                preset_data.get("farm_forcedivorce_after_other_claim", False),
                preset_data.get("auto_oh_enabled", False),
                preset_data.get("auto_oc_enabled", False),
                preset_data.get("series_snipe_only_self_rolls", False),
                preset_data.get("forcedivorce_channel_id", ""),
                preset_data.get("wish_starwish_kakera_only", False),
                preset_data.get("auto_mk_full_power_only", False),
                preset_data.get("auto_divorce_protect_wishes", True),
                preset_data.get("farm_characters", []),
                preset_data.get("enable_kakera_snipe_chat_reactions", False),
                preset_data.get("kakera_snipe_chat_messages", None),
                preset_data.get("oh_priority_order", None),
                preset_data.get("oh_unknown_explore_clicks", 3),
                preset_data.get("oc_reward_priority_order", None),
                preset_data.get("oc_collect_after_red", True),
                preset_data.get("webhook_url", ""),
                preset_data.get("webhook_log_types", None),
                preset_data.get("debug_log_categories", None),
                preset_data.get("auto_free_claim", True),
                preset_data.get("collect_purple_kakera", True),
                preset_data.get("oh_use_individually", False),
                preset_data.get("auto_dk_min_power", 0),
                preset_data.get("kakera_snipe_channels", None),
            )
        except Exception as e:
            if isinstance(e, getattr(discord, "LoginFailure", ())):
                print_log(
                    "Discord rejected this token (401 Unauthorized). Re-enter the current token in the preset, save it, then restart. Automatic restart has been stopped.",
                    preset_name,
                    "ERROR",
                )
                return
            print_log(f"Instance crashed: {e}\n{traceback.format_exc()}", preset_name, "ERROR")
        time.sleep(60)

def start_preset_thread(preset_name, preset_data):
    if not preset_data.get("token"):
        print_log("Preset has no token. Save it in the editor or set the preset token environment variable.", preset_name, "ERROR")
        return None
    t = threading.Thread(target=bot_lifecycle_wrapper, args=(preset_name, preset_data), daemon=True)
    t.start()
    return t


def start_active_preset_threads(preset_names, start_index=0):
    """Start only selected runnable presets with compact active-order stagger offsets."""
    started = []
    for preset_name, preset_data in prepare_active_presets(
        preset_names,
        presets,
        start_index=start_index,
    ):
        thread = start_preset_thread(preset_name, preset_data)
        if thread:
            started.append(thread)
    return started

class StdinEnterMapper:
    def __init__(self, original_stdin):
        self.original_stdin = original_stdin
    def read(self, n=1):
        char = self.original_stdin.read(n)
        return '\r' if char == '\n' else char
    def readline(self, *args, **kwargs):
        return self.original_stdin.readline(*args, **kwargs).replace('\n', '\r')
    def __getattr__(self, name):
        return getattr(self.original_stdin, name)

def main_menu():
    import inquirer
    banner = r"""
  __  __ _    _ _____          _____  ______ __  __  ____ _______ ______
 |  \/  | |  | |  __ \   /\   |  __ \|  ____|  \/  |/ __ \__   __|  ____|
 | \  / | |  | | |  | | /  \  | |__) | |__  | \  / | |  | | | |  | |__
 | |\/| | |  | | |  | |/ /\ \ |  _  /|  __| | |\/| | |  | | | |  |  __|
 | |  | | |__| | |__| / ____ \| | \ \| |____| |  | | |__| | | |  | |____
 |_|  |_|\____/|_____/_/    \_\_|  \_\______|_|  |_|\____/  |_|  |______|
"""
    print("\033[1;36m" + banner + "\033[0m\n")
    _menu_active.set()
    if os.name != 'nt' and not IS_TERMUX:
        import termios
        global _original_terminal_settings
        if _original_terminal_settings is not None:
            try:
                termios.tcflush(sys.stdin.fileno(), termios.TCIFLUSH)
                termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, _original_terminal_settings)
            except Exception: pass

    original_stdin = sys.stdin
    if os.name != 'nt' and not IS_TERMUX: sys.stdin = StdinEnterMapper(sys.stdin)

    def safe_prompt(q):
        ans = inquirer.prompt(q)
        if os.name != 'nt' and not IS_TERMUX:
            try:
                import termios
                termios.tcflush(sys.stdin.fileno(), termios.TCIFLUSH)
            except Exception: pass
        return ans

    threads = []
    try:
        while True:
            opts = ['Select and Run Preset', 'Select and Run Multiple', 'Exit']
            q = [inquirer.List('opt', message="Select Option", choices=opts)]
            ans = safe_prompt(q)
            if not ans or ans['opt'] == 'Exit': break

            if ans['opt'] == 'Select and Run Preset':
                p_ans = safe_prompt([inquirer.List('p', message="Preset", choices=list(presets.keys()))])
                if p_ans:
                    threads = [thread for thread in threads if thread and thread.is_alive()]
                    threads.extend(start_active_preset_threads([p_ans['p']], start_index=len(threads)))
            elif ans['opt'] == 'Select and Run Multiple':
                p_ans = safe_prompt([inquirer.Checkbox('p', message="Presets", choices=list(presets.keys()))])
                if p_ans:
                    threads = [thread for thread in threads if thread and thread.is_alive()]
                    threads.extend(start_active_preset_threads(p_ans['p'], start_index=len(threads)))
    finally:
        sys.stdin = original_stdin
        _menu_active.clear()
    if threads:
        print(f"\033[1;32m[{BOT_NAME}] Press 'p' at any time to pause/resume all bots.\033[0m")

def shutdown_mobile_runtime():
    """Authoritatively close all active Discord clients for the Android foreground service."""
    with _active_clients_lock:
        clients = list(_active_clients)
    for client in clients:
        loop = getattr(client, "loop", None)
        if loop and loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(client.close(), loop)
            except Exception:
                pass

def reset_mobile_runtime():
    """Reset active mobile runtime state before starting a new run."""
    with _active_clients_lock:
        _active_clients.clear()

def parse_args(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="Mudae Bot Helper")
    parser.add_argument("--preset", type=str, help="Name of the preset to run")
    parser.add_argument("--all", action="store_true", help="Run all presets")
    parser.add_argument("--stagger-index", type=int, default=0, help="Active preset position for automated staggering")
    return parser.parse_args(argv)

def run_cli(argv=None):
    cleanup_after_update()
    check_for_updates()
    args = parse_args(argv)
    if args.preset:
        if args.preset in presets:
            prepared = prepare_active_presets([args.preset], presets, start_index=args.stagger_index)
            if prepared:
                if len(prepared) == 1:
                    bot_lifecycle_wrapper(*prepared[0])
                else:
                    launched = [
                        start_preset_thread(preset_name, preset_data)
                        for preset_name, preset_data in prepared
                    ]
                    for thread in launched:
                        if thread:
                            thread.join()
            else:
                print(f"Preset '{args.preset}' has no token.")
        else:
            print(f"Preset '{args.preset}' not found.")
    elif args.all:
        started = start_active_preset_threads(list(presets.keys()), start_index=args.stagger_index)
        for t in started:
            if t: t.join()
    else:
        main_menu()
        try:
            while True: time.sleep(1)
        except KeyboardInterrupt:
            print("\n[MudaRemote] Shutting down...")

if __name__ == "__main__":
    run_cli()
