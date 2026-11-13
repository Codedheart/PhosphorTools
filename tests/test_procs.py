from pathlib import Path

from phosphor.apps import AppSpec
from phosphor.procs import HIDDEN, NOT_INSTALLED, STOPPED, VISIBLE, Manager

APP = AppSpec("count", "Phosphor Count", "o/r", "a.zip", "PhosphorCount.exe", ("." * 11,) * 9)


class FakeSystem:
    """Pretend Windows: windows are {hwnd: [pid, visible, titled]}, pids map to exe paths."""
    def __init__(self):
        self.wins = {}
        self.images = {}
        self.started = []

    def top_windows(self):
        return [(h, w[0], w[1], w[2]) for h, w in self.wins.items()]

    def process_image(self, pid):
        return self.images.get(pid)

    def pid_alive(self, pid):
        return pid in self.images

    def is_window(self, h):
        return h in self.wins

    def hide(self, h):
        self.wins[h][1] = False

    def show(self, h):
        self.wins[h][1] = True

    def start(self, exe):
        pid = 500 + len(self.started)
        self.started.append(exe)
        self.images[pid] = rf"C:\Users\x\AppData\Local\PhosphorTools\apps\count\{exe.name}"
        self.wins[900 + pid] = [pid, True, True]
        return pid


def setup(tmp_path):
    sysm = FakeSystem()
    exe = tmp_path / "PhosphorCount.exe"
    exe.write_bytes(b"")
    hidden = {}
    return sysm, Manager(hidden, sysm), exe, hidden


def test_click_cycle_start_hide_show(tmp_path):
    sysm, m, exe, hidden = setup(tmp_path)
    m.scan()
    assert m.state(APP, False) == NOT_INSTALLED and m.state(APP, True) == STOPPED
    assert m.toggle(APP, exe) == "started"
    m.scan()
    assert m.state(APP, True) == VISIBLE
    assert m.toggle(APP, exe) == "hidden"
    m.scan()
    assert m.state(APP, True) == HIDDEN and hidden["count"]["hwnds"]
    assert m.toggle(APP, exe) == "shown"
    m.scan()
    assert m.state(APP, True) == VISIBLE and "count" not in hidden
    assert len(sysm.started) == 1          # never started twice


def test_only_its_own_visible_windows_are_hidden_and_reshown(tmp_path):
    sysm, m, exe, hidden = setup(tmp_path)
    sysm.images = {7: r"D:\games\PhosphorCount\PhosphorCount.exe", 8: r"C:\other\Notepad.exe"}
    sysm.wins = {1: [7, True, True], 2: [7, False, False], 3: [8, True, True]}   # 2: Tk's hidden helper
    m.scan()
    m.toggle(APP, exe)                      # copy started outside the launcher is still found
    assert sysm.wins[1][1] is False and sysm.wins[3][1] is True
    m.scan()
    m.toggle(APP, exe)
    assert sysm.wins[1][1] is True and sysm.wins[2][1] is False      # helper stays hidden


def test_lost_track_falls_back_to_titled_windows(tmp_path):
    sysm, m, exe, hidden = setup(tmp_path)
    sysm.images = {7: r"C:\x\PhosphorCount.exe"}
    sysm.wins = {1: [7, False, True], 2: [7, False, False]}     # hidden, but not by us
    m.scan()
    assert m.state(APP, True) == HIDDEN
    m.toggle(APP, exe)
    assert sysm.wins[1][1] is True and sysm.wins[2][1] is False


def test_restore_all_on_exit_and_closed_app_forgotten(tmp_path):
    sysm, m, exe, hidden = setup(tmp_path)
    m.toggle(APP, exe); m.scan(); m.toggle(APP, exe)
    assert hidden
    m.restore_all()
    assert all(w[1] for w in sysm.wins.values()) and hidden == {}
    m.scan(); m.hide(APP); sysm.wins.clear(); sysm.images.clear()
    m.scan()
    assert m.state(APP, True) == STOPPED and hidden == {}       # app closed itself: nothing to restore
