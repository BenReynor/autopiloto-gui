"""Métricas: parseo de progreso.log → series temporales para gráficas.

Extrae de cada iteración: tarea, estado, duración, coste, gate, revisor.
"""

import os
import re
from datetime import datetime
from typing import Any

# Formato timestamp en log: [YYYY-MM-DD HH:MM:SS]
TIMESTAMP_RE = r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]"

# Formato real del script: [TS] == Iteración N: TAREA (rama autopiloto/.../tN) ==
# La rama puede ser autopiloto/FECHA/tN (legado) o autopiloto/tareas/FECHA/tN.
LINEA_ITER_NUEVO = re.compile(
    TIMESTAMP_RE
    + r" == Iteración (\d+): (.+?) \(rama autopiloto/(?:tareas/)?\d{4}-\d{2}-\d{2}/t(\d+)\) =="
)
# Formato alternativo tolerado: [TS] [N/MAX] TAREA -> autopiloto/.../tN
LINEA_ITER_LEGACY = re.compile(
    TIMESTAMP_RE + r" \[(\d+)/(\d+)\] (.+?) -> autopiloto/(?:tareas/)?\d{4}-\d{2}-\d{2}/t(\d+)"
)
# Líneas de cierre de iteración tras el timestamp (commit / completada / BLOQUEADA)
LINEA_ESTADO = re.compile(TIMESTAMP_RE + r"\s*(?:✔|✗)?\s*(.+)")
LINEA_COSTE = re.compile(
    TIMESTAMP_RE + r" (?:Costo estimado acumulado:|💰 Costo estimado acumulado:)\s*([\d.]+)\s*USD"
)
LINEA_FIN = re.compile(
    TIMESTAMP_RE + r" == AUTOPILOTO FINALIZADO"
)


def _diff_seg(fecha_ini: str, fecha_fin: str) -> int:
    """Segundos entre dos timestamps `YYYY-MM-DD HH:MM:SS` (0 si no parsean)."""
    try:
        fmt = "%Y-%m-%d %H:%M:%S"
        a = datetime.strptime(fecha_ini, fmt)
        b = datetime.strptime(fecha_fin, fmt)
        return max(0, int((b - a).total_seconds()))
    except (ValueError, TypeError):
        return 0


def _inicio_iteracion(linea: str):
    """Devuelve (fecha, numero, tarea) si la línea abre una iteración o None."""
    m = LINEA_ITER_NUEVO.search(linea)
    if m:
        return m.group(1), int(m.group(2)), m.group(3).strip()
    m = LINEA_ITER_LEGACY.search(linea)
    if m:
        return m.group(1), int(m.group(5)), m.group(4).strip()
    return None


def parsear_log(ruta_log: str) -> dict[str, Any]:
    """
    Parsea progreso.log y devuelve diccionario con series temporales y tabla.

    Returns:
        {
            "iteraciones": [...],           # lista de dicts por iteración
            "series": {
                "tareas_hora": [(timestamp, acumuladas)],
                "coste_acum": [(timestamp, coste)],
                "gate": [(timestamp, ok, fail)],
                "revisor": [(timestamp, pass_, fail)],
            },
            "resumen": {
                "total": int,
                "hechas": int,
                "bloqueadas": int,
                "pendientes": int,
                "coste_total": float,
                "duracion_min": float,
            }
        }
    """
    if not os.path.isfile(ruta_log):
        return _vacío()

    with open(ruta_log, encoding="utf-8", errors="replace") as f:
        lineas = f.readlines()

    iteraciones = []
    iter_actual = None
    ultima_completada = None  # Para asignar coste después de completar
    coste_acum = 0.0
    gate_ok = gate_fail = 0
    rev_pass = rev_fail = 0

    for linea in lineas:
        linea = linea.rstrip("\n")

        # Inicio de iteración
        m = _inicio_iteracion(linea)
        if m:
            if iter_actual:
                iteraciones.append(iter_actual)
            fecha, num, tarea = m
            iter_actual = {
                "timestamp": fecha,
                "iter": num,
                "tarea": tarea,
                "estado": "en_progreso",
                "duracion_s": 0,
                "coste_usd": 0.0,
                "gate": "pendiente",
                "revisor": "pendiente",
            }
            continue

        # Estado final de tarea (commit o bloqueada)
        m = LINEA_ESTADO.search(linea)
        if m and iter_actual:
            fecha, resto = m.groups()
            bajo = resto.lower()
            es_cierre = ("commit" in bajo or "completada" in bajo
                         or "bloqueada" in bajo)
            if es_cierre:
                if "commit" in bajo or "completada" in bajo:
                    iter_actual["estado"] = "hecha"
                    iter_actual["gate"] = "ok"
                    iter_actual["revisor"] = "pass"
                elif "bloqueada" in bajo:
                    iter_actual["estado"] = "bloqueada"
                iter_actual["duracion_s"] = _diff_seg(iter_actual["timestamp"], fecha)
                iteraciones.append(iter_actual)
                ultima_completada = iter_actual  # Guardar para asignar coste posterior
                iter_actual = None
                continue

        # Coste acumulado - asignar a la última completada
        m = LINEA_COSTE.search(linea)
        if m:
            coste_acum = float(m.group(2))
            if ultima_completada:
                ultima_completada["coste_usd"] = coste_acum
            elif iter_actual:
                iter_actual["coste_usd"] = coste_acum
            continue

        mayus = linea.upper()
        # Gate
        if "GATE OK" in mayus or "✅" in linea:
            gate_ok += 1
            if iter_actual:
                iter_actual["gate"] = "ok"
        elif "GATE" in mayus and ("FAIL" in mayus or "FALL" in mayus):
            gate_fail += 1
            if iter_actual:
                iter_actual["gate"] = "fail"

        # Revisor
        if "VERDICT: PASS" in linea or "REVISOR PASS" in linea:
            rev_pass += 1
            if iter_actual:
                iter_actual["revisor"] = "pass"
        elif "VERDICT: FAIL" in linea or "REVISOR FAIL" in linea:
            rev_fail += 1
            if iter_actual:
                iter_actual["revisor"] = "fail"

    # Última iteración si quedó abierta
    if iter_actual:
        iteraciones.append(iter_actual)

    # Construir series temporales
    tareas_hora = []
    coste_series = []
    gate_series = []
    rev_series = []

    hechas_acum = 0
    for it in iteraciones:
        ts = it["timestamp"]
        if it["estado"] == "hecha":
            hechas_acum += 1
        tareas_hora.append((ts, hechas_acum))
        coste_series.append((ts, it.get("coste_usd", 0.0)))
        gate_val = 1 if it.get("gate") == "ok" else (0 if it.get("gate") == "fail" else None)
        rev_val = 1 if it.get("revisor") == "pass" else (0 if it.get("revisor") == "fail" else None)
        gate_series.append((ts, gate_val))
        rev_series.append((ts, rev_val))

    hechas = sum(1 for it in iteraciones if it["estado"] == "hecha")
    bloqueadas = sum(1 for it in iteraciones if it["estado"] == "bloqueada")
    total = len(iteraciones)

    return {
        "iteraciones": iteraciones,
        "series": {
            "tareas_hora": tareas_hora,
            "coste_acum": coste_series,
            "gate": gate_series,
            "revisor": rev_series,
        },
        "resumen": {
            "total": total,
            "hechas": hechas,
            "bloqueadas": bloqueadas,
            "pendientes": max(0, total - hechas - bloqueadas),
            "coste_total": coste_acum,
            "duracion_min": 0.0,  # Se calcula en UI si hay timestamps
        },
    }


def _vacío() -> dict[str, Any]:
    return {
        "iteraciones": [],
        "series": {
            "tareas_hora": [],
            "coste_acum": [],
            "gate": [],
            "revisor": [],
        },
        "resumen": {
            "total": 0,
            "hechas": 0,
            "bloqueadas": 0,
            "pendientes": 0,
            "coste_total": 0.0,
            "duracion_min": 0.0,
        },
    }
