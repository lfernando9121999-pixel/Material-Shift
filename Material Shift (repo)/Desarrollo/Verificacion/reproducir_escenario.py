"""Reproduce un escenario .csv (v2 de v19 o v3 de Material Shift) con un motor dado, armando los
mismos argumentos que envía el programa, y deja el Plan Modificado en <salida>.xlsx.

  python reproducir_escenario.py <carpeta_app_motor> <escenario.csv> <salida.xlsx> [archivo_base]

Sirve para comparar el motor de v19.5 y el de Material Shift con escenarios reales.
"""
import json
import subprocess
import sys
import unicodedata
from pathlib import Path

app, csv_path, salida = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
base_override = sys.argv[4] if len(sys.argv) > 4 else None
PY = Path(__file__).resolve().parents[2] / "Model" / "python" / "python.exe"


def norm(s):
    s = (s or "").strip().lower()
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


sec, gen, mineral_col, listas, matrices, cfg = "", {}, {}, {}, {}, {}
head = {}
for raw in csv_path.read_text(encoding="utf-8-sig").splitlines():
    line = raw.strip()
    if not line or line.startswith("sep="):
        continue
    if line.startswith("["):
        sec = norm(line.strip("[]"))
        continue
    c = [x.strip().strip('"') for x in line.split(";")]
    k = norm(c[0])
    if sec in ("general", "objetivos") and len(c) >= 2:
        gen[k] = c[1]
        if len(c) >= 3:
            mineral_col[k] = c[2]
    elif sec.startswith(("donantes", "fases")) and c[0].isdigit():
        listas.setdefault(sec, []).append((int(c[0]), c[1], norm(c[2]) != "no" if len(c) > 2 else True))
    elif sec.startswith("materiales"):
        if k == "destino":
            head[sec] = c
        elif k != "nota" and sec in head:
            for j, v in enumerate(c[1:], 1):
                if v == "0":
                    matrices.setdefault(c[0], []).append(head[sec][j])
    elif sec == "config destinos" and k not in ("nota", "destino") and len(c) >= 3:
        cfg[c[0]] = {"destino": c[1], "material": c[2]}


def activos(nombre):
    return [x[1] for x in sorted(listas.get(nombre, [])) if x[2]]


def num(k, d=None):
    v = gen.get(k)
    return float(v.replace(",", ".")) if v else d


modo = "balanceado" if norm(gen.get("modo", "")).startswith("balanc") else "objetivo_fijo"
gran = "diario" if norm(gen.get("granularidad", "")).startswith("diar") else "semanal"
tol = num("tolerancia", 0.05)
if gen.get("unidad de tolerancia") == "%":
    tol = num("objetivo mt/sem") * tol / 100
ch1 = next((c for sec_, items in [] for c in items), None)
chs = ["Chw2a_1", "Chw2a_2"]
argv = ["--nogui", "--excel-only", "--input", base_override or gen["archivo base"], "--output", str(salida),
        "--sheet", gen.get("hoja", "Plan_Base"), "--target-mode", modo, "--target-mt", str(num("objetivo mt/sem")),
        "--tolerance-mt", str(tol), "--granularity", gran,
        "--daily-tolerance-mt", str(num("tolerancia diaria mt", 0.02)), "--daily-target-mt", str(num("objetivo mt/dia", 0.17)),
        "--donor-priority", json.dumps({chs[0]: activos("donantes 1"), chs[1]: activos("donantes 2")}),
        "--phase-priority", json.dumps({chs[0]: activos("fases 1"), chs[1]: activos("fases 2")}),
        "--donantes-override", json.dumps([x[1] for x in sorted(listas.get("donantes 1", []))]),
        "--active-year", str(int(num("ano activo", 2034))),
        "--material-matrix", json.dumps(matrices)]
if cfg:
    argv += ["--destino-config", json.dumps(cfg)]
if "donantes mineral" in listas:
    mt = num("objetivo mt/sem mineral") if "objetivo mt/sem mineral" in gen else float(mineral_col.get("objetivo mt/sem", "1"))
    mtol = num("tolerancia mineral") if "tolerancia mineral" in gen else float(mineral_col.get("tolerancia", "0.05"))
    argv += ["--mineral-donor-priority", json.dumps(activos("donantes mineral")),
             "--mineral-phase-priority", json.dumps(activos("fases mineral")),
             "--mineral-target-mt", str(mt), "--mineral-tolerance-mt", str(mtol)]
env = {"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1", "SYSTEMROOT": r"C:\Windows"}
r = subprocess.run([str(PY), str(app / "ajuste_plan_ejecutable.py")] + argv, capture_output=True, text=True, encoding="utf-8", cwd=str(app), env=env)
print("rc", r.returncode, (r.stdout + r.stderr)[-300:].replace("\n", " "))
