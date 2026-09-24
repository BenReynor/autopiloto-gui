#!/usr/bin/env python3
"""Tests para plantillas.py - creación de lecciones.md (memoria del proyecto)."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autopiloto_gui import plantillas


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
    finally:
        import shutil
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
        assert not os.path.exists(os.path.join(tmp, "lecciones.md"))
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

        # Personalizar un check y forzar diferencia en autopiloto.sh
        custom = os.path.join(tmp, "gate_checks", "99_custom.sh")
        with open(custom, "w", encoding="utf-8") as f:
            f.write("echo 'check custom'\n")
        script = os.path.join(tmp, "autopiloto.sh")
        with open(script, encoding="utf-8") as f:
            original = f.read()
        with open(script, "w", encoding="utf-8") as f:
            f.write(original + "\necho 'mod'\n")

        desact = plantillas._desactualizados(tmp)
        assert "gate_checks/99_custom.sh" not in desact
        assert "gate_checks/98_criterio.sh" not in desact
        assert "autopiloto.sh" in desact

        plantillas.actualizar(tmp)
        with open(custom, encoding="utf-8") as f:
            assert f.read() == "echo 'check custom'\n", "custom intacto tras actualizar"
        with open(script, encoding="utf-8") as f:
            assert f.read() != original + "\necho 'mod'\n", "script restaurado"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    test_faltan_incluye_lecciones()
    test_instalar_crea_lecciones()
    test_quitar_borra_lecciones()
    test_instalar_propaga_checks_nuevos_sin_pisar_custom()
    test_actualizar_no_toca_gate_checks_custom()
    print("\n🎉 Todos los tests de plantillas.py PASARON")
