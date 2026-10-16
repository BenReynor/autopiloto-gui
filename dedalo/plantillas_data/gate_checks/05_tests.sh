#!/usr/bin/env bash
# 05_tests.sh — Runs the test suite (configurable command).
# Override with the TEST_CMD env var. E.g.:
#   cd <backend> && python -m pytest -q
#   npm test
#   cargo test
set -uo pipefail

if [ -z "$TEST_CMD" ]; then
    echo "[GATE] ⚠ TEST_CMD no configurado, se omite la test suite"
    exit 0
fi

# Show the test output (the last lines) for diagnostics
SALIDA="$(eval "$TEST_CMD" 2>&1)"
rc=$?
echo "$SALIDA" | tail -10

# pytest with no tests returns 5; it is not a failure, there is just no suite
if echo "$SALIDA" | grep -qiE "no tests ran" && [ "$rc" -eq 5 ]; then
    echo "[GATE] ⚠ test suite vacía (no hay tests), se asume OK"
    exit 0
fi
if [ "$rc" -ne 0 ]; then
    echo "[GATE] ✗ test suite en ROJO"
    exit 1
fi
ok "test suite en verde"