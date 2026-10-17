#!/usr/bin/env bash
# Launcher for the Dédalo panel.
#
# It self-locates: resolves its own real path (following symlinks) and does
# not depend on the project location or a specific venv. Survives moving or
# renaming the folder and switching the Python interpreter.
set -euo pipefail

# Real location of this script. `readlink -f` is GNU: it does not exist on
# macOS (BSD), so we resolve symlinks by hand and end up with an absolute path.
ORIGEN="${BASH_SOURCE[0]:-$0}"
while [ -L "$ORIGEN" ]; do
    _dest="$(readlink "$ORIGEN")"
    case "$_dest" in
        /*) ORIGEN="$_dest" ;;
        *) ORIGEN="$(cd "$(dirname "$ORIGEN")" && pwd)/$_dest" ;;
    esac
done
ORIGEN="$(cd "$(dirname "$ORIGEN")" && pwd)/$(basename "$ORIGEN")"
PROYECTO="$(dirname "$ORIGEN")"

# ── Find a Python with PySide6 (the first working one wins) ─────────────
PYTHON=""
for p in \
    "$PROYECTO/.venv/bin/python" \
    "$PROYECTO/venv/bin/python" \
    "$PROYECTO/../.venv/bin/python" \
    "$PROYECTO/../venv/bin/python" \
    "$(command -v python3)" \
; do
    [ -n "$p" ] && [ -x "$p" ] || continue
    if "$p" -c 'import PySide6' >/dev/null 2>&1; then
        PYTHON="$p"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo "Dédalo: no Python with PySide6 installed was found." >&2
    echo "Install it with:  bash \"$PROYECTO/install.sh\"" >&2
    exit 1
fi

cd "$PROYECTO"
exec "$PYTHON" -m dedalo