from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

from helpers import LOC_GUARD, REPO_ROOT, LocGuardTestCase, write_config, write_lines


class SourceExtensionTests(LocGuardTestCase):
    def test_new_source_extensions_are_checked_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for name in ["Main.kt", "build.kts", "App.swift", "widget.vue", "script.rb", "app.dart", "index.php"]:
                write_lines(root / name, 2)
            write_lines(root / "notes.unknown", 2)

            result = self.run_guard(root, ".", "--warn", "1", "--fail", "3", "--json")

            self.assertEqual(result.returncode, 1, result.stderr)
            paths = {item["path"] for item in self.read_json(result)["files"]}
            self.assertEqual(
                paths,
                {"Main.kt", "build.kts", "App.swift", "widget.vue", "script.rb", "app.dart", "index.php"},
            )

    def test_new_comment_prefixes_are_ignored_for_kotlin_and_ruby(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "Main.kt").write_text("// comment\nval answer = 42\n", encoding="utf-8")
            (root / "script.rb").write_text("# comment\nanswer = 42\n", encoding="utf-8")

            result = self.run_guard(
                root, ".", "--warn", "1", "--fail", "3", "--ignore-comment-lines", "--json"
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                {item["path"]: item["countedLoc"] for item in self.read_json(result)["files"]},
                {"Main.kt": 1, "script.rb": 1},
            )

    def test_include_still_adds_a_non_default_extension_with_or_without_dot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_lines(root / "one.custom", 2)
            write_lines(root / "two.extra", 2)

            result = self.run_guard(
                root, ".", "--include", "custom", "--include", ".extra", "--warn", "1", "--fail", "3", "--json"
            )

            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertEqual(
                {item["path"] for item in self.read_json(result)["files"]},
                {"one.custom", "two.extra"},
            )

    def test_example_extensions_match_shipped_defaults(self) -> None:
        spec = importlib.util.spec_from_file_location("loc_guard", LOC_GUARD)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        example = json.loads((REPO_ROOT / "examples" / "loc-guard.config.json").read_text(encoding="utf-8"))

        self.assertEqual(set(example["includeExtensions"]), module.DEFAULT_INCLUDE_EXTENSIONS)


if __name__ == "__main__":
    import unittest

    unittest.main()
