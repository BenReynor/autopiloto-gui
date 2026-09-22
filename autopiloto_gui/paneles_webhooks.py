"""Panel de configuración de Webhooks (Telegram, Discord, WhatsApp).

Se integra en la pestaña Seguridad o Ejecución.
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from . import configuracion as cfg
from .webhooks import WebhookManager


def _fuente_ui(objeto):
    from PySide6.QtGui import QFont
    fuente = QFont(objeto.font())
    fuente.setFamily(cfg.FUENTE_UI)
    objeto.setFont(fuente)


def _fuente_monospace(objeto):
    from PySide6.QtGui import QFont
    fuente = QFont(objeto.font())
    fuente.setFamily(cfg.FUENTE_MONO)
    objeto.setFont(fuente)


class _BtnPrimary(QPushButton):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)


class _BtnGhost(QPushButton):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setProperty("ghost", True)


class _BtnDanger(QPushButton):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setProperty("danger", True)


class _LabelMuted(QLabel):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setProperty("status", "muted")


class PanelWebhooks(QWidget):
    """Configuración global de notificaciones push."""

    guardado = Signal(dict)

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config or {}
        self.webhook = WebhookManager(self.config)

        v = QVBoxLayout(self)
        v.setSpacing(12)
        v.setContentsMargins(0, 0, 0, 0)

        # --- Telegram ---
        g_tg = QGroupBox("Telegram Bot")
        gtg = QGridLayout(g_tg)
        gtg.setSpacing(8)
        gtg.setHorizontalSpacing(12)
        gtg.setVerticalSpacing(8)
        gtg.setContentsMargins(12, 12, 12, 12)

        self.tg_token = self._crear_lineedit(self.config.get("telegram_token", ""), "Bot Token (de @BotFather)")
        self.tg_chat = self._crear_lineedit(self.config.get("telegram_chat_id", ""), "Chat ID (numérico, ej. 123456789)")
        gtg.addWidget(QLabel("Bot Token:"), 0, 0)
        gtg.addWidget(self.tg_token, 0, 1)
        gtg.addWidget(QLabel("Chat ID:"), 1, 0)
        gtg.addWidget(self.tg_chat, 1, 1)

        b_tg_test = _BtnGhost("🧪 Probar Telegram")
        b_tg_test.clicked.connect(lambda: self._probar("telegram"))
        gtg.addWidget(b_tg_test, 2, 0, 1, 2)

        self.tg_activo = QCheckBox("Activar notificaciones Telegram")
        self.tg_activo.setChecked(bool(self.config.get("telegram_token")))
        gtg.addWidget(self.tg_activo, 3, 0, 1, 2)

        v.addWidget(g_tg)

        # --- Discord ---
        g_dc = QGroupBox("Discord Webhook")
        gdc = QGridLayout(g_dc)
        gdc.setSpacing(8)
        gdc.setHorizontalSpacing(12)
        gdc.setVerticalSpacing(8)
        gdc.setContentsMargins(12, 12, 12, 12)

        self.dc_url = self._crear_lineedit(self.config.get("discord_webhook_url", ""), "Webhook URL (de Server Settings → Integrations)")
        gdc.addWidget(QLabel("Webhook URL:"), 0, 0)
        gdc.addWidget(self.dc_url, 0, 1)

        b_dc_test = _BtnGhost("🧪 Probar Discord")
        b_dc_test.clicked.connect(lambda: self._probar("discord"))
        gdc.addWidget(b_dc_test, 1, 0, 1, 2)

        self.dc_activo = QCheckBox("Activar notificaciones Discord")
        self.dc_activo.setChecked(bool(self.config.get("discord_webhook_url")))
        gdc.addWidget(self.dc_activo, 2, 0, 1, 2)

        v.addWidget(g_dc)

        # --- WhatsApp (Meta Cloud API) ---
        g_wa = QGroupBox("WhatsApp (Meta Cloud API)")
        gwa = QGridLayout(g_wa)
        gwa.setSpacing(8)
        gwa.setHorizontalSpacing(12)
        gwa.setVerticalSpacing(8)
        gwa.setContentsMargins(12, 12, 12, 12)

        self.wa_api = self._crear_lineedit(self.config.get("whatsapp_api_url", ""), "API URL (ej. https://graph.facebook.com/v18.0/123456789)")
        self.wa_token = self._crear_lineedit(self.config.get("whatsapp_token", ""), "Access Token (permisos: whatsapp_business_messaging)")
        self.wa_phone = self._crear_lineedit(self.config.get("whatsapp_phone_id", ""), "Phone Number ID")
        self.wa_to = self._crear_lineedit(self.config.get("whatsapp_to", ""), "Destino (formato internacional, ej. 34600123456)")

        gwa.addWidget(QLabel("API URL:"), 0, 0)
        gwa.addWidget(self.wa_api, 0, 1)
        gwa.addWidget(QLabel("Access Token:"), 1, 0)
        gwa.addWidget(self.wa_token, 1, 1)
        gwa.addWidget(QLabel("Phone Number ID:"), 2, 0)
        gwa.addWidget(self.wa_phone, 2, 1)
        gwa.addWidget(QLabel("Destino (to):"), 3, 0)
        gwa.addWidget(self.wa_to, 3, 1)

        b_wa_test = _BtnGhost("🧪 Probar WhatsApp")
        b_wa_test.clicked.connect(lambda: self._probar("whatsapp"))
        gwa.addWidget(b_wa_test, 4, 0, 1, 2)

        self.wa_activo = QCheckBox("Activar notificaciones WhatsApp")
        self.wa_activo.setChecked(bool(self.config.get("whatsapp_token")))
        gwa.addWidget(self.wa_activo, 5, 0, 1, 2)

        v.addWidget(g_wa)

        # --- Eventos a notificar ---
        g_evt = QGroupBox("Eventos a notificar (por plataforma activada)")
        gev = QGridLayout(g_evt)
        gev.setSpacing(6)
        gev.setHorizontalSpacing(12)
        gev.setVerticalSpacing(4)
        gev.setContentsMargins(12, 12, 12, 12)

        self.chk_eventos = {}
        eventos = [
            ("inicio", "🚀 Loop iniciado"),
            ("bloqueada", "⚠ Tarea bloqueada"),
            ("fin", "✅ Loop finalizado"),
            ("tokens", "💸 Tokens agotados"),
            ("error", "💥 Error crítico"),
        ]
        evt_config = self.config.get("eventos", {})
        for i, (key, label) in enumerate(eventos):
            chk = QCheckBox(label)
            chk.setChecked(evt_config.get(key, True))
            gev.addWidget(chk, i // 3, i % 3)
            self.chk_eventos[key] = chk

        v.addWidget(g_evt)

        # --- Guardar ---
        h = QHBoxLayout()
        h.setSpacing(8)
        b_guardar = _BtnPrimary("💾 Guardar configuración")
        b_guardar.clicked.connect(self._guardar)
        h.addStretch()
        h.addWidget(b_guardar)
        v.addLayout(h)

        v.addStretch()

    def _crear_lineedit(self, texto: str, placeholder: str = "") -> QLineEdit:
        le = QLineEdit(texto)
        le.setPlaceholderText(placeholder)
        _fuente_ui(le)
        _fuente_monospace(le)
        le.setEchoMode(QLineEdit.Password)  # Tokens sensibles
        return le

    def _probar(self, plataforma: str):
        ok = self.webhook.probar(plataforma)
        if ok:
            QMessageBox.information(self, f"Test {plataforma.capitalize()}", "Mensaje de prueba enviado ✓")
        else:
            QMessageBox.warning(self, f"Test {plataforma.capitalize()}", "No se pudo enviar. Revisa la configuración.")

    def _guardar(self):
        nueva = {
            "telegram_token": self.tg_token.text().strip(),
            "telegram_chat_id": self.tg_chat.text().strip(),
            "discord_webhook_url": self.dc_url.text().strip(),
            "whatsapp_api_url": self.wa_api.text().strip(),
            "whatsapp_token": self.wa_token.text().strip(),
            "whatsapp_phone_id": self.wa_phone.text().strip(),
            "whatsapp_to": self.wa_to.text().strip(),
            "eventos": {k: v.isChecked() for k, v in self.chk_eventos.items()},
        }
        self.config.update(nueva)
        self.webhook.configurar(self.config)
        self.guardado.emit(self.config)
        QMessageBox.information(self, "Webhooks", "Configuración guardada ✓")

    def aplicar_config(self, config):
        """Rellena los campos con la configuración del proyecto activo."""
        self.config = dict(config or {})
        self.webhook.configurar(self.config)
        self.tg_token.setText(self.config.get("telegram_token", ""))
        self.tg_chat.setText(self.config.get("telegram_chat_id", ""))
        self.dc_url.setText(self.config.get("discord_webhook_url", ""))
        self.wa_api.setText(self.config.get("whatsapp_api_url", ""))
        self.wa_token.setText(self.config.get("whatsapp_token", ""))
        self.wa_phone.setText(self.config.get("whatsapp_phone_id", ""))
        self.wa_to.setText(self.config.get("whatsapp_to", ""))
        self.tg_activo.setChecked(bool(self.config.get("telegram_token")))
        self.dc_activo.setChecked(bool(self.config.get("discord_webhook_url")))
        self.wa_activo.setChecked(bool(self.config.get("whatsapp_token")))
        eventos = self.config.get("eventos", {})
        for key, chk in self.chk_eventos.items():
            chk.setChecked(eventos.get(key, True))

    def obtener_config(self) -> dict:
        return self.config
