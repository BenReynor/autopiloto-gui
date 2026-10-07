#!/usr/bin/env python3
"""Genera packaging/icono.icns (macOS) y packaging/icono.ico (Windows)
a partir de autopiloto_gui/icono.svg.

Uso:
    python3 packaging/make_iconos.py

Se ejecuta al final del build (build_linux.sh/build_macos.sh) y hay un test
que comprueba que los ficheros generados siguen siendo válidos; si cambias el
SVG, vuelve a lanzarlo y commitea los dos ficheros.

No necesita pantalla ni QApplication: pinta el SVG en un QImage offscreen.
"""
from __future__ import annotations

import io
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image  # noqa: E402
from PySide6.QtCore import QBuffer, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QImage, QPainter  # noqa: E402
from PySide6.QtSvg import QSvgRenderer  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
SVG = RAIZ / "autopiloto_gui" / "icono.svg"
ICNS = Path(__file__).resolve().parent / "icono.icns"
ICO = Path(__file__).resolve().parent / "icono.ico"
TAMANOS = [16, 32, 64, 128, 256, 512, 1024]


def _png(svg: QSvgRenderer, tam: int) -> Image.Image:
    img = QImage(tam, tam, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    pintor = QPainter(img)
    svg.render(pintor, QRectF(0, 0, tam, tam))
    pintor.end()
    buf = QBuffer()
    buf.open(QBuffer.WriteOnly)
    if not img.save(buf, "PNG"):
        raise RuntimeError(f"no pude pintar el icono a {tam}x{tam}")
    return Image.open(io.BytesIO(bytes(buf.data()))).convert("RGBA")


def generar() -> None:
    svg = QSvgRenderer(str(SVG))
    if not svg.isValid():
        raise RuntimeError(f"SVG inválido: {SVG}")
    iconos = {tam: _png(svg, tam) for tam in TAMANOS}

    # .icns: Pillow escribe ic07..ic14 (PNG embebidos); pasa los tamaños
    # exactos para que no tenga que reescalar.
    iconos[1024].save(ICNS, append_images=[iconos[t] for t in TAMANOS])

    # .ico: igual, con los tamaños que Windows espera (hasta 256).
    chicos = [t for t in TAMANOS if t <= 256]
    iconos[256].save(ICO, sizes=[(t, t) for t in chicos],
                     append_images=[iconos[t] for t in chicos])

    for ruta in (ICNS, ICO):
        try:
            nombre = ruta.relative_to(RAIZ)
        except ValueError:          # destino temporal (tests)
            nombre = ruta
        print(f"{nombre}  {ruta.stat().st_size} bytes")


if __name__ == "__main__":
    try:
        generar()
    except Exception as exc:  # noqa: BLE001 — mensaje claro y exit != 0
        print(f"make_iconos: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
