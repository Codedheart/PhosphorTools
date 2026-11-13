"""Install the apps from their GitHub releases into %LOCALAPPDATA%\\PhosphorTools\\apps\\<id>.

That folder always belongs to the user, so each app's own auto-updater can keep it current
afterwards; the launcher only does the first install (and "Reinstall latest" from its menu).
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from pathlib import Path

from . import updater
from .apps import AppSpec
from .updater import UpdateError


def apps_root() -> Path:
    base = os.environ.get("PHOSPHOR_TOOLS_APPS") or os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
    p = Path(base)
    if not os.environ.get("PHOSPHOR_TOOLS_APPS"):
        p = p / "PhosphorTools" / "apps"
    return p


def folder(app: AppSpec) -> Path:
    return apps_root() / app.id


def exe_path(app: AppSpec) -> Path:
    return folder(app) / app.exe


def installed(app: AppSpec) -> bool:
    return exe_path(app).is_file()


def installed_tag(app: AppSpec) -> str | None:
    try:
        return json.loads((folder(app) / ".phosphor-tools.json").read_text(encoding="utf-8")).get("tag")
    except (OSError, ValueError):
        return None


def install(app: AppSpec, progress=lambda frac: None, latest=None) -> Path:
    """Download the newest release and put it in place. Returns the path of the .exe.

    Safe to repeat: the old copy is only removed once the new one has fully unpacked, and is put
    back if anything goes wrong. Fails with a short message if the app is running (Windows won't
    let its files be replaced) or GitHub can't be reached.
    """
    get = latest or (lambda: updater.latest_release(repo=app.repo, asset=app.asset))
    rel = get()
    if rel is None or not rel.asset_url:
        raise UpdateError(f"NO {app.name.upper()} RELEASE YET")
    root = apps_root()
    root.mkdir(parents=True, exist_ok=True)
    stage = root / f".{app.id}-download"
    shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir(parents=True)
    try:
        z = updater.download(rel, stage / app.asset, progress=progress)
        new = updater.extract(z, stage / "unpacked", app.exe)
        target, old = folder(app), root / f".{app.id}-old"
        shutil.rmtree(old, ignore_errors=True)
        if target.exists():
            try:
                target.rename(old)
            except OSError as e:
                raise UpdateError(f"CLOSE {app.name.upper()} FIRST") from e
        try:
            shutil.move(str(new), str(target))
        except OSError:
            if old.exists() and not target.exists():
                old.rename(target)                   # put the previous copy back
            raise
        (target / ".phosphor-tools.json").write_text(
            json.dumps({"tag": rel.tag, "installed": time.strftime("%Y-%m-%d %H:%M")}), encoding="utf-8")
        shutil.rmtree(old, ignore_errors=True)
        return target / app.exe
    finally:
        shutil.rmtree(stage, ignore_errors=True)
