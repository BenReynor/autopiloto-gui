# 02_migrations.py — Migraciones al día (comando configurable).
# Port de 02_migrations.sh para el orquestador portable (Windows sin bash).
# Sobreescribe con MIGRATE_CHECK. Ej (Django):
#   "cd <backend> && python manage.py migrate --check"


def run(env):
    if env.migrate_check is not None:
        if env.ejecutar(env.migrate_check) == 0:
            env.ok("migraciones al día")
        else:
            env.fail("migraciones pendientes (MIGRATE_CHECK falló)")
            return 1
    else:
        env.aviso("MIGRATE_CHECK no configurado, se omite")
    return 0
