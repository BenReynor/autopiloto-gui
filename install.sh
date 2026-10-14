#!/usr/bin/env bash
# install.sh — instala Dédalo y crea el acceso directo dinámico

set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Instalando Dédalo en modo editable..."
python3 -m pip install -e "$DIR" 2>&1 | tail -15

echo -e "\nCreando acceso directo dinámico..."
bash "$DIR/dedalo/acceso.sh"
 2>&1 | tail -10

echo -e "\n¡Listo!"
echo "- Escritorio: ~/Escritorio/dedalo.desktop"
echo "- Lanzador: ~/.local/bin/dedalo"
echo "- Ejecutable rápido: cd $DIR && ./lanzar.sh"
