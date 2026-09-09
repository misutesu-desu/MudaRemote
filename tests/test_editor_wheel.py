"""Mouse-wheel routing tests for the preset editor (needs a display; skipped otherwise)."""

import unittest

try:
    import tkinter as tk
except ImportError:  # pragma: no cover
    tk = None

from mudae_preset_editor import PresetEditor, VersionSelectorDialog


def _can_open_tk():
    if tk is None:
        return False
    try:
        root = tk.Tk()
    except tk.TclError:
        return False
    root.destroy()
    return True


class _EditorStub:
    """Minimal object carrying only the state _on_mousewheel touches."""

    _on_mousewheel = PresetEditor._on_mousewheel

    def __init__(self, root, canvas, quick_canvas=None):
        self.root = root
        self.canvas = canvas
        self.quick_canvas = quick_canvas
        self.editor_mode = "advanced"


@unittest.skipUnless(_can_open_tk(), "no display available for tkinter")
class MouseWheelRoutingTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.geometry("400x300+80+80")
        self.canvas = tk.Canvas(self.root, bg="white")
        inner = tk.Frame(self.canvas, bg="white")
        self.inner_label = tk.Label(inner, text="settings")
        self.window_id = self.canvas.create_window((0, 0), window=inner, anchor=tk.NW)
        self.inner_label.pack()
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.configure(yscrollincrement=1)
        self.canvas.configure(scrollregion=(0, 0, 100, 4000))
        self.root.update()
        self.stub = _EditorStub(self.root, self.canvas)
        self.canvas.bind_all("<MouseWheel>", self.stub._on_mousewheel)
        self.canvas.bind_all("<Button-4>", self.stub._on_mousewheel)
        self.canvas.bind_all("<Button-5>", self.stub._on_mousewheel)

    def tearDown(self):
        self.root.unbind_all("<MouseWheel>")
        self.root.unbind_all("<Button-4>")
        self.root.unbind_all("<Button-5>")
        self.root.destroy()

    def _wheel_at(self, widget, offset_x=5, offset_y=5, delta=120):
        widget.update_idletasks()
        x = widget.winfo_rootx() + offset_x
        y = widget.winfo_rooty() + offset_y
        widget.event_generate("<MouseWheel>", x=offset_x, y=offset_y, delta=delta)
        self.root.update_idletasks()
        return x, y

    def _drain(self, predicate, timeout=3.0):
        import time as _time
        deadline = _time.time() + timeout
        while _time.time() < deadline:
            self.root.update()
            if predicate():
                return True
            _time.sleep(0.01)
        return False

    def _assert_scrolls(self):
        before = self.canvas.yview()[0]
        self._wheel_at(self.inner_label, offset_x=2, offset_y=2)
        after = self.canvas.yview()[0]
        self.assertGreater(before, after)

    def test_wheel_over_editor_canvas_scrolls_the_canvas(self):
        self.canvas.yview_moveto(0.5)
        self._assert_scrolls()

    def test_wheel_over_dialog_does_not_move_the_background_canvas(self):
        self.canvas.yview_moveto(0.4)
        before = self.canvas.yview()[0]
        dialog = tk.Toplevel(self.root)
        dialog.geometry("+100+100")
        listbox = tk.Listbox(dialog)
        listbox.insert(tk.END, "v4.9.0")
        listbox.pack()
        dialog.update()
        self.root.update()
        self._wheel_at(listbox)
        self.assertAlmostEqual(self.canvas.yview()[0], before, places=6)
        dialog.destroy()

    def test_wheel_over_main_window_listbox_does_not_move_the_canvas(self):
        self.canvas.yview_moveto(0.4)
        before = self.canvas.yview()[0]
        listbox = tk.Listbox(self.root)
        listbox.place(in_=self.root, x=250, y=10, width=100, height=100)
        self.root.update()
        self._wheel_at(listbox)
        self.assertAlmostEqual(self.canvas.yview()[0], before, places=6)
        listbox.destroy()

    def _install_via_dialog(self, initial_channel, toggle_to=None):
        import unittest.mock as mock
        fake = [{"tag": "v4.9.1-beta.4", "prerelease": True}, {"tag": "v4.9.0", "prerelease": False}]
        captured = []
        with mock.patch("mudae_core.versioning.fetch_available_releases", return_value=fake):
            dialog = VersionSelectorDialog(
                self.root, on_install=lambda tag, ch: captured.append((tag, ch)), channel=initial_channel,
            )
            self.assertTrue(self._drain(
                lambda: dialog.listbox.get(0, tk.END) != ("Loading releases from GitHub...",)
            ))
            if toggle_to is not None:
                dialog.beta_var.set(toggle_to)
            dialog.listbox.selection_set(1)
            dialog._do_install()
        return captured

    def test_version_selector_release_rows_map_to_real_tags(self):
        self.assertEqual(self._install_via_dialog("beta"), [("v4.9.0", "beta")])

    def test_dialog_reports_its_current_channel_on_install_both_directions(self):
        # Open from Stable, flip Beta on: the install callback carries beta.
        self.assertEqual(self._install_via_dialog("main", toggle_to=True), [("v4.9.0", "beta")])
        # Open from Beta, flip Beta off: the callback carries main.
        self.assertEqual(self._install_via_dialog("beta", toggle_to=False), [("v4.9.0", "main")])

    def test_version_selector_populates_and_reports_errors_honestly(self):
        import unittest.mock as mock
        fake = [{"tag": "v4.9.0", "prerelease": False, "version": "4.9.0"}]
        with mock.patch("mudae_core.versioning.fetch_available_releases", return_value=fake):
            dialog = VersionSelectorDialog(self.root, on_install=lambda tag, ch=None: None, channel="main")
            loaded = self._drain(lambda: dialog.listbox.get(0, tk.END) != ("Loading releases from GitHub...",))
            self.assertTrue(loaded)
            self.assertEqual(dialog.listbox.get(0, tk.END), ("v4.9.0 [Stable]",))
            dialog._populate([], "network failure", "main", dialog._fetch_generation)
            contents = dialog.listbox.get(0, tk.END)
            self.assertEqual(contents[0], "Failed to load releases:")
            self.assertTrue(any("network failure" in line for line in contents))
            self.assertFalse(any("v4.9.1-beta.3" in line for line in contents))
            dialog._populate(fake, None, "main", dialog._fetch_generation)
            self.assertEqual(dialog.listbox.get(0, tk.END), ("v4.9.0 [Stable]",))
            dialog._close()

if __name__ == "__main__":
    unittest.main()
