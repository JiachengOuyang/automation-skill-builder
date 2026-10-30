from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def run(args: list[object], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, *[str(a) for a in args]],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def make_skill(root: Path, name: str, body: str) -> Path:
    skill = root / name
    skill.mkdir(parents=True)
    description = (
        "A production-ready automation skill used to exercise the linter. "
        "It should trigger on desktop automation tasks."
    )
    (skill / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n{body}\n",
        encoding="utf-8",
    )
    return skill


class ScaffoldTests(unittest.TestCase):
    def test_scaffold_is_runnable_and_lints(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "demo-app"
            result = run([
                SCRIPTS / "scaffold_skill.py",
                "--name", "demo-app", "--app", "Demo App", "--out", target,
            ])
            self.assertEqual(result.returncode, 0, result.stderr)

            expected = [
                "SKILL.md",
                "scripts/demo_app_cli.py",
                "scripts/demo_app_env.py",
                "scripts/demo_app_selftest.py",
                "scripts/demo-app",
                "scripts/demo-app.cmd",
                "references/automation-notes.md",
                "references/troubleshooting.md",
                "evals/evals.json",
                "config.toml.example",
                "RESTORE.md",
            ]
            for rel in expected:
                self.assertTrue((target / rel).exists(), rel)

            env = run([target / "scripts/demo_app_cli.py", "env", "--json"])
            self.assertEqual(env.returncode, 0, env.stderr)
            payload = json.loads(env.stdout)
            self.assertEqual(payload["app"], "Demo App")
            self.assertIn(payload["status"], ("OK", "WARN"))
            self.assertTrue(any(i["name"] == "work_dir" for i in payload["items"]))

            selftest = run([target / "scripts/demo_app_cli.py", "selftest"])
            self.assertEqual(selftest.returncode, 0, selftest.stdout + selftest.stderr)
            self.assertIn("[OK] python", selftest.stdout)

            lint = run([SCRIPTS / "lint_skill.py", target])
            self.assertEqual(lint.returncode, 0, lint.stdout + lint.stderr)
            self.assertIn("0 fail", lint.stdout)

    def test_bad_name_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            result = run([
                SCRIPTS / "scaffold_skill.py",
                "--name", "Bad_Name", "--app", "X", "--out", Path(td) / "x",
            ])
            self.assertEqual(result.returncode, 2)
            self.assertIn("kebab-case", result.stderr)


class LintTests(unittest.TestCase):
    def test_missing_reference_fails(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            skill = make_skill(Path(td), "bad-ref", "See references/missing.md")
            result = run([SCRIPTS / "lint_skill.py", skill])
            self.assertEqual(result.returncode, 1)
            self.assertIn("missing", result.stdout.lower())

    def test_personal_path_fails(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            skill = make_skill(
                Path(td), "bad-path", r"Example: C:\Users\alice\private\data"
            )
            result = run([SCRIPTS / "lint_skill.py", skill])
            self.assertEqual(result.returncode, 1)
            self.assertIn("personal", result.stdout.lower())

    def test_valid_skill_passes_strict(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            skill = make_skill(
                Path(td), "good-skill",
                "A short, clean skill body with no references.",
            )
            result = run([SCRIPTS / "lint_skill.py", skill, "--strict"])
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_json_output_is_machine_readable(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            skill = make_skill(Path(td), "json-skill", "Body.")
            result = run([SCRIPTS / "lint_skill.py", skill, "--json"])
            payload = json.loads(result.stdout)
            self.assertIn("ok", payload)
            self.assertIn("checks", payload)
            self.assertEqual(payload["fails"], 0)


class ProbeTests(unittest.TestCase):
    def test_help_works_on_any_platform(self) -> None:
        result = run([SCRIPTS / "probe_windows.py", "--help"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Read-only", result.stdout)


if __name__ == "__main__":
    unittest.main()
