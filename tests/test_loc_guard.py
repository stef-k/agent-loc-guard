from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
LOC_GUARD = REPO_ROOT / "skills" / "loc-guard" / "scripts" / "loc_guard.py"


def write_lines(path: Path, count: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"line_{index} = {index}\n" for index in range(count)), encoding="utf-8")


class LocGuardTests(unittest.TestCase):
    def run_guard(self, cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(LOC_GUARD), *args],
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
        )

    def read_json(self, result: subprocess.CompletedProcess[str]) -> dict:
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            self.fail(f"stdout was not valid JSON: {exc}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}")

    def test_warn_threshold_returns_exit_1(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_lines(root / "warn.py", 4)

            result = self.run_guard(root, ".", "--warn", "3", "--fail", "6", "--json")

            self.assertEqual(result.returncode, 1, result.stderr)
            payload = self.read_json(result)
            self.assertEqual(payload["summary"]["warn"], 1)
            self.assertEqual(payload["files"][0]["status"], "warn")

    def test_fail_threshold_returns_exit_2(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_lines(root / "fail.py", 7)

            result = self.run_guard(root, ".", "--warn", "3", "--fail", "6", "--json")

            self.assertEqual(result.returncode, 2, result.stderr)
            payload = self.read_json(result)
            self.assertEqual(payload["summary"]["fail"], 1)
            self.assertEqual(payload["files"][0]["status"], "fail")

    def test_excluded_file_is_not_checked(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_lines(root / "generated" / "large.py", 10)
            write_lines(root / "kept.py", 1)

            result = self.run_guard(root, ".", "--warn", "3", "--fail", "6", "--json")

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = self.read_json(result)
            self.assertEqual(payload["summary"]["checked"], 1)
            self.assertEqual(payload["files"][0]["path"], "kept.py")

    def test_allowed_large_file_is_exempt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_lines(root / "large.py", 7)
            config = root / "loc-guard.config.json"
            config.write_text(
                json.dumps(
                    {
                        "warnAt": 3,
                        "failAt": 6,
                        "allowedLargeFiles": [
                            {
                                "path": "large.py",
                                "reason": "Intentional linear fixture.",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = self.run_guard(root, ".", "--config", str(config), "--json")

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = self.read_json(result)
            self.assertEqual(payload["summary"]["exempt"], 1)
            self.assertEqual(payload["files"][0]["status"], "exempt")
            self.assertEqual(payload["files"][0]["reason"], "Intentional linear fixture.")

    def test_changed_only_includes_untracked_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True, text=True)
            write_lines(root / "changed.py", 4)

            result = self.run_guard(root, ".", "--changed-only", "--warn", "3", "--fail", "6", "--json")

            self.assertEqual(result.returncode, 1, result.stderr)
            payload = self.read_json(result)
            self.assertEqual(payload["summary"]["checked"], 1)
            self.assertEqual(payload["files"][0]["path"], "changed.py")

    def test_staged_includes_staged_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True, text=True)
            write_lines(root / "staged.py", 4)
            subprocess.run(["git", "add", "staged.py"], cwd=root, check=True, capture_output=True, text=True)

            result = self.run_guard(root, ".", "--staged", "--warn", "3", "--fail", "6", "--json")

            self.assertEqual(result.returncode, 1, result.stderr)
            payload = self.read_json(result)
            self.assertEqual(payload["summary"]["checked"], 1)
            self.assertEqual(payload["files"][0]["path"], "staged.py")


if __name__ == "__main__":
    unittest.main()
