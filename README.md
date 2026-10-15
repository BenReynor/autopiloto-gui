# Dédalo

[![CI](https://github.com/BenReynor/dedalo/actions/workflows/ci.yml/badge.svg)](https://github.com/BenReynor/dedalo/actions/workflows/ci.yml)
[![Release](https://github.com/BenReynor/dedalo/actions/workflows/release.yml/badge.svg)](https://github.com/BenReynor/dedalo/actions/workflows/release.yml)
[![Latest release](https://img.shields.io/github/v/release/BenReynor/dedalo?sort=semver&color=blue)](https://github.com/BenReynor/dedalo/releases)
[![License: MIT](https://img.shields.io/github/license/BenReynor/dedalo?color=green)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](pyproject.toml)
[![Platforms](https://img.shields.io/badge/platforms-Linux%20%7C%20macOS%20%7C%20Windows-informational)](#-compatibilidad)

Panel de control gráfico (PySide6) para el sistema **Dédalo**: gestiona agentes IA (opencode, codex, claude) que iteran sobre tareas de un `plan.md`, ejecutan tests (`gate.sh`), piden revisión de código y commitean automáticamente.

> **¿Usas una IA para trabajar con este proyecto?** Pásale
> [`docs/FICHA_TECNICA.md`](docs/FICHA_TECNICA.md) —requisitos, dependencias,
> plataformas, superficie MCP y seguridad en un único fichero pensado para que
> un modelo (y una persona técnica) entienda de un vistazo qué es y qué tiene
> Dédalo— o el índice [`llms.txt`](llms.txt), pensado para que un LLM sepa qué
> hay aquí sin recorrer el repositorio entero.

---

## 📑 Índice

- [Instalación rápida](#-instalación-rápida)
- [Qué hace](#-qué-hace)
- [Tips de uso](#-tips-de-uso)
- [Atajos](#-atajos)
- [Temas (9 curados)](#-temas-9-curados)
- [Configuración persistente](#-configuración-persistente)
- [Agregar un proyecto que ya tiene contenido](#-agregar-un-proyecto-que-ya-tiene-contenido)
- [Catálogo de modelos (models.dev)](#-catálogo-de-modelos-modelsdev)
- [Requisitos del proyecto gestionado](#-requisitos-del-proyecto-gestionado)
- [Compatibilidad y descargas](#-compatibilidad)
- [Variables del loop (env)](#-variables-del-loop-env)
- [Servidor MCP (agente piloto)](#-servidor-mcp-agente-piloto)
- [Desarrollo](#-desarrollo)
- [Estructura clave](#-estructura-clave)
- [Bugs conocidos pendientes](#-bugs-conocidos-pendientes)

---

## 🚀 Instalación rápida

```bash
# Clonar
git clone https://github.com/BenReynor/dedalo.git
cd dedalo

# Instalación automática: crea .venv, instala con soporte MCP y
# genera el acceso directo en el escritorio.
bash install.sh

# Ejecutar: doble clic en el icono "Dédalo" del escritorio,
# o desde la terminal:
./lanzar.sh
```

> En Debian/Ubuntu, si falta el módulo venv: `sudo apt install python3-venv`.

<details>
<summary>Instalación manual (paso a paso)</summary>

```bash
# Entorno virtual (recomendado; evita el error PEP 668 de las distros)
python3 -m venv venv
source venv/bin/activate

# Dependencias (con soporte MCP)
pip install -e ".[mcp]"
# o mínimo sin MCP: pip install PySide6 pyqtgraph

# Dependencias de desarrollo (tests/lint)
pip install -e ".[dev]"

# Ejecutar
python -m dedalo
```
</details>

> **Python**: Requiere 3.10+.

---

## 🎯 Qué hace

| Función | Descripción |
|---------|-------------|
| **Plan** | Editor Kanban + Markdown de `plan.md` (tareas `- [ ]`, hechas `- [x]`, bloqueadas `- [B]`). |
| **Lecciones** | Editor de `lecciones.md` (memoria del proyecto): se inyecta al agente antes de cada tarea y se añade una entrada al bloquear. |
| **Incidencias** | Tabla de `incidencias.jsonl` (hora, iteración, tarea, tipo, motivo): fallos, abortos y bloqueos con su motivo real. |
| **Ejecución** | Lanza el loop: agente → gate → revisor → commit. Parámetros: hora límite, iteraciones, rama base, coste máx, revisión dual/manual. |
| **Logs** | Salida en vivo de `progreso.log` (loop) y `gate.sh`. Colapsable (⛶) con header siempre visible. Auto-scroll. |
| **Mapa** | Visor de `mapeo.txt` (módulos → tests). Botón **Regenerar** ejecuta `bash mapear.sh`. |
| **Métricas** | Dashboard en tiempo real: tareas/hora, coste acumulado (ámbar), gate OK/FAIL, revisor PASS/FAIL. Exporta CSV. |
| **Git** | Historial de commits del proyecto, revert rápido. |
| **Seguridad** | Límite temperatura CPU (apagado seguro), webhooks (Telegram, Discord, WhatsApp). |

> **Contexto del proyecto (`CONTEXTO.md`)**: fichero permanente que describe *de
> qué va* el proyecto (de qué trata, requisitos, filosofía, estructura). El loop
> lo **inyecta en el prompt del agente y del revisor** en cada iteración, para
> que trabajen con el marco del proyecto y no a ciegas. A diferencia de
> `lecciones.md` (errores aprendidos, crece solo) y `plan.md` (tareas), el
> contexto es estable y lo escribes tú. Se instala con un esqueleto en cada
> proyecto y **nunca se sobreescribe**. No tiene panel en la GUI: se edita con
> tu editor.

---

## 💡 Tips de uso

- **Empieza por el contexto.** Un `CONTEXTO.md` claro y un `plan.md` con tareas
  pequeñas y verificables dan mejores resultados que prompts largos: el loop
  inyecta `CONTEXTO.md` al agente y al revisor en *cada* iteración.
- **`auto` ya elige bien.** Toma el primer CLI instalado *y con sesión*; si un
  agente aparece como `claude (sin login)`, loguéalo o elige otro.
- **Primer contacto con un repo ajeno: activa revisión manual.** Con
  `REVISION_MANUAL=1` el loop pausa antes de cada commit y espera tu `APPROVE`.
- **Pon un tope de gasto.** `MAX_COSTO` es un límite duro en USD; fíjalo antes
  de dejar el loop desatendido.
- **No edites a mano los 3 scripts del framework** (`dedalo.sh`, `gate.sh`,
  `mapear.sh`): se renuevan solos al abrir el proyecto. Si los tocas, haz commit
  antes.
- **Mantén el gate rápido.** Corre en cada iteración; un gate lento frena todo
  el ciclo.
- **Tu configuración vive en `~/.config/dedalo/`.** Cópiala antes de
  experimentar; si quieres empezar de cero, bórrala.
- **El binario empaquetado no trae el MCP por stdio** (se compila sin consola):
  para el "agente piloto" MCP usa el código fuente.
- **Verifica las descargas.** Comprueba los `SHA256SUMS*` de cada Release antes
  de ejecutar un binario.

---

## ⌨️ Atajos

| Tecla | Acción |
|-------|--------|
| `Ctrl+1` … `Ctrl+9` | Cambiar pestaña (Plan, Lecciones, Incidencias, Ejecución, Logs, Mapa, Git, Métricas, Seguridad) |
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

Guarda en `~/.config/dedalo/proyectos.json`:

- Proyectos registrados (ruta + config por proyecto)
- Tema activo
- Seguridad térmica
- Webhooks
- Modelos seleccionados
- **Ancho del sidebar** (`sidebar_ancho`)

Dos datos de la ventana no van aquí, sino en el `QSettings` de Qt
(`~/.config/dedalo/panel.conf`): la geometría de la ventana y el
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
| Ficheros que faltan (`plan.md`, `lecciones.md`, `CONTEXTO.md`, `.gitignore`, scripts) | Los copia de la plantilla. **Nunca pisa un fichero que ya exista.** |
| `plan.md`, `lecciones.md`, `CONTEXTO.md`, `gate_checks/*.sh` | Son contenido tuyo. No se comparan ni se sobrescriben nunca. |
| `dedalo.sh`, `gate.sh`, `mapear.sh` | **Sí se sobrescriben** al abrir el proyecto si difieren de la plantilla. Si los editaste a mano, haz commit antes. |
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
├── dedalo.sh    # loop bash (DEPRECADO; la GUI usa el motor python)
├── gate.sh          # checks (tests, lint, etc.) — bash, única pieza no nativa
├── mapear.sh        # genera mapeo.txt
├── plan.md          # lista de tareas
├── lecciones.md     # memoria del proyecto
├── CONTEXTO.md      # contexto permanente (de qué va el proyecto; se inyecta al agente y al revisor)
├── incidencias.jsonl # fallos/abortos/bloqueos (lo escribe el motor)
└── progreso.log     # lo escribe el motor (lo parsea la GUI)
```

El motor del loop es `dedalo/loop.py` (port del script, nacido en `W2`,
mismo log/observabilidad). La GUI lo lanza con su propio intérprete
(`python -m dedalo.loop`, o `--dedalo-loop` dentro del binario
empaquetado) y ya no requiere bash para arrancar. Los ficheros `dedalo.sh`,
`gate.sh`, `mapear.sh` se copian automáticamente al crear/abrir el proyecto
desde la plantilla del repo (`dedalo/plantillas_data/`); `dedalo.sh`
se conserva como referencia y para ejecución manual en terminal POSIX.

---

## 🖥️ Compatibilidad

| SO | Estado |
|----|--------|
| **Linux** | ✅ Funciona. Es el entorno de referencia y donde corre CI. |
| **macOS** | ⚠️ Parcial. Ya no exige GNU coreutils: `timeout` → `_timeout` (GNU/gtimeout/respaldo bash que devuelve 124) y `sed -i "0,/…/"` → `marcar_plan` (awk+cat, conserva permisos), con tests que impiden regresiones. Queda el sensor térmico (`/sys/class/thermal`, sólo Linux; degrada a "sin dato") y la verificación en un Mac real + el `.dmg`. |
| **Windows** | ✅ GUI + loop + gate nativos. Tanto el loop (`dedalo/loop.py`) como el gate (`dedalo/gate.py`) son motores Python que la GUI lanza con su propio intérprete: **ya no hace falta Git Bash** (PATH con `os.pathsep`, CLIs con sufijo `.exe`/`.cmd`, suite en CI en `windows-latest`). El gate corre los checks `*.py` de `gate_checks/` y, si hay bash, prefiere los `*.sh` equivalentes. Queda bash solo para el mapa del proyecto (`mapear.sh`) y el motor bash opcional (`dedalo.sh`). |

Lo que sí es independiente del SO desde ya: los finales de línea de los `.sh`
(`.gitattributes` fuerza `eol=lf`, un `clone` en Windows con `autocrlf` ya no
rompe el shebang) y el formato numérico (`LC_ALL=C`: con un locale español,
`awk`/`printf` escribían `0,500000` y `metrics.jsonl` quedaba como JSON
inválido).

`tests/test_portabilidad.py` es el guardarraíl: falla si alguien reintroduce una
construcción no portable, y un job de CI en `macos-latest` ejecuta ese lint
contra los binutils de BSD de verdad. La allowlist de bloqueos pendientes
(sólo Windows; la de macOS quedó vacía al portar `timeout` y el marcado del
plan) está al final de ese fichero, con el motivo de cada uno.

### 📦 Descargas (Release)

Los binarios por plataforma se publican en [Releases](https://github.com/BenReynor/dedalo/releases)
al etiquetar un `v*` (Linux: `.tar.gz`/`.deb`/`.AppImage`; Windows: `.zip`
con `dedalo.exe`; macOS: `.dmg`). Los builds **no llevan firma de
código**: al instalarlos el sistema pedirá confirmación explícita:

| SO | Primer arranque |
|----|-----------------|
| **macOS** | `control + clic` en la app → *Abrir* (o `xattr -dr com.apple.quarantine /Applications/Dedalo.app`). |
| **Windows** | SmartScreen advertirá con *Más información → Ejecutar de todas formas*. |
| **Linux** | Sin firma ni sandbox; procedencia = este repositorio (los checksums están en la propia Release). |

Cada Release lleva sus `SHA256SUMS*`; se verifican con
`shasum -a 256 -c SHA256SUMS[-windows|-macos]`.

La validación de puntas (GUI + un run real del loop con un agente como
opencode) está documentada, paso a paso y por SO, en
[packaging/PRUEBA-MANUAL.md](packaging/PRUEBA-MANUAL.md).

#### 🏷️ Etiquetas (tags) y estado de las Releases

Los tags actuales son `v2.0.0`, `v2.0.1` (pre-renombrado) y `v2.0.2` (ya como
Dédalo). Cada tag `v*` dispara `.github/workflows/release.yml`, que construye y
publica una Release con los binarios de los tres SO. Conviene saber que:

- Las Releases **v2.0.0 / v2.0.1 son anteriores al renombrado**: su título es
  *"Autopiloto v2.0.x"* y sus assets se llaman `autopiloto-gui-*`. **Siguen
  descargándose** (son código funcional de la era pre-Dédalo), pero **no
  reflejan el código actual** del repo.
- A partir de **v2.0.2** los assets se generan como `dedalo-<versión>-…` y el
  título de la Release es *"Dédalo"*.
- Los enlaces *Full Changelog* de las Releases antiguas apuntan al nombre viejo
  `autopiloto-gui`; GitHub **redirige** los repos renombrados, así que no dan
  404.
- **Topics del repositorio**: se gestionan con
  `gh repo edit --add-topic <tema>` (independientes de los tags git).

---

## 🔧 Variables del loop (env)

El motor del loop (`dedalo/loop.py`; `dedalo.sh` es su port bash,
deprecado por la GUI) se configura por variables de entorno (la GUI las rellena
desde el formulario de Ejecución). Las más útiles:

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

## 🤖 Servidor MCP (agente piloto)

`dedalo.mcp_server` expone el estado de los proyectos y las acciones
del loop por **MCP sobre stdio**, para que un agente "piloto" (p. ej. opencode
o Claude Desktop) pueda leer el plan, las incidencias y las métricas, correr el
gate, iniciar/parar el loop y **resolver la revisión manual** que de otro modo
esperaría a una persona.

Requiere el extra opcional `mcp` (no se instala por defecto):

```bash
pip install -e ".[mcp]"

# Arrancar el servidor (habla JSON-RPC por stdin/stdout)
python -m dedalo.mcp_server
```

Configuración de un cliente MCP (ejemplo `opencode`/Claude Desktop):

```json
{
  "mcpServers": {
    "dedalo": {
      "command": "python",
      "args": ["-m", "dedalo.mcp_server"]
    }
  }
}
```

**Herramientas de lectura:** `listar_proyectos`, `estado_proyecto`,
`leer_fichero`, `leer_incidencias`, `resumen_metricas`, `cola_log`,
`estado_agentes`, `listar_modelos`.

**Herramientas de acción:** `instalar_proyecto`, `correr_gate`, `iniciar_loop`
(segundo plano), `estado_loop`, `detener_loop`, `resolver_revision`.

**Recursos:** `dedalo://{proyecto}/{fichero}` con lista blanca (`plan.md`,
`lecciones.md`, `CONTEXTO.md`, `progreso.log`, `metrics.jsonl`,
`incidencias.jsonl`, `mapeo.txt`).

La revisión manual del loop se resuelve escribiendo en
`<proyecto>/.dedalo_review/decision`: `resolver_revision(nombre, "APPROVE")`
o `REJECT <motivo>`. El piloto puede aprobar lo trivial y escalar lo dudoso.

> Nota: el binario de PyInstaller se empaqueta `--windowed` (sin consola), así
> que el transporte stdio no está disponible en el `.exe`; usa el código fuente
> para el servidor MCP.

---

## 🐛 Desarrollo

```bash
# Instalar deps de desarrollo
pip install -e ".[dev]"

# Tests
QT_QPA_PLATFORM=offscreen python -m pytest tests/ -q

# Lint
python -m ruff check dedalo/ tests/

# Smoke de instalación NO editable (la que de verdad importa: con
# `pip install -e .` los ficheros ausentes en package-data no se notan)
python -m pip wheel --no-deps -w /tmp/wheel . && python -m zipfile -l /tmp/wheel/*.whl

# Boot test (headless)
QT_QPA_PLATFORM=offscreen python -c "from dedalo.app import main; main()" &
```

`[project.optional-dependencies] dev` trae `pytest` y `ruff`, nada más: no
hay type checker en el proyecto, así que no configures mypy esperando que
haga nada.

---

## 📂 Estructura clave

```
dedalo/
├── app.py              # Ventana principal, orquestación, QProcess
├── paneles.py          # 8 paneles + widgets compartidos (PipelineLoop, LoopPill, etc.)
├── temas.py            # Sistema de diseño: 9 temas, QSS, colores_tema()
├── paneles_metricas.py # Dashboard pyqtgraph
├── metricas.py         # Parseo progreso.log → series
├── plan.py             # Modelo plan.md
├── proyectos.py        # Persistencia JSON (~/.config/dedalo/)
├── loop_launch.py      # preparación del lanzamiento (env + argv), compartida GUI/MCP
├── mcp_server.py       # servidor MCP por stdio (tools + recursos); extra `mcp`
├── plantillas.py       # Scaffold proyectos
├── plantillas_data/    # Scripts .sh template + memoria inicial
│   ├── dedalo.sh   # loop BASH (deprecado; referencia/uso manual)
│   ├── gate.sh         # gate bash (legacy/Unix; el loop usa gate.py)
│   ├── mapear.sh       # mapeo del repo
│   ├── plan.md         # memoria inicial (NO se sobreescribe)
│   ├── lecciones.md
│   ├── CONTEXTO.md     # contexto del proyecto (esqueleto; NO se sobreescribe)
│   ├── .gitignore      # excluye el framework del repo del usuario
│   └── gate_checks/    # 8 checks (.sh bash + .py port portable sin bash)
├── loop.py             # MOTOR del loop en Python (nativo, W2):
│   │                   #   Config, señales, gate portable, agentes, revisión,
│   │                   #   commit/merge/[B], integración, push
│   ├── gate.py         # orquestador portable del gate (checks .py; .sh vía bash)
│   ├── gate_env.py     # entorno del gate (port de gate_checks/_env.sh)
│   ├── loop_agentes.py # lanzamiento/agentes/revisor + métricas
│   ├── loop_git.py     # git en Python
│   ├── loop_proceso.py # run_con_timeout/killpg (agente o gate)
│   ├── loop_args.py    # parseo CLI (--hasta/--push/--padre/--trabajo)
│   └── plan.py         # modelo plan.md
└── tests/              # plan, métricas, plantillas, webhooks, GUI, log/revisión, agentes, net, sensor, proceso, config, portabilidad, temas/selector, loop python/e2e
```

---

## 🐛 Bugs conocidos pendientes

Defectos detectados y decididos no arreglar ahora, con su motivo y referencia al
código: [`docs/BUGS_CONOCIDOS.md`](docs/BUGS_CONOCIDOS.md).

---

## 📝 Licencia

MIT — texto completo en [LICENSE](LICENSE).