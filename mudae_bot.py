import sys
import asyncio
import discord
from discord.ext import commands
import re
import json
import threading
import datetime
from datetime import timezone
# NOTE: 'inquirer' is imported lazily inside main_menu() to avoid crashes
# in PyInstaller --windowed mode where sys.stdin is None.
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
CURRENT_VERSION = "4.2.6"

# --- GLOBAL PAUSE STATE ---
# Module-level flag: when True, ALL bot instances pause operations.
_global_paused = False
_active_clients = []  # Registry of all running bot client instances
_active_clients_lock = threading.Lock()

# [FIX] Bug 1: Threading Event to gate the keyboard listener.
# When set, the listener is SUPPRESSED (menu is using stdin).
# When cleared, the listener is ACTIVE (bots are running, menu is done).
_menu_active = threading.Event()

def _toggle_global_pause():
    """Toggle the global pause state and update all registered client instances."""
    global _global_paused
    _global_paused = not _global_paused
    
    # Propagate to all active client instances
    with _active_clients_lock:
        for c in _active_clients:
            c.is_paused = _global_paused
    
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    if _global_paused:
        # Yellow/Warning style
        print(f"\033[1;33m[{timestamp}][{BOT_NAME}] ⏸️  BOT PAUSED. Press 'p' again to resume.\033[0m")
    else:
        # Green/Success style
        print(f"\033[1;32m[{timestamp}][{BOT_NAME}] ▶️  BOT RESUMED. Operations continuing.\033[0m")

def _keyboard_listener_thread():
    """Background daemon thread: listens for raw 'p' keypress (no Enter needed).
    Uses msvcrt on Windows for non-blocking, single-keypress detection.
    Does NOT block the main asyncio event loop.
    
    [FIX] Bug 1: Two critical changes:
    1. Checks _menu_active event — when the interactive CLI menu (inquirer) is
       using stdin, this thread yields instead of competing for console input.
    2. Properly handles multi-byte Windows escape sequences (arrow keys send
       b'\xe0' or b'\x00' followed by a scan code like b'P' for Down Arrow).
       Without this, pressing Down Arrow would falsely trigger pause because
       the scan code b'P' matches the 'P' check."""
    if os.name == 'nt':
        while True:
            try:
                # [FIX] Gate: If the interactive menu is active, don't read stdin.
                # Poll periodically so we resume quickly when the menu finishes.
                if _menu_active.is_set():
                    time.sleep(0.2)
                    continue

                # Windows: msvcrt.getch() blocks this thread only, returns bytes.
                # Use kbhit() to poll non-blockingly so we can check _menu_active.
                if not msvcrt.kbhit():
                    time.sleep(0.05)
                    continue
                ch = msvcrt.getch()
                
                # [FIX] Multi-byte escape sequence handling:
                # Arrow keys and function keys send TWO bytes:
                #   Byte 1: b'\xe0' (0xE0) or b'\x00' (0x00) — extended key prefix
                #   Byte 2: Scan code (e.g., b'H'=Up, b'P'=Down, b'K'=Left, b'M'=Right)
                # We MUST consume both bytes to prevent the scan code (especially b'P'
                # for Down Arrow) from being misinterpreted as the 'P' pause toggle.
                if ch in (b'\xe0', b'\x00'):
                    # Consume the scan code byte and discard the entire sequence
                    if msvcrt.kbhit():
                        msvcrt.getch()  # Discard scan code
                    continue
                
                if ch in (b'p', b'P'):
                    _toggle_global_pause()
            except Exception:
                # If stdin is unavailable (e.g., PyInstaller --windowed), silently back off
                time.sleep(5)
    else:
        # Fallback for non-Windows (Linux/macOS): non-blocking terminal mode
        import tty, termios, select
        try:
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            try:
                tty.setcbreak(fd)
                while True:
                    if _menu_active.is_set():
                        time.sleep(0.2)
                        continue
                    
                    if select.select([sys.stdin], [], [], 0.1)[0]:
                        ch = sys.stdin.read(1)
                        # Handle escape sequences (arrow keys: ESC [ A/B/C/D)
                        if ch == '\x1b':
                            # Consume remaining escape sequence bytes
                            while select.select([sys.stdin], [], [], 0.01)[0]:
                                sys.stdin.read(1)
                            continue
                        if ch.lower() == 'p':
                            _toggle_global_pause()
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        except Exception:
            # If stdin is unavailable
            while True:
                time.sleep(5)

def _start_keyboard_listener():
    """Start the keyboard listener as a daemon thread (runs once at module level)."""
    t = threading.Thread(target=_keyboard_listener_thread, daemon=True)
    t.start()

# Auto-start the keyboard listener when the module loads
try:
    _start_keyboard_listener()
except Exception:
    pass  # Graceful degradation if terminal is not available

# --- UPDATE CONFIGURATION ---
# Replace this URL with your GitHub RAW URL for version.json and the script itself
UPDATE_URL = "https://raw.githubusercontent.com/misutesu-desu/MudaRemote/refs/heads/main/" 

def get_base_path():
    """Get the base path for file operations.
    When running as a PyInstaller --onefile .exe, sys._MEIPASS is the temp folder,
    but we want the directory where the actual .exe is located to read/write presets.json.
    """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def check_for_updates():
    if not UPDATE_URL:
        return
    
    is_frozen = getattr(sys, 'frozen', False)
    print(f"[{BOT_NAME}] Checking for updates... (Current: v{CURRENT_VERSION}, Mode: {'EXE' if is_frozen else 'Script'})")
    try:
        # Check version.json
        # Format: {"version": "4.0.7", "download_url": "...", "editor_download_url": "...", "exe_download_url": "..."}
        response = requests.get(f"{UPDATE_URL}version.json", timeout=10)
        if response.status_code == 200:
            data = response.json()
            latest_version = data.get("version")
            
            if latest_version and latest_version > CURRENT_VERSION:
                print(f"[{BOT_NAME}] New version found: v{latest_version}")
                print(f"[{BOT_NAME}] Downloading update...")
                
                if is_frozen:
                    # --- FROZEN (.exe) MODE ---
                    # An active .exe cannot overwrite itself, so we use a .bat swap strategy.
                    exe_download_url = data.get("exe_download_url")
                    if not exe_download_url:
                        print(f"[{BOT_NAME}] No exe_download_url in version.json. Skipping update.")
                        return
                    
                    current_exe = os.path.abspath(sys.executable)
                    current_dir = get_base_path()
                    exe_name = os.path.basename(current_exe)
                    update_exe = os.path.join(current_dir, "MudaRemote_update.exe")
                    bat_path = os.path.join(current_dir, "update.bat")
                    
                    # Download the new .exe
                    try:
                        update_res = requests.get(exe_download_url, timeout=120)
                        if update_res.status_code != 200:
                            print(f"[{BOT_NAME}] Failed to download exe update (HTTP {update_res.status_code}).")
                            return
                        
                        # Pre-delete stale update file if it exists (may be locked from a previous crash)
                        if os.path.exists(update_exe):
                            try:
                                os.remove(update_exe)
                            except Exception:
                                pass  # Best-effort cleanup; we'll handle write failure below
                        
                        # Attempt to write the downloaded exe
                        target_exe_path = update_exe
                        try:
                            with open(target_exe_path, "wb") as f:
                                f.write(update_res.content)
                        except PermissionError:
                            # Fallback: the default filename is locked (AV, prior crash, etc.)
                            # Use a unique timestamped filename to bypass the lock.
                            fallback_name = f"MudaRemote_update_{int(time.time())}.exe"
                            target_exe_path = os.path.join(current_dir, fallback_name)
                            print(f"[{BOT_NAME}] Primary update path locked. Using fallback: {fallback_name}")
                            with open(target_exe_path, "wb") as f:
                                f.write(update_res.content)
                        
                        print(f"[{BOT_NAME}] New exe downloaded ({len(update_res.content)} bytes).")
                        
                        # Generate a self-destructing .bat updater
                        # The bat waits for the old exe to unlock, swaps files, relaunches, and deletes itself.
                        # Uses target_exe_path which may be the default or the timestamped fallback.
                        original_args = ' '.join(f'"{a}"' for a in sys.argv[1:]) if sys.argv[1:] else ''
                        bat_content = f'''@echo off
timeout /t 3 /nobreak >nul
del /f /q "{current_exe}"
ren "{target_exe_path}" "{exe_name}"
start "" "{current_exe}" {original_args}
del "%~f0"
'''
                        with open(bat_path, "w", encoding="utf-8") as f:
                            f.write(bat_content)
                        
                        print(f"[{BOT_NAME}] Update staged. Restarting via updater...")
                        # Launch the bat hidden (minimized) and exit immediately
                        subprocess.Popen(
                            [bat_path],
                            creationflags=subprocess.CREATE_NO_WINDOW,
                            shell=True
                        )
                        os._exit(0)
                    except Exception as e:
                        # Total failure: log a friendly message and let the bot continue on the current version
                        print(f"[{BOT_NAME}] ⚠️  EXE update failed: {e}")
                        print(f"[{BOT_NAME}] Continuing with current version v{CURRENT_VERSION}. You can update manually from GitHub.")
                else:
                    # --- SCRIPT (.py) MODE --- (existing logic)
                    download_url = data.get("download_url")
                    if not download_url:
                        print(f"[{BOT_NAME}] No download_url in version.json. Skipping update.")
                        return
                    
                    update_res = requests.get(download_url, timeout=30)
                    if update_res.status_code == 200:
                        current_script = os.path.abspath(__file__)
                        backup_script = current_script + ".bak"
                        
                        # Create backup
                        shutil.copy2(current_script, backup_script)
                        
                        # Replace current script
                        with open(current_script, "wb") as f:
                            f.write(update_res.content)
                        
                        # Also update the preset editor
                        script_dir = os.path.dirname(current_script)
                        editor_path = os.path.join(script_dir, "mudae_preset_editor.py")
                        editor_url = data.get("editor_download_url", f"{UPDATE_URL}mudae_preset_editor.py")
                        try:
                            editor_res = requests.get(editor_url, timeout=30)
                            if editor_res.status_code == 200:
                                if os.path.exists(editor_path):
                                    shutil.copy2(editor_path, editor_path + ".bak")
                                with open(editor_path, "wb") as f:
                                    f.write(editor_res.content)
                                print(f"[{BOT_NAME}] Preset editor updated.")
                            else:
                                print(f"[{BOT_NAME}] Failed to download preset editor update.")
                        except Exception as e:
                            print(f"[{BOT_NAME}] Preset editor update failed: {e}")
                        
                        print(f"[{BOT_NAME}] Update applied. Starting new version in a fresh window...")
                        # Restart process
                        if os.name == 'nt':
                            subprocess.Popen([sys.executable] + sys.argv, creationflags=subprocess.CREATE_NEW_CONSOLE)
                        else:
                            os.execv(sys.executable, [sys.executable] + sys.argv)
                        sys.exit()
                    else:
                        print(f"[{BOT_NAME}] Failed to download update file.")
            else:
                print(f"[{BOT_NAME}] You are up to date.")
    except Exception as e:
        print(f"[{BOT_NAME}] Update check failed: {e}")

def cleanup_after_update():
    """Removes the backup files created during the update process."""
    current_script = os.path.abspath(__file__)
    script_dir = get_base_path()
    
    for bak_file in [os.path.join(script_dir, "mudae_bot.py.bak"), os.path.join(script_dir, "mudae_preset_editor.py.bak")]:
        if os.path.exists(bak_file):
            try:
                os.remove(bak_file)
                print(f"[{BOT_NAME}] Backup cleaned: {os.path.basename(bak_file)}")
            except Exception:
                pass

# Load config
presets = {}
presets_path = os.path.join(get_base_path(), "presets.json")

# Ensure presets.json exists
if not os.path.exists(presets_path):
    try:
        with open(presets_path, "w", encoding="utf-8") as f:
            json.dump({}, f, indent=4)
        print(f"[{BOT_NAME}] Created missing {presets_path}")
    except Exception as e:
        print(f"[{BOT_NAME}] Error creating {presets_path}: {e}")

try:
    with open(presets_path, "r", encoding="utf-8") as f:
        presets = json.load(f)
except json.JSONDecodeError:
    print(f"[{BOT_NAME}] {presets_path} is malformed.")
    sys.exit(1)
except Exception as e:
    print(f"[{BOT_NAME}] Failed to load {presets_path}: {e}")
    sys.exit(1)

# Enable ANSI escape sequences for Windows 10+ consoles
if os.name == 'nt':
    os.system('')

# Mudae's User ID
TARGET_BOT_ID = 432610292342587392

# Console Colors
COLORS = {
    "INFO": "\033[94m",    # Blue
    "CLAIM": "\033[92m",   # Green
    "KAKERA": "\033[93m",  # Yellow
    "ERROR": "\033[91m",   # Red
    "CHECK": "\033[95m",   # Magenta
    "RESET": "\033[36m",   # Cyan
    "ENDC": "\033[0m"      # End
}

# Heart buttons
CLAIM_EMOJIS = ['💖', '💗', '💘', '❤️', '💓', '💕', '♥️']

# Standard Kakera
KAKERA_EMOJIS = ['kakeraY', 'kakeraO', 'kakeraR', 'kakeraW', 'kakeraL', 'kakeraP', 'kakeraD', 'kakeraC']

# Chaos Kakera (for characters with 10+ keys)
CHAOS_KAKERA_EMOJIS = ['kakeraY', 'kakeraO', 'kakeraR', 'kakeraW', 'kakeraL', 'kakeraP', 'kakeraD', 'kakeraC']

# Sphere Emojis (Do not consume power)
SPHERE_EMOJIS = ['spP', 'spB', 'spT', 'spG', 'spY', 'spO', 'spR', 'spW', 'spL', 'spD', 'spM', 'spP2', 'spB2', 'spT2', 'spG2', 'spY2', 'spO2', 'spR2', 'spW2', 'spL2', 'spD2', 'spU'] # Added spM sphere emoji


def color_log(message, preset_name, log_type="INFO"):
    color_code = COLORS.get(log_type.upper(), COLORS["INFO"])
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_message = f"[{timestamp}][{preset_name}] {message}"
    print(f"{color_code}{log_message}{COLORS['ENDC']}")
    return log_message

def write_log_to_file(log_message):
    try:
        logs_path = os.path.join(get_base_path(), "logs.txt")
        with open(logs_path, "a", encoding='utf-8') as log_file:
            log_file.write(log_message + "\n")
    except Exception as e:
        print(f"Log file error: {e}")

def print_log(message, preset_name, log_type="INFO"):
    log_message_formatted = color_log(message, preset_name, log_type)
    write_log_to_file(log_message_formatted)

def _debug_log_global(client_ref, log_func, preset, message):
    """Global debug logger. Only prints when client.debug_mode is True.
    Prefixes all output with [DEBUG] for easy filtering."""
    try:
        if getattr(client_ref, 'debug_mode', False):
            log_func(f"[{getattr(client_ref, 'muda_name', 'MudaRemote')}] [DEBUG] {message}", preset, "INFO")
    except Exception:
        pass

def is_character_embed(embed):
    # Reliable check: Characters have an author name, an image, and NO thumbnail
    if not embed or not embed.author or not embed.author.name:
        return False
    
    has_image = embed.image and embed.image.url
    has_thumbnail = embed.thumbnail and embed.thumbnail.url

    return has_image and not has_thumbnail

def is_free_event(embed):
    """
    Detects special Mudae event characters (like Christmas Art Contest) 
    that do not consume claim rights.
    """
    if not embed or not embed.description:
        return False
    desc = embed.description.lower()
    # "on me, it's free!" is the standard indicator for these event cards.
    free_keywords = ["it's free!", "é de graça!", "¡es gratis!", "christmas art contest", "new year's contest"]
    return any(k in desc for k in free_keywords)

def has_claim_option(message, embed, claim_emojis):
    if not message.components:
        # If no buttons are present, check if the character is already owned via the footer.
        # If it belongs to someone, we ignore it as it's not a claimable roll.
        if get_character_owner(embed):
            return False
        return True
    for comp in message.components:
        for btn in comp.children:
            if hasattr(btn.emoji, 'name') and btn.emoji and btn.emoji.name in claim_emojis:
                return True
    return False

def count_chaos_keys(embed):
    # Extracts key count from description. Format: <:key:ID> (**N**)
    if not embed or not embed.description:
        return 0
    
    desc = embed.description
    key_pattern = r'<:(?:chaos)?key:\d+>\s*\(\*\*([\d,.]+)\*\*\)'
    matches = re.findall(key_pattern, desc, re.IGNORECASE)
    
    chaos_count = 0
    for match in matches:
        try:
            val = int(re.sub(r"[^\d]", "", match))
            if val >= 10:
                chaos_count += 1
        except ValueError:
            continue
    
    return chaos_count

def get_character_owner(embed):
    if not embed or not embed.footer or not embed.footer.text:
        return None
    
    footer_text = embed.footer.text
    # Patterns for: English, Portuguese, Spanish, French
    belongs_pattern = r'(?:[Bb]elongs to|[Pp]ertence a|[Pp]ertenece a|[Aa]ppartient [àa])\s+(.+?)$'
    match = re.search(belongs_pattern, footer_text)
    
    if match:
        return match.group(1).strip().rstrip().lower()
    
    return None

def is_wished_by_self(message, client_user_id: int) -> bool:
    """
    Checks if the Mudae message indicates this character is wished by the bot's user.
    Mudae format: "Wished by @user1, @user2" in message.content with users in mentions.
    
    This provides authoritative wishlist detection directly from Mudae, complementing
    the local wishlist. Characters detected this way are treated as wishlist characters
    for claiming purposes.
    
    Args:
        message: The Discord message object from Mudae
        client_user_id: The bot user's Discord ID
        
    Returns:
        True if the bot user is mentioned in a "Wished by" context
    """
    if not message or not message.content:
        return False
    
    content_lower = message.content.lower()
    if "wished by" not in content_lower:
        return False
    
    # Check if the bot user is among the mentioned users
    return client_user_id in [m.id for m in message.mentions]

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
            panic_roll_minutes_preset, lurker_mode_preset,
            max_dk_power_preset=100,  # [NEW] Task 1: Configurable max DK power cap
            randomized_claim_reactions_preset=None,  # [NEW] Task 5: Randomized claim reaction emojis
            main_account_id_preset="",  # [NEW] Task 6: Main account wishlist syncing
            scheduled_roll_times_preset=None,  # [NEW] Task 7: Scheduled roll times
            kakera_priority_order_preset=None,  # [NEW] Task 8: Customizable kakera priority
            auto_rt_after_claim_preset=False,  # [NEW] Auto $rt after successful claim
            mk_only_preset=False,  # [NEW] MK Kakera Only: ignore normal kakera, only click crystals from $mk rolls
            auto_dk_enabled_preset=True,  # [NEW] Auto $dk: master toggle for all automatic $dk usage
            command_channel_id_preset="",  # [NEW] Command Channel: send $tu/$daily/$dk/$rolls here instead of roll channel
            enable_snipe_chat_reactions_preset=False,  # [NEW] Snipe Chat Reactions: send random message after external snipe
            snipe_chat_messages_preset=None, # [NEW] Snipe Chat Messages: list of messages to randomly pick from
            farm_character_preset="", # [NEW] Kakera Farm Character
            op_perk_5_only_preset=False, # [NEW] $op Perk 5 Filter
            farm_character_enabled_preset=False, # [NEW] Kakera Farm Toggle
            auto_divorce_enabled_preset=False, # [NEW] Auto-Divorce Toggle
            auto_divorce_max_kakera_preset=50, # [NEW] Auto-Divorce Kakera Threshold
            auto_divorce_series_preset=None, # [NEW] Auto-Divorce Series List
            mk_bypass_power_check=False, # [NEW] Bypass MK power check
            auto_p_enabled=True): 

    client = commands.Bot(command_prefix=prefix, chunk_guilds_at_startup=False, self_bot=True)

    # Global Pause State: Synced from module-level _global_paused
    client.is_paused = _global_paused
    with _active_clients_lock:
        _active_clients.append(client)

    # Clean up console logging
    discord_logger = logging.getLogger('discord')
    discord_logger.propagate = False
    handlers = [h for h in discord_logger.handlers if isinstance(h, logging.StreamHandler)]
    for h in handlers: discord_logger.removeHandler(h)

    # Config init
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
    client.muda_name = BOT_NAME
    client.claim_right_available = False
    client.target_channel_id = target_channel_id
    client.command_channel_id_preset = str(command_channel_id_preset).strip() if command_channel_id_preset else ""
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
    client.tu_lock = None  # NEW FIX: Delay lock creation to avoid thread crash
    client.interrupt_rolling = False
    client.current_min_kakera_for_roll_claim = client.min_kakera
    client.kakera_snipe_mode_active = kakera_snipe_mode_preset
    client.kakera_snipe_threshold = kakera_snipe_threshold_preset
    client.enable_reactive_self_snipe = enable_reactive_self_snipe_preset
    client.reactive_snipe_delay = reactive_snipe_delay
    client.rolling_enabled = rolling_enabled
    client.rt_available = False # $rt (Reset Timer) status
    client.kakera_reaction_snipe_mode_active = kakera_reaction_snipe_mode_preset
    client.kakera_reaction_snipe_delay_value = kakera_reaction_snipe_delay_preset
    client.kakera_reaction_snipe_targets = set([t.lower() for t in kakera_reaction_snipe_targets])
    client.kakera_reaction_sniped_messages = set()
    client.kakera_react_available = True
    client.kakera_react_cooldown_until_utc = None

    # Humanization config
    client.humanization_enabled = humanization_enabled
    client.humanization_window_minutes = humanization_window_minutes
    client.inactive_hours = inactive_hours_preset if inactive_hours_preset else []
    client.humanization_inactivity_seconds = humanization_inactivity_seconds
    
    # Power and key settings
    client.auto_dk_enabled = auto_dk_enabled_preset  # [NEW] Master toggle for automatic $dk usage
    client.dk_power_management = dk_power_management
    client.skip_initial_commands = skip_initial_commands
    client.dk_stock_count = 0 
    client.max_dk_power = max_dk_power_preset  # [NEW] Task 1: Max DK power cap
    client.maintenance_until = None  # [NEW] Task 3: Mudae maintenance cooldown timestamp
    client.only_chaos = only_chaos
    client.mk_only = mk_only_preset  # [NEW] MK Kakera Only mode

    # Auto $us Configuration
    client.auto_us_enabled = auto_us_enabled
    client.auto_us_limit = auto_us_limit
    client.auto_us_stop_on_claim = auto_us_stop_on_claim
    client.us_pulled_this_cycle = 0
    client.mk_rolls_left = 0
    client.auto_mk_enabled = auto_mk_enabled_preset

    # Auto $rolls Configuration
    client.auto_rolls_enabled = auto_rolls_enabled
    client.auto_rolls_limit = auto_rolls_limit
    client.auto_rolls_in_key_mode = auto_rolls_in_key_mode
    client.rolls_item_used_count = 0
    client.rolls_used_this_interval_utc = None
    client.panic_roll_minutes = panic_roll_minutes_preset if panic_roll_minutes_preset is not None else 5
    client.lurker_mode = lurker_mode_preset
    client.auto_rt_after_claim = auto_rt_after_claim_preset  # [NEW] Auto $rt after successful claim

    # [NEW] Task 5: Randomized claim reaction emojis
    client.randomized_claim_reactions = randomized_claim_reactions_preset if randomized_claim_reactions_preset else ["💖", "💗", "💘", "❤️", "👍", "🔥"]

    # [NEW] Task 6: Main account wishlist syncing (Alt Account Targeter)
    client.main_account_id = str(main_account_id_preset).strip() if main_account_id_preset else ""

    # [NEW] Task 7: Scheduled roll times
    client.scheduled_roll_times = scheduled_roll_times_preset if scheduled_roll_times_preset else []

    # [NEW] Task 8: Customizable kakera priority order
    client.kakera_priority_order = kakera_priority_order_preset if kakera_priority_order_preset else [
        'kakeraP', 'kakeraC', 'kakeraL', 'kakeraW', 'kakeraR', 'kakeraO', 'kakeraD', 'kakeraY', 'kakeraG', 'kakeraT', 'kakera'
    ]

    # [NEW] Snipe Chat Reactions: Send a humanized message after external snipes
    client.enable_snipe_chat_reactions = enable_snipe_chat_reactions_preset
    client.snipe_chat_messages = snipe_chat_messages_preset if snipe_chat_messages_preset else ["omg", "ezz"]
    client.farm_character = str(farm_character_preset).strip().lower() if farm_character_preset else ""
    client.farm_character_enabled = farm_character_enabled_preset
    client.op_perk_5_only = op_perk_5_only_preset

    # State tracking
    client.next_claim_reset_at_utc = None
    client.claim_cooldown_until_utc = None
    client.snipe_watch = {} 
    client.snipe_watch_expiry_seconds = 180 
    client.snipe_globally_disabled_until = None

    # Kakera Power Management (Local Tracking)
    client.current_dk_power = 100
    client.dk_consumption = 35 # Default fallback
    client.dk_consumption_chaos = 18 # Default fallback
    client.kakera_reacted_messages = set() # Track processed kakera messages to prevent double counting
    client.processed_claim_messages = set() # Track already processed/claimed message IDs
    client.last_successfully_claimed_character = None # Prevent redundant RT on same name
    client._has_initialized = False # Tracks whether on_ready setup has already run (prevents duplicate $tu on reconnect)
    client._main_loop_task = None  # [FIX] Track the main status loop asyncio.Task for health checks
    client._immediate_check_event = None  # [FIX] asyncio.Event to signal immediate status check from external triggers


    # Slash command internal state
    client.use_slash_rolls = bool(use_slash_rolls and Route is not None)
    client.slash_fallback_active = False  # [NEW] Dynamic slash-to-text fallback state
    client.mudae_slash_cache = {}
    client.mudae_slash_missing = set()
    client.mudae_session_id = None
    client.slash_fail_streak = 0
    client.slash_fail_threshold = 3
    client.slash_min_interval = max(1.0, float(roll_speed)) if roll_speed else 1.0
    client.slash_max_backoff = 6.0
    client.last_slash_attempt = 0.0
    client.slash_rate_limited_until = 0.0

    # [NEW] Auto-Divorce Configuration
    client.auto_divorce_enabled = auto_divorce_enabled_preset
    client.auto_divorce_max_kakera = auto_divorce_max_kakera_preset if auto_divorce_max_kakera_preset is not None else 50
    client.auto_divorce_series = [s.lower().strip() for s in (auto_divorce_series_preset or []) if s.strip()]
    client.mk_bypass_power_check = mk_bypass_power_check
    client.auto_p_enabled = auto_p_enabled
    client.p_available = False
    client.next_p_claim_at_utc = None
    client.key_limit_hit = False
    client.time_rolls_to_claim_reset = time_rolls_to_claim_reset_preset
    client.rt_ignore_min_kakera_for_wishlist = rt_ignore_min_kakera_for_wishlist_preset
    
    # RT Self-Roll Only Mode: Prevents RT usage on external snipes
    client.rt_only_self_rolls = rt_only_self_rolls_preset
    
    # Reactive Kakera Delay: Humanized delay before clicking kakera on own rolls
    # Default: [0.3, 1.0] seconds (300ms to 1000ms)
    if reactive_kakera_delay_range_preset and isinstance(reactive_kakera_delay_range_preset, (list, tuple)) and len(reactive_kakera_delay_range_preset) == 2:
        client.reactive_kakera_delay_range = (float(reactive_kakera_delay_range_preset[0]), float(reactive_kakera_delay_range_preset[1]))
    else:
        client.reactive_kakera_delay_range = (0.3, 1.0)

    # Manual Intervals (in minutes) for minimized $tu usage
    client.claim_interval = claim_interval_preset if claim_interval_preset else 180
    client.roll_interval = roll_interval_preset if roll_interval_preset else 60
    
    # Custom Emojis
    # Use explicit None check to respect intentionally empty lists.
    # - None: user never configured -> use defaults
    # - []: user explicitly set blank -> use empty (no buttons clicked)
    # - [...]: user set custom -> use their values
    client.claim_emojis = claim_emojis_preset if claim_emojis_preset is not None else ['💖', '💗', '💘', '❤️', '💓', '💕', '♥️']
    client.kakera_emojis = kakera_emojis_preset if kakera_emojis_preset is not None else ['kakeraY', 'kakeraO', 'kakeraR', 'kakeraW', 'kakeraL', 'kakeraP', 'kakeraD', 'kakeraC']
    client.chaos_emojis = chaos_emojis_preset if chaos_emojis_preset is not None else ['kakeraY', 'kakeraO', 'kakeraR', 'kakeraW', 'kakeraL', 'kakeraP', 'kakeraD', 'kakeraC']
    client.sphere_perk_emojis = sphere_perk_emojis_preset if sphere_perk_emojis_preset is not None else ['kakeraY', 'kakeraO', 'kakeraR', 'kakeraW', 'kakeraL', 'kakeraP', 'kakeraD', 'kakeraC']
    client.sphere_emojis = SPHERE_EMOJIS
    client.kakera_power_thresholds = kakera_power_thresholds or {}
    client.debug_mode = debug_mode

    def debug_log(message):
        """Convenience wrapper: logs only when debug_mode is True. All output prefixed with [DEBUG]."""
        _debug_log_global(client, log_function, preset_name, message)


    async def health_monitor_task():
        # Reconnect if gateway drops
        unhealthy_streak = 0
        max_streak = 3
        while not client.is_closed():
            await asyncio.sleep(60)
            if client.latency == float('inf'):
                unhealthy_streak += 1
                log_function(f"[{client.muda_name}] Connection lost ({unhealthy_streak}/{max_streak}).", preset_name, "ERROR")
            else:
                if unhealthy_streak > 0:
                    log_function(f"[{client.muda_name}] Reconnected. Ping: {client.latency * 1000:.0f}ms.", preset_name, "INFO")
                unhealthy_streak = 0
            if unhealthy_streak >= max_streak:
                log_function(f"[{client.muda_name}] Connection dead. Restarting.", preset_name, "ERROR")
                try:
                    await client.close()
                except Exception:
                    pass
                return

    def is_inactive_hour() -> bool:
        """Returns True if the current local time falls within any configured inactive hour range."""
        if not client.inactive_hours:
            return False
        now_hour = datetime.datetime.now().hour
        for window in client.inactive_hours:
            if not isinstance(window, (list, tuple)) or len(window) != 2:
                continue
            start_h, end_h = int(window[0]), int(window[1])
            if start_h <= end_h:
                # Same-day range: e.g. [9, 17]
                if start_h <= now_hour < end_h:
                    return True
            else:
                # Overnight range: e.g. [23, 7] means 23:00 -> 07:00
                if now_hour >= start_h or now_hour < end_h:
                    return True
        return False

    def seconds_until_active() -> float:
        """Returns seconds until the current inactive period ends. 0 if not inactive."""
        if not is_inactive_hour():
            return 0
        now = datetime.datetime.now()
        now_hour = now.hour
        best = float('inf')
        for window in client.inactive_hours:
            if not isinstance(window, (list, tuple)) or len(window) != 2:
                continue
            start_h, end_h = int(window[0]), int(window[1])
            in_this = False
            if start_h <= end_h:
                in_this = start_h <= now_hour < end_h
            else:
                in_this = now_hour >= start_h or now_hour < end_h
            if in_this:
                # Calculate seconds until end_h:00:00
                wake = now.replace(hour=end_h, minute=0, second=0, microsecond=0)
                if wake <= now:
                    wake += datetime.timedelta(days=1)
                diff = (wake - now).total_seconds()
                best = min(best, diff)
        return best if best != float('inf') else 0

    def is_character_snipe_allowed(is_external_snipe: bool = False) -> bool:
        # If rt_only_self_rolls is enabled, don't count RT as available for external snipes
        rt_usable = client.rt_available and not (is_external_snipe and client.rt_only_self_rolls)
        return client.claim_right_available or rt_usable or client.key_mode

    def is_key_mode_kakera_only() -> bool:
        """
        Returns True when key_mode is active but neither claim nor RT is available.
        In this state, the bot should ONLY click kakera buttons and NOT claim characters.
        This prevents wasting keys on characters we cannot actually claim.
        """
        return client.key_mode and not client.claim_right_available and not client.rt_available

    def parse_hours_minutes(match_obj):
        if not match_obj: return 0, 0
        groups = match_obj.groups(default="")
        h_str = groups[0] if len(groups) >= 1 else ""
        m_str = groups[1] if len(groups) >= 2 else ""
        
        def get_val(s):
            d = re.sub(r"\D", "", s or "")
            return int(d) if d else 0
        return get_val(h_str), get_val(m_str)

    def is_kakera_reaction_allowed() -> bool:
        try:
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            if client.kakera_react_available:
                return True
            if client.kakera_react_cooldown_until_utc and now_utc >= client.kakera_react_cooldown_until_utc:
                client.kakera_react_available = True
                client.kakera_react_cooldown_until_utc = None
                return True
            return False
        except Exception:
            return True

    def get_current_dk_power() -> int:
        power = client.current_dk_power
        if not hasattr(client, 'last_dk_power_update_utc'):
            return power
        now = datetime.datetime.now(datetime.timezone.utc)
        elapsed = (now - client.last_dk_power_update_utc).total_seconds()
        regenerated = int(elapsed / 180) # 1% every 3 minutes
        if regenerated > 0:
            # [FIX] Task 1: Use configurable max_dk_power instead of hardcoded 100
            power = min(client.max_dk_power, power + regenerated)
            client.current_dk_power = power
            client.last_dk_power_update_utc += datetime.timedelta(minutes=3 * regenerated)
        return power

    # [NEW] Task 3: Check if bot is under maintenance pause
    # [FIX] Post-maintenance: respect humanization settings and expect channel inactivity
    def is_maintenance_active() -> bool:
        if client.maintenance_until is None:
            return False
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        if now_utc >= client.maintenance_until:
            # Phase 1: Apply humanized jitter before resuming (one-time extension)
            if client.humanization_enabled and not getattr(client, '_maintenance_jitter_applied', False):
                jitter_seconds = random.uniform(0, client.humanization_window_minutes * 60)
                client.maintenance_until = now_utc + datetime.timedelta(seconds=jitter_seconds)
                client._maintenance_jitter_applied = True
                log_function(f"[{client.muda_name}] Maintenance ended. Humanized re-entry: waiting {jitter_seconds/60:.1f}m before resuming.", preset_name, "RESET")
                return True  # Still paused during jitter phase

            # Phase 2: Jitter complete (or humanization disabled) — clear maintenance state
            client.maintenance_until = None
            client._maintenance_jitter_applied = False
            # Set flag so on_message waits for channel inactivity before processing
            client._post_maintenance_inactivity_needed = True
            client._post_maint_last_msg_utc = None
            log_function(f"[{client.muda_name}] Maintenance period ended. Waiting for channel inactivity before resuming.", preset_name, "INFO")
            return False
        return True

    # [NEW] Task 7: Scheduled roll times task
    async def scheduled_roll_task(channel):
        """Waits for specific scheduled times to execute rolls instead of interval loops."""
        log_function(f"[{client.muda_name}] Scheduled roll mode active. Times: {client.scheduled_roll_times}", preset_name, "INFO")
        while not client.is_closed():
            try:
                # --- PAUSE GUARD ---
                if client.is_paused:
                    await asyncio.sleep(1)
                    continue
                now = datetime.datetime.now()
                next_time = None
                min_wait = float('inf')

                for time_str in client.scheduled_roll_times:
                    try:
                        parts = time_str.strip().split(':')
                        target_hour = int(parts[0])
                        target_minute = int(parts[1]) if len(parts) > 1 else 0
                        target = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
                        if target <= now:
                            target += datetime.timedelta(days=1)
                        wait = (target - now).total_seconds()
                        if wait < min_wait:
                            min_wait = wait
                            next_time = target
                    except (ValueError, IndexError):
                        continue

                if next_time is None:
                    await asyncio.sleep(60)
                    continue

                log_function(f"[{client.muda_name}] Next scheduled roll at {next_time.strftime('%H:%M')} (in {min_wait/60:.1f}m)", preset_name, "RESET")
                await asyncio.sleep(min_wait)

                # [NEW] Task 7 CRITICAL: Respect humanization setting
                if client.humanization_enabled and client.humanization_window_minutes > 0:
                    jitter = random.uniform(0, client.humanization_window_minutes * 60)
                    log_function(f"[{client.muda_name}] Humanized delay: waiting {jitter/60:.1f}m before scheduled roll.", preset_name, "INFO")
                    await asyncio.sleep(jitter)

                # Skip if maintenance is active
                if is_maintenance_active():
                    continue

                # Skip if inactive hour
                if is_inactive_hour():
                    continue

                log_function(f"[{client.muda_name}] Executing scheduled roll.", preset_name, "INFO")
                # [FIX] Signal the main loop to run immediately instead of calling check_status directly
                if client._immediate_check_event:
                    client._immediate_check_event.set()

            except asyncio.CancelledError:
                break
            except Exception as e:
                log_function(f"[{client.muda_name}] Scheduled roll error: {e}", preset_name, "ERROR")
                await asyncio.sleep(60)


    def _refresh_session_id():
        try:
            ws = getattr(client, "ws", None)
            sid = getattr(ws, "session_id", None)
            if sid:
                client.mudae_session_id = sid
        except Exception:
            pass

    async def _fetch_mudae_slash_commands(channel):
        """[FIX] Bug 2: Fetch Mudae's slash commands visible to the user in a specific channel.
        
        Uses the channel-scoped application command search endpoint, which is
        what the Discord client itself uses. This works with user tokens and
        respects all channel-level permission overwrites.
        
        The old endpoint (GET /applications/{app_id}/commands) is a global
        endpoint that requires a bot token with the application's ownership —
        it returns 403 Forbidden for self-bot user tokens, which was the
        primary cause of slash command failures for many users.
        """
        guild = getattr(channel, 'guild', None)
        if not guild:
            return None
        
        cache_key = (guild.id, channel.id)
        if cache_key in client.mudae_slash_cache:
            return client.mudae_slash_cache[cache_key]
        
        http = getattr(client, "http", None)
        if not http or Route is None:
            return None

        commands_map = {}
        data = []
        
        # Strategy: Try multiple endpoints in order of reliability
        # 1. Channel-scoped search (most reliable for user tokens)
        # 2. Guild-scoped application commands (fallback)
        try:
            route = Route(
                "GET",
                "/channels/{channel_id}/application-commands/search",
                channel_id=channel.id
            )
            # Query params: filter by Mudae's application ID, type=1 (slash commands)
            params = {
                "type": 1,
                "application_id": str(TARGET_BOT_ID),
                "limit": 25
            }
            resp = await http.request(route, params=params)
            
            # Response format: {"application_commands": [...], "cursor": {...}}
            cmd_list = []
            if isinstance(resp, dict):
                cmd_list = resp.get("application_commands", [])
            elif isinstance(resp, list):
                cmd_list = resp
            
            for cmd in cmd_list:
                name = str(cmd.get("name", "")).lower()
                if name:
                    commands_map[name] = cmd
            
            if commands_map:
                client.mudae_slash_cache[cache_key] = commands_map
                debug_log(f"Fetched {len(commands_map)} Mudae slash commands via channel search for #{channel.name}")
                return commands_map
        except discord.HTTPException as e:
            status = getattr(e, 'status', 0)
            debug_log(f"Channel command search failed (HTTP {status}): {getattr(e, 'text', str(e))[:100]}")
            # 403/401 = permission issue, don't retry with fallback endpoint
            if status in (401, 403):
                log_function(f"[{client.muda_name}] Slash: Cannot access commands in #{channel.name} (HTTP {status}). Check 'Use Application Commands' permission.", preset_name, "ERROR")
                return None
        except Exception as e:
            debug_log(f"Channel command search exception: {type(e).__name__}: {str(e)[:100]}")
        
        # Fallback: Try guild-scoped search
        try:
            route = Route(
                "GET",
                "/guilds/{guild_id}/application-command-index",
                guild_id=guild.id
            )
            resp = await http.request(route)
            cmd_list = []
            if isinstance(resp, dict):
                cmd_list = resp.get("application_commands", [])
            elif isinstance(resp, list):
                cmd_list = resp
            
            for cmd in cmd_list:
                # Filter to only Mudae commands
                app_id = str(cmd.get("application_id", ""))
                if app_id == str(TARGET_BOT_ID):
                    name = str(cmd.get("name", "")).lower()
                    if name:
                        commands_map[name] = cmd
            
            if commands_map:
                client.mudae_slash_cache[cache_key] = commands_map
                debug_log(f"Fetched {len(commands_map)} Mudae slash commands via guild index for guild {guild.id}")
                return commands_map
        except Exception as e:
            debug_log(f"Guild command index fallback also failed: {type(e).__name__}: {str(e)[:100]}")

        # If both failed, return None
        log_function(f"[{client.muda_name}] Slash: Could not fetch commands for #{channel.name}. Mudae may not be installed or commands are disabled in this channel.", preset_name, "ERROR")
        return None

    def _check_slash_permissions(channel) -> tuple:
        """[FIX] Bug 2: Pre-flight permission check before attempting slash commands.
        Returns (can_proceed: bool, reason: str).
        Checks that the bot user has both 'Send Messages' and 'Use Application Commands' 
        permissions in the target channel."""
        guild = getattr(channel, 'guild', None)
        if not guild:
            return False, "No guild context"
        
        me = guild.me
        if not me:
            return False, "Cannot resolve guild member (guild not cached)"
        
        perms = channel.permissions_for(me)
        
        if not perms.send_messages:
            return False, "Missing 'Send Messages' permission"
        
        # use_application_commands was added in newer discord.py versions
        if hasattr(perms, 'use_application_commands') and not perms.use_application_commands:
            return False, "Missing 'Use Application Commands' permission"
        
        # Also check view_channel as a baseline
        if not perms.read_messages:
            return False, "Missing 'View Channel' permission"
        
        return True, "OK"

    async def _trigger_mudae_slash(channel, command_text):
        """
        Trigger a Mudae slash command. Returns True on success, False on failure.
        
        [FIX] Bug 2: Major improvements:
        1. Pre-flight permission check before attempting the request.
        2. Uses channel-scoped command fetch (works with user tokens).
        3. Enriched interaction payload with application_command wrapper.
        4. Immediate fallback to text on 403/401 (permission denied) errors 
           instead of waiting for fail_threshold consecutive failures.
        5. Periodic slash recovery: fallback mode auto-resets after 30 minutes
           so the bot re-attempts slash commands if conditions change.
        """
        cmd_display = f"/{command_text.strip().lstrip('/')}" if command_text else "/?"
        
        if not client.use_slash_rolls:
            log_function(f"[{client.muda_name}] Slash {cmd_display}: SKIP - Slash mode disabled", preset_name, "INFO")
            return False
        
        if not channel:
            log_function(f"[{client.muda_name}] Slash {cmd_display}: FAIL - No channel provided", preset_name, "ERROR")
            return False
        
        if not getattr(channel, "guild", None):
            log_function(f"[{client.muda_name}] Slash {cmd_display}: FAIL - Channel has no guild (DM or invalid)", preset_name, "ERROR")
            return False

        stripped = command_text.strip()
        if not stripped:
            log_function(f"[{client.muda_name}] Slash: FAIL - Empty command text", preset_name, "ERROR")
            return False
        
        # [FIX] Bug 2: Pre-flight permission check
        can_slash, perm_reason = _check_slash_permissions(channel)
        if not can_slash:
            if not client.slash_fallback_active:
                log_function(f"[{client.muda_name}] Slash {cmd_display}: FAIL - {perm_reason}. Activating text fallback.", preset_name, "ERROR")
                client.slash_fallback_active = True
                client.slash_fallback_activated_at = time.time()
            return False
        
        now_ts = time.time()
        if client.slash_rate_limited_until and now_ts < client.slash_rate_limited_until:
            remaining = client.slash_rate_limited_until - now_ts
            log_function(f"[{client.muda_name}] Slash {cmd_display}: SKIP - Rate limited ({remaining:.1f}s remaining)", preset_name, "WARN")
            return False
        
        if client.last_slash_attempt:
            elapsed = now_ts - client.last_slash_attempt
            if elapsed < client.slash_min_interval:
                await asyncio.sleep(client.slash_min_interval - elapsed)
        client.last_slash_attempt = time.time()
        
        # We don't support arguments in this slash impl yet
        if " " in stripped:
            key = f"mixed:{stripped.split(' ', 1)[0].lower()}"
            if key not in client.mudae_slash_missing:
                client.mudae_slash_missing.add(key)
                log_function(f"[{client.muda_name}] Slash {cmd_display}: FAIL - Commands with arguments not supported", preset_name, "WARN")
            return False
            
        base_name = stripped.lstrip("/").lower()
        guild = channel.guild
        
        # [FIX] Bug 2: Use channel-scoped fetch
        command_map = await _fetch_mudae_slash_commands(channel)
        
        if not command_map:
            log_function(f"[{client.muda_name}] Slash {cmd_display}: FAIL - Could not fetch Mudae slash commands for #{channel.name}. Check Mudae installation and channel permissions.", preset_name, "ERROR")
            return False

        command_data = command_map.get(base_name)
        if not command_data:
            key = f"missing:{base_name}"
            if key not in client.mudae_slash_missing:
                client.mudae_slash_missing.add(key)
                available_cmds = list(command_map.keys())[:10]  # Show first 10 available
                log_function(f"[{client.muda_name}] Slash {cmd_display}: FAIL - Command '{base_name}' not found. Available: {available_cmds}...", preset_name, "ERROR")
            return False

        _refresh_session_id()
        session_id = None
        ws = getattr(client, "ws", None)
        if ws and getattr(ws, "session_id", None):
            session_id = ws.session_id
        elif client.mudae_session_id:
            session_id = client.mudae_session_id

        if not session_id:
            log_function(f"[{client.muda_name}] Slash {cmd_display}: FAIL - No Discord session ID. WebSocket may be disconnected.", preset_name, "ERROR")
            return False

        # [FIX] Bug 2: Enriched interaction payload with application_command wrapper
        # and analytics_location field that Discord expects from clients.
        nonce_val = str(time_snowflake(datetime.datetime.now(datetime.timezone.utc)))
        payload = {
            "type": 2,
            "application_id": str(TARGET_BOT_ID),
            "guild_id": str(guild.id),
            "channel_id": str(channel.id),
            "session_id": session_id,
            "data": {
                "version": str(command_data.get("version", "")),
                "id": str(command_data.get("id", "")),
                "name": command_data.get("name"),
                "type": command_data.get("type", 1),
                "application_command": {
                    "id": str(command_data.get("id", "")),
                    "application_id": str(TARGET_BOT_ID),
                    "version": str(command_data.get("version", "")),
                    "type": command_data.get("type", 1),
                    "name": command_data.get("name"),
                    "description": command_data.get("description", ""),
                    "dm_permission": command_data.get("dm_permission", True),
                    "integration_types": command_data.get("integration_types", [0]),
                    "global_popularity_rank": command_data.get("global_popularity_rank", 0),
                    "options": command_data.get("options", []),
                    "description_localized": command_data.get("description", ""),
                    "name_localized": command_data.get("name", ""),
                },
                "attachments": [],
            },
            "nonce": nonce_val,
            "analytics_location": "slash_ui",
        }

        invalidate_cache = False
        try:
            await client.http.request(Route("POST", "/interactions"), json=payload)
            client.slash_fail_streak = 0
            client.slash_rate_limited_until = 0.0
            return True
        except discord.HTTPException as e:
            status = getattr(e, "status", "?")
            code = getattr(e, "code", "?")
            text = getattr(e, "text", str(e))
            retry_after = getattr(e, "retry_after", None)
            
            if retry_after:
                client.slash_rate_limited_until = time.time() + min(retry_after, client.slash_max_backoff)
                log_function(f"[{client.muda_name}] Slash {cmd_display}: FAIL - Rate limited by Discord. Retry after {retry_after}s", preset_name, "WARN")
                await asyncio.sleep(retry_after)
            elif status in (401, 403):
                # [FIX] Bug 2: Immediate fallback on authorization/permission errors.
                # Don't wait for fail_threshold — these are structural, not transient.
                log_function(f"[{client.muda_name}] Slash {cmd_display}: FAIL - HTTP {status} (Permission Denied). Switching to text commands immediately.", preset_name, "ERROR")
                client.slash_fallback_active = True
                client.slash_fallback_activated_at = time.time()
                return False
            elif status == 400:
                # Bad Request — likely payload issue. Invalidate cache and retry.
                invalidate_cache = True
                log_function(f"[{client.muda_name}] Slash {cmd_display}: FAIL - HTTP 400 (Bad Request, code: {code}): {text[:100]}. Command cache invalidated.", preset_name, "ERROR")
            else:
                invalidate_cache = True
                log_function(f"[{client.muda_name}] Slash {cmd_display}: FAIL - HTTP {status} (code: {code}): {text[:100]}", preset_name, "ERROR")
            client.slash_fail_streak += 1
        except Exception as e:
            client.slash_fail_streak += 1
            invalidate_cache = True
            log_function(f"[{client.muda_name}] Slash {cmd_display}: FAIL - Unexpected error: {type(e).__name__}: {str(e)[:100]}", preset_name, "ERROR")

        if invalidate_cache:
            # [FIX] Bug 2: Invalidate using the correct cache key (channel-scoped)
            cache_key = (guild.id, channel.id)
            client.mudae_slash_cache.pop(cache_key, None)
        if client.slash_fail_streak >= client.slash_fail_threshold and not client.slash_fallback_active:
            # [NEW] Activate dynamic text fallback after consecutive slash failures
            client.slash_fallback_active = True
            client.slash_fallback_activated_at = time.time()
            log_function(f"[{client.muda_name}] Slash: {client.slash_fail_streak} consecutive failures. Automatically falling back to text commands ({client.mudae_prefix}).", preset_name, "WARN")
        return False

    async def send_roll_command(channel, command_name):
        cmd = (command_name or "").strip()
        if not cmd:
            return

        normalized = cmd.lstrip('/')

        if client.use_slash_rolls and not client.slash_fallback_active:
            # Slash mode active and healthy — attempt slash command
            slash_target = normalized
            slash_override_map = {"w": "wx", "h": "hx", "m": "mx"}
            slash_target = slash_override_map.get(slash_target.lower(), slash_target)
            slash_name = slash_target if slash_target.startswith("/") else f"/{slash_target}"
            success = await _trigger_mudae_slash(channel, slash_name)
            if success:
                return
            # If fallback just activated inside _trigger_mudae_slash, fall through to text
            if not client.slash_fallback_active:
                return  # Slash is still preferred, just a transient failure

        # Text mode: Used when slash is disabled OR fallback is active
        await channel.send(f"{client.mudae_prefix}{normalized}")

    async def send_tu_command(channel):
        """
        Send $tu command via slash (if enabled) or text.
        If slash is enabled and not in fallback mode, retries up to 3 times on failure.
        If all slash attempts fail, activates text fallback automatically.
        """
        if client.use_slash_rolls and not client.slash_fallback_active:
            max_attempts = 3
            retry_delay = 5.0  # seconds between retries
            
            for attempt in range(1, max_attempts + 1):
                # _trigger_mudae_slash logs detailed failure reasons
                sent = await _trigger_mudae_slash(channel, "tu")
                if sent:
                    return True
                
                # If fallback just activated inside _trigger_mudae_slash, break out and use text
                if client.slash_fallback_active:
                    break
                
                if attempt < max_attempts:
                    log_function(f"[{client.muda_name}] Retrying /tu in {retry_delay}s... (attempt {attempt}/{max_attempts})", preset_name, "WARN")
                    await asyncio.sleep(retry_delay)
            
            # If fallback is now active, fall through to text. Otherwise wait.
            if not client.slash_fallback_active:
                log_function(f"[{client.muda_name}] /tu failed after {max_attempts} attempts. Entering 30-minute cooldown before next retry.", preset_name, "ERROR")
                await asyncio.sleep(30 * 60)
                return False
        
        # Text mode: Used when slash is disabled OR fallback is active
        await channel.send(f"{client.mudae_prefix}tu")
        return True

    def _get_command_channel():
        """Returns the command channel (for $tu, $daily, $dk, $rolls) or fallback to main channel."""
        return getattr(client, 'command_channel', None) or getattr(client, '_main_channel', None)

    def _is_main_loop_alive():
        """Check if the main status loop task is still running."""
        task = client._main_loop_task
        return task is not None and not task.done()

    async def main_status_loop(client, channel):
        """
        [FIX] Centralized main loop: replaces ALL recursive check_status calls.
        Runs check_status in a flat while-loop. External triggers signal via
        client._immediate_check_event instead of spawning duplicate tasks.
        """
        log_function(f"[{client.muda_name}] Main status loop started.", preset_name, "INFO")
        while not client.is_closed():
            try:
                # --- PAUSE GUARD ---
                if client.is_paused:
                    await asyncio.sleep(1)
                    continue
                # Run one cycle of check_status (no longer recursive)
                await check_status(client, channel, client.mudae_prefix, current_cycle_id=None)
            except asyncio.CancelledError:
                log_function(f"[{client.muda_name}] Main status loop cancelled.", preset_name, "INFO")
                break
            except Exception as e:
                log_function(f"[{client.muda_name}] Main loop error: {e}. Retrying in 60s.", preset_name, "ERROR")
                await asyncio.sleep(60)
        log_function(f"[{client.muda_name}] Main status loop exited.", preset_name, "INFO")

    @client.event
    async def on_ready():
        _refresh_session_id()

        # [FIX] Gateway reconnect: verify main loop health and restart if dead
        if client._has_initialized:
            log_function(f"[{client.muda_name}] Reconnected: {client.user}. Verifying loop health...", preset_name, "INFO")
            if not _is_main_loop_alive():
                channel = getattr(client, '_main_channel', None)
                if channel:
                    log_function(f"[{client.muda_name}] Main loop was dead after reconnect. Restarting.", preset_name, "ERROR")
                    client._main_loop_task = client.loop.create_task(main_status_loop(client, channel))
                else:
                    log_function(f"[{client.muda_name}] Reconnected but no channel reference. Cannot restart loop.", preset_name, "ERROR")
            else:
                log_function(f"[{client.muda_name}] Main loop still alive. Signaling immediate check.", preset_name, "INFO")
                if client._immediate_check_event:
                    client._immediate_check_event.set()
            return

        client._has_initialized = True
        client.is_processing_cycle = False
        client._immediate_check_event = asyncio.Event()
        log_function(f"[{client.muda_name}] Ready: {client.user}", preset_name, "INFO")
        client.loop.create_task(health_monitor_task())
        
        # Retrieve target channel and validate
        try:
            target_channel_id_int = int(target_channel_id)
        except (ValueError, TypeError):
            log_function(f"[{client.muda_name}] Err: Invalid channel ID format: {target_channel_id}", preset_name, "ERROR"); await client.close(); return

        channel = client.get_channel(target_channel_id_int)
        if not channel:
            log_function(f"[{client.muda_name}] Channel {target_channel_id_int} not in cache, fetching...", preset_name, "INFO")
            try:
                channel = await client.fetch_channel(target_channel_id_int)
            except discord.NotFound:
                log_function(f"[{client.muda_name}] Channel {target_channel_id_int} not found via API", preset_name, "ERROR"); await client.close(); return
            except discord.Forbidden:
                log_function(f"[{client.muda_name}] No access to channel {target_channel_id_int}", preset_name, "ERROR"); await client.close(); return
            except Exception as e:
                log_function(f"[{client.muda_name}] Err fetching channel {target_channel_id_int}: {e}", preset_name, "ERROR"); await client.close(); return
        
        if not isinstance(channel, (discord.TextChannel, discord.Thread, discord.VoiceChannel)):
            log_function(f"[{client.muda_name}] Err: Channel {target_channel_id_int} is not a messageable channel", preset_name, "ERROR"); await client.close(); return
        
        # Store main channel reference for _get_command_channel fallback
        client._main_channel = channel

        # --- Resolve Command Channel (optional) ---
        # If set, $tu/$daily/$dk/$rolls go here; rolls and claims stay on main channel.
        client.command_channel = None
        cmd_ch_id_str = client.command_channel_id_preset
        if cmd_ch_id_str:
            try:
                cmd_ch_id_int = int(cmd_ch_id_str)
                cmd_ch = client.get_channel(cmd_ch_id_int)
                if not cmd_ch:
                    try:
                        cmd_ch = await client.fetch_channel(cmd_ch_id_int)
                    except Exception as e:
                        log_function(f"[{client.muda_name}] Command channel {cmd_ch_id_int} fetch failed: {e}. Falling back to main channel.", preset_name, "WARN")
                        cmd_ch = None
                if cmd_ch and isinstance(cmd_ch, (discord.TextChannel, discord.Thread, discord.VoiceChannel)):
                    client.command_channel = cmd_ch
                    log_function(f"[{client.muda_name}] Command channel set: #{cmd_ch.name} ({cmd_ch.id})", preset_name, "INFO")
                elif cmd_ch:
                    log_function(f"[{client.muda_name}] Command channel {cmd_ch_id_int} is not messageable. Falling back to main channel.", preset_name, "WARN")
            except (ValueError, TypeError):
                log_function(f"[{client.muda_name}] Invalid command_channel_id: '{cmd_ch_id_str}'. Falling back to main channel.", preset_name, "WARN")

        if client.rolling_enabled:
             # Permissions check
            can_send = channel.permissions_for(channel.guild.me).send_messages
            if not can_send: log_function(f"[{client.muda_name}] No Send Permissions", preset_name, "ERROR"); await client.close(); return
        
        log_function(f"[{client.muda_name}] Starting in {start_delay}s...", preset_name, "INFO")
        await asyncio.sleep(start_delay + random.uniform(0.1, 0.5))

        if is_inactive_hour():
            wait_s = seconds_until_active()
            if client.humanization_enabled:
                wait_s += random.uniform(0, max(0.0, client.humanization_window_minutes * 60))
            log_function(f"[{client.muda_name}] Inactive hours active. Sleeping {wait_s/60:.0f}m until active period.", preset_name, "RESET")
            await asyncio.sleep(wait_s)

        if client.rolling_enabled:
            try:
                if not client.skip_initial_commands:
                    cmd_ch = _get_command_channel() or channel
                    await cmd_ch.send(f"{client.mudae_prefix}limroul 1 1 1 1"); await asyncio.sleep(1.0 + random.uniform(0.1, 0.4))
            except Exception as e:
                log_function(f"[{client.muda_name}] Setup error: {e}", preset_name, "ERROR"); await client.close(); return

            # [FIX] Launch the centralized main loop instead of a one-shot check_status
            client._main_loop_task = client.loop.create_task(main_status_loop(client, channel))

            if client.scheduled_roll_times:
                client.loop.create_task(scheduled_roll_task(channel))
        else:
            client.loop.create_task(snipe_only_status_loop(client, channel))

    async def handle_dk_power_management(client, channel, tu_content):
        content_lower = tu_content.lower()
        
        # Check stock
        dk_stock_match = re.search(r"\*\*(\d+)\*\*\s*\$dk\s*(?:available|dispon[ií]ve(?:l|is)|no estoque|disponible|en stock|disponibles?)", content_lower)
        if dk_stock_match:
            client.dk_stock_count = int(dk_stock_match.group(1))
            log_function(f"[{client.muda_name}] DK Stock: {client.dk_stock_count}", preset_name, "INFO")
        elif re.search(r"\$dk.*?(?:ready|pronto|disponible|prêt|dispon[ií]vel|listo)", content_lower):
            # Fallback for cases where it says "ready" without a stock number on the same line
            client.dk_stock_count = 1
            log_function(f"[{client.muda_name}] DK Stock: 1 (Derived)", preset_name, "INFO")
        else:
            client.dk_stock_count = 0
        
        if client.dk_stock_count == 0:
            return
        
        try:
            power_match = re.search(r"(?:power|poder):\s*\*{0,2}(\d+)%\*{0,2}", content_lower)
            
            # Handling PT-BR translation variance: "reação" vs "botão", Spanish/French: "botón"/"bouton"
            consumption_match = re.search(r"(?:each kakera (?:reaction|button) consumes|cada (?:reação|botão|botón) de kakera consume|chaque bouton kakera consomme)\s*(\d+)%", content_lower)
            
            if not power_match or not consumption_match:
                log_function(f"[{client.muda_name}] DK: Parse failed (power/consumption).", preset_name, "WARN")
                return
            
            current_power = int(power_match.group(1))
            consumption_cost = int(consumption_match.group(1))
            
            effective_cost = consumption_cost
            if getattr(client, 'only_chaos', False):
                effective_cost = int(consumption_cost / 2)

            # Use item if power is too low for the required reaction type
            if current_power < effective_cost:
                log_function(f"[{client.muda_name}] DK: Activating. ({current_power}% < {effective_cost}%)", preset_name, "KAKERA")
                await channel.send(f"{client.mudae_prefix}dk")
                await asyncio.sleep(1.5 + random.uniform(0.1, 0.4)) 
                client.dk_stock_count = max(0, client.dk_stock_count - 1)
                # [FIX] Task 1: $dk restores to max_dk_power instead of hardcoded 100
                client.current_dk_power = client.max_dk_power
                client.last_dk_power_update_utc = datetime.datetime.now(datetime.timezone.utc)
            else:
                pass

        except Exception as e:
            log_function(f"[{client.muda_name}] DK logic error: {e}", preset_name, "ERROR")


    async def snipe_only_status_loop(client, channel):
        """
        Ghost Mode Loop:
        1. Initial Handshake: Check $tu ONCE to sync minute/status.
        2. Silent Phase: Sleep until next calculated reset. Never send commands automatically.
        """
        log_function(f"[{client.muda_name}] Snipe-only: Performing initial handshake...", client.preset_name, "INFO")
        
        # --- INITIAL HANDSHAKE ---
        handshake_success = False
        while not client.is_closed():
            # --- PAUSE GUARD ---
            if client.is_paused:
                await asyncio.sleep(1)
                continue
            try:
                # Proceed to rolls=False, we just want data
                await check_status(client, channel, client.mudae_prefix, proceed_to_rolls=False, current_cycle_id=None)
                if client.next_claim_reset_at_utc:
                    handshake_success = True
                    break
                log_function(f"[{client.muda_name}] Snipe-only: Handshake incomplete. Retrying in 30s...", client.preset_name, "WARN")
                await asyncio.sleep(30)
            except Exception as e:
                log_function(f"[{client.muda_name}] Handshake error: {e}. Retrying in 30s...", client.preset_name, "ERROR")
                await asyncio.sleep(30)
        
        if not handshake_success: return # Client closed

        log_function(f"[{client.muda_name}] Snipe-only: Handshake complete. Entering Ghost Mode.", client.preset_name, "INFO")

        # --- GHOST LOOP ---
        while not client.is_closed():
            # --- PAUSE GUARD ---
            if client.is_paused:
                await asyncio.sleep(1)
                continue
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            
            if not client.claim_right_available:
                # STATE: COOLDOWN -> Sleep until reset
                if client.next_claim_reset_at_utc and client.next_claim_reset_at_utc > now_utc:
                    wait_seconds = (client.next_claim_reset_at_utc - now_utc).total_seconds()
                    # Add buffer to ensure we wake up AFTER the minute flips
                    real_wait = max(5, wait_seconds + 2.0)
                    
                    log_function(f"[{client.muda_name}] Snipe-only: Silent. Sleeping {real_wait/60:.1f}m until reset.", client.preset_name, "RESET")
                    try:
                        await asyncio.sleep(real_wait)
                    except asyncio.CancelledError:
                        break # Allow clean ext
                    
                    # WAKE UP: Internal State Update
                    # Double check time just in case
                    if datetime.datetime.now(datetime.timezone.utc) >= client.next_claim_reset_at_utc:
                        client.claim_right_available = True
                        client.last_successfully_claimed_character = None
                        log_function(f"[{client.muda_name}] Snipe-only: Reset time reached. Claim restored locally.", client.preset_name, "CLAIM")
                        
                        # Chain the minute anchor
                        reset_delta = datetime.timedelta(minutes=client.claim_interval)
                        while client.next_claim_reset_at_utc <= datetime.datetime.now(datetime.timezone.utc):
                             client.next_claim_reset_at_utc += reset_delta
                        
                        log_function(f"[{client.muda_name}] Snipe-only: Next reset anchored to {client.next_claim_reset_at_utc.strftime('%H:%M')}", client.preset_name, "INFO")
                else:
                    # Fallback (Should be rare)
                    await asyncio.sleep(10)
            else:
                # STATE: READY -> Passive Monitor
                # We are waiting for on_message to trigger 'claim_character' -> 'verify_snipe_outcome'
                # Passively sleep in short bursts to allow for responsive shutdown or state checks
                await asyncio.sleep(10)


    async def _interruptible_sleep(seconds):
        """[FIX] Sleep that can be interrupted by _immediate_check_event.
        Used for long waits (e.g., 30min failure retry) so reconnect can wake the loop."""
        evt = client._immediate_check_event
        if evt:
            evt.clear()
            try:
                await asyncio.wait_for(evt.wait(), timeout=seconds)
                debug_log(f"_interruptible_sleep interrupted after signal (was sleeping {seconds}s).")
            except asyncio.TimeoutError:
                pass  # Normal: sleep completed without interruption
        else:
            await asyncio.sleep(seconds)

    async def check_status(client, channel, mudae_prefix, proceed_to_rolls: bool = True, current_cycle_id=None):
        """[FIX] Now a single-execution function. No recursion. The main_status_loop
        handles looping. Returns a sleep duration (in minutes) for the caller to wait,
        or 0 to re-check immediately, or -1 to signal the caller to stop."""
        if getattr(client, 'is_processing_cycle', False):
            debug_log("check_status called but a cycle is already processing. Aborting duplicate execution.")
            return
        client.is_processing_cycle = True
        
        try:
            if current_cycle_id is None:
                current_cycle_id = time.time()
                client.active_cycle_id = current_cycle_id

            cmd_channel = _get_command_channel() or channel
            log_function(f"[{client.muda_name}] Checking $tu...", client.preset_name, "CHECK")
            tu_message_content = None


            # Retrieve $tu message (using slash command if enabled)
            # IMPORTANT: Validate that the response is addressed to THIS user, not another player
            def is_tu_response_for_self(message_content: str) -> bool:
                """
                Validates that a Mudae $tu response is addressed to the bot's own user.
                Mudae formats responses as: **Username**, your rolls: ... or **Username**, you __can__ claim...
                Returns True if the username in the response matches client.user.
                """
                if not message_content:
                    return False
                
                # Extract the bolded username at the start of the message
                # Pattern matches: **Username** at the beginning (with optional leading whitespace)
                username_match = re.match(r"^\s*\*\*([^*]+)\*\*", message_content)
                if not username_match:
                    # Fallback: some Mudae responses may use different formatting
                    # If we can't extract a username, be conservative and reject
                    return False
                
                response_username = username_match.group(1).strip().lower()
                
                # Compare against both the bot's username and display name
                bot_username = (client.user.name or "").strip().lower()
                bot_display_name = (client.user.display_name or "").strip().lower()
                
                # Match if either the username or display name matches
                return response_username == bot_username or response_username == bot_display_name
            
            # NEW FIX: Safely create the lock inside the running event loop
            if client.tu_lock is None:
                client.tu_lock = asyncio.Lock()

            if client.tu_lock.locked():
                return # Another task is currently checking $tu
            
            async with client.tu_lock:
                for _ in range(5):
                    await send_tu_command(cmd_channel); await asyncio.sleep(2.5 + random.uniform(0.2, 0.6))
                    async for msg in cmd_channel.history(limit=10):
                        if msg.author.id == TARGET_BOT_ID and msg.content:
                            c = msg.content.lower()
                            # Broad check for $tu response characteristics (rolls count, reset timers, or specific keywords)
                            # "rolls" is common across all tested languages (EN, FR, ES, PT)
                            # "reset" is also very common. "min" is universal for minutes.
                            if ("roll" in c and "min" in c) or ("roll" in c and "**" in c):
                                # Validate this response is for OUR user, not someone else's $tu
                                if is_tu_response_for_self(msg.content):
                                    tu_message_content = msg.content
                                    break
                                else:
                                    # This is another player's $tu response, skip it
                                    # Extract the detected username for debug logging
                                    other_user_match = re.match(r"^\s*\*\*([^*]+)\*\*", msg.content)
                                    other_user = other_user_match.group(1) if other_user_match else "Unknown"
                                    log_function(f"[{client.muda_name}] Skipped $tu response for '{other_user}' (not our user)", preset_name, "INFO")
                                    continue
                    if tu_message_content: break
                    await asyncio.sleep(5)
                
                if not tu_message_content:
                    log_function(f"[{client.muda_name}] Failed to get $tu response.", preset_name, "ERROR")
                    if client.rolling_enabled and proceed_to_rolls:
                        # [FIX] No recursion. Use Event-aware sleep so reconnect can wake us.
                        await _interruptible_sleep(1800)
                    return

                c_lower = tu_message_content.lower()
                debug_log(f"Raw $tu content (first 300 chars): {tu_message_content[:300]}")

            if client.auto_dk_enabled and client.dk_power_management and client.rolling_enabled:
                await handle_dk_power_management(client, cmd_channel, tu_message_content)

            # Automatic $daily and $dk handling
            if client.rolling_enabled:
                # Check if $daily is available and send if so
                if "$daily is available" in c_lower or "$daily está disponível" in c_lower or \
                   "$daily está disponible" in c_lower or "$daily est disponible" in c_lower:
                    log_function(f"[{client.muda_name}] $daily is available! Sending command...", preset_name, "INFO")
                    await cmd_channel.send(f"{client.mudae_prefix}daily")
                    await asyncio.sleep(2.0 + random.uniform(0.1, 0.5))

                # Check if $dk is ready (only when power management is OFF but auto_dk is ON)
                if client.auto_dk_enabled and not client.dk_power_management:
                    if re.search(r"\$dk.*?(?:ready|pronto|disponible|prêt|dispon[ií]vel|listo)", c_lower):
                        log_function(f"[{client.muda_name}] $dk is ready! Sending command...", preset_name, "INFO")
                        await cmd_channel.send(f"{client.mudae_prefix}dk")
                        await asyncio.sleep(2.0 + random.uniform(0.1, 0.5))

                # Check if $p is ready/available and auto_p_enabled is True
                if client.auto_p_enabled:
                    p_on_cooldown = False
                    if client.next_p_claim_at_utc and now_utc < client.next_p_claim_at_utc:
                        p_on_cooldown = True
                    
                    if not p_on_cooldown:
                        p_ready_keywords = ["$p is available", "$p está disponível", "$p está disponible", "$p est disponible"]
                        p_ready = any(x in c_lower for x in p_ready_keywords)
                        p_cooldown_match = re.search(r"(?:next \$p|próximo \$p|prochain \$p).*?\*{0,2}(\d+h)?\s*(\d+)\*{0,2}\s*min", c_lower)
                        
                        if p_cooldown_match:
                            h_p, m_p = parse_hours_minutes(p_cooldown_match)
                            p_reset_minutes = h_p * 60 + m_p
                            client.p_available = False
                            client.next_p_claim_at_utc = (now_utc + datetime.timedelta(minutes=p_reset_minutes)).replace(second=0, microsecond=0)
                            log_function(f"[{client.muda_name}] Points ($p): Cooldown ({h_p}h {m_p}m)", preset_name, "INFO")
                        elif p_ready:
                            client.p_available = True
                            client.next_p_claim_at_utc = None
                            log_function(f"[{client.muda_name}] Points ($p): Ready", preset_name, "INFO")
                        
                        if client.p_available:
                            log_function(f"[{client.muda_name}] $p is available! Sending command...", preset_name, "INFO")
                            await cmd_channel.send(f"{client.mudae_prefix}p")
                            client.p_available = False
                            client.next_p_claim_at_utc = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=2)).replace(second=0, microsecond=0)
                            await asyncio.sleep(2.0 + random.uniform(0.1, 0.5))

            # Always parse Kakera Power from $tu to update local state (Scanning for Power: XX%)
            try:
                power_match = re.search(r"(?:power|poder):\s*\*{0,2}(\d+)%\*{0,2}", c_lower)
                if power_match:
                    client.current_dk_power = int(power_match.group(1))
                    client.last_dk_power_update_utc = datetime.datetime.now(datetime.timezone.utc)
                    debug_log(f"Parsed DK Power: {client.current_dk_power}%")
                else:
                    debug_log("WARN: Could not parse DK Power from $tu. Regex found no match.")

                # Support EN, PT, ES, FR for consumption regex
                consumption_match = re.search(r"(?:each kakera (?:reaction|button) consumes|cada (?:reação|botão|botón) de kakera consume|chaque bouton kakera consomme)\s*(\d+)%", c_lower)
                if consumption_match:
                    client.dk_consumption = int(consumption_match.group(1))
                    client.dk_consumption_chaos = int(client.dk_consumption / 2)
                    debug_log(f"Parsed DK Consumption: {client.dk_consumption}% (Chaos: {client.dk_consumption_chaos}%)")
                else:
                    debug_log(f"WARN: Could not parse DK Consumption from $tu. Using fallback: {client.dk_consumption}%")
                
                # Update dk_stock_count while we are here, in case dk_power_management was off
                # This ensures logs reflect reality even if management is disabled
                dk_stock_match = re.search(r"\*\*(\d+)\*\*\s*\$dk\s*(?:available|dispon[ií]ve(?:l|is)|no estoque|disponible|en stock|disponibles?)", c_lower)
                if dk_stock_match:
                    client.dk_stock_count = int(dk_stock_match.group(1))
                    debug_log(f"Parsed DK Stock: {client.dk_stock_count}")
                elif re.search(r"\$dk.*?(?:ready|pronto|disponible|prêt|dispon[ií]vel|listo)", c_lower):
                    client.dk_stock_count = 1
                    debug_log("Parsed DK Stock: 1 (derived from ready status)")
                else:
                    debug_log("DK Stock: 0 (no ready/stock indicators found)")

            except Exception as e:
                log_function(f"[{client.muda_name}] Error parsing Power/DK state: {e}", preset_name, "WARN")


            now_utc = datetime.datetime.now(datetime.timezone.utc)

            # $rt Status
            # Multilingual support: EN, PT, ES, FR
            # Keywords: available, pronto, disponible, prêt
            rt_ready_keywords = ["$rt is available", "$rt está pronto", "$rt esta pronto", "$rt está disponível", 
                                 "$rt está disponible", "$rt est disponible", "$rt est prêt", "$rt is ready"]
            rt_ready = any(x in c_lower for x in rt_ready_keywords)
            rt_reset_minutes = None

            # Supports "$rt is in...", "$rt... time left:", "recarga do $rt", etc.
            # Captures: ... <text> ... (Hh)? Mm min
            match_rt_reset = re.search(r"(?:\$rt|recarga|enfriamiento|cool).*?(?:\:|in|em|en|dans|left|restante|restam|falta|tiempo|temps|tempo|restantes|restant)\s*:?\s*\*{0,2}(\d+h)?\s*(\d+)\*{0,2}\s*min", c_lower)
            if match_rt_reset:
                h_rt, m_rt = parse_hours_minutes(match_rt_reset)
                rt_reset_minutes = h_rt * 60 + m_rt
                client.rt_available = False
                log_function(f"[{client.muda_name}] RT: Cooldown ({h_rt}h {m_rt}m)", preset_name, "INFO")
                debug_log(f"Parsed RT Reset: {h_rt}h {m_rt}m ({rt_reset_minutes} total min). Raw match: '{match_rt_reset.group(0)}'")
            elif rt_ready:
                client.rt_available = True
                log_function(f"[{client.muda_name}] RT: Ready", preset_name, "INFO")
                debug_log("Parsed RT: Ready (keyword matched)")
            else:
                # Fallback: If we didn't find a timer AND didn't find "Ready", assume cooldown/unavailable
                # (Safety default)
                client.rt_available = False
                log_function(f"[{client.muda_name}] RT: Cooldown (Derived)", preset_name, "INFO")
                debug_log("WARN: RT status fallback — no timer regex match and no ready keyword. Assuming cooldown.")

            # Claim Status
            can_claim = False
            wait_time = 0



            # Regex for Claim Ready (Positive)
            # EN: you __can__ claim
            # PT: você __pode__ se casar
            # ES: __puedes__ reclamar
            # FR: vous __pouvez__ vous marier / remarier
            claim_ready_pattern = r"__(?:can|pode|puedes|pouvez)__\s+(?:claim|se casar|reclamar|vous (?:re)?marier)"
            claim_ready = bool(re.search(claim_ready_pattern, c_lower))
            debug_log(f"Claim Ready regex result: {claim_ready}")
            
            # Regex for Claim Reset Time (Cooldown)
            # Covers: "Next claim reset is in...", "temps restant...", "falta um tempo...", "no puedes reclamar..."
            # We look for keywords "claim/casar/marier/reclamar" OR "reset/tempo/temps/falta" followed eventually by time.
            # This broad regex attempts to catch the specific minutes line.
            claim_reset_minutes = None
            
            # Priority check for the "reset is in X min" line which usually appears when claiming is available (for next reset)
            # or when on cooldown.
            match_claim_reset = re.search(r"(?:next claim|próximo|siguiente|prochain|tempo|temps|falta)\s+(?:reset|reclamo|tempo|temps|um tempo).*?(?:in|em|en|dans|left|restante|restant|falta|dentro de)\s*:?\s*\*{0,2}(\d+h)?\s*(\d+)\*{0,2}\s*min", c_lower)
            
            # [FIX] Reject match_claim_reset if it accidentally matched a $daily/$dk/$rt line
            if match_claim_reset:
                matched_text = match_claim_reset.group(0)
                if any(kw in matched_text for kw in ["$daily", "$dk", "$rt"]):
                    debug_log(f"Claim Reset regex REJECTED (matched wrong timer): '{matched_text}'")
                    match_claim_reset = None
            
            # Alternative strict check for simple cooldown lines like "no puedes... 20 min"
            match_claim_wait = re.search(r"(?:can't|não pode|no puedes|avant de).*?(?:claim|casar|reclamar|remarier).*?\*{0,2}(\d+h)?\s*(\d+)\*{0,2}\s*min", c_lower)
            
            # [FIX] Portuguese claim cooldown: "falta um tempo antes que você possa se casar novamente **Xh Y** min."
            # This format is missed by both regexes above because it uses "antes que...casar novamente" instead of
            # "não pode...casar" or a "reset...em" structure.
            if not match_claim_wait:
                match_claim_wait = re.search(r"falta\s+um\s+tempo.*?(?:casar|remarier|claim|reclamar).*?\*{0,2}(\d+h)?\s*(\d+)\*{0,2}\s*min", c_lower)

            # Extract time from best match
            best_match = match_claim_reset or match_claim_wait
            if best_match:
                 h_c, m_c = parse_hours_minutes(best_match)
                 claim_reset_minutes = h_c * 60 + m_c
                 wait_time = claim_reset_minutes # In cooldown context, this is the wait time
                 debug_log(f"Parsed Claim Reset: {h_c}h {m_c}m ({claim_reset_minutes} total min). Raw: '{best_match.group(0)}'")
            else:
                 debug_log("WARN: No claim reset regex match found. Will attempt generic fallback.")

            if claim_ready:
                client.claim_right_available = True
                client.last_successfully_claimed_character = None # Reset last claim on new cycle
                log_function(f"[{client.muda_name}] Claim: Ready", preset_name, "INFO")
                client.current_min_kakera_for_roll_claim = client.min_kakera
                
                if client.snipe_ignore_min_kakera_reset: 
                     if claim_reset_minutes is not None and claim_reset_minutes <= 60:
                          client.current_min_kakera_for_roll_claim = 0
                          log_function(f"[{client.muda_name}] Reset soon ({claim_reset_minutes}m). Ignoring Min Kakera.", preset_name, "WARN")
                
                if claim_reset_minutes is not None:
                    # Align to the next minute boundary (:00) for precision
                    client.next_claim_reset_at_utc = (now_utc + datetime.timedelta(minutes=claim_reset_minutes)).replace(second=0, microsecond=0)
                else:
                    client.next_claim_reset_at_utc = now_utc.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)
                
                can_claim = True
            else:
                client.claim_right_available = False
                client.current_min_kakera_for_roll_claim = client.min_kakera  # Reset to normal rules
                
                if claim_reset_minutes is not None and claim_reset_minutes > 0:
                     log_function(f"[{client.muda_name}] Claim: Cooldown ({int(claim_reset_minutes/60)}h {claim_reset_minutes%60}m)", preset_name, "INFO")
                     
                     # Align to next minute for precision
                     target_time = (now_utc + datetime.timedelta(minutes=claim_reset_minutes)).replace(second=0, microsecond=0)
                     client.claim_cooldown_until_utc = target_time
                     client.next_claim_reset_at_utc = target_time
                else:
                     # Backup generic finder if specific regex failed (e.g. "20 min" floating alone in context)
                     # Only rely on this if we are SURE it's not a claim-ready state
                     match_generic = re.search(r"\*{0,2}(\d+h)?\s*(\d+)\*{0,2}\s*min", c_lower.split('\n')[0]) # Usually first line
                     if match_generic:
                          h_g, m_g = parse_hours_minutes(match_generic)
                          wait_time = h_g * 60 + m_g
                          log_function(f"[{client.muda_name}] Claim: Cooldown ({int(wait_time/60)}h {wait_time%60}m) (Generic)", preset_name, "INFO")
                          target_time = (now_utc + datetime.timedelta(minutes=wait_time)).replace(second=0, microsecond=0)
                          client.claim_cooldown_until_utc = target_time
                          client.next_claim_reset_at_utc = target_time
                          claim_reset_minutes = wait_time
                
            # Roll Reset Status (New in check_status for better sleep awareness)
            roll_reset_minutes = None
            match_roll_reset = re.search(r"(?:reset in|reinicialização é em|siguiente reinicio.*?en|prochain rolls reset dans)\s+\*{0,2}(\d+h)?\*{0,2}\s*\*{0,2}(\d+)\*{0,2}\s*min", c_lower)
            if match_roll_reset:
                h_r, m_r = parse_hours_minutes(match_roll_reset)
                roll_reset_minutes = h_r * 60 + m_r
                debug_log(f"Parsed Roll Reset: {h_r}h {m_r}m ({roll_reset_minutes} total min)")
            else:
                debug_log("Roll Reset regex: no match found.")
 
            # Kakera Status
            if "you __can__ react" in c_lower or "pode reagir" in c_lower or "pegar kakera" in c_lower or "puedes__ reaccionar" in c_lower or "puedes reaccionar" in c_lower or "pouvez__ réagir" in c_lower or "pouvez réagir" in c_lower:
                client.kakera_react_available = True
                client.kakera_react_cooldown_until_utc = None
            elif "can't react" in c_lower or "não pode" in c_lower or "no puedes" in c_lower:
                client.kakera_react_available = False
                # Try to parse time
                match_k = re.search(r"(?:react|pegar|reaccionar).*?\*{0,2}(\d+h)?\s*(\d+)\*{0,2}\s*min", c_lower)
                if match_k:
                    h, m = parse_hours_minutes(match_k)
                    client.kakera_react_cooldown_until_utc = now_utc + datetime.timedelta(minutes=(h*60+m))

            if client.key_limit_hit:
                log_function(f"[{client.muda_name}] Recovering from key limit. Skipping rolls.", preset_name, "INFO")
                client.key_limit_hit = False
                return

            # Timing logic: Only roll if claim reset is near (<= 60 mins)
            is_timing_window = False
            if client.time_rolls_to_claim_reset and claim_reset_minutes is not None and claim_reset_minutes <= 60:
                is_timing_window = True

            # Panic Roll Logic (Lurker Strategy)
            is_panic_window = False
            is_lurking = False
            if client.lurker_mode and client.claim_right_available and claim_reset_minutes is not None:
                if claim_reset_minutes <= client.panic_roll_minutes:
                    is_panic_window = True
                    client.current_min_kakera_for_roll_claim = 0
                    log_function(f"[{client.muda_name}] Panic Roll Mode: Reset soon ({claim_reset_minutes}m). Dumping everything.", preset_name, "CLAIM")
                else:
                    is_lurking = True
                    log_function(f"[{client.muda_name}] Lurking Mode: Waiting for others to roll. Panic in {claim_reset_minutes - client.panic_roll_minutes}m.", preset_name, "INFO")

            immediate_roll = (client.rolling_enabled and proceed_to_rolls and 
                             ((can_claim and not is_lurking) or client.key_mode or client.rt_available or is_timing_window or is_panic_window))
            
            # Globally parse $mk available from $tu
            mk_match = re.search(r"\(\+\*{0,2}([\d,.]+)\*{0,2}\s+\$mk\)", c_lower)
            if mk_match:
                client.mk_rolls_left = int(re.sub(r"[^\d]", "", mk_match.group(1)))
                debug_log(f"Parsed $mk rolls: {client.mk_rolls_left}")
            else:
                client.mk_rolls_left = 0
                debug_log("$mk rolls: 0 (no match)")
                
            if client.rolling_enabled and proceed_to_rolls and not immediate_roll:
                # If we're not doing normal rolls but have enough power and $mk left, use them before sleeping
                if client.auto_mk_enabled and client.mk_rolls_left > 0 and (get_current_dk_power() >= client.dk_consumption or getattr(client, 'mk_bypass_power_check', False)):
                    await process_mk_rolls(client, channel, current_cycle_id)
                    await asyncio.sleep(2)
                    return  # [FIX] Return to main loop for next iteration (no recursion)
            
            if immediate_roll:
                await check_rolls_left_tu(client, channel, mudae_prefix, log_function, preset_name,
                                          tu_message_content, 
                                          (client.current_min_kakera_for_roll_claim == 0),
                                          (client.key_mode and not client.rt_available and not client.claim_right_available),
                                          current_cycle_id)
            elif client.rolling_enabled and proceed_to_rolls:
                # Decide best sleep target using a prioritized candidate list to avoid "Dead Zones"
                sleep_choices = []
                
                # 1. Personal claim cooldown
                if wait_time > 0:
                    sleep_choices.append((float(wait_time), "claim cooldown"))
                
                # 2. Global claim reset (for timing window threshold entry at 60 mins)
                if client.time_rolls_to_claim_reset and claim_reset_minutes is not None and claim_reset_minutes > 60:
                    # Wake up right as we enter the window where "Timing" becomes possible
                    sleep_choices.append((float(claim_reset_minutes - 60), "timing threshold arrival"))
                
                # 2.5 Panic Roll window arrival
                if is_lurking and claim_reset_minutes is not None:
                    sleep_choices.append((float(claim_reset_minutes - client.panic_roll_minutes), "panic roll window arrival"))
                
                # 3. $rt reset
                if rt_reset_minutes is not None and rt_reset_minutes > 0:
                    sleep_choices.append((float(rt_reset_minutes), "$rt reset"))
                    
                # 4. Roll reset
                if roll_reset_minutes is not None and roll_reset_minutes > 0:
                    sleep_choices.append((float(roll_reset_minutes), "rolls replenishment"))

                if sleep_choices:
                    # Sort by wait time and pick the smallest logical event
                    sleep_choices.sort(key=lambda x: x[0])
                    best_sleep_wait, sleep_reason = sleep_choices[0]
                    # Ensure we don't sleep for too little or too much (clamped between 0.5 and the choice)
                    best_sleep_wait = max(0.5, best_sleep_wait)
                    await humanized_wait_and_proceed(client, channel, best_sleep_wait, sleep_reason)
                else:
                    # Default safety sleep if no timers could be parsed
                    await humanized_wait_and_proceed(client, channel, 30, "default status cycle")
                
                return  # [FIX] Return to main loop for next iteration (no recursion)
            else:
                return

        finally:
            client.is_processing_cycle = False

    async def check_rolls_left_tu(client, channel, mudae_prefix, log_function, preset_name,
                                  tu_message_content_for_rolls, ignore_limit_for_post_roll, key_mode_only_kakera_for_post_roll, current_cycle_id):
        content_lower = tu_message_content_for_rolls.lower()
        rolls_left = 0
        us_rolls_left = 0
        reset_time_r = 0
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        
        def parse_int_from_fragment(fragment: str) -> int:
            digits = re.sub(r"[^\d]", "", fragment or "")
            return int(digits) if digits else 0

        # Regex for rolls (singular/plural support for all languages)
        # Unified Regex: "You have/Vous avez/Tienes/Você tem" ... (count) ... "rolls"
        # Captures: 1=count, 2=middle_text
        main_match = re.search(r"(?:you have|vous avez|tienes|você tem)\s+\*{0,2}([\d,.]+)\*{0,2}\s+rolls?(.*?)(?:left|restantes?|restants?\b)", content_lower, re.DOTALL)
        
        if main_match:
            rolls_left = parse_int_from_fragment(main_match.group(1))
            middle_text = main_match.group(2)
            debug_log(f"Parsed base rolls: {rolls_left}. Middle text: '{middle_text.strip()[:100]}'")
            
            # Separate $us and $mk parsing.
            # $us are actual rolls we can use. $mk summon guaranteed kakera characters.
            for bonus_match in re.finditer(r"\(\+\*{0,2}([\d,.]+)\*{0,2}\s+\$(us|mk)\)", middle_text):
                amount = parse_int_from_fragment(bonus_match.group(1))
                bonus_type = bonus_match.group(2).lower()
                
                if bonus_type == "us":
                    us_rolls_left += amount
                    debug_log(f"Parsed $us bonus: +{amount} rolls")
                elif bonus_type == "mk":
                    client.mk_rolls_left = amount
                    debug_log(f"Parsed $mk bonus: +{amount} rolls")

            # Parse reset time
            # Unified Reset Regex: "Reset in... X min"
            # Matches: reset ... in/em/en/dans ... (Hh) Mm min
            match_reset = re.search(r"(?:reset|reinicialização|reinicio).*?(?:in|em|en|dans)\s+(?:.*?)\*{0,2}(\d+h)?\*{0,2}\s*\*{0,2}(\d+)\*{0,2}\s*min", content_lower[main_match.end():])
            
            if match_reset:
                h_r = parse_int_from_fragment(match_reset.group(1))
                m_r = parse_int_from_fragment(match_reset.group(2))
                reset_time_r = h_r * 60 + m_r
                debug_log(f"Parsed Roll Reset Time: {h_r}h {m_r}m ({reset_time_r} total min)")
                # Align to the next minute boundary (:00)
                new_roll_reset_utc = (now_utc + datetime.timedelta(minutes=reset_time_r)).replace(second=0, microsecond=0)
                
                # Detect new reset cycle to reset US pulled track
                if getattr(client, 'roll_reset_at_utc', None):
                    if (new_roll_reset_utc - client.roll_reset_at_utc).total_seconds() > 600:
                        client.us_pulled_this_cycle = 0
                        client.us_failed_this_cycle = False
                
                client.roll_reset_at_utc = new_roll_reset_utc
            else:
                reset_time_r = 60 # Default safe fallback
                client.roll_reset_at_utc = (now_utc + datetime.timedelta(minutes=reset_time_r)).replace(second=0, microsecond=0)
                debug_log(f"WARN: Roll reset regex failed. Using fallback: {reset_time_r}m")
            
            # Only add $us to total. Ignoring $mk fixes the 0+1 loop bug.
            total_rolls = rolls_left + us_rolls_left

            if total_rolls == 0:
                # Inactive hours gate (shared by both $rolls and $us)
                if is_inactive_hour():
                    wait_s = seconds_until_active()
                    if client.humanization_enabled:
                        wait_s += random.uniform(0, max(0.0, client.humanization_window_minutes * 60))
                    log_function(f"[{client.muda_name}] Sleeping until active period (Auto rolls interrupted).", preset_name, "RESET")
                    await asyncio.sleep(wait_s)
                    return # Break execution flow

                rolls_did_execute = False

                # AUTO $ROLLS LOGIC (1st Priority)
                if getattr(client, 'auto_rolls_enabled', False):
                    rolls_limit_ok = client.auto_rolls_limit == 0 or client.rolls_item_used_count < client.auto_rolls_limit
                    
                    if client.rolls_used_this_interval_utc is not None and hasattr(client, 'roll_reset_at_utc'):
                        if client.rolls_used_this_interval_utc != client.roll_reset_at_utc:
                            client.rolls_used_this_interval_utc = None
                    
                    not_used_this_interval = client.rolls_used_this_interval_utc is None
                    claim_ok = client.claim_right_available or (client.key_mode and client.auto_rolls_in_key_mode)
                    
                    if rolls_limit_ok and not_used_this_interval and claim_ok:
                        rolls_did_execute = True
                        log_function(f"[{client.muda_name}] Auto $rolls triggered.", preset_name, "INFO")
                        rolls_cmd_ch = _get_command_channel() or channel
                        await rolls_cmd_ch.send(f"{client.mudae_prefix}rolls")
                        client.rolls_item_used_count += 1
                        client.rolls_used_this_interval_utc = getattr(client, 'roll_reset_at_utc', None)
                        
                        limit_str = str(client.auto_rolls_limit) if client.auto_rolls_limit > 0 else '∞'
                        log_function(f"[{client.muda_name}] $rolls used ({client.rolls_item_used_count}/{limit_str}). Refreshing status...", preset_name, "INFO")
                        
                        await asyncio.sleep(2.0 + random.uniform(0.1, 0.5))
                        return  # [FIX] Return to main loop for next iteration (no recursion)

                # AUTO $US LOGIC (2nd Priority — only if $rolls did NOT execute)
                if not rolls_did_execute and getattr(client, 'auto_us_enabled', False):
                    stop_due_to_claim = client.auto_us_stop_on_claim and not client.claim_right_available
                    hit_limit = client.auto_us_limit > 0 and client.us_pulled_this_cycle >= client.auto_us_limit
                    us_failed_previously = getattr(client, 'us_failed_this_cycle', False)
                    
                    if not stop_due_to_claim and not hit_limit and not us_failed_previously:
                        last_attempt = getattr(client, 'last_us_attempt_utc', None)
                        if last_attempt and (now_utc - last_attempt).total_seconds() < 15:
                            # We just attempted $us and still have 0 rolls (possibly limits or unknown error).
                            client.us_failed_this_cycle = True
                            log_function(f"[{client.muda_name}] Auto $us failed repeatedly. Halting $us for this cycle.", preset_name, "WARN")
                            
                            # Fallback if rolls_left > 0
                            if rolls_left > 0:
                                log_function(f"[{client.muda_name}] Falling back to standard rolls ({rolls_left} rolls left).", preset_name, "INFO")
                                await start_roll_commands(client, channel, rolls_left, ignore_limit_for_post_roll, key_mode_only_kakera_for_post_roll, current_cycle_id)
                                return
                        else:
                            amount_to_pull = client.auto_us_limit - client.us_pulled_this_cycle if client.auto_us_limit > 0 else 20
                            amount_to_pull = max(0, amount_to_pull)
                            
                            if amount_to_pull > 0:
                                chunks = [20] * (amount_to_pull // 20) + ([amount_to_pull % 20] if amount_to_pull % 20 > 0 else [])
                                total_pulled_rolls = 0
                                
                                for chunk in chunks:
                                    await channel.send(f"{client.mudae_prefix}us {chunk}")
                                    client.last_us_attempt_utc = datetime.datetime.now(datetime.timezone.utc)
                                    
                                    # Humanized delay
                                    await asyncio.sleep(random.uniform(1.5, 2.5))
                                    
                                    # Check for failure
                                    chunk_failed = False
                                    async for msg in channel.history(limit=5):
                                        if msg.author.id == TARGET_BOT_ID and not msg.embeds:
                                            c_msg_lower = msg.content.lower()
                                            if "kakera" in c_msg_lower and ("enough" in c_msg_lower or "pas assez" in c_msg_lower or "insuficiente" in c_msg_lower):
                                                chunk_failed = True
                                                break
                                                
                                    if chunk_failed:
                                        client.us_failed_this_cycle = True
                                        log_function(f"[{client.muda_name}] Auto $us bulk pull failed (Not enough Kakera). Halting bulk pull.", preset_name, "WARN")
                                        break
                                    else:
                                        total_pulled_rolls += chunk
                                        client.us_pulled_this_cycle += chunk
                                        
                                if total_pulled_rolls > 0:
                                    limit_str = str(client.auto_us_limit) if client.auto_us_limit > 0 else '∞'
                                    log_function(f"[{client.muda_name}] Auto $us bulk pull completed. Pulled {total_pulled_rolls} rolls. ({client.us_pulled_this_cycle}/{limit_str})", preset_name, "INFO")
                                    await start_roll_commands(client, channel, total_pulled_rolls, ignore_limit_for_post_roll, key_mode_only_kakera_for_post_roll, current_cycle_id)
                                    return
                                elif rolls_left > 0:
                                    log_function(f"[{client.muda_name}] Auto $us failed. Falling back to standard rolls ({rolls_left} rolls left).", preset_name, "INFO")
                                    await start_roll_commands(client, channel, rolls_left, ignore_limit_for_post_roll, key_mode_only_kakera_for_post_roll, current_cycle_id)
                                    return
                            elif rolls_left > 0:
                                log_function(f"[{client.muda_name}] Falling back to standard rolls ({rolls_left} rolls left).", preset_name, "INFO")
                                await start_roll_commands(client, channel, rolls_left, ignore_limit_for_post_roll, key_mode_only_kakera_for_post_roll, current_cycle_id)
                                return
                    else:
                        # Fallback if rolls_left > 0
                        if rolls_left > 0:
                            log_function(f"[{client.muda_name}] $us unavailable (limit/exhausted/stopped). Falling back to standard rolls ({rolls_left} rolls left).", preset_name, "INFO")
                            await start_roll_commands(client, channel, rolls_left, ignore_limit_for_post_roll, key_mode_only_kakera_for_post_roll, current_cycle_id)
                            return

                # Reset time for rolls is known, but we should also check if we need to wake up for claim/timing
                # Parse claim reset again from local context to be safe
                sleep_candidates = [(float(reset_time_r if reset_time_r > 0 else 60), "rolls reset")]
                
                # Check claim reset and timing window awareness
                # Reuse the regex strategy from check_status for localized parsing
                match_c = re.search(r"(?:next claim|próximo|siguiente|prochain|tempo|temps|falta)\s+(?:reset|reclamo|tempo|temps|um tempo).*?(?:in|em|en|dans|left|restante|restant|falta|dentro de)\s*:?\s*\*{0,2}(\d+h)?\s*(\d+)\*{0,2}\s*min", content_lower, re.IGNORECASE)
                # [FIX] Reject if it matched a $daily/$dk/$rt line
                if match_c and any(kw in match_c.group(0) for kw in ["$daily", "$dk", "$rt"]):
                    match_c = None
                # [FIX] Portuguese fallback: "falta um tempo...casar novamente"
                if not match_c:
                    match_c = re.search(r"falta\s+um\s+tempo.*?(?:casar|remarier|claim|reclamar).*?\*{0,2}(\d+h)?\s*(\d+)\*{0,2}\s*min", content_lower, re.IGNORECASE)
                if match_c:
                    hours = parse_int_from_fragment(match_c.group(1))
                    minutes = parse_int_from_fragment(match_c.group(2))
                    c_min = hours * 60 + minutes
                    if c_min > 0:
                        sleep_candidates.append((float(c_min), "claim reset"))
                        if client.time_rolls_to_claim_reset and c_min > 60:
                            sleep_candidates.append((float(c_min - 60), "timing window arrival"))
                        if client.claim_right_available and c_min > client.panic_roll_minutes:
                            sleep_candidates.append((float(c_min - client.panic_roll_minutes), "panic roll arrival"))
                
                sleep_candidates.sort(key=lambda x: x[0])
                wait_m, reason = sleep_candidates[0]
                
                await humanized_wait_and_proceed(client, channel, wait_m, reason)
                return  # [FIX] Return to main loop for next iteration (no recursion)
            else:
                log_detail = f" (+{us_rolls_left} $us)" if us_rolls_left > 0 else ""
                log_function(f"[{client.muda_name}] Rolls: {total_rolls}{log_detail}. Reset: {reset_time_r}m", preset_name, "INFO")
                await start_roll_commands(client, channel, total_rolls, ignore_limit_for_post_roll, key_mode_only_kakera_for_post_roll, current_cycle_id)
                return
        else:
            log_function(f"[{client.muda_name}] Could not parse roll count.", preset_name, "ERROR")
            await asyncio.sleep(30)
            return  # [FIX] Return to main loop for next iteration (no recursion)

    async def process_mk_rolls(client, channel, current_cycle_id):
        if not getattr(client, 'auto_mk_enabled', True):
            return
        if client.mk_rolls_left > 0:
            current_pow = get_current_dk_power()
            if current_pow >= client.dk_consumption or getattr(client, 'mk_bypass_power_check', False):
                mk_used = 0
                while client.mk_rolls_left > 0 and (get_current_dk_power() >= client.dk_consumption or getattr(client, 'mk_bypass_power_check', False)):
                    log_function(f"[{client.muda_name}] Using $mk ({client.mk_rolls_left} left, Power: {get_current_dk_power()}%)", client.preset_name, "KAKERA")
                    await channel.send(f"{client.mudae_prefix}mk")
                    client.mk_rolls_left -= 1
                    mk_used += 1
                    await asyncio.sleep(3)  # Wait for Mudae to respond with character + kakera
                    
                    # Find and click the kakera on the $mk response
                    mk_start = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=5)
                    async for mk_msg in channel.history(limit=5, after=mk_start, oldest_first=False):
                        if mk_msg.author.id == TARGET_BOT_ID and mk_msg.embeds:
                            mk_embed = mk_msg.embeds[0]
                            if is_character_embed(mk_embed) and mk_msg.components:
                                await claim_character(client, channel, mk_msg, is_kakera=True, is_mk_roll=True)
                                break
                    await asyncio.sleep(1)
                
                if mk_used > 0:
                    log_function(f"[{client.muda_name}] Used {mk_used} $mk rolls.", client.preset_name, "KAKERA")
            else:
                log_function(f"[{client.muda_name}] Skipping $mk: Insufficient power ({current_pow}% < {client.dk_consumption}%).", client.preset_name, "INFO")

    async def start_roll_commands(client, channel, rolls_left, ignore_limit_for_post_roll, key_mode_only_kakera_for_post_roll, current_cycle_id):
        # [NEW] Feature 1: End-Game Kakera Farming (Pre-Roll Phase)
        if client.farm_character_enabled and client.farm_character and client.claim_right_available:
            log_function(f"[{client.muda_name}] Kakera Farm: Preparing {client.farm_character} for rolling.", client.preset_name, "INFO")
            await channel.send(f"{client.mudae_prefix}forcedivorce {client.farm_character}")
            await asyncio.sleep(1.5 + random.uniform(0.1, 0.4))
            await channel.send("y")
            await asyncio.sleep(1.5 + random.uniform(0.1, 0.4))

        # Auto $mk: Use $mk rolls before normal rolls if we have enough power
        await process_mk_rolls(client, channel, current_cycle_id)
        
        log_text = f"Rolling {rolls_left} times"
        log_text += " (Reactive)" if client.enable_reactive_self_snipe else ""
        log_function(f"[{client.muda_name}] {log_text}", client.preset_name, "INFO")
        
        # Timing Logic: If not ready to claim and timing is enabled, wait until just before claim reset
        # If reset is soon (<= 60 mins), we time it even if RT/KeyMode is available (per user request)
        reset_soon = False
        if client.next_claim_reset_at_utc:
            diff = (client.next_claim_reset_at_utc - datetime.datetime.now(datetime.timezone.utc)).total_seconds()
            if 0 < diff <= 60 * 60:
                reset_soon = True

        is_timing_mode_active = False
        if client.time_rolls_to_claim_reset and not client.claim_right_available and (reset_soon or (not client.rt_available and not client.key_mode)):
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            if client.next_claim_reset_at_utc and client.next_claim_reset_at_utc > now_utc:
                # [NEW] Feature 3: Slash Command Safety Limiter (min 2.0s for slash)
                actual_speed = max(2.0, client.roll_speed) if client.use_slash_rolls else client.roll_speed
                # [NEW] Feature 4: Micro-Randomization
                actual_speed += random.uniform(0.05, 0.25)
                
                total_duration = rolls_left * actual_speed
                
                # Aim for the last roll to finish ~1s AFTER reset.
                # This way claim happens after reset → we use normal claim (not RT) with fresh claim right.
                # Formula: start_time = reset + offset - total_duration
                # offset = 1 second after reset (minimizes new interval roll waste)
                target_start_time = client.next_claim_reset_at_utc + datetime.timedelta(seconds=1) - datetime.timedelta(seconds=total_duration)
                
                wait_seconds = (target_start_time - now_utc).total_seconds()
                
                # Safety: Don't wait past roll reset (ensure we finish before roll reset)
                if client.roll_reset_at_utc:
                    max_wait = (client.roll_reset_at_utc - now_utc).total_seconds() - total_duration - 5
                    wait_seconds = min(wait_seconds, max_wait)

                if wait_seconds > 2:
                    log_function(f"[{client.muda_name}] Timing rolls to finish after reset. Waiting {wait_seconds/60:.1f}m.", preset_name, "RESET")
                    await asyncio.sleep(wait_seconds)
                    is_timing_mode_active = True

        start_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=0.5)
        client.is_actively_rolling = True
        client.interrupt_rolling = False
        
        for i in range(rolls_left):
            if client.interrupt_rolling:
                break
            try:
                await send_roll_command(channel, roll_command)
                # [NEW] Feature 3 & 4: Slash Safety + Micro-Randomization
                roll_delay = (max(2.0, client.roll_speed) if client.use_slash_rolls else client.roll_speed) + random.uniform(0.05, 0.25)
                await asyncio.sleep(roll_delay)
            except Exception:
                await asyncio.sleep(1.0 + random.uniform(0.1, 0.3))
                
        client.is_actively_rolling = False
        await asyncio.sleep(5) # Let messages populate
        
        # If timing mode was active, claim reset has now happened. Update state for normal claim flow.
        if is_timing_mode_active:
            client.claim_right_available = True
            log_function(f"[{client.muda_name}] Reset passed. Claim is now available.", preset_name, "CLAIM")
        
        mudae_messages_to_process = []
        try:
            async for msg in channel.history(limit=(rolls_left*2 + 10), after=start_time, oldest_first=False):
                if msg.author.id == TARGET_BOT_ID and msg.embeds:
                    mudae_messages_to_process.append(msg)
            
            mudae_messages_to_process.reverse()
            if mudae_messages_to_process:
                 # In timing mode, use normal claim flow (not key_mode_only) since claim is now available
                 await handle_mudae_messages(client, channel, mudae_messages_to_process, ignore_limit_for_post_roll, False if is_timing_mode_active else key_mode_only_kakera_for_post_roll)
        except Exception as e:
            log_function(f"[{client.muda_name}] Post-roll processing error: {e}", preset_name, "ERROR")
        
        await asyncio.sleep(3)
        # [FIX] No recursion — return to main loop for next iteration
        return


    async def execute_auto_divorce(client, channel, char_name):
        """
        Auto-Divorce Interaction Flow (Language & Text Agnostic).
        Uses bold (**) markers for validation instead of hardcoded language strings.
        
        Step 1: Send $divorce {char_name}
        Step 2: Wait for Mudae confirmation prompt (contains **char_name** and y/n)
        Step 3: Send 'y' to confirm
        Step 4: Validate final response (contains both **char_name** and **bot_name**)
        """
        try:
            # Step 1: Send divorce command
            await asyncio.sleep(random.uniform(1.5, 2.5))
            await channel.send(f"{client.mudae_prefix}divorce {char_name}")
            log_function(f"[{client.muda_name}] Auto-Divorce: Initiating divorce for {char_name}...", client.preset_name, "INFO")

            # Step 2: Wait for Mudae's confirmation prompt
            await asyncio.sleep(random.uniform(1.5, 2.5))
            char_tag_lower = f"**{char_name.lower()}**"
            confirmation_found = False

            async for msg in channel.history(limit=8):
                if msg.author.id != TARGET_BOT_ID or not msg.content:
                    continue
                content_lower = msg.content.lower()
                # Validate: contains **char_name** AND a y/n or yes/no prompt
                if char_tag_lower in content_lower and ("(y/n" in content_lower or "yes/no" in content_lower or "(y /" in content_lower):
                    confirmation_found = True
                    break

            if not confirmation_found:
                log_function(f"[{client.muda_name}] Auto-Divorce: No confirmation prompt found for {char_name}. Aborting.", client.preset_name, "WARN")
                return False

            # Step 3: Send 'y' to confirm
            await asyncio.sleep(random.uniform(1.5, 2.5))
            await channel.send("y")

            # Step 4: Wait for final confirmation
            await asyncio.sleep(random.uniform(1.5, 2.5))
            bot_username_lower = client.user.name.lower()
            bot_display_lower = (client.user.display_name or client.user.name).lower()
            success = False
            kakera_earned = None

            async for msg in channel.history(limit=8):
                if msg.author.id != TARGET_BOT_ID or not msg.content:
                    continue
                content_lower = msg.content.lower()
                # Success validation: contains both **char_name** and **bot_name**
                has_char = char_tag_lower in content_lower
                has_bot = f"**{bot_username_lower}**" in content_lower or f"**{bot_display_lower}**" in content_lower
                if has_char and has_bot:
                    success = True
                    # Try to parse kakera earned from the message (e.g. "+50<:kakera:")
                    kakera_match = re.search(r"\+(\d+)\s*<:kakera:", msg.content)
                    if kakera_match:
                        kakera_earned = int(kakera_match.group(1))
                    break

            if success:
                kakera_str = f" (+{kakera_earned} kakera)" if kakera_earned else ""
                log_function(f"[{client.muda_name}] Auto-Divorce: Successfully divorced {char_name}{kakera_str}", client.preset_name, "KAKERA")
                return True
            else:
                log_function(f"[{client.muda_name}] Auto-Divorce: Could not confirm divorce for {char_name}. Check manually.", client.preset_name, "WARN")
                return False

        except Exception as e:
            log_function(f"[{client.muda_name}] Auto-Divorce: Error during divorce of {char_name}: {e}", client.preset_name, "ERROR")
            return False

    async def verify_snipe_outcome(client, channel, char_name, is_snipe_action=True, character_kakera=0, character_series=""):
        """
        Outcome Verifier:
        Checks the last few messages from Mudae to see who actually got the character.
        Language-agnostic: Searches for both the bot's user/display name AND the character name
        wrapped in bold tags (**), which is the universal format for marriage messages.
        """
        await asyncio.sleep(2.0 + random.uniform(0.2, 0.6)) # Wait for message to appear
        
        found_our_marriage = False
        winner_name = None
        
        log_label = "Snipe Verification" if is_snipe_action else "Claim Verification"
        bot_username = client.user.name.lower()
        bot_display_name = (client.user.display_name or client.user.name).lower()
        char_tag = f"**{char_name.lower()}**"
        
        debug_log(f"Verify: Searching for char_name='{char_name.lower()}' by bot='{bot_username}' / '{bot_display_name}'")
        
        scanned_messages_raw = []  # Collect for debug dump on failure
        
        # Scan recent history
        async for msg in channel.history(limit=8):
            if msg.author.id != TARGET_BOT_ID or not msg.content:
                continue
            
            content_lower = msg.content.lower()
            scanned_messages_raw.append(msg.content[:200])  # Store for debug
            
            # Strict Check: Mudae marriage messages across ALL languages use double asterisks for names
            if char_tag in content_lower:
                # Extract all bolded segments
                bold_segments = re.findall(r"\*\*(.+?)\*\*", content_lower)
                debug_log(f"Verify: Found char_tag in message. Bold segments: {bold_segments}")
                
                # Check if any bolded segment matches our bot's names
                for segment in bold_segments:
                    s_val = segment.lower()
                    if s_val == bot_username or s_val == bot_display_name:
                        found_our_marriage = True
                        break
                    elif s_val != char_name.lower():
                        winner_name = segment # Keep track of who won if it wasn't us
            
            # Fallback Check: Custom claims as hyperlinks may lack ** formatting
            if not found_our_marriage and not winner_name:
                if char_name.lower() in content_lower:
                    if bot_username in content_lower or bot_display_name in content_lower:
                        found_our_marriage = True
                    else:
                        winner_name = "Someone else (Custom Claim)"
            
            # Stop scanning once we find the relevant marriage message for this character
            if found_our_marriage or winner_name:
                break
        
        if found_our_marriage:
            log_function(f"[{client.muda_name}] {log_label}: SUCCESS! We got {char_name}.", client.preset_name, "CLAIM")

            # --- AUTO-DIVORCE EVALUATION ---
            # If enabled, check if the claimed character meets divorce conditions
            if client.auto_divorce_enabled:
                should_divorce = False
                divorce_reason = ""
                
                # Condition 1: Kakera value is at or below threshold
                if character_kakera > 0 and character_kakera <= client.auto_divorce_max_kakera:
                    should_divorce = True
                    divorce_reason = f"kakera {character_kakera} <= {client.auto_divorce_max_kakera}"
                
                # Condition 2: Character series matches divorce list
                if not should_divorce and character_series and client.auto_divorce_series:
                    series_lower = character_series.lower()
                    if any(s.lower() in series_lower for s in client.auto_divorce_series):
                        should_divorce = True
                        divorce_reason = f"series match in '{character_series[:60]}'"
                
                if should_divorce:
                    log_function(f"[{client.muda_name}] Auto-Divorce: {char_name} qualifies ({divorce_reason}). Initiating divorce.", client.preset_name, "INFO")
                    await execute_auto_divorce(client, channel, char_name)
            # Update State LOCALLY (No $tu needed)
            client.claim_right_available = False
            client.last_successfully_claimed_character = char_name.lower()
            
            # REFINED MINUTE-LOCK LOGIC:
            # Calculate next reset relative to the PAST reset point to maintain exact minute precision.
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            interval_delta = datetime.timedelta(minutes=client.claim_interval)
            
            if client.next_claim_reset_at_utc:
                base_reset = client.next_claim_reset_at_utc
                while base_reset <= now_utc:
                    base_reset += interval_delta
                
                client.next_claim_reset_at_utc = base_reset.replace(second=0, microsecond=0)
                log_function(f"[{client.muda_name}] Claim used. Next reset synced to {client.next_claim_reset_at_utc.strftime('%H:%M')} (Minute-Locked)", client.preset_name, "INFO")
            else:
                client.next_claim_reset_at_utc = (now_utc + interval_delta).replace(second=0, microsecond=0)
                log_function(f"[{client.muda_name}] Next claim reset set to {client.next_claim_reset_at_utc.strftime('%H:%M')} (Local Est.)", client.preset_name, "INFO")

            # --- AUTO $RT AFTER CLAIM ---
            # Sends $rt immediately after a successful claim to regain claim right.
            # Exclusions:
            #   1. Feature must be enabled
            #   2. Skip if the normal claim reset is less than 60 minutes away ("last hour")
            #   3. Skip if the bot has 0 rolls left or has finished its rolling sequence
            if client.auto_rt_after_claim:
                # Exclusion 2: "Last hour" check — don't waste $rt if claim resets soon naturally
                minutes_to_reset = None
                if client.next_claim_reset_at_utc:
                    minutes_to_reset = (client.next_claim_reset_at_utc - now_utc).total_seconds() / 60.0

                if minutes_to_reset is not None and minutes_to_reset < 60:
                    log_function(f"[{client.muda_name}] Auto $rt: SKIPPED — Claim resets in {minutes_to_reset:.0f}m (< 60m, not worth using $rt).", client.preset_name, "INFO")
                # Exclusion 3: Skip if rolling is finished (0 rolls left or no longer actively rolling)
                elif not client.is_actively_rolling:
                    log_function(f"[{client.muda_name}] Auto $rt: SKIPPED — Rolling sequence finished (no rolls left).", client.preset_name, "INFO")
                else:
                    # All conditions met — send $rt
                    log_function(f"[{client.muda_name}] Auto $rt: Sending $rt to regain claim right after claiming {char_name}.", client.preset_name, "CLAIM")
                    try:
                        await channel.send(f"{client.mudae_prefix}rt")
                        # $rt has been consumed; update local state
                        client.rt_available = False
                        # After $rt succeeds, claim right is restored
                        client.claim_right_available = True
                        log_function(f"[{client.muda_name}] Auto $rt: Claim right restored. Continuing to roll.", client.preset_name, "CLAIM")
                    except Exception as e:
                        log_function(f"[{client.muda_name}] Auto $rt: Failed to send $rt — {e}", client.preset_name, "ERROR")

            # [NEW] Feature 1: End-Game Kakera Farming (Post-Claim Phase / RT Loop)
            if client.farm_character_enabled and char_name.lower() == client.farm_character:
                if client.rt_available:
                    log_function(f"[{client.muda_name}] Kakera Farm: Resetting {char_name} for next roll.", client.preset_name, "KAKERA")
                    await channel.send(f"{client.mudae_prefix}rt")
                    client.rt_available = False
                    await asyncio.sleep(1.5 + random.uniform(0.1, 0.4))
                    await channel.send(f"{client.mudae_prefix}forcedivorce {client.farm_character}")
                    await asyncio.sleep(1.5 + random.uniform(0.1, 0.4))
                    await channel.send("y")
                    await asyncio.sleep(1.5 + random.uniform(0.1, 0.4))
                    # Reset claim right locally as RT was used
                    client.claim_right_available = True

            # --- SNIPE CHAT REACTION ---
            # After a successful external snipe, send a random chat message to look human.
            # Only triggers on external snipes (is_snipe_action=True), not self-rolls.
            if is_snipe_action and client.enable_snipe_chat_reactions and client.snipe_chat_messages:
                try:
                    reaction_delay = random.uniform(2.0, 5.0)
                    await asyncio.sleep(reaction_delay)
                    chosen_message = random.choice(client.snipe_chat_messages)
                    await channel.send(chosen_message)
                    log_function(f"[{client.muda_name}] Sent snipe chat reaction: {chosen_message}", client.preset_name, "INFO")
                except Exception as e:
                    log_function(f"[{client.muda_name}] Snipe chat reaction failed: {e}", client.preset_name, "ERROR")
        elif winner_name:
            log_function(f"[{client.muda_name}] {log_label}: FAILED. Taken by {winner_name}.", client.preset_name, "WARN")
            debug_log(f"Verify FAILED: '{char_name}' was taken by '{winner_name}'.")
        else:
            log_function(f"[{client.muda_name}] {log_label}: Inconclusive. Assuming failure or no marriage message.", client.preset_name, "WARN")
            # Dump scanned messages for diagnosis
            if client.debug_mode:
                debug_log(f"Verify INCONCLUSIVE: Scanned {len(scanned_messages_raw)} Mudae messages but char_tag '{char_tag}' not found.")
                for idx, raw_text in enumerate(scanned_messages_raw):
                    debug_log(f"  Scanned msg [{idx}]: {raw_text}")



    async def handle_mudae_messages(client, channel, mudae_messages, ignore_limit_param, key_mode_only_kakera_param):
        kakera_claims = []
        char_claims_post = []
        wl_claims_post = []
        min_kak_post = 0 if ignore_limit_param else client.min_kakera
        
        debug_log(f"Processing {len(mudae_messages)} Mudae messages. min_kakera_threshold={min_kak_post}, ignore_limit={ignore_limit_param}, key_only_kakera={key_mode_only_kakera_param}")
        
        # Track attempted character names in this burst to prevent duplicate claims (e.g. via $rt)
        attempted_char_names = set()

        for msg in mudae_messages:
            if not msg.embeds: continue
            embed = msg.embeds[0]
            if not is_character_embed(embed): continue
            
            all_kakera_emojis = client.kakera_emojis + client.chaos_emojis + client.sphere_emojis
            is_kakera = False
            if msg.components:
                for c in msg.components:
                    for b in c.children:
                        if hasattr(b.emoji, 'name') and b.emoji.name:
                            name = b.emoji.name
                            if name in all_kakera_emojis or name.rstrip('2') in all_kakera_emojis:
                                is_kakera = True
                                break
                    if is_kakera: break
            
            if is_kakera:
                kakera_claims.append(msg)
            else:
                if is_free_event(embed) or has_claim_option(msg, embed, client.claim_emojis):
                    char_n = embed.author.name.lower()
                    desc = embed.description or ""
                    
                    # Detect "Free" event cards (Christmas, New Year, etc.)
                    # These should be claimed regardless of claim availability 
                    if is_free_event(embed):
                        print_log(f"Detected free event card: {char_n}", client.preset_name, "CLAIM")
                        await claim_character(client, channel, msg, is_free_claim=True)
                        continue

                    k_v = 0
                    match_k = re.search(r"\**([\d,.]+)\**<:kakera:", desc)
                    if match_k:
                        k_v = int(re.sub(r"[^\d]", "", match_k.group(1)))
                    
                    series = desc.splitlines()[0].lower() if desc else ""
                    
                    is_avoided = char_n in client.avoid_list
                    
                    # Check if character is on wishlist OR Mudae indicates we wished for it
                    is_wl = (char_n in client.wishlist) or \
                            (client.series_snipe_mode and any(s in series for s in client.series_wishlist)) or \
                            is_wished_by_self(msg, client.user.id)
                    
                    # --- DEBUG: Per-character evaluation trace ---
                    if client.debug_mode:
                        if is_avoided:
                            action = "Skipped (Avoid List)"
                        elif is_wl:
                            action = "Targeted for Claim (Wishlist)"
                        elif k_v >= min_kak_post:
                            action = f"Targeted for Claim (Kakera {k_v} >= {min_kak_post})"
                        else:
                            action = f"Skipped (Below Min Kakera: {k_v} < {min_kak_post})"
                        debug_log(f"Eval: {char_n} | Kakera: {k_v} | Series: {series[:60]} | Wishlist: {is_wl} | Avoided: {is_avoided} | Action: {action}")
                    
                    if is_wl and not is_avoided:
                        wl_claims_post.append((msg, char_n, k_v))
                    elif k_v >= min_kak_post and not is_avoided:
                        char_claims_post.append((msg, char_n, k_v))

        # Kakera first
        for msg_k in kakera_claims:
            await claim_character(client, channel, msg_k, is_kakera=True)
            await asyncio.sleep(0.3)
        
        # Claims
        msg_claimed_id = -1
        
        # Key Mode Kakera-Only: If key_mode is ON but no claim/RT available, skip all character claims
        if key_mode_only_kakera_param or is_key_mode_kakera_only():
            log_function(f"[{client.muda_name}] Key mode active, no claim/RT. Skipping character claims (kakera only).", preset_name, "INFO")
        elif is_character_snipe_allowed(is_external_snipe=False):
            # 1. Primary Claim (uses claim_right_available, respects ignore_limit_param)
            if client.claim_right_available:
                if wl_claims_post:
                    wl_claims_post.sort(key=lambda x: (x[2], x[0].id), reverse=True)
                    msg_c, n, v = wl_claims_post[0]
                    if await claim_character(client, channel, msg_c, is_kakera=False, kakera_value=v):
                        msg_claimed_id = msg_c.id
                        attempted_char_names.add(n.lower())
                elif char_claims_post:
                    char_claims_post.sort(key=lambda x: (x[2], x[0].id), reverse=True)
                    msg_c, n, v = char_claims_post[0]
                    if await claim_character(client, channel, msg_c, is_kakera=False, kakera_value=v):
                        msg_claimed_id = msg_c.id
                        attempted_char_names.add(n.lower())
            
            # 2. Key Mode Claim (if no claim right and no RT available, use keys but strictly respect min_kakera)
            elif client.key_mode and not client.rt_available:
                valid_char_claims = [x for x in char_claims_post if x[2] >= client.min_kakera]
                if wl_claims_post:
                    wl_claims_post.sort(key=lambda x: (x[2], x[0].id), reverse=True)
                    msg_c, n, v = wl_claims_post[0]
                    if await claim_character(client, channel, msg_c, is_kakera=False, kakera_value=v):
                        msg_claimed_id = msg_c.id
                        attempted_char_names.add(n.lower())
                elif valid_char_claims:
                    valid_char_claims.sort(key=lambda x: (x[2], x[0].id), reverse=True)
                    msg_c, n, v = valid_char_claims[0]
                    if await claim_character(client, channel, msg_c, is_kakera=False, kakera_value=v):
                        msg_claimed_id = msg_c.id
                        attempted_char_names.add(n.lower())
        
        # 3. RT Claim (Strictly respects min_kakera / wishlist)
        if client.rt_available and not is_key_mode_kakera_only():
            rt_targets = []
            for msg, n, v in (wl_claims_post + char_claims_post):
                # Skip if claimed natively in this specific loop batch
                if msg.id == msg_claimed_id:
                    continue
                
                # Prevent RT on characters we already clicked/claimed (e.g., from reactive self-snipe)
                if msg.id in client.processed_claim_messages:
                    continue
                
                if n.lower() == getattr(client, 'last_successfully_claimed_character', ''):
                    continue
                
                # Verify wishlist status locally since list merging loses the context
                desc = msg.embeds[0].description or ""
                series = desc.splitlines()[0].lower() if desc else ""
                is_wl_rt = (n in client.wishlist) or \
                           (client.series_snipe_mode and any(s in series for s in client.series_wishlist)) or \
                           is_wished_by_self(msg, client.user.id)
                           
                bypass_min = is_wl_rt and client.rt_ignore_min_kakera_for_wishlist
                
                # RT strictly ignores the temporary "last hour" min kakera bypass (min_kak_post).
                # It relies on the original client.min_kakera, unless it's a wishlist target with bypass.
                if bypass_min or v >= client.min_kakera:
                    rt_targets.append((msg, n, v, is_wl_rt))
            
            rt_targets.sort(key=lambda x: (x[2], x[0].id), reverse=True)
            
            for msg_rt, n_rt, v_rt, is_wl_rt in rt_targets:
                if n_rt.lower() in attempted_char_names:
                    continue
                    
                log_function(f"[{client.muda_name}] Attempting RT on {n_rt} ({v_rt})", preset_name, "CLAIM")
                try:
                    await channel.send(f"{client.mudae_prefix}rt")
                    client.rt_available = False
                    attempted_char_names.add(n_rt.lower())
                    await asyncio.sleep(0.7)
                    await claim_character(client, channel, msg_rt, is_rt_claim=True, kakera_value=v_rt)
                    break # Only 1 RT allowed per cycle
                except Exception:
                    pass


    async def claim_character(client, channel, msg, is_kakera=False, is_rt_claim=False, is_snipe=False, is_free_claim=False, kakera_value=None, is_mk_roll=False):
        if not msg or not msg.embeds: return False
        
        # Global deduplication: Never process the same message ID twice for claims/kakera
        if msg.id in client.processed_claim_messages:
            debug_log(f"Skipping msg {msg.id}: already in processed_claim_messages set.")
            return False

        embed = msg.embeds[0]
        char_author = embed.author.name if embed.author else None
        char_name = char_author if char_author else "Unknown"
        
        debug_log(f"claim_character called: '{char_name}' | kakera={is_kakera} rt={is_rt_claim} snipe={is_snipe} free={is_free_claim} mk={is_mk_roll} kv={kakera_value}")
        
        # Redundancy check: If we just successfully claimed this exact character, skip it
        # This prevents the bot from using RT on a character it already won via normal claim
        if not is_kakera and not is_free_claim and char_name.lower() == getattr(client, 'last_successfully_claimed_character', ''):
            debug_log(f"Skipping '{char_name}': matches last_successfully_claimed_character.")
            return False

        # Kakera value logging logic
        kakera_str = ""
        if not is_kakera and not is_free_claim:
            val = kakera_value
            if val is None:
                desc = embed.description or ""
                match_k = re.search(r"\**([\d,.]+)\**<:kakera:", desc)
                if match_k:
                    val = re.sub(r"[^\d]", "", match_k.group(1))
            
            if val is not None:
                kakera_str = f" ({val} ka)"
        
        # Authorization check
        # For snipe operations, check with is_external_snipe flag
        if not is_kakera and not is_rt_claim and not is_free_claim and not is_character_snipe_allowed(is_external_snipe=is_snipe):
            debug_log(f"Authorization DENIED for '{char_name}': claim_right={client.claim_right_available}, rt={client.rt_available}, key_mode={client.key_mode}, is_snipe={is_snipe}")
            return False

        # Add to processed set (with periodic cleanup)
        # This is marked AFTER authorization so that failed attempts (due to no claim right) 
        # can be re-evaluated later in the same cycle (e.g. after a claim reset or via RT).
        client.processed_claim_messages.add(msg.id)
        if len(client.processed_claim_messages) > 1000:
            client.processed_claim_messages.clear()

        # RT Handling: If we are claiming a character and have no claim right but RT is ready, use it now.
        # If rt_only_self_rolls is enabled and this is an external snipe, don't use RT.
        rt_blocked_for_snipe = is_snipe and client.rt_only_self_rolls
        if not is_kakera and not is_free_claim and not is_rt_claim:
            if not client.claim_right_available and client.rt_available and not rt_blocked_for_snipe:
                log_function(f"[{client.muda_name}] Using RT for {char_name}", client.preset_name, "CLAIM")
                try:
                    await channel.send(f"{client.mudae_prefix}rt")
                    client.rt_available = False
                    await asyncio.sleep(random.uniform(0.6, 1.0)) # Wait for Mudae to process RT
                except Exception as e:
                    log_function(f"[{client.muda_name}] RT Failed: {e}", client.preset_name, "ERROR")
                    return False

        # Humanized delay for free event claims (since competition is low/none)
        if is_free_claim:
            await asyncio.sleep(random.uniform(1.0, 2.5))

        # Kakera Claim Logic
        if is_kakera:
            # [NEW] Feature 2: $op Perk 5 (Maxed/Sphere) Kakera Filter
            if client.op_perk_5_only:
                desc = (embed.description or "").lower()
                has_sphere = any(f"sp" in line for line in desc.split()) or any(s.lower() in desc for s in client.sphere_emojis)
                
                # NEW FIX: Do not skip if a Purple Kakera (kakeraP) button is present on the message
                has_kakera_p = False
                if msg.components:
                    has_kakera_p = any(
                        hasattr(b.emoji, 'name') and b.emoji.name == 'kakeraP'
                        for c in msg.components for b in c.children
                    )
                
                # If there is no sphere AND no kakeraP button, then we abort
                if not has_sphere and not has_kakera_p:
                    return False

            # [NEW] MK Kakera Only gate: If mk_only is enabled and this is NOT a $mk roll,
            # completely skip all kakera buttons to save reaction power.
            # $mk rolls (is_mk_roll=True) always bypass this gate unconditionally.
            if client.mk_only and not is_mk_roll:
                return False

            chaos_count = count_chaos_keys(embed)
            # $mk rolls bypass the only_chaos check unconditionally
            if not is_mk_roll and not is_snipe and client.only_chaos and chaos_count == 0:
                # Still allow free kakera (kakeraP, spheres) even when only_chaos blocks normal reactions
                has_free = msg.components and any(
                    hasattr(b.emoji, 'name') and (b.emoji.name == 'kakeraP' or b.emoji.name in client.sphere_emojis)
                    for c in msg.components for b in c.children
                )
                if not has_free:
                    return False
            
            has_sphere_perk = "💎/2" in (embed.description or "")
            if is_snipe:
                target_list = client.kakera_emojis
            elif has_sphere_perk:
                target_list = client.sphere_perk_emojis
            elif chaos_count > 0:
                target_list = client.chaos_emojis
            else:
                target_list = client.kakera_emojis
            target_list = target_list + client.sphere_emojis

            cooldown_active = not is_kakera_reaction_allowed()
            clicked = False
            
            # Check for KakeraP or Spheres (always safe)
            has_p_or_sphere = msg.components and any(hasattr(b.emoji, 'name') and (b.emoji.name == 'kakeraP' or b.emoji.name in client.sphere_emojis) for c in msg.components for b in c.children)
            
            # Only abort early if cooldown is active AND there are no potential discounts/spheres
            if cooldown_active and not has_p_or_sphere and chaos_count == 0 and not has_sphere_perk:
                return False

            # Double Deduction Prevention: Check if we already reacted to this message
            if msg.id in client.kakera_reacted_messages:
                return False
            
            # Maintenance: Clean up tracking set if it gets too large
            if len(client.kakera_reacted_messages) > 2000:
                client.kakera_reacted_messages.clear()

            if msg.components:
                # Collect all valid buttons first
                all_raw_buttons = []
                for comp in msg.components:
                    for btn in comp.children:
                         if hasattr(btn.emoji, 'name') and btn.emoji.name:
                             emoji_name = btn.emoji.name
                             if emoji_name in target_list or emoji_name.rstrip('2') in target_list:
                                 all_raw_buttons.append(btn)

                # [NEW] Task 8: Dynamic priority map from configurable kakera_priority_order
                # Higher index in the list = higher priority. Spheres always get max priority.
                prio_map = {}
                priority_list = list(reversed(client.kakera_priority_order))
                for idx, kakera_name in enumerate(priority_list):
                    prio_map[kakera_name.strip()] = (idx + 1) * 10
                # Ensure Spheres are top priority (999) regardless of user config
                for s in client.sphere_emojis: prio_map[s] = 999
                # Ensure kakeraP is always top priority if not already
                if 'kakeraP' not in prio_map or prio_map['kakeraP'] < 999:
                    prio_map['kakeraP'] = 999
                
                # Sort descending by priority value
                all_raw_buttons.sort(key=lambda b: prio_map.get(b.emoji.name.rstrip('2') if hasattr(b.emoji, 'name') and b.emoji.name else "", 0), reverse=True)

                # Iterate through sorted buttons
                for btn in all_raw_buttons:
                    name = btn.emoji.name
                    
                    # only_chaos gate: When only_chaos allowed this message through because
                    # it has free kakera, restrict clicks to ONLY the free buttons.
                    if not is_snipe and client.only_chaos and chaos_count == 0:
                        if name != 'kakeraP' and name not in client.sphere_emojis:
                            continue
                    
                    # If this kakera is perfectly normal (no chaos, no perks) and we are on cooldown, skip it.
                    # Otherwise, rely on get_current_dk_power() < cost to block it.
                    if cooldown_active and name != 'kakeraP' and name not in client.sphere_emojis and chaos_count == 0 and not has_sphere_perk:
                        continue

                    # Exempt KakeraP and Spheres from power consumption logic
                    if name == 'kakeraP' or name in client.sphere_emojis:
                        cost = 0
                    else:
                        base_cost = client.dk_consumption
                        desc_text = embed.description or ""
                        has_sphere_perk = "💎/2" in desc_text
                        
                        calc_cost = base_cost
                        # [FIX] Task 2: Only apply chaos key discount if we are the roller (not sniping)
                        if chaos_count > 0 and not is_snipe:
                            calc_cost = int(calc_cost / 2)
                        if has_sphere_perk:
                            calc_cost = int(calc_cost / 2)
                        
                        cost = calc_cost
                    
                    # Check local power availability before clicking to avoid warnings
                    current_pow = get_current_dk_power()
                    if current_pow < cost:
                        name_display = btn.emoji.name if hasattr(btn.emoji, 'name') else 'Kakera'
                        debug_log(f"Skipped {name_display}: Power ({current_pow}%) < Cost ({cost}%)")
                        if not hasattr(client, 'last_power_warn') or (time.time() - getattr(client, 'last_power_warn', 0) > 60):
                            log_function(f"[{client.muda_name}] Insufficient Power ({current_pow}% < {cost}%). Skipping {name_display}.", client.preset_name, "WARN")
                            client.last_power_warn = time.time()
                        continue
                        
                    # Check custom power thresholds for specific kakera
                    # For example, if user sets kakeraY: 80, we only click if current power >= 80%
                    if cost > 0 and hasattr(client, 'kakera_power_thresholds') and client.kakera_power_thresholds:
                        base_name = name.rstrip('2')
                        
                        # Determine specific prefix for chaos
                        prefix = "chaos_" if chaos_count > 0 else ""
                        specific_name = f"{prefix}{base_name}" if prefix else base_name
                        
                        # Check specific first (e.g. chaos_kakeraY), then fallback to base (e.g. kakeraY), then raw name
                        threshold = client.kakera_power_thresholds.get(specific_name)
                        if threshold is None:
                            threshold = client.kakera_power_thresholds.get(base_name) or client.kakera_power_thresholds.get(name)
                            
                        if threshold is not None and current_pow < threshold:
                            debug_log(f"Skipped {specific_name}: Power ({current_pow}%) below custom threshold ({threshold}%)")
                            log_function(f"[{client.muda_name}] Power ({current_pow}%) below threshold ({threshold}%) for {specific_name}. Waiting for better kakera.", client.preset_name, "INFO")
                            continue

                    # --- DEBUG: Dump button component data before click (Ghost Click diagnostics) ---
                    if client.debug_mode:
                        btn_custom_id = getattr(btn, 'custom_id', 'N/A')
                        btn_emoji_name = getattr(btn.emoji, 'name', 'N/A') if hasattr(btn, 'emoji') else 'N/A'
                        btn_emoji_id = getattr(btn.emoji, 'id', 'N/A') if hasattr(btn, 'emoji') else 'N/A'
                        ws_ref = getattr(client, 'ws', None)
                        session_id_val = getattr(ws_ref, 'session_id', None) if ws_ref else None
                        debug_log(f"Kakera Click Pre-flight: custom_id={btn_custom_id} | emoji.name={btn_emoji_name} | emoji.id={btn_emoji_id} | session_id={session_id_val} | cost={cost}%")
                        if not session_id_val:
                            debug_log("WARN: session_id is None/stale before kakera click! Ghost click risk.")

                    try:
                        await btn.click()
                        # Debit power locally to prevent immediate subsequent spam
                        client.current_dk_power = max(0, get_current_dk_power() - cost)
                        client.kakera_reacted_messages.add(msg.id)
                        
                        log_function(f"[{client.muda_name}] Kakera clicked: {char_name} [{name}] (Pw: {client.current_dk_power}%)", client.preset_name, "KAKERA")
                        clicked = True
                        client._last_kakera_click_ts = time.time()  # Track for bonus roll detection
                        debug_log(f"Kakera click SUCCESS: {name} on '{char_name}' (msg_id={msg.id})")
                        await asyncio.sleep(0.5)
                    except discord.HTTPException as e:
                        debug_log(f"Kakera click HTTPException: status={getattr(e, 'status', '?')} code={getattr(e, 'code', '?')} text={getattr(e, 'text', str(e))[:200]}")
                        log_function(f"[{client.muda_name}] Kakera click failed (HTTP {getattr(e, 'status', '?')}): {getattr(e, 'text', str(e))[:100]}", client.preset_name, "ERROR")
                    except Exception as e:
                        debug_log(f"Kakera click EXCEPTION: {type(e).__name__}: {str(e)[:200]}")
            return clicked

        # Character Claim Logic
        clicked_claim = False
        if msg.components:
            for comp in msg.components:
                if clicked_claim: break
                for btn in comp.children:
                    # If it's a free claim, click ANY button. Otherwise, check for standard hearts.
                    has_emoji = hasattr(btn.emoji, 'name') and btn.emoji.name is not None
                    is_heart = has_emoji and btn.emoji.name in client.claim_emojis
                    
                    if is_free_claim or is_heart:
                        # --- DEBUG: Dump claim button data (Ghost Click diagnostics) ---
                        if client.debug_mode:
                            btn_custom_id = getattr(btn, 'custom_id', 'N/A')
                            btn_emoji_name = getattr(btn.emoji, 'name', 'N/A') if has_emoji else 'N/A'
                            btn_emoji_id = getattr(btn.emoji, 'id', 'N/A') if has_emoji else 'N/A'
                            ws_ref = getattr(client, 'ws', None)
                            session_id_val = getattr(ws_ref, 'session_id', None) if ws_ref else None
                            debug_log(f"Claim Click Pre-flight: custom_id={btn_custom_id} | emoji.name={btn_emoji_name} | emoji.id={btn_emoji_id} | session_id={session_id_val}")
                            if not session_id_val:
                                debug_log("CRITICAL: session_id is None/stale before claim click! High ghost click risk.")

                        # [NEW] Task 4: Retry mechanism for button clicks (up to 3 attempts)
                        claim_success = False
                        for attempt in range(3):
                            try:
                                await btn.click()
                                claim_success = True
                                debug_log(f"Claim click SUCCESS on attempt {attempt+1}/3 for '{char_name}' (msg_id={msg.id})")
                                break
                            except discord.HTTPException as e:
                                debug_log(f"Claim click HTTPException (attempt {attempt+1}/3): status={getattr(e, 'status', '?')} code={getattr(e, 'code', '?')} text={getattr(e, 'text', str(e))[:200]}")
                                if attempt < 2:
                                    log_function(f"[{client.muda_name}] Claim click failed (attempt {attempt+1}/3): {e}. Retrying...", client.preset_name, "WARN")
                                    await asyncio.sleep(0.5)
                                else:
                                    log_function(f"[{client.muda_name}] Claim click failed after 3 attempts: {e}", client.preset_name, "ERROR")
                            except Exception as e:
                                debug_log(f"Claim click EXCEPTION (attempt {attempt+1}/3): {type(e).__name__}: {str(e)[:200]}")
                                if attempt < 2:
                                    log_function(f"[{client.muda_name}] Claim click failed (attempt {attempt+1}/3): {e}. Retrying...", client.preset_name, "WARN")
                                    await asyncio.sleep(0.5)
                                else:
                                    log_function(f"[{client.muda_name}] Claim click failed after 3 attempts: {e}", client.preset_name, "ERROR")
                        
                        if claim_success:
                            log_type = "CLAIM" if not is_free_claim else "INFO"
                            log_function(f"[{client.muda_name}] Claiming {char_name}{kakera_str}", client.preset_name, log_type)
                            clicked_claim = True
                            
                            # Snipe Verification Logic (is_snipe tells us if it was external)
                            # If we clicked, we verify if we actually won
                            # For regular rolling (not snipes), is_snipe is False -> "Claim Verification"
                            # Pass kakera value and series for auto-divorce evaluation
                            _claim_kv = kakera_value if kakera_value else 0
                            _claim_series = ""
                            if embed and embed.description:
                                _claim_series = embed.description.splitlines()[0] if embed.description else ""
                            await verify_snipe_outcome(client, channel, char_name, is_snipe_action=is_snipe, character_kakera=_claim_kv, character_series=_claim_series)
                            return True
        
        # Reaction fallback
        if not clicked_claim and has_claim_option(msg, embed, client.claim_emojis):
            try:
                # [NEW] Task 5: Use randomized claim reaction emoji instead of hardcoded heart
                reaction_emoji = random.choice(client.randomized_claim_reactions)
                debug_log(f"Using reaction fallback for '{char_name}' with emoji: {reaction_emoji}")
                await msg.add_reaction(reaction_emoji)
                log_function(f"[{client.muda_name}] Claiming {char_name}{kakera_str} (Reaction: {reaction_emoji})", client.preset_name, "CLAIM")
                # Reaction fallback — pass kakera/series for auto-divorce
                _react_kv = kakera_value if kakera_value else 0
                _react_series = ""
                if embed and embed.description:
                    _react_series = embed.description.splitlines()[0] if embed.description else ""
                await verify_snipe_outcome(client, channel, char_name, is_snipe_action=is_snipe, character_kakera=_react_kv, character_series=_react_series)
                return True
            except Exception as e:
                debug_log(f"Reaction fallback FAILED for '{char_name}': {type(e).__name__}: {str(e)[:200]}")
                return False

        return False

    async def humanized_wait_and_proceed(client, channel, base_reset_minutes, reason="reset"):
        # Calculate random wait time
        min_wait = max(0.0, base_reset_minutes * 60)
        window = max(0.0, client.humanization_window_minutes * 60)
        
        # If no explicit reset time, fallback to default delay
        if min_wait <= 0:
            min_wait = max(client.delay_seconds + 60, 240)
            
        human_jitter = random.uniform(0, window) if client.humanization_enabled else 0
        wait_seconds = min_wait + human_jitter
        end_time = datetime.datetime.now() + datetime.timedelta(seconds=wait_seconds)
        
        debug_log(f"Sleep calc: Base wait: {min_wait:.1f}s ({base_reset_minutes:.1f}m), Human jitter: {human_jitter:.1f}s, Total sleep: {wait_seconds:.1f}s ({wait_seconds/60:.1f}m). Reason: [{reason}]")
        
        log_prefix = "Humanized " if client.humanization_enabled else ""
        log_function(f"[{client.muda_name}] {log_prefix}Waiting {wait_seconds/60:.1f}m ({reason}).", preset_name, "RESET")
        await asyncio.sleep(wait_seconds)

        # Inactive hours gate: sleep until active period resumes
        if is_inactive_hour():
            wait_s = seconds_until_active()
            if client.humanization_enabled:
                wait_s += random.uniform(0, max(0.0, client.humanization_window_minutes * 60))
            log_function(f"[{client.muda_name}] Inactive hours. Sleeping {wait_s/60:.0f}m until active.", preset_name, "RESET")
            await asyncio.sleep(wait_s)

        # Inactivity check (anti-detection)
        if client.humanization_enabled:
            while True:
                try:
                    last_msg = None
                    async for m in channel.history(limit=1): last_msg = m
                    
                    if not last_msg: break
                    
                    diff = (datetime.datetime.now(timezone.utc) - last_msg.created_at).total_seconds()
                    if diff >= client.humanization_inactivity_seconds:
                        break
                    else:
                        await asyncio.sleep(client.humanization_inactivity_seconds - diff + 0.5)
                except Exception:
                    break

    async def handle_birthday_candle(msg):
        await asyncio.sleep(random.uniform(0.5, 2.0))
        if msg.components:
            for comp in msg.components:
                for btn in comp.children:
                    if hasattr(btn.emoji, 'name') and btn.emoji.name == '🕯️':
                        try:
                            await btn.click()
                            
                            char_name = "Unknown"
                            if msg.embeds:
                                embed = msg.embeds[0]
                                if embed.author and embed.author.name:
                                    char_name = embed.author.name
                                    
                            log_function(f"[{client.muda_name}] 🕯️ Clicked candle for {char_name}", preset_name, "CLAIM")
                        except Exception:
                            pass
                        return

    @client.event
    async def on_message(message):
        # --- PAUSE GUARD: Ignore ALL messages while paused ---
        if client.is_paused:
            return

        # Filter for relevant messages
        if message.author.id != TARGET_BOT_ID or message.channel.id != client.target_channel_id:
            if client.rolling_enabled: await client.process_commands(message)
            return

        # [NEW] Task 3: Mudae Maintenance Auto-Pause detection
        if message.content and "Command under maintenance!" in message.content:
            maint_match = re.search(r"For (\d+) minutes", message.content)
            if maint_match:
                maint_minutes = int(maint_match.group(1))
                client.maintenance_until = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=maint_minutes)
                log_function(f"[{client.muda_name}] Mudae is under maintenance! Pausing all operations for {maint_minutes} minutes.", preset_name, "ERROR")
            else:
                # Fallback: pause for 10 minutes if we can't parse duration
                client.maintenance_until = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=10)
                log_function(f"[{client.muda_name}] Mudae is under maintenance! Pausing all operations for 10 minutes (fallback).", preset_name, "ERROR")
            return

        # [NEW] Task 3: Skip all processing if maintenance is active
        if is_maintenance_active():
            return

        # [FIX] Post-maintenance inactivity gate: wait for channel to go quiet before resuming
        # Mirrors the same inactivity check used in humanized_wait_and_proceed.
        if getattr(client, '_post_maintenance_inactivity_needed', False):
            if client.humanization_enabled and client.humanization_inactivity_seconds > 0:
                now_utc = datetime.datetime.now(datetime.timezone.utc)
                last_seen = getattr(client, '_post_maint_last_msg_utc', None)
                client._post_maint_last_msg_utc = now_utc

                if last_seen is None:
                    # First message after maintenance — start tracking, skip this one
                    return

                gap = (now_utc - last_seen).total_seconds()
                if gap < client.humanization_inactivity_seconds:
                    # Channel is still active, keep waiting silently
                    return

                # Channel has been quiet long enough — resume operations
                log_function(f"[{client.muda_name}] Post-maintenance: Channel inactive for {gap:.0f}s. Resuming operations.", preset_name, "INFO")

            # Clear the flag (either inactivity passed, or humanization is off)
            client._post_maintenance_inactivity_needed = False
            client._post_maint_last_msg_utc = None

        # --- BIRTHDAY EVENT CANDLE DETECTION ---
        if message.components:
            for comp in message.components:
                candle_found = False
                for btn in comp.children:
                    if hasattr(btn.emoji, 'name') and btn.emoji.name == '🕯️':
                        client.loop.create_task(handle_birthday_candle(message))
                        candle_found = True
                        break
                if candle_found:
                    break

        # Suppress all activity during inactive hours
        if is_inactive_hour():
            return

        # [NEW] Task 6: Main Account Wishlist Syncing (Alt Account Targeter)
        # If a roll comes from the main account OR Mudae flags a character as wished by
        # the main account, treat it as a high-priority claim — bypassing local wishlist.
        if client.main_account_id:
            # Safely convert main_account_id to int for mention comparison
            try:
                main_id_int = int(client.main_account_id)
            except (ValueError, TypeError):
                main_id_int = None

            if main_id_int is not None and message.embeds:
                embed_ma = message.embeds[0]
                if is_character_embed(embed_ma):
                    # Smart Sync: Only trigger when Mudae explicitly says "Wished by @MainAccount"
                    main_is_wished = is_wished_by_self(message, main_id_int)

                    if main_is_wished:
                        c_name_ma = embed_ma.author.name.lower() if embed_ma.author else ""
                        is_avoided_ma = c_name_ma in client.avoid_list

                        if not is_avoided_ma and has_claim_option(message, embed_ma, client.claim_emojis):
                            if is_character_snipe_allowed(is_external_snipe=True):
                                log_function(f"[{client.muda_name}] Main Account Sync (wished by Main): {c_name_ma}! Priority claiming.", preset_name, "CLAIM")
                                # Bypass standard snipe delays for main account syncing
                                await asyncio.sleep(0.1 + random.uniform(0.01, 0.05))
                                if await claim_character(client, message.channel, message, is_snipe=True):
                                    return

        # [NEW] Kakera Bonus Roll Detection
        # When the bot clicks certain kakera (e.g. KakeraC/Chaos), Mudae may grant extra rolls
        # as a plain text message. Detect and use them automatically.
        # Example: "<:kakeraC:ID> **+5 rolls** this hour."
        if message.content and not message.embeds and client.rolling_enabled:
            bonus_roll_match = re.search(r"\+\**(\d+)\**\s*rolls?", message.content, re.IGNORECASE)
            if bonus_roll_match:
                # Guard: Only act if WE recently clicked a kakera (within 10 seconds)
                # This prevents reacting to bonus messages from other users' kakera clicks
                now_ts = time.time()
                last_kakera_ts = getattr(client, '_last_kakera_click_ts', 0)
                if (now_ts - last_kakera_ts) <= 10:
                    bonus_count = int(bonus_roll_match.group(1))
                    log_function(f"[{client.muda_name}] Gained +{bonus_count} extra rolls from Kakera! Signaling main loop...", preset_name, "KAKERA")
                    
                    # [FIX] Signal the main loop via Event instead of spawning a duplicate check_status task
                    if client._immediate_check_event and not client.is_actively_rolling:
                        client._immediate_check_event.set()

        if not message.embeds: return
        embed = message.embeds[0]

        # Debug Mode: Log every character in real-time as it arrives
        if client.debug_mode and is_character_embed(embed):
            dbg_name = embed.author.name if embed.author else "Unknown"
            dbg_desc = embed.description or ""
            dbg_kv = 0
            dbg_k_match = re.search(r"\**([\d,.]+)\**<:kakera:", dbg_desc)
            if dbg_k_match:
                dbg_kv = int(re.sub(r"[^\d]", "", dbg_k_match.group(1)))
            dbg_series = dbg_desc.splitlines()[0] if dbg_desc else ""
            dbg_owner = get_character_owner(embed) or "unclaimed"
            dbg_has_buttons = bool(message.components)
            dbg_is_wl = dbg_name.lower() in client.wishlist or is_wished_by_self(message, client.user.id)
            dbg_is_avoided = dbg_name.lower() in client.avoid_list
            dbg_source = "own roll" if client.is_actively_rolling else "external"
            
            # Build action preview
            if dbg_is_avoided:
                dbg_action = "Skipped (Avoid List)"
            elif dbg_is_wl:
                dbg_action = "Targeted for Claim (Wishlist)"
            elif dbg_kv >= client.current_min_kakera_for_roll_claim:
                dbg_action = f"Targeted for Claim (Kakera {dbg_kv} >= {client.current_min_kakera_for_roll_claim})"
            else:
                dbg_action = f"Skipped (Below Min Kakera: {dbg_kv} < {client.current_min_kakera_for_roll_claim})"
            
            debug_log(f"Eval ({dbg_source}): {dbg_name} | Kakera: {dbg_kv} | Series: {dbg_series[:60]} | Wishlist: {dbg_is_wl} | Owner: {dbg_owner} | Buttons: {dbg_has_buttons} | Action: {dbg_action}")

        # Handle Kakera Drops (non-character messages)
        if not is_character_embed(embed):
            # Logic for sniping loose kakera if enabled
            if client.kakera_reaction_snipe_mode_active and message.id not in client.kakera_reaction_sniped_messages:
                 # Verify it's actually a drop via buttons
                all_k = client.kakera_emojis + client.chaos_emojis + client.sphere_emojis
                has_btn = False
                if message.components:
                    for c in message.components:
                        for b in c.children:
                            if hasattr(b.emoji, 'name') and b.emoji.name:
                                e_name = b.emoji.name
                                if e_name in all_k or e_name.rstrip('2') in all_k:
                                    has_btn = True; break
                        if has_btn: break
                
                if has_btn:
                    # Check owner targets
                    if client.kakera_reaction_snipe_targets:
                        owner = get_character_owner(embed)
                        if not owner or owner not in client.kakera_reaction_snipe_targets:
                            return

                    client.kakera_reaction_sniped_messages.add(message.id)
                    # [NEW] Feature 4: Micro-Randomization
                    await asyncio.sleep(client.kakera_reaction_snipe_delay_value + random.uniform(0.05, 0.25))
                    # Snipe flag is True here
                    await claim_character(client, message.channel, message, is_kakera=True, is_snipe=True)
            return

        # Handle Character Rolls
        
        # Key Limit Check
        if client.rolling_enabled and client.is_actively_rolling:
            desc = embed.description or ""
            if "limit of 1,000 keys" in desc or "limite de 1.000 chaves" in desc or "límite de 1.000 llaves" in desc:
                client.interrupt_rolling = True
                client.key_limit_hit = True
                log_function(f"[{client.muda_name}] Key Limit Hit. Pausing 1h.", preset_name, "ERROR")
                # [FIX] Wait 1 hour + human jitter, then signal main loop instead of calling check_status
                async def _key_limit_recovery():
                    await asyncio.sleep(3600 + random.randint(0, 600))
                    if client._immediate_check_event:
                        client._immediate_check_event.set()
                client.loop.create_task(_key_limit_recovery())
                return

        process = True
        
        # Self-snipe (Reactive)
        if client.rolling_enabled and client.enable_reactive_self_snipe and client.is_actively_rolling:
            c_name = embed.author.name.lower()
            desc = embed.description or ""
            series = desc.splitlines()[0].lower() if desc else ""
            k_val = 0
            m_k = re.search(r"\**([\d,.]+)\**<:kakera:", desc)
            if m_k: k_val = int(re.sub(r"[^\d]", "", m_k.group(1)))
            
            # Check if character is on wishlist OR Mudae indicates we wished for it
            is_wl = c_name in client.wishlist or \
                    (client.series_snipe_mode and any(s in series for s in client.series_wishlist)) or \
                    is_wished_by_self(message, client.user.id)
            is_val = client.kakera_snipe_mode_active and k_val >= client.kakera_snipe_threshold
            is_avoided = c_name in client.avoid_list
            
            if (is_wl or is_val) and not is_avoided and has_claim_option(message, embed, client.claim_emojis):
                # Skip reactive claim if key_mode is active but no claim/RT available
                if is_key_mode_kakera_only():
                    pass  # Will fall through to kakera handling below
                else:
                    # [FIX] Race Condition: Pre-emptively halt the rolling loop BEFORE
                    # calling claim_character. This is critical because claim_character
                    # may send $rt and sleep 0.6-1.0s waiting for Mudae to process it.
                    # Without this, the start_roll_commands loop fires the next $wa during
                    # that sleep, creating overlapping traffic that causes Mudae to reject
                    # the subsequent claim button click.
                    # 
                    # Setting interrupt_rolling = True here guarantees the rolling loop's
                    # next iteration sees the flag and breaks before sending another command,
                    # giving $rt + claim exclusive channel priority.
                    client.interrupt_rolling = True
                    log_function(f"[{client.muda_name}] Reactive Self-Snipe: Halting rolls for claim attempt on {c_name}", preset_name, "CLAIM")

                    # [NEW] Feature 4: Micro-Randomization
                    if client.reactive_snipe_delay > 0: await asyncio.sleep(client.reactive_snipe_delay + random.uniform(0.05, 0.25))
                    if await claim_character(client, message.channel, message, kakera_value=k_val):
                        process = False

        # Snipe other users
        if process and not client.is_actively_rolling:
            c_name = embed.author.name.lower()
            
            # External Kakera Snipe on Character Rolls
            if client.kakera_reaction_snipe_mode_active and message.id not in client.kakera_reaction_sniped_messages and process:
                 all_k = client.kakera_emojis + client.chaos_emojis + client.sphere_emojis
                 has_btn = False
                 if message.components:
                    for c in message.components:
                        for b in c.children:
                            if hasattr(b.emoji, 'name') and b.emoji.name:
                                e_name = b.emoji.name
                                if e_name in all_k or e_name.rstrip('2') in all_k:
                                    has_btn = True; break
                        if has_btn: break
                 if has_btn:
                    # Check owner
                    target_ok = True
                    if client.kakera_reaction_snipe_targets:
                        owner = get_character_owner(embed)
                        if not owner or owner not in client.kakera_reaction_snipe_targets:
                            target_ok = False
                    
                    if target_ok:
                        client.kakera_reaction_sniped_messages.add(message.id)
                        await asyncio.sleep(client.kakera_reaction_snipe_delay_value)
                        await claim_character(client, message.channel, message, is_kakera=True, is_snipe=True)
                        process = False
            
            # Series Snipe
            if client.series_snipe_mode and client.series_wishlist:
                desc = embed.description or ""
                series = desc.splitlines()[0].lower() if desc else ""
                is_avoided = c_name in client.avoid_list
                if any(s in series for s in client.series_wishlist) and not is_avoided and has_claim_option(message, embed, client.claim_emojis):
                    if is_key_mode_kakera_only():
                        pass  # Key mode kakera-only: skip character claims
                    elif not is_character_snipe_allowed(is_external_snipe=True):
                        pass  # Can't snipe without claim right/RT (when rt_only_self_rolls is on)
                    else:
                        # [NEW] Feature 4: Micro-Randomization
                        await asyncio.sleep(client.series_snipe_delay + random.uniform(0.05, 0.25))
                        if await claim_character(client, message.channel, message, is_snipe=True):
                             client.series_snipe_happened = True; process = False

            # Wishlist Snipe (includes "Wished by" detection from Mudae)
            is_on_wishlist = c_name in client.wishlist or is_wished_by_self(message, client.user.id)
            is_avoided = c_name in client.avoid_list
            if process and client.snipe_mode and is_on_wishlist and not is_avoided and has_claim_option(message, embed, client.claim_emojis):
                if is_key_mode_kakera_only():
                    pass  # Key mode kakera-only: skip character claims
                elif not is_character_snipe_allowed(is_external_snipe=True):
                    pass  # Can't snipe without claim right/RT (when rt_only_self_rolls is on)
                else:
                    # [NEW] Feature 4: Micro-Randomization
                    await asyncio.sleep(client.snipe_delay + random.uniform(0.05, 0.25))
                    if await claim_character(client, message.channel, message, is_snipe=True):
                        client.snipe_happened = True; process = False
            
            # Value Snipe
            if process and client.kakera_snipe_mode_active:
                desc = embed.description or ""
                k_val = 0
                m_k = re.search(r"\**([\d,.]+)\**<:kakera:", desc)
                if m_k: k_val = int(re.sub(r"[^\d]", "", m_k.group(1)))
                
                is_avoided = c_name in client.avoid_list
                if k_val >= client.kakera_snipe_threshold and not is_avoided and has_claim_option(message, embed, client.claim_emojis):
                    if is_key_mode_kakera_only():
                        pass  # Key mode kakera-only: skip character claims
                    elif not is_character_snipe_allowed(is_external_snipe=True):
                        pass  # Can't snipe without claim right/RT (when rt_only_self_rolls is on)
                    else:
                        # [NEW] Feature 4: Micro-Randomization
                        await asyncio.sleep(client.snipe_delay + random.uniform(0.05, 0.25))
                        if await claim_character(client, message.channel, message, is_snipe=True, kakera_value=k_val):
                            client.snipe_happened = True; process = False

            # Free Event Card Snipe (Regardless of mode)
            if process and is_free_event(embed):
                print_log(f"Sniping free event card: {c_name}", client.preset_name, "CLAIM")
                if await claim_character(client, message.channel, message, is_free_claim=True):
                    process = False

        # Reactive Kakera on own rolls (with humanized delay)
        if client.rolling_enabled and client.enable_reactive_self_snipe and client.is_actively_rolling and process:
            # Check if kakera button exists and value is high enough
            all_k = client.kakera_emojis + client.chaos_emojis + client.sphere_emojis
            has_btn = False
            if message.components:
                for c in message.components:
                    for b in c.children:
                        if hasattr(b.emoji, 'name') and b.emoji.name:
                            e_name = b.emoji.name
                            if e_name in all_k or e_name.rstrip('2') in all_k:
                                has_btn = True; break
                    if has_btn: break
            
            if has_btn:
                 # Apply humanized delay before clicking kakera on own rolls
                 delay_min, delay_max = client.reactive_kakera_delay_range
                 if delay_max > 0:
                     await asyncio.sleep(random.uniform(delay_min, delay_max))
                 await claim_character(client, message.channel, message, is_kakera=True)


    # Logic to handle the Discord client execution
    try:
        # log_handler=None prevents logging conflicts within threads on Windows
        # reconnect=True ensures the bot attempts to stay online during minor outages
        client.run(token, reconnect=True)
    except Exception as e:
        # This specific error happens on Windows when the bot runs in a sub-thread.
        # It's a signal handling limitation and doesn't affect Mudae functionality.
        if "set_wakeup_fd" in str(e):
            pass 
        else:
            log_function(f"[{BOT_NAME}] Crash: {e}", preset_name, "ERROR")
    finally:
        # Unregister client from global pause registry on shutdown
        with _active_clients_lock:
            if client in _active_clients:
                _active_clients.remove(client)

def bot_lifecycle_wrapper(preset_name, preset_data):
    # Auto-restart wrapper
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
                preset_data.get("claim_emojis", None),
                preset_data.get("kakera_emojis", None),
                preset_data.get("chaos_emojis", None),
                preset_data.get("sphere_perk_emojis", None),
                preset_data.get("rt_only_self_rolls", False),
                preset_data.get("reactive_kakera_delay_range", [0.3, 1.0]),
                preset_data.get("claim_interval", 180),
                preset_data.get("roll_interval", 60),
                preset_data.get("avoid_list", []),
                preset_data.get("inactive_hours", []),
                preset_data.get("auto_us_enabled", False),
                preset_data.get("auto_us_limit", 0),
                preset_data.get("auto_us_stop_on_claim", True),
                preset_data.get("kakera_power_thresholds", {}),
                preset_data.get("debug_mode", False),
                preset_data.get("auto_mk_enabled", True),
                preset_data.get("auto_rolls_enabled", False),
                preset_data.get("auto_rolls_limit", 0),
                preset_data.get("auto_rolls_in_key_mode", False),
                preset_data.get("panic_roll_minutes", 5),
                preset_data.get("lurker_mode", False),
                # [NEW] Task 1-8: New preset parameters with backwards-compatible defaults
                preset_data.get("max_dk_power", 100),
                preset_data.get("randomized_claim_reactions", None),
                preset_data.get("main_account_id", ""),
                preset_data.get("scheduled_roll_times", None),
                preset_data.get("kakera_priority_order", None),
                preset_data.get("auto_rt_after_claim", False),
                preset_data.get("mk_only", False),
                preset_data.get("auto_dk_enabled", True),
                preset_data.get("command_channel_id", ""),
                preset_data.get("enable_snipe_chat_reactions", False),
                preset_data.get("snipe_chat_messages", None),
                preset_data.get("farm_character", ""),
                preset_data.get("op_perk_5_only", False),
                preset_data.get("farm_character_enabled", False),
                preset_data.get("auto_divorce_enabled", False),
                preset_data.get("auto_divorce_max_kakera", 50),
                preset_data.get("auto_divorce_series", []),
                preset_data.get("mk_bypass_power_check", False),
                preset_data.get("auto_p_enabled", True)
            )
        except Exception as e:
            print_log(f"Instance crashed: {e}", preset_name, "ERROR")
        
        time.sleep(60)

def start_preset_thread(preset_name, preset_data):
    if not preset_data.get("token"): return None
    t = threading.Thread(target=bot_lifecycle_wrapper, args=(preset_name, preset_data), daemon=True)
    t.start()
    return t

def main_menu():
    # Lazy import: inquirer uses blessed.Terminal which crashes in windowed mode (no stdin)
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
    
    # [FIX] Bug 1: Suppress the keyboard listener while the interactive menu is active.
    # This prevents the background thread from stealing keystrokes meant for inquirer.
    _menu_active.set()
    
    threads = []
    while True:
        opts = ['Select and Run Preset', 'Select and Run Multiple', 'Exit']
        q = [inquirer.List('opt', message="Select Option", choices=opts)]
        ans = inquirer.prompt(q)
        
        if not ans or ans['opt'] == 'Exit': break
        
        if ans['opt'] == 'Select and Run Preset':
            p_ans = inquirer.prompt([inquirer.List('p', message="Preset", choices=list(presets.keys()))])
            if p_ans: threads.append(start_preset_thread(p_ans['p'], presets[p_ans['p']]))
            
        elif ans['opt'] == 'Select and Run Multiple':
            p_ans = inquirer.prompt([inquirer.Checkbox('p', message="Presets", choices=list(presets.keys()))])
            if p_ans: 
                for p in p_ans['p']: threads.append(start_preset_thread(p, presets[p]))
    
    # [FIX] Bug 1: Menu is done — re-enable the keyboard listener for pause toggle.
    # From this point on, inquirer is no longer using stdin, so the listener is safe.
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
    args = parse_args()
    
    if args.preset:
        if args.preset in presets:
            # FIX: Runs directly in main thread to avoid 'set_wakeup_fd' error
            bot_lifecycle_wrapper(args.preset, presets[args.preset])
        else:
            print(f"Preset '{args.preset}' not found.")
    elif args.all:
        started = []
        for p_name, p_data in presets.items():
            t = start_preset_thread(p_name, p_data)
            if t: started.append(t)
        # FIX: Ensure all threads are finished before closing
        for t in started: 
            if t: t.join()
    else:
        # Start the interactive menu
        main_menu()
        
        # FIX: Keep the main thread alive after menu selection so daemon threads don't die
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[MudaRemote] Shutting down...")