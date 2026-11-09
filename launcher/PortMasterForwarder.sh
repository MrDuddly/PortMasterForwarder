#!/bin/bash
# PortMasterForwarder - gamepad GUI for Knulli (put this file + the PortMasterForwarder folder in roms/tools)
XDG_DATA_HOME=${XDG_DATA_HOME:-$HOME/.local/share}
DIR="$(cd "$(dirname "$0")" && pwd)/PortMasterForwarder"
export PORTMASTERFORWARDER_HOME="$DIR/data"
export PYTHONPATH="$DIR:$PYTHONPATH"
export PYTHONDONTWRITEBYTECODE=1
export SDL_GAMECONTROLLERCONFIG_FILE="${SDL_GAMECONTROLLERCONFIG_FILE:-/userdata/system/gamecontrollerdb.txt}"
mkdir -p "$DIR/data"
# keep the log small
[ -f "$DIR/data/log.txt" ] && [ "$(stat -c %s "$DIR/data/log.txt" 2>/dev/null || echo 0)" -gt 1000000 ] && : > "$DIR/data/log.txt"
# PortMaster ships its own pygame; use it if the system python has none
PM="/userdata/roms/ports/PortMaster"
[ -d "$PM/pylibs" ] && export PYTHONPATH="$PYTHONPATH:$PM/pylibs"
PY=python3
if ! $PY -c "import pygame" 2>/dev/null; then
  for p in /userdata/system/python*/bin/python3 /usr/bin/python3; do [ -x "$p" ] && $p -c "import pygame" 2>/dev/null && PY=$p && break; done
fi
if ! $PY -c "import pygame" 2>/dev/null; then echo "pygame not found" >> "$DIR/data/log.txt"; exit 1; fi
exec $PY -m portmasterforwarder --gamepad >> "$DIR/data/log.txt" 2>&1
