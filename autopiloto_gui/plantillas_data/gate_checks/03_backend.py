# 03_backend.py — Levanta el backend y prueba que responde y sirve endpoints.
# Port de 03_backend.sh para el orquestador portable (Windows sin bash).
#
#   SERVE_CMD    comando para arrancar el backend ("" = se omite el check)
#   SERVE_URL    URL base a la que llamar (ej: http://localhost:8000)
#   TOKEN_URL    endpoint de login para obtener token ("" = sin auth)
#   USUARIO/CLAVE credenciales de login
#   ENDPOINTS    lista "ep1 ep2 ..." (se unen como $SERVE_URL/api/$ep)
#
# Si existe endpoints.txt en la raíz, tiene prioridad (lo resuelve gate_env).
import json
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request


def _http(url, headers=None, body=None):
    """Devuelve (codigo, cuerpo). codigo 0 = sin respuesta HTTP (000)."""
    datos = body.encode("utf-8") if isinstance(body, str) else body
    req = urllib.request.Request(url, data=datos, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.getcode(), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        try:
            cuerpo = e.read().decode("utf-8", "replace")
        except Exception:
            cuerpo = ""
        return e.code, cuerpo
    except Exception:
        return 0, ""


def _responde(url):
    return _http(url)[0] != 0


def _resumen(texto):
    return texto.replace("\n", " ")[:200]


def _liberar_puerto(serve_url):
    m = re.search(r":(\d+)", serve_url or "")
    if not m or not shutil.which("lsof"):
        return
    try:
        salida = subprocess.run(
            ["lsof", "-ti", ":" + m.group(1)], capture_output=True, text=True)
        pids = [p for p in salida.stdout.split() if p.strip()]
        if pids:
            print(f"[GATE] \u26a0 puerto {m.group(1)} ocupado, liberando")
            subprocess.run(["kill", "-9"] + pids, capture_output=True)
            time.sleep(1)
    except OSError:
        pass


def _token(env):
    if not env.token_url:
        return ""
    body = "{}"
    if env.usuario:
        body = json.dumps({"username": env.usuario, "password": env.clave})
    code, cuerpo = _http(env.token_url, {"Content-Type": "application/json"}, body)
    try:
        d = json.loads(cuerpo)
        return d.get("access") or d.get("token") or d.get("token_type", "")
    except Exception:
        print(f"[GATE] \u2717 no se obtuvo token en {env.token_url} (HTTP {code})")
        if cuerpo:
            print(f"[GATE]   respuesta: {_resumen(cuerpo)}")
        return ""


def run(env):
    if env.serve_cmd is None:
        env.aviso("SERVE_CMD no configurado, se omite el check de backend")
        return 0

    base = env.serve_url or "http://localhost:8000"
    _liberar_puerto(env.serve_url)
    proc = env.lanzar(env.serve_cmd)
    try:
        for _ in range(15):
            if _responde(base + "/"):
                break
            time.sleep(1)
        if not _responde(base + "/"):
            env.fail(f"backend no responde en {base}")
            return 1
        env.ok(f"backend responde en {base}")

        token = ""
        if env.token_url:
            token = _token(env)
            if not token:
                return 1
            env.ok(f"token JWT en {env.token_url}")

        if not env.endpoints:
            env.aviso("sin endpoints configurados; solo comprobación de arranque")
            return 0

        err = 0
        for ep in env.endpoints:
            url = ep if ep.startswith("http") else f"{base}/api/{ep}"
            headers = {"Authorization": f"Bearer {token}"} if token else {}
            code, cuerpo = _http(url, headers)
            if 200 <= code < 300:
                env.ok(url)
            else:
                env.fail(f"{url} (HTTP {code})")
                if cuerpo:
                    print(f"[GATE]   respuesta: {_resumen(cuerpo)}")
                err = 1
        return 1 if err else 0
    finally:
        if proc is not None:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
