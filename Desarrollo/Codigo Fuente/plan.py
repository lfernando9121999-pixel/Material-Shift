"""Vector Plan: lectura agnóstica del Excel de métricas del plan, vínculo con los indicadores de SimA
y cálculo de los valores simulados por réplica (Desempeño vs Plan).

Estructura esperada (como «Formato de Vector Plan.xlsx», sin depender de celdas fijas):
  · una celda inicial con el nombre del plan;
  · filas de sección («1.  Producción por Origen») sin unidad ni valor;
  · filas de ítem con texto, unidad (Mt, %, min, talad, Mtpa, TPH…) y valor (número o «-»).
"""
import re
import unicodedata

import modelo
import registro

VARIACIONES = {"div": ("B/A", "División (B/A)"), "resta": ("B-A", "Resta (B-A)"),
               "dif": ("(B-A)/A", "División Diferencial ((B-A)/A)")}
# Comportamiento por defecto según la unidad (tomado del formato «Resultados … .xlsx»)
_VAR_UNIDAD = {"mt": "div", "%": "resta", "min": "resta", "talad": "resta", "mtpa": "resta", "tph": "dif"}
SIN_VINCULO = ""


def _n(texto):
    t = unicodedata.normalize("NFKD", str(texto or ""))
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return t


def _compacto(texto):
    return re.sub(r"[^0-9a-z&]+", "", _n(texto))


def variacion_por_defecto(unidad):
    return _VAR_UNIDAD.get(_n(unidad).strip(), "resta")


# ----------------------------------------------------------------------------------------
# Lectura del Excel
# ----------------------------------------------------------------------------------------
_NUMERADO = re.compile(r"^\s*\d+(\.\d+)*\.?\s+\S")


class ErrorPlan(Exception):
    pass


def leer_excel(ruta):
    """Devuelve {'nombre', 'hoja', 'filas': [...]} leyendo la primera hoja visible con métricas."""
    import openpyxl
    try:
        wb = openpyxl.load_workbook(ruta, data_only=True)
    except Exception as e:
        raise ErrorPlan(f"No se pudo abrir el archivo: {e}")
    mejor = None
    for ws in wb.worksheets:
        if ws.sheet_state != "visible":
            continue
        r = _leer_hoja(ws)
        if r and (mejor is None or len(r["filas"]) > len(mejor["filas"])):
            mejor = r
    if not mejor or not any(f["tipo"] == "item" for f in mejor["filas"]):
        raise ErrorPlan("No se encontraron métricas en el archivo. Se esperan filas con texto, "
                        "unidad y valor (por ejemplo «3.1 Perforadora Precorte | % | 79.2%»).")
    return mejor


def _leer_hoja(ws):
    celdas = {}
    for fila in ws.iter_rows():
        for c in fila:
            if c.value is not None and str(c.value).strip() != "":
                celdas[(c.row, c.column)] = c
    if not celdas:
        return None
    # Columna de textos: la que tiene más textos numerados ("1.1  Material Expit")
    conteo = {}
    for (r, col), c in celdas.items():
        if isinstance(c.value, str) and _NUMERADO.match(c.value):
            conteo[col] = conteo.get(col, 0) + 1
    if not conteo:
        return None
    col_txt = max(conteo, key=conteo.get)
    filas_txt = sorted(r for (r, col) in celdas if col == col_txt and isinstance(celdas[(r, col)].value, str))
    if not filas_txt:
        return None
    # Columna de valores: a la derecha, la que tiene más números o «-»
    cand = {}
    for r in filas_txt:
        for (rr, col), c in celdas.items():
            if rr == r and col > col_txt and (isinstance(c.value, (int, float)) or str(c.value).strip() in ("-", "–")):
                cand[col] = cand.get(col, 0) + 1
    col_val = max(cand, key=cand.get) if cand else None
    # Columna de unidades: textos cortos entre la de textos y la de valores
    cand_u = {}
    for r in filas_txt:
        for (rr, col), c in celdas.items():
            if rr == r and col > col_txt and (col_val is None or col < col_val) and isinstance(c.value, str) \
                    and len(c.value.strip()) <= 8:
                cand_u[col] = cand_u.get(col, 0) + 1
    col_uni = max(cand_u, key=cand_u.get) if cand_u else None
    primera = filas_txt[0]
    nombre = ""
    for (r, col) in sorted(celdas):
        if r < primera and isinstance(celdas[(r, col)].value, str):
            nombre = celdas[(r, col)].value.strip()
            break
    filas = []
    for r in filas_txt:
        texto = str(celdas[(r, col_txt)].value).rstrip()
        unidad = str(celdas[(r, col_uni)].value).strip() if col_uni and (r, col_uni) in celdas else ""
        c_val = celdas.get((r, col_val)) if col_val else None
        valor, formato = None, "General"
        if c_val is not None:
            formato = c_val.number_format or "General"
            if isinstance(c_val.value, (int, float)) and not isinstance(c_val.value, bool):
                valor = float(c_val.value)
        es_item = bool(unidad) or c_val is not None
        filas.append({"tipo": "item" if es_item else "seccion", "texto": texto, "unidad": unidad,
                      "valor": valor, "formato": formato, "fila": r})
    return {"nombre": nombre or ws.title, "hoja": ws.title, "filas": filas,
            "columnas": {"texto": col_txt, "unidad": col_uni, "valor": col_val}}


# ----------------------------------------------------------------------------------------
# Catálogo de indicadores de SimA y vínculo automático
# ----------------------------------------------------------------------------------------
def catalogo(esc):
    """Lista de (clave, etiqueta) disponibles según la configuración del escenario."""
    out = []
    clases = esc.clases or {}
    for fam, nom in (("disp", "Disponibilidad"), ("util", "Utilización")):
        for clase in modelo.ORDEN_CLASES:
            cfg = clases.get(clase)
            if not cfg:
                continue
            plural = modelo.CLASES[clase]["plural"]
            for t in modelo.CLASES[clase]["tipos"]:
                if t in (cfg.get("tipos") or {}).values():
                    out.append((f"{fam}|{clase}|tipo|{t}", f"{nom} · {plural} · Tipo {t}"))
            for t, en in _combos_energia(cfg) if clase == "perforadoras" else []:
                out.append((f"{fam}|{clase}|energia|{t}|{en}", f"{nom} · {plural} · {t} {en}"))
            for f in cfg.get("flotas", {}):
                out.append((f"{fam}|{clase}|flota|{f}", f"{nom} · {plural} · Flota {f}"))
    if esc.origenes:
        for t in ("Expit", "Rehandle"):
            out.append((f"origen|{t}", f"Tonelaje por Origen · {t}"))
        out.append(("origen|Total", "Tonelaje por Origen · Total Movido"))
    if esc.destinos:
        for t in registro.TIPOS_DESTINO:
            out.append((f"destino|{t}", f"Tonelaje por Destino · {t}"))
    palas = (clases.get("palas") or {}).get("tipos") or {}
    camiones = (clases.get("camiones") or {}).get("tipos") or {}
    if esc.origenes and palas and camiones:
        for t_cam, _f in registro.grupos_camiones(camiones):
            for etq, _p in registro.grupos_palas(palas):
                out.append((f"hang|{etq}|{t_cam}", f"Tiempo de Hang · {etq} – {t_cam}"))
        for td in registro.TIPOS_DESTINO:
            for t_cam, _f in registro.grupos_camiones(camiones):
                out.append((f"descarga|{td}|{t_cam}", f"Cola + Descarga · {td} – {t_cam}"))
    perf = clases.get("perforadoras")
    if perf:
        for t in modelo.CLASES["perforadoras"]["tipos"]:
            if t in (perf.get("tipos") or {}).values():
                out.append((f"taladros|tipo|{t}", f"N° Taladros · Tipo {t}"))
        for f in perf.get("flotas", {}):
            out.append((f"taladros|flota|{f}", f"N° Taladros · Flota {f}"))
    for f in palas:
        out.append((f"material_pala|{f}", f"Material Movido por Pala (Mtpa, promedio por pala) · {f}"))
    for f in palas:
        out.append((f"rend_pala|{f}", f"Rendimiento por Pala (t/h) · {f}"))
    return out


def _combos_energia(cfg):
    """(tipo, fuente de energía) presentes en las perforadoras, en orden."""
    tipos, energia = cfg.get("tipos") or {}, cfg.get("energia") or {}
    vistos = []
    for t in modelo.CLASES["perforadoras"]["tipos"]:
        for en in modelo.ENERGIAS:
            if any(tipos.get(f) == t and energia.get(f) == en for f in tipos) and (t, en) not in vistos:
                vistos.append((t, en))
    return vistos


def _energia_en(texto):
    n = _n(texto)
    e, d = "electr" in n, "diesel" in n
    return "Eléctrica" if e and not d else ("Diésel" if d and not e else None)


def _familia(seccion, unidad):
    s = _n(seccion)
    u = _n(unidad).strip()
    if "origen" in s:
        return "origen"
    if "destino" in s:
        return "destino"
    if "disponib" in s:
        return "disp"
    if "utiliz" in s:
        return "util"
    if "hang" in s or "espera de pala" in s:
        return "hang"
    if "descarga" in s or "cola" in s:
        return "descarga"
    if "taladro" in s:
        return "taladros"
    if "material" in s and "pala" in s or u == "mtpa":
        return "material_pala"
    if "rendimiento" in s or "productiv" in s or u == "tph":
        return "rend_pala"
    return None


def _flota_en(texto, flotas):
    """Flota cuyo nombre (sin espacios) aparece en el texto; la más larga."""
    c = _compacto(texto)
    hallados = [f for f in flotas if _compacto(f) and _compacto(f) in c]
    return max(hallados, key=lambda f: len(_compacto(f))) if hallados else None


def _flotas_en(texto, flotas):
    c = _compacto(texto)
    return [f for f in flotas if _compacto(f) and _compacto(f) in c]


def _tipo_en(texto, tipos):
    n = _compacto(texto)
    for t in tipos:
        raiz = _compacto(t).rstrip("s")
        if raiz and raiz in n:
            return t
    if "ultra" in n:
        for t in tipos:
            if "ultra" in _compacto(t):
                return t
    return None


def claves_de(vinculo):
    """Lista de indicadores de un vínculo (texto = uno; lista = selección múltiple)."""
    if not vinculo:
        return []
    if isinstance(vinculo, (list, tuple)):
        return [str(v) for v in vinculo if v]
    return [str(vinculo)]


def familia(clave):
    """Familia de un indicador: solo se pueden combinar indicadores de la misma familia (y clase)."""
    p = str(clave).split("|")
    return f"{p[0]}|{p[1]}" if p[0] in ("disp", "util") and len(p) > 1 else p[0]


# Cómo se combinan varios indicadores de una familia
COMBINACION = {"origen": "Suma", "destino": "Suma", "taladros": "Suma", "disp": "Ponderada por Horas",
               "util": "Ponderada por Horas", "hang": "Promedio Ponderado por Registros",
               "descarga": "Promedio Ponderado por Registros", "material_pala": "Promedio por Pala",
               "rend_pala": "Ponderado por Horas Productivas"}


def vincular(esc, filas):
    """Sugiere el indicador de SimA para cada ítem del plan (no modifica los textos)."""
    clases = esc.clases or {}
    validos = {k for k, _e in catalogo(esc)}
    seccion = ""
    for f in filas:
        if f["tipo"] == "seccion":
            seccion = f["texto"]
            continue
        f.setdefault("variacion", variacion_por_defecto(f["unidad"]))
        actual = claves_de(f.get("vinculo"))
        if actual and all(c in validos for c in actual):
            continue
        clave = _sugerir(clases, seccion, f["texto"], f["unidad"])
        f["vinculo"] = clave if clave in validos else SIN_VINCULO
    # Un mismo indicador no puede representar dos ítems distintos de una sección: se deja a elección
    por_sec, seccion = {}, ""
    for f in filas:
        if f["tipo"] == "seccion":
            seccion = f["texto"]
        elif f.get("vinculo"):
            por_sec.setdefault((seccion, tuple(claves_de(f["vinculo"]))), []).append(f)
    for lista in por_sec.values():
        if len(lista) > 1:
            for f in lista:
                f["vinculo"] = SIN_VINCULO
                f["revisar"] = True
    return filas


def _sugerir(clases, seccion, texto, unidad):
    fam = _familia(seccion, unidad)
    t = re.sub(r"^\s*\d+(\.\d+)*\.?\s*", "", texto)
    n = _n(t)
    if fam == "origen":
        if "total" in n:
            return "origen|Total"
        if "remanejo" in n or "rehandle" in n:
            return "origen|Rehandle"
        if "expit" in n or "ex pit" in n:
            return "origen|Expit"
        return None
    if fam == "destino":
        if "chancad" in n or "crusher" in n:
            return "destino|Chancador"
        if "stock" in n:
            return "destino|Stockpile"
        if "botader" in n or "desmonte" in n or "dump" in n:
            return "destino|Botadero"
        return None
    if fam in ("disp", "util"):
        if "perfor" in n:
            orden = ["perforadoras"]
        elif "pala" in n:
            orden = ["palas"]
        elif "camion" in n:
            orden = ["camiones"]
        else:
            orden = modelo.ORDEN_CLASES
        for clase in orden:
            cfg = clases.get(clase) or {}
            fl = _flota_en(t, cfg.get("flotas", {}))
            if fl:
                return f"{fam}|{clase}|flota|{fl}"
            tp = _tipo_en(t, modelo.CLASES[clase]["tipos"])
            if tp:
                en = _energia_en(t) if clase == "perforadoras" else None
                if en and (tp, en) in _combos_energia(cfg):
                    return f"{fam}|{clase}|energia|{tp}|{en}"
                return f"{fam}|{clase}|tipo|{tp}"
        return None
    palas = (clases.get("palas") or {}).get("tipos") or {}
    camiones = (clases.get("camiones") or {}).get("tipos") or {}
    if fam == "hang":
        partes = re.split(r"\s[–—-]\s", t)
        izq, der = (partes[0], partes[-1]) if len(partes) > 1 else (t, t)
        etq = None
        fls = _flotas_en(izq, palas)
        hidr = [f for f, tp in palas.items() if tp == "Hidráulicas"]
        if "hidraul" in _n(izq) or (fls and set(fls) == set(hidr) and len(fls) > 1):
            etq = registro.HIDRAULICAS
        elif len(fls) == 1:
            etq = fls[0] if palas.get(fls[0]) != "Hidráulicas" or len(hidr) == 1 else registro.HIDRAULICAS
        tc = _tipo_en(der, modelo.CLASES["camiones"]["tipos"])
        if tc is None:
            fc = _flota_en(der, camiones)
            tc = camiones.get(fc) if fc else None
        return f"hang|{etq}|{tc}" if etq and tc else None
    if fam == "descarga":
        s = _n(seccion)
        td = "Chancador" if "chancad" in s else ("Stockpile" if "stock" in s else (
            "Botadero" if "botader" in s else "Chancador"))
        tc = _tipo_en(t, modelo.CLASES["camiones"]["tipos"])
        if tc is None:
            fc = _flota_en(t, camiones)
            tc = camiones.get(fc) if fc else None
        return f"descarga|{td}|{tc}" if tc else None
    if fam == "taladros":
        perf = clases.get("perforadoras") or {}
        tp = _tipo_en(t, modelo.CLASES["perforadoras"]["tipos"])
        if tp:
            return f"taladros|tipo|{tp}"
        fl = _flota_en(t, perf.get("flotas", {}))
        return f"taladros|flota|{fl}" if fl else None
    if fam in ("material_pala", "rend_pala"):
        fl = _flota_en(t, palas)
        return f"{fam}|{fl}" if fl else None
    return None


def revisar_vinculos(esc, filas):
    """Avisos de vínculos dudosos: indicador de otra familia que su sección o el mismo indicador en
    dos ítems (datos repetidos). Devuelve {índice de fila: motivo}."""
    avisos, seccion, usados = {}, "", {}
    for i, f in enumerate(filas):
        if f["tipo"] == "seccion":
            seccion = f["texto"]
            continue
        lista = claves_de(f.get("vinculo"))
        if not lista:
            continue
        clave = lista[0] if len(lista) == 1 else tuple(sorted(lista))
        fam_sec = _familia(seccion, f.get("unidad") or "")
        partes = lista[0].split("|")
        fam_vin = partes[0]
        if fam_sec and fam_sec != fam_vin:
            avisos[i] = "El indicador no corresponde a la sección"
        elif "flota" in partes and len(lista) == 1:
            # el ítem nombra un tipo (p. ej. «Producción») pero el indicador es de una flota de otro tipo
            clase = partes[1] if fam_vin in ("disp", "util") else ("perforadoras" if fam_vin == "taladros" else None)
            if clase:
                flota = partes[-1]
                tipo_texto = _tipo_en(re.sub(r"\(.*?\)", " ", f["texto"]), modelo.CLASES[clase]["tipos"])
                tipo_flota = ((esc.clases or {}).get(clase) or {}).get("tipos", {}).get(flota)
                if tipo_texto and tipo_flota and tipo_texto != tipo_flota and not _flota_en(f["texto"], [flota]):
                    avisos[i] = f"El ítem es de tipo {tipo_texto} pero el indicador es la flota {flota} ({tipo_flota})"
        if clave in usados:
            avisos[i] = avisos.get(i) or f"Mismo indicador que «{filas[usados[clave]]['texto'].strip()}»"
            avisos.setdefault(usados[clave], f"Mismo indicador que «{f['texto'].strip()}»")
        else:
            usados[clave] = i
    return avisos


def etiqueta(esc, clave, cat=None):
    lista = claves_de(clave)
    if not lista:
        return "Sin Vínculo"
    nombres = dict(cat or catalogo(esc))
    if len(lista) == 1:
        return nombres.get(lista[0], lista[0])
    base = nombres.get(lista[0], lista[0]).split(" · ")[0]
    partes = [nombres.get(c, c).split(" · ")[-1] for c in lista]
    return f"{base} · " + " + ".join(partes) + f"  ({COMBINACION.get(lista[0].split('|')[0], 'Suma')})"


# ----------------------------------------------------------------------------------------
# Valores simulados
# ----------------------------------------------------------------------------------------
def valor(esc, clave, res_rep):
    """Valor de SimA para una réplica (mismas unidades del plan). None si no hay dato. Con varios indicadores
    (misma familia) se suman los tonelajes y taladros y se ponderan los indicadores de tiempo y rendimiento."""
    lista = claves_de(clave)
    if not lista or not res_rep:
        return None
    if len(lista) == 1:
        return _valor1(esc, lista[0], res_rep)
    fam = lista[0].split("|")[0]
    if fam in ("origen", "destino", "taladros"):
        vals = [_valor1(esc, c, res_rep) for c in lista]
        vals = [v for v in vals if v is not None]
        return sum(vals) if vals else None
    if fam in ("disp", "util"):
        s = {k: 0.0 for k in ("tp", "dpp", "dpnp", "tc", "sb")}
        hay = False
        for c in lista:
            for x in _filas_estado(esc, c, res_rep):
                hay = True
                for k in s:
                    s[k] += x.get(k) or 0.0
        if not hay:
            return None
        op = s["tp"] + s["dpp"] + s["dpnp"]
        if fam == "disp":
            return op / (s["tc"] - s["sb"]) if s["tc"] - s["sb"] else None
        return s["tp"] / op if op else None
    cargas = res_rep.get("cargas")
    cfg = esc.clases or {}
    if fam == "hang" and cargas:
        palas = (cfg.get("palas") or {}).get("tipos") or {}
        camiones = (cfg.get("camiones") or {}).get("tipos") or {}
        num = den = 0.0
        for c in lista:
            p = c.split("|")
            prom, n = registro.promedio_hang(cargas, dict(registro.grupos_palas(palas)).get(p[1], []),
                                             dict(registro.grupos_camiones(camiones)).get(p[2], []))
            if prom is not None and n:
                num += prom * n
                den += n
        return num / den if den else None
    if fam == "descarga" and cargas:
        camiones = (cfg.get("camiones") or {}).get("tipos") or {}
        num = den = 0.0
        for c in lista:
            p = c.split("|")
            r = registro.promedio_descarga(cargas, esc.destinos, p[1], dict(registro.grupos_camiones(camiones)).get(p[2], []))
            if r:
                num += r["total"] * r["n"]
                den += r["n"]
        return num / den if den else None
    if fam in ("material_pala", "rend_pala"):
        r = res_rep.get("clases", {}).get("palas")
        filas = [x for x in (r or {}).get("flota", []) if x["nombre"] in {c.split("|")[1] for c in lista}]
        if not filas:
            return None
        m = sum(x["metrica_total"] for x in filas)
        if fam == "material_pala":
            n = sum(x.get("n_equipos") or 0 for x in filas) or 1
            return m / n * 365.0 / float(esc.dias or 365)
        hp = sum(x["horas_productivas"] for x in filas)
        return m * 1e6 / hp if hp else None
    return None


def _filas_estado(esc, clave, res_rep):
    """Filas (flota o tipo) con las horas por estado que componen un indicador de disponibilidad/utilización."""
    p = clave.split("|")
    r = res_rep.get("clases", {}).get(p[1]) if len(p) > 1 else None
    if not r:
        return []
    if p[2] == "energia":
        energia = ((esc.clases or {}).get(p[1]) or {}).get("energia") or {}
        return [x for x in r["flota"] if x.get("tipo") == p[3] and energia.get(x["nombre"]) == p[4]]
    return [x for x in r["flota" if p[2] == "flota" else "tipo"] if x["nombre"] == p[3]]


def _valor1(esc, clave, res_rep):
    p = clave.split("|")
    fam = p[0]
    clases_r = res_rep.get("clases", {})
    cargas = res_rep.get("cargas")
    cfg = esc.clases or {}
    if fam in ("disp", "util") and p[2] == "energia":
        r = clases_r.get(p[1])
        energia = (cfg.get(p[1]) or {}).get("energia") or {}
        if not r:
            return None
        filas = [x for x in r["flota"] if x.get("tipo") == p[3] and energia.get(x["nombre"]) == p[4]]
        if not filas:
            return None
        s = {k: sum(x.get(k) or 0.0 for x in filas) for k in ("tp", "dpp", "dpnp", "tc", "sb")}
        op = s["tp"] + s["dpp"] + s["dpnp"]
        if fam == "disp":
            return op / (s["tc"] - s["sb"]) if s["tc"] - s["sb"] else None
        return s["tp"] / op if op else None
    if fam in ("disp", "util"):
        _f, clase, nivel, nombre = p
        r = clases_r.get(clase)
        if not r:
            return None
        fila = next((x for x in r["flota" if nivel == "flota" else "tipo"] if x["nombre"] == nombre), None)
        return None if fila is None else fila["disponibilidad" if fam == "disp" else "utilizacion"]
    if fam in ("origen", "destino"):
        if not cargas:
            return None
        if fam == "origen":
            r = registro.por_tipo_origen(cargas, esc.origenes)
            t = r["total"] if p[1] == "Total" else r["tipos"].get(p[1], 0.0)
        else:
            t = registro.por_tipo_destino(cargas, esc.destinos)["tipos"].get(p[1], 0.0)
        return t / 1e6
    if fam == "hang":
        if not cargas:
            return None
        palas = (cfg.get("palas") or {}).get("tipos") or {}
        camiones = (cfg.get("camiones") or {}).get("tipos") or {}
        grupo = dict(registro.grupos_palas(palas)).get(p[1], [])
        cams = dict(registro.grupos_camiones(camiones)).get(p[2], [])
        return registro.promedio_hang(cargas, grupo, cams)[0]
    if fam == "descarga":
        if not cargas:
            return None
        camiones = (cfg.get("camiones") or {}).get("tipos") or {}
        cams = dict(registro.grupos_camiones(camiones)).get(p[2], [])
        r = registro.promedio_descarga(cargas, esc.destinos, p[1], cams)
        return r["total"] if r else None
    if fam == "taladros":
        r = clases_r.get("perforadoras")
        if not r:
            return None
        fila = next((x for x in r["flota" if p[1] == "flota" else "tipo"] if x["nombre"] == p[2]), None)
        return None if fila is None else fila["metrica_total"]
    if fam in ("material_pala", "rend_pala"):
        r = clases_r.get("palas")
        if not r:
            return None
        fila = next((x for x in r["flota"] if x["nombre"] == p[1]), None)
        if fila is None:
            return None
        if fam == "material_pala":
            # Mtpa por pala: material de la flota ÷ N° de palas, llevado a un año
            n = fila.get("n_equipos") or 1
            return fila["metrica_total"] / n * 365.0 / float(esc.dias or 365)
        hp = fila["horas_productivas"]
        return fila["metrica_total"] * 1e6 / hp if hp else None
    return None


def variacion(tipo, a, b):
    """A = Plan, B = Simulación."""
    if a is None or b is None:
        return None
    if tipo == "div":
        return b / a if a else None
    if tipo == "dif":
        return (b - a) / a if a else None
    return b - a


def es_porcentaje(fila):
    return "%" in (fila.get("unidad") or "") or "%" in (fila.get("formato") or "")


def decimales(fila):
    u = _n(fila.get("unidad")).strip()
    if es_porcentaje(fila):
        return 2
    return {"mt": 1, "mtpa": 1, "min": 2, "talad": 0, "tph": 0}.get(u, 2)


def texto_valor(fila, v):
    if v is None:
        return "-"
    if es_porcentaje(fila):
        return f"{v * 100:,.2f}%"
    return f"{v:,.{decimales(fila)}f}"


def texto_variacion(fila, tipo, v):
    if v is None:
        return "-"
    if tipo in ("div", "dif"):
        return f"{v * 100:+,.2f}%" if tipo == "dif" else f"{v * 100:,.2f}%"
    if es_porcentaje(fila):
        return f"{v * 100:+,.2f}%"
    return f"{v:+,.{max(decimales(fila), 2) if decimales(fila) else 0}f}"


def formato_excel(fila, columna="valor"):
    """Formato numérico de Excel para valores (plan/simulación) o variaciones."""
    if columna == "var":
        tipo = fila.get("variacion") or "resta"
        if tipo in ("div", "dif") or es_porcentaje(fila):
            return "0.00%"
        return "0.00" if decimales(fila) else "#,##0"
    f = fila.get("formato") or "General"
    if f != "General":
        return f
    if es_porcentaje(fila):
        return "0.00%"
    d = decimales(fila)
    return "#,##0" if d == 0 else "#,##0." + "0" * d


def replicas_resultados(esc):
    """Réplicas individuales calculadas (sin «Todas»), en orden."""
    res = esc.resultados or {}
    por = res.get("por_replica") or {}
    return [r for r in (res.get("replicas") or list(por)) if r != "Todas" and r in por]
