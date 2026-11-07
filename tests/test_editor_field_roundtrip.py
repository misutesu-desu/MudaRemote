import ast
import os
import unittest

EDITOR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mudae_preset_editor.py")


def _string_lists(function):
    for node in ast.walk(function):
        if isinstance(node, ast.List) and node.elts and all(
            isinstance(item, ast.Constant) and isinstance(item.value, str) for item in node.elts
        ):
            yield {item.value for item in node.elts}


class EditorFieldRoundTripTests(unittest.TestCase):
    def test_every_saved_text_field_is_loaded_back_into_the_form(self):
        # Reported: the $dk time was written to the preset, but the field came
        # back empty when the preset was opened and the next save erased it.
        with open(EDITOR, encoding="utf-8") as handle:
            tree = ast.parse(handle.read())
        functions = {node.name: node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
        saved = next(keys for keys in _string_lists(functions["save_current_preset"]) if "webhook_url" in keys)
        loaded = next(keys for keys in _string_lists(functions["_select_preset_impl"]) if "webhook_url" in keys)
        self.assertEqual(saved - loaded, set())

    def test_every_list_field_is_saved_and_loaded(self):
        # Reported: Never Snipe From These Users was never written to the
        # preset, and the text typed for one preset stayed in the form when
        # another preset was opened.
        with open(EDITOR, encoding="utf-8") as handle:
            tree = ast.parse(handle.read())
        functions = {node.name: node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
        shown = {
            node.args[1].value
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and getattr(node.func, "attr", None) == "add_list_field"
            and len(node.args) > 1
            and isinstance(node.args[1], ast.Constant)
        }
        saved = next(keys for keys in _string_lists(functions["save_current_preset"]) if "wishlist" in keys)
        loaded = next(keys for keys in _string_lists(functions["_select_preset_impl"]) if "wishlist" in keys)
        self.assertIn("snipe_ignore_users", shown)
        self.assertEqual(shown - saved, set())
        self.assertEqual(shown - loaded, set())


if __name__ == "__main__":
    unittest.main()
