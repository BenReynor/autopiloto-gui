#!/usr/bin/env python3
"""Arguments of the native loop (port of dedalo.sh's parsing).

Same contract as the script: position 1 = plan.md (by default), and the
--hasta/--push/--padre/--trabajo options. Deliberate difference: the Python
engine is strict about options missing a value (exit 64 = EX_USAGE, same as
the script's recent fix); bash treated an unknown flag as a positional plan.
"""

import argparse
import os


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        # 64 = EX_USAGE: consistent with the dedalo.sh fix for
        # `--hasta`/`--padre`/`--trabajo` with no value (they used to hang).
        self.exit(64, f"{self.prog}: error: {message}\n")


def parse_args(argv=None):
    parser = _Parser(
        prog="dedalo.loop",
        description="Bucle de tareas de dedalo contra agents (port Python).",
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
    # The plan can come as a path (absolute) or as a file inside the
    # current directory (which is the project when the GUI launches it, same
    # as the script's `[[ "$PLAN" != /* ]]` resolution).
    if not os.path.isabs(args.plan):
        args.plan = os.path.normpath(os.path.join(os.getcwd(), args.plan))
    else:
        args.plan = os.path.normpath(args.plan)
    return args
