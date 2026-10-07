#!/usr/bin/env python3
"""Tests de regresión: un proyecto quitado NO debe reaparecer en el registro.

Protege contra el bug donde closeEvent/_cambiar_proyecto llamaban a
guardar_config_proyecto() y éste re-añadía (`setdefault`) el nombre del
proyecto que el usuario acababa de quitar, haciendo que reapareciera al
reabrir la GUI como una entrada huérfana (config sin ruta).
"""

import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autopiloto_gui import configuracion as cfg
from autopiloto_gui import proyectos


def _config_aislada(contenido=None):
    """Redirige CONFIG_DIR/REGISTRO a un temp y devuelve la ruta del registro.

    Por defecto escribe un registro válido y vacío; pasando `contenido` se
    puede sembrar cualquier texto (incluido JSON inválido).
    """
    tmp = tempfile.mkdtemp()
    reg = os.path.join(tmp, "proyectos.json")
    cfg.CONFIG_DIR = tmp
    cfg.REGISTRO = reg
    proyectos.cfg.CONFIG_DIR = tmp
    proyectos.cfg.REGISTRO = reg
    if contenido is None:
        contenido = json.dumps({"proyectos": {}}, ensure_ascii=False)
    with open(reg, "w", encoding="utf-8") as f:
        f.write(contenido)
    return reg


def _limpiar(reg):
    import shutil

    shutil.rmtree(os.path.dirname(reg), ignore_errors=True)


def test_guardar_config_no_reañade_proyecto_quitado():
    reg = _config_aislada()
    try:
        # Registro con dos proyectos, luego el usuario quita "A"
        proyectos_dic = {
            "A": {"ruta": "/tmp/a", "config": {"tema": "X"}},
            "B": {"ruta": "/tmp/b", "config": {}},
        }
        proyectos.guardar(proyectos_dic, "Oscuro")
        proyectos_dic.pop("A", None)
        proyectos.guardar(proyectos_dic, "Oscuro")

        # closeEvent sigue llamando con el nombre activo ya quitado
        proyectos.guardar_config_proyecto(proyectos_dic, "A", {"tema": "Y"})

        with open(reg, encoding="utf-8") as f:
            datos = json.load(f)
        assert "A" not in datos["proyectos"], "el proyecto quitado no debe reaparecer"
        assert set(datos["proyectos"]) == {"B"}
    finally:
        import shutil

        shutil.rmtree(os.path.dirname(reg), ignore_errors=True)


def test_guardar_config_sigue_guardando_proyectos_existentes():
    reg = _config_aislada()
    try:
        proyectos_dic = {"B": {"ruta": "/tmp/b", "config": {}}}
        proyectos.guardar(proyectos_dic, "Oscuro")
        proyectos.guardar_config_proyecto(
            proyectos_dic, "B", {"modelos": {"tarea": "x"}}
        )

        with open(reg, encoding="utf-8") as f:
            datos = json.load(f)
        assert "B" in datos["proyectos"]
        assert datos["proyectos"]["B"]["config"]["modelos"]["tarea"] == "x"
    finally:
        import shutil

        shutil.rmtree(os.path.dirname(reg), ignore_errors=True)


# ---------- integridad del registro ----------
#
# Regresión grave: _leer_archivo() se tragaba el JSONDecodeError y devolvía {},
# así que Ventana.__init__ (app.py:78) veía "sin proyectos" y llamaba a
# guardar(), que volvía a escribir un registro VACÍO sobre el corrupto. Un
# registro dañado = todos los proyectos del usuario borrados en el arranque
# siguiente, sin ningún aviso.


def test_registro_corrupto_no_se_sobreescribe():
    """verificar_registro() debe lanzar Y dejar el original intacto."""
    reg = _config_aislada(contenido='{"proyectos": {"A": {"ruta": "/tmp/a"')
    try:
        with pytest.raises(proyectos.RegistroCorrupto) as exc:
            proyectos.verificar_registro()

        assert os.path.exists(reg), "el original no debe tocarse al detectar"
        with open(reg, encoding="utf-8") as f:
            assert f.read() == '{"proyectos": {"A": {"ruta": "/tmp/a"'
        assert exc.value.copia and os.path.exists(exc.value.copia)
    finally:
        _limpiar(reg)


def test_registro_corrupto_hace_copia_de_seguridad():
    """La copia .corrupto conserva los datos para que el usuario los recupere."""
    reg = _config_aislada(contenido='{"proyectos": {"A": {"ruta": "/tmp/a"')
    try:
        with pytest.raises(proyectos.RegistroCorrupto) as exc:
            proyectos.verificar_registro()
        with open(exc.value.copia, encoding="utf-8") as f:
            assert '"A"' in f.read()
    finally:
        _limpiar(reg)


def test_registro_corrupto_bloquea_en_cada_arranque():
    """Mientras el usuario no decida, el aviso se repite: no se pierde el
    registro en silencio por haber cerrado y reabierto la app."""
    reg = _config_aislada(contenido="no soy json")
    try:
        for _ in range(2):
            with pytest.raises(proyectos.RegistroCorrupto):
                proyectos.verificar_registro()
        with open(reg, encoding="utf-8") as f:
            assert f.read() == "no soy json"
    finally:
        _limpiar(reg)


def test_copia_corrupta_no_pisa_la_anterior():
    """Dos corrompidos seguidos = dos copias distintas."""
    reg = _config_aislada(contenido="basura1")
    try:
        with pytest.raises(proyectos.RegistroCorrupto) as c1:
            proyectos.verificar_registro()
        with open(reg, "w", encoding="utf-8") as f:
            f.write("basura2")
        with pytest.raises(proyectos.RegistroCorrupto) as c2:
            proyectos.verificar_registro()

        assert c1.value.copia != c2.value.copia
        with open(c1.value.copia, encoding="utf-8") as f:
            assert f.read() == "basura1"
        with open(c2.value.copia, encoding="utf-8") as f:
            assert f.read() == "basura2"
    finally:
        _limpiar(reg)


def test_descartar_registro_permite_arrancar_vacio():
    """Con el consentimiento del usuario, se borra el corrupto y guardar()
    reconstruye un registro válido; la copia se conserva."""
    reg = _config_aislada(contenido="basura")
    try:
        with pytest.raises(proyectos.RegistroCorrupto) as exc:
            proyectos.verificar_registro()

        proyectos.descartar_registro_corrupto()
        assert not os.path.exists(reg)

        proyectos.verificar_registro()  # ya no lanza

        proyectos.guardar({"B": {"ruta": "/tmp/b"}}, "Oscuro")
        with open(reg, encoding="utf-8") as f:
            datos = json.load(f)
        assert datos["proyectos"]["B"]["ruta"] == "/tmp/b"
        assert datos["tema"] == "Oscuro"
        assert os.path.exists(exc.value.copia), "la copia debe sobrevivir"
    finally:
        _limpiar(reg)


def test_escribir_es_atomico_y_no_deja_temporales():
    """Nada de .tmp huérfanos: replace() sustituye de golpe."""
    reg = _config_aislada()
    try:
        proyectos.guardar({"A": {"ruta": "/tmp/a"}}, "Oscuro")
        proyectos.guardar_sidebar_ancho(320)

        assert not [f for f in os.listdir(os.path.dirname(reg)) if ".tmp" in f]
        with open(reg, encoding="utf-8") as f:
            assert json.load(f)["sidebar_ancho"] == 320
    finally:
        _limpiar(reg)


def test_escribir_no_deja_el_registro_roto_si_falla_la_serializacion():
    """Si json.dump revienta a media escritura, el registro bueno anterior
    debe seguir legible (por eso se escribe a un temporal y no in situ)."""
    reg = _config_aislada()
    try:
        proyectos.guardar({"A": {"ruta": "/tmp/a"}}, "Oscuro")

        class Inserializable:
            pass

        with pytest.raises(TypeError):
            proyectos._escribir({"proyectos": {"A": Inserializable()}})

        with open(reg, encoding="utf-8") as f:
            datos = json.load(f)
        assert datos["proyectos"]["A"]["ruta"] == "/tmp/a"
        assert not [f for f in os.listdir(os.path.dirname(reg)) if ".tmp" in f]
    finally:
        _limpiar(reg)


# ---------- permisos del registro (tokens de webhooks) ----------
#
# El registro guarda telegram_token/whatsapp_token/discord en claro. Con los
# permisos por omisión del umask salía en 0664, legible por el grupo. El
# fix: crear el temporal con 0600 ANTES de escribir (replace mueve el inodo,
# así que el destino hereda el modo) y endurecer en verificar_registro los
# registros antiguos.


def test_escribir_deja_el_registro_en_0600():
    """Ni el umask laxo ni el temporal deben dejar permisos de grupo/otros."""
    reg = _config_aislada()
    try:
        umask_previo = os.umask(0o022)  # umask de por defecto, permisivo
        try:
            proyectos.guardar({"A": {"ruta": "/tmp/a", "config": {
                "webhooks": {"telegram_token": "123:abc"}}}}, "Oscuro")
        finally:
            os.umask(umask_previo)

        modo = os.stat(reg).st_mode & 0o777
        assert modo == 0o600, f"permisos del registro: {modo:04o}, esperado 0600"
    finally:
        _limpiar(reg)


def test_verificar_registro_endurece_un_registro_antiguo():
    """Un proyectos.json heredado (0664) se endurece al arrancar."""
    reg = _config_aislada()
    try:
        os.chmod(reg, 0o664)
        proyectos.verificar_registro()  # no lanza: el JSON es válido

        modo = os.stat(reg).st_mode & 0o777
        assert modo == 0o600, f"tras verificar: {modo:04o}, esperado 0600"
    finally:
        _limpiar(reg)


if __name__ == "__main__":
    test_guardar_config_no_reañade_proyecto_quitado()
    test_guardar_config_sigue_guardando_proyectos_existentes()
    print("\nTests de regresión de proyectos.py PASARON")
