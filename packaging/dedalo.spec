# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for dedalo (onedir, cross-platform).

Invoked from the project root:

    pyinstaller --clean --noconfirm packaging/dedalo.spec

Generates dist/dedalo/ (onedir). We chose onedir and not onefile because:

  · The .deb and the AppImage expect an application directory.
  · onefile extracts to /tmp on every start (PySide6 weighs ~150 MB: it shows)
    and the extracted binaries break the signal-based cleanup that
    dedalo.sh already has.

The data is mounted EXACTLY at the path the code expects at
runtime: dedalo/plantillas_data/ and dedalo/icono.svg,
resolved via os.path.dirname(__file__), which in a binary points to
_MEIPASS/dedalo/.
"""

import os
import re
import sys
from pathlib import Path

SPEC_DIR = Path(SPECPATH).resolve()          # noqa: F821 (injected by PyInstaller)
RAIZ = SPEC_DIR.parent                        # repo root
PAQUETE = RAIZ / "dedalo"

# Version from pyproject.toml (same source as build_*.sh).
VERSION = re.search(
    r'^version\s*=\s*"([^"]+)"',
    (RAIZ / "pyproject.toml").read_text(encoding="utf-8"),
    re.M,
).group(1)

# --- package data -----------------------------------------------------------
# rglob("*") does include the .gitignore files (the package-data globs in
# pyproject do not, and the tests already warn about that): the .gitignore of
# plantillas_data is essential so the framework is not committed
# into users' repos.
datas = []
for ruta in sorted(PAQUETE.rglob("*")):
    # The package's .py files are already collected by Analysis via import;
    # here only the NON-code files are needed (templates, icon, acceso.sh).
    # EXCEPTION: the gate_checks/*.py checks are DATA (gate.py runs them with
    # exec, it does not import them), so they must be mounted next to the .sh.
    if not ruta.is_file():
        continue
    es_check_py = (ruta.suffix == ".py"
                   and ruta.parent.name == "gate_checks")
    if "__pycache__" in ruta.parts or (
            ruta.suffix in {".py", ".pyc", ".pyo"} and not es_check_py):
        continue
    relativa = ruta.relative_to(PAQUETE)      # e.g. plantillas_data/gate.sh
    destino = Path("dedalo") / relativa.parent
    datas.append((str(ruta), str(destino)))

hiddenimports = [
    # pyqtgraph is imported with importorskip in the GUI: if PyInstaller does
    # not see it, the app works but the metrics silently disappear.
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
    console=False,          # desktop app; the log goes to progreso.log
    # Windows requires .ico (the .svg does not work); generated with make_iconos.py.
    icon=str(SPEC_DIR / "icono.ico") if os.name == "nt" else None,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,              # UPX broke Qt signatures and antivirus flagged it
    name="dedalo",
)

# On macOS the artifact is a real .app (icns icon, identifier and
# version for Finder, codesign and notarization). A loose onedir cannot be
# signed. The .dmg is also generated in build_macos.sh.
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
