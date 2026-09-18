"""Configuración centralizada del panel autopiloto.

Constantes compartidas por todos los módulos: rutas, valores por defecto,
timeouts y tamaños. Editar aquí en lugar de repartidos por el código.
"""

import os

APLICACION = "autopiloto"
CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".config", APLICACION)
REGISTRO = os.path.join(CONFIG_DIR, "proyectos.json")
CATALOGO_MODELOS = os.path.join(CONFIG_DIR, "models_dev.json")

# ----- Ventana -----
ANCHO = 1080
ALTO = 720
TEMA_DEFECTO = "Oscuro"
FUENTE_MONO = "JetBrains Mono"
FUENTE_UI = "Outfit"

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
    "costo_max": 0,
    "costo_iter": 0.50,
    "dual": True,
    "push": True,
    "voz": False,
}

# ----- Modelos -----
MODELO_SUGERIDO = "opencode/big-pickle"

# ----- Timeouts (segundos) -----
TIMEOUT_INTERNET = 3
TIMEOUT_OPENCODE = 20
TIMEOUT_GIT = 20
TIMEOUT_SENSORES = 5
TIMEOUT_CATALOGO = 15

# ----- Temporizadores (ms) -----
TIMER_TAIL_MS = 1000
TIMER_TEMP_MS = 1000
TIMER_NET_MS = 15000
TAIL_LOG_BYTES = 4000