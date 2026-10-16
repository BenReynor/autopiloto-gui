# 02_migrations.py — Migrations up to date (configurable command).
# Port of 02_migrations.sh for the portable orchestrator (Windows without bash).
# Override with MIGRATE_CHECK. E.g. (Django):
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
