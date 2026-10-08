"""Punto de entrada para el binario de PyInstaller.

El import va dentro de main() para que PyInstaller no arrastre Qt a
tiempo de importación del spec (y para que el fallo de carga de PySide6
se pueda reportar antes de que Qt tome el control).

Doble modo:
  · sin argumentos (o con argumentos de la GUI): arranca el panel de control.
  · `--autopiloto-loop <args…>`: arranca el MOTOR del loop (autopiloto_gui.loop)
    como subproceso. La GUI en el binario lo lanza así en vez de
    `python -m` (que en un ejecutable congelado no resuelve el módulo);
    en el código fuente la GUI usa `python -m autopiloto_gui.loop` en su lugar.
"""
import sys


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "--autopiloto-loop":
        from autopiloto_gui.loop import main as _loop_main
        return _loop_main(argv[1:]) or 0
    try:
        from autopiloto_gui.app import main as _main
    except Exception:
        import traceback

        traceback.print_exc()
        print(
            "\nAutopiloto: no se pudieron cargar sus dependencias "
            "(¿falta libQt/GL en el sistema?).",
            file=sys.stderr,
        )
        return 1
    _main()  # main() cierra con sys.exit(app.exec())
    return 0


if __name__ == "__main__":
    sys.exit(main())
