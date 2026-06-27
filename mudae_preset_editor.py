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
    "mk_bypass_power_check": False,
    "snipe_channels": [],
    "max_like_rank": 0,
    "enable_hybrid_panic_claim": False,
    "hybrid_panic_instant_claim_min_kakera": 300,
    "hybrid_panic_instant_claim_max_rank": 200,
    "claim_rounds_thresholds": [],
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
    ("snipe_channels", "Target Snipe Channels (Comma-separated IDs of external channels to monitor for sniping)", [], True),
]

# Default emoji values
DEFAULT_CLAIM_EMOJIS = ['💖', '💗', '💘', '❤️', '💓', '💕', '♥️']
DEFAULT_KAKERA_EMOJIS = ['kakeraY', 'kakeraO', 'kakeraR', 'kakeraW', 'kakeraL', 'kakeraP', 'kakeraD', 'kakeraC']
DEFAULT_CHAOS_EMOJIS = ['kakeraY', 'kakeraO', 'kakeraR', 'kakeraW', 'kakeraL', 'kakeraP', 'kakeraD', 'kakeraC']
DEFAULT_SPHERE_PERK_EMOJIS = ['kakeraY', 'kakeraO', 'kakeraR', 'kakeraW', 'kakeraL', 'kakeraP', 'kakeraD', 'kakeraC']

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
        
        # Load presets
        self.load_presets()
        
        # Build UI
        self.build_ui()
        
        # Select first preset if exists
        if self.presets:
            first_preset = list(self.presets.keys())[0]
            self.select_preset(first_preset)
    
    def apply_theme(self):
        """Apply a dark theme to the application."""
        self.root.configure(bg="#1e1e2e")
        
        style = ttk.Style()
        style.theme_use("clam")
        
        # Colors
        bg_dark = "#1e1e2e"
        bg_mid = "#2d2d3f"
        bg_light = "#3d3d5c"
        fg = "#cdd6f4"
        fg_dim = "#a6adc8"
        accent = "#89b4fa"
        accent_hover = "#b4befe"
        danger = "#f38ba8"
        success = "#a6e3a1"
        
        # Configure styles
        style.configure(".", background=bg_dark, foreground=fg, fieldbackground=bg_mid)
        style.configure("TFrame", background=bg_dark)
        style.configure("TLabel", background=bg_dark, foreground=fg, font=("Segoe UI", 10))
        style.configure("TLabelframe", background=bg_dark, foreground=fg)
        style.configure("TLabelframe.Label", background=bg_dark, foreground=accent, font=("Segoe UI", 11, "bold"))
        style.configure("TEntry", fieldbackground=bg_mid, foreground=fg, insertcolor=fg)
        style.configure("TCheckbutton", background=bg_dark, foreground=fg, font=("Segoe UI", 10))
        style.map("TCheckbutton", background=[("active", bg_mid)])
        style.configure("TButton", background=bg_light, foreground=fg, font=("Segoe UI", 10, "bold"), padding=8)
        style.map("TButton", background=[("active", accent), ("pressed", accent_hover)])
        style.configure("Accent.TButton", background=accent, foreground=bg_dark)
        style.map("Accent.TButton", background=[("active", accent_hover)])
        style.configure("Danger.TButton", background=danger, foreground=bg_dark)
        style.map("Danger.TButton", background=[("active", "#eba0ac")])
        style.configure("Success.TButton", background=success, foreground=bg_dark)
        style.map("Success.TButton", background=[("active", "#b5e8b0")])
        
        # Listbox styling (not ttk, so manual)
        self.listbox_config = {
            "bg": bg_mid,
            "fg": fg,
            "selectbackground": accent,
            "selectforeground": bg_dark,
            "font": ("Segoe UI", 11),
            "borderwidth": 0,
            "highlightthickness": 0,
        }
    
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
        """Build the main UI."""
        # Main container
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Left sidebar - Preset list
        sidebar = ttk.Frame(main_frame, width=200)
        sidebar.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        sidebar.pack_propagate(False)
        
        ttk.Label(sidebar, text="Bot Configurations", font=("Segoe UI", 14, "bold")).pack(anchor=tk.W, pady=(0, 10))
        
        # Preset listbox
        self.preset_listbox = tk.Listbox(sidebar, **self.listbox_config, height=20)
        self.preset_listbox.pack(fill=tk.BOTH, expand=True)
        self.preset_listbox.bind("<<ListboxSelect>>", self.on_preset_select)
        
        # Refresh preset list
        self.refresh_preset_list()
        
        # Sidebar buttons
        sidebar_btns = ttk.Frame(sidebar)
        sidebar_btns.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(sidebar_btns, text="+ Create New", command=self.create_preset).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        ttk.Button(sidebar_btns, text="Copy Selected", command=self.duplicate_preset).pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Right side - Settings panel
        self.settings_container = ttk.Frame(main_frame)
        self.settings_container.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Canvas for scrolling
        self.canvas = tk.Canvas(self.settings_container, bg="#1e1e2e", highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.settings_container, orient=tk.VERTICAL, command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)
        
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
            lbl = ttk.Label(self.rounds_frame, text=text, font=("Segoe UI", 9, "bold"))
            lbl.grid(row=0, column=col_idx, padx=5, pady=2, sticky=tk.W)

        # Generate exactly num_rounds input rows
        for i in range(1, num_rounds + 1):
            lbl_round = ttk.Label(self.rounds_frame, text=f"Round {i} (Hour {i})", font=("Segoe UI", 9))
            lbl_round.grid(row=i, column=0, padx=5, pady=2, sticky=tk.W)

            ent_min_k = ttk.Entry(self.rounds_frame, width=12)
            ent_min_k.grid(row=i, column=1, padx=5, pady=2, sticky=tk.W)
            self.widgets[f"round_{i}_min_kakera"] = ent_min_k

            ent_max_claim = ttk.Entry(self.rounds_frame, width=12)
            ent_max_claim.grid(row=i, column=2, padx=5, pady=2, sticky=tk.W)
            self.widgets[f"round_{i}_max_claim_rank"] = ent_max_claim

            ent_max_like = ttk.Entry(self.rounds_frame, width=12)
            ent_max_like.grid(row=i, column=3, padx=5, pady=2, sticky=tk.W)
            self.widgets[f"round_{i}_max_like_rank"] = ent_max_like
    
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
        
        # Title
        self.title_label = ttk.Label(frame, text="Select a config to start", font=("Segoe UI", 18, "bold"))
        self.title_label.pack(anchor=tk.W, pady=(0, 20))
        
        # --- Connection ---
        core_frame = ttk.LabelFrame(frame, text="Connection (Essential Setup)", padding=15)
        core_frame.pack(fill=tk.X, pady=(0, 15))
        
        self.add_text_field(core_frame, "token", "Discord Account Token (REQUIRED: Your secret account key)", show="*")
        self.add_text_field(core_frame, "channel_id", "Discord Channel ID (Where the bot should roll)")
        self.add_text_field(core_frame, "command_channel_id", "Command Channel ID (Optional: For $tu, $daily, $dk — leave empty to use roll channel)")
        
        prefix_row = ttk.Frame(core_frame)
        prefix_row.pack(fill=tk.X, pady=5)
        self.add_text_field(prefix_row, "prefix", "Self-Bot Prefix", pack_side=tk.LEFT)
        self.add_text_field(prefix_row, "mudae_prefix", "Mudae Game Prefix", pack_side=tk.LEFT)
        
        self.add_text_field(core_frame, "roll_command", "Roll Type (wa, ha, ma, etc.)")
        self.add_number_field(core_frame, "delay_seconds", "Wait Time Before Checking Commands (seconds)", 0)
        self.add_number_field(core_frame, "start_delay", "Wait Before Starting (seconds)", 0)
        self.add_checkbox(core_frame, "autostart", "Start with Windows")
        
        # --- Rolling ---
        roll_outer = ttk.Frame(frame)
        roll_outer.pack(fill=tk.X, pady=(0, 15))
        roll_frame = ttk.LabelFrame(roll_outer, text="Rolling Options", padding=15)
        roll_frame.pack(fill=tk.X)
        
        rolling_var = self.add_checkbox(roll_frame, "rolling", "Rolling Enabled (Turn off to only snipe without rolling yourself)")
        roll_sub = self.create_subframe(roll_frame, rolling_var)
        
        self.add_checkbox(roll_sub, "use_slash_rolls", "Use /slash commands (Earn 10% more Kakera)")
        self.add_number_field(roll_sub, "roll_speed", "Rolling Speed (Seconds between each roll)", 0.4)
        self.add_number_field(roll_sub, "roll_interval", "Roll Timer (Minutes until your rolls refresh)", 60)
        self.add_checkbox(roll_sub, "time_rolls_to_claim_reset", "Smart Timing (Finish rolling exactly when your claim resets)")
        
        auto_rolls_var = self.add_checkbox(roll_sub, "auto_rolls_enabled", "Automatically Use Daily Rolls ($rolls)")
        auto_rolls_sub = self.create_subframe(roll_sub, auto_rolls_var)
        self.add_number_field(auto_rolls_sub, "auto_rolls_limit", "Maximum times to use daily rolls (0 = unlimited)", 0)
        self.add_checkbox(auto_rolls_sub, "auto_rolls_only_claim_hour", "Only Use Daily Rolls in Claim Hour")
        
        self.add_checkbox(roll_sub, "auto_rolls_in_key_mode", "Use Daily Rolls for Keys (Use $rolls even when you can't claim)")
        
        # --- Stacked Rolls ($us) ---
        us_outer = ttk.Frame(frame)
        us_outer.pack(fill=tk.X, pady=(0, 15))
        us_frame = ttk.LabelFrame(us_outer, text="Saved Rolls ($us)", padding=15)
        us_frame.pack(fill=tk.X)
        
        us_enabled_var = self.add_checkbox(us_frame, "auto_us_enabled", "Automatically Use Saved Rolls ($us)")
        us_sub = self.create_subframe(us_frame, us_enabled_var)
        
        self.add_checkbox(us_sub, "bulk_us_enabled", "Bulk US Mode (Pull all rolls at once instead of in batches of 20)")
        self.add_checkbox(us_sub, "auto_us_stop_on_claim", "Save Rolls (Stop using $us after claim)")
        self.add_number_field(us_sub, "auto_us_limit", "Maximum Saved Rolls to Use per Hour", 0)
        self.add_checkbox(us_frame, "auto_mk_enabled", "Automatically Use Extra Kakera Rolls ($mk)")
        self.add_checkbox(us_frame, "mk_bypass_power_check", "Force $mk Rolls (Use $mk even when power is too low for normal kakera)")
        
        # --- Claiming ---
        claim_frame = ttk.LabelFrame(frame, text="Claim Rules", padding=15)
        claim_frame.pack(fill=tk.X, pady=(0, 15))
        
        self.add_number_field(claim_frame, "min_kakera", "Minimum Value to Claim (Claim if character is worth this much)", 100)
        claim_interval_entry = self.add_number_field(claim_frame, "claim_interval", "Claim Timer (Minutes until you get a new claim right)", 180)
        self.add_number_field(claim_frame, "max_claim_rank", "Maximum Claims Rank Limit (e.g. 500 to claim any character ranked #1-#500. 0 = disabled)", 0)
        self.add_number_field(claim_frame, "max_like_rank", "Maximum Likes Rank Limit (e.g. 300 to claim any character ranked #1-#300. 0 = disabled)", 0)
        self.add_checkbox(claim_frame, "lurker_mode", "Lurker Strategy (Wait for others to roll while sniping - Panic dump at the end)")
        self.add_number_field(claim_frame, "panic_roll_minutes", "Panic Roll When No Claim In Snipe Mode (Minutes before reset)", 5)
        self.add_checkbox(claim_frame, "key_mode", "Key Farming Mode (Keep rolling to earn keys even if you can't claim)")
        self.add_checkbox(claim_frame, "auto_rt_after_claim", "Auto $rt After Claim (Instantly reset your claim timer after a successful claim)")
        
        # Hybrid Smart Panic Claim
        hybrid_var = self.add_checkbox(claim_frame, "enable_hybrid_panic_claim", "Hybrid Smart Panic Claim (Instantly claim high-value characters in the last claim hour, collect others)")
        hybrid_sub = self.create_subframe(claim_frame, hybrid_var)
        self.add_number_field(hybrid_sub, "hybrid_panic_instant_claim_min_kakera", "Hybrid Instant Claim Min Kakera (Minimum value to claim instantly in panic hour)", 300)
        self.add_number_field(hybrid_sub, "hybrid_panic_instant_claim_max_rank", "Hybrid Instant Claim Max Rank Limit (Rank <= this to claim instantly in panic hour)", 200)

        # claim_rounds_thresholds
        self.rounds_frame = ttk.LabelFrame(claim_frame, text="Dynamic Cooldown Rounds (Hourly Thresholds)", padding=10)
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
        
        # --- Sniping ---
        snipe_outer = ttk.Frame(frame)
        snipe_outer.pack(fill=tk.X, pady=(0, 15))
        snipe_frame = ttk.LabelFrame(snipe_outer, text="Sniping & Stealing", padding=15)
        snipe_frame.pack(fill=tk.X)
        
        snipe_mode_var = self.add_checkbox(snipe_frame, "snipe_mode", "Snipe Characters (Claim characters rolled by other people)")
        snipe_sub = self.create_subframe(snipe_frame, snipe_mode_var)
        self.add_number_field(snipe_sub, "snipe_delay", "Snipe Wait Time (Wait X seconds before stealing a roll)", 2)
        self.add_checkbox(snipe_sub, "snipe_ignore_min_kakera_reset", "Panic Claim (Claim ANY character right before your timer resets)")
        self.add_list_field(snipe_sub, "snipe_channels", "Target Snipe Channels (Comma-separated IDs of external channels to monitor for sniping)")
        
        reactive_snipe_var = self.add_checkbox(snipe_frame, "reactive_snipe_on_own_rolls", "Instant Self-Claim (Immediately claim your own good rolls)")
        reactive_sub = self.create_subframe(snipe_frame, reactive_snipe_var)
        self.add_number_field(reactive_sub, "reactive_snipe_delay", "Self-Claim Delay (Seconds to wait before claiming your own rolls)", 0)
        
        # Series snipe
        series_snipe_var = self.add_checkbox(snipe_frame, "series_snipe_mode", "Series Sniping (Auto-claim any character from specific shows/games)")
        series_sub = self.create_subframe(snipe_frame, series_snipe_var)
        self.add_number_field(series_sub, "series_snipe_delay", "Series Snipe Wait Time (Wait X seconds before stealing from series)", 3)
        self.add_list_field(series_sub, "series_wishlist", "Series Wishlist (Shows or Games you want to auto-claim)")
        
        # Kakera snipe
        kakera_snipe_var = self.add_checkbox(snipe_frame, "kakera_snipe_mode", "Value Sniping (Snipe expensive characters rolled by others)")
        kakera_sub = self.create_subframe(snipe_frame, kakera_snipe_var)
        self.add_number_field(kakera_sub, "kakera_snipe_threshold", "Minimum Value to Steal (Only steal if worth this much)", 0)
        
        kakera_react_snipe_var = self.add_checkbox(snipe_frame, "kakera_reaction_snipe_mode", "Auto-Collect Kakera (Click crystals on other people's rolls)")
        kakera_react_sub = self.create_subframe(snipe_frame, kakera_react_snipe_var)
        self.add_number_field(kakera_react_sub, "kakera_reaction_snipe_delay", "Kakera Collection Delay (How fast to click others' crystals)", 0.75)
        self.add_list_field(kakera_react_sub, "kakera_reaction_snipe_targets", "Target User IDs (Only steal Kakera from these specific users)")
        
        self.add_checkbox(snipe_frame, "only_chaos", "Chaos Kakera Only (Only click crystals that cost 50% less power)")
        self.add_checkbox(snipe_frame, "mk_only", "MK Kakera Only (Ignore normal kakera, ONLY click crystals from your $mk rolls)")
        
        # $rt settings
        self.add_checkbox(snipe_frame, "rt_only_self_rolls", "Private Restore (Only use $rt on characters YOU rolled)")
        self.add_checkbox(snipe_frame, "rt_ignore_min_kakera_for_wishlist", "Restore for Wishlist (Use $rt for wishlisted characters regardless of value)")
        
        # Snipe Chat Reactions
        enable_chat_var = self.add_checkbox(snipe_frame, "enable_snipe_chat_reactions", "Snipe Chat Reactions (Send a random message after a successful external snipe)")
        chat_sub = self.create_subframe(snipe_frame, enable_chat_var)
        self.add_list_field(chat_sub, "snipe_chat_messages", "Snipe Chat Messages (Comma-separated, e.g., omg, ezz, yay)")
        
        self.add_checkbox(snipe_frame, "op_perk_5_only", "Only Click Kakera on $op (Perk 5) Characters")
        
        # --- Wishlists & Filters ---
        list_frame = ttk.LabelFrame(frame, text="Wishlists & Ignored Characters", padding=15)
        list_frame.pack(fill=tk.X, pady=(0, 15))
        
        self.add_list_field(list_frame, "wishlist", "Character Wishlist (Names of characters you want to auto-claim)")
        self.add_list_field(list_frame, "avoid_list", "Blacklisted Characters (Names of characters to NEVER claim)")
        
        farm_var = self.add_checkbox(list_frame, "farm_character_enabled", "Enable Kakera Farming Loop (Auto-Forcedivorce)")
        farm_sub = self.create_subframe(list_frame, farm_var)
        self.add_text_field(farm_sub, "farm_character", "Kakera Farm Character (Name of character to endlessly farm)")
        
        # --- Auto-Divorce ---
        divorce_var = self.add_checkbox(list_frame, "auto_divorce_enabled", "Auto-Divorce (Automatically separate low-value characters after claiming)")
        divorce_sub = self.create_subframe(list_frame, divorce_var)
        self.add_number_field(divorce_sub, "auto_divorce_max_kakera", "Kakera Threshold (Divorce if character value ≤ this)", 50)
        self.add_list_field(divorce_sub, "auto_divorce_series", "Divorce Series List (Always divorce characters from these series)")
        
        # --- Emoji Settings ---
        emoji_frame = ttk.LabelFrame(frame, text="Custom Emojis (Advanced)", padding=15)
        emoji_frame.pack(fill=tk.X, pady=(0, 15))
        
        ttk.Label(emoji_frame, text="Uncheck to use defaults. Check with empty field to disable.", 
                 foreground="#a6adc8", font=("Segoe UI", 9)).pack(anchor=tk.W, pady=(0, 10))
        
        self.add_optional_list_field(emoji_frame, "claim_emojis", "Claim Emojis", 
                                     ", ".join(DEFAULT_CLAIM_EMOJIS))
        self.add_optional_list_field(emoji_frame, "kakera_emojis", "Kakera Emojis", 
                                     ", ".join(DEFAULT_KAKERA_EMOJIS))
        self.add_optional_list_field(emoji_frame, "chaos_emojis", "Chaos Emojis", 
                                     ", ".join(DEFAULT_CHAOS_EMOJIS))
        self.add_optional_list_field(emoji_frame, "sphere_perk_emojis", "Sphere Perk Emojis", 
                                     ", ".join(DEFAULT_SPHERE_PERK_EMOJIS))
        
        # [NEW] Task 5: Randomized claim reaction emojis
        self.add_list_field(emoji_frame, "randomized_claim_reactions", "Claim Reaction Emojis (Randomized fallback emojis for claims without buttons)")
        
        # [NEW] Task 8: Customizable kakera/sphere priority map
        self.add_list_field(emoji_frame, "kakera_priority_order", "Kakera Priority Order (Highest priority first, comma-separated)")
        ttk.Label(emoji_frame, text="Default: kakeraP, kakeraC, kakeraL, kakeraW, kakeraR, kakeraO, kakeraD, kakeraY, kakeraG, kakeraT, kakera",
                 foreground="#a6adc8", font=("Segoe UI", 9)).pack(anchor=tk.W)
        
        # --- Anti-Detection ---
        human_outer = ttk.Frame(frame)
        human_outer.pack(fill=tk.X, pady=(0, 15))
        human_frame = ttk.LabelFrame(human_outer, text="Anti-Ban (Stealth Mode)", padding=15)
        human_frame.pack(fill=tk.X)
        
        human_var = self.add_checkbox(human_frame, "humanization_enabled", "Anti-Ban Stealth (Randomizes timing to look like a real human)")
        human_sub = self.create_subframe(human_frame, human_var)
        
        self.add_number_field(human_sub, "humanization_window_minutes", "Random Wait Time (minutes) to Look Like a Real Human", 40)
        self.add_number_field(human_sub, "humanization_inactivity_seconds", "Patience (Wait for X seconds of no chat before rolling)", 5)
        
        # Inactive hours
        inactive_row = ttk.Frame(human_sub)
        inactive_row.pack(fill=tk.X, pady=5)
        ttk.Label(inactive_row, text="Bot Sleep Schedule (e.g. 1-7, 23-6):").pack(anchor=tk.W)
        ttk.Label(inactive_row, text="The bot will not roll during these hours (uses your local time)",
                 foreground="#a6adc8", font=("Segoe UI", 9)).pack(anchor=tk.W)
        inactive_entry = ttk.Entry(inactive_row)
        inactive_entry.pack(fill=tk.X)
        self.widgets["inactive_hours"] = inactive_entry
        
        # Reactive kakera delay range
        range_row = ttk.Frame(human_sub)
        range_row.pack(fill=tk.X, pady=5)
        ttk.Label(range_row, text="Self-Roll Kakera Delay (Random wait range in seconds):").pack(anchor=tk.W)
        range_inputs = ttk.Frame(range_row)
        range_inputs.pack(fill=tk.X)
        
        self.widgets["reactive_kakera_delay_min"] = ttk.Entry(range_inputs, width=10)
        self.widgets["reactive_kakera_delay_min"].pack(side=tk.LEFT, padx=(0, 5))
        ttk.Label(range_inputs, text="to").pack(side=tk.LEFT, padx=5)
        self.widgets["reactive_kakera_delay_max"] = ttk.Entry(range_inputs, width=10)
        self.widgets["reactive_kakera_delay_max"].pack(side=tk.LEFT, padx=(5, 0))
        
        # --- Advanced ---
        power_frame = ttk.LabelFrame(frame, text="Power & Expert Settings", padding=15)
        power_frame.pack(fill=tk.X, pady=(0, 15))
        
        self.add_checkbox(power_frame, "auto_dk_enabled", "Auto $dk (Automatically use $dk when ready or low on power)")
        self.add_checkbox(power_frame, "auto_p_enabled", "Auto $p (Automatically claim pokemon when available)")
        self.add_checkbox(power_frame, "dk_power_management", "Smart Power Refill (Auto-use $dk when low on energy)")
        # [NEW] Task 1: Max DK Power setting
        self.add_number_field(power_frame, "max_dk_power", "Maximum DK Power % (Default 100, increase for late-game users)", 100)
        self.add_checkbox(power_frame, "skip_initial_commands", "Fast Start (Skip initial setup commands on startup)")
        self.add_text_field(power_frame, "kakera_power_thresholds", "Min Power per Kakera (e.g. kakeraY:80, chaos_kakeraY:50)")
        self.add_checkbox(power_frame, "debug_mode", "Expert Logs (Show technical data for every single roll)")
        
        # [NEW] Task 6: Main account ID for wishlist syncing
        self.add_text_field(power_frame, "main_account_id", "Main Account ID (Alt accounts will auto-claim wishlist characters rolled by this account)")
        
        # [NEW] Task 7: Scheduled roll times
        sched_row = ttk.Frame(power_frame)
        sched_row.pack(fill=tk.X, pady=5)
        ttk.Label(sched_row, text="Scheduled Roll Times (e.g. 14:00, 18:30 — comma-separated, 24h format):").pack(anchor=tk.W)
        ttk.Label(sched_row, text="If set, the bot will roll at these specific times instead of interval loops. Respects humanization.",
                 foreground="#a6adc8", font=("Segoe UI", 9)).pack(anchor=tk.W)
        sched_entry = ttk.Entry(sched_row)
        sched_entry.pack(fill=tk.X)
        self.widgets["scheduled_roll_times"] = sched_entry
        
        # --- Action Buttons ---
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=20)
        
        ttk.Button(btn_frame, text="💾 Save Changes", style="Accent.TButton", 
                  command=self.save_current_preset).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(btn_frame, text="▶ Launch Bot", style="Success.TButton",
                  command=self.run_bot).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(btn_frame, text="🗑 Delete Config", style="Danger.TButton",
                  command=self.delete_preset).pack(side=tk.RIGHT)
    
    def add_text_field(self, parent, key, label, show=None, pack_side=None):
        """Add a text entry field."""
        container = ttk.Frame(parent)
        if pack_side:
            container.pack(side=pack_side, fill=tk.X, expand=True, padx=5, pady=5)
        else:
            container.pack(fill=tk.X, pady=5)
        
        ttk.Label(container, text=label).pack(anchor=tk.W)
        entry = ttk.Entry(container, show=show)
        entry.pack(fill=tk.X)
        self.widgets[key] = entry
    
    def add_number_field(self, parent, key, label, default):
        """Add a numeric entry field."""
        container = ttk.Frame(parent)
        container.pack(fill=tk.X, pady=5)
        
        ttk.Label(container, text=f"{label} (default: {default})").pack(anchor=tk.W)
        entry = ttk.Entry(container, width=15)
        entry.pack(anchor=tk.W)
        self.widgets[key] = entry
        return entry
    
    def add_checkbox(self, parent, key, label):
        """Add a checkbox."""
        var = tk.BooleanVar()
        cb = ttk.Checkbutton(parent, text=label, variable=var)
        cb.pack(anchor=tk.W, pady=2)
        self.widgets[key] = var
        return var

    def create_subframe(self, parent, var):
        """Create a subframe that shows/hides based on a BooleanVar."""
        subframe = ttk.Frame(parent)
        
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
    
    def add_list_field(self, parent, key, label):
        """Add a comma-separated list field."""
        container = ttk.Frame(parent)
        container.pack(fill=tk.X, pady=5)
        
        ttk.Label(container, text=label).pack(anchor=tk.W)
        entry = ttk.Entry(container)
        entry.pack(fill=tk.X)
        self.widgets[key] = entry
    
    def add_optional_list_field(self, parent, key, label, placeholder):
        """Add an optional list field with checkbox to enable/disable."""
        container = ttk.Frame(parent)
        container.pack(fill=tk.X, pady=5)
        
        # Checkbox to enable
        var = tk.BooleanVar()
        cb = ttk.Checkbutton(container, text=label, variable=var)
        cb.pack(anchor=tk.W)
        
        # Entry for values
        entry = ttk.Entry(container)
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
        
        self.widgets[f"{key}_enabled"] = var
        self.widgets[key] = entry
    
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
                if isinstance(widget, ttk.Entry):
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
                    "enable_hybrid_panic_claim"]:
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
                    "snipe_chat_messages", "auto_divorce_series", "snipe_channels"]:
            if key in self.widgets:
                widget = self.widgets[key]
                if isinstance(widget, ttk.Entry):
                    widget.delete(0, tk.END)
                    value = data.get(key, [])
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
                    "enable_hybrid_panic_claim"]:
            if key in self.widgets:
                data[key] = self.widgets[key].get()
        
        # Collect list fields
        # [NEW] Include randomized_claim_reactions and kakera_priority_order in list collection
        for key in ["wishlist", "series_wishlist", "avoid_list", "kakera_reaction_snipe_targets",
                    "randomized_claim_reactions", "kakera_priority_order",
                    "snipe_chat_messages", "auto_divorce_series", "snipe_channels"]:
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