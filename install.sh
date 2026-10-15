#!/usr/bin/env bash
# install.sh — instala Dédalo y crea el acceso directo dinámico

set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$DIR/.venv"

# Entorno virtual propio: evita el error "externally-managed-environment"
# (PEP 668) de las distros modernas al instalar con el pip del sistema.
if [ ! -x "$VENV/bin/python" ]; then
    echo "Creando entorno virtual en $VENV ..."
    python3 -m venv "$VENV"
fi

echo "Instalando Dédalo en modo editable (con soporte MCP)..."
"$VENV/bin/python" -m pip install --quiet --upgrade pip >/dev/null 2>&1 || true
"$VENV/bin/python" -m pip install -e "$DIR[mcp]" 2>&1 | tail -15

echo -e "\nCreando acceso directo dinámico..."
bash "$DIR/dedalo/acceso.sh" 2>&1 | tail -10

echo -e "\n¡Listo!"
echo "- Escritorio: ~/Escritorio/dedalo.desktop"
echo "- Lanzador: ~/.local/bin/dedalo"
echo "- Ejecutable rápido: cd $DIR && ./lanzar.sh"
