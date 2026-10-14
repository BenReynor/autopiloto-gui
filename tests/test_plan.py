#!/usr/bin/env python3
"""Tests para plan.py - parsing de plan.md"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dedalo.plan import Plan

PLAN_SAMPLE = """# PLAN — Test

## Tareas

- [ ] Tarea 1: Primera tarea
      criterio: test 1 pasa

- [x] Tarea 2: Ya hecha
      criterio: test 2 pasa

- [B] Tarea 3: Bloqueada
      criterio: test 3 falla

- [ ] Tarea 4: Sin criterio
"""

def test_plan_cargar():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write(PLAN_SAMPLE)
        path = f.name

    try:
        plan = Plan(path)
        plan.cargar()

        tareas = plan.tareas
        assert len(tareas) == 4

        # Tarea 1 - pendiente
        assert tareas[0]["estado"] == "pendiente"
        assert "Tarea 1" in tareas[0]["texto"]
        assert tareas[0]["linea"] == 5

        # Tarea 2 - hecha
        assert tareas[1]["estado"] == "hecha"
        assert "Tarea 2" in tareas[1]["texto"]

        # Tarea 3 - bloqueada
        assert tareas[2]["estado"] == "bloqueada"
        assert "Tarea 3" in tareas[2]["texto"]

        # Tarea 4 - pendiente
        assert tareas[3]["estado"] == "pendiente"

        # Conteo
        pend, hechas, bloqueadas = plan.conteo()
        assert pend == 2
        assert hechas == 1
        assert bloqueadas == 1

        print("✅ test_plan_cargar PASSED")
    finally:
        os.unlink(path)


def test_plan_guardar():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write(PLAN_SAMPLE)
        path = f.name

    try:
        plan = Plan(path)
        plan.cargar()

        # Modificar: marcar primera como hecha
        nuevo_texto = plan.texto.replace("- [ ] Tarea 1", "- [x] Tarea 1")
        plan.guardar(nuevo_texto)

        # Recargar y verificar
        plan2 = Plan(path)
        plan2.cargar()
        pend, hechas, bloqueadas = plan2.conteo()
        assert hechas == 2
        assert pend == 1

        print("✅ test_plan_guardar PASSED")
    finally:
        os.unlink(path)


def test_plan_inexistente():
    plan = Plan("/ruta/que/no/existe/plan.md")
    assert not plan.existe()
    plan.cargar()
    tareas = plan.tareas
    assert len(tareas) == 0

    pend, hechas, bloqueadas = plan.conteo()
    assert pend == hechas == bloqueadas == 0
    print("✅ test_plan_inexistente PASSED")


def _plan_con_tmp(texto):
    f = tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False)
    f.write(texto)
    f.close()
    plan = Plan(f.name)
    plan.cargar()
    return plan, f.name


def test_marcar_primera_x():
    plan, path = _plan_con_tmp(PLAN_SAMPLE)
    try:
        assert plan.marcar_primera("x") is True
        pend, hechas, bloqueadas = plan.conteo()
        assert (pend, hechas, bloqueadas) == (1, 2, 1)
        assert "- [x] Tarea 1: Primera tarea" in plan.texto
        assert plan.tareas[0]["estado"] == "hecha"
        # No toca más de una tarea
        assert plan.tareas[3]["estado"] == "pendiente"
    finally:
        os.unlink(path)


def test_marcar_primera_B():
    plan, path = _plan_con_tmp(PLAN_SAMPLE)
    try:
        assert plan.marcar_primera("B") is True
        assert "- [B] Tarea 1: Primera tarea" in plan.texto
        assert plan.tareas[0]["estado"] == "bloqueada"
    finally:
        os.unlink(path)


def test_marcar_primera_solo_columna_cero():
    plan, path = _plan_con_tmp(
        "- [ ] Fuera\n\n  - [ ] Indentada (no cuenta)\n")
    try:
        assert plan.marcar_primera("x") is True
        assert "- [x] Fuera" in plan.texto
        assert "  - [ ] Indentada" in plan.texto
    finally:
        os.unlink(path)


def test_marcar_primera_sin_pendientes():
    plan, path = _plan_con_tmp("- [x] hecha\n- [B] bloqueada\n")
    try:
        assert plan.marcar_primera("x") is False
        assert "- [x] hecha" in plan.texto
    finally:
        os.unlink(path)


def test_marcar_primera_texto_persistido_en_disco():
    plan, path = _plan_con_tmp(PLAN_SAMPLE)
    try:
        plan.marcar_primera("x")
        with open(path, encoding="utf-8") as f:
            contenido = f.read()
        assert "- [x] Tarea 1: Primera tarea" in contenido
        plan2 = Plan(path)
        plan2.cargar()
        pend, hechas, bloqueadas = plan2.conteo()
        assert (pend, hechas, bloqueadas) == (1, 2, 1)
    finally:
        os.unlink(path)


if __name__ == "__main__":
    test_plan_cargar()
    test_plan_guardar()
    test_plan_inexistente()
    print("\n🎉 Todos los tests de plan.py PASARON")
