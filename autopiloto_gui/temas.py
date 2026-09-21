"""Sistema de diseño visual: colores semánticos, tipografía y componentes.

Basado en referencias de diseño desktop (Linear, Vercel, VS Code).
Un solo acento, escala neutral coherente, foco visible, contraste WCAG AA.
"""

# ─── FUENTES ───────────────────────────────────────────────────────

# Fuentes preferidas para apps desktop (evitar Inter, Roboto, Arial)
# Si no están instaladas, Qt usa fallback del sistema
FONT_UI_FAMILIES = [
    "JetBrains Mono",   # mono para código/logs
    "Geist Mono",       # alternativa mono
    "Fira Code",        # fallback mono con ligaduras
    "Monospace",        # fallback genérico
]

FONT_UI_PRIMARY = [
    "Outfit",           # UI limpia, moderna
    "DM Sans",          # neutral, versátil
    "Plus Jakarta Sans",# pulida
    "Source Sans 3",    # legible denso
    "System",           # fallback nativo (Segoe UI / San Francisco / Ubuntu)
]

FONT_MONO = "JetBrains Mono"  # preferida para monospace

# Inicialización perezosa de fuentes (requiere QApplication creado)
_FUENTES = {"mono": None, "ui": None}


def _inicializar_fuentes():
    """Registra fuentes instaladas en el sistema para uso en QSS.
    Debe llamarse después de crear QApplication."""
    global _FUENTES
    if _FUENTES["mono"] is not None:
        return
    from PySide6.QtGui import QFontDatabase
    familias = QFontDatabase.families()
    _FUENTES["mono"] = next((f for f in FONT_UI_FAMILIES if f in familias), "Monospace")
    _FUENTES["ui"] = next((f for f in FONT_UI_PRIMARY if f in familias), "System")


def _get_fuente_mono():
    if _FUENTES["mono"] is None:
        _inicializar_fuentes()
    return _FUENTES["mono"]


def _get_fuente_ui():
    if _FUENTES["ui"] is None:
        _inicializar_fuentes()
    return _FUENTES["ui"]


# ─── ESCALA TIPOGRÁFICA (Major Third 1.25x) ────────────────────────

# Base 14px para desktop denso
TEXT_XS = "10px"      # captions, badges
TEXT_SM = "11px"      # labels secundarios, sidebar
TEXT_BASE = "13px"    # body, inputs, botones
TEXT_MD = "16px"      # subheadings
TEXT_LG = "20px"      # section headings
TEXT_XL = "25px"      # page titles

# Line heights
LH_TIGHT = "1.2"      # botones, labels
LH_NORMAL = "1.4"     # inputs, celdas tabla
LH_RELAXED = "1.6"    # párrafos

# Letter spacing
LS_UPPER = "0.06em"   # labels uppercase
LS_HEADING = "-0.01em"
LS_BODY = "0"

# ─── ESPACIADO (4px base) ────────────────────────────────────────

SPACE_1 = "2px"
SPACE_2 = "4px"
SPACE_3 = "6px"
SPACE_4 = "8px"
SPACE_5 = "10px"
SPACE_6 = "12px"
SPACE_8 = "16px"
SPACE_10 = "20px"
SPACE_12 = "24px"
SPACE_16 = "32px"

# Border radius
RADIUS_SM = "4px"
RADIUS_MD = "6px"
RADIUS_LG = "8px"
RADIUS_XL = "12px"

# Sombras (direccional, no glow)
SHADOW_SM = "0 1px 2px rgba(0,0,0,0.05)"
SHADOW_MD = "0 4px 6px -1px rgba(0,0,0,0.07), 0 2px 4px -2px rgba(0,0,0,0.05)"
SHADOW_LG = "0 10px 15px -3px rgba(0,0,0,0.08), 0 4px 6px -4px rgba(0,0,0,0.04)"
SHADOW_XL = "0 20px 25px -5px rgba(0,0,0,0.1), 0 8px 10px -6px rgba(0,0,0,0.05)"

# Transiciones (sin bounce)
TRANSITION_FAST = "100ms ease"
TRANSITION_NORMAL = "150ms ease"
TRANSITION_SLOW = "200ms ease"

# ─── COLORES SEMÁNTICOS ───────────────────────────────────────────

# Neutros: Slate (azul-frío, limpio, estilo Linear/Vercel)
NEUTRAL_SLATE = {
    50:  "#f8fafc",
    100: "#f1f5f9",
    200: "#e2e8f0",
    300: "#cbd5e1",
    400: "#94a3b8",
    500: "#64748b",
    600: "#475569",
    700: "#334155",
    800: "#1e293b",
    900: "#0f172a",
    950: "#020617",
}

# Neutros: Zinc (frío neutro, estilo Vercel/Linear)
NEUTRAL_ZINC = {
    50:  "#fafafa",
    100: "#f4f4f5",
    200: "#e4e4e7",
    300: "#d4d4d8",
    400: "#a1a1aa",
    500: "#71717a",
    600: "#52525b",
    700: "#3f3f46",
    800: "#27272a",
    900: "#18181b",
    950: "#09090b",
}

# Neutros: Gray (gris puro, clásico)
NEUTRAL_GRAY = {
    50:  "#f9fafb",
    100: "#f3f4f6",
    200: "#e5e7eb",
    300: "#d1d5db",
    400: "#9ca3af",
    500: "#6b7280",
    600: "#4b5563",
    700: "#374151",
    800: "#1f2937",
    900: "#111827",
    950: "#030712",
}

# Neutros: Stone (cálido, estilo Notion/escritura)
NEUTRAL_STONE = {
    50:  "#fafaf9",
    100: "#f5f5f4",
    200: "#e7e5e4",
    300: "#d6d3d1",
    400: "#a8a29e",
    500: "#78716c",
    600: "#57534e",
    700: "#44403c",
    800: "#292524",
    900: "#1c1917",
    950: "#0c0a09",
}

# Neutros por nombre para fácil acceso
NEUTRALS = {
    "slate": NEUTRAL_SLATE,
    "zinc": NEUTRAL_ZINC,
    "gray": NEUTRAL_GRAY,
    "stone": NEUTRAL_STONE,
}

# Acentos disponibles (sat < 75% para legibilidad)
ACCENTS = {
    "blue": {      # Electric Blue - técnico
        50:  "#eff6ff", 100: "#dbeafe", 400: "#60a5fa",
        500: "#3b82f6", 600: "#2563eb", 700: "#1d4ed8", 900: "#1e3a8a",
    },
    "teal": {      # Teal - datos, productividad
        50:  "#f0fdfa", 100: "#ccfbf1", 400: "#2dd4bf",
        500: "#14b8a6", 600: "#0d9488", 700: "#0f766e", 900: "#134e4a",
    },
    "emerald": {   # Emerald - éxito, limpio
        50:  "#ecfdf5", 100: "#d1fae5", 400: "#34d399",
        500: "#10b981", 600: "#059669", 700: "#047857", 900: "#065f46",
    },
    "green": {     # Green - naturaleza
        50:  "#f0fdf4", 100: "#dcfce7", 400: "#4ade80",
        500: "#22c55e", 600: "#16a34a", 700: "#15803d", 900: "#14532d",
    },
    "amber": {     # Amber - cálido, creativo
        50:  "#fffbeb", 100: "#fef3c7", 400: "#fbbf24",
        500: "#f59e0b", 600: "#d97706", 700: "#b45309", 900: "#92400e",
    },
    "orange": {    # Orange - energía
        50:  "#fff7ed", 100: "#ffedd5", 400: "#fb923c",
        500: "#f97316", 600: "#ea580c", 700: "#c2410c", 900: "#9a3412",
    },
    "red": {       # Red - peligro, error
        50:  "#fef2f2", 100: "#fee2e2", 400: "#f87171",
        500: "#ef4444", 600: "#dc2626", 700: "#b91c1c", 900: "#991b1b",
    },
    "rose": {      # Rose - moderno, marca
        50:  "#fff1f2", 100: "#ffe4e6", 400: "#fb7185",
        500: "#f43f5e", 600: "#e11d48", 700: "#be123c", 900: "#9f1239",
    },
    "violet": {    # Violet - premium (OK en data viz)
        50:  "#f5f3ff", 100: "#ede9fe", 400: "#a78bfa",
        500: "#8b5cf6", 600: "#7c3aed", 700: "#6d28d9", 900: "#5b21b6",
    },
    "purple": {    # Purple - creativo
        50:  "#faf5ff", 100: "#f3e8ff", 400: "#c084fc",
        500: "#a855f7", 600: "#9333ea", 700: "#7e22ce", 900: "#6b21a8",
    },
    "indigo": {    # Indigo - enterprise
        50:  "#eef2ff", 100: "#e0e7ff", 400: "#818cf8",
        500: "#6366f1", 600: "#4f46e5", 700: "#4338ca", 900: "#312e81",
    },
    "sky": {       # Sky - ligero, aéreo
        50:  "#f0f9ff", 100: "#e0f2fe", 400: "#38bdf8",
        500: "#0ea5e9", 600: "#0284c7", 700: "#0369a1", 900: "#075985",
    },
    "cyan": {      # Cian - técnico
        50:  "#ecfeff", 100: "#cffafe", 400: "#22d3ee",
        500: "#06b6d4", 600: "#0891b2", 700: "#0e7490", 900: "#164e63",
    },
}

# Alias para compatibilidad
NEUTRAL = NEUTRAL_SLATE
ACCENT = ACCENTS["blue"]

# Estado (semánticos, no solo color)
STATUS_SUCCESS = "#16a34a"
STATUS_WARNING = "#d97706"
STATUS_ERROR = "#dc2626"
STATUS_INFO = "#2563eb"

# ─── GENERADOR QSS ────────────────────────────────────────────────

def _qss_variables(tema: str) -> dict:
    """Devuelve diccionario de tokens para el tema."""

    # Temas especiales hardcoded
    if tema == "Hacker":
        return _build_hacker_theme()

    # Parsear tema: "Neutral/Accent [Claro|Oscuro]"
    # Ejemplos: "Slate/Blue Oscuro", "Zinc/Teal Claro", "Stone/Amber Oscuro"
    parts = tema.split()
    if len(parts) >= 2:
        neutral_accent = parts[0].split("/")
        if len(neutral_accent) == 2:
            neutral_name, accent_name = neutral_accent
            is_dark = "Oscuro" in tema
            if neutral_name in NEUTRALS and accent_name in ACCENTS:
                return _build_theme(neutral_name, accent_name, is_dark)

    # Fallback: temas legacy
    is_dark = tema in ("Oscuro", "Hacker")
    if tema == "Hacker":
        return _build_hacker_theme()

    return _build_theme("slate", "blue", is_dark)


def _build_theme(neutral_name: str, accent_name: str, is_dark: bool) -> dict:
    """Construye un tema a partir de neutral + acento + modo claro/oscuro."""
    neutral = NEUTRALS[neutral_name]
    accent = ACCENTS[accent_name]

    if is_dark:
        return {
            "bg_app":       neutral[950],
            "bg_panel":     neutral[900],
            "bg_elevated":  neutral[800],
            "bg_sunken":    "rgba(0,0,0,0.3)",
            "bg_overlay":   "rgba(0,0,0,0.6)",

            "text_primary":   neutral[50],
            "text_secondary": neutral[400],
            "text_tertiary":  neutral[500],
            "text_disabled":  neutral[700],
            "text_inverse":   neutral[950],

            "border_subtle":  "rgba(255,255,255,0.04)",
            "border_default": "rgba(255,255,255,0.08)",
            "border_strong":  "rgba(255,255,255,0.14)",
            "border_focus":   accent[600],

            "action_primary":       accent[600],
            "action_primary_hover": accent[700],
            "action_primary_active": accent[900],
            "action_primary_text":  "#ffffff",
            "action_secondary":     neutral[800],
            "action_secondary_hover": neutral[700],

            "surface_hover":    "rgba(255,255,255,0.05)",
            "surface_selected": f"rgba({_hex_to_rgb(accent[600])}, 0.15)",
            "surface_active":   f"rgba({_hex_to_rgb(accent[600])}, 0.20)",

            "status_success": STATUS_SUCCESS,
            "status_warning": STATUS_WARNING,
            "status_error":   STATUS_ERROR,
            "status_info":    STATUS_INFO,

            "shadow_sm": SHADOW_SM,
            "shadow_md": SHADOW_MD,
            "shadow_lg": SHADOW_LG,
            "shadow_xl": SHADOW_XL,

            "btn_text_primary": "#ffffff",
            "btn_text_hover": "#ffffff",
            "btn_text_disabled": neutral[600],
            "btn_bg_hover": accent[700],
            "btn_bg_active": accent[900],
            "btn_bg_disabled": neutral[800],
            "btn_border_disabled": neutral[800],
        }

    # Claro
    return {
        "bg_app":       neutral[50],
        "bg_panel":     "#ffffff",
        "bg_elevated":  "#ffffff",
        "bg_sunken":    neutral[100],
        "bg_overlay":   "rgba(0,0,0,0.4)",

        "text_primary":   neutral[900],
        "text_secondary": neutral[500],
        "text_tertiary":  neutral[400],
        "text_disabled":  neutral[300],
        "text_inverse":   "#ffffff",

        "border_subtle":  neutral[100],
        "border_default": neutral[200],
        "border_strong":  neutral[300],
        "border_focus":   accent[600],

        "action_primary":       accent[600],
        "action_primary_hover": accent[700],
        "action_primary_active": accent[900],
        "action_primary_text":  "#ffffff",
        "action_secondary":     neutral[100],
        "action_secondary_hover": neutral[200],

        "surface_hover":    neutral[100],
        "surface_selected": f"rgba({_hex_to_rgb(accent[600])}, 0.08)",
        "surface_active":   f"rgba({_hex_to_rgb(accent[600])}, 0.12)",

        "status_success": STATUS_SUCCESS,
        "status_warning": STATUS_WARNING,
        "status_error":   STATUS_ERROR,
        "status_info":    STATUS_INFO,

        "shadow_sm": SHADOW_SM,
        "shadow_md": SHADOW_MD,
        "shadow_lg": SHADOW_LG,
        "shadow_xl": SHADOW_XL,

        "btn_text_primary": "#ffffff",
        "btn_text_hover": "#ffffff",
        "btn_text_disabled": neutral[400],
        "btn_bg_hover": accent[700],
        "btn_bg_active": accent[900],
        "btn_bg_disabled": neutral[200],
        "btn_border_disabled": neutral[200],
    }


def _hex_to_rgb(hex_color: str) -> str:
    """Convierte #RRGGBB a 'R, G, B' para rgba()."""
    h = hex_color.lstrip("#")
    return f"{int(h[0:2], 16)}, {int(h[2:4], 16)}, {int(h[4:6], 16)}"


def _build_hacker_theme():
    """Tema Hacker especial (verde terminal)."""
    return {
        "bg_app":       "#04080a", "bg_panel":     "#071009", "bg_elevated":  "#0a1a0e",
        "bg_sunken":    "#04180d", "bg_overlay":   "rgba(0,0,0,0.6)",
        "text_primary":   "#00ff99", "text_secondary": "#00cc77", "text_tertiary":  "#00aa66",
        "text_disabled":  "#006644", "text_inverse":   "#04080a",
        "border_subtle":  "#0f3d24", "border_default": "#1a5c3a", "border_strong":  "#2a7a4e",
        "border_focus":   "#00ff77",
        "action_primary":       "#00ff77", "action_primary_hover": "#33ff99", "action_primary_active": "#00cc5f",
        "action_primary_text":  "#04080a", "action_secondary":     "#0a1a0e", "action_secondary_hover": "#1a3a2a",
        "surface_hover":     "rgba(0,255,153,0.08)", "surface_selected":  "rgba(0,255,153,0.15)",
        "surface_active":    "rgba(0,255,153,0.20)",
        "status_success": "#00cc55", "status_warning": "#ffaa00", "status_error": "#ff4444", "status_info": "#00aaff",
        "shadow_sm": SHADOW_SM, "shadow_md": SHADOW_MD, "shadow_lg": SHADOW_LG, "shadow_xl": SHADOW_XL,
        "btn_text_primary": "#04080a", "btn_text_hover": "#04080a", "btn_text_disabled": "#2e7a52",
        "btn_bg_hover": "#33ff99", "btn_bg_active": "#00cc5f", "btn_bg_disabled": "#0a1a0e", "btn_border_disabled": "#0a1a0e",
    }


# Plantilla QSS con placeholders para .format()
_QSS_TEMPLATE = """
/* ─── RESET BASE ─── */
* {{
    font-family: "{fuente_ui}";
    font-size: {TEXT_BASE};
    line-height: {LH_NORMAL};
}}

QWidget {{
    background-color: {bg_app};
    color: {text_primary};
}}

QMainWindow, QDialog {{ background-color: {bg_app}; }}
QLabel {{ background: transparent; color: {text_primary}; }}

/* ─── TÍTULOS ─── */
QLabel[heading="true"] {{
    font-size: {TEXT_LG};
    font-weight: 600;
    color: {text_primary};
    letter-spacing: {LS_HEADING};
    qproperty-textWrap: balance;
}}

/* ─── GRUPOS ─── */
QGroupBox {{
    border: 1px solid {border_default};
    border-radius: {RADIUS_LG};
    margin-top: {SPACE_6};
    padding-top: {SPACE_3};
    background: {bg_panel};
    font-weight: 500;
    color: {text_primary};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: {SPACE_4};
    padding: 0 {SPACE_3};
    color: {action_primary};
    font-weight: 600;
    font-size: {TEXT_MD};
}}

/* ─── BOTONES ─── */
QPushButton {{
    background-color: {action_primary};
    color: {btn_text_primary};
    border: 1px solid {action_primary};
    border-radius: {RADIUS_MD};
    padding: {SPACE_3} {SPACE_6};
    font-size: {TEXT_BASE};
    font-weight: 500;
    font-family: "{fuente_ui}";
    min-height: 28px;
}}
QPushButton:hover {{
    background-color: {btn_bg_hover};
    border-color: {btn_bg_hover};
}}
QPushButton:pressed {{
    background-color: {action_primary_active};
    border-color: {action_primary_active};
}}
QPushButton:disabled {{
    background-color: {btn_bg_disabled};
    color: {btn_text_disabled};
    border-color: {btn_border_disabled};
}}
QPushButton:focus {{
    outline: none;
    border: 2px solid {border_focus};
    outline-offset: 2px;
}}

/* Botón secundario (ghost) */
QPushButton[ghost="true"] {{
    background-color: transparent;
    color: {text_secondary};
    border: 1px solid {border_default};
    padding: {SPACE_2} {SPACE_4};
}}
QPushButton[ghost="true"]:hover {{
    background-color: {surface_hover};
    color: {text_primary};
    border-color: {border_strong};
}}
QPushButton[ghost="true"]:focus {{
    outline: none;
    border: 2px solid {border_focus};
}}

/* Botón peligro (destructivo) */
QPushButton[danger="true"] {{
    background-color: {STATUS_ERROR};
    border-color: {STATUS_ERROR};
    color: #ffffff;
}}
QPushButton[danger="true"]:hover {{ background-color: #b91c1c; border-color: #b91c1c; }}

/* ─── INPUTS Y COMBOBOX ─── */
QLineEdit, QComboBox {{
    background-color: {bg_sunken};
    color: {text_primary};
    border: 1px solid {border_default};
    border-radius: {RADIUS_MD};
    padding: {SPACE_3} {SPACE_4};
    font-size: {TEXT_BASE};
    font-family: "{fuente_ui}";
    min-height: 28px;
    selection-background-color: {action_primary};
    selection-color: #ffffff;
}}
QLineEdit:hover, QComboBox:hover {{
    border-color: {border_strong};
}}
QLineEdit:focus, QComboBox:focus {{
    border-color: {border_focus};
    outline: none;
}}
QLineEdit:disabled, QComboBox:disabled {{
    background-color: {bg_sunken};
    color: {text_disabled};
    border-color: {border_subtle};
}}

/* ComboBox dropdown */
QComboBox::drop-down {{
    border: none;
    width: 24px;
    background: transparent;
}}
QComboBox QAbstractItemView {{
    background-color: {bg_elevated};
    color: {text_primary};
    selection-background-color: {surface_selected};
    selection-color: {text_primary};
    border: 1px solid {border_default};
    border-radius: {RADIUS_MD};
    padding: {SPACE_2};
    outline: none;
}}
QComboBox QAbstractItemView::item {{
    padding: {SPACE_2} {SPACE_3};
    border-radius: {RADIUS_SM};
}}
QComboBox QAbstractItemView::item:hover {{
    background: {surface_hover};
}}
QComboBox QAbstractItemView::item:selected {{
    background: {surface_selected};
    color: {text_primary};
}}

/* ─── PLAINTEXTEDIT (logs, código) ─── */
QPlainTextEdit, QTextEdit {{
    background-color: {bg_sunken};
    color: {text_primary};
    border: 1px solid {border_default};
    border-radius: {RADIUS_MD};
    padding: {SPACE_3};
    font-family: "{fuente_mono}";
    font-size: {TEXT_SM};
    line-height: 1.6;
    selection-background-color: {action_primary};
    selection-color: #ffffff;
}}
QPlainTextEdit:focus, QTextEdit:focus {{
    border-color: {border_focus};
    outline: none;
}}

/* ─── TABS ─── */
QTabWidget::pane {{
    border: 1px solid {border_default};
    border-radius: {RADIUS_LG};
    top: -1px;
    background: transparent;
}}
QTabBar::tab {{
    background-color: {bg_panel};
    color: {text_secondary};
    border: 1px solid {border_default};
    padding: {SPACE_3} {SPACE_6};
    margin-right: {SPACE_2};
    border-top-left-radius: {RADIUS_MD};
    border-top-right-radius: {RADIUS_MD};
    font-size: {TEXT_SM};
    font-weight: 500;
    min-height: 28px;
}}
QTabBar::tab:selected {{
    background-color: {action_primary};
    color: {action_primary_text};
    font-weight: 600;
    border-color: {action_primary};
}}
QTabBar::tab:hover:!selected {{
    background-color: {action_secondary_hover};
    color: {text_primary};
}}
QTabBar::tab:focus {{
    outline: none;
    border: 2px solid {border_focus};
}}

/* ─── CHECKBOX ─── */
QCheckBox {{
    background: transparent;
    spacing: {SPACE_3};
    color: {text_primary};
    font-size: {TEXT_BASE};
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {border_default};
    border-radius: {RADIUS_SM};
    background: {bg_sunken};
}}
QCheckBox::indicator:hover {{
    border-color: {border_strong};
}}
QCheckBox::indicator:checked {{
    background-color: {action_primary};
    border-color: {action_primary};
    image: url(data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTIiIGhlaWdodD0iOSIgdmlld0JveD0iMCAwIDEyIDkiIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+CjxwYXRoIGQ9Ik0xIDQuNUw0LjUgOEwxMSAxIiBzdHJva2U9IiNmZmZmZmYiIHN0cm9rZS13aWR0aD0iMiIgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIiBzdHJva2UtbGluZWpvaW49InJvdW5kIi8+Cjwvc3ZnPgo=);
}}
QCheckBox::indicator:focus {{
    outline: none;
    border: 2px solid {border_focus};
}}

/* ─── SCROLLBARS ─── */
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background-color: {border_default};
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background-color: {border_strong};
}}
QScrollBar::handle:vertical:pressed {{
    background-color: {border_strong};
}}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

/* Horizontal */
QScrollBar:horizontal {{
    background: transparent;
    height: 8px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background-color: {border_default};
    border-radius: 4px;
    min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{
    background-color: {border_strong};
}}

/* ─── TOOLTIPS ─── */
QToolTip {{
    background-color: {bg_elevated};
    color: {text_primary};
    border: 1px solid {border_default};
    border-radius: {RADIUS_MD};
    padding: {SPACE_3} {SPACE_4};
    font-size: {TEXT_SM};
}}

/* ─── PROGRESS BAR ─── */
QProgressBar {{
    background-color: {bg_sunken};
    border: 1px solid {border_default};
    border-radius: {RADIUS_MD};
    text-align: center;
    color: {text_primary};
    font-size: {TEXT_SM};
}}
QProgressBar::chunk {{
    background-color: {action_primary};
    border-radius: {RADIUS_MD};
}}

/* ─── SPLITTER (redimensionable) ─── */
QSplitter::handle {{
    background: transparent;
    width: 4px;
    height: 4px;
}}
QSplitter::handle:hover {{
    background: {border_focus};
}}
QSplitter::handle:horizontal {{
    width: 4px;
}}
QSplitter::handle:vertical {{
    height: 4px;
}}
QSplitter::handle:focus {{
    outline: none;
    background: {border_focus};
}}

/* ─── MENSAJES DE ESTADO (labels con clase) ─── */
QLabel[status="success"] {{ color: {status_success}; font-weight: 500; }}
QLabel[status="warning"] {{ color: {status_warning}; font-weight: 500; }}
QLabel[status="error"]   {{ color: {status_error}; font-weight: 500; }}
QLabel[status="info"]    {{ color: {status_info}; font-weight: 500; }}
QLabel[status="muted"]   {{ color: {text_tertiary}; }}
"""


def _qss(c: dict) -> str:
    """Genera QSS completo con tokens semánticos usando .format() para evitar problemas con llaves."""
    # Resolver fuentes (inicializa si no lo está)
    fuente_mono = _get_fuente_mono()
    fuente_ui = _get_fuente_ui()
    return _QSS_TEMPLATE.format(
        fuente_ui=fuente_ui,
        fuente_mono=fuente_mono,
        TEXT_BASE=TEXT_BASE,
        LH_NORMAL=LH_NORMAL,
        TEXT_LG=TEXT_LG,
        LS_HEADING=LS_HEADING,
        TEXT_MD=TEXT_MD,
        TEXT_SM=TEXT_SM,
        SPACE_2=SPACE_2,
        SPACE_3=SPACE_3,
        SPACE_4=SPACE_4,
        SPACE_6=SPACE_6,
        RADIUS_SM=RADIUS_SM,
        RADIUS_MD=RADIUS_MD,
        RADIUS_LG=RADIUS_LG,
        STATUS_ERROR=STATUS_ERROR,
        **c
    )


# Temas disponibles - combinaciones Neutral/Accent + Claro/Oscuro + Hacker
NEUTRALES_DISPONIBLES = ["Slate", "Zinc", "Gray", "Stone"]
ACENTOS_DISPONIBLES = ["Blue", "Teal", "Emerald", "Green", "Amber", "Orange", "Red", "Rose", "Violet", "Purple", "Indigo", "Sky", "Cyan"]
MODOS = ["Claro", "Oscuro"]

# Generar todas las combinaciones base
NOMBRES = [f"{n}/{a} {m}" for n in NEUTRALES_DISPONIBLES for a in ACENTOS_DISPONIBLES for m in MODOS]

# Añadir temas legacy y especial
NOMBRES += ["Claro", "Oscuro", "Hacker"]
_TEMAS_CACHE = {}


def inicializar_temas():
    """Genera los temas QSS. Debe llamarse después de crear QApplication."""
    global _TEMAS_CACHE
    if not _TEMAS_CACHE:
        for nombre in NOMBRES:
            _TEMAS_CACHE[nombre] = _qss(_qss_variables(nombre))


def obtener_temas():
    """Devuelve el diccionario de temas, inicializando si es necesario."""
    if not _TEMAS_CACHE:
        inicializar_temas()
    return _TEMAS_CACHE
