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

## Requisitos e instalación

```bash
pip install -r requirements.txt
```

## Uso

```bash
python -m autopiloto_gui
```

## Preparar un proyecto

Copia las plantillas a la raíz de cada proyecto (son los scripts que el
panel ejecuta) y edita su `plan.md`:

```bash
cp plantillas/autopiloto.sh plantillas/gate.sh plantillas/mapear.sh <proyecto>/
```

`mapear.sh` genera `mapeo.txt` (mapa módulos → tests) cada vez que arranca el
loop. Los scripts son portátiles (deducen su propia raíz); consulta los
comentarios de cada uno para ver las variables de entorno que admiten.

## Estructura

```
autopiloto_gui/
  __main__.py     entrada
  app.py          ventana principal
  proceso.py      captura en vivo de procesos
  proyectos.py    registro de proyectos
plantillas/       scripts por proyecto (autopiloto.sh, gate.sh, mapear.sh, plan.md)
```