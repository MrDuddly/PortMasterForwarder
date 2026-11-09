# Changelog

All notable changes are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [1.3.0]
### Added
- **Gamepad edition**: a pygame interface that runs on the handheld from `roms/tools` and is driven by the console buttons (on-screen keyboard, categories, presets,
  per-block sources, fetch / pin / clear, save a single game). Built as `PortMasterForwarder-<version>-knulli.zip` (`scripts/build_release.sh`).
- Category folders created by hand (for example `portandroid`) are discovered automatically; hand-made shortcuts count as categorized and are never overwritten.
- Nintendo 3DS in the icon list; EmulationStation is reloaded after APPLY on the handheld.
- `python -m portmasterforwarder --gamepad | --desktop`; `docs/GAMEPAD.md` and a Portuguese README.
- Gamepad UI: 8-bit CRT look in the logo's colors (pixel borders, scanlines), game image preview next to the list, button guide at the bottom,
  left analog stick navigation, fullscreen forced on Linux handhelds.
- **Saving a single game rewrites existing metadata** with the values you typed or fetched (global APPLY still only fills gaps).
- Edit a category's **name and icon** (Menu > Edit categories); the folder never changes, so shortcuts keep working.
### Fixed
- Crash when creating a category with **X**; a failed background job no longer reports "Applied" and **B** cancels a stuck job.
- On-screen keyboard overflow on narrow screens (accented letters added); the game screen scrolls on small screens; `gamelist.xml` is no longer re-parsed every frame.
### Changed
- Both editions share one `core.py`/`meta.py`. The MCPE launcher now lives in `extras/`.
- The release workflow publishes the Windows `.exe` and the Knulli zip together.

## [1.2.0]
First public release, published as **PortMasterForwarder** (during private development the tool was called "Knulli Categorias" and later "PortForwarder").
### Added
- One shortcut per MCPE Launcher version found in `roms/ports/mcpe_launcher/versions/` (option "One shortcut per MCPE version"). Needs a McpeLauncher.sh that accepts the version as its first argument. Not verified on hardware.
- Standalone Windows executable (`PortMasterForwarder.exe`) with `--version` and `--self-test` flags, built by a GitHub Actions workflow.
- Project logo, application icon and Windows version information.
- Clear independence notice: the project is **not affiliated with the PortMaster project** (README, About window, footer, `docs/INDEPENDENCE.md`).
- *Tested on Knulli only* notice in the app and the documentation.
- Open-source repository layout (`src/portmasterforwarder` package, tests, docs, CI and release workflows) under the MIT license.
- Inline block editor (one block per metadata field with its own source, *Fetch* button and your own value) with a live preview; presets; "+ New category...".
- Standardized genres (exactly one of 15), gameplay-only English descriptions, multi-signal ratings and an optional AI evaluation.
- Platform profiles (`PROFILES`) so other EmulationStation-based systems can be added; Knulli is the default.
### Compatibility with earlier private builds
- Settings from `portforwarder.json` / `knulli_categorias.json` (next to the program or in `%APPDATA%\\PortForwarder`) are imported once.
- Launchers and system files created by earlier builds are recognized, so *Undo everything* still removes them.
