# Contributing to PortMasterForwarder

Thanks for helping! PortMasterForwarder is small, open source (MIT) and **tested on Knulli only**, so reports from other setups are especially valuable.

> PortMasterForwarder is an **independent** project and is **not affiliated with PortMaster**. Please report problems with this tool here, not to the PortMaster team.

## Ways to help
- **Compatibility reports** for other firmware or devices (use the *Compatibility report* issue template). Please include what worked and what did not.
- Bug reports and feature ideas (use the issue templates).
- Code, tests and documentation improvements.

## Development setup
```bash
git clone <repository-url>
cd PortMasterForwarder
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v      # run the tests (no network needed)
ruff check src tests                         # lint
PYTHONPATH=src python -m portmasterforwarder       # run the app (Windows: run_from_source.bat)
```
Python 3.9 or newer. The only runtime dependency is Pillow; keep it that way unless there is a strong reason.

## Guidelines
- **Everything user-facing is English** (UI text, messages, documentation, generated metadata). A test enforces this.
- **Never silently overwrite user data.** New features that write to the SD card must keep the *fill / replace / keep* semantics, back up what they change and be reversible.
- **Do not invent metadata.** If a value cannot be built from reliable evidence, leave it empty.
- Keep logic in `core.py` / `meta.py` and screens in `app.py`. New behavior needs tests; network calls are faked in the tests (see `FakeNet`).
- Be honest in the docs: describe what you tested. Do not claim support for hardware you did not test.
- Keep changes focused, update `CHANGELOG.md`, and make sure CI passes.

## Adding things
- A new **metadata source**, **platform profile** or **genre rule**: see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [docs/METADATA_RULES.md](docs/METADATA_RULES.md).
- A new **platform profile** must be marked *untested* in [docs/KNULLI.md](docs/KNULLI.md) until someone with the hardware verifies it.

## Pull requests
1. Fork and create a branch.
2. Add or update tests, run the test-suite and `ruff`.
3. Describe what changed and how you tested it (including the device/firmware, if relevant).

By contributing you agree that your contributions are licensed under the [MIT License](LICENSE).
