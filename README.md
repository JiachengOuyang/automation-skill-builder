# automation-skill-builder

> 把一个陌生桌面软件摸清、做自动化，并封装成可复用的 Claude Code skill。
> A Claude Code skill for turning a desktop application into a reliable, reusable automation skill.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![tests](https://github.com/JiachengOuyang/automation-skill-builder/actions/workflows/test.yml/badge.svg)](https://github.com/JiachengOuyang/automation-skill-builder/actions/workflows/test.yml)

---

## 中文

### 这是什么

大多数桌面软件没有好用的 API。直接写 pywinauto 坐标脚本，往往在换分辨率、换版本、中文输入法、Qt 自绘控件面前崩掉。

这个 skill 把“**先侦察、再选层、先闭环、后工程化、最后封装**”做成一套可执行的流程，并附带三个工具：

- `probe_windows.py`：只读侦察。列窗口、看 DPI、dump 控件树、截图、按名称找控件，不会点击或输入。
- `scaffold_skill.py`：生成一个能直接跑的 skill 骨架（CLI + env check + selftest + 双平台启动壳）。
- `lint_skill.py`：交付前自检。frontmatter、引用文件、本机路径/用户名/密钥、脚本编译、JSON。

它不是 pywinauto 用法大全，而是从一次完整的 CAD/CAE 软件自动化项目里提炼出的**避坑清单**。

### 为什么需要它

- **GUI 最贵、最脆**：大多数“点界面”的需求，其实有配置文件、命令行、数据库或日志入口。
- **点完不等于成功**：界面弹“完成”，数据可能没变；必须用数据库/文件/数值验收。
- **失败会重复**：坐标、DPI、焦点、输入法、文件锁、残留进程，每个都能让脚本“偶尔成功、经常失败”。
- **知识会丢**：不写成决策树和“不要走的路”，下一个人（或未来的你）会再踩一遍。

### 核心原则

1. **先找不用界面的入口**：配置/文件 → CLI/COM/插件/脚本 → 数据库/日志 → GUI。
2. **GUI 只做扳机**：点“开始”，结果用 L2（数据库/文件/日志）验收。
3. **一切写操作先复制**：源数据只读，改写走副本。
4. **定位靠结构，坐标只兜底**：AutomationId/Name → 标签 → 行内文字点 → 坐标 → 模板。
5. **等待轮询状态**：窗口出现、控件可用、DB 行数、文件大小稳定；不用固定 sleep。
6. **三次失败换策略**：不要重复同样的点击。
7. **没有黄金输出/后置条件，不算打通**。
8. **封装时写清“不要走的路”**，比只写正确做法更省时间。
9. **分享前脱敏**：路径、用户名、许可证、客户数据、内部命令名。

### 安装

用户级（所有项目可用）：

```bash
# macOS / Linux
git clone https://github.com/JiachengOuyang/automation-skill-builder.git ~/.claude/skills/automation-skill-builder

# Windows PowerShell
git clone https://github.com/JiachengOuyang/automation-skill-builder.git "$env:USERPROFILE\.claude\skills\automation-skill-builder"
```

> 如果实际仓库地址不同，替换上面的 URL 即可。

项目级（只在该项目触发）：

```bash
git clone https://github.com/JiachengOuyang/automation-skill-builder.git <project>/.claude/skills/automation-skill-builder
```

依赖：

- Python 3.10+。
- `probe_windows.py` 的 `windows/info/scaling` 只用标准库；`dump/find` 需要 `pywinauto`，`shot` 需要 `Pillow`。
- 目前 `probe_windows.py` 只支持 Windows；其余脚本跨平台。

```bash
pip install -r requirements.txt
```

### 快速开始

```bash
# 1) 侦察一个正在运行的软件（只读，不会点击）
python scripts/probe_windows.py windows --filter "MyApp"
python scripts/probe_windows.py info --title "MyApp"
python scripts/probe_windows.py scaling --json
python scripts/probe_windows.py dump --title "MyApp" --out _work/controls.txt
python scripts/probe_windows.py find --title "MyApp" --name "Export|导出"
python scripts/probe_windows.py shot --title "MyApp" --out _work/shot.png

# 2) 生成新 skill 骨架
python scripts/scaffold_skill.py --name my-app --app "My App" --out ../my-app

# 3) 跑通骨架
python ../my-app/scripts/my_app_cli.py env --json
python ../my-app/scripts/my_app_cli.py selftest

# 4) 交付前自检（填完 TODO 后再加 --strict）
python scripts/lint_skill.py ../my-app
```

`scaffold_skill.py` 生成的目录名必须和 `--name` 一致；Claude 用目录名匹配 skill 名。

### 工作流（0–5）

| 阶段 | 核心问题 | 产出 | 通过条件 |
|---|---|---|---|
| 0 定边界 | 要重复做的到底是什么？ | 验收断言 + 最小样例 | 能一句话说清“成功长什么样” |
| 1 侦察 | 有哪些入口？错误写在哪？ | 启动链/数据/接口/界面清单 | 能安全启停；不看界面能读到一种结果 |
| 2 选层 | 哪一层最稳、最省？ | L0–L3 方案 + 证据 | 每层都有“怎么证明生效” |
| 3 闭环 | 能一条命令跑通吗？ | CLI 骨架 + 一条端到端 | 连跑两次结果一致，失败能清理 |
| 4 工程化 | 换机器/换数据还稳吗？ | 护栏 + selftest + 校准清单 | 冷启动 selftest 通过 |
| 5 封装 | 别人能直接用吗？ | skill 包 + 文档 + evals | 新会话照文档能复现 |

自动化层从稳到脆：

| 层 | 手段 | 典型用途 |
|---|---|---|
| L0 | 配置/文件 | 批量生成、格式转换、参数注入 |
| L1 | CLI/COM/插件/内嵌脚本/宏 | 真正的建模、计算、导出 |
| L2 | 数据库/日志/产物 | 读结果、做验收、绕开界面 |
| L3 | UIA/win32/键盘/剪贴板/截图 | 只能点界面的缺口 |

最常见的好方案是 **L3 + L2**：GUI 只负责扳机，结果用数据库/文件验收。

### 仓库结构

```text
.
├── SKILL.md                  # 触发 + 六阶段 + 决策树 + GUI 规则
├── references/
│   ├── recon.md              # 侦察清单
│   ├── automation-layers.md  # L0–L3 分层与选择矩阵
│   ├── gui-automation.md     # Windows GUI 工程手册
│   ├── safety-and-verification.md
│   ├── batch-and-delivery.md # manifest/对账/续跑/打印队列
│   ├── skill-packaging.md    # 封装、脱敏、发布
│   └── case-study.md         # 匿名案例
├── scripts/
│   ├── probe_windows.py
│   ├── scaffold_skill.py
│   └── lint_skill.py
├── evals/evals.json
├── tests/test_tools.py
├── requirements.txt
├── .github/workflows/test.yml
├── LICENSE
└── README.md
```

### 安全与合规

- 只自动化你**有权自动化**的软件；遵守 EULA、公司政策和当地法律。
- 不绕过许可证、DRM、登录、验证码或访问控制。
- 源数据只读；修改前备份；有副作用的命令默认 `--dry-run`，危险动作需要显式确认。
- 运行前审查生成的脚本；不要直接执行来源不明的 skill/脚本。
- 本工具按“原样”提供，不保证任何具体软件可自动化，也不承担数据损失责任。

### 已知限制

- `probe_windows.py` 只支持 Windows；其他平台请用等价工具（Accessibility API、AT-SPI、pynput 等）。
- Qt/Electron/OpenGL/游戏引擎的自绘控件，UIA 树可能为空；需要 win32/键盘/视觉兜底。
- `lint_skill.py` 的隐私扫描是启发式，不替代人工审查。
- 这是一套方法论和工具，不是“一键自动化任何软件”的魔法。

### 开发与测试

```bash
python -m unittest discover -s tests -v
python scripts/lint_skill.py . --strict
```

CI 在 Ubuntu 和 Windows、Python 3.10/3.12 上跑单元测试与严格 lint。

> 仓库目录名需要与 `SKILL.md` 的 `name` 一致（`automation-skill-builder`）；`lint_skill.py` 会检查这一点，CI 也在仓库根目录上跑。

### 贡献

欢迎 issue/PR。请保持通用、脱敏：不要提交客户数据、本机路径、许可证或内部命令名。新增脚本请附测试；改动行为请更新 `CHANGELOG.md`。

### 许可证

MIT，见 [LICENSE](LICENSE)。

---

## English

### What it is

Most desktop applications have no usable API. Naive GUI scripts break on DPI changes, localization, IME input, Qt custom controls, file locks, and leftover processes.

This skill turns **recon → choose a layer → build a walking skeleton → harden → package** into an executable workflow. It ships with three tools:

- `probe_windows.py` — read-only reconnaissance: windows, DPI, accessibility tree, screenshots, control search. It never clicks or types.
- `scaffold_skill.py` — generates a runnable skill skeleton (CLI, env check, selftest, shims).
- `lint_skill.py` — pre-delivery checks: frontmatter, referenced files, personal paths/secrets, Python/JSON validity.

It is not a pywinauto tutorial. It is a hard-won checklist distilled from a full CAD/CAE automation project.

### Install

```bash
git clone https://github.com/JiachengOuyang/automation-skill-builder.git ~/.claude/skills/automation-skill-builder
```

On Windows PowerShell:

```powershell
git clone https://github.com/JiachengOuyang/automation-skill-builder.git "$env:USERPROFILE\.claude\skills\automation-skill-builder"
```

Requirements: Python 3.10+. The probe's `windows/info/scaling` use the standard library; `dump/find` need `pywinauto`, `shot` needs `Pillow`. The probe is Windows-only; the rest is cross-platform.

```bash
pip install -r requirements.txt
```

### Quick start

```bash
# Recon a running app (read-only)
python scripts/probe_windows.py windows --filter "MyApp"
python scripts/probe_windows.py scaling --json
python scripts/probe_windows.py dump --title "MyApp" --out _work/controls.txt
python scripts/probe_windows.py shot --title "MyApp" --out _work/shot.png

# Generate a skill skeleton
python scripts/scaffold_skill.py --name my-app --app "My App" --out ../my-app

# Smoke test and lint
python ../my-app/scripts/my_app_cli.py env --json
python ../my-app/scripts/my_app_cli.py selftest
python scripts/lint_skill.py ../my-app
```

### How it works

Prefer the most deterministic layer:

1. **L0** configuration/files
2. **L1** native CLI / COM / plugin API / embedded scripting / macros
3. **L2** database, logs, artifacts (also used for verification)
4. **L3** GUI automation (UIA/win32/keyboard/clipboard/screenshots)

The best pattern is usually **L3 trigger + L2 verification**: click "Start", then wait for database rows or an output file — never trust a success dialog.

### Responsible use

Automate only software you are authorized to automate. Do not bypass licenses, DRM, logins, CAPTCHAs, or access controls. Keep source data read-only, back up before writes, and review generated scripts before running them. Provided as-is, without warranty.

### License

MIT. See [LICENSE](LICENSE).
