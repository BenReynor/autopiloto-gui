# Autopiloto GUI

Panel de control gráfico (PySide6) para el sistema **autopiloto**: gestiona agentes IA (opencode, codex, claude) que iteran sobre tareas de un `plan.md`, ejecutan tests (`gate.sh`), piden revisión de código y commitean automáticamente.

---

## 🚀 Instalación rápida

```bash
# Clonar
git clone <repo>
cd autopiloto-gui

# Entorno virtual (recomendado)
python3 -m venv venv
source venv/bin/activate

# Dependencias
pip install -e .
# o manual: pip install PySide6 pyqtgraph

# Ejecutar
python -m autopiloto_gui
```

> **Python**: Requiere 3.10+. En este repo se usa el venv en `../Sistema_Pos/frontend/venv/`.

---

## 🎯 Qué hace

| Función | Descripción |
|---------|-------------|
| **Plan** | Editor Kanban + Markdown de `plan.md` (tareas `- [ ]`, hechas `- [x]`, bloqueadas `- [B]`). |
| **Ejecución** | Lanza el loop: agente → gate → revisor → commit. Parámetros: hora límite, iteraciones, rama base, coste máx, revisión dual/manual. |
| **Logs** | Salida en vivo de `progreso.log` (loop) y `gate.sh`. Colapsable (⛶) con header siempre visible. Auto-scroll. |
| **Mapa** | Visor de `mapeo.txt` (módulos → tests). Botón **Regenerar** ejecuta `bash mapear.sh`. |
| **Métricas** | Dashboard temps-real: tareas/hora, coste acumulado (ámbar), gate OK/FAIL, revisor PASS/FAIL. Exporta CSV. |
| **Git** | Historial de commits del proyecto, revert rápido. |
| **Seguridad** | Límite temperatura CPU (apagado seguro), webhooks (Telegram, Discord, WhatsApp). |

---

## ⌨️ Atajos

| Tecla | Acción |
|-------|--------|
| `Ctrl+1` … `Ctrl+8` | Cambiar pestaña (Plan, Lecciones, Ejecución, Logs, Mapa, Git, Métricas, Seguridad) |
| `Ctrl+Q` | Salir |

---

## 🎨 Temas (9 curados)

| Tema | Estilo |
|------|--------|
| **Oscuro / Claro** | Slate/Blue clásicos |
| **Hacker** | Verde terminal |
| **Cyberpunk** | Neón fucsia/morado sobre grafito |
| **Zinc/Amber Oscuro** | Cabina ámbar (defecto) |
| **Gray/Red Oscuro** | Rojo |
| **Stone/Emerald Claro** | Verde cálido |
| **Zinc/Sky Claro** | Azul |
| **Slate/Teal Oscuro** | Teal profundo |

Cambio en vivo desde el selector "Tema" en la barra superior.

---

## ⚙️ Configuración persistente

Guarda en `~/.config/autopiloto/proyectos.json`:

- Proyectos registrados (ruta + config por proyecto)
- Tema activo
- Seguridad térmica
- Webhooks
- Modelos seleccionados
- **Ancho del sidebar** (`sidebar_ancho`)

---

## 🔧 Requisitos del proyecto gestionado

Cada proyecto debe tener en su raíz:

```
proyecto/
├── autopiloto.sh    # script principal (se copia del template)
├── gate.sh          # checks (tests, lint, etc.)
├── mapear.sh        # genera mapeo.txt
├── plan.md          # lista de tareas
├── lecciones.md     # memoria del proyecto
└── progreso.log     # lo escribe el loop
```

Los scripts `autopiloto.sh`, `gate.sh`, `mapear.sh` se copian automáticamente al crear/abrir el proyecto desde la plantilla del repo (`autopiloto_gui/plantillas_data/`).

---

## 🐛 Desarrollo

```bash
# Tests
QT_QPA_PLATFORM=offscreen python -m pytest tests/ -q

# Lint
python -m ruff check autopiloto_gui/

# Type check (opcional)
python -m mypy autopiloto_gui/ --ignore-missing-imports

# Boot test (headless)
QT_QPA_PLATFORM=offscreen python -c "from autopiloto_gui.app import main; main()" &
```

---

## 📂 Estructura clave

```
autopiloto_gui/
├── app.py              # Ventana principal, orquestación, QProcess
├── paneles.py          # 8 paneles + widgets compartidos (PipelineLoop, LoopPill, etc.)
├── temas.py            # Sistema de diseño: 9 temas, QSS, colores_tema()
├── paneles_metricas.py # Dashboard pyqtgraph
├── metricas.py         # Parseo progreso.log → series
├── plan.py             # Modelo plan.md
├── proyectos.py        # Persistencia JSON (~/.config/autopiloto/)
├── plantillas.py       # Scaffold proyectos
├── plantillas_data/    # Scripts .sh template
│   ├── autopiloto.sh
│   ├── gate.sh
│   └── mapear.sh
└── tests/              # 17 tests (plan, metricas, navegador, plantillas, webhooks)
```

---

## 📝 Licencia

MIT