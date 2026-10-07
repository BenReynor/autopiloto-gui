# Bugs conocidos pendientes

Registro intencionado de defectos **detectados y decididos no arreglar ahora**, con
motivo y referencia al código. Vive aquí para que no se pierdan en el chat ni en la
memoria del agente.

Estado de la suite: ver [README](../README.md#-desarrollo). Cada entrada indica si
tiene riesgo activo o sólo deuda técnica.

---

## 1. `liberar()` con nombre de atributo equivocado — `paneles.py`

**Riesgo activo: ninguno.** Deuda técnica.

`autopiloto_gui/paneles.py:1493` llama `w.liberar(self, "worker")` (sin guion bajo)
cuando el atributo real es `self._worker` (línea 1487). `Trabajo.liberar` hace
`setattr(owner, nombre, None)`, así que:

- crea un atributo nuevo `worker` que no usa nadie,
- `self._worker` **nunca se limpia**.

No provoca el crash de "QThread: Destroyed while thread is still running" porque la
línea 1489 ya tiene el guard `if self._worker and self._worker.isRunning(): return`,
que impide que haya dos hilos a la vez. El coste real es una referencia retenida al
último hilo terminado, que se sustituye en el siguiente arranque.

Se corrigió el gemelo grave de este bug en `webhooks.py` (commit `d45dbd3`), donde no
había guard y dos eventos solapados sí abortaban la aplicación.

**Arreglo cuando se toque ese panel:** cambiar `"worker"` por `"_worker"` y mover
`self._worker = w` antes de `w.start()`, como ya se hace en `app.py:164-175`.

---

## 2. El gate mata cualquier proceso del puerto — `03_backend.sh`

**Riesgo activo: aceptado por decisión explícita del usuario.**

`autopiloto_gui/plantillas_data/gate_checks/03_backend.sh:28-37` mata con
`lsof -ti :"$PUERTO" | xargs kill -9`. El comentario del código dice "otro proceso
**del gate**", pero en realidad es **cualquier** proceso que escuche en ese puerto,
incluido el backend de desarrollo del usuario, y sin aviso previo.

Se revisó y **se dejó como está** a petición explícita. Mitigación parcial ya
existente: el check libera el puerto en cada iteración, así que un proceso zombie de
una vuelta anterior sí se limpia.

Consecuencia conocida: `kill $BPID` (línea 41) no mata a los nietos que arranque el
servidor, que pueden quedar con el socket abierto. El siguiente `lsof` los encuentra y
los mata con `kill -9`.

**El `kill -9` por puerto mata a quien tenga el socket, sea o no del gate.** Se
comprobó de forma involuntariamente directa al escribir los tests del check: el puerto lo
deduce de `SERVE_URL`, así que si el servidor de test escucha ahí, `lsof -ti` devuelve
el propio PID de pytest y el check se mataba a sí mismo (el runner moría con SIGKILL
y sin rastro, porque el pipe a `tail` se llevaba el buffer). Por eso
`tests/test_gate_backend.py` pone un `lsof` de stub en el `PATH`: así el `kill -9`
queda fuera de los tests y no depende de un comportamiento que mata procesos
arbitrarios.

---

## 2b. Un 3xx en los endpoints ahora es fallo

**Riesgo activo: cosmético, con diagnóstico.**

Al endurecer la comprobación HTTP, un endpoint que responde 307/308 (típico por una
barra final que falta) pasó a ser rojo, antes verde. El mensaje incluye el código, así
que la causa es evidente: se corrige añadiendo la barra final al endpoint en
`endpoints.txt` o en `ENDPOINTS`.

No se usa `curl -L` a propósito: seguir redirecciones automáticamente podría dar un
falso 2xx sobre una ruta mal escrita.

---

## 3. `proyectos.json` no tiene versionado de esquema

**Riesgo activo: bajo.** Deuda técnica.

`autopiloto_gui/registro.py` ya protege el registro contra corrupción sintáctica
(escritura atómica, copia `.corrupto` y arranque bloqueado en lugar de perder
proyectos — commit `ffef4d6`), pero el formato no lleva versión. Una migración futura
que cambie claves no tiene forma de distinguir "configuración antigua" de "archivo
corrupto".

Cuando se añada la primera migración real: escribir `version: N` al crear el
registro y validar el número al leer.

---

## 4. Ramas huérfanas de tareas bloqueadas se acumulan

**Riesgo activo: cosmetico.** Consecuencia de una decisión tomada.

Al marcar una tarea como `[B]` por fallo de merge (decisión del usuario), la rama
`autopiloto/tareas/<fecha>/t<n>` se conserva para poder inspeccionar el trabajo. El
reaper de `autopiloto.sh:878-883` sólo borra la rama del mismo `<fecha>/t<iter>` del
run en curso, así que las de días anteriores se quedan.

Listarlas y borrarlas:

```bash
git -C <proyecto> branch --list 'autopiloto/tareas/*'
git -C <proyecto> branch --delete --force <rama>
```

---

## 5. Compatibilidad de plataforma

**Riesgo activo: conocido y documentado.** Ver
[README](../README.md#-compatibilidad).

- Linux es la plataforma de referencia y la única con verificación completa.
- macOS ya no exige GNU coreutils: `timeout` → `_timeout` (GNU/gtimeout/respaldo
  bash) y `sed -i "0,/…/"` → `marcar_plan` (awk+cat), con tests que impiden
  regresiones. Falta verificar en un Mac real y empaquetar el `.dmg`; el sensor
  térmico (`/sys/class/thermal`) no existe allí y degrada a "sin dato".
- Windows no tiene soporte: el backend es un script bash y los agentes CLI son Unix.