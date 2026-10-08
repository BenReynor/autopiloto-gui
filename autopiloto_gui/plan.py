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
            with open(self.ruta, encoding="utf-8") as f:
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

    def marcar_primera(self, estado):
        """Marca la PRIMERA tarea pendiente con `estado` (`x`/`B`).

        Misma semántica que `marcar_plan` de autopiloto.sh: sólo la primera
        línea que empieza (columna 0) por `- [ ]`. Escritura atómica (fichero
        temporal en el mismo directorio + os.replace) para no dejar el plan a
        medias si el proceso muere a mitad de escritura. Devuelve True si
        tocó alguna tarea.
        """
        marca = "B" if str(estado).upper() == "B" else "x"
        hecha = False
        lineas = []
        for linea in self.texto.splitlines(keepends=True):
            if not hecha and linea.startswith("- [ ]"):
                lineas.append(linea.replace("- [ ]", f"- [{marca}]", 1))
                hecha = True
            else:
                lineas.append(linea)
        if not hecha:
            return False
        tmp = os.path.join(
            os.path.dirname(self.ruta),
            f".plan.md.tmp.{os.getpid()}")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                f.write("".join(lineas))
            os.replace(tmp, self.ruta)
        except OSError:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        self.texto = "".join(lineas)
        return True
