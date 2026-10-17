#!/usr/bin/env bash
# install.sh — installs Dédalo and creates the dynamic shortcut

set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$DIR/.venv"

# Own virtual environment: avoids the "externally-managed-environment"
# error (PEP 668) of modern distros when installing with the system pip.
if [ ! -x "$VENV/bin/python" ]; then
    echo "Creating virtual environment at $VENV ..."
    if ! python3 -m venv "$VENV"; then
        echo >&2 "Could not create the virtual environment."
        echo >&2 "On Debian/Ubuntu the package is missing; install it with:"
        echo >&2 "    sudo apt install python3-venv"
        exit 1
    fi
fi

echo "Installing Dédalo in editable mode (with MCP support)..."
"$VENV/bin/python" -m pip install --quiet --upgrade pip >/dev/null 2>&1 || true
"$VENV/bin/python" -m pip install -e "$DIR[mcp]" 2>&1 | tail -15

echo -e "\nCreating dynamic shortcut..."
# The desktop shortcut is optional: if it fails (e.g. without a user
# desktop), it must not abort an installation that already completed fine.
if ! bash "$DIR/dedalo/acceso.sh" 2>&1 | tail -10; then
    echo "(Note: the shortcut was not created; run ./lanzar.sh directly)"
fi

echo -e "\nDone!"
echo "- Desktop: ~/Escritorio/dedalo.desktop"
echo "- Launcher: ~/.local/bin/dedalo"
echo "- Quick run: cd $DIR && ./lanzar.sh"
