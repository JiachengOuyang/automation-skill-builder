#!/usr/bin/env python3
"""probe_windows.py — read-only Windows UI reconnaissance.

This script never clicks, types, or changes anything. It only enumerates
windows, reports DPI/scaling, dumps accessibility trees, and takes screenshots.

Subcommands:
  windows   list top-level windows (title/class/pid/rect/visible)
  info      details for one window (rect, DPI, monitor, process path)
  scaling   screen metrics, system DPI, per-monitor DPI
  dump      dump the control tree (pywinauto; uia or win32 backend)
  find      find controls by name/type regex and print their rectangles
  shot      save a screenshot of a window (or the full screen)

Exit codes: 0 ok, 1 runtime error, 2 usage, 3 missing dependency/platform.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
else:  # pragma: no cover - the skill targets Windows first
    ctypes = None  # type: ignore
    wintypes = None  # type: ignore
    user32 = None  # type: ignore
    kernel32 = None  # type: ignore
    gdi32 = None  # type: ignore


# --------------------------------------------------------------------------
# Win32 helpers
# --------------------------------------------------------------------------

def _configure_stdio() -> None:
    """Never crash on a character the console codec cannot encode."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _set_dpi_awareness() -> None:
    """Make coordinates physical pixels; otherwise Windows virtualizes metrics."""
    if not IS_WINDOWS:
        return
    try:
        fn = user32.SetProcessDpiAwarenessContext
        fn.argtypes = [wintypes.HANDLE]
        fn.restype = wintypes.BOOL
        if fn(wintypes.HANDLE(-4)):  # PER_MONITOR_AWARE_V2
            return
    except Exception:
        pass
    try:
        shcore = ctypes.WinDLL("shcore", use_last_error=True)
        shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
    except Exception:
        pass


_configure_stdio()
_set_dpi_awareness()


def _declare_win32() -> None:
    """Set prototypes once. Without argtypes, 64-bit handles get truncated."""
    if not IS_WINDOWS:
        return
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetClassNameW.restype = ctypes.c_int
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetWindowRect.restype = wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND, ctypes.POINTER(wintypes.DWORD)
    ]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.IsIconic.restype = wintypes.BOOL
    user32.GetDC.argtypes = [wintypes.HWND]
    user32.GetDC.restype = wintypes.HDC
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    user32.ReleaseDC.restype = ctypes.c_int
    gdi32.GetDeviceCaps.argtypes = [wintypes.HDC, ctypes.c_int]
    gdi32.GetDeviceCaps.restype = ctypes.c_int
    user32.GetSystemMetrics.argtypes = [ctypes.c_int]
    user32.GetSystemMetrics.restype = ctypes.c_int
    kernel32.OpenProcess.argtypes = [
        wintypes.DWORD, wintypes.BOOL, wintypes.DWORD
    ]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    for name in ("GetDpiForWindow", "GetDpiForSystem"):
        fn = getattr(user32, name, None)
        if fn is not None:
            fn.restype = wintypes.UINT
            if name == "GetDpiForWindow":
                fn.argtypes = [wintypes.HWND]


_declare_win32()


def require_windows() -> None:
    if not IS_WINDOWS:
        print("error: this script currently supports Windows only", file=sys.stderr)
        raise SystemExit(3)


@dataclass
class WindowInfo:
    hwnd: int
    title: str
    class_name: str
    pid: int
    process: str
    rect: list[int]
    width: int
    height: int
    visible: bool
    minimized: bool
    dpi: int | None = None
    scale: float | None = None


def _process_name(pid: int) -> str:
    if not pid:
        return ""
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(len(buf))
        ok = kernel32.QueryFullProcessImageNameW(
            handle, 0, buf, ctypes.byref(size)
        )
        return buf.value if ok else ""
    finally:
        kernel32.CloseHandle(handle)


def _dpi_for_window(hwnd: int) -> int | None:
    fn = getattr(user32, "GetDpiForWindow", None)
    if fn is None:
        return None
    try:
        fn.argtypes = [wintypes.HWND]
        fn.restype = wintypes.UINT
        return int(fn(hwnd)) or None
    except Exception:
        return None


def _system_dpi() -> int:
    fn = getattr(user32, "GetDpiForSystem", None)
    if fn is not None:
        try:
            fn.restype = wintypes.UINT
            value = int(fn())
            if value:
                return value
        except Exception:
            pass
    hdc = user32.GetDC(0)
    try:
        LOGPIXELSX = 88
        return int(gdi32.GetDeviceCaps(hdc, LOGPIXELSX))
    finally:
        user32.ReleaseDC(0, hdc)


def _scale(dpi: int | None) -> float | None:
    return round(dpi / 96.0, 3) if dpi else None


def _enum_windows() -> list[WindowInfo]:
    require_windows()
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    results: list[WindowInfo] = []

    def callback(hwnd: int, _lparam: int) -> bool:
        length = user32.GetWindowTextLengthW(hwnd)
        title_buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title_buf, length + 1)
        class_buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, class_buf, 256)
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        dpi = _dpi_for_window(hwnd)
        results.append(
            WindowInfo(
                hwnd=int(hwnd),
                title=title_buf.value,
                class_name=class_buf.value,
                pid=int(pid.value),
                process=_process_name(int(pid.value)),
                rect=[rect.left, rect.top, rect.right, rect.bottom],
                width=rect.right - rect.left,
                height=rect.bottom - rect.top,
                visible=bool(user32.IsWindowVisible(hwnd)),
                minimized=bool(user32.IsIconic(hwnd)),
                dpi=dpi,
                scale=_scale(dpi),
            )
        )
        return True

    user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    user32.EnumWindows(WNDENUMPROC(callback), 0)
    return results


def _resolve(title_re: str | None, hwnd: int | None) -> WindowInfo:
    windows = _enum_windows()
    if hwnd:
        for w in windows:
            if w.hwnd == hwnd:
                return w
        raise RuntimeError(f"window handle not found: {hwnd}")
    if not title_re:
        raise RuntimeError("pass --title (regex) or --hwnd")
    rx = re.compile(title_re, re.IGNORECASE)
    matches = [
        w for w in windows
        if rx.search(w.title) or rx.search(w.process) or rx.search(w.class_name)
    ]
    if not matches:
        raise RuntimeError(f"no window matches title/process regex: {title_re}")
    # Prefer a visible, non-minimized window; otherwise show candidates.
    visible = [w for w in matches if w.visible and not w.minimized]
    pool = visible or [w for w in matches if w.visible] or matches
    if len(pool) > 1:
        candidates = "\n".join(
            f"  hwnd={w.hwnd} pid={w.pid} class={w.class_name!r} title={w.title!r}"
            for w in pool[:10]
        )
        raise RuntimeError(
            f"ambiguous window regex {title_re!r}; pass --hwnd. Candidates:\n{candidates}"
        )
    return pool[0]


# --------------------------------------------------------------------------
# Subcommands
# --------------------------------------------------------------------------

def cmd_windows(args: argparse.Namespace) -> int:
    require_windows()
    windows = _enum_windows()
    if not args.all:
        windows = [w for w in windows if w.visible]
    if args.filter:
        rx = re.compile(args.filter, re.IGNORECASE)
        windows = [
            w
            for w in windows
            if rx.search(w.title) or rx.search(w.class_name) or rx.search(w.process)
        ]
    windows.sort(key=lambda w: (w.process.lower(), w.title.lower(), w.hwnd))
    if args.json:
        print(json.dumps([asdict(w) for w in windows], ensure_ascii=True, indent=2))
        return 0
    print(f"# {len(windows)} window(s)")
    print(f"{'HWND':>10}  {'PID':>6}  {'CLASS':<28} {'TITLE':<50} {'RECT'}")
    for w in windows:
        flags = "" if not w.minimized else " [min]"
        print(
            f"{w.hwnd:>10}  {w.pid:>6}  {w.class_name[:28]:<28} "
            f"{w.title[:50]:<50} {w.rect}{flags}"
        )
    return 0


def cmd_info(args: argparse.Namespace) -> int:
    require_windows()
    w = _resolve(args.title, args.hwnd)
    info = asdict(w)
    info["process_path"] = _process_name(w.pid)
    info["system_dpi"] = _system_dpi()
    info["system_scale"] = _scale(info["system_dpi"])
    if args.json:
        print(json.dumps(info, ensure_ascii=True, indent=2))
        return 0
    for key, value in info.items():
        print(f"{key:14}: {value}")
    return 0


def cmd_scaling(args: argparse.Namespace) -> int:
    require_windows()
    system_dpi = _system_dpi()
    screen_w = user32.GetSystemMetrics(0)
    screen_h = user32.GetSystemMetrics(1)
    virtual_w = user32.GetSystemMetrics(78)   # SM_CXVIRTUALSCREEN
    virtual_h = user32.GetSystemMetrics(79)   # SM_CYVIRTUALSCREEN

    monitors: list[dict[str, Any]] = []
    try:
        MONITORENUMPROC = ctypes.WINFUNCTYPE(
            wintypes.BOOL, wintypes.HANDLE, wintypes.HDC,
            ctypes.POINTER(wintypes.RECT), wintypes.LPARAM
        )

        class MONITORINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD),
            ]

        def cb(hmon: int, _hdc: int, _rect: Any, _data: int) -> bool:
            mi = MONITORINFO()
            mi.cbSize = ctypes.sizeof(MONITORINFO)
            if user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
                dpi_x = wintypes.UINT(0)
                dpi_y = wintypes.UINT(0)
                dpi = None
                try:
                    shcore = ctypes.WinDLL("shcore", use_last_error=True)
                    shcore.GetDpiForMonitor.argtypes = [
                        wintypes.HANDLE,
                        ctypes.c_int,
                        ctypes.POINTER(wintypes.UINT),
                        ctypes.POINTER(wintypes.UINT),
                    ]
                    shcore.GetDpiForMonitor(
                        hmon, 0, ctypes.byref(dpi_x), ctypes.byref(dpi_y)
                    )
                    dpi = int(dpi_x.value) or None
                except Exception:
                    pass
                r = mi.rcMonitor
                monitors.append(
                    {
                        "handle": int(hmon),
                        "primary": bool(mi.dwFlags & 1),
                        "rect": [r.left, r.top, r.right, r.bottom],
                        "work": [mi.rcWork.left, mi.rcWork.top,
                                 mi.rcWork.right, mi.rcWork.bottom],
                        "dpi": dpi,
                        "scale": _scale(dpi or system_dpi),
                    }
                )
            return True

        user32.EnumDisplayMonitors.argtypes = [
            wintypes.HDC, ctypes.c_void_p, MONITORENUMPROC, wintypes.LPARAM
        ]
        user32.EnumDisplayMonitors.restype = wintypes.BOOL
        user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
        user32.GetMonitorInfoW.restype = wintypes.BOOL
        user32.EnumDisplayMonitors(None, None, MONITORENUMPROC(cb), 0)
    except Exception as exc:  # non-fatal: still report system metrics
        monitors.append({"error": str(exc)})

    data = {
        "system_dpi": system_dpi,
        "system_scale": _scale(system_dpi),
        "screen": [screen_w, screen_h],
        "virtual_screen": [virtual_w, virtual_h],
        "monitors": monitors,
    }
    if args.json:
        print(json.dumps(data, ensure_ascii=True, indent=2))
        return 0
    print(f"system_dpi      : {data['system_dpi']} (scale {data['system_scale']})")
    print(f"screen          : {screen_w} x {screen_h}")
    print(f"virtual_screen  : {virtual_w} x {virtual_h}")
    for i, m in enumerate(monitors):
        print(f"monitor[{i}]      : {m}")
    return 0


def _connect_window(title: str | None, hwnd: int | None, backend: str) -> Any:
    try:
        from pywinauto import Desktop
    except ImportError as exc:  # pragma: no cover
        print(
            "error: pywinauto is required for dump/find; "
            "install it in the skill venv",
            file=sys.stderr,
        )
        raise SystemExit(3) from exc
    w = _resolve(title, hwnd)
    return Desktop(backend=backend).window(handle=w.hwnd), w


def cmd_dump(args: argparse.Namespace) -> int:
    require_windows()
    spec, w = _connect_window(args.title, args.hwnd, args.backend)
    # Capture first: pywinauto's filename= path uses the locale codec, which
    # can fail on titles containing characters outside the ANSI codepage.
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        spec.print_control_identifiers(depth=args.depth)
    text = buf.getvalue()

    print(f"target : hwnd={w.hwnd} pid={w.pid} title={w.title!r} class={w.class_name!r}")
    print(f"backend: {args.backend}")
    if args.out:
        out = os.path.abspath(args.out)
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        with open(out, "w", encoding="utf-8", errors="replace") as fh:
            fh.write(text)
        print(f"output : {out}")
        print(f"size   : {os.path.getsize(out)} bytes")
    else:
        print(text)
    return 0


def _control_dict(ctrl: Any) -> dict[str, Any]:
    def safe(fn: Any, default: Any = "") -> Any:
        try:
            return fn()
        except Exception:
            return default

    rect = safe(lambda: ctrl.rectangle(), None)
    element = getattr(ctrl, "element_info", None)
    return {
        "title": safe(ctrl.window_text, ""),
        "class": safe(ctrl.class_name, ""),
        "friendly_class": safe(ctrl.friendly_class_name, ""),
        "control_type": getattr(element, "control_type", "") if element else "",
        "auto_id": getattr(element, "automation_id", "") if element else "",
        "control_id": safe(lambda: ctrl.control_id(), ""),
        "rect": [rect.left, rect.top, rect.right, rect.bottom] if rect else None,
        "enabled": safe(lambda: ctrl.is_enabled(), None),
        "visible": safe(lambda: ctrl.is_visible(), None),
    }


def cmd_find(args: argparse.Namespace) -> int:
    require_windows()
    spec, w = _connect_window(args.title, args.hwnd, args.backend)
    name_rx = re.compile(args.name, re.IGNORECASE) if args.name else None
    type_rx = re.compile(args.control_type, re.IGNORECASE) if args.control_type else None

    matches: list[dict[str, Any]] = []
    try:
        controls = [spec.wrapper_object()] + list(spec.descendants())
    except Exception:
        controls = list(spec.descendants())

    for ctrl in controls:
        info = _control_dict(ctrl)
        haystack = " ".join(
            str(info[k]) for k in
            ("title", "class", "friendly_class", "control_type", "auto_id", "control_id")
        )
        if name_rx and not name_rx.search(haystack):
            continue
        if type_rx and not type_rx.search(str(info.get("control_type") or info.get("class"))):
            continue
        matches.append(info)
        if len(matches) >= args.limit:
            break

    if args.json:
        print(json.dumps(matches, ensure_ascii=True, indent=2))
        return 0
    print(f"# {len(matches)} match(es) in hwnd={w.hwnd} title={w.title!r}")
    for info in matches:
        print(
            f"[{info['control_type'] or info['class']}] "
            f"title={info['title']!r} auto_id={info['auto_id']!r} "
            f"id={info['control_id']!r} rect={info['rect']} "
            f"enabled={info['enabled']} visible={info['visible']}"
        )
    return 0


def cmd_shot(args: argparse.Namespace) -> int:
    require_windows()
    try:
        from PIL import ImageGrab
    except ImportError as exc:  # pragma: no cover
        print("error: Pillow is required for shot", file=sys.stderr)
        raise SystemExit(3) from exc

    if args.title or args.hwnd:
        w = _resolve(args.title, args.hwnd)
        bbox = tuple(w.rect)
        label = f"hwnd={w.hwnd} title={w.title!r}"
        if w.minimized:
            print("warning: window is minimized; screenshot may be blank", file=sys.stderr)
    else:
        bbox = None
        label = "full screen"

    image = ImageGrab.grab(bbox=bbox, all_screens=True)
    out = args.out or os.path.join(
        os.getcwd(), f"screenshot_{time.strftime('%Y%m%d_%H%M%S')}.png"
    )
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    image.save(out)
    print(f"target : {label}")
    print(f"size   : {image.size[0]} x {image.size[1]}")
    print(f"output : {os.path.abspath(out)}")
    return 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Read-only Windows UI reconnaissance (never clicks or types).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--version", action="version", version="probe_windows 1.0")
    sub = p.add_subparsers(dest="command", required=True)

    q = sub.add_parser("windows", help="list top-level windows")
    q.add_argument("--filter", help="regex on title/class/process")
    q.add_argument("--all", action="store_true", help="include invisible windows")
    q.add_argument("--json", action="store_true")
    q.set_defaults(func=cmd_windows)

    q = sub.add_parser("info", help="show one window's details")
    q.add_argument("--title", help="title/process regex")
    q.add_argument("--hwnd", type=int)
    q.add_argument("--json", action="store_true")
    q.set_defaults(func=cmd_info)

    q = sub.add_parser("scaling", help="screen metrics and DPI")
    q.add_argument("--json", action="store_true")
    q.set_defaults(func=cmd_scaling)

    q = sub.add_parser("dump", help="dump control tree (pywinauto)")
    q.add_argument("--title", help="title/process regex")
    q.add_argument("--hwnd", type=int)
    q.add_argument("--backend", choices=["uia", "win32"], default="uia")
    q.add_argument("--depth", type=int, default=None)
    q.add_argument("--out", help="write tree to this file")
    q.set_defaults(func=cmd_dump)

    q = sub.add_parser("find", help="find controls by name/type")
    q.add_argument("--title", help="title/process regex")
    q.add_argument("--hwnd", type=int)
    q.add_argument("--backend", choices=["uia", "win32"], default="uia")
    q.add_argument("--name", help="regex on title/class/auto_id/control_id")
    q.add_argument("--control-type", help="regex on control type/class")
    q.add_argument("--limit", type=int, default=50)
    q.add_argument("--json", action="store_true")
    q.set_defaults(func=cmd_find)

    q = sub.add_parser("shot", help="screenshot a window or the screen")
    q.add_argument("--title", help="title/process regex")
    q.add_argument("--hwnd", type=int)
    q.add_argument("--out", help="output PNG path")
    q.set_defaults(func=cmd_shot)

    return p


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        return int(args.func(args))
    except SystemExit:
        raise
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
