#!/usr/bin/env python3
"""lint_skill.py — pre-delivery checks for a Claude Code skill.

Checks:
  * SKILL.md exists, has frontmatter, name matches the directory
  * description is present and long enough to trigger
  * SKILL.md is not bloated (>500 lines = warning)
  * every references/ scripts/ assets/ path mentioned in SKILL.md exists
  * no personal absolute paths, usernames, or obvious secrets
  * all Python scripts compile; all JSON files parse
  * obvious binary/project artifacts are present (warning)

Exit codes: 0 clean, 1 FAIL (or WARN with --strict), 2 usage.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

LINK_RE = re.compile(r"(?<![\w/])((?:references|scripts|assets)/[A-Za-z0-9_./-]+)")
PERSONAL_PATH_RE = re.compile(
    r"(?:[A-Za-z]:\\Users\\(?!<|\.\.\.)[^\\\s\"']+"
    r"|/(?:home|Users)/(?!<|\.\.\.)[^/\s\"']+)",
    re.IGNORECASE,
)
LAB_PATH_RE = re.compile(r"[A-Za-z]:\\Table\\", re.IGNORECASE)
SECRET_RES = [
    (re.compile(r"(?i)\b(api[_-]?key|secret|password|passwd|access[_-]?token)"
                r"\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{8,}"), "possible secret"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private key block"),
]
BINARY_SUFFIXES = {".db", ".fsf", ".dwg", ".dxf", ".lic", ".png", ".zip",
                   ".exe", ".dll", ".pdf", ".xlsx", ".docx"}


class Reporter:
    def __init__(self) -> None:
        self.checks: list[dict] = []

    def add(self, level: str, code: str, message: str) -> None:
        self.checks.append({"level": level, "code": code, "message": message})

    def ok(self, code: str, message: str) -> None:
        self.add("OK", code, message)

    def warn(self, code: str, message: str) -> None:
        self.add("WARN", code, message)

    def fail(self, code: str, message: str) -> None:
        self.add("FAIL", code, message)

    def counts(self) -> tuple[int, int]:
        fails = sum(1 for c in self.checks if c["level"] == "FAIL")
        warns = sum(1 for c in self.checks if c["level"] == "WARN")
        return fails, warns


def parse_frontmatter(text: str) -> tuple[dict[str, str], str | None]:
    if not text.startswith("---"):
        return {}, "SKILL.md must start with YAML frontmatter (---)"
    end = text.find("\n---", 3)
    if end == -1:
        return {}, "frontmatter is not closed with ---"
    block = text[3:end]
    data: dict[str, str] = {}
    for line in block.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip().strip("'\"")
    return data, None


def check_skill(skill: Path, rep: Reporter) -> None:
    skill_md = skill / "SKILL.md"
    if not skill_md.is_file():
        rep.fail("skill.md", f"missing {skill_md}")
        return
    text = skill_md.read_text(encoding="utf-8", errors="replace")
    rep.ok("skill.md", f"found SKILL.md ({len(text.splitlines())} lines)")

    data, err = parse_frontmatter(text)
    if err:
        rep.fail("frontmatter", err)
    else:
        name = data.get("name", "")
        desc = data.get("description", "")
        if not name:
            rep.fail("frontmatter.name", "missing name")
        elif not re.match(r"^[a-z][a-z0-9-]{1,62}$", name):
            rep.fail("frontmatter.name", f"not kebab-case: {name!r}")
        elif name != skill.name:
            rep.fail("frontmatter.name",
                     f"name {name!r} does not match directory {skill.name!r}")
        else:
            rep.ok("frontmatter.name", name)

        if not desc:
            rep.fail("frontmatter.description", "missing description")
        elif len(desc) < 60:
            rep.warn("frontmatter.description",
                     f"description is short ({len(desc)} chars); "
                     "add product names, aliases, file types, and task verbs")
        else:
            rep.ok("frontmatter.description", f"{len(desc)} chars")

    lines = len(text.splitlines())
    if lines > 500:
        rep.warn("skill.md.length",
                 f"{lines} lines (>500); move details into references/")
    else:
        rep.ok("skill.md.length", f"{lines} lines")

    # Referenced files must exist (skip templates/globs with placeholders).
    referenced = set()
    for match in LINK_RE.finditer(text):
        rel = match.group(1).rstrip(".,);:")
        if any(ch in rel for ch in "<>{}*") or rel.endswith("/"):
            continue
        referenced.add(rel)
    missing = []
    for rel in sorted(referenced):
        if not (skill / rel).exists():
            missing.append(rel)
    if missing:
        rep.fail("references.missing", "missing: " + ", ".join(missing))
    else:
        rep.ok("references", f"{len(referenced)} referenced path(s) exist")

    # Personal data / secrets, across docs the skill will be shipped with.
    docs = [skill_md]
    docs += sorted((skill / "references").rglob("*.md")) if (skill / "references").is_dir() else []
    docs += sorted((skill / "evals").glob("*.json")) if (skill / "evals").is_dir() else []
    docs += [
        p for p in (
            skill / "README.md", skill / "SECURITY.md", skill / "CONTRIBUTING.md",
            skill / "CHANGELOG.md", skill / "LICENSE", skill / "RESTORE.md",
            skill / "config.toml.example",
        ) if p.is_file()
    ]

    personal_hits: list[str] = []
    lab_hits: list[str] = []
    secret_hits: list[str] = []
    username = os.environ.get("USERNAME") or os.environ.get("USER") or ""
    username_hits: list[str] = []
    for path in docs:
        body = path.read_text(encoding="utf-8", errors="replace")
        rel = path.relative_to(skill)
        for match in PERSONAL_PATH_RE.findall(body):
            personal_hits.append(f"{rel}: {match}")
        for match in LAB_PATH_RE.findall(body):
            lab_hits.append(f"{rel}: {match}")
        if len(username) >= 3 and re.search(
            rf"\b{re.escape(username)}\b", body, re.IGNORECASE
        ):
            username_hits.append(str(rel))
        for pattern, label in SECRET_RES:
            if pattern.search(body):
                secret_hits.append(f"{rel}: {label}")

    if personal_hits:
        rep.fail("privacy.path",
                 "personal absolute path(s): " + ", ".join(personal_hits[:3]))
    else:
        rep.ok("privacy.path", "no personal absolute paths in docs")

    if lab_hits:
        rep.fail("privacy.lab_path",
                 "machine-specific path(s): " + ", ".join(lab_hits[:3]))
    else:
        rep.ok("privacy.lab_path", "no machine-specific paths in docs")

    if username_hits:
        rep.fail("privacy.username",
                 f"username {username!r} appears in: " + ", ".join(username_hits[:3]))
    else:
        rep.ok("privacy.username", "no local username in docs")

    if secret_hits:
        rep.warn("privacy.secret", "check: " + ", ".join(secret_hits[:3]))
    else:
        rep.ok("privacy.secret", "no obvious secret pattern")

    # Python compiles.
    py_files = sorted((skill / "scripts").rglob("*.py")) if (skill / "scripts").is_dir() else []
    broken = []
    for path in py_files:
        try:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        except Exception as exc:
            broken.append(f"{path.name}: {exc}")
    if broken:
        rep.fail("scripts.compile", "; ".join(broken[:5]))
    else:
        rep.ok("scripts.compile", f"{len(py_files)} Python file(s) compile")

    # JSON parses.
    json_files = sorted(skill.rglob("*.json"))
    json_broken = []
    for path in json_files:
        if path.stat().st_size > 2_000_000:
            continue
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            json_broken.append(f"{path.name}: {exc}")
    if json_broken:
        rep.fail("json.parse", "; ".join(json_broken[:5]))
    else:
        rep.ok("json.parse", f"{len(json_files)} JSON file(s) parse")

    # Artifacts that should not ship.
    artifacts = [
        str(p.relative_to(skill))
        for p in skill.rglob("*")
        if p.is_file() and p.suffix.lower() in BINARY_SUFFIXES
    ]
    if artifacts:
        rep.warn("artifacts", "binary/project files present: " + ", ".join(artifacts[:5]))
    else:
        rep.ok("artifacts", "no binary/project artifacts")

    # TODOs are expected in scaffolds but not in a finished skill.
    todo_count = len(re.findall(r"\b(TODO|FIXME)\b", text))
    if todo_count:
        rep.warn("todo", f"{todo_count} TODO/FIXME marker(s) in SKILL.md")
    else:
        rep.ok("todo", "no TODO/FIXME in SKILL.md")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Lint a Claude Code skill.")
    parser.add_argument("path", help="skill directory")
    parser.add_argument("--strict", action="store_true",
                        help="treat warnings as failures")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    skill = Path(args.path).expanduser().resolve()
    if not skill.is_dir():
        print(f"error: not a directory: {skill}", file=sys.stderr)
        return 2

    rep = Reporter()
    check_skill(skill, rep)
    fails, warns = rep.counts()
    ok = fails == 0 and (not args.strict or warns == 0)

    if args.json:
        print(json.dumps(
            {"ok": ok, "fails": fails, "warnings": warns, "checks": rep.checks},
            ensure_ascii=True, indent=2,
        ))
    else:
        for check in rep.checks:
            print(f"[{check['level']}] {check['code']}: {check['message']}")
        print(f"\nresult: {fails} fail(s), {warns} warning(s) -> "
              f"{'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
