import sys
import asyncio
import discord
from discord.ext import commands
import re
import json
import threading
import datetime
import inquirer
import logging

# Global bot name
BOT_NAME = "MudaRemote"

# Load presets from JSON file
presets = {}
try:
    with open("presets.json", "r") as f:
        presets = json.load(f)
except FileNotFoundError:
    print("presets.json dosyası bulunamadı. Lütfen oluşturun ve gerekli bilgileri girin.")
    sys.exit(1)

# Target bot ID (Mudae's ID)
TARGET_BOT_ID = 432610292342587392

# Log list (Not used anymore, logs are directly written to file and console)
log_list = []

# ANSI color codes
COLORS = {
    "INFO": "\033[94m",    # Blue
    "CLAIM": "\033[92m",   # Green
    "KAKERA": "\033[93m",  # Yellow
    "ERROR": "\033[91m",    # Red
    "CHECK": "\033[95m",    # Magenta
    "RESET": "\033[36m",    # Cyan
    "ENDC": "\033[0m"      # End Color
}

# Define claim and kakera emojis at the top level
CLAIM_EMOJIS = ['💖', '💗', '💘', '❤️', '💓', '💕', '♥️', '🪐']
KAKERA_EMOJIS = ['kakeraY', 'kakeraO', 'kakeraR', 'kakeraW', 'kakeraL']


def color_log(message, preset_name, log_type="INFO"):
    color_code = COLORS.get(log_type.upper(), COLORS["INFO"])
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_message = f"[{timestamp}][{preset_name}] {message}"
    print(f"{color_code}{log_message}{COLORS['ENDC']}")
    return log_message

def write_log_to_file(log_message):
    try:
        with open("logs.txt", "a") as log_file:
            log_file.write(log_message + "\n")
    except Exception as e:
        print(f"Log dosyasına yazma hatası: {e}")

def print_log(message, preset_name, log_type="INFO"):
    log_message_formatted = color_log(message, preset_name, log_type)
    write_log_to_file(log_message_formatted)


def run_bot(token, prefix, target_channel_id, roll_command, min_kakera, delay_seconds, mudae_prefix,
            log_function, preset_name, key_mode, start_delay, snipe_mode, snipe_delay,
            snipe_ignore_min_kakera_reset, wishlist,
            series_snipe_mode, series_snipe_delay, series_wishlist, roll_speed): # ADD roll_speed parameter
    client = commands.Bot(command_prefix=prefix, chunk_guilds_at_startup=False)

    # Disable discord.py's default logging to console
    discord_logger = logging.getLogger('discord')
    discord_logger.propagate = False
    handlers = [handler for handler in discord_logger.handlers if isinstance(handler, logging.StreamHandler)]
    for handler in handlers:
        discord_logger.removeHandler(handler)

    # Store preset-specific settings in the client
    client.preset_name = preset_name
    client.min_kakera = min_kakera
    client.snipe_mode = snipe_mode
    client.snipe_delay = snipe_delay
    client.snipe_ignore_min_kakera_reset = snipe_ignore_min_kakera_reset
    client.wishlist = wishlist
    client.series_snipe_mode = series_snipe_mode
    client.series_snipe_delay = series_snipe_delay
    client.series_wishlist = series_wishlist
    client.muda_name = BOT_NAME
    client.claim_right_available = False
    client.target_channel_id = target_channel_id # Store target_channel_id in client!
    client.roll_speed = roll_speed # Store roll_speed in client!

    # Initialize sniping trackers
    client.sniped_messages = set()
    client.snipe_happened = False
    client.series_sniped_messages = set()
    client.series_snipe_happened = False

    @client.event
    async def on_ready():
        log_function(f"[{client.muda_name}] Bot is ready.", preset_name, "INFO")
        log_function(f"[{client.muda_name}] Delay: {delay_seconds} seconds", preset_name, "INFO")
        log_function(f"[{client.muda_name}] Start Delay: {start_delay} seconds", preset_name, "INFO")
        log_function(f"[{client.muda_name}] Key Mode: {'Enabled' if key_mode else 'Disabled'}", preset_name, "INFO")
        log_function(f"[{client.muda_name}] Snipe Mode: {'Enabled' if snipe_mode else 'Disabled'}", preset_name, "INFO")
        log_function(f"[{client.muda_name}] Series Snipe Mode: {'Enabled' if series_snipe_mode else 'Disabled'}", preset_name, "INFO")
        log_function(f"[{client.muda_name}] Roll Speed: {roll_speed} seconds", preset_name, "INFO") # Log roll speed
        await asyncio.sleep(start_delay)
        await asyncio.sleep(delay_seconds)
        channel = client.get_channel(target_channel_id)
        try:
            await channel.send(f"{mudae_prefix}limroul 1 1 1 1")
            await asyncio.sleep(0.5)
            await channel.send(f"{mudae_prefix}dk")
            await asyncio.sleep(0.5)
            await channel.send(f"{mudae_prefix}daily")
            await asyncio.sleep(0.5)
            await check_claim_rights(client, channel)
        except discord.errors.Forbidden as e:
            log_function(f"[{client.muda_name}] Hata: Kanala mesaj gönderemez iznim yok. {e}", preset_name, "ERROR")
            await client.close()

    async def check_claim_rights(client, channel):
        log_function(f"[{client.muda_name}] Checking claim rights...", preset_name, "CHECK")
        error_count = 0
        max_retries = 5
        while True:
            await channel.send(f"{mudae_prefix}mu")
            await asyncio.sleep(1)
            try:
                async for msg in channel.history(limit=2):
                    if msg.author.id == TARGET_BOT_ID:
                        if "right now" in msg.content.lower():
                            client.claim_right_available = True
                            match = re.search(r"The next claim reset is in \*\*(\d+h)?\s*(\d+)\*\* min\.", msg.content)
                            if match:
                                hours = int(match.group(1)[:-1]) if match.group(1) else 0
                                minutes = int(match.group(2))
                                remaining_seconds = (hours * 60 + minutes) * 60
                                if remaining_seconds <= 3600:
                                    if client.snipe_mode and client.snipe_ignore_min_kakera_reset:
                                        log_function(f"[{client.muda_name}] Claim right available (<1h) and snipe override active; ignoring min_kakera limit.", preset_name, "INFO")
                                        await check_rolls_left(client, channel, ignore_limit=True)
                                    else:
                                        log_function(f"[{client.muda_name}] Claim right available (<1h) but snipe override inactive; applying claim limit.", preset_name, "INFO")
                                        await check_rolls_left(client, channel, ignore_limit=False)
                                else:
                                    log_function(f"[{client.muda_name}] Claim right available (>1h remaining); applying claim limit.", preset_name, "INFO")
                                    await check_rolls_left(client, channel, ignore_limit=False)
                                return
                            else:
                                raise ValueError("Time information could not be parsed.")
                        elif "you can't claim" in msg.content.lower():
                            client.claim_right_available = False
                            match = re.search(r"you can't claim for another \*\*(\d+h)?\s*(\d+)\*\* min\.", msg.content)
                            if match:
                                hours = int(match.group(1)[:-1]) if match.group(1) else 0
                                minutes = int(match.group(2))
                                total_seconds = (hours * 60 + minutes) * 60
                                if key_mode:
                                    log_function(f"[{client.muda_name}] Claim right not available, but Key Mode is enabled. Rolling for kakera only.", preset_name, "INFO")
                                    await check_rolls_left(client, channel, ignore_limit=True, key_mode_only_kakera=True)
                                    return
                                else:
                                    log_function(f"[{client.muda_name}] Claim right not available. Will retry in {hours}h {minutes}min.", preset_name, "INFO")
                                    await wait_for_reset(total_seconds, delay_seconds, log_function, preset_name)
                                    await check_claim_rights(client, channel)
                                    return
                            else:
                                raise ValueError("Waiting time not found.")
                raise ValueError("Mudae message not found.")
            except ValueError as e:
                error_count += 1
                log_function(f"[{client.muda_name}] Error: {e}", preset_name, "ERROR")
                if error_count >= max_retries:
                    log_function(f"[{client.muda_name}] Max retries reached for claim rights. Retrying in 30 minutes.", preset_name, "ERROR")
                    await asyncio.sleep(1800)
                    error_count = 0
                else:
                    log_function(f"[{client.muda_name}] Claim right check failed. Retrying in 5 seconds.", preset_name, "ERROR")
                    await asyncio.sleep(5)
                continue
            except Exception as e:
                error_count += 1
                log_function(f"[{client.muda_name}] Error: {e}", preset_name, "ERROR")
                if error_count >= max_retries:
                    log_function(f"[{client.muda_name}] Max retries reached for claim rights. Retrying in 30 minutes.", preset_name, "ERROR")
                    await asyncio.sleep(1800)
                    error_count = 0
                else:
                    log_function(f"[{client.muda_name}] Claim right check failed. Retrying in 5 seconds.", preset_name, "ERROR")
                    await asyncio.sleep(5)
                continue

    async def check_rolls_left(client, channel, ignore_limit=False, key_mode_only_kakera=False):
        log_function(f"[{client.muda_name}] Checking rolls left...", preset_name, "CHECK")
        error_count = 0
        max_retries = 5
        while True:
            await channel.send(f"{mudae_prefix}ru")
            await asyncio.sleep(1)
            try:
                async for msg in channel.history(limit=5):
                    if msg.author.id == TARGET_BOT_ID and "roll" in msg.content.lower():
                        match = re.search(r"You have \*\*(\d+)\*\* roll(?:s)?(?: \+\*\*(\d+)\*\* \$(?:mk|us))? left\.", msg.content)
                        if not match:
                            match = re.search(r"You have (\d+) rolls? left\.", msg.content)
                        if match:
                            rolls_left = int(match.group(1))
                            reset_match = re.search(r"Next rolls? reset in \*\*(\d+)\*\* (min|h)", msg.content)
                            if reset_match:
                                reset_time = int(reset_match.group(1))
                                reset_unit = reset_match.group(2)
                                if reset_unit == "h":
                                    reset_time *= 60
                            else:
                                reset_time = 0
                                log_function(f"[{client.muda_name}] Warning: Could not parse roll reset time.", preset_name, "ERROR")
                            if rolls_left == 0:
                                log_function(f"[{client.muda_name}] No rolls left. Reset in {reset_time} min.", preset_name, "RESET")
                                await wait_for_rolls_reset(reset_time, delay_seconds, log_function, preset_name)
                                await check_claim_rights(client, channel)
                                return
                            else:
                                log_function(f"[{client.muda_name}] Rolls left: {rolls_left}", preset_name, "INFO")
                                await start_roll_commands(client, channel, rolls_left, ignore_limit, key_mode_only_kakera)
                                return
                        else:
                            log_function(f"[{client.muda_name}] Could not parse roll information: {msg.content}", preset_name, "ERROR")
                            raise ValueError(f"Could not parse roll information. Mudae's response was: {msg.content}")
                raise ValueError("Mudae did not respond with roll information within the time limit.")
            except ValueError as e:
                 error_count += 1
                 log_function(f"[{client.muda_name}] Error ({error_count}/{max_retries}): {e}", preset_name, "ERROR")
                 if error_count >= max_retries:
                     log_function(f"[{client.muda_name}] Max retries reached. Giving up on roll check. Retrying in 30 minutes.", preset_name, "ERROR")
                     await asyncio.sleep(1800)
                     error_count = 0
                 else:
                     await asyncio.sleep(5)
            except Exception as e:
                 error_count += 1
                 log_function(f"[{client.muda_name}] Unexpected error ({error_count}/{max_retries}): {e}", preset_name, "ERROR")
                 if error_count >= max_retries:
                     log_function(f"[{client.muda_name}] Max retries reached. Giving up on roll check. Retrying in 30 minutes.", preset_name, "ERROR")
                     await asyncio.sleep(1800)
                     error_count = 0
                 else:
                     await asyncio.sleep(5)

    async def start_roll_commands(client, channel, rolls_left, ignore_limit=False, key_mode_only_kakera=False):
        for _ in range(rolls_left):
            await channel.send(f"{mudae_prefix}{roll_command}")
            await asyncio.sleep(client.roll_speed) # Use roll_speed here
        await asyncio.sleep(4)
        await check_new_characters(client, channel)
        mudae_messages = []
        async for msg in channel.history(limit=rolls_left * 2, oldest_first=False):
            if msg.author.id == TARGET_BOT_ID:
                mudae_messages.append(msg)
        await handle_mudae_messages(client, channel, mudae_messages, ignore_limit, key_mode_only_kakera)
        await asyncio.sleep(2)
        if client.snipe_happened or client.series_snipe_happened:
            client.snipe_happened = False
            client.series_snipe_happened = False
            await asyncio.sleep(2) # Small delay before checking claim rights after snipe
            await check_claim_rights(client, channel) # Log claim rights after snipe
            return
        await check_claim_rights(client, channel)

    async def handle_mudae_messages(client, channel, mudae_messages, ignore_limit=False, key_mode_only_kakera=False):
        # Kakera claim logic - always execute regardless of claim rights
        for msg in mudae_messages:
            if msg.embeds:
                embed = msg.embeds[0]
                if msg.components:
                    for component in msg.components:
                        for button in component.children:
                            if button.emoji and button.emoji.name in KAKERA_EMOJIS:
                                try:
                                    await button.click()
                                    log_function(f"[{client.muda_name}] Claimed Kakera: {embed.author.name}", preset_name, "KAKERA")
                                    await asyncio.sleep(3)
                                except discord.errors.HTTPException as e:
                                    log_function(f"[{client.muda_name}] Kakera claim hatası: {e}", preset_name, "ERROR")

        if not client.claim_right_available and key_mode: # Key mode and no claim right logic
            highest_claim_character = None
            highest_claim_character_message = None
            for msg in mudae_messages:
                if msg.embeds:
                    embed = msg.embeds[0]
                    if embed.color.value in [16751916, 1360437]:
                        match = re.search(r"\*\*(\d+)\*\*<:kakera:", embed.description or "")
                        if match:
                            kakera_value = int(match.group(1))
                            if (not highest_claim_character or kakera_value > highest_claim_character) and (ignore_limit or kakera_value > client.min_kakera):
                                highest_claim_character = kakera_value
                                highest_claim_character_message = msg

            if highest_claim_character_message and highest_claim_character is not None and client.min_kakera is not None:
                if highest_claim_character > client.min_kakera:
                    await channel.send(f"{mudae_prefix}rt")
                    await asyncio.sleep(0.5)
                    await claim_character(client, channel, highest_claim_character_message, is_rt_claim=True)

        elif client.claim_right_available: # Normal claim logic when claim right is available (Key mode independent)
            highest_claim_character = None
            highest_claim_character_message = None
            second_highest_claim_character = None
            second_highest_claim_character_message = None

            for msg in mudae_messages:
                if msg.embeds:
                    embed = msg.embeds[0]
                    if embed.color.value in [16751916, 1360437]:
                        match = re.search(r"\*\*(\d+)\*\*<:kakera:", embed.description or "")
                        if match:
                            kakera_value = int(match.group(1))
                            if (not highest_claim_character or kakera_value > highest_claim_character) and (ignore_limit or kakera_value > client.min_kakera):
                                second_highest_claim_character = highest_claim_character
                                second_highest_claim_character_message = highest_claim_character_message
                                highest_claim_character = kakera_value
                                highest_claim_character_message = msg
                            elif (not second_highest_claim_character or kakera_value > second_highest_claim_character) and (ignore_limit or kakera_value > client.min_kakera):
                                second_highest_claim_character = kakera_value
                                second_highest_claim_character_message = msg

            if highest_claim_character_message:
                await claim_character(client, channel, highest_claim_character_message)
                if second_highest_claim_character_message and second_highest_claim_character is not None and client.min_kakera is not None:
                    if second_highest_claim_character > client.min_kakera:
                        await channel.send(f"{mudae_prefix}rt")
                        await asyncio.sleep(0.5)
                        await claim_character(client, channel, second_highest_claim_character_message, is_rt_claim=True)


    async def claim_character(client, channel, msg, is_kakera=False, is_rt_claim=False):
        log_message = "Claimed Kakera" if is_kakera else "Claimed Character"
        if is_rt_claim:
            log_message = "Claimed Character with $rt"
        log_type = "KAKERA" if is_kakera else "CLAIM" # Determine log type
        if msg.components:
            for component in msg.components:
                for button in component.children:
                    if button.emoji and button.emoji.name in (CLAIM_EMOJIS if not is_kakera else KAKERA_EMOJIS):
                        try:
                            await button.click()
                            log_function(f"[{client.muda_name}] {log_message}: {msg.embeds[0].author.name}", client.preset_name, log_type)
                            await asyncio.sleep(3)
                            return
                        except discord.errors.HTTPException as e:
                            log_function(f"[{client.muda_name}] Karakter claim hatası: {e}", client.preset_name, "ERROR")
        else:
            try:
                await msg.add_reaction("✅")
                log_function(f"[{client.muda_name}] {log_message}: {msg.embeds[0].author.name}", client.preset_name, log_type)
                await asyncio.sleep(3)
            except discord.errors.HTTPException:
                log_function(f"[{client.muda_name}] Reaksiyon eklenemedi. Muhtemelen karakter başkası tarafından çoktan alındı.", client.preset_name, "ERROR")

    async def check_new_characters(client, channel):
        async for msg in channel.history(limit=15):
            if msg.author.id == TARGET_BOT_ID:
                if msg.embeds:
                    embed = msg.embeds[0]
                    match = re.search(r"Claims: \#(\d+)", embed.description or "")
                    # if match: # Removed "New character" log
                    #     claims_value = int(match.group(1))
                    #     log_function(f"[{client.muda_name}] New character: {embed.author.name} (Claims: #{claims_value})", client.preset_name, "INFO") # Removed log
                    pass # Do nothing instead of logging new character

    async def wait_for_reset(seconds, delay_seconds, log_function, preset_name):
        now = datetime.datetime.now()
        target_time = now + datetime.timedelta(seconds=seconds)
        target_time = target_time.replace(second=0, microsecond=0)
        if target_time < now:
            target_time += datetime.timedelta(minutes=1)
        wait_seconds = (target_time - now).total_seconds() + delay_seconds
        log_function(f"[{client.muda_name}] Waiting for reset. Target time: {target_time.strftime('%H:%M:%S')}, additional delay: {delay_seconds} seconds", preset_name, "RESET")
        await asyncio.sleep(wait_seconds)

    async def wait_for_rolls_reset(reset_time_minutes, delay_seconds, log_function, preset_name):
        now = datetime.datetime.now()
        target_minute = (now.minute + reset_time_minutes) % 60
        target_time = now.replace(minute=target_minute, second=0, microsecond=0)
        if target_time < now:
            target_time += datetime.timedelta(hours=1)
        wait_seconds = (target_time - now).total_seconds() + delay_seconds
        log_function(f"[{client.muda_name}] Waiting for rolls reset. Target time: {target_time.strftime('%H:%M:%S')}, additional delay: {delay_seconds} seconds", preset_name, "RESET")
        await asyncio.sleep(wait_seconds)

    @client.event
    async def on_message(message):
        if message.author.id != TARGET_BOT_ID:
            await client.process_commands(message)
            return
        if message.embeds: # Check if embeds exist before accessing
            if not message.embeds: # Double check in case embed list is empty
                await client.process_commands(message)
                return
        else:
            await client.process_commands(message)
            return

        if not client.claim_right_available and not client.series_snipe_mode and not client.snipe_mode:
            await client.process_commands(message)
            return # If no claim right and no snipe mode, just process commands and return

        # --- Real-time SERIES SNIPING (Channel-Specific!) ---
        if client.series_snipe_mode and client.series_wishlist and message.channel.id == client.target_channel_id:
            embed = message.embeds[0]
            description = embed.description or ""
            if description:
                first_line = description.splitlines()[0]
                if any(kw and kw.lower() in first_line.lower() for kw in client.series_wishlist):
                    # CHECK FOR CLAIM EMOJIS IN SERIES SNIPE
                    if any(button.emoji and button.emoji.name in CLAIM_EMOJIS for comp in message.components for button in comp.children):
                        if message.id not in client.series_sniped_messages:
                            client.series_sniped_messages.add(message.id)
                            log_function(f"[{client.muda_name}] (Real-time) Series snipe candidate found: {first_line}", client.preset_name, "CLAIM") # Log as CLAIM
                            await asyncio.sleep(client.series_snipe_delay)
                            await claim_character(client, message.channel, message)
                            client.series_snipe_happened = True
                            await asyncio.sleep(2) # Small delay before checking claim rights after snipe
                            await check_claim_rights(client, message.channel) # Log claim rights after snipe
                            await client.process_commands(message)
                            return

        # --- Real-time NORMAL SNIPING (Channel-Specific!) ---
        if client.snipe_mode and client.wishlist and message.channel.id == client.target_channel_id:
            embed = message.embeds[0]
            character_name = None
            if embed.author and embed.author.name:
                character_name = embed.author.name
                if any(wish and wish.lower() in character_name.lower() for wish in client.wishlist):
                    # CHECK FOR CLAIM EMOJIS IN NORMAL SNIPE
                    if any(button.emoji and button.emoji.name in CLAIM_EMOJIS for comp in message.components for button in comp.children):
                        if message.id not in client.sniped_messages:
                            client.sniped_messages.add(message.id)
                            log_function(f"[{client.muda_name}] (Real-time) Snipe candidate found: {character_name}", client.preset_name, "CLAIM") # Log as CLAIM
                            await asyncio.sleep(client.snipe_delay)
                            await claim_character(client, message.channel, message)
                            client.snipe_happened = True
                            await asyncio.sleep(2) # Small delay before checking claim rights after snipe
                            await check_claim_rights(client, message.channel) # Log claim rights after snipe
                            await client.process_commands(message)
                            return
        await client.process_commands(message)


    client.run(token)


def show_banner():
    banner = r"""
  __  __ _    _ _____          _____  ______ __  __  ____ _______ ______
 |  \/  | |  | |  __ \   /\   |  __ \|  ____|  \/  |/ __ \__   __|  ____|
 | \  / | |  | | |  | | /  \  | |__) | |__  | \  / | |  | | | |  | |__
 | |\/| | |  | | |  | |/ /\ \ |  _  /|  __| | |\/| | |  | | | |  |  __|
 | |  | | |__| | |__| / ____ \| | \ \| |____| |  | | |__| | | |  | |____
 |_|  |_|\____/|_____/_/    \_\_|  \_\______|_|  |_|\____/  |_|  |______|


                                                                         """
    print("\033[1;36m" + banner + "\033[0m")
    print("\033[1;33mWelcome to MudaRemote - Your Remote Mudae Assistant\033[0m\n")

def main_menu():
    show_banner()
    while True:
        questions = [
            inquirer.List('option',
                          message="Please select an option:",
                          choices=[
                              'Select and Run Preset',
                              'Select and Run Multiple Presets',
                              'Exit'
                          ],
                          ),
        ]
        answers = inquirer.prompt(questions)
        if answers['option'] == 'Select and Run Preset':
            select_and_run_preset()
        elif answers['option'] == 'Select and Run Multiple Presets':
            select_and_run_multiple_presets()
        elif answers['option'] == 'Exit':
            print("\033[1;32mExiting MudaRemote. Goodbye!\033[0m")
            break

def select_and_run_preset():
    preset_list = list(presets.keys())
    if not preset_list:
        print("No presets found.")
        return
    questions = [
        inquirer.List('preset',
                      message="Select a preset to run:",
                      choices=preset_list,
                      ),
    ]
    answers = inquirer.prompt(questions)
    selected_preset = answers['preset']
    preset = presets[selected_preset]
    key_mode = preset.get("key_mode", False)
    start_delay = preset.get("start_delay", 0)
    snipe_mode = preset.get("snipe_mode", False)
    snipe_delay = preset.get("snipe_delay", 5)
    snipe_ignore_min_kakera_reset = preset.get("snipe_ignore_min_kakera_reset", False)
    wishlist = preset.get("wishlist", [])
    series_snipe_mode = preset.get("series_snipe_mode", False)
    series_snipe_delay = preset.get("series_snipe_delay", 5)
    series_wishlist = preset.get("series_wishlist", [])
    roll_speed = preset.get("roll_speed", 0.3) # ADD roll_speed retrieval, default to 0.3 if not present
    threading.Thread(target=run_bot, args=(
        preset["token"],
        preset["prefix"],
        preset["channel_id"],
        preset["roll_command"],
        preset["min_kakera"],
        preset["delay_seconds"],
        preset["mudae_prefix"],
        print_log,
        selected_preset,
        key_mode,
        start_delay,
        snipe_mode,
        snipe_delay,
        snipe_ignore_min_kakera_reset,
        wishlist,
        series_snipe_mode,
        series_snipe_delay,
        series_wishlist,
        roll_speed # ADD roll_speed to args
    )).start()

def select_and_run_multiple_presets():
    preset_list = list(presets.keys())
    if not preset_list:
        print("No presets found.")
        return
    questions = [
        inquirer.Checkbox('presets',
                          message="Select presets to run (Use spacebar to select, Enter to confirm):",
                          choices=preset_list,
                          ),
    ]
    answers = inquirer.prompt(questions)
    selected_presets = answers['presets']
    for preset_name in selected_presets:
        preset = presets[preset_name]
        key_mode = preset.get("key_mode", False)
        start_delay = preset.get("start_delay", 0)
        snipe_mode = preset.get("snipe_mode", False)
        snipe_delay = preset.get("snipe_delay", 5)
        snipe_ignore_min_kakera_reset = preset.get("snipe_ignore_min_kakera_reset", False)
        wishlist = preset.get("wishlist", [])
        series_snipe_mode = preset.get("series_snipe_mode", False)
        series_snipe_delay = preset.get("series_snipe_delay", 5)
        series_wishlist = preset.get("series_wishlist", [])
        roll_speed = preset.get("roll_speed", 0.3) # ADD roll_speed retrieval, default to 0.3 if not present
        threading.Thread(target=run_bot, args=(
            preset["token"],
            preset["prefix"],
            preset["channel_id"],
            preset["roll_command"],
            preset["min_kakera"],
            preset["delay_seconds"],
            preset["mudae_prefix"],
            print_log,
            preset_name,
            key_mode,
            start_delay,
            snipe_mode,
            snipe_delay,
            snipe_ignore_min_kakera_reset,
            wishlist,
            series_snipe_mode,
            series_snipe_delay,
            series_wishlist,
            roll_speed # ADD roll_speed to args
        )).start()

if __name__ == "__main__":
    main_menu()
