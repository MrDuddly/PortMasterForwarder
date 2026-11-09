# Third-party notices

PortMasterForwarder itself is released under the [MIT License](LICENSE). It uses or interacts with the following third-party components and services.

## Bundled in the Windows executable
| Component | License | Notes |
|---|---|---|
| [Python](https://www.python.org/) and its standard library (including Tcl/Tk) | PSF License; Tcl/Tk BSD-style license | Runtime of the executable |
| [Pillow](https://python-pillow.org/) | HPND (Historical Permission Notice and Disclaimer) | Image resizing and thumbnails |
| [PyInstaller](https://pyinstaller.org/) | GPL-2.0-or-later with a special exception that allows bundled applications to use any license | Build tool; its bootloader is embedded in the executable |

Please consult each project's own license text for the exact terms.

## Referenced but not included
- **[pygame](https://www.pygame.org/)** (LGPL-2.1) is used by the gamepad edition on the handheld. It is provided by Knulli or by PortMaster's `pylibs`; PortMasterForwarder does not bundle or modify it.
- **[Art Book Next](https://github.com/anthonycaccese/art-book-next-es)** theme by Anthony Caccese, licensed **CC BY-NC-SA 2.0**. PortMasterForwarder **does not include or redistribute any theme files**;
  it only contains a list of the theme's icon identifiers (names such as `gc`, `steam`, `ps2`) so that you can pick them for your categories. Obtain the theme from its own repository and follow its license.
- **Knulli, Batocera and EmulationStation** are separate projects; PortMasterForwarder only writes files in the formats they read.
- **PortMaster** is a separate project that PortMasterForwarder has **no affiliation with** (see [docs/INDEPENDENCE.md](docs/INDEPENDENCE.md)). No PortMaster code or assets are included.

## Online services (optional)
Using a service means you accept *its* terms; PortMasterForwarder is not affiliated with any of them.
- **Steam** (Valve): store data and images belong to their publishers and Valve. Used for personal library metadata only.
- **Wikipedia / Wikidata** (Wikimedia): article text is available under CC BY-SA 4.0 and Wikidata under CC0. Sentences taken from Wikipedia are shortened and filtered; if you republish
  game lists that contain them, credit Wikipedia accordingly.
- **RAWG**: requires attribution (a link back to rawg.io) when its data is shown publicly, and a free API key.
- **Google Programmable Search**: requires your own API key and is subject to Google's terms and quotas.
- **Anthropic API**: optional AI evaluation with your own API key; collected source texts are sent to the service you configure.

## Trademarks
Steam, Nintendo, GameCube, Wii, PlayStation, Anbernic, Knulli, Batocera, PortMaster, Google, Anthropic and other names are trademarks or names of their owners and are used only to describe compatibility.
The project logo and application icon were supplied by the project owner and are distributed with the project under the MIT License.
