import datetime as dt
import argparse
import re
import unicodedata
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix

try:
    import xlsxwriter
except ImportError as exc:
    raise SystemExit("Falta xlsxwriter en el runtime de Python.") from exc


INPUT = Path(r"D:\Descargas\Ajuste Plan 2034.xlsx")
OUTPUT_DIR = Path(r"C:\Users\Sebastian\Desktop\Antamina 2026\outputs\ajuste_plan_2034")
OUTPUT = OUTPUT_DIR / "Ajuste Plan 2034 - Resultado.xlsx"
DEFAULT_SHEET = "Plan_Base"

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

REQUESTED_WEEK_CHW = 1_180_000.0
LAST_LP = {"success": True, "message": ""}
ACTIVE_YEAR = 2034
CHANCADORES = ["Chw2a_1", "Chw2a_2"]
# name -> "Mineral" / "Desmonte" / "N/A", populated from an optional "Config"
# sheet (see read_config_sheet()). Empty when the workbook has no such sheet
# -- callers then fall back to the ORE_TYPES/WASTE_TYPES boundary heuristic.
CIRCUIT_OF = {}
# name -> "Receptor" / "Donante" / "N/A", populated alongside CIRCUIT_OF from
# the same Config sheet row (see read_config_sheet()).
DESTINO_ROLE = {}
CONFIG_SHEET_USED = False
DONORS = ["E10_1", "DiqueN_1", "E9_3", "E9_4", "E9_5", "N2_1", "N2_2", "N2_3"]
# N2_1/N2_2/N2_3 (Tucush) behave exactly like the other donors -- they trade
# tonnage directly with a crusher, configurable in the same priority lists --
# except they never carry Wa material (see TUCUSH_DONORS below). This is kept
# as an explicit, documented exception (by name) even though CHANCADORES and
# DONORS themselves are now detected automatically from the sheet -- see
# detect_destinations().
TUCUSH_DONORS = {"N2_1", "N2_2", "N2_3", "N3_7"}
SEVEN = ["Chw2a_1", "Chw2a_2", "DiqueN_1", "E10_1", "E9_3", "E9_4", "E9_5", "N2_1", "N2_2", "N2_3"]
WASTE_TYPES = ["Wa", "Wb", "Wc", "Wh", "Wrell", "Wrip"]
# Ore-type columns (M1/M2/M2a/M2at/M4b/M4bt/M5/M6) sit right after the last
# Botadero column and before Wa -- not used as donors/crushers today, but
# they mark where the destino/donante block ends on the sheet (see
# detect_destinations()).
ORE_TYPES = ["M1", "M2", "M2a", "M2at", "M4b", "M4bt", "M5", "M6"]
PHASE_PRIORITY = {"PHASE 10": 0, "PHASE 11": 1, "PHASE 12": 2, "PHASE 13": 3, "PHASE 14": 4}
DONOR_PRIORITY = {"E10_1": 0, "DiqueN_1": 1, "E9_3": 2, "E9_4": 3, "E9_5": 4, "N2_1": 5, "N2_2": 6, "N2_3": 7}


def colnum(col):
    n = 0
    for ch in col:
        n = n * 26 + ord(ch) - 64
    return n


def colname(n):
    out = ""
    while n:
        n, rem = divmod(n - 1, 26)
        out = chr(65 + rem) + out
    return out


def split_ref(ref):
    # Hand-rolled instead of a regex match + a separate colnum() call --
    # this runs once per cell (roughly a million times for the full sheet),
    # so avoiding the regex engine and a second function call adds up.
    i = 0
    n = 0
    length = len(ref)
    while i < length:
        ch = ref[i]
        if ch < "A" or ch > "Z":
            break
        n = n * 26 + (ord(ch) - 64)
        i += 1
    return n, int(ref[i:])


def text(el):
    return None if el is None else "".join(el.itertext())


def to_number(value):
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def clean_value(value):
    if value is None:
        return None
    if isinstance(value, str):
        s = value.strip()
        if s == "":
            return None
        try:
            n = float(s)
            if abs(n - round(n)) < 1e-9 and abs(n) < 10**12:
                return int(round(n))
            return n
        except ValueError:
            return value
    return value


def excel_date(serial):
    if serial is None or serial <= 0:
        return None
    return (dt.datetime(1899, 12, 30) + dt.timedelta(days=serial)).date()


def _norm_text(s):
    """Accent/case-insensitive normalization, used to match Config sheet
    header names and dropdown values regardless of how they were typed."""
    s = str(s or "").strip().lower()
    return "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch))


def _find_sheet_path(zf, sheet_name):
    wb = ET.fromstring(zf.read("xl/workbook.xml"))
    rels_root = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    rels = {r.attrib["Id"]: r.attrib["Target"] for r in rels_root}
    matches = [
        s.attrib.get(REL + "id")
        for s in wb.findall(NS + "sheets/" + NS + "sheet")
        if _norm_text(s.attrib.get("name")) == _norm_text(sheet_name)
    ]
    if not matches:
        return None
    sheet_path = rels[matches[0]].lstrip("/")
    if not sheet_path.startswith("xl/"):
        sheet_path = "xl/" + sheet_path
    return sheet_path


def _read_shared_strings(zf):
    shared = []
    if "xl/sharedStrings.xml" in zf.namelist():
        for _, elem in ET.iterparse(zf.open("xl/sharedStrings.xml"), events=("end",)):
            if elem.tag == NS + "si":
                shared.append("".join(elem.itertext()))
                elem.clear()
    return shared


def _read_sheet_grid(zf, sheet_path, shared):
    """Generic reader for a small sheet: returns {row_num: {col_num: value}}.
    Unlike load_plan_base's reader this isn't optimized for a million rows --
    the Config sheet is expected to have one row per destino column."""
    rows = {}
    for _, elem in ET.iterparse(zf.open(sheet_path), events=("end",)):
        if elem.tag == NS + "row":
            r = int(elem.attrib["r"])
            row = {}
            for c in elem.findall(NS + "c"):
                ci, _ = split_ref(c.attrib["r"])
                cell_type = c.attrib.get("t")
                v_text = None
                is_text = None
                for child in c:
                    if child.tag == NS + "v":
                        v_text = "".join(child.itertext())
                    elif child.tag == NS + "is":
                        is_text = "".join(child.itertext())
                value = None
                if v_text is not None:
                    value = shared[int(v_text)] if cell_type == "s" else v_text
                elif cell_type == "inlineStr":
                    value = is_text
                row[ci] = clean_value(value)
            rows[r] = row
            elem.clear()
    return rows


def read_config_sheet(input_path):
    """Reads an optional 'Config' sheet that declares, per destino column:
      - Config_Destinos: Receptor / Donante / N/A
      - Config_Materiales: Mineral / Desmonte / N/A
    Column headers and dropdown values are matched accent/case-insensitively,
    in any column order, as long as a 'Columna' (or 'Destino'/'Nombre') column
    names the destino. Returns {name: {"destino": ..., "material": ...}}, or
    None if the workbook has no 'Config' sheet (caller falls back to the old
    name-based detection for full backward compatibility)."""
    with zipfile.ZipFile(input_path) as zf:
        sheet_path = _find_sheet_path(zf, "Config")
        if sheet_path is None:
            return None
        shared = _read_shared_strings(zf)
        rows = _read_sheet_grid(zf, sheet_path, shared)

    if not rows:
        return {}

    header_row_num = min(rows)
    header = rows[header_row_num]
    max_col = max(header) if header else 0

    col_name = col_destino = col_material = None
    for ci in range(1, max_col + 1):
        h = _norm_text(header.get(ci))
        if h in ("columna", "destino", "nombre"):
            col_name = ci
        elif "config_destino" in h or h == "destinos":
            col_destino = ci
        elif "config_material" in h or h == "materiales":
            col_material = ci
    if col_name is None:
        return {}

    result = {}
    for r in sorted(rows):
        if r == header_row_num:
            continue
        row = rows[r]
        name = row.get(col_name)
        if not name:
            continue
        name = str(name).strip()
        dest_val = _norm_text(row.get(col_destino)) if col_destino else ""
        mat_val = _norm_text(row.get(col_material)) if col_material else ""
        destino_role = (
            "Receptor" if dest_val.startswith("recept")
            else "Donante" if dest_val.startswith("donan")
            else "N/A"
        )
        material_circuit = (
            "Mineral" if mat_val.startswith("miner")
            else "Desmonte" if mat_val.startswith("desmon")
            else "N/A"
        )
        result[name] = {"destino": destino_role, "material": material_circuit}
    return result


def detect_destinations(headers):
    """Finds chancadoras and destinos/donantes by header name/position instead
    of a hardcoded column list, so the tool adapts to a plan whose columns
    were renamed, reordered, added or removed -- as long as the shape below
    still holds:
      - Chancadoras: any header containing "Chw2a" (in sheet order).
      - Destinos/donantes: everything between the chancadoras and the first
        material-type column (ore types M1.. or waste types Wa..), excluding
        any header containing "Botadero"."""
    chw_idx = [i for i, h in enumerate(headers) if h and "Chw2a" in str(h)]
    if not chw_idx:
        raise SystemExit("No se encontro ninguna columna de chancadora (nombre con 'Chw2a') en la hoja.")
    chancadoras = [headers[i] for i in chw_idx]

    boundary_names = set(ORE_TYPES) | set(WASTE_TYPES)
    boundary_idx = [i for i, h in enumerate(headers) if h in boundary_names]
    end = min(boundary_idx) if boundary_idx else len(headers)

    donors = [
        h for h in headers[max(chw_idx) + 1 : end]
        if h and "Botadero" not in str(h)
    ]
    return chancadoras, donors


def detect_active_year(records):
    """Suggests an active year by counting 'Fecha Liberacion' years across
    the records and returning the most common one -- used to pre-fill the
    year field in the UI. ACTIVE_YEAR itself stays whatever the caller sets
    (see adjust_plan's active_year param); this is only a suggestion."""
    counts = Counter()
    for rec in records:
        d = excel_date(to_number(rec.get("Fecha Liberación")))
        if d is not None:
            counts[d.year] += 1
    if not counts:
        return None
    return counts.most_common(1)[0][0]


# Parse cache (Material Shift): reading a ~27 MB workbook takes ~5 s, and the
# same file is re-read on every detection/calculation. The cache key includes
# size and mtime, so editing the Excel always invalidates it. Values are stored
# pickled and unpickled on every hit, so callers always get fresh objects that
# no earlier run could have mutated -- the result is byte-for-byte the same as
# re-parsing. PARSE_CACHE is a plain dict the worker process (motor_servidor)
# injects after reloading this module; CACHE_DIR adds an on-disk layer.
PARSE_CACHE = None
CACHE_DIR = None


def _cache_key(input_path, sheet_name, kind):
    import hashlib
    p = Path(input_path).resolve()
    st = p.stat()
    raw = f"{kind}|{p}|{sheet_name}|{st.st_size}|{st.st_mtime_ns}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _cached(input_path, sheet_name, kind, build):
    import pickle
    try:
        key = _cache_key(input_path, sheet_name, kind)
    except OSError:
        return build()
    if PARSE_CACHE is not None and key in PARSE_CACHE:
        return pickle.loads(PARSE_CACHE[key])
    disk = Path(CACHE_DIR) / f"{key}.pkl" if CACHE_DIR else None
    if disk is not None and disk.exists():
        try:
            blob = disk.read_bytes()
            value = pickle.loads(blob)
            if PARSE_CACHE is not None:
                PARSE_CACHE[key] = blob
            return value
        except Exception:
            pass
    value = build()
    blob = pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)
    if PARSE_CACHE is not None:
        # Keep only the most recent few workbooks in memory.
        while len(PARSE_CACHE) >= 6:
            PARSE_CACHE.pop(next(iter(PARSE_CACHE)))
        PARSE_CACHE[key] = blob
    if disk is not None:
        try:
            disk.parent.mkdir(parents=True, exist_ok=True)
            tmp = disk.with_suffix(".tmp")
            tmp.write_bytes(blob)
            tmp.replace(disk)
            olds = sorted(disk.parent.glob("*.pkl"), key=lambda f: f.stat().st_mtime, reverse=True)
            for f in olds[12:]:
                f.unlink(missing_ok=True)
        except OSError:
            pass
    return pickle.loads(blob)


def list_sheets(input_path):
    """Sheet names in workbook order (for the Inputs tab's 'Hoja' dropdown)."""
    with zipfile.ZipFile(input_path) as zf:
        wb = ET.fromstring(zf.read("xl/workbook.xml"))
        return [s.attrib.get("name") for s in wb.findall(NS + "sheets/" + NS + "sheet")]


def load_plan_base(input_path=INPUT, sheet_name=DEFAULT_SHEET):
    headers, records = _cached(input_path, sheet_name, "plan", lambda: _parse_plan_base(input_path, sheet_name))
    return _finish_load_plan_base(input_path, headers, records)


def _parse_plan_base(input_path, sheet_name):
    with zipfile.ZipFile(input_path) as zf:
        wb = ET.fromstring(zf.read("xl/workbook.xml"))
        rels_root = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        rels = {r.attrib["Id"]: r.attrib["Target"] for r in rels_root}
        rid = [
            s.attrib.get(REL + "id")
            for s in wb.findall(NS + "sheets/" + NS + "sheet")
            if s.attrib["name"] == sheet_name
        ][0]
        sheet_path = rels[rid].lstrip("/")
        if not sheet_path.startswith("xl/"):
            sheet_path = "xl/" + sheet_path

        shared = []
        if "xl/sharedStrings.xml" in zf.namelist():
            for _, elem in ET.iterparse(zf.open("xl/sharedStrings.xml"), events=("end",)):
                if elem.tag == NS + "si":
                    shared.append("".join(elem.itertext()))
                    elem.clear()

        rows = {}
        formula_cache = {}
        for _, elem in ET.iterparse(zf.open(sheet_path), events=("end",)):
            if elem.tag == NS + "row":
                r = int(elem.attrib["r"])
                row = {}
                for c in elem.findall(NS + "c"):
                    ci, _ = split_ref(c.attrib["r"])
                    cell_type = c.attrib.get("t")
                    # A single pass over the cell's direct children instead of
                    # two/three separate .find() tree-searches per cell -- this
                    # loop runs roughly a million times for the full sheet.
                    v_text = None
                    f_text = None
                    is_text = None
                    for child in c:
                        tag = child.tag
                        if tag == NS + "v":
                            v_text = "".join(child.itertext())
                        elif tag == NS + "f":
                            f_text = "".join(child.itertext())
                        elif tag == NS + "is":
                            is_text = "".join(child.itertext())
                    value = None
                    if v_text is not None:
                        if cell_type == "s":
                            value = shared[int(v_text)]
                        elif cell_type == "b":
                            value = v_text == "1"
                        else:
                            value = v_text
                    elif cell_type == "inlineStr":
                        value = is_text
                    if f_text is not None:
                        formula_cache[(r, ci)] = f_text
                    row[ci] = clean_value(value)
                rows[r] = row
                elem.clear()

    # Neither the last column nor the last row is fixed anymore: a plan with
    # more than ~11,000 rows (or extra columns) is read in full instead of
    # being silently cut off.
    header_row = rows.get(4, {})
    max_col = max([ci for ci, v in header_row.items() if v is not None and ci >= 2] or [colnum("CJ")])
    headers = [header_row.get(c) for c in range(2, max_col + 1)]
    last_row = max(rows) if rows else 4
    records = []
    for r in range(5, last_row + 1):
        src = rows.get(r)
        if not src or src.get(2) is None:
            continue
        rec = {headers[c - 2]: src.get(c) for c in range(2, max_col + 1)}
        rec["_excel_row"] = r
        rec["_values"] = [src.get(c) for c in range(2, max_col + 1)]
        records.append(rec)
    return headers, records


def _finish_load_plan_base(input_path, headers, records):
    global CHANCADORES, DONORS, SEVEN, PHASE_PRIORITY, CIRCUIT_OF, DESTINO_ROLE, CONFIG_SHEET_USED
    config = _cached(input_path, "Config", "config", lambda: read_config_sheet(input_path))
    if config:
        header_set = set(headers)
        # Keep the sheet's own column order rather than dict/row order.
        chancadoras = [h for h in headers if h in config and config[h]["destino"] == "Receptor"]
        donors = [h for h in headers if h in config and config[h]["destino"] == "Donante"]
        if not chancadoras:
            raise SystemExit(
                "La hoja 'Config' existe pero ningun destino tiene Config_Destinos = Receptor."
            )
        CHANCADORES, DONORS = chancadoras, donors
        CIRCUIT_OF = {name: cfg["material"] for name, cfg in config.items() if name in header_set}
        DESTINO_ROLE = {name: cfg["destino"] for name, cfg in config.items() if name in header_set}
        CONFIG_SHEET_USED = True
    else:
        CHANCADORES, DONORS = detect_destinations(headers)
        CIRCUIT_OF = {}
        DESTINO_ROLE = {}
        CONFIG_SHEET_USED = False
    SEVEN = CHANCADORES + DONORS
    phases = detect_phases(records)
    if phases:
        PHASE_PRIORITY = {p: i for i, p in enumerate(phases)}

    return headers, records


def apply_destino_config_override(headers, override):
    """Applies an in-app override of the same shape read_config_sheet()
    returns ({name: {"destino": ..., "material": ...}}), without touching the
    source Excel -- used when the user edits Config_Destinos/Config_Materiales
    from the app's own editor instead of (or on top of) a 'Config' sheet
    already in the file. Mirrors read_config_sheet()'s effect on the module
    globals that load_plan_base() would otherwise have set."""
    global CHANCADORES, DONORS, SEVEN, CIRCUIT_OF, DESTINO_ROLE, CONFIG_SHEET_USED
    header_set = set(headers)
    chancadoras = [h for h in headers if override.get(h, {}).get("destino") == "Receptor"]
    donors = [h for h in headers if override.get(h, {}).get("destino") == "Donante"]
    if not chancadoras:
        raise SystemExit("La configuracion de destinos no tiene ningun Receptor.")
    CHANCADORES, DONORS = chancadoras, donors
    CIRCUIT_OF = {name: cfg.get("material", "N/A") for name, cfg in override.items() if name in header_set}
    DESTINO_ROLE = {name: cfg.get("destino", "N/A") for name, cfg in override.items() if name in header_set}
    CONFIG_SHEET_USED = True
    SEVEN = CHANCADORES + DONORS


def default_destino_config(headers):
    """Starting point for the app's Config_Destinos/Config_Materiales editor
    on a file that has no 'Config' sheet yet: today's auto-detected
    chancadoras/donantes, tagged as the Desmonte circuit (the only one that
    has ever existed without an explicit Config sheet) -- everything else
    (Botaderos, Ore-area columns, material-type columns) defaults to N/A.
    Editing and saving this from the app is what turns CONFIG_SHEET_USED on
    for the rest of that session, via apply_destino_config_override()."""
    chancadoras, donors = detect_destinations(headers)
    out = {}
    for h in chancadoras:
        out[h] = {"destino": "Receptor", "material": "Desmonte"}
    for h in donors:
        out[h] = {"destino": "Donante", "material": "Desmonte"}
    return out


def detect_phases(records):
    """Unique values of the 'Fase' column (column D, from row 5 down to the
    LAST row -- no fixed cutoff), ignoring only truly empty cells, in natural
    order (PHASE 10, 11, ... 15 ..., then any non-numeric value such as
    REHANDLE/Remanejo last). Previously REHANDLE was dropped outright, so it
    could never be prioritized from the app even though its rows were still
    eligible for reassignment -- now every value actually present in the
    column shows up and can be ordered like any other phase."""
    seen = []
    for rec in records:
        v = rec.get("Fase")
        if v is None:
            continue
        s = str(v).strip()
        if s == "" or s == "0":
            continue
        if s not in seen:
            seen.append(s)

    def natural(s):
        digits = "".join(ch for ch in s if ch.isdigit())
        return (int(digits) if digits else 10**9, s)

    return sorted(seen, key=natural)


def detect_materials(headers):
    """Waste-type columns present in the sheet, in sheet order. Ore types
    (M1..M6) are deliberately left out: they are never reassigned."""
    return [h for h in headers if h in WASTE_TYPES]


def detect_material_columns(headers, candidates):
    """Which of the given candidate material-type column names are present
    in this file's headers, in sheet order. Generalization of
    detect_materials() to an arbitrary candidate list (WASTE_TYPES or
    ORE_TYPES), used by resolve_circuit()."""
    candidate_set = set(candidates)
    return [h for h in headers if h in candidate_set]


def resolve_circuit(circuit_name, headers):
    """Returns (chancadoras, donors, materials) for one circuit ("Mineral" or
    "Desmonte"), or None if that circuit isn't configured for this file.

    Without a 'Config' sheet (see read_config_sheet()), only 'Desmonte' is
    available, via today's legacy name-based detection (detect_destinations()
    + WASTE_TYPES) -- 'Mineral' has never been modeled before, so it has no
    legacy fallback and is simply unavailable on those files.

    With a 'Config' sheet, a circuit's chancadoras/donors are exactly the
    destinos that sheet tags for it (Config_Materiales) and marks Receptor/
    Donante (Config_Destinos); its materials are whichever ORE_TYPES or
    WASTE_TYPES columns are actually present in the file."""
    if not CONFIG_SHEET_USED:
        if circuit_name != "Desmonte":
            return None
        chancadoras, donors = detect_destinations(headers)
        materials = detect_material_columns(headers, WASTE_TYPES)
        return chancadoras, donors, materials

    chancadoras = [h for h in headers if CIRCUIT_OF.get(h) == circuit_name and DESTINO_ROLE.get(h) == "Receptor"]
    donors = [h for h in headers if CIRCUIT_OF.get(h) == circuit_name and DESTINO_ROLE.get(h) == "Donante"]
    if not chancadoras:
        return None
    candidates = ORE_TYPES if circuit_name == "Mineral" else WASTE_TYPES
    materials = detect_material_columns(headers, candidates)
    return chancadoras, donors, materials


def run_circuit(circuit_name, headers, base_records, **adjust_kwargs):
    """Runs adjust_plan() for a single circuit ("Mineral" or "Desmonte"),
    returning its usual result tuple, or None if that circuit isn't
    configured for this file (see resolve_circuit()).

    adjust_plan/refine_daily/build_validations/etc. were all written against
    fixed module-level globals (CHANCADORES, DONORS, WASTE_TYPES) back when
    there was only ever one circuit -- their LP/refinement logic itself never
    hardcodes a destino or material name, so swapping those globals for the
    duration of the call lets the exact same engine run either circuit,
    without duplicating or rewriting it."""
    resolved = resolve_circuit(circuit_name, headers)
    if resolved is None:
        return None
    chancadoras, donors, materials = resolved

    global CHANCADORES, DONORS, WASTE_TYPES, SEVEN
    saved = (CHANCADORES, DONORS, WASTE_TYPES, SEVEN)
    CHANCADORES, DONORS, WASTE_TYPES = chancadoras, donors, materials
    SEVEN = CHANCADORES + DONORS
    try:
        return adjust_plan(headers, base_records, **adjust_kwargs)
    finally:
        CHANCADORES, DONORS, WASTE_TYPES, SEVEN = saved


def default_material_blocked(destinations):
    """Default material-permission table: every destination takes every
    material, except Tucush (N2_x / N3_7), which never carries Wa."""
    return {d: {"Wa"} for d in destinations if d in TUCUSH_DONORS}


def infer_waste_type(rec):
    for material in WASTE_TYPES:
        if to_number(rec.get(material)) > 1e-9:
            return material
    if to_number(rec.get("Ore1")) > 1e-9:
        return "Ore"
    return "Sin material"


def is_active_2034(rec):
    d = excel_date(to_number(rec.get("Fecha Liberación")))
    w = int(to_number(rec.get("Semana")))
    return d is not None and d.year == ACTIVE_YEAR and 1 <= w <= 52


def phase_rank(phase):
    return PHASE_PRIORITY.get(str(phase), 99)


def adjust_plan(
    headers,
    base_records,
    target_mode="objetivo_fijo",
    requested_week_chw=REQUESTED_WEEK_CHW,
    tolerance_abs=None,
    donor_priority=None,
    phase_priority=None,
    active_year=None,
    material_blocked=None,
):
    """target_mode is 'objetivo_fijo' or 'balanceado'. requested_week_chw is
    used as the weekly target for BOTH modes and both crushers.

    This version solves each week as a small transportation-style linear
    program instead of the old sequential fill/drain/repair passes: donors
    are supply nodes, crushers are demand nodes, and each donor-crusher arc
    costs less the higher that donor's priority is for that crusher. Being
    solved as ONE joint problem per week means conservation can never be left
    half-finished (the classic failure mode of a "fill, then repair" pass),
    and material only ever moves crusher<->donor -- never crusher<->crusher.
    'balanceado' adds a soft penalty term that additionally rewards the two
    crushers landing close to each other that week, without ever moving
    tonnage directly between them; if a week's own donors truly cannot reach
    the band, the LP reports the shortfall/surplus honestly as a "Brecha"
    instead of silently drifting a destination's annual total.

    tolerance_abs is the half-width (in tons) of the acceptable band around
    the weekly target. Defaults to 1% of the target when not provided.

    donor_priority / phase_priority hold an independent ranking PER CRUSHER.
    Accepted shapes: a dict {crusher: [ordered ids]} for a per-crusher order,
    or a plain [ordered ids] list applied to both crushers. Any donor/phase
    left out of a crusher's list keeps participating for that crusher, just
    without a preferred rank (used last, in whatever order is left)."""
    mode_alias = {"objetivo_solicitado": "objetivo_fijo"}
    target_mode = mode_alias.get(target_mode, target_mode)

    if active_year is not None:
        # Overrides the hardcoded ACTIVE_YEAR (2034) so a plan for a
        # different year doesn't silently filter out every row as inactive.
        global ACTIVE_YEAR
        ACTIVE_YEAR = int(active_year)

    def as_per_crusher(value, fallback):
        if value is None:
            return {crusher: list(fallback) for crusher in CHANCADORES}
        if isinstance(value, dict):
            return {crusher: list(value.get(crusher) or fallback) for crusher in CHANCADORES}
        return {crusher: list(value) for crusher in CHANCADORES}

    donor_priority_by_crusher = as_per_crusher(donor_priority, DONORS)
    phase_priority_by_crusher = as_per_crusher(phase_priority, list(PHASE_PRIORITY.keys()))

    donor_rank_by_crusher = {
        crusher: {d: i for i, d in enumerate(order)} for crusher, order in donor_priority_by_crusher.items()
    }
    phase_rank_by_crusher = {
        crusher: {p: i for i, p in enumerate(order)} for crusher, order in phase_priority_by_crusher.items()
    }

    def donor_rank_of(d, crusher):
        return donor_rank_by_crusher[crusher].get(d, len(DONORS) + 1)

    def phase_rank_of(phase, crusher):
        return phase_rank_by_crusher[crusher].get(str(phase), 99)

    modified = []
    for rec in base_records:
        m = dict(rec)
        m["_values"] = list(rec["_values"])
        m["_waste_type"] = infer_waste_type(rec)
        m["_active_2034"] = is_active_2034(rec)
        modified.append(m)

    col_pos = {name: idx for idx, name in enumerate(headers)}
    candidates_by_week = defaultdict(list)
    for idx, rec in enumerate(modified):
        if not rec["_active_2034"] or rec["_waste_type"] not in WASTE_TYPES:
            continue
        week = int(to_number(rec.get("Semana")))
        candidates_by_week[week].append(idx)

    target_by_crusher = {crusher: requested_week_chw for crusher in CHANCADORES}
    tolerance_by_crusher = {
        crusher: tolerance_abs if tolerance_abs is not None else target_by_crusher[crusher] * 0.01
        for crusher in CHANCADORES
    }

    # Material-permission table: blocked[dest] = materials that destination
    # never interacts with (neither receives nor gives). Default keeps the old
    # behaviour: everything allowed except Tucush with Wa.
    if material_blocked is None:
        blocked = default_material_blocked(list(CHANCADORES) + list(DONORS))
    else:
        blocked = {d: set(v) for d, v in material_blocked.items()}

    def allowed(dest, material):
        return material not in blocked.get(dest, ())

    nd, nc, nm = len(DONORS), len(CHANCADORES), len(WASTE_TYPES)
    mat_index = {m: i for i, m in enumerate(WASTE_TYPES)}

    # One pass to precompute every week's starting totals PER MATERIAL -- the
    # LP works material by material so the permission table is enforced
    # exactly (a donor's Wb can only go to a crusher that takes Wb, etc.).
    rows_by_week_mat = {week: {m: [] for m in WASTE_TYPES} for week in range(1, 53)}
    cbase = np.zeros((53, nc, nm))
    davail = np.zeros((53, nd, nm))
    for week, idxs in candidates_by_week.items():
        if week < 1 or week > 52:
            continue
        for i in idxs:
            rec = modified[i]
            mi = mat_index[rec["_waste_type"]]
            rows_by_week_mat[week][rec["_waste_type"]].append(i)
            for ci, c in enumerate(CHANCADORES):
                cbase[week, ci, mi] += to_number(rec.get(c))
            for di, d in enumerate(DONORS):
                davail[week, di, mi] += to_number(rec.get(d))
    week_crusher_base = {week: {c: float(cbase[week, ci].sum()) for ci, c in enumerate(CHANCADORES)} for week in range(1, 53)}

    moves = []
    weekly_status = []
    donor_ledger = Counter()
    # "balanceado" penalizes the two crushers landing far apart -- only
    # meaningful (and only ever indexed, see CHANCADORES[0]/[1] below) when a
    # circuit actually HAS two chancadoras. A circuit with 1 (or 3+) simply
    # has no such pair to compare, so it silently behaves like
    # "objetivo_fijo" instead of crashing on CHANCADORES[1].
    balance_weight = 2.0 if target_mode == "balanceado" and len(CHANCADORES) == 2 else 0.0
    BIG_M = 1.0e7

    def apply_donor_to_crusher(row_idxs, donor, crusher, amount, week):
        ordered = sorted(
            row_idxs,
            key=lambda i: (
                phase_rank_of(modified[i].get("Fase"), crusher),
                str(modified[i].get("Poligono / Origen")),
                int(to_number(modified[i].get("# Sec"))),
            ),
        )
        remaining = amount
        for i in ordered:
            if remaining <= 1e-7:
                break
            rec = modified[i]
            available = to_number(rec.get(donor))
            if available <= 1e-9:
                continue
            transfer = min(available, remaining)
            rec[donor] = available - transfer
            rec[crusher] = to_number(rec.get(crusher)) + transfer
            rec["_values"][col_pos[donor]] = rec[donor]
            rec["_values"][col_pos[crusher]] = rec[crusher]
            moves.append([week, rec.get("_excel_row"), rec.get("Fase"), rec.get("Cota"), rec.get("Poligono / Origen"), rec.get("_waste_type"), donor, crusher, transfer])
            remaining -= transfer

    def apply_crusher_to_donor(row_idxs, donor, crusher, amount, week):
        eligible = [i for i in row_idxs if to_number(modified[i].get(crusher)) > 1e-9]
        ordered = sorted(
            eligible,
            key=lambda i: (
                -phase_rank_of(modified[i].get("Fase"), crusher),
                -int(to_number(modified[i].get("# Sec"))),
            ),
        )
        remaining = amount
        for i in ordered:
            if remaining <= 1e-7:
                break
            rec = modified[i]
            available = to_number(rec.get(crusher))
            if available <= 1e-9:
                continue
            transfer = min(available, remaining)
            rec[crusher] = available - transfer
            rec[donor] = to_number(rec.get(donor)) + transfer
            rec["_values"][col_pos[crusher]] = rec[crusher]
            rec["_values"][col_pos[donor]] = rec[donor]
            moves.append([week, rec.get("_excel_row"), rec.get("Fase"), rec.get("Cota"), rec.get("Poligono / Origen"), rec.get("_waste_type"), crusher, donor, transfer])
            remaining -= transfer

    # Solved as ONE joint problem across all 52 weeks (not 52 independent
    # ones): annual conservation per destination is a cross-week invariant --
    # whatever a donor gives up in one week must come back to that SAME donor
    # at some point in the year, and a crusher's own annual total likewise
    # never changes. That can only be expressed as equality constraints that
    # sum over every week at once. Variables are indexed by material too, so
    # the permission table is a plain upper bound (0 = never touched).
    has_diff = balance_weight > 0
    blk = nd * nm
    n_xtc = 52 * nc * blk
    n_xtd = 52 * nc * blk
    n_short = 52 * nc
    n_sur = 52 * nc
    n_diff = 52 if has_diff else 0
    n = n_xtc + n_xtd + n_short + n_sur + n_diff

    def idx_xtc(week, ci, di, mi):
        return (((week - 1) * nc + ci) * nd + di) * nm + mi

    def idx_xtd(week, ci, di, mi):
        return n_xtc + (((week - 1) * nc + ci) * nd + di) * nm + mi

    def idx_short(week, ci):
        return n_xtc + n_xtd + (week - 1) * nc + ci

    def idx_sur(week, ci):
        return n_xtc + n_xtd + n_short + (week - 1) * nc + ci

    def idx_diff(week):
        return n_xtc + n_xtd + n_short + n_sur + (week - 1)

    c_obj = np.zeros(n)
    ub = np.full(n, np.inf)
    for week in range(1, 53):
        for ci, crusher in enumerate(CHANCADORES):
            for di, donor in enumerate(DONORS):
                for mi, mat in enumerate(WASTE_TYPES):
                    ok = allowed(donor, mat) and allowed(crusher, mat)
                    a = idx_xtc(week, ci, di, mi)
                    b = idx_xtd(week, ci, di, mi)
                    c_obj[a] = donor_rank_of(donor, crusher) + 1.0
                    c_obj[b] = 0.1
                    ub[a] = float(davail[week, di, mi]) if ok else 0.0
                    ub[b] = float(cbase[week, ci, mi]) if ok else 0.0
            c_obj[idx_short(week, ci)] = BIG_M
            c_obj[idx_sur(week, ci)] = BIG_M
        if has_diff:
            c_obj[idx_diff(week)] = balance_weight

    class _Sparse:
        def __init__(self):
            self.r, self.c, self.v, self.b, self.count = [], [], [], [], 0

        def add(self, cols, vals, rhs):
            self.r.extend([self.count] * len(cols))
            self.c.extend(cols)
            self.v.extend(vals)
            self.b.append(rhs)
            self.count += 1

        def matrix(self):
            return coo_matrix((self.v, (self.r, self.c)), shape=(self.count, n)).tocsr()

    ub_rows = _Sparse()
    eq_rows = _Sparse()

    for week in range(1, 53):
        base = week_crusher_base[week]

        # each donor's supply of each material this week
        for di, donor in enumerate(DONORS):
            for mi, mat in enumerate(WASTE_TYPES):
                cap = float(davail[week, di, mi])
                if cap <= 0:
                    continue
                ub_rows.add([idx_xtc(week, ci, di, mi) for ci in range(nc)], [1.0] * nc, cap)

        # each crusher's give-back of each material this week
        for ci, crusher in enumerate(CHANCADORES):
            for mi, mat in enumerate(WASTE_TYPES):
                cap = float(cbase[week, ci, mi])
                if cap <= 0:
                    continue
                ub_rows.add([idx_xtd(week, ci, di, mi) for di in range(nd)], [1.0] * nd, cap)

        for ci, crusher in enumerate(CHANCADORES):
            b0 = base[crusher]
            tgt = target_by_crusher[crusher]
            tol = tolerance_by_crusher[crusher]
            a0 = idx_xtc(week, ci, 0, 0)
            d0 = idx_xtd(week, ci, 0, 0)
            span = list(range(blk))
            cols = [a0 + k for k in span] + [d0 + k for k in span] + [idx_short(week, ci)]
            vals = [-1.0] * blk + [1.0] * blk + [-1.0]
            ub_rows.add(cols, vals, b0 - (tgt - tol))
            cols2 = [a0 + k for k in span] + [d0 + k for k in span] + [idx_sur(week, ci)]
            vals2 = [1.0] * blk + [-1.0] * blk + [-1.0]
            ub_rows.add(cols2, vals2, (tgt + tol) - b0)

        if has_diff:
            base1, base2 = base[CHANCADORES[0]], base[CHANCADORES[1]]
            span = list(range(blk))
            a1, d1 = idx_xtc(week, 0, 0, 0), idx_xtd(week, 0, 0, 0)
            a2, d2 = idx_xtc(week, 1, 0, 0), idx_xtd(week, 1, 0, 0)
            cols = [a1 + k for k in span] + [d1 + k for k in span] + [a2 + k for k in span] + [d2 + k for k in span] + [idx_diff(week)]
            ub_rows.add(cols, [1.0] * blk + [-1.0] * blk + [-1.0] * blk + [1.0] * blk + [-1.0], base2 - base1)
            ub_rows.add(cols, [-1.0] * blk + [1.0] * blk + [1.0] * blk + [-1.0] * blk + [-1.0], base1 - base2)

    # Annual conservation: each donor's and each crusher's own yearly total is
    # exactly what the base plan already had -- only the WEEK it lands in can
    # move, never how much a destination ends up with over the whole year.
    for di, donor in enumerate(DONORS):
        cols, vals = [], []
        for week in range(1, 53):
            for ci in range(nc):
                for mi in range(nm):
                    cols.append(idx_xtc(week, ci, di, mi)); vals.append(1.0)
                    cols.append(idx_xtd(week, ci, di, mi)); vals.append(-1.0)
        eq_rows.add(cols, vals, 0.0)

    for ci, crusher in enumerate(CHANCADORES):
        cols, vals = [], []
        for week in range(1, 53):
            for di in range(nd):
                for mi in range(nm):
                    cols.append(idx_xtc(week, ci, di, mi)); vals.append(1.0)
                    cols.append(idx_xtd(week, ci, di, mi)); vals.append(-1.0)
        eq_rows.add(cols, vals, 0.0)

    result = linprog(
        c_obj,
        A_ub=ub_rows.matrix(),
        b_ub=np.array(ub_rows.b),
        A_eq=eq_rows.matrix(),
        b_eq=np.array(eq_rows.b),
        bounds=list(zip(np.zeros(n), [None if np.isinf(u) else u for u in ub])),
        method="highs",
    )
    LAST_LP["success"] = bool(result.success)
    LAST_LP["message"] = str(result.message)
    x = result.x if result.success else np.zeros(n)

    for week in range(1, 53):
        base = week_crusher_base[week]
        for ci, crusher in enumerate(CHANCADORES):
            for di, donor in enumerate(DONORS):
                for mi, mat in enumerate(WASTE_TYPES):
                    net = float(x[idx_xtc(week, ci, di, mi)] - x[idx_xtd(week, ci, di, mi)])
                    if abs(net) <= 1e-6:
                        continue
                    row_idxs = rows_by_week_mat[week][mat]
                    if net > 0:
                        apply_donor_to_crusher(row_idxs, donor, crusher, net, week)
                    else:
                        apply_crusher_to_donor(row_idxs, donor, crusher, -net, week)
                    donor_ledger[(crusher, donor)] += net

        for ci, crusher in enumerate(CHANCADORES):
            target = target_by_crusher[crusher]
            tolerance = tolerance_by_crusher[crusher]
            a0 = idx_xtc(week, ci, 0, 0)
            d0 = idx_xtd(week, ci, 0, 0)
            inflow = float(x[a0:a0 + blk].sum())
            outflow = float(x[d0:d0 + blk].sum())
            current = base[crusher] + inflow - outflow
            diff = current - target
            weekly_status.append(
                [
                    week,
                    crusher,
                    target,
                    current,
                    diff,
                    "OK" if abs(diff) <= tolerance + 1e-6 else "Brecha por restricciones locales (fuera de banda)",
                ]
            )

    return modified, moves, weekly_status, target_by_crusher, donor_ledger, tolerance_by_crusher


def build_validations(base, modified, target_by_crusher, tolerance_by_crusher=None):
    total_rows = []
    base_by_week = defaultdict(lambda: defaultdict(float))
    mod_by_week = defaultdict(lambda: defaultdict(float))
    base_week_chw = defaultdict(lambda: defaultdict(float))
    mod_week_chw = defaultdict(lambda: defaultdict(float))
    row_breaks = []
    total_base = defaultdict(float)
    total_mod = defaultdict(float)

    for b, m in zip(base, modified):
        b_row = sum(to_number(b.get(c)) for c in SEVEN)
        m_row = sum(to_number(m.get(c)) for c in SEVEN)
        if abs(b_row - m_row) > 1e-5 and len(row_breaks) < 100:
            row_breaks.append([b.get("_excel_row"), b.get("Semana"), b.get("Poligono / Origen"), b_row, m_row, m_row - b_row])
        for c in SEVEN:
            total_base[c] += to_number(b.get(c))
            total_mod[c] += to_number(m.get(c))
        if m.get("_active_2034"):
            week = int(to_number(m.get("Semana")))
            waste = m.get("_waste_type")
            for dest in SEVEN:
                base_by_week[week][dest] += to_number(b.get(dest))
                mod_by_week[week][dest] += to_number(m.get(dest))
            for crusher in CHANCADORES:
                base_week_chw[week][crusher] += to_number(b.get(crusher))
                mod_week_chw[week][crusher] += to_number(m.get(crusher))

    for c in SEVEN:
        total_rows.append([c, total_base[c], total_mod[c], total_mod[c] - total_base[c], "OK" if abs(total_mod[c] - total_base[c]) <= 1e-5 else "Revisar"])
    total_rows.append(["TOTAL 7 COLUMNAS", sum(total_base.values()), sum(total_mod.values()), sum(total_mod.values()) - sum(total_base.values()), "OK" if abs(sum(total_mod.values()) - sum(total_base.values())) <= 1e-5 else "Revisar"])

    weekly_rows = []
    for week in range(1, 53):
        for crusher in CHANCADORES:
            target = target_by_crusher[crusher]
            tolerance = (tolerance_by_crusher or {}).get(crusher, target * 0.01)
            mod_value = mod_week_chw[week][crusher]
            diff = mod_value - target
            weekly_rows.append([week, crusher, target, mod_value, diff, "OK" if abs(diff) <= tolerance else "Brecha fuera de banda"])

    row_summary = [
        ["Filas evaluadas", len(base)],
        ["Filas con diferencia en total diario 7 columnas", len(row_breaks)],
        ["Estado", "OK" if not row_breaks else "Revisar"],
    ]
    return total_rows, weekly_rows, row_summary, row_breaks


def check_material_matrix(base, modified, material_blocked=None):
    """Proof that the material-permission table was honoured: for every
    destination/material cell marked as blocked, the tonnage of that
    destination on rows of that material must be identical to the base plan
    (nothing added, nothing taken)."""
    if material_blocked is None:
        blocked = default_material_blocked(list(CHANCADORES) + list(DONORS))
    else:
        blocked = {d: set(v) for d, v in material_blocked.items()}
    violations = []
    for b, m in zip(base, modified):
        mat = m.get("_waste_type")
        for dest, mats in blocked.items():
            if mat in mats:
                delta = to_number(m.get(dest)) - to_number(b.get(dest))
                if abs(delta) > 1e-6:
                    violations.append([m.get("_excel_row"), dest, mat, delta])
    return {"ok": not violations, "violations": violations}


def check_row_material_balance(modified, tolerance_pct=0.05):
    """Per-row identity required once Tucush (N2_1/N2_2/N2_3) is in play:
    SUMA(columnas de destino) debe igualar SUMA(columnas de material) para
    cada fila, dentro de una tolerancia de +/-0.05%. El modelo nunca toca las
    columnas de material y nunca cambia el total de destinos de una fila, asi
    que esto se mantiene automaticamente si ya se cumplia en el plan base --
    este chequeo es la prueba explicita de que sigue siendo asi."""
    bad_rows = []
    checked = 0
    max_dev_pct = 0.0
    for rec in modified:
        sum_dest = sum(to_number(rec.get(c)) for c in SEVEN)
        sum_mat = sum(to_number(rec.get(c)) for c in WASTE_TYPES)
        if sum_dest < 1e-6 and sum_mat < 1e-6:
            continue
        checked += 1
        denom = max(sum_dest, sum_mat, 1e-9)
        dev_pct = abs(sum_dest - sum_mat) / denom * 100
        if dev_pct > max_dev_pct:
            max_dev_pct = dev_pct
        if dev_pct > tolerance_pct:
            bad_rows.append([rec.get("_excel_row"), rec.get("Semana"), rec.get("Poligono / Origen"), sum_dest, sum_mat, dev_pct])
    return {
        "checked": checked,
        "bad_rows": bad_rows,
        "max_dev_pct": max_dev_pct,
        "ok": not bad_rows,
    }


def refine_daily(modified, headers, target_by_crusher, daily_tolerance_abs, donor_priority=None, phase_priority=None, daily_target_abs=None, material_blocked=None):
    """Second-stage pass, run AFTER adjust_plan(). Within each week, redistributes
    the crusher's already weekly-conserved tonnage across its calendar days
    (from 'Fecha Liberacion'), inside a daily tolerance band. Donors are only
    pulled from / returned to rows sharing the exact same day, so weekly and
    annual totals per destination are unaffected -- this only smooths
    day-to-day variation inside each week.

    daily_target_abs is an INDEPENDENT daily target (in tons/day), set by the
    user separately from the weekly objective -- it is NOT required to equal
    weekly_target/7. When a week's real total doesn't average out to this
    daily target, the fill/drain budget is still capped to what's actually
    reconcilable (see fill_budget below), so conservation stays exact and any
    unreachable days show up honestly as "Brecha diaria" instead of drifting
    a destination's total. Falls back to weekly_target/days_in_week when not
    provided."""
    col_pos = {name: idx for idx, name in enumerate(headers)}
    if material_blocked is None:
        blocked = default_material_blocked(list(CHANCADORES) + list(DONORS))
    else:
        blocked = {d: set(v) for d, v in material_blocked.items()}

    def allowed(dest, material):
        return material not in blocked.get(dest, ())

    def as_per_crusher(value, fallback):
        if value is None:
            return {crusher: list(fallback) for crusher in CHANCADORES}
        if isinstance(value, dict):
            return {crusher: list(value.get(crusher) or fallback) for crusher in CHANCADORES}
        return {crusher: list(value) for crusher in CHANCADORES}

    donor_priority_by_crusher = as_per_crusher(donor_priority, DONORS)
    phase_priority_by_crusher = as_per_crusher(phase_priority, list(PHASE_PRIORITY.keys()))
    donor_rank_by_crusher = {c: {d: i for i, d in enumerate(o)} for c, o in donor_priority_by_crusher.items()}
    phase_rank_by_crusher = {c: {p: i for i, p in enumerate(o)} for c, o in phase_priority_by_crusher.items()}

    def donor_rank_of(d, crusher):
        return donor_rank_by_crusher[crusher].get(d, len(DONORS) + 1)

    def phase_rank_of(phase, crusher):
        return phase_rank_by_crusher[crusher].get(str(phase), 99)

    candidates_by_day = defaultdict(list)
    days_by_week = defaultdict(set)
    for idx, rec in enumerate(modified):
        if not rec.get("_active_2034") or rec.get("_waste_type") not in WASTE_TYPES:
            continue
        day = excel_date(to_number(rec.get("Fecha Liberación")))
        if day is None:
            continue
        week = int(to_number(rec.get("Semana")))
        candidates_by_day[day].append(idx)
        days_by_week[week].add(day)

    day_to_week = {}
    for week, days in days_by_week.items():
        for d in days:
            day_to_week[d] = week

    moves = []
    daily_status = []

    # Mirrors adjust_plan's own pass1/pass2 structure: fill ALL days of the week
    # first (recording a week-scoped ledger per crusher+donor), THEN drain the
    # week's over-target days using that same ledger. Doing fill+drain together
    # per single day (instead of per week) breaks weekly conservation, since a
    # day that only needs draining never has anything in its own ledger to give
    # back to.
    for week, days in sorted(days_by_week.items()):
        ordered_days = sorted(days)
        n_days = max(len(days), 1)

        for crusher in CHANCADORES:
            if daily_target_abs is not None:
                target_day = daily_target_abs
            else:
                # Fallback: spread the week's ACTUAL already-conserved total
                # evenly across its days (weekly_target/7 equivalent).
                week_total = sum(
                    to_number(modified[i].get(crusher))
                    for day in ordered_days
                    for i in candidates_by_day.get(day, [])
                )
                target_day = week_total / n_days
            ledger = Counter()
            pull_log = []
            snap_cols = [crusher] + list(DONORS)
            snap_moves = len(moves)
            snap = {i: [to_number(modified[i].get(col)) for col in snap_cols] for day in ordered_days for i in candidates_by_day.get(day, [])}

            # A day left inside its own tolerance band is never touched, so its
            # own deviation from target_day is not "returned" anywhere -- fill
            # and drain totals are only guaranteed to match if we additionally
            # cap total fill at whatever total excess actually exists this week
            # (computed up-front, before any transfer happens).
            total_need = 0.0
            total_excess = 0.0
            for day in ordered_days:
                day_rows = candidates_by_day.get(day, [])
                current = sum(to_number(modified[i].get(crusher)) for i in day_rows)
                total_need += max(0.0, (target_day - daily_tolerance_abs) - current)
                total_excess += max(0.0, current - (target_day + daily_tolerance_abs))
            fill_budget = min(total_need, total_excess)

            # Pass A: fill under-target days from that same day's donors, capped
            # so the week never fills more than it can later drain back.
            for day in ordered_days:
                if fill_budget <= 1e-7:
                    break
                day_rows = candidates_by_day.get(day, [])
                current = sum(to_number(modified[i].get(crusher)) for i in day_rows)
                need = max(0.0, (target_day - daily_tolerance_abs) - current)
                need = min(need, fill_budget)
                if need <= 1e-7:
                    continue
                ordered_rows = sorted(
                    day_rows,
                    key=lambda i: (
                        phase_rank_of(modified[i].get("Fase"), crusher),
                        str(modified[i].get("Poligono / Origen")),
                        int(to_number(modified[i].get("# Sec"))),
                    ),
                )
                for row_idx in ordered_rows:
                    if need <= 1e-7:
                        break
                    rec = modified[row_idx]
                    mat = rec.get("_waste_type")
                    if not allowed(crusher, mat):
                        continue
                    for donor in sorted(DONORS, key=lambda d: donor_rank_of(d, crusher)):
                        if not allowed(donor, mat):
                            continue
                        available = to_number(rec.get(donor))
                        if available <= 1e-9:
                            continue
                        transfer = min(available, need)
                        rec[donor] = available - transfer
                        rec[crusher] = to_number(rec.get(crusher)) + transfer
                        rec["_values"][col_pos[donor]] = rec[donor]
                        rec["_values"][col_pos[crusher]] = rec[crusher]
                        ledger[donor] += transfer
                        pull_log.append((row_idx, donor, transfer))
                        moves.append([day.isoformat(), rec.get("_excel_row"), rec.get("Fase"), rec.get("Cota"), rec.get("Poligono / Origen"), rec.get("_waste_type"), donor, crusher, transfer])
                        need -= transfer
                        fill_budget -= transfer

            # Pass B: drain over-target days, returning tonnage to the same
            # donor columns consumed in pass A (possibly on a different day of
            # this same week) -- exactly like adjust_plan's pass2.
            for day in ordered_days:
                day_rows = candidates_by_day.get(day, [])
                current = sum(to_number(modified[i].get(crusher)) for i in day_rows)
                excess = max(0.0, current - (target_day + daily_tolerance_abs))
                if excess <= 1e-7:
                    continue
                surplus_rows = sorted(
                    [i for i in day_rows if to_number(modified[i].get(crusher)) > 1e-9],
                    key=lambda i: (
                        -phase_rank_of(modified[i].get("Fase"), crusher),
                        -int(to_number(modified[i].get("# Sec"))),
                    ),
                )
                for row_idx in surplus_rows:
                    if excess <= 1e-7:
                        break
                    rec = modified[row_idx]
                    mat = rec.get("_waste_type")
                    if not allowed(crusher, mat):
                        continue
                    available = to_number(rec.get(crusher))
                    if available <= 1e-9:
                        continue
                    transfer = min(available, excess)
                    remaining = transfer
                    for donor in sorted(DONORS, key=lambda d: donor_rank_of(d, crusher)):
                        if remaining <= 1e-7:
                            break
                        if not allowed(donor, mat):
                            continue
                        needed_back = ledger[donor]
                        if needed_back <= 1e-9:
                            continue
                        add_back = min(remaining, needed_back)
                        rec[donor] = to_number(rec.get(donor)) + add_back
                        rec["_values"][col_pos[donor]] = rec[donor]
                        ledger[donor] -= add_back
                        moves.append([day.isoformat(), rec.get("_excel_row"), rec.get("Fase"), rec.get("Cota"), rec.get("Poligono / Origen"), rec.get("_waste_type"), crusher, donor, add_back])
                        remaining -= add_back
                    transfer -= remaining
                    rec[crusher] = available - transfer
                    rec["_values"][col_pos[crusher]] = rec[crusher]
                    excess -= transfer

            # Settle: whatever pass A pulled from a donor that pass B could not
            # hand back (that donor does not take the material of the
            # over-target rows, e.g. Tucush and Wa) goes back from ANY row of
            # this week that the crusher holds and the donor accepts, so weekly
            # and annual totals per destination stay exact. Last resort:
            # undo the original pull on the very row it came from.
            def give_back(rec, donor, amount, day_label):
                avail = to_number(rec.get(crusher))
                t = min(avail, amount)
                if t <= 1e-9:
                    return 0.0
                rec[crusher] = avail - t
                rec[donor] = to_number(rec.get(donor)) + t
                rec["_values"][col_pos[crusher]] = rec[crusher]
                rec["_values"][col_pos[donor]] = rec[donor]
                moves.append([day_label, rec.get("_excel_row"), rec.get("Fase"), rec.get("Cota"), rec.get("Poligono / Origen"), rec.get("_waste_type"), crusher, donor, t])
                return t

            for donor in DONORS:
                owed = ledger[donor]
                if owed <= 1e-7:
                    continue
                for day in ordered_days:
                    if owed <= 1e-7:
                        break
                    for i in candidates_by_day.get(day, []):
                        if owed <= 1e-7:
                            break
                        mat = modified[i].get("_waste_type")
                        if allowed(crusher, mat) and allowed(donor, mat):
                            owed -= give_back(modified[i], donor, owed, day.isoformat())
                if owed > 1e-7:
                    for row_idx, d2, amt in reversed(pull_log):
                        if owed <= 1e-7:
                            break
                        if d2 == donor:
                            owed -= give_back(modified[row_idx], donor, min(owed, amt), "ajuste")
                ledger[donor] = owed

            # Safety net: if the week still could not be settled exactly, undo
            # this crusher's daily smoothing for the week (weekly result stays;
            # the daily gaps are reported as they are) -- totals never drift.
            if any(ledger[d] > 1e-6 for d in DONORS):
                for i, vals in snap.items():
                    rec = modified[i]
                    for col, v in zip(snap_cols, vals):
                        rec[col] = v
                        rec["_values"][col_pos[col]] = v
                del moves[snap_moves:]

    for week, days in sorted(days_by_week.items()):
        ordered_days = sorted(days)
        n_days = max(len(days), 1)
        for crusher in CHANCADORES:
            if daily_target_abs is not None:
                target_day = daily_target_abs
            else:
                week_total = sum(
                    to_number(modified[i].get(crusher))
                    for day in ordered_days
                    for i in candidates_by_day.get(day, [])
                )
                target_day = week_total / n_days
            for day in ordered_days:
                day_rows = candidates_by_day.get(day, [])
                current = sum(to_number(modified[i].get(crusher)) for i in day_rows)
                diff = current - target_day
                daily_status.append([day.isoformat(), crusher, target_day, current, diff, "OK" if abs(diff) <= daily_tolerance_abs else "Brecha diaria (fuera de banda)"])

    return moves, daily_status


def build_pivot_like(modified):
    agg = defaultdict(float)
    for rec in modified:
        if not rec.get("_active_2034"):
            continue
        waste = rec.get("_waste_type")
        if waste not in WASTE_TYPES:
            continue
        week = int(to_number(rec.get("Semana")))
        for dest in SEVEN:
            v = to_number(rec.get(dest))
            if abs(v) > 1e-9:
                agg[(week, dest, waste)] += v
    return [[w, d, t, agg[(w, d, t)]] for (w, d, t) in sorted(agg)]


def build_dashboard_rows(base, modified, target_by_crusher, requested_week_chw, tolerance_week_chw):
    weekly = []
    for week in range(1, 53):
        row = [week]
        total_mod = 0.0
        for crusher in CHANCADORES:
            base_v = sum(to_number(rec.get(crusher)) for rec in base if is_active_2034(rec) and int(to_number(rec.get("Semana"))) == week)
            mod_v = sum(to_number(rec.get(crusher)) for rec in modified if rec.get("_active_2034") and int(to_number(rec.get("Semana"))) == week)
            total_mod += mod_v
            row.extend([base_v, mod_v, target_by_crusher[crusher]])
        row.extend([total_mod, requested_week_chw - tolerance_week_chw, requested_week_chw + tolerance_week_chw])
        weekly.append(row)

    dest_rows = []
    for dest in SEVEN:
        base_v = sum(to_number(rec.get(dest)) for rec in base if is_active_2034(rec))
        mod_v = sum(to_number(rec.get(dest)) for rec in modified if rec.get("_active_2034"))
        dest_rows.append([dest, base_v, mod_v, mod_v - base_v, "OK" if abs(mod_v - base_v) <= 1e-5 else "Revisar"])

    waste_rows = []
    for waste in WASTE_TYPES:
        base_v = sum(to_number(rec.get("Total Material (t)")) for rec in base if is_active_2034(rec) and infer_waste_type(rec) == waste)
        mod_chw = sum(sum(to_number(rec.get(c)) for c in CHANCADORES) for rec in modified if rec.get("_active_2034") and rec.get("_waste_type") == waste)
        waste_rows.append([waste, base_v, mod_chw])

    kpis = [
        ["Modo objetivo", "Promedio conservado por destino"],
        ["Objetivo solicitado por chancador", requested_week_chw],
        ["Tolerancia rango +/-", tolerance_week_chw],
        ["Objetivo efectivo Chw2a_1", target_by_crusher["Chw2a_1"]],
        ["Objetivo efectivo Chw2a_2", target_by_crusher["Chw2a_2"]],
        ["Total Chw2a_1 conservado", target_by_crusher["Chw2a_1"] * 52],
        ["Total Chw2a_2 conservado", target_by_crusher["Chw2a_2"] * 52],
    ]
    return weekly, dest_rows, waste_rows, kpis


def add_dashboard(workbook, formats, base, modified, target_by_crusher, requested_week_chw, tolerance_week_chw):
    weekly, dest_rows, waste_rows, kpis = build_dashboard_rows(base, modified, target_by_crusher, requested_week_chw, tolerance_week_chw)
    ws = workbook.add_worksheet("Dashboard")
    ws.hide_gridlines(2)
    ws.write("A1", "Dashboard Ajuste Plan 2034", formats["title"])
    ws.write("A2", "Perfil semanal, conservación por destino y resumen de desmonte", formats["note"])

    weekly_headers = [
        "Semana",
        "Chw2a_1 Base",
        "Chw2a_1 Mod",
        "Chw2a_1 Objetivo",
        "Chw2a_2 Base",
        "Chw2a_2 Mod",
        "Chw2a_2 Objetivo",
        "Total Chancadoras Mod",
        "Rango Min Solicitado",
        "Rango Max Solicitado",
    ]
    ws.write_row("A4", weekly_headers, formats["header"])
    for i, row in enumerate(weekly, 5):
        ws.write_row(i - 1, 0, row)
    ws.add_table(3, 0, 55, len(weekly_headers) - 1, {
        "name": "TablaDashboardSemanal",
        "style": "Table Style Medium 2",
        "columns": [{"header": h} for h in weekly_headers],
    })
    ws.set_column("A:A", 9)
    ws.set_column("B:J", 16, formats["number"])

    ws.write_row("L4", ["Indicador", "Valor"], formats["header"])
    for i, row in enumerate(kpis, 5):
        ws.write_row(i - 1, 11, row)
    ws.set_column("L:L", 29)
    ws.set_column("M:M", 18, formats["number"])

    dest_start = 59
    ws.write_row(dest_start - 1, 0, ["Destino", "Base", "Modificado", "Diferencia", "Estado"], formats["header"])
    for i, row in enumerate(dest_rows, dest_start):
        ws.write_row(i, 0, row)
    ws.add_table(dest_start - 1, 0, dest_start + len(dest_rows) - 1, 4, {
        "name": "TablaDashboardDestino",
        "style": "Table Style Medium 2",
        "columns": [{"header": h} for h in ["Destino", "Base", "Modificado", "Diferencia", "Estado"]],
    })

    waste_start = 59
    ws.write_row(waste_start - 1, 6, ["Tipo Desmonte", "Total Plan", "A Chancadoras Mod"], formats["header"])
    for i, row in enumerate(waste_rows, waste_start):
        ws.write_row(i, 6, row)
    ws.add_table(waste_start - 1, 6, waste_start + len(waste_rows) - 1, 8, {
        "name": "TablaDashboardDesmonte",
        "style": "Table Style Medium 2",
        "columns": [{"header": h} for h in ["Tipo Desmonte", "Total Plan", "A Chancadoras Mod"]],
    })
    ws.set_column("G:G", 15)
    ws.set_column("H:I", 18, formats["number"])

    line = workbook.add_chart({"type": "line"})
    for col, name, color in [
        (2, "Chw2a_1 Mod", "#1F77B4"),
        (3, "Chw2a_1 Objetivo", "#1F77B4"),
        (5, "Chw2a_2 Mod", "#FF7F0E"),
        (6, "Chw2a_2 Objetivo", "#FF7F0E"),
    ]:
        dash = "dash" if "Objetivo" in name else "solid"
        line.add_series({
            "name": ["Dashboard", 3, col],
            "categories": ["Dashboard", 4, 0, 55, 0],
            "values": ["Dashboard", 4, col, 55, col],
            "line": {"color": color, "dash_type": dash},
        })
    line.set_title({"name": "Alimentacion semanal por chancador (t)"})
    line.set_x_axis({"name": "Semana"})
    line.set_y_axis({"name": "Tonelaje", "num_format": "#,##0"})
    line.set_legend({"position": "bottom"})
    ws.insert_chart("L13", line, {"x_scale": 1.45, "y_scale": 1.35})

    bar = workbook.add_chart({"type": "column"})
    bar.add_series({
        "name": ["Dashboard", dest_start - 1, 1],
        "categories": ["Dashboard", dest_start, 0, dest_start + len(dest_rows) - 1, 0],
        "values": ["Dashboard", dest_start, 1, dest_start + len(dest_rows) - 1, 1],
        "fill": {"color": "#7F7F7F"},
    })
    bar.add_series({
        "name": ["Dashboard", dest_start - 1, 2],
        "categories": ["Dashboard", dest_start, 0, dest_start + len(dest_rows) - 1, 0],
        "values": ["Dashboard", dest_start, 2, dest_start + len(dest_rows) - 1, 2],
        "fill": {"color": "#2CA02C"},
    })
    bar.set_title({"name": "Conservacion de tonelaje por destino"})
    bar.set_y_axis({"name": "Tonelaje", "num_format": "#,##0"})
    bar.set_legend({"position": "bottom"})
    ws.insert_chart("L37", bar, {"x_scale": 1.45, "y_scale": 1.20})
    ws.freeze_panes(4, 0)


def write_sheet_table(ws, headers, rows, formats, autofilter=True, freeze=(1, 0), table_name=None):
    ws.write_row(0, 0, headers, formats["header"])
    for r, row in enumerate(rows, 1):
        ws.write_row(r, 0, row)
    if table_name and rows:
        ws.add_table(
            0,
            0,
            len(rows),
            len(headers) - 1,
            {
                "name": table_name,
                "style": "Table Style Medium 2",
                "columns": [{"header": str(h)} for h in headers],
            },
        )
    elif autofilter and rows:
        ws.autofilter(0, 0, len(rows), len(headers) - 1)
    ws.freeze_panes(*freeze)


def set_plan_formats(ws, headers, nrows, formats):
    widths = {
        "# Sec": 8,
        "Semana": 8,
        "Fase": 12,
        "Malla / Stock": 18,
        "Cota": 10,
        "Poligono / Origen": 20,
        "Polígono Predecesor \n(si se requiere 100% completado por seguridad)": 26,
        "Fecha Liberación": 14,
        "Proceso a la Liberación (inicio modelo) / \"Tallus\"": 18,
        "Total Material (t)": 15,
    }
    for i, h in enumerate(headers):
        ws.set_column(i, i, widths.get(h, 12))
    for name in ["Total Material (t)"] + SEVEN + WASTE_TYPES:
        if name in headers:
            col = headers.index(name)
            ws.set_column(col, col, 14, formats["number"])
    if "Fecha Liberación" in headers:
        ws.set_column(headers.index("Fecha Liberación"), headers.index("Fecha Liberación"), 14, formats["date_serial"])
    ws.freeze_panes(1, 6)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    headers, base = load_plan_base()
    modified, moves, weekly_status, target_by_crusher, donor_ledger, tolerance_by_crusher = adjust_plan(headers, base)
    total_rows, weekly_rows, row_summary, row_breaks = build_validations(base, modified, target_by_crusher, tolerance_by_crusher)
    pivot_rows = build_pivot_like(modified)

    workbook = xlsxwriter.Workbook(OUTPUT)
    workbook.set_properties({"title": "Ajuste Plan 2034", "comments": "Redistribución de desmonte hacia Chw2a_1 y Chw2a_2"})
    formats = {
        "title": workbook.add_format({"bold": True, "font_size": 14, "font_color": "#FFFFFF", "bg_color": "#1F4E78"}),
        "header": workbook.add_format({"bold": True, "font_color": "#FFFFFF", "bg_color": "#1F4E78", "border": 1, "text_wrap": True, "valign": "vcenter"}),
        "subheader": workbook.add_format({"bold": True, "font_color": "#FFFFFF", "bg_color": "#5B9BD5", "border": 1}),
        "number": workbook.add_format({"num_format": "#,##0.00"}),
        "integer": workbook.add_format({"num_format": "#,##0"}),
        "date_serial": workbook.add_format({"num_format": "yyyy-mm-dd"}),
        "ok": workbook.add_format({"font_color": "#006100", "bg_color": "#C6EFCE"}),
        "bad": workbook.add_format({"font_color": "#9C0006", "bg_color": "#FFC7CE"}),
    }

    ws_base = workbook.add_worksheet("Plan Base")
    write_sheet_table(ws_base, headers, [r["_values"] for r in base], formats, freeze=(1, 6), table_name="TablaPlanBase")
    set_plan_formats(ws_base, headers, len(base), formats)

    ws_mod = workbook.add_worksheet("Plan Modificado")
    write_sheet_table(ws_mod, headers, [r["_values"] for r in modified], formats, freeze=(1, 6), table_name="TablaPlanModificado")
    set_plan_formats(ws_mod, headers, len(modified), formats)

    ws_val = workbook.add_worksheet("Validacion")
    ws_val.write("A1", "Validacion de restricciones", formats["title"])
    ws_val.write_row("A3", ["Restriccion", "Resultado"], formats["header"])
    ws_val.write_row("A4", ["Total 7 columnas en 52 semanas", "OK" if abs(total_rows[-1][3]) <= 1e-5 else "Revisar"])
    ws_val.write_row("A5", ["Total diario por fila", row_summary[-1][1]])
    ws_val.write_row("A6", ["Meta semanal por chancador", "OK con brechas marcadas por semana" if any(r[5] != "OK" for r in weekly_rows) else "OK"])
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
    ws_val.set_column("A:A", 26)
    ws_val.set_column("B:F", 16, formats["number"])
    ws_val.conditional_format(8, 4, 8 + len(total_rows), 4, {"type": "text", "criteria": "containing", "value": "OK", "format": formats["ok"]})
    ws_val.conditional_format(start, 5, start + len(weekly_rows), 5, {"type": "text", "criteria": "containing", "value": "OK", "format": formats["ok"]})
    ws_val.conditional_format(start, 5, start + len(weekly_rows), 5, {"type": "text", "criteria": "containing", "value": "Brecha", "format": formats["bad"]})
    ws_val.freeze_panes(8, 0)

    ws_res = workbook.add_worksheet("Resumen Desmonte")
    write_sheet_table(ws_res, ["Semana", "Destino", "Tipo Desmonte", "Tonelaje"], pivot_rows, formats, table_name="TablaResumenDesmonte")
    ws_res.set_column("A:A", 10)
    ws_res.set_column("B:C", 16)
    ws_res.set_column("D:D", 16, formats["number"])

    ws_moves = workbook.add_worksheet("Movimientos")
    write_sheet_table(ws_moves, ["Semana", "Fila Excel", "Fase", "Cota", "Poligono / Origen", "Tipo Desmonte", "Desde", "Hacia", "Tonelaje Movido"], moves, formats, table_name="TablaMovimientos")
    ws_moves.set_column("A:B", 10)
    ws_moves.set_column("C:H", 18)
    ws_moves.set_column("I:I", 16, formats["number"])

    workbook.close()

    print(OUTPUT)
    print("movimientos", len(moves))
    print("brechas", sum(1 for r in weekly_rows if r[5] != "OK"))
    print("row_breaks", len(row_breaks))
    print("total_7_diff", total_rows[-1][3])


if __name__ == "__main__":
    main()
