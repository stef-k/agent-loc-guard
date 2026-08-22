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


def commit_all(root: Path, message: str) -> str:
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", message], cwd=root, check=True, capture_output=True, text=True)
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


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

    def test_ci_warning_returns_exit_0_and_preserves_json_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_lines(root / "warn.py", 4)

            result = self.run_guard(root, ".", "--warn", "3", "--fail", "6", "--ci", "--json")

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = self.read_json(result)
            self.assertEqual(payload["summary"]["warn"], 1)
            self.assertEqual(payload["files"][0]["status"], "warn")

    def test_ci_warning_remains_visible_in_text_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_lines(root / "warn.py", 4)

            result = self.run_guard(root, ".", "--warn", "3", "--fail", "6", "--ci")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("WARN:", result.stdout)
            self.assertIn("warn.py", result.stdout)

    def test_ci_hard_failure_returns_exit_2_and_takes_precedence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_lines(root / "warn.py", 4)
            write_lines(root / "fail.py", 7)

            result = self.run_guard(root, ".", "--warn", "3", "--fail", "6", "--ci", "--json")

            self.assertEqual(result.returncode, 2, result.stderr)
            payload = self.read_json(result)
            self.assertEqual(payload["summary"]["warn"], 1)
            self.assertEqual(payload["summary"]["fail"], 1)

    def test_ci_configuration_failure_returns_exit_3(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            result = self.run_guard(root, ".", "--config", "missing.json", "--ci", "--json")

            self.assertEqual(result.returncode, 3)
            self.assertIn("config file not found", self.read_json(result)["error"])

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
            self.assertIn("file-selection mode", payload["error"])

    def test_base_ref_includes_added_and_modified_committed_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            init_git_repo(root, {"modified.py": 1, "unchanged.py": 1})
            base = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
            ).stdout.strip()
            write_lines(root / "modified.py", 2)
            write_lines(root / "added.py", 1)
            commit_all(root, "feature changes")

            result = self.run_guard(root, ".", "--base-ref", base, "--json")

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = self.read_json(result)
            self.assertEqual([file["path"] for file in payload["files"]], ["added.py", "modified.py"])

    def test_base_ref_ignores_deleted_and_unmodified_legacy_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            init_git_repo(root, {"deleted.py": 7, "legacy.py": 7, "small.py": 1})
            base = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
            ).stdout.strip()
            (root / "deleted.py").unlink()
            write_lines(root / "small.py", 2)
            commit_all(root, "delete and modify")

            result = self.run_guard(
                root, ".", "--base-ref", base, "--warn", "3", "--fail", "6", "--ci", "--json"
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = self.read_json(result)
            self.assertEqual([file["path"] for file in payload["files"]], ["small.py"])

    def test_base_ref_ci_detects_changed_oversized_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            init_git_repo(root)
            base = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
            ).stdout.strip()
            write_lines(root / "large.py", 7)
            commit_all(root, "add oversized file")

            result = self.run_guard(
                root, ".", "--base-ref", base, "--warn", "3", "--fail", "6", "--ci", "--json"
            )

            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual(self.read_json(result)["files"][0]["status"], "fail")

    def test_base_ref_uses_merge_base_and_ignores_later_base_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            init_git_repo(root, {"shared.py": 1})
            initial_branch = subprocess.run(
                ["git", "branch", "--show-current"], cwd=root, check=True, capture_output=True, text=True
            ).stdout.strip()
            subprocess.run(["git", "switch", "-c", "feature"], cwd=root, check=True, capture_output=True)
            write_lines(root / "feature.py", 1)
            commit_all(root, "feature commit")
            subprocess.run(["git", "switch", initial_branch], cwd=root, check=True, capture_output=True)
            write_lines(root / "base-only.py", 7)
            commit_all(root, "later base commit")
            subprocess.run(["git", "switch", "feature"], cwd=root, check=True, capture_output=True)

            result = self.run_guard(
                root, ".", "--base-ref", initial_branch, "--warn", "3", "--fail", "6", "--ci", "--json"
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = self.read_json(result)
            self.assertEqual([file["path"] for file in payload["files"]], ["feature.py"])

    def test_invalid_base_ref_returns_tool_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            init_git_repo(root, {"legacy.py": 7})

            result = self.run_guard(root, ".", "--base-ref", "missing-ref", "--ci", "--json")

            self.assertEqual(result.returncode, 3)
            self.assertIn("missing-ref", self.read_json(result)["error"])

    def test_base_ref_conflicts_with_worktree_selection_modes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            init_git_repo(root)

            for mode in ("--changed-only", "--staged"):
                with self.subTest(mode=mode):
                    result = self.run_guard(root, ".", mode, "--base-ref", "HEAD", "--json")
                    self.assertEqual(result.returncode, 3)
                    self.assertIn("file-selection mode", self.read_json(result)["error"])


if __name__ == "__main__":
    unittest.main()
