"""Entry point for the PyInstaller binary.

The import goes inside main() so PyInstaller does not drag Qt into
the spec's import time (and so a PySide6 load failure can be reported
before Qt takes control).

Triple mode:
  · no arguments (or GUI arguments): starts the control panel.
  · `--dedalo-loop <args…>`: starts the loop ENGINE (dedalo.loop)
    as a subprocess. The GUI in the binary launches it this way instead of
    `python -m` (which in a frozen executable does not resolve the module);
    in the source code the GUI uses `python -m dedalo.loop` instead.
  · `--dedalo-gate [--proyecto DIR]`: runs the portable gate (dedalo.gate).
    The loop in the binary launches it this way; in the source it uses
    `python -m dedalo.gate`.
  · `--dedalo-mcp`: starts the MCP server over stdio (dedalo.mcp_server).
    Requires the `mcp` extra; in the source: `python -m dedalo.mcp_server`.
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
    _main()  # main() ends with sys.exit(app.exec())
    return 0


if __name__ == "__main__":
    sys.exit(main())
