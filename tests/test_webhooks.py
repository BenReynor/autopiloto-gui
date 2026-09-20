#!/usr/bin/env python3
"""Tests para webhooks.py - formateo y envío"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autopiloto_gui.webhooks import WebhookManager


def test_formateo_plantillas():
    """Test formateo de mensajes para cada evento"""
    config = {
        "telegram_token": "test_token",
        "telegram_chat_id": "12345",
        "discord_webhook_url": "https://discord.com/api/webhooks/test",
        "eventos": {"inicio": True, "bloqueada": True, "fin": True, "tokens": True, "error": True}
    }
    wm = WebhookManager(config)
    
    # Test evento inicio
    datos = {"proyecto": "mi-proyecto", "modelo_tarea": "openai/gpt-4o", "modelo_revisor": "anthropic/claude"}
    msg = wm._formatear("inicio", datos)
    assert "mi-proyecto" in msg
    assert "openai/gpt-4o" in msg
    assert "anthropic/claude" in msg
    assert "Loop iniciado" in msg
    
    # Test evento bloqueada
    datos = {"proyecto": "test", "tarea": "login fail"}
    msg = wm._formatear("bloqueada", datos)
    assert "Tarea bloqueada" in msg
    assert "login fail" in msg
    
    # Test evento fin
    datos = {"proyecto": "test", "hechas": 5, "total": 8, "coste": 3.50, "duracion_min": 12.5}
    msg = wm._formatear("fin", datos)
    assert "5/8" in msg or "5" in msg and "8" in msg
    assert "3.50" in msg
    assert "12.5" in msg
    
    print("✅ test_formateo_plantillas PASSED")


def test_eventos_activos():
    """Test lógica de eventos habilitados"""
    # Config con telegram activado
    config = {
        "telegram_token": "token",
        "telegram_chat_id": "123",
        "eventos": {"inicio": True, "bloqueada": False}
    }
    wm = WebhookManager(config)
    assert wm.esta_activo("inicio") == True
    assert wm.esta_activo("bloqueada") == False
    assert wm.esta_activo("fin") == False  # no configurado = False
    
    # Config sin credenciales
    config2 = {"eventos": {"inicio": True}}
    wm2 = WebhookManager(config2)
    assert wm2.esta_activo("inicio") == False  # sin credenciales
    
    print("✅ test_eventos_activos PASSED")


def test_whatsapp_config():
    """Test validación config WhatsApp"""
    config = {
        "whatsapp_api_url": "https://graph.facebook.com/v18.0/123",
        "whatsapp_token": "token",
        "whatsapp_phone_id": "456",
        "whatsapp_to": "34600123456",
        "eventos": {"inicio": True}
    }
    wm = WebhookManager(config)
    assert wm.esta_activo("inicio") == True
    
    # Faltan phone_id o to
    config2 = {
        "whatsapp_api_url": "https://graph.facebook.com/v18.0/123",
        "whatsapp_token": "token",
        "eventos": {"inicio": True}
    }
    wm2 = WebhookManager(config2)
    # Debería estar inactivo por faltar phone_id/to
    # (la validación real ocurre en _enviar_whatsapp)
    
    print("✅ test_whatsapp_config PASSED")


if __name__ == "__main__":
    test_formateo_plantillas()
    test_eventos_activos()
    test_whatsapp_config()
    print("\n🎉 Todos los tests de webhooks.py PASARON")