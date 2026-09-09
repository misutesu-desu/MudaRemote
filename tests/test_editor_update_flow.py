"""Desktop update flows must never run on the Tk event thread.

These tests drive the PresetEditor update plumbing with fake widgets and a
fake mudae_bot whose work blocks until released, proving:

- manifest fetching, downloading, and installation run on a worker thread;
- phase text reaches the visible progress label through the GUI event queue
  while the worker is still blocked;
- confirmation dialogs are raised on the GUI thread, never from the worker;
- failures restore the busy controls and surface the artifact detail;
- a frozen success reaches the immediate-exit handoff without an
  acknowledgement dialog.
"""

import queue
import sys
import threading
import time
import types
import unittest
from unittest import mock

import tkinter as tk

import mudae_preset_editor as _mpe
from mudae_preset_editor import PresetEditor


class _FakeRoot:
    def __init__(self):
        self.scheduled = []
        self.destroyed = False

    def after(self, delay, func):
        self.scheduled.append((delay, func))

    def destroy(self):
        self.destroyed = True


class _FakeWidget:
    def __init__(self, name="widget"):
        self.name = name
        self.configs = []
        self.visible = False
        self.running = False

    def config(self, **kwargs):
        self.configs.append(kwargs)

    def pack(self, **kwargs):
        self.visible = True

    def pack_forget(self):
        self.visible = False

    def start(self, interval=0):
        self.running = True

    def stop(self):
        self.running = False


class _MessageboxRecorder:
    def __init__(self, askyesno_answer=True):
        self.calls = []
        self.askyesno_answer = askyesno_answer

    def _record(self, kind):
        def _show(*args, **kwargs):
            self.calls.append((kind, args, kwargs, threading.current_thread()))
            return None
        return _show

    def askyesno(self, *args, **kwargs):
        self.calls.append(("askyesno", args, kwargs, threading.current_thread()))
        return self.askyesno_answer

    def __getattr__(self, item):
        return self._record(item)


def _make_editor():
    editor = PresetEditor.__new__(PresetEditor)
    editor.root = _FakeRoot()
    editor._update_busy = False
    editor._update_events = queue.Queue()
    editor._update_last_error = None
    editor.check_updates_btn = _FakeWidget("check")
    editor.version_switch_btn = _FakeWidget("switch")
    editor.update_status_lbl = _FakeWidget("status")
    editor.update_progress_bar = _FakeWidget("bar")
    editor.bot_processes = {}
    editor.current_preset = None
    editor.beta_channel_var = types.SimpleNamespace(get=lambda: False)
    return editor


def _pump_until(editor, predicate, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        editor._poll_update_events()
        if predicate():
            return True
        time.sleep(0.01)
    return False


def _button_state(widget, index=-1):
    return widget.configs[index].get("state")


class EditorUpdateFlowTests(unittest.TestCase):
    def setUp(self):
        # patch.object against the imported module: android-bridge tests can
        # evict mudae_preset_editor from sys.modules, after which string
        # targets would patch a re-imported copy the class never sees.
        self.editor = _make_editor()
        self.box = _MessageboxRecorder()
        patcher = mock.patch.object(_mpe, "messagebox", new=self.box)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _install_fake_bot(self, check_for_updates):
        fake = types.SimpleNamespace(check_for_updates=check_for_updates)
        patcher = mock.patch.dict(sys.modules, {"mudae_bot": fake})
        patcher.start()
        self.addCleanup(patcher.stop)

    def _start_version_switch(self, target="v4.6.4", channel="main"):
        with mock.patch.object(_mpe, "VersionSelectorDialog") as dialog:
            self.editor.open_version_selector()
        on_install = dialog.call_args[0][1]
        on_install(target, channel)

    def test_worker_blocked_manifest_still_updates_progress_label_on_gui(self):
        release = threading.Event()
        threads_seen = {}

        def fake_check_for_updates(**kwargs):
            threads_seen["worker"] = threading.current_thread()
            kwargs["progress"]("manifest", "Fetching release manifest for v4.6.4...")
            self.assertTrue(release.wait(5), "test deadlocked waiting for release")
            return "current"

        self._install_fake_bot(fake_check_for_updates)
        self.editor.manual_check_updates()

        # Busy state: indeterminate bar animating, actions locked.
        self.assertTrue(self.editor._update_busy)
        self.assertTrue(self.editor.update_progress_bar.running)
        self.assertTrue(self.editor.update_progress_bar.visible)
        self.assertEqual(_button_state(self.editor.check_updates_btn), tk.DISABLED)
        self.assertEqual(_button_state(self.editor.version_switch_btn), tk.DISABLED)

        # The GUI drains the queued phase while the worker is still blocked.
        shown = _pump_until(
            self.editor,
            lambda: {"text": "Fetching release manifest for v4.6.4..."}
            in self.editor.update_status_lbl.configs,
        )
        self.assertTrue(shown, "progress label never received the queued phase")
        self.assertIsNot(threads_seen["worker"], threading.main_thread())
        self.assertFalse(self.editor.root.destroyed)

        release.set()
        done = _pump_until(self.editor, lambda: not self.editor._update_busy)
        self.assertTrue(done, "worker outcome never reached the GUI")

        # "current" posts the up-to-date dialog on the GUI thread.
        kinds = [kind for kind, _, _, _ in self.box.calls]
        self.assertIn("showinfo", kinds)
        dialog_thread = [t for k, _, _, t in self.box.calls if k == "showinfo"][0]
        self.assertIs(dialog_thread, threading.main_thread())

        # Controls restored, progress dismissed.
        self.assertEqual(_button_state(self.editor.check_updates_btn), tk.NORMAL)
        self.assertEqual(_button_state(self.editor.version_switch_btn), tk.NORMAL)
        self.assertFalse(self.editor.update_progress_bar.running)
        self.assertFalse(self.editor.update_progress_bar.visible)

    def test_confirmation_dialog_runs_on_gui_thread_not_worker(self):
        release = threading.Event()
        outcome = {}

        def fake_check_for_updates(**kwargs):
            worker = threading.current_thread()
            outcome["worker_is_main"] = worker == threading.main_thread()
            outcome["answer"] = kwargs["confirm_update"]("5.0.0", "changelog")
            release.set()
            return "skipped"

        self._install_fake_bot(fake_check_for_updates)
        self.editor.manual_check_updates()

        asked = _pump_until(self.editor, lambda: release.is_set())
        self.assertTrue(asked, "confirmation never reached the GUI queue")
        done = _pump_until(self.editor, lambda: not self.editor._update_busy)
        self.assertTrue(done)

        self.assertFalse(outcome["worker_is_main"])
        self.assertIs(outcome["answer"], True)  # from the recorder default
        ask_threads = [t for k, _, _, t in self.box.calls if k == "askyesno"]
        self.assertEqual(ask_threads, [threading.main_thread()])
        # A cancelled install ("skipped") restores controls without dialogs.
        self.assertEqual(_button_state(self.editor.check_updates_btn), tk.NORMAL)
        self.assertNotIn("showinfo", [k for k, _, _, _ in self.box.calls])

    def test_checksum_failure_surfaces_artifact_detail_and_restores_controls(self):
        detail = (
            "The published download for executable MudaRemote.exe does not match "
            "its checksum.\nURL: https://example.invalid/MudaRemote.exe"
        )

        def fake_check_for_updates(**kwargs):
            kwargs["progress"]("error", detail)
            return "failed"

        self._install_fake_bot(fake_check_for_updates)
        self.box.askyesno_answer = True
        self._start_version_switch()

        done = _pump_until(self.editor, lambda: not self.editor._update_busy)
        self.assertTrue(done)
        self.assertEqual(self.editor._update_last_error, detail)
        errors = [args for k, args, _, _ in self.box.calls if k == "showerror"]
        self.assertEqual(len(errors), 1)
        self.assertIn(detail, " ".join(str(part) for part in errors[0]))
        self.assertEqual(_button_state(self.editor.check_updates_btn), tk.NORMAL)

    def test_frozen_success_exits_immediately_without_dialog(self):
        def fake_check_for_updates(**kwargs):
            return "frozen"

        self._install_fake_bot(fake_check_for_updates)
        self.box.askyesno_answer = True
        self._start_version_switch()

        done = _pump_until(self.editor, lambda: self.editor.root.destroyed)
        self.assertTrue(done, "frozen outcome never reached the exit handoff")
        kinds = [kind for kind, _, _, _ in self.box.calls]
        self.assertNotIn("showinfo", kinds)  # no acknowledgement dialog
        self.assertNotIn("showerror", kinds)

    def test_source_success_relaunches_on_gui_thread_then_exits(self):
        def fake_check_for_updates(**kwargs):
            return "source"

        self._install_fake_bot(fake_check_for_updates)
        self.box.askyesno_answer = True
        seen_threads = []
        with mock.patch.object(
            _mpe, "_relaunch_editor",
            side_effect=lambda: seen_threads.append(threading.current_thread()),
        ) as relaunch:
            self._start_version_switch()
            done = _pump_until(self.editor, lambda: self.editor.root.destroyed)
        self.assertTrue(done, "source outcome never reached the relaunch handoff")
        relaunch.assert_called_once()
        self.assertEqual(seen_threads, [threading.main_thread()])
        kinds = [kind for kind, _, _, _ in self.box.calls]
        self.assertIn("showinfo", kinds)  # source keeps its restart notice dialog

    def test_duplicate_update_actions_are_blocked_while_busy(self):
        called = []
        self._install_fake_bot(lambda **kwargs: called.append(True) or "current")
        self.editor._update_busy = True
        with mock.patch.object(_mpe, "VersionSelectorDialog") as dialog:
            self.editor.manual_check_updates()
            self.editor.open_version_selector()
        self.assertEqual(called, [])
        dialog.assert_not_called()
        warnings = [args for k, args, _, _ in self.box.calls if k == "showwarning"]
        self.assertEqual(len(warnings), 2)
        self.assertTrue(
            all("already in progress" in args[1] for args in warnings),
            warnings,
        )


if __name__ == "__main__":
    unittest.main()
