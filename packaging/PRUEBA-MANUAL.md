# Prueba manual de un binario publicado (v2.0.0)

Checklist de ~15 min por SO para validar de punta a punta un binario de la
[Release de GitHub](https://github.com/BenReynor/autopiloto-gui/releases).
El agente de prueba recomendado es **opencode** (CLI agnóstico; en Windows es
`.exe`/`.cmd`). Los binarios **no llevan firma de código**: ver el apartado
de primer arranque de cada SO.

Códigos de salida del motor (`--autopiloto-loop`): `0` = loop completado,
`2` = agente no disponible, `4` = sin internet, `7` = error interno.

---

## 0. Preparación común

1. Un proyecto de prueba con un plan mínimo:

   ```markdown
   # Plan

   - [ ] t1: crear hola.txt
         criterio: existe hola.txt
   ```

2. Tener **opencode instalado y visible en el PATH** de la shell con la que se
   lanzará (en la GUI, el PATH que hereda la app desde el escritorio).
   Comprobar con `opencode --version`.

---

## 1. Linux (`.AppImage` / `.deb` / `.tar.gz`)

1. Verificar checksum: `sha256sum -c SHA256SUMS` (junto a los ficheros en la
   Release).
2. AppImage: `chmod +x autopiloto-gui-*.AppImage && ./autopiloto-gui-*.AppImage`.
   .deb: `sudo apt install ./autopiloto-gui_*.deb`.
3. **GUI**: arranca el panel; añadir un proyecto con el `plan.md` del punto 0;
   cambiar de tema y confirmar que persiste al reiniciar.
4. **Motor**: lanzar el loop desde el panel → `progreso.log` avanza, el gate
   corre, y `t1` termina `[x]` (existe `hola.txt`).
5. **CLI**: `./autopiloto-gui-*.AppImage --autopiloto-loop plan.md`
   (en el cwd del proyecto): con opencode en PATH → rc `0`; si se quita del
   PATH → rc `2` y `ABORTADO: agente no disponible (opencode)` en la cola del
   `progreso.log`.
6. **Sensor térmico**: en máquinas con `/sys/class/thermal` se muestra el dato;
   sin él, "sin dato" (degradación esperada).

## 2. Windows (`autopiloto-gui-2.0.0-win64.zip`)

1. Verificar checksum desde PowerShell:
   `Get-FileHash autopiloto-gui-2.0.0-win64.zip -Algorithm SHA256`
   y comparar con `SHA256SUMS-windows`.
2. Descomprimir → `autopiloto-gui\autopiloto-gui.exe`.
3. **Primer arranque**: SmartScreen → *Más información* → *Ejecutar de todas
   formas*. Abre el panel.
4. **GUI**: añadir proyecto con el `plan.md` del punto 0; tema persistente.
5. **Gate**: requiere **Git for Windows** instalado (el loop usa `gate.sh`
   con su `bash`). Sin Git Bash, el loop corre pero el gate bloquea la tarea.
   Con Git Bash en el PATH, `t1` pasa el criterio y `progreso.log` lo refleja.
6. **CLI** (PowerShell, en el cwd del proyecto):
   `.\autopiloto-gui\autopiloto-gui.exe --autopiloto-loop plan.md`
   → rc `0` con opencode en PATH; rc `2` sin él.

## 3. macOS (`autopiloto-gui-2.0.0-macos-arm64.dmg`)

> Solo **Apple Silicon (arm64)**. Binario sin firmar ni notarizar.

1. Verificar checksum: `shasum -a 256 -c SHA256SUMS-macos`.
2. Abrir el dmg → arrastrar **Autopiloto.app** a Aplicaciones.
3. **Primer arranque**: `control + clic` en la app → *Abrir*. Alternativa:
   `xattr -dr com.apple.quarantine /Applications/Autopiloto.app`.
4. **GUI + motor**: igual que Linux; el **sensor térmico degrada a "sin dato"**
   (no hay `/sys/class/thermal` en macOS; comportamiento esperado).
5. **CLI**: `"/Applications/Autopiloto.app/Contents/MacOS/autopiloto-gui" \
   --autopiloto-loop plan.md` → rc `0` con opencode en PATH; rc `2` sin él.

---

## Qué falla y qué hacer

| Síntoma | Causa probable |
|---|---|
| SmartScreen / Gatekeeper bloquea | Binario sin firma: usar los pasos de "primer arranque". |
| Loop bloquea la tarea (Windows) | Falta Git for Windows (el gate usa bash). |
| rc `2` inesperado | El agente no está en el PATH que hereda la app: usa `CLI_OPENCODE` o configura el PATH. |
| rc `4` | Sin red en el momento del run. |
| "sin dato" de temperatura | Esperado en macOS; en Linux solo si no existe `/sys/class/thermal`. |

Si algo no encaja: abre un issue con el texto del `progreso.log`.