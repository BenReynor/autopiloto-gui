"""Modelo de datos de plan.md: lectura, conteo y guardado de tareas.

Separa el formato del plan de la UI para que el conteo y el guardado sean
consistentes y testables (mismo criterio que usa el script autopiloto.sh:
task `- [ ]`, hechas `- [x]`, bloqueadas `- [B]`).
"""

import os
import re

ESTADOS = {" ": "pendiente", "x": "hecha", "b": "bloqueada"}

_LINEA_TAREA = re.compile(r"^\s*-\s+\[(.)\]\s*(.*)$")


class Plan:
    def __init__(self, ruta):
        self.ruta = ruta
        self.texto = ""

    def existe(self):
        return os.path.isfile(self.ruta)

    def cargar(self):
        try:
            with open(self.ruta, "r", encoding="utf-8") as f:
                self.texto = f.read()
        except OSError:
            self.texto = ""
        return self.texto

    def guardar(self, texto):
        with open(self.ruta, "w", encoding="utf-8") as f:
            f.write(texto)
        self.texto = texto

    @property
    def tareas(self):
        """Lista de dicts {linea, estado, texto}, en orden del archivo."""
        out = []
        for i, linea in enumerate(self.texto.splitlines(), start=1):
            m = _LINEA_TAREA.match(linea)
            if not m:
                continue
            estado = m.group(1).lower()
            out.append({
                "linea": i,
                "estado": ESTADOS.get(estado, "pendiente"),
                "texto": m.group(2).strip(),
            })
        return out

    def conteo(self):
        """Devuelve (pendientes, hechas, bloqueadas)."""
        pend = hecho = bloq = 0
        for t in self.tareas:
            if t["estado"] == "pendiente":
                pend += 1
            elif t["estado"] == "hecha":
                hecho += 1
            elif t["estado"] == "bloqueada":
                bloq += 1
        return pend, hecho, bloq