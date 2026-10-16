"""Consentimiento de primer uso para el gate del proyecto (gate_checks/).

Ejecutar el gate corre código que vive en el repo destino (gate.sh,
gate_checks/*.sh|.py) con los privilegios del usuario: un repo clonado puede
traer comandos arbitrarios. Antes del primer gate de un proyecto se muestra qué
se va a ejecutar y se exige una decisión explícita, que se recuerda ligada a un
hash del contenido de los checks: si los checks cambian, se vuelve a preguntar.

Opt-in sin diálogo: `DEDALO_GATE_CONSENT=1` (recomendado en CI). La confianza se
guarda en `~/.config/dedalo/confianza.json` (0o600, fuera del repo, de modo que
el propio repo no pueda auto-concederse el permiso).
"""

import hashlib
import json
import os
import tempfile

from .configuracion import CONFIG_DIR

CONSENT_ENV = "DEDALO_GATE_CONSENT"


def _dir_checks(proyecto):
    return os.path.join(proyecto, "gate_checks")


def ficheros(proyecto):
    """Relative paths of the files under `gate_checks/` (sorted)."""
    base = _dir_checks(proyecto)
    if not os.path.isdir(base):
        return []
    salida = []
    for raiz, _dirs, nombres in os.walk(base):
        for nombre in nombres:
            salida.append(os.path.relpath(os.path.join(raiz, nombre), base))
    return sorted(salida)


def manifest(proyecto):
    """SHA-256 of the `gate_checks/` contents ("" if the directory is absent).

    Includes each file's relative path and the hash of its content, so any
    change (add/remove/edit/rename) yields a different manifest.
    """
    base = _dir_checks(proyecto)
    if not os.path.isdir(base):
        return ""
    h = hashlib.sha256()
    for rel in ficheros(proyecto):
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        try:
            with open(os.path.join(base, rel), "rb") as f:
                h.update(hashlib.sha256(f.read()).digest())
        except OSError:
            h.update(b"?")
    return h.hexdigest()


def _ruta_confianza():
    return os.path.join(CONFIG_DIR, "confianza.json")


def _leer_confianza():
    try:
        with open(_ruta_confianza(), encoding="utf-8") as f:
            datos = json.load(f)
    except (OSError, ValueError):
        return {}
    return datos if isinstance(datos, dict) else {}


def esta_confiado(proyecto, manifiesto=None):
    """¿El usuario ya aprobó ESTE contenido del gate de ESTE proyecto?"""
    manifiesto = manifest(proyecto) if manifiesto is None else manifiesto
    if not manifiesto:
        return True
    return _leer_confianza().get(os.path.abspath(proyecto)) == manifiesto


def confiar(proyecto, manifiesto=None):
    """Persiste la aprobación del manifiesto actual (escritura atómica 0o600)."""
    manifiesto = manifest(proyecto) if manifiesto is None else manifiesto
    datos = _leer_confianza()
    datos[os.path.abspath(proyecto)] = manifiesto
    ruta = _ruta_confianza()
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(ruta))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(tmp, ruta)
        try:
            os.chmod(ruta, 0o600)
        except OSError:
            pass
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def revocar(proyecto):
    """Olvida la aprobación de un proyecto (vuelve a pedir consentimiento)."""
    datos = _leer_confianza()
    if datos.pop(os.path.abspath(proyecto), None) is not None:
        ruta = _ruta_confianza()
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=2, sort_keys=True)


def concedido(proyecto, entorno=None):
    """¿Puede correr el gate?

    True si no hay checks, si `DEDALO_GATE_CONSENT=1` (que además persiste la
    confianza) o si el manifiesto actual ya fue aprobado. False en cualquier
    otro caso: sin consentimiento, el gate de un repo desconocido no se ejecuta.
    """
    entorno = os.environ if entorno is None else entorno
    if not manifest(proyecto):
        return True
    if str(entorno.get(CONSENT_ENV, "")).strip() == "1":
        try:
            confiar(proyecto)
        except OSError:
            pass
        return True
    return esta_confiado(proyecto)
