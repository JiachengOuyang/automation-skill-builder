# Security policy

## Supported versions

The `1.x` line is supported. Security fixes are applied to the latest release.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting or open a security advisory
on this repository. Do not open a public issue with exploit details.

Include:

- affected version/commit,
- a minimal reproduction or proof of concept,
- impact and suggested fix (if known).

## Scope

This project provides automation methodology and tooling. It intentionally does
**not** include:

- license, DRM, login, CAPTCHA, or access-control bypasses;
- exploits or privilege escalation;
- malware, persistence, or data exfiltration.

Reports about those capabilities are out of scope.

## Safe use

- Automate only software you are authorized to automate, and follow its EULA.
- Review generated scripts and skills before running them. A Claude Code skill
  can execute code on your machine.
- Keep source data read-only; back up before writes; prefer `--dry-run`.
- `probe_windows.py` is read-only. GUI automation is not: it can click, type, and
  overwrite. Use `--yes` deliberately and keep failure artifacts.
- Do not put credentials, license keys, or customer data into skills, logs, or
  screenshots.
