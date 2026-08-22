# Agent LOC Guard

Agent LOC Guard is a small, portable file-length guard for agent-assisted development.

It combines:

- a deterministic Python LOC checker;
- an agent skill (`SKILL.md`);
- a reusable policy reference;
- example Codex and Claude integration files;
- a GitHub Actions workflow example.

The goal is not to force tiny files. The goal is to stop agents from producing oversized, hard-to-review files without judgment.

## Packaging choice

Use this project as a cross-agent skill/tool.

The canonical pieces are:

- `skills/loc-guard/SKILL.md` for agent behavior;
- `skills/loc-guard/references/loc-policy.md` for reusable policy text;
- `skills/loc-guard/scripts/loc_guard.py` for deterministic checking;
- `examples/loc-guard.config.json` for project-local thresholds and excludes.

## Policy summary

- `400` counted LOC is a review trigger, not an automatic refactor command.
- `600` counted LOC is a hard cap unless the user explicitly approves an exception.
- A warning requires the agent to inspect cohesion, responsibility boundaries, and likely near-term growth.
- A split should happen only when it improves boundaries or reduces meaningful complexity.
- Large-file exemptions require a path and reason and are explicit policy decisions; agents may not create or alter them without explicit user approval.
- LOC must not be gamed through dense formatting or readability loss. Project style and sound design take precedence over optimizing the metric.

Required warning report:

```text
warning accepted with justification: ...
```

or:

```text
split performed because: ...
```

## Recommended repo layout

Copy the package into a project like this:

```text
.agent-tools/
  loc_guard.py
  loc-guard.config.json

.agent-skills/
  loc-guard/
    SKILL.md
    references/
      loc-policy.md

AGENTS.md
CLAUDE.md
```

For a simple installation, copy:

```text
skills/loc-guard/scripts/loc_guard.py
```

to:

```text
.agent-tools/loc_guard.py
```

and copy:

```text
examples/loc-guard.config.json
```

to:

```text
.agent-tools/loc-guard.config.json
```

Minimal project install from a checkout of this repository:

```bash
mkdir -p .agent-tools .agent-skills
cp skills/loc-guard/scripts/loc_guard.py .agent-tools/loc_guard.py
cp examples/loc-guard.config.json .agent-tools/loc-guard.config.json
cp -R skills/loc-guard .agent-skills/loc-guard
```

Copy the skill directory when the target agent supports project skills:

```bash
mkdir -p .agent-skills
cp -R skills/loc-guard .agent-skills/loc-guard
```

For agents that do not have a skill loader, copy the policy block from `examples/AGENTS.md` or `examples/CLAUDE.md` into the agent instruction file and keep the checker under `.agent-tools/`.

## Codex installation

After this repository is published, Codex users can install the skill directly from GitHub:

```text
Use $skill-installer to install https://github.com/stef-k/agent-loc-guard/tree/main/skills/loc-guard
```

For project-local use, also copy the checker and config:

```bash
mkdir -p .agent-tools
cp skills/loc-guard/scripts/loc_guard.py .agent-tools/loc_guard.py
cp examples/loc-guard.config.json .agent-tools/loc-guard.config.json
```

## Claude Code installation

Claude Code supports the same `SKILL.md` format, but uses Claude-specific install locations.

Personal install:

```bash
mkdir -p ~/.claude/skills
cp -R skills/loc-guard ~/.claude/skills/loc-guard
```

Project install:

```bash
mkdir -p .claude/skills
cp -R skills/loc-guard .claude/skills/loc-guard
```

Project hook install:

```bash
mkdir -p .claude .agent-tools
cp hooks/claude/settings.example.json .claude/settings.json
cp skills/loc-guard/scripts/loc_guard.py .agent-tools/loc_guard.py
cp examples/loc-guard.config.json .agent-tools/loc-guard.config.json
```

Claude discovers personal skills from `~/.claude/skills/<skill-name>/SKILL.md` and project skills from `.claude/skills/<skill-name>/SKILL.md`. The Codex-only `skills/loc-guard/agents/openai.yaml` file is harmless for Claude but is not used for Claude discovery.

## Discovery and installation

For users, describe this package with these search terms wherever it is published:

```text
agent loc guard, agent file length policy, AI coding guardrail, Codex skill, Claude skill, source file size checker
```

For installed agents, discovery comes from:

- the skill metadata in `skills/loc-guard/SKILL.md`;
- the UI metadata in `skills/loc-guard/agents/openai.yaml`;
- the instruction snippets in `examples/AGENTS.md` and `examples/CLAUDE.md`;
- hook examples under `hooks/` for automatic checks after edits.

Suggested installation modes:

- **Project-local**: copy `.agent-tools/`, `.agent-skills/`, and instruction snippets into each repository that wants enforcement.
- **Personal agent skill**: install `skills/loc-guard/` into the agent's personal skills directory and copy `loc_guard.py` into each checked project.
- **CI visibility**: copy `ci/github/loc-guard.yml` into `.github/workflows/loc-guard.yml` so users see policy failures in pull requests.

Verify an install against current work with:

```bash
python3 .agent-tools/loc_guard.py . --config .agent-tools/loc-guard.config.json --changed-only
```

Publishing checklist:

- Keep the repository name and package title as `agent-loc-guard`.
- Keep the first README paragraph focused on agent-assisted coding and file length policy.
- Add repository topics matching the search terms above.
- Include `skills/loc-guard/agents/openai.yaml` in published packages for Codex UI discovery.
- Keep `examples/AGENTS.md` and `examples/CLAUDE.md` short so users can paste them directly.
- Tag releases when the checker behavior or policy text changes.

## Usage

Run from the root of a repository. Normal agent work checks staged, unstaged, and untracked files relative to `HEAD`:

```bash
python3 .agent-tools/loc_guard.py . --config .agent-tools/loc-guard.config.json --changed-only
```

This protects current work without making unrelated pre-existing technical debt part of the task. A legacy file modified by the task is still checked in its current resulting form.

Check staged/index files only, such as in a pre-commit hook:

```bash
python3 .agent-tools/loc_guard.py . --config .agent-tools/loc-guard.config.json --staged
```

Check committed pull-request changes from the merge base with an explicit base ref:

```bash
python3 .agent-tools/loc_guard.py . --config .agent-tools/loc-guard.config.json --base-ref <base-ref> --ci
```

`--base-ref` uses Git's three-dot comparison (`<base-ref>...HEAD`), so base-only changes are excluded. `--changed-only`, `--staged`, and `--base-ref` are mutually exclusive.

Run an explicit full-repository audit by omitting all change-selection flags:

```bash
python3 .agent-tools/loc_guard.py . --config .agent-tools/loc-guard.config.json --ci
```

The audit example uses `--ci`: warnings remain visible, while only hard failures and tool errors make automation fail. Omit `--ci` locally when warnings should return a nonzero status.

Emit JSON:

```bash
python3 .agent-tools/loc_guard.py . --json
```

Override thresholds:

```bash
python3 .agent-tools/loc_guard.py . --warn 400 --fail 600
```

## Exit codes

Normal CLI:

```text
0 = OK
1 = one or more warning-threshold files found
2 = one or more hard-fail files found
3 = tool/configuration/runtime error
```

With `--ci`, exit `0` means OK or warning; exits `2` and `3` retain their meanings. Warning files remain `warn` in text and JSON reports. Hard failures take precedence over warnings in both modes.

## Counted LOC

By default, counted LOC means non-blank physical lines.

Comments are counted by default because large comment-heavy files can still become hard to review. You may set `countCommentLines` to `false` in the config for a lighter check.

Generated, vendored, designer, minified, migration, lock, snapshot, and machine-produced files should normally be excluded by configuration.

Each `allowedLargeFiles` entry must be an object with a non-empty string `path` and `reason`. Valid oversized exemptions remain visible as `exempt` with the configured reason. Malformed entries are configuration errors (exit `3`), including under `--ci` and in machine-readable `--json` mode.

Exemptions represent explicit user-approved policy, not an escape hatch for an agent responding to a warning or failure. Likewise, agents must not compress readable source onto fewer physical lines to evade a threshold; legitimate LOC reduction comes from clearer code or better responsibility boundaries.

## Agent skill

The skill lives at:

```text
skills/loc-guard/SKILL.md
```

For Claude Code, this can be installed as a project or personal skill.

For Codex, keep the policy in `AGENTS.md`, include the skill directory when your workflow uses skills, and keep `skills/loc-guard/agents/openai.yaml` with the skill for UI visibility.

## Hook examples

Codex example:

```text
hooks/codex/hooks.example.json
```

Claude example:

```text
hooks/claude/settings.example.json
```

These are examples because exact hook configuration can vary by local setup and agent version.

## GitHub Actions

The pull-request workflow example is provided at:

```text
ci/github/loc-guard.yml
```

Copy it to:

```text
.github/workflows/loc-guard.yml
```

It runs only for `pull_request`, checks out the PR head with full history, and compares it with `github.event.pull_request.base.sha`. This avoids relying on the checkout's immediate working-tree state and handles branches that are ahead of, behind, or diverged from the base.

A separate manual full-repository audit is provided at:

```text
ci/github/loc-guard-audit.yml
```

Neither reusable example assigns PR semantics to pushes. Projects that want push auditing can run the full scan explicitly. This repository's own CI does that on pushes to `main`/`master`, while pull requests use `--base-ref`.

This repository also includes active CI at:

```text
.github/workflows/ci.yml
```

It compiles the checker, runs the test suite, validates JSON examples, checks PR changes on pull requests, and performs an explicit full audit on pushes.

## Tests

Run the publication test suite with:

```bash
python3 -m unittest discover -s tests
```

## Suggested agent instruction

Add this to `AGENTS.md` and/or `CLAUDE.md`:

```markdown
## LOC Guard

Use the LOC Guard skill when creating or modifying source files.

Run:

```bash
python3 .agent-tools/loc_guard.py . --config .agent-tools/loc-guard.config.json --changed-only
```

This checks current work so unrelated unchanged legacy files do not become part of the task. Run without `--changed-only` only for an explicit full-repository audit.

400 counted LOC is a review trigger, not an automatic refactor command.

600 counted LOC is a hard cap unless the user explicitly approves an exception.

When a changed or new file warns, inspect cohesion, single responsibility, near-term growth, and whether splitting improves boundaries.

Report either:

- `warning accepted with justification: ...`
- `split performed because: ...`
```

## License

MIT.
