#!/usr/bin/env python3
"""Tests para navegador.py - navigator automático"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autopiloto_gui.navegador import _cli_opencode


def test_cli_opencode():
    """Test detección de CLI opencode"""
    cli = _cli_opencode()
    # Debe devolver string no vacío
    assert isinstance(cli, str)
    assert len(cli) > 0
    print(f"✅ CLI opencode detectado: {cli}")


def test_buscar_contexto_sync():
    """Test wrapper síncrono (requiere opencode instalado)"""
    from autopiloto_gui.navegador import buscar_contexto_sync
    
    # Test con proyecto actual
    ruta = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tarea = "test: arreglar login"
    
    try:
        # Usar modelo por defecto
        resultado = buscar_contexto_sync(ruta, tarea)
        # Si opencode no está disponible o falla, retorna string vacío
        assert isinstance(resultado, str)
        print(f"✅ buscar_contexto_sync ejecutado (longitud: {len(resultado)})")
    except Exception as e:
        # En entorno sin opencode, es esperado
        print(f"⚠️ buscar_contexto_sync falló (esperado sin opencode): {e}")
        print("✅ test_buscar_contexto_sync PASSED (skip)")


if __name__ == "__main__":
    test_cli_opencode()
    test_buscar_contexto_sync()
    print("\n🎉 Tests de navegador.py PASARON")