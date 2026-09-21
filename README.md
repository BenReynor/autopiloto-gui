# Panel de control del autopiloto

App de escritorio (PySide6) para gestionar el modo autopiloto en varios
proyectos sin tocar archivos ni terminal.

## Qué hace

- Registro de proyectos (`~/.config/autopiloto/proyectos.json`).
- **Vista Kanban** en la pestaña Plan: columnas Pendiente/Hecha/Bloqueada con drag-visual de tareas.
- Editor de `plan.md` con contador de tareas (`[ ]` / `[x]` / `[B]`).
- Lanzar / detener el loop (`autopiloto.sh`) con opciones: `--hasta`, `--padre`,
  `--trabajo`, `--push`, `MAX_ITER`.
- **Rama de trabajo (`--trabajo`)**: elige en qué rama se integra el trabajo
  del run. Si la rama no existe, se crea desde la base; si existe (local u
  origin) se usa tal cual. Al terminar, todo lo producido en
  `autopiloto/<fecha>` se integra en la rama elegida y, con `--push`, se sube
  esa rama (y se indica el PR a abrir a la base).
- **Métricas del run**: pestaña con 4 gráficas en vivo (tareas por iteración,
  duración, coste acumulado, estado) + tabla resumen, leyendo `progreso.log`
  mientras el autopiloto corre.
- **Revisión manual de diff antes de commit** (opcional): la GUI muestra el diff,
  tú apruebas/rechazas; si rechazas, el motivo se inyecta en el siguiente intento.
- **Feedback automático del revisor**: si el gate dual da FAIL, sus razones se
  inyectan en el prompt del siguiente reintento.
- Salida en vivo del loop y de `gate.sh`.
- Vista de rama, `git status` y últimos commits (en hilo de fondo, no bloquea).
- Temas: Claro, Oscuro y Hacker (verde/negro).
- Auto-provisión y actualización: al abrir un proyecto, instala los archivos
  que falten (`autopiloto.sh`, `gate.sh`, `mapear.sh`, `plan.md`) y actualiza
  automáticamente los scripts `.sh` si su versión difiere de la de la app.
  `plan.md` solo se crea si falta: nunca se sobreescribe con la plantilla (es
  el contenido editable de tus tareas).
- Quitar proyecto: al eliminar un proyecto de la lista se pregunta primero y,
  si confirmas, borra solo los archivos de autopiloto del disco
  (`autopiloto.sh`, `gate.sh`, `mapear.sh`, `plan.md`, `progreso.log`,
  `gate_checks/`); el resto del proyecto jamás se toca.
- Sin internet: el loop de tareas se aborta/rebota y la GUI lo indica en
  pantalla y no arranca sin conexión (los modelos IA necesitan red).
- Gate dual: al terminar una tarea, un segundo agente revisa el diff y debe
  emitir `VERDICT: PASS` antes de commitear. Modelos de opencode seleccionables
  por separado para tarea y revisor (lista en vivo con `opencode models`, botón
  ↻ Refrescar).
- **Gates por plugins**: `gate.sh` ejecuta los checks en `gate_checks/*.sh`
  (01_db, 02_migraciones, 03_backend, 04_imports, 05_tests, 99_custom). Añade
  o quita checks libremente; `99_custom.sh` es la plantilla para tus propias
  verificaciones (lint, mypy, build…).
- Modelos de IA en dos niveles: el selector muestra primero el proveedor
  (`opencode`, `google`, `openai`, `anthropic`, etc.) y, al elegirlo, muestra
  los modelos de esa empresa. La lista se obtiene con `opencode models` (cuando
  el proveedor tiene credenciales) y, si no, del catálogo oficial de models.dev
  (la misma fuente de opencode, cacheado 7 días). Todo por selección, sin
  escribir; la elección se conserva entre sesiones.
- Presupuesto estimado en USD/iteración con parada automática al agotarse.
- **Notificación visual/sonora** cuando una tarea queda bloqueada (`[B]`).
- **Webhooks / notificaciones push**: pestaña Notificaciones para configurar
  Telegram, Discord y/o WhatsApp (Meta Cloud API) y recibir los eventos del
  autopiloto al instante.
- **Navigator automático**: antes de cada tarea, un agente navegador busca el
  contexto relevante (archivos a tocar, tests, endpoints) y se lo inyecta al
  agente de tarea, por modelo (configurable en la pestaña Ejecución).
- **Protección térmica**: vigila la temperatura de la CPU y, si supera el
  umbral, muestra el aviso dentro de la ventana con una cuenta regresiva;
  si nadie responde, el loop se detiene y la aplicación se apaga sola.
  Botones Continuar / Apagar ahora (pestaña Seguridad). La visualización en el
  panel es opcional (la verificación de fondo sigue activa) y, al activarla,
  la temperatura se actualiza cada segundo.

## Requisitos e instalación

Python 3.10+ con PySide6 (UI), pyqtgraph (gráficas de métricas) y opencode
instalado para el modo autopiloto.

```bash
pip install -r requirements.txt
```

## Uso

```bash
# directo
python -m autopiloto_gui

# con el lanzador (busca el intérprete con PySide6)
bash lanzar.sh
```

## Acceso directo (instalación automática)

`autopiloto_gui/acceso.sh` instala un acceso "inteligente" en el escritorio:

```bash
bash autopiloto_gui/acceso.sh
```

Instala tres piezas: el lanzador `~/.local/bin/autopiloto` (resuelve la
ubicación del proyecto dinámicamente y ejecuta `lanzar.sh`), el icono en
`~/.local/share/icons/autopiloto.svg` y el acceso
`~/Escritorio/autopiloto-gui.desktop`. Como el lanzador localiza el proyecto
solo, puedes mover la carpeta y el acceso seguirá funcionando. Reejecuta
`acceso.sh` cuando quieras refrescar icono o lanzador.

## Crear un proyecto nuevo

1. Crea la carpeta vacía de tu proyecto.
2. En el panel: **Agregar…** → selecciona esa carpeta.
3. La app instala sola `autopiloto.sh`, `gate.sh`, `mapear.sh`, `plan.md`
   (plantilla) y crea `progreso.log`. Las actualizaciones de estas plantillas
   se aplican automáticamente al abrir el proyecto.
4. Edita `plan.md` con tus tareas y pulsa **▶ Iniciar loop**.

## Estructura

```
autopiloto_gui/
  __main__.py       entrada
  app.py            ventana principal (orquestación de proyectos/procesos)
  configuracion.py  constantes centralizadas (rutas, timeouts, defaults)
  paneles.py        widgets por pestaña: Plan, Ejecución, Git, Seguridad + aviso térmico
  paneles_metricas.py panel de Métricas (4 gráficas pyqtgraph + tabla resumen)
  paneles_webhooks.py panel de Notificaciones (Telegram, Discord, WhatsApp)
  plan.py           modelo de datos de plan.md (lectura/conteo/guardado)
  modelos.py        lista de modelos de opencode (`opencode models`, cacheado por sesión)
  selector_modelo.py selector proveedor→modelo de dos niveles (editable)
  navegador.py      agente navegador automático (contexto para cada tarea)
  metricas.py       parseo de progreso.log → series temporales para gráficas
  webhooks.py       envío asíncrono de notificaciones (QThread)
  net.py            conectividad (verificación en segundo plano, no bloquea la UI)
  sensor.py         lectura de temperatura de CPU (con caché)
  proceso.py        captura en vivo de procesos
  plantillas.py     instalación de scripts en un proyecto
  plantillas_data/  autopiloto.sh (agnóstico: opencode/codex/claude),
                    gate.sh + gate_checks/*.sh (checks plugin), mapear.sh, plan.md
  proyectos.py      registro de proyectos, tema, seguridad, webhooks y modelos
  temas.py          estilos Claro / Oscuro / Hacker
  acceso.sh         instala el acceso directo dinámico en el escritorio
lanzar.sh           lanzador que localiza un intérprete con PySide6
```