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

# --- Constants ---
PRESETS_FILE = "presets.json"
BOT_SCRIPT = "mudae_bot.py"

# Default values (for display hints)
DEFAULTS = {
    "token": "",
    "prefix": "/////////////",
    "mudae_prefix": "$",
    "channel_id": "",
    "roll_command": "wa",
    "min_kakera": 100,
    "delay_seconds": 0,
    "start_delay": 0,
    "roll_speed": 0.4,
    "snipe_delay": 2,
    "series_snipe_delay": 3,
    "kakera_snipe_threshold": 0,
    "kakera_reaction_snipe_delay": 0.75,
    "humanization_window_minutes": 40,
    "humanization_inactivity_seconds": 5,
    "reactive_snipe_delay": 0,
    "reactive_kakera_delay_range": [0.3, 1.0],
}

# Boolean settings with their display names and defaults
BOOL_SETTINGS = [
    ("rolling", "Enable Rolling", True),
    ("use_slash_rolls", "Use Slash Commands", False),
    ("snipe_mode", "Snipe Mode", False),
    ("snipe_ignore_min_kakera_reset", "Snipe: Ignore Min Kakera on Reset", False),
    ("series_snipe_mode", "Series Snipe Mode", False),
    ("kakera_snipe_mode", "Kakera Value Snipe Mode", False),
    ("kakera_reaction_snipe_mode", "Kakera Reaction Snipe Mode", False),
    ("reactive_snipe_on_own_rolls", "Reactive Snipe on Own Rolls", True),
    ("key_mode", "Key Mode (Always Claim)", False),
    ("only_chaos", "Only Chaos Kakera", False),
    ("humanization_enabled", "Humanization Enabled", False),
    ("dk_power_management", "DK Power Management", False),
    ("skip_initial_commands", "Skip Initial Commands", False),
    ("time_rolls_to_claim_reset", "Time Rolls to Claim Reset", False),
    ("rt_ignore_min_kakera_for_wishlist", "RT: Ignore Min Kakera for Wishlist", False),
    ("rt_only_self_rolls", "RT: Only Self Rolls", False),
]

# Numeric settings with their display names, defaults, and types
NUMERIC_SETTINGS = [
    ("min_kakera", "Minimum Kakera", 100, int),
    ("delay_seconds", "Delay Between Rolls (s)", 0, float),
    ("start_delay", "Start Delay (s)", 0, int),
    ("roll_speed", "Roll Speed (s)", 0.4, float),
    ("snipe_delay", "Snipe Delay (s)", 2, float),
    ("series_snipe_delay", "Series Snipe Delay (s)", 3, float),
    ("kakera_snipe_threshold", "Kakera Snipe Threshold", 0, int),
    ("kakera_reaction_snipe_delay", "Kakera Reaction Snipe Delay (s)", 0.75, float),
    ("humanization_window_minutes", "Humanization Window (min)", 40, int),
    ("humanization_inactivity_seconds", "Humanization Inactivity (s)", 5, int),
    ("reactive_snipe_delay", "Reactive Snipe Delay (s)", 0, float),
]

# Text/list settings
TEXT_SETTINGS = [
    ("token", "Discord Token", "", False),  # (key, label, default, is_list)
    ("prefix", "Bot Prefix", "/////////////", False),
    ("mudae_prefix", "Mudae Prefix", "$", False),
    ("channel_id", "Channel ID", "", False),
    ("roll_command", "Roll Command", "wa", False),
    ("wishlist", "Wishlist (comma-separated)", [], True),
    ("series_wishlist", "Series Wishlist (comma-separated)", [], True),
    ("kakera_reaction_snipe_targets", "Kakera Snipe Targets (comma-separated)", [], True),
]

# Default emoji values
DEFAULT_CLAIM_EMOJIS = ['💖', '💗', '💘', '❤️', '💓', '💕', '♥️']
DEFAULT_KAKERA_EMOJIS = ['kakeraY', 'kakeraO', 'kakeraR', 'kakeraW', 'kakeraL', 'kakeraP', 'kakeraD', 'kakeraC']
DEFAULT_CHAOS_EMOJIS = ['kakeraY', 'kakeraO', 'kakeraR', 'kakeraW', 'kakeraL', 'kakeraP', 'kakeraD', 'kakeraC']


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
                messagebox.showerror("Error", f"Failed to parse {PRESETS_FILE}:\n{e}")
                self.presets = {}
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load {PRESETS_FILE}:\n{e}")
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
            messagebox.showerror("Error", f"Failed to save {PRESETS_FILE}:\n{e}")
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
        
        ttk.Label(sidebar, text="Presets", font=("Segoe UI", 14, "bold")).pack(anchor=tk.W, pady=(0, 10))
        
        # Preset listbox
        self.preset_listbox = tk.Listbox(sidebar, **self.listbox_config, height=20)
        self.preset_listbox.pack(fill=tk.BOTH, expand=True)
        self.preset_listbox.bind("<<ListboxSelect>>", self.on_preset_select)
        
        # Refresh preset list
        self.refresh_preset_list()
        
        # Sidebar buttons
        sidebar_btns = ttk.Frame(sidebar)
        sidebar_btns.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(sidebar_btns, text="+ New", command=self.create_preset).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        ttk.Button(sidebar_btns, text="Duplicate", command=self.duplicate_preset).pack(side=tk.LEFT, fill=tk.X, expand=True)
        
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
        self.title_label = ttk.Label(frame, text="Select a preset", font=("Segoe UI", 18, "bold"))
        self.title_label.pack(anchor=tk.W, pady=(0, 20))
        
        # --- Core Settings ---
        core_frame = ttk.LabelFrame(frame, text="Core Settings", padding=15)
        core_frame.pack(fill=tk.X, pady=(0, 15))
        
        # Token
        self.add_text_field(core_frame, "token", "Discord Token", show="*")
        
        # Channel ID
        self.add_text_field(core_frame, "channel_id", "Channel ID")
        
        # Prefixes
        prefix_row = ttk.Frame(core_frame)
        prefix_row.pack(fill=tk.X, pady=5)
        self.add_text_field(prefix_row, "prefix", "Bot Prefix", pack_side=tk.LEFT)
        self.add_text_field(prefix_row, "mudae_prefix", "Mudae Prefix", pack_side=tk.LEFT)
        
        # Roll command
        self.add_text_field(core_frame, "roll_command", "Roll Command")
        
        # --- Rolling Settings ---
        roll_frame = ttk.LabelFrame(frame, text="Rolling Settings", padding=15)
        roll_frame.pack(fill=tk.X, pady=(0, 15))
        
        self.add_checkbox(roll_frame, "rolling", "Enable Rolling")
        self.add_checkbox(roll_frame, "use_slash_rolls", "Use Slash Commands")
        self.add_number_field(roll_frame, "roll_speed", "Roll Speed (seconds)", 0.4)
        self.add_number_field(roll_frame, "delay_seconds", "Delay Between Rolls (seconds)", 0)
        self.add_number_field(roll_frame, "start_delay", "Start Delay (seconds)", 0)
        self.add_checkbox(roll_frame, "time_rolls_to_claim_reset", "Time Rolls to Claim Reset")
        
        # --- Claim Settings ---
        claim_frame = ttk.LabelFrame(frame, text="Claim Settings", padding=15)
        claim_frame.pack(fill=tk.X, pady=(0, 15))
        
        self.add_number_field(claim_frame, "min_kakera", "Minimum Kakera", 100)
        self.add_checkbox(claim_frame, "key_mode", "Key Mode (Always Claim)")
        self.add_checkbox(claim_frame, "only_chaos", "Only Chaos Kakera")
        
        # --- Snipe Settings ---
        snipe_frame = ttk.LabelFrame(frame, text="Snipe Settings", padding=15)
        snipe_frame.pack(fill=tk.X, pady=(0, 15))
        
        self.add_checkbox(snipe_frame, "snipe_mode", "Snipe Mode")
        self.add_number_field(snipe_frame, "snipe_delay", "Snipe Delay (seconds)", 2)
        self.add_checkbox(snipe_frame, "snipe_ignore_min_kakera_reset", "Ignore Min Kakera on Reset")
        self.add_checkbox(snipe_frame, "reactive_snipe_on_own_rolls", "Reactive Snipe on Own Rolls")
        self.add_number_field(snipe_frame, "reactive_snipe_delay", "Reactive Snipe Delay (seconds)", 0)
        
        # Series snipe
        self.add_checkbox(snipe_frame, "series_snipe_mode", "Series Snipe Mode")
        self.add_number_field(snipe_frame, "series_snipe_delay", "Series Snipe Delay (seconds)", 3)
        
        # Kakera snipe
        self.add_checkbox(snipe_frame, "kakera_snipe_mode", "Kakera Value Snipe Mode")
        self.add_number_field(snipe_frame, "kakera_snipe_threshold", "Kakera Snipe Threshold", 0)
        self.add_checkbox(snipe_frame, "kakera_reaction_snipe_mode", "Kakera Reaction Snipe Mode")
        self.add_number_field(snipe_frame, "kakera_reaction_snipe_delay", "Kakera Reaction Snipe Delay (seconds)", 0.75)
        
        # RT settings
        self.add_checkbox(snipe_frame, "rt_only_self_rolls", "RT: Only Self Rolls")
        self.add_checkbox(snipe_frame, "rt_ignore_min_kakera_for_wishlist", "RT: Ignore Min Kakera for Wishlist")
        
        # --- Wishlists ---
        list_frame = ttk.LabelFrame(frame, text="Wishlists", padding=15)
        list_frame.pack(fill=tk.X, pady=(0, 15))
        
        self.add_list_field(list_frame, "wishlist", "Character Wishlist (comma-separated)")
        self.add_list_field(list_frame, "series_wishlist", "Series Wishlist (comma-separated)")
        self.add_list_field(list_frame, "kakera_reaction_snipe_targets", "Kakera Snipe Targets (comma-separated)")
        
        # --- Emoji Settings ---
        emoji_frame = ttk.LabelFrame(frame, text="Emoji Overrides", padding=15)
        emoji_frame.pack(fill=tk.X, pady=(0, 15))
        
        ttk.Label(emoji_frame, text="Uncheck to use defaults. Check with empty field to disable.", 
                 foreground="#a6adc8", font=("Segoe UI", 9)).pack(anchor=tk.W, pady=(0, 10))
        
        self.add_optional_list_field(emoji_frame, "claim_emojis", "Claim Emojis", 
                                     ", ".join(DEFAULT_CLAIM_EMOJIS))
        self.add_optional_list_field(emoji_frame, "kakera_emojis", "Kakera Emojis", 
                                     ", ".join(DEFAULT_KAKERA_EMOJIS))
        self.add_optional_list_field(emoji_frame, "chaos_emojis", "Chaos Emojis", 
                                     ", ".join(DEFAULT_CHAOS_EMOJIS))
        
        # --- Humanization ---
        human_frame = ttk.LabelFrame(frame, text="Humanization", padding=15)
        human_frame.pack(fill=tk.X, pady=(0, 15))
        
        self.add_checkbox(human_frame, "humanization_enabled", "Enable Humanization")
        self.add_number_field(human_frame, "humanization_window_minutes", "Activity Window (minutes)", 40)
        self.add_number_field(human_frame, "humanization_inactivity_seconds", "Inactivity Threshold (seconds)", 5)
        
        # Reactive kakera delay range
        range_row = ttk.Frame(human_frame)
        range_row.pack(fill=tk.X, pady=5)
        ttk.Label(range_row, text="Reactive Kakera Delay Range (seconds):").pack(anchor=tk.W)
        range_inputs = ttk.Frame(range_row)
        range_inputs.pack(fill=tk.X)
        
        self.widgets["reactive_kakera_delay_min"] = ttk.Entry(range_inputs, width=10)
        self.widgets["reactive_kakera_delay_min"].pack(side=tk.LEFT, padx=(0, 5))
        ttk.Label(range_inputs, text="to").pack(side=tk.LEFT, padx=5)
        self.widgets["reactive_kakera_delay_max"] = ttk.Entry(range_inputs, width=10)
        self.widgets["reactive_kakera_delay_max"].pack(side=tk.LEFT, padx=(5, 0))
        
        # --- Power Management ---
        power_frame = ttk.LabelFrame(frame, text="Power Management", padding=15)
        power_frame.pack(fill=tk.X, pady=(0, 15))
        
        self.add_checkbox(power_frame, "dk_power_management", "DK Power Management")
        self.add_checkbox(power_frame, "skip_initial_commands", "Skip Initial Commands")
        
        # --- Action Buttons ---
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=20)
        
        ttk.Button(btn_frame, text="💾 Save Preset", style="Accent.TButton", 
                  command=self.save_current_preset).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(btn_frame, text="▶ Run Bot", style="Success.TButton",
                  command=self.run_bot).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(btn_frame, text="🗑 Delete Preset", style="Danger.TButton",
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
    
    def add_checkbox(self, parent, key, label):
        """Add a checkbox."""
        var = tk.BooleanVar()
        cb = ttk.Checkbutton(parent, text=label, variable=var)
        cb.pack(anchor=tk.W, pady=2)
        self.widgets[key] = var
    
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
        for key in ["token", "prefix", "mudae_prefix", "channel_id", "roll_command", 
                    "min_kakera", "delay_seconds", "start_delay", "roll_speed",
                    "snipe_delay", "series_snipe_delay", "kakera_snipe_threshold",
                    "kakera_reaction_snipe_delay", "humanization_window_minutes",
                    "humanization_inactivity_seconds", "reactive_snipe_delay"]:
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
                    "rt_only_self_rolls"]:
            if key in self.widgets:
                var = self.widgets[key]
                if isinstance(var, tk.BooleanVar):
                    # Use default from BOOL_SETTINGS if key not in data
                    default = next((d for k, _, d in BOOL_SETTINGS if k == key), False)
                    var.set(data.get(key, default))
        
        # Populate list fields
        for key in ["wishlist", "series_wishlist", "kakera_reaction_snipe_targets"]:
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
                              ("chaos_emojis", DEFAULT_CHAOS_EMOJIS)]:
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
        
        # Populate reactive kakera delay range
        range_val = data.get("reactive_kakera_delay_range", [0.3, 1.0])
        if isinstance(range_val, (list, tuple)) and len(range_val) == 2:
            self.widgets["reactive_kakera_delay_min"].delete(0, tk.END)
            self.widgets["reactive_kakera_delay_min"].insert(0, str(range_val[0]))
            self.widgets["reactive_kakera_delay_max"].delete(0, tk.END)
            self.widgets["reactive_kakera_delay_max"].insert(0, str(range_val[1]))
        
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
        for key in ["token", "prefix", "mudae_prefix", "channel_id", "roll_command"]:
            if key in self.widgets:
                value = self.widgets[key].get().strip()
                if value:
                    # Special handling for channel_id
                    if key == "channel_id":
                        try:
                            data[key] = int(value)
                        except ValueError:
                            data[key] = value  # Store as string if not numeric
                    else:
                        data[key] = value
        
        # Collect numeric fields
        for key in ["min_kakera", "delay_seconds", "start_delay", "roll_speed",
                    "snipe_delay", "series_snipe_delay", "kakera_snipe_threshold",
                    "kakera_reaction_snipe_delay", "humanization_window_minutes",
                    "humanization_inactivity_seconds", "reactive_snipe_delay"]:
            if key in self.widgets:
                value = self.widgets[key].get().strip()
                if value:
                    try:
                        # Determine type
                        if key in ["min_kakera", "start_delay", "kakera_snipe_threshold",
                                   "humanization_window_minutes", "humanization_inactivity_seconds"]:
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
                    "rt_only_self_rolls"]:
            if key in self.widgets:
                data[key] = self.widgets[key].get()
        
        # Collect list fields
        for key in ["wishlist", "series_wishlist", "kakera_reaction_snipe_targets"]:
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
        for key in ["claim_emojis", "kakera_emojis", "chaos_emojis"]:
            enabled_key = f"{key}_enabled"
            if enabled_key in self.widgets and key in self.widgets:
                if self.widgets[enabled_key].get():  # Checkbox is checked
                    value = self.widgets[key].get().strip()
                    if value:
                        data[key] = [item.strip() for item in value.split(",") if item.strip()]
                    else:
                        data[key] = []  # Explicitly empty
                # else: checkbox unchecked, don't include key (use defaults)
        
        # Collect reactive kakera delay range
        try:
            min_val = float(self.widgets["reactive_kakera_delay_min"].get().strip() or "0.3")
            max_val = float(self.widgets["reactive_kakera_delay_max"].get().strip() or "1.0")
            data["reactive_kakera_delay_range"] = [min_val, max_val]
        except ValueError:
            data["reactive_kakera_delay_range"] = [0.3, 1.0]
        
        # Update and save
        self.presets[self.current_preset] = data
        if self.save_presets():
            messagebox.showinfo("Success", f"Preset '{self.current_preset}' saved!")
    
    def create_preset(self):
        """Create a new preset."""
        name = simpledialog.askstring("New Preset", "Enter preset name:", parent=self.root)
        if name:
            name = name.strip()
            if name in self.presets:
                messagebox.showwarning("Warning", f"Preset '{name}' already exists.")
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
                "rolling": True,
                "wishlist": [],
                "series_wishlist": [],
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
        
        # Check if bot script exists
        if not os.path.exists(BOT_SCRIPT):
            messagebox.showerror("Error", f"{BOT_SCRIPT} not found in current directory.")
            return
        
        try:
            # Launch in new console
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


def main():
    root = tk.Tk()
    app = PresetEditor(root)
    root.mainloop()


if __name__ == "__main__":
    main()
