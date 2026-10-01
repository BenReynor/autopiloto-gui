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

# Dependencias de desarrollo (tests/lint/types)
pip install -e ".[dev]"

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

## 🔧 Variables del loop (env)

`autopiloto.sh` se configura por variables de entorno (la GUI las rellena desde
el formulario de Ejecución). Las más útiles:

| Variable | Descripción |
|----------|-------------|
| `AGENTE_TAREA` | Agente que implementa: `opencode`\|`codex`\|`claude`\|`auto` (def). |
| `AGENTES_PREFERIDOS` | Orden de preferencia para `auto` y el revisor. |
| `MODELO_TAREA` | Modelo `provider/model` de la tarea (solo opencode). |
| `AGENTE_REVISOR` / `MODELO_REVISOR` | Agente y modelo del gate dual (revisor del diff). |
| `REVISION_DUAL` | `1` activa el revisor (def), `0` lo apaga. |
| `REVISION_MANUAL` | `1` pausa antes de commit y espera tu aprobación en la GUI. |
| `TIMEOUT_REVISION_MANUAL` | Segundos máximos de espera de aprobación manual; al expirar marca la tarea `[B]` y sigue (`0` = infinito). def: `1800`. |
| `MAX_COSTO` | Presupuesto en USD (`0` = sin límite). |
| `COSTO_POR_ITER` | Coste estimado USD por tarea+revisión (def `0.50`). |
| `VOZ` | `1` activa alertas con `notify-send`/`spd-say`. |
| `NAVEGADOR` / `MODELO_NAVEGADOR` | Navegador automático de contexto antes de cada tarea. |
| `CRITERIO` | Se extrae de la línea `criterio:` bajo la tarea en `plan.md`. |

> Durante la espera de `REVISION_MANUAL`, si se cae la red el loop aborta (no se
> queda colgado); y si expira `TIMEOUT_REVISION_MANUAL` marca la tarea `[B]`.

---

## 🐛 Desarrollo

```bash
# Instalar deps de desarrollo
pip install -e ".[dev]"

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
└── tests/              # 48 tests (plan, métricas, navegador, plantillas, webhooks, GUI, net, sensor, proceso)
```

---

## 📝 Licencia

MIT