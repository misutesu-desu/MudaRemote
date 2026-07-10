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
    ("humanization_enabled", "Anti-Ban Stealth (Randomizes timing to look like a real human)", False),
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
    ("auto_rt_after_claim", "Auto $rt After Claim (Instantly reset your claim timer after a successful claim)", False),
    ("enable_snipe_chat_reactions", "Snipe Chat Reactions (Send a random message after a successful external snipe)", False),
    ("op_perk_5_only", "Only Click Kakera on $op (Perk 5) Characters", False),
    ("farm_character_enabled", "Enable Kakera Farming Loop (Auto-Forcedivorce)", False),
    ("auto_divorce_enabled", "Auto-Divorce (Automatically separate characters after claiming them)", False),
    ("mk_bypass_power_check", "Force $mk Rolls (Use $mk even when power is too low for normal kakera)", False),
    ("enable_hybrid_panic_claim", "Hybrid Smart Panic Claim (Instantly claim high-value characters in the last claim hour, collect others)", False),
    ("immediate_kakera_click", "Immediate Kakera Click (Click crystals instantly instead of waiting for all rolls to finish)", True),
    ("auto_p_enabled", "Auto $p (Automatically claim pokemon when available)", True),
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
        
        # Apply dark theme
        self.apply_theme()
        
        # Data
        self.presets = {}
        self.current_preset = None
        self.widgets = {}  # Store widget references for data binding
        self.settings_fields = []  # References for real-time search/filter
        self.subframe_controls = {}  # Map of subframe -> control_key
        
        # Load presets
        self.load_presets()
        
        # Build UI
        self.build_ui()
        
        # Select first preset if exists
        if self.presets:
            first_preset = list(self.presets.keys())[0]
            self.select_preset(first_preset)
    
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
                with open(PRESETS_FILE, "r", encoding="utf-8") as f:
                    self.presets = json.load(f)
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
            with open(PRESETS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.presets, f, indent=4, ensure_ascii=False)
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
        
        # Canvas for scrolling
        self.canvas = tk.Canvas(self.settings_container, bg=BG_DARK, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.settings_container, orient=tk.VERTICAL, command=self.canvas.yview)
        self.scrollable_frame = tk.Frame(self.canvas, bg=BG_DARK)
        
        self.scrollable_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor=tk.NW)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Bind mousewheel
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        
        # Build settings form
        self.build_settings_form()
    
    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        
    def rebuild_rounds_frame(self, claim_interval_mins):
        """Dynamically generate round row inputs based on claim interval."""
        num_rounds = max(1, math.ceil(claim_interval_mins / 60))
        
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
            self._bind_focus_highlight(ent_min_k)

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
            self._bind_focus_highlight(ent_max_claim)

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
            self._bind_focus_highlight(ent_max_like)
    
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
        self.add_checkbox(claim_frame.content, "auto_rt_after_claim", "Auto $rt After Claim (Instantly reset your claim timer after a successful claim)")
        
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
        self.rebuild_rounds_frame(180)
        
        def on_interval_change(*args):
            try:
                val = float(claim_interval_entry.get().strip() or "180")
                self.rebuild_rounds_frame(int(val))
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
        human_frame = CollapsibleLabelFrame(human_outer, text="Anti-Ban (Stealth Mode)", start_open=False)
        human_frame.pack(fill=tk.X)
        
        human_var = self.add_checkbox(human_frame.content, "humanization_enabled", "Anti-Ban Stealth (Randomizes timing to look like a real human)")
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
        
        # --- Advanced ---
        power_frame = CollapsibleLabelFrame(frame, text="Power & Expert Settings", start_open=False)
        power_frame.pack(fill=tk.X, pady=(0, 15))
        
        self.add_checkbox(power_frame.content, "auto_dk_enabled", "Auto $dk (Automatically use $dk when ready or low on power)")
        self.add_checkbox(power_frame.content, "auto_p_enabled", "Auto $p (Automatically claim pokemon when available)")
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
        lbl_sched_desc = tk.Label(sched_row, text="If set, the bot will roll at these specific times instead of interval loops. Respects humanization.",
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
        
        # --- Action Buttons ---
        self.btn_frame = tk.Frame(frame, bg=BG_DARK)
        self.btn_frame.pack(fill=tk.X, pady=20)
        
        self.create_flat_button(
            self.btn_frame, "💾 Save Changes", self.save_current_preset,
            bg_color=COLOR_SUCCESS, fg_color=BG_DARK, hover_bg="#b5e8b0"
        ).pack(side=tk.LEFT, padx=(0, 10))
        
        self.create_flat_button(
            self.btn_frame, "▶ Launch Bot", self.run_bot,
            bg_color=ACCENT, fg_color=BG_DARK, hover_bg=ACCENT_ALT
        ).pack(side=tk.LEFT, padx=(0, 10))
        
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
            
        entry = tk.Entry(
            container, 
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
        entry.pack(fill=tk.X, ipady=4)
        self.widgets[key] = entry
        
        self._register_settings_widget(parent, container, label + " " + (description or ""), key)
        self._bind_focus_highlight(entry)
        
        if key == "token":
            tooltip_msg = "Safety: Your token is stored locally on your PC in presets.json. Never share this with anyone. To get it, open Discord in browser, open DevTools (F12), go to Network, filter by '/api', click any request, and copy the 'Authorization' header value."
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
        """Add a comma-separated list field."""
        container = tk.Frame(parent, bg=self._get_parent_bg(parent))
        container.pack(fill=tk.X, pady=5)
        
        lbl = tk.Label(container, text=label, bg=container.cget("bg"), fg=TEXT_MAIN, font=("Segoe UI", 10))
        lbl.pack(anchor=tk.W)
        
        if description:
            lbl_desc = tk.Label(container, text=description, bg=container.cget("bg"), fg=TEXT_MUTED, font=("Segoe UI", 9), justify=tk.LEFT, wraplength=600)
            lbl_desc.pack(anchor=tk.W)
            
        entry = tk.Entry(
            container,
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
        entry.pack(fill=tk.X, ipady=4)
        self.widgets[key] = entry
        
        self._register_settings_widget(parent, container, label + " " + (description or ""), key)
        self._bind_focus_highlight(entry)
    
    def add_optional_list_field(self, parent, key, label, placeholder):
        """Add an optional list field with checkbox to enable/disable."""
        container = tk.Frame(parent, bg=self._get_parent_bg(parent))
        container.pack(fill=tk.X, pady=5)
        
        # Checkbox to enable
        var = tk.BooleanVar()
        cb = ttk.Checkbutton(container, text=label, variable=var)
        cb.pack(anchor=tk.W)
        
        # Entry for values
        entry = tk.Entry(
            container,
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
        entry.pack(fill=tk.X, padx=(20, 0), ipady=4)
        entry.insert(0, placeholder)
        entry.configure(state="disabled")
        
        # Toggle entry state based on checkbox
        def toggle_entry():
            if var.get():
                entry.configure(state="normal")
            else:
                entry.configure(state="disabled")
        
        var.trace_add("write", lambda *_: toggle_entry())
        
        self.widgets[f"{key}_enabled"] = var
        self.widgets[key] = entry
        
        self._register_settings_widget(parent, container, label, key)
        self._bind_focus_highlight(entry)
    
    def on_preset_select(self, event):
        """Handle preset selection from listbox."""
        selection = self.preset_listbox.curselection()
        if selection:
            preset_name = self.preset_listbox.get(selection[0])
            self.select_preset(preset_name)
    
    def select_preset(self, preset_name):
        """Load preset data into the form."""
        if preset_name not in self.presets:
            return
        
        self.current_preset = preset_name
        data = self.presets[preset_name]
        
        # Update title
        self.title_label.config(text=f"Editing: {preset_name}")
        
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
                    value = data.get(key, "")
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
                    "enable_snipe_chat_reactions", "op_perk_5_only", "farm_character_enabled",
                    "auto_divorce_enabled", "mk_bypass_power_check", "auto_p_enabled",
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
                if isinstance(widget, (ttk.Entry, tk.Entry)):
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
        self.rebuild_rounds_frame(claim_interval_mins)

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
    
    def save_current_preset(self):
        """Save the current form data to the preset."""
        if not self.current_preset:
            messagebox.showwarning("Warning", "No preset selected.")
            return
        
        data = {}
        
        # Collect text fields
        # [NEW] Include main_account_id and farm_character in text fields collection
        for key in ["token", "prefix", "mudae_prefix", "channel_id", "command_channel_id", "roll_command", "main_account_id", "farm_character"]:
            if key in self.widgets:
                value = self.widgets[key].get().strip()
                if value:
                    # Special handling for channel_id
                    if key in ("channel_id", "command_channel_id"):
                        try:
                            data[key] = int(value)
                        except ValueError:
                            data[key] = value  # Store as string if not numeric
                    else:
                        data[key] = value
        
        # Collect numeric fields
        # [NEW] Include max_dk_power in numeric fields
        for key in ["min_kakera", "delay_seconds", "start_delay", "roll_speed",
                    "snipe_delay", "series_snipe_delay", "kakera_snipe_threshold",
                    "kakera_reaction_snipe_delay", "humanization_window_minutes",
                    "humanization_inactivity_seconds", "reactive_snipe_delay",
                    "claim_interval", "roll_interval", "auto_us_limit",
                    "auto_rolls_limit", "panic_roll_minutes", "max_dk_power",
                    "auto_divorce_max_kakera", "max_claim_rank", "max_like_rank",
                    "hybrid_panic_instant_claim_min_kakera", "hybrid_panic_instant_claim_max_rank"]:
            if key in self.widgets:
                value = self.widgets[key].get().strip()
                if value:
                    try:
                        # Determine type
                        if key in ["min_kakera", "start_delay", "kakera_snipe_threshold",
                                   "humanization_window_minutes", "humanization_inactivity_seconds",
                                   "claim_interval", "roll_interval", "auto_us_limit", 
                                   "auto_rolls_limit", "panic_roll_minutes", "max_dk_power",
                                   "auto_divorce_max_kakera", "max_claim_rank", "max_like_rank"]:
                            data[key] = int(float(value))
                        else:
                            data[key] = float(value)
                    except ValueError:
                        pass
        
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
                    "enable_snipe_chat_reactions", "op_perk_5_only", "farm_character_enabled",
                    "auto_divorce_enabled", "mk_bypass_power_check", "auto_p_enabled",
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
        if inactive_text:
            # Parse "1-7, 23-6" -> [[1,7],[23,6]]
            inactive_parsed = []
            for part in inactive_text.split(","):
                part = part.strip()
                if "-" in part:
                    try:
                        s, e = part.split("-", 1)
                        inactive_parsed.append([int(s.strip()), int(e.strip())])
                    except ValueError:
                        pass
            data["inactive_hours"] = inactive_parsed
        else:
            data["inactive_hours"] = []
        
        # Collect reactive kakera delay range
        try:
            min_val = float(self.widgets["reactive_kakera_delay_min"].get().strip() or "0.3")
            max_val = float(self.widgets["reactive_kakera_delay_max"].get().strip() or "1.0")
            data["reactive_kakera_delay_range"] = [min_val, max_val]
        except ValueError:
            data["reactive_kakera_delay_range"] = [0.3, 1.0]

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
                        pass
        
        # [NEW] Task 7: Collect scheduled roll times
        if "scheduled_roll_times" in self.widgets:
            sched_text = self.widgets["scheduled_roll_times"].get().strip()
            if sched_text:
                data["scheduled_roll_times"] = [t.strip() for t in sched_text.split(",") if t.strip()]
            else:
                data["scheduled_roll_times"] = []
                
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

            def safe_int(v):
                if not v:
                    return None
                try:
                    return int(float(v))
                except ValueError:
                    return None

            parsed_min_k = safe_int(min_k_val)
            parsed_max_claim = safe_int(max_claim_val)
            parsed_max_like = safe_int(max_like_val)

            if parsed_min_k is not None:
                round_dict["min_kakera"] = parsed_min_k
            if parsed_max_claim is not None:
                round_dict["max_claim_rank"] = parsed_max_claim
            if parsed_max_like is not None:
                round_dict["max_like_rank"] = parsed_max_like

            if len(round_dict) > 1:
                claim_rounds_thresholds.append(round_dict)

        data["claim_rounds_thresholds"] = claim_rounds_thresholds
        
        # Update and save
        self.presets[self.current_preset] = data
        if self.save_presets():
            messagebox.showinfo("Success", f"Settings for '{self.current_preset}' are now saved!")
            
        # Manage autostart
        self._manage_autostart(self.current_preset, data.get("autostart", False))
            
    def _manage_autostart(self, preset_name, enable):
        """Manage Windows Startup shortcut for the given preset."""
        if sys.platform != "win32":
            return
            
        startup_dir = os.path.join(os.environ["APPDATA"], "Microsoft", "Windows", "Start Menu", "Programs", "Startup")
        bat_path = os.path.join(startup_dir, f"MudaRemote_{preset_name}.bat")
        
        if enable:
            is_frozen = getattr(sys, 'frozen', False)
            cwd = get_base_path()
            
            try:
                with open(bat_path, "w", encoding="utf-8") as f:
                    f.write(f'@echo off\n')
                    f.write(f'cd /d "{cwd}"\n')
                    if is_frozen:
                        # In frozen (.exe) mode, sys.executable IS the .exe
                        exe_path = os.path.abspath(sys.executable)
                        f.write(f'start "{preset_name} - MudaRemote" "{exe_path}" --preset "{preset_name}"\n')
                    else:
                        # In script (.py) mode, launch python with the bot script
                        python_exe = sys.executable
                        bot_script = os.path.join(cwd, BOT_SCRIPT)
                        f.write(f'start "{preset_name} - MudaRemote" "{python_exe}" "{bot_script}" --preset "{preset_name}"\n')
            except Exception as e:
                print(f"Failed to create autostart script: {e}")
        else:
            if os.path.exists(bat_path):
                try:
                    os.remove(bat_path)
                except Exception as e:
                    print(f"Failed to remove autostart script: {e}")
    
    def create_preset(self):
        """Create a new preset."""
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
                "enable_snipe_chat_reactions": False,
                "snipe_chat_messages": ["omg", "ezz"],
                "sphere_click_targets": ["spG", "spY", "spO", "spR", "spW", "spL", "spD", "spM", "spU"],
                "immediate_kakera_click": True,
                "character_snipe_targets": [],
            }
            
            self.refresh_preset_list()
            self.select_preset(name)
    
    def duplicate_preset(self):
        """Duplicate the current preset."""
        if not self.current_preset:
            messagebox.showwarning("Warning", "No preset selected.")
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
            
            self.refresh_preset_list()
            self.select_preset(name)

    def share_preset(self):
        """Export the currently selected preset to the clipboard without exposing the token."""
        if not self.current_preset:
            messagebox.showwarning("Warning", "No preset selected.")
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
            self._manage_autostart(self.current_preset, False)
            del self.presets[self.current_preset]
            self.save_presets()
            self.current_preset = None
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
        
        # Save first
        self.save_current_preset()
        
        is_frozen = getattr(sys, 'frozen', False)
        
        if not is_frozen:
            # In script mode, verify bot script exists on disk
            if not os.path.exists(BOT_SCRIPT):
                messagebox.showerror("Error", f"{BOT_SCRIPT} not found in current directory.")
                return
        
        try:
            if is_frozen:
                # In frozen (.exe) mode, sys.executable IS the .exe itself.
                # We relaunch the same .exe with --preset to run in headless bot mode.
                if sys.platform == "win32":
                    subprocess.Popen(
                        [sys.executable, "--preset", self.current_preset],
                        creationflags=subprocess.CREATE_NEW_CONSOLE
                    )
                else:
                    subprocess.Popen([sys.executable, "--preset", self.current_preset])
            else:
                # In script (.py) mode, launch python with the bot script
                if sys.platform == "win32":
                    subprocess.Popen(
                        [sys.executable, BOT_SCRIPT, "--preset", self.current_preset],
                        creationflags=subprocess.CREATE_NEW_CONSOLE
                    )
                else:
                    subprocess.Popen([sys.executable, BOT_SCRIPT, "--preset", self.current_preset])
            
            messagebox.showinfo("Bot Started", 
                               f"Bot started with preset '{self.current_preset}'.\n"
                               "A new terminal window should open.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to start bot:\n{e}")


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


def run_headless(preset_names):
    """
    Headless mode: import mudae_bot and run specified presets in threads.
    Used when the .exe (or script) is launched with --preset or --all.
    """
    import mudae_bot
    
    # Load presets from disk (mudae_bot already ensures it exists on import)
    try:
        with open(PRESETS_FILE, "r", encoding="utf-8") as f:
            all_presets = json.load(f)
    except (json.JSONDecodeError, Exception) as e:
        print(f"[MudaRemote] Failed to load {PRESETS_FILE}: {e}")
        sys.exit(1)
    
    threads = []
    for name in preset_names:
        if name not in all_presets:
            print(f"[MudaRemote] Preset '{name}' not found. Skipping.")
            continue
        print(f"[MudaRemote] Starting preset: {name}")
        t = mudae_bot.start_preset_thread(name, all_presets[name])
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
        run_headless(preset_names)
    
    elif args.preset:
        # Run specific preset(s) in headless mode
        print(f"[MudaRemote] Running preset(s): {', '.join(args.preset)}")
        run_headless(args.preset)
    
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