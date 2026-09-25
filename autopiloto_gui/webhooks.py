"""Webhooks para notificaciones push: Telegram, Discord, WhatsApp.

Envío asíncrono vía QThread (Trabajo) para no bloquear la UI.
Configuración global (un solo lugar para todos los proyectos).
"""

import json
import urllib.request
from typing import Any

from PySide6.QtCore import QObject, Signal

from .proceso import Trabajo


class WebhookManager(QObject):
    """Gestiona envío de notificaciones a Telegram, Discord, WhatsApp."""

    enviado = Signal(str, str)      # evento, mensaje
    error = Signal(str, str)        # plataforma, error

    PLANTILLAS = {
        "inicio": "🚀 *Loop iniciado*\nProyecto: `{proyecto}`\nModelo tarea: `{modelo_tarea}`\nModelo revisor: `{modelo_revisor}`",
        "bloqueada": "⚠ *Tarea bloqueada*\nProyecto: `{proyecto}`\nTarea: `{tarea}`",
        "fin": "✅ *Loop finalizado*\nProyecto: `{proyecto}`\nTareas: {hechas}/{total}\nCoste: ${coste:.2f}\nDuración: {duracion_min:.1f} min",
        "tokens": "💸 *Tokens/cuota agotados*\nProyecto: `{proyecto}`\nEl loop se ha detenido.",
        "error": "💥 *Error crítico*\nProyecto: `{proyecto}`\nDetalle: `{detalle}`",
    }

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__()
        self.config = config or {}
        self._worker: Trabajo | None = None

    def configurar(self, config: dict[str, Any]):
        self.config = config

    def esta_activo(self, evento: str) -> bool:
        """Verifica si el evento está habilitado y hay al menos una plataforma configurada."""
        if not self.config.get("eventos", {}).get(evento, False):
            return False
        return any([
            self.config.get("telegram_token") and self.config.get("telegram_chat_id"),
            self.config.get("discord_webhook_url"),
            self.config.get("whatsapp_api_url") and self.config.get("whatsapp_token"),
        ])

    def enviar(self, evento: str, datos: dict[str, Any]):
        """Envía notificación de forma asíncrona (no bloquea UI)."""
        if not self.esta_activo(evento):
            return

        texto = self._formatear(evento, datos)

        # Ejecutar en hilo de fondo
        self._worker = Trabajo(lambda: self._enviar_todas(texto))
        self._worker.conectar(lambda _: None)
        self._worker.liberar(self, "_worker")
        self._worker.start()

    def _formatear(self, evento: str, datos: dict[str, Any]) -> str:
        plantilla = self.PLANTILLAS.get(evento, "{evento}: {datos}")
        try:
            return plantilla.format(**datos)
        except KeyError:
            return f"{evento}: {datos}"

    def _enviar_todas(self, texto: str):
        """Envía a todas las plataformas configuradas."""
        # Telegram
        if self.config.get("telegram_token") and self.config.get("telegram_chat_id"):
            self._enviar_telegram(texto)

        # Discord
        if self.config.get("discord_webhook_url"):
            self._enviar_discord(texto)

        # WhatsApp (Meta Cloud API)
        if self.config.get("whatsapp_api_url") and self.config.get("whatsapp_token"):
            self._enviar_whatsapp(texto)

    def _enviar_telegram(self, texto: str):
        token = self.config["telegram_token"]
        chat_id = self.config["telegram_chat_id"]
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = json.dumps({
            "chat_id": chat_id,
            "text": texto,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }).encode("utf-8")

        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status != 200:
                    self.error.emit("telegram", f"HTTP {resp.status}")
                else:
                    self.enviado.emit("telegram", "OK")
        except Exception as e:
            self.error.emit("telegram", str(e))

    def _enviar_discord(self, texto: str):
        url = self.config["discord_webhook_url"]
        data = json.dumps({"content": texto}).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status not in (200, 204):
                    self.error.emit("discord", f"HTTP {resp.status}")
                else:
                    self.enviado.emit("discord", "OK")
        except Exception as e:
            self.error.emit("discord", str(e))

    def _enviar_whatsapp(self, texto: str):
        """WhatsApp via Meta Cloud API (requiere Business Account)."""
        url = self.config["whatsapp_api_url"].rstrip("/") + "/messages"
        token = self.config["whatsapp_token"]
        phone_id = self.config.get("whatsapp_phone_id", "")
        to = self.config.get("whatsapp_to", "")  # número destino en formato internacional

        if not phone_id or not to:
            self.error.emit("whatsapp", "Falta phone_id o to")
            return

        data = json.dumps({
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"preview_url": False, "body": texto},
        }).encode("utf-8")

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        req = urllib.request.Request(url, data=data, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status != 200:
                    self.error.emit("whatsapp", f"HTTP {resp.status}")
                else:
                    self.enviado.emit("whatsapp", "OK")
        except Exception as e:
            self.error.emit("whatsapp", str(e))

    def probar(self, plataforma: str) -> bool:
        """Envía mensaje de prueba a una plataforma específica."""
        if not self.config.get(plataforma):
            return False

        texto = "🧪 *Test de webhook* desde Autopiloto GUI"
        if plataforma == "telegram":
            self._enviar_telegram(texto)
        elif plataforma == "discord":
            self._enviar_discord(texto)
        elif plataforma == "whatsapp":
            self._enviar_whatsapp(texto)
        else:
            return False
        return True
