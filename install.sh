#!/usr/bin/env bash
# install.sh — instala autopiloto-gui y crea el acceso directo dinámico

set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Instalando autopiloto-gui en modo editable..."
python3 -m pip install -e "$DIR" 2>&1 | tail -15

echo -e "\nCreando acceso directo dinámico..."
bash "$DIR/autopiloto_gui/acceso.sh"
 2>&1 | tail -10

echo -e "\n¡Listo!"
echo "- Escritorio: ~/Escritorio/autopiloto-gui.desktop"
echo "- Lanzador: ~/.local/bin/autopiloto"
echo "- Ejecutable rápido: cd $DIR && ./lanzar.sh"
