# 01_db.py — Verifica la base de datos (comando configurable).
# Port de 01_db.sh para el orquestador portable (Windows sin bash).
# Sobreescribe con DB_CHECK_CMD. Ej: pg_isready -q, mysqladmin ping, ""


def run(env):
    if env.db_check is not None:
        if env.ejecutar(env.db_check, timeout=30) == 0:
            env.ok("Base de datos disponible")
        else:
            env.fail("la base de datos no responde (DB_CHECK_CMD)")
            return 1
    else:
        env.aviso("DB_CHECK_CMD no configurado; lo confirma el backend")
    return 0
