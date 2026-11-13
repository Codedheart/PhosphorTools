# Phosphor Tools

A small round launcher for the Phosphor apps, with the same CRT look and 18 color palettes.
It sits on top of everything as one little circle. Click it and the apps fan out around it.

| App | What it is |
|---|---|
| **Phosphor XP** | EXP / hour overlay |
| **Phosphor Count** | Boss respawn timers |
| **PhosphorWatch** | Twitch stream viewer |

## Download (no Python needed)

**[⬇ Download the latest version](../../releases/latest)**, then grab **`PhosphorTools-windows.zip`**
under *Assets*. Right-click it, **Extract All…**, move the `PhosphorTools` folder somewhere of your
own (Documents or the Desktop), and double-click **`PhosphorTools.exe`**. If Windows says
"Windows protected your PC", click **More info**, then **Run anyway**.

You don't need to download the apps separately: the launcher installs them.

## Using it

| | |
|---|---|
| Click the circle | Open / close the app menu. It opens away from the screen edges: in the bottom-right corner it fans up and to the left, and so on |
| Click an app | **Not installed:** downloads and installs it (a ring fills as it downloads), then starts it. **Closed:** starts it. **Running:** hides it. **Hidden:** shows it again |
| Hover an app | Its name, what it is, and what a click will do |
| Drag the circle | Move it anywhere (it remembers where) |
| Right-click the circle | Apps (install / reinstall, open the apps folder), opacity, color palette, start with Windows, updates, exit |

- The menu folds away by itself a moment after the mouse leaves it.
- A filled dot under an app means it's running; a hollow dot means it's running but hidden.
- Hiding an app doesn't close it: timers keep counting, streams keep playing. **Exit** on the
  launcher shows any hidden apps again (it never leaves them stuck invisible), and the apps keep running.
- Apps started some other way (e.g. from their own zip folder) are recognised and can be hidden too.
- Apps are installed in `%LOCALAPPDATA%\PhosphorTools\apps`, a folder that always belongs to you, so
  each app's own auto-updater keeps it current. **Reinstall** in the right-click menu fetches the
  latest version if one ever gets stuck.
- The launcher updates itself the same way the apps do (right-click > **Check for updates**).

Settings are in `%APPDATA%\PhosphorTools\config.json`.

## Adding another app

Add one entry to `APPS` in [`phosphor/apps.py`](phosphor/apps.py): its name, GitHub repo, release zip
name, `.exe` name and an 11x9 pixel icon. The app's releases need the same layout as the others
(`<Name>-windows.zip` containing `<Name>/<Name>.exe`). The radial menu makes room automatically.

## Run from source / build

Needs Python 3.10+ (standard library only). Double-click **`run.bat`**. To make the no-Python zip,
push a tag like `v1.0` (GitHub builds and publishes it) or run **`build.bat`**.

Tests: `python -m pytest -q tests`

## Credits

VT323 font by Peter Hull, SIL Open Font License (downloaded at build time).
