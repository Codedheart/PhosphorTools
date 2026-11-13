"""Settings persisted as JSON in %APPDATA%\\PhosphorTools (or ~/.phosphortools)."""
from __future__ import annotations

import json
import os
from pathlib import Path

APP_NAME = "Phosphor Tools"


def data_dir() -> Path:
    base = os.environ.get("PHOSPHOR_TOOLS_DATA")
    if base:
        p = Path(base)
    elif os.name == "nt":
        p = Path(os.environ.get("APPDATA", Path.home())) / "PhosphorTools"
    else:
        p = Path.home() / ".phosphortools"
    p.mkdir(parents=True, exist_ok=True)
    return p


DEFAULTS: dict = {
    "x": 120,                     # hub centre, screen pixels
    "y": 120,
    "opacity": 0.95,
    "theme": "green",             # see phosphor/themes.py
    "auto_update": True,          # check GitHub for a newer launcher at startup / every few hours
    "hidden": {},                 # app id -> {"pid": n, "hwnds": [...]}: windows we hid, to restore
}


class Config(dict):
    def __init__(self) -> None:
        super().__init__(json.loads(json.dumps(DEFAULTS)))
        self.path = data_dir() / "config.json"
        try:
            saved = json.loads(self.path.read_text(encoding="utf-8"))
            for k, v in saved.items():
                if k in DEFAULTS:
                    self[k] = v
        except (OSError, ValueError):
            pass

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self, indent=2), encoding="utf-8")
        tmp.replace(self.path)
