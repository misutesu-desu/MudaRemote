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
import shutil
import requests
import subprocess

if os.name == 'nt':
    import msvcrt
from discord.utils import time_snowflake

try:
    from discord.http import Route
except ImportError:
    Route = None

# Bot Identification
BOT_NAME = "MudaRemote"
CURRENT_VERSION = "4.4.1"

# Global Pause State
_global_paused = False
_active_clients = []
_active_clients_lock = threading.Lock()
_menu_active = threading.Event()
_original_terminal_settings = None

class BotLogger:
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
        print(f"{color_code}{formatted}{cls.COLORS['ENDC']}")
        try:
            logs_path = os.path.join(get_base_path(), "logs.txt")
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
    "DK_POWER": r"(?:power|poder):\s*\*{0,2}(\d+)%\*{0,2}",
    "DK_CONSUMPTION": r"(?:each kakera (?:reaction|button) consumes|cada (?:reação|botão|botón) de kakera consume|chaque bouton kakera consomme)\s*(\d+)%",
    "P_COOLDOWN": r"(?:next \$p|próximo \$p|prochain \$p).*?\*{0,2}(\d+h)?\s*(\d+)\*{0,2}\s*min",
    "RT_RESET": r"(?:\$rt|recarga|enfriamiento|cool).*?(?:\:|in|em|en|dans|left|restante|restam|falta|tiempo|temps|tempo|restantes|restant)\s*:?\s*\*{0,2}(\d+h)?\s*(\d+)\*{0,2}\s*min",
    "CLAIM_READY": r"__(?:can|pode|puedes|pouvez)__\s+(?:claim|se casar|reclamar|vous (?:re)?marier)",
    "CLAIM_RESET": r"(?:next claim|próximo|siguiente|prochain|tempo|temps|falta)\s+(?:reset|reclamo|tempo|temps|um tempo).*?(?:in|em|en|dans|left|restante|restant|falta|dentro de)\s*:?\s*\*{0,2}(\d+h)?\s*(\d+)\*{0,2}\s*min",
    "CLAIM_COOLDOWN": r"(?:can't|não pode|no puedes|avant de|falta\s+um\s+tempo).*?(?:claim|casar|reclamar|remarier).*?\*{0,2}(\d+h)?\s*(\d+)\*{0,2}\s*min",
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
    "MAINTENANCE": r"For (\d+) minutes",
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
            c.is_paused = _global_paused
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
        response = requests.get(f"{UPDATE_URL}version.json", timeout=10)
        if response.status_code != 200: return
        data = response.json()
        latest_version = data.get("version")
        if not latest_version or latest_version <= CURRENT_VERSION:
            print_system_log("You are up to date.", "INFO")
            return
            
        print_system_log(f"New version found: v{latest_version}. Downloading update...", "INFO")
        current_dir = get_base_path()
        
        if is_frozen:
            exe_url = data.get("exe_download_url")
            if not exe_url: return
            current_exe = os.path.abspath(sys.executable)
            exe_name = os.path.basename(current_exe)
            update_exe = os.path.join(current_dir, "MudaRemote_update.exe")
            
            res = requests.get(exe_url, timeout=120)
            if res.status_code != 200: return
            
            if os.path.exists(update_exe):
                try: os.remove(update_exe)
                except Exception: pass
                
            target_exe = update_exe
            try:
                with open(target_exe, "wb") as f: f.write(res.content)
            except PermissionError:
                target_exe = os.path.join(current_dir, f"MudaRemote_update_{int(time.time())}.exe")
                with open(target_exe, "wb") as f: f.write(res.content)
                
            args_str = ' '.join(f'"{a}"' for a in sys.argv[1:])
            bat_content = f'@echo off\ntimeout /t 3 /nobreak >nul\ndel /f /q "{current_exe}"\nren "{target_exe}" "{exe_name}"\nstart "" "{current_exe}" {args_str}\ndel "%~f0"\n'
            with open(os.path.join(current_dir, "update.bat"), "w", encoding="utf-8") as f:
                f.write(bat_content)
                
            print_system_log("Update staged. Restarting via updater...", "RESET")
            subprocess.Popen([os.path.join(current_dir, "update.bat")], creationflags=subprocess.CREATE_NO_WINDOW, shell=True)
            os._exit(0)
        else:
            py_url = data.get("download_url")
            if not py_url: return
            res = requests.get(py_url, timeout=30)
            if res.status_code == 200:
                current_script = os.path.abspath(__file__)
                shutil.copy2(current_script, current_script + ".bak")
                with open(current_script, "wb") as f: f.write(res.content)
                
                editor_path = os.path.join(os.path.dirname(current_script), "mudae_preset_editor.py")
                editor_url = data.get("editor_download_url", f"{UPDATE_URL}mudae_preset_editor.py")
                try:
                    res_ed = requests.get(editor_url, timeout=30)
                    if res_ed.status_code == 200:
                        if os.path.exists(editor_path):
                            shutil.copy2(editor_path, editor_path + ".bak")
                        with open(editor_path, "wb") as f: f.write(res_ed.content)
                        print_system_log("Preset editor updated.", "INFO")
                except Exception: pass
                
                print_system_log("Update applied. Starting new version...", "RESET")
                if os.name == 'nt':
                    subprocess.Popen([sys.executable] + sys.argv, creationflags=subprocess.CREATE_NEW_CONSOLE)
                else:
                    os.execv(sys.executable, [sys.executable] + sys.argv)
                sys.exit()
    except Exception as e:
        print_system_log(f"Update failed: {e}", "ERROR")

def cleanup_after_update():
    script_dir = get_base_path()
    for name in ["mudae_bot.py.bak", "mudae_preset_editor.py.bak"]:
        bak = os.path.join(script_dir, name)
        if os.path.exists(bak):
            try:
                os.remove(bak)
                print_system_log(f"Backup cleaned: {name}", "INFO")
            except Exception: pass

presets = {}
presets_path = os.path.join(get_base_path(), "presets.json")
if not os.path.exists(presets_path):
    try:
        with open(presets_path, "w", encoding="utf-8") as f: json.dump({}, f, indent=4)
        print_system_log(f"Created missing {presets_path}", "INFO")
    except Exception as e:
        print_system_log(f"Error creating {presets_path}: {e}", "ERROR")

try:
    with open(presets_path, "r", encoding="utf-8") as f: presets = json.load(f)
except Exception as e:
    print_system_log(f"Failed to load {presets_path}: {e}", "ERROR")
    sys.exit(1)

if os.name == 'nt': os.system('')

TARGET_BOT_ID = 432610292342587392
CLAIM_EMOJIS = ['💖', '💗', '💘', '❤️', '💓', '💕', '♥️']
KAKERA_EMOJIS = ['kakeraY', 'kakeraO', 'kakeraR', 'kakeraW', 'kakeraL', 'kakeraP', 'kakeraD', 'kakeraC']
CHAOS_KAKERA_EMOJIS = ['kakeraY', 'kakeraO', 'kakeraR', 'kakeraW', 'kakeraL', 'kakeraP', 'kakeraD', 'kakeraC']
SPHERE_EMOJIS = ['spP', 'spB', 'spT', 'spG', 'spY', 'spO', 'spR', 'spW', 'spL', 'spD', 'spM', 'spP2', 'spB2', 'spT2', 'spG2', 'spY2', 'spO2', 'spR2', 'spW2', 'spL2', 'spD2', 'spU']

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

def parse_mudae_ranks(embed_description: str) -> tuple[int, int]:
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
            humanization_enabled, humanization_window_minutes, humanization_inactivity_seconds,
            dk_power_management, skip_initial_commands, use_slash_rolls, only_chaos,
            reactive_snipe_delay, time_rolls_to_claim_reset_preset,
            rt_ignore_min_kakera_for_wishlist_preset,
            claim_emojis_preset, kakera_emojis_preset, chaos_emojis_preset, sphere_perk_emojis_preset,
            rt_only_self_rolls_preset, reactive_kakera_delay_range_preset,
            claim_interval_preset, roll_interval_preset, avoid_list,
            inactive_hours_preset,
            auto_us_enabled, auto_us_limit, auto_us_stop_on_claim,
            kakera_power_thresholds, debug_mode, auto_mk_enabled_preset,
            auto_rolls_enabled, auto_rolls_limit, auto_rolls_in_key_mode,
            auto_rolls_only_claim_hour_preset,
            panic_roll_minutes_preset, lurker_mode_preset,
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
            mk_bypass_power_check=False,
            snipe_channels_preset=None,
            max_claim_rank_preset=0,
            max_like_rank_preset=0,
            auto_p_enabled=True,
            enable_hybrid_panic_claim_preset=False,
            hybrid_panic_instant_claim_min_kakera_preset=300,
            hybrid_panic_instant_claim_max_rank_preset=200,
            claim_rounds_thresholds_preset=None): 

    client = commands.Bot(command_prefix=prefix, chunk_guilds_at_startup=False, self_bot=True)
    client.is_paused = _global_paused
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
    client.avoid_list = set([a.lower() for a in avoid_list])
    
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

    client.enable_snipe_chat_reactions = enable_snipe_chat_reactions_preset
    client.snipe_chat_messages = snipe_chat_messages_preset or ["omg", "ezz"]
    client.farm_character = str(farm_character_preset or "").strip().lower()
    client.farm_character_enabled = farm_character_enabled_preset
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
    client.dk_consumption_chaos = 18
    client.kakera_reacted_messages = set()
    client.processed_claim_messages = set()
    client.last_successfully_claimed_character = None
    client._has_initialized = False
    client._main_loop_task = None
    client._immediate_check_event = None

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
    client.desync_detected = False
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

    def is_character_snipe_allowed(is_external_snipe: bool = False) -> bool:
        if client.next_claim_reset_at_utc:
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            if now_utc >= client.next_claim_reset_at_utc:
                client.claim_right_available = True
                client.last_successfully_claimed_character = None
                delta = datetime.timedelta(minutes=client.claim_interval)
                while client.next_claim_reset_at_utc <= now_utc:
                    client.next_claim_reset_at_utc += delta
                BotLogger.log("Local prediction: Reset time reached. Claim right restored.", preset_name, "CLAIM")
        
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

    def get_current_dk_power() -> int:
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
        claim_reset_minutes = None
        if client.next_claim_reset_at_utc:
            now_utc = datetime.datetime.now(timezone.utc)
            claim_reset_minutes = (client.next_claim_reset_at_utc - now_utc).total_seconds() / 60.0

        total_rounds = (client.claim_interval + 59) // 60
        if claim_reset_minutes is None or claim_reset_minutes <= 0:
            round_num = total_rounds
        else:
            minutes = min(claim_reset_minutes, client.claim_interval)
            if minutes % 60 == 0:
                round_num = total_rounds - (minutes // 60) + 1
            else:
                round_num = total_rounds - (minutes // 60)
            round_num = max(1, min(round_num, total_rounds))

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
            BotLogger.log(
                f"Dynamic override switched to Round {round_num} thresholds "
                f"(Min Kakera: {client.min_kakera}, Max Claim Rank: {client.max_claim_rank}, Max Like Rank: {client.max_like_rank})", 
                preset_name, "RESET"
            )

    async def scheduled_roll_task(channel):
        BotLogger.log(f"Scheduled roll mode active. Times: {client.scheduled_roll_times}", preset_name, "INFO")
        while not client.is_closed():
            try:
                if client.is_paused:
                    await asyncio.sleep(1)
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
                    await asyncio.sleep(60)
                    continue
                BotLogger.log(f"Next scheduled roll at {next_time.strftime('%H:%M')} (in {min_wait/60:.1f}m)", preset_name, "RESET")
                await asyncio.sleep(min_wait)
                
                if client.humanization_enabled and client.humanization_window_minutes > 0:
                    jitter = random.uniform(0, client.humanization_window_minutes * 60)
                    BotLogger.log(f"Humanized delay: waiting {jitter/60:.1f}m before scheduled roll.", preset_name, "INFO")
                    await asyncio.sleep(jitter)
                if is_maintenance_active() or is_inactive_hour(): continue
                BotLogger.log("Executing scheduled roll.", preset_name, "INFO")
                if client._immediate_check_event: client._immediate_check_event.set()
            except asyncio.CancelledError: break
            except Exception as e:
                BotLogger.log(f"Scheduled roll error: {e}", preset_name, "ERROR")
                await asyncio.sleep(60)

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
            if el < client.slash_min_interval: await asyncio.sleep(client.slash_min_interval - el)
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
            await client.http.request(Route("POST", "/interactions"), json=payload)
            client.slash_fail_streak = 0
            client.slash_rate_limited_until = 0.0
            return True
        except discord.HTTPException as e:
            if getattr(e, "retry_after", None):
                client.slash_rate_limited_until = time.time() + min(e.retry_after, client.slash_max_backoff)
                await asyncio.sleep(e.retry_after)
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
        if not cmd: return
        if client.use_slash_rolls and not client.slash_fallback_active:
            override = {"w": "wx", "h": "hx", "m": "mx"}.get(cmd.lower(), cmd)
            if await _trigger_mudae_slash(channel, f"/{override}"): return
            if not client.slash_fallback_active: return
        await channel.send(f"{client.mudae_prefix}{cmd}")

    async def send_tu_command(channel):
        if client.use_slash_rolls and not client.slash_fallback_active:
            for attempt in range(1, 4):
                if await _trigger_mudae_slash(channel, "tu"): return True
                if client.slash_fallback_active: break
                if attempt < 3: await asyncio.sleep(5.0)
            if not client.slash_fallback_active:
                BotLogger.log("/tu failed after 3 attempts. Cooldown of 30m activated.", preset_name, "ERROR")
                await asyncio.sleep(1800)
                return False
        await channel.send(f"{client.mudae_prefix}tu")
        return True

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
                    await asyncio.sleep(1)
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
        
        BotLogger.log(f"Starting in {start_delay}s...", preset_name, "INFO")
        await asyncio.sleep(start_delay + random.uniform(0.1, 0.5))

        if is_inactive_hour():
            wait_s = seconds_until_active() + (random.uniform(0, client.humanization_window_minutes * 60) if client.humanization_enabled else 0)
            BotLogger.log(f"Inactive hours active. Sleeping {wait_s/60:.0f}m.", preset_name, "RESET")
            await asyncio.sleep(wait_s)

        if client.rolling_enabled:
            if not client.skip_initial_commands:
                cmd_ch = _get_command_channel() or channel
                try:
                    await cmd_ch.send(f"{client.mudae_prefix}limroul 1 1 1 1")
                    await asyncio.sleep(1.0 + random.uniform(0.1, 0.4))
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
            if getattr(client, 'only_chaos', False): cost = int(cost / 2)
            
            if cur_power < cost:
                BotLogger.log(f"DK: Activating. ({cur_power}% < {cost}%)", preset_name, "KAKERA")
                await channel.send(f"{client.mudae_prefix}dk")
                await asyncio.sleep(1.5 + random.uniform(0.1, 0.4))
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
                await asyncio.sleep(1)
                continue
            try:
                await check_status(client, channel, client.mudae_prefix, proceed_to_rolls=False)
                if client.next_claim_reset_at_utc:
                    handshake = True
                    break
                await asyncio.sleep(30)
            except Exception:
                await asyncio.sleep(30)
        if not handshake: return
        BotLogger.log("Snipe-only: Handshake complete. Entering Ghost Mode.", preset_name, "INFO")
        while not client.is_closed():
            if client.is_paused:
                await asyncio.sleep(1)
                continue
            now = datetime.datetime.now(datetime.timezone.utc)
            if not client.claim_right_available:
                if client.next_claim_reset_at_utc and client.next_claim_reset_at_utc > now:
                    wait_s = max(5.0, (client.next_claim_reset_at_utc - now).total_seconds() + 2.0)
                    BotLogger.log(f"Snipe-only: Silent. Sleeping {wait_s/60:.1f}m.", preset_name, "RESET")
                    try: await asyncio.sleep(wait_s)
                    except asyncio.CancelledError: break
                    if datetime.datetime.now(datetime.timezone.utc) >= client.next_claim_reset_at_utc:
                        client.claim_right_available = True
                        client.last_successfully_claimed_character = None
                        delta = datetime.timedelta(minutes=client.claim_interval)
                        while client.next_claim_reset_at_utc <= datetime.datetime.now(datetime.timezone.utc):
                            client.next_claim_reset_at_utc += delta
                else:
                    await asyncio.sleep(10)
            else:
                await asyncio.sleep(10)

    async def _interruptible_sleep(seconds):
        evt = client._immediate_check_event
        if evt:
            evt.clear()
            try: await asyncio.wait_for(evt.wait(), timeout=seconds)
            except asyncio.TimeoutError: pass
        else:
            await asyncio.sleep(seconds)

    async def check_status(client, channel, mudae_prefix, proceed_to_rolls: bool = True, current_cycle_id=None):
        if getattr(client, 'is_claiming', False): return
        if getattr(client, 'is_processing_cycle', False): return
        client.is_processing_cycle = True
        
        update_dynamic_thresholds()
        
        try:
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            if current_cycle_id is None:
                current_cycle_id = time.time()
                client.active_cycle_id = current_cycle_id
            cmd_channel = _get_command_channel() or channel
            
            can_bypass = False
            if client.last_tu_query_utc is not None and not client.desync_detected:
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

            if can_bypass:
                BotLogger.log("Skipping $tu (using cached status).", preset_name, "CHECK")
                claim_reset_m = max(0, int((client.next_claim_reset_at_utc - now_utc).total_seconds() / 60)) if client.next_claim_reset_at_utc else 0
                roll_reset_m = max(0, int((client.roll_reset_at_utc - now_utc).total_seconds() / 60)) if client.roll_reset_at_utc else 0
                wait_time = claim_reset_m if not client.claim_right_available else 0
                if client.rolling_enabled and proceed_to_rolls:
                    choices = []
                    if wait_time > 0: choices.append((float(wait_time), "claim cooldown"))
                    if client.time_rolls_to_claim_reset and not client.claim_right_available and claim_reset_m > 60: choices.append((float(claim_reset_m - 60), "timing threshold arrival"))
                    if roll_reset_m > 0: choices.append((float(roll_reset_m), "rolls replenishment"))
                    if choices:
                        choices.sort(key=lambda x: x[0])
                        await humanized_wait_and_proceed(client, channel, max(0.5, choices[0][0]), choices[0][1])
                    else:
                        await humanized_wait_and_proceed(client, channel, 30, "default status cycle")
                return

            BotLogger.log("Checking $tu...", preset_name, "CHECK")
            tu_content = None
            if client.tu_lock is None: client.tu_lock = asyncio.Lock()
            if client.tu_lock.locked(): return

            def is_for_self(text):
                m = re.match(REGEX_PATTERNS["USER_BOLD"], text)
                return m and m.group(1).strip().lower() in [client.user.name.lower(), getattr(client.user, 'display_name', '').lower()]

            async with client.tu_lock:
                for _ in range(5):
                    await send_tu_command(cmd_channel)
                    await asyncio.sleep(2.5 + random.uniform(0.2, 0.6))
                    async for msg in cmd_channel.history(limit=10):
                        if msg.author.id == TARGET_BOT_ID and msg.content:
                            c = msg.content.lower()
                            if ("roll" in c and "min" in c) or ("roll" in c and "**" in c):
                                if is_for_self(msg.content):
                                    tu_content = msg.content
                                    break
                                else:
                                    other = re.match(r"^\s*\*\*([^*]+)\*\*", msg.content)
                                    BotLogger.log(f"Skipped $tu response for '{other.group(1) if other else 'Unknown'}'", preset_name, "INFO")
                    if tu_content: break
                    await asyncio.sleep(5)
                
                if not tu_content:
                    BotLogger.log("Failed to get $tu response.", preset_name, "ERROR")
                    if client.rolling_enabled and proceed_to_rolls: await _interruptible_sleep(1800)
                    return

                c_lower = tu_content.lower()

            if client.auto_dk_enabled and client.dk_power_management and client.rolling_enabled:
                await handle_dk_power_management(client, cmd_channel, tu_content)

            if client.rolling_enabled:
                if any(x in c_lower for x in ["$daily is available", "$daily está disponível", "$daily está disponible", "$daily est disponible"]):
                    BotLogger.log("$daily is available! Sending command...", preset_name, "INFO")
                    await cmd_channel.send(f"{client.mudae_prefix}daily")
                    await asyncio.sleep(2.0 + random.uniform(0.1, 0.5))

                if client.auto_dk_enabled and not client.dk_power_management:
                    if re.search(r"\$dk.*?(?:ready|pronto|disponible|prêt|dispon[ií]vel|listo)", c_lower):
                        BotLogger.log("$dk is ready! Sending command...", preset_name, "INFO")
                        await cmd_channel.send(f"{client.mudae_prefix}dk")
                        await asyncio.sleep(2.0 + random.uniform(0.1, 0.5))

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
                            await cmd_channel.send(f"{client.mudae_prefix}p")
                            client.p_available = False
                            client.next_p_claim_at_utc = (datetime.datetime.now(timezone.utc) + datetime.timedelta(hours=2)).replace(second=0, microsecond=0)
                            await asyncio.sleep(2.0 + random.uniform(0.1, 0.5))

            try:
                power_match = re.search(REGEX_PATTERNS["DK_POWER"], c_lower)
                if power_match:
                    client.current_dk_power = int(power_match.group(1))
                    client.last_dk_power_update_utc = datetime.datetime.now(timezone.utc)
                consumption_match = re.search(REGEX_PATTERNS["DK_CONSUMPTION"], c_lower)
                if consumption_match:
                    client.dk_consumption = int(consumption_match.group(1))
                    client.dk_consumption_chaos = int(client.dk_consumption / 2)
                dk_stock_match = re.search(REGEX_PATTERNS["DK_STOCK"], c_lower)
                if dk_stock_match: client.dk_stock_count = int(dk_stock_match.group(1))
                elif re.search(REGEX_PATTERNS["DK_READY"], c_lower): client.dk_stock_count = 1
                else: client.dk_stock_count = 0
            except Exception as e:
                BotLogger.log(f"Error parsing Power/DK state: {e}", preset_name, "WARN")

            rt_ready = any(x in c_lower for x in ["$rt is available", "$rt está pronto", "$rt esta pronto", "$rt está disponível", "$rt está disponible", "$rt est disponible", "$rt est prêt", "$rt is ready"])
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
                BotLogger.log("Claim: Ready", preset_name, "INFO")
                client.current_min_kakera_for_roll_claim = client.min_kakera
                if client.snipe_ignore_min_kakera_reset and claim_reset_minutes is not None and claim_reset_minutes <= 60:
                    client.current_min_kakera_for_roll_claim = 0
                    BotLogger.log(f"Reset soon ({claim_reset_minutes}m). Ignoring Min Kakera.", preset_name, "WARN")
                client.next_claim_reset_at_utc = (now_utc + datetime.timedelta(minutes=claim_reset_minutes or 1)).replace(second=0, microsecond=0)
                can_claim = True
            else:
                client.claim_right_available = False
                client.current_min_kakera_for_roll_claim = client.min_kakera
                if claim_reset_minutes is not None and claim_reset_minutes > 0:
                     BotLogger.log(f"Claim: Cooldown ({int(claim_reset_minutes/60)}h {claim_reset_minutes%60}m)", preset_name, "INFO")
                     target_time = (now_utc + datetime.timedelta(minutes=claim_reset_minutes)).replace(second=0, microsecond=0)
                     client.claim_cooldown_until_utc = client.next_claim_reset_at_utc = target_time
                else:
                     wait_g = parse_timer_minutes("GENERIC_COOLDOWN", c_lower.split('\n')[0])
                     if wait_g is not None:
                          wait_time = wait_g
                          BotLogger.log(f"Claim: Cooldown ({int(wait_time/60)}h {wait_time%60}m) (Generic)", preset_name, "INFO")
                          target_time = (now_utc + datetime.timedelta(minutes=wait_time)).replace(second=0, microsecond=0)
                          client.claim_cooldown_until_utc = client.next_claim_reset_at_utc = target_time
                          claim_reset_minutes = wait_time
                 
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
            client.desync_detected = False
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
                             ((can_claim and not is_lurking) or client.key_mode or client.rt_available or is_timing_window or is_panic_window))
            
            mk_match = re.search(REGEX_PATTERNS["MK_BONUS"], c_lower)
            client.mk_rolls_left = int(re.sub(r"[^\d]", "", mk_match.group(1))) if mk_match else 0
                
            if client.rolling_enabled and proceed_to_rolls and not immediate_roll:
                if client.auto_mk_enabled and client.mk_rolls_left > 0 and (get_current_dk_power() >= client.dk_consumption or client.mk_bypass_power_check):
                    await process_mk_rolls(client, channel, current_cycle_id)
                    await asyncio.sleep(2)
                    return
            
            if immediate_roll:
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
                    await humanized_wait_and_proceed(client, channel, max(0.5, sleep_choices[0][0]), sleep_choices[0][1])
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
                    await asyncio.sleep(wait_s)
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
                            await rolls_cmd_ch.send(f"{client.mudae_prefix}rolls")
                            client.rolls_item_used_count += 1
                            client.rolls_used_this_interval_utc = client.roll_reset_at_utc
                            client.desync_detected = True
                            await asyncio.sleep(2.0 + random.uniform(0.1, 0.5))
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
                                        await channel.send(f"{client.mudae_prefix}us {chk}")
                                        client.last_us_attempt_utc = datetime.datetime.now(timezone.utc)
                                        await asyncio.sleep(random.uniform(1.5, 2.5))
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
                                        client.desync_detected = True
                                        await start_roll_commands(client, channel, pulled, ignore_limit_for_post_roll, key_mode_only_kakera_for_post_roll, current_cycle_id, is_us_pull=True)
                                        return
                                    elif rolls_left > 0:
                                        await start_roll_commands(client, channel, rolls_left, ignore_limit_for_post_roll, key_mode_only_kakera_for_post_roll, current_cycle_id)
                                        return
                                else:
                                    step = min(20, amt)
                                    await channel.send(f"{client.mudae_prefix}us {step}")
                                    client.last_us_attempt_utc = datetime.datetime.now(timezone.utc)
                                    BotLogger.log(f"Auto $us: Pulled batch of {step} rolls...", preset_name, "INFO")
                                    await asyncio.sleep(random.uniform(1.5, 2.5))
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
                                        client.desync_detected = True
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

                if c_min is not None and c_min > 0:
                    sleep_candidates.append((float(c_min), "claim reset"))
                    if client.time_rolls_to_claim_reset and c_min > 60: sleep_candidates.append((float(c_min - 60), "timing window arrival"))
                    if client.claim_right_available and c_min > client.panic_roll_minutes: sleep_candidates.append((float(c_min - client.panic_roll_minutes), "panic roll arrival"))
                sleep_candidates.sort(key=lambda x: x[0])
                await humanized_wait_and_proceed(client, channel, max(0.5, sleep_candidates[0][0]), sleep_candidates[0][1])
            else:
                BotLogger.log(f"Rolls: {total_rolls}" + (f" (+{us_rolls_left} $us)" if us_rolls_left > 0 else "") + f". Reset: {reset_time_r}m", preset_name, "INFO")
                await start_roll_commands(client, channel, total_rolls, ignore_limit_for_post_roll, key_mode_only_kakera_for_post_roll, current_cycle_id)
        else:
            BotLogger.log("Could not parse roll count.", preset_name, "ERROR")
            await asyncio.sleep(30)

    async def process_mk_rolls(client, channel, current_cycle_id):
        if channel.id != client.target_channel_id:
            channel = client.get_channel(client.target_channel_id) or client._main_channel or channel
        if not getattr(client, 'auto_mk_enabled', True) or client.mk_rolls_left <= 0: return
        
        if get_current_dk_power() >= client.dk_consumption or client.mk_bypass_power_check:
            used = 0
            while client.mk_rolls_left > 0 and (get_current_dk_power() >= client.dk_consumption or client.mk_bypass_power_check):
                BotLogger.log(f"Using $mk ({client.mk_rolls_left} left, Power: {get_current_dk_power()}%)", preset_name, "KAKERA")
                await channel.send(f"{client.mudae_prefix}mk")
                client.mk_rolls_left -= 1
                used += 1
                await asyncio.sleep(3)
                async for msg in channel.history(limit=5, oldest_first=False):
                    if msg.author.id == TARGET_BOT_ID and msg.embeds and is_character_embed(msg.embeds[0]) and msg.components:
                        await claim_character(client, channel, msg, is_kakera=True, is_mk_roll=True)
                        break
                await asyncio.sleep(1)
            if used > 0: BotLogger.log(f"Used {used} $mk rolls.", preset_name, "KAKERA")
        else:
            BotLogger.log(f"Skipping $mk: Insufficient power ({get_current_dk_power()}% < {client.dk_consumption}%).", preset_name, "INFO")

    async def start_roll_commands(client, channel, rolls_left, ignore_limit_for_post_roll, key_mode_only_kakera_for_post_roll, current_cycle_id, is_us_pull: bool = False):
        if channel.id != client.target_channel_id:
            channel = client.get_channel(client.target_channel_id) or client._main_channel or channel
        if client.farm_character_enabled and client.farm_character and client.claim_right_available:
            BotLogger.log(f"Kakera Farm: Preparing {client.farm_character} for rolling.", preset_name, "INFO")
            await channel.send(f"{client.mudae_prefix}forcedivorce {client.farm_character}")
            await asyncio.sleep(1.5 + random.uniform(0.1, 0.4))
            await channel.send("y")
            await asyncio.sleep(1.5 + random.uniform(0.1, 0.4))

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
                    await asyncio.sleep(wait_s)
                    is_timing_mode_active = True

        BotLogger.log(f"Rolling {rolls_left} times" + (" (Reactive)" if client.enable_reactive_self_snipe else ""), preset_name, "INFO")
        client.is_actively_rolling = True
        client.interrupt_rolling = False
        client._rolls_sent = client._rolls_received = 0
        client.collected_rolls = []
        
        for i in range(rolls_left):
            if client.interrupt_rolling:
                client.desync_detected = True
                break
            try:
                await send_roll_command(channel, roll_command)
                client._rolls_sent += 1
                client.rolls_left = max(0, client.rolls_left - 1)
                roll_delay = (max(2.0, client.roll_speed) if client.use_slash_rolls else client.roll_speed) + random.uniform(0.05, 0.25)
                await asyncio.sleep(roll_delay)
            except Exception:
                await asyncio.sleep(1.0 + random.uniform(0.1, 0.3))
                
        timeout, poll_start = 5.0, time.time()
        while time.time() - poll_start < timeout and client._rolls_received < client._rolls_sent:
            await asyncio.sleep(0.05)

        client.is_actively_rolling = False
        
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
        await asyncio.sleep(1.0 + random.uniform(0.1, 0.5))

    async def execute_auto_divorce(client, channel, char_name):
        try:
            await asyncio.sleep(random.uniform(1.5, 2.5))
            await channel.send(f"{client.mudae_prefix}divorce {char_name}")
            BotLogger.log(f"Auto-Divorce: Initiating divorce for {char_name}...", preset_name, "INFO")
            await asyncio.sleep(random.uniform(1.5, 2.5))
            
            char_tag = f"**{char_name.lower()}**"
            confirm = False
            async for msg in channel.history(limit=8):
                if msg.author.id == TARGET_BOT_ID and msg.content:
                    c = msg.content.lower()
                    if char_tag in c and ("(y/n" in c or "yes/no" in c or "(y /" in c):
                        confirm = True
                        break
            if not confirm: return False
            
            await asyncio.sleep(random.uniform(1.5, 2.5))
            await channel.send("y")
            await asyncio.sleep(random.uniform(1.5, 2.5))
            
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

    async def verify_snipe_outcome(client, channel, char_name, is_snipe_action=True, character_kakera=0, character_series=""):
        await asyncio.sleep(2.0 + random.uniform(0.2, 0.6))
        success = False
        winner = None
        bot_u = client.user.name.lower()
        bot_d = (client.user.display_name or client.user.name).lower()
        char_tag = f"**{char_name.lower()}**"
        
        async for msg in channel.history(limit=8):
            if msg.author.id == TARGET_BOT_ID and msg.content:
                c = msg.content.lower()
                if char_tag in c:
                    bolds = [b.lower() for b in re.findall(REGEX_PATTERNS["BOLD_TEXT"], c)]
                    if bot_u in bolds or bot_d in bolds:
                        success = True
                        break
                    else:
                        non_char = [b for b in bolds if b != char_name.lower()]
                        if non_char: winner = non_char[0]
                if not success and not winner and char_name.lower() in c:
                    if bot_u in c or bot_d in c: success = True
                    else: winner = "Someone else (Custom)"
                if success or winner: break

        lbl = "Snipe Verification" if is_snipe_action else "Claim Verification"
        if success:
            BotLogger.log(f"{lbl}: SUCCESS! We got {char_name}.", preset_name, "CLAIM")
            if client.auto_divorce_enabled:
                should = False
                reason = ""
                if character_kakera > 0 and character_kakera <= client.auto_divorce_max_kakera:
                    should, reason = True, f"kakera {character_kakera} <= {client.auto_divorce_max_kakera}"
                if not should and character_series and client.auto_divorce_series:
                    if any(s.lower() in character_series.lower() for s in client.auto_divorce_series):
                        should, reason = True, f"series match in '{character_series[:60]}'"
                if should:
                    BotLogger.log(f"Auto-Divorce: {char_name} qualifies ({reason}).", preset_name, "INFO")
                    await execute_auto_divorce(client, channel, char_name)
            
            client.claim_right_available = False
            client.last_successfully_claimed_character = char_name.lower()
            now = datetime.datetime.now(timezone.utc)
            if client.next_claim_reset_at_utc:
                base = client.next_claim_reset_at_utc
                delta = datetime.timedelta(minutes=client.claim_interval)
                while base <= now: base += delta
                client.next_claim_reset_at_utc = base.replace(second=0, microsecond=0)
            else:
                client.next_claim_reset_at_utc = (now + datetime.timedelta(minutes=client.claim_interval)).replace(second=0, microsecond=0)
                
            if client.auto_rt_after_claim:
                mins_to_reset = ((client.next_claim_reset_at_utc - now).total_seconds() / 60.0) if client.next_claim_reset_at_utc else None
                if mins_to_reset is not None and mins_to_reset < 60:
                    BotLogger.log(f"Auto $rt: SKIPPED — resets soon ({mins_to_reset:.0f}m).", preset_name, "INFO")
                elif not client.is_actively_rolling:
                    BotLogger.log("Auto $rt: SKIPPED — rolling sequence finished.", preset_name, "INFO")
                else:
                    BotLogger.log(f"Auto $rt: Sending $rt after claiming {char_name}.", preset_name, "CLAIM")
                    try:
                        await channel.send(f"{client.mudae_prefix}rt")
                        client.rt_available = False
                        client.claim_right_available = True
                    except Exception as e:
                        BotLogger.log(f"Auto $rt failed: {e}", preset_name, "ERROR")

            if client.farm_character_enabled and char_name.lower() == client.farm_character:
                if client.rt_available:
                    await channel.send(f"{client.mudae_prefix}rt")
                    client.rt_available = False
                    await asyncio.sleep(1.5)
                    await channel.send(f"{client.mudae_prefix}forcedivorce {client.farm_character}")
                    await asyncio.sleep(1.5)
                    await channel.send("y")
                    client.claim_right_available = True

            if is_snipe_action and client.enable_snipe_chat_reactions and client.snipe_chat_messages:
                try:
                    await asyncio.sleep(random.uniform(2.0, 5.0))
                    msg_reaction = random.choice(client.snipe_chat_messages)
                    await channel.send(msg_reaction)
                except Exception as e:
                    BotLogger.log(f"Snipe chat reaction failed: {e}", preset_name, "ERROR")
        elif winner:
            BotLogger.log(f"{lbl}: FAILED. Taken by {winner}.", preset_name, "WARN")
        else:
            BotLogger.log(f"{lbl}: Inconclusive.", preset_name, "WARN")

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
            is_k = msg.components and any(hasattr(b.emoji, 'name') and b.emoji.name and (b.emoji.name in all_k or b.emoji.name.rstrip('2') in all_k) for comp in msg.components for b in comp.children)
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
                    
                    series = (embed.description or "").splitlines()[0].lower()
                    claims_r, likes_r = parse_mudae_ranks(embed.description or "")
                    is_ranked = (client.max_claim_rank > 0 and 0 < claims_r <= client.max_claim_rank) or (client.max_like_rank > 0 and 0 < likes_r <= client.max_like_rank)
                    is_wl = c_name in client.wishlist or (client.series_snipe_mode and any(s in series for s in client.series_wishlist)) or is_wished_by_self(msg, client.user.id) or is_ranked
                    is_avoided = c_name in client.avoid_list
                    
                    if is_wl and not is_avoided: wl_claims.append((msg, c_name, k_v, series))
                    elif k_v >= min_kak_post and not is_avoided: char_claims.append((msg, c_name, k_v, series))

        for msg_k in k_claims:
            await claim_character(client, channel, msg_k, is_kakera=True)
            await asyncio.sleep(0.3)
        
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
            
            rt_targets.sort(key=lambda x: (x[2], x[0].id), reverse=True)
            for msg_rt, n_rt, v_rt in rt_targets:
                if n_rt in attempted: continue
                BotLogger.log(f"Attempting RT on {n_rt} ({v_rt})", preset_name, "CLAIM")
                try:
                    await channel.send(f"{client.mudae_prefix}rt")
                    client.rt_available = False
                    attempted.add(n_rt)
                    await asyncio.sleep(0.7)
                    await claim_character(client, channel, msg_rt, is_rt_claim=True, kakera_value=v_rt)
                    break
                except Exception: pass

    async def claim_character(client, channel, msg, is_kakera=False, is_rt_claim=False, is_snipe=False, is_free_claim=False, kakera_value=None, is_mk_roll=False):
        if not msg or not msg.embeds: return False
        
        def check_is_green(b):
            s = getattr(b, 'style', None)
            return s is not None and (getattr(s, 'value', None) == 3 or str(s).endswith('success') or str(s) == '3')

        if msg.id in client.processed_claim_messages: return False

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

        client.processed_claim_messages.add(msg.id)
        if len(client.processed_claim_messages) > 1000: client.processed_claim_messages.clear()

        if not is_kakera: client.is_claiming = True
        try:
            if not is_kakera and not is_free_claim and not is_rt_claim:
                if not client.claim_right_available and client.rt_available and not (is_snipe and client.rt_only_self_rolls):
                    BotLogger.log(f"Using RT for {char_name}", preset_name, "CLAIM")
                    try:
                        await channel.send(f"{client.mudae_prefix}rt")
                        client.rt_available = False
                        await asyncio.sleep(random.uniform(0.6, 1.0))
                    except Exception as e:
                        BotLogger.log(f"RT Failed: {e}", preset_name, "ERROR")
                        return False

            if is_free_claim: await asyncio.sleep(random.uniform(1.0, 2.5))

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
                
                has_sp_perk = "💎/2" in (embed.description or "")
                target_list = client.kakera_emojis if is_snipe else (client.sphere_perk_emojis if has_sp_perk else (client.chaos_emojis if chaos_count > 0 else client.kakera_emojis))
                target_list = target_list + client.sphere_emojis

                cooldown_active = not is_kakera_reaction_allowed()
                has_free_button = msg.components and any(hasattr(b.emoji, 'name') and (b.emoji.name == 'kakeraP' or b.emoji.name in client.sphere_emojis or check_is_green(b)) for c in msg.components for b in c.children)
                if cooldown_active and not has_free_button and chaos_count == 0 and not has_sp_perk: return False

                if msg.id in client.kakera_reacted_messages: return False
                if len(client.kakera_reacted_messages) > 2000: client.kakera_reacted_messages.clear()

                clicked = False
                if msg.components:
                    all_btns_tracked = []
                    for row_idx, comp in enumerate(msg.components):
                        for child_idx, btn in enumerate(comp.children):
                            if hasattr(btn.emoji, 'name') and btn.emoji.name:
                                name_clean = btn.emoji.name.rstrip('2')
                                if btn.emoji.name in target_list or name_clean in target_list:
                                    all_btns_tracked.append({
                                        'btn': btn,
                                        'custom_id': btn.custom_id,
                                        'pos': (row_idx, child_idx),
                                        'emoji_name': btn.emoji.name
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
                        
                        is_free = name == 'kakeraP' or name in client.sphere_emojis or check_is_green(btn)
                        cost = 0 if is_free else (client.dk_consumption_chaos if chaos_count > 0 else client.dk_consumption)
                        current_pow = get_current_dk_power()
                        
                        if current_pow < cost:
                            if client.auto_dk_enabled and client.dk_power_management and client.dk_stock_count > 0:
                                log_name = btn.emoji.name if hasattr(btn.emoji, 'name') else 'Kakera'
                                BotLogger.log(f"Dynamic DK Refill: Power too low ({current_pow}% < {cost}%). Sending $dk for {log_name}...", preset_name, "KAKERA")
                                try:
                                    cmd_ch = _get_command_channel() or channel
                                    await cmd_ch.send(f"{client.mudae_prefix}dk")
                                    client.dk_stock_count = max(0, client.dk_stock_count - 1)
                                    client.current_dk_power = client.max_dk_power
                                    client.last_dk_power_update_utc = datetime.datetime.now(timezone.utc)
                                    await asyncio.sleep(1.2 + random.uniform(0.1, 0.4))
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
                            spec_name = f"chaos_{base_name}" if chaos_count > 0 else base_name
                            threshold = client.kakera_power_thresholds.get(spec_name) or client.kakera_power_thresholds.get(base_name) or client.kakera_power_thresholds.get(name)
                            if threshold is not None and current_pow < threshold:
                                BotLogger.log(f"Power ({current_pow}%) below threshold ({threshold}%) for {spec_name}. Waiting.", preset_name, "INFO")
                                continue

                        if client.debug_mode:
                            ws_ref = getattr(client, 'ws', None)
                            sid = getattr(ws_ref, 'session_id', None) if ws_ref else None
                            BotLogger.log(f"Kakera Click: custom_id={getattr(btn, 'custom_id', 'N/A')} | name={name} | session_id={sid}", preset_name, "DEBUG", client)

                        try:
                            await btn.click()
                            client.current_dk_power = max(0, get_current_dk_power() - cost)
                            client.kakera_reacted_messages.add(msg.id)
                            BotLogger.log(f"Kakera clicked: {char_name} [{name}] (Pw: {client.current_dk_power}%)", preset_name, "KAKERA")
                            clicked = True
                            clicked_count += 1
                            client._last_kakera_click_ts = time.time()
                            await asyncio.sleep(0.6)
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
                        if is_free_claim or (has_emoji and btn.emoji.name in client.claim_emojis):
                            if client.debug_mode:
                                ws_ref = getattr(client, 'ws', None)
                                sid = getattr(ws_ref, 'session_id', None) if ws_ref else None
                                BotLogger.log(f"Claim Click: custom_id={getattr(btn, 'custom_id', 'N/A')} | session_id={sid}", preset_name, "DEBUG", client)

                            claim_success = False
                            for attempt in range(3):
                                try:
                                    await btn.click()
                                    claim_success = True
                                    break
                                except Exception as e:
                                    if attempt < 2:
                                        BotLogger.log(f"Claim click failed (attempt {attempt+1}/3): {e}. Retrying...", preset_name, "WARN")
                                        await asyncio.sleep(0.5)
                                    else:
                                        BotLogger.log(f"Claim click failed after 3 attempts: {e}", preset_name, "ERROR")
                            
                            if claim_success:
                                BotLogger.log(f"Claiming {char_name}{kakera_str}", preset_name, "CLAIM" if not is_free_claim else "INFO")
                                clicked_claim = True
                                _claim_kv = kakera_value or 0
                                _claim_series = embed.description.splitlines()[0] if embed and embed.description else ""
                                await verify_snipe_outcome(client, channel, char_name, is_snipe_action=is_snipe, character_kakera=_claim_kv, character_series=_claim_series)
                                return True
            
            if not clicked_claim and has_claim_option(msg, embed, client.claim_emojis):
                try:
                    reaction_emoji = random.choice(client.randomized_claim_reactions)
                    await msg.add_reaction(reaction_emoji)
                    BotLogger.log(f"Claiming {char_name}{kakera_str} (Reaction: {reaction_emoji})", preset_name, "CLAIM")
                    _react_kv = kakera_value or 0
                    _react_series = embed.description.splitlines()[0] if embed and embed.description else ""
                    await verify_snipe_outcome(client, channel, char_name, is_snipe_action=is_snipe, character_kakera=_react_kv, character_series=_react_series)
                    return True
                except Exception as e:
                    BotLogger.log(f"Reaction fallback FAILED: {e}", preset_name, "ERROR")
                    return False
            return False
        finally:
            if not is_kakera: client.is_claiming = False

    async def humanized_wait_and_proceed(client, channel, base_reset_minutes, reason="reset"):
        min_wait = max(0.0, base_reset_minutes * 60)
        if min_wait <= 0: min_wait = max(client.delay_seconds + 60, 240)
        human_jitter = random.uniform(0, max(0.0, client.humanization_window_minutes * 60)) if client.humanization_enabled else 0
        wait_seconds = min_wait + human_jitter
        
        BotLogger.log(f"{'Humanized ' if client.humanization_enabled else ''}Waiting {wait_seconds/60:.1f}m ({reason}).", preset_name, "RESET")
        await asyncio.sleep(wait_seconds)

        if is_inactive_hour():
            wait_s = seconds_until_active() + (random.uniform(0, client.humanization_window_minutes * 60) if client.humanization_enabled else 0)
            BotLogger.log(f"Inactive hours. Sleeping {wait_s/60:.0f}m.", preset_name, "RESET")
            await asyncio.sleep(wait_s)

        if client.humanization_enabled:
            while True:
                try:
                    last_msg = None
                    async for m in channel.history(limit=1): last_msg = m
                    if not last_msg: break
                    diff = (datetime.datetime.now(timezone.utc) - last_msg.created_at).total_seconds()
                    if diff >= client.humanization_inactivity_seconds: break
                    await asyncio.sleep(client.humanization_inactivity_seconds - diff + 0.5)
                except Exception: break

    async def handle_birthday_candle(msg):
        await asyncio.sleep(random.uniform(0.5, 2.0))
        if msg.components:
            for comp in msg.components:
                for btn in comp.children:
                    if hasattr(btn.emoji, 'name') and btn.emoji.name == '🕯️':
                        try:
                            await btn.click()
                            c_name = msg.embeds[0].author.name if msg.embeds and msg.embeds[0].author else "Unknown"
                            BotLogger.log(f"🕯️ Clicked candle for {c_name}", preset_name, "CLAIM")
                        except Exception: pass
                        return

    @client.event
    async def on_message(message):
        if client.is_paused: return
        
        update_dynamic_thresholds()
        is_roll = (message.channel.id == client.target_channel_id)
        is_snipe = (client.snipe_mode and message.channel.id in client.snipe_channels)

        if message.author.id != TARGET_BOT_ID or not (is_roll or is_snipe):
            if client.rolling_enabled: await client.process_commands(message)
            return

        if message.content and "Command under maintenance!" in message.content:
            m_match = re.search(REGEX_PATTERNS["MAINTENANCE"], message.content)
            m_mins = int(m_match.group(1)) if m_match else 10
            client.maintenance_until = datetime.datetime.now(timezone.utc) + datetime.timedelta(minutes=m_mins)
            BotLogger.log(f"Mudae is under maintenance! Pausing for {m_mins} minutes.", preset_name, "ERROR")
            return

        if is_maintenance_active(): return

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

        if client.main_account_id:
            try: main_id = int(client.main_account_id)
            except ValueError: main_id = None
            if main_id is not None and message.embeds:
                embed_ma = message.embeds[0]
                if is_character_embed(embed_ma) and is_wished_by_self(message, main_id):
                    c_name = embed_ma.author.name.lower()
                    if c_name not in client.avoid_list and has_claim_option(message, embed_ma, client.claim_emojis):
                        if is_character_snipe_allowed(is_external_snipe=True):
                            BotLogger.log(f"Main Account Sync (wished by Main): {c_name}! Priority claiming.", preset_name, "CLAIM")
                            await asyncio.sleep(0.1 + random.uniform(0.01, 0.05))
                            if await claim_character(client, message.channel, message, is_snipe=True): return

        if message.content and not message.embeds and client.rolling_enabled:
            m_bonus = re.search(REGEX_PATTERNS["EXTRA_ROLLS"], message.content)
            if m_bonus and (time.time() - getattr(client, '_last_kakera_click_ts', 0)) <= 10:
                BotLogger.log(f"Gained +{m_bonus.group(1)} extra rolls from Kakera! Signaling main loop...", preset_name, "KAKERA")
                if client._immediate_check_event and not client.is_actively_rolling:
                    client._immediate_check_event.set()

        if not message.embeds: return
        embed = message.embeds[0]

        if not is_character_embed(embed):
            if client.kakera_reaction_snipe_mode_active and message.id not in client.kakera_reaction_sniped_messages:
                all_k = client.kakera_emojis + client.chaos_emojis + client.sphere_emojis
                has_btn = message.components and any(hasattr(b.emoji, 'name') and b.emoji.name and (b.emoji.name in all_k or b.emoji.name.rstrip('2') in all_k) for comp in message.components for b in comp.children)
                if has_btn:
                    if client.kakera_reaction_snipe_targets:
                        owner = get_character_owner(embed)
                        if not owner or owner not in client.kakera_reaction_snipe_targets: return
                    client.kakera_reaction_sniped_messages.add(message.id)
                    await asyncio.sleep(client.kakera_reaction_snipe_delay_value + random.uniform(0.05, 0.25))
                    await claim_character(client, message.channel, message, is_kakera=True, is_snipe=True)
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
                
                if is_high_value and not is_avoided and has_claim_option(message, embed, client.claim_emojis):
                    if is_key_mode_kakera_only():
                        pass
                    else:
                        client.interrupt_rolling = True
                        BotLogger.log(f"Hybrid Smart Instant Claim triggered for {c_name} ({k_val} ka)!", preset_name, "CLAIM")
                        if client.reactive_snipe_delay > 0:
                            await asyncio.sleep(client.reactive_snipe_delay + random.uniform(0.05, 0.25))
                        if await claim_character(client, message.channel, message, kakera_value=k_val):
                            process = False
                elif k_val >= client.current_min_kakera_for_roll_claim and not is_avoided:
                    client.collected_rolls.append(message)
            else:
                if not getattr(client, 'enable_reactive_self_snipe', True):
                    client.collected_rolls.append(message)
                else:
                    is_val = k_val >= client.current_min_kakera_for_roll_claim
                    if (is_wl or is_val) and not is_avoided and has_claim_option(message, embed, client.claim_emojis):
                        if is_key_mode_kakera_only():
                            pass
                        else:
                            if not client.claim_right_available and not client.rt_available and client.next_claim_reset_at_utc:
                                t_to_r = (client.next_claim_reset_at_utc - datetime.datetime.now(timezone.utc)).total_seconds()
                                if 0 < t_to_r <= 15:
                                    BotLogger.log(f"Claim reset is in {t_to_r:.1f}s. Waiting for reset...", preset_name, "INFO")
                                    client.interrupt_rolling = True
                                    await asyncio.sleep(t_to_r + 0.2)
                                    client.claim_right_available = True
                                    client.last_successfully_claimed_character = None
                                    delta = datetime.timedelta(minutes=client.claim_interval)
                                    while client.next_claim_reset_at_utc <= datetime.datetime.now(timezone.utc):
                                        client.next_claim_reset_at_utc += delta
                            
                            client.interrupt_rolling = True
                            BotLogger.log(f"Real-time Claim: Halting rolls for claim attempt on {c_name}", preset_name, "CLAIM")
                            if client.reactive_snipe_delay > 0:
                                await asyncio.sleep(client.reactive_snipe_delay + random.uniform(0.05, 0.25))
                            if await claim_character(client, message.channel, message, kakera_value=k_val):
                                process = False
                
                if process:
                    all_k = client.kakera_emojis + client.chaos_emojis + client.sphere_emojis + client.sphere_perk_emojis
                    has_btn = message.components and any(hasattr(b.emoji, 'name') and b.emoji.name and (b.emoji.name in all_k or b.emoji.name.rstrip('2') in all_k) for comp in message.components for b in comp.children)
                    if has_btn:
                         d_min, d_max = client.reactive_kakera_delay_range
                         if d_max > 0: await asyncio.sleep(random.uniform(d_min, d_max))
                         await claim_character(client, message.channel, message, is_kakera=True)
        else:
            c_name = embed.author.name.lower()
            process = True
            if client.kakera_reaction_snipe_mode_active and message.id not in client.kakera_reaction_sniped_messages:
                 all_k = client.kakera_emojis + client.chaos_emojis + client.sphere_emojis
                 has_btn = message.components and any(hasattr(b.emoji, 'name') and b.emoji.name and (b.emoji.name in all_k or b.emoji.name.rstrip('2') in all_k) for comp in message.components for b in comp.children)
                 if has_btn:
                    target_ok = True
                    if client.kakera_reaction_snipe_targets:
                        owner = get_character_owner(embed)
                        if not owner or owner not in client.kakera_reaction_snipe_targets: target_ok = False
                    if target_ok:
                        client.kakera_reaction_sniped_messages.add(message.id)
                        await asyncio.sleep(client.kakera_reaction_snipe_delay_value)
                        await claim_character(client, message.channel, message, is_kakera=True, is_snipe=True)
                        process = False
            
            if process and client.series_snipe_mode and client.series_wishlist:
                desc = embed.description or ""
                series = desc.splitlines()[0].lower() if desc else ""
                is_avoided = c_name in client.avoid_list
                if any(s in series for s in client.series_wishlist) and not is_avoided and has_claim_option(message, embed, client.claim_emojis):
                    if is_key_mode_kakera_only() or not is_character_snipe_allowed(is_external_snipe=True): pass
                    else:
                        await asyncio.sleep(client.series_snipe_delay + random.uniform(0.05, 0.25))
                        if await claim_character(client, message.channel, message, is_snipe=True):
                             client.series_snipe_happened = True; process = False
  
            claims_r, likes_r = parse_mudae_ranks(embed.description or "")
            is_ranked = (client.max_claim_rank > 0 and 0 < claims_r <= client.max_claim_rank) or (client.max_like_rank > 0 and 0 < likes_r <= client.max_like_rank)
            is_on_wishlist = c_name in client.wishlist or is_wished_by_self(message, client.user.id) or is_ranked
            is_avoided = c_name in client.avoid_list
            if process and client.snipe_mode and is_on_wishlist and not is_avoided and has_claim_option(message, embed, client.claim_emojis):
                if is_key_mode_kakera_only() or not is_character_snipe_allowed(is_external_snipe=True): pass
                else:
                    await asyncio.sleep(client.snipe_delay + random.uniform(0.05, 0.25))
                    if await claim_character(client, message.channel, message, is_snipe=True):
                        client.snipe_happened = True; process = False
            
            if process and client.kakera_snipe_mode_active:
                desc = embed.description or ""
                k_val = 0
                m_k = re.search(REGEX_PATTERNS["KAKERA_VALUE"], desc)
                if m_k: k_val = int(re.sub(r"[^\d]", "", m_k.group(1)))
                is_avoided = c_name in client.avoid_list
                if k_val >= client.kakera_snipe_threshold and not is_avoided and has_claim_option(message, embed, client.claim_emojis):
                    if is_key_mode_kakera_only() or not is_character_snipe_allowed(is_external_snipe=True): pass
                    else:
                        await asyncio.sleep(client.snipe_delay + random.uniform(0.05, 0.25))
                        if await claim_character(client, message.channel, message, is_snipe=True, kakera_value=k_val):
                            client.snipe_happened = True; process = False
  
            if process and is_free_event(embed):
                print_log(f"Sniping free event card: {c_name}", preset_name, "CLAIM")
                if await claim_character(client, message.channel, message, is_free_claim=True): process = False

    try:
        client.run(token, reconnect=True)
    except Exception as e:
        if "set_wakeup_fd" not in str(e): BotLogger.log(f"Crash: {e}", preset_name, "ERROR")
    finally:
        with _active_clients_lock:
            if client in _active_clients: _active_clients.remove(client)

def bot_lifecycle_wrapper(preset_name, preset_data):
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
                preset_data.get("mk_bypass_power_check", False), preset_data.get("snipe_channels", []),
                preset_data.get("max_claim_rank", 0), preset_data.get("max_like_rank", 0),
                preset_data.get("auto_p_enabled", True),
                preset_data.get("enable_hybrid_panic_claim", False),
                preset_data.get("hybrid_panic_instant_claim_min_kakera", 300),
                preset_data.get("hybrid_panic_instant_claim_max_rank", 200),
                preset_data.get("claim_rounds_thresholds", None)
            )
        except Exception as e:
            print_log(f"Instance crashed: {e}", preset_name, "ERROR")
        time.sleep(60)

def start_preset_thread(preset_name, preset_data):
    if not preset_data.get("token"): return None
    t = threading.Thread(target=bot_lifecycle_wrapper, args=(preset_name, preset_data), daemon=True)
    t.start()
    return t

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
    if os.name != 'nt':
        import termios
        global _original_terminal_settings
        if _original_terminal_settings is not None:
            try:
                termios.tcflush(sys.stdin.fileno(), termios.TCIFLUSH)
                termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, _original_terminal_settings)
            except Exception: pass

    original_stdin = sys.stdin
    if os.name != 'nt': sys.stdin = StdinEnterMapper(sys.stdin)

    def safe_prompt(q):
        ans = inquirer.prompt(q)
        if os.name != 'nt':
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
                if p_ans: threads.append(start_preset_thread(p_ans['p'], presets[p_ans['p']]))
            elif ans['opt'] == 'Select and Run Multiple':
                p_ans = safe_prompt([inquirer.Checkbox('p', message="Presets", choices=list(presets.keys()))])
                if p_ans: 
                    for p in p_ans['p']: threads.append(start_preset_thread(p, presets[p]))
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
    return parser.parse_args()

if __name__ == "__main__":
    cleanup_after_update()
    check_for_updates()
    args = parse_args()
    if args.preset:
        if args.preset in presets:
            bot_lifecycle_wrapper(args.preset, presets[args.preset])
        else:
            print(f"Preset '{args.preset}' not found.")
    elif args.all:
        started = []
        for p_name, p_data in presets.items():
            t = start_preset_thread(p_name, p_data)
            if t: started.append(t)
        for t in started:
            if t: t.join()
    else:
        main_menu()
        try:
            while True: time.sleep(1)
        except KeyboardInterrupt:
            print("\n[MudaRemote] Shutting down...")