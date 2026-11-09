# Releasing

1. Update `__version__` in `src/portmasterforwarder/__init__.py` and add a section for it in `CHANGELOG.md` (a test checks that both agree).
2. Run `python -m unittest discover -s tests` and `ruff check src tests`.
3. Commit, then tag and push:
   ```bash
   git tag v1.2.0
   git push origin main --tags
   ```
4. The **Release** workflow builds `PortMasterForwarder.exe`, runs `--self-test`, and publishes the executable plus its SHA-256 checksum on the GitHub release page.
5. Open the release, check the generated notes, and download the exe once on a clean Windows machine before announcing it.

## First-time repository setup

- Create the repository, push the code, and set the description and topics (`knulli`, `emulationstation`, `portmaster`, `retro-handheld`).
- Add the CI badge to `README.md` if you like: `https://github.com/<user>/<repo>/actions/workflows/ci.yml/badge.svg`.
- Enable *Private vulnerability reporting* (Settings > Code security) so that [SECURITY.md](../SECURITY.md) works.
- Keep the *Tested on Knulli only* notice until other platforms are verified by someone with the hardware.
