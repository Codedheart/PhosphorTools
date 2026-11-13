"""Phosphor Tools - a small round launcher for the Phosphor apps."""
import sys
import traceback


def _fatal(msg: str) -> None:
    try:
        import tkinter
        from tkinter import messagebox
        r = tkinter.Tk()
        r.withdraw()
        messagebox.showerror("Phosphor Tools", msg)
        r.destroy()
    except Exception:
        print(msg, file=sys.stderr)


def main() -> int:
    if sys.version_info < (3, 10):
        _fatal("Phosphor Tools needs Python 3.10 or newer (this is %d.%d)." % sys.version_info[:2])
        return 1
    from phosphor import winapi
    if not winapi.single_instance("PhosphorTools.Launcher"):
        return 0                       # already running: one hub is enough
    try:
        from phosphor.ui import App
        App().run()
    except Exception:
        from phosphor.config import data_dir
        (data_dir() / "error.log").write_text(traceback.format_exc(), encoding="utf-8")
        _fatal("Phosphor Tools crashed:\n\n" + traceback.format_exc(limit=3))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
