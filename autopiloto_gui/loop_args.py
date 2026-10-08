#!/usr/bin/env python3
"""Argumentos del loop nativo (port del parseo de autopiloto.sh).

Mismo contrato que el script: posición 1 = plan.md (por defecto), y las
opciones --hasta/--push/--padre/--trabajo. Diferencia deliberada: el motor
Python es estricto con las opciones que faltan de valor (exit 64 = EX_USAGE,
igual que el fix reciente del script); el bash trataba un flag desconocido
como plan posicional.
"""

import argparse
import os


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        # 64 = EX_USAGE: coherente con el fix de autopiloto.sh para
        # `--hasta`/`--padre`/`--trabajo` sin valor (antes colgaban).
        self.exit(64, f"{self.prog}: error: {message}\n")


def parse_args(argv=None):
    parser = _Parser(
        prog="autopiloto.loop",
        description="Bucle de tareas de autopiloto contra agents (port Python).",
    )
    parser.add_argument(
        "plan", nargs="?", default="plan.md",
        help="ruta del plan.md (por defecto: plan.md en el directorio actual)")
    parser.add_argument(
        "--hasta", default="",
        help="hora límite HH:MM (vacío = sin límite)")
    parser.add_argument(
        "--push", action="store_true",
        help="hacer push al terminar el run")
    parser.add_argument(
        "--padre", default="master",
        help="rama base del run (por defecto: master)")
    parser.add_argument(
        "--trabajo", default="",
        help="rama de trabajo (vacío = la rama del run)")
    args = parser.parse_args(argv)
    # El plan puede venir como ruta (absoluta) o como fichero dentro del
    # directorio actual (que es el proyecto cuando lo lanza la GUI, igual que
    # la resolución `[[ "$PLAN" != /* ]]` del script).
    if not os.path.isabs(args.plan):
        args.plan = os.path.normpath(os.path.join(os.getcwd(), args.plan))
    else:
        args.plan = os.path.normpath(args.plan)
    return args
