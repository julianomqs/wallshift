# wallshift

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

*[Leia isto em português](README.md)*

Minimalist wallpaper changer for **KDE Plasma**, using Windows Spotlight
images as its source. Built to replace Variety without the weight of a full
GUI application.

Exclusive to KDE Plasma on Debian: there is no desktop-environment detection
nor support for other DEs.

## Installation

One-liner, no manual cloning (it self-clones into
`~/.local/share/wallshift`):

```bash
curl -fsSL https://raw.githubusercontent.com/julianomqs/wallshift/master/install.sh | bash
```

Or clone first:

```bash
git clone https://github.com/julianomqs/wallshift.git ~/.local/share/wallshift
cd ~/.local/share/wallshift
./install.sh
```

It's safe to re-run `install.sh` at any time (it won't overwrite the
config or duplicate autostart). `install.sh`:
1. Installs whatever is missing via `apt` (`pipx`, `qdbus-qt6`, `python3-gi`,
   `gir1.2-ayatanaappindicator3-0.1`), if needed.
2. Installs the package with `pipx install --system-site-packages .` (the
   `--system-site-packages` flag is required so the tray icon can see the
   system's `gi`/GTK bindings).
3. Creates `~/.config/wallshift/config.toml` from `config.default.toml`
   (does not overwrite an existing config).
4. Registers autostart at `~/.config/autostart/wallshift.desktop`, unless
   `autostart = false` in config.toml (autostart points at `wallshift-tray`,
   with a tray icon).

## Uninstallation

```bash
~/.local/share/wallshift/uninstall.sh
```

(or via the tray icon's "Desinstalar" menu item, which runs the same script)

Removes the package (via `pipx uninstall`), the autostart entry, the
`config.toml`, and the image cache. System dependencies (`pipx`,
`qdbus-qt6`) are **not** removed, since they may be used by other
applications or be part of KDE Plasma itself.

## Configuration

File: `~/.config/wallshift/config.toml`

| Key | Default | Description |
|---|---|---|
| `interval_minutes` | `30` | interval between wallpaper changes |
| `autostart` | `true` | controls whether `install.sh` registers autostart in Plasma |
| `cache_dir` | `~/.cache/wallshift` | folder where downloaded images are kept |
| `max_cache_images` | `20` | maximum number of images kept in the cache |
| `country` / `locale` | `US` / `en-US` | region used when querying the Spotlight API |

## Usage

```bash
wallshift          # starts the headless loop (changes wallpaper every interval_minutes)
wallshift --once   # changes the wallpaper once and exits (good for testing)
wallshift-tray      # same loop, with a tray icon in Plasma
```

`wallshift-tray` is what autostart uses by default. The icon (a simple
landscape glyph, original color scheme) sits in the tray with a menu:

- **Próximo** ("Next") - changes the wallpaper right away, without waiting
  for the interval.
- **Desinstalar** ("Uninstall") - asks for confirmation and, if confirmed,
  runs `uninstall.sh` and closes the icon.
- **Sair** ("Quit") - closes the process (does not uninstall anything).

Logs are plain `print()` calls with a timestamp, straight to stdout - run it
in a terminal or redirect to a file if you want to keep history.

## How it works

- **`wallshift/source_spotlight.py`**: queries the Windows Spotlight v4 API
  (`fd.api.iris.microsoft.com`), used by Windows 11 for lockscreen and
  wallpaper (images up to 4K). The endpoint and parameters were confirmed
  against the
  [ORelio/Spotlight-Downloader](https://github.com/ORelio/Spotlight-Downloader/blob/master/SpotlightAPI.md)
  project's documentation. This API isn't officially documented by
  Microsoft and may change without notice - so any failure here is caught
  and logged, never crashes the process.
- **`wallshift/cache.py`**: downloads the chosen image into `cache_dir` and
  keeps at most `max_cache_images` files, deleting the oldest ones.
- **`wallshift/setter.py`**: applies the wallpaper by running a script
  against the `plasmashell` scripting API (`org.kde.PlasmaShell.evaluateScript`
  via `qdbus6`/`qdbus`) - the same mechanism Plasma itself uses internally
  to change wallpaper.
- **`wallshift/main.py`**: main loop (headless); the config file is re-read
  on every cycle, so editing `config.toml` (interval, cache dir, etc.)
  takes effect on the next cycle without restarting the process. If any
  step fails (network down, plasmashell not running, etc.), the error is
  logged and the current wallpaper is left untouched until the next cycle.
- **`wallshift/tray.py`**: tray icon via GTK3 + AyatanaAppIndicator3
  (StatusNotifierItem) - reuses the same `run_once` from `main.py`, just
  swapping the blocking call for a thread + `GLib.idle_add` so the icon
  never freezes.
- **`wallshift/notify.py`**: native notifications via D-Bus
  (`org.freedesktop.Notifications`), used by the tray to report success or
  failure.

## Tested on

- **Actually tested**: Debian 13 (trixie), KDE Plasma 6, using `qdbus6`
  (`qdbus-qt6` package) - installation, API fetch, download, and wallpaper
  change all confirmed on this environment.
- **Should work, not tested**: Debian 12 (bookworm) with KDE Plasma 5, using
  `qdbus` (`setter.py` already tries `qdbus6` first and falls back to
  `qdbus`, and the `evaluateScript` method has existed since Plasma 5).
- **Out of scope**: any desktop environment other than KDE Plasma (GNOME,
  XFCE, etc.) - no DE detection or fallback, by design.

## Known limitations

- The Spotlight API is unofficial (reverse-engineered); changes to
  Microsoft's response format may break `source_spotlight.py` without
  warning.
- No graphical configuration UI: edit `config.toml` directly - most
  settings take effect on the next cycle automatically, without a restart.
