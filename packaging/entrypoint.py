"""Punto de entrada para el binario de PyInstaller.

El import va dentro de main() para que PyInstaller no arrastre Qt a
tiempo de importación del spec (y para que el fallo de carga de PySide6
se pueda reportar antes de que Qt tome el control).
"""
import sys


def main():
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
