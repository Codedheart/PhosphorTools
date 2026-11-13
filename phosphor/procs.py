"""Start the apps, and hide / show their windows ("minimise to the launcher").

The Phosphor apps are always-on-top overlays without taskbar buttons, so "minimise" here means
hiding the app's windows; selecting it in the launcher again shows exactly those windows again.
The windows we hid are remembered in config.json, so even if the launcher is closed or restarted,
nothing gets stuck hidden: it restores them on exit and can find them again on start.

Apps are recognised by their .exe name, so a copy started some other way (e.g. from its own zip
folder) is controlled too.
"""
from __future__ import annotations

import ntpath
import os
import subprocess
from pathlib import Path

from . import winapi
from .apps import AppSpec

NOT_INSTALLED, STOPPED, VISIBLE, HIDDEN = "not_installed", "stopped", "visible", "hidden"


class System:
    """The Windows calls procs needs; tests swap in a fake."""
    top_windows = staticmethod(winapi.top_windows)
    process_image = staticmethod(winapi.process_image)
    pid_alive = staticmethod(winapi.pid_alive)
    is_window = staticmethod(winapi.is_window)
    hide = staticmethod(winapi.hide_window)
    show = staticmethod(winapi.show_window)

    @staticmethod
    def start(exe: Path) -> int:
        flags = 0x00000008 | 0x00000200 if os.name == "nt" else 0   # DETACHED_PROCESS | NEW_PROCESS_GROUP
        p = subprocess.Popen([str(exe)], cwd=str(exe.parent), close_fds=True, creationflags=flags,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return p.pid


class Manager:
    def __init__(self, hidden: dict, system: System | None = None) -> None:
        self.sys = system or System()
        self.hidden = hidden          # app id -> {"pid": n, "hwnds": [...]}; lives in config.json
        self._images: dict[int, str] = {}
        self._wins: list[tuple[int, int, bool, bool]] = []

    # ------------------------------------------------------------- looking
    def scan(self) -> None:
        """Take a fresh look at the open windows (cheap; done a couple of times a second)."""
        self._wins = self.sys.top_windows()
        live = {pid for _h, pid, _v, _t in self._wins}
        self._images = {pid: img for pid, img in self._images.items() if pid in live}

    def _exe_of(self, pid: int) -> str:
        if pid not in self._images:
            self._images[pid] = ntpath.basename(self.sys.process_image(pid) or "").lower()   # handles \\ and /
        return self._images[pid]

    def windows(self, app: AppSpec) -> list[tuple[int, int, bool, bool]]:
        exe = app.exe.lower()
        return [w for w in self._wins if self._exe_of(w[1]) == exe]

    def state(self, app: AppSpec, installed: bool) -> str:
        wins = self.windows(app)
        if not wins:
            self.hidden.pop(app.id, None)
            return STOPPED if installed else NOT_INSTALLED
        if any(vis for _h, _p, vis, _t in wins):
            return VISIBLE
        return HIDDEN

    # -------------------------------------------------------------- acting
    def hide(self, app: AppSpec) -> bool:
        wins = [w for w in self.windows(app) if w[2]]
        if not wins:
            return False
        rec = self.hidden.setdefault(app.id, {"pid": wins[0][1], "hwnds": []})
        for hwnd, pid, _v, _t in wins:
            self.sys.hide(hwnd)
            if hwnd not in rec["hwnds"]:
                rec["hwnds"].append(hwnd)
            rec["pid"] = pid
        return True

    def show(self, app: AppSpec) -> bool:
        wins = self.windows(app)
        ours = {h for h, _p, _v, _t in wins}
        rec = self.hidden.pop(app.id, None)
        targets = [h for h in (rec or {}).get("hwnds", []) if h in ours and self.sys.is_window(h)]
        if not targets:
            # we didn't hide it (or lost track): bring back its titled main window(s)
            targets = [h for h, _p, _v, titled in wins if titled]
        for h in targets:
            self.sys.show(h)
        return bool(targets)

    def restore_all(self) -> None:
        """On exit: never leave an app invisible with no way back."""
        self.scan()
        for app_id in list(self.hidden):
            rec = self.hidden.pop(app_id)
            for h in rec.get("hwnds", []):
                if self.sys.is_window(h):
                    self.sys.show(h)

    def start(self, exe: Path) -> int:
        return self.sys.start(exe)

    def toggle(self, app: AppSpec, exe: Path | None) -> str:
        """What one click on the app does. Returns what happened: started/hidden/shown/missing."""
        st = self.state(app, exe is not None and exe.exists())
        if st == VISIBLE:
            self.hide(app)
            return "hidden"
        if st == HIDDEN:
            self.show(app)
            return "shown"
        if exe is None or not exe.exists():
            return "missing"
        self.start(exe)
        return "started"
