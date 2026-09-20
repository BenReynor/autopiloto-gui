# Panel de control del autopiloto

App de escritorio (PySide6) para gestionar el modo autopiloto en varios
proyectos sin tocar archivos ni terminal.

## Qué hace

- Registro de proyectos (`~/.config/autopiloto/proyectos.json`).
- **Vista Kanban** en la pestaña Plan: columnas Pendiente/Hecha/Bloqueada con drag-visual de tareas.
- Editor de `plan.md` con contador de tareas (`[ ]` / `[x]` / `[B]`).
- Lanzar / detener el loop (`autopiloto.sh`) con opciones: `--hasta`, `--padre`,
  `--push`, `MAX_ITER`.
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
- **Protección térmica**: vigila la temperatura de la CPU y, si supera el
  umbral, muestra el aviso dentro de la ventana con una cuenta regresiva;
  si nadie responde, el loop se detiene y la aplicación se apaga sola.
  Botones Continuar / Apagar ahora (pestaña Seguridad). La visualización en el
  panel es opcional (la verificación de fondo sigue activa) y, al activarla,
  la temperatura se actualiza cada segundo.

## Requisitos e instalación

```bash
pip install -r requirements.txt
```

## Uso

```bash
python -m autopiloto_gui
```

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
  __main__.py      entrada
  app.py           ventana principal (orquestación de proyectos/procesos)
  configuracion.py constantes centralizadas (rutas, timeouts, defaults)
  paneles.py       widgets por pestaña: Plan, Ejecución, Git, Seguridad + aviso térmico
  plan.py          modelo de datos de plan.md (lectura/conteo/guardado)
  modelos.py       lista de modelos de opencode (`opencode models`, cacheado por sesión)
  selector_modelo.py selector proveedor→modelo de dos niveles (editable)
  net.py           conectividad (verificación en segundo plano, no bloquea la UI)
  sensor.py        lectura de temperatura de CPU (con caché)
  proceso.py       captura en vivo de procesos
  plantillas.py    instalación de scripts en un proyecto
  plantillas/      autopiloto.sh (agnóstico: opencode/codex/claude),
                   gate.sh + gate_checks/*.sh (checks plugin), mapear.sh, plan.md
  proyectos.py     registro de proyectos, tema y ajustes de seguridad
  temas.py         estilos Claro / Oscuro / Hacker
```