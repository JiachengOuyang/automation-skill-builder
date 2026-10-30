#!/usr/bin/env python3
"""scaffold_skill.py — generate a runnable skill skeleton for app automation.

The generated skill is deliberately small but end-to-end:
  * one CLI dispatcher
  * env/config check with  env > config.toml > defaults
  * selftest with [OK]/[WARN]/[FAIL]
  * bash and cmd shims
  * SKILL.md, references/, evals/, config.toml.example, RESTORE.md

Usage:
  python scaffold_skill.py --name my-app --app "My App" --out ./my-app-skill
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

NAME_RE = re.compile(r"^[a-z][a-z0-9-]{1,62}$")


def _write(path: Path, text: str, mode: int | None = None,
           newline: str = "\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline=newline)
    if mode is not None:
        try:
            os.chmod(path, mode)
        except OSError:
            pass


def _cli(slug: str, app: str) -> str:
    mod = slug.replace("-", "_")
    return f'''#!/usr/bin/env python3
"""__APP__ automation CLI (generated scaffold).

Replace the hello command with real domain commands. Keep the dispatcher thin:
each module exposes main(argv) -> int and owns its own argparse parser.
"""
from __future__ import annotations

import argparse
import importlib
import sys

COMMANDS = {{
    "env": "{mod}_env",
    "selftest": "{mod}_selftest",
}}

APP = "{app}"
VERSION = "0.1.0"


def cmd_hello(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="{slug} hello")
    parser.add_argument("--name", default="world")
    args = parser.parse_args(argv)
    print(f"hello {{args.name}} from {{APP}} {{VERSION}}")
    return 0


def print_help() -> None:
    print(f"{{APP}} automation CLI ({{VERSION}})")
    print()
    print("usage: {slug} <command> [options]")
    print()
    print("commands:")
    print("  env check [--json]     show effective paths/config and status")
    print("  selftest [--json]      smoke-test the environment")
    print("  hello [--name NAME]    placeholder command")
    print()
    print("Add real commands in COMMANDS above, one module per domain.")


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print_help()
        return 0
    name = argv[0]
    if name in ("-V", "--version"):
        print(VERSION)
        return 0
    if name == "hello":
        return cmd_hello(argv[1:])
    target = COMMANDS.get(name)
    if target is None:
        print(f"unknown command: {{name}}", file=sys.stderr)
        return 2
    try:
        module = importlib.import_module(target)
    except ImportError as exc:
        print(f"error: cannot import {{target}}: {{exc}}", file=sys.stderr)
        return 3
    return int(module.main(argv[1:]))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
'''


def _env(slug: str, app: str) -> str:
    mod = slug.replace("-", "_")
    prefix = slug.upper().replace("-", "_")
    work = f"_{slug}_work"
    return f'''#!/usr/bin/env python3
"""__APP__ environment/config helper (generated scaffold).

Priority: environment variable > config.toml > built-in default.
Config search: <PREFIX>_SKILL_CONFIG, then ./config.toml, then skill root.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    try:
        import tomli as tomllib  # type: ignore
    except ModuleNotFoundError:
        tomllib = None  # type: ignore

SKILL_ROOT = Path(__file__).resolve().parent.parent
PREFIX = "{prefix}"
APP = "{app}"

DEFAULTS = {{
    ("app", "install_dir"): "",
    ("app", "exe"): "",
    ("gui", "timeout"): 60,
    ("work", "dir"): "{work}",
}}


def config_path() -> Path | None:
    explicit = os.environ.get(PREFIX + "_SKILL_CONFIG", "")
    if explicit:
        path = Path(explicit).expanduser()
        return path if path.is_file() else None
    for path in (Path.cwd() / "config.toml", SKILL_ROOT / "config.toml"):
        if path.is_file():
            return path
    return None


def load_config() -> dict:
    path = config_path()
    if path is None or tomllib is None:
        return {{}}
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
        return data if isinstance(data, dict) else {{}}
    except Exception:
        return {{}}


def get(section: str, key: str, default=None):
    env_key = f"{{PREFIX}}_{{section}}_{{key}}".upper()
    if env_key in os.environ:
        return os.environ[env_key]
    section_data = load_config().get(section, {{}})
    if isinstance(section_data, dict) and key in section_data:
        return section_data[key]
    if default is not None:
        return default
    return DEFAULTS.get((section, key), "")


def check() -> dict:
    items: list[dict] = []
    path = config_path()
    items.append({{
        "name": "config",
        "status": "OK" if path else "WARN",
        "detail": str(path) if path else "config.toml not found (defaults in use)",
    }})

    install = str(get("app", "install_dir", ""))
    if install:
        exists = Path(install).expanduser().is_dir()
        items.append({{
            "name": "install_dir",
            "status": "OK" if exists else "FAIL",
            "detail": install,
        }})
    else:
        items.append({{"name": "install_dir", "status": "WARN",
                      "detail": "not set in config.toml"}})

    exe = str(get("app", "exe", ""))
    if exe:
        exe_path = Path(exe).expanduser()
        if not exe_path.is_absolute() and install:
            exe_path = Path(install).expanduser() / exe_path
        items.append({{
            "name": "exe",
            "status": "OK" if exe_path.is_file() else "FAIL",
            "detail": str(exe_path),
        }})

    work = str(get("work", "dir"))
    work_path = Path(work).expanduser()
    if not work_path.is_absolute():
        work_path = SKILL_ROOT / work_path
    try:
        work_path.mkdir(parents=True, exist_ok=True)
        writable = os.access(work_path, os.W_OK)
        items.append({{
            "name": "work_dir",
            "status": "OK" if writable else "FAIL",
            "detail": str(work_path),
        }})
    except OSError as exc:
        items.append({{"name": "work_dir", "status": "FAIL", "detail": str(exc)}})

    fail = any(i["status"] == "FAIL" for i in items)
    warn = any(i["status"] == "WARN" for i in items)
    status = "FAIL" if fail else ("WARN" if warn else "OK")
    return {{"status": status, "app": APP, "config": str(path) if path else None,
             "items": items}}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="{slug} env")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    data = check()
    if args.json:
        print(json.dumps(data, ensure_ascii=True, indent=2))
    else:
        print(f"{{APP}} environment")
        for item in data["items"]:
            print(f"[{{item['status']}}] {{item['name']}}: {{item['detail']}}")
        print(f"status: {{data['status']}}")
    return 1 if data["status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
'''


def _selftest(slug: str, app: str) -> str:
    mod = slug.replace("-", "_")
    return f'''#!/usr/bin/env python3
"""__APP__ selftest (generated scaffold)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import {mod}_env as envmod

MIN_PY = (3, 10)


def run_checks() -> list[dict]:
    items: list[dict] = []

    items.append({{
        "name": "python",
        "status": "OK" if sys.version_info >= MIN_PY else "FAIL",
        "detail": sys.version.split()[0],
    }})

    env = envmod.check()
    items.append({{
        "name": "environment",
        "status": env["status"],
        "detail": env.get("config") or "no config.toml (defaults)",
    }})

    script_dir = Path(__file__).resolve().parent
    py_files = sorted(script_dir.glob("*.py"))
    broken: list[str] = []
    for path in py_files:
        try:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        except Exception as exc:
            broken.append(f"{{path.name}}: {{exc}}")
    items.append({{
        "name": "scripts",
        "status": "OK" if not broken else "FAIL",
        "detail": f"{{len(py_files)}} file(s)" if not broken else "; ".join(broken[:3]),
    }})

    try:
        import json as _json
        for path in (script_dir.parent / "evals").glob("*.json"):
            _json.loads(path.read_text(encoding="utf-8"))
        items.append({{"name": "evals_json", "status": "OK", "detail": "parsed"}})
    except Exception as exc:
        items.append({{"name": "evals_json", "status": "WARN", "detail": str(exc)}})

    return items


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="{slug} selftest")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    items = run_checks()
    failed = any(i["status"] == "FAIL" for i in items)
    if args.json:
        print(json.dumps({{"ok": not failed, "items": items}}, ensure_ascii=True, indent=2))
    else:
        print(f"{{'FAIL' if failed else 'OK'}}: {slug} selftest")
        for item in items:
            print(f"[{{item['status']}}] {{item['name']}}: {{item['detail']}}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
'''


def _skill_md(slug: str, app: str) -> str:
    return f'''---
name: {slug}
description: 用 {app} 做自动化……（TODO：把产品名、别名、模块名、文件后缀、用户会说的动词都列进来；最后加一句“即使用户没有点名 {app} 也触发”。）
---

# {app} 自动化技能

> 这是脚手架生成的骨架。先用侦察结果替换所有 TODO，再删掉不需要的章节。

## 红线

1. 不碰原件：项目/数据只读，改写先复制到 `_{slug}_work/`。
2. 危险 GUI 动作默认拒绝，必须 `--yes`。
3. 不猜命令/字段/语法；以录制、日志、文档或实测为准。
4. 不硬编码坐标；坐标只兜底并告警。
5. 不用固定 sleep；轮询可观测状态。
6. 三次失败停下，记录证据并问用户。

## 先自检

```bash
scripts/{slug} env --json
scripts/{slug} selftest
```

`status: OK` 才继续；`[WARN]` 记录原因；`[FAIL]` 先修环境。

## 决策树

| 用户想做什么 | 用什么 |
|---|---|
| 检查环境/配置 | `scripts/{slug} env --json` |
| 冒烟测试 | `scripts/{slug} selftest` |
| TODO：启动软件 | `scripts/{slug} launch ...` |
| TODO：读数据/查结果 | `scripts/{slug} db ...`（只读） |
| TODO：批量操作 | `scripts/{slug} <domain> ... --copy` |
| TODO：只能点界面 | `scripts/{slug} gui ...`（先截图/控件树） |

## 已侦察到的事实

- 安装目录：TODO
- 启动方式/包装脚本：TODO
- 配置/日志位置：TODO
- 数据格式/数据库：TODO
- 可用接口（CLI/COM/脚本/宏）：TODO
- 界面工具包/控件可访问性：TODO

## 输出约定

- 工作目录：`_{slug}_work/`
- 日志：`_{slug}_work/logs/`
- 截图：`_{slug}_work/screenshots/`
- 失败现场：`_{slug}_work/failures/`

## 已知限制 / 未验证

- TODO：把“未打通/未验证/不要走的路”写在这里。

## 参考文档

| 文件 | 内容 |
|---|---|
| `references/automation-notes.md` | 侦察记录、分层选择、实测结论 |
| `references/troubleshooting.md` | 现象 → 原因 → 处理 |
'''


def _shim_bash(slug: str) -> str:
    mod = slug.replace("-", "_")
    return f'''#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PY="$HERE/../.venv/Scripts/python.exe"
[ -x "$PY" ] || PY="$HERE/../../.venv/Scripts/python.exe"
[ -x "$PY" ] || PY="python"
export PYTHONUTF8=1
exec "$PY" "$HERE/{mod}_cli.py" "$@"
'''


def _shim_cmd(slug: str) -> str:
    mod = slug.replace("-", "_")
    return f'''@echo off
setlocal
set "HERE=%~dp0"
set "PY=%HERE%..\\.venv\\Scripts\\python.exe"
if not exist "%PY%" set "PY=%HERE%..\\..\\.venv\\Scripts\\python.exe"
if not exist "%PY%" set "PY=python"
set PYTHONUTF8=1
"%PY%" "%HERE%{mod}_cli.py" %*
'''


def _notes(slug: str, app: str) -> str:
    return f'''# {app} 侦察与自动化笔记

## 环境

- 日期：
- 软件版本：
- Windows 版本 / 分辨率 / 缩放：
- 安装路径：
- 启动方式：
- 许可方式：
- 配置位置：
- 日志位置：

## 启动链

1. TODO

## 数据与接口

| 类型 | 位置/格式 | 只读方法 | 备注 |
|---|---|---|---|
| 项目文件 | TODO | | |
| 数据库 | TODO | | |
| CLI/脚本 | TODO | | |
| 日志 | TODO | | |

## 分层选择

| 层 | 用不用 | 原因 |
|---|---|---|
| L0 配置/文件 | TODO | |
| L1 原生接口 | TODO | |
| L2 数据/日志 | TODO | |
| L3 GUI | TODO | |

## 已实测

| 日期 | 操作 | 结果 | 证据（md5/数值/截图） |
|---|---|---|---|
| | | | |

## 不要再走的路

- TODO：失败 ≥3 次的路径，写清现象和根因。
'''


def _troubleshooting(slug: str) -> str:
    return '''# 排障

| 现象 | 原因 | 处理 |
|---|---|---|
| 启动即退 | TODO | TODO |
| 找不到窗口 | TODO | TODO |
| 点击无效 | TODO | TODO |
| 结果不对 | TODO | TODO |
| 文件被锁 | TODO | TODO |

## 采集现场

```text
_<app>_work/failures/<timestamp>/
  screenshot.png
  controls.txt
  windows.json
  foreground.txt
  app.log
  step.txt
```
'''


def _restore(slug: str, app: str) -> str:
    return f'''# 换机器恢复

## 新机器

1. 安装 {app}（版本：TODO）。
2. 准备 Python 3.10+。
3. 复制本 skill 目录。
4. 运行 `scripts/{slug} env --json`，按提示写 `config.toml`（参考 `config.toml.example`）。
5. 运行 `scripts/{slug} selftest`。

## 已配置机器

只替换 `scripts/` 和 `SKILL.md`，保留 `config.toml`。

## 升级

1. 备份旧版。
2. 替换代码。
3. 跑 `selftest` 和一条端到端命令。
4. 记录版本/日期到 `references/automation-notes.md`。

## 回滚

恢复备份目录；`config.toml` 不动。
'''


def _evals(slug: str, app: str) -> str:
    return f'''{{
  "skill_name": "{slug}",
  "evals": [
    {{
      "id": 1,
      "prompt": "用 {app} 把这批文件批量处理一下，具体是 TODO。",
      "expected_output": "先侦察输入格式与可用接口，给出最小闭环和验收方式，不直接硬点界面。",
      "files": []
    }},
    {{
      "id": 2,
      "prompt": "{app} 打不开了，帮我看看怎么回事。",
      "expected_output": "先看启动链/日志/selftest，定位是许可、配置还是路径问题。",
      "files": []
    }},
    {{
      "id": 3,
      "prompt": "这个软件没有 API，只能点界面，能不能自动化？",
      "expected_output": "先确认是否真的没有 CLI/脚本/数据库入口；若只能 GUI，给出控件树/DPI/焦点/等待方案和 L2 验收。",
      "files": []
    }}
  ]
}}
'''


def _config_example(slug: str) -> str:
    return f'''# Copy to config.toml and fill in.
[app]
install_dir = ""
exe = ""

[gui]
timeout = 60
# dpi_scale = 1.5

[work]
dir = "_{slug}_work"
'''


def write_skill(target: Path, slug: str, app: str, force: bool) -> list[Path]:
    if target.exists() and any(target.iterdir()):
        if not force:
            raise SystemExit(
                f"error: {target} exists and is not empty; pass --force to overwrite"
            )

    files: list[Path] = []

    def add(rel: str, text: str, mode: int | None = None,
            newline: str = "\n") -> None:
        path = target / rel
        _write(path, text, mode, newline)
        files.append(path)

    add("SKILL.md", _skill_md(slug, app))
    add(f"scripts/{slug.replace('-', '_')}_cli.py", _cli(slug, app))
    add(f"scripts/{slug.replace('-', '_')}_env.py", _env(slug, app))
    add(f"scripts/{slug.replace('-', '_')}_selftest.py", _selftest(slug, app))
    add(f"scripts/{slug}", _shim_bash(slug), 0o755)
    add(f"scripts/{slug}.cmd", _shim_cmd(slug), newline="\r\n")
    add("scripts/requirements.txt",
        "# Optional GUI dependencies; install in the project venv.\n"
        "# pywinauto>=0.6.9\n# Pillow\n# pyperclip\n# pyautogui\n")
    add("references/automation-notes.md", _notes(slug, app))
    add("references/troubleshooting.md", _troubleshooting(slug))
    add("evals/evals.json", _evals(slug, app))
    add("config.toml.example", _config_example(slug))
    add("RESTORE.md", _restore(slug, app))
    return files


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Generate a runnable automation skill skeleton."
    )
    parser.add_argument("--name", required=True,
                        help="skill directory name, kebab-case (e.g. my-app)")
    parser.add_argument("--app", required=True,
                        help="human-readable application name")
    parser.add_argument("--out", default=None,
                        help="target directory (default: ./<name>)")
    parser.add_argument("--force", action="store_true",
                        help="overwrite an existing non-empty directory")
    args = parser.parse_args(argv)

    if not NAME_RE.match(args.name):
        print("error: --name must be kebab-case: ^[a-z][a-z0-9-]{1,62}$",
              file=sys.stderr)
        return 2
    if not args.app.strip():
        print("error: --app must not be empty", file=sys.stderr)
        return 2

    target = Path(args.out or args.name).expanduser().resolve()
    if target.name != args.name:
        print(
            f"warning: target directory {target.name!r} != skill name "
            f"{args.name!r}; Claude expects them to match, so rename before install",
            file=sys.stderr,
        )
    files = write_skill(target, args.name, args.app.strip(), args.force)

    print(f"created {len(files)} file(s) in {target}")
    for path in files:
        print(f"  {path.relative_to(target)}")
    print()
    print("next:")
    print(f"  python {target / 'scripts' / (args.name.replace('-', '_') + '_cli.py')} env --json")
    print(f"  python {target / 'scripts' / (args.name.replace('-', '_') + '_cli.py')} selftest")
    print(f"  python <this-skill>/scripts/lint_skill.py {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
