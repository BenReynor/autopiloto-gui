#!/usr/bin/env python3
"""Tests de 03_backend.sh: el gate no puede dar verde con el backend roto.

Regresión del bug: las cuatro llamadas de `curl` eran `curl -s`, que devuelve 0
aunque la respuesta sea 404 o 500. El bucle de endpoints marcaba `ok` para un 404
y el check terminaba con exit 0, así que un backend con las rutas rotas pasaba el
gate.

Poner `-f` a pelo tampoco vale: aborta con "HTTP 404" y descarta el cuerpo, que es
donde FastAPI/Django explican el motivo ("detail": "no encontrado"). La solución es
leer el código con `-w '%{http_code}'` y conservar el cuerpo para el diagnóstico.

Se levanta un servidor HTTP real (http.server en un hilo) para probar los códigos de
verdad, en vez de simular curl.

Sobre el stub de `lsof`: el check mata con `kill -9` cualquier proceso que escuche en
el puerto que deduce de SERVE_URL. En estos tests ese puerto es el del servidor de
test, cuyo socket pertenece al propio proceso de pytest, así que sin el stub el
check se mataría a sí mismo. El `kill -9` por puerto está fuera del alcance de este
cambio (decisión explícita: se mantiene tal cual) y consta en
docs/BUGS_CONOCIDOS.md; aquí se anula con un `lsof` que nunca encuentra nada.
"""

import http.server
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RAIZ = Path(__file__).resolve().parent.parent
CHECK = RAIZ / "autopiloto_gui" / "plantillas_data" / "gate_checks" / "03_backend.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or os.name == "nt",
    reason="harness POSIX (gate.sh en bash): se valida en Linux")

PENDIENTE = 100  # puerto sin servicio, para probar "no responde"


class _Handler(http.server.BaseHTTPRequestHandler):
    """Responde con el código que marque la ruta en `self.server.respuestas`."""

    def do_GET(self):
        self._responder()

    def do_POST(self):
        self._responder()

    def _responder(self):
        status, cuerpo = self.server.respuestas.get(
            self.path.split("?")[0], (404, "no encontrado"))
        datos = cuerpo.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(datos)))
        self.end_headers()
        self.wfile.write(datos)

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def servidor():
    """Servidor HTTP local en un hilo; `respuestas` se rellena por test."""
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    httpd.respuestas = {}
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd
    httpd.shutdown()
    httpd.server_close()


def _preparar(tmp_path, endpoints=None):
    """Copia el check a un temporal y crea un `lsof` inerte. Devuelve el proyecto."""
    proyecto = tmp_path / "proyecto"
    proyecto.mkdir(exist_ok=True)
    shutil.copy2(CHECK, proyecto / "check.sh")
    if endpoints is not None:
        (proyecto / "endpoints.txt").write_text(
            "".join(f"{e}\n" for e in endpoints), encoding="utf-8")
    binstub = tmp_path / "bin"
    binstub.mkdir(exist_ok=True)
    lsof = binstub / "lsof"
    lsof.write_text("#!/bin/sh\n# stub: ningún puerto aparece ocupado\nexit 1\n",
                    encoding="utf-8")
    lsof.chmod(0o755)
    return proyecto, binstub


def _correr(proyecto, binstub, url, endpoints=None, **extra):
    """Ejecuta el check real. `url` es la base del servidor (o un puerto muerto)."""
    env = {
        "PATH": f"{binstub}{os.pathsep}{os.environ['PATH']}",
        "HOME": os.environ.get("HOME", "/tmp"),
        "PROYECTO": str(proyecto),
        "SERVE_CMD": "true",
        "SERVE_URL": url,
        "TOKEN_URL": "",
        "USUARIO": "",
        "CLAVE": "",
        "ENDPOINTS": "",
        "PY_BACKEND": sys.executable,
    }
    env.update(extra)
    res = subprocess.run(
        ["bash", str(proyecto / "check.sh")],
        capture_output=True, text=True, timeout=90,
        cwd=str(proyecto), env=env,
    )
    return res.returncode, res.stdout + res.stderr


def _url(servidor):
    return f"http://127.0.0.1:{servidor.server_address[1]}"


def _con_respuestas(servidor, respuestas):
    servidor.respuestas = respuestas


# ─── Endpoints: 404/500 ya no son verdes ────────────────────────────────

def test_endpoint_404_falla_el_gate(tmp_path, servidor):
    """Un endpoint que devuelve 404 debe hacer fallar el check."""
    _con_respuestas(servidor, {"/api/roto": (404, '{"detail":"no encontrado"}')})
    proyecto, binstub = _preparar(tmp_path, ["roto"])
    rc, out = _correr(proyecto, binstub, _url(servidor))
    assert rc == 1, f"se esperaba rc=1 con un 404:\n{out}"
    assert "✗" in out
    assert "404" in out


def test_endpoint_500_falla_con_el_cuerpo_en_el_log(tmp_path, servidor):
    """Un 500 falla y además muestra el cuerpo, que es el diagnóstico útil."""
    _con_respuestas(servidor,
                    {"/api/error": (500, '{"detail":"boom en la base de datos"}')})
    proyecto, binstub = _preparar(tmp_path, ["error"])
    rc, out = _correr(proyecto, binstub, _url(servidor))
    assert rc == 1, f"se esperaba rc=1 con un 500:\n{out}"
    assert "500" in out
    assert "boom en la base de datos" in out, (
        f"el cuerpo del error no llegó al log, no hay diagnóstico:\n{out}")


def test_endpoint_404_no_pisa_al_siguiente(tmp_path, servidor):
    """Un endpoint roto marca error, pero los sanos se siguen evaluando."""
    _con_respuestas(servidor, {
        "/api/roto": (404, "nope"),
        "/api/bueno": (200, '{"ok":true}'),
    })
    proyecto, binstub = _preparar(tmp_path, ["roto", "bueno"])
    rc, out = _correr(proyecto, binstub, _url(servidor))
    assert rc == 1
    assert "✓" in out and "api/bueno" in out


def test_endpoints_sanos_pasan(tmp_path, servidor):
    """Con todos los endpoints en 2xx, el check pasa."""
    _con_respuestas(servidor, {
        "/": (200, "{}"),
        "/api/uno": (200, '{"ok":true}'),
        "/api/dos": (201, '{"ok":true}'),
    })
    proyecto, binstub = _preparar(tmp_path, ["uno", "dos"])
    rc, out = _correr(proyecto, binstub, _url(servidor))
    assert rc == 0, f"se esperaba rc=0:\n{out}"
    assert "✗" not in out


def test_endpoint_307_falla(tmp_path, servidor):
    """Un 3xx se considera ruta mal escrita y falla, diciendo el código."""
    _con_respuestas(servidor, {"/api/sin-barra": (307, "")})
    proyecto, binstub = _preparar(tmp_path, ["sin-barra"])
    rc, out = _correr(proyecto, binstub, _url(servidor))
    assert rc == 1
    assert "307" in out


def test_cuerpo_multilinea_se_resume_en_una_linea(tmp_path, servidor):
    """Un cuerpo con saltos de línea no rompe el formato del log."""
    _con_respuestas(servidor, {"/api/largo": (500, json_dumps_multilinea())})
    proyecto, binstub = _preparar(tmp_path, ["largo"])
    rc, out = _correr(proyecto, binstub, _url(servidor))
    assert rc == 1
    lineas = [ln for ln in out.splitlines() if "respuesta:" in ln]
    assert lineas, f"no se imprimió el resumen del cuerpo:\n{out}"
    assert len(lineas[0]) < 260, "el resumen no se recortó"


def json_dumps_multilinea():
    return '{"detail": "linea 1",\n "otro": "linea 2",\n "cola": "linea 3"}'


# ─── Arranque: un 404 en la raíz NO es un backend caído ─────────────────

def test_raiz_404_no_se_toma_por_backend_caido(tmp_path, servidor):
    """Lo que prueba que el servidor arrancó es que responda HTTP, no el 2xx.

    Una API sin ruta "/" devuelve 404 en la raíz y está perfectamente sana (es lo
    normal en FastAPI y Express). Si el check exigiera 2xx aquí, tumbaría casi
    todos los proyectos reales.
    """
    _con_respuestas(servidor, {
        "/": (404, "Not Found"),
        "/api/ok": (200, "{}"),
    })
    proyecto, binstub = _preparar(tmp_path, ["ok"])
    rc, out = _correr(proyecto, binstub, _url(servidor))
    assert rc == 0, f"un 404 en la raíz no debe tumbar el gate:\n{out}"
    assert "backend responde" in out


def test_sin_respuesta_http_falla(tmp_path):
    """Si no hay respuesta (000), el backend sí está caído y se avisa."""
    proyecto, binstub = _preparar(tmp_path, [])
    rc, out = _correr(proyecto, binstub, f"http://127.0.0.1:{PENDIENTE}")
    assert rc == 1
    assert "no responde" in out


# ─── Token: un 401 debe explicar por qué ────────────────────────────────

def test_token_401_falla_con_el_mensaje_del_servidor(tmp_path, servidor):
    """Credenciales malas: el cuerpo de la respuesta lo dice y hay que mostrarlo."""
    _con_respuestas(servidor, {"/api/token": (401, '{"detail":"credenciales incorrectas"}')})
    proyecto, binstub = _preparar(tmp_path, [])
    rc, out = _correr(proyecto, binstub, _url(servidor),
                      TOKEN_URL=f"{_url(servidor)}/api/token")
    assert rc == 1, f"se esperaba rc=1 con un 401 en el login:\n{out}"
    assert "401" in out
    assert "credenciales incorrectas" in out


def test_token_valido_llega_a_los_endpoints(tmp_path, servidor):
    """Con token válido, los endpoints se piden autenticados."""
    pedidos = []
    original = _Handler._responder

    def _spy(self):
        pedidos.append((self.path, self.headers.get("Authorization")))
        return original(self)

    _Handler._responder = _spy
    try:
        _con_respuestas(servidor, {
            "/api/token": (200, '{"access":"jwt-falso-123"}'),
            "/api/privado": (200, "{}"),
        })
        proyecto, binstub = _preparar(tmp_path, ["privado"])
        rc, out = _correr(proyecto, binstub, _url(servidor),
                          TOKEN_URL=f"{_url(servidor)}/api/token",
                          USUARIO="admin", CLAVE="secreto")
    finally:
        _Handler._responder = original

    assert rc == 0, f"se esperaba rc=0:\n{out}"
    auths = [a for ruta, a in pedidos if ruta == "/api/privado"]
    assert auths == ["Bearer jwt-falso-123"], (
        f"el endpoint no se pidió autenticado: {pedidos}")


# ─── Sin endpoints y sin SERVE_CMD: comportamiento intacto ───────────────

def test_sin_endpoints_solo_comprueba_arranque(tmp_path, servidor):
    """Decisión explícita del usuario: lista vacía = aviso, no fallo."""
    _con_respuestas(servidor, {"/": (404, "")})
    proyecto, binstub = _preparar(tmp_path, [])
    rc, out = _correr(proyecto, binstub, _url(servidor))
    assert rc == 0, f"sin endpoints no debe fallar:\n{out}"
    assert "sin endpoints configurados" in out


def test_serve_cmd_vacio_omite_el_check(tmp_path):
    """SERVE_CMD vacío sigue omitiendo el check por completo."""
    proyecto, binstub = _preparar(tmp_path, [])
    rc, out = _correr(proyecto, binstub, "", SERVE_CMD="")
    assert rc == 0
    assert "se omite el check de backend" in out


# ─── Ejecución aislada ───────────────────────────────────────────────────

def test_check_funciona_sin_env_sh(tmp_path, servidor):
    """El check debe poder correr suelto, sin el `ok` que define gate.sh.

    Ejecutado como proceso independiente no hereda las funciones de gate.sh. Si
    `ok` no estuviera definida, bash daría rc=127, el check seguiría (no hay
    `set -e`) y saldría con exit 0: verde sin comprobar nada.
    """
    _con_respuestas(servidor, {"/": (200, ""), "/api/ok": (200, "{}")})
    proyecto, binstub = _preparar(tmp_path, ["ok"])
    rc, out = _correr(proyecto, binstub, _url(servidor))
    assert rc == 0, out
    assert "[GATE] ✓" in out, f"el check no pudo imprimir su ok: {out}"
    assert "orden no encontrada" not in out
