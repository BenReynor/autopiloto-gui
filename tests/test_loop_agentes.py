#!/usr/bin/env python3
"""Tests de autopiloto_gui.loop_agentes (port de la capa de agentes del loop).

Se toman de las secciones de autopiloto.sh (cli_agente, agente_ok,
detectar_agente, elegir_revisor, sin_autenticacion, tokens_agotados,
_registrar_metrica, revisar_diff) manteniendo la MISMA semántica, incluyendo
la corroboración de auth (sólo aborta si además no hubo trabajo).
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autopiloto_gui.loop_agentes import (  # noqa: E402
    agente_ok,
    costo_por_modelo,
    detectar_agente,
    elegir_revisor,
    extraer_tokens,
    registrar_metrica,
    revisar_diff,
    run_agente,
    sin_autenticacion,
    tokens_agotados,
)
from autopiloto_gui.loop_args import parse_args  # noqa: E402


def _config(tmp_path, env_extra=None):
    from autopiloto_gui.loop import Config
    env = {
        "PATH": os.environ.get("PATH", ""),
        "AGENTE_TAREA": "opencode",
        "VOZ": "0",
        "MAX_ITER": "1",
        "TIMEOUT_POR_TAREA": "60",
        "TIMEOUT_NAVEGADOR": "60",
        "TIMEOUT_REVISION_MANUAL": "0",
    }
    env.update(env_extra or {})
    return Config(parse_args(["plan.md"]), environ=env, proyecto=str(tmp_path))


def _leer(ruta):
    try:
        with open(ruta, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _binario_falso(tmp_path, nombre="opencode", cuerpo="true\n"):
    bin_ = tmp_path / "bin" / nombre
    bin_.parent.mkdir(parents=True, exist_ok=True)
    bin_.write_text("#!/usr/bin/env bash\n" + cuerpo, encoding="utf-8")
    bin_.chmod(0o755)
    return bin_


# ---------------------------------------------------------------- cli/agente_ok


def test_cli_agente_lee_cli_sobrescrito(tmp_path):
    bin_ = _binario_falso(tmp_path, "opencode")
    cfg = _config(tmp_path, {"CLI_OPENCODE": str(bin_)})
    assert agente_ok("opencode", cfg)


def test_agente_ok_falso_si_no_existe(tmp_path):
    cfg = _config(tmp_path, {"CLI_OPENCODE": "/no/existe/opencode"})
    assert not agente_ok("opencode", cfg)


# Binarios ineistentes en CLI_*: bloquean el `which <global>` del sistema.
_INE = "/no/existe/"

def test_detectar_agente_usa_primer_disponible(tmp_path):
    _binario_falso(tmp_path, "codex")
    cfg = _config(tmp_path, {"CLI_OPENCODE": _INE + "opencode",
                             "CLI_CODEX": str(tmp_path / "bin" / "codex")})
    cfg.agentes_preferidos = "opencode codex claude"
    assert detectar_agente(cfg) == "codex"


def test_detectar_agente_vacio_sin_ninguno(tmp_path):
    cfg = _config(tmp_path, {"CLI_OPENCODE": _INE + "opencode",
                             "CLI_CODEX": _INE + "codex",
                             "CLI_CLAUDE": _INE + "claude"})
    cfg.agentes_preferidos = "opencode codex claude"
    assert detectar_agente(cfg) == ""


def test_elegir_revisor_preferido_concreto(tmp_path):
    _binario_falso(tmp_path, "claude")
    cfg = _config(tmp_path, {
        "CLI_OPENCODE": _INE + "opencode",
        "CLI_CLAUDE": str(tmp_path / "bin" / "claude"),
        "AGENTE_REVISOR": "claude",
    })
    cfg.agente_tarea = "opencode"
    assert elegir_revisor(cfg) == "claude"


def test_elegir_revisor_otro_distinto_de_tarea(tmp_path):
    _binario_falso(tmp_path, "codex")
    _binario_falso(tmp_path, "claude")
    env = {
        "CLI_OPENCODE": _INE + "opencode",
        "CLI_CODEX": str(tmp_path / "bin" / "codex"),
        "CLI_CLAUDE": str(tmp_path / "bin" / "claude"),
    }
    cfg = _config(tmp_path, env)
    cfg.agentes_preferidos = "opencode codex claude"
    cfg.agente_tarea = "codex"
    # codex es el agente de tarea; el revisor prefiere otro agente.
    assert elegir_revisor(cfg) == "claude"


# --------------------------------------------------------------- auth / tokens


def test_sin_autenticacion_detecta_401_en_stderr(tmp_path):
    err = tmp_path / "out.err"
    out = tmp_path / "out"
    err.write_text("Authentication Error: HTTP 401 Unauthorized\n",
                   encoding="utf-8")
    out.write_text("intentando...", encoding="utf-8")
    assert sin_autenticacion(str(err), str(out), 1)
    assert not sin_autenticacion(str(err), str(out), 0)


def test_sin_autenticacion_falso_positivo_por_narrativa(tmp_path):
    """Una mención de *auth* en stdout no basta si la iteración produjo
    trabajo (corroborar=0): el loop no debe abortar."""
    err = tmp_path / "out.err"
    err.write_text("", encoding="utf-8")
    out = tmp_path / "out"
    # '401' suelto en narrativa NO es patrón de alta confianza.
    out.write_text("el cliente dice '401' en narrativa\n" * 5, encoding="utf-8")
    assert not sin_autenticacion(str(err), str(out), 0)
    assert not sin_autenticacion(str(err), str(out), 1)
    # Patrón REAL (HTTP 401) en stdout: con trabajo NO aborta, sin trabajo SÍ.
    out2 = tmp_path / "out2"
    out2.write_text("trabajo real\n" * 40 + "HTTP 401 Unauthorized\n",
                    encoding="utf-8")
    assert not sin_autenticacion(str(err), str(out2), 0)
    assert sin_autenticacion(str(err), str(out2), 1)
    # stderr con patrón claro aborta siempre que corrobore.
    err2 = tmp_path / "out2.err"
    err2.write_text("Please run opencode auth login\n", encoding="utf-8")
    assert sin_autenticacion(str(err2), str(out2), 1)


def test_tokens_agotados_detecta_cuota(tmp_path):
    out = tmp_path / "out"
    out.write_text("Error: insufficient_quota for the request",
                   encoding="utf-8")
    assert tokens_agotados(str(out))
    out.write_text("todo ok", encoding="utf-8")
    assert not tokens_agotados(str(out))


# ------------------------------------------------------------------- costes


def test_costo_por_modelo_distingue_tarifas():
    assert costo_por_modelo("anthropic/claude-3.5-sonnet", 1_000_000, 0) == 15
    assert costo_por_modelo("gpt-4o", 1_000_000, 0) == 30
    assert costo_por_modelo("gpt-3.5-turbo", 1_000_000, 0) == 0.5
    assert costo_por_modelo("opencode/big-pickle", 1_000_000, 1_000_000) == 4


def test_extraer_tokens_ultimo_usage():
    texto = ('{"usage":{"input_tokens":1,"output_tokens":2}}\n'
             '{"usage":{"input_tokens":100,"output_tokens":50}}')
    assert extraer_tokens(texto, "opencode") == (100, 50)


def test_extraer_tokens_codex_usa_tokens_used():
    texto = "tokens_used: 5\ntokens_used: 7"
    assert extraer_tokens(texto, "codex") == (0, 7)


def test_registrar_metrica_escribe_json_valido(tmp_path):
    cfg = _config(tmp_path)
    salida = tmp_path / "out"
    salida.write_text('{"usage":{"input_tokens":100,"output_tokens":100}}',
                      encoding="utf-8")
    registrar_metrica(cfg, "opencode", "", 1000, 0, str(salida), "t1", 1)
    lineas = _leer(cfg.metrics).splitlines()
    assert lineas, "metrics.jsonl vacío"
    d = json.loads(lineas[0])
    assert d["iter"] == 1 and d["agente"] == "opencode"
    assert d["tokens_in"] == 100 and d["tokens_out"] == 100
    assert d["costo_usd"] > 0 and isinstance(d["costo_usd"], float)
    assert d["tarea"] == "t1"


# ------------------------------------------------------------- run_agente


def test_run_agente_ejecuta_y_registra_metrica(tmp_path):
    salida = tmp_path / "out"
    bin_ = tmp_path / "bin" / "opencode"
    bin_.parent.mkdir(parents=True, exist_ok=True)
    bin_.write_text(
        "#!/usr/bin/env bash\necho '{\"usage\":{\"input_tokens\":5,"
        "\"output_tokens\":5}}'\nexit 0\n", encoding="utf-8")
    bin_.chmod(0o755)
    cfg = _config(tmp_path, {"CLI_OPENCODE": str(bin_)})
    cfg.timeout_por_tarea = 30

    rc, _vivo = run_agente(cfg, "opencode", str(salida), "", "prompt", "t1", 1)
    assert rc == 0
    assert json.loads(_leer(cfg.metrics).splitlines()[0])["rc"] == 0
    assert '{"usage":{"input_tokens":5' in salida.read_text(encoding="utf-8")


def test_run_agente_resuelve_auto(tmp_path):
    salida = tmp_path / "out"
    bin_ = tmp_path / "bin" / "opencode"
    bin_.parent.mkdir(parents=True, exist_ok=True)
    bin_.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    bin_.chmod(0o755)
    env = {"CLI_OPENCODE": str(bin_),
           "AGENTES_PREFERIDOS": "opencode",
           "AGENTE_TAREA": "auto"}
    cfg = _config(tmp_path, env)
    cfg.timeout_por_tarea = 30
    rc, _ = run_agente(cfg, "auto", str(salida), "", "prompt", "t1", 1)
    assert rc == 0


# ---------------------------------------------------------------- revisar_diff


def _revisor_falso(tmp_path, salida_texto):
    bin_ = tmp_path / "bin" / "claude"
    bin_.parent.mkdir(parents=True, exist_ok=True)
    bin_.write_text("#!/usr/bin/env bash\ncat <<'EOF'\n" + salida_texto +
                    "\nEOF\n", encoding="utf-8")
    bin_.chmod(0o755)
    return bin_


def test_revisar_diff_pass(tmp_path):
    bin_ = _revisor_falso(tmp_path, '{"usage":{"input_tokens":1,'
                                      '"output_tokens":1}}\nrazon\nVERDICT: PASS')
    cfg = _config(tmp_path, {"CLI_CLAUDE": str(bin_)})
    cfg.revisor = "claude"
    cfg.modelo_revisor = ""
    cfg.timeout_por_tarea = 30
    resultado, _fb = revisar_diff(cfg, "claude", "t1", "diff")
    assert resultado == "pass"


def test_revisar_diff_fail_devuelve_feedback(tmp_path):
    bin_ = _revisor_falso(tmp_path, 'falta arreglar el modulo\nVERDICT: FAIL')
    cfg = _config(tmp_path, {"CLI_CLAUDE": str(bin_)})
    cfg.timeout_por_tarea = 30
    resultado, fb = revisar_diff(cfg, "claude", "t1", "diff")
    assert resultado == "fail"
    assert "falta arreglar" in fb


def test_revisar_diff_sin_veredicto_como_fail(tmp_path):
    """Salida sin VERDICT: el revisor no pudo evaluar → FAIL (no sin_auth
    porque tampoco hay patrón de auth)."""
    bin_ = _revisor_falso(tmp_path, "no se que paso")
    cfg = _config(tmp_path, {"CLI_CLAUDE": str(bin_)})
    cfg.timeout_por_tarea = 30
    resultado, fb = revisar_diff(cfg, "claude", "t1", "diff")
    assert resultado == "fail"
    assert fb


def test_revisar_diff_auth_sin_veredicto(tmp_path):
    """Sin veredicto + patrón de auth → sin_auth (el loop aborta con 7)."""
    bin_ = _revisor_falso(
        tmp_path, "Please run claude /login\nveremos")
    cfg = _config(tmp_path, {"CLI_CLAUDE": str(bin_)})
    cfg.timeout_por_tarea = 30
    resultado, _fb = revisar_diff(cfg, "claude", "t1", "diff")
    assert resultado == "sin_auth"


def test_revisar_diff_auth_con_veredicto_es_falso_positivo(tmp_path):
    """Con VERDICT presente la mención de auth es narrativa: cuenta como
    pass (el revisor SÍ funcionó)."""
    bin_ = _revisor_falso(
        tmp_path, 'texto dice "401" pero reviso\nVERDICT: PASS')
    cfg = _config(tmp_path, {"CLI_CLAUDE": str(bin_)})
    cfg.timeout_por_tarea = 30
    resultado, _fb = revisar_diff(cfg, "claude", "t1", "diff")
    assert resultado == "pass"
