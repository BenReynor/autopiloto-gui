# PLAN

Reglas:
- Cada tarea = 1 línea de QUÉ + 1 línea de CRITERIO (archivos + tests). Nada subjetivo.
- DONE = commit en la rama de la tarea + gate verde (gate.sh) + el test falla sin el cambio.
- El loop procesa las tareas en orden de dependencia.
- Esto es la PLANTILLA: reemplaza la tarea de ejemplo por tus tareas reales conservando el formato.

## Tareas (en orden de dependencia)

- [ ] #1 REEMPLÁZAME: en una frase, qué construirá o arreglará el agente.
      criterio: test en tests/test_x.py → test_nombre en verde y falla sin el cambio; gate.sh OK.