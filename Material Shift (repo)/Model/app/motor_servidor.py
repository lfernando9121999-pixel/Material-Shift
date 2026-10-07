"""Proceso motor persistente de Material Shift.

La app (Material Shift.exe) lo arranca una sola vez y le envía peticiones por stdin, una
por línea: {"id": 7, "argv": ["--nogui", "--list-columns", ...]}. Cada petición ejecuta
exactamente la misma CLI de ajuste_plan_ejecutable.main(argv) que un proceso nuevo, y la
respuesta sale por stdout en una línea: {"id": 7, "rc": 0, "output": "...COLUMNS_RESULT:..."}.

Por qué: así no se paga en cada clic el arranque de Python + numpy/scipy (~1.2 s) ni la
lectura del Excel (~5 s, queda en caché). Para que cada petición se comporte igual que un
proceso nuevo, los dos módulos del motor se recargan antes de cada una (sus variables
globales vuelven a los valores por defecto); solo la caché de lectura sobrevive, y esa
caché devuelve copias nuevas en cada uso (ver generar_ajuste_plan_2034._cached).
"""
import contextlib
import importlib
import io
import json
import os
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import generar_ajuste_plan_2034 as core  # noqa: E402
import ajuste_plan_ejecutable as motor  # noqa: E402

CACHE = {}


def atender(argv):
    global core, motor
    core = importlib.reload(core)
    motor = importlib.reload(motor)
    core.PARSE_CACHE = CACHE
    core.CACHE_DIR = os.environ.get("MS_CACHE_DIR") or None
    salida = io.StringIO()
    rc = 0
    with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(salida):
        try:
            motor.main(argv)
        except SystemExit as e:
            if e.code not in (None, 0):
                rc = 1
                if not isinstance(e.code, int):
                    print(str(e.code))
        except Exception:
            rc = 1
            traceback.print_exc()
    return rc, salida.getvalue()


def main():
    entrada = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8")
    respuesta = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", newline="\n")
    respuesta.write(json.dumps({"id": 0, "rc": 0, "output": "READY"}) + "\n")
    respuesta.flush()
    for linea in entrada:
        linea = linea.strip()
        if not linea:
            continue
        try:
            req = json.loads(linea)
        except ValueError:
            continue
        if req.get("cmd") == "exit":
            break
        rc, out = atender(list(req.get("argv") or []))
        respuesta.write(json.dumps({"id": req.get("id"), "rc": rc, "output": out}, ensure_ascii=False) + "\n")
        respuesta.flush()


if __name__ == "__main__":
    main()
