"""The apps the launcher knows about.

To add an app: append an AppSpec below. It needs a GitHub repo whose releases carry
<Name>-windows.zip with <Name>/<Name>.exe inside (the layout every Phosphor app's build uses),
and an 11x9 pixel icon ('#' = palette colour, '.' = empty). Nothing else in the launcher changes:
the radial menu makes room for however many apps there are.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AppSpec:
    id: str            # short, stable: used for its install folder and in config.json
    name: str          # shown in the launcher
    repo: str          # GitHub "owner/repo" to install from
    asset: str         # release zip name
    exe: str           # program inside the zip
    icon: tuple        # 11 x 9 pixel art
    blurb: str = ""    # one line, shown on hover


_XP_ICON = (".........##",            # rising bars: EXP per hour
            ".........##",
            "......##.##",
            "......##.##",
            "...##.##.##",
            "...##.##.##",
            "##.##.##.##",
            "##.##.##.##",
            "###########")

_COUNT_ICON = ("###########",          # hourglass: respawn timers
               ".#.......#.",
               "..#.....#..",
               "...#.#.#...",
               ".....#.....",
               "...#...#...",
               "..#..#..#..",
               ".#..###..#.",
               "###########")

_WATCH_ICON = ("###########",          # screen with a play button: stream viewer
               "#.........#",
               "#...#.....#",
               "#...###...#",
               "#...#####.#",
               "#...###...#",
               "#...#.....#",
               "###########",
               "...#####...")

APPS: list[AppSpec] = [
    AppSpec("xp", "Phosphor XP", "Codedheart/PhosphorXP", "PhosphorXP-windows.zip", "PhosphorXP.exe",
            _XP_ICON, "EXP / hour overlay"),
    AppSpec("count", "Phosphor Count", "Codedheart/PhosphorCount", "PhosphorCount-windows.zip",
            "PhosphorCount.exe", _COUNT_ICON, "Boss respawn timers"),
    AppSpec("watch", "PhosphorWatch", "Codedheart/PhosphorWatch", "PhosphorWatch-windows.zip",
            "PhosphorWatch.exe", _WATCH_ICON, "Twitch stream viewer"),
]

BY_ID = {a.id: a for a in APPS}
