#!/usr/bin/env python3
"""Tests del consentimiento de primer uso del gate (consentimiento.py)."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dedalo import consentimiento  # noqa: E402


@pytest.fixture(autouse=True)
def config_dir_aislado(tmp_path, monkeypatch):
    """Nunca tocar el ~/.config real del usuario durante los tests."""
    monkeypatch.setattr(consentimiento, "CONFIG_DIR", str(tmp_path / "cfg"))


def _proyecto_con_checks(tmp_path, contenido="exit 0\n"):
    proyecto = tmp_path / "proyecto"
    checks = proyecto / "gate_checks"
    checks.mkdir(parents=True)
    (checks / "01_x.sh").write_text(contenido, encoding="utf-8")
    return str(proyecto)


def test_sin_gate_checks_no_pide_consentimiento(tmp_path):
    proyecto = tmp_path / "vacio"
    proyecto.mkdir()
    assert consentimiento.manifest(str(proyecto)) == ""
    assert consentimiento.concedido(str(proyecto), {}) is True
    assert consentimiento.ficheros(str(proyecto)) == []


def test_manifest_estable_y_sensible_al_contenido(tmp_path):
    proyecto = _proyecto_con_checks(tmp_path)
    m1 = consentimiento.manifest(proyecto)
    assert m1 and m1 == consentimiento.manifest(proyecto)
    (tmp_path / "proyecto" / "gate_checks" / "01_x.sh").write_text(
        "exit 1\n", encoding="utf-8")
    assert consentimiento.manifest(proyecto) != m1


def test_manifest_sensible_a_ficheros_nuevos(tmp_path):
    proyecto = _proyecto_con_checks(tmp_path)
    m1 = consentimiento.manifest(proyecto)
    (tmp_path / "proyecto" / "gate_checks" / "02_y.py").write_text(
        "def run(env):\n    return 0\n", encoding="utf-8")
    assert consentimiento.manifest(proyecto) != m1


def test_concedido_por_entorno_persiste_la_confianza(tmp_path):
    proyecto = _proyecto_con_checks(tmp_path)
    assert consentimiento.concedido(
        proyecto, {consentimiento.CONSENT_ENV: "1"}) is True
    # quedó persistida: sin entorno, el mismo manifiesto ya está aprobado
    assert consentimiento.concedido(proyecto, {}) is True


def test_concedido_falso_sin_entorno_ni_confianza(tmp_path):
    proyecto = _proyecto_con_checks(tmp_path)
    assert consentimiento.concedido(proyecto, {}) is False


def test_confiar_y_revocar(tmp_path):
    proyecto = _proyecto_con_checks(tmp_path)
    assert consentimiento.esta_confiado(proyecto) is False
    consentimiento.confiar(proyecto)
    assert consentimiento.esta_confiado(proyecto) is True
    consentimiento.revocar(proyecto)
    assert consentimiento.esta_confiado(proyecto) is False


def test_cambiar_los_checks_exige_consentimiento_de_nuevo(tmp_path):
    proyecto = _proyecto_con_checks(tmp_path)
    consentimiento.confiar(proyecto)
    assert consentimiento.esta_confiado(proyecto) is True
    (tmp_path / "proyecto" / "gate_checks" / "01_x.sh").write_text(
        "exit 2\n", encoding="utf-8")
    assert consentimiento.esta_confiado(proyecto) is False


def test_ficheros_lista_los_checks(tmp_path):
    proyecto = _proyecto_con_checks(tmp_path)
    (tmp_path / "proyecto" / "gate_checks" / "_env.sh").write_text(
        "", encoding="utf-8")
    assert consentimiento.ficheros(proyecto) == ["01_x.sh", "_env.sh"]
