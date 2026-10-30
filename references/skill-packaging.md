# 把自动化封装成 skill

目标：让**未来的自己或另一个 Claude 会话**在没有上下文的情况下，照着文档就能用、能排障、能扩展。

## 目录

1. 目录结构
2. SKILL.md：frontmatter
3. SKILL.md：正文结构
4. 决策树怎么写
5. references 怎么拆
6. scripts 约定
7. 环境、配置与换机器
8. evals
9. 脱敏与公开/私有分仓
10. 安装、升级与校验

## 1. 目录结构

```text
<skill-name>/
├── SKILL.md                 # 必需；触发 + 工作流 + 决策树
├── references/              # 按需加载的长文档
│   ├── installation.md
│   ├── troubleshooting.md
│   ├── database.md
│   ├── modules/
│   └── portability.md
├── scripts/                 # 可执行代码
│   ├── <app>                # bash 壳
│   ├── <app>.cmd            # Windows 壳
│   ├── <app>_cli.py         # 唯一入口
│   ├── <app>_env.py
│   ├── <app>_selftest.py
│   └── <app>_<domain>.py
├── evals/evals.json
├── config.toml.example
└── RESTORE.md
```

原则：

- **SKILL.md < 500 行**；超过就把细节下沉。
- 脚本可以无限长，因为执行时不必全部读进上下文。
- 参考文档按“什么时候需要”拆，不按“作者写起来方便”拆。

## 2. SKILL.md：frontmatter

```yaml
---
name: app-name
description: 用一句话说清“做什么 + 什么时候用”。把产品名、别名、模块名、文件后缀、用户会说的动词都列进去；最后加一句“即使用户没有点名也触发”。不要只写“帮助使用 X”。
---
```

好的 description 是触发词总表，不是简介。它要覆盖：

- 产品名/别名/旧名。
- 模块/子功能/文件扩展名。
- 用户会说的任务动词：批量、导出、导入、计算、建模、出图、排障、启动。
- 相邻概念：RPA、宏、脚本、自动化、没有 API、每次都要点。
- 反触发边界：纯网页、纯 CLI、手机 App 不适用（避免误触发）。

## 3. SKILL.md：正文结构

推荐顺序（按“出错代价”排序）：

1. **红线**：绝对不能做的事（写原库、改全局变量、硬编码坐标、分享敏感信息）。
2. **自检**：一条 `env check` / `selftest` 命令，告诉读者先跑什么。
3. **决策树**：用户想做什么 → 用哪条命令/哪一层。
4. **按主题的命令速查**：每节 3–10 条，带最小示例。
5. **已实测结论**：日期、版本、数值、md5；区分“已打通/未打通/不要走”。
6. **输出约定**：工作目录、命名、编码。
7. **参考文档索引**。
8. **依赖与安装**。
9. **已知限制 / 待核实**。

写作风格：

- 命令用代码块，路径用占位符（`<db>`、`<out>`），不要写死本机路径。
- 每条结论带证据（实测日期/字节数/误差），读者能判断可信度。
- 明确写“不要走的路”，比只写“正确做法”更省时间。
- 用“现象 | 原因 | 处理”三列表写排障。
- 不要堆砌形容词；写可执行的判断条件。

## 4. 决策树怎么写

一张表覆盖 80% 日常任务：

```markdown
| 用户想做什么 | 用什么 |
|---|---|
| 打开软件 | `app launch <module>` |
| 查数据 | `app db query ...`（只读） |
| 批量计算 | `app calc ... --copy` |
| 排障 | `app journal summary --latest` |
| 只能点界面 | `app gui ...`（先截图/控件树） |
```

规则：

- 左列用**用户的话**，不是内部术语。
- 右列给**可直接复制的命令**。
- 长流程在右列写“见第 N 节”，不要让表格变成教程。
- 表下面按主题展开；每个主题只保留最常用命令。

## 5. references 怎么拆

三类，不要混：

| 类型 | 内容 | 例子 |
|---|---|---|
| 横切主题 | 安装、许可、日志、数据库、可移植性 | `installation.md`、`troubleshooting.md` |
| 模块文档 | 每个模块/子系统的流程与坑 | `modules/calc.md`、`modules/draw.md` |
| 命令速查 | 大量命令的分组索引 | `modules/calc-commands.md` |

写法：

- 每篇 H1 起；>300 行加 `## 目录`。
- 开头一句“什么时候读这篇”。
- 关键结论带实测日期/版本/环境。
- 排障用三列表；流程用编号步骤；命令用代码块。
- 文末写“已知限制/未验证”，不要把猜测写成事实。
- 交叉引用用相对路径；确保 `lint_skill.py` 能检查到文件存在。

## 6. scripts 约定

### 6.1 唯一入口 + 分发

```python
# app_cli.py
COMMANDS = {
    "env": "app_env",
    "selftest": "app_selftest",
    "db": "app_db",
    "calc": "app_calc",
}

def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print_help(); return 0
    name = argv[0]
    mod = COMMANDS.get(name)
    if not mod:
        print(f"unknown command: {name}", file=sys.stderr); return 2
    return importlib.import_module(mod).main(argv[1:])
```

- 每个模块实现 `main(argv) -> int`。
- 未知命令退出 2；缺依赖退出 3。
- 不要在每个领域脚本里重复窗口/等待/DB 逻辑；抽到原语层。

### 6.2 平台壳

`app`（bash）和 `app.cmd` 只做一件事：找到解释器并转发。

```bash
#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PY="$HERE/../.venv/Scripts/python.exe"
[ -x "$PY" ] || PY="$HERE/../../.venv/Scripts/python.exe"
[ -x "$PY" ] || PY="python"
exec "$PY" -I "$HERE/app_cli.py" "$@"
```

- 设置 `PYTHONUTF8=1`。
- 用 `-I` 隔离用户 site-packages（可选，但能减少环境差异）。
- 不要把业务逻辑写进壳。

### 6.3 通用参数

| 参数 | 含义 |
|---|---|
| `--dry-run` | 只打印计划，不执行 |
| `--json` | 机器可读输出 |
| `--timeout N` | 单步超时 |
| `--copy` | 复制到工作目录再操作（默认推荐） |
| `--in-place` | 显式允许改原件（危险） |
| `--yes` | 确认 GUI/危险动作 |
| `--keep-open` | 失败时保留窗口便于排查 |
| `--replace` | 允许覆盖已有产物 |

### 6.4 输出

- 默认人类可读：`key : value` + 简短结论。
- `--json`：`{"ok": true, "data": {...}}`；错误 `{"ok": false, "code": N, "error": "..."}`。
- 错误写 stderr；不要用 print 混在 JSON 里。
- 日志写 `_app_work/logs/`，控制台只打摘要。

## 7. 环境、配置与换机器

三层优先级，必须一致：

```text
环境变量  >  config.toml  >  内置默认值
```

- 配置搜索顺序：`APP_SKILL_CONFIG` → 当前目录 → skill 根。
- `app env check` 打印最终生效值、来源、是否 OK。
- `app setup`：自动探测 → 交互确认 → 写配置；`--check` 只读；`--reset` 先备份；`--yes` 非交互。
- `RESTORE.md` 写四种场景：新机器、已配置机器、升级、回滚。
- 换机器先 `setup`/`env check`，再跑 `selftest`。
- 不把 `config.toml`、许可证、项目数据提交到仓库。

## 8. evals

`evals/evals.json` 用真实用户会说的话，不要写“测试技能是否工作”。

```json
{
  "skill_name": "app-name",
  "evals": [
    {
      "id": 1,
      "prompt": "帮我把这个软件每天导出的报表批量转成 CSV，文件夹在 ...",
      "expected_output": "先侦察文件格式/是否有 CLI，给出最小闭环方案，包含只读/副本和验收",
      "files": []
    }
  ]
}
```

3–5 条即可，覆盖：

- 典型任务（最常见的那条）。
- 边界任务（只能 GUI/没有样例）。
- 排障任务（启动失败/结果不对）。
- 反例（纯网页/纯 CLI，不应触发本技能）。

## 9. 脱敏与公开/私有分仓

分享/发布前逐项扫描：

| 项 | 检查 |
|---|---|
| 本机路径 | `C:\Users\<name>`、`D:\...`、`/home/<name>` |
| 用户名/主机名 | `%USERNAME%`、`hostname`、邮箱 |
| 许可证/密钥 | `LICENSE`、`api_key`、`password`、token |
| 客户/项目数据 | 项目号、合同号、客户名、真实数值 |
| 内部命令/逆向细节 | 只写“GUI 流程/读库”，不写内部命令名 |
| 截图 | 打码路径/用户名/项目名 |

分仓策略：

- **本机版**：保留本机路径、内部适配器、私有实现。日常开发用。
- **私有版**：脱敏，但保留内部实现。仅本人。
- **公开版**：只保留通用实现，删除逆向/内部细节；换机器用 `setup`。

同步规则写清楚：不自动同步；明确说“更新公开版”才动；公开版更新前先列出依赖检查项。

## 10. 安装、升级与校验

- 用户级：`~/.claude/skills/<name>/`，所有项目可用。
- 项目级：`<project>/.claude/skills/<name>/`，只在该项目触发。
- 安装后跑：`python scripts/lint_skill.py <skill-dir>` + skill 自带 `selftest`。
- 升级：替换代码，保留 `config.toml`；跑回归；在 `progress`/`CHANGELOG` 记版本和日期。
- 回滚：保留上一版备份；`RESTORE.md` 写回滚步骤。

## 11. 交付前自检

```bash
python scripts/lint_skill.py <skill-dir> --strict
python <skill-dir>/scripts/<app>_cli.py env check
python <skill-dir>/scripts/<app>_cli.py selftest
```

- frontmatter 的 name 与目录名一致。
- 所有 `references/...`、`scripts/...` 引用存在。
- 没有 TODO/FIXME 漏在正文。
- 脚本能编译，JSON 能解析。
- 没有本机路径/用户名/密钥。
