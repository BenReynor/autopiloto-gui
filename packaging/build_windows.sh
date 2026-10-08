#!/usr/bin/env bash
# build_windows.sh — empaqueta autopiloto-gui para Windows y hace el smoke
# del binario (la GUI arranca, y el modo `--autopiloto-loop` ejecuta el motor
# python empaquetado y devuelve su código de salida).
#
# Salidas (en packaging/out/):
#   autopiloto-gui/                   onedir (autopiloto-gui.exe + libs)
#   autopiloto-gui-<v>-win64.zip      portátil (descomprimir y ejecutar)
#
# Uso:
#   bash packaging/build_windows.sh
#
# Requiere Windows con Git Bash (p. ej. el runner windows-latest de GitHub
# Actions) y python con el proyecto + PyInstaller.
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
NOMBRE="autopiloto-gui"
APP="$OUT/$NOMBRE"

echo "==> PyInstaller v$VERSION"
rm -rf "$OUT" build
"$PY" -m PyInstaller \
    --clean --noconfirm --distpath "$OUT" --workpath "$OUT/build" \
    packaging/"$NOMBRE".spec
[ -x "$APP/$NOMBRE.exe" ] || { echo "el binario no salió en $APP" >&2; exit 1; }

# ── Smoke 1: la GUI arranca y sigue viva a los 6 s ────────────────────────────
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
# Tras el kill, tope de 10 s: si la GUI no muere, fallar ya (un `wait`
# bloqueante convertiría cualquier regresión en un job de 6 h colgado).
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

# ── Smoke 2: el motor empaquetado vía `--autopiloto-loop` ─────────────────────
# Con un agente deliberadamente inexistente el run aborta ANTES de tocar la
# red/git/gate (orden del script): rc 2 y el log documenta el motivo. Esto
# valida el branch del entrypoint de PyInstaller y que el motor corre en el
# exe windowed (sus prints van a devnull, no a una consola inexistente).
echo "==> smoke motor (--autopiloto-loop)"
SMOKE_DIR="$OUT/smoke_loop"
rm -rf "$SMOKE_DIR"
mkdir -p "$SMOKE_DIR"
printf '# PLAN\n\n- [ ] t1\n' > "$SMOKE_DIR/plan.md"
# PowerShell con tope de 120 s: el proceso se lanza y espera con WaitForExit;
# si el binario se cuelga (p. ej. regresión de encoding) el job falla en
# minutos con rc 124 en vez de quedarse 6 h hasta el timeout de GitHub.
# Nota: RC se captura FUERA del subshell: dentro no se propaga al padre.
set +e
CLI_OPENCODE=/no/existe/opencode AGENTE_TAREA=opencode \
EXE="$APP/$NOMBRE.exe" SMOKE_LOOP_DIR="$SMOKE_DIR" \
powershell -NoProfile -Command '
    $p = Start-Process -FilePath $env:EXE -ArgumentList "--autopiloto-loop","plan.md" `
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

# ── zip portátil ─────────────────────────────────────────────────────────────
echo "==> zip portátil"
ZIP="$OUT/$NOMBRE-$VERSION-win64.zip"
rm -f "$ZIP"
# Compress-Archive es PowerShell nativo y no entiende rutas POSIX (/d/...):
# se pasan convertidas con cygpath (D:\...).
W_APP="$(cygpath -w "$APP")"
W_ZIP="$(cygpath -w "$ZIP")"
powershell -NoProfile -Command "Compress-Archive -Force -Path '$W_APP' -DestinationPath '$W_ZIP'"
echo "    $ZIP"

echo "==> listo: $(ls -1 "$OUT" | grep -E '\.zip$' | tr '\n' ' ')"