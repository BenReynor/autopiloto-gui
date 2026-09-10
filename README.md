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
- Auto-provisión: al agregar un proyecto, genera los archivos necesarios
  (`autopiloto.sh`, `gate.sh`, `mapear.sh`, `plan.md`, `progreso.log`).

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
   (plantilla) y crea `progreso.log`.
4. Edita `plan.md` con tus tareas y pulsa **▶ Iniciar loop**.

El botón "Instalar plantillas" re-hace ese paso en el proyecto seleccionado.

## Estructura

```
autopiloto_gui/
  __main__.py      entrada
  app.py           ventana principal
  proceso.py       captura en vivo de procesos
  plantillas.py    instalación de scripts en un proyecto
  plantillas/      autopiloto.sh, gate.sh, mapear.sh, plan.md (empaquetados)
  proyectos.py     registro de proyectos y tema
  temas.py         estilos Claro / Oscuro / Hacker
```