"""Configuración centralizada del panel de Dédalo.

Constantes compartidas por todos los módulos: rutas, valores por defecto,
timeouts y tamaños. Editar aquí en lugar de repartidos por el código.
"""

import os

APLICACION = "dedalo"
CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".config", APLICACION)
REGISTRO = os.path.join(CONFIG_DIR, "proyectos.json")
CATALOGO_MODELOS = os.path.join(CONFIG_DIR, "models_dev.json")

# ----- Ventana -----
# Tamaño inicial y mínimo: con menos de ANCHO_MIN x ALTO_MIN los paneles
# quedan ilegibles; el layout se reajusta entre esos límites (los paneles
# internos usan splitters/scroll y crecen con la ventana).
ANCHO = 1180
ALTO = 780
ANCHO_MIN = 960
ALTO_MIN = 600
TEMA_DEFECTO = "Zinc/Amber Oscuro"
FUENTE_MONO = "JetBrains Mono"
FUENTE_UI = "Outfit"

# ----- Cabina (navegación y movimiento) -----
# Sidebar vertical de navegación (ancho en px). Oscuro por defecto del tema.
SIDEBAR_ANCHO = 220
# Movimiento UI: píldora/lotes con animación sutil. False = estático (reduced motion).
MOTION = True

# ----- Seguridad térmica -----
SEGURIDAD_DEFECTO = {
    "activo": True,
    "ver": False,
    "umbral": 85,
    "segundos": 5,
}

# ----- Valores por defecto del lanzamiento -----
LAUNCH_DEFECTO = {
    "hasta": "22:00",
    "iteraciones": 40,
    "padre": "master",
    "trabajo": "",
    "costo_max": 0,
    "costo_iter": 0.50,
    "dual": True,
    "push": True,
    "voz": False,
}

# ----- Navigator (búsqueda de contexto antes de cada tarea) -----
NAVEGADOR_DEFECTO = False
MODELO_NAVEGADOR_SUGERIDO = "opencode/big-pickle"

# ----- Webhooks (notificaciones push) -----
WEBHOOK_DEFECTO = {
    "telegram_token": "",
    "telegram_chat_id": "",
    "discord_webhook_url": "",
    "whatsapp_api_url": "",
    "whatsapp_token": "",
    "whatsapp_phone_id": "",
    "eventos": {
        "inicio": True,
        "bloqueada": True,
        "fin": True,
        "tokens": True,
        "error": True,
    },
}

# ----- Modelos -----
MODELO_SUGERIDO = "opencode/big-pickle"

# ----- Agentes CLI disponibles -----
# AGENTES_CONOCIDOS son los CLIs que el dedalo sabe invocar. AGENTE_DEFECTO
# "auto" = usar el primero instalado según AGENTES_PREFERIDOS.
AGENTES_CONOCIDOS = ("opencode", "codex", "claude")
AGENTES_PREFERIDOS = ("opencode", "codex", "claude")
AGENTES_DISPONIBLES = AGENTES_CONOCIDOS + ("auto",)
AGENTE_DEFECTO = "auto"

# ----- Timeouts (segundos) -----
TIMEOUT_INTERNET = 3
TIMEOUT_OPENCODE = 20
TIMEOUT_GIT = 20
TIMEOUT_SENSORES = 5
TIMEOUT_CATALOGO = 15
TIMEOUT_NAVEGADOR = 60

# ----- Temporizadores (ms) -----
TIMER_TAIL_MS = 1000
TIMER_TEMP_MS = 1000
TIMER_NET_MS = 15000
TIMER_METRICAS_MS = 5000
TAIL_LOG_BYTES = 4000
