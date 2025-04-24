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
    print("presets.json file not found. Please create it and enter the necessary information.")
    sys.exit(1)
except json.JSONDecodeError:
    print("Error decoding presets.json. Please check the file format.")
    sys.exit(1)


# Target bot ID (Mudae's ID)
TARGET_BOT_ID = 432610292342587392

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
    """Formats a log message with timestamp, preset name, and color."""
    color_code = COLORS.get(log_type.upper(), COLORS["INFO"])
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_message = f"[{timestamp}][{preset_name}] {message}"
    print(f"{color_code}{log_message}{COLORS['ENDC']}")
    return log_message

def write_log_to_file(log_message):
    """Appends a log message to the logs.txt file."""
    try:
        # Ensure logs.txt exists, create if not
        with open("logs.txt", "a") as log_file:
            log_file.write(log_message + "\n")
    except Exception as e:
        # Fallback to print error to console if file writing fails
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"\033[91m[{timestamp}][System] Error writing to log file: {e}\033[0m")


def print_log(message, preset_name, log_type="INFO"):
    """Prints a colored log message to the console and writes it to the log file."""
    log_message_formatted = color_log(message, preset_name, log_type)
    write_log_to_file(log_message_formatted)


def run_bot(token, prefix, target_channel_id, roll_command, min_kakera, delay_seconds, mudae_prefix,
            log_function, preset_name, key_mode, start_delay, snipe_mode, snipe_delay,
            snipe_ignore_min_kakera_reset, wishlist,
            series_snipe_mode, series_snipe_delay, series_wishlist, roll_speed):
    """Sets up and runs a single bot instance based on preset settings."""

    intents = discord.Intents.default()
    intents.message_content = True # Explicitly enable message content intent
    intents.messages = True
    intents.guilds = True

    client = commands.Bot(command_prefix=prefix, intents=intents, chunk_guilds_at_startup=False)

    # Disable discord.py's default logging to console
    discord_logger = logging.getLogger('discord')
    discord_logger.propagate = False
    # Remove existing StreamHandlers if any
    handlers = [handler for handler in discord_logger.handlers if isinstance(handler, logging.StreamHandler)]
    for handler in handlers:
        discord_logger.removeHandler(handler)

    # Store preset-specific settings in the client
    client.preset_name = preset_name
    client.min_kakera = min_kakera
    client.snipe_mode = snipe_mode
    client.snipe_delay = snipe_delay
    client.snipe_ignore_min_kakera_reset = snipe_ignore_min_kakera_reset
    client.wishlist = [w.lower() for w in wishlist] # Store wishlist as lowercase
    client.series_snipe_mode = series_snipe_mode
    client.series_snipe_delay = series_snipe_delay
    client.series_wishlist = [sw.lower() for sw in series_wishlist] # Store series wishlist as lowercase
    client.muda_name = BOT_NAME # Use the global bot name
    client.claim_right_available = False
    client.target_channel_id = target_channel_id
    client.roll_speed = roll_speed
    client.mudae_prefix = mudae_prefix # Store mudae prefix
    client.key_mode = key_mode # Store key_mode status
    client.delay_seconds = delay_seconds # Store delay

    # Initialize sniping trackers
    client.sniped_messages = set()
    client.snipe_happened = False
    client.series_sniped_messages = set()
    client.series_snipe_happened = False

    @client.event
    async def on_ready():
        log_function(f"[{client.muda_name}] Bot is ready. User: {client.user}", preset_name, "INFO")
        log_function(f"[{client.muda_name}] Target Channel ID: {target_channel_id}", preset_name, "INFO")
        log_function(f"[{client.muda_name}] Delay: {delay_seconds} seconds", preset_name, "INFO")
        log_function(f"[{client.muda_name}] Start Delay: {start_delay} seconds", preset_name, "INFO")
        log_function(f"[{client.muda_name}] Key Mode: {'Enabled' if key_mode else 'Disabled'}", preset_name, "INFO")
        log_function(f"[{client.muda_name}] Snipe Mode: {'Enabled' if snipe_mode else 'Disabled'}", preset_name, "INFO")
        if snipe_mode:
            log_function(f"[{client.muda_name}] Snipe Delay: {snipe_delay}s", preset_name, "INFO")
            log_function(f"[{client.muda_name}] Snipe Wishlist Size: {len(client.wishlist)}", preset_name, "INFO")
            log_function(f"[{client.muda_name}] Snipe Ignore Min Kakera Reset: {snipe_ignore_min_kakera_reset}", preset_name, "INFO")
        log_function(f"[{client.muda_name}] Series Snipe Mode: {'Enabled' if series_snipe_mode else 'Disabled'}", preset_name, "INFO")
        if series_snipe_mode:
            log_function(f"[{client.muda_name}] Series Snipe Delay: {series_snipe_delay}s", preset_name, "INFO")
            log_function(f"[{client.muda_name}] Series Wishlist Size: {len(client.series_wishlist)}", preset_name, "INFO")
        log_function(f"[{client.muda_name}] Roll Speed: {roll_speed} seconds", preset_name, "INFO")
        log_function(f"[{client.muda_name}] Min Kakera Value: {client.min_kakera}", preset_name, "INFO")

        # Validate Channel Access
        channel = client.get_channel(target_channel_id)
        if not channel:
            log_function(f"[{client.muda_name}] Error: Cannot find channel with ID {target_channel_id}. Check the ID and bot's permissions.", preset_name, "ERROR")
            await client.close()
            return
        if not channel.permissions_for(channel.guild.me).send_messages:
            log_function(f"[{client.muda_name}] Error: Bot does not have permission to send messages in channel {channel.name} ({target_channel_id}).", preset_name, "ERROR")
            await client.close()
            return
        if not channel.permissions_for(channel.guild.me).read_message_history:
             log_function(f"[{client.muda_name}] Error: Bot does not have permission to read message history in channel {channel.name} ({target_channel_id}).", preset_name, "ERROR")
             await client.close()
             return
        if not channel.permissions_for(channel.guild.me).add_reactions:
            log_function(f"[{client.muda_name}] Warning: Bot does not have permission to add reactions in channel {channel.name} ({target_channel_id}). Reaction claim fallback might fail.", preset_name, "ERROR")
        if not channel.permissions_for(channel.guild.me).use_external_emojis:
             log_function(f"[{client.muda_name}] Warning: Bot may not have permission to use external emojis in {channel.name} ({target_channel_id}). Kakera claims might fail if they require custom emojis.", preset_name, "ERROR")

        log_function(f"[{client.muda_name}] Initial delay of {start_delay} seconds...", preset_name, "INFO")
        await asyncio.sleep(start_delay)

        try:
            log_function(f"[{client.muda_name}] Sending initial commands...", preset_name, "INFO")
            await channel.send(f"{client.mudae_prefix}limroul 1 1 1 1")
            await asyncio.sleep(1.5) # Slightly increased delay
            await channel.send(f"{client.mudae_prefix}dk")
            await asyncio.sleep(1.5)
            await channel.send(f"{client.mudae_prefix}daily")
            await asyncio.sleep(1.5)
            await check_status(client, channel, client.mudae_prefix) # Use combined status check
        except discord.errors.Forbidden as e:
            log_function(f"[{client.muda_name}] Error: Permission denied to send messages in the target channel. {e}", preset_name, "ERROR")
            await client.close()
        except Exception as e:
            log_function(f"[{client.muda_name}] Error during initial setup/commands: {e}", preset_name, "ERROR")
            await client.close()

    # --- MODIFIED check_status FUNCTION ---
    async def check_status(client, channel, mudae_prefix):
        """Checks claim rights and rolls using $tu and proceeds."""
        log_function(f"[{client.muda_name}] Checking claim rights and rolls using {mudae_prefix}tu...", preset_name, "CHECK")
        error_count = 0
        max_retries = 5
        while True:
            await channel.send(f"{mudae_prefix}tu")
            await asyncio.sleep(2) # Give Mudae time to respond
            try:
                # Look for Mudae's response in recent history
                async for msg in channel.history(limit=5): # Check 5 recent messages
                    # More robust check for Mudae's $tu response
                    if msg.author.id == TARGET_BOT_ID and \
                       ("rolls left" in msg.content.lower() or \
                        "you can't claim for another" in msg.content.lower() or \
                        "you __can__ claim" in msg.content.lower()):

                        content_lower = msg.content.lower()

                        # Try to parse rolls first, as it's usually present
                        rolls_left = -1 # Default to -1 if parsing fails
                        reset_time_minutes = -1 # Default to -1
                        match_rolls = re.search(r"you have \*\*(\d+)\*\* rolls?(?: \(.+?\))? left", content_lower)
                        if match_rolls:
                            rolls_left = int(match_rolls.group(1))
                            reset_match = re.search(r"next rolls? reset in \*\*(\d+)\*\* min", content_lower)
                            if reset_match:
                                reset_time_minutes = int(reset_match.group(1))
                            else:
                                log_function(f"[{client.muda_name}] Warning: Could not parse roll reset time from $tu.", preset_name, "ERROR")
                        else:
                             log_function(f"[{client.muda_name}] Warning: Could not parse rolls left from $tu.", preset_name, "ERROR")

                        # --- Claim Right Check ---
                        if "you __can__ claim" in content_lower:
                            client.claim_right_available = True
                            ignore_limit = False # Default to not ignoring
                            # Try to parse remaining claim time for logging/logic
                            match_claim = re.search(r"next claim reset .*?\*\*(\d+h)?\s*(\d+)\*\* min", content_lower)
                            if match_claim:
                                hours_str = match_claim.group(1)
                                hours = int(hours_str[:-1]) if hours_str else 0
                                minutes = int(match_claim.group(2))
                                remaining_seconds = (hours * 60 + minutes) * 60
                                log_function(f"[{client.muda_name}] Claim right available. Reset in {hours}h {minutes}min.", preset_name, "INFO")

                                # Snipe Ignore Logic based on claim time
                                if remaining_seconds <= 3600: # Less than or equal to 1 hour left
                                    if client.snipe_mode and client.snipe_ignore_min_kakera_reset:
                                        log_function(f"[{client.muda_name}] Claim reset <1h & snipe override active; ignoring min_kakera limit for rolls.", preset_name, "INFO")
                                        ignore_limit = True
                                    else:
                                        log_function(f"[{client.muda_name}] Claim reset <1h; applying min_kakera limit for rolls.", preset_name, "INFO")
                                else:
                                    log_function(f"[{client.muda_name}] Claim reset >1h; applying min_kakera limit for rolls.", preset_name, "INFO")
                            else:
                                log_function(f"[{client.muda_name}] Claim right available, but couldn't parse exact reset time. Applying min_kakera limit.", preset_name, "INFO")

                            # --- Roll Action (Can Claim) ---
                            if rolls_left == 0:
                                log_function(f"[{client.muda_name}] No rolls left. Reset in {reset_time_minutes} min.", preset_name, "RESET")
                                await wait_for_rolls_reset(reset_time_minutes, client.delay_seconds, log_function, preset_name)
                                # After waiting, re-check the overall status ($tu)
                                continue # Go back to start of while loop to send $tu again
                            elif rolls_left > 0:
                                log_function(f"[{client.muda_name}] Rolls left: {rolls_left}. Starting rolls.", preset_name, "INFO")
                                await start_roll_commands(client, channel, rolls_left, ignore_limit, key_mode_only_kakera=False)
                                return # Finished rolling for this cycle
                            else: # rolls_left is -1 (parsing failed)
                                log_function(f"[{client.muda_name}] Could not determine rolls left, but claim is available. Retrying status check shortly.", preset_name, "ERROR")
                                await asyncio.sleep(60)
                                continue # Go back to start of while loop

                        elif "can't claim for another" in content_lower:
                            client.claim_right_available = False
                            match_claim_wait = re.search(r"another \*\*(\d+h)?\s*(\d+)\*\* min", content_lower)
                            if match_claim_wait:
                                hours_str = match_claim_wait.group(1)
                                hours = int(hours_str[:-1]) if hours_str else 0
                                minutes = int(match_claim_wait.group(2))
                                total_seconds_claim_wait = (hours * 60 + minutes) * 60

                                # --- Roll Action (Can't Claim) ---
                                if client.key_mode:
                                    log_function(f"[{client.muda_name}] Claim unavailable ({hours}h {minutes}m left), but Key Mode active.", preset_name, "INFO")
                                    if rolls_left == 0:
                                        log_function(f"[{client.muda_name}] No rolls left (key mode). Reset in {reset_time_minutes} min.", preset_name, "RESET")
                                        await wait_for_rolls_reset(reset_time_minutes, client.delay_seconds, log_function, preset_name)
                                        # After waiting, re-check the overall status ($tu)
                                        continue # Go back to start of while loop
                                    elif rolls_left > 0:
                                        log_function(f"[{client.muda_name}] Rolling for kakera only (Key Mode). Rolls left: {rolls_left}", preset_name, "INFO")
                                        # Key mode implicitly ignores min_kakera for *character* claims (since none happen),
                                        # but we still want to claim high-value kakera.
                                        # Setting ignore_limit=True here allows kakera claim regardless of value.
                                        await start_roll_commands(client, channel, rolls_left, ignore_limit=True, key_mode_only_kakera=True)
                                        return # Finished rolling for this cycle
                                    else: # rolls_left is -1 (parsing failed)
                                        log_function(f"[{client.muda_name}] Key Mode active, claim unavailable, but couldn't determine rolls. Retrying status check shortly.", preset_name, "ERROR")
                                        await asyncio.sleep(60)
                                        continue # Go back to start of while loop
                                else: # Not key mode, claim unavailable
                                    log_function(f"[{client.muda_name}] Claim right not available. Reset in {hours}h {minutes}min. Waiting for claim reset...", preset_name, "RESET")
                                    await wait_for_reset(total_seconds_claim_wait, client.delay_seconds, log_function, preset_name)
                                    # After waiting for claim, re-check the overall status ($tu)
                                    continue # Go back to start of while loop to send $tu again
                            else:
                                log_function(f"[{client.muda_name}] Claim unavailable, but couldn't parse wait time. Retrying status check shortly.", preset_name, "ERROR")
                                await asyncio.sleep(60)
                                continue # Go back to start of while loop
                        else:
                            # Found a message matching the initial filter but couldn't parse status
                            log_function(f"[{client.muda_name}] Found likely Mudae $tu response but couldn't determine claim status. Content: {content_lower}", preset_name, "ERROR")
                            # Fall through to retry logic below

                        # If we reached here, it means we found the message but failed to parse something crucial
                        # Let the loop continue to the retry logic

                # If loop finishes without finding a suitable message from Mudae
                raise ValueError("Mudae $tu message containing key phrases not found in recent history.")

            except ValueError as e: # Catch specific error for not finding message
                error_count += 1
                log_function(f"[{client.muda_name}] Error checking status ({error_count}/{max_retries}): {e}", preset_name, "ERROR")
                if error_count >= max_retries:
                    log_function(f"[{client.muda_name}] Max retries reached for $tu status check. Retrying in 30 minutes.", preset_name, "ERROR")
                    await asyncio.sleep(1800)
                    error_count = 0 # Reset after long wait
                else:
                    log_function(f"[{client.muda_name}] Retrying status check in 5 seconds.", preset_name, "ERROR")
                    await asyncio.sleep(5)
                continue # Continue the while loop to retry check_status

            except Exception as e: # Catch other potential errors
                error_count += 1
                log_function(f"[{client.muda_name}] Unexpected error during status check ({error_count}/{max_retries}): {e}", preset_name, "ERROR")
                if error_count >= max_retries:
                    log_function(f"[{client.muda_name}] Max retries reached due to unexpected error. Retrying in 30 minutes.", preset_name, "ERROR")
                    await asyncio.sleep(1800)
                    error_count = 0
                else:
                    log_function(f"[{client.muda_name}] Retrying status check in 10 seconds.", preset_name, "ERROR")
                    await asyncio.sleep(10)
                continue # Continue the while loop to retry check_status
    # --- END OF MODIFIED check_status FUNCTION ---


    # --- check_rolls_left_tu FUNCTION REMOVED ---


    async def start_roll_commands(client, channel, rolls_left, ignore_limit=False, key_mode_only_kakera=False):
        """Sends roll commands and handles the resulting messages."""
        log_function(f"[{client.muda_name}] Starting {rolls_left} rolls...", preset_name, "INFO")
        rolled_messages_ids = set() # Keep track of message IDs we initiated rolls for
        for i in range(rolls_left):
            try:
                sent_msg = await channel.send(f"{client.mudae_prefix}{roll_command}")
                rolled_messages_ids.add(sent_msg.id) # Store the ID of the command message
                # log_function(f"[{client.muda_name}] Roll {i+1}/{rolls_left} sent.", preset_name, "INFO") # Optional: verbose logging
                await asyncio.sleep(client.roll_speed)
            except discord.errors.HTTPException as e:
                log_function(f"[{client.muda_name}] Error sending roll command: {e}. Skipping roll.", preset_name, "ERROR")
                await asyncio.sleep(1) # Wait a bit before next attempt
            except discord.errors.Forbidden as e:
                 log_function(f"[{client.muda_name}] Error sending roll command (Forbidden): {e}. Check permissions. Stopping rolls.", preset_name, "ERROR")
                 break # Stop trying to roll if permission is denied

        log_function(f"[{client.muda_name}] Finished sending rolls. Waiting briefly for Mudae...", preset_name, "INFO")
        await asyncio.sleep(5) # Increased wait time after finishing rolls

        # Fetch recent messages to process
        mudae_messages_to_process = []
        try:
            # Fetch slightly more to account for potential other bot messages or delays
            async for msg in channel.history(limit=rolls_left * 2 + 15, oldest_first=False):
                # Ensure it's from Mudae and likely a character roll embed
                if msg.author.id == TARGET_BOT_ID and msg.embeds:
                     # Basic check if it's a character embed (has author name or description)
                     embed = msg.embeds[0]
                     if (embed.author and embed.author.name) or embed.description:
                         mudae_messages_to_process.append(msg)
                     # Break early if we have processed enough messages related to the rolls
                     # This isn't perfect but helps avoid processing very old messages unnecessarily
                     if len(mudae_messages_to_process) >= rolls_left + 5:
                         break

            log_function(f"[{client.muda_name}] Processing {len(mudae_messages_to_process)} potential character messages.", preset_name, "INFO")
            if mudae_messages_to_process:
                 # Pass key_mode_only_kakera to handle_mudae_messages
                 await handle_mudae_messages(client, channel, mudae_messages_to_process, ignore_limit, key_mode_only_kakera)
            else:
                 log_function(f"[{client.muda_name}] No character messages found to process after rolling.", preset_name, "INFO")

        except discord.errors.Forbidden:
             log_function(f"[{client.muda_name}] Error fetching message history (Forbidden). Check Read Message History permission.", preset_name, "ERROR")
        except Exception as e:
            log_function(f"[{client.muda_name}] Error fetching/processing messages after rolling: {e}", preset_name, "ERROR")

        await asyncio.sleep(2) # Brief pause before re-checking status

        # Always re-check status after a batch of rolls or a snipe attempt
        if client.snipe_happened or client.series_snipe_happened:
            log_function(f"[{client.muda_name}] Snipe occurred, re-checking status.", preset_name, "INFO")
            client.snipe_happened = False
            client.series_snipe_happened = False
            await asyncio.sleep(1)
            await check_status(client, channel, client.mudae_prefix)
        else:
            log_function(f"[{client.muda_name}] Rolls complete, re-checking status.", preset_name, "INFO")
            await asyncio.sleep(1)
            await check_status(client, channel, client.mudae_prefix)


    async def handle_mudae_messages(client, channel, mudae_messages, ignore_limit=False, key_mode_only_kakera=False):
        """Processes a list of Mudae messages for claiming kakera and characters."""
        # Separate lists for potential claims
        kakera_claims = []
        character_claims = [] # Includes high-value characters (wishlist handled separately)
        wishlist_claims = []
        rt_claims = [] # Potential targets for $rt

        # Determine the effective minimum Kakera value based on ignore_limit flag
        # ignore_limit=True means we claim characters regardless of kakera value (usually when claim reset is soon)
        # ignore_limit=False means we apply the preset's min_kakera value
        # key_mode_only_kakera=True means we ONLY claim kakera, never characters.
        min_kak_value_for_char = 0 if ignore_limit else client.min_kakera

        log_function(f"[{client.muda_name}] Handling messages. Min Char Kakera: {min_kak_value_for_char}. KeyMode+NoClaim: {key_mode_only_kakera}", preset_name, "CHECK")

        # --- First Pass: Identify all potential claims ---
        for msg in mudae_messages:
            if not msg.embeds: continue
            embed = msg.embeds[0]
            char_name = (embed.author.name if embed.author else "Unknown").lower()
            description = embed.description or ""
            kakera_value = 0
            series_name = (description.splitlines()[0] if description else "Unknown").lower()

            # Extract Kakera value if present
            match = re.search(r"\*\*([\d,]+)\*\*<:(kakera[PYORGLW]?):\d+>", description) # Improved regex for kakera variants
            if match:
                try:
                    kakera_value = int(match.group(1).replace(",", ""))
                except ValueError:
                    log_function(f"[{client.muda_name}] Failed to parse kakera value from: {match.group(1)}", preset_name, "ERROR")

            # Check for Kakera reaction/button
            if msg.components:
                for component in msg.components:
                    if isinstance(component, discord.ActionRow): # Check if it's an ActionRow
                        for button in component.children:
                           if isinstance(button, discord.Button) and button.emoji and hasattr(button.emoji, 'name'):
                                if any(k_emoji in button.emoji.name for k_emoji in KAKERA_EMOJIS):
                                    # Always add kakera opportunities if buttons exist
                                    kakera_claims.append((msg, kakera_value)) # Store msg and value
                                    # log_function(f"[{client.muda_name}] Kakera button found for {char_name} (Value: {kakera_value})", client.preset_name, "DEBUG") # Debug log
                                    break # Found kakera button for this message

            # --- Character/Wishlist Claim Eligibility ---
            # Skip character claim checks if in key_mode_only_kakera mode
            if key_mode_only_kakera:
                continue

            # Check if this character is on the normal wishlist
            is_wishlist = any(wish == char_name for wish in client.wishlist)
            if not is_wishlist: # Fallback to substring check
                is_wishlist = any(wish in char_name for wish in client.wishlist if len(wish) > 2)

            # Check if this character's series is on the series wishlist
            is_series_wishlist = any(swish in series_name for swish in client.series_wishlist)

            # Check if a claim button exists (required for non-RT claims)
            has_claim_button = False
            claim_button_emoji_name = None
            if msg.components:
                 for component in msg.components:
                     if isinstance(component, discord.ActionRow):
                         for button in component.children:
                             if isinstance(button, discord.Button) and button.emoji and hasattr(button.emoji, 'name'):
                                 if any(c_emoji in button.emoji.name for c_emoji in CLAIM_EMOJIS): # Check name contains emoji base
                                    has_claim_button = True
                                    claim_button_emoji_name = button.emoji.name # Store for logging
                                    break # Found claim button
                 if has_claim_button: break # Found in this component row

            # Decide if this character is a candidate for claiming
            if client.claim_right_available: # Must have claim right available for normal claims
                if is_wishlist and has_claim_button:
                     wishlist_claims.append((msg, char_name, kakera_value))
                     log_function(f"[{client.muda_name}] Wishlist character found: {embed.author.name} (Value: {kakera_value})", preset_name, "INFO")
                elif is_series_wishlist and has_claim_button:
                     # Treat series wishlist same as normal for priority? Add to wishlist_claims or separate? Let's add to wishlist.
                     wishlist_claims.append((msg, f"{embed.author.name} [{series_name.splitlines()[0]}]", kakera_value))
                     log_function(f"[{client.muda_name}] Series Wishlist character found: {embed.author.name} from {series_name.splitlines()[0]} (Value: {kakera_value})", preset_name, "INFO")
                elif has_claim_button and kakera_value >= min_kak_value_for_char:
                    # Only consider non-wishlist if meets kakera threshold (or threshold is 0 due to ignore_limit)
                    character_claims.append((msg, char_name, kakera_value))
                    # log_function(f"[{client.muda_name}] High value character found: {embed.author.name} (Value: {kakera_value})", preset_name, "DEBUG") # Optional debug log
                elif has_claim_button: # Eligible for RT if value > 0, even if below threshold? Or just add all? Let's add all with button.
                    rt_claims.append((msg, char_name, kakera_value)) # Add potential RT target even if low value initially

            elif has_claim_button: # No claim right, but has button -> Potential RT target if RT happens
                 rt_claims.append((msg, char_name, kakera_value))


        # --- Second Pass: Execute Claims based on priority ---
        claimed_normally = False
        used_rt = False

        # 1. Claim Kakera (Always try if buttons found)
        # Sort kakera claims by value descending, claim highest first
        kakera_claims.sort(key=lambda item: item[1], reverse=True)
        for msg, k_val in kakera_claims:
            # Check if kakera button is *still* available (important!)
            kakera_button_still_present = False
            if msg.components:
                 for component in msg.components:
                    if isinstance(component, discord.ActionRow):
                         for button in component.children:
                             if isinstance(button, discord.Button) and button.emoji and hasattr(button.emoji, 'name'):
                                 if any(k_emoji in button.emoji.name for k_emoji in KAKERA_EMOJIS):
                                     kakera_button_still_present = True
                                     break
                    if kakera_button_still_present: break

            if kakera_button_still_present:
                log_function(f"[{client.muda_name}] Attempting to claim Kakera (Value: {k_val})", client.preset_name, "KAKERA")
                await claim_character(client, channel, msg, is_kakera=True)
                await asyncio.sleep(0.5) # Small delay between kakera clicks
            else:
                 log_function(f"[{client.muda_name}] Kakera button disappeared for value {k_val}, skipping.", client.preset_name, "INFO")


        # 2. Claiming Characters (only if not in key_mode_only_kakera)
        if not key_mode_only_kakera:
            # Sort all potential claims for easier processing
            wishlist_claims.sort(key=lambda item: item[2], reverse=True) # Sort wishlist by value (highest value wishlist first)
            character_claims.sort(key=lambda item: item[2], reverse=True) # Sort regular by value

            # Prioritize Wishlist for Normal Claim
            if client.claim_right_available and wishlist_claims:
                msg_to_claim, name, value = wishlist_claims[0]
                log_function(f"[{client.muda_name}] Prioritizing wishlist claim: {name} (Value: {value})", preset_name, "CLAIM")
                success = await claim_character(client, channel, msg_to_claim, is_kakera=False)
                if success:
                    claimed_normally = True
                    # Remove from other lists to avoid re-claiming
                    character_claims = [(m, n, v) for m, n, v in character_claims if m.id != msg_to_claim.id]
                    rt_claims = [(m, n, v) for m, n, v in rt_claims if m.id != msg_to_claim.id]
                    wishlist_claims.pop(0) # Remove the claimed one

            # Normal Claim for Highest Value (if no wishlist claimed yet)
            if client.claim_right_available and not claimed_normally and character_claims:
                msg_to_claim, name, value = character_claims[0]
                log_function(f"[{client.muda_name}] Claiming highest value character: {name} (Value: {value})", preset_name, "CLAIM")
                success = await claim_character(client, channel, msg_to_claim, is_kakera=False)
                if success:
                    claimed_normally = True
                    character_claims.pop(0) # Remove claimed item
                    # Remove from other lists
                    rt_claims = [(m, n, v) for m, n, v in rt_claims if m.id != msg_to_claim.id]
                    wishlist_claims = [(m, n, v) for m, n, v in wishlist_claims if m.id != msg_to_claim.id]

            # RT Claim Logic (only if a normal claim happened)
            if claimed_normally:
                # Combine remaining wishlist, high-value, and specific RT candidates
                potential_rt_targets = wishlist_claims + character_claims + rt_claims
                # Remove duplicates based on message ID, keeping the first occurrence (which might have more accurate list info)
                seen_ids = set()
                unique_rt_targets = []
                for item in potential_rt_targets:
                    if item[0].id not in seen_ids:
                        unique_rt_targets.append(item)
                        seen_ids.add(item[0].id)

                unique_rt_targets.sort(key=lambda item: item[2], reverse=True) # Sort remaining by value

                if unique_rt_targets:
                    msg_to_rt_claim, name, value = unique_rt_targets[0]
                    # Check if RT is actually worth it (use non-ignored threshold for RT)
                    # Also ensure the target still has a claim button!
                    rt_claim_button_still_present = False
                    if msg_to_rt_claim.components:
                         for component in msg_to_rt_claim.components:
                             if isinstance(component, discord.ActionRow):
                                 for button in component.children:
                                     if isinstance(button, discord.Button) and button.emoji and hasattr(button.emoji, 'name'):
                                         if any(c_emoji in button.emoji.name for c_emoji in CLAIM_EMOJIS):
                                            rt_claim_button_still_present = True
                                            break
                         if rt_claim_button_still_present: break

                    if rt_claim_button_still_present and value >= client.min_kakera:
                        log_function(f"[{client.muda_name}] Attempting RT claim for: {name} (Value: {value})", preset_name, "CLAIM")
                        try:
                            await channel.send(f"{client.mudae_prefix}rt")
                            used_rt = True
                            await asyncio.sleep(0.8) # Wait slightly longer after rt command
                            await claim_character(client, channel, msg_to_rt_claim, is_rt_claim=True)
                            # No need to set claimed_normally=True here, RT is separate
                        except Exception as e:
                             log_function(f"[{client.muda_name}] Error during RT command/claim: {e}", preset_name, "ERROR")
                    elif not rt_claim_button_still_present:
                         log_function(f"[{client.muda_name}] Skipping RT for {name} (Value: {value}) as claim button disappeared.", preset_name, "INFO")
                    else:
                        log_function(f"[{client.muda_name}] Skipping RT for {name} (Value: {value}) as it's below min_kakera ({client.min_kakera}) for RT.", preset_name, "INFO")


    async def claim_character(client, channel, msg, is_kakera=False, is_rt_claim=False):
        """Clicks the appropriate button or adds a reaction to claim. Returns True on success, False on failure."""
        if not msg or not msg.embeds: # Basic check
            log_function(f"[{client.muda_name}] Invalid message passed to claim_character.", client.preset_name, "ERROR")
            return False

        embed = msg.embeds[0]
        character_name = embed.author.name if embed.author else "Unknown Character"
        log_prefix = f"[{client.muda_name}]"
        log_suffix = f": {character_name}"
        log_type = "CLAIM"
        target_emojis = CLAIM_EMOJIS

        if is_kakera:
            log_message = "Attempting Kakera claim"
            log_type = "KAKERA"
            target_emojis = KAKERA_EMOJIS
        elif is_rt_claim:
            log_message = "Attempting RT claim"
        else:
            log_message = "Attempting character claim"

        # Try clicking buttons first (more reliable)
        button_clicked = False
        if msg.components:
            target_button = None
            # Find the specific button
            for component in msg.components:
                 if isinstance(component, discord.ActionRow):
                     for button in component.children:
                        if isinstance(button, discord.Button) and button.emoji and hasattr(button.emoji, 'name'):
                           # Check if button emoji name CONTAINS any target emoji string
                           if any(emoji_str in button.emoji.name for emoji_str in target_emojis):
                               target_button = button
                               break # Found the button
                 if target_button:
                     break # Found button in this row

            if target_button:
                try:
                    log_function(f"{log_prefix} {log_message}{log_suffix} (via button: {target_button.emoji.name})", client.preset_name, log_type)
                    # Use interaction simulation if available (more robust)
                    # Note: Simulating interactions might require specific intents or library versions
                    # Fallback to button.click() which is standard discord.py
                    await target_button.click()
                    button_clicked = True
                    await asyncio.sleep(1.5) # Wait after click
                    log_function(f"{log_prefix} Claim successful for {character_name}", client.preset_name, log_type)
                    return True # Successfully clicked

                except discord.errors.NotFound:
                    log_function(f"{log_prefix} Button interaction failed (NotFound - likely already claimed/expired){log_suffix}", client.preset_name, "ERROR")
                    return False # Don't try reaction if button failed this way
                except discord.errors.HTTPException as e:
                    # Common error: 400 Bad Request (Interaction Failed) -> Already claimed or expired
                    if e.status == 400:
                         log_function(f"{log_prefix} Button interaction failed (Interaction Failed - likely already claimed/expired){log_suffix}", client.preset_name, "ERROR")
                    else:
                         log_function(f"{log_prefix} Button click failed (HTTPException {e.status}){log_suffix}", client.preset_name, "ERROR")
                    return False
                except Exception as e:
                     log_function(f"{log_prefix} Unexpected error clicking button{log_suffix}: {e}", client.preset_name, "ERROR")
                     return False # Stop claim attempt on unexpected error
            else:
                 # Log if no suitable button was found, except for kakera (where it's expected sometimes)
                 if not is_kakera:
                     log_function(f"{log_prefix} No suitable claim button found for {character_name}.", client.preset_name, "INFO")


        # Fallback to reaction if no button was clicked (and not kakera)
        # Avoid reaction fallback for kakera as it doesn't work
        if not button_clicked and not is_kakera:
            log_function(f"{log_prefix} No claim button found/clicked for {character_name}. Attempting reaction fallback.", client.preset_name, "INFO")
            try:
                # Using a common claim emoji like heart
                await msg.add_reaction("💖")
                log_function(f"{log_prefix} {log_message}{log_suffix} (via reaction 💖)", client.preset_name, log_type)
                await asyncio.sleep(1.5) # Wait after reaction
                # Reaction success doesn't guarantee claim success with Mudae, but we tried
                return True # Indicate reaction was added
            except discord.errors.Forbidden:
                 log_function(f"{log_prefix} Reaction claim failed (Forbidden - check permissions){log_suffix}", client.preset_name, "ERROR")
                 return False
            except discord.errors.NotFound:
                 log_function(f"{log_prefix} Reaction claim failed (NotFound - message deleted?){log_suffix}", client.preset_name, "ERROR")
                 return False
            except discord.errors.HTTPException as e:
                 log_function(f"{log_prefix} Reaction claim failed (HTTPException {e.status}){log_suffix}", client.preset_name, "ERROR")
                 return False
            except Exception as e:
                 log_function(f"{log_prefix} Unexpected error adding reaction{log_suffix}: {e}", client.preset_name, "ERROR")
                 return False

        # If no button was found for Kakera, or reaction fallback failed
        if is_kakera and not button_clicked:
            # Don't log an error if no kakera button, just info
            # log_function(f"{log_prefix} No kakera button found for {character_name}.", client.preset_name, "INFO")
            pass # Silently skip if no kakera button

        return False # Indicate claim attempt failed


    async def wait_for_reset(seconds_to_wait, base_delay_seconds, log_function, preset_name):
        """Waits until the next claim reset, adding the base delay."""
        if seconds_to_wait <= 0:
            seconds_to_wait = 1 # Ensure at least a minimal wait

        # Add the base delay configured for the preset
        total_wait = max(1, seconds_to_wait + base_delay_seconds) # Ensure wait is at least 1 sec

        wait_end_time = datetime.datetime.now() + datetime.timedelta(seconds=total_wait)

        log_function(f"[{preset_name}] Waiting for claim reset. Wait time: {seconds_to_wait}s + {base_delay_seconds}s delay = {total_wait:.2f}s. Resuming at ~{wait_end_time.strftime('%H:%M:%S')}", preset_name, "RESET")
        await asyncio.sleep(total_wait)
        log_function(f"[{preset_name}] Claim wait finished. Re-checking status.", preset_name, "RESET")


    async def wait_for_rolls_reset(reset_time_minutes, base_delay_seconds, log_function, preset_name):
        """Waits until the next roll reset, adding the base delay."""
        if reset_time_minutes <= 0:
             # If reset time is unknown or 0, wait a default reasonable time (e.g., 60 seconds + delay)
             log_function(f"[{preset_name}] Unknown or zero roll reset time. Waiting default 60s + delay.", preset_name, "RESET")
             seconds_until_reset = 60
        else:
            now = datetime.datetime.now()
            # Calculate seconds until the next roll reset minute mark precisely
            # Example: reset_time_minutes = 40. Wait until the *next* time minutes are XX:40:00
            # This requires knowing Mudae's exact reset interval (usually 1 hour)
            # Simpler approach: Wait for the specified minutes + small buffer
            seconds_until_reset = (reset_time_minutes * 60) + 5 # Add 5 sec buffer

        # Add the base delay configured for the preset
        total_wait = max(1, seconds_until_reset + base_delay_seconds) # Ensure wait is at least 1 sec

        wait_end_time = datetime.datetime.now() + datetime.timedelta(seconds=total_wait)

        log_function(f"[{preset_name}] Waiting for rolls reset (~{reset_time_minutes} min cycle). Wait time: {seconds_until_reset}s + {base_delay_seconds}s delay = {total_wait:.2f}s. Resuming at ~{wait_end_time.strftime('%H:%M:%S')}", preset_name, "RESET")
        await asyncio.sleep(total_wait)
        log_function(f"[{preset_name}] Roll wait finished. Re-checking status.", preset_name, "RESET")


    @client.event
    async def on_message(message):
        # Ignore messages from self
        if message.author == client.user:
            return

        # Basic command processing (if needed, e.g., for owner commands)
        # Add command checks here if you implement any bot commands
        # await client.process_commands(message)

        # --- Sniping Logic ---
        # Only proceed if it's the target bot in the target channel
        if message.author.id != TARGET_BOT_ID or message.channel.id != client.target_channel_id:
            return

        # Ignore messages without embeds (likely not character rolls)
        if not message.embeds:
            return

        embed = message.embeds[0]
        process_further = True # Flag to decide if normal command processing should happen (currently none)

        # Check for claim button presence early
        claim_button_present = False
        if message.components:
             for component in message.components:
                 if isinstance(component, discord.ActionRow):
                     for button in component.children:
                        if isinstance(button, discord.Button) and button.emoji and hasattr(button.emoji, 'name'):
                           if any(emoji_str in button.emoji.name for emoji_str in CLAIM_EMOJIS):
                                claim_button_present = True
                                break
                 if claim_button_present:
                     break

        # If no claim button, sniping is impossible
        if not claim_button_present:
            return

        # 1. Series Sniping Check
        if client.series_snipe_mode and client.series_wishlist:
            description = embed.description or ""
            if description:
                first_line = description.splitlines()[0].lower() # Lowercase for comparison
                # Check if any series keyword is in the first line
                if any(kw in first_line for kw in client.series_wishlist):
                     if message.id not in client.series_sniped_messages:
                        client.series_sniped_messages.add(message.id)
                        series_name_for_log = embed.author.name if embed.author else first_line # Get name for log
                        log_function(f"[{client.muda_name}] (SNIPE) Series match: {series_name_for_log}. Waiting {client.series_snipe_delay}s", client.preset_name, "CLAIM")
                        await asyncio.sleep(client.series_snipe_delay)
                        # Re-check button presence before sniping
                        if any(any(emoji_str in b.emoji.name for emoji_str in CLAIM_EMOJIS) for comp in message.components for b in comp.children if isinstance(b, discord.Button) and b.emoji and hasattr(b.emoji, 'name')):
                            await claim_character(client, message.channel, message, is_kakera=False)
                            client.series_snipe_happened = True # Signal that a snipe happened
                        else:
                            log_function(f"[{client.muda_name}] (SNIPE) Claim button disappeared for series {series_name_for_log} before snipe.", client.preset_name, "INFO")
                        process_further = False # Stop processing this message further


        # 2. Normal Character Sniping Check (only if series snipe didn't happen)
        if process_further and client.snipe_mode and client.wishlist:
            if embed.author and embed.author.name:
                character_name_lower = embed.author.name.lower()
                # Check if character name is in the wishlist (substring match)
                is_snipe_target = any(wish == character_name_lower for wish in client.wishlist) # Exact match first
                if not is_snipe_target: # Fallback to substring check
                     is_snipe_target = any(wish in character_name_lower for wish in client.wishlist if len(wish) > 2)

                if is_snipe_target:
                     if message.id not in client.sniped_messages:
                        client.sniped_messages.add(message.id)
                        log_function(f"[{client.muda_name}] (SNIPE) Wishlist match: {embed.author.name}. Waiting {client.snipe_delay}s", client.preset_name, "CLAIM")
                        await asyncio.sleep(client.snipe_delay)
                        # Re-check button presence before sniping
                        if any(any(emoji_str in b.emoji.name for emoji_str in CLAIM_EMOJIS) for comp in message.components for b in comp.children if isinstance(b, discord.Button) and b.emoji and hasattr(b.emoji, 'name')):
                            await claim_character(client, message.channel, message, is_kakera=False)
                            client.snipe_happened = True # Signal that a snipe happened
                        else:
                            log_function(f"[{client.muda_name}] (SNIPE) Claim button disappeared for {embed.author.name} before snipe.", client.preset_name, "INFO")
                        process_further = False # Stop processing this message further

        # Add any other on_message logic here if needed (e.g., responding to Mudae events)


    # --- Bot Execution ---
    try:
        # client.run is blocking, so it needs to be run in the main thread or awaited if using asyncio.run
        # Since we use threading, this is correct.
        client.run(token)
    except discord.errors.LoginFailure:
        log_function(f"[{BOT_NAME}] Bot failed to log in for preset '{preset_name}'. Check the token.", preset_name, "ERROR")
    except discord.errors.PrivilegedIntentsRequired:
         log_function(f"[{BOT_NAME}] Bot failed for preset '{preset_name}'. The Message Content Intent is required. Enable it in the Discord Developer Portal.", preset_name, "ERROR")
    except Exception as e:
        log_function(f"[{BOT_NAME}] An unexpected error occurred running the bot for preset '{preset_name}': {e}", preset_name, "ERROR")
        import traceback
        traceback.print_exc() # Print full traceback for debugging


def show_banner():
    """Displays the MudaRemote banner."""
    banner = r"""
  __  __ _    _ _____          _____  ______ __  __  ____ _______ ______
 |  \/  | |  | |  __ \   /\   |  __ \|  ____|  \/  |/ __ \__   __|  ____|
 | \  / | |  | | |  | | /  \  | |__) | |__  | \  / | |  | | | |  | |__
 | |\/| | |  | | |  | |/ /\ \ |  _  /|  __| | |\/| | |  | | | |  |  __|
 | |  | | |__| | |__| / ____ \| | \ \| |____| |  | | |__| | | |  | |____
 |_|  |_|\____/|_____/_/    \_\_|  \_\______|_|  |_|\____/  |_|  |______|

"""
    print("\033[1;36m" + banner + "\033[0m") # Cyan Bold
    print("\033[1;33mWelcome to MudaRemote - Your Remote Mudae Assistant\033[0m\n") # Yellow Bold

def validate_preset(preset_name, preset_data):
    """Validates required fields and types in a preset."""
    required_keys = ["token", "prefix", "channel_id", "roll_command", "min_kakera", "delay_seconds", "mudae_prefix"]
    valid = True
    missing_keys = [key for key in required_keys if key not in preset_data]
    if missing_keys:
        print(f"\033[91mError in preset '{preset_name}': Missing required keys: {', '.join(missing_keys)}\033[0m")
        valid = False

    # Check types for existing required keys
    if "token" in preset_data and (not isinstance(preset_data["token"], str) or not preset_data["token"]):
        print(f"\033[91mError in preset '{preset_name}': 'token' must be a non-empty string.\033[0m")
        valid = False
    if "prefix" in preset_data and not isinstance(preset_data["prefix"], str):
         print(f"\033[91mError in preset '{preset_name}': 'prefix' must be a string.\033[0m")
         valid = False
    if "channel_id" in preset_data and not isinstance(preset_data["channel_id"], int):
        # Try converting if string looks like int
        if isinstance(preset_data["channel_id"], str) and preset_data["channel_id"].isdigit():
             preset_data["channel_id"] = int(preset_data["channel_id"])
             print(f"\033[93mWarning in preset '{preset_name}': Converted 'channel_id' from string to integer.\033[0m")
        else:
             print(f"\033[91mError in preset '{preset_name}': 'channel_id' must be an integer.\033[0m")
             valid = False
    if "roll_command" in preset_data and not isinstance(preset_data["roll_command"], str):
         print(f"\033[91mError in preset '{preset_name}': 'roll_command' must be a string.\033[0m")
         valid = False
    if "min_kakera" in preset_data and (not isinstance(preset_data["min_kakera"], int) or preset_data["min_kakera"] < 0):
        print(f"\033[91mError in preset '{preset_name}': 'min_kakera' must be a non-negative integer.\033[0m")
        valid = False
    if "delay_seconds" in preset_data and (not isinstance(preset_data["delay_seconds"], (int, float)) or preset_data["delay_seconds"] < 0):
         print(f"\033[91mError in preset '{preset_name}': 'delay_seconds' must be a non-negative number.\033[0m")
         valid = False
    if "mudae_prefix" in preset_data and not isinstance(preset_data["mudae_prefix"], str):
        print(f"\033[91mError in preset '{preset_name}': 'mudae_prefix' must be a string.\033[0m")
        valid = False

    # Optional fields validation (type checks if they exist)
    if "key_mode" in preset_data and not isinstance(preset_data["key_mode"], bool):
         print(f"\033[91mWarning in preset '{preset_name}': 'key_mode' should be true or false. Found: {type(preset_data['key_mode'])}. Using False.\033[0m")
         preset_data["key_mode"] = False
    if "start_delay" in preset_data and (not isinstance(preset_data["start_delay"], (int, float)) or preset_data["start_delay"] < 0):
        print(f"\033[91mWarning in preset '{preset_name}': 'start_delay' should be a non-negative number. Found: {preset_data['start_delay']}. Using 0.\033[0m")
        preset_data["start_delay"] = 0
    if "snipe_mode" in preset_data and not isinstance(preset_data["snipe_mode"], bool):
         print(f"\033[91mWarning in preset '{preset_name}': 'snipe_mode' should be true or false. Using False.\033[0m")
         preset_data["snipe_mode"] = False
    if "snipe_delay" in preset_data and (not isinstance(preset_data["snipe_delay"], (int, float)) or preset_data["snipe_delay"] < 0):
         print(f"\033[91mWarning in preset '{preset_name}': 'snipe_delay' should be a non-negative number. Using default 5.\033[0m")
         preset_data["snipe_delay"] = 5
    if "snipe_ignore_min_kakera_reset" in preset_data and not isinstance(preset_data["snipe_ignore_min_kakera_reset"], bool):
         print(f"\033[91mWarning in preset '{preset_name}': 'snipe_ignore_min_kakera_reset' should be true or false. Using False.\033[0m")
         preset_data["snipe_ignore_min_kakera_reset"] = False
    if "wishlist" in preset_data and not isinstance(preset_data["wishlist"], list):
         print(f"\033[91mWarning in preset '{preset_name}': 'wishlist' should be a list (e.g., [\"Char1\", \"Char2\"]). Using empty list.\033[0m")
         preset_data["wishlist"] = []
    elif "wishlist" in preset_data: # Ensure all items are strings
         preset_data["wishlist"] = [str(item) for item in preset_data["wishlist"]]

    if "series_snipe_mode" in preset_data and not isinstance(preset_data["series_snipe_mode"], bool):
         print(f"\033[91mWarning in preset '{preset_name}': 'series_snipe_mode' should be true or false. Using False.\033[0m")
         preset_data["series_snipe_mode"] = False
    if "series_snipe_delay" in preset_data and (not isinstance(preset_data["series_snipe_delay"], (int, float)) or preset_data["series_snipe_delay"] < 0):
         print(f"\033[91mWarning in preset '{preset_name}': 'series_snipe_delay' should be a non-negative number. Using default 5.\033[0m")
         preset_data["series_snipe_delay"] = 5
    if "series_wishlist" in preset_data and not isinstance(preset_data["series_wishlist"], list):
         print(f"\033[91mWarning in preset '{preset_name}': 'series_wishlist' should be a list (e.g., [\"Series1\", \"Series2\"]). Using empty list.\033[0m")
         preset_data["series_wishlist"] = []
    elif "series_wishlist" in preset_data: # Ensure all items are strings
         preset_data["series_wishlist"] = [str(item) for item in preset_data["series_wishlist"]]

    if "roll_speed" in preset_data and (not isinstance(preset_data["roll_speed"], (int, float)) or preset_data["roll_speed"] <= 0):
        print(f"\033[91mWarning in preset '{preset_name}': 'roll_speed' should be a positive number. Using default 0.4.\033[0m")
        preset_data["roll_speed"] = 0.4

    return valid


def start_preset_thread(preset_name, preset_data):
     """Validates and starts a bot thread for a given preset."""
     if not validate_preset(preset_name, preset_data):
         print(f"\033[91mSkipping preset '{preset_name}' due to configuration errors.\033[0m")
         return None # Return None if validation fails

     print(f"\033[92mStarting bot for preset: {preset_name}\033[0m")
     # Get values with defaults for optional settings using .get() after validation
     key_mode = preset_data.get("key_mode", False)
     start_delay = preset_data.get("start_delay", 0)
     snipe_mode = preset_data.get("snipe_mode", False)
     snipe_delay = preset_data.get("snipe_delay", 5)
     snipe_ignore_min_kakera_reset = preset_data.get("snipe_ignore_min_kakera_reset", False)
     wishlist = preset_data.get("wishlist", [])
     series_snipe_mode = preset_data.get("series_snipe_mode", False)
     series_snipe_delay = preset_data.get("series_snipe_delay", 5)
     series_wishlist = preset_data.get("series_wishlist", [])
     roll_speed = preset_data.get("roll_speed", 0.4)

     thread = threading.Thread(target=run_bot, args=(
         preset_data["token"],
         preset_data["prefix"],
         preset_data["channel_id"],
         preset_data["roll_command"],
         preset_data["min_kakera"],
         preset_data["delay_seconds"],
         preset_data["mudae_prefix"],
         print_log, # Pass the unified logging function
         preset_name, # Pass the preset name for logging
         key_mode,
         start_delay,
         snipe_mode,
         snipe_delay,
         snipe_ignore_min_kakera_reset,
         wishlist,
         series_snipe_mode,
         series_snipe_delay,
         series_wishlist,
         roll_speed
     ), daemon=True) # Set daemon=True so threads exit when main program exits
     thread.start()
     return thread # Return the thread object


def main_menu():
    """Displays the main menu and handles user selection."""
    show_banner()
    active_threads = {} # Use a dictionary {preset_name: thread}

    while True:
        # Clear finished threads
        finished_presets = [name for name, t in active_threads.items() if not t.is_alive()]
        for name in finished_presets:
            print(f"\033[91mBot thread for preset '{name}' has stopped.\033[0m")
            del active_threads[name]

        questions = [
            inquirer.List('option',
                          message=f"Select an option ({len(active_threads)} bots running):",
                          choices=[
                              'Select and Run Preset',
                              'Select and Run Multiple Presets',
                              'Exit'
                          ],
                          ),
        ]
        try:
            answers = inquirer.prompt(questions, raise_keyboard_interrupt=True)
            if not answers: # Handle case where prompt returns None (e.g., empty selection)
                 print("\nExiting...")
                 break

            option = answers['option']

            if option == 'Select and Run Preset':
                available_presets = [p for p in presets.keys() if p not in active_threads]
                if not available_presets:
                    print("\033[93mAll available presets are already running or no presets found.\033[0m")
                    continue
                preset_questions = [
                    inquirer.List('preset',
                                  message="Select a preset to run:",
                                  choices=available_presets,
                                  ),
                ]
                preset_answers = inquirer.prompt(preset_questions, raise_keyboard_interrupt=True)
                if preset_answers:
                    selected_preset = preset_answers['preset']
                    if selected_preset in active_threads:
                         print(f"\033[93mPreset '{selected_preset}' is already running.\033[0m")
                    else:
                        thread = start_preset_thread(selected_preset, presets[selected_preset])
                        if thread:
                            active_threads[selected_preset] = thread

            elif option == 'Select and Run Multiple Presets':
                available_presets = [p for p in presets.keys() if p not in active_threads]
                if not available_presets:
                     print("\033[93mAll available presets are already running or no presets found.\033[0m")
                     continue
                multi_preset_questions = [
                    inquirer.Checkbox('presets',
                                      message="Select presets to run (Spacebar to select/deselect, Enter to confirm):",
                                      choices=available_presets,
                                      ),
                ]
                multi_preset_answers = inquirer.prompt(multi_preset_questions, raise_keyboard_interrupt=True)
                if multi_preset_answers:
                    selected_presets = multi_preset_answers['presets']
                    for preset_name in selected_presets:
                         if preset_name in active_threads:
                             print(f"\033[93mPreset '{preset_name}' is already running. Skipping.\033[0m")
                         else:
                            thread = start_preset_thread(preset_name, presets[preset_name])
                            if thread:
                                active_threads[preset_name] = thread

            elif option == 'Exit':
                print("\033[1;32mExiting MudaRemote. Running bots will stop when the main program exits.\033[0m")
                # Daemon threads will exit automatically.
                # If explicit cleanup is needed, you'd signal threads to stop gracefully here.
                break

        except KeyboardInterrupt:
             print("\nCtrl+C detected. Exiting MudaRemote...")
             break
        except Exception as e:
            print(f"\033[91mAn error occurred in the main menu: {e}\033[0m")
            import traceback
            traceback.print_exc()
            # Optionally wait before showing menu again
            # time.sleep(2)

if __name__ == "__main__":
    # Ensure logs.txt exists at startup (optional, write_log_to_file handles it too)
    try:
        with open("logs.txt", "a") as f:
            f.write(f"\n--- MudaRemote Log Start: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n")
    except Exception as e:
         print(f"\033[91mCould not initialize log file: {e}\033[0m")

    main_menu()
    print("\033[1;36mMudaRemote finished.\033[0m")
