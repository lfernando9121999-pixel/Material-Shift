"""Compara la salida del motor de Material Shift contra la de v19.5 (referencia).

  python comparar_resultados.py <carpeta_v19.5> <carpeta_material_shift> caso1 [caso2 ...]

Por cada caso compara:
  1. Plan Modificado (todas las celdas): v19.5 '<caso> - Solo Plan Modificado.xlsx'
     vs Material Shift '<caso>.xlsx' (botón Excel, nombre exacto).
  2. Datos del dashboard por circuito: el JSON embebido en el HTML Recharts de v19.5
     vs '<caso> - Resultados.json'.
  3. Resumen MODEL_RESULT (movimientos, brechas, destinos_ok, objetivos).
Sale con código 1 si hay cualquier diferencia.
"""
import json
import math
import re
import sys
from pathlib import Path

import openpyxl


def celdas(path):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.worksheets[0]
    filas = [tuple(r) for r in ws.iter_rows(values_only=True)]
    wb.close()
    return filas


def igual(a, b):
    if isinstance(a, float) or isinstance(b, float):
        try:
            return math.isclose(float(a), float(b), rel_tol=1e-12, abs_tol=1e-9)
        except (TypeError, ValueError):
            return False
    return a == b


def comparar_json(a, b, ruta, difs, limite=20):
    if isinstance(a, dict) and isinstance(b, dict):
        for k in a:
            if k not in b:
                difs.append(f"{ruta}.{k}: falta en Material Shift")
            else:
                comparar_json(a[k], b[k], f"{ruta}.{k}", difs)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            difs.append(f"{ruta}: largo {len(a)} vs {len(b)}")
            return
        for i, (x, y) in enumerate(zip(a, b)):
            if len(difs) > limite:
                return
            comparar_json(x, y, f"{ruta}[{i}]", difs)
    elif not igual(a, b):
        difs.append(f"{ruta}: {a!r} vs {b!r}")


def data_html(path):
    t = Path(path).read_text(encoding="utf-8")
    m = re.search(r"const DATA = (\{.*?\});\n", t, re.S)
    return json.loads(m.group(1))


def main():
    ref, new = Path(sys.argv[1]), Path(sys.argv[2])
    total = 0
    for caso in sys.argv[3:]:
        print(f"== {caso}")
        a, b = celdas(ref / f"{caso} - Solo Plan Modificado.xlsx"), celdas(new / f"{caso}.xlsx")
        difs = []
        if len(a) != len(b):
            difs.append(f"filas {len(a)} vs {len(b)}")
        for i, (ra, rb) in enumerate(zip(a, b)):
            for j, (x, y) in enumerate(zip(ra, rb)):
                if not igual(x, y):
                    difs.append(f"fila {i + 1} col {j + 1}: {x!r} vs {y!r}")
        print(f"  Plan Modificado: {len(a)} filas x {len(a[0]) if a else 0} columnas -> {'IDENTICO' if not difs else f'{len(difs)} diferencias'}")
        for d in difs[:10]:
            print("    ", d)
        total += len(difs)

        res = json.loads((new / f"{caso} - Resultados.json").read_text(encoding="utf-8"))
        for circ, sufijo in (("Desmonte", ""), ("Mineral", " Mineral")):
            h = ref / f"{caso} - Recharts{sufijo}.html"
            if not h.exists():
                if circ in res["circuitos"]:
                    print(f"  {circ}: solo existe en Material Shift")
                    total += 1
                continue
            old = data_html(h)
            nueva = res["circuitos"].get(circ)
            difs = []
            if nueva is None:
                difs.append("falta el circuito")
            else:
                for k, v in old.items():
                    if k in ("baseMaterialDayDest", "materialDayDest", "conservationDayDest") and not v:
                        continue  # v19.5 solo las generaba en modo diario; ahora siempre
                    comparar_json(v, nueva.get(k), k, difs)
            print(f"  Dashboard {circ}: {len(old)} series -> {'IDENTICO' if not difs else f'{len(difs)} diferencias'}")
            for d in difs[:10]:
                print("    ", d)
            total += len(difs)

        ra = json.loads((ref / f"{caso}_dashboard-only.json").read_text(encoding="utf-8"))
        rb = json.loads((new / f"{caso}_dashboard-only.json").read_text(encoding="utf-8"))
        for circ in ("Desmonte", "Mineral"):
            if ra.get(circ) is None and rb.get(circ) is None:
                continue
            difs = []
            for k in ("movimientos", "brechas", "brechas_diarias", "row_breaks", "destinos_ok", "target_por_chancadora", "chancadoras", "donantes"):
                if not igual(json.dumps(ra[circ].get(k), sort_keys=True), json.dumps(rb[circ].get(k), sort_keys=True)):
                    difs.append(f"{k}: {ra[circ].get(k)} vs {rb[circ].get(k)}")
            print(f"  Resumen {circ}: movimientos={rb[circ]['movimientos']} brechas={rb[circ]['brechas']} -> {'IDENTICO' if not difs else difs}")
            total += len(difs)
    print("RESULTADO:", "SIN DIFERENCIAS" if total == 0 else f"{total} DIFERENCIAS")
    sys.exit(1 if total else 0)


if __name__ == "__main__":
    main()
