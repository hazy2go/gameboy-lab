#!/bin/sh
# Double-click on a Mac: ClaudeBoy's bridge for a Game Boy on the gb-link-usb Pico.
cd "$(dirname "$0")"
[ -d .venv ] || { echo "First run: installing the bridge (one minute)..."; make .venv || exit 1; }
make bridge
echo; echo "Bridge stopped. Press Enter to close."; read _
