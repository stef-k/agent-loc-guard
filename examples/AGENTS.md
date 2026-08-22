# Agent Instructions

## LOC Guard

Use the LOC Guard skill when creating or modifying source files.

Run:

```bash
python3 .agent-tools/loc_guard.py . --config .agent-tools/loc-guard.config.json --changed-only
```

LOC Guard protects current work without making unrelated pre-existing technical debt part of the task. Files modified by the task are still evaluated in their resulting form; run without `--changed-only` only for an explicit full-repository audit.

400 counted LOC is a review trigger, not an automatic refactor command.

600 counted LOC is a hard cap unless the user explicitly approves an exception.

Honor existing approved `allowedLargeFiles` entries, but do not add, broaden, modify, repurpose, or invent reasons for exemptions without explicit user approval.

Do not game counted LOC through dense formatting, combined independent statements/declarations, minification, or removal of useful comments or structure. Follow the project's formatter and normal style; readability and design outrank metric optimization.

When a changed or new file warns:

1. Inspect whether the file is still cohesive and single-responsibility.
2. Decide whether the extra size is justified by necessary orchestration or simple structure.
3. Check whether the file is mixing separable responsibilities.
4. Consider likely near-term growth from upcoming slices before accepting a warning.
5. Split only when it improves responsibility boundaries or reduces meaningful complexity.
6. Do not split purely to satisfy the number if the split adds indirection without design benefit.

Report the decision as either:

```text
warning accepted with justification: ...
```

or:

```text
split performed because: ...
```
