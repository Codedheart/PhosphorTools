"""The launcher: a small round always-on-top hub that fans out a radial menu of apps."""
from __future__ import annotations

import math
import os
import queue
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
import webbrowser
from pathlib import Path

from . import installer, radial, themes, updater, winapi
from .apps import APPS, AppSpec
from .config import APP_NAME, Config, data_dir
from .procs import HIDDEN, NOT_INSTALLED, STOPPED, VISIBLE, Manager
from .version import VERSION

ASSETS = Path(__file__).parent / "assets"
KEY = "#FE01FD"           # see-through colour (never used by any palette); clicks pass through it
POLL_MS = 600             # how often app states are refreshed
COLLAPSE_MS = 1600        # menu folds away this long after the mouse leaves it
UPDATE_CHECK_MS = 6 * 3600 * 1000
DRAG_PX = 5

# 9x9 hub glyph: dots in a ring around a centre dot
HUB = ["....#....",
       ".........",
       ".#.....#.",
       ".........",
       "#...#...#",
       ".........",
       ".#.....#.",
       ".........",
       "....#...."]
DOWN = ["..#..",       # "click to install" marker
        "..#..",
        "#####",
        ".###.",
        "..#.."]


def _runs(bitmap, mark="#"):
    for y, line in enumerate(bitmap):
        x = 0
        while x < len(line):
            if line[x] == mark:
                s = x
                while x < len(line) and line[x] == mark:
                    x += 1
                yield y, s, x - s
            else:
                x += 1


class App:
    def __init__(self) -> None:
        winapi.set_dpi_aware()
        self.cfg = Config()
        if not isinstance(self.cfg.get("hidden"), dict):
            self.cfg["hidden"] = {}
        self.mgr = Manager(self.cfg["hidden"])
        self.states: dict[str, str] = {}
        self.installing: dict[str, float] = {}        # app id -> download progress 0..1
        self.errors: dict[str, tuple[str, float]] = {}  # app id -> (message, until)
        self.q: "queue.Queue[tuple]" = queue.Queue()
        self.expanded = False
        self.items: list[tuple[AppSpec, float, float]] = []   # app, centre x, centre y (canvas)
        self.hover: str | None = None                  # "hub" or an app id
        self._press = None                             # (x_root, y_root, target)
        self._dragging = False
        self._collapse_job = None
        self._menu_open = False
        self._closing = False
        self.update_rel: updater.Release | None = None
        self.update_busy: str | None = None
        self.dialog = None

        self.root = tk.Tk()
        self.root.report_callback_exception = self._log_exc
        self.root.title(APP_NAME)
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        try:
            self.root.attributes("-transparentcolor", KEY)       # Windows: round, see-through window
        except tk.TclError:
            pass
        self._set_alpha()
        self._fonts()
        self._metrics()
        self.canvas = tk.Canvas(self.root, highlightthickness=0, bd=0, bg=KEY, cursor="hand2")
        self.canvas.pack(fill="both", expand=True)
        c = self.canvas
        c.bind("<ButtonPress-1>", self._on_press)
        c.bind("<B1-Motion>", self._on_drag)
        c.bind("<ButtonRelease-1>", self._on_release)
        c.bind("<Motion>", self._on_motion)
        c.bind("<Leave>", self._on_leave)
        c.bind("<Enter>", lambda e: self._cancel_collapse())
        c.bind("<Button-3>", self._menu)
        self.tip = Tip(self)

        self.hx, self.hy = self._clamp_hub(int(self.cfg["x"]), int(self.cfg["y"]))
        self._poll(render=False)
        self._layout()
        self.root.after_idle(self._after_mapped)
        self.root.after(POLL_MS, self._poll_loop)
        self.root.after(2000, self._keep_on_top)
        self.root.after(5000, self._auto_check)
        self.root.protocol("WM_DELETE_WINDOW", self.quit)
        self._report_last_update()

    # ------------------------------------------------------------- setup
    def _after_mapped(self) -> None:
        self.root.update_idletasks()
        if not self.root.winfo_viewable():
            self.root.after(50, self._after_mapped)
            return
        winapi.set_overlay_styles(self.root.winfo_id(), False)
        self._set_alpha()

    def _log_exc(self, exc, val, tb) -> None:
        import traceback
        try:
            with (data_dir() / "error.log").open("a", encoding="utf-8") as f:
                f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + "".join(traceback.format_exception(exc, val, tb)))
        except OSError:
            pass

    def _fonts(self) -> None:
        ttf = ASSETS / "VT323-Regular.ttf"
        if ttf.exists():
            winapi.add_private_font(str(ttf))
        fams = set(tkfont.families(self.root))
        if "VT323" in fams:
            fam, small, mid = "VT323", 15, 18
        else:
            fam = next((f for f in ("Lucida Console", "Consolas", "Courier New", "DejaVu Sans Mono")
                        if f in fams), "TkFixedFont")
            small, mid = 9, 10
        self.f_small = tkfont.Font(family=fam, size=small)
        self.f_mid = tkfont.Font(family=fam, size=mid)

    def _metrics(self) -> None:
        lh = self.f_small.metrics("linespace")
        self.px = max(2, round(lh / 9))               # pixel-art scale; follows Windows display scaling
        self.hub_r = 9 * self.px // 2 + 3 * self.px    # hub radius
        self.item_r = 11 * self.px // 2 + 3 * self.px  # app button radius

    @property
    def th(self) -> dict:
        return themes.get(self.cfg["theme"])

    def _set_alpha(self) -> None:
        self.root.attributes("-alpha", min(0.99, max(0.3, float(self.cfg["opacity"]))))

    def _keep_on_top(self) -> None:
        self.root.after(2000, self._keep_on_top)
        if not self._menu_open and not self._closing:
            self.root.attributes("-topmost", True)
            self.root.lift()

    def _area(self) -> tuple[int, int, int, int]:
        wa = None
        try:
            wa = winapi.work_area(self.root.winfo_id())
        except Exception:
            pass
        return wa or (0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight())

    def _clamp_hub(self, x: int, y: int) -> tuple[int, int]:
        vs = winapi.virtual_screen()
        if vs:
            l, t, w, h = vs
        else:
            l, t, w, h = 0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        r = self.hub_r + 2
        return min(max(x, l + r), l + w - r), min(max(y, t + r), t + h - r)

    # ------------------------------------------------------------ layout
    def _layout(self) -> None:
        """Size and place the window: just the hub, or the hub plus the fanned-out apps."""
        if self.expanded:
            pts, _rad = radial.fan(self.hx, self.hy, len(APPS), self.item_r, self._area(), gap=self.px * 3)
            l, t, r, b = radial.bbox(pts, self.item_r, (self.hx, self.hy), self.hub_r, pad=3)
            self.items = [(app, x - l, y - t) for app, (x, y) in zip(APPS, pts)]
        else:
            pad = self.hub_r + 3
            l, t, r, b = self.hx - pad, self.hy - pad, self.hx + pad, self.hy + pad
            self.items = []
        self.ox, self.oy = l, t                  # window origin on screen
        self.root.geometry(f"{r - l}x{b - t}+{l}+{t}")
        self.canvas.configure(width=r - l, height=b - t)
        self._render()

    def _hub_xy(self) -> tuple[float, float]:
        return self.hx - self.ox, self.hy - self.oy

    # ----------------------------------------------------------- drawing
    def _disc(self, cx, cy, r, ring, inner, fill=None) -> None:
        """A CRT-style round button: filled disc, scanlines, double ring."""
        c, th = self.canvas, self.th
        c.create_oval(cx - r, cy - r, cx + r, cy + r, fill=fill or th["bg"], outline="", tags=("dyn",))
        y = cy - r + 2
        while y < cy + r - 1:                       # scanlines clipped to the circle
            half = math.sqrt(max(0.0, r * r - (y - cy) ** 2)) - 2
            if half > 0:
                c.create_line(cx - half, y, cx + half, y, fill=th["scan"], tags=("dyn",))
            y += 3
        c.create_oval(cx - r, cy - r, cx + r, cy + r, outline=ring, width=max(1, self.px // 2 + 1), tags=("dyn",))
        c.create_oval(cx - r + 3, cy - r + 3, cx + r - 3, cy + r - 3, outline=inner, tags=("dyn",))

    def _bitmap(self, bitmap, cx, cy, color, px=None) -> None:
        p = px or self.px
        w, h = len(bitmap[0]) * p, len(bitmap) * p
        x0, y0 = round(cx - w / 2), round(cy - h / 2)
        for row, start, length in _runs(bitmap):
            self.canvas.create_rectangle(x0 + start * p, y0 + row * p, x0 + (start + length) * p - 1,
                                         y0 + (row + 1) * p - 1, fill=color, width=0, tags=("dyn",))

    def _render(self) -> None:
        if self._closing:
            return
        c, th = self.canvas, self.th
        c.delete("dyn")
        now = time.monotonic()
        # hub
        hx, hy = self._hub_xy()
        hov = self.hover == "hub"
        ring = th["warn"] if (self.update_rel or self.update_busy) else (th["fg"] if hov or self.expanded else th["dim"])
        self._disc(hx, hy, self.hub_r, ring, th["glow"], fill=th["glow"] if hov else None)
        any_visible = any(s == VISIBLE for s in self.states.values())
        self._bitmap(HUB, hx, hy, th["fg"] if (hov or any_visible or self.expanded) else th["mid"])
        # apps
        for app, x, y in self.items:
            st = self.states.get(app.id, NOT_INSTALLED)
            hov = self.hover == app.id
            err = self.errors.get(app.id)
            if err and err[1] < now:
                self.errors.pop(app.id, None)
                err = None
            if err:
                ring, icon = th["late"], th["late"]
            elif app.id in self.installing:
                ring, icon = th["dim"], th["mid"]
            elif st == VISIBLE:
                ring, icon = th["fg"], th["fg"]
            elif st == HIDDEN:
                ring, icon = th["mid"], th["mid"]
            elif st == STOPPED:
                ring, icon = th["dim"], th["mid"]
            else:
                ring, icon = th["dim"], th["dim"]
            if hov:
                icon = th["fg"]
            self._disc(x, y, self.item_r, ring, th["glow"], fill=th["glow"] if hov else None)
            self._bitmap(app.icon, x, y, icon)
            r = self.item_r
            if app.id in self.installing:            # download progress around the rim
                ext = -359.9 * max(0.02, self.installing[app.id])
                c.create_arc(x - r, y - r, x + r, y + r, start=90, extent=ext, style="arc",
                             outline=th["warn"], width=max(2, self.px), tags=("dyn",))
            elif st == NOT_INSTALLED and not err:     # small "download" badge, bottom right
                bx, by, br = x + r * 0.66, y + r * 0.66, 4 * self.px
                c.create_oval(bx - br, by - br, bx + br, by + br, fill=th["bg"], outline=th["mid"], tags=("dyn",))
                self._bitmap(DOWN, bx, by + 1, th["fg"] if hov else th["mid"], px=max(1, self.px - 1) if self.px > 2 else 1)
            elif st == VISIBLE:                       # "running" dot, bottom
                d = self.px
                c.create_oval(x - d, y + r - 3 * d, x + d, y + r - d, fill=th["fg"], outline="", tags=("dyn",))
            elif st == HIDDEN:                        # hollow dot: running but tucked away
                d = self.px
                c.create_oval(x - d, y + r - 3 * d, x + d, y + r - d, outline=th["mid"], tags=("dyn",))
        self.tip.update()

    # ------------------------------------------------------------- input
    def _target_at(self, x, y) -> str | None:
        hx, hy = self._hub_xy()
        if math.hypot(x - hx, y - hy) <= self.hub_r + 1:
            return "hub"
        for app, ax, ay in self.items:
            if math.hypot(x - ax, y - ay) <= self.item_r + 1:
                return app.id
        return None

    def _on_press(self, e) -> None:
        self._press = (e.x_root, e.y_root, self._target_at(e.x, e.y), self.hx, self.hy)
        self._dragging = False

    def _on_drag(self, e) -> None:
        if not self._press or self._press[2] != "hub":
            return
        x0, y0, _t, hx0, hy0 = self._press
        if not self._dragging and math.hypot(e.x_root - x0, e.y_root - y0) < DRAG_PX:
            return
        if not self._dragging:
            self._dragging = True
            if self.expanded:
                self.expanded = False
            self.tip.hide()
        self.hx, self.hy = hx0 + e.x_root - x0, hy0 + e.y_root - y0
        self._layout()

    def _on_release(self, e) -> None:
        press, self._press = self._press, None
        if press is None:
            return
        if self._dragging:
            self._dragging = False
            self.hx, self.hy = self._clamp_hub(self.hx, self.hy)
            self.cfg["x"], self.cfg["y"] = self.hx, self.hy
            self.save()
            self._layout()
            return
        target = self._target_at(e.x, e.y)
        if target != press[2] or target is None:
            return
        if target == "hub":
            self.toggle_menu()
        else:
            self.activate(target)

    def _on_motion(self, e) -> None:
        t = self._target_at(e.x, e.y)
        if t != self.hover:
            self.hover = t
            self._render()

    def _on_leave(self, _e) -> None:
        if self.hover is not None:
            self.hover = None
            self._render()
        if self.expanded and not self._menu_open:
            self._cancel_collapse()
            self._collapse_job = self.root.after(COLLAPSE_MS, self._auto_collapse)

    def _cancel_collapse(self) -> None:
        if self._collapse_job:
            self.root.after_cancel(self._collapse_job)
            self._collapse_job = None

    def _auto_collapse(self) -> None:
        self._collapse_job = None
        if self.expanded and self.hover is None and not self._press:
            self.toggle_menu(False)

    def toggle_menu(self, open_: bool | None = None) -> None:
        self.expanded = (not self.expanded) if open_ is None else open_
        self._cancel_collapse()
        self._layout()

    # ----------------------------------------------------------- actions
    def activate(self, app_id: str) -> None:
        """One click on an app: install it if needed, otherwise start / hide / show it."""
        app = next(a for a in APPS if a.id == app_id)
        if app.id in self.installing:
            return
        if not installer.installed(app):
            self._install(app, then_start=True)
            return
        self.mgr.scan()
        try:
            did = self.mgr.toggle(app, installer.exe_path(app))
        except OSError:
            did = "failed"
            self.errors[app.id] = ("COULDN'T START IT", time.monotonic() + 5)
        if did in ("hidden", "shown"):
            self.save()
        self.root.after(250, self._poll)
        self._render()

    def _install(self, app: AppSpec, then_start: bool) -> None:
        self.installing[app.id] = 0.0
        self.errors.pop(app.id, None)

        def work():
            try:
                exe = installer.install(app, progress=lambda f: self.q.put(("progress", app.id, f)))
                self.q.put(("installed", app.id, exe, then_start))
            except updater.UpdateError as e:
                self.q.put(("install_failed", app.id, str(e)))
            except Exception as e:
                self.q.put(("install_failed", app.id, type(e).__name__.upper()))
        threading.Thread(target=work, daemon=True).start()
        self._render()

    def reinstall(self, app: AppSpec) -> None:
        self.mgr.scan()
        if self.mgr.state(app, True) in (VISIBLE, HIDDEN):
            self.errors[app.id] = (f"CLOSE {app.name.upper()} FIRST", time.monotonic() + 5)
            self.toggle_menu(True)
            return
        self.toggle_menu(True)
        self._install(app, then_start=False)

    # ----------------------------------------------------------- polling
    def _poll(self, render: bool = True) -> None:
        self.mgr.scan()
        new = {a.id: self.mgr.state(a, installer.installed(a)) for a in APPS}
        changed = new != self.states
        self.states = new
        if render and (changed or self.installing or self.errors):
            self._render()

    def _poll_loop(self) -> None:
        if self._closing:
            return
        try:
            self._drain()
            self._poll()
        except Exception:
            self._log_exc(*sys.exc_info())
        finally:
            if not self._closing:
                self.root.after(POLL_MS, self._poll_loop)

    def _drain(self) -> None:
        while True:
            try:
                msg = self.q.get_nowait()
            except queue.Empty:
                return
            kind = msg[0]
            if kind == "progress":
                if msg[1] in self.installing:
                    self.installing[msg[1]] = msg[2]
            elif kind == "installed":
                _k, app_id, exe, then_start = msg
                self.installing.pop(app_id, None)
                if then_start:
                    try:
                        self.mgr.start(exe)
                    except OSError:
                        self.errors[app_id] = ("COULDN'T START IT", time.monotonic() + 5)
            elif kind == "install_failed":
                self.installing.pop(msg[1], None)
                self.errors[msg[1]] = (msg[2], time.monotonic() + 8)
                self.toggle_menu(True)
            elif kind == "checked":
                self._checked(*msg[1:])
            elif kind == "upd_progress":
                self.update_busy = f"DOWNLOADING {int(msg[1] * 100)}%"
            elif kind == "upd_ready":
                self._install_self(msg[1], msg[2])
            elif kind == "upd_failed":
                self.update_busy = None
                self._dialog("UPDATE FAILED", f"{msg[1]}\n\nThe launcher stays as it is.", [("OK", None)])
        self._render()

    def save(self) -> None:
        self.cfg["hidden"] = self.mgr.hidden
        self.cfg.save()

    def quit(self) -> None:
        if self._closing:
            return
        self._closing = True
        try:
            self.mgr.restore_all()         # never leave an app hidden with no launcher to bring it back
        finally:
            self.save()
            self.root.destroy()

    # -------------------------------------------------------------- menu
    def _menu(self, e) -> None:
        if self._target_at(e.x, e.y) != "hub":
            return
        th = self.th
        mk = dict(tearoff=0, bg=th["bg"], fg=th["fg"], activebackground=th["glow"],
                  activeforeground=th["fg"], font=self.f_small)
        m = tk.Menu(self.root, **mk)
        m.add_command(label=f"Phosphor Tools {self._version_label()}", state="disabled")
        m.add_separator()
        apps_m = tk.Menu(m, **mk)
        for app in APPS:
            tag = installer.installed_tag(app)
            if installer.installed(app):
                apps_m.add_command(label=f"Reinstall {app.name} (latest)" + (f"  [had {tag}]" if tag else ""),
                                   command=lambda a=app: self.reinstall(a))
            else:
                apps_m.add_command(label=f"Install {app.name}", command=lambda a=app: self.reinstall(a))
        apps_m.add_separator()
        apps_m.add_command(label="Open apps folder", command=self.open_apps_folder)
        m.add_cascade(label="Apps", menu=apps_m)
        sub = tk.Menu(m, **mk)
        ov = tk.DoubleVar(value=round(float(self.cfg["opacity"]), 2))
        for p in (0.5, 0.65, 0.8, 0.95):
            sub.add_radiobutton(label=f"{int(round(p * 100))}%", value=p, variable=ov,
                                command=lambda p=p: self.set_cfg("opacity", p))
        m.add_cascade(label="Opacity", menu=sub)
        pal, tv = self._palette_menu(m)
        m.add_cascade(label="Color palette", menu=pal)
        sv = tk.BooleanVar(value=winapi.get_autostart())
        m.add_checkbutton(label="Start with Windows", variable=sv, command=self.toggle_autostart,
                          state="normal" if updater.app_dir() else "disabled")
        m.add_separator()
        if self.update_rel:
            m.add_command(label=f"Install update {self.update_rel.tag}...", command=self.offer_update)
        m.add_command(label="Check for updates", command=lambda: self.check_updates(manual=True))
        av = tk.BooleanVar(value=bool(self.cfg.get("auto_update", True)))
        m.add_checkbutton(label="Check for updates automatically", variable=av,
                          command=lambda: self.set_cfg("auto_update", not self.cfg.get("auto_update", True)))
        m.add_command(label="Open settings folder", command=lambda: self._open(data_dir()))
        m.add_separator()
        m.add_command(label="Exit (apps keep running)", command=self.quit)
        self._menu_vars = (ov, tv, sv, av)
        self._menu_open = True
        self._cancel_collapse()
        self.tip.hide()
        m.bind("<Unmap>", lambda _e: self._menu_closed())
        winapi.foreground(self.root.winfo_id())
        try:
            m.tk_popup(e.x_root + 2, e.y_root + 2)
        finally:
            m.grab_release()
            if winapi.IS_WIN:
                self._menu_closed()

    def _menu_closed(self) -> None:
        self.root.after(300, lambda: setattr(self, "_menu_open", False))

    def _palette_menu(self, parent):
        th = self.th
        sub = tk.Menu(parent, tearoff=0, bg=th["bg"], fg=th["fg"], activebackground=th["glow"],
                      activeforeground=th["fg"], font=self.f_small)
        tv = tk.StringVar(value=self.cfg["theme"])
        self._swatches = []
        group = None
        for key, name, grp, col in themes.PALETTES:
            if grp != group:
                group = grp
                sub.add_command(label=f"-- {grp.upper()} --", state="disabled", font=self.f_small)
            sw = self._swatch(col)
            self._swatches.append(sw)
            sub.add_radiobutton(label=f" {name}  ", image=sw, compound="left", value=key, variable=tv,
                                font=self.f_mid, background=col["bg"], foreground=col["fg"],
                                activebackground=col["glow"], activeforeground=col["fg"],
                                selectcolor=col["fg"], command=lambda k=key: self.set_cfg("theme", k))
        return sub, tv

    def _swatch(self, col: dict) -> tk.PhotoImage:
        h = max(12, self.f_mid.metrics("linespace") - 6)
        w = h * 3
        im = tk.PhotoImage(master=self.root, width=w, height=h)
        im.put(col["dim"], to=(0, 0, w, h))
        im.put(col["bg"], to=(1, 1, w - 1, h - 1))
        bw = (w - 4 * 3) // 3
        for i, c in enumerate((col["fg"], col["mid"], col["warn"])):
            x0 = 3 + i * (bw + 3)
            im.put(c, to=(x0, 3, x0 + bw, h - 3))
        return im

    def set_cfg(self, key: str, value) -> None:
        self.cfg[key] = value
        self.save()
        if key == "opacity":
            self._set_alpha()
        self._render()

    def toggle_autostart(self) -> None:
        where = updater.app_dir()
        if not where:
            return
        on = not winapi.get_autostart()
        winapi.set_autostart(f'"{where / updater.EXE}"' if on else None)

    def open_apps_folder(self) -> None:
        root = installer.apps_root()
        root.mkdir(parents=True, exist_ok=True)
        self._open(root)

    def _open(self, folder: Path) -> None:
        try:
            if winapi.IS_WIN:
                os.startfile(str(folder))
            else:
                webbrowser.open(Path(folder).as_uri())
        except OSError:
            pass

    # ---------------------------------------------------- self-updating
    @staticmethod
    def _version_label() -> str:
        return f"v{VERSION}" if updater.parse_version(VERSION) else "(from source)"

    def _report_last_update(self) -> None:
        try:
            result = updater.take_result()
        except OSError:
            return
        if result == "fail":
            self.root.after(800, lambda: self._dialog(
                "UPDATE FAILED", "The last launcher update didn't install, so the old version was kept.",
                [("OK", None)]))

    def _auto_check(self) -> None:
        self.root.after(UPDATE_CHECK_MS, self._auto_check)
        if self.cfg.get("auto_update", True) and updater.parse_version(VERSION) and not self.update_busy:
            self.check_updates(manual=False)

    def check_updates(self, manual: bool) -> None:
        def work():
            try:
                self.q.put(("checked", updater.latest_release(), manual, None))
            except Exception as e:
                self.q.put(("checked", None, manual, str(e) or "UPDATE CHECK FAILED"))
        threading.Thread(target=work, daemon=True).start()

    def _checked(self, rel, manual: bool, err) -> None:
        mine = updater.parse_version(VERSION)
        if err:
            if manual:
                self._dialog("UPDATE CHECK", err, [("OK", None)])
        elif rel and mine and updater.is_newer(rel.version, mine):
            self.update_rel = rel
            if manual:
                self.offer_update()
        elif manual:
            msg = (f"Up to date ({self._version_label()})." if mine else
                   f"Running from source; latest release is {rel.tag if rel else 'none yet'} (git pull).")
            self._dialog("UPDATE CHECK", msg, [("OK", None)])

    def offer_update(self) -> None:
        rel = self.update_rel
        if rel is None or self.update_busy:
            return
        where = updater.app_dir()
        problem = updater.location_problem(where) if where else "Running from source: use git pull."
        if problem or not rel.asset_url:
            self._dialog("CAN'T UPDATE HERE", problem or f"{rel.tag} has no download yet; try again soon.",
                         [("DOWNLOAD PAGE", lambda: webbrowser.open(rel.page_url)), ("OK", None)])
            return
        self._dialog(f"UPDATE {rel.tag} AVAILABLE",
                     f"You have {self._version_label()}. The launcher will download the update, close, "
                     "swap in the new files and reopen. Your apps keep running.",
                     [("INSTALL", self._start_download), ("WHAT'S NEW", lambda: webbrowser.open(rel.page_url)),
                      ("LATER", None)])

    def _start_download(self) -> None:
        rel = self.update_rel
        if rel is None or self.update_busy:
            return
        self.update_busy = "DOWNLOADING 0%"
        stage = updater.staging_dir()

        def work():
            try:
                stage.mkdir(parents=True, exist_ok=True)
                z = updater.download(rel, stage / updater.ASSET,
                                     progress=lambda f: self.q.put(("upd_progress", f)))
                self.q.put(("upd_ready", updater.extract(z, stage / "new"), rel))
            except updater.UpdateError as e:
                self.q.put(("upd_failed", str(e)))
            except Exception as e:
                self.q.put(("upd_failed", type(e).__name__.upper()))
        threading.Thread(target=work, daemon=True).start()

    def _install_self(self, new, rel) -> None:
        try:
            bat = updater.write_helper(updater.staging_dir(), updater.app_dir(), new, rel.tag, os.getpid())
            updater.launch_helper(bat)
        except Exception as e:
            self.update_busy = None
            self._dialog("UPDATE FAILED", str(e) if isinstance(e, updater.UpdateError) else type(e).__name__,
                         [("OK", None)])
            return
        self.quit()

    def _dialog(self, title: str, body: str, buttons) -> None:
        if self.dialog:
            self.dialog.close()
        self.dialog = Dialog(self, title, body, buttons)

    def run(self) -> None:
        self.root.mainloop()


class Tip:
    """Hover label for an app button: name, what it is, and what a click will do."""

    def __init__(self, app: App) -> None:
        self.app = app
        self.win: tk.Toplevel | None = None
        self.shown_for = None

    def _text(self, a: AppSpec) -> tuple[str, str, str]:
        app = self.app
        st = app.states.get(a.id, NOT_INSTALLED)
        err = app.errors.get(a.id)
        if err:
            return a.name.upper(), err[0], "late"
        if a.id in app.installing:
            return a.name.upper(), f"INSTALLING {int(app.installing[a.id] * 100)}%", "warn"
        what = {VISIBLE: "running - click to hide", HIDDEN: "hidden - click to show",
                STOPPED: "click to start", NOT_INSTALLED: "click to install"}[st]
        return a.name.upper(), f"{a.blurb} - {what}" if a.blurb else what, "mid"

    def update(self) -> None:
        app = self.app
        target = next((a for a, _x, _y in app.items if a.id == app.hover), None)
        if target is None or app._dragging:
            self.hide()
            return
        th = app.th
        title, line, col = self._text(target)
        if self.win is None:
            self.win = tk.Toplevel(app.root, bg=th["dim"], padx=1, pady=1)
            self.win.overrideredirect(True)
            self.win.attributes("-topmost", True)
            self.inner = tk.Frame(self.win, bg=th["bg"], padx=8, pady=4)
            self.inner.pack()
            self.l1 = tk.Label(self.inner, bg=th["bg"], fg=th["fg"], font=app.f_mid, anchor="w")
            self.l1.pack(fill="x")
            self.l2 = tk.Label(self.inner, bg=th["bg"], fg=th["mid"], font=app.f_small, anchor="w")
            self.l2.pack(fill="x")
            self.win.after(100, lambda: self.win and winapi.set_overlay_styles(self.win.winfo_id(), False))
        self.win.configure(bg=th["dim"])
        self.inner.configure(bg=th["bg"])
        self.l1.configure(text=title, bg=th["bg"], fg=th["fg"])
        self.l2.configure(text=line, bg=th["bg"], fg=th[col])
        if self.shown_for != (target.id, title, line):
            self.shown_for = (target.id, title, line)
            self._place(target)

    def _place(self, target: AppSpec) -> None:
        """Beside the button, on the side facing away from the hub, kept on screen."""
        app, w = self.app, self.win
        w.update_idletasks()
        tw, th_ = w.winfo_reqwidth(), w.winfo_reqheight()
        _a, x, y = next(i for i in app.items if i[0].id == target.id)
        sx, sy = app.ox + x, app.oy + y
        dx, dy = sx - app.hx, sy - app.hy
        r = app.item_r + 6
        if abs(dx) >= abs(dy):
            px = sx + r if dx >= 0 else sx - r - tw
            py = sy - th_ / 2
        else:
            px = sx - tw / 2
            py = sy + r if dy >= 0 else sy - r - th_
        l, t, rr, b = app._area()
        px = min(max(px, l + 2), rr - tw - 2)
        py = min(max(py, t + 2), b - th_ - 2)
        w.geometry(f"+{int(px)}+{int(py)}")

    def hide(self) -> None:
        if self.win is not None:
            self.win.destroy()
            self.win = None
            self.shown_for = None


class Dialog:
    """Small CRT-styled message box next to the hub (no white system dialogs)."""

    def __init__(self, app: App, title: str, body: str, buttons) -> None:
        self.app = app
        th = app.th
        self.win = w = tk.Toplevel(app.root, bg=th["dim"], padx=1, pady=1)
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        inner = tk.Frame(w, bg=th["bg"], padx=12, pady=10, highlightthickness=1, highlightbackground=th["glow"])
        inner.pack(fill="both", expand=True)
        width = max(280, app.f_mid.measure("M") * 34)
        tk.Label(inner, text=title, bg=th["bg"], fg=th["warn"], font=app.f_mid, anchor="w",
                 justify="left").pack(fill="x")
        tk.Label(inner, text=body, bg=th["bg"], fg=th["fg"], font=app.f_small, anchor="w",
                 justify="left", wraplength=width).pack(fill="x", pady=(6, 10))
        row = tk.Frame(inner, bg=th["bg"])
        row.pack(fill="x")
        self._buttons = list(buttons)
        for label, action in buttons:
            b = tk.Label(row, text=f"[ {label} ]", bg=th["bg"], fg=th["mid"], font=app.f_small, cursor="hand2")
            b.pack(side="left", padx=(0, 10))
            b.bind("<Enter>", lambda e, b=b: b.configure(fg=th["fg"], bg=th["glow"]))
            b.bind("<Leave>", lambda e, b=b: b.configure(fg=th["mid"], bg=th["bg"]))
            b.bind("<Button-1>", lambda e, a=action: self._click(a))
        w.bind("<Escape>", lambda e: self.close())
        w.update_idletasks()
        dw, dh = w.winfo_reqwidth(), w.winfo_reqheight()
        l, t, r, b = app._area()
        x = app.hx + app.hub_r + 8 if app.hx + app.hub_r + 8 + dw <= r else app.hx - app.hub_r - 8 - dw
        y = min(max(app.hy - dh // 2, t), b - dh)
        w.geometry(f"+{int(max(l, x))}+{int(y)}")

    def _click(self, action) -> None:
        self.close()
        if action:
            action()

    def close(self) -> None:
        if self.win.winfo_exists():
            self.win.destroy()
        if self.app.dialog is self:
            self.app.dialog = None
