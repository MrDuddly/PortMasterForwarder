#!/bin/bash
# Builds dist/PortMasterForwarder-<version>-knulli.zip
# The zip holds a "roms" folder: copy it onto the SHARE partition of your SD card (merge folders).
set -e
cd "$(dirname "$0")/.."
VER=$(python3 -c "import re;print(re.search(r'\"([^\"]+)\"',open('src/portmasterforwarder/__init__.py').read().split('__version__')[1]).group(1))")
OUT=dist/stage; rm -rf dist; mkdir -p $OUT/roms/tools/PortMasterForwarder/extras
cp launcher/PortMasterForwarder.sh $OUT/roms/tools/
cp -r src/portmasterforwarder $OUT/roms/tools/PortMasterForwarder/
cp LICENSE $OUT/roms/tools/PortMasterForwarder/
cp extras/McpeLauncher.sh $OUT/roms/tools/PortMasterForwarder/extras/
# the handheld edition needs neither the desktop (tkinter) front-end nor the Windows icon
rm -f $OUT/roms/tools/PortMasterForwarder/portmasterforwarder/app.py $OUT/roms/tools/PortMasterForwarder/portmasterforwarder/assets/icon.ico
find $OUT -name __pycache__ -prune -exec rm -rf {} +
chmod +x $OUT/roms/tools/PortMasterForwarder.sh
( cd $OUT && zip -qr "../PortMasterForwarder-$VER-knulli.zip" roms )
( cd dist && sha256sum "PortMasterForwarder-$VER-knulli.zip" > "PortMasterForwarder-$VER-knulli.zip.sha256" )
rm -rf $OUT
echo "Built dist/PortMasterForwarder-$VER-knulli.zip"
