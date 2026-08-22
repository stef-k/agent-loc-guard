#!/usr/bin/env python3
"""
LOC Guard.

Portable file-length checker for agent-assisted development.

Default policy:
- warn above 400 counted LOC;
- fail above 600 counted LOC.

Counted LOC defaults to non-blank physical lines. Comments are counted by default.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_WARN_AT = 400
DEFAULT_FAIL_AT = 600
DEFAULT_INCLUDE_EXTENSIONS = {
    ".cs", ".cshtml", ".razor",
    ".js", ".jsx", ".ts", ".tsx",
    ".py", ".java", ".kt", ".kts", ".scala",
    ".go", ".rs", ".swift", ".dart", ".zig",
    ".cpp", ".c", ".h", ".hpp",
    ".m", ".mm", ".fs", ".fsx", ".vb",
    ".css", ".scss", ".html", ".vue",
    ".php", ".rb", ".ex", ".exs",
    ".erl", ".hrl", ".clj", ".cljs", ".cljc", ".lua",
    ".sql", ".sh", ".ps1",
}
DEFAULT_EXCLUDES = [
    "**/.git/**",
    "**/.vs/**",
    "**/.idea/**",
    "**/.vscode/**",
    "**/bin/**",
    "**/obj/**",
    "**/node_modules/**",
    "**/dist/**",
    "**/build/**",
    "**/coverage/**",
    "**/generated/**",
    "**/Generated/**",
    "**/vendor/**",
    "**/Vendor/**",
    "**/Migrations/**",
    "**/*.g.cs",
    "**/*.generated.cs",
    "**/*.Designer.cs",
    "**/*.designer.cs",
    "**/*.min.js",
    "**/*.min.css",
]


SINGLE_LINE_COMMENT_PREFIXES = {
    ".cs": ["//"],
    ".cshtml": ["@*"],
    ".razor": ["@*", "//"],
    ".js": ["//"],
    ".jsx": ["//"],
    ".ts": ["//"],
    ".tsx": ["//"],
    ".py": ["#"],
    ".java": ["//"],
    ".kt": ["//"],
    ".kts": ["//"],
    ".scala": ["//"],
    ".go": ["//"],
    ".rs": ["//"],
    ".swift": ["//"],
    ".dart": ["//"],
    ".zig": ["//"],
    ".cpp": ["//"],
    ".c": ["//"],
    ".h": ["//"],
    ".hpp": ["//"],
    ".m": ["//"],
    ".mm": ["//"],
    ".fs": ["//"],
    ".fsx": ["//"],
    ".vb": ["'"],
    ".css": ["/*"],
    ".scss": ["//", "/*"],
    ".html": ["<!--"],
    ".vue": ["<!--"],
    ".php": ["//", "#"],
    ".rb": ["#"],
    ".ex": ["#"],
    ".exs": ["#"],
    ".erl": ["%"],
    ".hrl": ["%"],
    ".clj": [";"],
    ".cljs": [";"],
    ".cljc": [";"],
    ".lua": ["--"],
    ".sql": ["--"],
    ".sh": ["#"],
    ".ps1": ["#"],
}


@dataclass(frozen=True)
class AllowedLargeFile:
    path: str
    reason: str


@dataclass(frozen=True)
class ThresholdOverride:
    match: list[str]
    warn_at: int
    fail_at: int


@dataclass(frozen=True)
class Config:
    warn_at: int
    fail_at: int
    count_blank_lines: bool
    count_comment_lines: bool
    include_extensions: set[str]
    exclude: list[str]
    allowed_large_files: list[AllowedLargeFile]
    overrides: list[ThresholdOverride]


@dataclass(frozen=True)
class FileResult:
    path: str
    counted_loc: int
    status: str
    reason: str | None = None
    warn_at: int = DEFAULT_WARN_AT
    fail_at: int = DEFAULT_FAIL_AT
    override_index: int | None = None


def main() -> int:
    parser = argparse.ArgumentParser(description="Check source files against LOC policy.")
    parser.add_argument("paths", nargs="*", default=["."], help="Files or directories to inspect.")
    parser.add_argument("--config", help="Path to loc-guard.config.json.")
    parser.add_argument("--warn", type=int, help="Override warning threshold.")
    parser.add_argument("--fail", type=int, help="Override failure threshold.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    parser.add_argument("--ci", action="store_true", help="Do not fail solely on soft warnings.")
    parser.add_argument("--changed-only", action="store_true", help="Only inspect git changed files.")
    parser.add_argument("--staged", action="store_true", help="Only inspect git staged files.")
    parser.add_argument("--base-ref", help="Only inspect committed changes from this Git ref to HEAD.")
    parser.add_argument("--include", action="append", default=[], help="Extra extension to include, such as .md.")
    parser.add_argument("--exclude", action="append", default=[], help="Extra glob pattern to exclude.")
    parser.add_argument("--count-blank-lines", action="store_true", help="Count blank lines.")
    parser.add_argument("--ignore-comment-lines", action="store_true", help="Do not count simple comment-only lines.")

    args = parser.parse_args()

    try:
        config = load_config(args)
        root = find_repo_root(Path.cwd())
        files = collect_files(args, config, root)
        results = evaluate_files(files, config, root)
        if args.json:
            print_json(results, config)
        else:
            print_text(results, config)
        return exit_code(results, ci=args.ci)
    except Exception as exc:
        if args.json:
            print(json.dumps({"error": str(exc)}, indent=2))
        else:
            print(f"LOC Guard error: {exc}", file=sys.stderr)
        return 3


def load_config(args: argparse.Namespace) -> Config:
    data: dict[str, Any] = {}

    config_path = args.config
    if config_path:
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"config file not found: {config_path}")
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        auto = Path(".agent-tools/loc-guard.config.json")
        if auto.exists():
            data = json.loads(auto.read_text(encoding="utf-8"))

    warn_at = int(args.warn or data.get("warnAt", DEFAULT_WARN_AT))
    fail_at = int(args.fail or data.get("failAt", DEFAULT_FAIL_AT))
    if warn_at >= fail_at:
        raise ValueError("warn threshold must be lower than fail threshold")

    include_extensions = set(data.get("includeExtensions", list(DEFAULT_INCLUDE_EXTENSIONS)))
    include_extensions.update(args.include)
    include_extensions = {normalise_extension(ext) for ext in include_extensions}

    exclude = list(data.get("exclude", DEFAULT_EXCLUDES))
    exclude.extend(args.exclude)

    allowed = parse_allowed_large_files(data.get("allowedLargeFiles", []))
    overrides = parse_overrides(data.get("overrides", []))

    count_blank_lines = bool(data.get("countBlankLines", False)) or bool(args.count_blank_lines)
    count_comment_lines = bool(data.get("countCommentLines", True))
    if args.ignore_comment_lines:
        count_comment_lines = False

    return Config(
        warn_at=warn_at,
        fail_at=fail_at,
        count_blank_lines=count_blank_lines,
        count_comment_lines=count_comment_lines,
        include_extensions=include_extensions,
        exclude=exclude,
        allowed_large_files=allowed,
        overrides=overrides,
    )


def parse_allowed_large_files(value: Any) -> list[AllowedLargeFile]:
    if not isinstance(value, list):
        raise ValueError("allowedLargeFiles must be an array")

    allowed: list[AllowedLargeFile] = []
    for index, item in enumerate(value):
        location = f"allowedLargeFiles[{index}]"
        if not isinstance(item, dict):
            raise ValueError(f"{location} must be an object")

        path = item.get("path")
        if not isinstance(path, str) or not path.strip():
            raise ValueError(f"{location}.path must be a non-empty string")

        reason = item.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError(f"{location}.reason must be a non-empty string")

        allowed.append(AllowedLargeFile(path=path.replace("\\", "/"), reason=reason))

    return allowed


def parse_overrides(value: Any) -> list[ThresholdOverride]:
    if not isinstance(value, list):
        raise ValueError("overrides must be an array")

    overrides: list[ThresholdOverride] = []
    for index, item in enumerate(value):
        location = f"overrides[{index}]"
        if not isinstance(item, dict):
            raise ValueError(f"{location} must be an object")

        patterns = item.get("match")
        if (
            not isinstance(patterns, list)
            or not patterns
            or any(not isinstance(pattern, str) or not pattern.strip() for pattern in patterns)
        ):
            raise ValueError(f"{location}.match must be a non-empty array of non-empty strings")

        warn_at = parse_positive_integer(item.get("warnAt"), f"{location}.warnAt")
        fail_at = parse_positive_integer(item.get("failAt"), f"{location}.failAt")
        if warn_at >= fail_at:
            raise ValueError(f"{location}.warnAt must be lower than {location}.failAt")

        overrides.append(ThresholdOverride(
            match=[pattern.replace("\\", "/") for pattern in patterns],
            warn_at=warn_at,
            fail_at=fail_at,
        ))

    return overrides


def parse_positive_integer(value: Any, location: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{location} must be a positive integer")
    return value


def normalise_extension(value: str) -> str:
    value = value.strip()
    if not value:
        return value
    return value if value.startswith(".") else f".{value}"


def find_repo_root(start: Path) -> Path:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=start,
            check=True,
            text=True,
            capture_output=True,
        )
        return Path(result.stdout.strip()).resolve()
    except Exception:
        return start.resolve()


def collect_files(args: argparse.Namespace, config: Config, root: Path) -> list[Path]:
    has_base_ref = args.base_ref is not None
    selection_modes = sum((args.changed_only, args.staged, has_base_ref))
    if selection_modes > 1:
        raise ValueError("use only one file-selection mode: --changed-only, --staged, or --base-ref")
    if has_base_ref and not args.base_ref.strip():
        raise ValueError("--base-ref must not be empty")

    if has_base_ref:
        files = git_base_files(root, args.base_ref)
    elif args.changed_only or args.staged:
        files = git_files(root, staged=args.staged)
    else:
        files = expand_paths([Path(p) for p in args.paths])

    filtered: list[Path] = []
    for file_path in files:
        resolved = file_path if file_path.is_absolute() else (Path.cwd() / file_path)
        resolved = resolved.resolve()
        if not resolved.exists() or not resolved.is_file():
            continue
        if should_include(resolved, config, root):
            filtered.append(resolved)

    return sorted(set(filtered), key=lambda p: relative_path(p, root))


def git_files(root: Path, staged: bool) -> list[Path]:
    has_head = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", "HEAD"],
        cwd=root,
        check=False,
        capture_output=True,
    ).returncode == 0
    diff_target = ["--cached"] if staged or not has_head else ["HEAD"]
    command = ["git", "diff", *diff_target, "--name-only", "--diff-filter=ACMR", "-z"]
    result = subprocess.run(command, cwd=root, check=True, capture_output=True)
    files = [root / os.fsdecode(path) for path in result.stdout.split(b"\0") if path]

    if not staged:
        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard", "-z"],
            cwd=root,
            check=True,
            capture_output=True,
        )
        files.extend(root / os.fsdecode(path) for path in untracked.stdout.split(b"\0") if path)

    return files


def git_base_files(root: Path, base_ref: str) -> list[Path]:
    command = [
        "git",
        "diff",
        "--name-only",
        "--diff-filter=ACMR",
        "-z",
        f"{base_ref}...HEAD",
        "--",
    ]
    try:
        result = subprocess.run(command, cwd=root, check=True, capture_output=True)
    except subprocess.CalledProcessError as exc:
        detail = os.fsdecode(exc.stderr).strip()
        message = f"unable to compare base ref {base_ref!r} with HEAD"
        raise RuntimeError(f"{message}: {detail}" if detail else message) from exc

    return [root / os.fsdecode(path) for path in result.stdout.split(b"\0") if path]


def expand_paths(paths: list[Path]) -> list[Path]:
    files: list[Path] = []

    for path in paths:
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            for current_root, dir_names, file_names in os.walk(path):
                dir_names[:] = [name for name in dir_names if name not in {".git", "node_modules", "bin", "obj"}]
                for file_name in file_names:
                    files.append(Path(current_root) / file_name)

    return files


def should_include(path: Path, config: Config, root: Path) -> bool:
    if path.suffix not in config.include_extensions:
        return False

    rel = relative_path(path, root)
    for pattern in config.exclude:
        if matches_path_glob(rel, pattern):
            return False

    return True


def matches_path_glob(path: str, pattern: str) -> bool:
    normalised_path = path.replace("\\", "/").removeprefix("./")
    normalised_pattern = pattern.replace("\\", "/").removeprefix("./")
    if normalised_path == normalised_pattern:
        return True
    candidates = [normalised_pattern]

    while normalised_pattern.startswith("**/"):
        normalised_pattern = normalised_pattern[3:]
        candidates.append(normalised_pattern)

    return any(fnmatch.fnmatch(normalised_path, candidate) for candidate in candidates)


def evaluate_files(files: list[Path], config: Config, root: Path) -> list[FileResult]:
    results: list[FileResult] = []

    for path in files:
        rel = relative_path(path, root)
        counted = count_loc(path, config)
        allowed = find_allowed_large_file(rel, config)
        warn_at, fail_at, override_index = effective_thresholds(rel, config)

        if allowed and counted > warn_at:
            status = "exempt"
            reason = allowed.reason
        elif counted > fail_at:
            status = "fail"
            reason = None
        elif counted > warn_at:
            status = "warn"
            reason = None
        else:
            status = "ok"
            reason = None

        results.append(FileResult(rel, counted, status, reason, warn_at, fail_at, override_index))

    return results


def count_loc(path: Path, config: Config) -> int:
    count = 0
    prefixes = SINGLE_LINE_COMMENT_PREFIXES.get(path.suffix, [])

    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for raw_line in handle:
            line = raw_line.rstrip("\n\r")
            stripped = line.strip()

            if not config.count_blank_lines and not stripped:
                continue

            if not config.count_comment_lines and is_simple_comment_line(stripped, prefixes, path.suffix):
                continue

            count += 1

    return count


def is_simple_comment_line(stripped: str, prefixes: list[str], extension: str) -> bool:
    if not stripped:
        return False
    if extension == ".php" and stripped.startswith("#["):
        return False
    return any(stripped.startswith(prefix) for prefix in prefixes)


def find_allowed_large_file(rel: str, config: Config) -> AllowedLargeFile | None:
    for item in config.allowed_large_files:
        if matches_path_glob(rel, item.path):
            return item
    return None


def effective_thresholds(rel: str, config: Config) -> tuple[int, int, int | None]:
    selected: tuple[int, ThresholdOverride] | None = None
    for index, override in enumerate(config.overrides):
        if any(matches_path_glob(rel, pattern) for pattern in override.match):
            selected = (index, override)

    if selected is None:
        return config.warn_at, config.fail_at, None

    index, override = selected
    return override.warn_at, override.fail_at, index


def print_json(results: list[FileResult], config: Config) -> None:
    payload = {
        "warnAt": config.warn_at,
        "failAt": config.fail_at,
        "summary": summary(results),
        "files": [
            {
                "path": result.path,
                "countedLoc": result.counted_loc,
                "status": result.status,
                "reason": result.reason,
                "warnAt": result.warn_at,
                "failAt": result.fail_at,
                "overrideIndex": result.override_index,
            }
            for result in results
        ],
    }
    print(json.dumps(payload, indent=2))


def print_text(results: list[FileResult], config: Config) -> None:
    data = summary(results)

    print("LOC Guard Report")
    print()
    print(f"Checked files: {data['checked']}")
    print(f"Soft warning threshold: {config.warn_at}")
    print(f"Hard failure threshold: {config.fail_at}")
    print()

    for status in ["fail", "warn", "exempt"]:
        matching = [result for result in results if result.status == status]
        if not matching:
            continue

        print(status.upper() + ":")
        for result in matching:
            print(f"- {result.path}")
            print(f"  Counted LOC: {result.counted_loc}")
            if result.reason:
                print(f"  Reason: {result.reason}")
            if result.override_index is not None:
                print(
                    f"  Effective thresholds: warn {result.warn_at}, fail {result.fail_at} "
                    f"(override {result.override_index})"
                )

            if status == "warn":
                print("  Required agent action:")
                print("  - inspect cohesion and responsibility boundaries")
                print("  - report either:")
                print("    warning accepted with justification: ...")
                print("    split performed because: ...")
            elif status == "fail":
                print("  Required agent action:")
                print("  - split/refactor below the hard cap, or")
                print("  - request explicit user approval for an exception")
        print()

    if data["fail"] == 0 and data["warn"] == 0:
        print("OK: no LOC warnings or failures.")


def summary(results: list[FileResult]) -> dict[str, int]:
    return {
        "checked": len(results),
        "ok": sum(1 for result in results if result.status == "ok"),
        "warn": sum(1 for result in results if result.status == "warn"),
        "fail": sum(1 for result in results if result.status == "fail"),
        "exempt": sum(1 for result in results if result.status == "exempt"),
    }


def exit_code(results: list[FileResult], ci: bool = False) -> int:
    if any(result.status == "fail" for result in results):
        return 2
    if not ci and any(result.status == "warn" for result in results):
        return 1
    return 0


def relative_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


if __name__ == "__main__":
    sys.exit(main())
