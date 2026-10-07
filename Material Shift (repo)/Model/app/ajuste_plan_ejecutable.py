import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

import xlsxwriter

import generar_ajuste_plan_2034 as core


DEFAULT_INPUT = r"D:\Descargas\Ajuste Plan 2034.xlsx"
DEFAULT_OUTPUT = r"C:\Users\Sebastian\Desktop\Antamina 2026\outputs\ajuste_plan_2034\Ajuste Plan 2034 - Resultado Dashboard.xlsx"
def fmt_t(value):
    try:
        return f"{float(value):,.0f}"
    except (TypeError, ValueError):
        return str(value)


def calculate_preview(
    input_path,
    sheet_name="Plan_Base",
    target_mode="objetivo_fijo",
    target_mt=1.18,
    tolerance_mt=0.05,
    donor_priority=None,
    phase_priority=None,
    granularity="semanal",
    daily_target_mt=None,
    daily_tolerance_mt=0.02,
    preloaded=None,
    donantes_override=None,
    active_year=None,
    material_blocked=None,
    circuit="Desmonte",
    destino_config=None,
):
    """Computes one circuit's preview ("Mineral" or "Desmonte"). Everything
    below this point (adjust_plan, refine_daily, the build_* dashboard
    helpers) was already written against core.CHANCADORES/DONORS/WASTE_TYPES/
    SEVEN generically -- it never hardcodes a destino or material name -- so
    running a different circuit only means temporarily pointing those globals
    at that circuit's own destinos/materiales (core.resolve_circuit()) for
    the duration of this call, exactly like core.run_circuit() does for the
    weekly LP alone. Returns None if this file has no such circuit
    configured (see core.resolve_circuit()).

    destino_config, when given, overrides Config_Destinos/Config_Materiales
    in-app (from the "Editar columnas detectadas" editor) instead of/on top
    of a 'Config' sheet in the file -- ignored when preloaded is given, since
    the caller (calculate_preview_both) already applied it once up front."""
    if preloaded is not None:
        headers, base = preloaded
    else:
        headers, base = core.load_plan_base(Path(input_path), sheet_name)
        if destino_config is not None:
            core.apply_destino_config_override(headers, destino_config)

    resolved = core.resolve_circuit(circuit, headers)
    if resolved is None:
        return None
    chancadoras, donors, materials = resolved
    if donantes_override is not None and not core.CONFIG_SHEET_USED:
        # Legacy manual override from the old "Columnas detectadas" editor --
        # only meaningful on a file without a 'Config' sheet (a single,
        # always-Desmonte circuit). With a Config sheet, donors come straight
        # from Config_Destinos, which supersedes this override entirely.
        donors = list(donantes_override)

    saved_globals = (core.CHANCADORES, core.DONORS, core.WASTE_TYPES, core.SEVEN)
    core.CHANCADORES, core.DONORS, core.WASTE_TYPES = chancadoras, donors, materials
    core.SEVEN = core.CHANCADORES + core.DONORS
    try:
        modified, moves, weekly_status, target_by_crusher, _, tolerance_by_crusher = core.adjust_plan(
            headers,
            base,
            target_mode=target_mode,
            requested_week_chw=target_mt * 1_000_000.0,
            tolerance_abs=tolerance_mt * 1_000_000.0,
            donor_priority=donor_priority,
            phase_priority=phase_priority,
            active_year=active_year,
            material_blocked=material_blocked,
        )
        daily_moves = []
        daily_status = []
        if granularity == "diario":
            daily_moves, daily_status = core.refine_daily(
                modified, headers, target_by_crusher, daily_tolerance_mt * 1_000_000.0,
                donor_priority=donor_priority, phase_priority=phase_priority,
                daily_target_abs=daily_target_mt * 1_000_000.0 if daily_target_mt is not None else None,
                material_blocked=material_blocked,
            )
        total_rows, weekly_rows, row_summary, row_breaks = core.build_validations(base, modified, target_by_crusher, tolerance_by_crusher)
        row_material_balance = core.check_row_material_balance(modified)
        matrix_check = core.check_material_matrix(base, modified, material_blocked)
        pivot_rows = core.build_pivot_like(modified)
        dashboard_weekly = weekly_rows
        dashboard_dest = build_dashboard_dest_fast(base, modified)
        dashboard_waste = []
        kpis = {}
        base_material_week_dest = build_material_week_dest(base)
        material_week_dest = build_material_week_dest(modified)
        movement_week_dest = build_movement_week_dest(moves)
        conservation_week_dest = build_conservation_week_dest(base, modified)
        waste_dest_detail = build_waste_dest_detail(base, modified)
        base_material_day_dest = build_material_day_dest(base) if granularity == "diario" else []
        material_day_dest = build_material_day_dest(modified) if granularity == "diario" else []
        conservation_day_dest = build_conservation_day_dest(base, modified) if granularity == "diario" else []
        brechas_diarias = sum(1 for r in daily_status if r[5] != "OK")
        return {
            "circuit": circuit,
            "chancadoras": chancadoras,
            "donantes": donors,
            "materiales": materials,
            "headers": headers,
            "base": base,
            "modified": modified,
            "moves": moves,
            "total_rows": total_rows,
            "weekly_rows": weekly_rows,
            "row_summary": row_summary,
            "row_breaks": row_breaks,
            "pivot_rows": pivot_rows,
            "dashboard_weekly": dashboard_weekly,
            "dashboard_dest": dashboard_dest,
            "dashboard_waste": dashboard_waste,
            "base_material_week_dest": base_material_week_dest,
            "material_week_dest": material_week_dest,
            "base_material_day_dest": base_material_day_dest,
            "material_day_dest": material_day_dest,
            "conservation_day_dest": conservation_day_dest,
            "daily_status": daily_status,
            "movement_week_dest": movement_week_dest,
            "conservation_week_dest": conservation_week_dest,
            "waste_dest_detail": waste_dest_detail,
            "kpis": kpis,
            "target_by_crusher": target_by_crusher,
            "tolerance_by_crusher": tolerance_by_crusher,
            "granularity": granularity,
            "daily_target_mt": daily_target_mt,
            "daily_tolerance_mt": daily_tolerance_mt,
            "row_material_balance": row_material_balance,
            "summary": {
                "movimientos": len(moves) + len(daily_moves),
                "brechas": sum(1 for r in weekly_rows if r[5] != "OK"),
                "brechas_diarias": brechas_diarias,
                "row_breaks": len(row_breaks),
                "destinos_ok": all(row[4] == "OK" for row in total_rows[:-1]),
                "balance_material_ok": row_material_balance["ok"],
                "balance_material_bad_rows": len(row_material_balance["bad_rows"]),
                "balance_material_max_dev_pct": row_material_balance["max_dev_pct"],
                "matriz_ok": matrix_check["ok"],
                "matriz_violaciones": len(matrix_check["violations"]),
                "lp_ok": core.LAST_LP["success"],
            },
        }
    finally:
        core.CHANCADORES, core.DONORS, core.WASTE_TYPES, core.SEVEN = saved_globals


def calculate_preview_both(
    input_path, sheet_name="Plan_Base", preloaded=None, destino_config=None,
    mineral_donor_priority=None, mineral_phase_priority=None,
    mineral_target_mt=None, mineral_tolerance_mt=None, **kwargs
):
    """Entry point for a single 'Calcular' click: runs Desmonte (always) and
    Mineral (only if this file's 'Config' sheet -- or an in-app
    destino_config override -- configures a Mineral receptor) and returns
    {"Desmonte": <preview or None>, "Mineral": <preview or None>}. Both
    circuits share one load_plan_base() call/parse.

    mineral_donor_priority/mineral_phase_priority are Mineral's OWN priority
    order (a plain list, applied to every Mineral chancadora the same way --
    see adjust_plan()'s as_per_crusher) -- kept separate from
    donor_priority/phase_priority, which are Desmonte's, since the two
    circuits' donors/chancadoras are different names entirely."""
    if preloaded is not None:
        headers, base = preloaded
    else:
        headers, base = core.load_plan_base(Path(input_path), sheet_name)
        if destino_config is not None:
            core.apply_destino_config_override(headers, destino_config)
    preloaded = (headers, base)

    result = {
        "Desmonte": calculate_preview(input_path, sheet_name, preloaded=preloaded, circuit="Desmonte", **kwargs),
        "Mineral": None,
    }
    if core.CONFIG_SHEET_USED and core.resolve_circuit("Mineral", headers) is not None:
        mineral_kwargs = dict(kwargs)
        mineral_kwargs.pop("donantes_override", None)  # legacy override is Desmonte-only
        mineral_kwargs["donor_priority"] = mineral_donor_priority
        mineral_kwargs["phase_priority"] = mineral_phase_priority
        if mineral_target_mt is not None:
            mineral_kwargs["target_mt"] = mineral_target_mt
        if mineral_tolerance_mt is not None:
            mineral_kwargs["tolerance_mt"] = mineral_tolerance_mt
        result["Mineral"] = calculate_preview(input_path, sheet_name, preloaded=preloaded, circuit="Mineral", **mineral_kwargs)
    return result


def build_material_week_dest(modified):
    rows = [{"Semana": week, **{dest: 0.0 for dest in core.SEVEN}, "Total": 0.0} for week in range(1, 53)]
    for week in range(1, 53):
        rows[week - 1]["Semana"] = week
    for rec in modified:
        if not (rec.get("_active_2034") or core.is_active_2034(rec)):
            continue
        week = int(core.to_number(rec.get("Semana")))
        if week < 1 or week > 52:
            continue
        row = rows[week - 1]
        for dest in core.SEVEN:
            value = core.to_number(rec.get(dest))
            row[dest] += value
            row["Total"] += value
    return rows


def build_material_day_dest(modified):
    rows = {}
    for rec in modified:
        if not (rec.get("_active_2034") or core.is_active_2034(rec)):
            continue
        day = core.excel_date(core.to_number(rec.get("Fecha Liberación")))
        if day is None:
            continue
        key = day.isoformat()
        if key not in rows:
            rows[key] = {"Dia": key, **{dest: 0.0 for dest in core.SEVEN}, "Total": 0.0}
        for dest in core.SEVEN:
            value = core.to_number(rec.get(dest))
            rows[key][dest] += value
            rows[key]["Total"] += value
    return [rows[k] for k in sorted(rows.keys())]


def build_movement_week_dest(moves):
    agg = {}
    for move in moves:
        week = int(move[0])
        source = str(move[6])
        target = str(move[7])
        tons = float(move[8])
        for dest, incoming, outgoing in [(target, tons, 0.0), (source, 0.0, tons)]:
            if dest not in core.SEVEN:
                continue
            key = (week, dest)
            if key not in agg:
                agg[key] = {"Semana": week, "Destino": dest, "Entradas": 0.0, "Salidas": 0.0, "Neto": 0.0}
            agg[key]["Entradas"] += incoming
            agg[key]["Salidas"] += outgoing
            agg[key]["Neto"] += incoming - outgoing
    return [agg[key] for key in sorted(agg)]


def build_conservation_week_dest(base, modified):
    agg = {(week, dest): {"Semana": week, "Destino": dest, "Base": 0.0, "Modificado": 0.0, "Diferencia": 0.0} for week in range(1, 53) for dest in core.SEVEN}
    for label, records in [("Base", base), ("Modificado", modified)]:
        for rec in records:
            if not (rec.get("_active_2034") or core.is_active_2034(rec)):
                continue
            week = int(core.to_number(rec.get("Semana")))
            if week < 1 or week > 52:
                continue
            for dest in core.SEVEN:
                agg[(week, dest)][label] += core.to_number(rec.get(dest))
    rows = []
    for week in range(1, 53):
        for dest in core.SEVEN:
            row = agg[(week, dest)]
            row["Diferencia"] = row["Modificado"] - row["Base"]
            rows.append(row)
    return rows


def build_conservation_day_dest(base, modified):
    agg = {}
    for label, records in [("Base", base), ("Modificado", modified)]:
        for rec in records:
            if not (rec.get("_active_2034") or core.is_active_2034(rec)):
                continue
            day = core.excel_date(core.to_number(rec.get("Fecha Liberación")))
            if day is None:
                continue
            key = day.isoformat()
            for dest in core.SEVEN:
                agg.setdefault((key, dest), {"Dia": key, "Destino": dest, "Base": 0.0, "Modificado": 0.0, "Diferencia": 0.0})
                agg[(key, dest)][label] += core.to_number(rec.get(dest))
    rows = []
    for key, dest in sorted(agg.keys()):
        row = agg[(key, dest)]
        row["Diferencia"] = row["Modificado"] - row["Base"]
        rows.append(row)
    return rows


def build_dashboard_dest_fast(base, modified):
    rows = []
    total_base = 0.0
    total_mod = 0.0
    for dest in core.SEVEN:
        base_v = 0.0
        mod_v = 0.0
        for rec in base:
            if core.is_active_2034(rec):
                base_v += core.to_number(rec.get(dest))
        for rec in modified:
            if rec.get("_active_2034") or core.is_active_2034(rec):
                mod_v += core.to_number(rec.get(dest))
        diff = mod_v - base_v
        rows.append([dest, base_v, mod_v, diff, "OK" if abs(diff) <= 1 else "Revisar"])
        total_base += base_v
        total_mod += mod_v
    total_diff = total_mod - total_base
    rows.append(["TOTAL 7 COLUMNAS", total_base, total_mod, total_diff, "OK" if abs(total_diff) <= 1 else "Revisar"])
    return rows


def build_waste_dest_detail(base, modified):
    agg = {}
    for label, records in [("Base", base), ("Modificado", modified)]:
        for rec in records:
            active = rec.get("_active_2034") or core.is_active_2034(rec)
            waste = rec.get("_waste_type") or core.infer_waste_type(rec)
            if not active or waste not in core.WASTE_TYPES:
                continue
            for dest in core.SEVEN:
                key = (dest, waste)
                if key not in agg:
                    agg[key] = {"Destino": dest, "Tipo": waste, "Base": 0.0, "Modificado": 0.0}
                agg[key][label] += core.to_number(rec.get(dest))
    rows = []
    for dest in core.SEVEN:
        for waste in core.WASTE_TYPES:
            row = agg.get((dest, waste), {"Destino": dest, "Tipo": waste, "Base": 0.0, "Modificado": 0.0})
            row["Diferencia"] = row["Modificado"] - row["Base"]
            rows.append(row)
    return rows


def build_formats(workbook):
    return {
        "title": workbook.add_format({"bold": True, "font_size": 14, "font_color": "#FFFFFF", "bg_color": "#1F4E78"}),
        "header": workbook.add_format({"bold": True, "font_color": "#FFFFFF", "bg_color": "#1F4E78", "border": 1, "text_wrap": True, "valign": "vcenter"}),
        "subheader": workbook.add_format({"bold": True, "font_color": "#FFFFFF", "bg_color": "#5B9BD5", "border": 1}),
        "note": workbook.add_format({"font_color": "#666666", "italic": True}),
        "number": workbook.add_format({"num_format": "#,##0.00"}),
        "integer": workbook.add_format({"num_format": "#,##0"}),
        "date_serial": workbook.add_format({"num_format": "yyyy-mm-dd"}),
        "ok": workbook.add_format({"font_color": "#006100", "bg_color": "#C6EFCE"}),
        "bad": workbook.add_format({"font_color": "#9C0006", "bg_color": "#FFC7CE"}),
    }


def build_dashboard_payload(preview):
    """Data the dashboard (Model\\app\\dashboard.html) draws for one circuit.
    Same keys the v19 Recharts page embedded, plus 'settings'. Day series are
    always included so the dashboard can switch Semanal/Diario."""
    return {
        "destinations": list(core.SEVEN),
        "baseMaterialWeekDest": preview["base_material_week_dest"],
        "materialWeekDest": preview["material_week_dest"],
        "movementWeekDest": preview["movement_week_dest"],
        "conservationTotal": [
            {
                "Destino": row[0],
                "Base": row[1],
                "Modificado": row[2],
                "Diferencia": row[3],
                "Estado": row[4],
            }
            for row in preview["dashboard_dest"]
        ],
        "conservationWeekDest": preview["conservation_week_dest"],
        "wasteDestDetail": preview["waste_dest_detail"],
        "summary": preview["summary"],
        "targets": preview["target_by_crusher"],
        "tolerances": preview.get("tolerance_by_crusher") or {},
        "granularity": preview.get("granularity", "semanal"),
        "dailyTargetMt": preview.get("daily_target_mt"),
        "dailyToleranceMt": preview.get("daily_tolerance_mt", 0.02),
        "baseMaterialDayDest": preview.get("base_material_day_dest") or [],
        "materialDayDest": preview.get("material_day_dest") or [],
        "conservationDayDest": preview.get("conservation_day_dest") or [],
        "circuit": preview.get("circuit") or "Desmonte",
        "chancadoras": preview.get("chancadoras") or list(preview["target_by_crusher"].keys()),
        "materialTypes": preview.get("material_types") or ["Wa", "Wb", "Wc", "Wh", "Wrell", "Wrip"],
        "settings": preview.get("settings") or {},
    }


def _safe_name(name):
    name = re.sub(r'[<>:"/\\|?*]+', "_", str(name or "").strip()).strip(". ")
    return name or "Sin titulo"


def write_results_files(output_path, scenario_name, circuits, meta):
    """Writes the run's results for the dashboard and for later comparisons:
      <carpeta de salida>\\<escenario> - Resultados.json   (read by the app)
      <carpeta de salida>\\<escenario> - Dashboard.html    (same dashboard, offline, to share)
    Named after the scenario (not the Excel) so runs of different scenarios
    never overwrite each other."""
    output_path = Path(output_path)
    folder = output_path.parent
    folder.mkdir(parents=True, exist_ok=True)
    stem = _safe_name(scenario_name)
    doc = {"tipo": "Material Shift - Resultados", "version": 1, "escenario": scenario_name or "Sin titulo", **meta, "circuitos": circuits}
    json_path = folder / f"{stem} - Resultados.json"
    text = json.dumps(doc, ensure_ascii=False, separators=(",", ":"))
    json_path.write_text(text, encoding="utf-8")
    html_path = None
    template = Path(__file__).resolve().parent / "dashboard.html"
    if template.exists():
        html = template.read_text(encoding="utf-8")
        embed = "<script>window.MS_EMBED=" + text.replace("</", "<\\/") + ";</script>"
        html = html.replace("<!--MS_EMBED-->", embed, 1)
        html_path = folder / f"{stem} - Dashboard.html"
        html_path.write_text(html, encoding="utf-8")
    return json_path, html_path


def write_validation_sheet(workbook, formats, total_rows, weekly_rows, row_summary, row_breaks, sheet_name="Validacion"):
    ws_val = workbook.add_worksheet(sheet_name)
    ws_val.write("A1", "Validacion de restricciones", formats["title"])
    ws_val.write_row("A3", ["Restriccion", "Resultado"], formats["header"])
    ws_val.write_row("A4", ["Total por destino en 52 semanas", "OK" if all(row[4] == "OK" for row in total_rows[:-1]) else "Revisar"])
    ws_val.write_row("A5", ["Total diario por fila", row_summary[-1][1]])
    ws_val.write_row("A6", ["Perfil semanal por chancador", "OK con brechas marcadas por semana" if any(r[5] != "OK" for r in weekly_rows) else "OK"])

    ws_val.write_row("A8", ["Destino", "Base", "Modificado", "Diferencia", "Estado"], formats["header"])
    for idx, row in enumerate(total_rows, 9):
        ws_val.write_row(idx - 1, 0, row)

    start = 11 + len(total_rows)
    ws_val.write_row(start - 1, 0, ["Semana", "Chancador", "Objetivo", "Modificado", "Diferencia", "Estado"], formats["header"])
    for i, row in enumerate(weekly_rows, start):
        ws_val.write_row(i, 0, row)

    row_start = start + len(weekly_rows) + 3
    ws_val.write_row(row_start, 0, ["Fila Excel", "Semana", "Poligono / Origen", "Base total 7", "Mod total 7", "Diferencia"], formats["header"])
    for i, row in enumerate(row_breaks, row_start + 1):
        ws_val.write_row(i, 0, row)

    ws_val.set_column("A:A", 28)
    ws_val.set_column("B:F", 16, formats["number"])
    ws_val.conditional_format(8, 4, 8 + len(total_rows), 4, {"type": "text", "criteria": "containing", "value": "OK", "format": formats["ok"]})
    ws_val.conditional_format(8, 4, 8 + len(total_rows), 4, {"type": "text", "criteria": "containing", "value": "Revisar", "format": formats["bad"]})
    ws_val.conditional_format(start, 5, start + len(weekly_rows), 5, {"type": "text", "criteria": "containing", "value": "OK", "format": formats["ok"]})
    ws_val.conditional_format(start, 5, start + len(weekly_rows), 5, {"type": "text", "criteria": "containing", "value": "Brecha", "format": formats["bad"]})
    ws_val.freeze_panes(8, 0)


def write_plan_modified_only(output_path, headers, modified):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    workbook = xlsxwriter.Workbook(output_path)
    workbook.set_properties({
        "title": "Plan Modificado",
        "comments": "Exportacion de una sola hoja con el Plan Modificado",
    })
    formats = build_formats(workbook)
    ws_mod = workbook.add_worksheet("Plan Modificado")
    core.write_sheet_table(
        ws_mod,
        headers,
        [r["_values"] for r in modified],
        formats,
        freeze=(1, 6),
        table_name="TablaPlanModificado",
    )
    core.set_plan_formats(ws_mod, headers, len(modified), formats)
    workbook.close()
    return output_path


def write_app_dashboard_sheet(workbook, formats, preview, sheet_name="Dashboard App", table_suffix=""):
    ws = workbook.add_worksheet(sheet_name)
    ws.hide_gridlines(2)
    ws.write("A1", "Dashboard operativo", formats["title"])
    ws.write("A2", "Tablas usadas por el ejecutable para revisar material, movimientos y conservacion.", formats["note"])

    material_headers = ["Semana"] + core.SEVEN + ["Total"]
    material_rows = [[row[h] for h in material_headers] for row in preview["material_week_dest"]]
    ws.write_row("A4", material_headers, formats["header"])
    for r, row in enumerate(material_rows, 5):
        ws.write_row(r - 1, 0, row)
    ws.add_table(3, 0, 55, len(material_headers) - 1, {
        "name": "TablaMaterialSemanaDestino" + table_suffix,
        "style": "Table Style Medium 2",
        "columns": [{"header": h} for h in material_headers],
    })
    ws.set_column("A:A", 9)
    ws.set_column("B:I", 14, formats["number"])

    move_headers = ["Semana", "Destino", "Entradas", "Salidas", "Neto"]
    move_start = 4
    move_col = 10
    ws.write_row(move_start - 1, move_col, move_headers, formats["header"])
    for i, row in enumerate(preview["movement_week_dest"], move_start + 1):
        ws.write_row(i - 1, move_col, [row[h] for h in move_headers])
    ws.add_table(move_start - 1, move_col, move_start + len(preview["movement_week_dest"]), move_col + len(move_headers) - 1, {
        "name": "TablaMovimientoSemanaDestino" + table_suffix,
        "style": "Table Style Medium 2",
        "columns": [{"header": h} for h in move_headers],
    })
    ws.set_column(move_col, move_col + len(move_headers) - 1, 14, formats["number"])

    cons_headers = ["Destino", "Base", "Modificado", "Diferencia", "Estado"]
    cons_start = 60
    ws.write_row(cons_start - 1, 0, cons_headers, formats["header"])
    for i, row in enumerate(preview["dashboard_dest"], cons_start + 1):
        ws.write_row(i - 1, 0, row)
    ws.add_table(cons_start - 1, 0, cons_start + len(preview["dashboard_dest"]), len(cons_headers) - 1, {
        "name": "TablaConservacionDestinoApp" + table_suffix,
        "style": "Table Style Medium 2",
        "columns": [{"header": h} for h in cons_headers],
    })
    ws.freeze_panes(4, 1)


def run_model(
    input_path,
    output_path,
    sheet_name="Plan_Base",
    target_mode="objetivo_fijo",
    target_mt=1.18,
    tolerance_mt=0.05,
    full_workbook=True,
    write_dashboard=True,
    export_plan=True,
    donor_priority=None,
    phase_priority=None,
    granularity="semanal",
    daily_target_mt=None,
    daily_tolerance_mt=0.02,
    donantes_override=None,
    active_year=None,
    material_blocked=None,
    plan_output_exact=False,
    circuit="Desmonte",
    preloaded=None,
    workbook=None,
    destino_config=None,
):
    """Computes and writes one circuit's full output ("Mineral" or
    "Desmonte"). Same global-swap technique as calculate_preview() -- see its
    docstring -- so this stays a thin wrapper around the existing, proven
    Excel-writing code instead of a rewrite.

    workbook: an already-open xlsxwriter.Workbook to write this circuit's
    sheets into (used by run_model_both() to put both circuits in one file);
    this function only closes it when IT opened it (workbook=None). Sheet
    names get a " <circuit>" suffix for any circuit other than "Desmonte", so
    both circuits' sheets can coexist without colliding.

    destino_config: see calculate_preview()'s docstring -- ignored when
    preloaded is given (the caller already applied it once up front).

    Returns None if this file has no such circuit configured."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if preloaded is not None:
        headers, base = preloaded
    else:
        headers, base = core.load_plan_base(Path(input_path), sheet_name)
        if destino_config is not None:
            core.apply_destino_config_override(headers, destino_config)

    resolved = core.resolve_circuit(circuit, headers)
    if resolved is None:
        return None
    chancadoras, donors, materials = resolved
    if donantes_override is not None and not core.CONFIG_SHEET_USED:
        donors = list(donantes_override)

    suffix = "" if circuit == "Desmonte" else f" {circuit}"
    # add_dashboard()/build_dashboard_rows() hardcode a weekly chart laid out
    # for exactly "Chw2a_1"/"Chw2a_2" -- only safe to call for a circuit that
    # actually has those two chancadoras. Any other circuit (Mineral, or a
    # future Desmonte with different/more crushers) still gets every other
    # sheet, just without that specific chart.
    can_chart = list(chancadoras) == ["Chw2a_1", "Chw2a_2"]

    saved_globals = (core.CHANCADORES, core.DONORS, core.WASTE_TYPES, core.SEVEN)
    core.CHANCADORES, core.DONORS, core.WASTE_TYPES = chancadoras, donors, materials
    core.SEVEN = core.CHANCADORES + core.DONORS
    try:
        modified, moves, weekly_status, target_by_crusher, _, tolerance_by_crusher = core.adjust_plan(
            headers,
            base,
            target_mode=target_mode,
            requested_week_chw=target_mt * 1_000_000.0,
            tolerance_abs=tolerance_mt * 1_000_000.0,
            donor_priority=donor_priority,
            phase_priority=phase_priority,
            active_year=active_year,
            material_blocked=material_blocked,
        )
        daily_moves = []
        daily_status = []
        if granularity == "diario":
            daily_moves, daily_status = core.refine_daily(
                modified, headers, target_by_crusher, daily_tolerance_mt * 1_000_000.0,
                donor_priority=donor_priority, phase_priority=phase_priority,
                daily_target_abs=daily_target_mt * 1_000_000.0 if daily_target_mt is not None else None,
                material_blocked=material_blocked,
            )
        total_rows, weekly_rows, row_summary, row_breaks = core.build_validations(base, modified, target_by_crusher, tolerance_by_crusher)
        row_material_balance = core.check_row_material_balance(modified)
        matrix_check = core.check_material_matrix(base, modified, material_blocked)
        dashboard_dest = build_dashboard_dest_fast(base, modified)
        brechas_diarias = sum(1 for r in daily_status if r[5] != "OK")
        export_preview = {
            "base_material_week_dest": build_material_week_dest(base),
            "material_week_dest": build_material_week_dest(modified),
            # Always built (not only in "diario" mode) so the dashboard can
            # switch between weekly and daily views of any run.
            "base_material_day_dest": build_material_day_dest(base),
            "material_day_dest": build_material_day_dest(modified),
            "conservation_day_dest": build_conservation_day_dest(base, modified),
            "movement_week_dest": build_movement_week_dest(moves),
            "dashboard_dest": dashboard_dest,
            "conservation_week_dest": build_conservation_week_dest(base, modified),
            "waste_dest_detail": build_waste_dest_detail(base, modified),
            "row_material_balance": row_material_balance,
            "summary": {
                "movimientos": len(moves) + len(daily_moves),
                "brechas": sum(1 for r in weekly_rows if r[5] != "OK"),
                "brechas_diarias": brechas_diarias,
                "row_breaks": len(row_breaks),
                "destinos_ok": all(row[4] == "OK" for row in total_rows[:-1]),
                "balance_material_ok": row_material_balance["ok"],
                "balance_material_bad_rows": len(row_material_balance["bad_rows"]),
                "balance_material_max_dev_pct": row_material_balance["max_dev_pct"],
                "matriz_ok": matrix_check["ok"],
                "matriz_violaciones": len(matrix_check["violations"]),
                "lp_ok": core.LAST_LP["success"],
            },
            "target_by_crusher": target_by_crusher,
            "tolerance_by_crusher": tolerance_by_crusher,
            "granularity": granularity,
            "daily_target_mt": daily_target_mt,
            "daily_tolerance_mt": daily_tolerance_mt,
            # Lets the Recharts dashboard show the right circuit name, crusher
            # list and material-type list instead of the Desmonte-only values
            # it used to hardcode (Chw2a_1/Chw2a_2, Wa/Wb/Wc/Wh/Wrell/Wrip) --
            # those broke Mineral's dashboard (empty charts, "Obj. Chw2a_1"
            # showing 0, "Desmonte total por tipo" always empty).
            "circuit": circuit,
            "chancadoras": list(chancadoras),
            "material_types": list(materials),
            "settings": {
                "modo": target_mode,
                "objetivo_mt": target_mt,
                "tolerancia_mt": tolerance_mt,
                "granularidad": granularity,
                "objetivo_diario_mt": daily_target_mt,
                "tolerancia_diaria_mt": daily_tolerance_mt,
                "donantes": list(donors),
            },
        }
        dashboard_payload = build_dashboard_payload(export_preview) if write_dashboard else None

        # The Excel the user asked for keeps EXACTLY the name they chose (no
        # " - Solo Plan Modificado" suffix) when it is the plan-only export.
        plan_modified_only = output_path if plan_output_exact else output_path.with_name(output_path.stem + f" - Solo Plan Modificado{suffix}.xlsx")
        if export_plan:
            write_plan_modified_only(plan_modified_only, headers, modified)

        owns_workbook = workbook is None
        if full_workbook:
            pivot_rows = core.build_pivot_like(modified)
            if workbook is None:
                workbook = xlsxwriter.Workbook(output_path)
                workbook.set_properties({"title": "Modelo de Reasignación de Materiales", "comments": "Redistribucion de material hacia los destinos receptores"})
            formats = build_formats(workbook)

            if can_chart:
                core.add_dashboard(
                    workbook,
                    formats,
                    base,
                    modified,
                    target_by_crusher,
                    target_mt * 1_000_000.0,
                    tolerance_mt * 1_000_000.0,
                )
            write_app_dashboard_sheet(workbook, formats, export_preview, sheet_name="Dashboard App" + suffix, table_suffix=suffix.replace(" ", ""))

            ws_base = workbook.add_worksheet("Plan Base" + suffix)
            core.write_sheet_table(ws_base, headers, [r["_values"] for r in base], formats, freeze=(1, 6), table_name="TablaPlanBase" + suffix.replace(" ", ""))
            core.set_plan_formats(ws_base, headers, len(base), formats)

            ws_mod = workbook.add_worksheet("Plan Modificado" + suffix)
            core.write_sheet_table(ws_mod, headers, [r["_values"] for r in modified], formats, freeze=(1, 6), table_name="TablaPlanModificado" + suffix.replace(" ", ""))
            core.set_plan_formats(ws_mod, headers, len(modified), formats)

            write_validation_sheet(workbook, formats, total_rows, weekly_rows, row_summary, row_breaks, sheet_name="Validacion" + suffix)

            ws_res = workbook.add_worksheet(f"Resumen {circuit}")
            core.write_sheet_table(ws_res, ["Semana", "Destino", "Tipo Material", "Tonelaje"], pivot_rows, formats, table_name="TablaResumen" + circuit)
            ws_res.set_column("A:A", 10)
            ws_res.set_column("B:C", 16)
            ws_res.set_column("D:D", 16, formats["number"])

            ws_moves = workbook.add_worksheet("Movimientos" + suffix)
            core.write_sheet_table(ws_moves, ["Semana", "Fila Excel", "Fase", "Cota", "Poligono / Origen", "Tipo Material", "Desde", "Hacia", "Tonelaje Movido"], moves, formats, table_name="TablaMovimientos" + suffix.replace(" ", ""))
            ws_moves.set_column("A:B", 10)
            ws_moves.set_column("C:H", 18)
            ws_moves.set_column("I:I", 16, formats["number"])

            ws_params = workbook.add_worksheet("Parametros" + suffix)
            params = [
                ["Parametro", "Valor"],
                ["Circuito", circuit],
                ["Archivo fuente", str(input_path)],
                ["Hoja fuente", sheet_name],
                ["Modo objetivo", target_mode],
                ["Objetivo solicitado Mt/semana/chancador", target_mt],
                ["Tolerancia Mt/semana/chancador", tolerance_mt],
                ["Conserva total por destino", "Si"],
                ["Conserva total diario por fila", "Si"],
                ["Donantes permitidos", ", ".join(core.DONORS)],
                ["Chancadoras (receptores)", ", ".join(core.CHANCADORES)],
            ]
            for crusher in core.CHANCADORES:
                params.append([f"Objetivo efectivo {crusher} t/semana", target_by_crusher[crusher]])
            core.write_sheet_table(ws_params, params[0], params[1:], formats, table_name="TablaParametros" + suffix.replace(" ", ""))
            ws_params.set_column("A:A", 42)
            ws_params.set_column("B:B", 90)
            if owns_workbook:
                workbook.close()

        result = {
            "circuit": circuit,
            "chancadoras": list(chancadoras),
            "donantes": list(donors),
            "output": str(output_path),
            "plan_modified_output": str(plan_modified_only),
            "movimientos": len(moves) + len(daily_moves),
            "brechas": sum(1 for r in weekly_rows if r[5] != "OK"),
            "brechas_diarias": brechas_diarias,
            "row_breaks": len(row_breaks),
            "destinos_ok": all(row[4] == "OK" for row in total_rows[:-1]),
            "target_por_chancadora": dict(target_by_crusher),
            "granularity": granularity,
            "dashboard": dashboard_payload,
            "balance_material_ok": export_preview["summary"]["balance_material_ok"],
            "matriz_ok": export_preview["summary"]["matriz_ok"],
            "modified": modified,
            "headers": headers,
        }
        # Backward-compatible keys for the one shape this ever had before
        # circuits existed: exactly Chw2a_1/Chw2a_2.
        if "Chw2a_1" in target_by_crusher:
            result["target_chw2a_1"] = target_by_crusher["Chw2a_1"]
        if "Chw2a_2" in target_by_crusher:
            result["target_chw2a_2"] = target_by_crusher["Chw2a_2"]
        return result
    finally:
        core.CHANCADORES, core.DONORS, core.WASTE_TYPES, core.SEVEN = saved_globals


def _merge_modified(headers, base, circuit_results):
    """Combines several circuits' 'modified' record lists (each a full copy
    of every row, but with only that circuit's own destino columns changed)
    into ONE plan: for every row, takes each circuit's own destino columns
    from its result and everything else from the base plan. Circuits never
    share a destino column (Config_Materiales tags each column for exactly
    one circuit), so this is a straightforward column-wise overlay, not a
    numeric merge."""
    col_pos = {name: i for i, name in enumerate(headers)}
    merged = [dict(rec) for rec in base]
    for rec in merged:
        rec["_values"] = list(rec["_values"])
    for result in circuit_results:
        if result is None:
            continue
        owned_cols = set(result.get("chancadoras", [])) | set(result.get("donantes", []))
        for dst, src in zip(merged, result["modified"]):
            for col in owned_cols:
                dst[col] = src.get(col)
                if col in col_pos:
                    dst["_values"][col_pos[col]] = src.get(col)
    return merged


def run_model_both(
    input_path,
    output_path,
    sheet_name="Plan_Base",
    donantes_override=None,
    active_year=None,
    destino_config=None,
    mineral_donor_priority=None,
    mineral_phase_priority=None,
    mineral_target_mt=None,
    mineral_tolerance_mt=None,
    mineral_target_mode=None,
    mineral_granularity=None,
    mineral_daily_target_mt=None,
    mineral_daily_tolerance_mt=None,
    scenario_name=None,
    export_plan=True,
    plan_output_exact=False,
    **kwargs,
):
    """Entry point for one 'Calcular' / 'Excel' click: runs Desmonte (always)
    and Mineral (only if configured via the 'Config' sheet or destino_config).

    Each circuit has its own criteria: the mineral_* arguments override, for
    Mineral only, the shared ones in kwargs (target_mode, target_mt,
    tolerance_mt, granularity, daily_target_mt, daily_tolerance_mt). Left as
    None they fall back to the shared value (v19 behaviour).

    - full_workbook: writes the full report (Dashboard App, Plan Base/Modificado,
      Validacion, Resumen, Movimientos, Parametros) at output_path.
    - export_plan: writes the merged Plan Modificado (both circuits). With
      plan_output_exact it goes EXACTLY at output_path (the 'Excel' button);
      otherwise as '<output> - Solo Plan Modificado.xlsx'.
    - write_dashboard: writes '<escenario> - Resultados.json' + 'Dashboard.html'."""
    for reserved in ("circuit", "preloaded", "workbook", "plan_output_exact"):
        kwargs.pop(reserved, None)
    full_workbook = kwargs.get("full_workbook", True)
    write_dashboard = kwargs.get("write_dashboard", True)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    headers, base = core.load_plan_base(Path(input_path), sheet_name)
    if destino_config is not None:
        core.apply_destino_config_override(headers, destino_config)
    preloaded = (headers, base)

    workbook = None
    if full_workbook:
        workbook = xlsxwriter.Workbook(output_path)
        workbook.set_properties({"title": "Material Shift", "comments": "Redistribucion de material hacia los destinos receptores"})
    try:
        desmonte_result = run_model(
            input_path, output_path, sheet_name,
            preloaded=preloaded, workbook=workbook, export_plan=False,
            circuit="Desmonte", donantes_override=donantes_override, active_year=active_year,
            **kwargs,
        )
        mineral_result = None
        if core.CONFIG_SHEET_USED and core.resolve_circuit("Mineral", headers) is not None:
            mineral_kwargs = dict(kwargs)
            mineral_kwargs["donor_priority"] = mineral_donor_priority
            mineral_kwargs["phase_priority"] = mineral_phase_priority
            for key, value in (
                ("target_mt", mineral_target_mt),
                ("tolerance_mt", mineral_tolerance_mt),
                ("target_mode", mineral_target_mode),
                ("granularity", mineral_granularity),
                ("daily_target_mt", mineral_daily_target_mt),
                ("daily_tolerance_mt", mineral_daily_tolerance_mt),
            ):
                if value is not None:
                    mineral_kwargs[key] = value
            mineral_result = run_model(
                input_path, output_path, sheet_name,
                preloaded=preloaded, workbook=workbook, export_plan=False,
                circuit="Mineral", active_year=active_year,
                **mineral_kwargs,
            )
    finally:
        if workbook is not None:
            workbook.close()

    plan_modified_only = None
    if export_plan:
        plan_modified_only = output_path if plan_output_exact else output_path.with_name(output_path.stem + " - Solo Plan Modificado.xlsx")
        merged_modified = _merge_modified(headers, base, [desmonte_result, mineral_result])
        write_plan_modified_only(plan_modified_only, headers, merged_modified)

    results_json = dashboard_html = None
    if write_dashboard:
        circuits = {}
        for name, res in (("Desmonte", desmonte_result), ("Mineral", mineral_result)):
            if res is not None and res.get("dashboard") is not None:
                circuits[name] = res["dashboard"]
        meta = {
            "fecha": dt.datetime.now().strftime("%d/%m/%Y %H:%M"),
            "archivo_base": str(input_path),
            "hoja": sheet_name,
            "anio_activo": active_year if active_year is not None else core.ACTIVE_YEAR,
        }
        results_json, dashboard_html = write_results_files(output_path, scenario_name, circuits, meta)

    return {
        "Desmonte": desmonte_result,
        "Mineral": mineral_result,
        "output": str(output_path),
        "plan_modified_output": str(plan_modified_only) if plan_modified_only else None,
        "results_json": str(results_json) if results_json else None,
        "dashboard_html": str(dashboard_html) if dashboard_html else None,
    }


def default_destino_config_full(headers, candidatos):
    """Like core.default_destino_config(), but covers every candidate column
    (including the Botadero-named ones today's auto-detection excludes), so
    the app's editor has a N/A starting row for literally everything the
    user might want to turn into a Receptor/Donante of either circuit."""
    out = core.default_destino_config(headers)
    for h in candidatos:
        out.setdefault(h, {"destino": "N/A", "material": "N/A"})
    return out


def _strip_heavy(result):
    """Drops the large per-row fields (modified/headers) from a run_model()
    result before it goes into a CLI JSON print -- those are already on disk
    in the Excel this call just wrote."""
    if result is None:
        return None
    return {k: v for k, v in result.items() if k not in ("modified", "headers", "dashboard")}


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Material Shift - motor de reasignacion de materiales.")
    parser.add_argument("--nogui", action="store_true", help="Ejecuta sin interfaz grafica.")
    parser.add_argument("--input", default=DEFAULT_INPUT)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--sheet", default="Plan_Base")
    parser.add_argument("--target-mode", choices=["objetivo_fijo", "balanceado", "objetivo_solicitado"], default="objetivo_fijo")
    parser.add_argument("--target-mt", type=float, default=1.18)
    parser.add_argument("--tolerance-mt", type=float, default=0.05)
    parser.add_argument("--lite-excel", action="store_true", help="Genera solo el dashboard HTML y el Excel de una hoja Plan Modificado.")
    parser.add_argument("--dashboard-only", action="store_true", help="Genera solo el dashboard HTML, sin escribir Excel.")
    parser.add_argument("--excel-only", action="store_true", help="Genera solo el Excel de una hoja Plan Modificado, sin reescribir dashboard.")
    parser.add_argument("--donor-priority", default=None, help="JSON {crusher: [ids ordenados]} para priorizar donantes por chancadora (circuito Desmonte).")
    parser.add_argument("--phase-priority", default=None, help="JSON {crusher: [fases ordenadas]} para priorizar fases por chancadora (circuito Desmonte).")
    parser.add_argument("--mineral-donor-priority", default=None, help="JSON [ids ordenados] -- prioridad de donantes del circuito Mineral (misma orden para todas sus chancadoras).")
    parser.add_argument("--mineral-phase-priority", default=None, help="JSON [fases ordenadas] -- prioridad de fases del circuito Mineral.")
    parser.add_argument("--mineral-target-mt", type=float, default=None, help="Objetivo semanal del circuito Mineral, en Mt. Si se omite, usa el mismo objetivo que Desmonte (--target-mt).")
    parser.add_argument("--mineral-tolerance-mt", type=float, default=None, help="Tolerancia semanal del circuito Mineral, en Mt. Si se omite, usa la misma que Desmonte.")
    parser.add_argument("--granularity", choices=["semanal", "diario"], default="semanal", help="Semanal (por defecto) o diario (refina dentro de cada semana por dia).")
    parser.add_argument("--daily-target-mt", type=float, default=None, help="Objetivo diario independiente en Mt/dia; si se omite usa objetivo semanal / dias de la semana.")
    parser.add_argument("--daily-tolerance-mt", type=float, default=0.02, help="Banda aceptable diaria en Mt, solo aplica con --granularity diario.")
    parser.add_argument("--list-columns", action="store_true", help="Solo detecta chancadoras/donantes del Excel (por nombre/posicion) y los imprime como JSON, sin calcular.")
    parser.add_argument("--donantes-override", default=None, help="JSON con la lista de nombres de columna a usar como donantes/destinos, reemplazando la deteccion automatica. Ignorado si se pasa --destino-config.")
    parser.add_argument("--material-matrix", default=None, help="JSON {destino: [materiales bloqueados]} -- tabla de permisos destino x material.")
    parser.add_argument("--active-year", type=int, default=None, help="Anio activo del plan (filtra 'Fecha Liberacion'). Si se omite usa 2034.")
    parser.add_argument("--destino-config", default=None, help="JSON {destino: {\"destino\": \"Receptor\"|\"Donante\"|\"N/A\", \"material\": \"Mineral\"|\"Desmonte\"|\"N/A\"}} -- reemplaza la hoja 'Config' del Excel (o la deteccion por nombre) con la configuracion editada en la app.")
    parser.add_argument("--mineral-target-mode", choices=["objetivo_fijo", "balanceado"], default=None, help="Modo del circuito Mineral. Si se omite, usa --target-mode.")
    parser.add_argument("--mineral-granularity", choices=["semanal", "diario"], default=None, help="Granularidad del circuito Mineral. Si se omite, usa --granularity.")
    parser.add_argument("--mineral-daily-target-mt", type=float, default=None, help="Objetivo diario del circuito Mineral (Mt/dia).")
    parser.add_argument("--mineral-daily-tolerance-mt", type=float, default=None, help="Tolerancia diaria del circuito Mineral (Mt).")
    parser.add_argument("--scenario-name", default=None, help="Nombre del escenario (rotula los resultados y el dashboard).")
    parser.add_argument("--cache-dir", default=None, help="Carpeta para la cache de lectura del Excel.")
    parser.add_argument("--full-report", action="store_true", help="Escribe solo el reporte Excel completo (Dashboard App, Plan Base/Modificado, Validacion, Resumen, Movimientos, Parametros).")
    parser.add_argument("--pptx-chart", default=None, help="JSON con uno o varios graficos: crea un .pptx con graficos nativos editables en --output.")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.cache_dir:
        core.CACHE_DIR = args.cache_dir
    if args.pptx_chart:
        import exportar_ppt
        spec = json.loads(Path(args.pptx_chart).read_text(encoding="utf-8"))
        print("PPTX_RESULT:" + json.dumps({"output": str(exportar_ppt.crear_pptx(spec, args.output))}, ensure_ascii=False))
        return
    if not args.nogui:
        raise SystemExit("Material Shift se usa desde 'Material Shift.exe' (este motor no tiene interfaz propia).")
    destino_config = json.loads(args.destino_config) if args.destino_config else None
    if args.list_columns:
        hojas = core.list_sheets(Path(args.input))
        if args.sheet not in hojas:
            print("COLUMNS_RESULT:" + json.dumps({"error": f"La hoja '{args.sheet}' no existe en el archivo.", "hojas": hojas}, ensure_ascii=False))
            return
        headers, _base = core.load_plan_base(Path(args.input), args.sheet)
        if destino_config is not None:
            core.apply_destino_config_override(headers, destino_config)
        # Full pre-filter candidate range: the whole destino block, from right
        # after "Total Material (t)" to the first material-type column. Wider
        # than detect_destinations()'s Desmonte-only range (which starts
        # after the chancadoras) because a Config sheet can tag destinos that
        # sit BEFORE the chancadoras too (e.g. Mineral's Ore1/Area Stock N
        # columns, which come before Chw2a_1/2 on a real file) -- includes
        # Botadero-named columns too, which detect_destinations() excludes.
        boundary_names = set(core.ORE_TYPES) | set(core.WASTE_TYPES)
        boundary_idx = [i for i, h in enumerate(headers) if h in boundary_names]
        end = min(boundary_idx) if boundary_idx else len(headers)
        total_idx = [i for i, h in enumerate(headers) if h == "Total Material (t)"]
        start = (total_idx[0] + 1) if total_idx else 0
        candidatos = [h for h in headers[start:end] if h and h not in core.CHANCADORES]
        # Per-destino Config_Destinos/Config_Materiales for ALL candidates
        # (chancadoras + candidatos), so the app's editor always has a
        # starting value even on a file with no 'Config' sheet yet.
        if core.CONFIG_SHEET_USED:
            circuitos = {
                h: {"destino": core.DESTINO_ROLE.get(h, "N/A"), "material": core.CIRCUIT_OF.get(h, "N/A")}
                for h in core.CHANCADORES + candidatos
            }
        else:
            circuitos = default_destino_config_full(headers, candidatos)
        # "chancadoras"/"donantes" below are Desmonte-specific (not the raw,
        # all-circuits-combined core.CHANCADORES/DONORS a Config sheet
        # produces) -- the Prioridad tab and its donor/phase priority only
        # ever apply to Desmonte today, so they must stay scoped to it
        # regardless of how many other circuits this file configures.
        desmonte_resolved = core.resolve_circuit("Desmonte", headers)
        mineral_resolved = core.resolve_circuit("Mineral", headers)
        desmonte_chancadoras = desmonte_resolved[0] if desmonte_resolved else []
        desmonte_donantes = desmonte_resolved[1] if desmonte_resolved else []
        print("COLUMNS_RESULT:" + json.dumps({
            "chancadoras": desmonte_chancadoras,
            "donantes": desmonte_donantes,
            "candidatos": candidatos,
            "anio_sugerido": core.detect_active_year(_base),
            "fases": core.detect_phases(_base),
            "materiales": desmonte_resolved[2] if desmonte_resolved else core.detect_materials(headers),
            "bloqueos_default": {d: sorted(v) for d, v in core.default_material_blocked(desmonte_chancadoras + desmonte_donantes).items()},
            "config_sheet_used": core.CONFIG_SHEET_USED,
            "circuitos": circuitos,
            "desmonte_disponible": desmonte_resolved is not None,
            "mineral_disponible": mineral_resolved is not None,
            "mineral_chancadoras": mineral_resolved[0] if mineral_resolved else [],
            "mineral_donantes": mineral_resolved[1] if mineral_resolved else [],
            "mineral_materiales": mineral_resolved[2] if mineral_resolved else [],
            "bloqueos_default_mineral": {d: sorted(v) for d, v in core.default_material_blocked((mineral_resolved[0] + mineral_resolved[1]) if mineral_resolved else []).items()},
            "hojas": hojas,
        }, ensure_ascii=False))
        return
    donor_priority = json.loads(args.donor_priority) if args.donor_priority else None
    phase_priority = json.loads(args.phase_priority) if args.phase_priority else None
    mineral_donor_priority = json.loads(args.mineral_donor_priority) if args.mineral_donor_priority else None
    mineral_phase_priority = json.loads(args.mineral_phase_priority) if args.mineral_phase_priority else None
    donantes_override = json.loads(args.donantes_override) if args.donantes_override else None
    material_blocked = json.loads(args.material_matrix) if args.material_matrix else None
    result = run_model_both(
        args.input,
        args.output,
        args.sheet,
        target_mode=args.target_mode,
        target_mt=args.target_mt,
        tolerance_mt=args.tolerance_mt,
        full_workbook=not (args.lite_excel or args.dashboard_only or args.excel_only),
        write_dashboard=not (args.excel_only or args.full_report),
        export_plan=not (args.dashboard_only or args.full_report),
        donor_priority=donor_priority,
        phase_priority=phase_priority,
        granularity=args.granularity,
        daily_target_mt=args.daily_target_mt,
        daily_tolerance_mt=args.daily_tolerance_mt,
        donantes_override=donantes_override,
        active_year=args.active_year,
        material_blocked=material_blocked,
        plan_output_exact=args.excel_only,
        destino_config=destino_config,
        mineral_donor_priority=mineral_donor_priority,
        mineral_phase_priority=mineral_phase_priority,
        mineral_target_mt=args.mineral_target_mt,
        mineral_tolerance_mt=args.mineral_tolerance_mt,
        mineral_target_mode=args.mineral_target_mode,
        mineral_granularity=args.mineral_granularity,
        mineral_daily_target_mt=args.mineral_daily_target_mt,
        mineral_daily_tolerance_mt=args.mineral_daily_tolerance_mt,
        scenario_name=args.scenario_name,
    )
    print("MODEL_RESULT:" + json.dumps({
        "output": result["output"],
        "plan_modified_output": result["plan_modified_output"],
        "results_json": result["results_json"],
        "dashboard_html": result["dashboard_html"],
        "Desmonte": _strip_heavy(result["Desmonte"]),
        "Mineral": _strip_heavy(result["Mineral"]),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
