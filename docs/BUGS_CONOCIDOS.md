# Known bugs still open

A deliberate record of defects **found and decided not to fix now**, with
the reason and a pointer to the code. It lives here so they don't get lost in chat or in the
agent's memory.

Suite status: see [README](../README.md#-development). Each entry states whether it carries
an active risk or is just technical debt.

---

## 1. `liberar()` with the wrong attribute name — `paneles.py`

**Active risk: none.** Technical debt.

`dedalo/paneles.py:1493` calls `w.liberar(self, "worker")` (no underscore)
when the real attribute is `self._worker` (line 1487). `Trabajo.liberar` does
`setattr(owner, nombre, None)`, so:

- it creates a brand-new `worker` attribute nobody uses,
- `self._worker` **is never cleared**.

It does not cause the "QThread: Destroyed while thread is still running" crash because line
1489 already has the guard `if self._worker and self._worker.isRunning(): return`,
which keeps two threads from coexisting. The real cost is a retained reference to the
last finished thread, which is replaced on the next start.

The severe twin of this bug was fixed in `webhooks.py` (commit `d45dbd3`), where there
was no guard and two overlapping events did abort the application.

**Fix when that panel is touched:** change `"worker"` to `"_worker"` and move
`self._worker = w` before `w.start()`, as `app.py:164-175` already does.

---

## 2. The gate kills any process on the port — `03_backend.sh`

**Active risk: accepted at the user's explicit request.**

`dedalo/plantillas_data/gate_checks/03_backend.sh:28-37` kills with
`lsof -ti :"$PUERTO" | xargs kill -9`. The code comment says "another process
**of the gate**", but what it actually kills is **any** process listening on that port,
including the user's development backend, and without any warning.

It was reviewed and **left as is** at explicit request. Partial mitigation already
in place: the check frees the port on every iteration, so a zombie process from a
previous round does get cleaned up.

Known consequence: `kill $BPID` (line 41) does not kill the grandchildren spawned by the
server, which can be left holding the socket open. The next `lsof` finds them and
kills them with `kill -9`.

**The port-based `kill -9` kills whoever holds the socket, whether or not it belongs to the gate.** This was
proved in an unintentionally direct way while writing the tests for the check: the port is derived
from `SERVE_URL`, so if the test server listens there, `lsof -ti` returns
pytest's own PID and the check killed itself (the runner died with SIGKILL
and without a trace, because the pipe to `tail` took the buffer). That is why
`tests/test_gate_backend.py` puts a stub `lsof` on the `PATH`: that way the `kill -9`
stays out of the tests and does not depend on behavior that kills arbitrary
processes.

---

## 2b. A 3xx on endpoints is now a failure

**Active risk: cosmetic, with diagnostics.**

When the HTTP check was hardened, an endpoint responding 307/308 (typical for a
missing trailing slash) went from green to red. The message includes the code, so
the cause is obvious: fix it by adding the trailing slash to the endpoint in
`endpoints.txt` or in `ENDPOINTS`.

`curl -L` is deliberately not used: following redirects automatically could yield a
false 2xx on a mistyped route.

---

## 3. `proyectos.json` has no schema versioning

**Active risk: low.** Technical debt.

`dedalo/registro.py` already protects the registry against syntactic corruption
(atomic write, `.corrupto` copy and a blocked startup instead of losing
projects — commit `ffef4d6`), but the format carries no version. A future migration
that changes keys has no way to tell "old configuration" from "corrupt file".

When the first real migration lands: write `version: N` when creating the
registry and validate the number when reading.

---

## 4. Orphan branches from blocked tasks pile up

**Active risk: cosmetic.** Consequence of a deliberate decision.

Marking a task as `[B]` because a merge failed (user decision) keeps the branch
`dedalo/tareas/<fecha>/t<n>` around so the work can be inspected. The reaper in
`dedalo.sh:878-883` only deletes the branch for the same `<fecha>/t<iter>` of the
run in progress, so branches from earlier days stay behind.

To list and delete them:

```bash
git -C <proyecto> branch --list 'dedalo/tareas/*'
git -C <proyecto> branch --delete --force <rama>
```

---

## 5. Platform compatibility

**Active risk: known and documented.** See
[README](../README.md#-compatibility).

- Linux is the reference platform and the only one with full verification.
- macOS no longer requires GNU coreutils: `timeout` → `_timeout` (GNU/gtimeout/bash
  fallback) and `sed -i "0,/…/"` → `marcar_plan` (awk+cat), with tests that prevent
  regressions. Still to verify on a real Mac and to package the `.dmg`; the thermal
  sensor (`/sys/class/thermal`) does not exist there and degrades to "no data".
- Windows is partial: the GUI and the engines (loop `loop.py`, gate `gate.py`)
  run natively on Python (PATH joined with `os.pathsep`, `.exe`/`.cmd`
  CLIs resolved, tests in CI with the POSIX ones skipped). The gate runs the checks
  `*.py` in `gate_checks/` and only uses bash, if present, to prefer the equivalent
  `*.sh` ones. Bash remains only for the project map (`mapear.sh`,
  the "Refresh map" button) and the optional bash engine (`dedalo.sh`); verification
  on a real Windows machine is still missing.