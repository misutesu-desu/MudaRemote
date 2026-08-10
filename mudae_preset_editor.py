"""
MudaRemote Preset Editor
A graphical interface for managing mudae_bot.py presets.
"""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import copy
import json
import os
import subprocess
import sys
import argparse
import time
import threading
import math
import re

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


def get_mudae_emoji_asset_path(option):
    """Find bundled Fandom artwork first, while allowing Discord cache updates."""
    filename = f"{option}.png"
    external_path = os.path.join(get_base_path(), "mudae_emoji_assets", filename)
    if os.path.isfile(external_path):
        return external_path
    bundled_root = getattr(sys, "_MEIPASS", "")
    bundled_path = os.path.join(bundled_root, "mudae_emoji_assets", filename)
    return bundled_path if os.path.isfile(bundled_path) else None

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
        self.change_callback = None

        self.chips = []

        self.entry_frame = tk.Frame(self, bg=self.cget("bg"))
        self.entry_frame.pack(fill=tk.X)

        self.entry = tk.Entry(
            self.entry_frame,
            bg=bg_input,
            fg=text_main,
            disabledbackground=bg_panel,
            disabledforeground=text_muted,
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

        if self.change_callback:
            self.change_callback()

    def _remove_chip(self, text):
        if text in self.chips:
            self.chips.remove(text)
            if self.state_callback:
                self.state_callback()
            self._redraw_chips()

    def toggle_chip(self, text):
        """Toggle a predefined option without removing custom text entry."""
        text = str(text).strip()
        if not text:
            return
        if text in self.chips:
            self.chips.remove(text)
        else:
            self.chips.append(text)
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

    def replace(self, value):
        """Replace all values with a single redraw during preset loading."""
        new_chips = [item.strip() for item in str(value or "").split(",") if item.strip()]
        entry_has_text = bool(self.entry.get())
        if new_chips == self.chips and not entry_has_text:
            return
        self.chips = new_chips
        if entry_has_text:
            self.entry.delete(0, tk.END)
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
                self.entry.configure(
                    bg=self.bg_panel,
                    disabledbackground=self.bg_panel,
                    disabledforeground=self.text_muted,
                )
            else:
                self.entry.configure(bg=self.bg_input)

    def bind(self, sequence=None, func=None, add=None):
        return self.entry.bind(sequence, func, add)


class EmojiOptionPicker(tk.Frame):
    """Visual emoji picker with explicit selection state and optional reordering."""
    _COLORS = {
        "Y": "#f9e2af", "O": "#fab387", "R": "#f38ba8", "W": "#f5f5f5",
        "L": "#cba6f7", "P": "#cba6f7", "D": "#89b4fa", "C": "#a6e3a1",
        "G": "#a6e3a1", "T": "#94e2d5",
    }

    def __init__(self, parent, chip_widget, options, reorderable=False):
        super().__init__(parent, bg=parent.cget("bg"))
        self.chip_widget = chip_widget
        self.options = list(options)
        self.reorderable = reorderable
        self.cards = {}
        self.icons = {}
        self.checks = {}
        self.images = {}
        self.enable_callback = None
        self.drag_option = None
        chip_widget.change_callback = self.refresh

        controls = tk.Frame(self, bg=self.cget("bg"))
        controls.pack(fill=tk.X, pady=(0, 2))
        control_label = "Drag to reorder" if reorderable else "Options"
        tk.Label(controls, text=control_label, bg=controls.cget("bg"), fg=TEXT_MUTED,
                 font=("Segoe UI", 8)).pack(side=tk.LEFT)
        for text, command in (("Select all", self.select_all), ("Clear", self.clear_all)):
            tk.Button(controls, text=text, command=command, bg=BG_PANEL, fg=TEXT_MAIN,
                      activebackground=BG_INPUT, activeforeground=TEXT_MAIN, bd=0,
                      font=("Segoe UI", 8), padx=6, pady=1, cursor="hand2").pack(side=tk.RIGHT, padx=(4, 0))

        self.card_row = tk.Frame(self, bg=self.cget("bg"))
        self.card_row.pack(fill=tk.X)
        self.refresh()

    def _toggle(self, option):
        if self.enable_callback:
            self.enable_callback()
        self.chip_widget.toggle_chip(option)

    def select_all(self):
        if self.enable_callback:
            self.enable_callback()
        custom_values = [value for value in self.chip_widget.chips if value not in self.options]
        self.chip_widget.chips = list(self.options) + custom_values
        if self.chip_widget.state_callback:
            self.chip_widget.state_callback()
        self.chip_widget._redraw_chips()

    def clear_all(self):
        self.chip_widget.chips = [value for value in self.chip_widget.chips if value not in self.options]
        if self.chip_widget.state_callback:
            self.chip_widget.state_callback()
        self.chip_widget._redraw_chips()

    def _display_options(self):
        if not self.reorderable:
            return self.options
        selected = [value for value in self.chip_widget.chips if value in self.options]
        return selected + [value for value in self.options if value not in selected]

    def _build_cards(self):
        for child in self.card_row.winfo_children():
            child.destroy()
        self.cards.clear()
        self.icons.clear()
        self.checks.clear()
        self.images.clear()
        selected = set(self.chip_widget.chips)
        for option in self._display_options():
            selected_option = option in selected
            background = BG_INPUT if selected_option else BG_PANEL
            card = tk.Frame(self.card_row, bg=background, highlightthickness=2,
                            highlightbackground=ACCENT if selected_option else BORDER_COLOR, cursor="hand2")
            card.pack(side=tk.LEFT, padx=(0, 5), pady=(2, 4))
            icon = tk.Canvas(card, width=28, height=28, bg=background, highlightthickness=0)
            icon.pack(padx=4, pady=4)
            self._draw_icon(icon, option)
            check = tk.Label(card, text="✓", bg=ACCENT, fg=BG_DARK, font=("Segoe UI", 7, "bold"),
                             padx=2)
            if selected_option:
                check.place(relx=1, rely=0, anchor="ne")
            Tooltip(card, option + (" — drag to reorder" if self.reorderable else ""))
            for widget in (card, icon):
                widget.bind("<ButtonPress-1>", lambda event, value=option: self._start_drag(event, value))
                widget.bind("<ButtonRelease-1>", lambda event, value=option: self._finish_drag(event, value))
            self.cards[option] = card
            self.icons[option] = icon
            self.checks[option] = check

    def _start_drag(self, _event, option):
        self.drag_option = option

    def _finish_drag(self, event, option):
        dragged = self.drag_option
        self.drag_option = None
        if not self.reorderable or dragged not in self.chip_widget.chips:
            self._toggle(option)
            return
        targets = [value for value in self._display_options() if value in self.chip_widget.chips]
        if not targets:
            self._toggle(option)
            return
        target = min(targets, key=lambda value: abs(event.x_root - (self.cards[value].winfo_rootx() + self.cards[value].winfo_width() / 2)))
        if target == dragged:
            self._toggle(option)
            return
        ordered = list(self.chip_widget.chips)
        ordered.remove(dragged)
        ordered.insert(ordered.index(target), dragged)
        self.chip_widget.chips = ordered
        if self.chip_widget.state_callback:
            self.chip_widget.state_callback()
        self.chip_widget._redraw_chips()

    def _draw_icon(self, canvas, option):
        image = self._load_mudae_emoji_image(option)
        if image is not None:
            canvas.create_image(14, 14, image=image)
            self.images[option] = image
            return

        if option.startswith("kakera") or option.startswith("sp"):
            prefix = "kakera" if option.startswith("kakera") else "sp"
            color = self._COLORS.get(option[len(prefix):].rstrip("2"), "#cba6f7")
            canvas.create_polygon(14, 3, 25, 14, 14, 25, 3, 14,
                                 fill=color, outline="#ffffff")
        else:
            canvas.create_text(14, 14, text=option, fill="#f5c2e7",
                               font=("Segoe UI Emoji", 14))

    @staticmethod
    def _load_mudae_emoji_image(option):
        """Use Mudae's cached Discord artwork, with a drawn fallback until synced."""
        path = get_mudae_emoji_asset_path(option)
        if path is None:
            return None
        try:
            image = tk.PhotoImage(file=path)
            factor = max(1, math.ceil(max(image.width(), image.height()) / 23))
            return image.subsample(factor, factor)
        except tk.TclError:
            return None

    def refresh(self):
        display_options = self._display_options()
        if set(self.cards) != set(display_options):
            self._build_cards()
            return

        selected = set(self.chip_widget.chips)
        for option in display_options:
            card = self.cards[option]
            icon = self.icons[option]
            check = self.checks[option]
            selected_option = option in selected
            background = BG_INPUT if selected_option else BG_PANEL
            card.pack_forget()
            card.pack(side=tk.LEFT, padx=(0, 5), pady=(2, 4))
            card.configure(
                bg=background,
                highlightbackground=ACCENT if selected_option else BORDER_COLOR,
            )
            icon.configure(bg=background)
            if selected_option:
                check.place(relx=1, rely=0, anchor="ne")
            else:
                check.place_forget()

# --- Constants ---
PRESETS_FILE = os.path.join(get_base_path(), "presets.json")
BOT_SCRIPT = os.path.join(get_base_path(), "mudae_bot.py")

# Default values (for display hints)
DEFAULTS = {
    "token": "",
    "additional_tokens": "",
    "prefix": "/////////////",
    "mudae_prefix": "$",
    "channel_id": "",
    "command_channel_id": "",
    "forcedivorce_channel_id": "",
    "roll_command": "wa",
    "min_kakera": 100,
    "delay_seconds": 0,
    "start_delay": 0,
    "auto_p_enabled": True,
    "auto_oh_enabled": False,
    "oh_use_individually": False,
    "auto_oc_enabled": False,
    "roll_speed": 0.4,
    "snipe_delay": 2,
    "series_snipe_delay": 3,
    "series_snipe_only_self_rolls": False,
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
    "auto_mk_full_power_only": False,
    "auto_rolls_enabled": False,
    "auto_rolls_limit": 0,
    "auto_rolls_in_key_mode": False,
    "auto_rolls_only_claim_hour": False,
    "panic_roll_minutes": 5,
    "lurker_mode": False,
    "auto_rt_after_claim": False,
    "auto_dk_enabled": True,
    "auto_dk_min_power": 0,
    "max_dk_power": 100,
    "randomized_claim_reactions": ["💖", "💗", "💘", "❤️", "👍", "🔥"],
    "main_account_id": "",
    "scheduled_roll_times": [],
    "kakera_priority_order": ["kakeraP", "kakeraC", "kakeraL", "kakeraW", "kakeraR", "kakeraO", "kakeraD", "kakeraY", "kakeraG", "kakeraT", "kakera"],
    "enable_snipe_chat_reactions": False,
    "snipe_chat_messages": ["omg", "ezz"],
    "enable_kakera_snipe_chat_reactions": False,
    "kakera_snipe_chat_messages": ["nice", "free kakera"],
    "farm_character": "",
    "farm_characters": [],
    "farm_character_enabled": False,
    "farm_forcedivorce_before_roll": False,
    "farm_forcedivorce_after_claim": False,
    "farm_forcedivorce_after_other_claim": False,
    "op_perk_5_only": False,
    "auto_divorce_enabled": False,
    "auto_divorce_protect_wishes": True,
    "auto_divorce_max_kakera": 50,
    "auto_divorce_series": [],
    "auto_divorce_blacklist": [],
    "auto_divorce_blacklist_series": [],
    "mk_bypass_power_check": False,
    "snipe_channels": [],
    "kakera_snipe_channels": [],
    "max_claim_rank": 0,
    "max_like_rank": 0,
    "enable_hybrid_panic_claim": False,
    "hybrid_panic_instant_claim_min_kakera": 300,
    "hybrid_panic_instant_claim_max_rank": 200,
    "claim_rounds_thresholds": [],
    "sphere_click_targets": ["spG", "spY", "spO", "spR", "spW", "spL", "spD", "spM", "spU"],
    "immediate_kakera_click": True,
    "collect_purple_kakera": True,
    "wish_starwish_kakera_only": False,
    "oh_priority_order": [],
    "oh_unknown_explore_clicks": 3,
    "oc_reward_priority_order": [],
    "oc_collect_after_red": True,
    "webhook_url": "",
    "webhook_log_types": ["ERROR", "WARN", "CLAIM", "KAKERA"],
    "debug_log_categories": ["all"],
    "character_snipe_targets": [],
    "auto_free_claim": True,
}

# Boolean settings with their display names and defaults
BOOL_SETTINGS = [
    ("rolling", "Rolling Enabled (Turn off to only snipe without rolling yourself)", True),
    ("use_slash_rolls", "Use /slash commands (Earn 10% more Kakera)", False),
    ("snipe_mode", "Snipe Characters (Claim characters rolled by other people)", False),
    ("snipe_ignore_min_kakera_reset", "Panic Claim (Claim ANY character right before your timer resets)", False),
    ("series_snipe_mode", "Series Sniping (Auto-claim any character from specific shows/games)", False),
    ("series_snipe_only_self_rolls", "Series Claims on Own Rolls Only (Never steal series characters from other players)", False),
    ("kakera_snipe_mode", "Value Sniping (Snipe expensive characters rolled by others)", False),
    ("kakera_reaction_snipe_mode", "Auto-Collect Kakera (Click crystals on other people's rolls)", False),
    ("reactive_snipe_on_own_rolls", "Instant Self-Claim (Immediately claim your own good rolls)", True),
    ("auto_free_claim", "Auto-Claim Perk 6 Free Claims (Turn off to prevent this account from clicking green claim buttons)", True),
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
    ("auto_mk_full_power_only", "Use $mk Only at Full Power (Wait for power regeneration/reset checks)", False),
    ("lurker_mode", "Lurker Strategy (Wait for others to roll while sniping - Panic dump at the end)", False),
    ("auto_rt_after_claim", "Auto $rt After Claim (Also controls $rt for Kakera farm claims)", False),
    ("enable_snipe_chat_reactions", "Snipe Chat Reactions (Send a random message after a successful external snipe)", False),
    ("enable_kakera_snipe_chat_reactions", "Kakera Snipe Chat Message (Send after collecting Kakera from another roll)", False),
    ("op_perk_5_only", "Only Click Kakera on OP5 Characters", False),
    ("farm_character_enabled", "Enable Kakera Farming Loop (Auto-Forcedivorce)", False),
    ("farm_forcedivorce_before_roll", "Forcedivorce Before Rolling (Solo/Startup Cleanup)", False),
    ("farm_forcedivorce_after_claim", "Forcedivorce After Own Verified Claim", False),
    ("farm_forcedivorce_after_other_claim", "Forcedivorce After Another Account Claims (Shared Server Mode)", False),
    ("auto_divorce_enabled", "Auto-Divorce (Automatically separate characters after claiming them)", False),
    ("auto_divorce_protect_wishes", "Protect Wished/Starwished Characters and Series from Auto-Divorce", True),
    ("mk_bypass_power_check", "Force $mk Rolls (Use $mk even when power is too low for normal kakera)", False),
    ("enable_hybrid_panic_claim", "Hybrid Smart Panic Claim (Instantly claim high-value characters in the last claim hour, collect others)", False),
    ("immediate_kakera_click", "Immediate Kakera Click (Click crystals instantly instead of waiting for all rolls to finish)", True),
    ("collect_purple_kakera", "Collect Purple Kakera (Disable on extra accounts to avoid reaction races)", True),
    ("auto_p_enabled", "Auto $p (Automatically claim pokemon when available)", True),
    ("auto_oh_enabled", "Auto $oh (Automatically play Sphere Harvest when available)", False),
    ("oh_use_individually", "$oh: Play Every Available Use Separately (one board per use)", False),
    ("auto_oc_enabled", "Auto $oc (Automatically solve Sphere Chest when available)", False),
    ("oc_collect_after_red", "$oc: Keep Collecting Rewards After Finding Red", True),
    ("wish_starwish_kakera_only", "Only Click Kakera on Wish/Starwish Characters (combines with other filters)", False),
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
    ("oh_unknown_explore_clicks", "$oh Unknown Exploration Clicks (before fallback strategy)", 3, int),
]

# Text/list settings
TEXT_SETTINGS = [
    ("token", "Discord Account Token (REQUIRED: Your secret account key)", "", False),  # (key, label, default, is_list)
    ("prefix", "Self-Bot Prefix (Command prefix for controlling the bot)", "/////////////", False),
    ("mudae_prefix", "Mudae Game Prefix (Usually $)", "$", False),
    ("channel_id", "Discord Channel ID (Where the bot should roll)", "", False),
    ("forcedivorce_channel_id", "Forcedivorce Channel ID (Optional: leave empty to use roll channel)", "", False),
    ("roll_command", "Roll Type (wa, ha, ma, etc.)", "wa", False),
    ("wishlist", "Character Wishlist (Names of characters you want to auto-claim)", [], True),
    ("series_wishlist", "Series Wishlist (Shows or Games you want to auto-claim)", [], True),
    ("avoid_list", "Blacklisted Characters (Names of characters to NEVER claim)", [], True),
    ("kakera_reaction_snipe_targets", "Target User IDs (Only steal Kakera from these specific users)", [], True),
    ("farm_characters", "Kakera Farm Characters (comma-separated)", [], True),
    ("kakera_snipe_chat_messages", "Kakera Snipe Chat Messages", ["nice", "free kakera"], True),
    ("oh_priority_order", "$oh Reward Priority (highest first)", [], True),
    ("oc_reward_priority_order", "$oc Reward Priority After Red (highest first)", [], True),
    ("webhook_url", "Remote Log Discord Webhook URL", "", False),
    ("webhook_log_types", "Webhook Log Types", ["ERROR", "WARN", "CLAIM", "KAKERA"], True),
    ("debug_log_categories", "Expert Log Categories", ["all"], True),
    ("auto_divorce_series", "Auto-Divorce Series (Divorce if character is from these series)", [], True),
    ("auto_divorce_blacklist", "Divorce Blacklist (Characters to NEVER divorce)", [], True),
    ("auto_divorce_blacklist_series", "Divorce Blacklist Series (Series to NEVER divorce)", [], True),
    ("snipe_channels", "Character Snipe Channels (Comma-separated IDs of external channels to monitor for character sniping)", [], True),
    ("kakera_snipe_channels", "Kakera Snipe Channels (Comma-separated IDs of channels to monitor for Kakera)", [], True),
    ("sphere_click_targets", "Target Sphere Emojis (Comma-separated list of sphere emojis to click, e.g., spM, spU, spG)", ["spG", "spY", "spO", "spR", "spW", "spL", "spD", "spM", "spU"], True),
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


# Opinionated defaults for the common single-account workflow. These are used
# for new profiles and the Quick Setup reset action; existing profiles retain
# their explicit advanced values.
RECOMMENDED_PRESET_OVERRIDES = {
    "rolling": True,
    "reactive_snipe_on_own_rolls": True,
    "auto_free_claim": True,
    "use_slash_rolls": True,
    "snipe_mode": False,
    "kakera_reaction_snipe_mode": False,
    "series_snipe_mode": False,
    "series_snipe_only_self_rolls": True,
    "kakera_snipe_mode": False,
    "key_mode": False,
    "time_rolls_to_claim_reset": False,
    "auto_mk_enabled": True,
    "auto_dk_enabled": True,
    "auto_p_enabled": True,
    "immediate_kakera_click": True,
    "min_kakera": 100,
    "roll_command": "wa",
}


def build_recommended_preset():
    """Return a complete, independent preset for the mainstream workflow."""
    data = copy.deepcopy(DEFAULTS)
    for key, _label, default in BOOL_SETTINGS:
        data.setdefault(key, copy.deepcopy(default))
    for key, _label, default, _value_type in NUMERIC_SETTINGS:
        data.setdefault(key, copy.deepcopy(default))
    for key, _label, default, _is_list in TEXT_SETTINGS:
        data.setdefault(key, copy.deepcopy(default))
    data.update(copy.deepcopy(RECOMMENDED_PRESET_OVERRIDES))
    data.update({
        "inactive_hours": [],
        "kakera_power_thresholds": {},
        "reactive_kakera_delay_range": [0.3, 1.0],
        "scheduled_roll_times": [],
    })
    data.pop("additional_tokens", None)
    data["token"] = ""
    return data


class PresetEditor:
    def __init__(self, root):
        self.root = root
        self.root.title("MudaRemote Preset Editor")
        self.root.geometry("900x700")
        self.root.minsize(800, 600)

        # Track unsaved edits
        self.is_dirty = False
        self.loading_preset = False
        self._preset_selection_generation = 0
        self._preset_selection_in_progress = False
        self._pending_preset_selection = None

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
        self.editor_mode = "quick"
        self.quick_widgets = {}
        self.quick_goal_vars = {}
        self.quick_summary_var = tk.StringVar(value="Select a profile to begin.")

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
            self.save_active_preset()
            # If save was aborted due to validation error, is_dirty remains True
            return not self.is_dirty
        elif ans is False:  # No, discard changes and proceed
            self.is_dirty = False
            return True
        else:  # Cancel
            return False

    def update_listbox_selection(self, preset_name):
        """Helper to restore listbox selection to avoid UI desync."""
        was_loading = self.loading_preset
        self.loading_preset = True
        try:
            for i in range(self.preset_listbox.size()):
                if self.preset_listbox.get(i) == preset_name:
                    self.preset_listbox.selection_clear(0, tk.END)
                    self.preset_listbox.selection_set(i)
                    self.preset_listbox.activate(i)
                    self.preset_listbox.see(i)
                    break
        finally:
            self.loading_preset = was_loading

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

        # Read-only comboboxes otherwise inherit a bright native field on
        # Windows, which breaks the dark theme in Quick Setup.
        style.configure(
            "Quick.TCombobox",
            fieldbackground=BG_INPUT,
            background=BG_INPUT,
            foreground=TEXT_MAIN,
            arrowcolor=ACCENT,
            bordercolor=BORDER_COLOR,
            lightcolor=BORDER_COLOR,
            darkcolor=BORDER_COLOR,
            padding=5,
        )
        style.map(
            "Quick.TCombobox",
            fieldbackground=[("readonly", BG_INPUT), ("focus", BG_INPUT)],
            foreground=[("readonly", TEXT_MAIN), ("focus", TEXT_MAIN)],
            background=[("active", BG_INPUT), ("readonly", BG_INPUT)],
            selectbackground=[("readonly", BG_INPUT)],
            selectforeground=[("readonly", TEXT_MAIN)],
        )

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
            button.configure(bg=button._flat_hover_bg, fg=button._flat_fg)
        def on_leave(e):
            button.configure(bg=button._flat_normal_bg, fg=button._flat_fg)

        button.bind("<Enter>", on_enter)
        button.bind("<Leave>", on_leave)

    def set_flat_button_colors(self, button, bg_color, fg_color, hover_bg):
        """Update every visual state of a custom flat button together."""
        button._flat_normal_bg = bg_color
        button._flat_hover_bg = hover_bg
        button._flat_fg = fg_color
        button.configure(
            bg=bg_color,
            fg=fg_color,
            activebackground=hover_bg,
            activeforeground=fg_color,
        )

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
        btn._flat_normal_bg = bg_color
        btn._flat_hover_bg = hover_bg
        btn._flat_fg = fg_color
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

        visible_names = [
            name for name in sorted(self.presets.keys())
            if not query or query in name.lower()
        ]
        self._replace_preset_list(visible_names)

    def load_presets(self):
        """Load presets from JSON file."""
        if os.path.exists(PRESETS_FILE):
            try:
                self.presets = load_json(PRESETS_FILE, {})
                migrated = False
                for preset_name, data in self.presets.items():
                    if not data.get("farm_characters") and data.get("farm_character"):
                        data["farm_characters"] = [data["farm_character"]]
                        migrated = True
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

        self.preset_listbox = tk.Listbox(
            listbox_border,
            exportselection=False,
            selectmode=tk.BROWSE,
            **self.listbox_config,
        )
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

        # First-run users start in the guided flow. The existing form remains
        # available as an explicit advanced mode for power users.
        self.mode_bar = tk.Frame(self.settings_container, bg=BG_DARK)
        self.mode_bar.pack(fill=tk.X, pady=(0, 10))
        mode_title = tk.Label(
            self.mode_bar,
            text="Configuration",
            bg=BG_DARK,
            fg=TEXT_MAIN,
            font=("Segoe UI", 13, "bold"),
        )
        mode_title.pack(side=tk.LEFT)
        self.advanced_mode_btn = self.create_flat_button(
            self.mode_bar,
            "Advanced Settings",
            lambda: self.show_editor_mode("advanced"),
            bg_color=BG_PANEL,
            fg_color=TEXT_MAIN,
            hover_bg=BG_INPUT,
            font=("Segoe UI", 9, "bold"),
        )
        self.advanced_mode_btn.pack(side=tk.RIGHT)
        self.quick_mode_btn = self.create_flat_button(
            self.mode_bar,
            "Quick Setup",
            lambda: self.show_editor_mode("quick"),
            bg_color=ACCENT,
            fg_color=BG_DARK,
            hover_bg=ACCENT_ALT,
            font=("Segoe UI", 9, "bold"),
        )
        self.quick_mode_btn.pack(side=tk.RIGHT, padx=(0, 6))

        # Settings Search Frame at the top of settings
        self.advanced_search_frame = tk.Frame(self.settings_container, bg=BG_DARK, bd=0)
        self.advanced_search_frame.pack(fill=tk.X, pady=(0, 10))

        self.settings_search_var = tk.StringVar()
        self.settings_search_var.trace_add("write", self.filter_settings)

        self.settings_search_entry = tk.Entry(
            self.advanced_search_frame,
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
        self.advanced_scroll_area = tk.Frame(self.settings_container, bg=BG_DARK)
        self.advanced_scroll_area.pack(fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(self.advanced_scroll_area, bg=BG_DARK, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.advanced_scroll_area, orient=tk.VERTICAL, command=self.canvas.yview)
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
        self.build_quick_setup()
        self.show_editor_mode("quick")

    def _quick_label(self, parent, text, muted=False):
        label = tk.Label(
            parent,
            text=text,
            bg=parent.cget("bg"),
            fg=TEXT_MUTED if muted else TEXT_MAIN,
            font=("Segoe UI", 9 if muted else 10),
            justify=tk.LEFT,
            anchor="w",
            wraplength=620,
        )
        label.pack(anchor=tk.W, fill=tk.X)
        return label

    def _quick_entry(self, parent, key, label, placeholder="", show=None):
        container = tk.Frame(parent, bg=parent.cget("bg"))
        container.pack(fill=tk.X, pady=(6, 0))
        self._quick_label(container, label)
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
            relief="flat",
        )
        entry.pack(fill=tk.X, ipady=5, pady=(3, 0))
        if placeholder:
            entry.insert(0, placeholder)
            entry.configure(fg=TEXT_MUTED)

            def focus_in(_event):
                if entry.get() == placeholder:
                    entry.delete(0, tk.END)
                    entry.configure(fg=TEXT_MAIN)

            def focus_out(_event):
                if not entry.get().strip():
                    entry.insert(0, placeholder)
                    entry.configure(fg=TEXT_MUTED)

            entry.bind("<FocusIn>", focus_in)
            entry.bind("<FocusOut>", focus_out)
        entry.bind("<Key>", lambda _event: self.mark_dirty())
        self._bind_focus_highlight(entry)
        self.quick_widgets[key] = entry
        return entry

    def _quick_combo(self, parent, key, label, values, description=None):
        container = tk.Frame(parent, bg=parent.cget("bg"))
        container.pack(fill=tk.X, pady=(6, 0))
        self._quick_label(container, label)
        if description:
            self._quick_label(container, description, muted=True)
        combo = ttk.Combobox(
            container,
            values=values,
            state="readonly",
            style="Quick.TCombobox",
            font=("Segoe UI", 10),
        )
        combo.pack(anchor=tk.W, fill=tk.X, ipady=3, pady=(3, 0))
        combo.bind("<<ComboboxSelected>>", lambda _event: (self.mark_dirty(), self.update_quick_summary()))
        self.quick_widgets[key] = combo
        return combo

    def _quick_list(self, parent, key, label, description):
        container = tk.Frame(parent, bg=parent.cget("bg"))
        container.pack(fill=tk.X, pady=(6, 0))
        self._quick_label(container, label)
        self._quick_label(container, description, muted=True)
        def on_list_change():
            self.mark_dirty()
            self.update_quick_summary()

        widget = ChipListWidget(
            container,
            bg_input=BG_INPUT,
            text_main=TEXT_MAIN,
            border_color=BORDER_COLOR,
            accent=ACCENT,
            bg_panel=BG_PANEL,
            text_muted=TEXT_MUTED,
            state_callback=on_list_change,
        )
        widget.pack(fill=tk.X, pady=(3, 0))
        self.quick_widgets[key] = widget
        return widget

    def _quick_check(self, parent, key, text, description):
        container = tk.Frame(parent, bg=parent.cget("bg"))
        container.pack(fill=tk.X, pady=(5, 0))
        var = tk.BooleanVar(value=False)
        check = ttk.Checkbutton(container, text=text, variable=var)
        check.pack(anchor=tk.W)
        self._quick_label(container, description, muted=True)
        var.trace_add("write", lambda *_args: self.mark_dirty())
        self.quick_widgets[key] = var
        return var

    def build_quick_setup(self):
        """Build a task-oriented first-run flow over the existing preset model."""
        self.quick_view = tk.Frame(self.settings_container, bg=BG_DARK)
        self.quick_canvas = tk.Canvas(self.quick_view, bg=BG_DARK, highlightthickness=0)
        quick_scrollbar = ttk.Scrollbar(self.quick_view, orient=tk.VERTICAL, command=self.quick_canvas.yview)
        self.quick_content = tk.Frame(self.quick_canvas, bg=BG_DARK)
        self.quick_content.bind(
            "<Configure>",
            lambda _event: self.quick_canvas.configure(scrollregion=self.quick_canvas.bbox("all")),
        )
        self.quick_canvas_window = self.quick_canvas.create_window(
            (0, 0), window=self.quick_content, anchor=tk.NW
        )
        self.quick_canvas.bind(
            "<Configure>",
            lambda event: self.quick_canvas.itemconfigure(self.quick_canvas_window, width=event.width),
        )
        self.quick_canvas.configure(yscrollcommand=quick_scrollbar.set)
        self.quick_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        quick_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        content = self.quick_content
        header = tk.Frame(content, bg=BG_DARK)
        header.pack(fill=tk.X, pady=(0, 14))
        tk.Label(
            header,
            text="Quick Setup",
            bg=BG_DARK,
            fg=TEXT_MAIN,
            font=("Segoe UI", 18, "bold"),
        ).pack(anchor=tk.W)
        self._quick_label(
            header,
            "The recommended profile covers the common single-account workflow. Advanced settings stay preserved and can be edited any time.",
            muted=True,
        )

        connection = tk.Frame(content, bg=BG_PANEL, highlightbackground=BORDER_COLOR, highlightthickness=1)
        connection.pack(fill=tk.X, pady=(0, 10), padx=1)
        inner = tk.Frame(connection, bg=BG_PANEL)
        inner.pack(fill=tk.X, padx=14, pady=12)
        self._quick_label(inner, "1. Connect your account")
        self._quick_label(inner, "Only the account and channel are required for a first run.", muted=True)
        self._quick_entry(inner, "token", "Discord account token", "Paste your token here", show="*")
        self._quick_entry(inner, "channel_id", "Roll channel ID", "Paste the Discord channel ID")

        behavior = tk.Frame(content, bg=BG_PANEL, highlightbackground=BORDER_COLOR, highlightthickness=1)
        behavior.pack(fill=tk.X, pady=(0, 10), padx=1)
        inner = tk.Frame(behavior, bg=BG_PANEL)
        inner.pack(fill=tk.X, padx=14, pady=12)
        self._quick_label(inner, "2. Choose what the bot should do")
        self._quick_label(inner, "Recommended options are enabled for new profiles. External-player actions stay opt-in.", muted=True)
        self._quick_combo(
            inner,
            "roll_command",
            "Roll pool",
            ("wa", "ha", "ma", "wx", "hx", "mx", "wg", "hg", "mg"),
            "wa is the recommended default. Choose the pool you normally use in Mudae.",
        )
        self.quick_goal_vars["roll"] = self._quick_check(
            inner, "rolling", "Roll automatically", "Send the configured Mudae roll command on schedule.")
        self.quick_goal_vars["claim"] = self._quick_check(
            inner, "reactive_snipe_on_own_rolls", "Claim matching characters", "Claim wishlist and value-based matches from your own rolls, including free green claim buttons.")
        self.quick_goal_vars["slash"] = self._quick_check(
            inner, "use_slash_rolls", "Use slash roll commands (+10% Kakera)", "Recommended. Text commands are used automatically if slash commands are unavailable.")
        self._quick_label(inner, "Kakera on your own automated rolls is collected automatically.", muted=True)
        self.quick_goal_vars["kakera"] = self._quick_check(
            inner, "kakera_reaction_snipe_mode", "Collect Kakera from other players", "Optional. Click Kakera on other players' rolls in monitored channels.")
        self.quick_goal_vars["snipe"] = self._quick_check(
            inner, "snipe_mode", "Claim wishlist matches from other players", "Optional. Watch other players' rolls for your wishlist and series targets.")
        self.create_flat_button(
            inner,
            "Restore Recommended Behavior",
            self.apply_recommended_quick_defaults,
            bg_color=BG_INPUT,
            fg_color=TEXT_MAIN,
            hover_bg=BORDER_COLOR,
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor=tk.W, pady=(10, 0))

        targets = tk.Frame(content, bg=BG_PANEL, highlightbackground=BORDER_COLOR, highlightthickness=1)
        targets.pack(fill=tk.X, pady=(0, 10), padx=1)
        inner = tk.Frame(targets, bg=BG_PANEL)
        inner.pack(fill=tk.X, padx=14, pady=12)
        self._quick_label(inner, "3. Define your targets")
        self._quick_label(inner, "These are optional. Mudae's own wish indicator is also recognized automatically.", muted=True)
        self._quick_list(inner, "wishlist", "Additional character targets", "Characters to prioritize in addition to your Mudae wishlist.")
        self._quick_list(inner, "series_wishlist", "Series targets", "Series to prioritize; external rolls are included only when the external-claim option is enabled.")
        self._quick_list(inner, "avoid_list", "Never claim", "Characters to exclude from automated claiming.")
        self._quick_entry(inner, "min_kakera", "Minimum Kakera value (recommended: 100)", "100")

        review = tk.Frame(content, bg=BG_INPUT, highlightbackground=ACCENT, highlightthickness=1)
        review.pack(fill=tk.X, pady=(0, 12), padx=1)
        review_inner = tk.Frame(review, bg=BG_INPUT)
        review_inner.pack(fill=tk.X, padx=14, pady=12)
        self._quick_label(review_inner, "4. Review and start")
        self._quick_label(review_inner, "Check the summary below, save the profile, then start the bot.", muted=True)
        summary = tk.Label(
            review_inner,
            textvariable=self.quick_summary_var,
            bg=BG_INPUT,
            fg=TEXT_MAIN,
            font=("Segoe UI", 10),
            justify=tk.LEFT,
            anchor="w",
            wraplength=620,
        )
        summary.pack(fill=tk.X, pady=(8, 0))

        for widget in self.quick_widgets.values():
            if isinstance(widget, tk.Variable):
                widget.trace_add("write", lambda *_args: self.update_quick_summary())
            else:
                widget.bind("<KeyRelease>", lambda _event: self.update_quick_summary(), add="+")

    def apply_recommended_quick_defaults(self):
        """Restore mainstream behavior without touching identity or target lists."""
        recommended_quick_values = {
            "rolling": True,
            "reactive_snipe_on_own_rolls": True,
            "use_slash_rolls": True,
            "kakera_reaction_snipe_mode": False,
            "snipe_mode": False,
        }
        for key, value in recommended_quick_values.items():
            widget = self.quick_widgets.get(key)
            if isinstance(widget, tk.BooleanVar):
                widget.set(value)
        roll_combo = self.quick_widgets.get("roll_command")
        if roll_combo:
            roll_combo.set(RECOMMENDED_PRESET_OVERRIDES["roll_command"])
        threshold = self.quick_widgets.get("min_kakera")
        if threshold:
            threshold.delete(0, tk.END)
            threshold.insert(0, str(RECOMMENDED_PRESET_OVERRIDES["min_kakera"]))
            threshold.configure(fg=TEXT_MAIN)
        self.mark_dirty()
        self.update_quick_summary()

    def show_editor_mode(self, mode):
        """Switch between the guided setup and the complete expert editor."""
        mode = "advanced" if mode == "advanced" else "quick"
        if mode != self.editor_mode and self.current_preset:
            # The two forms intentionally use separate Tk variables. Resolve
            # the active form before switching, then reload both views from the
            # same persisted snapshot so stale hidden widgets cannot overwrite
            # a newer edit later.
            if not self.prompt_unsaved_changes():
                return False
            self.select_preset(self.current_preset)
        self.editor_mode = mode
        if mode == "quick":
            self.advanced_search_frame.pack_forget()
            self.advanced_scroll_area.pack_forget()
            self.quick_view.pack(fill=tk.BOTH, expand=True, before=self.footer_frame)
            self.set_flat_button_colors(self.quick_mode_btn, ACCENT, BG_DARK, ACCENT_ALT)
            self.set_flat_button_colors(self.advanced_mode_btn, BG_PANEL, TEXT_MAIN, BG_INPUT)
            self.update_quick_summary()
        else:
            self.quick_view.pack_forget()
            self.advanced_search_frame.pack(fill=tk.X, pady=(0, 10), before=self.footer_frame)
            self.advanced_scroll_area.pack(fill=tk.BOTH, expand=True, before=self.footer_frame)
            self.set_flat_button_colors(self.quick_mode_btn, BG_PANEL, TEXT_MAIN, BG_INPUT)
            self.set_flat_button_colors(self.advanced_mode_btn, ACCENT, BG_DARK, ACCENT_ALT)
        return True

    def _quick_value(self, key, default=""):
        widget = self.quick_widgets.get(key)
        if widget is None:
            return default
        if isinstance(widget, tk.Variable):
            return widget.get()
        value = widget.get().strip()
        placeholder = {
            "token": "Paste your token here",
            "additional_tokens": "Leave empty for a single account",
            "channel_id": "Paste the Discord channel ID",
        }.get(key)
        return "" if placeholder and value == placeholder else value

    def update_quick_summary(self, *_args):
        if not self.current_preset or not self.quick_widgets:
            self.quick_summary_var.set("Select a profile to begin.")
            return
        channel = self._quick_value("channel_id") or "not set"
        roll_command = self._quick_value("roll_command") or RECOMMENDED_PRESET_OVERRIDES["roll_command"]
        min_kakera = self._quick_value("min_kakera") or str(RECOMMENDED_PRESET_OVERRIDES["min_kakera"])
        core_actions = []
        if self._quick_value("rolling"):
            command_prefix = "/" if self._quick_value("use_slash_rolls") else "$"
            core_actions.append(f"roll automatically with {command_prefix}{roll_command}")
            core_actions.append("collect Kakera from your own rolls")
        if self._quick_value("reactive_snipe_on_own_rolls"):
            core_actions.append(f"claim own-roll matches worth {min_kakera}+ Kakera")
        external_actions = []
        if self._quick_value("kakera_reaction_snipe_mode"):
            external_actions.append("collect Kakera")
        if self._quick_value("snipe_mode"):
            external_actions.append("claim wishlist/series matches")
        has_automation = bool(core_actions or external_actions)
        if not core_actions and not external_actions:
            core_actions.append("wait for manual actions")
        wishlist = self._quick_value("wishlist")
        series = self._quick_value("series_wishlist")
        target_count = len([item for item in wishlist.split(",") if item.strip()])
        series_count = len([item for item in series.split(",") if item.strip()])
        token_ready = bool(self._quick_token_values())
        channel_ready = channel.isdigit() and int(channel) > 0
        try:
            threshold_ready = float(min_kakera) >= 0
        except (TypeError, ValueError):
            threshold_ready = False
        missing = []
        if not token_ready:
            missing.append("account token")
        if not channel_ready:
            missing.append("valid channel ID")
        if not threshold_ready:
            missing.append("valid minimum Kakera value")
        if not has_automation:
            missing.append("at least one automation option")
        status = "Ready to start" if not missing else "Needs: " + ", ".join(missing)
        external_text = ", ".join(external_actions) if external_actions else "off (recommended)"
        self.quick_summary_var.set(
            f"{status}\n"
            f"Profile: {self.current_preset} · Channel: {channel}\n"
            f"Core automation: {', '.join(core_actions)}.\n"
            f"External-player actions: {external_text}.\n"
            f"Extra targets: {target_count} characters, {series_count} series."
        )

    def _quick_token_values(self):
        primary = self._quick_value("token")
        additional_widget = self.quick_widgets.get("additional_tokens")
        if additional_widget is None and self.current_preset:
            stored = self.secret_store.get_tokens(
                self.current_preset,
                self.presets.get(self.current_preset, {}).get("token", ""),
            )
            additional_candidates = stored[1:]
        else:
            additional = self._quick_value("additional_tokens")
            additional_candidates = re.split(r"[\s,]+", additional)
        values = []
        seen = set()
        for candidate in [primary] + list(additional_candidates):
            candidate = str(candidate or "").strip()
            if candidate and candidate not in seen:
                values.append(candidate)
                seen.add(candidate)
        return values

    def save_active_preset(self, show_success=True, require_runtime=False):
        if self.editor_mode == "quick":
            return self.save_quick_setup(show_success=show_success, require_runtime=require_runtime)
        return self.save_current_preset(show_success=show_success, require_runtime=require_runtime)

    def save_quick_setup(self, show_success=True, require_runtime=False):
        """Persist only the guided fields while retaining every advanced option."""
        if not self.current_preset:
            messagebox.showwarning("Warning", "No profile selected.")
            return False
        import copy
        data = copy.deepcopy(self.presets.get(self.current_preset, {}))
        for key, value in DEFAULTS.items():
            data.setdefault(key, copy.deepcopy(value))
        channel = self._quick_value("channel_id")
        min_kakera = self._quick_value("min_kakera") or "100"
        try:
            data["min_kakera"] = int(float(min_kakera))
        except ValueError:
            messagebox.showerror("Validation Error", "Minimum Kakera value must be a number.", parent=self.root)
            return False
        data["channel_id"] = channel
        data["roll_command"] = self._quick_value("roll_command") or RECOMMENDED_PRESET_OVERRIDES["roll_command"]
        data["rolling"] = bool(self._quick_value("rolling"))
        data["reactive_snipe_on_own_rolls"] = bool(self._quick_value("reactive_snipe_on_own_rolls"))
        data["auto_free_claim"] = data["reactive_snipe_on_own_rolls"]
        data["use_slash_rolls"] = bool(self._quick_value("use_slash_rolls"))
        data["kakera_reaction_snipe_mode"] = bool(self._quick_value("kakera_reaction_snipe_mode"))
        data["snipe_mode"] = bool(self._quick_value("snipe_mode"))
        data["wishlist"] = [item.strip() for item in self._quick_value("wishlist").split(",") if item.strip()]
        data["series_wishlist"] = [item.strip() for item in self._quick_value("series_wishlist").split(",") if item.strip()]
        data["avoid_list"] = [item.strip() for item in self._quick_value("avoid_list").split(",") if item.strip()]
        data["series_snipe_mode"] = bool(data["series_wishlist"])
        data["series_snipe_only_self_rolls"] = not data["snipe_mode"]
        data["token"] = ""
        return self._persist_preset_data(
            data,
            self._quick_token_values(),
            show_success=show_success,
            require_runtime=require_runtime,
        )

    def _on_mousewheel(self, event):
        if getattr(event, "num", None) == 4:
            delta = -1
        elif getattr(event, "num", None) == 5:
            delta = 1
        else:
            raw_delta = getattr(event, "delta", 0)
            delta = -1 if raw_delta > 0 else 1 if raw_delta < 0 else 0
        if delta:
            scroll_target = self.quick_canvas if self.editor_mode == "quick" else self.canvas
            scroll_target.yview_scroll(delta, "units")

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
        self._replace_preset_list(sorted(self.presets.keys()))

    def _replace_preset_list(self, preset_names):
        """Rebuild the sidebar without losing or spuriously changing selection."""
        names = list(preset_names)
        was_loading = self.loading_preset
        self.loading_preset = True
        try:
            self.preset_listbox.delete(0, tk.END)
            for name in names:
                self.preset_listbox.insert(tk.END, name)
            if self.current_preset in names:
                index = names.index(self.current_preset)
                self.preset_listbox.selection_set(index)
                self.preset_listbox.activate(index)
                self.preset_listbox.see(index)
        finally:
            self.loading_preset = was_loading

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
        self.add_text_field(
            core_frame.content,
            "additional_tokens",
            "Additional Tokens (Optional, comma-separated; securely encrypted)",
            show="*",
        )
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
        self.add_checkbox(us_frame.content, "auto_mk_full_power_only", "Use $mk Only at Full Power")
        self.add_checkbox(us_frame.content, "mk_bypass_power_check", "Force $mk Rolls (Use $mk even when power is too low for normal kakera)")

        # --- Claiming ---
        claim_frame = CollapsibleLabelFrame(frame, text="Claim Rules", start_open=False)
        claim_frame.pack(fill=tk.X, pady=(0, 15))

        self.add_number_field(claim_frame.content, "min_kakera", "Minimum Value to Claim (Claim if character is worth this much)", 100)
        claim_interval_entry = self.add_number_field(claim_frame.content, "claim_interval", "Claim Timer (Minutes until you get a new claim right)", 180)
        self.add_checkbox(claim_frame.content, "auto_free_claim", "Auto-Claim Perk 6 Free Claims (Turn off to prevent this account from clicking green claim buttons)")
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
        self.add_list_field(snipe_sub, "snipe_channels", "Character Snipe Channels (Comma-separated IDs of external channels to monitor for character sniping)")

        reactive_snipe_var = self.add_checkbox(char_snipe_frame.content, "reactive_snipe_on_own_rolls", "Instant Self-Claim (Immediately claim your own good rolls)")
        reactive_sub = self.create_subframe(char_snipe_frame.content, reactive_snipe_var, "reactive_snipe_on_own_rolls")
        self.add_number_field(reactive_sub, "reactive_snipe_delay", "Self-Claim Delay (Seconds to wait before claiming your own rolls)", 0)

        # Series snipe
        series_snipe_var = self.add_checkbox(char_snipe_frame.content, "series_snipe_mode", "Series Sniping (Auto-claim any character from specific shows/games)")
        series_sub = self.create_subframe(char_snipe_frame.content, series_snipe_var, "series_snipe_mode")
        self.add_checkbox(series_sub, "series_snipe_only_self_rolls", "Series Claims on Own Rolls Only (Never steal series characters from other players)")
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
        kakera_chat_var = self.add_checkbox(
            char_snipe_frame.content,
            "enable_kakera_snipe_chat_reactions",
            "Kakera Snipe Chat Message (Send after a successful external Kakera click)",
        )
        kakera_chat_sub = self.create_subframe(
            char_snipe_frame.content,
            kakera_chat_var,
            "enable_kakera_snipe_chat_reactions",
        )
        self.add_list_field(
            kakera_chat_sub,
            "kakera_snipe_chat_messages",
            "Kakera Snipe Chat Messages (Comma-separated)",
        )

        # --- Kakera Reaction Collection ---
        kakera_react_outer = ttk.Frame(frame)
        kakera_react_outer.pack(fill=tk.X, pady=(0, 15))
        kakera_react_frame = CollapsibleLabelFrame(kakera_react_outer, text="Kakera Reaction Collection", start_open=False)
        kakera_react_frame.pack(fill=tk.X)

        kakera_react_snipe_var = self.add_checkbox(kakera_react_frame.content, "kakera_reaction_snipe_mode", "Auto-Collect Kakera (Click crystals on other people's rolls)")
        kakera_react_sub = self.create_subframe(kakera_react_frame.content, kakera_react_snipe_var, "kakera_reaction_snipe_mode")
        self.add_number_field(kakera_react_sub, "kakera_reaction_snipe_delay", "Kakera Collection Delay (How fast to click others' crystals)", 0.75)
        self.add_list_field(kakera_react_sub, "kakera_snipe_channels", "Kakera Snipe Channels (Leave empty to reuse Character Snipe Channels)")
        self.add_list_field(kakera_react_sub, "kakera_reaction_snipe_targets", "Target User IDs (Only steal Kakera from these specific users)")

        self.add_checkbox(kakera_react_frame.content, "only_chaos", "Chaos Kakera Only (Only click crystals that cost 50% less power)")
        self.add_checkbox(kakera_react_frame.content, "mk_only", "MK Kakera Only (Ignore normal kakera, ONLY click crystals from your $mk rolls)")

        self.add_checkbox(kakera_react_frame.content, "immediate_kakera_click", "Immediate Kakera Click (Click crystals instantly instead of waiting for all rolls to finish)", description="If enabled, the bot clicks crystals as soon as they appear. Otherwise, it waits to prioritize the best ones.")
        self.add_checkbox(kakera_react_frame.content, "collect_purple_kakera", "Collect Purple Kakera", description="Turn this off on extra accounts when several accounts watch the same rolls.")

        self.add_checkbox(kakera_react_frame.content, "op_perk_5_only", "Only Click Kakera on OP5 Characters")
        self.add_checkbox(
            kakera_react_frame.content,
            "wish_starwish_kakera_only",
            "Only Click Kakera on Wish/Starwish Characters (combines with other filters; starwish = sw emoji in series)",
        )
        ttk.Label(
            kakera_react_frame.content,
            text="Filter rule: every enabled 'Only' option must match. Purple Kakera follows this preset's toggle. Chaos Emojis apply only to your own rolls.",
            foreground="#f9e2af",
            font=("Segoe UI", 9),
        ).pack(anchor=tk.W, padx=20, pady=(2, 6))

        # --- Wishlists & Filters ---
        list_frame = CollapsibleLabelFrame(frame, text="Wishlists & Ignored Characters", start_open=False)
        list_frame.pack(fill=tk.X, pady=(0, 15))

        self.add_list_field(list_frame.content, "wishlist", "Character Wishlist (Names of characters you want to auto-claim)")
        self.add_list_field(list_frame.content, "avoid_list", "Blacklisted Characters (Names of characters to NEVER claim)")

        farm_var = self.add_checkbox(list_frame.content, "farm_character_enabled", "Enable Kakera Farming Loop (Auto-Forcedivorce)")
        farm_sub = self.create_subframe(list_frame.content, farm_var, "farm_character_enabled")
        self.add_list_field(farm_sub, "farm_characters", "Kakera Farm Characters (Comma-separated names)")
        self.add_text_field(farm_sub, "forcedivorce_channel_id", "Forcedivorce Channel ID (Optional: leave empty to use roll channel)")
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
        self.add_checkbox(divorce_sub, "auto_divorce_protect_wishes", "Protect Wished/Starwished Characters and Series")
        self.add_number_field(divorce_sub, "auto_divorce_max_kakera", "Kakera Threshold (Divorce if character value ≤ this)", 50)
        self.add_list_field(divorce_sub, "auto_divorce_series", "Auto-Divorce Series (Divorce if character is from these series)")
        self.add_list_field(divorce_sub, "auto_divorce_blacklist", "Divorce Blacklist (Characters to NEVER divorce)")
        self.add_list_field(divorce_sub, "auto_divorce_blacklist_series", "Divorce Blacklist Series (Series to NEVER divorce)")

        # --- Emoji Settings ---
        emoji_frame = CollapsibleLabelFrame(frame, text="Custom Emojis (Advanced)", start_open=False)
        emoji_frame.pack(fill=tk.X, pady=(0, 15))

        ttk.Label(emoji_frame.content, text="Choose from the cards. Use ‘Add custom emoji’ only when you need a custom emoji name.",
                 foreground="#a6adc8", font=("Segoe UI", 9)).pack(anchor=tk.W, pady=(0, 8))

        self.add_optional_list_field(emoji_frame.content, "claim_emojis", "Claim Emojis",
                                     ", ".join(DEFAULT_CLAIM_EMOJIS))
        self.add_optional_list_field(emoji_frame.content, "kakera_emojis", "Kakera Emojis",
                                     ", ".join(DEFAULT_KAKERA_EMOJIS))
        self.add_optional_list_field(emoji_frame.content, "chaos_emojis", "Custom Chaos Emoji Override (Own Rolls Only; unchecked inherits Kakera Emojis)",
                                     ", ".join(DEFAULT_CHAOS_EMOJIS))
        self.add_optional_list_field(emoji_frame.content, "sphere_perk_emojis", "Custom Ouroperk 8 Emoji Override (unchecked inherits Kakera Emojis)",
                                     ", ".join(DEFAULT_SPHERE_PERK_EMOJIS))

        # [NEW] Task 5: Randomized claim reaction emojis
        self.add_list_field(emoji_frame.content, "randomized_claim_reactions", "Claim Reaction Emojis (Randomized fallback emojis for claims without buttons)")

        # [NEW] Task 8: Customizable kakera/sphere priority map
        self.add_list_field(emoji_frame.content, "kakera_priority_order", "Kakera Priority Order",
                            description="Drag cards from highest to lowest priority.")

        # [NEW] Sphere click targets setting
        self.add_list_field(emoji_frame.content, "sphere_click_targets", "Target Sphere Emojis")
        self.add_list_field(emoji_frame.content, "oh_priority_order", "$oh Reward Priority (Highest first; e.g. spD, spP, spU)")
        self.add_number_field(emoji_frame.content, "oh_unknown_explore_clicks", "$oh Unknown Exploration Clicks", 3)
        self.add_list_field(emoji_frame.content, "oc_reward_priority_order", "$oc Reward Priority After Red (Highest first)")
        self.add_checkbox(emoji_frame.content, "oc_collect_after_red", "$oc: Keep Collecting Rewards After Finding Red")

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
        lbl_sleep = tk.Label(inactive_row, text="Bot Sleep Schedule (e.g. 01:30-07:15, 23:45-06:10):", bg=BG_DARK, fg=TEXT_MAIN, font=("Segoe UI", 10))
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
        self._register_settings_widget(human_frame.content, inactive_row, "Bot Sleep Schedule (minute precision):", "inactive_hours")
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
        self.add_checkbox(
            power_frame.content,
            "oh_use_individually",
            "$oh: Play Every Available Use Separately",
            description="Enabled: sends one $oh per stock. Disabled: combines up to 10 uses into one multiplier board.",
        )
        self.add_checkbox(power_frame.content, "auto_oc_enabled", "Auto $oc (Automatically solve Sphere Chest when available)")
        self.add_checkbox(power_frame.content, "dk_power_management", "Smart Power Refill (Auto-use $dk when low on energy)")
        self.add_number_field(
            power_frame.content,
            "auto_dk_min_power",
            "Auto $dk Trigger Below Power % (0 = match next Kakera cost)",
            0,
        )
        # [NEW] Task 1: Max DK Power setting
        self.add_number_field(power_frame.content, "max_dk_power", "Maximum DK Power % (Default 100, increase for late-game users)", 100)
        self.add_checkbox(power_frame.content, "skip_initial_commands", "Fast Start (Skip initial setup commands on startup)")
        self.add_text_field(power_frame.content, "kakera_power_thresholds", "Min Power per Kakera (e.g. kakeraY:80, chaos_kakeraY:50)")
        self.add_checkbox(power_frame.content, "debug_mode", "Expert Logs (Show technical data for every single roll)")
        self.add_list_field(power_frame.content, "debug_log_categories", "Expert Log Categories (all, claim, kakera, roll, status, sphere, coordination, other)")
        self.add_text_field(power_frame.content, "webhook_url", "Remote Log Discord Webhook URL (Optional)")
        self.add_list_field(power_frame.content, "webhook_log_types", "Webhook Log Types (ERROR, WARN, CLAIM, KAKERA, INFO, CHECK, RESET, DEBUG or ALL)")

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
            self.btn_frame, "💾 Save Changes", self.save_active_preset,
            bg_color=COLOR_SUCCESS, fg_color=BG_DARK, hover_bg="#b5e8b0"
        ).pack(side=tk.LEFT, padx=(0, 10))

        self.create_flat_button(
            self.btn_frame, "▶ Save & Start Bot", self.run_bot,
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
        self.create_flat_button(
            self.btn_frame, "Apply to All", self.apply_current_to_all_presets,
            bg_color=BG_PANEL, fg_color=TEXT_MAIN, hover_bg=BG_INPUT
        ).pack(side=tk.RIGHT, padx=(0, 10))

    def apply_current_to_all_presets(self):
        """Copy the current preset settings to every preset without copying secrets."""
        if not self.current_preset:
            messagebox.showwarning("Warning", "No preset selected.")
            return
        if not self.save_active_preset(show_success=False):
            return
        preserve_identity = messagebox.askyesnocancel(
            "Apply to All Presets",
            "Apply these settings to every preset?\n\n"
            "Yes: preserve each preset's channels, prefixes, account identity, autostart, and tokens (recommended).\n"
            "No: copy every non-secret field.\n"
            "Cancel: do nothing.",
            parent=self.root,
        )
        if preserve_identity is None:
            return

        import copy
        source = copy.deepcopy(self.presets[self.current_preset])
        identity_keys = {
            "channel_id", "command_channel_id", "forcedivorce_channel_id",
            "prefix", "mudae_prefix", "main_account_id", "autostart",
        }
        for preset_name, existing in list(self.presets.items()):
            if preset_name == self.current_preset:
                continue
            replacement = copy.deepcopy(source)
            replacement["token"] = ""
            replacement.pop("tokens", None)
            if preserve_identity:
                for key in identity_keys:
                    if key in existing:
                        replacement[key] = copy.deepcopy(existing[key])
            self.presets[preset_name] = replacement
        if not self.save_presets():
            return
        messagebox.showinfo(
            "Applied",
            f"Settings were applied to {max(0, len(self.presets) - 1)} other preset(s). "
            "Secure tokens were not changed.",
            parent=self.root,
        )

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

        if key in {"token", "additional_tokens"}:
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

        if key in {"token", "additional_tokens"}:
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

    def add_custom_emoji_toggle(self, parent, entry, padx=0, enable_callback=None):
        """Keep manual emoji input available without duplicating the icon grid."""
        entry.pack_forget()
        visible = tk.BooleanVar(value=False)
        button = tk.Button(
            parent,
            text="Add custom emoji",
            bg=BG_PANEL,
            fg=TEXT_MAIN,
            activebackground=BG_INPUT,
            activeforeground=TEXT_MAIN,
            bd=0,
            font=("Segoe UI", 8),
            padx=8,
            pady=3,
            cursor="hand2",
        )
        button.pack(anchor=tk.W, padx=padx, pady=(3, 0))

        def toggle():
            if not visible.get():
                if enable_callback:
                    enable_callback()
                entry.pack(fill=tk.X, padx=padx, pady=(4, 0), after=button)
                button.configure(text="Hide custom emoji input")
                visible.set(True)
            else:
                entry.pack_forget()
                button.configure(text="Add custom emoji")
                visible.set(False)

        button.configure(command=toggle)
        return button

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

        option_sets = {
            "kakera_priority_order": ["kakeraP", "kakeraC", "kakeraL", "kakeraW", "kakeraR", "kakeraO", "kakeraD", "kakeraY", "kakeraG", "kakeraT", "kakera"],
            "sphere_click_targets": ["spP", "spB", "spT", "spG", "spY", "spO", "spR", "spW", "spL", "spD", "spM", "spU"],
        }
        if key in option_sets:
            picker = EmojiOptionPicker(container, entry, option_sets[key], reorderable=(key == "kakera_priority_order"))
            picker.pack(fill=tk.X, before=entry)
            self.add_custom_emoji_toggle(container, entry)

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

        option_sets = {
            "kakera_emojis": ["kakeraY", "kakeraO", "kakeraR", "kakeraW", "kakeraL", "kakeraP", "kakeraD", "kakeraC", "kakeraG", "kakeraT", "kakera"],
            "chaos_emojis": ["kakeraY", "kakeraO", "kakeraR", "kakeraW", "kakeraL", "kakeraP", "kakeraD", "kakeraC", "kakeraG", "kakeraT", "kakera"],
            "sphere_perk_emojis": ["kakeraY", "kakeraO", "kakeraR", "kakeraW", "kakeraL", "kakeraP", "kakeraD", "kakeraC", "kakeraG", "kakeraT", "kakera"],
        }
        if key in option_sets:
            picker = EmojiOptionPicker(container, entry, option_sets[key])
            picker.pack(fill=tk.X, padx=(20, 0), before=entry)
            picker.enable_callback = lambda: var.set(True)
            self.add_custom_emoji_toggle(container, entry, padx=20, enable_callback=lambda: var.set(True))

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

    def _populate_quick_setup(self, data, stored_tokens=None):
        """Mirror the selected preset into the small guided form."""
        stored_tokens = stored_tokens if stored_tokens is not None else []

        def set_entry(key, value, placeholder=None):
            widget = self.quick_widgets.get(key)
            if not widget:
                return
            widget.delete(0, tk.END)
            value = "" if value is None else str(value)
            if not value and placeholder:
                widget.insert(0, placeholder)
                widget.configure(fg=TEXT_MUTED)
            else:
                widget.insert(0, value)
                widget.configure(fg=TEXT_MAIN)

        set_entry("token", stored_tokens[0] if stored_tokens else "", "Paste your token here")
        set_entry("additional_tokens", ", ".join(stored_tokens[1:]), "Leave empty for a single account")
        set_entry("channel_id", data.get("channel_id", ""), "Paste the Discord channel ID")
        set_entry("min_kakera", data.get("min_kakera", DEFAULTS["min_kakera"]), "100")
        roll_combo = self.quick_widgets.get("roll_command")
        if roll_combo:
            roll_combo.set(data.get("roll_command", RECOMMENDED_PRESET_OVERRIDES["roll_command"]))

        for key in ("wishlist", "series_wishlist", "avoid_list"):
            widget = self.quick_widgets.get(key)
            if widget:
                widget.delete(0, tk.END)
                value = data.get(key, [])
                if isinstance(value, list):
                    widget.insert(0, ", ".join(str(item) for item in value))

        for key in ("rolling", "reactive_snipe_on_own_rolls", "use_slash_rolls", "kakera_reaction_snipe_mode", "snipe_mode"):
            var = self.quick_widgets.get(key)
            if isinstance(var, tk.BooleanVar):
                default = RECOMMENDED_PRESET_OVERRIDES.get(
                    key,
                    next((item[2] for item in BOOL_SETTINGS if item[0] == key), False),
                )
                var.set(bool(data.get(key, default)))
        self.update_quick_summary()

    def on_preset_select(self, event):
        """Load the clicked preset immediately while retaining re-entry safety."""
        if self.loading_preset:
            return
        selection = self.preset_listbox.curselection()
        if not selection:
            return
        preset_name = self.preset_listbox.get(selection[0])
        if preset_name == self.current_preset:
            return

        self._preset_selection_generation += 1
        generation = self._preset_selection_generation
        if self._preset_selection_in_progress:
            self._pending_preset_selection = (preset_name, generation)
            return
        self._commit_preset_selection(preset_name, generation)

    def _commit_preset_selection(self, preset_name, generation):
        """Apply a still-current listbox selection as one atomic transition."""
        if (
            generation != self._preset_selection_generation
            or self.loading_preset
            or preset_name == self.current_preset
        ):
            return
        if self._preset_selection_in_progress:
            self._pending_preset_selection = (preset_name, generation)
            return
        if preset_name not in self.presets:
            return

        self._preset_selection_in_progress = True
        try:
            can_switch = self.prompt_unsaved_changes()
            if generation != self._preset_selection_generation:
                return
            if can_switch:
                self.select_preset(preset_name)
            else:
                self.update_listbox_selection(self.current_preset)
        finally:
            self._preset_selection_in_progress = False
            pending = self._pending_preset_selection
            self._pending_preset_selection = None
            if pending and pending[1] == self._preset_selection_generation:
                self._commit_preset_selection(*pending)

    def select_preset(self, preset_name):
        """Load preset data into the form with loading/dirty flag safety wrapper."""
        if preset_name not in self.presets:
            return False
        self.loading_preset = True
        try:
            self._select_preset_impl(preset_name)
        finally:
            self.loading_preset = False
            self.is_dirty = False
        return True

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
        stored_tokens = self.secret_store.get_tokens(
            preset_name,
            data.get("tokens") or data.get("token", ""),
        )
        for key in ["token", "additional_tokens", "prefix", "mudae_prefix", "channel_id", "command_channel_id", "forcedivorce_channel_id",
                    "roll_command",
                    "min_kakera", "delay_seconds", "start_delay", "roll_speed",
                    "snipe_delay", "series_snipe_delay", "kakera_snipe_threshold",
                    "kakera_reaction_snipe_delay", "humanization_window_minutes",
                    "humanization_inactivity_seconds", "reactive_snipe_delay",
                    "claim_interval", "roll_interval", "auto_us_limit",
                    "auto_rolls_limit", "panic_roll_minutes", "max_dk_power", "auto_dk_min_power",
                    "main_account_id", "webhook_url", "auto_divorce_max_kakera",
                    "max_claim_rank", "max_like_rank", "hybrid_panic_instant_claim_min_kakera",
                    "hybrid_panic_instant_claim_max_rank", "oh_unknown_explore_clicks"]:
            if key in self.widgets:
                widget = self.widgets[key]
                if isinstance(widget, (ttk.Entry, tk.Entry)):
                    widget.delete(0, tk.END)
                    if key == "token":
                        value = stored_tokens[0] if stored_tokens else ""
                    elif key == "additional_tokens":
                        value = ", ".join(stored_tokens[1:])
                    else:
                        value = data.get(key, DEFAULTS.get(key, ""))
                    if value is not None:
                        widget.insert(0, str(value))

        # Populate boolean fields
        for key in ["rolling", "use_slash_rolls", "snipe_mode", "snipe_ignore_min_kakera_reset",
                    "series_snipe_mode", "series_snipe_only_self_rolls", "kakera_snipe_mode", "kakera_reaction_snipe_mode",
                    "reactive_snipe_on_own_rolls", "key_mode", "only_chaos",
                    "auto_free_claim",
                    "humanization_enabled", "dk_power_management", "skip_initial_commands",
                    "time_rolls_to_claim_reset", "rt_ignore_min_kakera_for_wishlist",
                    "rt_only_self_rolls", "auto_us_enabled", "auto_us_stop_on_claim",
                    "bulk_us_enabled",
                    "auto_rolls_enabled", "auto_rolls_in_key_mode", "auto_rolls_only_claim_hour",
                    "autostart", "debug_mode", "auto_mk_enabled", "auto_mk_full_power_only", "lurker_mode",
                    "auto_rt_after_claim", "mk_only", "auto_dk_enabled",
                    "enable_snipe_chat_reactions", "enable_kakera_snipe_chat_reactions", "op_perk_5_only", "farm_character_enabled", "farm_forcedivorce_before_roll", "farm_forcedivorce_after_claim", "farm_forcedivorce_after_other_claim",
                    "auto_divorce_enabled", "auto_divorce_protect_wishes", "mk_bypass_power_check", "auto_p_enabled", "auto_oh_enabled", "oh_use_individually", "auto_oc_enabled", "oc_collect_after_red",
                    "enable_hybrid_panic_claim", "immediate_kakera_click", "collect_purple_kakera", "wish_starwish_kakera_only"]:
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
                    "snipe_chat_messages", "kakera_snipe_chat_messages", "farm_characters",
                    "auto_divorce_series", "auto_divorce_blacklist", "auto_divorce_blacklist_series",
                    "snipe_channels", "kakera_snipe_channels", "sphere_click_targets", "oh_priority_order", "oc_reward_priority_order",
                    "webhook_log_types", "debug_log_categories", "character_snipe_targets"]:
            if key in self.widgets:
                widget = self.widgets[key]
                if isinstance(widget, (ttk.Entry, tk.Entry, ChipListWidget)):
                    value = data.get(key, DEFAULTS.get(key, []))
                    if key == "farm_characters" and not value and data.get("farm_character"):
                        value = [data["farm_character"]]
                    if isinstance(value, list):
                        serialized = ", ".join(value)
                        if isinstance(widget, ChipListWidget):
                            widget.replace(serialized)
                        else:
                            widget.delete(0, tk.END)
                            widget.insert(0, serialized)

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
                    value = data[key]
                    if isinstance(value, list):
                        serialized = ", ".join(value)
                        if isinstance(entry, ChipListWidget):
                            entry.replace(serialized)
                        else:
                            entry.delete(0, tk.END)
                            entry.insert(0, serialized)
                else:
                    # Context-specific overrides inherit the regular Kakera
                    # selection. Reflect that effective runtime value instead
                    # of displaying a misleading all-colours default.
                    effective_defaults = defaults
                    if key in ("chaos_emojis", "sphere_perk_emojis"):
                        effective_defaults = data.get("kakera_emojis", DEFAULT_KAKERA_EMOJIS)
                    var.set(False)
                    entry.configure(state="normal")
                    serialized = ", ".join(effective_defaults)
                    if isinstance(entry, ChipListWidget):
                        entry.replace(serialized)
                    else:
                        entry.delete(0, tk.END)
                        entry.insert(0, serialized)
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

        self._populate_quick_setup(data, stored_tokens=stored_tokens)

        # Update listbox selection
        for i in range(self.preset_listbox.size()):
            if self.preset_listbox.get(i) == preset_name:
                self.preset_listbox.selection_clear(0, tk.END)
                self.preset_listbox.selection_set(i)
                break

    def _persist_preset_data(self, data, resolved_tokens, show_success=True, require_runtime=False):
        """Validate and persist a preset draft or a runtime-ready configuration."""
        validation_errors = validate_preset(
            data,
            resolved_token=resolved_tokens,
            require_runtime=require_runtime,
        )
        if validation_errors:
            messagebox.showerror("Validation Error", "\n".join(validation_errors), parent=self.root)
            return False

        try:
            self.secret_store.set_tokens(self.current_preset, resolved_tokens)
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
        was_loading = self.loading_preset
        self.loading_preset = True
        try:
            self._populate_quick_setup(
                data,
                stored_tokens=self.secret_store.get_tokens(self.current_preset, ""),
            )
        finally:
            self.loading_preset = was_loading
        self.is_dirty = False
        return True

    def save_current_preset(self, show_success=True, require_runtime=False):
        """Save the current form data to the preset."""
        if not self.current_preset:
            messagebox.showwarning("Warning", "No preset selected.")
            return False

        data = {}
        resolved_token = self.widgets["token"].get().strip() if "token" in self.widgets else ""
        additional_token_text = (
            self.widgets["additional_tokens"].get().strip()
            if "additional_tokens" in self.widgets
            else ""
        )
        resolved_tokens = []
        seen_tokens = set()
        for candidate in [resolved_token] + re.split(r"[\s,]+", additional_token_text):
            cleaned_token = str(candidate or "").strip()
            if cleaned_token and cleaned_token not in seen_tokens:
                seen_tokens.add(cleaned_token)
                resolved_tokens.append(cleaned_token)

        # Collect text fields
        # [NEW] Include main_account_id and farm_character in text fields collection
        for key in ["prefix", "mudae_prefix", "channel_id", "command_channel_id", "forcedivorce_channel_id", "roll_command", "main_account_id", "webhook_url"]:
            if key in self.widgets:
                value = self.widgets[key].get().strip()
                # Special handling for channel_id
                if key in ("channel_id", "command_channel_id", "forcedivorce_channel_id") and value:
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
                    "auto_rolls_limit", "panic_roll_minutes", "max_dk_power", "auto_dk_min_power",
                    "auto_divorce_max_kakera", "max_claim_rank", "max_like_rank",
                    "hybrid_panic_instant_claim_min_kakera", "hybrid_panic_instant_claim_max_rank",
                    "oh_unknown_explore_clicks"]
        for key in numeric_keys:
            if key in self.widgets:
                value = self.widgets[key].get().strip()
                if value:
                    try:
                        # Determine type
                        if key in ["min_kakera", "start_delay", "kakera_snipe_threshold",
                                   "humanization_window_minutes", "humanization_inactivity_seconds",
                                   "claim_interval", "roll_interval", "auto_us_limit",
                                   "auto_rolls_limit", "panic_roll_minutes", "max_dk_power", "auto_dk_min_power",
                                   "auto_divorce_max_kakera", "max_claim_rank", "max_like_rank",
                                   "hybrid_panic_instant_claim_min_kakera", "hybrid_panic_instant_claim_max_rank",
                                   "oh_unknown_explore_clicks"]:
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
                    "series_snipe_mode", "series_snipe_only_self_rolls", "kakera_snipe_mode", "kakera_reaction_snipe_mode",
                    "reactive_snipe_on_own_rolls", "key_mode", "only_chaos",
                    "auto_free_claim",
                    "humanization_enabled", "dk_power_management", "skip_initial_commands",
                    "time_rolls_to_claim_reset", "rt_ignore_min_kakera_for_wishlist",
                    "rt_only_self_rolls", "auto_us_enabled", "auto_us_stop_on_claim",
                    "bulk_us_enabled",
                    "auto_rolls_enabled", "auto_rolls_in_key_mode", "auto_rolls_only_claim_hour",
                    "autostart", "debug_mode", "auto_mk_enabled", "auto_mk_full_power_only", "lurker_mode",
                    "auto_rt_after_claim", "mk_only", "auto_dk_enabled",
                    "enable_snipe_chat_reactions", "enable_kakera_snipe_chat_reactions", "op_perk_5_only", "farm_character_enabled", "farm_forcedivorce_before_roll", "farm_forcedivorce_after_claim", "farm_forcedivorce_after_other_claim",
                    "auto_divorce_enabled", "auto_divorce_protect_wishes", "mk_bypass_power_check", "auto_p_enabled", "auto_oh_enabled", "oh_use_individually", "auto_oc_enabled", "oc_collect_after_red",
                    "enable_hybrid_panic_claim", "immediate_kakera_click", "collect_purple_kakera", "wish_starwish_kakera_only"]:
            if key in self.widgets:
                data[key] = self.widgets[key].get()

        # Collect list fields
        # [NEW] Include randomized_claim_reactions and kakera_priority_order in list collection
        for key in ["wishlist", "series_wishlist", "avoid_list", "kakera_reaction_snipe_targets",
                    "randomized_claim_reactions", "kakera_priority_order",
                    "snipe_chat_messages", "kakera_snipe_chat_messages", "farm_characters",
                    "auto_divorce_series", "auto_divorce_blacklist", "auto_divorce_blacklist_series",
                    "snipe_channels", "kakera_snipe_channels", "sphere_click_targets", "oh_priority_order", "oc_reward_priority_order",
                    "webhook_log_types", "debug_log_categories", "character_snipe_targets"]:
            if key in self.widgets:
                value = self.widgets[key].get().strip()
                if value:
                    data[key] = [item.strip() for item in value.split(",") if item.strip()]
                else:
                    data[key] = []
        data["farm_character"] = data.get("farm_characters", [""])[0] if data.get("farm_characters") else ""

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

        return self._persist_preset_data(
            data,
            resolved_tokens,
            show_success=show_success,
            require_runtime=require_runtime,
        )

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
        active_index = 0
        for active_name in active_names:
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
            active_tokens = self.secret_store.get_tokens(
                active_name,
                self.presets.get(active_name, {}).get("token", ""),
            )
            active_index += max(1, len(active_tokens))

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

            self.presets[name] = build_recommended_preset()
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
                source_tokens = self.secret_store.get_tokens(
                    self.current_preset,
                    self.presets[self.current_preset].get("token", ""),
                )
                if source_tokens:
                    self.secret_store.set_tokens(name, source_tokens)
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
        if self.is_dirty and not self.save_active_preset(show_success=False):
            return

        preset_data = self.presets.get(self.current_preset)
        if not preset_data:
            return

        import copy
        clean_data = copy.deepcopy(preset_data)
        clean_data["token"] = ""
        clean_data.pop("tokens", None)

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

        if not self.save_active_preset(show_success=False, require_runtime=True):
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
            running_preset_names = [
                name for name, process in self.bot_processes.items()
                if process and process.poll() is None
            ]
            stagger_index = sum(
                max(
                    1,
                    len(self.secret_store.get_tokens(
                        name,
                        self.presets.get(name, {}).get("token", ""),
                    )),
                )
                for name in running_preset_names
            )
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
    root.withdraw()
    try:
        import mudae_bot

        mudae_bot.cleanup_after_update()

        def confirm_update(latest_version, changelog):
            return messagebox.askyesno(
                "MudaRemote Update Available",
                (
                    f"MudaRemote v{latest_version} is available.\n\n"
                    f"Changelog:\n{changelog}\n\n"
                    "Install this update now?\n\n"
                    "Your saved presets will be kept."
                ),
                parent=root,
            )

        mudae_bot.check_for_updates(confirm_update=confirm_update)
    except Exception as e:
        print(f"[MudaRemote] Update check failed: {e}")

    app = PresetEditor(root)
    root.deiconify()
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
        preset_data["tokens"] = SecretStore(get_base_path()).get_tokens(
            name,
            preset_data.get("tokens") or preset_data.get("token", ""),
        )
        preset_data["token"] = preset_data["tokens"][0] if preset_data["tokens"] else ""
        if not preset_data["tokens"]:
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
