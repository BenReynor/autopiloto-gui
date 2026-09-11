# Panel de control del autopiloto

App de escritorio (PySide6) para gestionar el modo autopiloto en varios
proyectos sin tocar archivos ni terminal.

## Qué hace

- Registro de proyectos (`~/.config/autopiloto/proyectos.json`).
- Editor de `plan.md` con contador de tareas (`[ ]` / `[x]` / `[B]`).
- Lanzar / detener el loop (`autopiloto.sh`) con opciones: `--hasta`, `--padre`,
  `--push`, `MAX_ITER`.
- Salida en vivo del loop y de `gate.sh`.
- Vista de rama, `git status` y últimos commits.
- Temas: Claro, Oscuro y Hacker (verde/negro).
- Auto-provisión y actualización: al abrir un proyecto, instala los archivos
  que falten (`autopiloto.sh`, `gate.sh`, `mapear.sh`, `plan.md`, `progreso.log`)
  y actualiza automáticamente los que tengan una versión distinta a la de la app.
- Sin internet: el loop de tareas se aborta/rebota y la GUI lo indica en
  pantalla y no arranca sin conexión (los modelos IA necesitan red).
- Gate dual: al terminar una tarea, un segundo agente revisa el diff y debe
  emitir `VERDICT: PASS` antes de commitear. Modelos de opencode seleccionables
  por separado para tarea y revisor (lista en vivo con `opencode models`, botón
  ↻ Refrescar).
- Presupuesto estimado en USD/iteración con parada automática al agotarse.
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
  app.py           ventana principal
  modelos.py       lista de modelos de opencode (`opencode models`)
  sensor.py        lectura de temperatura de CPU
  proceso.py       captura en vivo de procesos
  plantillas.py    instalación de scripts en un proyecto
  plantillas/      autopiloto.sh, gate.sh, mapear.sh, plan.md (empaquetados)
  proyectos.py     registro de proyectos, tema y ajustes de seguridad
  temas.py         estilos Claro / Oscuro / Hacker
```