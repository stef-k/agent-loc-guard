---
name: loc-guard
description: Use when creating, editing, reviewing, or refactoring source files to enforce a deterministic file-length policy across agent-assisted coding workflows. Run the bundled LOC checker, warn at 400 counted LOC, and hard fail at 600 counted LOC unless explicitly exempted.
license: Complete terms in LICENSE.txt
---

# LOC Guard

Use this skill whenever source files are created, edited, reviewed, or refactored.

The purpose of this skill is not to force tiny files. The purpose is to prevent oversized, hard-to-review, multi-responsibility files.

## Thresholds

- 400 counted LOC is a review trigger, not an automatic refactor command.
- More than 600 counted LOC is a prohibited default state for normal handwritten source unless an explicit approved exemption applies.

## Interpretation

When a changed or new file triggers the 400 LOC warning:

1. Inspect whether the file is still cohesive.
2. Check whether it has a clear single responsibility.
3. Decide whether the extra size is justified by necessary orchestration or simple linear structure.
4. Check whether the file is mixing separable responsibilities.
5. Consider likely near-term growth from upcoming slices before accepting the warning.
6. Split only when the split improves responsibility boundaries or reduces meaningful complexity.
7. Do not split purely to satisfy the number if the split adds indirection without design benefit.

## Required behavior after editing

Run the LOC checker after source edits.

Preferred project-local command:

```bash
python3 .agent-tools/loc_guard.py . --config .agent-tools/loc-guard.config.json --changed-only
```

If the project has not copied the checker into `.agent-tools/`, run the bundled checker from this skill instead:

```bash
python3 skills/loc-guard/scripts/loc_guard.py . --changed-only
```

In Claude Code, when the skill is installed under `~/.claude/skills/` or `.claude/skills/`, use Claude's skill-directory variable for the bundled checker:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/loc_guard.py" . --changed-only
```

Changed-file checking protects current work without making unrelated pre-existing technical debt part of the task. A legacy file that the task modifies is current work and is still evaluated. Run without a change-selection flag only for an explicit full-repository audit.

If no warning or failure occurs, no special report is needed.

If a file exceeds 400 counted LOC but stays at or below 600 counted LOC, report one of:

```text
warning accepted with justification: ...
```

or:

```text
split performed because: ...
```

If a file exceeds 600 counted LOC without an approved exemption, do not continue as if the task is complete. Either:

1. split/refactor the file below the hard cap, or
2. ask the user for explicit approval for an exception.

## Good warning justifications

Accepting a 400 LOC warning may be reasonable when:

- the file is cohesive and has one clear responsibility;
- most of the size is straightforward orchestration;
- splitting would create artificial indirection;
- the file is unlikely to grow much in the next slices;
- the file is a focused test suite with grouped cases;
- the change reduced complexity even if the file remains large.

## Bad warning justifications

Do not accept a warning merely because:

- it was faster;
- refactoring was not requested;
- the file already existed;
- the agent wanted to avoid touching more files;
- the new code is "only temporary";
- the split would be slightly inconvenient.

## Hard cap rule

A file over 600 counted LOC is a prohibited default state for normal handwritten source files unless an explicit approved exemption applies. This limit is a guardrail; it does not prove that every exceptional file has bad architecture.

Existing approved `allowedLargeFiles` entries may be honored and reported with their configured reasons. Do not add, broaden, modify, or repurpose an exemption, or invent its reason, to bypass a warning or hard failure without explicit user approval.

Do not infer approval from a hard failure, inconvenient refactoring, a nearby or broad exemption, historical file size, time pressure, or a request to complete the coding task. An unapproved file over the hard cap must be resolved or explicitly approved by the user.

Generated, vendored, minified, designer, lock, snapshot, migration, and machine-produced files may be excluded by configuration.

## Do not game counted LOC

LOC thresholds must never be satisfied by reducing readability or departing from the project's normal source style merely to lower counted physical lines. Follow the project's established formatter and formatting conventions, such as `dotnet format`, `ktfmt`, `gofmt`, `black`, `ruff format`, or `prettier`, when applicable.

Do not:

- place otherwise independent statements or declarations on one physical line;
- collapse branches or control flow merely to save lines;
- compress expressions or logical operations into unusually dense forms;
- manually minify or quasi-minify handwritten source;
- remove useful comments or structural whitespace solely to reduce LOC;
- adopt formatting inconsistent with the project's formatter or style to lower the count.

For example, do not change this readable code:

```csharp
var user = GetUser();
var trip = GetTrip();
Validate(user, trip);
Save(user, trip);
```

into this solely to evade LOC Guard:

```csharp
var user = GetUser(); var trip = GetTrip(); Validate(user, trip); Save(user, trip);
```

Legitimate LOC reduction comes from design or code improvement: remove redundant or dead code, simplify control flow, consolidate duplication when that improves the design, split cohesive responsibilities, or use a clearer idiom. A file is not legitimately below a threshold when deliberate readability-degrading physical-line compression produced the reduction. The checker does not detect this automatically; it is an agent behavioral requirement.

## Checker

The bundled checker is at:

```text
scripts/loc_guard.py
```

Recommended project-local copy:

```text
.agent-tools/loc_guard.py
```

## Policy reference

For the full reusable policy text to copy into `AGENTS.md`, `CLAUDE.md`, or another agent instruction file, see:

```text
references/loc-policy.md
```
