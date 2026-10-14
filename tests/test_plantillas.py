#!/usr/bin/env python3
"""Tests para plantillas.py - creación de lecciones.md (memoria del proyecto)."""

import glob
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dedalo import plantillas

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PYPROJECT = os.path.join(RAIZ, "pyproject.toml")


def _globs_de_package_data():
    """Extrae los globs de [tool.setuptools.package-data] sin depender de tomli.

    Se lee el texto a propósito: así el test funciona con Python 3.10, donde
    tomllib no existe (requires-python del proyecto es >=3.10).
    """
    with open(PYPROJECT, encoding="utf-8") as f:
        texto = f.read()
    m = re.search(
        r"^\[tool\.setuptools\.package-data\][^\[]*?dedalo\s*=\s*\[(.*?)\]",
        texto,
        re.S | re.M,
    )
    assert m, "no se encontró [tool.setuptools.package-data] en pyproject.toml"
    return re.findall(r'"([^"]+)"', m.group(1))


def _lo_que_instala_en_runtime():
    """Los nombres que instalar() copia sin condición desde PLANTILLA_DIR.

    Refleja plantillas.instalar(): list(ARCHIVOS) + list(GATE_CHECKS) +
    [".gitignore"]. Si esto crece sin tocar package-data, el paquete deja de
    ser instalable de forma no editable.
    """
    return list(plantillas.ARCHIVOS) + list(plantillas.GATE_CHECKS) + [
        ".gitignore"
    ]


def test_package_data_cubre_lo_que_instala():
    """pyproject.toml debe empaquetar TODO lo que instalar() copia.

    Sin esto, `pip install .` produce un paquete al que le falta
    plantillas_data/.gitignore; instalar() hace shutil.copy2 sin try y revienta
    con FileNotFoundError al agregar el primer proyecto. Los tests no lo
    detectaban porque la CI instala siempre con `-e`.
    """
    patrones = _globs_de_package_data()
    base = os.path.join(RAIZ, "dedalo")
    cubiertos = set()
    for patron in patrones:
        cubiertos.update(os.path.relpath(p, base) for p in glob.glob(
            os.path.join(base, patron)
        ))

    sin_cubrir = [
        nombre
for nombre in _lo_que_instala_en_runtime()
    # Comparar SIEMPRE con "/": en Windows os.path.join mezclaría muchísimas
    # barras y glob.relpath usa las del SO, por eso ambos lados se normalizan.
    if os.path.join("plantillas_data", nombre).replace("\\", "/") not in {
        p.replace("\\", "/") for p in cubiertos
    }
    ]
    assert not sin_cubrir, (
        "pyproject.toml no empaqueta estos ficheros que instalar() copia "
        f"incondicionalmente: {sin_cubrir}. Añade su glob a "
        "[tool.setuptools.package-data] (recuerda: `*` no hace match con "
        "ficheros que empiezan por punto)."
    )


def test_package_data_no_declara_ficheros_inexistentes():
    """Los globs no deben apuntar a nada: globs fantasma promoción a bugs."""
    base = os.path.join(RAIZ, "dedalo")
    for patron in _globs_de_package_data():
        assert glob.glob(os.path.join(base, patron)), (
            f"[tool.setuptools.package-data] declara {patron!r} pero no "
            "coincide con ningún fichero del paquete"
        )


def _proyecto_tmp():
    tmp = tempfile.mkdtemp()
    try:
        for nombre in plantillas.SCRIPTS:
            with open(os.path.join(tmp, nombre), "w", encoding="utf-8"):
                pass
        os.mkdir(os.path.join(tmp, "gate_checks"))
        with open(os.path.join(tmp, "progreso.log"), "w", encoding="utf-8"):
            pass
    except OSError:
        pass
    return tmp


def test_faltan_incluye_lecciones():
    tmp = _proyecto_tmp()
    try:
        assert "lecciones.md" in plantillas.faltan(tmp)
        assert "CONTEXTO.md" in plantillas.faltan(tmp)
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def test_instalar_crea_contexto():
    """CONTEXTO.md se instala con esqueleto y nunca se sobreescribe."""
    import shutil
    tmp = _proyecto_tmp()
    try:
        creados = plantillas.instalar(tmp)
        assert "CONTEXTO.md" in creados
        ruta = os.path.join(tmp, "CONTEXTO.md")
        with open(ruta, encoding="utf-8") as f:
            assert "CONTEXTO DEL PROYECTO" in f.read()
        # Contenido propio del usuario: no se pisa en la segunda instalación
        with open(ruta, "w", encoding="utf-8") as f:
            f.write("# Mi contexto propio")
        creados2 = plantillas.instalar(tmp)
        assert "CONTEXTO.md" not in creados2
        with open(ruta, encoding="utf-8") as f:
            assert f.read() == "# Mi contexto propio"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_instalar_crea_lecciones():
    tmp = _proyecto_tmp()
    try:
        creados = plantillas.instalar(tmp)
        assert "lecciones.md" in creados
        ruta = os.path.join(tmp, "lecciones.md")
        assert os.path.exists(ruta)
        with open(ruta, encoding="utf-8") as f:
            contenido = f.read()
        assert "Lecciones aprendidas" in contenido
        # No se sobreescribe si ya existe contenido del usuario
        with open(ruta, "w", encoding="utf-8") as f:
            f.write("# Mi memoria propia")
        creados2 = plantillas.instalar(tmp)
        assert "lecciones.md" not in creados2
        with open(ruta, encoding="utf-8") as f:
            assert f.read() == "# Mi memoria propia"
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def test_quitar_borra_lecciones():
    tmp = _proyecto_tmp()
    try:
        plantillas.instalar(tmp)
        eliminados = plantillas.quitar(tmp)
        assert "lecciones.md" in eliminados
        assert "CONTEXTO.md" in eliminados
        assert not os.path.exists(os.path.join(tmp, "lecciones.md"))
        assert not os.path.exists(os.path.join(tmp, "CONTEXTO.md"))
        assert not os.path.exists(os.path.join(tmp, "plan.md"))
        assert not os.path.exists(os.path.join(tmp, "progreso.log"))
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def test_instalar_propaga_checks_nuevos_sin_pisar_custom():
    """Un check NUEVO de plantilla se instala; un check CUSTOM no se toca."""
    import shutil
    tmp = _proyecto_tmp()
    try:
        plantillas.instalar(tmp)
        # El usuario crea un check propio con contenido distinto de plantilla
        custom = os.path.join(tmp, "gate_checks", "99_custom.sh")
        with open(custom, "w", encoding="utf-8") as f:
            f.write("echo 'check custom'\n")
        # Proyecto "viejo": sin el check nuevo de la plantilla
        os.remove(os.path.join(tmp, "gate_checks", "98_criterio.sh"))

        creados = plantillas.instalar(tmp)

        assert "gate_checks/98_criterio.sh" in creados, "check nuevo se propaga"
        with open(custom, encoding="utf-8") as f:
            assert f.read() == "echo 'check custom'\n", "custom no se sobreescribe"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_actualizar_no_toca_gate_checks_custom():
    """actualizar() solo renueva los SCRIPTS; gate_checks custom quedan intactos."""
    import shutil
    tmp = _proyecto_tmp()
    try:
        plantillas.instalar(tmp)

        # Personalizar un check y forzar diferencia en dedalo.sh
        custom = os.path.join(tmp, "gate_checks", "99_custom.sh")
        with open(custom, "w", encoding="utf-8") as f:
            f.write("echo 'check custom'\n")
        script = os.path.join(tmp, "dedalo.sh")
        with open(script, encoding="utf-8") as f:
            original = f.read()
        with open(script, "w", encoding="utf-8") as f:
            f.write(original + "\necho 'mod'\n")

        desact = plantillas._desactualizados(tmp)
        assert "gate_checks/99_custom.sh" not in desact
        assert "gate_checks/98_criterio.sh" not in desact
        assert "dedalo.sh" in desact

        plantillas.actualizar(tmp)
        with open(custom, encoding="utf-8") as f:
            assert f.read() == "echo 'check custom'\n", "custom intacto tras actualizar"
        with open(script, encoding="utf-8") as f:
            assert f.read() != original + "\necho 'mod'\n", "script restaurado"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_instalar_crea_gitignore_del_framework():
    """Un proyecto nuevo recibe .gitignore que excluye los archivos del framework."""
    tmp = _proyecto_tmp()
    try:
        creados = plantillas.instalar(tmp)
        assert ".gitignore" in creados
        ruta = os.path.join(tmp, ".gitignore")
        assert os.path.exists(ruta)
        with open(ruta, encoding="utf-8") as f:
            contenido = f.read()
        # El repo del proyecto jamás debe commitear/pushear archivos de Dédalo
        for entrada in ("dedalo.sh", "gate.sh", "gate_checks/", "plan.md",
                        "lecciones.md", "CONTEXTO.md", "progreso.log",
                        "metrics.jsonl", "incidencias.jsonl",
                        ".dedalo_review/"):
            assert entrada in contenido, f"falta entrada {entrada!r}"
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def test_instalar_no_pisa_gitignore_existente():
    """Si el proyecto ya tiene .gitignore propio, se respeta (no se sobreescribe)."""
    import shutil
    tmp = _proyecto_tmp()
    try:
        ruta = os.path.join(tmp, ".gitignore")
        with open(ruta, "w", encoding="utf-8") as f:
            f.write("# node\nnode_modules/\n")
        creados = plantillas.instalar(tmp)
        assert ".gitignore" not in creados
        with open(ruta, encoding="utf-8") as f:
            assert f.read() == "# node\nnode_modules/\n"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_asegurar_gitignore_anade_bloque_existente():
    """asegurar_gitignore añade el bloque de Dédalo a un .gitignore existente."""
    import shutil
    tmp = tempfile.mkdtemp()
    try:
        ruta = os.path.join(tmp, ".gitignore")
        with open(ruta, "w", encoding="utf-8") as f:
            f.write("# node\nnode_modules/\n")
        assert plantillas.asegurar_gitignore(tmp) is True
        with open(ruta, encoding="utf-8") as f:
            contenido = f.read()
        assert "node_modules/" in contenido, "lo del usuario no se toca"
        for entrada in ("dedalo.sh", "gate.sh", "gate_checks/", "plan.md",
                        "lecciones.md", "CONTEXTO.md", "progreso.log",
                        "metrics.jsonl", "incidencias.jsonl",
                        ".dedalo_review/"):
            assert entrada in contenido, f"falta entrada {entrada!r}"
        # Idempotente: segunda llamada no duplica
        assert plantillas.asegurar_gitignore(tmp) is False
        with open(ruta, encoding="utf-8") as f:
            assert f.read().count("dedalo.sh") == 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_asegurar_gitignore_crea_si_falta():
    """Si no hay .gitignore, asegurar_gitignore copia la plantilla completa."""
    import shutil
    tmp = tempfile.mkdtemp()
    try:
        assert plantillas.asegurar_gitignore(tmp) is True
        ruta = os.path.join(tmp, ".gitignore")
        assert os.path.exists(ruta)
        with open(ruta, encoding="utf-8") as f:
            contenido = f.read()
        assert "Dédalo:" in contenido
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_quitar_framework_del_git():
    """quitar_framework_del_git deja de trackear pero conserva en disco."""
    import shutil
    import subprocess
    tmp = tempfile.mkdtemp()
    try:
        subprocess.run(["git", "init", "-q"], cwd=tmp, check=True)
        for nombre in ["dedalo.sh", "gate.sh", "plan.md", "lecciones.md",
                       "CONTEXTO.md", "progreso.log", "metrics.jsonl",
                       "incidencias.jsonl", "mapeo.txt", "endpoints.txt",
                       "gate_checks/01_db.sh", "readme.md"]:
            p = os.path.join(tmp, nombre)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8"):
                pass
        subprocess.run(["git", "add", "-A"], cwd=tmp, check=True)
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=T",
                        "commit", "-q", "-m", "init"], cwd=tmp, check=True)

        salidos = plantillas.quitar_framework_del_git(tmp)

        assert "dedalo.sh" in salidos
        assert "gate_checks/01_db.sh" in salidos
        assert "CONTEXTO.md" in salidos
        assert "readme.md" not in salidos, "lo del usuario no se toca"
        # En disco siguen
        assert os.path.exists(os.path.join(tmp, "dedalo.sh"))
        assert os.path.exists(os.path.join(tmp, "plan.md"))
        # Dejaron de estar en el índice
        out = subprocess.run(["git", "ls-files"], cwd=tmp, capture_output=True,
                             text=True, check=True)
        trackeados = out.stdout.splitlines()
        assert "dedalo.sh" not in trackeados
        assert "plan.md" not in trackeados
        assert "readme.md" in trackeados
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_inicializar_git_crea_repo_si_falta():
    import shutil
    tmp = tempfile.mkdtemp()
    try:
        with open(os.path.join(tmp, "plan.md"), "w", encoding="utf-8") as f:
            f.write("# PLAN\n\n- [ ] tarea\n      criterio: ok\n")
        assert not plantillas._es_repo_git(tmp)
        res = plantillas.inicializar_git(tmp)
        assert res["repo"] == "creado"
        assert res["archivos"] >= 1
        assert plantillas._es_repo_git(tmp)
        # Segunda llamada no re-inicializa
        res2 = plantillas.inicializar_git(tmp)
        assert res2["repo"] == "ya-existia"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_inicializar_git_no_rompe_repo_existente():
    import shutil
    import subprocess
    tmp = tempfile.mkdtemp()
    try:
        subprocess.run(["git", "init", "-q"], cwd=tmp, check=True)
        with open(os.path.join(tmp, "readme.md"), "w", encoding="utf-8") as f:
            f.write("# repo\n")
        subprocess.run(["git", "add", "-A"], cwd=tmp, check=True)
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=T",
                        "commit", "-q", "-m", "init"], cwd=tmp, check=True)
        res = plantillas.inicializar_git(tmp)
        assert res["repo"] == "ya-existia"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    test_faltan_incluye_lecciones()
    test_instalar_crea_lecciones()
    test_instalar_crea_contexto()
    test_quitar_borra_lecciones()
    test_instalar_propaga_checks_nuevos_sin_pisar_custom()
    test_actualizar_no_toca_gate_checks_custom()
    test_inicializar_git_crea_repo_si_falta()
    test_inicializar_git_no_rompe_repo_existente()
    test_instalar_crea_gitignore_del_framework()
    test_instalar_no_pisa_gitignore_existente()
    test_asegurar_gitignore_anade_bloque_existente()
    test_asegurar_gitignore_crea_si_falta()
    test_quitar_framework_del_git()
    print("\n🎉 Todos los tests de plantillas.py PASARON")
