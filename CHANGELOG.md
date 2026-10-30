# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-10-30

### Added

- Six-phase workflow (0–5): scope, recon, layer choice, walking skeleton,
  hardening, packaging.
- L0–L3 automation ladder with selection matrix, escalation/de-escalation, and
  hybrid trigger/verify patterns.
- Windows GUI engineering guide: locator cascade, focus, DPI awareness,
  clipboard input, polling waits, Qt quirks, drag/drop, failure capture.
- Safety and verification: read-only sources, copy-on-write, dry-run/`--yes`,
  exit codes, golden outputs, post-conditions, cross-checks, selftest.
- Batch and delivery guide: manifest-driven runs, per-item transactions,
  reconciliation, resume, failure isolation, print/export queues.
- Skill packaging guide: structure, frontmatter, decision trees, references,
  scripts, evals, privacy, public/private split.
- Anonymized case study with the failure modes and dead ends that shaped the
  workflow.
- `probe_windows.py`: read-only window/DPI/control-tree/screenshot probe.
- `scaffold_skill.py`: generates a runnable skill skeleton.
- `lint_skill.py`: pre-delivery structural, privacy, and compile checks.
- Unit tests and GitHub Actions CI for Ubuntu and Windows.

### Changed

- Refined the trigger description to cover direct SQLite/XML/JSON/log reading
  and launch/license/database-selection dialogs. Validated on a 20-query
  trigger set at 20/20 (3 runs per query).

### Fixed

- Corrected the DPI section: pyautogui does not automatically become DPI-aware;
  awareness must be checked and set before importing it.
- Corrected the workflow heading to match the 0–5 phases.
- Added missing guidance for `draw_outline`, `WindowFromPoint`, DWM invisible
  borders, `WM_DPICHANGED`, and `click_input(coords=...)`.
