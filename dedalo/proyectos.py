"""Registro de proyectos, tema y protección térmica del panel de Dédalo.

Se guarda en ~/.config/dedalo/proyectos.json y es compartido por todos
los proyectos quegestion es desde el panel.

Integridad: el registro se escribe SIEMPRE de forma atómica (escribir en un
fichero temporal y os.replace), de modo que un cierre abrupto a mitad de
guardado no pueda truncarlo. Y si el JSON llegara a estar corrupto, main()
FALLA ANTES de arrancar en vez de tragar el error y sobrescribirlo con un
registro vacío (que era como se perdían todos los proyectos del usuario).
"""

import json
import os
import shutil

from . import configuracion as cfg


class RegistroCorrupto(Exception):
    """El registro de proyectos no es JSON válido.

    Lleva la ruta del fichero original y la de la copia .corrupto de
    seguridad. El original NO se borra al detectarlo: sólo cuando el usuario
    acepta empezar de cero (descartar_registro_corrupto).
    """

    def __init__(self, ruta, copia):
        super().__init__(f"registro de proyectos corrupto: {ruta}")
        self.ruta = ruta
        self.copia = copia


def _copia_de_seguridad(corrupto):
    """Copia el registro a <registro>.corrupto sin pisar la anterior.

    Devuelve la ruta de la copia creada. Los sufijos son .corrupto,
    .corrupto.2, .corrupto.3... para no perder ni la primera versión.
    """
    n = 1
    while True:
        sufijo = "" if n == 1 else f".{n}"
        cand = f"{corrupto}.corrupto{sufijo}"
        if not os.path.exists(cand):
            shutil.copy2(corrupto, cand)
            return cand
        n += 1


def verificar_registro():
    """Valida el registro ANTES de arrancar. Lanza RegistroCorrupto si no es
    JSON válido, dejando antes una copia .corrupto de los datos.

    No modifica el original a propósito: si el usuario cierra la app y la
    vuelve a abrir, el aviso se repite en vez de perder el registro en
    silencio al primer guardado.
    """
    if not os.path.exists(cfg.REGISTRO):
        return
    # Un registro creado por una versión anterior puede quedar en 0664 y ahí
    # viven los tokens de webhooks: se endurece al detectarlo.
    try:
        os.chmod(cfg.REGISTRO, 0o600)
    except OSError:
        pass
    try:
        with open(cfg.REGISTRO, encoding="utf-8") as f:
            json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RegistroCorrupto(cfg.REGISTRO, _copia_de_seguridad(cfg.REGISTRO)) from exc


def descartar_registro_corrupto():
    """Borra el registro corrupto (sus datos quedan en la copia .corrupto)."""
    try:
        os.remove(cfg.REGISTRO)
    except FileNotFoundError:
        pass


def _escribir(datos):
    """Escribe el registro de forma atómica y privada.

    json.dump va primero al temporal y sólo después se os.replace() sobre el
    destino: replace es atómico en el mismo sistema de ficheros, así que un
    corte de luz o un kill a mitad de escritura deja el registro anterior
    intacto en lugar de un JSON truncado e ilegible.

    El temporal se crea con permisos 0o600 (sólo el usuario) ANTES de
    escribir, y como replace mueve el inodo, el destino hereda esos
    permisos: los tokens de webhooks que guarda el registro no acaban
    legibles por el grupo ni por otros usuarios (antes salían en 0664).
    """
    os.makedirs(cfg.CONFIG_DIR, exist_ok=True, mode=0o700)
    tmp = f"{cfg.REGISTRO}.{os.getpid()}.tmp"
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(datos, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        # Por si un umask laxo o un temporal heredado hayan aflojado el modo.
        os.chmod(tmp, 0o600)
        os.replace(tmp, cfg.REGISTRO)
    except BaseException:
        # Incluye TypeError/ValueError de json.dump con datos no serializables:
        # el temporal ya creado debe irse igual o se acumula basura en ~/.config.
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _leer_archivo():
    try:
        with open(cfg.REGISTRO, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def cargar():
    return _leer_archivo().get("proyectos", {})


def leer_tema():
    return _leer_archivo().get("tema", cfg.TEMA_DEFECTO)


def leer_seguridad():
    datos = _leer_archivo().get("seguridad", {})
    seg = dict(cfg.SEGURIDAD_DEFECTO)
    seg.update(datos)
    return seg


def leer_modelos():
    """Modelos seleccionados (tarea/revisor) guardados entre sesiones."""
    return _leer_archivo().get("modelos", {})


def leer_webhooks():
    """Configuración global de webhooks (Telegram, Discord, WhatsApp)."""
    return _leer_archivo().get("webhooks", {})


def leer_sidebar_ancho():
    """Ancho persistido del sidebar (px)."""
    return _leer_archivo().get("sidebar_ancho", cfg.SIDEBAR_ANCHO)


def guardar_sidebar_ancho(ancho: int):
    """Guarda el ancho del sidebar."""
    datos = _leer_archivo()
    datos["sidebar_ancho"] = ancho
    _escribir(datos)


def leer_config_proyecto(nombre):
    """Configuración guardada para un proyecto concreto (sin fusionar).

    Los valores globales (tema/seguridad/webhooks/modelos) actúan como
    base; lo que haya dentro de proyectos[nombre]["config"] gana a esa base.
    """
    proy = cargar().get(nombre)
    return proy.get("config", {}) if proy else {}


def guardar_config_proyecto(proyectos, nombre, config):
    """Persiste la configuración específica del proyecto junto a su registro.

    No re-añade el proyecto si ya no existe en el registro (p. ej. tras
    "Quitar"): un nombre eliminado no debe reaparecer al guardar su config.
    """
    if nombre not in proyectos:
        return
    datos = _leer_archivo()
    datos["proyectos"] = proyectos
    proyectos.setdefault(nombre, {})["config"] = config
    _escribir(datos)


def guardar(proyectos, tema=None, seguridad=None, webhooks=None, modelos=None):
    datos = _leer_archivo()
    datos["proyectos"] = proyectos
    if tema:
        datos["tema"] = tema
    if seguridad is not None:
        datos["seguridad"] = seguridad
    if webhooks is not None:
        datos["webhooks"] = webhooks
    if modelos is not None:
        datos["modelos"] = modelos
    _escribir(datos)
