# Windows GUI 自动化工程手册

只在 L0–L2 覆盖不到时使用。核心思路：**GUI 只负责扳机，结果用数据验收；定位靠结构，坐标只兜底。**

## 目录

1. 先判断工具包
2. 窗口身份：标题不够
3. 定位级联
4. 焦点与前台
5. 输入：剪贴板优先
6. 等待：轮询，不 sleep
7. 菜单、对话框与 Qt 的坑
8. 拖放
9. DPI 与缩放
10. 截图与视觉匹配
11. 进程生命周期与日志
12. 失败现场采集
13. 检查清单

## 1. 先判断工具包

| 线索 | 工具包 | 影响 |
|---|---|---|
| `Qt5Core.dll`/`Qt6Core.dll`，类名 `Qt5QWindowIcon` | Qt | 自绘控件多，UIA 常为空 |
| `Chrome_WidgetWin_1`、`electron.exe` | Electron | 类似浏览器，UIA 可能可用但层级深 |
| `HwndWrapper[...]`、`PresentationFramework` | WPF | UIA 通常较好 |
| `SunAwtFrame`、`jvm.dll` | Java | UIA 支持有限 |
| `#32770` + 标准 Button/Edit | Win32 | 最好自动化 |
| 截图正常、控件树为空 | 自绘/OpenGL/DirectX | 只能键盘/坐标/视觉 |

用 `probe_windows.py dump` 看控件树；如果只有顶层窗口没有子控件，基本可以判定为自绘。

## 2. 窗口身份：标题不够

标题会随文档名、语言、状态变化。优先用 **进程 + 窗口类 + 标题正则** 的组合。

```python
from pywinauto import Desktop

desk = Desktop(backend="uia")
win = desk.window(title_re=r".*MyApp.*", class_name="Qt5QWindowIcon")
```

更稳的做法是从进程 PID 反查窗口：

```python
import subprocess, json

# 用 probe_windows.py windows --json 拿到 pid/title/class/hwnd
```

- 启动后先等主窗口出现，再操作；不要假设 `Popen` 返回就可点。
- 记录 splash/主窗口/对话框的不同标题。
- 单实例软件：第二次启动可能只是激活旧窗口；先检测再启动。

## 3. 定位级联

从稳到脆，逐级降级；每降一级都要在日志里写明原因。

1. **AutomationId / Name**（最稳）
   ```python
   btn = win.child_window(auto_id="calculateButton", control_type="Button")
   btn.invoke()          # UIA invoke，尽量不用鼠标
   # 或 btn.click_input()
   ```
2. **控件类型 + 邻近标签**：找同一行的 Label，再找它右侧/下方的 Edit。
   ```python
   label = win.child_window(title="Output file", control_type="Text")
   edit = win.child_window(control_type="Edit", found_index=0)  # 需结合矩形筛选
   ```
3. **行内文字点**：表格/树的整行矩形中心往往是空白，点击要落在文字起点附近。
   ```python
   r = item.rectangle()
   pyautogui.click(r.left + 18, r.top + r.height() // 2)
   ```
4. **屏幕坐标**：必须有校准依据和 WARN 日志；换分辨率/DPI 后重测。
5. **模板匹配**：自绘控件找不到时用；阈值 0.8 起，多尺度；失败回退坐标并告警。

辅助工具：

```python
win.dump_tree()                 # 整棵树
win.descendants()               # 遍历
win.print_control_identifiers() # 可读清单
ctrl.draw_outline()             # 在屏幕上画出“脚本以为的矩形”
```

`draw_outline()` 是最快的定位自检：框正好套住控件 = 坐标对；框偏出约 1.5 倍 = DPI 问题；框住别的窗口 = 句柄/矩形过期。比看日志快。

点击前还可以直接问 Windows“这个点归谁”：

```python
import ctypes
from ctypes import wintypes
u = ctypes.windll.user32
u.WindowFromPoint.restype = ctypes.c_void_p
pt = wintypes.POINT(x, y)
h = u.WindowFromPoint(pt)
root = u.GetAncestor(h, 2)      # GA_ROOT
assert root == hwnd, f"该点属于 {root:#x}，会被别的窗口接走"
```

注意：`click_input(coords=...)` 的 `coords` 是**控件客户区坐标**，不是屏幕坐标；把屏幕坐标塞进去是很常见的二次偏移来源。UIA 与 win32 的矩形还可能差 7–8px（DWM 不可见边框），这不是 DPI 问题，混用两个 backend 时要统一口径。

## 4. 焦点与前台

很多点击失败不是控件找不到，而是目标窗口不在前台。

```python
import ctypes
u = ctypes.windll.user32

def foreground_is(hwnd: int) -> bool:
    return u.GetForegroundWindow() == hwnd

def force_foreground(hwnd: int) -> None:
    fg = u.GetForegroundWindow()
    fg_tid = u.GetWindowThreadProcessId(fg, None)
    tgt_tid = u.GetWindowThreadProcessId(hwnd, None)
    u.AttachThreadInput(fg_tid, tgt_tid, True)
    u.SetForegroundWindow(hwnd)
    u.AttachThreadInput(fg_tid, tgt_tid, False)
```

规则：

- 点击前 `GetForegroundWindow()` 校验；不是目标就先聚焦，再校验一次。
- `SetForegroundWindow` 受前台锁限制会**静默失败**：检查返回值。`GetForegroundWindow()` 也可能返回 0，要兜底到桌面窗口。
- `AttachThreadInput` 必须在 `finally` 里解绑；原前台窗口也要还原。
- 聚焦校验失败就中止，不要“再点一次”——盲点比报错更危险。
- 不要用窗口标题找“终端”；按进程祖先链找启动它的控制台/终端。
- 操作完把焦点还给用户原来的窗口（至少还给终端）。
- 只聚焦必须聚焦的窗口；弹出菜单里点选项不要重新聚焦主窗（会关掉菜单）。

## 5. 输入：剪贴板优先

逐字键入在中文输入法下会变成乱码（文件名、路径、备注尤其明显）。

```python
import pyperclip
from pywinauto.keyboard import send_keys

def set_text_safe(ctrl, text: str) -> None:
    ctrl.click_input()
    send_keys("^a")
    pyperclip.copy(text)
    send_keys("^v")
    # 回读校验：不同控件读取方式不同，至少检查文本非空/前缀匹配
```

- Qt 的某些 Edit 不支持 `set_edit_text`/ValuePattern；用 click + Ctrl+A + 剪贴板 + Tab。
- `send_keys` 里 `{ } + ^ % ~ ( )` 是特殊字符，要转义；路径/文件名优先走剪贴板，绕开转义和输入法。
- 路径输入优先走系统文件对话框的“文件名”框，避开自绘路径控件。
- 输入后立即回读；不一致就停，不要继续点下一步。
- 密码/许可证不要写进日志。

## 6. 等待：轮询，不 sleep

```python
import time

def wait_until(pred, timeout=30.0, interval=0.25, what="condition"):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        try:
            value = pred()
            if value:
                return value
        except Exception as exc:   # 控件暂不存在是正常状态
            last = exc
        time.sleep(interval)
    raise TimeoutError(f"{what} 超时（{timeout}s）: {last}")
```

pywinauto 自带 `win.wait("ready"/"visible"/"enabled", timeout=...)`，包装器稳定时优先用；需要等业务状态（DB 行数、文件大小）时用自己的 `wait_until`。

可轮询的信号，按可靠性排序：

1. 数据库结果行数/状态字段。
2. 输出文件存在且大小连续两次不变。
3. 日志出现完成关键字。
4. 进度对话框消失/Close 可用。
5. 窗口标题变化。
6. 控件 enabled/visible。

不要用固定 `sleep(5)` 猜计算时间；长任务可能有 1–20 分钟。

## 7. 菜单、对话框与 Qt 的坑

- 原生菜单：`win.menu_select("File->Save As")` 通常可用。
- Qt 自绘菜单：UIA 可能只暴露一个 Custom 控件；用键盘：
  ```python
  send_keys("%f")          # Alt+F
  send_keys("{DOWN 6}{RIGHT}{DOWN 3}{ENTER}")
  ```
  把按键序列写进文档，换版本要重录。
- 文件对话框：
  - 系统 `#32770`：可直接找 Edit + “打开/保存”按钮。
  - Qt 自绘：优先用文件名输入框 + Enter；路径用剪贴板粘贴。
- 保存对话框文件名常为空；显式填**唯一文件名**，避免覆盖确认。
- 覆盖确认/警告的标题不在常见集合里；关闭逻辑要按按钮文本/控件类型处理，不能只匹配标题。
- 进度条 100% 不自动关：仍要轮询 Close/OK/Finish。
- 模态框会阻塞主窗口；先处理模态框再继续。
- 语言/主题会影响按钮文字；用 control_type/auto_id，或维护多语言标签表。

## 8. 拖放

```python
pyautogui.moveTo(src_x, src_y, duration=0.2)
pyautogui.mouseDown()
pyautogui.moveTo(dst_x, dst_y, duration=0.5)
pyautogui.mouseUp()
```

- 源/目标都落在**文字或图标**上，不要落在整行矩形中心。
- 拖之前确认源和目标在同一屏、可见、未被遮挡。
- 拖完用 L2 验证（树结构/数据库变化），不要只看界面。
- 某些控件需要 `drag_and_drop` 或 UIA 的 DragPattern；pyautogui 失败时试 API。

## 9. DPI 与缩放

150% 下的坐标偏移几乎都来自 **DPI awareness**，而不是控件定位。规则：

1. **先查进程 awareness，再设，设完断言**。`GetProcessDpiAwareness(None, byref(v))` 返回 0/1/2；不是 2 就设置 PMv2。重复设置可能返回 `0x80070005`（已经设过），不是致命错误。
2. **必须在创建窗口/导入 pyautogui 之前设**。设成 per-monitor 后，UIA 的 `rectangle()`、`ImageGrab`、`pyautogui` 才在同一物理像素空间。
3. **不要假设 pyautogui 自动感知**：unaware 进程里 `GetSystemMetrics`/`GetCursorPos`/pyautogui 看到的是逻辑像素，而 `ImageGrab` 可能是物理像素；`locateOnScreen` 在 150% 下失效通常就是这个原因。
4. **校准断言**：截图 bbox 的宽高与控件矩形宽高差 ≤2px；否则 WARN 并记录 awareness/dpi/scale/分辨率，不要继续批量点。
5. **跨屏拖动**会触发 `WM_DPICHANGED`，缓存的矩形全部作废；每次点击前重算。
6. **UIA 与 win32 矩形可能差 7–8px**（DWM 不可见边框），这不是 DPI；混用 backend 时统一口径。
7. 多屏：`ImageGrab.grab(all_screens=True)`；窗口可能跨屏，矩形用虚拟屏坐标。
8. 把分辨率、缩放、窗口是否最大化写进配置和 selftest；换机器先跑校准。

```python
import ctypes
u = ctypes.windll.user32
v = ctypes.c_int()
ctypes.windll.shcore.GetProcessDpiAwareness(None, ctypes.byref(v))
if v.value != 2:
    try:
        u.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # PMv2
    except (AttributeError, OSError):
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
# 重新查询 v 并断言 == 2；再 assert 截图尺寸 ≈ 控件矩形尺寸（±2px）
```

## 10. 截图与视觉匹配

```python
from PIL import ImageGrab
img = ImageGrab.grab(bbox=(l, t, r, b), all_screens=True)
img.save("_work/shot.png")
```

- 被遮挡的窗口：用 `PrintWindow`（ctypes）抓窗口自身；某些 GPU 渲染窗口仍可能黑屏。
- 模板匹配：
  ```python
  import cv2
  res = cv2.matchTemplate(gray, tpl, cv2.TM_CCOEFF_NORMED)
  _, score, _, loc = cv2.minMaxLoc(res)
  if score >= 0.8:
      ...
  ```
- 模板要来自**同版本、同主题、同缩放**；升级后重新截。
- 视觉是最后手段；命中后仍要用 L2 验证业务结果。

## 11. 进程生命周期与日志

```python
import subprocess
log = open("_work/logs/app.log", "ab")
proc = subprocess.Popen(
    cmd,
    stdout=log,
    stderr=subprocess.STDOUT,
    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
)
```

- **不要把子进程 stdout 接到管道再 `| tail`**：父进程可能一直等管道关闭而挂住；重定向到文件。
- 启动后等主窗口/日志关键字，不要只看 PID。
- 退出顺序：友好关闭 → 处理保存/确认对话框 → 等进程退出 → terminate → kill。
- `try/finally` 里清理：关进程、关文件句柄、删临时文件、释放锁。
- 退出后检查残留进程和锁文件；单实例软件残留会导致下次启动失败。

## 12. 失败现场采集

任何 GUI 异常都保存一套“现场”，否则无法复盘：

```text
_work/failures/<timestamp>/
  screenshot.png
  controls.txt        # dump_tree
  windows.json        # 当前所有窗口
  foreground.txt      # 前台窗口标题/类/PID
  app.log             # 最后 N 行
  step.txt            # 正在执行的步骤/参数
```

采集本身要包在 try/except 里，不能因为采集失败掩盖原始错误。

## 13. 检查清单

- [ ] 已确认工具包和控件可访问性
- [ ] 窗口用进程/类/标题正则定位，不只靠标题
- [ ] 定位按 AutomationId → 标签 → 行内点 → 坐标 → 模板降级，并记录降级原因
- [ ] 每次点击前校验前台窗口
- [ ] 输入走剪贴板，输入后回读
- [ ] 所有等待都是轮询，有超时和明确错误
- [ ] 菜单/对话框有键盘兜底，按键序列已记录
- [ ] 保存用唯一文件名，处理覆盖确认
- [ ] DPI/分辨率已校准，坐标有告警
- [ ] 子进程日志重定向，退出有 finally 清理
- [ ] 失败现场三件套：截图 + 控件树 + 日志
- [ ] 每个 GUI 动作后都有 L2 验收
