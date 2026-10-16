#!/usr/bin/env bash
# build_windows.sh — packages Dédalo for Windows and runs the smoke test
# of the binary (the GUI starts, and `--dedalo-loop` mode runs the packaged
# python engine and returns its exit code).
#
# Outputs (in packaging/out/):
#   dedalo/                   onedir (dedalo.exe + libs)
#   dedalo-<v>-win64.zip      portable (unzip and run)
#
# Usage:
#   bash packaging/build_windows.sh
#
# Requires Windows with Git Bash (e.g. the windows-latest GitHub Actions
# runner) and python with the project + PyInstaller.
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RAIZ"

PY="${PYTHON:-python}"
VERSION="$("$PY" -c '
import sys
sys.stdout = sys.stdout or open("NUL", "w")  # binario windowed: stdout may be None
import tomllib
from pathlib import Path
with open(Path("pyproject.toml"), "rb") as f:
    print(tomllib.load(f)["project"]["version"])
')"

OUT="$RAIZ/packaging/out"
NOMBRE="dedalo"
APP="$OUT/$NOMBRE"

echo "==> PyInstaller v$VERSION"
rm -rf "$OUT" build
"$PY" -m PyInstaller \
    --clean --noconfirm --distpath "$OUT" --workpath "$OUT/build" \
    packaging/"$NOMBRE".spec
[ -x "$APP/$NOMBRE.exe" ] || { echo "el binario no salió en $APP" >&2; exit 1; }

# ── Smoke 1: the GUI starts and is still alive at 6 s ─────────────────────────
echo "==> smoke GUI (offscreen)"
QT_QPA_PLATFORM=offscreen "$APP/$NOMBRE.exe" &
SMOKE=$!
sleep 6
if ! kill -0 "$SMOKE" 2>/dev/null; then
    wait "$SMOKE" || true
    echo "el binario murió al arrancar (GUI)" >&2
    exit 1
fi
(cmd //c "taskkill /F /PID $SMOKE" 2>/dev/null || kill "$SMOKE" 2>/dev/null || true) || true
# After the kill, a 10 s cap: if the GUI does not die, fail now (a blocking
# `wait` would turn any regression into a hung 6 h job).
for _i in 1 2 3 4 5 6 7 8 9 10; do
    kill -0 "$SMOKE" 2>/dev/null || break
    sleep 1
done
if kill -0 "$SMOKE" 2>/dev/null; then
    cmd //c "taskkill /F /IM $NOMBRE.exe" 2>/dev/null || true
    echo "la GUI no responde al kill tras 10 s" >&2
    exit 1
fi
wait "$SMOKE" 2>/dev/null || true

# ── Smoke 2: the packaged engine via `--dedalo-loop` ───────────────────────
# With a deliberately nonexistent agent the run aborts BEFORE touching the
# network/git/gate (script's order): rc 2 and the log documents the reason.
# This validates the PyInstaller entrypoint branch and that the engine runs
# in the windowed exe (its prints go to devnull, not to a nonexistent console).
echo "==> smoke motor (--dedalo-loop)"
SMOKE_DIR="$OUT/smoke_loop"
rm -rf "$SMOKE_DIR"
mkdir -p "$SMOKE_DIR"
printf '# PLAN\n\n- [ ] t1\n' > "$SMOKE_DIR/plan.md"
# PowerShell with a 120 s cap: the process is launched and waited with WaitForExit;
# if the binary hangs (e.g. an encoding regression) the job fails within
# minutes with rc 124 instead of sitting 6 h until GitHub's timeout.
# Note: RC is captured OUTSIDE the subshell: inside it does not propagate to
# the parent.
set +e
CLI_OPENCODE=/no/existe/opencode AGENTE_TAREA=opencode \
EXE="$APP/$NOMBRE.exe" SMOKE_LOOP_DIR="$SMOKE_DIR" \
powershell -NoProfile -Command '
    $p = Start-Process -FilePath $env:EXE -ArgumentList "--dedalo-loop","plan.md" `
        -PassThru -WorkingDirectory $env:SMOKE_LOOP_DIR
    if (-not $p.WaitForExit(120000)) { $p.Kill(); exit 124 }
    exit $p.ExitCode'
RC=$?
set -e
if [ "$RC" = "124" ]; then
    echo "el motor se colgó (>120 s con el agente inexistente)" >&2
    grep -a . "$SMOKE_DIR/progreso.log" 2>/dev/null | tail -6 >&2 || true
    exit 1
fi
if [ "$RC" != "2" ]; then
    echo "el motor devolvió $RC (esperado 2)" >&2
    grep -a . "$SMOKE_DIR/progreso.log" 2>/dev/null | tail -6 >&2 || true
    exit 1
fi
grep -q "ABORTADO: agente no disponible (opencode)" "$SMOKE_DIR/progreso.log" \
    || { echo "el log no documenta el aborto" >&2; exit 1; }
rm -rf "$SMOKE_DIR"

# ── portable zip ────────────────────────────────────────────────────────────
echo "==> zip portátil"
ZIP="$OUT/$NOMBRE-$VERSION-win64.zip"
rm -f "$ZIP"
# Compress-Archive is native PowerShell and does not understand POSIX paths
# (/d/...): they are passed converted with cygpath (D:\...).
W_APP="$(cygpath -w "$APP")"
W_ZIP="$(cygpath -w "$ZIP")"
powershell -NoProfile -Command "Compress-Archive -Force -Path '$W_APP' -DestinationPath '$W_ZIP'"
echo "    $ZIP"

echo "==> listo: $(ls -1 "$OUT" | grep -E '\.zip$' | tr '\n' ' ')"