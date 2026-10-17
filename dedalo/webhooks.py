"""Webhooks for push notifications: Telegram, Discord, WhatsApp.

Asynchronous sending via QThread (Trabajo) so as not to block the UI.
Global configuration (a single place for all projects).
"""

import json
import urllib.request
from typing import Any

from PySide6.QtCore import QObject, Qt, Signal

from .proceso import Trabajo


class WebhookManager(QObject):
    """Manages the sending of notifications to Telegram, Discord, WhatsApp."""

    enviado = Signal(str, str)      # event, message
    error = Signal(str, str)        # platform, error

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
        self._workers: set[Trabajo] = set()

    def configurar(self, config: dict[str, Any]):
        self.config = config

    def _sanitizar(self, mensaje: str) -> str:
        """Hides tokens and embedded URLs before emitting the error.

        The Telegram token travels in the URL itself (api.telegram.org/bot<token>/…)
        and urllib may include it in the exception message; we mask it.
        """
        if not mensaje:
            return ""
        for clave in ("telegram_token", "whatsapp_token", "discord_webhook_url", "whatsapp_api_url"):
            secreto = self.config.get(clave)
            if secreto:
                mensaje = mensaje.replace(str(secreto), "***")
        return mensaje

    def esta_activo(self, evento: str) -> bool:
        """Checks whether the event is enabled and at least one platform is configured."""
        if not self.config.get("eventos", {}).get(evento, False):
            return False
        return any([
            self.config.get("telegram_token") and self.config.get("telegram_chat_id"),
            self.config.get("discord_webhook_url"),
            self.config.get("whatsapp_api_url") and self.config.get("whatsapp_token"),
        ])

    def enviar(self, evento: str, datos: dict[str, Any]):
        """Sends the notification asynchronously (does not block the UI).

        Each send is an independent QThread and ALL of them stay referenced
        in `self._workers` until they finish. With a single shared attribute,
        two overlapping events (e.g. `inicio` and `fin`, each with up to 3
        HTTP requests of 10 s) clobbered each other: the second `send()` reassigned the
        attribute and the first QThread was left without a Python reference. Since
        `Trabajo` is created with `parent=None`, the collector could free it
        while running and the application aborted with
        "QThread: Destroyed while thread is still running".
        """
        if not self.esta_activo(evento):
            return

        texto = self._formatear(evento, datos)

        worker = Trabajo(lambda: self._enviar_todas(texto))
        self._workers.add(worker)
        worker.finished.connect(
            lambda w=worker: self._workers.discard(w),
            Qt.ConnectionType.QueuedConnection,
        )
        worker.start()

    def _pendientes(self) -> int:
        """Number of sends still in flight (diagnostics and tests)."""
        return sum(1 for w in self._workers if w.isRunning())

    def _formatear(self, evento: str, datos: dict[str, Any]) -> str:
        plantilla = self.PLANTILLAS.get(evento, "{evento}: {datos}")
        try:
            return plantilla.format(**datos)
        except KeyError:
            return f"{evento}: {datos}"

    def _enviar_todas(self, texto: str):
        """Sends to all configured platforms."""
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
                    self.error.emit("telegram", self._sanitizar(f"HTTP {resp.status}"))
                else:
                    self.enviado.emit("telegram", "OK")
        except Exception as e:
            self.error.emit("telegram", self._sanitizar(str(e)))

    def _enviar_discord(self, texto: str):
        url = self.config["discord_webhook_url"]
        data = json.dumps({"content": texto}).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status not in (200, 204):
                    self.error.emit("discord", self._sanitizar(f"HTTP {resp.status}"))
                else:
                    self.enviado.emit("discord", "OK")
        except Exception as e:
            self.error.emit("discord", self._sanitizar(str(e)))

    def _enviar_whatsapp(self, texto: str):
        """WhatsApp via Meta Cloud API (requires a Business Account)."""
        url = self.config["whatsapp_api_url"].rstrip("/") + "/messages"
        token = self.config["whatsapp_token"]
        phone_id = self.config.get("whatsapp_phone_id", "")
        to = self.config.get("whatsapp_to", "")  # destination number in international format

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
                    self.error.emit("whatsapp", self._sanitizar(f"HTTP {resp.status}"))
                else:
                    self.enviado.emit("whatsapp", "OK")
        except Exception as e:
            self.error.emit("whatsapp", self._sanitizar(str(e)))

    def _configurada(self, plataforma: str) -> bool:
        """Checks whether the platform has the minimum keys to send."""
        if plataforma == "telegram":
            return bool(self.config.get("telegram_token")
                        and self.config.get("telegram_chat_id"))
        if plataforma == "discord":
            return bool(self.config.get("discord_webhook_url"))
        if plataforma == "whatsapp":
            return bool(self.config.get("whatsapp_api_url")
                        and self.config.get("whatsapp_token"))
        return False

    def probar(self, plataforma: str) -> bool:
        """Sends a test message to a specific platform."""
        if not self._configurada(plataforma):
            return False

        texto = "🧪 *Test de webhook* desde Dédalo GUI"
        if plataforma == "telegram":
            self._enviar_telegram(texto)
        elif plataforma == "discord":
            self._enviar_discord(texto)
        elif plataforma == "whatsapp":
            self._enviar_whatsapp(texto)
        else:
            return False
        return True
