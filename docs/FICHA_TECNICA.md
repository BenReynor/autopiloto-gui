# Ficha técnica — Dédalo

Documento para quien va a **usar o integrar** Dédalo y quiere los datos duros
sin leer el código. Para uso paso a paso ver [README](../README.md); para deuda
técnica viva, [BUGS_CONOCIDOS.md](BUGS_CONOCIDOS.md).

## Qué es

Panel de control gráfico (PySide6) que orquesta agentes IA de línea de comandos
(`opencode`, `codex`, `claude`) sobre un proyecto: iteran tareas de un `plan.md`,
ejecutan el gate (`gate.sh`), piden revisión de código y commitean. El motor no
depende de la GUI: se puede manejar por CLI o por MCP.

- **Paquete / CLI / binario**: `dedalo`
- **Nombre visible**: Dédalo
- **Repositorio**: <https://github.com/BenReynor/dedalo>
- **Versión**: 2.0.2
- **Licencia**: MIT (código propio)

## Requisitos

| Requisito | Valor |
|-----------|-------|
| Python | ≥ 3.10 |
| Sistema operativo | Linux (referencia), macOS (arm64), Windows nativo (WSL2/Git Bash no necesario) |
| Interfaz gráfica | Qt (X11/Wayland en Linux, nativo en macOS/Windows) |
| Red | Solo saliente (API de modelos, `git` remoto, webhooks); no abre puertos |

## Dependencias

| Paquete | Versión | Papel | Licencia |
|---------|---------|-------|----------|
| PySide6 | ≥ 6.11.0 | GUI (Qt) | LGPL-3.0 (vía bindings dinámicos) |
| pyqtgraph | ≥ 0.13.7 | Gráficas | MIT |
| mcp | ≥ 2 (extra `[mcp]`) | Servidor MCP por stdio | MIT |

Dev (`.[dev]`): `pytest`, `ruff`. Cerradura completa con hashes en
[`requirements.lock`](../requirements.lock) (generada con `uv pip compile`).

## Instalación

```bash
git clone https://github.com/BenReynor/dedalo.git
cd dedalo
python3 -m venv venv && source venv/bin/activate
pip install -e .            # de fuentes
pip install -e ".[dev]"     # + tests/lint
pip install -e ".[mcp]"     # + servidor MCP
python -m dedalo            # arranca la GUI
```

También hay `install.sh` (entorno + acceso directo en el escritorio).

## Componentes

| Módulo | Función |
|--------|---------|
| `dedalo/app.py` | Ventana principal PySide6 (arranque `python -m dedalo`). |
| `dedalo/loop.py` | Motor del loop: agente → gate → revisor → commit. |
| `dedalo/gate.py` | Ejecuta los checks (`gate_checks/`) y decide verde/rojo. |
| `dedalo/mcp_server.py` | Servidor MCP por stdio (integración con agentes/editores). |
| `dedalo/plantillas_data/dedalo.sh` | Port bash del loop (deprecado por la GUI). |
| `dedalo/plantillas_data/gate.sh`, `mapear.sh` | Gate y mapeo del proyecto del usuario. |
| `dedalo/plantillas_data/` | Plantillas que se copian a cada proyecto: `plan.md`, `lecciones.md`, `CONTEXTO.md`, `gate_checks/`, icono. |

Instalar las plantillas en un proyecto crea `dedalo.sh`, `gate.sh`, `mapear.sh`,
`gate_checks/`, `CONTEXTO.md` y ajusta el `.gitignore` para excluir el framework
del repo del usuario.

## Uso por CLI

```bash
python -m dedalo                      # GUI
python -m dedalo.gate --proyecto RUTA  # solo el gate (exit 0 verde / ≠0 rojo)
python -m dedalo.mcp_server            # servidor MCP (stdio)
```

`dedalo.sh` (port bash, deprecado) y el `entrypoint` empaquetado aceptan
`--dedalo-loop`, `--dedalo-gate`, `--dedalo-mcp`. El motor se configura por
variables de entorno (ver tabla en el [README](../README.md#-variables-del-loop-env)).

## Servidor MCP

Servidor por **stdio** (JSON-RPC), pensado para que un cliente MCP (opencode,
etc.) controle Dédalo sin GUI. Protocolo `2024-11-05`.

- **Arranque**: `python -m dedalo.mcp_server`
- **17 herramientas**: `listar_proyectos`, `estado_proyecto`, `leer_fichero`,
  `leer_plan`, `leer_lecciones`, `leer_contexto`, `leer_incidencias`,
  `resumen_metricas`, `cola_log`, `estado_agentes`, `listar_modelos`,
  `instalar_proyecto`, `correr_gate`, `iniciar_loop`, `estado_loop`,
  `detener_loop`, `resolver_revision`.
- **Instrucciones** (`instructions` del `initialize`): manual curado de Dédalo
  (qué es, cómo funciona el loop, ficheros del proyecto y flujo de uso), que el
  cliente entrega al modelo como contexto de arranque.
- **Recursos**:
  - `dedalo://{nombre}/{fichero}` — ficheros permitidos: `plan.md`,
    `lecciones.md`, `CONTEXTO.md`, `progreso.log`, `metrics.jsonl`,
    `incidencias.jsonl`, `mapeo.txt`.
  - `dedalo://manual` — el manual completo bajo demanda.

Ejemplo de configuración en un cliente MCP (opencode):

```json
{
  "mcp": {
    "dedalo": {
      "type": "local",
      "command": ["/ruta/al/venv/bin/python", "-m", "dedalo.mcp_server"],
      "enabled": true
    }
  }
}
```

## Datos y estado

| Ruta | Contenido |
|------|-----------|
| `~/.config/dedalo/proyectos.json` | Registro de proyectos (+ tokens de webhooks). |
| `~/.config/dedalo/models_dev.json` | Catálogo de modelos. |
| `<proyecto>/plan.md`, `lecciones.md`, `progreso.log` | Estado por proyecto. |

El directorio de config se crea con permisos `0700`.

## Plataformas y artefactos

Los binarios se publican en [Releases](https://github.com/BenReynor/dedalo/releases)
al etiquetar `v*`; cada Release incluye `SHA256SUMS*`.

| SO | Artefactos | Estado |
|----|------------|--------|
| Linux | `dedalo-<v>-linux-x86_64.tar.gz`, `dedalo_<v>_amd64.deb`, `dedalo-<v>-x86_64.AppImage` | Referencia |
| macOS | `dedalo-<v>-macos-arm64.dmg` | Publicado (sin firmar) |
| Windows | `dedalo-<v>-win64.zip` (`dedalo.exe`, onedir) | Nativo (sin Git Bash) |

Los builds **no van firmados**: macOS pide `control + clic → Abrir`; Windows,
SmartScreen (*Más información → Ejecutar de todas formas*). Checksums en la
propia Release (`shasum -a 256 -c SHA256SUMS*`).

### Decisiones de distribución (cerradas)

- **Sin firma de código** ni notarización: los secretos de firma son opcionales
  en CI; sin ellos el `.dmg`/`.exe` salen sin firmar y el SO avisa.
- **Sin `.rpm`/Snap/Flatpak**: se cubre «cualquier distro» con AppImage +
  `.deb` + tar.gz portátil.
- **Windows nativo**: no se empaqueta WSL2; el motor bash se sustituye por
  Python en el bundle (`dedalo.exe`), sin exigir Git Bash.
- **macOS Intel**: pendiente (hoy solo arm64).
- Verificación de integridad vía `SHA256SUMS` en cada Release (sin firma GPG).

## Seguridad (postura actual)

Implementado:

- Sin servidor HTTP propio ni `eval`/`exec`/`os.system`/`pickle.load`.
- Escritura atómica del registro (temporal + `os.replace`).
- **CI `seguridad`**: `gitleaks` sobre el historial completo + `pip-audit
  --strict` sobre `requirements.lock` + comprobación de que el lock está al día.
- Cerradura de dependencias con hashes (`requirements.lock`).
- `_sanitizar()` enmascara tokens (telegram/whatsapp/discord) en errores.
- El gate restaura `gate.sh`/`gate_checks/` si el agente los modifica.

Riesgos conocidos (aceptados, ver [BUGS_CONOCIDOS.md](BUGS_CONOCIDOS.md)):

- Los tokens de webhooks se guardan **en claro** en
  `~/.config/dedalo/proyectos.json` (carpeta `0700`; fichero sin cifrar).
- El agente IA corre con el usuario completo, **sin sandbox** (modelo de la
  herramienta, documentado como riesgo).

## Calidad y CI

| Aspecto | Estado |
|---------|--------|
| Tests | 414 passed, 4 skipped (`pytest`) |
| Lint | `ruff` (reglas E, F, W, I, UP, B) — limpio |
| Portabilidad | `test_portabilidad.py` como guardarraíl (bash BSD/GNU) |
| CI | 5 jobs: Linux, Windows, macOS, portabilidad macOS, seguridad |

## Enlaces

- [README](../README.md) — uso y referencia de variables.
- [docs/BUGS_CONOCIDOS.md](BUGS_CONOCIDOS.md) — deuda técnica viva.
- [packaging/PRUEBA-MANUAL.md](../packaging/PRUEBA-MANUAL.md) — validación manual por SO.
