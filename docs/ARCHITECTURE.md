# Architecture

```
src/portmasterforwarder/
  __init__.py   version
  __main__.py   python -m portmasterforwarder
  app.py        Windows/desktop front-end (tkinter) + main() / --self-test
  padgui.py     handheld front-end (pygame, gamepad + on-screen keyboard) - same core
  core.py       everything that touches the SD card + sources + settings
  meta.py       pure rules: genres, descriptions, ratings, optional AI evaluator
  assets/       icon.ico / icon.png
packaging/      PyInstaller spec, launcher and build script (Windows .exe)
launcher/       roms/tools launcher for Knulli;  scripts/build_release.sh builds the Knulli zip
extras/         optional McpeLauncher.sh
tests/          unit, regression and GUI-smoke tests (standard library only)
```

## Layers

- **meta.py** has no GUI and no file access. Plain functions (`normalize_genre`, `build_description`, `compute_rating`, `ai_evaluate`, `build_metadata`) that are easy to test.
- **core.py** holds platform profiles, settings, game discovery, launchers, `gamelist.xml` editing, system files and the metadata sources. It does not import tkinter.
- **app.py** (tkinter) and **padgui.py** (pygame) only build screens and call `core`; both front-ends share every rule. Network work runs in background threads and reports through a queue polled by the Tk loop.

## Data flow (APPLY)

```
games + per-game state (category, sources, pinned values, image mode)
        |
core.apply_game
   1. write launcher (never overwrites hand-made ones)
   2. plan_fields  -> per block: pinned / keep / auto(fill|replace|keep) / explicit source
   3. collect_sources (Steam, Wikipedia/Wikidata, RAWG, Google)  ->  evidence + facts per source
   4. resolve_field -> meta.build_metadata (genre / description / rating) or facts (date, developer, publisher)
   5. apply pinned values (normalized), write gamelist.xml (+ .bak once), save the screenshot
```

## Per-game state (`DEFAULT_GAME`)

`cat`, `steam_id`, `steam_name`, `steam_checked`, `steam_term`, `meta_mode` (`follow|replace|keep`), `shot_mode` (`auto|web|rawg|local|none`), `shot_idx`, `shot_local`,
`src` (block -> source), `manual` (block -> pinned value). Older keys (`desc`, `rating`, `genre`) are still read.

## Extension points

- **Another emulation system:** add an entry to `core.PROFILES` (device root path, folder layout relative to the card, launch command, system file pattern) and select it with the `profile` setting.
  Untested profiles must be documented as such in `docs/KNULLI.md`.
- **Another metadata source:** add a `*_metadata()` function returning facts plus an `_evidence` dict (`labels`, `texts`, `scores`), register it in `core.SOURCES`, `collect_sources` and the options dialog.
- **Genre/description/rating rules:** edit `meta.py` and add tests in `tests/test_portmasterforwarder.py` (see `GenreTests`, `DescriptionTests`, `RatingTests`).

## Settings

`%APPDATA%\PortMasterForwarder\portmasterforwarder.json` (`~/.config/PortMasterForwarder` on Linux, override with `PORTMASTERFORWARDER_HOME`). Settings from the program folder or older names are imported once.

## Testing

`python -m unittest discover -s tests -v`. Network access is replaced by a fake (`FakeNet`) and the GUI is exercised against a fake `tkinter`, so the suite runs headless on any OS.
