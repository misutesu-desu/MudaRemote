# PROJECT RUNTIME CODE CONTEXT

This document contains the complete, unabridged, verbatim runtime source code and configuration files required to run MudaRemote.

## File: `mudae_bot.py`

```python
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
    entries = [
        entry for entry in manifest_response.json().get("source_files", [])
        if str(entry.get("path", "")).replace("\\", "/").startswith("mudae_core/")
    ]
    required = {
        "mudae_core/__init__.py", "mudae_core/claiming.py", "mudae_core/config.py",
        "mudae_core/coordinator.py", "mudae_core/runtime.py", "mudae_core/secrets.py",
        "mudae_core/status.py", "mudae_core/kakera.py", "mudae_core/spheres.py",
        "mudae_core/updater.py", "mudae_core/versioning.py",
    }
    if not required.issubset({entry.get("path") for entry in entries}):
        raise RuntimeError("The modular core manifest is incomplete.")

    stage_dir = tempfile.mkdtemp(prefix="mudae-bootstrap-", dir=base_path)
    try:
        for entry in entries:
            relative_path = os.path.normpath(str(entry["path"]).replace("/", os.sep))
            if not relative_path.startswith("mudae_core" + os.sep) or os.pardir in relative_path.split(os.sep):
                raise RuntimeError("Unsafe modular core path in update manifest.")
            content_response = requests.get(entry["url"], timeout=30)
            content_response.raise_for_status()
            content = content_response.content
            if hashlib.sha256(content).hexdigest().lower() != str(entry.get("sha256", "")).lower():
                raise RuntimeError("Core checksum verification failed for {}.".format(relative_path))
            staged_path = os.path.join(stage_dir, relative_path)
            os.makedirs(os.path.dirname(staged_path), exist_ok=True)
            with open(staged_path, "wb") as handle:
                handle.write(content)
        for entry in entries:
            relative_path = os.path.normpath(str(entry["path"]).replace("/", os.sep))
            destination = os.path.join(base_path, relative_path)
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            os.replace(os.path.join(stage_dir, relative_path), destination)
    finally:
        shutil.rmtree(stage_dir, ignore_errors=True)


try:
    from mudae_core import (
        ClaimCoordinator, ClaimOutcome, CommandPacer, SecretStore, UpdateError, apply_update,
        active_stagger_seconds, calculate_kakera_power_cost, classify_claim_owner, classify_claim_text, clear_status_dirty,
        consume_tu_urgent_bypass,
        cooldown_deadline, defer_tu_queries, harvest_reveal_is_free, has_free_claim_button, initialize_status_tracking,
        is_claim_announcement_for_character,
        looks_like_tu_status_snapshot,
        mark_status_dirty, pause_interruptible_sleep, prepare_active_presets, record_tu_failure,
        record_tu_success, set_client_paused, status_dirty_fields,
        status_refresh_reasons, tu_retry_wait, has_perk_eight_discount,
        choose_chest_position, choose_harvest_position, normalize_sphere_emoji, parse_sphere_game_status,
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
        ClaimCoordinator, ClaimOutcome, CommandPacer, SecretStore, UpdateError, apply_update,
        active_stagger_seconds, calculate_kakera_power_cost, classify_claim_owner, classify_claim_text, clear_status_dirty,
        consume_tu_urgent_bypass,
        cooldown_deadline, defer_tu_queries, harvest_reveal_is_free, has_free_claim_button, initialize_status_tracking,
        is_claim_announcement_for_character,
        looks_like_tu_status_snapshot,
        mark_status_dirty, pause_interruptible_sleep, prepare_active_presets, record_tu_failure,
        record_tu_success, set_client_paused, status_dirty_fields,
        status_refresh_reasons, tu_retry_wait, has_perk_eight_discount,
        choose_chest_position, choose_harvest_position, normalize_sphere_emoji, parse_sphere_game_status,
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
CURRENT_VERSION = "4.6.8"

IS_TERMUX = "TERMUX_VERSION" in os.environ or ("PREFIX" in os.environ and "com.termux" in os.environ["PREFIX"])

# Global Pause State
_global_paused = False
_active_clients = []
_active_clients_lock = threading.Lock()
_menu_active = threading.Event()
_original_terminal_settings = None

_claim_coordinator = ClaimCoordinator()

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

    @classmethod
    def log(cls, message, preset_name="MudaRemote", log_type="INFO", client=None):
        if log_type == "DEBUG" and not getattr(client, 'debug_mode', False):
            return
        log_type_upper = log_type.upper()
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

def check_for_updates():
    if not UPDATE_URL: return
    is_frozen = getattr(sys, 'frozen', False)
    print_system_log(f"Checking for updates... (Current: v{CURRENT_VERSION}, Mode: {'EXE' if is_frozen else 'Script'})", "RESET")
    try:
        response = requests.get(f"{UPDATE_URL}version.json", timeout=(3.05, 8.0))
        response.raise_for_status()
        data = response.json()
        latest_version = data.get("version")
        result = apply_update(
            requests,
            data,
            CURRENT_VERSION,
            get_base_path(),
            frozen=is_frozen,
            executable=sys.executable,
        )
        if result == "current":
            print_system_log("You are up to date.", "INFO")
            return
        if result == "git":
            print_system_log(f"v{latest_version} is available. This is a Git checkout; run 'git pull' so local changes are never overwritten.", "WARN")
            return
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
    except Exception as e:
        print_system_log(f"Update failed: {e}", "ERROR")

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
        _preset_data["token"] = _secret_store.get_token(_preset_name, _preset_data.get("token", ""))
except Exception as e:
    print_system_log(f"Failed to load {presets_path}: {e}", "ERROR")
    sys.exit(1)

if os.name == 'nt': os.system('')

TARGET_BOT_ID = 432610292342587392
CLAIM_EMOJIS = ['💖', '💗', '💘', '❤️', '💓', '💕', '♥️']
KAKERA_EMOJIS = ['kakeraY', 'kakeraO', 'kakeraR', 'kakeraW', 'kakeraL', 'kakeraP', 'kakeraD', 'kakeraC', 'kakera']
CHAOS_KAKERA_EMOJIS = ['kakeraY', 'kakeraO', 'kakeraR', 'kakeraW', 'kakeraL', 'kakeraP', 'kakeraD', 'kakeraC', 'kakera']
SPHERE_EMOJIS = ['spP', 'spB', 'spT', 'spG', 'spY', 'spO', 'spR', 'spW', 'spL', 'spD', 'spM', 'spP2', 'spB2', 'spT2', 'spG2', 'spY2', 'spO2', 'spR2', 'spW2', 'spL2', 'spD2', 'spU']

async def detect_roll_owner(client, message) -> tuple:
    """
    Detects the owner of a roll message.
    Returns a tuple of (user_id, username_lowercase).
    """
    # 1. If it was rolled via a Slash Command (Interaction)
    if hasattr(message, 'interaction') and message.interaction:
        user = message.interaction.user
        return user.id, user.name.lower()

    # 2. Fallback for text commands: scan channel history right before this message
    # We look for: $w, $h, $m, $wx, $mx, $hx, $wa, $ha, $ma, $mg, $hg, $wg
    valid_commands = ["w", "h", "m", "wx", "mx", "hx", "wa", "ha", "ma", "mg", "hg", "wg"]
    roll_prefixes = [f"{client.mudae_prefix}{cmd}" for cmd in valid_commands]

    try:
        async for msg in message.channel.history(limit=5, before=message):
            content = (msg.content or "").strip().lower()
            if content and any(content.startswith(p) for p in roll_prefixes):
                return msg.author.id, msg.author.name.lower()
    except Exception:
        pass

    # 3. Last fallback: Check embed footer for Mudae ownership text if present
    owner_username = None
    if message.embeds:
        embed = message.embeds[0]
        if embed.footer and embed.footer.text:
            m = re.search(REGEX_PATTERNS["OWNER"], embed.footer.text)
            if m:
                owner_username = m.group(1).strip().lower()

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
    return any(hasattr(btn.emoji, 'name') and btn.emoji and btn.emoji.name in claim_emojis for comp in message.components for btn in comp.children)

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
            auto_oc_enabled_preset=False):

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
    client.series_snipe_delay = series_snipe_delay
    client.series_wishlist = set([sw.lower() for sw in series_wishlist])
    client.avoid_list = set([a.lower() for a in (avoid_list or [])])

    client.snipe_channels = set()
    if snipe_channels_preset:
        for ch in snipe_channels_preset:
            try: client.snipe_channels.add(int(ch))
            except ValueError: pass

    client.max_claim_rank = int(max_claim_rank_preset or 0)
    client.max_like_rank = int(max_like_rank_preset or 0)
    client.muda_name = BOT_NAME
    client.claim_right_available = False
    client.target_channel_id = target_channel_id
    client.command_channel_id_preset = str(command_channel_id_preset or "").strip()
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
    client.current_min_kakera_for_roll_claim = client.min_kakera
    client.kakera_snipe_mode_active = kakera_snipe_mode_preset
    client.kakera_snipe_threshold = kakera_snipe_threshold_preset
    client.enable_reactive_self_snipe = enable_reactive_self_snipe_preset
    client.reactive_snipe_delay = reactive_snipe_delay
    client.rolling_enabled = rolling_enabled
    client.rt_available = False
    client.kakera_reaction_snipe_mode_active = kakera_reaction_snipe_mode_preset
    client.kakera_reaction_snipe_delay_value = kakera_reaction_snipe_delay_preset
    client.kakera_reaction_snipe_targets = set([t.lower() for t in kakera_reaction_snipe_targets])
    client.character_snipe_targets = set([t.lower().strip() for t in (character_snipe_targets or []) if t.strip()])
    client.kakera_reaction_sniped_messages = set()
    client.kakera_react_available = True
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
    sphere_click_targets = sphere_click_targets_preset or ["spG", "spY", "spO", "spR", "spW", "spL", "spD", "spM", "spU"]
    client.sphere_click_targets = set([t.lower() for t in sphere_click_targets])
    client.immediate_kakera_click = immediate_kakera_click_preset
    client.auto_oh_enabled = bool(auto_oh_enabled_preset)
    client.auto_oc_enabled = bool(auto_oc_enabled_preset)
    client.sphere_game_counts = {"oh": 0, "oc": 0, "oq": 0, "ot": 0}
    client.sphere_game_refill_at_utc = None
    # run_bot is entered from a worker thread before discord.py creates that
    # thread's event loop. Bind the lock lazily from the first async game task.
    client._sphere_game_lock = None
    client._sphere_game_response_future = None
    client._sphere_game_response_channel_id = None
    client._sphere_game_response_kind = None
    client._sphere_game_retry_after = {"oh": 0.0, "oc": 0.0}
    client._sphere_board_update_events = {}
    client.collected_kakera_rolls = []

    client.enable_snipe_chat_reactions = enable_snipe_chat_reactions_preset
    client.snipe_chat_messages = snipe_chat_messages_preset or ["omg", "ezz"]
    client.farm_character = str(farm_character_preset or "").strip().lower()
    client.farm_character_enabled = farm_character_enabled_preset
    client.farm_forcedivorce_after_claim = bool(farm_forcedivorce_after_claim_preset)
    client.farm_forcedivorce_before_roll = bool(farm_forcedivorce_before_roll_preset)
    client.farm_forcedivorce_after_other_claim = bool(farm_forcedivorce_after_other_claim_preset)
    client._farm_release_recent = {}
    client.op_perk_5_only = op_perk_5_only_preset

    client.next_claim_reset_at_utc = None
    client.roll_reset_at_utc = None
    client.claim_cooldown_until_utc = None
    client.is_claiming = False
    client.snipe_watch = {}
    client.snipe_watch_expiry_seconds = 180
    client.snipe_globally_disabled_until = None

    client.current_dk_power = 100
    client.dk_consumption = 35
    client.kakera_reacted_messages = set()
    client.processed_claim_messages = set()
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
    client.rt_ignore_min_kakera_for_wishlist = rt_ignore_min_kakera_for_wishlist_preset

    client.last_tu_query_utc = None
    initialize_status_tracking(client)
    client._tu_response_future = None
    client._tu_response_channel_id = None
    client._tu_request_started_at = None
    client._local_extra_rolls_pending = 0
    client.rolls_left = 0
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
    client.chaos_emojis = chaos_emojis_preset if chaos_emojis_preset is not None else CHAOS_KAKERA_EMOJIS
    client.sphere_perk_emojis = sphere_perk_emojis_preset if sphere_perk_emojis_preset is not None else KAKERA_EMOJIS
    client.sphere_emojis = SPHERE_EMOJIS
    client.kakera_power_thresholds = kakera_power_thresholds or {}
    client.debug_mode = debug_mode
    client.persistent_stagger_seconds = max(0.0, float(persistent_stagger_seconds_preset or 0.0))
    account_index = int(client.persistent_stagger_seconds // active_stagger_seconds(1))

    BotLogger.log(
        f"Automated Staggering: Assigned active index {account_index} (Preset: '{preset_name}') -> "
        f"+{client.persistent_stagger_seconds}s persistent sleep offset applied.",
        preset_name, "INFO"
    )

    def is_inactive_hour() -> bool:
        if not client.inactive_hours: return False
        h = datetime.datetime.now().hour
        for start_h, end_h in client.inactive_hours:
            if start_h <= end_h:
                if start_h <= h < end_h: return True
            else:
                if h >= start_h or h < end_h: return True
        return False

    def seconds_until_active() -> float:
        if not is_inactive_hour(): return 0
        now = datetime.datetime.now()
        best = float('inf')
        for start_h, end_h in client.inactive_hours:
            in_this = (start_h <= now.hour < end_h) if start_h <= end_h else (now.hour >= start_h or now.hour < end_h)
            if in_this:
                wake = now.replace(hour=end_h, minute=0, second=0, microsecond=0)
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

    def claim_identities():
        user = getattr(client, 'user', None)
        if user is None:
            return []
        return [getattr(user, 'name', ''), getattr(user, 'display_name', '')]

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
        kind = sphere_game_kind(message)
        if kind != getattr(client, '_sphere_game_response_kind', None):
            return False
        if not sphere_game_belongs_to_self(message):
            return False
        if len(sphere_game_buttons(message)) != 25:
            return False
        future.set_result(message)
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
        user = getattr(client, 'user', None)
        identity_values = [getattr(user, 'name', '').lower(), getattr(user, 'display_name', '').lower()]
        user_id = getattr(user, 'id', None)
        addressed_to_self = any(identity and identity in c_low for identity in identity_values)
        if user_id is not None and (f"<@{user_id}>" in message.content or f"<@!{user_id}>" in message.content):
            addressed_to_self = True
        if not addressed_to_self:
            return False
        match = re.search(REGEX_PATTERNS["CLAIM_COOLDOWN"], c_low, re.IGNORECASE)
        if not match:
            match = re.search(REGEX_PATTERNS["CLAIM_INTERVAL_COOLDOWN"], c_low, re.IGNORECASE)
        if not match:
            return False
        hours, minutes = parse_hm(match)
        cooldown_minutes = hours * 60 + minutes
        BotLogger.log(f"Detected claim cooldown message from Mudae: {cooldown_minutes}m left. Locking claim.", preset_name, "WARN")
        set_claim_cooldown(cooldown_minutes, source="Mudae message", wake=False)
        request_status_refresh({"claim", "rt"}, reason="claim-rejected-cooldown", urgent=True)
        wake_status_loop()
        pending = getattr(client, 'pending_claim', None)
        if pending and pending.get("consumes_claim"):
            # This is explicit rejection evidence, not proof that the click
            # consumed a claim. Keep the roll pending until $tu confirms
            # whether it can be retried with a claim right or $rt.
            pending["rejected_by_cooldown"] = True
            event = getattr(client, '_claim_evidence_event', None)
            if event is not None:
                event.set()
        return True

    async def paced_mudae_action(action):
        return await client.command_pacer.run(
            action,
            lambda seconds: pause_interruptible_sleep(client, seconds, abort_on_pause=True),
            lambda: not client.is_paused and not is_maintenance_active(),
        )

    async def guarded_send(channel, content):
        return await paced_mudae_action(lambda: channel.send(content))

    async def guarded_click(target):
        if client.is_paused or is_maintenance_active():
            return False
        await target.click()
        return True

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
        while paid_clicks < 5 and total_clicks < 25:
            buttons, emojis, disabled, snapshot = sphere_board_snapshot(current)
            if len(buttons) != 25:
                BotLogger.log(f"{game_label}: Expected 25 sphere buttons but received {len(buttons)}.", preset_name, "WARN")
                return False
            if all(disabled):
                break

            if kind == "oc":
                position = choose_chest_position(emojis, disabled)
            else:
                position = choose_harvest_position(emojis, disabled, paid_clicks=paid_clicks)
            if position is None or position < 0 or position >= len(buttons):
                BotLogger.log(f"{game_label}: No safe enabled sphere button remains.", preset_name, "WARN")
                break

            if not await active_delay(random.uniform(0.45, 0.85)):
                return False
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
            BotLogger.log(
                f"{game_label}: Click {total_clicks} ({paid_clicks}/5 used) at row {position // 5 + 1}, column {position % 5 + 1}"
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
                        and sphere_game_kind(candidate) == kind
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
            completed = await run_sphere_game(channel, kind, available)
            if completed:
                client.sphere_game_counts[kind] = 0
                refill_seconds = max(300.0, float(status.refill_minutes or 60) * 60.0)
                client._sphere_game_retry_after[kind] = time.monotonic() + refill_seconds
            else:
                client._sphere_game_retry_after[kind] = time.monotonic() + 300.0
                client.loop.call_later(302.0, wake_status_loop)

    def is_character_snipe_allowed(is_external_snipe: bool = False) -> bool:
        if client.next_claim_reset_at_utc:
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            if not client.claim_right_available and now_utc >= client.next_claim_reset_at_utc:
                request_status_refresh({"claim"}, reason="predicted-claim-reset", urgent=True)
                if not client._claim_reset_refresh_requested:
                    client._claim_reset_refresh_requested = True
                    BotLogger.log("Predicted claim reset reached. Verifying with $tu before claiming.", preset_name, "CHECK")

        rt_usable = client.rt_available and not (is_external_snipe and client.rt_only_self_rolls)
        return client.claim_right_available or rt_usable or client.key_mode

    def is_key_mode_kakera_only() -> bool:
        return client.key_mode and not client.claim_right_available and not client.rt_available

    def is_kakera_reaction_allowed() -> bool:
        now = datetime.datetime.now(datetime.timezone.utc)
        if client.kakera_react_available: return True
        if client.kakera_react_cooldown_until_utc and now >= client.kakera_react_cooldown_until_utc:
            client.kakera_react_available = True
            client.kakera_react_cooldown_until_utc = None
            return True
        return False

    def get_current_dk_power() -> float:
        p = client.current_dk_power
        if not hasattr(client, 'last_dk_power_update_utc'): return p
        now = datetime.datetime.now(datetime.timezone.utc)
        el = int((now - client.last_dk_power_update_utc).total_seconds() / 180)
        if el > 0:
            p = min(client.max_dk_power, p + el)
            client.current_dk_power = p
            client.last_dk_power_update_utc += datetime.timedelta(minutes=3 * el)
        return p

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
            if not await paced_mudae_action(
                lambda: client.http.request(Route("POST", "/interactions"), json=payload)
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

    async def send_tu_command(channel):
        if client.is_paused or is_maintenance_active(): return False
        if client.use_slash_rolls and not client.slash_fallback_active:
            for attempt in range(1, 4):
                if await _trigger_mudae_slash(channel, "tu"): return True
                if client.slash_fallback_active: break
                if attempt < 3 and not await active_delay(5.0): return False
            if not client.slash_fallback_active:
                client.slash_fallback_active = True
                BotLogger.log("/tu failed after 3 attempts. Switching to text $tu so status tracking can continue.", preset_name, "WARN")
        return await guarded_send(channel, f"{client.mudae_prefix}tu")

    def _get_command_channel():
        try:
            if client.command_channel_id_preset:
                c = client.get_channel(int(client.command_channel_id_preset))
                if c: return c
        except Exception: pass
        return getattr(client, '_main_channel', None)

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

            if cur_power < cost:
                BotLogger.log(f"DK: Activating. ({cur_power}% < {cost}%)", preset_name, "KAKERA")
                if not await guarded_send(channel, f"{client.mudae_prefix}dk"):
                    return
                if not await active_delay(1.5 + random.uniform(0.1, 0.4)):
                    return
                client.dk_stock_count = max(0, client.dk_stock_count - 1)
                client.current_dk_power = client.max_dk_power
                client.last_dk_power_update_utc = datetime.datetime.now(datetime.timezone.utc)
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
                if client.next_claim_reset_at_utc:
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
            if not client.claim_right_available:
                if client.next_claim_reset_at_utc and client.next_claim_reset_at_utc > now:
                    wait_s = max(5.0, (client.next_claim_reset_at_utc - now).total_seconds() + 2.0)
                    BotLogger.log(f"Snipe-only: Silent. Sleeping {wait_s/60:.1f}m.", preset_name, "RESET")
                    try: await _interruptible_sleep(wait_s)
                    except asyncio.CancelledError: break
                    if datetime.datetime.now(datetime.timezone.utc) >= client.next_claim_reset_at_utc:
                        client._claim_reset_refresh_requested = True
                        request_status_refresh({"claim"}, reason="snipe-claim-reset", urgent=True)
                        await check_status(client, channel, client.mudae_prefix, proceed_to_rolls=False)
                else:
                    await _interruptible_sleep(10)
            else:
                await _interruptible_sleep(10)

    async def _interruptible_sleep(seconds):
        evt = client._immediate_check_event
        if evt:
            evt.clear()
            try: await asyncio.wait_for(evt.wait(), timeout=seconds)
            except asyncio.TimeoutError: pass
        else:
            await pause_interruptible_sleep(client, seconds)

    async def check_status(client, channel, mudae_prefix, proceed_to_rolls: bool = True, current_cycle_id=None):
        if client.is_paused or is_maintenance_active(): return
        if getattr(client, 'is_claiming', False): return
        if getattr(client, 'is_processing_cycle', False): return
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
            if client.last_tu_query_utc is not None and not status_dirty_fields(client) and not client.scheduled_roll_due:
                elapsed = (now_utc - client.last_tu_query_utc).total_seconds()
                if elapsed < 1800:
                    is_before_claim = client.next_claim_reset_at_utc is None or now_utc < client.next_claim_reset_at_utc
                    is_before_roll = client.roll_reset_at_utc is None or now_utc < client.roll_reset_at_utc
                    if is_before_claim and is_before_roll and client.rolls_left <= 0:
                        can_bypass = True
                        if client.rolling_enabled:
                            pending_rolls = pending_us = pending_mk = False
                            if client.auto_rolls_enabled:
                                lim_ok = client.auto_rolls_limit == 0 or client.rolls_item_used_count < client.auto_rolls_limit
                                reset_utc = getattr(client, 'roll_reset_at_utc', None)
                                used_utc = getattr(client, 'rolls_used_this_interval_utc', None)
                                if used_utc and reset_utc and used_utc != reset_utc: used_utc = None
                                claim_ok = client.claim_right_available or (client.key_mode and client.auto_rolls_in_key_mode)
                                if lim_ok and used_utc is None and claim_ok:
                                    ch_hour = True
                                    if client.auto_rolls_only_claim_hour:
                                        ch_hour = bool(client.next_claim_reset_at_utc and reset_utc and client.next_claim_reset_at_utc <= reset_utc)
                                    if ch_hour: pending_rolls = True
                            if client.auto_us_enabled:
                                stop_c = client.auto_us_stop_on_claim and not client.claim_right_available
                                limit = client.auto_us_limit > 0 and client.us_pulled_this_cycle >= client.auto_us_limit
                                if not stop_c and not limit and not getattr(client, 'us_failed_this_cycle', False):
                                    pending_us = True
                            if client.auto_mk_enabled and client.mk_rolls_left > 0:
                                if get_current_dk_power() >= client.dk_consumption or client.mk_bypass_power_check:
                                    pending_mk = True
                            if pending_rolls or pending_us or pending_mk: can_bypass = False
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
                    if wait_time > 0: choices.append((float(wait_time), "claim cooldown"))
                    if client.time_rolls_to_claim_reset and not client.claim_right_available and claim_reset_m > 60: choices.append((float(claim_reset_m - 60), "timing threshold arrival"))
                    if roll_reset_m > 0: choices.append((float(roll_reset_m), "rolls replenishment"))
                    if choices:
                        choices.sort(key=lambda x: x[0])
                        await humanized_wait_and_proceed(client, channel, max(0.05, choices[0][0]), choices[0][1])
                    else:
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
                    BotLogger.log(f"Deferring $tu for {retry_wait:.0f}s after an unanswered query ({dirty}).", preset_name, "INFO")
                    client._tu_last_defer_log_monotonic = now_mono
                return

            if client.delay_seconds > 0:
                await _interruptible_sleep(client.delay_seconds)
            reasons = status_refresh_reasons(client)
            reason_text = ", ".join(reasons) if reasons else ("scheduled-roll" if client.scheduled_roll_due else "status-boundary")
            BotLogger.log(f"Checking $tu... (reason: {reason_text})", preset_name, "CHECK")
            tu_content = None
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
            if not (re.search(REGEX_PATTERNS["CLAIM_READY"], c_lower) or
                    re.search(REGEX_PATTERNS["CLAIM_RESET"], c_lower) or
                    re.search(REGEX_PATTERNS["CLAIM_COOLDOWN"], c_lower)):
                BotLogger.log("Your $tu response is missing the 'claim' category. Run '$tuarrange' in Discord to include it.", preset_name, "WARN")

            if not re.search(REGEX_PATTERNS["ROLLS_COUNT"], c_lower, re.DOTALL):
                BotLogger.log("Your $tu response is missing the 'rolls' or 'rollsreset' category. Run '$tuarrange' in Discord to include it.", preset_name, "WARN")

            v_rt_ready = any(x in c_lower for x in ["$rt is available", "$rt está pronto", "$rt esta pronto", "$rt está disponível", "$rt está disponible", "$rt est disponible", "$rt est prêt", "$rt is ready"])
            v_rt_reset = parse_timer_minutes("RT_RESET", c_lower)
            if not (v_rt_ready or v_rt_reset is not None or "$rt" in c_lower or re.search(r'\brt\b', c_lower)):
                BotLogger.log("Your $tu response is missing the 'rt' category. Run '$tuarrange' in Discord to include it.", preset_name, "WARN")

            if not (re.search(REGEX_PATTERNS["DK_POWER"], c_lower) or
                    re.search(REGEX_PATTERNS["DK_CONSUMPTION"], c_lower)):
                BotLogger.log("Your $tu response is missing the 'kakerapower' or 'kakerainfo' category. Run '$tuarrange' in Discord to include it.", preset_name, "WARN")

            if not (re.search(REGEX_PATTERNS["DK_STOCK"], c_lower) or
                    re.search(REGEX_PATTERNS["DK_READY"], c_lower) or
                    re.search(REGEX_PATTERNS["DK_COOLDOWN"], c_lower)):
                BotLogger.log("Your $tu response is missing the 'dk' category. Run '$tuarrange' in Discord to include it.", preset_name, "WARN")

            try:
                power_match = re.search(REGEX_PATTERNS["DK_POWER"], c_lower)
                if power_match:
                    client.current_dk_power = int(power_match.group(1))
                    client.last_dk_power_update_utc = datetime.datetime.now(timezone.utc)
                consumption_match = re.search(REGEX_PATTERNS["DK_CONSUMPTION"], c_lower)
                if consumption_match:
                    client.dk_consumption = int(consumption_match.group(1))
                dk_stock_match = re.search(REGEX_PATTERNS["DK_STOCK"], c_lower)
                if dk_stock_match: client.dk_stock_count = int(dk_stock_match.group(1))
                elif re.search(REGEX_PATTERNS["DK_READY"], c_lower): client.dk_stock_count = 1
                else: client.dk_stock_count = 0
            except Exception as e:
                BotLogger.log(f"Error parsing Power/DK state: {e}", preset_name, "WARN")

            if client.auto_dk_enabled and client.dk_power_management and client.rolling_enabled:
                await handle_dk_power_management(client, cmd_channel, tu_content)

            if client.rolling_enabled:
                if any(x in c_lower for x in ["$daily is available", "$daily está disponível", "$daily está disponible", "$daily est disponible"]):
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
                        p_ready = any(x in c_lower for x in ["$p is available", "$p está disponível", "$p está disponible", "$p est disponible"])
                        p_cooldown_mins = parse_timer_minutes("P_COOLDOWN", c_lower)
                        if p_cooldown_mins is not None:
                            client.p_available = False
                            client.next_p_claim_at_utc = (now_utc + datetime.timedelta(minutes=p_cooldown_mins)).replace(second=0, microsecond=0)
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
                BotLogger.log(f"RT: Cooldown ({int(rt_reset_minutes/60)}h {rt_reset_minutes%60}m)", preset_name, "INFO")
            elif rt_ready:
                client.rt_available = True
                BotLogger.log("RT: Ready", preset_name, "INFO")
            else:
                client.rt_available = False
            wait_time = 0
            can_claim = False
            claim_ready = bool(re.search(REGEX_PATTERNS["CLAIM_READY"], c_lower))

            claim_reset_minutes = None
            m_reset = re.search(REGEX_PATTERNS["CLAIM_RESET"], c_lower)
            if m_reset and not any(kw in m_reset.group(0) for kw in ["$daily", "$dk", "$rt"]):
                h_c, m_c = parse_hm(m_reset)
                claim_reset_minutes = h_c * 60 + m_c
            else:
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
                client.last_tu_query_utc = datetime.datetime.now(timezone.utc)
                clear_status_dirty(client)
                mark_status_dirty(client, {"claim"}, reason="pending-claim-unresolved", urgent=True)
                defer_tu_queries(client, 45.0)
                return

            roll_reset_minutes = parse_timer_minutes("ROLL_RESET", c_lower)

            if any(x in c_lower for x in ["you __can__ react", "pode reagir", "pegar kakera", "puedes__ reaccionar", "puedes reaccionar", "pouvez__ réagir", "pouvez réagir"]):
                client.kakera_react_available = True
                client.kakera_react_cooldown_until_utc = None
            elif any(x in c_lower for x in ["can't react", "não pode", "no puedes"]):
                client.kakera_react_available = False
                k_cooldown = parse_timer_minutes("KAKERA_COOLDOWN", c_lower)
                if k_cooldown is not None:
                    client.kakera_react_cooldown_until_utc = now_utc + datetime.timedelta(minutes=k_cooldown)

            client.last_tu_query_utc = datetime.datetime.now(timezone.utc)
            clear_status_dirty(client)
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
                if client.auto_mk_enabled and client.mk_rolls_left > 0 and (get_current_dk_power() >= client.dk_consumption or client.mk_bypass_power_check):
                    await process_mk_rolls(client, channel, current_cycle_id)
                    if not await active_delay(2): return
                    return

            if immediate_roll:
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

    async def check_rolls_left_tu(client, channel, mudae_prefix, log_function, preset_name,
                                  tu_message_content_for_rolls, ignore_limit_for_post_roll, key_mode_only_kakera_for_post_roll, current_cycle_id):
        content_lower = tu_message_content_for_rolls.lower()
        rolls_left = us_rolls_left = reset_time_r = 0
        now_utc = datetime.datetime.now(timezone.utc)

        main_match = re.search(REGEX_PATTERNS["ROLLS_COUNT"], content_lower, re.DOTALL)
        if main_match:
            rolls_left = int(re.sub(r"[^\d]", "", main_match.group(1)))
            for bonus_match in re.finditer(REGEX_PATTERNS["BONUS_ROLLS"], main_match.group(2)):
                amt = int(re.sub(r"[^\d]", "", bonus_match.group(1)))
                if bonus_match.group(2).lower() == "us": us_rolls_left += amt
                else: client.mk_rolls_left = amt

            reset_time_r = parse_timer_minutes("ROLL_RESET_TU", content_lower[main_match.end():])
            if reset_time_r is not None:
                new_reset = (now_utc + datetime.timedelta(minutes=reset_time_r)).replace(second=0, microsecond=0)
                if getattr(client, 'roll_reset_at_utc', None) and (new_reset - client.roll_reset_at_utc).total_seconds() > 600:
                    client.us_pulled_this_cycle = 0
                    client.us_failed_this_cycle = False
                client.roll_reset_at_utc = new_reset
            else:
                reset_time_r = 60
                client.roll_reset_at_utc = (now_utc + datetime.timedelta(minutes=reset_time_r)).replace(second=0, microsecond=0)

            total_rolls = rolls_left + us_rolls_left
            client.rolls_left = total_rolls

            if total_rolls == 0:
                if is_inactive_hour():
                    wait_s = seconds_until_active() + (random.uniform(0, client.humanization_window_minutes * 60) if client.humanization_enabled else 0)
                    BotLogger.log("Sleeping until active period (Auto rolls interrupted).", preset_name, "RESET")
                    await _interruptible_sleep(wait_s)
                    return

                rolls_did_execute = False
                if getattr(client, 'auto_rolls_enabled', False):
                    lim_ok = client.auto_rolls_limit == 0 or client.rolls_item_used_count < client.auto_rolls_limit
                    if client.rolls_used_this_interval_utc != client.roll_reset_at_utc: client.rolls_used_this_interval_utc = None
                    claim_ok = client.claim_right_available or (client.key_mode and client.auto_rolls_in_key_mode)
                    if lim_ok and client.rolls_used_this_interval_utc is None and claim_ok:
                        ch_hour = True
                        if client.auto_rolls_only_claim_hour:
                            ch_hour = bool(client.next_claim_reset_at_utc and client.roll_reset_at_utc and client.next_claim_reset_at_utc <= client.roll_reset_at_utc)

                        if ch_hour:
                            rolls_did_execute = True
                            BotLogger.log("Auto $rolls triggered.", preset_name, "INFO")
                            rolls_cmd_ch = _get_command_channel() or channel
                            if not await guarded_send(rolls_cmd_ch, f"{client.mudae_prefix}rolls"):
                                return
                            client.rolls_item_used_count += 1
                            client.rolls_used_this_interval_utc = client.roll_reset_at_utc
                            mark_status_dirty(client, {"rolls"}, reason="auto-rolls-command")
                            if not await active_delay(2.0 + random.uniform(0.1, 0.5)):
                                return
                            return

                if not rolls_did_execute and client.auto_us_enabled:
                    stop_c = client.auto_us_stop_on_claim and not client.claim_right_available
                    limit = client.auto_us_limit > 0 and client.us_pulled_this_cycle >= client.auto_us_limit
                    if not stop_c and not limit and not getattr(client, 'us_failed_this_cycle', False):
                        last_att = getattr(client, 'last_us_attempt_utc', None)
                        if last_att and (now_utc - last_att).total_seconds() < 15:
                            client.us_failed_this_cycle = True
                            BotLogger.log("Auto $us failed repeatedly. Halting $us.", preset_name, "WARN")
                            if rolls_left > 0:
                                await start_roll_commands(client, channel, rolls_left, ignore_limit_for_post_roll, key_mode_only_kakera_for_post_roll, current_cycle_id)
                                return
                        else:
                            amt = max(0, client.auto_us_limit - client.us_pulled_this_cycle if client.auto_us_limit > 0 else 20)
                            if amt > 0:
                                if client.bulk_us_enabled:
                                    chunks = [20] * (amt // 20) + ([amt % 20] if amt % 20 > 0 else [])
                                    pulled = 0
                                    for chk in chunks:
                                        if not await guarded_send(channel, f"{client.mudae_prefix}us {chk}"):
                                            return
                                        client.last_us_attempt_utc = datetime.datetime.now(timezone.utc)
                                        if not await active_delay(random.uniform(1.5, 2.5)):
                                            return
                                        failed = False
                                        async for msg in channel.history(limit=5):
                                            if msg.author.id == TARGET_BOT_ID and not msg.embeds:
                                                c_lower = msg.content.lower()
                                                if "kakera" in c_lower and ("enough" in c_lower or "pas assez" in c_lower or "insuficiente" in c_lower):
                                                    failed = True
                                                    break
                                        if failed:
                                            client.us_failed_this_cycle = True
                                            break
                                        else:
                                            pulled += chk
                                            client.us_pulled_this_cycle += chk
                                    if pulled > 0:
                                        client.rolls_left = pulled
                                        mark_status_dirty(client, {"rolls"}, reason="auto-us-pull")
                                        await start_roll_commands(client, channel, pulled, ignore_limit_for_post_roll, key_mode_only_kakera_for_post_roll, current_cycle_id, is_us_pull=True)
                                        return
                                    elif rolls_left > 0:
                                        await start_roll_commands(client, channel, rolls_left, ignore_limit_for_post_roll, key_mode_only_kakera_for_post_roll, current_cycle_id)
                                        return
                                else:
                                    step = min(20, amt)
                                    if not await guarded_send(channel, f"{client.mudae_prefix}us {step}"):
                                        return
                                    client.last_us_attempt_utc = datetime.datetime.now(timezone.utc)
                                    BotLogger.log(f"Auto $us: Pulled batch of {step} rolls...", preset_name, "INFO")
                                    if not await active_delay(random.uniform(1.5, 2.5)):
                                        return
                                    failed = False
                                    async for msg in channel.history(limit=5):
                                        if msg.author.id == TARGET_BOT_ID and not msg.embeds:
                                            c_lower = msg.content.lower()
                                            if "kakera" in c_lower and ("enough" in c_lower or "pas assez" in c_lower or "insuficiente" in c_lower):
                                                failed = True
                                                break
                                    if failed:
                                        client.us_failed_this_cycle = True
                                        if rolls_left > 0:
                                            await start_roll_commands(client, channel, rolls_left, ignore_limit_for_post_roll, key_mode_only_kakera_for_post_roll, current_cycle_id)
                                            return
                                    else:
                                        client.us_pulled_this_cycle += step
                                        client.rolls_left = step
                                        mark_status_dirty(client, {"rolls"}, reason="auto-us-pull")
                                        await start_roll_commands(client, channel, step, ignore_limit_for_post_roll, key_mode_only_kakera_for_post_roll, current_cycle_id, is_us_pull=True)
                                        if client._immediate_check_event: client._immediate_check_event.set()
                                        return

                sleep_candidates = [(float(reset_time_r or 60), "rolls reset")]
                m_c = re.search(REGEX_PATTERNS["CLAIM_RESET"], content_lower)
                if m_c and any(kw in m_c.group(0) for kw in ["$daily", "$dk", "$rt"]): m_c = None

                c_min = None
                if m_c:
                    h, m = parse_hm(m_c)
                    c_min = h * 60 + m
                else:
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

        if get_current_dk_power() >= client.dk_consumption or client.mk_bypass_power_check:
            used = 0
            while client.mk_rolls_left > 0 and (get_current_dk_power() >= client.dk_consumption or client.mk_bypass_power_check):
                if client.is_paused or is_maintenance_active() or client.interrupt_rolling:
                    mark_status_dirty(client, {"rolls", "power"}, reason="mk-interrupted")
                    break
                command_label = "/mk" if client.use_slash_rolls and not client.slash_fallback_active else f"{client.mudae_prefix}mk"
                BotLogger.log(f"Using {command_label} ({client.mk_rolls_left} left, Power: {get_current_dk_power()}%)", preset_name, "KAKERA")
                if not await send_roll_command(channel, "mk"):
                    mark_status_dirty(client, {"rolls", "power"}, reason="mk-send-blocked")
                    break
                client.mk_rolls_left -= 1
                used += 1
                if not await active_delay(3):
                    mark_status_dirty(client, {"rolls", "power"}, reason="mk-delay-interrupted")
                    break
                async for msg in channel.history(limit=5, oldest_first=False):
                    if msg.author.id == TARGET_BOT_ID and msg.embeds and is_character_embed(msg.embeds[0]) and msg.components:
                        await claim_character(client, channel, msg, is_kakera=True, is_mk_roll=True)
                        break
                if not await active_delay(1):
                    mark_status_dirty(client, {"rolls", "power"}, reason="mk-post-send-interrupted")
                    break
            if used > 0: BotLogger.log(f"Used {used} MK rolls.", preset_name, "KAKERA")
        else:
            BotLogger.log(f"Skipping $mk: Insufficient power ({get_current_dk_power()}% < {client.dk_consumption}%).", preset_name, "INFO")

    async def execute_farm_forcedivorce(client, channel, char_name, reason):
        """Release the configured farm character and confirm through the shared command queue."""
        if client.is_paused or is_maintenance_active():
            return False
        release_key = str(char_name or "").strip().casefold()
        now_monotonic = time.monotonic()
        last_release = client._farm_release_recent.get(release_key, 0.0)
        if release_key and now_monotonic - last_release < 15.0:
            BotLogger.log(f"Kakera Farm: Skipping duplicate forcedivorce for {char_name}.", preset_name, "DEBUG", client)
            return True
        if release_key:
            client._farm_release_recent[release_key] = now_monotonic
        BotLogger.log(f"Kakera Farm: Forcedivorcing {char_name} {reason}.", preset_name, "INFO")
        if not await guarded_send(channel, f"{client.mudae_prefix}forcedivorce {char_name}"):
            client._farm_release_recent.pop(release_key, None)
            BotLogger.log(f"Kakera Farm: Could not send forcedivorce for {char_name}.", preset_name, "WARN")
            return False
        if not await guarded_send(channel, "y"):
            client._farm_release_recent.pop(release_key, None)
            BotLogger.log(f"Kakera Farm: Could not confirm forcedivorce for {char_name}.", preset_name, "WARN")
            return False
        BotLogger.log(f"Kakera Farm: Confirmed forcedivorce for {char_name}.", preset_name, "INFO")
        return await active_delay(1.0 + random.uniform(0.1, 0.4))

    async def start_roll_commands(client, channel, rolls_left, ignore_limit_for_post_roll, key_mode_only_kakera_for_post_roll, current_cycle_id, is_us_pull: bool = False):
        if client.is_paused or is_maintenance_active(): return
        client.interrupt_rolling = False
        if channel.id != client.target_channel_id:
            channel = client.get_channel(client.target_channel_id) or client._main_channel or channel

        if (client.farm_character_enabled and client.farm_character and client.claim_right_available
                and client.farm_forcedivorce_before_roll):
            if client.is_paused or is_maintenance_active() or client.interrupt_rolling: return
            if not await execute_farm_forcedivorce(client, channel, client.farm_character, "before rolling (configured timing)"):
                return

        if client.is_paused or is_maintenance_active() or client.interrupt_rolling: return
        await process_mk_rolls(client, channel, current_cycle_id)

        reset_soon = False
        if client.next_claim_reset_at_utc:
            diff = (client.next_claim_reset_at_utc - datetime.datetime.now(timezone.utc)).total_seconds()
            if 0 < diff <= 3600: reset_soon = True

        is_timing_mode_active = False
        if not is_us_pull and client.time_rolls_to_claim_reset and not client.claim_right_available and (reset_soon or (not client.rt_available and not client.key_mode)):
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

        BotLogger.log(f"Rolling {rolls_left} times" + (" (Reactive)" if client.enable_reactive_self_snipe else ""), preset_name, "INFO")
        client.is_actively_rolling = True
        client.interrupt_rolling = False
        client._rolls_sent = client._rolls_received = 0
        client.collected_rolls = []
        client.collected_kakera_rolls = []

        client.rolls_left = rolls_left
        consecutive_failures = 0
        while client.rolls_left > 0:
            if client.is_paused or client.interrupt_rolling or is_maintenance_active():
                mark_status_dirty(client, {"rolls"}, reason="rolling-interrupted")
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

        if not getattr(client, 'immediate_kakera_click', True) and getattr(client, 'collected_kakera_rolls', []):
            BotLogger.log("Processing collected rolls for Kakera priority collection...", preset_name, "INFO")

            prio_map = {k.strip(): (idx + 1) * 10 for idx, k in enumerate(reversed(client.kakera_priority_order))}
            for s in client.sphere_emojis: prio_map[s] = 999
            prio_map['kakeraP'] = 999

            clickable_buttons = []
            for msg in client.collected_kakera_rolls:
                if not msg.embeds or not msg.components:
                    continue
                embed = msg.embeds[0]
                chaos_count = count_chaos_keys(embed)
                has_sp_perk = has_perk_eight_discount(embed.description)

                only_free = False
                if client.only_chaos and chaos_count == 0:
                    only_free = True

                target_list = client.sphere_perk_emojis if has_sp_perk else (client.chaos_emojis if chaos_count > 0 else client.kakera_emojis)

                for row_idx, comp in enumerate(msg.components):
                    for child_idx, btn in enumerate(comp.children):
                        if hasattr(btn.emoji, 'name') and btn.emoji.name:
                            name = btn.emoji.name
                            name_clean = name.rstrip('2')

                            is_sphere = (name in client.sphere_emojis) or (name_clean in client.sphere_emojis)
                            is_free = name == 'kakeraP' or is_sphere or check_is_green(btn)

                            if only_free and not is_free:
                                continue

                            is_clickable = False
                            if is_sphere:
                                if (name.lower() in client.sphere_click_targets) or (name_clean.lower() in client.sphere_click_targets):
                                    is_clickable = True
                            else:
                                if (name in target_list or name_clean in target_list) or ("kakera" in name.lower() and check_is_green(btn)):
                                    is_clickable = True

                            if is_clickable:
                                prio = prio_map.get(name_clean, 0)
                                if is_sphere or name == 'kakeraP' or check_is_green(btn):
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
                                    'cost': calculate_kakera_power_cost(
                                        client.dk_consumption,
                                        has_chaos_discount=chaos_count > 0,
                                        has_perk_eight_discount=has_sp_perk,
                                        is_free=is_free,
                                    ),
                                    'char_name': (embed.author.name if embed.author else "Unknown").strip()
                                })

            # Sort globally by priority descending
            clickable_buttons.sort(key=lambda item: item['priority'], reverse=True)

            clicks_per_message = {}
            for item in clickable_buttons:
                msg = item['message']
                custom_id = item['custom_id']
                pos = item['pos']
                name = item['emoji_name']
                is_free = item['is_free']
                cost = item['cost']
                chaos_count = item['chaos_count']
                char_name = item['char_name']

                msg_id = msg.id
                if clicks_per_message.get(msg_id, 0) >= 3:
                    continue

                # Update target message reference to avoid stale element exceptions
                try:
                    msg = await channel.fetch_message(msg_id)
                    found = False
                    for row_idx, c_f in enumerate(msg.components):
                        for child_idx, b_f in enumerate(c_f.children):
                            match_custom = (custom_id is not None and b_f.custom_id == custom_id)
                            match_pos = (pos == (row_idx, child_idx))
                            if match_custom or (custom_id is None and match_pos):
                                btn, found = b_f, True
                                break
                        if found: break
                    if not found: continue
                except Exception:
                    continue

                if getattr(btn, 'disabled', False):
                    continue

                current_pow = get_current_dk_power()
                if current_pow < cost:
                    if client.auto_dk_enabled and client.dk_power_management and client.dk_stock_count > 0:
                        log_name = name
                        BotLogger.log(f"Dynamic DK Refill: Power too low ({current_pow}% < {cost}%). Sending $dk for {log_name}...", preset_name, "KAKERA")
                        try:
                            cmd_ch = _get_command_channel() or channel
                            if not await guarded_send(cmd_ch, f"{client.mudae_prefix}dk"):
                                return
                            client.dk_stock_count = max(0, client.dk_stock_count - 1)
                            client.current_dk_power = client.max_dk_power
                            client.last_dk_power_update_utc = datetime.datetime.now(timezone.utc)
                            if not await active_delay(1.2 + random.uniform(0.1, 0.4)):
                                return
                            current_pow = get_current_dk_power()
                        except Exception as e:
                            BotLogger.log(f"Dynamic DK Refill failed: {e}", preset_name, "ERROR")

                if current_pow < cost:
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

                try:
                    if not await guarded_click(btn):
                        return
                    client.current_dk_power = max(0, get_current_dk_power() - cost)
                    client.kakera_reacted_messages.add(msg_id)
                    clicks_per_message[msg_id] = clicks_per_message.get(msg_id, 0) + 1
                    BotLogger.log(f"Kakera clicked: {char_name} [{name}] (Pw: {client.current_dk_power}%)", preset_name, "KAKERA")
                    client._last_kakera_click_ts = time.time()
                    if not await active_delay(0.6):
                        return
                except discord.HTTPException as e:
                    BotLogger.log(f"Kakera click failed (HTTP {getattr(e, 'status', '?')}): {getattr(e, 'text', str(e))[:100]}", preset_name, "ERROR")
                except Exception as e:
                    BotLogger.log(f"Kakera click error: {e}", preset_name, "ERROR")

            client.collected_kakera_rolls.clear()

        if is_timing_mode_active:
            client.claim_right_available = True
            BotLogger.log("Reset passed. Claim is now available.", preset_name, "CLAIM")

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
                await handle_mudae_messages(client, channel, client.collected_rolls, ignore_limit_for_post_roll, False if is_timing_mode_active else key_mode_only_kakera_for_post_roll)
            except Exception as e:
                BotLogger.log(f"Defer-roll processing error: {e}", preset_name, "ERROR")
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

    async def finalize_successful_claim(pending, channel, verification_source):
        if pending.get("finalized"):
            return
        pending["finalized"] = True
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
            and bool(client.farm_character)
            and char_name.casefold() == client.farm_character.casefold()
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
            is_blacklisted = False
            if char_name.lower() in getattr(client, 'auto_divorce_blacklist', set()):
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

        if consumes_claim and client.auto_rt_after_claim and not client.is_paused and not farm_character_claimed:
            mins_to_reset = ((client.next_claim_reset_at_utc - now).total_seconds() / 60.0) if client.next_claim_reset_at_utc else None
            if mins_to_reset is not None and mins_to_reset < 60:
                BotLogger.log(f"Auto $rt: SKIPPED — resets soon ({mins_to_reset:.0f}m).", preset_name, "INFO")
            elif client.rolling_enabled and not client.is_actively_rolling:
                BotLogger.log("Auto $rt: SKIPPED — rolling sequence finished.", preset_name, "INFO")
            else:
                BotLogger.log(f"Auto $rt: Sending $rt after claiming {char_name}.", preset_name, "CLAIM")
                try:
                    if await guarded_send(channel, f"{client.mudae_prefix}rt"):
                        client.rt_available = False
                        request_status_refresh({"claim", "rt"}, reason="auto-rt-used", urgent=True)
                except Exception as e:
                    BotLogger.log(f"Auto $rt failed: {e}", preset_name, "ERROR")

        if farm_character_claimed and consumes_claim and client.auto_rt_after_claim and client.rt_available:
            if post_claim_farm_mode:
                if farm_release_sent and await guarded_send(channel, f"{client.mudae_prefix}rt"):
                    client.rt_available = False
                    BotLogger.log(f"Kakera Farm: $rt restored after releasing {char_name}.", preset_name, "CLAIM")
                    request_status_refresh({"claim", "rt"}, reason="farm-rt-used", urgent=True)
            elif await guarded_send(channel, f"{client.mudae_prefix}rt"):
                client.rt_available = False
                if await active_delay(1.5):
                    await execute_farm_forcedivorce(
                        client,
                        channel,
                        client.farm_character,
                        "after $rt (solo/key mode)",
                    )
                request_status_refresh({"claim", "rt"}, reason="farm-rt-used", urgent=True)

        if is_snipe_action and client.enable_snipe_chat_reactions and client.snipe_chat_messages:
            try:
                if await active_delay(random.uniform(2.0, 5.0)):
                    await guarded_send(channel, random.choice(client.snipe_chat_messages))
            except Exception as e:
                BotLogger.log(f"Snipe chat reaction failed: {e}", preset_name, "ERROR")

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
            client.processed_claim_messages.discard(message_id)
            if message_id is not None and retry_count < 1 and can_retry and not client.is_paused:
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
        deadline = time.monotonic() + 8.0

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
            clear_pending_claim(pending)
            clear_status_dirty(client, {"claim"})
            return ClaimOutcome.FAILURE

        BotLogger.log(f"{lbl}: Inconclusive. Refreshing $tu before changing claim state.", preset_name, "WARN")
        if pending.get("consumes_claim"):
            request_status_refresh({"claim"}, reason="claim-verification-inconclusive", urgent=True)
        else:
            clear_pending_claim(pending)
        return ClaimOutcome.INCONCLUSIVE

    async def handle_mudae_messages(client, channel, mudae_messages, ignore_limit_param, key_mode_only_kakera_param):
        k_claims = []
        char_claims = []
        wl_claims = []
        min_kak_post = 0 if ignore_limit_param else client.min_kakera

        attempted = set()
        for msg in mudae_messages:
            if not msg.embeds: continue
            embed = msg.embeds[0]
            if not is_character_embed(embed): continue

            all_k = client.kakera_emojis + client.chaos_emojis + client.sphere_emojis
            is_k = msg.components and any(
                hasattr(b.emoji, 'name') and b.emoji.name and (
                    b.emoji.name in all_k or
                    b.emoji.name.rstrip('2') in all_k or
                    ("kakera" in b.emoji.name.lower() and check_is_green(b))
                ) for comp in msg.components for b in comp.children
            )
            if is_k:
                k_claims.append(msg)
            else:
                if is_free_event(embed) or has_claim_option(msg, embed, client.claim_emojis):
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
                    is_wl = c_name in client.wishlist or (client.series_snipe_mode and any(s in series for s in client.series_wishlist)) or is_wished_by_self(msg, client.user.id) or is_ranked
                    is_avoided = c_name in client.avoid_list

                    if is_wl and not is_avoided: wl_claims.append((msg, c_name, k_v, series))
                    elif k_v >= min_kak_post and not is_avoided: char_claims.append((msg, c_name, k_v, series))

        # Filter claims to exclude messages already claimed/in progress globally
        wl_claims = _claim_coordinator.filter_available(wl_claims)
        char_claims = _claim_coordinator.filter_available(char_claims)

        for msg_k in k_claims:
            await claim_character(client, channel, msg_k, is_kakera=True)
            if not await active_delay(0.3): return

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
            for msg, n, v, s in (wl_claims + char_claims):
                if msg.id == msg_claimed_id or msg.id in client.processed_claim_messages or n == getattr(client, 'last_successfully_claimed_character', ''):
                    continue
                claims_r, likes_r = parse_mudae_ranks(msg.embeds[0].description or "")
                is_ranked = (client.max_claim_rank > 0 and 0 < claims_r <= client.max_claim_rank) or (client.max_like_rank > 0 and 0 < likes_r <= client.max_like_rank)
                is_wl_rt = n in client.wishlist or (client.series_snipe_mode and any(s_in in s for s_in in client.series_wishlist)) or is_wished_by_self(msg, client.user.id) or is_ranked

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
                    _claim_coordinator.release_restore(msg_rt.id)
                    continue

                BotLogger.log(f"Attempting RT on {n_rt} ({v_rt})", preset_name, "CLAIM")
                rt_sent_successfully = False
                try:
                    if not await guarded_send(channel, f"{client.mudae_prefix}rt"):
                        break
                    client.rt_available = False
                    attempted.add(n_rt)
                    if not await active_delay(0.7):
                        break
                    rt_sent_successfully = True
                    await claim_character(client, channel, msg_rt, is_rt_claim=True, kakera_value=v_rt)
                    break
                except Exception:
                    pass
                finally:
                    _claim_coordinator.release_all(msg_rt.id)

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
                        return False

                    BotLogger.log(f"Using RT for {char_name}", preset_name, "CLAIM")
                    try:
                        if not await guarded_send(channel, f"{client.mudae_prefix}rt"):
                            return False
                        client.rt_available = False
                        if not await active_delay(random.uniform(0.6, 1.0)):
                            return False
                    except Exception as e:
                        BotLogger.log(f"RT Failed: {e}", preset_name, "ERROR")
                        return False

                    # Transition to claim lock
                    claim_locked_successfully = _claim_coordinator.transition_restore_to_claim(msg.id)
                    claim_registered = claim_locked_successfully
                    rt_registered = False

                    if not claim_locked_successfully:
                        return False

            if is_free_claim and not await active_delay(random.uniform(1.0, 2.5)): return False

            if is_kakera:
                if client.op_perk_5_only:
                    has_free = msg.components and any(hasattr(b.emoji, 'name') and (b.emoji.name == 'kakeraP' or b.emoji.name in client.sphere_emojis or check_is_green(b)) for c in msg.components for b in c.children)
                    if not has_free:
                        desc = (embed.description or "").lower()
                        if not (any(f"sp" in line for line in desc.split()) or any(s.lower() in desc for s in client.sphere_emojis)):
                            return False

                if client.mk_only and not is_mk_roll: return False

                chaos_count = count_chaos_keys(embed)
                if not is_mk_roll and not is_snipe and client.only_chaos and chaos_count == 0:
                    has_free = msg.components and any(hasattr(b.emoji, 'name') and (b.emoji.name == 'kakeraP' or b.emoji.name in client.sphere_emojis or check_is_green(b)) for c in msg.components for b in c.children)
                    if not has_free: return False

                has_sp_perk = has_perk_eight_discount(embed.description)
                target_list = client.kakera_emojis if is_snipe else (client.sphere_perk_emojis if has_sp_perk else (client.chaos_emojis if chaos_count > 0 else client.kakera_emojis))

                cooldown_active = not is_kakera_reaction_allowed()
                has_free_button = msg.components and any(hasattr(b.emoji, 'name') and (b.emoji.name == 'kakeraP' or b.emoji.name in client.sphere_emojis or check_is_green(b)) for c in msg.components for b in c.children)
                # The 10+ key discount and cooldown bypass only applies to self-rolls (when is_snipe is False)
                if cooldown_active and not has_free_button and (chaos_count == 0 or is_snipe) and not has_sp_perk: return False

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
                                is_sphere = (name in client.sphere_emojis) or (name_clean in client.sphere_emojis)
                                if is_sphere:
                                    if (name.lower() in client.sphere_click_targets) or (name_clean.lower() in client.sphere_click_targets):
                                        all_btns_tracked.append({
                                            'btn': btn,
                                            'custom_id': btn.custom_id,
                                            'pos': (row_idx, child_idx),
                                            'emoji_name': name
                                        })
                                else:
                                    if (name in target_list or name_clean in target_list) or ("kakera" in name.lower() and check_is_green(btn)):
                                        all_btns_tracked.append({
                                            'btn': btn,
                                            'custom_id': btn.custom_id,
                                            'pos': (row_idx, child_idx),
                                            'emoji_name': name
                                        })

                    prio_map = {k.strip(): (idx + 1) * 10 for idx, k in enumerate(reversed(client.kakera_priority_order))}
                    for s in client.sphere_emojis: prio_map[s] = 999
                    prio_map['kakeraP'] = 999

                    all_btns_tracked.sort(key=lambda item: prio_map.get(item['emoji_name'].rstrip('2'), 0), reverse=True)

                    buttons_to_click = all_btns_tracked

                    max_clicks = 3
                    clicked_count = 0
                    for item in buttons_to_click:
                        if clicked_count >= max_clicks: break
                        btn = item['btn']
                        custom_id = item['custom_id']
                        pos = item['pos']
                        name = item['emoji_name']

                        if clicked_count > 0:
                            try:
                                msg = await channel.fetch_message(msg.id)
                                found = False
                                for row_idx, c_f in enumerate(msg.components):
                                    for child_idx, b_f in enumerate(c_f.children):
                                        match_custom = (custom_id is not None and b_f.custom_id == custom_id)
                                        match_pos = (pos == (row_idx, child_idx))
                                        if match_custom or (custom_id is None and match_pos):
                                            btn, found = b_f, True
                                            break
                                    if found: break
                                if not found: continue
                            except Exception: break

                        name_clean = name.rstrip('2')
                        is_sphere = name in client.sphere_emojis or name_clean in client.sphere_emojis
                        is_free = name == 'kakeraP' or is_sphere or check_is_green(btn)
                        if client.only_chaos and chaos_count == 0 and not is_free:
                            continue
                        cost = calculate_kakera_power_cost(
                            client.dk_consumption,
                            has_chaos_discount=chaos_count > 0,
                            has_perk_eight_discount=has_sp_perk,
                            is_external_roll=is_snipe,
                            is_free=is_free,
                        )
                        current_pow = get_current_dk_power()

                        if current_pow < cost:
                            if client.auto_dk_enabled and client.dk_power_management and client.dk_stock_count > 0:
                                log_name = btn.emoji.name if hasattr(btn.emoji, 'name') else 'Kakera'
                                BotLogger.log(f"Dynamic DK Refill: Power too low ({current_pow}% < {cost}%). Sending $dk for {log_name}...", preset_name, "KAKERA")
                                try:
                                    cmd_ch = _get_command_channel() or channel
                                    if not await guarded_send(cmd_ch, f"{client.mudae_prefix}dk"):
                                        return clicked
                                    client.dk_stock_count = max(0, client.dk_stock_count - 1)
                                    client.current_dk_power = client.max_dk_power
                                    client.last_dk_power_update_utc = datetime.datetime.now(timezone.utc)
                                    if not await active_delay(1.2 + random.uniform(0.1, 0.4)):
                                        return clicked
                                    current_pow = get_current_dk_power()
                                except Exception as e:
                                    BotLogger.log(f"Dynamic DK Refill failed: {e}", preset_name, "ERROR")

                        if current_pow < cost:
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

                        try:
                            if not await guarded_click(btn):
                                return clicked
                            client.current_dk_power = max(0, get_current_dk_power() - cost)
                            client.kakera_reacted_messages.add(msg.id)
                            BotLogger.log(f"Kakera clicked: {char_name} [{name}] (Pw: {client.current_dk_power}%)", preset_name, "KAKERA")
                            clicked = True
                            clicked_count += 1
                            client._last_kakera_click_ts = time.time()
                            if not await active_delay(0.6):
                                return clicked
                        except discord.HTTPException as e:
                            BotLogger.log(f"Kakera click failed (HTTP {getattr(e, 'status', '?')}): {getattr(e, 'text', str(e))[:100]}", preset_name, "ERROR")
                        except Exception as e:
                            BotLogger.log(f"Kakera click error: {e}", preset_name, "ERROR")
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
                            for attempt in range(3):
                                try:
                                    if not await guarded_click(btn):
                                        break
                                    claim_success = True
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
                                await verify_snipe_outcome(client, channel, msg, pending)
                                return True
                            clear_pending_claim(pending)

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
                        clear_pending_claim(pending)
                        return False
                    BotLogger.log(f"Claiming {char_name}{kakera_str} (Reaction: {reaction_emoji})", preset_name, "CLAIM")
                    await verify_snipe_outcome(client, channel, msg, pending)
                    return True
                except Exception as e:
                    clear_pending_claim(locals().get('pending'))
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
        precision_wait = "claim reset" in reason.lower() or "timing threshold" in reason.lower()
        human_jitter = random.uniform(0, max(0.0, client.humanization_window_minutes * 60)) if client.humanization_enabled and not precision_wait else 0
        wait_seconds = min_wait + human_jitter + getattr(client, 'persistent_stagger_seconds', 0)

        BotLogger.log(f"{'Humanized ' if client.humanization_enabled else ''}Waiting {wait_seconds/60:.1f}m ({reason}).", preset_name, "RESET")
        await _interruptible_sleep(wait_seconds)
        if client.is_paused:
            return

        if is_inactive_hour():
            wait_s = seconds_until_active() + (random.uniform(0, client.humanization_window_minutes * 60) if client.humanization_enabled else 0)
            BotLogger.log(f"Inactive hours. Sleeping {wait_s/60:.0f}m.", preset_name, "RESET")
            await _interruptible_sleep(wait_s)
            if client.is_paused:
                return

        if client.humanization_enabled:
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

    @client.event
    async def on_message_edit(before, after):
        update_event = client._sphere_board_update_events.get(getattr(after, 'id', None))
        if update_event is not None:
            update_event.set()

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
        capture_tu_response(message)
        capture_sphere_game_response(message)
        is_roll = (message.channel.id == client.target_channel_id)
        is_snipe = (client.snipe_mode and message.channel.id in client.snipe_channels)

        if message.author.id != TARGET_BOT_ID or not (is_roll or is_snipe):
            if not client.is_paused and client.rolling_enabled: await client.process_commands(message)
            return

        record_claim_text_evidence(message)
        process_claim_cooldown_message(message)

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
            request_status_refresh(reason="mudae-maintenance", urgent=True)
            BotLogger.log(f"Mudae is under maintenance! Pausing for {m_mins} minutes.", preset_name, "ERROR")
            return

        if is_maintenance_active(): return
        if client.is_paused:
            if client.rolling_enabled and client.is_actively_rolling and message.embeds and is_character_embed(message.embeds[0]):
                client._rolls_received += 1
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

        if (
            is_roll
            and client.farm_character_enabled
            and client.farm_character
            and client.farm_forcedivorce_after_other_claim
            and is_claim_announcement_for_character(message.content, client.farm_character)
        ):
            farm_claim_evidence = classify_claim_text(
                message.content,
                client.farm_character,
                claim_identities(),
                user_id=getattr(getattr(client, "user", None), "id", None),
            )
            if farm_claim_evidence.outcome != ClaimOutcome.SUCCESS:
                client.loop.create_task(execute_farm_forcedivorce(
                    client,
                    message.channel,
                    client.farm_character,
                    "after another account claimed it (configured timing)",
                ))

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
            if m_bonus and (time.time() - getattr(client, '_last_kakera_click_ts', 0)) <= 10:
                bonus_amt = int(m_bonus.group(1))
                client.rolls_left += bonus_amt
                client._local_extra_rolls_pending += bonus_amt
                BotLogger.log(f"Gained +{bonus_amt} extra rolls from Kakera! rolls_left is now {client.rolls_left}.", preset_name, "KAKERA")
                wake_status_loop()

        if not message.embeds: return
        embed = message.embeds[0]

        if not is_character_embed(embed):
            if client.kakera_reaction_snipe_mode_active and message.id not in client.kakera_reaction_sniped_messages:
                all_k = client.kakera_emojis + client.chaos_emojis + client.sphere_emojis
                has_btn = message.components and any(hasattr(b.emoji, 'name') and b.emoji.name and (b.emoji.name in all_k or b.emoji.name.rstrip('2') in all_k) for comp in message.components for b in comp.children)
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

        if has_free_claim_button(message.components, client.claim_emojis):
            c_name = embed.author.name.lower()
            if c_name not in client.avoid_list and not _claim_coordinator.is_reserved(message.id):
                BotLogger.log(f"Free Claim: green claim button detected for {c_name}.", preset_name, "CLAIM")
                if await claim_character(client, message.channel, message, is_free_claim=True):
                    return

        if client.rolling_enabled and client.is_actively_rolling:
            client._rolls_received += 1
            desc = embed.description or ""
            if any(limit in desc for limit in ["limit of 1,000 keys", "limite de 1.000 chaves", "límite de 1.000 llaves"]):
                client.interrupt_rolling = True
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
            is_wl = c_name in client.wishlist or (client.series_snipe_mode and any(s in series for s in client.series_wishlist)) or is_wished_by_self(message, client.user.id) or is_ranked
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
                        BotLogger.log(f"Hybrid Smart Instant Claim triggered for {c_name} ({k_val} ka)!", preset_name, "CLAIM")
                        if client.reactive_snipe_delay > 0:
                            if not await active_delay(client.reactive_snipe_delay + random.uniform(0.05, 0.25)): return
                        if await claim_character(client, message.channel, message, kakera_value=k_val):
                            process = False
                elif k_val >= client.current_min_kakera_for_roll_claim and not is_avoided:
                    client.collected_rolls.append(message)
            else:
                if not getattr(client, 'enable_reactive_self_snipe', True):
                    client.collected_rolls.append(message)
                else:
                    is_val = k_val >= client.current_min_kakera_for_roll_claim
                    already_in_progress = _claim_coordinator.is_reserved(message.id)
                    if (is_wl or is_val) and not is_avoided and has_claim_option(message, embed, client.claim_emojis) and not already_in_progress:
                        if is_key_mode_kakera_only():
                            pass
                        else:
                            if not client.claim_right_available and not client.rt_available and client.next_claim_reset_at_utc:
                                t_to_r = (client.next_claim_reset_at_utc - datetime.datetime.now(timezone.utc)).total_seconds()
                                if 0 < t_to_r <= 15:
                                    BotLogger.log(f"Claim reset is in {t_to_r:.1f}s. Waiting for reset...", preset_name, "INFO")
                                    client.interrupt_rolling = True
                                    if not await active_delay(t_to_r + 0.2): return
                                    client.claim_right_available = True
                                    client.last_successfully_claimed_character = None
                                    delta = datetime.timedelta(minutes=client.claim_interval)
                                    while client.next_claim_reset_at_utc <= datetime.datetime.now(timezone.utc):
                                        client.next_claim_reset_at_utc += delta

                            client.interrupt_rolling = True
                            BotLogger.log(f"Real-time Claim: Halting rolls for claim attempt on {c_name}", preset_name, "CLAIM")
                            if client.reactive_snipe_delay > 0:
                                if not await active_delay(client.reactive_snipe_delay + random.uniform(0.05, 0.25)): return
                            if await claim_character(client, message.channel, message, kakera_value=k_val):
                                process = False

                all_k = client.kakera_emojis + client.chaos_emojis + client.sphere_emojis + client.sphere_perk_emojis
                has_btn = message.components and any(hasattr(b.emoji, 'name') and b.emoji.name and (b.emoji.name in all_k or b.emoji.name.rstrip('2') in all_k) for comp in message.components for b in comp.children)
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
            owner_id, owner_name = await detect_roll_owner(client, message)

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
                is_wanted = c_name in client.wishlist or (client.series_snipe_mode and any(s in series for s in client.series_wishlist)) or is_wished_by_self(message, client.user.id) or is_ranked or k_val >= client.current_min_kakera_for_roll_claim
                is_avoided = c_name in client.avoid_list
                already_in_progress = _claim_coordinator.is_reserved(message.id)
                if is_wanted and not is_avoided and has_claim_option(message, embed, client.claim_emojis) and not already_in_progress:
                    if not is_key_mode_kakera_only() and is_character_snipe_allowed(is_external_snipe=False):
                        BotLogger.log(f"Manual Self-Roll Claim: {c_name} ({k_val} ka)", preset_name, "CLAIM")
                        if client.reactive_snipe_delay > 0:
                            if not await active_delay(client.reactive_snipe_delay + random.uniform(0.05, 0.25)): return
                        if await claim_character(client, message.channel, message, kakera_value=k_val):
                            process = False

            if client.kakera_reaction_snipe_mode_active and message.id not in client.kakera_reaction_sniped_messages:
                 all_k = client.kakera_emojis + client.chaos_emojis + client.sphere_emojis
                 has_btn = message.components and any(hasattr(b.emoji, 'name') and b.emoji.name and (b.emoji.name in all_k or b.emoji.name.rstrip('2') in all_k) for comp in message.components for b in comp.children)
                 if has_btn:
                    target_ok = True
                    if client.kakera_reaction_snipe_targets:
                        is_target = False
                        if owner_id and str(owner_id) in client.kakera_reaction_snipe_targets:
                            is_target = True
                        if owner_name and owner_name in client.kakera_reaction_snipe_targets:
                            is_target = True
                        if not is_target:
                            target_ok = False
                    if target_ok:
                        client.kakera_reaction_sniped_messages.add(message.id)
                        if not await active_delay(client.kakera_reaction_snipe_delay_value): return
                        await claim_character(client, message.channel, message, is_kakera=True, is_snipe=True)

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
                    if any(s in series for s in client.series_wishlist) and not is_avoided and has_claim_option(message, embed, client.claim_emojis) and not already_in_progress:
                        if is_key_mode_kakera_only() or not is_character_snipe_allowed(is_external_snipe=True): pass
                        else:
                            if not await active_delay(client.series_snipe_delay + random.uniform(0.05, 0.25)): return
                            if await claim_character(client, message.channel, message, is_snipe=True):
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

def parse_args():
    import argparse
    parser = argparse.ArgumentParser(description="Mudae Bot Helper")
    parser.add_argument("--preset", type=str, help="Name of the preset to run")
    parser.add_argument("--all", action="store_true", help="Run all presets")
    parser.add_argument("--stagger-index", type=int, default=0, help="Active preset position for automated staggering")
    return parser.parse_args()

if __name__ == "__main__":
    cleanup_after_update()
    check_for_updates()
    args = parse_args()
    if args.preset:
        if args.preset in presets:
            prepared = prepare_active_presets([args.preset], presets, start_index=args.stagger_index)
            if prepared:
                bot_lifecycle_wrapper(*prepared[0])
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

```

## File: `mudae_preset_editor.py`

```python
"""
MudaRemote Preset Editor
A graphical interface for managing mudae_bot.py presets.
"""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import json
import os
import subprocess
import sys
import argparse
import time
import threading
import math

try:
    from mudae_core import SecretStore, active_stagger_seconds, prepare_active_presets
    from mudae_core.config import (
        atomic_write_json,
        load_json,
        parse_inactive_hours,
        parse_scheduled_times,
        validate_preset,
    )
    from mudae_core.secrets import SecretStoreError
except (ModuleNotFoundError, ImportError) as core_error:
    missing_module = str(getattr(core_error, "name", ""))
    if missing_module and not missing_module.startswith("mudae_core"):
        raise
    if not missing_module and "mudae_core" not in str(core_error):
        raise
    # Legacy source updaters only fetched the bot/editor pair. Importing the
    # updated bot runs its one-time verified bridge, then these imports succeed.
    import mudae_bot  # noqa: F401
    from mudae_core import SecretStore, active_stagger_seconds, prepare_active_presets
    from mudae_core.config import atomic_write_json, load_json, parse_inactive_hours, parse_scheduled_times, validate_preset
    from mudae_core.secrets import SecretStoreError

def get_base_path():
    """Get the base path for file operations.
    When running as a PyInstaller --onefile .exe, sys._MEIPASS is the temp folder,
    but we want the directory where the actual .exe is located to read/write presets.json.
    """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

# Premium Catppuccin Mocha Color Palette
BG_DARK = "#0f0f14"          # Main application background
BG_PANEL = "#151521"         # Sidebar, card backgrounds, labels
BG_INPUT = "#1e1e2e"         # Text input fields background
ACCENT = "#89b4fa"           # Primary interactions, buttons
ACCENT_ALT = "#cba6f7"       # Secondary borders, toggle cards
TEXT_MAIN = "#cdd6f4"        # High contrast primary text
TEXT_MUTED = "#8084a3"       # Secondary help text and descriptions
BORDER_COLOR = "#2b2b3a"     # Subtle division lines
COLOR_SUCCESS = "#a6e3a1"    # Active/Save buttons
COLOR_DANGER = "#f38ba8"     # Delete buttons

class Tooltip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip_window = None
        self.id = None

        self.widget.bind("<Enter>", self.enter)
        self.widget.bind("<Leave>", self.leave)
        self.widget.bind("<ButtonPress>", self.leave)

    def enter(self, event=None):
        self.schedule()

    def leave(self, event=None):
        self.unschedule()
        self.hide()

    def schedule(self):
        self.unschedule()
        self.id = self.widget.after(400, self.show)

    def unschedule(self):
        if self.id:
            self.widget.after_cancel(self.id)
            self.id = None

    def show(self):
        if self.tip_window or not self.text:
            return
        x = self.widget.winfo_rootx() + 25
        y = self.widget.winfo_rooty() + 20

        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")

        frame = tk.Frame(tw, bg=BG_PANEL, bd=1, relief="solid", highlightbackground=ACCENT, highlightthickness=1)
        frame.pack()

        label = tk.Label(
            frame,
            text=self.text,
            justify=tk.LEFT,
            bg=BG_PANEL,
            fg=TEXT_MAIN,
            font=("Segoe UI", 9),
            padx=10,
            pady=6,
            wraplength=250
        )
        label.pack()

    def hide(self):
        tw = self.tip_window
        self.tip_window = None
        if tw:
            tw.destroy()

class CollapsibleLabelFrame(ttk.Frame):
    def __init__(self, parent, text, start_open=False, *args, **kwargs):
        super().__init__(parent, style="Card.TFrame", *args, **kwargs)
        self.text = text
        self.is_open = start_open

        self.header = tk.Frame(self, bg=BG_PANEL, bd=0, highlightbackground=BORDER_COLOR, highlightthickness=1)
        self.header.pack(fill=tk.X, ipady=4)

        self.toggle_lbl = tk.Label(
            self.header,
            text=("▼   " if start_open else "▶   ") + text,
            bg=BG_PANEL,
            fg=TEXT_MAIN,
            font=("Segoe UI", 11, "bold"),
            cursor="hand2",
            anchor="w",
            padx=12,
            pady=8
        )
        self.toggle_lbl.pack(fill=tk.X, side=tk.LEFT, expand=True)

        def on_enter(e):
            self.header.configure(bg=BG_INPUT)
            self.toggle_lbl.configure(bg=BG_INPUT)
        def on_leave(e):
            self.header.configure(bg=BG_PANEL)
            self.toggle_lbl.configure(bg=BG_PANEL)

        self.toggle_lbl.bind("<Enter>", on_enter)
        self.toggle_lbl.bind("<Leave>", on_leave)
        self.toggle_lbl.bind("<Button-1>", lambda e: self.toggle())

        self.content = tk.Frame(self, bg=BG_DARK, bd=0, highlightthickness=1, highlightbackground=BORDER_COLOR)
        if start_open:
            self.content.pack(fill=tk.X, expand=False, padx=2, pady=(2, 5))

    def toggle(self):
        if self.is_open:
            self.content.pack_forget()
            self.toggle_lbl.config(text="▶   " + self.text)
            self.is_open = False
        else:
            self.content.pack(fill=tk.X, expand=False, padx=2, pady=(2, 5))
            self.toggle_lbl.config(text="▼   " + self.text)
            self.is_open = True

class ChipListWidget(tk.Frame):
    """An interactive chip/tag list editor widget that transforms comma-separated text into tag chips."""
    def __init__(self, parent, bg_input, text_main, border_color, accent, bg_panel, text_muted, state_callback=None, *args, **kwargs):
        super().__init__(parent, bg=parent.cget("bg") if hasattr(parent, "cget") else BG_DARK, *args, **kwargs)
        self.bg_input = bg_input
        self.text_main = text_main
        self.border_color = border_color
        self.accent = accent
        self.bg_panel = bg_panel
        self.text_muted = text_muted
        self.state_callback = state_callback

        self.chips = []

        self.entry_frame = tk.Frame(self, bg=self.cget("bg"))
        self.entry_frame.pack(fill=tk.X)

        self.entry = tk.Entry(
            self.entry_frame,
            bg=bg_input,
            fg=text_main,
            insertbackground=text_main,
            font=("Segoe UI", 10),
            bd=0,
            highlightthickness=1,
            highlightbackground=border_color,
            highlightcolor=accent,
            relief="flat"
        )
        self.entry.pack(fill=tk.X, ipady=4)

        self.chips_frame = tk.Frame(self, bg=self.cget("bg"))
        self.chips_frame.pack(fill=tk.X, pady=(4, 0))

        self.entry.bind("<Return>", self._on_enter)
        self.entry.bind("<KeyRelease-comma>", self._on_comma)
        self.entry.bind("<FocusOut>", self._on_focus_out)

    def _on_enter(self, event):
        self._add_from_entry()
        return "break"

    def _on_comma(self, event):
        self._add_from_entry()
        return "break"

    def _on_focus_out(self, event):
        self._add_from_entry()

    def _add_from_entry(self):
        val = self.entry.get().strip()
        if val.endswith(","):
            val = val[:-1].strip()
        if val:
            parts = [p.strip() for p in val.split(",") if p.strip()]
            added = False
            for part in parts:
                if part not in self.chips:
                    self.chips.append(part)
                    added = True
            if added:
                if self.state_callback:
                    self.state_callback()
                self._redraw_chips()
            self.entry.delete(0, tk.END)

    def _redraw_chips(self):
        for w in self.chips_frame.winfo_children():
            w.destroy()

        self.chips_frame.update_idletasks()
        max_width = self.winfo_width()
        if max_width <= 1:
            max_width = 600

        current_row_frame = tk.Frame(self.chips_frame, bg=self.cget("bg"))
        current_row_frame.pack(fill=tk.X, anchor=tk.W)
        current_width = 0

        for idx, text in enumerate(self.chips):
            chip = tk.Frame(current_row_frame, bg=self.bg_panel, highlightthickness=1, highlightbackground=self.border_color, padx=6, pady=2)
            lbl = tk.Label(chip, text=text, bg=self.bg_panel, fg=self.text_main, font=("Segoe UI", 9))
            lbl.pack(side=tk.LEFT)

            btn = tk.Label(chip, text="×", bg=self.bg_panel, fg=self.text_muted, font=("Segoe UI", 10, "bold"), cursor="hand2")
            btn.pack(side=tk.LEFT, padx=(4, 0))
            btn.bind("<Button-1>", lambda e, t=text: self._remove_chip(t))

            btn.bind("<Enter>", lambda e, b=btn: b.config(fg=COLOR_DANGER))
            btn.bind("<Leave>", lambda e, b=btn: b.config(fg=self.text_muted))

            chip_width = len(text) * 7 + 45
            if current_width + chip_width > max_width and idx > 0:
                current_row_frame = tk.Frame(self.chips_frame, bg=self.cget("bg"))
                current_row_frame.pack(fill=tk.X, anchor=tk.W, pady=(4, 0))
                current_width = 0

            chip.pack(side=tk.LEFT, padx=(0, 4))
            current_width += chip_width + 4

    def _remove_chip(self, text):
        if text in self.chips:
            self.chips.remove(text)
            if self.state_callback:
                self.state_callback()
            self._redraw_chips()

    def get(self):
        current_entry = self.entry.get().strip()
        all_chips = list(self.chips)
        if current_entry:
            if current_entry.endswith(","):
                current_entry = current_entry[:-1].strip()
            if current_entry and current_entry not in all_chips:
                all_chips.append(current_entry)
        return ", ".join(all_chips)

    def delete(self, first, last=None):
        self.chips = []
        self.entry.delete(0, tk.END)
        self._redraw_chips()

    def insert(self, index, value):
        if value:
            self.chips = [item.strip() for item in value.split(",") if item.strip()]
        else:
            self.chips = []
        self._redraw_chips()

    def configure(self, **kwargs):
        entry_kwargs = {}
        for key in ["bg", "highlightbackground", "highlightcolor"]:
            if key in kwargs:
                entry_kwargs[key] = kwargs[key]

        if entry_kwargs:
            self.entry.configure(**entry_kwargs)

        super_kwargs = {k: v for k, v in kwargs.items() if k not in ["bg", "highlightbackground", "highlightcolor", "state"]}
        if super_kwargs:
            super().configure(**super_kwargs)

        if "state" in kwargs:
            state = kwargs["state"]
            self.entry.configure(state=state)
            if state == "disabled":
                self.entry.configure(bg=self.bg_panel)
            else:
                self.entry.configure(bg=self.bg_input)

    def bind(self, sequence=None, func=None, add=None):
        return self.entry.bind(sequence, func, add)

# --- Constants ---
PRESETS_FILE = os.path.join(get_base_path(), "presets.json")
BOT_SCRIPT = os.path.join(get_base_path(), "mudae_bot.py")

# Default values (for display hints)
DEFAULTS = {
    "token": "",
    "prefix": "/////////////",
    "mudae_prefix": "$",
    "channel_id": "",
    "command_channel_id": "",
    "roll_command": "wa",
    "min_kakera": 100,
    "delay_seconds": 0,
    "start_delay": 0,
    "auto_p_enabled": True,
    "auto_oh_enabled": False,
    "auto_oc_enabled": False,
    "roll_speed": 0.4,
    "snipe_delay": 2,
    "series_snipe_delay": 3,
    "kakera_snipe_threshold": 0,
    "kakera_reaction_snipe_delay": 0.75,
    "humanization_window_minutes": 40,
    "humanization_inactivity_seconds": 5,
    "reactive_snipe_delay": 0,
    "reactive_kakera_delay_range": [0.3, 1.0],
    "claim_interval": 180,
    "roll_interval": 60,
    "avoid_list": [],
    "auto_us_enabled": False,
    "auto_us_limit": 0,
    "auto_us_stop_on_claim": True,
    "bulk_us_enabled": False,
    "auto_mk_enabled": True,
    "auto_rolls_enabled": False,
    "auto_rolls_limit": 0,
    "auto_rolls_in_key_mode": False,
    "auto_rolls_only_claim_hour": False,
    "panic_roll_minutes": 5,
    "lurker_mode": False,
    "auto_rt_after_claim": False,
    "auto_dk_enabled": True,
    "max_dk_power": 100,
    "randomized_claim_reactions": ["💖", "💗", "💘", "❤️", "👍", "🔥"],
    "main_account_id": "",
    "scheduled_roll_times": [],
    "kakera_priority_order": ["kakeraP", "kakeraC", "kakeraL", "kakeraW", "kakeraR", "kakeraO", "kakeraD", "kakeraY", "kakeraG", "kakeraT", "kakera"],
    "enable_snipe_chat_reactions": False,
    "snipe_chat_messages": ["omg", "ezz"],
    "farm_character": "",
    "farm_character_enabled": False,
    "farm_forcedivorce_before_roll": False,
    "farm_forcedivorce_after_claim": False,
    "farm_forcedivorce_after_other_claim": False,
    "op_perk_5_only": False,
    "auto_divorce_enabled": False,
    "auto_divorce_max_kakera": 50,
    "auto_divorce_series": [],
    "auto_divorce_blacklist": [],
    "auto_divorce_blacklist_series": [],
    "mk_bypass_power_check": False,
    "snipe_channels": [],
    "max_claim_rank": 0,
    "max_like_rank": 0,
    "enable_hybrid_panic_claim": False,
    "hybrid_panic_instant_claim_min_kakera": 300,
    "hybrid_panic_instant_claim_max_rank": 200,
    "claim_rounds_thresholds": [],
    "sphere_click_targets": ["spG", "spY", "spO", "spR", "spW", "spL", "spD", "spM", "spU"],
    "immediate_kakera_click": True,
    "character_snipe_targets": [],
}

# Boolean settings with their display names and defaults
BOOL_SETTINGS = [
    ("rolling", "Rolling Enabled (Turn off to only snipe without rolling yourself)", True),
    ("use_slash_rolls", "Use /slash commands (Earn 10% more Kakera)", False),
    ("snipe_mode", "Snipe Characters (Claim characters rolled by other people)", False),
    ("snipe_ignore_min_kakera_reset", "Panic Claim (Claim ANY character right before your timer resets)", False),
    ("series_snipe_mode", "Series Sniping (Auto-claim any character from specific shows/games)", False),
    ("kakera_snipe_mode", "Value Sniping (Snipe expensive characters rolled by others)", False),
    ("kakera_reaction_snipe_mode", "Auto-Collect Kakera (Click crystals on other people's rolls)", False),
    ("reactive_snipe_on_own_rolls", "Instant Self-Claim (Immediately claim your own good rolls)", True),
    ("key_mode", "Key Farming Mode (Keep rolling to earn keys even if you can't claim)", False),
    ("only_chaos", "Chaos Kakera Only (Only click crystals that cost 50% less power)", False),
    ("mk_only", "MK Kakera Only (Ignore normal kakera, ONLY click crystals from your $mk rolls)", False),
    ("humanization_enabled", "Timing Variation (Randomizes timing; does not prevent detection or bans)", False),
    ("auto_dk_enabled", "Auto $dk (Automatically use $dk when ready or low on power)", True),
    ("dk_power_management", "Smart Power Refill (Auto-use $dk when low on energy)", False),
    ("skip_initial_commands", "Fast Start (Skip initial setup commands on startup)", False),
    ("time_rolls_to_claim_reset", "Smart Timing (Finish rolling exactly when your claim resets)", False),
    ("rt_ignore_min_kakera_for_wishlist", "Restore for Wishlist (Use $rt for wishlisted characters regardless of value)", False),
    ("rt_only_self_rolls", "Private Restore (Only use $rt on characters YOU rolled)", False),
    ("auto_us_enabled", "Automatically Use Saved Rolls ($us)", False),
    ("auto_us_stop_on_claim", "Save Rolls (Stop using $us after claim)", True),
    ("bulk_us_enabled", "Bulk US Mode (Pull all saved rolls at once instead of in batches of 20)", False),
    ("auto_rolls_enabled", "Automatically Use Daily Rolls ($rolls)", False),
    ("auto_rolls_only_claim_hour", "Only Use Daily Rolls in Claim Hour (Only use $rolls during the hour claim resets)", False),
    ("auto_rolls_in_key_mode", "Use Daily Rolls for Keys (Use $rolls even when you can't claim)", False),
    ("autostart", "Start with Windows", False),
    ("debug_mode", "Expert Logs (Show technical data for every single roll)", False),
    ("auto_mk_enabled", "Automatically Use Extra Kakera Rolls ($mk)", True),
    ("lurker_mode", "Lurker Strategy (Wait for others to roll while sniping - Panic dump at the end)", False),
    ("auto_rt_after_claim", "Auto $rt After Claim (Also controls $rt for Kakera farm claims)", False),
    ("enable_snipe_chat_reactions", "Snipe Chat Reactions (Send a random message after a successful external snipe)", False),
    ("op_perk_5_only", "Only Click Kakera on $op (Perk 5) Characters", False),
    ("farm_character_enabled", "Enable Kakera Farming Loop (Auto-Forcedivorce)", False),
    ("farm_forcedivorce_before_roll", "Forcedivorce Before Rolling (Solo/Startup Cleanup)", False),
    ("farm_forcedivorce_after_claim", "Forcedivorce After Own Verified Claim", False),
    ("farm_forcedivorce_after_other_claim", "Forcedivorce After Another Account Claims (Shared Server Mode)", False),
    ("auto_divorce_enabled", "Auto-Divorce (Automatically separate characters after claiming them)", False),
    ("mk_bypass_power_check", "Force $mk Rolls (Use $mk even when power is too low for normal kakera)", False),
    ("enable_hybrid_panic_claim", "Hybrid Smart Panic Claim (Instantly claim high-value characters in the last claim hour, collect others)", False),
    ("immediate_kakera_click", "Immediate Kakera Click (Click crystals instantly instead of waiting for all rolls to finish)", True),
    ("auto_p_enabled", "Auto $p (Automatically claim pokemon when available)", True),
    ("auto_oh_enabled", "Auto $oh (Automatically play Sphere Harvest when available)", False),
    ("auto_oc_enabled", "Auto $oc (Automatically solve Sphere Chest when available)", False),
]

# Numeric settings with their display names, defaults, and types
NUMERIC_SETTINGS = [
    ("min_kakera", "Minimum Value to Claim (Claim if character is worth this much)", 100, int),
    ("delay_seconds", "Wait Time Before Checking Commands (seconds)", 0, float),
    ("start_delay", "Wait Before Starting (seconds)", 0, int),
    ("roll_speed", "Rolling Speed (Seconds between each roll)", 0.4, float),
    ("snipe_delay", "Snipe Wait Time (Wait X seconds before stealing a roll)", 2, float),
    ("series_snipe_delay", "Series Snipe Wait Time (Wait X seconds before stealing from series)", 3, float),
    ("kakera_snipe_threshold", "Minimum Value to Steal (Only steal if worth this much)", 0, int),
    ("kakera_reaction_snipe_delay", "Kakera Collection Delay (How fast to click others' crystals)", 0.75, float),
    ("humanization_window_minutes", "Random Wait Time (minutes) to Look Like a Real Human", 40, int),
    ("humanization_inactivity_seconds", "Patience (Wait for X seconds of no chat before rolling)", 5, int),
    ("reactive_snipe_delay", "Self-Claim Delay (Seconds to wait before claiming your own rolls)", 0, float),
    ("claim_interval", "Claim Timer (Minutes until you get a new claim right)", 180, int),
    ("roll_interval", "Roll Timer (Minutes until your rolls refresh)", 60, int),
    ("auto_us_limit", "Maximum Saved Rolls to Use per Hour", 0, int),
    ("auto_rolls_limit", "Maximum times to use daily rolls (0 = unlimited)", 0, int),
    ("panic_roll_minutes", "Panic Roll Start (Minutes before claim reset)", 5, int),
    ("auto_divorce_max_kakera", "Auto-Divorce Kakera Threshold (Divorce if value <= this)", 50, int),
    ("max_claim_rank", "Maximum Claims Rank Limit (e.g. 500 to claim any character ranked #1-#500. 0 = disabled)", 0, int),
    ("max_like_rank", "Maximum Likes Rank Limit (e.g. 300 to claim any character ranked #1-#300. 0 = disabled)", 0, int),
    ("hybrid_panic_instant_claim_min_kakera", "Hybrid Instant Claim Min Kakera (Minimum value to claim instantly in panic hour)", 300, int),
    ("hybrid_panic_instant_claim_max_rank", "Hybrid Instant Claim Max Rank Limit (Rank <= this to claim instantly in panic hour)", 200, int),
]

# Text/list settings
TEXT_SETTINGS = [
    ("token", "Discord Account Token (REQUIRED: Your secret account key)", "", False),  # (key, label, default, is_list)
    ("prefix", "Self-Bot Prefix (Command prefix for controlling the bot)", "/////////////", False),
    ("mudae_prefix", "Mudae Game Prefix (Usually $)", "$", False),
    ("channel_id", "Discord Channel ID (Where the bot should roll)", "", False),
    ("roll_command", "Roll Type (wa, ha, ma, etc.)", "wa", False),
    ("wishlist", "Character Wishlist (Names of characters you want to auto-claim)", [], True),
    ("series_wishlist", "Series Wishlist (Shows or Games you want to auto-claim)", [], True),
    ("avoid_list", "Blacklisted Characters (Names of characters to NEVER claim)", [], True),
    ("kakera_reaction_snipe_targets", "Target User IDs (Only steal Kakera from these specific users)", [], True),
    ("farm_character", "Kakera Farm Character (Name of character to endlessly forcedivorce/claim)", "", False),
    ("auto_divorce_series", "Auto-Divorce Series (Divorce if character is from these series)", [], True),
    ("auto_divorce_blacklist", "Divorce Blacklist (Characters to NEVER divorce)", [], True),
    ("auto_divorce_blacklist_series", "Divorce Blacklist Series (Series to NEVER divorce)", [], True),
    ("snipe_channels", "Target Snipe Channels (Comma-separated IDs of external channels to monitor for sniping)", [], True),
    ("sphere_click_targets", "Target Sphere Emojis (Comma-separated list of sphere emojis to click, e.g., spU, spG, spY)", ["spG", "spY", "spO", "spR", "spW", "spL", "spD", "spM", "spU"], True),
    ("character_snipe_targets", "Target Character Snipe Users (Comma-separated IDs or usernames. Only snipe from these players. Leave empty to snipe everyone).", [], True),
]

# Default emoji values
DEFAULT_CLAIM_EMOJIS = ['💖', '💗', '💘', '❤️', '💓', '💕', '♥️']
DEFAULT_KAKERA_EMOJIS = ['kakeraY', 'kakeraO', 'kakeraR', 'kakeraW', 'kakeraL', 'kakeraP', 'kakeraD', 'kakeraC', 'kakera']
DEFAULT_CHAOS_EMOJIS = ['kakeraY', 'kakeraO', 'kakeraR', 'kakeraW', 'kakeraL', 'kakeraP', 'kakeraD', 'kakeraC', 'kakera']
DEFAULT_SPHERE_PERK_EMOJIS = ['kakeraY', 'kakeraO', 'kakeraR', 'kakeraW', 'kakeraL', 'kakeraP', 'kakeraD', 'kakeraC', 'kakera']

# [NEW] Task 5: Default randomized claim reaction emojis
DEFAULT_RANDOMIZED_CLAIM_REACTIONS = ['💖', '💗', '💘', '❤️', '👍', '🔥']

# [NEW] Task 8: Default kakera priority order
DEFAULT_KAKERA_PRIORITY_ORDER = ['kakeraP', 'kakeraC', 'kakeraL', 'kakeraW', 'kakeraR', 'kakeraO', 'kakeraD', 'kakeraY', 'kakeraG', 'kakeraT', 'kakera']

# [NEW] Default snipe chat reaction messages
DEFAULT_SNIPE_CHAT_MESSAGES = ['omg', 'ezz']


class PresetEditor:
    def __init__(self, root):
        self.root = root
        self.root.title("MudaRemote Preset Editor")
        self.root.geometry("900x700")
        self.root.minsize(800, 600)

        # Track unsaved edits
        self.is_dirty = False
        self.loading_preset = False

        # Apply dark theme
        self.apply_theme()

        # Data
        self.presets = {}
        self.current_preset = None
        self.widgets = {}  # Store widget references for data binding
        self.settings_fields = []  # References for real-time search/filter
        self.subframe_controls = {}  # Map of subframe -> control_key
        self.secret_store = SecretStore(get_base_path())
        self.bot_processes = {}
        self._round_count = 0

        # Load presets
        self.load_presets()

        # Build UI
        self.build_ui()

        # Bind close window protocol
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # Select first preset if exists
        if self.presets:
            first_preset = list(self.presets.keys())[0]
            self.select_preset(first_preset)

    def on_close(self):
        """Prompt to save changes when closing the window."""
        if self.prompt_unsaved_changes():
            self.root.destroy()

    def mark_dirty(self, event=None):
        """Mark the configuration as modified and update the window title."""
        if self.loading_preset:
            return
        if not self.is_dirty:
            self.is_dirty = True
            if self.current_preset:
                self.title_label.config(text=f"Editing: {self.current_preset} *")

    def prompt_unsaved_changes(self):
        """Prompt the user if they have unsaved changes. Returns True if safe to proceed, False otherwise."""
        if not self.is_dirty:
            return True

        ans = messagebox.askyesnocancel(
            "Unsaved Changes",
            f"You have unsaved changes in '{self.current_preset}'. Do you want to save them before proceeding?",
            parent=self.root
        )
        if ans is True:  # Yes, save and proceed
            self.save_current_preset()
            # If save was aborted due to validation error, is_dirty remains True
            return not self.is_dirty
        elif ans is False:  # No, discard changes and proceed
            self.is_dirty = False
            return True
        else:  # Cancel
            return False

    def update_listbox_selection(self, preset_name):
        """Helper to restore listbox selection to avoid UI desync."""
        for i in range(self.preset_listbox.size()):
            if self.preset_listbox.get(i) == preset_name:
                self.preset_listbox.selection_clear(0, tk.END)
                self.preset_listbox.selection_set(i)
                break

    def apply_theme(self):
        """Apply the premium Catppuccin Mocha style palette."""
        self.root.configure(bg=BG_DARK)

        style = ttk.Style()
        style.theme_use("clam")

        style.configure(".", background=BG_DARK, foreground=TEXT_MAIN, fieldbackground=BG_PANEL)
        style.configure("TFrame", background=BG_DARK)
        style.configure("Card.TFrame", background=BG_PANEL)
        style.configure("TLabel", background=BG_DARK, foreground=TEXT_MAIN, font=("Segoe UI", 10))
        style.configure("TLabelframe", background=BG_DARK, foreground=TEXT_MAIN, borderwidth=1, bordercolor=BORDER_COLOR)
        style.configure("TLabelframe.Label", background=BG_DARK, foreground=ACCENT, font=("Segoe UI", 11, "bold"))
        style.configure("TEntry", fieldbackground=BG_INPUT, foreground=TEXT_MAIN, insertcolor=TEXT_MAIN, borderwidth=0)
        style.configure("TCheckbutton", background=BG_DARK, foreground=TEXT_MAIN, font=("Segoe UI", 10))
        style.map("TCheckbutton", background=[("active", BG_DARK)])
        style.configure("TScrollbar", gripcount=0, background=BG_PANEL, troughcolor=BG_DARK, borderwidth=0, arrowsize=8)

        # Ttk Button styling (used primarily for secondary scrollbars/internal fallback buttons)
        style.configure("TButton", background=BG_PANEL, foreground=TEXT_MAIN, font=("Segoe UI", 10, "bold"), borderwidth=1, bordercolor=BORDER_COLOR, padding=8)
        style.map("TButton", background=[("active", BG_INPUT)])

        self.listbox_config = {
            "bg": BG_PANEL,
            "fg": TEXT_MAIN,
            "selectbackground": ACCENT,
            "selectforeground": BG_DARK,
            "font": ("Segoe UI", 10),
            "borderwidth": 0,
            "highlightthickness": 0,
            "relief": "flat",
            "activestyle": "none"
        }

    def _bind_focus_highlight(self, entry):
        """Binds focus highlighting to text inputs to transition borders dynamically."""
        def on_focus_in(e):
            entry.configure(bg="#313244", highlightbackground=ACCENT, highlightcolor=ACCENT)
        def on_focus_out(e):
            entry.configure(bg=BG_INPUT, highlightbackground=BORDER_COLOR, highlightcolor=ACCENT)

        entry.bind("<FocusIn>", on_focus_in, add="+")
        entry.bind("<FocusOut>", on_focus_out, add="+")

    def _bind_hover_animation(self, button, normal_bg, hover_bg):
        """Transition background color smoothly on hover."""
        def on_enter(e):
            button.configure(bg=hover_bg)
        def on_leave(e):
            button.configure(bg=normal_bg)

        button.bind("<Enter>", on_enter)
        button.bind("<Leave>", on_leave)

    def create_flat_button(self, parent, text, command, bg_color, fg_color, hover_bg, font=("Segoe UI", 10, "bold"), **kwargs):
        """Create a premium borderless flat button with hover animations."""
        btn = tk.Button(
            parent,
            text=text,
            command=command,
            bg=bg_color,
            fg=fg_color,
            font=font,
            bd=0,
            relief="flat",
            activebackground=hover_bg,
            activeforeground=fg_color,
            padx=15,
            pady=8,
            cursor="hand2"
        )
        self._bind_hover_animation(btn, bg_color, hover_bg)
        return btn

    def _get_parent_bg(self, parent):
        """Safely retrieve background color of a parent widget, defaulting to BG_DARK."""
        if not parent:
            return BG_DARK
        try:
            return parent.cget("bg")
        except Exception:
            try:
                return parent.cget("background")
            except Exception:
                return BG_DARK

    def _register_settings_widget(self, parent, container, label_text, key):
        """Register setting widget reference for real-time search & filter indexing."""
        card = None
        curr = parent
        while curr:
            if isinstance(curr, CollapsibleLabelFrame):
                card = curr
                break
            try:
                curr = curr.master
            except AttributeError:
                break
        self.settings_fields.append({
            "card": card,
            "container": container,
            "label_text": label_text.lower(),
            "key": key.lower()
        })

    def _get_all_collapsible_cards(self):
        """Locates all collapsible layout panels inside settings form."""
        cards = []
        for widget in self.scrollable_frame.winfo_children():
            if isinstance(widget, CollapsibleLabelFrame):
                cards.append(widget)
            elif isinstance(widget, ttk.Frame) or isinstance(widget, tk.Frame):
                for sub in widget.winfo_children():
                    if isinstance(sub, CollapsibleLabelFrame):
                        cards.append(sub)
        return cards

    def _filter_container_children(self, parent_widget, query):
        """Recursively hides/shows children of a parent container maintaining original pack order."""
        if hasattr(self, "rounds_frame") and parent_widget == self.rounds_frame:
            # Do not filter or unpack grid-managed children of the rounds table
            # Check if search query matches round-related keywords to show/hide the table block
            rounds_title = "dynamic cooldown rounds (hourly thresholds)"
            return not query or query in rounds_title or "round" in query or "cooldown" in query or "hour" in query

        any_match = False

        # Hide all children first to reset packing order
        for child in parent_widget.winfo_children():
            child.pack_forget()

        for child in parent_widget.winfo_children():
            # Check if this child is a registered settings container
            settings_item = None
            for item in self.settings_fields:
                if item["container"] == child:
                    settings_item = item
                    break

            if settings_item:
                lbl = settings_item["label_text"]
                key = settings_item["key"]
                if not query or query in lbl or query in key:
                    child.pack(fill=tk.X, pady=5)
                    any_match = True
            elif isinstance(child, (tk.Frame, ttk.Frame, tk.LabelFrame)):
                # Filter its children recursively
                sub_match = self._filter_container_children(child, query)

                # Check if it is a subframe controlled by a checkbox
                if child in self.subframe_controls:
                    ctrl_key = self.subframe_controls[child]
                    ctrl_var = self.widgets.get(ctrl_key)
                    is_enabled = ctrl_var.get() if (ctrl_var and isinstance(ctrl_var, tk.BooleanVar)) else False

                    if is_enabled and (not query or sub_match):
                        child.pack(fill=tk.X, padx=(20, 0), pady=2)
                        any_match = any_match or sub_match
                else:
                    # It's a general layout frame (like prefix_row or rounds_frame)
                    if not query or sub_match:
                        if child == self.rounds_frame:
                            child.pack(fill=tk.X, pady=10)
                        else:
                            child.pack(fill=tk.X, pady=5)
                        any_match = any_match or sub_match
            elif isinstance(child, (tk.Label, ttk.Label)):
                # Static description label
                text = child.cget("text").lower()
                if not query or query in text:
                    # Keep its original padding if it is the uncheck defaults label
                    if "uncheck to use defaults" in text:
                        child.pack(anchor=tk.W, pady=(0, 10))
                    else:
                        child.pack(anchor=tk.W)

        return any_match

    def filter_settings(self, *args):
        """Real-time filter for all settings sections and inputs."""
        if not hasattr(self, "scrollable_frame") or not hasattr(self, "settings_search_var"):
            return
        query = self.settings_search_var.get().strip().lower()
        if query == "🔍 search settings (e.g., snipe, rolls, cooldown)..." or not query:
            query = ""

        cards_with_matches = set()
        cards_to_open = set()

        # Recursively filter content children for each collapsible card
        for card in self._get_all_collapsible_cards():
            has_match = self._filter_container_children(card.content, query)
            if has_match:
                cards_with_matches.add(card)
                if query:
                    cards_to_open.add(card)

        # Repack all top-level child widgets of self.scrollable_frame in their original order
        # Hide all first
        for child in self.scrollable_frame.winfo_children():
            child.pack_forget()

        # Repack sequentially in original creation order
        for child in self.scrollable_frame.winfo_children():
            if child == self.title_label:
                child.pack(anchor=tk.W, pady=(0, 20))
            elif hasattr(self, "btn_frame") and child == self.btn_frame:
                child.pack(fill=tk.X, pady=20)
            elif isinstance(child, CollapsibleLabelFrame):
                if not query or child in cards_with_matches:
                    child.pack(fill=tk.X, pady=(0, 15))
                    if query and child in cards_to_open and not child.is_open:
                        child.toggle()
            elif isinstance(child, (tk.Frame, ttk.Frame)):
                # It could be a wrapper frame (like roll_outer, us_outer, human_outer, char_snipe_outer, kakera_react_outer)
                inner_card = None
                for sub in child.winfo_children():
                    if isinstance(sub, CollapsibleLabelFrame):
                        inner_card = sub
                        break

                if inner_card:
                    if not query or inner_card in cards_with_matches:
                        child.pack(fill=tk.X, pady=(0, 15))
                        inner_card.pack(fill=tk.X)
                        if query and inner_card in cards_to_open and not inner_card.is_open:
                            inner_card.toggle()
                else:
                    # General frame packed at top level
                    if not query:
                        child.pack(fill=tk.X, pady=5)

    def filter_presets(self, *args):
        """Real-time search filters for configurations sidebar."""
        if not hasattr(self, "preset_listbox") or not hasattr(self, "preset_search_var"):
            return
        query = self.preset_search_var.get().strip().lower()
        if query == "🔍 search configs..." or not query:
            query = ""

        self.preset_listbox.delete(0, tk.END)
        for name in sorted(self.presets.keys()):
            if not query or query in name.lower():
                self.preset_listbox.insert(tk.END, name)

    def load_presets(self):
        """Load presets from JSON file."""
        if os.path.exists(PRESETS_FILE):
            try:
                self.presets = load_json(PRESETS_FILE, {})
                migrated = False
                for preset_name, data in self.presets.items():
                    if "farm_forcedivorce_before_roll" not in data:
                        data["farm_forcedivorce_before_roll"] = (
                            bool(data.get("farm_character_enabled", False))
                            and not bool(data.get("farm_forcedivorce_after_claim", False))
                            and not bool(data.get("farm_forcedivorce_after_other_claim", False))
                        )
                        migrated = True
                    legacy_token = str(data.get("token", "") or "")
                    if legacy_token:
                        try:
                            self.secret_store.set_token(preset_name, legacy_token)
                            data["token"] = ""
                            migrated = True
                        except SecretStoreError:
                            # Keep the legacy value until secure storage is available.
                            pass
                if migrated:
                    try:
                        atomic_write_json(PRESETS_FILE, self.presets)
                    except Exception as exc:
                        messagebox.showwarning("Token Migration", f"Tokens were secured, but presets.json could not be cleaned:\n{exc}")
            except json.JSONDecodeError as e:
                messagebox.showerror("Loading Error", f"Oops! I couldn't read your configurations:\n{e}")
                self.presets = {}
            except Exception as e:
                messagebox.showerror("Loading Error", f"I had trouble loading your saved data:\n{e}")
                self.presets = {}
        else:
            self.presets = {}

    def save_presets(self):
        """Save presets to JSON file."""
        try:
            atomic_write_json(PRESETS_FILE, self.presets)
            return True
        except Exception as e:
            messagebox.showerror("Save Error", f"Could not save your changes:\n{e}")
            return False

    def build_ui(self):
        """Build the main UI with a modern design system."""
        # Main container
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)

        # Left sidebar - Preset list
        sidebar = tk.Frame(main_frame, width=220, bg=BG_DARK)
        sidebar.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 15))
        sidebar.pack_propagate(False)

        tk.Label(sidebar, text="Bot Configurations", font=("Segoe UI", 13, "bold"), bg=BG_DARK, fg=TEXT_MAIN).pack(anchor=tk.W, pady=(0, 10))

        # Configs Search Entry
        self.preset_search_var = tk.StringVar()
        self.preset_search_var.trace_add("write", self.filter_presets)

        preset_search = tk.Entry(
            sidebar,
            textvariable=self.preset_search_var,
            bg=BG_INPUT,
            fg=TEXT_MAIN,
            insertbackground=TEXT_MAIN,
            font=("Segoe UI", 10),
            bd=0,
            highlightthickness=1,
            highlightbackground=BORDER_COLOR,
            highlightcolor=ACCENT,
            relief="flat"
        )
        preset_search.pack(fill=tk.X, pady=(0, 10), ipady=6)

        # Placeholder
        preset_search.insert(0, "🔍 Search configs...")
        preset_search.configure(fg=TEXT_MUTED)

        def on_ps_focus_in(e):
            if preset_search.get() == "🔍 Search configs...":
                preset_search.delete(0, tk.END)
                preset_search.configure(fg=TEXT_MAIN)
        def on_ps_focus_out(e):
            if not preset_search.get():
                preset_search.insert(0, "🔍 Search configs...")
                preset_search.configure(fg=TEXT_MUTED)

        preset_search.bind("<FocusIn>", on_ps_focus_in)
        preset_search.bind("<FocusOut>", on_ps_focus_out)
        self._bind_focus_highlight(preset_search)

        # Preset listbox
        # Wrap it in a frame to give it a clean border
        listbox_border = tk.Frame(sidebar, bg=BORDER_COLOR, bd=0, highlightbackground=BORDER_COLOR, highlightthickness=1)
        listbox_border.pack(fill=tk.BOTH, expand=True)

        self.preset_listbox = tk.Listbox(listbox_border, **self.listbox_config)
        self.preset_listbox.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        self.preset_listbox.bind("<<ListboxSelect>>", self.on_preset_select)

        # Refresh preset list
        self.refresh_preset_list()

        # Sidebar buttons (using flat custom buttons)
        sidebar_btns = tk.Frame(sidebar, bg=BG_DARK)
        sidebar_btns.pack(fill=tk.X, pady=(15, 0))

        self.create_flat_button(
            sidebar_btns, "+ Create New", self.create_preset,
            bg_color=ACCENT, fg_color=BG_DARK, hover_bg=ACCENT_ALT, font=("Segoe UI", 9, "bold")
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        self.create_flat_button(
            sidebar_btns, "Copy Selected", self.duplicate_preset,
            bg_color=BG_PANEL, fg_color=TEXT_MAIN, hover_bg=BG_INPUT, font=("Segoe UI", 9, "bold")
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.create_flat_button(
            sidebar, "📤 Share Preset", self.share_preset,
            bg_color=BG_PANEL, fg_color=TEXT_MAIN, hover_bg=BG_INPUT, font=("Segoe UI", 9, "bold")
        ).pack(fill=tk.X, pady=(5, 0))

        # Right side - Settings panel
        self.settings_container = tk.Frame(main_frame, bg=BG_DARK)
        self.settings_container.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Settings Search Frame at the top of settings
        search_frame = tk.Frame(self.settings_container, bg=BG_DARK, bd=0)
        search_frame.pack(fill=tk.X, pady=(0, 10))

        self.settings_search_var = tk.StringVar()
        self.settings_search_var.trace_add("write", self.filter_settings)

        self.settings_search_entry = tk.Entry(
            search_frame,
            textvariable=self.settings_search_var,
            bg=BG_INPUT,
            fg=TEXT_MAIN,
            insertbackground=TEXT_MAIN,
            font=("Segoe UI", 10),
            bd=0,
            highlightthickness=1,
            highlightbackground=BORDER_COLOR,
            highlightcolor=ACCENT,
            relief="flat"
        )
        self.settings_search_entry.pack(fill=tk.X, ipady=6)

        # Placeholder
        self.settings_search_entry.insert(0, "🔍 Search settings (e.g., snipe, rolls, cooldown)...")
        self.settings_search_entry.configure(fg=TEXT_MUTED)

        def on_ss_focus_in(e):
            if self.settings_search_entry.get() == "🔍 Search settings (e.g., snipe, rolls, cooldown)...":
                self.settings_search_entry.delete(0, tk.END)
                self.settings_search_entry.configure(fg=TEXT_MAIN)
        def on_ss_focus_out(e):
            if not self.settings_search_entry.get():
                self.settings_search_entry.insert(0, "🔍 Search settings (e.g., snipe, rolls, cooldown)...")
                self.settings_search_entry.configure(fg=TEXT_MUTED)

        self.settings_search_entry.bind("<FocusIn>", on_ss_focus_in)
        self.settings_search_entry.bind("<FocusOut>", on_ss_focus_out)
        self._bind_focus_highlight(self.settings_search_entry)

        # Scrollable settings area; action buttons live in a fixed footer below it.
        scroll_area = tk.Frame(self.settings_container, bg=BG_DARK)
        scroll_area.pack(fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(scroll_area, bg=BG_DARK, highlightthickness=0)
        scrollbar = ttk.Scrollbar(scroll_area, orient=tk.VERTICAL, command=self.canvas.yview)
        self.scrollable_frame = tk.Frame(self.canvas, bg=BG_DARK)

        self.scrollable_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

        self.canvas_window = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor=tk.NW)
        self.canvas.bind("<Configure>", lambda event: self.canvas.itemconfigure(self.canvas_window, width=event.width))
        self.canvas.configure(yscrollcommand=scrollbar.set)

        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.footer_frame = tk.Frame(self.settings_container, bg=BG_DARK, highlightthickness=1, highlightbackground=BORDER_COLOR)
        self.footer_frame.pack(fill=tk.X, pady=(10, 0), ipady=8)

        # Bind mousewheel
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind_all("<Button-4>", self._on_mousewheel)
        self.canvas.bind_all("<Button-5>", self._on_mousewheel)

        # Build settings form
        self.build_settings_form()

    def _on_mousewheel(self, event):
        if getattr(event, "num", None) == 4:
            delta = -1
        elif getattr(event, "num", None) == 5:
            delta = 1
        else:
            raw_delta = getattr(event, "delta", 0)
            delta = -1 if raw_delta > 0 else 1 if raw_delta < 0 else 0
        if delta:
            self.canvas.yview_scroll(delta, "units")

    def rebuild_rounds_frame(self, claim_interval_mins, preserve=True):
        """Dynamically generate round row inputs based on claim interval."""
        num_rounds = max(1, math.ceil(claim_interval_mins / 60))
        if preserve and num_rounds == self._round_count:
            return

        previous_values = {}
        if preserve:
            for key, widget in list(self.widgets.items()):
                if key.startswith("round_") and hasattr(widget, "get"):
                    previous_values[key] = widget.get()

        for key in [key for key in self.widgets if key.startswith("round_")]:
            del self.widgets[key]

        # Clear existing widgets inside the rounds_frame
        for widget in self.rounds_frame.winfo_children():
            widget.destroy()

        # Re-draw the table headers
        headers = ["Round / Hour", "Min Kakera", "Max Claim Rank", "Max Like Rank"]
        for col_idx, text in enumerate(headers):
            lbl = tk.Label(self.rounds_frame, text=text, font=("Segoe UI", 9, "bold"), bg=BG_DARK, fg=ACCENT)
            lbl.grid(row=0, column=col_idx, padx=5, pady=2, sticky=tk.W)

        # Generate exactly num_rounds input rows
        for i in range(1, num_rounds + 1):
            lbl_round = tk.Label(self.rounds_frame, text=f"Round {i} (Hour {i})", font=("Segoe UI", 9), bg=BG_DARK, fg=TEXT_MAIN)
            lbl_round.grid(row=i, column=0, padx=5, pady=2, sticky=tk.W)

            ent_min_k = tk.Entry(
                self.rounds_frame,
                width=12,
                bg=BG_INPUT,
                fg=TEXT_MAIN,
                insertbackground=TEXT_MAIN,
                font=("Segoe UI", 9),
                bd=0,
                highlightthickness=1,
                highlightbackground=BORDER_COLOR,
                highlightcolor=ACCENT,
                relief="flat"
            )
            ent_min_k.grid(row=i, column=1, padx=5, pady=2, sticky=tk.W)
            self.widgets[f"round_{i}_min_kakera"] = ent_min_k
            if previous_values.get(f"round_{i}_min_kakera"):
                ent_min_k.insert(0, previous_values[f"round_{i}_min_kakera"])
            self._bind_focus_highlight(ent_min_k)
            ent_min_k.bind("<Key>", lambda e: self.mark_dirty())

            ent_max_claim = tk.Entry(
                self.rounds_frame,
                width=12,
                bg=BG_INPUT,
                fg=TEXT_MAIN,
                insertbackground=TEXT_MAIN,
                font=("Segoe UI", 9),
                bd=0,
                highlightthickness=1,
                highlightbackground=BORDER_COLOR,
                highlightcolor=ACCENT,
                relief="flat"
            )
            ent_max_claim.grid(row=i, column=2, padx=5, pady=2, sticky=tk.W)
            self.widgets[f"round_{i}_max_claim_rank"] = ent_max_claim
            if previous_values.get(f"round_{i}_max_claim_rank"):
                ent_max_claim.insert(0, previous_values[f"round_{i}_max_claim_rank"])
            self._bind_focus_highlight(ent_max_claim)
            ent_max_claim.bind("<Key>", lambda e: self.mark_dirty())

            ent_max_like = tk.Entry(
                self.rounds_frame,
                width=12,
                bg=BG_INPUT,
                fg=TEXT_MAIN,
                insertbackground=TEXT_MAIN,
                font=("Segoe UI", 9),
                bd=0,
                highlightthickness=1,
                highlightbackground=BORDER_COLOR,
                highlightcolor=ACCENT,
                relief="flat"
            )
            ent_max_like.grid(row=i, column=3, padx=5, pady=2, sticky=tk.W)
            self.widgets[f"round_{i}_max_like_rank"] = ent_max_like
            if previous_values.get(f"round_{i}_max_like_rank"):
                ent_max_like.insert(0, previous_values[f"round_{i}_max_like_rank"])
            self._bind_focus_highlight(ent_max_like)
            ent_max_like.bind("<Key>", lambda e: self.mark_dirty())
        self._round_count = num_rounds

    def refresh_preset_list(self):
        """Refresh the preset listbox."""
        self.preset_listbox.delete(0, tk.END)
        for name in sorted(self.presets.keys()):
            self.preset_listbox.insert(tk.END, name)

    def build_settings_form(self):
        """Build the settings form inside the scrollable frame."""
        frame = self.scrollable_frame

        # Clear existing widgets
        for widget in frame.winfo_children():
            widget.destroy()
        self.widgets = {}

        self.title_label = tk.Label(frame, text="Select a config to start", font=("Segoe UI", 16, "bold"), bg=BG_DARK, fg=TEXT_MAIN)
        self.title_label.pack(anchor=tk.W, pady=(0, 20))

        # --- Connection ---
        core_frame = CollapsibleLabelFrame(frame, text="Connection (Essential Setup)", start_open=True)
        core_frame.pack(fill=tk.X, pady=(0, 15))

        self.add_text_field(core_frame.content, "token", "Discord Account Token (REQUIRED: Your secret account key)", show="*")
        self.add_text_field(core_frame.content, "channel_id", "Discord Channel ID (Where the bot should roll)")
        self.add_text_field(core_frame.content, "command_channel_id", "Command Channel ID (Optional: For $tu, $daily, $dk — leave empty to use roll channel)")

        prefix_row = ttk.Frame(core_frame.content)
        prefix_row.pack(fill=tk.X, pady=5)
        self.add_text_field(prefix_row, "prefix", "Self-Bot Prefix", pack_side=tk.LEFT)
        self.add_text_field(prefix_row, "mudae_prefix", "Mudae Game Prefix", pack_side=tk.LEFT)

        self.add_text_field(core_frame.content, "roll_command", "Roll Type (wa, ha, ma, etc.)")
        self.add_number_field(core_frame.content, "delay_seconds", "Wait Time Before Checking Commands (seconds)", 0)
        self.add_number_field(core_frame.content, "start_delay", "Wait Before Starting (seconds)", 0)
        self.add_checkbox(core_frame.content, "autostart", "Start with Windows")

        # --- Rolling ---
        roll_outer = ttk.Frame(frame)
        roll_outer.pack(fill=tk.X, pady=(0, 15))
        roll_frame = CollapsibleLabelFrame(roll_outer, text="Rolling Options", start_open=False)
        roll_frame.pack(fill=tk.X)

        rolling_var = self.add_checkbox(roll_frame.content, "rolling", "Rolling Enabled (Turn off to only snipe without rolling yourself)")
        roll_sub = self.create_subframe(roll_frame.content, rolling_var, "rolling")

        self.add_checkbox(roll_sub, "use_slash_rolls", "Use /slash commands (Earn 10% more Kakera)")
        self.add_number_field(roll_sub, "roll_speed", "Rolling Speed (Seconds between each roll)", 0.4)
        self.add_number_field(roll_sub, "roll_interval", "Roll Timer (Minutes until your rolls refresh)", 60)
        self.add_checkbox(roll_sub, "time_rolls_to_claim_reset", "Smart Timing (Finish rolling exactly when your claim resets)")

        auto_rolls_var = self.add_checkbox(roll_sub, "auto_rolls_enabled", "Automatically Use Daily Rolls ($rolls)")
        auto_rolls_sub = self.create_subframe(roll_sub, auto_rolls_var, "auto_rolls_enabled")
        self.add_number_field(auto_rolls_sub, "auto_rolls_limit", "Maximum times to use daily rolls (0 = unlimited)", 0)
        self.add_checkbox(auto_rolls_sub, "auto_rolls_only_claim_hour", "Only Use Daily Rolls in Claim Hour")

        self.add_checkbox(roll_sub, "auto_rolls_in_key_mode", "Use Daily Rolls for Keys (Use $rolls even when you can't claim)")

        # --- Stacked Rolls ($us) ---
        us_outer = ttk.Frame(frame)
        us_outer.pack(fill=tk.X, pady=(0, 15))
        us_frame = CollapsibleLabelFrame(us_outer, text="Saved Rolls ($us)", start_open=False)
        us_frame.pack(fill=tk.X)

        us_enabled_var = self.add_checkbox(us_frame.content, "auto_us_enabled", "Automatically Use Saved Rolls ($us)")
        us_sub = self.create_subframe(us_frame.content, us_enabled_var, "auto_us_enabled")

        self.add_checkbox(us_sub, "bulk_us_enabled", "Bulk US Mode (Pull all rolls at once instead of in batches of 20)")
        self.add_checkbox(us_sub, "auto_us_stop_on_claim", "Save Rolls (Stop using $us after claim)")
        self.add_number_field(us_sub, "auto_us_limit", "Maximum Saved Rolls to Use per Hour", 0)
        self.add_checkbox(us_frame.content, "auto_mk_enabled", "Automatically Use Extra Kakera Rolls ($mk)")
        self.add_checkbox(us_frame.content, "mk_bypass_power_check", "Force $mk Rolls (Use $mk even when power is too low for normal kakera)")

        # --- Claiming ---
        claim_frame = CollapsibleLabelFrame(frame, text="Claim Rules", start_open=False)
        claim_frame.pack(fill=tk.X, pady=(0, 15))

        self.add_number_field(claim_frame.content, "min_kakera", "Minimum Value to Claim (Claim if character is worth this much)", 100)
        claim_interval_entry = self.add_number_field(claim_frame.content, "claim_interval", "Claim Timer (Minutes until you get a new claim right)", 180)
        self.add_number_field(claim_frame.content, "max_claim_rank", "Maximum Claims Rank Limit (e.g. 500 to claim any character ranked #1-#500. 0 = disabled)", 0,
                              description="Claim/Like rank limits let you claim highly-ranked characters even if they are worth less than your Minimum Kakera value.")
        self.add_number_field(claim_frame.content, "max_like_rank", "Maximum Likes Rank Limit (e.g. 300 to claim any character ranked #1-#300. 0 = disabled)", 0)

        self.add_checkbox(claim_frame.content, "lurker_mode", "Lurker Strategy (Wait for others to roll while sniping - Panic dump at the end)")
        self.add_number_field(claim_frame.content, "panic_roll_minutes", "Panic Roll When No Claim In Snipe Mode (Minutes before reset)", 5)
        self.add_checkbox(claim_frame.content, "key_mode", "Key Farming Mode (Keep rolling to earn keys even if you can't claim)")
        self.add_checkbox(
            claim_frame.content,
            "auto_rt_after_claim",
            "Auto $rt After Claim (Also controls $rt for Kakera farm claims)",
            description="When disabled, forcedivorce farming will never use $rt by itself.",
        )

        # Hybrid Smart Panic Claim
        hybrid_var = self.add_checkbox(claim_frame.content, "enable_hybrid_panic_claim", "Hybrid Smart Panic Claim (Instantly claim high-value characters in the last claim hour, collect others)")
        hybrid_sub = self.create_subframe(claim_frame.content, hybrid_var, "enable_hybrid_panic_claim")
        self.add_number_field(hybrid_sub, "hybrid_panic_instant_claim_min_kakera", "Hybrid Instant Claim Min Kakera (Minimum value to claim instantly in panic hour)", 300)
        self.add_number_field(hybrid_sub, "hybrid_panic_instant_claim_max_rank", "Hybrid Instant Claim Max Rank Limit (Rank <= this to claim instantly in panic hour)", 200)

        # claim_rounds_thresholds
        self.rounds_frame = tk.LabelFrame(
            claim_frame.content,
            text="Dynamic Cooldown Rounds (Hourly Thresholds)",
            bg=BG_DARK,
            fg=ACCENT,
            bd=1,
            relief="solid",
            highlightbackground=BORDER_COLOR,
            highlightthickness=0,
            font=("Segoe UI", 10, "bold"),
            padx=10,
            pady=10
        )
        self.rounds_frame.pack(fill=tk.X, pady=10)
        self.rebuild_rounds_frame(180, preserve=False)

        def on_interval_change(*args):
            try:
                val = float(claim_interval_entry.get().strip() or "180")
                self.rebuild_rounds_frame(int(val), preserve=True)
            except ValueError:
                pass
        claim_interval_entry.bind("<FocusOut>", on_interval_change)
        claim_interval_entry.bind("<KeyRelease>", on_interval_change)

        # --- Character Sniping & Stealing ---
        char_snipe_outer = ttk.Frame(frame)
        char_snipe_outer.pack(fill=tk.X, pady=(0, 15))
        char_snipe_frame = CollapsibleLabelFrame(char_snipe_outer, text="Character Sniping & Stealing", start_open=False)
        char_snipe_frame.pack(fill=tk.X)

        snipe_mode_var = self.add_checkbox(char_snipe_frame.content, "snipe_mode", "Snipe Characters (Claim characters rolled by other people)")
        snipe_sub = self.create_subframe(char_snipe_frame.content, snipe_mode_var, "snipe_mode")
        self.add_number_field(snipe_sub, "snipe_delay", "Snipe Wait Time (Wait X seconds before stealing a roll)", 2)
        self.add_checkbox(snipe_sub, "snipe_ignore_min_kakera_reset", "Panic Claim (Claim ANY character right before your timer resets)")
        self.add_list_field(snipe_sub, "snipe_channels", "Target Snipe Channels (Comma-separated IDs of external channels to monitor for sniping)")

        reactive_snipe_var = self.add_checkbox(char_snipe_frame.content, "reactive_snipe_on_own_rolls", "Instant Self-Claim (Immediately claim your own good rolls)")
        reactive_sub = self.create_subframe(char_snipe_frame.content, reactive_snipe_var, "reactive_snipe_on_own_rolls")
        self.add_number_field(reactive_sub, "reactive_snipe_delay", "Self-Claim Delay (Seconds to wait before claiming your own rolls)", 0)

        # Series snipe
        series_snipe_var = self.add_checkbox(char_snipe_frame.content, "series_snipe_mode", "Series Sniping (Auto-claim any character from specific shows/games)")
        series_sub = self.create_subframe(char_snipe_frame.content, series_snipe_var, "series_snipe_mode")
        self.add_number_field(series_sub, "series_snipe_delay", "Series Snipe Wait Time (Wait X seconds before stealing from series)", 3)
        self.add_list_field(series_sub, "series_wishlist", "Series Wishlist (Shows or Games you want to auto-claim)")

        # Kakera snipe
        kakera_snipe_var = self.add_checkbox(char_snipe_frame.content, "kakera_snipe_mode", "Value Sniping (Snipe expensive characters rolled by others)")
        kakera_sub = self.create_subframe(char_snipe_frame.content, kakera_snipe_var, "kakera_snipe_mode")
        self.add_number_field(kakera_sub, "kakera_snipe_threshold", "Minimum Value to Steal (Only steal if worth this much)", 0,
                              description="Note: Applies to the calculated Kakera value of characters rolled by other players.")

        self.add_list_field(char_snipe_frame.content, "character_snipe_targets", "Target Character Snipe Users (Comma-separated IDs or usernames. Only snipe from these players. Leave empty to snipe everyone).")

        # $rt settings
        self.add_checkbox(char_snipe_frame.content, "rt_only_self_rolls", "Private Restore (Only use $rt on characters YOU rolled)")
        self.add_checkbox(char_snipe_frame.content, "rt_ignore_min_kakera_for_wishlist", "Restore for Wishlist (Use $rt for wishlisted characters regardless of value)")

        # Snipe Chat Reactions
        enable_chat_var = self.add_checkbox(char_snipe_frame.content, "enable_snipe_chat_reactions", "Snipe Chat Reactions (Send a random message after a successful external snipe)")
        chat_sub = self.create_subframe(char_snipe_frame.content, enable_chat_var, "enable_snipe_chat_reactions")
        self.add_list_field(chat_sub, "snipe_chat_messages", "Snipe Chat Messages (Comma-separated, e.g., omg, ezz, yay)")

        # --- Kakera Reaction Collection ---
        kakera_react_outer = ttk.Frame(frame)
        kakera_react_outer.pack(fill=tk.X, pady=(0, 15))
        kakera_react_frame = CollapsibleLabelFrame(kakera_react_outer, text="Kakera Reaction Collection", start_open=False)
        kakera_react_frame.pack(fill=tk.X)

        kakera_react_snipe_var = self.add_checkbox(kakera_react_frame.content, "kakera_reaction_snipe_mode", "Auto-Collect Kakera (Click crystals on other people's rolls)")
        kakera_react_sub = self.create_subframe(kakera_react_frame.content, kakera_react_snipe_var, "kakera_reaction_snipe_mode")
        self.add_number_field(kakera_react_sub, "kakera_reaction_snipe_delay", "Kakera Collection Delay (How fast to click others' crystals)", 0.75)
        self.add_list_field(kakera_react_sub, "kakera_reaction_snipe_targets", "Target User IDs (Only steal Kakera from these specific users)")

        self.add_checkbox(kakera_react_frame.content, "only_chaos", "Chaos Kakera Only (Only click crystals that cost 50% less power)")
        self.add_checkbox(kakera_react_frame.content, "mk_only", "MK Kakera Only (Ignore normal kakera, ONLY click crystals from your $mk rolls)")

        self.add_checkbox(kakera_react_frame.content, "immediate_kakera_click", "Immediate Kakera Click (Click crystals instantly instead of waiting for all rolls to finish)", description="If enabled, the bot clicks crystals as soon as they appear. Otherwise, it waits to prioritize the best ones.")

        self.add_checkbox(kakera_react_frame.content, "op_perk_5_only", "Only Click Kakera on $op (Perk 5) Characters")

        # --- Wishlists & Filters ---
        list_frame = CollapsibleLabelFrame(frame, text="Wishlists & Ignored Characters", start_open=False)
        list_frame.pack(fill=tk.X, pady=(0, 15))

        self.add_list_field(list_frame.content, "wishlist", "Character Wishlist (Names of characters you want to auto-claim)")
        self.add_list_field(list_frame.content, "avoid_list", "Blacklisted Characters (Names of characters to NEVER claim)")

        farm_var = self.add_checkbox(list_frame.content, "farm_character_enabled", "Enable Kakera Farming Loop (Auto-Forcedivorce)")
        farm_sub = self.create_subframe(list_frame.content, farm_var, "farm_character_enabled")
        self.add_text_field(farm_sub, "farm_character", "Kakera Farm Character (Name of character to endlessly farm)")
        self.add_checkbox(
            farm_sub,
            "farm_forcedivorce_before_roll",
            "Forcedivorce Before Rolling (Solo/Startup Cleanup)",
            description="Releases the farm character before a roll cycle when a claim is ready. This also clears a character already owned at startup, but makes it available to other players.",
        )
        self.add_checkbox(
            farm_sub,
            "farm_forcedivorce_after_claim",
            "Forcedivorce After Own Verified Claim",
            description="Releases the farm character immediately after this account verifies its own claim.",
        )
        self.add_checkbox(
            farm_sub,
            "farm_forcedivorce_after_other_claim",
            "Forcedivorce After Another Account Claims (Shared Server Mode)",
            description="Optionally releases the configured farm character when another account claims it in the target channel.",
        )

        # --- Auto-Divorce ---
        divorce_var = self.add_checkbox(list_frame.content, "auto_divorce_enabled", "Auto-Divorce (Automatically separate low-value characters after claiming)")
        divorce_sub = self.create_subframe(list_frame.content, divorce_var, "auto_divorce_enabled")
        self.add_number_field(divorce_sub, "auto_divorce_max_kakera", "Kakera Threshold (Divorce if character value ≤ this)", 50)
        self.add_list_field(divorce_sub, "auto_divorce_series", "Auto-Divorce Series (Divorce if character is from these series)")
        self.add_list_field(divorce_sub, "auto_divorce_blacklist", "Divorce Blacklist (Characters to NEVER divorce)")
        self.add_list_field(divorce_sub, "auto_divorce_blacklist_series", "Divorce Blacklist Series (Series to NEVER divorce)")

        # --- Emoji Settings ---
        emoji_frame = CollapsibleLabelFrame(frame, text="Custom Emojis (Advanced)", start_open=False)
        emoji_frame.pack(fill=tk.X, pady=(0, 15))

        ttk.Label(emoji_frame.content, text="Uncheck to use defaults. Check with empty field to disable.",
                 foreground="#a6adc8", font=("Segoe UI", 9)).pack(anchor=tk.W, pady=(0, 10))

        self.add_optional_list_field(emoji_frame.content, "claim_emojis", "Claim Emojis",
                                     ", ".join(DEFAULT_CLAIM_EMOJIS))
        self.add_optional_list_field(emoji_frame.content, "kakera_emojis", "Kakera Emojis",
                                     ", ".join(DEFAULT_KAKERA_EMOJIS))
        self.add_optional_list_field(emoji_frame.content, "chaos_emojis", "Chaos Emojis",
                                     ", ".join(DEFAULT_CHAOS_EMOJIS))
        self.add_optional_list_field(emoji_frame.content, "sphere_perk_emojis", "Sphere Perk Emojis",
                                     ", ".join(DEFAULT_SPHERE_PERK_EMOJIS))

        # [NEW] Task 5: Randomized claim reaction emojis
        self.add_list_field(emoji_frame.content, "randomized_claim_reactions", "Claim Reaction Emojis (Randomized fallback emojis for claims without buttons)")

        # [NEW] Task 8: Customizable kakera/sphere priority map
        self.add_list_field(emoji_frame.content, "kakera_priority_order", "Kakera Priority Order (Highest priority first, comma-separated)",
                            description="Default: kakeraP, kakeraC, kakeraL, kakeraW, kakeraR, kakeraO, kakeraD, kakeraY, kakeraG, kakeraT, kakera")

        # [NEW] Sphere click targets setting
        self.add_list_field(emoji_frame.content, "sphere_click_targets", "Target Sphere Emojis (Comma-separated list of sphere emojis to click, e.g., spU, spG, spY)")

        # --- Anti-Detection ---
        human_outer = ttk.Frame(frame)
        human_outer.pack(fill=tk.X, pady=(0, 15))
        human_frame = CollapsibleLabelFrame(human_outer, text="Timing & Activity Controls", start_open=False)
        human_frame.pack(fill=tk.X)

        human_var = self.add_checkbox(human_frame.content, "humanization_enabled", "Timing Variation (Randomizes timing; does not prevent detection or bans)")
        human_sub = self.create_subframe(human_frame.content, human_var, "humanization_enabled")

        self.add_number_field(human_sub, "humanization_window_minutes", "Random Wait Time (minutes) to Look Like a Real Human", 40)
        self.add_number_field(human_sub, "humanization_inactivity_seconds", "Patience (Wait for X seconds of no chat before rolling)", 5)

        # Inactive hours
        inactive_row = tk.Frame(human_sub, bg=BG_DARK)
        inactive_row.pack(fill=tk.X, pady=5)
        lbl_sleep = tk.Label(inactive_row, text="Bot Sleep Schedule (e.g. 1-7, 23-6):", bg=BG_DARK, fg=TEXT_MAIN, font=("Segoe UI", 10))
        lbl_sleep.pack(anchor=tk.W)
        lbl_sleep_desc = tk.Label(inactive_row, text="The bot will not roll during these hours (uses your local time)",
                 bg=BG_DARK, fg=TEXT_MUTED, font=("Segoe UI", 9))
        lbl_sleep_desc.pack(anchor=tk.W)
        inactive_entry = tk.Entry(
            inactive_row,
            bg=BG_INPUT,
            fg=TEXT_MAIN,
            insertbackground=TEXT_MAIN,
            font=("Segoe UI", 10),
            bd=0,
            highlightthickness=1,
            highlightbackground=BORDER_COLOR,
            highlightcolor=ACCENT,
            relief="flat"
        )
        inactive_entry.pack(fill=tk.X, ipady=4)
        self.widgets["inactive_hours"] = inactive_entry
        self._register_settings_widget(human_frame.content, inactive_row, "Bot Sleep Schedule (e.g. 1-7, 23-6):", "inactive_hours")
        self._bind_focus_highlight(inactive_entry)
        inactive_entry.bind("<Key>", lambda e: self.mark_dirty())

        # Reactive kakera delay range
        range_row = tk.Frame(human_sub, bg=BG_DARK)
        range_row.pack(fill=tk.X, pady=5)
        lbl_delay = tk.Label(range_row, text="Self-Roll Kakera Delay (Random wait range in seconds):", bg=BG_DARK, fg=TEXT_MAIN, font=("Segoe UI", 10))
        lbl_delay.pack(anchor=tk.W)
        range_inputs = tk.Frame(range_row, bg=BG_DARK)
        range_inputs.pack(fill=tk.X)

        self.widgets["reactive_kakera_delay_min"] = tk.Entry(
            range_inputs,
            width=10,
            bg=BG_INPUT,
            fg=TEXT_MAIN,
            insertbackground=TEXT_MAIN,
            font=("Segoe UI", 10),
            bd=0,
            highlightthickness=1,
            highlightbackground=BORDER_COLOR,
            highlightcolor=ACCENT,
            relief="flat"
        )
        self.widgets["reactive_kakera_delay_min"].pack(side=tk.LEFT, padx=(0, 5), ipady=4)
        lbl_to = tk.Label(range_inputs, text="to", bg=BG_DARK, fg=TEXT_MAIN, font=("Segoe UI", 10))
        lbl_to.pack(side=tk.LEFT, padx=5)
        self.widgets["reactive_kakera_delay_max"] = tk.Entry(
            range_inputs,
            width=10,
            bg=BG_INPUT,
            fg=TEXT_MAIN,
            insertbackground=TEXT_MAIN,
            font=("Segoe UI", 10),
            bd=0,
            highlightthickness=1,
            highlightbackground=BORDER_COLOR,
            highlightcolor=ACCENT,
            relief="flat"
        )
        self.widgets["reactive_kakera_delay_max"].pack(side=tk.LEFT, padx=(5, 0), ipady=4)

        self._register_settings_widget(human_frame.content, range_row, "Self-Roll Kakera Delay (Random wait range in seconds):", "reactive_kakera_delay")
        self._bind_focus_highlight(self.widgets["reactive_kakera_delay_min"])
        self._bind_focus_highlight(self.widgets["reactive_kakera_delay_max"])
        self.widgets["reactive_kakera_delay_min"].bind("<Key>", lambda e: self.mark_dirty())
        self.widgets["reactive_kakera_delay_max"].bind("<Key>", lambda e: self.mark_dirty())

        # --- Advanced ---
        power_frame = CollapsibleLabelFrame(frame, text="Power & Expert Settings", start_open=False)
        power_frame.pack(fill=tk.X, pady=(0, 15))

        self.add_checkbox(power_frame.content, "auto_dk_enabled", "Auto $dk (Automatically use $dk when ready or low on power)")
        self.add_checkbox(power_frame.content, "auto_p_enabled", "Auto $p (Automatically claim pokemon when available)")
        self.add_checkbox(power_frame.content, "auto_oh_enabled", "Auto $oh (Automatically play Sphere Harvest when available)")
        self.add_checkbox(power_frame.content, "auto_oc_enabled", "Auto $oc (Automatically solve Sphere Chest when available)")
        self.add_checkbox(power_frame.content, "dk_power_management", "Smart Power Refill (Auto-use $dk when low on energy)")
        # [NEW] Task 1: Max DK Power setting
        self.add_number_field(power_frame.content, "max_dk_power", "Maximum DK Power % (Default 100, increase for late-game users)", 100)
        self.add_checkbox(power_frame.content, "skip_initial_commands", "Fast Start (Skip initial setup commands on startup)")
        self.add_text_field(power_frame.content, "kakera_power_thresholds", "Min Power per Kakera (e.g. kakeraY:80, chaos_kakeraY:50)")
        self.add_checkbox(power_frame.content, "debug_mode", "Expert Logs (Show technical data for every single roll)")

        # [NEW] Task 6: Main account ID for wishlist syncing
        self.add_text_field(power_frame.content, "main_account_id", "Main Account ID (Alt accounts will auto-claim wishlist characters rolled by this account)")

        # [NEW] Task 7: Scheduled roll times
        sched_row = tk.Frame(power_frame.content, bg=BG_DARK)
        sched_row.pack(fill=tk.X, pady=5)
        lbl_sched = tk.Label(sched_row, text="Scheduled Roll Times (e.g. 14:00, 18:30 — comma-separated, 24h format):", bg=BG_DARK, fg=TEXT_MAIN, font=("Segoe UI", 10))
        lbl_sched.pack(anchor=tk.W)
        lbl_sched_desc = tk.Label(sched_row, text="These times force an available-roll check in addition to normal reset tracking. Respects humanization.",
                 bg=BG_DARK, fg=TEXT_MUTED, font=("Segoe UI", 9))
        lbl_sched_desc.pack(anchor=tk.W)
        sched_entry = tk.Entry(
            sched_row,
            bg=BG_INPUT,
            fg=TEXT_MAIN,
            insertbackground=TEXT_MAIN,
            font=("Segoe UI", 10),
            bd=0,
            highlightthickness=1,
            highlightbackground=BORDER_COLOR,
            highlightcolor=ACCENT,
            relief="flat"
        )
        sched_entry.pack(fill=tk.X, ipady=4)
        self.widgets["scheduled_roll_times"] = sched_entry
        self._register_settings_widget(power_frame.content, sched_row, "Scheduled Roll Times (e.g. 14:00, 18:30 — comma-separated, 24h format):", "scheduled_roll_times")
        self._bind_focus_highlight(sched_entry)
        sched_entry.bind("<Key>", lambda e: self.mark_dirty())

        # --- Action Buttons ---
        self.btn_frame = tk.Frame(self.footer_frame, bg=BG_DARK)
        self.btn_frame.pack(fill=tk.X, padx=10)

        self.create_flat_button(
            self.btn_frame, "💾 Save Changes", self.save_current_preset,
            bg_color=COLOR_SUCCESS, fg_color=BG_DARK, hover_bg="#b5e8b0"
        ).pack(side=tk.LEFT, padx=(0, 10))

        self.create_flat_button(
            self.btn_frame, "▶ Launch Bot", self.run_bot,
            bg_color=ACCENT, fg_color=BG_DARK, hover_bg=ACCENT_ALT
        ).pack(side=tk.LEFT, padx=(0, 10))

        self.create_flat_button(
            self.btn_frame, "⏹ Stop Bot", self.stop_bot,
            bg_color=BG_PANEL, fg_color=TEXT_MAIN, hover_bg=BG_INPUT
        ).pack(side=tk.LEFT, padx=(0, 10))

        self.run_status_label = tk.Label(self.btn_frame, text="Not running", bg=BG_DARK, fg=TEXT_MUTED, font=("Segoe UI", 9))
        self.run_status_label.pack(side=tk.LEFT, padx=(0, 10))

        self.create_flat_button(
            self.btn_frame, "🗑 Delete Config", self.delete_preset,
            bg_color=COLOR_DANGER, fg_color=BG_DARK, hover_bg="#eba0ac"
        ).pack(side=tk.RIGHT)

    def add_text_field(self, parent, key, label, show=None, pack_side=None, description=None):
        """Add a text entry field."""
        container = tk.Frame(parent, bg=self._get_parent_bg(parent))
        if pack_side:
            container.pack(side=pack_side, fill=tk.X, expand=True, padx=5, pady=5)
        else:
            container.pack(fill=tk.X, pady=5)

        lbl = tk.Label(container, text=label, bg=container.cget("bg"), fg=TEXT_MAIN, font=("Segoe UI", 10))
        lbl.pack(anchor=tk.W)

        if description:
            lbl_desc = tk.Label(container, text=description, bg=container.cget("bg"), fg=TEXT_MUTED, font=("Segoe UI", 9), justify=tk.LEFT, wraplength=600)
            lbl_desc.pack(anchor=tk.W)

        entry_row = tk.Frame(container, bg=container.cget("bg"))
        entry_row.pack(fill=tk.X)

        entry = tk.Entry(
            entry_row,
            show=show,
            bg=BG_INPUT,
            fg=TEXT_MAIN,
            insertbackground=TEXT_MAIN,
            font=("Segoe UI", 10),
            bd=0,
            highlightthickness=1,
            highlightbackground=BORDER_COLOR,
            highlightcolor=ACCENT,
            relief="flat"
        )
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)
        self.widgets[key] = entry

        # Track unsaved edits
        entry.bind("<Key>", lambda e: self.mark_dirty())

        if key == "token":
            # Add dynamic token visibility toggle button
            def toggle_token_visibility():
                if entry.cget("show") == "*":
                    entry.configure(show="")
                    toggle_btn.configure(text="Hide Token")
                else:
                    entry.configure(show="*")
                    toggle_btn.configure(text="Show Token")

            toggle_btn = self.create_flat_button(
                entry_row,
                "Show Token",
                toggle_token_visibility,
                bg_color=BG_PANEL,
                fg_color=TEXT_MAIN,
                hover_bg=BG_INPUT,
                font=("Segoe UI", 8, "bold")
            )
            toggle_btn.pack(side=tk.RIGHT, padx=(5, 0))
            toggle_btn.configure(pady=4, padx=10)

        self._register_settings_widget(parent, container, label + " " + (description or ""), key)
        self._bind_focus_highlight(entry)

        if key == "token":
            tooltip_msg = "Safety: Your token is kept outside presets.json using Windows DPAPI, the system keyring, or Termux private app storage. Never share it with anyone."
            Tooltip(lbl, tooltip_msg)
            Tooltip(entry, tooltip_msg)

        return entry

    def add_number_field(self, parent, key, label, default, description=None):
        """Add a numeric entry field."""
        container = tk.Frame(parent, bg=self._get_parent_bg(parent))
        container.pack(fill=tk.X, pady=5)

        lbl = tk.Label(container, text=f"{label} (default: {default})", bg=container.cget("bg"), fg=TEXT_MAIN, font=("Segoe UI", 10))
        lbl.pack(anchor=tk.W)

        if description:
            lbl_desc = tk.Label(container, text=description, bg=container.cget("bg"), fg=TEXT_MUTED, font=("Segoe UI", 9), justify=tk.LEFT, wraplength=600)
            lbl_desc.pack(anchor=tk.W)

        entry = tk.Entry(
            container,
            width=15,
            bg=BG_INPUT,
            fg=TEXT_MAIN,
            insertbackground=TEXT_MAIN,
            font=("Segoe UI", 10),
            bd=0,
            highlightthickness=1,
            highlightbackground=BORDER_COLOR,
            highlightcolor=ACCENT,
            relief="flat"
        )
        entry.pack(anchor=tk.W, ipady=4)
        self.widgets[key] = entry

        # Track unsaved edits
        entry.bind("<Key>", lambda e: self.mark_dirty())

        self._register_settings_widget(parent, container, label + " " + (description or ""), key)
        self._bind_focus_highlight(entry)

        if key == "kakera_snipe_threshold":
            tooltip_msg = "Character Sniping: The bot will only snipe characters rolled by other players if their value is greater than or equal to this threshold. Set to 0 to steal all characters."
            Tooltip(lbl, tooltip_msg)
            Tooltip(entry, tooltip_msg)

        return entry

    def add_checkbox(self, parent, key, label, description=None):
        """Add a checkbox."""
        var = tk.BooleanVar()
        container = tk.Frame(parent, bg=self._get_parent_bg(parent))
        container.pack(fill=tk.X, pady=2)

        cb = ttk.Checkbutton(container, text=label, variable=var)
        cb.pack(anchor=tk.W)
        self.widgets[key] = var

        # Track unsaved edits
        var.trace_add("write", lambda *_: self.mark_dirty())

        if description:
            lbl_desc = tk.Label(container, text=description, bg=container.cget("bg"), fg=TEXT_MUTED, font=("Segoe UI", 9), justify=tk.LEFT, wraplength=600)
            lbl_desc.pack(anchor=tk.W, padx=20)

        self._register_settings_widget(parent, container, label + " " + (description or ""), key)

        if key == "immediate_kakera_click":
            Tooltip(cb, "If enabled, the bot clicks crystals as soon as they appear. Otherwise, it waits to prioritize the best ones based on your kakera priority list.")
        elif key == "lurker_mode":
            Tooltip(cb, "Lurker Strategy: The bot will only watch the channel and steal characters rolled by others without performing rolls itself. Near the end of the claim window, it will perform panic claims.")

        return var

    def create_subframe(self, parent, var, key=None):
        """Create a subframe that shows/hides based on a BooleanVar."""
        subframe = tk.Frame(parent, bg=self._get_parent_bg(parent))
        if key:
            self.subframe_controls[subframe] = key

        def toggle(*args):
            if var.get():
                subframe.pack(fill=tk.X, padx=(20, 0), pady=2, before=None)
            else:
                subframe.pack_forget()

        # Initial state
        if var.get():
            subframe.pack(fill=tk.X, padx=(20, 0), pady=2)

        var.trace_add("write", toggle)
        return subframe

    def add_list_field(self, parent, key, label, description=None):
        """Add a comma-separated list field with tag chip functionality."""
        container = tk.Frame(parent, bg=self._get_parent_bg(parent))
        container.pack(fill=tk.X, pady=5)

        lbl = tk.Label(container, text=label, bg=container.cget("bg"), fg=TEXT_MAIN, font=("Segoe UI", 10))
        lbl.pack(anchor=tk.W)

        if description:
            lbl_desc = tk.Label(container, text=description, bg=container.cget("bg"), fg=TEXT_MUTED, font=("Segoe UI", 9), justify=tk.LEFT, wraplength=600)
            lbl_desc.pack(anchor=tk.W)

        entry = ChipListWidget(
            container,
            bg_input=BG_INPUT,
            text_main=TEXT_MAIN,
            border_color=BORDER_COLOR,
            accent=ACCENT,
            bg_panel=BG_PANEL,
            text_muted=TEXT_MUTED,
            state_callback=self.mark_dirty
        )
        entry.pack(fill=tk.X)
        self.widgets[key] = entry

        self._register_settings_widget(parent, container, label + " " + (description or ""), key)
        self._bind_focus_highlight(entry)

    def add_optional_list_field(self, parent, key, label, placeholder):
        """Add an optional list field with checkbox to enable/disable and tag chip functionality."""
        container = tk.Frame(parent, bg=self._get_parent_bg(parent))
        container.pack(fill=tk.X, pady=5)

        # Checkbox to enable
        var = tk.BooleanVar()
        cb = ttk.Checkbutton(container, text=label, variable=var)
        cb.pack(anchor=tk.W)

        # Entry for chips
        entry = ChipListWidget(
            container,
            bg_input=BG_INPUT,
            text_main=TEXT_MAIN,
            border_color=BORDER_COLOR,
            accent=ACCENT,
            bg_panel=BG_PANEL,
            text_muted=TEXT_MUTED,
            state_callback=self.mark_dirty
        )
        entry.pack(fill=tk.X, padx=(20, 0))
        entry.insert(0, placeholder)
        entry.configure(state="disabled")

        # Toggle entry state based on checkbox
        def toggle_entry():
            if var.get():
                entry.configure(state="normal")
            else:
                entry.configure(state="disabled")

        var.trace_add("write", lambda *_: toggle_entry())
        var.trace_add("write", lambda *_: self.mark_dirty())

        self.widgets[f"{key}_enabled"] = var
        self.widgets[key] = entry

        self._register_settings_widget(parent, container, label, key)
        self._bind_focus_highlight(entry)

    def on_preset_select(self, event):
        """Handle preset selection from listbox."""
        selection = self.preset_listbox.curselection()
        if selection:
            preset_name = self.preset_listbox.get(selection[0])
            if preset_name != self.current_preset:
                if self.prompt_unsaved_changes():
                    self.select_preset(preset_name)
                else:
                    self.update_listbox_selection(self.current_preset)

    def select_preset(self, preset_name):
        """Load preset data into the form with loading/dirty flag safety wrapper."""
        self.loading_preset = True
        try:
            self._select_preset_impl(preset_name)
        finally:
            self.loading_preset = False
            self.is_dirty = False

    def _select_preset_impl(self, preset_name):
        """Internal implementation of loading preset data into the form."""
        if preset_name not in self.presets:
            return

        self.current_preset = preset_name
        data = self.presets[preset_name]

        # Update title
        self.title_label.config(text=f"Editing: {preset_name}")
        process = self.bot_processes.get(preset_name)
        if process and process.poll() is None:
            self.run_status_label.configure(text=f"Running: {preset_name}", fg=COLOR_SUCCESS)
        else:
            self.run_status_label.configure(text="Not running", fg=TEXT_MUTED)

        # Populate text/number fields
        # [NEW] Include max_dk_power and main_account_id in text/number population
        for key in ["token", "prefix", "mudae_prefix", "channel_id", "command_channel_id",
                    "roll_command",
                    "min_kakera", "delay_seconds", "start_delay", "roll_speed",
                    "snipe_delay", "series_snipe_delay", "kakera_snipe_threshold",
                    "kakera_reaction_snipe_delay", "humanization_window_minutes",
                    "humanization_inactivity_seconds", "reactive_snipe_delay",
                    "claim_interval", "roll_interval", "auto_us_limit",
                    "auto_rolls_limit", "panic_roll_minutes", "max_dk_power",
                    "main_account_id", "farm_character", "auto_divorce_max_kakera",
                    "max_claim_rank", "max_like_rank", "hybrid_panic_instant_claim_min_kakera",
                    "hybrid_panic_instant_claim_max_rank"]:
            if key in self.widgets:
                widget = self.widgets[key]
                if isinstance(widget, (ttk.Entry, tk.Entry)):
                    widget.delete(0, tk.END)
                    value = self.secret_store.get_token(preset_name, data.get("token", "")) if key == "token" else data.get(key, DEFAULTS.get(key, ""))
                    if value is not None:
                        widget.insert(0, str(value))

        # Populate boolean fields
        for key in ["rolling", "use_slash_rolls", "snipe_mode", "snipe_ignore_min_kakera_reset",
                    "series_snipe_mode", "kakera_snipe_mode", "kakera_reaction_snipe_mode",
                    "reactive_snipe_on_own_rolls", "key_mode", "only_chaos",
                    "humanization_enabled", "dk_power_management", "skip_initial_commands",
                    "time_rolls_to_claim_reset", "rt_ignore_min_kakera_for_wishlist",
                    "rt_only_self_rolls", "auto_us_enabled", "auto_us_stop_on_claim",
                    "bulk_us_enabled",
                    "auto_rolls_enabled", "auto_rolls_in_key_mode", "auto_rolls_only_claim_hour",
                    "autostart", "debug_mode", "auto_mk_enabled", "lurker_mode",
                    "auto_rt_after_claim", "mk_only", "auto_dk_enabled",
                    "enable_snipe_chat_reactions", "op_perk_5_only", "farm_character_enabled", "farm_forcedivorce_before_roll", "farm_forcedivorce_after_claim", "farm_forcedivorce_after_other_claim",
                    "auto_divorce_enabled", "mk_bypass_power_check", "auto_p_enabled", "auto_oh_enabled", "auto_oc_enabled",
                    "enable_hybrid_panic_claim", "immediate_kakera_click"]:
            if key in self.widgets:
                var = self.widgets[key]
                if isinstance(var, tk.BooleanVar):
                    # Use default from BOOL_SETTINGS if key not in data
                    default = next((d for k, _, d in BOOL_SETTINGS if k == key), False)
                    var.set(data.get(key, default))

        # Populate list fields
        # [NEW] Include randomized_claim_reactions and kakera_priority_order in list field population
        for key in ["wishlist", "series_wishlist", "avoid_list", "kakera_reaction_snipe_targets",
                    "randomized_claim_reactions", "kakera_priority_order",
                    "snipe_chat_messages", "auto_divorce_series", "auto_divorce_blacklist", "auto_divorce_blacklist_series", "snipe_channels", "sphere_click_targets",
                    "character_snipe_targets"]:
            if key in self.widgets:
                widget = self.widgets[key]
                if isinstance(widget, (ttk.Entry, tk.Entry, ChipListWidget)):
                    widget.delete(0, tk.END)
                    value = data.get(key, DEFAULTS.get(key, []))
                    if isinstance(value, list):
                        widget.insert(0, ", ".join(value))

        # Populate optional emoji fields
        for key, defaults in [("claim_emojis", DEFAULT_CLAIM_EMOJIS),
                              ("kakera_emojis", DEFAULT_KAKERA_EMOJIS),
                              ("chaos_emojis", DEFAULT_CHAOS_EMOJIS),
                              ("sphere_perk_emojis", DEFAULT_SPHERE_PERK_EMOJIS)]:
            enabled_key = f"{key}_enabled"
            if enabled_key in self.widgets and key in self.widgets:
                var = self.widgets[enabled_key]
                entry = self.widgets[key]

                if key in data:
                    # Key exists in preset - enable and populate
                    var.set(True)
                    entry.configure(state="normal")
                    entry.delete(0, tk.END)
                    value = data[key]
                    if isinstance(value, list):
                        entry.insert(0, ", ".join(value))
                else:
                    # Key missing - disable and show defaults
                    var.set(False)
                    entry.configure(state="normal")
                    entry.delete(0, tk.END)
                    entry.insert(0, ", ".join(defaults))
                    entry.configure(state="disabled")

        # Populate inactive hours
        inactive_val = data.get("inactive_hours", [])
        self.widgets["inactive_hours"].delete(0, tk.END)
        if isinstance(inactive_val, list) and inactive_val:
            # Convert [[1,7],[23,6]] -> "1-7, 23-6"
            parts = []
            for window in inactive_val:
                if isinstance(window, (list, tuple)) and len(window) == 2:
                    parts.append(f"{window[0]}-{window[1]}")
            self.widgets["inactive_hours"].insert(0, ", ".join(parts))

        # Populate reactive kakera delay range
        range_val = data.get("reactive_kakera_delay_range", [0.3, 1.0])
        if isinstance(range_val, (list, tuple)) and len(range_val) == 2:
            self.widgets["reactive_kakera_delay_min"].delete(0, tk.END)
            self.widgets["reactive_kakera_delay_min"].insert(0, str(range_val[0]))
            self.widgets["reactive_kakera_delay_max"].delete(0, tk.END)
            self.widgets["reactive_kakera_delay_max"].insert(0, str(range_val[1]))

        # Populate kakera power thresholds
        thresholds = data.get("kakera_power_thresholds", {})
        if "kakera_power_thresholds" in self.widgets:
            self.widgets["kakera_power_thresholds"].delete(0, tk.END)
            if isinstance(thresholds, dict) and thresholds:
                thresh_str = ", ".join([f"{k}:{v}" for k, v in thresholds.items()])
                self.widgets["kakera_power_thresholds"].insert(0, thresh_str)

        # [NEW] Task 7: Populate scheduled roll times
        sched_val = data.get("scheduled_roll_times", [])
        if "scheduled_roll_times" in self.widgets:
            self.widgets["scheduled_roll_times"].delete(0, tk.END)
            if isinstance(sched_val, list) and sched_val:
                self.widgets["scheduled_roll_times"].insert(0, ", ".join(sched_val))

        # Read claim_interval
        claim_interval_val = data.get("claim_interval", 180)
        try:
            claim_interval_mins = int(float(claim_interval_val))
        except (ValueError, TypeError):
            claim_interval_mins = 180

        # Rebuild rounds frame to draw correct rows
        self.rebuild_rounds_frame(claim_interval_mins, preserve=False)

        # Populate round-specific fields
        claim_rounds = data.get("claim_rounds_thresholds", [])
        if isinstance(claim_rounds, list):
            for rt in claim_rounds:
                r_num = rt.get("round")
                for suffix in ["min_kakera", "max_claim_rank", "max_like_rank"]:
                    widget = self.widgets.get(f"round_{r_num}_{suffix}")
                    if widget and suffix in rt:
                        widget.insert(0, str(rt[suffix]))

        # Update listbox selection
        for i in range(self.preset_listbox.size()):
            if self.preset_listbox.get(i) == preset_name:
                self.preset_listbox.selection_clear(0, tk.END)
                self.preset_listbox.selection_set(i)
                break

    def save_current_preset(self, show_success=True):
        """Save the current form data to the preset."""
        if not self.current_preset:
            messagebox.showwarning("Warning", "No preset selected.")
            return False

        data = {}
        resolved_token = self.widgets["token"].get().strip() if "token" in self.widgets else ""

        # Collect text fields
        # [NEW] Include main_account_id and farm_character in text fields collection
        for key in ["prefix", "mudae_prefix", "channel_id", "command_channel_id", "roll_command", "main_account_id", "farm_character"]:
            if key in self.widgets:
                value = self.widgets[key].get().strip()
                # Special handling for channel_id
                if key in ("channel_id", "command_channel_id") and value:
                    try:
                        data[key] = int(value)
                    except ValueError:
                        data[key] = value
                else:
                    data[key] = value

        # Collect numeric fields
        # [NEW] Include max_dk_power in numeric fields
        numeric_keys = ["min_kakera", "delay_seconds", "start_delay", "roll_speed",
                    "snipe_delay", "series_snipe_delay", "kakera_snipe_threshold",
                    "kakera_reaction_snipe_delay", "humanization_window_minutes",
                    "humanization_inactivity_seconds", "reactive_snipe_delay",
                    "claim_interval", "roll_interval", "auto_us_limit",
                    "auto_rolls_limit", "panic_roll_minutes", "max_dk_power",
                    "auto_divorce_max_kakera", "max_claim_rank", "max_like_rank",
                    "hybrid_panic_instant_claim_min_kakera", "hybrid_panic_instant_claim_max_rank"]
        for key in numeric_keys:
            if key in self.widgets:
                value = self.widgets[key].get().strip()
                if value:
                    try:
                        # Determine type
                        if key in ["min_kakera", "start_delay", "kakera_snipe_threshold",
                                   "humanization_window_minutes", "humanization_inactivity_seconds",
                                   "claim_interval", "roll_interval", "auto_us_limit",
                                   "auto_rolls_limit", "panic_roll_minutes", "max_dk_power",
                                   "auto_divorce_max_kakera", "max_claim_rank", "max_like_rank",
                                   "hybrid_panic_instant_claim_min_kakera", "hybrid_panic_instant_claim_max_rank"]:
                            data[key] = int(float(value))
                        else:
                            data[key] = float(value)
                    except ValueError:
                        messagebox.showerror(
                            "Validation Error",
                            f"Invalid numeric value '{value}' for key '{key}'. Please enter a valid number.",
                            parent=self.root
                        )
                        widget = self.widgets[key]
                        if hasattr(widget, "focus_set"):
                            widget.focus_set()
                        return False
        for key in numeric_keys:
            data.setdefault(key, DEFAULTS.get(key, 0))

        # Collect boolean fields
        for key in ["rolling", "use_slash_rolls", "snipe_mode", "snipe_ignore_min_kakera_reset",
                    "series_snipe_mode", "kakera_snipe_mode", "kakera_reaction_snipe_mode",
                    "reactive_snipe_on_own_rolls", "key_mode", "only_chaos",
                    "humanization_enabled", "dk_power_management", "skip_initial_commands",
                    "time_rolls_to_claim_reset", "rt_ignore_min_kakera_for_wishlist",
                    "rt_only_self_rolls", "auto_us_enabled", "auto_us_stop_on_claim",
                    "bulk_us_enabled",
                    "auto_rolls_enabled", "auto_rolls_in_key_mode", "auto_rolls_only_claim_hour",
                    "autostart", "debug_mode", "auto_mk_enabled", "lurker_mode",
                    "auto_rt_after_claim", "mk_only", "auto_dk_enabled",
                    "enable_snipe_chat_reactions", "op_perk_5_only", "farm_character_enabled", "farm_forcedivorce_before_roll", "farm_forcedivorce_after_claim", "farm_forcedivorce_after_other_claim",
                    "auto_divorce_enabled", "mk_bypass_power_check", "auto_p_enabled", "auto_oh_enabled", "auto_oc_enabled",
                    "enable_hybrid_panic_claim", "immediate_kakera_click"]:
            if key in self.widgets:
                data[key] = self.widgets[key].get()

        # Collect list fields
        # [NEW] Include randomized_claim_reactions and kakera_priority_order in list collection
        for key in ["wishlist", "series_wishlist", "avoid_list", "kakera_reaction_snipe_targets",
                    "randomized_claim_reactions", "kakera_priority_order",
                    "snipe_chat_messages", "auto_divorce_series", "auto_divorce_blacklist", "auto_divorce_blacklist_series", "snipe_channels", "sphere_click_targets",
                    "character_snipe_targets"]:
            if key in self.widgets:
                value = self.widgets[key].get().strip()
                if value:
                    data[key] = [item.strip() for item in value.split(",") if item.strip()]
                else:
                    data[key] = []

        # Collect optional emoji fields
        # Key rule:
        # - Checkbox unchecked → key NOT in data (use defaults)
        # - Checkbox checked + empty → key = [] (disable)
        # - Checkbox checked + values → key = [values]
        for key in ["claim_emojis", "kakera_emojis", "chaos_emojis", "sphere_perk_emojis"]:
            enabled_key = f"{key}_enabled"
            if enabled_key in self.widgets and key in self.widgets:
                if self.widgets[enabled_key].get():  # Checkbox is checked
                    value = self.widgets[key].get().strip()
                    if value:
                        data[key] = [item.strip() for item in value.split(",") if item.strip()]
                    else:
                        data[key] = []  # Explicitly empty
                # else: checkbox unchecked, don't include key (use defaults)

        # Collect inactive hours
        inactive_text = self.widgets["inactive_hours"].get().strip()
        data["inactive_hours"], inactive_errors = parse_inactive_hours(inactive_text)
        if inactive_errors:
            messagebox.showerror("Validation Error", "\n".join(inactive_errors), parent=self.root)
            self.widgets["inactive_hours"].focus_set()
            return False

        # Collect reactive kakera delay range
        try:
            min_val = float(self.widgets["reactive_kakera_delay_min"].get().strip() or "0.3")
            max_val = float(self.widgets["reactive_kakera_delay_max"].get().strip() or "1.0")
            data["reactive_kakera_delay_range"] = [min_val, max_val]
        except ValueError:
            messagebox.showerror("Validation Error", "Reactive Kakera delay values must be numeric.", parent=self.root)
            return False

        # Collect kakera power thresholds
        thresh_text = ""
        if "kakera_power_thresholds" in self.widgets:
            thresh_text = self.widgets["kakera_power_thresholds"].get().strip()

        data["kakera_power_thresholds"] = {}
        if thresh_text:
            for part in thresh_text.split(","):
                part = part.strip()
                if ":" in part:
                    k, v = part.split(":", 1)
                    k = k.strip()
                    try:
                        v_int = int(v.strip())
                        data["kakera_power_thresholds"][k] = v_int
                    except ValueError:
                        messagebox.showerror("Validation Error", f"Power threshold '{part}' must use an integer value.", parent=self.root)
                        return False
                else:
                    messagebox.showerror("Validation Error", f"Power threshold '{part}' must use name:value format.", parent=self.root)
                    return False

        # [NEW] Task 7: Collect scheduled roll times
        if "scheduled_roll_times" in self.widgets:
            sched_text = self.widgets["scheduled_roll_times"].get().strip()
            data["scheduled_roll_times"], schedule_errors = parse_scheduled_times(sched_text)
            if schedule_errors:
                messagebox.showerror("Validation Error", "\n".join(schedule_errors), parent=self.root)
                self.widgets["scheduled_roll_times"].focus_set()
                return False

        # Determine num_rounds dynamically
        claim_interval_val = self.widgets.get("claim_interval").get().strip() if self.widgets.get("claim_interval") else "180"
        try:
            claim_interval_mins = int(float(claim_interval_val or "180"))
        except ValueError:
            claim_interval_mins = 180
        num_rounds = max(1, math.ceil(claim_interval_mins / 60))

        # Collect claim_rounds_thresholds from the round entry fields dynamically
        claim_rounds_thresholds = []
        for i in range(1, num_rounds + 1):
            min_k_widget = self.widgets.get(f"round_{i}_min_kakera")
            max_claim_widget = self.widgets.get(f"round_{i}_max_claim_rank")
            max_like_widget = self.widgets.get(f"round_{i}_max_like_rank")

            min_k_val = min_k_widget.get().strip() if min_k_widget else ""
            max_claim_val = max_claim_widget.get().strip() if max_claim_widget else ""
            max_like_val = max_like_widget.get().strip() if max_like_widget else ""

            if not min_k_val and not max_claim_val and not max_like_val:
                continue

            round_dict = {"round": i}

            def safe_int(v, field_name, widget):
                if not v:
                    return None
                try:
                    return int(float(v))
                except ValueError:
                    messagebox.showerror(
                        "Validation Error",
                        f"Invalid numeric value '{v}' for Round {i} {field_name}. Please enter a valid number.",
                        parent=self.root
                    )
                    if widget and hasattr(widget, "focus_set"):
                        widget.focus_set()
                    return -999999

            if min_k_val:
                parsed_min_k = safe_int(min_k_val, "Minimum Kakera", min_k_widget)
                if parsed_min_k == -999999:
                    return False
                round_dict["min_kakera"] = parsed_min_k

            if max_claim_val:
                parsed_max_claim = safe_int(max_claim_val, "Maximum Claim Rank", max_claim_widget)
                if parsed_max_claim == -999999:
                    return False
                round_dict["max_claim_rank"] = parsed_max_claim

            if max_like_val:
                parsed_max_like = safe_int(max_like_val, "Maximum Like Rank", max_like_widget)
                if parsed_max_like == -999999:
                    return False
                round_dict["max_like_rank"] = parsed_max_like

            if len(round_dict) > 1:
                claim_rounds_thresholds.append(round_dict)

        data["claim_rounds_thresholds"] = claim_rounds_thresholds

        validation_errors = validate_preset(data, resolved_token=resolved_token)
        if validation_errors:
            messagebox.showerror("Validation Error", "\n".join(validation_errors), parent=self.root)
            return False

        try:
            self.secret_store.set_token(self.current_preset, resolved_token)
        except SecretStoreError as exc:
            messagebox.showerror("Secure Token Storage", str(exc), parent=self.root)
            return False

        data["token"] = ""
        previous_data = self.presets.get(self.current_preset)
        self.presets[self.current_preset] = data
        if not self.save_presets():
            self.presets[self.current_preset] = previous_data
            return False

        if show_success:
            messagebox.showinfo("Success", f"Settings for '{self.current_preset}' are now saved!")
        self.is_dirty = False
        self.title_label.config(text=f"Editing: {self.current_preset}")
        self._manage_autostart(self.current_preset, data.get("autostart", False))
        return True

    def _manage_autostart(self, preset_name, enable):
        """Refresh Windows Startup scripts using only enabled presets for stagger order."""
        if sys.platform != "win32":
            return

        startup_dir = os.path.join(os.environ["APPDATA"], "Microsoft", "Windows", "Start Menu", "Programs", "Startup")
        bat_path = os.path.join(startup_dir, f"MudaRemote_{preset_name}.bat")

        if not enable and os.path.exists(bat_path):
            try:
                os.remove(bat_path)
            except Exception as e:
                print(f"Failed to remove autostart script: {e}")

        active_names = [
            name for name, data in self.presets.items()
            if data.get("autostart", False)
        ]
        is_frozen = getattr(sys, 'frozen', False)
        cwd = get_base_path()
        for active_index, active_name in enumerate(active_names):
            active_bat_path = os.path.join(startup_dir, f"MudaRemote_{active_name}.bat")
            try:
                with open(active_bat_path, "w", encoding="utf-8") as f:
                    f.write('@echo off\n')
                    f.write(f'cd /d "{cwd}"\n')
                    if is_frozen:
                        exe_path = os.path.abspath(sys.executable)
                        f.write(
                            f'start "{active_name} - MudaRemote" "{exe_path}" --preset "{active_name}" '
                            f'--stagger-index {active_index}\n'
                        )
                    else:
                        python_exe = sys.executable
                        bot_script = os.path.join(cwd, BOT_SCRIPT)
                        f.write(
                            f'start "{active_name} - MudaRemote" "{python_exe}" "{bot_script}" '
                            f'--preset "{active_name}" --stagger-index {active_index}\n'
                        )
            except Exception as e:
                print(f"Failed to create autostart script for '{active_name}': {e}")

    def create_preset(self):
        """Create a new preset."""
        if not self.prompt_unsaved_changes():
            return
        name = simpledialog.askstring("New Configuration", "What would you like to name this new config?", parent=self.root)
        if name:
            name = name.strip()
            if name in self.presets:
                messagebox.showwarning("Name Taken", f"You already have a config named '{name}'. Please choose a different name.")
                return

            # Create with minimal defaults
            self.presets[name] = {
                "token": "",
                "prefix": "/////////////",
                "mudae_prefix": "$",
                "channel_id": "",
                "roll_command": "wa",
                "min_kakera": 100,
                "delay_seconds": 0,
                "start_delay": 0,
                "rolling": True,
                "wishlist": [],
                "series_wishlist": [],
                "auto_us_enabled": False,
                "auto_us_limit": 0,
                "auto_us_stop_on_claim": True,
                "bulk_us_enabled": False,
                "auto_rolls_enabled": False,
                "auto_rolls_limit": 0,
                "auto_rolls_in_key_mode": False,
                "auto_rolls_only_claim_hour": False,
                "auto_mk_enabled": True,
                "mk_bypass_power_check": False,
                "auto_rt_after_claim": False,
                "mk_only": False,
                "auto_dk_enabled": True,
                "auto_p_enabled": True,
                "auto_oh_enabled": False,
                "auto_oc_enabled": False,
                "enable_snipe_chat_reactions": False,
                "snipe_chat_messages": ["omg", "ezz"],
                "farm_forcedivorce_before_roll": False,
                "farm_forcedivorce_after_claim": False,
                "farm_forcedivorce_after_other_claim": False,
                "sphere_click_targets": ["spG", "spY", "spO", "spR", "spW", "spL", "spD", "spM", "spU"],
                "immediate_kakera_click": True,
                "character_snipe_targets": [],
            }
            if not self.save_presets():
                del self.presets[name]
                return
            self.refresh_preset_list()
            self.select_preset(name)

    def duplicate_preset(self):
        """Duplicate the current preset."""
        if not self.current_preset:
            messagebox.showwarning("Warning", "No preset selected.")
            return

        if not self.prompt_unsaved_changes():
            return

        name = simpledialog.askstring("Duplicate Preset",
                                      f"Enter name for copy of '{self.current_preset}':",
                                      parent=self.root)
        if name:
            name = name.strip()
            if name in self.presets:
                messagebox.showwarning("Warning", f"Preset '{name}' already exists.")
                return

            # Deep copy
            import copy
            self.presets[name] = copy.deepcopy(self.presets[self.current_preset])
            try:
                source_token = self.secret_store.get_token(self.current_preset, self.presets[self.current_preset].get("token", ""))
                if source_token:
                    self.secret_store.set_token(name, source_token)
            except SecretStoreError as exc:
                del self.presets[name]
                messagebox.showerror("Secure Token Storage", str(exc), parent=self.root)
                return
            self.presets[name]["token"] = ""
            if not self.save_presets():
                del self.presets[name]
                try:
                    self.secret_store.delete_token(name)
                except SecretStoreError:
                    pass
                return
            self.refresh_preset_list()
            self.select_preset(name)

    def share_preset(self):
        """Export the currently selected preset to the clipboard without exposing the token."""
        if not self.current_preset:
            messagebox.showwarning("Warning", "No preset selected.")
            return
        if self.is_dirty and not self.save_current_preset(show_success=False):
            return

        preset_data = self.presets.get(self.current_preset)
        if not preset_data:
            return

        import copy
        clean_data = copy.deepcopy(preset_data)
        clean_data["token"] = ""

        json_str = json.dumps(clean_data, indent=4, ensure_ascii=False)

        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(json_str)
            self.root.update()
            messagebox.showinfo("Success", "Preset copied to clipboard without token!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to copy preset to clipboard:\n{e}")

    def delete_preset(self):
        """Delete the current preset."""
        if not self.current_preset:
            messagebox.showwarning("Warning", "No preset selected.")
            return

        if messagebox.askyesno("Confirm Delete",
                               f"Are you sure you want to delete preset '{self.current_preset}'?"):
            preset_name = self.current_preset
            deleted_data = self.presets.pop(preset_name)
            if not self.save_presets():
                self.presets[preset_name] = deleted_data
                return
            process = self.bot_processes.pop(preset_name, None)
            if process and process.poll() is None:
                process.terminate()
            self._manage_autostart(preset_name, False)
            try:
                self.secret_store.delete_token(preset_name)
            except SecretStoreError as exc:
                messagebox.showwarning("Secure Token Storage", f"Preset was deleted, but its stored token could not be removed:\n{exc}")
            self.current_preset = None
            self.is_dirty = False
            self.refresh_preset_list()
            self.title_label.config(text="Select a preset")

            # Clear form or select first preset
            if self.presets:
                self.select_preset(list(self.presets.keys())[0])

    def run_bot(self):
        """Run the bot with the current preset."""
        if not self.current_preset:
            messagebox.showwarning("Warning", "No preset selected.")
            return

        if not self.save_current_preset(show_success=False):
            return

        existing = self.bot_processes.get(self.current_preset)
        if existing and existing.poll() is None:
            messagebox.showinfo("Already Running", f"'{self.current_preset}' is already running.")
            return

        is_frozen = getattr(sys, 'frozen', False)

        if not is_frozen:
            # In script mode, verify bot script exists on disk
            if not os.path.exists(BOT_SCRIPT):
                messagebox.showerror("Error", f"{BOT_SCRIPT} not found in current directory.")
                return

        try:
            active_processes = [
                process for process in self.bot_processes.values()
                if process and process.poll() is None
            ]
            stagger_index = len(active_processes)
            if is_frozen:
                # In frozen (.exe) mode, sys.executable IS the .exe itself.
                # We relaunch the same .exe with --preset to run in headless bot mode.
                if sys.platform == "win32":
                    process = subprocess.Popen(
                        [sys.executable, "--preset", self.current_preset, "--stagger-index", str(stagger_index)],
                        creationflags=subprocess.CREATE_NEW_CONSOLE
                    )
                else:
                    process = subprocess.Popen(
                        [sys.executable, "--preset", self.current_preset, "--stagger-index", str(stagger_index)]
                    )
            else:
                # In script (.py) mode, launch python with the bot script
                if sys.platform == "win32":
                    process = subprocess.Popen(
                        [sys.executable, BOT_SCRIPT, "--preset", self.current_preset, "--stagger-index", str(stagger_index)],
                        creationflags=subprocess.CREATE_NEW_CONSOLE
                    )
                else:
                    process = subprocess.Popen(
                        [sys.executable, BOT_SCRIPT, "--preset", self.current_preset, "--stagger-index", str(stagger_index)]
                    )

            self.bot_processes[self.current_preset] = process
            self.run_status_label.configure(text=f"Running: {self.current_preset}", fg=COLOR_SUCCESS)
            self.root.after(1500, lambda name=self.current_preset: self._poll_bot_process(name))
        except Exception as e:
            messagebox.showerror("Error", f"Failed to start bot:\n{e}")

    def _poll_bot_process(self, preset_name):
        process = self.bot_processes.get(preset_name)
        if not process:
            return
        exit_code = process.poll()
        if exit_code is None:
            self.root.after(1500, lambda: self._poll_bot_process(preset_name))
            return
        self.bot_processes.pop(preset_name, None)
        if self.current_preset == preset_name:
            self.run_status_label.configure(text=f"Stopped: {preset_name} (exit {exit_code})", fg=COLOR_DANGER)
        if exit_code != 0:
            messagebox.showerror("Bot Stopped", f"'{preset_name}' exited with code {exit_code}. Check logs.txt for details.")

    def stop_bot(self):
        if not self.current_preset:
            return
        process = self.bot_processes.get(self.current_preset)
        if not process or process.poll() is not None:
            messagebox.showinfo("Not Running", f"'{self.current_preset}' is not running from this editor session.")
            return
        process.terminate()
        self.run_status_label.configure(text=f"Stopping: {self.current_preset}", fg=TEXT_MUTED)


def launch_gui():
    """Launch the Tkinter GUI preset editor."""
    # When built with --console (needed for headless bot mode), hide the console
    # window in GUI mode so double-clicking the .exe looks clean.
    if sys.platform == "win32" and getattr(sys, 'frozen', False):
        try:
            import ctypes
            console_window = ctypes.windll.kernel32.GetConsoleWindow()
            if console_window:
                ctypes.windll.user32.ShowWindow(console_window, 0)  # SW_HIDE
        except Exception:
            pass

    root = tk.Tk()
    app = PresetEditor(root)
    root.mainloop()


def run_headless(preset_names, start_index=0):
    """
    Headless mode: import mudae_bot and run specified presets in threads.
    Used when the .exe (or script) is launched with --preset or --all.
    """
    import mudae_bot

    # Load presets from disk (mudae_bot already ensures it exists on import)
    try:
        all_presets = load_json(PRESETS_FILE, {})
    except (json.JSONDecodeError, Exception) as e:
        print(f"[MudaRemote] Failed to load {PRESETS_FILE}: {e}")
        sys.exit(1)

    requested_names = []
    resolved_presets = {}
    for name in preset_names:
        if name not in all_presets:
            print(f"[MudaRemote] Preset '{name}' not found. Skipping.")
            continue
        preset_data = dict(all_presets[name])
        preset_data["token"] = SecretStore(get_base_path()).get_token(name, preset_data.get("token", ""))
        if not preset_data.get("token"):
            print(f"[MudaRemote] Preset '{name}' has no token. Skipping.")
            continue
        requested_names.append(name)
        resolved_presets[name] = preset_data

    threads = []
    for name, preset_data in prepare_active_presets(
        requested_names,
        resolved_presets,
        start_index=start_index,
    ):
        active_index = int(preset_data["persistent_stagger_seconds"] // active_stagger_seconds(1))
        print(f"[MudaRemote] Starting active preset #{active_index + 1}: {name}")
        t = mudae_bot.start_preset_thread(name, preset_data)
        if t:
            threads.append(t)

    if not threads:
        print("[MudaRemote] No valid presets to run.")
        sys.exit(1)

    # Keep the main thread alive so daemon threads don't die
    print(f"[MudaRemote] {len(threads)} preset(s) running. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[MudaRemote] Shutting down...")


def main():
    # [NEW] Feature 5: Move Auto-Update Trigger to GUI Startup
    # Check for updates and cleanup backup files before doing anything else.
    # This ensures the batch script swaps the .exe before the UI even appears.
    try:
        import mudae_bot
        mudae_bot.cleanup_after_update()
        mudae_bot.check_for_updates()
    except Exception as e:
        print(f"[MudaRemote] Update check failed: {e}")

    parser = argparse.ArgumentParser(
        description="MudaRemote - Mudae Bot Manager & Preset Editor",
        prog="MudaRemote"
    )
    parser.add_argument(
        "--preset",
        nargs='+',
        type=str,
        help="Name(s) of preset(s) to run in headless mode (e.g. --preset MyPreset1 MyPreset2)"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run ALL presets from presets.json in headless mode"
    )
    parser.add_argument(
        "--stagger-index",
        type=int,
        default=0,
        help="Starting active preset position for automated staggering"
    )

    args = parser.parse_args()

    if args.all:
        # Load all preset names and run them all
        try:
            with open(PRESETS_FILE, "r", encoding="utf-8") as f:
                all_presets = json.load(f)
            preset_names = list(all_presets.keys())
        except Exception as e:
            print(f"[MudaRemote] Failed to load presets: {e}")
            sys.exit(1)

        if not preset_names:
            print("[MudaRemote] No presets found in presets.json.")
            sys.exit(1)

        print(f"[MudaRemote] Running ALL {len(preset_names)} preset(s): {', '.join(preset_names)}")
        run_headless(preset_names, start_index=args.stagger_index)

    elif args.preset:
        # Run specific preset(s) in headless mode
        print(f"[MudaRemote] Running preset(s): {', '.join(args.preset)}")
        run_headless(args.preset, start_index=args.stagger_index)

    else:
        # No arguments → launch the GUI
        launch_gui()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        traceback.print_exc()
        if len(sys.argv) > 1:
            input("\nPress Enter to close...")
        sys.exit(1)
    except SystemExit as e:
        if e.code != 0 and e.code is not None and len(sys.argv) > 1:
            input("\nPress Enter to close...")
        sys.exit(e.code)

```

## File: `build.py`

```python
"""
MudaRemote Build Script
Compiles mudae_preset_editor.py into a standalone .exe using PyInstaller.

Usage:
    python build.py                   # Default: --onedir build
    python build.py --onefile          # Single-file build
    python build.py --console          # Build with console window visible
    python build.py --onefile --console
"""

import argparse
import hashlib
import os
import sys


def build(onefile=False, console=False):
    """Run PyInstaller to compile MudaRemote."""
    try:
        import PyInstaller.__main__
    except ImportError:
        print("[BUILD] ERROR: PyInstaller is not installed.")
        print("[BUILD] Install the pinned build dependencies with:")
        print(f"[BUILD]   {sys.executable} -m pip install -r requirements-dev.txt")
        sys.exit(1)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    entry_point = os.path.join(script_dir, "mudae_preset_editor.py")
    icon_path = os.path.join(script_dir, "icon.png")
    release_spec = os.path.join(script_dir, "MudaRemote.spec")
    version_file = os.path.join(script_dir, "packaging", "windows_version_info.txt")
    spec_dir = os.path.join(script_dir, "build", "spec")
    os.makedirs(spec_dir, exist_ok=True)

    if not os.path.exists(entry_point):
        print(f"[BUILD] ERROR: {entry_point} not found.")
        sys.exit(1)

    if onefile:
        # The checked-in spec is the canonical release definition. Keeping CI,
        # local builds, metadata and antivirus-hardening flags in one place
        # prevents different machines from silently producing different layouts.
        args = [release_spec, "--noconfirm", "--clean"]
        print("[BUILD] Mode: Single file (.exe)")
    else:
        args = [
            entry_point,
            "--noconfirm",
            "--clean",
            "--noupx",
            "--name=MudaRemote",
            f"--specpath={spec_dir}",
            "--onedir",
            # Include mudae_bot.py as hidden import so the bundle contains all bot logic.
            "--hidden-import=mudae_bot",
            "--hidden-import=requests",
            "--hidden-import=discord",
            "--hidden-import=discord.ext.commands",
            "--hidden-import=discord.http",
            "--hidden-import=inquirer",
            "--collect-submodules=mudae_core",
            "--hidden-import=keyring",
            f"--version-file={version_file}",
        ]
        print("[BUILD] Mode: Directory (faster startup)")

    if onefile:
        print("[BUILD] Window and icon settings: MudaRemote.spec")
    else:
        # IMPORTANT: We MUST use --console (not --windowed) because the exe needs to
        # spawn visible console windows for headless bot mode (--preset).
        # The console is hidden programmatically via ctypes when launching the GUI.
        args.append("--console")
        if console:
            print("[BUILD] Window: Console (always visible)")
        else:
            print("[BUILD] Window: Console (hidden automatically in GUI mode)")

        if os.path.exists(icon_path):
            args.append(f"--icon={icon_path}")
            print(f"[BUILD] Icon: {icon_path}")
        else:
            print(f"[BUILD] WARNING: icon.png not found at {icon_path}, building without icon.")

    print(f"\n[BUILD] Starting PyInstaller...\n{'='*60}")
    print(f"[BUILD] Command: pyinstaller {' '.join(args)}\n")

    PyInstaller.__main__.run(args)

    print(f"\n{'='*60}")
    print("[BUILD] Build complete!")
    if onefile:
        output_path = os.path.join(script_dir, "dist", "MudaRemote.exe")
    else:
        output_path = os.path.join(script_dir, "dist", "MudaRemote", "MudaRemote.exe")
    print(f"[BUILD] Output: {output_path}")
    if os.path.isfile(output_path):
        with open(output_path, "rb") as executable:
            digest = hashlib.sha256(executable.read()).hexdigest()
        print(f"[BUILD] SHA256: {digest}")
    print("[BUILD] Make sure presets.json is in the same directory as the .exe when running.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build MudaRemote into a standalone .exe")
    parser.add_argument("--onefile", action="store_true", help="Build as a single .exe file (slower startup)")
    parser.add_argument("--console", action="store_true", help="Show console window (useful for debugging)")
    args = parser.parse_args()

    build(onefile=args.onefile, console=args.console)

```

## File: `mudae_core/__init__.py`

```python
"""Shared, testable infrastructure for MudaRemote."""

from .config import atomic_write_json, load_json, validate_preset
from .claiming import (
    ClaimEvidence,
    ClaimOutcome,
    classify_claim_owner,
    classify_claim_text,
    cooldown_deadline,
    has_free_claim_button,
    is_claim_announcement_for_character,
)
from .coordinator import ClaimCoordinator
from .kakera import calculate_kakera_power_cost, has_perk_eight_discount
from .runtime import (
    AUTOMATED_STAGGER_INTERVAL_SECONDS,
    CommandPacer,
    active_stagger_seconds,
    pause_interruptible_sleep,
    prepare_active_presets,
    set_client_paused,
    wait_until_resumed,
)
from .secrets import SecretStore
from .spheres import (
    SphereGameStatus,
    chest_red_candidates,
    choose_chest_position,
    choose_chest_reward_position,
    choose_harvest_position,
    harvest_reveal_is_free,
    normalize_sphere_emoji,
    parse_sphere_game_status,
)
from .status import (
    STATUS_FIELDS,
    clear_status_dirty,
    consume_tu_urgent_bypass,
    defer_tu_queries,
    initialize_status_tracking,
    looks_like_tu_status_snapshot,
    mark_status_dirty,
    record_tu_failure,
    record_tu_success,
    status_dirty_fields,
    status_refresh_reasons,
    tu_retry_wait,
)
from .updater import UpdateError, apply_update
from .versioning import compare_versions, is_newer_version

__all__ = [
    "ClaimCoordinator",
    "ClaimEvidence",
    "ClaimOutcome",
    "CommandPacer",
    "AUTOMATED_STAGGER_INTERVAL_SECONDS",
    "SecretStore",
    "SphereGameStatus",
    "STATUS_FIELDS",
    "UpdateError",
    "apply_update",
    "active_stagger_seconds",
    "atomic_write_json",
    "calculate_kakera_power_cost",
    "classify_claim_owner",
    "classify_claim_text",
    "chest_red_candidates",
    "choose_chest_position",
    "choose_chest_reward_position",
    "choose_harvest_position",
    "clear_status_dirty",
    "consume_tu_urgent_bypass",
    "compare_versions",
    "cooldown_deadline",
    "defer_tu_queries",
    "has_free_claim_button",
    "harvest_reveal_is_free",
    "initialize_status_tracking",
    "is_claim_announcement_for_character",
    "is_newer_version",
    "has_perk_eight_discount",
    "load_json",
    "looks_like_tu_status_snapshot",
    "mark_status_dirty",
    "normalize_sphere_emoji",
    "pause_interruptible_sleep",
    "prepare_active_presets",
    "parse_sphere_game_status",
    "record_tu_failure",
    "record_tu_success",
    "set_client_paused",
    "status_dirty_fields",
    "status_refresh_reasons",
    "tu_retry_wait",
    "validate_preset",
    "wait_until_resumed",
]

```

## File: `mudae_core/claiming.py`

```python
"""Pure helpers for interpreting Mudae claim outcomes and cooldowns."""

from dataclasses import dataclass
import datetime
from enum import Enum
import re
from typing import Iterable, Optional


class ClaimOutcome(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class ClaimEvidence:
    outcome: ClaimOutcome
    winner: Optional[str] = None
    source: str = "none"


def _is_success_button_style(button: object) -> bool:
    style = getattr(button, "style", None)
    return bool(
        style is not None
        and (
            getattr(style, "value", None) == 3
            or str(style).casefold().endswith("success")
            or str(style) == "3"
        )
    )


def has_free_claim_button(components: object, claim_emojis: Iterable[object]) -> bool:
    """Detect Mudae's green claim button, which does not consume a claim right."""
    allowed = {str(emoji) for emoji in claim_emojis}
    for component in components or ():
        for button in getattr(component, "children", ()) or ():
            emoji = getattr(getattr(button, "emoji", None), "name", None)
            if emoji is not None and str(emoji) in allowed and _is_success_button_style(button):
                return True
    return False


def normalize_external_text(value: object) -> str:
    """Normalize Discord/Mudae text without depending on a specific markdown style."""
    text = str(value or "")
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    text = re.sub(r"<@!?(\d+)>", r" user-\1 ", text)
    text = re.sub(r"[*_~`>|]+", " ", text)
    text = re.sub(r"[^\w]+", " ", text.casefold(), flags=re.UNICODE)
    return " ".join(text.split())


def _contains_normalized(haystack: str, needle: object) -> bool:
    normalized = normalize_external_text(needle).strip()
    if not normalized:
        return False
    return " {} ".format(normalized) in " {} ".format(haystack)


def identity_matches(value: object, identities: Iterable[object], user_id: Optional[int] = None) -> bool:
    normalized = normalize_external_text(value)
    if user_id is not None and _contains_normalized(normalized, "user-{}".format(user_id)):
        return True
    return any(_contains_normalized(normalized, identity) for identity in identities if identity)


def classify_claim_text(
    content: object,
    character_name: object,
    identities: Iterable[object],
    user_id: Optional[int] = None,
) -> ClaimEvidence:
    """Classify a textual claim confirmation using strict and permissive evidence."""
    raw = str(content or "")
    normalized = normalize_external_text(raw)
    character = normalize_external_text(character_name)
    if not character or not _contains_normalized(normalized, character):
        return ClaimEvidence(ClaimOutcome.INCONCLUSIVE)

    safe_identities = [identity for identity in identities if normalize_external_text(identity) != character]
    if identity_matches(raw, safe_identities, user_id=user_id):
        return ClaimEvidence(ClaimOutcome.SUCCESS, source="confirmation-text")

    labels = re.findall(r"\*\*(.+?)\*\*|\[([^\]]+)\]\([^\)]+\)", raw, flags=re.DOTALL)
    candidates = []
    for bold_label, link_label in labels:
        label = (bold_label or link_label).strip()
        normalized_label = normalize_external_text(label)
        if not normalized_label or normalized_label == character:
            continue
        if normalized_label.isdigit() or normalized_label in {"kakera", "claim", "claimed", "married"}:
            continue
        candidates.append(label)

    relationship_markers = (
        "married", "claimed", "belongs", "casou", "casado", "reclamado",
        "marié", "mariée", "épous", "se casar", "se casó",
    )
    if candidates and any(marker in normalized for marker in relationship_markers):
        return ClaimEvidence(ClaimOutcome.FAILURE, winner=candidates[0], source="confirmation-text")
    return ClaimEvidence(ClaimOutcome.INCONCLUSIVE)


def is_claim_announcement_for_character(content: object, character_name: object) -> bool:
    """Return whether a Mudae message announces that the character was claimed."""
    normalized = normalize_external_text(content)
    character = normalize_external_text(character_name)
    if not character or not _contains_normalized(normalized, character):
        return False

    # Forcedivorce prompts also contain relationship wording, but they are not
    # new claims and must never start another release cycle.
    excluded_markers = (
        "force the divorce",
        "forcedivorce",
        "belongs to",
        "divorced",
    )
    if any(marker in normalized for marker in excluded_markers):
        return False

    claim_markers = (
        "are now married",
        "is now married",
        "has claimed",
        " claimed ",
        "casou",
        "casado",
        "reclamado",
        "marie",
        "mariee",
        "epous",
        "se caso",
    )
    padded = " {} ".format(normalized)
    return any(marker in padded for marker in claim_markers)


def classify_claim_owner(
    owner: object,
    identities: Iterable[object],
    user_id: Optional[int] = None,
) -> ClaimEvidence:
    """Treat an owner on the edited character embed as authoritative evidence."""
    if not owner:
        return ClaimEvidence(ClaimOutcome.INCONCLUSIVE)
    if identity_matches(owner, identities, user_id=user_id):
        return ClaimEvidence(ClaimOutcome.SUCCESS, source="character-owner")
    return ClaimEvidence(ClaimOutcome.FAILURE, winner=str(owner), source="character-owner")


def cooldown_deadline(
    now: datetime.datetime,
    minutes: int,
    safety_seconds: float = 2.0,
) -> datetime.datetime:
    """Build a timezone-preserving deadline without truncating seconds early."""
    return now + datetime.timedelta(minutes=max(0, int(minutes)), seconds=max(0.0, safety_seconds))

```

## File: `mudae_core/config.py`

```python
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
    farm_after_other_claim = bool(data.get("farm_forcedivorce_after_other_claim", False))
    farm_before_roll = bool(data.get(
        "farm_forcedivorce_before_roll",
        farm_enabled and not farm_after_claim and not farm_after_other_claim,
    ))
    if farm_enabled and not str(data.get("farm_character", "") or "").strip():
        errors.append("Kakera Farm Character is required when the farming loop is enabled.")
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

```

## File: `mudae_core/coordinator.py`

```python
"""Thread-safe cross-account claim and $rt reservations."""

import threading


class ClaimCoordinator:
    """Coordinates message reservations under one lock to prevent deadlocks."""

    def __init__(self):
        self._lock = threading.RLock()
        self._claims = set()
        self._restores = set()

    def is_reserved(self, message_id):
        with self._lock:
            return message_id in self._claims or message_id in self._restores

    def filter_available(self, items, id_getter=lambda item: item[0].id):
        with self._lock:
            return [item for item in items if id_getter(item) not in self._claims and id_getter(item) not in self._restores]

    def reserve_claim(self, message_id, allow_reserved_restore=False):
        with self._lock:
            if message_id in self._claims:
                return False
            if message_id in self._restores and not allow_reserved_restore:
                return False
            self._claims.add(message_id)
            if allow_reserved_restore:
                self._restores.discard(message_id)
            return True

    def reserve_restore(self, message_id):
        with self._lock:
            if message_id in self._claims or message_id in self._restores:
                return False
            self._restores.add(message_id)
            return True

    def transition_restore_to_claim(self, message_id):
        with self._lock:
            if message_id in self._claims:
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

    def snapshot(self):
        with self._lock:
            return frozenset(self._claims), frozenset(self._restores)

```

## File: `mudae_core/kakera.py`

```python
"""Pure helpers for Mudae Kakera reaction discounts."""

import re


def has_perk_eight_discount(description: object) -> bool:
    """Detect the Perk 8 half-power marker across common Unicode variants."""
    normalized = str(description or "").replace("\ufe0f", "").replace("\u20e3", "")
    return re.search(r"💎\s*(?:/|÷|➗)\s*2", normalized) is not None


def calculate_kakera_power_cost(
    base_cost: float,
    *,
    has_chaos_discount: bool = False,
    has_perk_eight_discount: bool = False,
    is_external_roll: bool = False,
    is_free: bool = False,
):
    """Apply independent half-cost modifiers without collapsing stacked discounts.

    The 10+ key discount is only assumed for the bot's own rolls because external
    rolls do not prove that the reacting account owns the character. The visible
    Perk 8 marker is authoritative and therefore applies to either roll source.
    """
    if is_free:
        return 0

    cost = max(0.0, float(base_cost or 0))
    if has_chaos_discount and not is_external_roll:
        cost /= 2.0
    if has_perk_eight_discount:
        cost /= 2.0

    cost = round(cost, 4)
    return int(cost) if cost.is_integer() else cost

```

## File: `mudae_core/runtime.py`

```python
"""Cross-thread pause state and asyncio waiting helpers."""

import asyncio
import random
import time

from .status import STATUS_FIELDS, mark_status_dirty


AUTOMATED_STAGGER_INTERVAL_SECONDS = 20.0


def active_stagger_seconds(active_index, interval=AUTOMATED_STAGGER_INTERVAL_SECONDS):
    """Return the deterministic delay for a preset's position in the active launch set."""
    return max(0, int(active_index or 0)) * max(0.0, float(interval or 0.0))


def prepare_active_presets(preset_names, preset_mapping, start_index=0):
    """Clone runnable selected presets and assign compact stagger offsets in launch order."""
    prepared = []
    seen = set()
    for name in preset_names:
        if name in seen or name not in preset_mapping:
            continue
        seen.add(name)
        data = dict(preset_mapping[name])
        if not data.get("token"):
            continue
        active_index = max(0, int(start_index or 0)) + len(prepared)
        data["persistent_stagger_seconds"] = active_stagger_seconds(active_index)
        prepared.append((name, data))
    return prepared


class CommandPacer:
    """Serialize outbound commands and keep a randomized gap between them."""

    def __init__(self, minimum_delay=0.6, maximum_delay=0.8, clock=None, jitter=None):
        minimum_delay = float(minimum_delay)
        maximum_delay = float(maximum_delay)
        if minimum_delay < 0 or maximum_delay < minimum_delay:
            raise ValueError("Command delay must satisfy 0 <= minimum <= maximum.")
        self.minimum_delay = minimum_delay
        self.maximum_delay = maximum_delay
        self._clock = clock or time.monotonic
        self._jitter = jitter or random.uniform
        self._lock = None
        self._next_command_at = 0.0

    def _get_lock(self):
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def run(self, action, wait, is_allowed=None):
        """Run one async command action after all earlier actions and their gap."""
        allowed = is_allowed or (lambda: True)
        if not allowed():
            return False

        async with self._get_lock():
            if not allowed():
                return False
            remaining = self._next_command_at - self._clock()
            if remaining > 0 and not await wait(remaining):
                return False
            if not allowed():
                return False

            await action()
            self._next_command_at = self._clock() + self._jitter(
                self.minimum_delay,
                self.maximum_delay,
            )
            return True


def _wake_runtime_events(client) -> None:
    for name in ("_runtime_state_event", "_immediate_check_event"):
        event = getattr(client, name, None)
        if event is not None:
            event.set()


def set_client_paused(client, paused: bool) -> None:
    """Apply pause state and wake the owning asyncio loop safely."""
    paused = bool(paused)
    previous = bool(getattr(client, "is_paused", False))
    client.is_paused = paused
    if paused and not previous:
        client._pause_generation = int(getattr(client, "_pause_generation", 0)) + 1
    if paused and not previous:
        interrupted_fields = set()
        if getattr(client, "pending_claim", None) is not None:
            interrupted_fields.add("claim")
        if bool(getattr(client, "is_actively_rolling", False)):
            interrupted_fields.add("rolls")
        tu_future = getattr(client, "_tu_response_future", None)
        if tu_future is not None and not tu_future.done():
            interrupted_fields.update(STATUS_FIELDS)
        if interrupted_fields:
            mark_status_dirty(client, interrupted_fields, reason="pause-interrupted-active-work")

    loop = getattr(client, "loop", None)
    try:
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(_wake_runtime_events, client)
            return
    except (AttributeError, RuntimeError):
        pass
    _wake_runtime_events(client)


async def wait_until_resumed(client) -> None:
    """Wait without polling when a runtime event is available."""
    while bool(getattr(client, "is_paused", False)):
        event = getattr(client, "_runtime_state_event", None)
        if event is None:
            await asyncio.sleep(0.1)
            continue
        event.clear()
        if not bool(getattr(client, "is_paused", False)):
            break
        await event.wait()


async def pause_interruptible_sleep(client, seconds: float, abort_on_pause: bool = False) -> bool:
    """Sleep against wall time, optionally aborting as soon as pause is requested."""
    duration = max(0.0, float(seconds))
    deadline = time.monotonic() + duration
    start_generation = int(getattr(client, "_pause_generation", 0))

    while True:
        if abort_on_pause and (
            bool(getattr(client, "is_paused", False))
            or int(getattr(client, "_pause_generation", 0)) != start_generation
        ):
            return False
        if bool(getattr(client, "is_paused", False)):
            await wait_until_resumed(client)

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return True

        event = getattr(client, "_runtime_state_event", None)
        if event is None:
            await asyncio.sleep(min(remaining, 0.1))
            continue

        event.clear()
        if abort_on_pause and int(getattr(client, "_pause_generation", 0)) != start_generation:
            return False
        if bool(getattr(client, "is_paused", False)):
            continue
        try:
            await asyncio.wait_for(event.wait(), timeout=remaining)
        except asyncio.TimeoutError:
            return True

```

## File: `mudae_core/secrets.py`

```python
"""Credential storage with Windows DPAPI and cross-platform keyring support."""

import base64
import ctypes
import os
import re
from ctypes import wintypes

from .config import atomic_write_json, load_json


class SecretStoreError(RuntimeError):
    pass


class SecretStore:
    SERVICE = "MudaRemote"
    TERMUX_STORE_PARTS = (".local", "share", "mudaremote", "secrets.json")

    def __init__(self, base_path):
        self.path = os.path.join(base_path, ".mudae-secrets.json")
        termux_home = os.environ.get("HOME") or os.path.expanduser("~")
        self.termux_path = os.path.join(termux_home, *self.TERMUX_STORE_PARTS)

    @staticmethod
    def _is_termux():
        prefix = str(os.environ.get("PREFIX", "") or "")
        return bool(os.environ.get("TERMUX_VERSION") or "com.termux" in prefix)

    @staticmethod
    def _env_name(preset_name):
        clean = re.sub(r"[^A-Za-z0-9]+", "_", preset_name).strip("_").upper()
        return "MUDAREMOTE_TOKEN_{}".format(clean)

    def get_token(self, preset_name, legacy_token=""):
        env_token = os.environ.get(self._env_name(preset_name))
        if env_token:
            return env_token
        try:
            stored = self._get_platform_secret(preset_name)
            if stored:
                return stored
        except SecretStoreError:
            pass
        return str(legacy_token or "")

    def set_token(self, preset_name, token):
        token = str(token or "")
        if token and os.environ.get(self._env_name(preset_name)) == token:
            return
        if self._is_termux():
            self._set_termux_secret(preset_name, token)
            return
        if os.name == "nt":
            self._set_dpapi_secret(preset_name, token)
            return
        try:
            import keyring
            if token:
                keyring.set_password(self.SERVICE, preset_name, token)
            else:
                try:
                    keyring.delete_password(self.SERVICE, preset_name)
                except keyring.errors.PasswordDeleteError:
                    pass
        except Exception as exc:
            raise SecretStoreError(
                "Secure token storage is unavailable. Install/configure the 'keyring' package or use {}."
                .format(self._env_name(preset_name))
            ) from exc

    def delete_token(self, preset_name):
        self.set_token(preset_name, "")

    def _get_platform_secret(self, preset_name):
        if self._is_termux():
            values = self._load_termux_values()
            return str(values.get(preset_name, "") or "")
        if os.name == "nt":
            values = self._load_dpapi_values()
            encoded = values.get(preset_name)
            return self._dpapi_unprotect(encoded) if encoded else ""
        try:
            import keyring
            return keyring.get_password(self.SERVICE, preset_name) or ""
        except Exception as exc:
            raise SecretStoreError(str(exc)) from exc

    def _set_termux_secret(self, preset_name, token):
        try:
            values = self._load_termux_values()
            if token:
                values[preset_name] = token
            else:
                values.pop(preset_name, None)

            if not values:
                try:
                    os.remove(self.termux_path)
                except FileNotFoundError:
                    pass
                return

            store_directory = os.path.dirname(self.termux_path)
            os.makedirs(store_directory, mode=0o700, exist_ok=True)
            os.chmod(store_directory, 0o700)
            atomic_write_json(self.termux_path, values)
            os.chmod(self.termux_path, 0o600)
        except Exception as exc:
            raise SecretStoreError(
                "Termux could not save the token in its private app storage."
            ) from exc

    def _load_termux_values(self):
        try:
            values = load_json(self.termux_path, {})
            if not isinstance(values, dict):
                raise ValueError("secret store root is not an object")
            return values
        except Exception as exc:
            raise SecretStoreError(
                "The Termux private token store is unreadable; restore or remove {}."
                .format(self.termux_path)
            ) from exc

    def _set_dpapi_secret(self, preset_name, token):
        values = self._load_dpapi_values()
        if token:
            values[preset_name] = self._dpapi_protect(token)
        else:
            values.pop(preset_name, None)
        atomic_write_json(self.path, values)

    def _load_dpapi_values(self):
        try:
            values = load_json(self.path, {})
            if not isinstance(values, dict):
                raise ValueError("secret store root is not an object")
            return values
        except Exception as exc:
            raise SecretStoreError("The encrypted token store is unreadable; restore or remove {}.".format(self.path)) from exc

    @staticmethod
    def _blob(data):
        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]
        buffer = ctypes.create_string_buffer(data)
        return DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))), buffer, DATA_BLOB

    @classmethod
    def _dpapi_protect(cls, value):
        raw = value.encode("utf-8")
        in_blob, in_buffer, blob_type = cls._blob(raw)
        out_blob = blob_type()
        if not ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(in_blob), cls.SERVICE, None, None, None, 0, ctypes.byref(out_blob)
        ):
            raise SecretStoreError("Windows DPAPI could not encrypt the token.")
        try:
            encrypted = ctypes.string_at(out_blob.pbData, out_blob.cbData)
            return base64.b64encode(encrypted).decode("ascii")
        finally:
            ctypes.windll.kernel32.LocalFree(out_blob.pbData)

    @classmethod
    def _dpapi_unprotect(cls, encoded):
        try:
            encrypted = base64.b64decode(encoded)
            in_blob, in_buffer, blob_type = cls._blob(encrypted)
            out_blob = blob_type()
            if not ctypes.windll.crypt32.CryptUnprotectData(
                ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)
            ):
                raise SecretStoreError("Windows DPAPI could not decrypt the token.")
            try:
                return ctypes.string_at(out_blob.pbData, out_blob.cbData).decode("utf-8")
            finally:
                ctypes.windll.kernel32.LocalFree(out_blob.pbData)
        except SecretStoreError:
            raise
        except Exception as exc:
            raise SecretStoreError("Stored token is unreadable.") from exc

```

## File: `mudae_core/status.py`

```python
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

```

## File: `mudae_core/updater.py`

```python
"""Verified, manifest-based updater for both source and frozen builds."""

import hashlib
import os
import py_compile
import shutil
import subprocess
import sys
import tempfile

from .versioning import is_newer_version


class UpdateError(RuntimeError):
    pass


# Keep startup failures short. ``requests`` applies these as separate connect
# and read-idle limits, including redirected GitHub release downloads.
UPDATE_DOWNLOAD_TIMEOUT = (5.0, 20.0)


def sha256_bytes(content):
    return hashlib.sha256(content).hexdigest()


def _download(session, url, timeout):
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    return response.content


def _validate_relative_path(relative_path):
    normalized = os.path.normpath(str(relative_path).replace("/", os.sep))
    if os.path.isabs(normalized) or normalized == os.pardir or normalized.startswith(os.pardir + os.sep):
        raise UpdateError("Unsafe update path: {!r}".format(relative_path))
    return normalized


def _verified_download(session, url, expected_hash, timeout=UPDATE_DOWNLOAD_TIMEOUT):
    if not expected_hash:
        raise UpdateError("The update manifest is missing a SHA-256 checksum.")
    content = _download(session, url, timeout)
    actual_hash = sha256_bytes(content)
    if actual_hash.lower() != str(expected_hash).lower():
        raise UpdateError("SHA-256 verification failed for {}.".format(url))
    return content


def _stage_source_manifest(session, manifest, stage_dir):
    files = manifest.get("source_files")
    if not isinstance(files, list) or not files:
        raise UpdateError("No source_files manifest was published for this update.")

    staged_paths = []
    seen_paths = set()
    for entry in files:
        if not isinstance(entry, dict):
            raise UpdateError("The source_files manifest contains an invalid entry.")
        relative_path = _validate_relative_path(entry.get("path", ""))
        if not relative_path:
            raise UpdateError("The source_files manifest contains an empty path.")
        if relative_path in seen_paths:
            raise UpdateError("The source_files manifest contains a duplicate path: {}.".format(relative_path))
        seen_paths.add(relative_path)
        target_path = os.path.join(stage_dir, relative_path)
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        content = _verified_download(session, entry.get("url"), entry.get("sha256"))
        with open(target_path, "wb") as handle:
            handle.write(content)
        staged_paths.append(relative_path)

    required = {"mudae_bot.py", "mudae_preset_editor.py", os.path.join("mudae_core", "__init__.py")}
    if not required.issubset(set(staged_paths)):
        raise UpdateError("The source manifest is incomplete; update was not applied.")

    for relative_path in staged_paths:
        if relative_path.endswith(".py"):
            py_compile.compile(os.path.join(stage_dir, relative_path), doraise=True)
    return staged_paths


def _replace_transactionally(base_path, stage_dir, relative_paths):
    backup_dir = tempfile.mkdtemp(prefix="mudae-backup-", dir=base_path)
    replaced = []
    try:
        for relative_path in relative_paths:
            source = os.path.join(stage_dir, relative_path)
            destination = os.path.join(base_path, relative_path)
            backup = os.path.join(backup_dir, relative_path)
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            if os.path.exists(destination):
                os.makedirs(os.path.dirname(backup), exist_ok=True)
                shutil.copy2(destination, backup)
            os.replace(source, destination)
            replaced.append(relative_path)
    except Exception:
        for relative_path in reversed(replaced):
            destination = os.path.join(base_path, relative_path)
            backup = os.path.join(backup_dir, relative_path)
            try:
                if os.path.exists(backup):
                    os.replace(backup, destination)
                elif os.path.exists(destination):
                    os.remove(destination)
            except OSError:
                pass
        raise
    finally:
        shutil.rmtree(backup_dir, ignore_errors=True)


def _stage_frozen_update(session, manifest, base_path, executable):
    url = manifest.get("exe_download_url")
    expected_hash = manifest.get("exe_sha256")
    if not url or not expected_hash:
        raise UpdateError("A verified executable is not available for this release.")
    content = _verified_download(session, url, expected_hash)
    staged_exe = os.path.join(base_path, "MudaRemote_update.exe")
    with open(staged_exe, "wb") as handle:
        handle.write(content)

    executable = os.path.abspath(executable)
    arguments = subprocess.list2cmdline(sys.argv[1:])
    batch_path = os.path.join(base_path, "update.bat")
    batch = (
        "@echo off\r\n"
        "timeout /t 3 /nobreak >nul\r\n"
        "del /f /q \"{current}\"\r\n"
        "move /y \"{staged}\" \"{current}\" >nul\r\n"
        "start \"\" \"{current}\" {arguments}\r\n"
        "del \"%~f0\"\r\n"
    ).format(current=executable, staged=staged_exe, arguments=arguments)
    with open(batch_path, "w", encoding="utf-8", newline="") as handle:
        handle.write(batch)
    return batch_path


def apply_update(session, manifest, current_version, base_path, frozen=False, executable=None):
    """Apply a newer verified update. Return one of: current, git, source, frozen."""
    latest_version = manifest.get("version")
    if not latest_version or not is_newer_version(latest_version, current_version):
        return "current"

    if frozen:
        batch_path = _stage_frozen_update(session, manifest, base_path, executable or sys.executable)
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.Popen([batch_path], creationflags=creation_flags, shell=True)
        return "frozen"

    if os.path.isdir(os.path.join(base_path, ".git")):
        return "git"

    stage_dir = tempfile.mkdtemp(prefix="mudae-update-", dir=base_path)
    try:
        relative_paths = _stage_source_manifest(session, manifest, stage_dir)
        _replace_transactionally(base_path, stage_dir, relative_paths)
    finally:
        shutil.rmtree(stage_dir, ignore_errors=True)
    return "source"

```

## File: `mudae_core/versioning.py`

```python
"""Small semantic-version helpers without an external dependency."""

import re
from itertools import zip_longest


_VERSION_RE = re.compile(
    r"^\s*[vV]?(?P<release>\d+(?:\.\d+)*)"
    r"(?:[-.]?(?P<pre>(?:a|alpha|b|beta|rc|pre|preview))[-.]?(?P<pre_n>\d*)?)?"
    r"(?:\+[0-9A-Za-z.-]+)?\s*$",
    re.IGNORECASE,
)
_PRECEDENCE = {"a": 0, "alpha": 0, "b": 1, "beta": 1, "pre": 2, "preview": 2, "rc": 3}


def _parse(version):
    match = _VERSION_RE.match(str(version or ""))
    if not match:
        raise ValueError("Invalid version: {!r}".format(version))
    release = tuple(int(part) for part in match.group("release").split("."))
    pre_name = match.group("pre")
    if pre_name is None:
        pre = (1, 0, 0)
    else:
        pre = (0, _PRECEDENCE[pre_name.lower()], int(match.group("pre_n") or 0))
    return release, pre


def compare_versions(left, right):
    """Return -1, 0, or 1 using semantic numeric version ordering."""
    left_release, left_pre = _parse(left)
    right_release, right_pre = _parse(right)
    for l_part, r_part in zip_longest(left_release, right_release, fillvalue=0):
        if l_part != r_part:
            return 1 if l_part > r_part else -1
    if left_pre == right_pre:
        return 0
    return 1 if left_pre > right_pre else -1


def is_newer_version(candidate, current):
    return compare_versions(candidate, current) > 0

```

## File: `presets.example.json`

```json
{
  "Example": {
    "token": "",
    "prefix": "/////////////",
    "mudae_prefix": "$",
    "channel_id": 123456789012345678,
    "roll_command": "wa",
    "min_kakera": 100,
    "delay_seconds": 0,
    "claim_interval": 180,
    "roll_interval": 60,
    "rolling": true,
    "auto_oh_enabled": false,
    "auto_oc_enabled": false,
    "farm_character_enabled": false,
    "farm_character": "",
    "farm_forcedivorce_before_roll": false,
    "farm_forcedivorce_after_claim": false,
    "farm_forcedivorce_after_other_claim": false
  }
}

```

## File: `requirements.txt`

```
discord.py-self>=2.0.0,<3
inquirer>=3.1,<4
keyring>=24,<25
requests>=2.31,<3

```

## File: `requirements-dev.txt`

```
-r requirements.txt
pyinstaller==6.21.0
pyinstaller-hooks-contrib==2026.6
pillow==11.3.0

```

## File: `version.json`

```json
{
  "version": "4.6.8",
  "download_url": "https://raw.githubusercontent.com/misutesu-desu/MudaRemote/main/mudae_bot.py",
  "editor_download_url": "https://raw.githubusercontent.com/misutesu-desu/MudaRemote/main/mudae_preset_editor.py",
  "exe_download_url": "https://github.com/misutesu-desu/MudaRemote/releases/latest/download/MudaRemote.exe",
  "exe_sha256": "84dfd1f2e94244f8bacd86f8b91316f429b922cdce1752bda5b5d0f0242d9c19",
  "source_files": [
    {
      "path": "mudae_bot.py",
      "url": "https://raw.githubusercontent.com/misutesu-desu/MudaRemote/main/mudae_bot.py",
      "sha256": "595188d37b4662011acba57a9a728858e3973231a302995b6fcbeaf19244c4a1"
    },
    {
      "path": "mudae_preset_editor.py",
      "url": "https://raw.githubusercontent.com/misutesu-desu/MudaRemote/main/mudae_preset_editor.py",
      "sha256": "0e7b0607277960d15ffe665c828ef30016dc5ea40e5e93e11a4de21ab7077ec6"
    },
    {
      "path": "mudae_core/__init__.py",
      "url": "https://raw.githubusercontent.com/misutesu-desu/MudaRemote/main/mudae_core/__init__.py",
      "sha256": "01cd4e0970b6ffccd9281d4dea5f49a7615f7cbb4befa9d39d515fff2b624eef"
    },
    {
      "path": "mudae_core/claiming.py",
      "url": "https://raw.githubusercontent.com/misutesu-desu/MudaRemote/main/mudae_core/claiming.py",
      "sha256": "eb42d750c4a78dd4070d448999d9326a2b97c11d540775fac208b81085615060"
    },
    {
      "path": "mudae_core/config.py",
      "url": "https://raw.githubusercontent.com/misutesu-desu/MudaRemote/main/mudae_core/config.py",
      "sha256": "6fc6eec0cf231e1f5dfd691dfb225d3466e2f9b9ca6cd4c6e6e595d81b7bc082"
    },
    {
      "path": "mudae_core/kakera.py",
      "url": "https://raw.githubusercontent.com/misutesu-desu/MudaRemote/main/mudae_core/kakera.py",
      "sha256": "bc521c3b61fb54d651c56b74b53fe4b46590a471075be14bd72d6a7a1a3aa7b4"
    },
    {
      "path": "mudae_core/coordinator.py",
      "url": "https://raw.githubusercontent.com/misutesu-desu/MudaRemote/main/mudae_core/coordinator.py",
      "sha256": "e3fa86adf0a5906f3da57e11c7e4a5693ad5716bae10021d353244c4465acad5"
    },
    {
      "path": "mudae_core/runtime.py",
      "url": "https://raw.githubusercontent.com/misutesu-desu/MudaRemote/main/mudae_core/runtime.py",
      "sha256": "7b7e574152dbbc6abcc19888c98802db27033f1911a8886a43e4df2e965dfa36"
    },
    {
      "path": "mudae_core/secrets.py",
      "url": "https://raw.githubusercontent.com/misutesu-desu/MudaRemote/main/mudae_core/secrets.py",
      "sha256": "a742974557a39cdb8f2e099fde79a5d1d72e814f5eb3d499b3c22a051e0889ac"
    },
    {
      "path": "mudae_core/status.py",
      "url": "https://raw.githubusercontent.com/misutesu-desu/MudaRemote/main/mudae_core/status.py",
      "sha256": "479152129f8e45701f272dd21360b97fbc6adf3f3b57ee046f9b86b90f0acb16"
    },
    {
      "path": "mudae_core/spheres.py",
      "url": "https://raw.githubusercontent.com/misutesu-desu/MudaRemote/main/mudae_core/spheres.py",
      "sha256": "c4c91fe1ff847a7a37ff8190ed251c73e6fe0157a9a577c56052a0c1770a95eb"
    },
    {
      "path": "mudae_core/updater.py",
      "url": "https://raw.githubusercontent.com/misutesu-desu/MudaRemote/main/mudae_core/updater.py",
      "sha256": "02d5ce4206174639a093b6974dba1e963f1b0ef8857d6976896d4721159897cb"
    },
    {
      "path": "mudae_core/versioning.py",
      "url": "https://raw.githubusercontent.com/misutesu-desu/MudaRemote/main/mudae_core/versioning.py",
      "sha256": "0f6294c3273842b95f4e03231d03d51c39045420435aaa561b4da913162cbdf3"
    },
    {
      "path": "requirements.txt",
      "url": "https://raw.githubusercontent.com/misutesu-desu/MudaRemote/main/requirements.txt",
      "sha256": "be9ba4d455b5095e5df39730f078b561ddb7bf18abc132dbe8ea47bc7cd61c4f"
    }
  ]
}

```

