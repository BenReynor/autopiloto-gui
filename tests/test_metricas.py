#!/usr/bin/env python3
"""Tests para metricas.py - parsing de progreso.log"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autopiloto_gui.metricas import parsear_log

SAMPLE_LOG = """[2025-01-15 10:00:00] [1/40] Tarea 1: arreglar login -> autopiloto/2025-01-15/t1
[2025-01-15 10:02:00] ✔ commit: Tarea 1: arreglar login
[2025-01-15 10:02:00] Costo estimado acumulado: 0.50 USD
[2025-01-15 10:05:00] [2/40] Tarea 2: validar email -> autopiloto/2025-01-15/t2
[2025-01-15 10:08:00] ✗ tarea bloqueada tras 2 intentos. Marcada [B] en plan.md
[2025-01-15 10:08:00] Costo estimado acumulado: 1.00 USD
[2025-01-15 10:10:00] [3/40] Tarea 3: tests unitarios -> autopiloto/2025-01-15/t3
[2025-01-15 10:15:00] ✔ commit: Tarea 3: tests unitarios
[2025-01-15 10:15:00] Costo estimado acumulado: 1.50 USD
[2025-01-15 10:20:00] == AUTOPILOTO FINALIZADO (iter=3, rama=autopiloto/2025-01-15, costo≈1.50) ==
"""

def test_parsear_log_basico():
    """Test parsing básico de log con tareas hechas y bloqueadas"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
        f.write(SAMPLE_LOG)
        log_path = f.name

    try:
        result = parsear_log(log_path)

        # Verificar estructura
        assert "iteraciones" in result
        assert "series" in result
        assert "resumen" in result

        # Verificar iteraciones parseadas
        iteraciones = result["iteraciones"]
        assert len(iteraciones) == 3

        # Tarea 1 - hecha
        assert iteraciones[0]["tarea"] == "Tarea 1: arreglar login"
        assert iteraciones[0]["estado"] == "hecha"
        assert iteraciones[0]["gate"] == "ok"
        assert iteraciones[0]["revisor"] == "pass"

        # Tarea 2 - bloqueada
        assert iteraciones[1]["tarea"] == "Tarea 2: validar email"
        assert iteraciones[1]["estado"] == "bloqueada"

        # Tarea 3 - hecha
        assert iteraciones[2]["tarea"] == "Tarea 3: tests unitarios"
        assert iteraciones[2]["estado"] == "hecha"

        # Verificar resumen
        resumen = result["resumen"]
        assert resumen["total"] == 3
        assert resumen["hechas"] == 2
        assert resumen["bloqueadas"] == 1
        assert resumen["coste_total"] == 1.50

        # Verificar series
        series = result["series"]
        assert len(series["tareas_hora"]) == 3
        assert len(series["coste_acum"]) == 3

        print("✅ test_parsear_log_basico PASSED")
    finally:
        os.unlink(log_path)


def test_parsear_log_vacio():
    """Test con log vacío o inexistente"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
        f.write("")
        log_path = f.name

    try:
        result = parsear_log(log_path)
        assert result["resumen"]["total"] == 0
        assert len(result["iteraciones"]) == 0
        print("✅ test_parsear_log_vacio PASSED")
    finally:
        os.unlink(log_path)


def test_parsear_log_solo_inicio():
    """Test log solo con inicios de iteración (sin final)"""
    log = """[2025-01-15 10:00:00] [1/40] Tarea 1 -> autopiloto/2025-01-15/t1
[2025-01-15 10:05:00] [2/40] Tarea 2 -> autopiloto/2025-01-15/t2
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
        f.write(log)
        log_path = f.name

    try:
        result = parsear_log(log_path)
        assert len(result["iteraciones"]) == 2
        assert result["iteraciones"][0]["estado"] == "en_progreso"
        assert result["iteraciones"][1]["estado"] == "en_progreso"
        print("✅ test_parsear_log_solo_inicio PASSED")
    finally:
        os.unlink(log_path)


def test_series_temporales():
    """Verificar que las series temporales se generan correctamente"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
        f.write(SAMPLE_LOG)
        log_path = f.name

    try:
        result = parsear_log(log_path)
        series = result["series"]

        # tareas_hora acumulativo: 1, 1, 2 (la primera hecha, segunda bloqueada, tercera hecha)
        tareas = [v for _, v in series["tareas_hora"]]
        assert tareas == [1, 1, 2]

        # coste acumulativo
        costes = [v for _, v in series["coste_acum"]]
        assert costes == [0.5, 1.0, 1.5]

        print("✅ test_series_temporales PASSED")
    finally:
        os.unlink(log_path)


def test_coste_con_coma_decimal():
    """El log real (locale es_CO) escribe '0,50 USD' con coma decimal."""
    log = """[2025-01-15 10:00:00] [1/40] Tarea 1 -> autopiloto/tareas/2025-01-15/t1
[2025-01-15 10:02:00] ✔ commit: Tarea 1
[2025-01-15 10:02:00] Costo estimado acumulado: 0,50 USD
[2025-01-15 10:05:00] [2/40] Tarea 2 -> autopiloto/tareas/2025-01-15/t2
[2025-01-15 10:07:00] ✔ commit: Tarea 2
[2025-01-15 10:07:00] Costo estimado acumulado: 1,00 USD
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
        f.write(log)
        log_path = f.name

    try:
        result = parsear_log(log_path)
        # Formato nuevo de ramas tolerado: autopiloto/tareas/FECHA/tN
        assert len(result["iteraciones"]) == 2
        assert result["iteraciones"][0]["tarea"] == "Tarea 1"
        assert result["iteraciones"][0]["duracion_s"] == 120
        assert result["resumen"]["coste_total"] == 1.00
        costes = [v for _, v in result["series"]["coste_acum"]]
        assert costes == [0.50, 1.00]
        print("✅ test_coste_con_coma_decimal PASSED")
    finally:
        os.unlink(log_path)


def test_coste_por_iteracion():
    """Coste exacto por iteración: cada tarea suma su propio coste a la serie
    acumulada (formato log_autopiloto: 'Costo iteración N: X USD')."""
    log = """[2025-01-15 10:00:00] == Iteración 1: Tarea A (rama autopiloto/tareas/2025-01-15/t1) ==
[2025-01-15 10:02:00] Costo iteración 1: 1.00 USD
[2025-01-15 10:02:00] ✔ commit: Tarea A
[2025-01-15 10:05:00] == Iteración 2: Tarea B (rama autopiloto/tareas/2025-01-15/t2) ==
[2025-01-15 10:07:00] Costo iteración 2: 0.50 USD
[2025-01-15 10:07:00] ✔ commit: Tarea B
[2025-01-15 10:10:00] == Iteración 3: Tarea C (rama autopiloto/tareas/2025-01-15/t3) ==
[2025-01-15 10:12:00] Costo iteración 3: 0.75 USD
[2025-01-15 10:12:00] ✗ tarea bloqueada tras 2 intentos. Marcada [B] en plan.md
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
        f.write(log)
        log_path = f.name

    try:
        result = parsear_log(log_path)
        iters = result["iteraciones"]
        assert [it["iter"] for it in iters] == [1, 2, 3]
        # Coste exacto asignado a cada iteración (el acumulado ya no pisa)
        assert iters[0]["coste_usd"] == 1.00
        assert iters[1]["coste_usd"] == 0.50
        assert iters[2]["coste_usd"] == 0.75
        # Serie acumulada por iteración
        costes = [v for _, v in result["series"]["coste_acum"]]
        assert costes == [1.00, 1.50, 2.25]
        assert result["resumen"]["coste_total"] == 2.25
        print("✅ test_coste_por_iteracion PASSED")
    finally:
        os.unlink(log_path)


if __name__ == "__main__":
    test_parsear_log_basico()
    test_parsear_log_vacio()
    test_parsear_log_solo_inicio()
    test_series_temporales()
    test_coste_con_coma_decimal()
    test_coste_por_iteracion()
    print("\n🎉 Todos los tests de metricas.py PASARON")
