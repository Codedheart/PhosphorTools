"""Thin Windows helpers (ctypes, user32 only). Everything is a no-op off Windows.

Besides our own window, the launcher lists top-level windows and shows / hides the windows
of the Phosphor apps it starts (the same calls the taskbar uses). Nothing here touches any game.
"""
from __future__ import annotations

import sys

IS_WIN = sys.platform == "win32"

if IS_WIN:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)

    GWL_EXSTYLE = -20
    WS_EX_LAYERED = 0x00080000
    WS_EX_TRANSPARENT = 0x00000020
    WS_EX_TOOLWINDOW = 0x00000080
    WS_EX_NOACTIVATE = 0x08000000
    WS_EX_APPWINDOW = 0x00040000
    WDA_NONE = 0x0
    WDA_EXCLUDEFROMCAPTURE = 0x11

    user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
    user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    H, I, U = wintypes.HWND, ctypes.c_int, wintypes.UINT
    for _name, _args, _res in (
        ("GetAncestor", [H, U], H),
        ("SetWindowDisplayAffinity", [H, wintypes.DWORD], wintypes.BOOL),
        ("SetForegroundWindow", [H], wintypes.BOOL),
        ("GetSystemMetrics", [I], I),
        ("MonitorFromWindow", [H, wintypes.DWORD], wintypes.HMONITOR),
    ):
        _f = getattr(user32, _name)
        _f.argtypes, _f.restype = _args, _res

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

    user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFO)]
    user32.GetMonitorInfoW.restype = wintypes.BOOL


def set_dpi_aware() -> None:
    """Crisp text on 125% / 150% displays; fonts are sized in points so they scale."""
    if not IS_WIN:
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass


def virtual_screen() -> tuple[int, int, int, int] | None:
    """(left, top, width, height) spanning all monitors."""
    if not IS_WIN:
        return None
    g = user32.GetSystemMetrics
    return g(76), g(77), g(78), g(79)


def _top(hwnd_from_tk: int) -> int:
    # Tk's winfo_id is a child; the real top-level is its root ancestor
    return user32.GetAncestor(hwnd_from_tk, 2) or hwnd_from_tk  # GA_ROOT


def work_area(tk_hwnd: int) -> tuple[int, int, int, int] | None:
    """(left, top, right, bottom) of the usable area of the monitor our window is on."""
    if not IS_WIN:
        return None
    mon = user32.MonitorFromWindow(_top(tk_hwnd), 2)  # MONITOR_DEFAULTTONEAREST
    mi = MONITORINFO()
    mi.cbSize = ctypes.sizeof(MONITORINFO)
    if not mon or not user32.GetMonitorInfoW(mon, ctypes.byref(mi)):
        return None
    r = mi.rcWork
    return r.left, r.top, r.right, r.bottom


def foreground(tk_hwnd: int) -> None:
    if IS_WIN:
        user32.SetForegroundWindow(_top(tk_hwnd))


def set_overlay_styles(tk_hwnd: int, can_focus: bool = False) -> None:
    """No taskbar button and, normally, clicks never steal focus from the game.
    ``can_focus`` lifts that while the channel number is being typed."""
    if not IS_WIN:
        return
    h = _top(tk_hwnd)
    ex = user32.GetWindowLongPtrW(h, GWL_EXSTYLE)
    ex |= WS_EX_TOOLWINDOW | WS_EX_LAYERED
    ex &= ~(WS_EX_APPWINDOW | WS_EX_TRANSPARENT)
    if can_focus:
        ex &= ~WS_EX_NOACTIVATE
    else:
        ex |= WS_EX_NOACTIVATE
    user32.SetWindowLongPtrW(h, GWL_EXSTYLE, ex)


def exclude_from_capture(tk_hwnd: int, on: bool) -> bool:
    """Hide our window from screen capture / streams (Win10 2004+)."""
    if not IS_WIN:
        return False
    return bool(user32.SetWindowDisplayAffinity(_top(tk_hwnd), WDA_EXCLUDEFROMCAPTURE if on else WDA_NONE))


# --------------------------------------------------------- other apps' windows
if IS_WIN:
    EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    for _name, _args, _res in (
        ("EnumWindows", [EnumWindowsProc, wintypes.LPARAM], wintypes.BOOL),
        ("GetWindowThreadProcessId", [H, ctypes.POINTER(wintypes.DWORD)], wintypes.DWORD),
        ("IsWindowVisible", [H], wintypes.BOOL),
        ("IsWindow", [H], wintypes.BOOL),
        ("IsIconic", [H], wintypes.BOOL),
        ("ShowWindow", [H, I], wintypes.BOOL),
        ("GetWindowTextLengthW", [H], I),
        ("GetWindow", [H, U], H),
    ):
        _f = getattr(user32, _name)
        _f.argtypes, _f.restype = _args, _res
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                    ctypes.POINTER(wintypes.DWORD)]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SW_HIDE, SW_SHOWNOACTIVATE, SW_RESTORE = 0, 4, 9


def top_windows() -> list[tuple[int, int, bool, bool]]:
    """Every top-level window that isn't owned by another: (hwnd, pid, visible, has_title)."""
    if not IS_WIN:
        return []
    out = []

    def cb(hwnd, _lp):
        if user32.GetWindow(hwnd, 4):            # GW_OWNER: skip dialogs / menus owned by others
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        visible = bool(user32.IsWindowVisible(hwnd)) and not user32.IsIconic(hwnd)
        out.append((int(hwnd), int(pid.value), visible, user32.GetWindowTextLengthW(hwnd) > 0))
        return True

    user32.EnumWindows(EnumWindowsProc(cb), 0)
    return out


def process_image(pid: int) -> str | None:
    """Full path of a process's .exe (works without admin for our own user's processes)."""
    if not IS_WIN:
        return None
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return None
    try:
        buf = ctypes.create_unicode_buffer(1024)
        n = wintypes.DWORD(len(buf))
        return buf.value if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)) else None
    finally:
        kernel32.CloseHandle(h)


def pid_alive(pid: int) -> bool:
    if not IS_WIN:
        return False
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return False
    try:
        code = wintypes.DWORD()
        return bool(kernel32.GetExitCodeProcess(h, ctypes.byref(code))) and code.value == 259  # STILL_ACTIVE
    finally:
        kernel32.CloseHandle(h)


def is_window(hwnd: int) -> bool:
    return bool(IS_WIN and user32.IsWindow(hwnd))


def hide_window(hwnd: int) -> None:
    if IS_WIN:
        user32.ShowWindow(hwnd, SW_HIDE)


def show_window(hwnd: int) -> None:
    """Show again without stealing focus; un-minimise if it was minimised."""
    if IS_WIN:
        user32.ShowWindow(hwnd, SW_RESTORE if user32.IsIconic(hwnd) else SW_SHOWNOACTIVATE)


_mutex = None


def single_instance(name: str) -> bool:
    """False if another copy of the launcher is already running (one hub is enough)."""
    global _mutex
    if not IS_WIN:
        return True
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    _mutex = kernel32.CreateMutexW(None, False, name)
    return ctypes.get_last_error() != 183          # ERROR_ALREADY_EXISTS


# ------------------------------------------------------------ start with Windows
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_RUN_NAME = "PhosphorTools"


def get_autostart() -> bool:
    if not IS_WIN:
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
            winreg.QueryValueEx(k, _RUN_NAME)
            return True
    except OSError:
        return False


def set_autostart(command: str | None) -> bool:
    """command=None removes the entry. Per-user (HKCU), no admin needed."""
    if not IS_WIN:
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if command:
                winreg.SetValueEx(k, _RUN_NAME, 0, winreg.REG_SZ, command)
            else:
                try:
                    winreg.DeleteValue(k, _RUN_NAME)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False


def add_private_font(path: str) -> bool:
    """Make a bundled .ttf available to this process only (no install)."""
    if not IS_WIN:
        return False
    try:
        return ctypes.windll.gdi32.AddFontResourceExW(path, 0x10, 0) > 0  # FR_PRIVATE
    except Exception:
        return False
