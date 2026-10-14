# 05_tests.py — Ejecuta la test suite (comando configurable).
# Port de 05_tests.sh para el orquestador portable (Windows sin bash).
# Sobreescribe con TEST_CMD. Ej:
#   cd <backend> && python -m pytest -q
#   npm test
#   cargo test
import re


def run(env):
    if env.test_cmd is None:
        env.aviso("TEST_CMD no configurado, se omite la test suite")
        return 0

    rc, salida = env.ejecutar_salida(env.test_cmd)
    for linea in salida.splitlines()[-10:]:
        print(linea)

    # pytest sin tests devuelve 5; no es un fallo, solo no hay suite
    if rc == 5 and re.search(r"no tests ran", salida, re.IGNORECASE):
        env.aviso("test suite vacía (no hay tests), se asume OK")
        return 0
    if rc != 0:
        env.fail("test suite en ROJO")
        return 1
    env.ok("test suite en verde")
    return 0
