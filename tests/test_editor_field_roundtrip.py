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


if __name__ == "__main__":
    unittest.main()
