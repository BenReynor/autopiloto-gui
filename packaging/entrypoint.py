"""Punto de entrada para el binario de PyInstaller.

El import va dentro de main() para que PyInstaller no arrastre Qt a
tiempo de importación del spec (y para que el fallo de carga de PySide6
se pueda reportar antes de que Qt tome el control).

Triple modo:
  · sin argumentos (o con argumentos de la GUI): arranca el panel de control.
  · `--dedalo-loop <args…>`: arranca el MOTOR del loop (dedalo.loop)
    como subproceso. La GUI en el binario lo lanza así en vez de
    `python -m` (que en un ejecutable congelado no resuelve el módulo);
    en el código fuente la GUI usa `python -m dedalo.loop` en su lugar.
  · `--dedalo-gate [--proyecto DIR]`: corre el gate portable (dedalo.gate).
    El loop en el binario lo lanza así; en el código fuente usa
    `python -m dedalo.gate`.
  · `--dedalo-mcp`: arranca el servidor MCP por stdio (dedalo.mcp_server).
    Requiere el extra `mcp`; en el código fuente: `python -m dedalo.mcp_server`.
"""
import sys


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "--dedalo-loop":
        from dedalo.loop import main as _loop_main
        return _loop_main(argv[1:]) or 0
    if argv and argv[0] == "--dedalo-gate":
        from dedalo.gate import main as _gate_main
        return _gate_main(argv[1:]) or 0
    if argv and argv[0] == "--dedalo-mcp":
        from dedalo.mcp_server import main as _mcp_main
        return _mcp_main() or 0
    try:
        from dedalo.app import main as _main
    except Exception:
        import traceback

        traceback.print_exc()
        print(
            "\nDédalo: no se pudieron cargar sus dependencias "
            "(¿falta libQt/GL en el sistema?).",
            file=sys.stderr,
        )
        return 1
    _main()  # main() cierra con sys.exit(app.exec())
    return 0


if __name__ == "__main__":
    sys.exit(main())
