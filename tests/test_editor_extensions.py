import os
import tempfile
import tkinter as tk
import unittest
from unittest import mock

import mudae_preset_editor
from mudae_preset_editor import PresetEditor


class FakeExtension:
    title = "Cloud"

    def __init__(self):
        self.built_with = None
        self.shown = 0
        self.closed = 0

    def build(self, parent, editor):
        self.built_with = (parent, editor)
        tk.Label(parent, text="cloud view").pack()

    def on_show(self):
        self.shown += 1

    def on_close(self):
        self.closed += 1


class EditorExtensionTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest("Tk unavailable: {}".format(error))
        self.root.withdraw()
        self.addCleanup(self._destroy)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        patches = [
            mock.patch.object(mudae_preset_editor, "PRESETS_FILE", os.path.join(self.directory.name, "presets.json")),
            mock.patch.object(mudae_preset_editor, "get_base_path", return_value=self.directory.name),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def _destroy(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def test_without_extensions_editor_is_unchanged(self):
        editor = PresetEditor(self.root)
        self.assertFalse(hasattr(editor, "_nav_bar"))
        self.assertEqual(editor.extensions, [])
        self.assertTrue(editor.main_frame.winfo_manager())

    def test_extension_view_switches_and_returns_to_local(self):
        extension = FakeExtension()
        editor = PresetEditor(self.root, extensions=[extension])
        self.assertIs(extension.built_with[1], editor)
        self.assertEqual(set(editor._extension_buttons), {"Local", "Cloud"})
        editor.show_view("Cloud")
        self.assertEqual(extension.shown, 1)
        self.assertEqual(editor.main_frame.winfo_manager(), "")
        self.assertEqual(editor._extension_frames["Cloud"].winfo_manager(), "pack")
        editor.show_view("Local")
        self.assertEqual(editor._extension_frames["Cloud"].winfo_manager(), "")
        self.assertTrue(editor.main_frame.winfo_manager())
        with self.assertRaises(KeyError):
            editor.show_view("Missing")

    def test_unsaved_local_changes_block_leaving_local_view(self):
        editor = PresetEditor(self.root, extensions=[FakeExtension()])
        editor.is_dirty = True
        with mock.patch.object(editor, "prompt_unsaved_changes", return_value=False):
            editor.show_view("Cloud")
        self.assertEqual(editor._active_view, "Local")

    def test_close_notifies_extensions(self):
        extension = FakeExtension()
        editor = PresetEditor(self.root, extensions=[extension])
        editor.on_close()
        self.assertEqual(extension.closed, 1)

    def test_launch_gui_can_skip_public_update_check(self):
        with mock.patch("mudae_bot.check_for_updates") as check, \
                mock.patch.object(mudae_preset_editor.tk.Tk, "mainloop"), \
                mock.patch.object(mudae_preset_editor, "PresetEditor") as editor_class, \
                mock.patch.object(mudae_preset_editor.tk.Tk, "deiconify"):
            extensions = [FakeExtension()]
            mudae_preset_editor.launch_gui(extensions=extensions, check_updates=False)
        check.assert_not_called()
        editor_class.assert_called_once()
        self.assertEqual(editor_class.call_args.kwargs["extensions"], extensions)


if __name__ == "__main__":
    unittest.main()
