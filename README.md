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

# Dependencias de desarrollo (tests/lint)
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

Dos datos de la ventana no van aquí, sino en el `QSettings` de Qt
(`~/.config/autopiloto-gui/panel.conf`): la geometría de la ventana y el
proyecto que estaba activo.

El registro se escribe de forma atómica (temporal + `os.replace()`), así que
un corte de luz a mitad de escritura no lo deja a medias. Aun así, si el
JSON llegara a estar corrupto, la app **no arranca**: te dice dónde está el
problema, deja una copia `proyectos.json.corrupto` (nunca pisa una anterior) y
ofrece dos salidas:

- **Salir y repararlo a mano** (por defecto): el original queda intacto y, si
  reabres, vuelve a avisarte en vez de perder el registro en silencio.
- **Empezar de cero**: sólo entonces se descarta el original, y la copia se
  conserva por si hay que recuperar algo a mano.

---

## 📂 Agregar un proyecto que ya tiene contenido

El selector de carpeta admite cualquier directorio existente, no sólo uno
vacío. Conviene saber qué toca la app en cada caso:

| | Qué hace |
|---|---|
| Ficheros que faltan (`plan.md`, `lecciones.md`, `.gitignore`, scripts) | Los copia de la plantilla. **Nunca pisa un fichero que ya exista.** |
| `plan.md`, `lecciones.md`, `gate_checks/*.sh` | Son contenido tuyo. No se comparan ni se sobrescriben nunca. |
| `autopiloto.sh`, `gate.sh`, `mapear.sh` | **Sí se sobrescriben** al abrir el proyecto si difieren de la plantilla. Si los editaste a mano, haz commit antes. |
| Directorio sin repo git | Hace `git init -b master` y un commit inicial con lo que haya (`git add -A`). |

O sea: tu código y tus documentos están a salvo; los tres scripts del
framework se consideran código de soporte y se renuevan solos.

---

## 🌐 Catálogo de modelos (models.dev)

Los modelos salen de `https://models.dev/api.json`, y el catálogo se cachea
**7 días** (`modelos.CATALOGO_HORAS`). Cambiar de proveedor relanza la
consulta; el resto de la sesión va sobre la caché, así que refrescar la GUI no
toca la red. Si no hay red, se sirve lo cacheado y se avisa en el log.

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

## 🖥️ Compatibilidad

| SO | Estado |
|----|--------|
| **Linux** | ✅ Funciona. Es el entorno de referencia y donde corre CI. |
| **macOS** | ⚠️ Parcial. Las plantillas ya no usan construcciones exclusivas de GNU (`seq`, `date +%3N`, `head -n -1`, `find -printf`, `${VAR^^}`, `ping -W`), pero **todavía falla** por: `timeout` (no viene en macOS), `sed -i "0,/…/"` (extensión GNU: el marcado `[x]/[B]` del plan no se aplica) y `/sys/class/thermal` en el sensor. |
| **Windows** | ❌ No. Las plantillas son bash puro y la GUI las lanza con `bash`. Haría falta WSL2/Git Bash. Además la GUI concatena el PATH con `:` en vez de `os.pathsep` y busca los CLI sin `.exe`. |

Lo que sí es independiente del SO desde ya: los finales de línea de los `.sh`
(`.gitattributes` fuerza `eol=lf`, un `clone` en Windows con `autocrlf` ya no
rompe el shebang) y el formato numérico (`LC_ALL=C`: con un locale español,
`awk`/`printf` escribían `0,500000` y `metrics.jsonl` quedaba como JSON
inválido).

`tests/test_portabilidad.py` es el guardarraíl: falla si alguien reintroduce una
construcción no portable, y un job de CI en `macos-latest` ejecuta ese lint
contra los binutils de BSD de verdad. La allowlist de bloqueos pendientes
(sólo macOS/Windows) está al final de ese fichero, con el motivo de cada uno.

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
| `AGENTE_JUEZ` | Agente del juez de `criterio:` (def: el de la tarea). |
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

### Agentes CLI

`auto` (por defecto) elige el primer CLI instalado según `AGENTES_PREFERIDOS`
(`opencode codex claude`). La GUI muestra sólo los agentes que encuentra en la
máquina y etiqueta el detectado en la opción `auto`, así que nunca ofrece uno
que no exista.

- `codex` se invoca con `codex exec --skip-git-repo-check`.
- `claude` se invoca con `claude -p --output-format text`.
- Sólo `opencode` acepta `MODELO_*` (`provider/model`); la GUI deshabilita el
  selector para los otros dos, que toman su modelo de su propia cuenta.
- Si el CLI está instalado pero sin sesión (`Not logged in`, 401, API key
  inválida), el loop se detiene con un aviso claro en lugar de marcar tareas
  como fallidas por un error de autenticación.
- Al arrancar, la GUI sondea en segundo plano si cada CLI tiene sesión: los que
  no la tienen aparecen como `claude (sin login)` y no se pueden seleccionar.
  El sondeo se cachea y no bloquea la interfaz; el botón de refrescar modelos
  vuelve a lanzarlo.
- Para `opencode` la sesión no se puede determinar sin ambigüedad (responde
  siempre 0 y sus modelos de catálogo no necesitan credenciales), así que se
  considera utilizable y se marca como "sesión no verificada".

---

## 🐛 Desarrollo

```bash
# Instalar deps de desarrollo
pip install -e ".[dev]"

# Tests
QT_QPA_PLATFORM=offscreen python -m pytest tests/ -q

# Lint
python -m ruff check autopiloto_gui/ tests/

# Smoke de instalación NO editable (la que de verdad importa: con
# `pip install -e .` los ficheros ausentes en package-data no se notan)
python -m pip wheel --no-deps -w /tmp/wheel . && python -m zipfile -l /tmp/wheel/*.whl

# Boot test (headless)
QT_QPA_PLATFORM=offscreen python -c "from autopiloto_gui.app import main; main()" &
```

`[project.optional-dependencies] dev` trae `pytest` y `ruff`, nada más: no
hay type checker en el proyecto, así que no configures mypy esperando que
haga nada.

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
├── plantillas_data/    # Scripts .sh template + memoria inicial
│   ├── autopiloto.sh   # loop principal
│   ├── gate.sh         # gate de calidad
│   ├── mapear.sh       # mapeo del repo
│   ├── plan.md         # memoria inicial (NO se sobreescribe)
│   ├── lecciones.md
│   ├── .gitignore      # excluye el framework del repo del usuario
│   └── gate_checks/    # 8 checks (db, migrations, backend, imports, tests…)
└── tests/              # plan, métricas, plantillas, webhooks, GUI, log/revisión, agentes, net, sensor, proceso, config, portabilidad, temas/selector
```

---

## 🐛 Bugs conocidos pendientes

Defectos detectados y decididos no arreglar ahora, con su motivo y referencia al
código: [`docs/BUGS_CONOCIDOS.md`](docs/BUGS_CONOCIDOS.md).

---

## 📝 Licencia

MIT — texto completo en [LICENSE](LICENSE).