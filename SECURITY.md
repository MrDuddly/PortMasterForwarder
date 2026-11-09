# Security Policy

## Supported versions
Only the latest release receives fixes.

## Reporting a vulnerability
Please **do not open a public issue** for security problems. Use GitHub's *Report a vulnerability* button on the repository's **Security** tab (private vulnerability reporting).
Include the version, how to reproduce the problem and its impact. You will get a response as soon as the maintainers can.

## Things to know
- PortMasterForwarder has **no telemetry** and runs locally. It only contacts the services you enable in *Options* (Steam, Wikipedia/Wikidata, RAWG, Google, Anthropic).
- API keys are stored **in plain text** in `%APPDATA%\PortMasterForwarder\portmasterforwarder.json`. Do not share or commit that file (it is in `.gitignore`).
- The Windows executable is **not code-signed**. Verify downloads with the SHA-256 checksum published on the release page, or build it yourself ([docs/BUILDING.md](docs/BUILDING.md)).
- The app writes only inside the folders you choose on the SD card and never executes downloaded content.
