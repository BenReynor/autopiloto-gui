# 99_custom.py — User's custom checks.
# Port of 99_custom.sh for the portable orchestrator (Windows without bash).
# Returns 0=OK, 1=FAIL. Put your own verifications here:
# lint, typecheck, security, build, quality gates, etc.
import os
import shutil
import subprocess


def run(env):
    # ── Lint: ruff (Python) ──
    if shutil.which("ruff") and not os.environ.get("SKIP_RUFF"):
        p = subprocess.run(
            ["ruff", "check", "."], cwd=env.backend_dir,
            capture_output=True, text=True)
        if p.returncode == 0:
            env.ok("ruff OK")
        else:
            env.fail("ruff encontró problemas (SKIP_RUFF=1 para omitir)")
            return 1
    else:
        env.aviso("ruff no instalado o SKIP_RUFF=1, se omite")

    print("[GATE] \u2713 custom checks (ruff)")
    return 0
