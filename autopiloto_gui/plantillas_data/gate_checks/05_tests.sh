#!/usr/bin/env bash
# 05_tests.sh — Ejecuta la test suite (comando configurable).
# Sobreescribe con TEST_CMD env. Ej:
#   cd <backend> && python -m pytest -q
#   npm test
#   cargo test
set -uo pipefail

if [ -z "$TEST_CMD" ]; then
    echo "[GATE] ⚠ TEST_CMD no configurado, se omite la test suite"
    exit 0
fi

# Mostrar la salida de tests (las últimas líneas) para diagnóstico
SALIDA="$(eval "$TEST_CMD" 2>&1)"
rc=$?
echo "$SALIDA" | tail -10

# pytest sin tests devuelve 5; no es un fallo, solo no hay suite
if echo "$SALIDA" | grep -qiE "no tests ran" && [ "$rc" -eq 5 ]; then
    echo "[GATE] ⚠ test suite vacía (no hay tests), se asume OK"
    exit 0
fi
if [ "$rc" -ne 0 ]; then
    echo "[GATE] ✗ test suite en ROJO"
    exit 1
fi
ok "test suite en verde"