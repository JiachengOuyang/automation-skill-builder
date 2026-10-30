# 侦察手册：在写第一行自动化之前

目标：用最低成本回答三个问题——**它怎么启动、数据在哪、错误写在哪**。侦察阶段只读，不改配置、不点危险按钮、不写安装目录。

## 目录

1. 先拿到三样东西
2. 启动链
3. 数据与文件格式
4. 程序接口
5. 界面与工具包
6. 运行态与时间
7. 证据记录模板
8. 红旗清单

## 1. 先拿到三样东西

| 东西 | 为什么 | 怎么拿 |
|---|---|---|
| 安装目录 | 找 exe、DLL、帮助、示例、默认配置 | 快捷方式属性、注册表、`where`、进程路径 |
| 启动包装脚本 | 许可、环境变量、工作目录常在这里 | 读 `.bat`/`.cmd`/`.sh`/快捷方式目标 |
| 一份样例数据 | 没有样例就无法验证 | 向用户要副本，或复制示例工程 |

拿到后先做一件事：**原样启动一次、正常退出一次**，记录窗口标题、进程名、日志新增了哪些文件。

## 2. 启动链

### 2.1 安装与启动

- 安装目录里有什么：`bin/`、`lib/`、`plugins/`、`samples/`、`docs/`、`help/`、`config/`、`log/`。
- 快捷方式的 Target、Arguments、Start in 分别是什么。
- 是否有包装脚本：先完整读一遍，别急着运行。
- 是否有多个版本共存；自动化要绑定到具体版本/路径。
- 是否需要管理员权限；是否弹 UAC。
- 是否单实例：重复启动是激活已有窗口，还是报错，还是开新进程。

Windows 常用：

```powershell
# 进程与路径
Get-Process | Where-Object {$_.MainWindowTitle} | Select-Object Name,Id,MainWindowTitle,Path
# 快捷方式
$s = (New-Object -ComObject WScript.Shell).CreateShortcut("C:\path\to\app.lnk")
$s | Select-Object TargetPath,Arguments,WorkingDirectory
# 服务
Get-Service | Where-Object {$_.DisplayName -like "*APP*"}
# 计划任务/更新器
Get-ScheduledTask | Where-Object {$_.TaskName -like "*APP*"}
```

### 2.2 环境变量与许可

- 启动脚本里设置的变量：`set`、`export`、`PATH` 前置、`*_HOME`、`*_CONF`、`*_LICENSE*`。
- 许可类型：文件、环境变量、浮动许可服务器、加密狗、登录账号。**不要改全局变量**；用进程级环境或包装脚本。
- 许可失败的表现：启动即退、弹窗、日志里的固定错误码。
- 许可是否与机器绑定；换机器是否需要重新配置。

### 2.3 配置与日志

- 配置优先级：命令行 > 环境变量 > 用户配置 > 安装默认。找全再改。
- 配置格式：INI/XML/JSON/注册表/私有二进制。能否只改副本或用户级配置。
- 日志目录：安装目录、`%APPDATA%`、`%LOCALAPPDATA%`、`%PROGRAMDATA%`、临时目录。
- 日志是否按模块/日期分文件；错误对话框的真实原因是否只写日志。
- 日志是否会轮转/清空；自动化要在启动前记录文件列表和大小。
- **关键动作**：故意制造一个可恢复的小错误（例如打开不存在的文件），看日志里出现什么。这是排障的锚点。

### 2.4 单实例、更新器、后台进程

- 单实例用互斥量、锁文件还是端口；自动化前先检测。
- 自动更新会改变 UI/路径；自动化应固定版本或禁用更新。
- 是否有常驻后台进程/托盘程序；退出主窗口后是否还在。
- 子进程：计算/导出常由独立进程完成，父进程只是壳。

## 3. 数据与文件格式

### 3.1 识别格式

```bash
# Git Bash / Linux
file sample.dat
head -c 32 sample.dat | xxd
# PowerShell
Format-Hex -Path .\sample.dat -Count 64
```

常见特征：

| 特征 | 可能是 |
|---|---|
| `SQLite format 3` | SQLite 数据库 |
| `PK\x03\x04` | ZIP（可能是 docx/xlsx/自定义包） |
| `<?xml` | XML |
| `{\"` / `[` | JSON |
| 固定头部 + 二进制浮点 | 私有二进制；需要结构推断 |

### 3.2 数据库

- 先复制再打开；连接串只读（SQLite：`file:...?mode=ro` + `PRAGMA query_only=ON`）。
- 导出 schema：表名、字段、类型、主键、行数；**空表不要凭名字猜含义**。
- 找“结果表”：行数随时间/操作变化，字段含 result/calc/status/saved 等。
- 找“配置表”：版本、路径、许可、最近文件。
- 记录哪些表是缓存、哪些是真实数据；同会话缓存可能导致“已保存但读不到”。

### 3.3 文件型数据

- 让软件“另存为”到新文件，对比前后差异；这能暴露最小可写结构。
- 模板法：保留一份已知正确的样例，只改需要改的字段。
- 编码：UTF-8 / UTF-8 BOM / GBK / UTF-16；不要默认 UTF-8。
- 换行：CRLF/LF；文本导入对话框可能挑剔。
- 路径：有些旧软件不接受中文/空格/长路径；工作目录用 ASCII 短路径。

### 3.4 帮助与示例

- CHM/PDF/在线帮助里常有：命令行参数、脚本 API、文件格式、错误码。
- 安装目录的 `samples/`、`templates/`、`examples/` 是最好的输入素材。
- 帮助文档里的命令名要实测确认版本一致。

## 4. 程序接口

按顺序找，找到就停：

1. **CLI**：`app --help`、`app -h`、`app /?`、`app help`；看安装目录的 `bin/` 是否有 console 版。
2. **COM/ActiveX**：注册表 `HKCR\CLSID`、`HKCR\<ProgID>`；Python 用 `win32com.client`/`comtypes`。
3. **插件/扩展 API**：`plugins/`、`addins/`、SDK 目录、开发者文档。
4. **内嵌脚本**：脚本控制台、宏录制器、启动脚本、`init.js`/`startup.py`/`.tcl` 等。
5. **命令行开关**：`strings app.exe | grep -i -- "--"`（先确认许可证允许）。
6. **AutomationId/无障碍**：Inspect.exe、Accessibility Insights、`pywinauto` 的 `dump_tree`。

判断标准：**这个接口能不能在不显示界面的情况下完成核心动作，并留下可验证的产物？**

## 5. 界面与工具包

### 5.1 识别工具包

| 线索 | 工具包 |
|---|---|
| `Qt5Core.dll`/`Qt6Core.dll`，类名 `Qt5QWindowIcon` | Qt |
| `electron.exe`、`Chrome_WidgetWin_1` | Electron/Chromium |
| `PresentationFramework`、`HwndWrapper[...]` | WPF/.NET |
| `jvm.dll`、类名 `SunAwtFrame` | Java/Swing |
| 纯 `#32770`、标准 Button/Edit | Win32 原生 |
| 窗口截图正常但控件树为空 | 自绘/OpenGL/DirectX |

### 5.2 窗口与控件

```bash
python scripts/probe_windows.py windows --filter "关键词"
python scripts/probe_windows.py dump --title "主窗口标题" --out _work/controls.txt
python scripts/probe_windows.py shot --title "主窗口标题" --out _work/main.png
```

记录：

- 启动画面、主窗口、MDI 子窗口、浮动面板、模态对话框的标题和类名。
- 哪些控件有 Name/AutomationId，哪些只有类型。
- 菜单是原生菜单还是自绘；下拉是否能枚举。
- 表格/树的行矩形是否整行宽（拖放/点击要落在文字上）。
- 文件对话框是系统 `#32770` 还是自绘。

### 5.3 DPI 与多屏

- 系统缩放（100%/125%/150%/200%）、主屏分辨率、窗口是否跨屏。
- 截图是物理像素，鼠标 API 可能是逻辑像素；先拿一个已知控件校准。
- 换分辨率/缩放后哪些坐标会漂移；写进“校准清单”。

## 6. 运行态与时间

- 启动到可操作要多久；计算/导出要多久；有没有进度条/ Please wait 对话框。
- 进度 100% 后是否自动关闭；是否有“完成”按钮。
- 失败时是否弹模态框；模态框是否会阻塞主线程。
- 退出后子进程是否残留；临时文件/锁文件是否释放。
- 连续跑两次是否需要重启软件（缓存/单实例/许可）。

## 7. 证据记录模板

每个结论都按这个格式记，后面写文档直接复用：

```markdown
### [日期] [软件版本] [操作]
- 环境：Windows 版本 / 分辨率 / 缩放 / 是否管理员
- 输入：样例文件路径（副本）
- 操作：点了什么 / 跑了什么命令
- 结果：窗口标题 / 退出码 / 产物大小 / md5
- 日志：路径 + 关键行
- 截图：路径
- 结论：可用 / 不可用 / 需人工
```

## 8. 红旗清单

遇到这些要提前告诉用户“会变慢/会返工”：

- 没有日志，或错误只弹框不落盘。
- 全自绘 UI（Qt/OpenGL/游戏引擎），UIA 树为空。
- 加密狗/在线许可/机器绑定。
- 自动更新且不可关闭。
- 单实例 + 长计算 + 无进度可观测。
- 保存即覆盖、无副本机制。
- 项目文件加密/压缩且无文档。
- 需要人工登录/验证码/双因素。
- 软件明确禁止自动化（先确认授权与 EULA）。

侦察的终点不是“我都知道了”，而是**能画出启动链、数据流、验收点三张图**。画不出来就继续问，不要开始写点击脚本。
