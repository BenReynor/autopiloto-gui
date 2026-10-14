# -*- mode: python ; coding: utf-8 -*-
"""Spec de PyInstaller para dedalo (onedir, multiplataforma).

Se invoca desde la raíz del proyecto:

    pyinstaller --clean --noconfirm packaging/dedalo.spec

Genera dist/dedalo/ (onedir). Elegimos onedir y no onefile porque:

  · El .deb y el AppImage esperan un directorio de aplicación.
  · onefile extrae a /tmp en cada arranque (PySide6 pesa ~150 MB: se nota)
    y los binarios extraídos rompen la limpieza por señales que ya
    tiene dedalo.sh.

Los datos se montan EXACTAMENTE en la ruta que el código espera en
runtime: dedalo/plantillas_data/ y dedalo/icono.svg,
resueltas vía os.path.dirname(__file__), que en un binario apunta a
_MEIPASS/dedalo/.
"""

import os
import re
import sys
from pathlib import Path

SPEC_DIR = Path(SPECPATH).resolve()          # noqa: F821 (inyectado por PyInstaller)
RAIZ = SPEC_DIR.parent                        # raíz del repo
PAQUETE = RAIZ / "dedalo"

# Versión desde pyproject.toml (misma fuente que build_*.sh).
VERSION = re.search(
    r'^version\s*=\s*"([^"]+)"',
    (RAIZ / "pyproject.toml").read_text(encoding="utf-8"),
    re.M,
).group(1)

# --- datos del paquete -----------------------------------------------------
# rglob("*") sí incluye los .gitignore (los globs de package-data de
# pyproject no, y los tests ya advierten de eso): el .gitignore de
# plantillas_data es imprescindible para que el framework no se commitee
# en los repos de los usuarios.
datas = []
for ruta in sorted(PAQUETE.rglob("*")):
    # Los .py del paquete ya los recoge Analysis por importación; aquí sólo
    # se necesitan los ficheros NO de código (plantillas, icono, acceso.sh).
    # EXCEPCIÓN: los checks gate_checks/*.py son DATOS (gate.py los ejecuta con
    # exec, no los importa), así que deben montarse junto a los .sh.
    if not ruta.is_file():
        continue
    es_check_py = (ruta.suffix == ".py"
                   and ruta.parent.name == "gate_checks")
    if "__pycache__" in ruta.parts or (
            ruta.suffix in {".py", ".pyc", ".pyo"} and not es_check_py):
        continue
    relativa = ruta.relative_to(PAQUETE)      # p. ej. plantillas_data/gate.sh
    destino = Path("dedalo") / relativa.parent
    datas.append((str(ruta), str(destino)))

hiddenimports = [
    # pyqtgraph se importa con importorskip en la GUI: si PyInstaller no lo
    # ve, la app funciona pero las métricas desaparecen en silencio.
    "pyqtgraph",
    "numpy",
]

a = Analysis(
    [str(SPEC_DIR / "entrypoint.py")],
    pathex=[str(RAIZ)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "ruff"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="dedalo",
    console=False,          # app de escritorio; el log va a progreso.log
    # Windows exige .ico (el .svg no sirve); se genera con make_iconos.py.
    icon=str(SPEC_DIR / "icono.ico") if os.name == "nt" else None,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,              # UPX revienta firmas Qt y antivirus lo marcaban
    name="dedalo",
)

# En macOS el artefacto es un .app de verdad (icono icns, identificador y
# versión para Finder, codesign y notarización). Sólo el onedir suelto no se
# puede firmar. Se genera además el .dmg en build_macos.sh.
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Dedalo.app",
        icon=str(SPEC_DIR / "icono.icns"),
        bundle_identifier="io.github.benreynor.dedalo",
        info_plist={
            "CFBundleShortVersionString": VERSION,
            "NSHighResolutionCapable": True,
            "LSApplicationCategoryType": "public.app-category.developer-tools",
            "NSHumanReadableCopyright": "Copyright (c) 2026 BenReynor",
        },
    )
