from __future__ import annotations

import tempfile
from pathlib import Path

from helpers import LocGuardTestCase, write_config, write_lines


class ThresholdOverrideTests(LocGuardTestCase):
    def test_global_thresholds_are_unchanged_without_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_lines(root / "warn.py", 4)
            write_lines(root / "fail.py", 7)

            result = self.run_guard(root, ".", "--warn", "3", "--fail", "6", "--json")

            self.assertEqual(result.returncode, 2, result.stderr)
            files = {item["path"]: item for item in self.read_json(result)["files"]}
            self.assertEqual(files["warn.py"]["status"], "warn")
            self.assertEqual(files["fail.py"]["status"], "fail")
            self.assertEqual(files["warn.py"]["overrideIndex"], None)
            self.assertEqual((files["warn.py"]["warnAt"], files["warn.py"]["failAt"]), (3, 6))

    def test_matching_override_warns_while_non_matching_file_uses_global_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_lines(root / "match.py", 7)
            write_lines(root / "other.ts", 7)
            config = write_config(root, {
                "warnAt": 3,
                "failAt": 6,
                "overrides": [{"match": ["*.py"], "warnAt": 6, "failAt": 9}],
            })

            result = self.run_guard(root, ".", "--config", str(config), "--json")

            self.assertEqual(result.returncode, 2, result.stderr)
            files = {item["path"]: item for item in self.read_json(result)["files"]}
            self.assertEqual(files["match.py"]["status"], "warn")
            self.assertEqual((files["match.py"]["warnAt"], files["match.py"]["failAt"]), (6, 9))
            self.assertEqual(files["match.py"]["overrideIndex"], 0)
            self.assertEqual(files["other.ts"]["status"], "fail")
            self.assertEqual((files["other.ts"]["warnAt"], files["other.ts"]["failAt"]), (3, 6))
            self.assertIsNone(files["other.ts"]["overrideIndex"])

    def test_last_matching_override_wins_at_root_and_nested_depth(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_lines(root / "RootTest.kt", 10)
            write_lines(root / "src" / "NestedTest.kt", 10)
            config = write_config(root, {
                "warnAt": 3,
                "failAt": 6,
                "overrides": [
                    {"match": ["**/*Test.kt"], "warnAt": 6, "failAt": 9},
                    {"match": ["RootTest.kt", "src/**"], "warnAt": 9, "failAt": 12},
                ],
            })

            result = self.run_guard(root, ".", "--config", str(config), "--json")

            self.assertEqual(result.returncode, 1, result.stderr)
            for item in self.read_json(result)["files"]:
                self.assertEqual(item["status"], "warn")
                self.assertEqual(item["overrideIndex"], 1)
                self.assertEqual((item["warnAt"], item["failAt"]), (9, 12))

    def test_cli_thresholds_only_replace_global_thresholds(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_lines(root / "match.py", 7)
            write_lines(root / "other.ts", 7)
            config = write_config(root, {
                "warnAt": 3,
                "failAt": 6,
                "overrides": [{"match": ["*.py"], "warnAt": 6, "failAt": 9}],
            })

            result = self.run_guard(
                root, ".", "--config", str(config), "--warn", "10", "--fail", "20", "--json"
            )

            self.assertEqual(result.returncode, 1, result.stderr)
            files = {item["path"]: item for item in self.read_json(result)["files"]}
            self.assertEqual((files["match.py"]["warnAt"], files["match.py"]["failAt"]), (6, 9))
            self.assertEqual((files["other.ts"]["warnAt"], files["other.ts"]["failAt"]), (10, 20))

    def test_override_and_exemption_use_effective_warning_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_lines(root / "tests" / "large.py", 7)
            write_lines(root / "tests" / "small.py", 5)
            config = write_config(root, {
                "warnAt": 3,
                "failAt": 6,
                "overrides": [{"match": ["**/*.py"], "warnAt": 6, "failAt": 9}],
                "allowedLargeFiles": [
                    {"path": "**/large.py", "reason": "Approved cohesive fixture."},
                    {"path": "**/small.py", "reason": "Below the effective warning threshold."},
                ],
            })

            result = self.run_guard(root, ".", "--config", str(config), "--json")

            self.assertEqual(result.returncode, 0, result.stderr)
            files = {item["path"]: item for item in self.read_json(result)["files"]}
            self.assertEqual(files["tests/large.py"]["status"], "exempt")
            self.assertEqual(files["tests/large.py"]["reason"], "Approved cohesive fixture.")
            self.assertEqual(files["tests/large.py"]["overrideIndex"], 0)
            self.assertEqual(files["tests/small.py"]["status"], "ok")
            self.assertIsNone(files["tests/small.py"]["reason"])

    def test_human_report_explains_override_for_non_ok_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_lines(root / "large.py", 7)
            config = write_config(root, {
                "warnAt": 3,
                "failAt": 6,
                "overrides": [{"match": ["*.py"], "warnAt": 6, "failAt": 9}],
            })

            result = self.run_guard(root, ".", "--config", str(config))

            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn("Effective thresholds: warn 6, fail 9 (override 0)", result.stdout)

    def test_invalid_top_level_and_entry_types_return_configuration_error(self) -> None:
        values = [None, {}, "rule", [None], ["rule"]]
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for value in values:
                with self.subTest(value=value):
                    config = write_config(root, {"overrides": value})
                    result = self.run_guard(root, ".", "--config", str(config), "--json")
                    self.assertEqual(result.returncode, 3)
                    self.assertIn("overrides", self.read_json(result)["error"])

    def test_invalid_match_values_return_configuration_error(self) -> None:
        entries = [
            {},
            {"match": []},
            {"match": "*.py"},
            {"match": [""]},
            {"match": ["   "]},
            {"match": [123]},
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for entry in entries:
                with self.subTest(entry=entry):
                    entry = {**entry, "warnAt": 3, "failAt": 6}
                    config = write_config(root, {"overrides": [entry]})
                    result = self.run_guard(root, ".", "--config", str(config), "--json")
                    self.assertEqual(result.returncode, 3)
                    self.assertIn("overrides[0].match", self.read_json(result)["error"])

    def test_invalid_threshold_values_return_configuration_error(self) -> None:
        cases = [
            ({"failAt": 6}, "warnAt"),
            ({"warnAt": 3}, "failAt"),
            ({"warnAt": 0, "failAt": 6}, "warnAt"),
            ({"warnAt": -1, "failAt": 6}, "warnAt"),
            ({"warnAt": "3", "failAt": 6}, "warnAt"),
            ({"warnAt": 3.0, "failAt": 6}, "warnAt"),
            ({"warnAt": True, "failAt": 6}, "warnAt"),
            ({"warnAt": 3, "failAt": 0}, "failAt"),
            ({"warnAt": 3, "failAt": -1}, "failAt"),
            ({"warnAt": 3, "failAt": "6"}, "failAt"),
            ({"warnAt": 3, "failAt": 6.0}, "failAt"),
            ({"warnAt": 3, "failAt": False}, "failAt"),
            ({"warnAt": 6, "failAt": 6}, "lower"),
            ({"warnAt": 7, "failAt": 6}, "lower"),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for thresholds, expected in cases:
                with self.subTest(thresholds=thresholds):
                    config = write_config(root, {
                        "overrides": [{"match": ["*.py"], **thresholds}],
                    })
                    result = self.run_guard(root, ".", "--config", str(config), "--json")
                    self.assertEqual(result.returncode, 3)
                    self.assertIn(expected, self.read_json(result)["error"])

    def test_malformed_override_remains_exit_3_under_ci(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = write_config(root, {"overrides": [{"match": ["*.py"], "warnAt": True, "failAt": 6}]})

            result = self.run_guard(root, ".", "--config", str(config), "--ci", "--json")

            self.assertEqual(result.returncode, 3)
            self.assertIn("overrides[0].warnAt", self.read_json(result)["error"])


if __name__ == "__main__":
    import unittest

    unittest.main()
