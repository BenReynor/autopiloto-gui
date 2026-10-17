#!/usr/bin/env python3
"""Tests for webhooks.py - formatting, sending and concurrency"""

import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dedalo.webhooks import WebhookManager


def test_envios_simultaneos_no_se_pisan(app, monkeypatch):
    """Several events at once must use independent threads and all complete.

    Regression of the bug: `enviar()` stored the QThread in a single attribute
    `self._worker`, so a second send reassigned the attribute and the first
    thread was left without a Python reference. Being created with `parent=None`, the
    collector could destroy it while hot and abort the application with
    "QThread: Destroyed while thread is still running".

    The `Barrier` (3 threads + the main one) forces the real overlap: the three must
    reach urlopen before the test continues. With the old implementation
    there would be only one thread, the barrier would expire and the test would fail.
    `liberar` keeps the threads alive while the invariant is checked:
    without it, the sends finish as soon as the barrier opens and the assert
    on pending depends on the machine's speed (flaky).
    """
    enviados = []
    barrera = threading.Barrier(4, timeout=15)
    liberar = threading.Event()
    cuerpos = []

    class _Respuesta:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def _urlopen_falso(req, timeout=None):
        cuerpos.append(req.data.decode("utf-8"))
        barrera.wait()
        liberar.wait(timeout=15)
        enviados.append("OK")
        return _Respuesta()

    monkeypatch.setattr("urllib.request.urlopen", _urlopen_falso)

    wm = WebhookManager({
        "telegram_token": "tok-secreto",
        "telegram_chat_id": "12345",
        "eventos": {"inicio": True, "fin": True, "tokens": True},
    })

    wm.enviar("inicio", {"proyecto": "p1", "modelo_tarea": "m1", "modelo_revisor": "m2"})
    wm.enviar("fin", {"proyecto": "p1", "hechas": 3, "total": 3,
                      "coste": 1.25, "duracion_min": 4.0})
    wm.enviar("tokens", {"proyecto": "p1"})

    # The three threads have entered urlopen (barrier shared with the
    # main one): they are all really running, without depending on timing.
    barrera.wait()

    # The three threads are referenced and alive at the same time: the invariant that
    # the shared attribute violated.
    assert len(wm._workers) == 3
    assert wm._pendientes() == 3

    liberar.set()

    assert _esperar(app, lambda: wm._pendientes() == 0 and not wm._workers), (
        "los envíos no terminaron o quedaron referencias sin liberar")

    assert len(cuerpos) == 3, f"se esperaban 3 peticiones y hubo {len(cuerpos)}"
    assert any("Loop iniciado" in c for c in cuerpos)
    assert any("Loop finalizado" in c for c in cuerpos)
    assert any("Tokens" in c for c in cuerpos)
    assert len(enviados) == 3

    # No reference leak: the set is empty on finish.
    assert wm._workers == set()


def test_envio_unico_deja_referencia_y_la_libera(app, monkeypatch):
    """An isolated send is referenced while it runs and discarded on finish."""
    class _Respuesta:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=None: _Respuesta())

    wm = WebhookManager({
        "telegram_token": "tok",
        "telegram_chat_id": "123",
        "eventos": {"bloqueada": True},
    })

    wm.enviar("bloqueada", {"proyecto": "p1", "tarea": "tarea rota"})
    assert len(wm._workers) == 1

    assert _esperar(app, lambda: wm._pendientes() == 0 and not wm._workers)
    assert wm._workers == set()


def test_evento_no_habilitado_no_lanza_hilo():
    """Without an enabled event or credentials, `enviar` does not create any job."""
    wm = WebhookManager({"eventos": {"inicio": True}})
    wm.enviar("inicio", {"proyecto": "p1", "modelo_tarea": "m", "modelo_revisor": "m"})
    wm.enviar("fin", {"proyecto": "p1"})
    assert wm._workers == set()
    assert wm._pendientes() == 0


def _esperar(app, condicion, timeout=20.0):
    """Pumps the event loop until `condicion` is true."""
    limite = time.time() + timeout
    while time.time() < limite:
        app.processEvents()
        if condicion():
            return True
        time.sleep(0.01)
    app.processEvents()
    return bool(condicion())


def test_formateo_plantillas():
    """Test message formatting for each event"""
    config = {
        "telegram_token": "test_token",
        "telegram_chat_id": "12345",
        "discord_webhook_url": "https://discord.com/api/webhooks/test",
        "eventos": {"inicio": True, "bloqueada": True, "fin": True, "tokens": True, "error": True}
    }
    wm = WebhookManager(config)

    # Test inicio event
    datos = {"proyecto": "mi-proyecto", "modelo_tarea": "openai/gpt-4o", "modelo_revisor": "anthropic/claude"}
    msg = wm._formatear("inicio", datos)
    assert "mi-proyecto" in msg
    assert "openai/gpt-4o" in msg
    assert "anthropic/claude" in msg
    assert "Loop iniciado" in msg

    # Test bloqueada event
    datos = {"proyecto": "test", "tarea": "login fail"}
    msg = wm._formatear("bloqueada", datos)
    assert "Tarea bloqueada" in msg
    assert "login fail" in msg

    # Test fin event
    datos = {"proyecto": "test", "hechas": 5, "total": 8, "coste": 3.50, "duracion_min": 12.5}
    msg = wm._formatear("fin", datos)
    assert "5/8" in msg or "5" in msg and "8" in msg
    assert "3.50" in msg
    assert "12.5" in msg

    print("✅ test_formateo_plantillas PASSED")


def test_eventos_activos():
    """Test enabled-events logic"""
    # Config with telegram enabled
    config = {
        "telegram_token": "token",
        "telegram_chat_id": "123",
        "eventos": {"inicio": True, "bloqueada": False}
    }
    wm = WebhookManager(config)
    assert wm.esta_activo("inicio")
    assert not wm.esta_activo("bloqueada")
    assert not wm.esta_activo("fin")  # not configured = False

    # Config without credentials
    config2 = {"eventos": {"inicio": True}}
    wm2 = WebhookManager(config2)
    assert not wm2.esta_activo("inicio")  # without credentials

    print("✅ test_eventos_activos PASSED")


def test_whatsapp_config():
    """Test WhatsApp config validation"""
    config = {
        "whatsapp_api_url": "https://graph.facebook.com/v18.0/123",
        "whatsapp_token": "token",
        "whatsapp_phone_id": "456",
        "whatsapp_to": "34600123456",
        "eventos": {"inicio": True}
    }
    wm = WebhookManager(config)
    assert wm.esta_activo("inicio")

    # Missing phone_id or to
    config2 = {
        "whatsapp_api_url": "https://graph.facebook.com/v18.0/123",
        "whatsapp_token": "token",
        "eventos": {"inicio": True}
    }
    wm2 = WebhookManager(config2)
    # It has api_url and token → esta_activo is True; the real validation of
    # phone_id/to happens in _enviar_whatsapp
    assert wm2.esta_activo("inicio")

    print("✅ test_whatsapp_config PASSED")


def test_probar_configurada():
    """Test that probar() only sends when the platform has the minimum keys.

    Regression of the bug: probar() checked self.config.get(plataforma) with
    "telegram"/"discord"/"whatsapp", but the real keys are
    telegram_token, discord_webhook_url, whatsapp_api_url... → always False.
    """
    # Without credentials: it must not send (not even start the send)
    wm_vacio = WebhookManager({})
    assert not wm_vacio._configurada("telegram")
    assert not wm_vacio._configurada("discord")
    assert not wm_vacio._configurada("whatsapp")
    assert not wm_vacio._configurada("desconocida")
    assert not wm_vacio.probar("telegram")
    assert not wm_vacio.probar("discord")
    assert not wm_vacio.probar("whatsapp")

    # Telegram requires token + chat_id
    wm_tg = WebhookManager({"telegram_token": "tok", "telegram_chat_id": "123"})
    assert wm_tg._configurada("telegram")
    assert wm_tg.probar("telegram")  # returns True (starts async send)

    wm_tg2 = WebhookManager({"telegram_token": "tok"})
    assert not wm_tg2._configurada("telegram")
    assert not wm_tg2.probar("telegram")

    # Discord only needs a URL
    wm_dc = WebhookManager({"discord_webhook_url": "https://discord.com/api/webhooks/x"})
    assert wm_dc._configurada("discord")
    assert wm_dc.probar("discord")

    # WhatsApp requires api_url + token (phone_id/to are validated in _enviar_whatsapp)
    wm_wa = WebhookManager({
        "whatsapp_api_url": "https://graph.facebook.com/v18.0/123",
        "whatsapp_token": "tok",
    })
    assert wm_wa._configurada("whatsapp")
    assert wm_wa.probar("whatsapp")

    wm_wa2 = WebhookManager({"whatsapp_api_url": "https://graph.facebook.com/v18.0/123"})
    assert not wm_wa2._configurada("whatsapp")
    assert not wm_wa2.probar("whatsapp")

    print("✅ test_probar_configurada PASSED")


if __name__ == "__main__":
    test_formateo_plantillas()
    test_eventos_activos()
    test_whatsapp_config()
    test_probar_configurada()
    test_evento_no_habilitado_no_lanza_hilo()
    print("\n🎉 Todos los tests de webhooks.py PASARON")
