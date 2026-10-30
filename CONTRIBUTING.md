# Contributing

Thanks for improving `automation-skill-builder`.

## Ground rules

- Keep it generic. Do not add vendor-specific internal commands, customer data,
  machine paths, license keys, or screenshots with identifying information.
- Prefer executable steps over general advice. A checklist item should say what
  to run, what to observe, and what counts as success.
- Record evidence: date, version, resolution/DPI, and the observed result.
- If a path is a dead end, document it under "不要再走的路" / "Do not go this way".

## Adding a reference

- Put cross-cutting topics in `references/<topic>.md`; keep command catalogs separate.
- Add a table of contents if the file is longer than ~300 lines.
- Use "symptom | cause | fix" tables for troubleshooting.
- Link the new file from `SKILL.md`'s reference table.
- Keep `SKILL.md` under 500 lines; move detail into references.

## Adding a script

- One entry point, with a thin dispatcher and modules exposing `main(argv) -> int`.
- Support `--dry-run` for side effects and `--json` for machine-readable output.
- Use the exit-code convention: 0 success, 1 runtime/verification failure,
  2 usage/safety refusal, 3 missing dependency/environment.
- Never write to installation directories; use a project-local work directory.
- Add tests under `tests/`.

## Before opening a PR

```bash
python -m unittest discover -s tests -v
python scripts/lint_skill.py . --strict
```

- Update `CHANGELOG.md` under `Unreleased` or the next version.
- Bump `VERSION` for user-visible behavior changes.
- Describe the problem, the change, and how you verified it.

## License

By contributing, you agree that your contributions are licensed under the MIT
License (see `LICENSE`).
