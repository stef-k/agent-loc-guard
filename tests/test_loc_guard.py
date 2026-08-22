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


def init_git_repo(root: Path, tracked_files: dict[str, int] | None = None) -> None:
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "LOC Guard Tests"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "loc-guard@example.invalid"], cwd=root, check=True)

    for path, count in (tracked_files or {}).items():
        write_lines(root / path, count)

    subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "test fixture"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )


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

    def test_root_and_nested_directory_exclusions_are_consistent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            excluded_directories = ["generated", "vendor", "build", "coverage", "Migrations"]
            for directory in excluded_directories:
                write_lines(root / directory / "root.py", 1)
                write_lines(root / "src" / directory / "nested.py", 1)
            write_lines(root / "src" / "included.py", 1)

            result = self.run_guard(root, ".", "--json")

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = self.read_json(result)
            self.assertEqual([file["path"] for file in payload["files"]], ["src/included.py"])

    def test_filename_specific_exclusions_work_at_root_and_nested_depth(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_lines(root / "root.generated.cs", 1)
            write_lines(root / "src" / "nested.generated.cs", 1)
            write_lines(root / "src" / "included.cs", 1)

            result = self.run_guard(root, ".", "--json")

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = self.read_json(result)
            self.assertEqual([file["path"] for file in payload["files"]], ["src/included.cs"])

    def test_project_directory_exclusion_matches_root_and_nested_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_lines(root / "custom" / "root.py", 1)
            write_lines(root / "src" / "custom" / "nested.py", 1)
            write_lines(root / "kept.py", 1)
            config = root / "loc-guard.config.json"
            config.write_text(json.dumps({"exclude": ["**/custom/**"]}), encoding="utf-8")

            result = self.run_guard(root, ".", "--config", str(config), "--json")

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = self.read_json(result)
            self.assertEqual([file["path"] for file in payload["files"]], ["kept.py"])

    def test_exclusion_normalises_leading_dot_and_backslashes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_lines(root / "custom" / "root.py", 1)
            write_lines(root / "src" / "custom" / "nested.py", 1)
            write_lines(root / "kept.py", 1)
            config = root / "loc-guard.config.json"
            config.write_text(json.dumps({"exclude": [".\\**\\custom\\**"]}), encoding="utf-8")

            result = self.run_guard(root, ".", "--config", str(config), "--json")

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = self.read_json(result)
            self.assertEqual([file["path"] for file in payload["files"]], ["kept.py"])

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
            init_git_repo(root)
            write_lines(root / "changed.py", 4)

            result = self.run_guard(root, ".", "--changed-only", "--warn", "3", "--fail", "6", "--json")

            self.assertEqual(result.returncode, 1, result.stderr)
            payload = self.read_json(result)
            self.assertEqual(payload["summary"]["checked"], 1)
            self.assertEqual(payload["files"][0]["path"], "changed.py")

    def test_staged_includes_staged_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            init_git_repo(root)
            write_lines(root / "staged.py", 4)
            subprocess.run(["git", "add", "staged.py"], cwd=root, check=True, capture_output=True, text=True)

            result = self.run_guard(root, ".", "--staged", "--warn", "3", "--fail", "6", "--json")

            self.assertEqual(result.returncode, 1, result.stderr)
            payload = self.read_json(result)
            self.assertEqual(payload["summary"]["checked"], 1)
            self.assertEqual(payload["files"][0]["path"], "staged.py")

    def test_changed_only_includes_staged_unstaged_and_untracked_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            init_git_repo(root, {"staged.py": 1, "unstaged.py": 1, "mixed.py": 1})

            write_lines(root / "staged.py", 2)
            subprocess.run(["git", "add", "staged.py"], cwd=root, check=True)
            write_lines(root / "unstaged.py", 2)
            write_lines(root / "mixed.py", 2)
            subprocess.run(["git", "add", "mixed.py"], cwd=root, check=True)
            write_lines(root / "mixed.py", 3)
            write_lines(root / "untracked.py", 1)

            result = self.run_guard(root, ".", "--changed-only", "--json")

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = self.read_json(result)
            self.assertEqual(
                [file["path"] for file in payload["files"]],
                ["mixed.py", "staged.py", "unstaged.py", "untracked.py"],
            )

    def test_changed_only_includes_newly_added_staged_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            init_git_repo(root)
            write_lines(root / "new.py", 1)
            subprocess.run(["git", "add", "new.py"], cwd=root, check=True)

            result = self.run_guard(root, ".", "--changed-only", "--json")

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = self.read_json(result)
            self.assertEqual([file["path"] for file in payload["files"]], ["new.py"])

    def test_changed_only_omits_staged_and_unstaged_changes_that_cancel(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            init_git_repo(root, {"unchanged.py": 1})
            write_lines(root / "unchanged.py", 2)
            subprocess.run(["git", "add", "unchanged.py"], cwd=root, check=True)
            write_lines(root / "unchanged.py", 1)

            result = self.run_guard(root, ".", "--changed-only", "--json")

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = self.read_json(result)
            self.assertEqual(payload["summary"]["checked"], 0)

    def test_changed_only_supports_staged_and_untracked_files_without_head(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True, text=True)
            write_lines(root / "staged.py", 1)
            subprocess.run(["git", "add", "staged.py"], cwd=root, check=True)
            write_lines(root / "untracked.py", 1)

            result = self.run_guard(root, ".", "--changed-only", "--json")

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = self.read_json(result)
            self.assertEqual([file["path"] for file in payload["files"]], ["staged.py", "untracked.py"])

    def test_changed_only_does_not_evaluate_deleted_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            init_git_repo(root, {"deleted.py": 1})
            (root / "deleted.py").unlink()

            result = self.run_guard(root, ".", "--changed-only", "--json")

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = self.read_json(result)
            self.assertEqual(payload["summary"]["checked"], 0)

    def test_staged_excludes_purely_unstaged_and_untracked_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            init_git_repo(root, {"staged.py": 1, "unstaged.py": 1})
            write_lines(root / "staged.py", 2)
            subprocess.run(["git", "add", "staged.py"], cwd=root, check=True)
            write_lines(root / "unstaged.py", 2)
            write_lines(root / "untracked.py", 1)

            result = self.run_guard(root, ".", "--staged", "--json")

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = self.read_json(result)
            self.assertEqual([file["path"] for file in payload["files"]], ["staged.py"])

    def test_changed_only_and_staged_are_mutually_exclusive(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            init_git_repo(root)

            result = self.run_guard(root, ".", "--changed-only", "--staged", "--json")

            self.assertEqual(result.returncode, 3)
            payload = self.read_json(result)
            self.assertEqual(payload["error"], "use either --changed-only or --staged, not both")


if __name__ == "__main__":
    unittest.main()
