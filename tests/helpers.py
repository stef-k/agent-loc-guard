from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
LOC_GUARD = REPO_ROOT / "skills" / "loc-guard" / "scripts" / "loc_guard.py"


def write_lines(path: Path, count: int, prefix: str = "line") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{prefix}_{index}\n" for index in range(count)), encoding="utf-8")


class LocGuardTestCase(unittest.TestCase):
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
            self.fail(f"invalid JSON output: {exc}\nstdout={result.stdout}\nstderr={result.stderr}")


def write_config(root: Path, value: object) -> Path:
    path = root / "loc-guard.config.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path
