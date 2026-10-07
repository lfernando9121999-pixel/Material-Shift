"""Registro de cargas (o_registro_cargas.csv): agregados por réplica y reportes de tonelaje y tiempos.

El archivo se recorre una sola vez, por bloques, y se resume en tablas pequeñas por réplica:
  od    : Origen × Destino            → Σ Carga (t)
  hang  : Flota Carguío × Flota Acarreo → Σ tHang (min), N° de registros con tHang
  desc  : Destino × Flota Acarreo      → Σ Cola en Descarga, Σ Descarga (min), N° de registros
  pala  : Flota Carguío × Unidad Carguío → Σ Carga (t)
  est   : Flota Carguío × Flota Acarreo × medida → Σ, N°, mínimo y máximo (carguío, cuadrado, hang,
          colas, descarga y pases) de los registros con carga
  reg   : Flota Carguío × Flota Acarreo → N° de registros con carga y Σ Carga (t)
Los promedios (hang, cola, descarga) son por registro de carga (como el «Promedio» de la tabla
dinámica de la plantilla): Σ valores ÷ N° de registros, también al agrupar flotas o réplicas.
Los registros sin carga (camión que no llegó a cargar) no cuentan en N° de registros ni en los tiempos.
Los tipos de origen/destino se aplican al mostrar, por lo que cambiarlos no requiere recalcular.
"""
import re
from collections import Counter


import csvio
from perezoso import pd

ARCHIVO = "o_registro_cargas.csv"
TIPOS_ORIGEN = ["Expit", "Rehandle", "N/A"]
CONDICIONES = ["Insitu", "Relleno"]
TIPOS_DESTINO = ["Chancador", "Stockpile", "Botadero"]
HIDRAULICAS = "Palas Hidráulicas"

# columna lógica -> (nombres normalizados aceptados, posición por defecto en la plantilla)
_COLUMNAS = {
    "esc": (("escenario",), 0), "nrep": (("nrep",), 1),
    "fa": (("flota acarreo",), 3), "fc": (("flota carguio",), 5), "uc": (("unidad carguio",), 6),
    "o": (("origen",), 7), "d": (("destino",), 8), "t": (("carga",), 9),
    "cola": (("cola en descarga",), 21), "desc": (("descarga",), 22), "hang": (("thang",), 24),
    "td": (("tipo destino",), 26), "h": (("fecha",), 2),
    "cc": (("cola en carga",), 17), "cu": (("cuadrado",), 18), "cg": (("carguio",), 19),
    "ps": (("pases",), 25),
}
# Medidas del registro con estadística (mínimo, promedio por registro y máximo), en el orden de reporte
MEDIDAS_TIEMPO = [("cg", "Tiempo de Carguío", "min"), ("cu", "Tiempo de Cuadrado", "min"),
                  ("hang", "Tiempo de Hang", "min"), ("cc", "Tiempo de Cola en Carga", "min"),
                  ("cola", "Tiempo de Cola en Descarga", "min"), ("desc", "Tiempo de Descarga", "min")]
MEDIDA_PASES = ("ps", "N° de Pases", "pases")
MEDIDA_CARGA = ("t", "Carga por Camión", "t")
_ESTADISTICAS = [k for k, _t, _u in MEDIDAS_TIEMPO] + [MEDIDA_PASES[0], MEDIDA_CARGA[0]]
FASE_REHANDLE = "Rehandle"          # en el Plan de Mina los polígonos sin fase (stocks) se reportan así
_FASE = re.compile(r"(?:^|[_\-\s])(F\d[0-9A-Za-z]*)(?=[_\-\s.]|$)")
SIN_FASE = "Sin Fase"
MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre",
         "Octubre", "Noviembre", "Diciembre"]


def fase_de(origen):
    """Fase del polígono: el primer tramo que inicia con «F» + número hasta un separador (- o _)."""
    m = _FASE.search(str(origen or ""))
    return m.group(1) if m else SIN_FASE


def anio_de_origenes(origenes):
    """Año sugerido por el prefijo AAMM de los polígonos (p. ej. 2701_F11… → 2027); None si no hay."""
    c = Counter()
    for o in origenes:
        m = re.match(r"^(\d{2})(\d{2})[_\-]", str(o))
        if m and 1 <= int(m.group(2)) <= 12:
            c[2000 + int(m.group(1))] += 1
    return c.most_common(1)[0][0] if c else None


def fecha_de_dia(anio, dia):
    """Día n (0 = 1 de enero) del año de simulación → date."""
    import datetime as _dt
    return _dt.date(int(anio), 1, 1) + _dt.timedelta(days=int(dia))
_TEXTO = ("esc", "fa", "fc", "uc", "o", "d", "td")
_TD_CSV = {"botadero": "Botadero", "chancador": "Chancador", "stock pile": "Stockpile",
           "stockpile": "Stockpile"}


def _ubicar(crudas):
    claves = [csvio.norm(c) for c in crudas]
    pos = {}
    for k, (nombres, defecto) in _COLUMNAS.items():
        i = next((claves.index(n) for n in nombres if n in claves), None)
        if i is None and defecto < len(crudas) and k not in ("td",):
            i = defecto
        if i is not None:
            pos[k] = i
    faltan = [k for k in ("nrep", "fa", "fc", "o", "d", "t") if k not in pos]
    if faltan:
        raise csvio.ErrorLectura("o_registro_cargas.csv no tiene las columnas esperadas "
                                 "(NREP, Flota Acarreo, Flota Carguío, Origen, Destino, Carga).")
    return pos


def agregar(ruta, meta, progreso=None, cancelar=None, chunk=1_000_000):
    """Recorre el archivo y devuelve (nombres_escenario: Counter, replicas: set, agregados: dict)."""
    opciones = csvio._opciones(meta)
    crudas = list(pd.read_csv(ruta, nrows=0, **opciones).columns)
    pos = _ubicar(crudas)
    usar = sorted(set(pos.values()))
    nombre_de = {crudas[i]: k for k, i in pos.items()}
    nombres, partes = Counter(), {"od": [], "hang": [], "desc": [], "pala": [], "td": [], "perfil": [],
                                  "est": [], "reg": []}
    total = meta.get("filas") or 0
    leidas = 0
    lector = pd.read_csv(ruta, usecols=usar, chunksize=chunk, low_memory=False,
                         dtype={crudas[pos[k]]: str for k in _TEXTO if k in pos}, **opciones)
    for df in lector:
        if cancelar and cancelar():
            raise csvio.Cancelado()
        df = df.rename(columns=nombre_de)
        for k in _TEXTO:
            if k in df.columns:
                df[k] = df[k].str.strip()
        if "esc" in df.columns:
            nombres.update(df["esc"].dropna().value_counts().to_dict())
        df["nrep"] = csvio.normalizar_replica(df["nrep"].astype(str).str.strip())
        df = df[df["nrep"] != ""]
        for k in ("t", "cola", "desc", "hang", "h", "cc", "cu", "cg", "ps"):
            if k in df.columns:
                df[k] = pd.to_numeric(df[k], errors="coerce")
        con_t = df[df["t"].notna()]
        # Registros con carga (el camión cargó): base de N° de registros y de la estadística de tiempos
        cargado = con_t[con_t["t"] > 0]
        g = cargado.groupby(["nrep", "fc", "fa"], dropna=False)
        partes["reg"].append(g["t"].agg(["count", "sum"]))
        for k in _ESTADISTICAS:
            if k in cargado.columns:
                e = g[k].agg(["sum", "count", "min", "max"])
                e["m"] = k
                partes["est"].append(e.set_index("m", append=True))
        partes["od"].append(con_t.groupby(["nrep", "o", "d"], dropna=False)["t"].sum())
        if "h" in df.columns:
            # Fecha en horas del año: día = parte entera de (horas ÷ 24); 0 = 1 de enero
            p = con_t[con_t["h"].notna()].assign(dia=lambda x: (x["h"] // 24).astype("int64"))
            if "uc" not in p.columns:
                p = p.assign(uc="")
            partes["perfil"].append(p.groupby(["nrep", "dia", "o", "d", "fc", "uc"], dropna=False)["t"].sum())
        if "uc" in df.columns:
            partes["pala"].append(con_t.groupby(["nrep", "fc", "uc"], dropna=False)["t"].sum())
        else:
            partes["pala"].append(con_t.assign(uc="").groupby(["nrep", "fc", "uc"])["t"].sum())
        if "hang" in df.columns:
            h = df[df["hang"].notna()]
            partes["hang"].append(h.groupby(["nrep", "fc", "fa"])["hang"].agg(["sum", "count"]))
        if "cola" in df.columns and "desc" in df.columns:
            dd = df[df["cola"].notna() & df["desc"].notna() & df["d"].notna()]
            partes["desc"].append(dd.groupby(["nrep", "d", "fa"]).agg(
                sc=("cola", "sum"), sd=("desc", "sum"), n=("desc", "count")))
        if "td" in df.columns:
            partes["td"].append(df[df["d"].notna()].groupby(["d", "td"]).size())
        leidas += len(df)
        if progreso and total:
            progreso(min(0.99, leidas / total))

    def unir(lista):
        lista = [x for x in lista if len(x)]
        if not lista:
            return None
        return pd.concat(lista).groupby(level=list(range(lista[0].index.nlevels))).sum()

    por = {}

    def rep(r):
        return por.setdefault(str(r), {"od": [], "hang": [], "desc": [], "pala": [], "perfil": [],
                                       "est": [], "reg": []})

    reg = unir(partes["reg"])
    if reg is not None:
        for (r, fc, fa), fila in reg.iterrows():
            rep(r)["reg"].append([_txt(fc), _txt(fa), int(fila["count"]), round(float(fila["sum"]), 3)])
    est = [x for x in partes["est"] if len(x)]
    if est:
        todo = pd.concat(est).groupby(level=[0, 1, 2, 3], dropna=False).agg(
            {"sum": "sum", "count": "sum", "min": "min", "max": "max"})
        for (r, fc, fa, m), fila in todo.iterrows():
            if fila["count"] > 0:
                rep(r)["est"].append([_txt(fc), _txt(fa), m, round(float(fila["sum"]), 4), int(fila["count"]),
                                      round(float(fila["min"]), 4), round(float(fila["max"]), 4)])

    perfil = unir(partes["perfil"])
    if perfil is not None:
        for (r, dia, o, d, fc, uc), t in perfil.items():
            rep(r)["perfil"].append([int(dia), _txt(o), _txt(d), _txt(fc), _txt(uc), round(float(t), 3)])

    od = unir(partes["od"])
    if od is not None:
        for (r, o, d), t in od.items():
            rep(r)["od"].append([_txt(o), _txt(d), round(float(t), 6)])
    pala = unir(partes["pala"])
    if pala is not None:
        for (r, fc, uc), t in pala.items():
            rep(r)["pala"].append([_txt(fc), _txt(uc), round(float(t), 6)])
    hang = unir(partes["hang"])
    if hang is not None:
        for (r, fc, fa), fila in hang.iterrows():
            rep(r)["hang"].append([_txt(fc), _txt(fa), round(float(fila["sum"]), 6), int(fila["count"])])
    desc = unir(partes["desc"])
    if desc is not None:
        for (r, d, fa), fila in desc.iterrows():
            rep(r)["desc"].append([_txt(d), _txt(fa), round(float(fila["sc"]), 6),
                                   round(float(fila["sd"]), 6), int(fila["n"])])
    td = unir(partes["td"])
    tipo_csv = {}
    if td is not None:
        for (d, t), n in td.sort_values(ascending=False).items():
            tipo_csv.setdefault(_txt(d), _TD_CSV.get(csvio.norm(t)))
    return nombres, set(por), {"por_replica": por, "tipo_destino_csv": tipo_csv}


def _txt(v):
    return "" if v is None or (isinstance(v, float) and v != v) else str(v)


def combinar(lista):
    """Promedio de varias réplicas: tonelajes ÷ N; los promedios conservan Σ/N° (ponderados)."""
    n = len(lista)
    if n == 1:
        return lista[0]
    acc = {"od": {}, "hang": {}, "desc": {}, "pala": {}, "perfil": {}, "est": {}, "reg": {}}
    for r in lista:
        for fc, fa, nn, t in r.get("reg", []):
            a = acc["reg"].setdefault((fc, fa), [0.0, 0.0])
            a[0] += nn / n
            a[1] += t / n
        for fc, fa, m, s, c, mn, mx in r.get("est", []):
            a = acc["est"].get((fc, fa, m))
            if a is None:
                acc["est"][(fc, fa, m)] = [s, c, mn, mx]
            else:
                a[0] += s
                a[1] += c
                a[2] = min(a[2], mn)
                a[3] = max(a[3], mx)
        for dia, o, d, fc, uc, t in r.get("perfil", []):
            k = (dia, o, d, fc, uc)
            acc["perfil"][k] = acc["perfil"].get(k, 0.0) + t / n
        for o, d, t in r.get("od", []):
            acc["od"][(o, d)] = acc["od"].get((o, d), 0.0) + t / n
        for fc, uc, t in r.get("pala", []):
            acc["pala"][(fc, uc)] = acc["pala"].get((fc, uc), 0.0) + t / n
        for fc, fa, s, c in r.get("hang", []):
            a = acc["hang"].setdefault((fc, fa), [0.0, 0])
            a[0] += s
            a[1] += c
        for d, fa, sc, sd, c in r.get("desc", []):
            a = acc["desc"].setdefault((d, fa), [0.0, 0.0, 0])
            a[0] += sc
            a[1] += sd
            a[2] += c
    return {"od": [[o, d, round(t, 6)] for (o, d), t in acc["od"].items()],
            "pala": [[fc, uc, round(t, 6)] for (fc, uc), t in acc["pala"].items()],
            "hang": [[fc, fa, s, c] for (fc, fa), (s, c) in acc["hang"].items()],
            "desc": [[d, fa, sc, sd, c] for (d, fa), (sc, sd, c) in acc["desc"].items()],
            "perfil": [[*k, round(t, 3)] for k, t in acc["perfil"].items()],
            "reg": [[fc, fa, round(nn, 3), round(t, 3)] for (fc, fa), (nn, t) in acc["reg"].items()],
            "est": [[fc, fa, m, s, c, mn, mx] for (fc, fa, m), (s, c, mn, mx) in acc["est"].items()]}


# ----------------------------------------------------------------------------------------
# Configuración de orígenes y destinos
# ----------------------------------------------------------------------------------------
def configurar_od(agregados, previos_o=None, previos_d=None):
    """Lista de orígenes y destinos (valores únicos) con su tipo.

    Origen: «N/A» si no movió carga; «Rehandle» si también es destino (stock re-manipulado);
    «Expit» en otro caso. Condición «Insitu». Destino: según la columna Tipo Destino del
    registro; si no la tiene, «Botadero». Lo que el usuario ya configuró se conserva.
    """
    previos_o, previos_d = previos_o or {}, previos_d or {}
    carga_o, carga_d = Counter(), Counter()
    for r in agregados.get("por_replica", {}).values():
        for o, d, t in r.get("od", []):
            if o:
                carga_o[o] += t
            if d:
                carga_d[d] += t
    n = max(1, len(agregados.get("por_replica", {})))
    destinos_set = set(carga_d)
    origenes = {}
    for o in sorted(carga_o, key=str.lower):
        p = previos_o.get(o) or {}
        tipo = p.get("tipo") if p.get("tipo") in TIPOS_ORIGEN else (
            "N/A" if carga_o[o] <= 0 else ("Rehandle" if o in destinos_set else "Expit"))
        cond = p.get("condicion") if p.get("condicion") in CONDICIONES else "Insitu"
        origenes[o] = {"tipo": tipo, "condicion": cond, "carga": round(carga_o[o] / n, 3), "fase": fase_de(o)}
    tipo_csv = agregados.get("tipo_destino_csv", {})
    destinos = {}
    for d in sorted(carga_d, key=str.lower):
        p = previos_d.get(d) or {}
        tipo = p.get("tipo") if p.get("tipo") in TIPOS_DESTINO else (tipo_csv.get(d) or "Botadero")
        destinos[d] = {"tipo": tipo, "carga": round(carga_d[d] / n, 3), "tipo_csv": tipo_csv.get(d)}
    return origenes, destinos


# ----------------------------------------------------------------------------------------
# Reportes
# ----------------------------------------------------------------------------------------
def _tipo_o(origenes, o):
    return (origenes.get(o) or {}).get("tipo") or "Expit"


def _tipo_d(destinos, d):
    return (destinos.get(d) or {}).get("tipo") or "Botadero"


def por_tipo_origen(cargas, origenes):
    """{'tipos': {tipo: t}, 'detalle': {tipo: [(origen, t)]}, 'total': t}"""
    por_o = Counter()
    for o, _d, t in cargas.get("od", []):
        por_o[o] += t
    tipos, detalle = Counter(), {}
    for o, t in por_o.items():
        k = _tipo_o(origenes, o)
        tipos[k] += t
        detalle.setdefault(k, []).append((o, t))
    for k in detalle:
        detalle[k].sort(key=lambda x: -x[1])
    return {"tipos": dict(tipos), "detalle": detalle, "total": sum(por_o.values())}


def por_tipo_destino(cargas, destinos):
    por_d = Counter()
    for _o, d, t in cargas.get("od", []):
        por_d[d] += t
    tipos, detalle = Counter(), {}
    for d, t in por_d.items():
        if not d:
            continue
        k = _tipo_d(destinos, d)
        tipos[k] += t
        detalle.setdefault(k, []).append((d, t))
    for k in detalle:
        detalle[k].sort(key=lambda x: -x[1])
    return {"tipos": dict(tipos), "detalle": detalle, "total": sum(tipos.values())}


def matriz_flujo(cargas, origenes, destinos):
    """Tonelaje Tipo de Origen (y Condición) × Tipo de Destino."""
    m = {}
    for o, d, t in cargas.get("od", []):
        if not d:
            continue
        cfg = origenes.get(o) or {}
        clave = (_tipo_o(origenes, o), cfg.get("condicion") or "Insitu")
        fila = m.setdefault(clave, Counter())
        fila[_tipo_d(destinos, d)] += t
    return m


def fases_por_tipo(cargas, origenes):
    """{tipo de origen: [(fase, t, [(origen, t), …]), …]} ordenado por tonelaje (grupo «Fases»)."""
    por_o = Counter()
    for o, _d, t in cargas.get("od", []):
        por_o[o] += t
    acc = {}
    for o, t in por_o.items():
        cfg = origenes.get(o) or {}
        fase = cfg.get("fase") or fase_de(o)
        acc.setdefault(_tipo_o(origenes, o), {}).setdefault(fase, []).append((o, t))
    salida = {}
    for tipo, fases in acc.items():
        lista = [(f, sum(t for _o, t in v), sorted(v, key=lambda x: -x[1])) for f, v in fases.items()]
        salida[tipo] = sorted(lista, key=lambda x: (x[0] == SIN_FASE, -x[1]))
    return salida


def flujo_poligonos(cargas, origenes, destinos):
    """{(tipo de origen, condición): {origen: Counter(tipo de destino → t)}} (desglose del flujo)."""
    m = {}
    for o, d, t in cargas.get("od", []):
        if not d:
            continue
        cfg = origenes.get(o) or {}
        clave = (_tipo_o(origenes, o), cfg.get("condicion") or "Insitu")
        m.setdefault(clave, {}).setdefault(o, Counter())[_tipo_d(destinos, d)] += t
    return m


def _flotas_por_tipo(tipos):
    grupos = {}
    for flota, tipo in (tipos or {}).items():
        grupos.setdefault(tipo, []).append(flota)
    return grupos


def grupos_palas(tipos_palas):
    """[(etiqueta, [flotas])]: cada pala eléctrica (o sin tipo) por separado y las hidráulicas juntas."""
    salida, hidr = [], []
    for flota, tipo in (tipos_palas or {}).items():
        if tipo == "Hidráulicas":
            hidr.append(flota)
        else:
            salida.append((flota, [flota]))
    if hidr:
        salida.append((HIDRAULICAS, hidr))
    return salida


def grupos_camiones(tipos_camiones, cfg=None):
    """[(tipo, [flotas])] en el orden de reporte de los tipos de camión (por defecto UltraClass, KOM930)."""
    g = _flotas_por_tipo(tipos_camiones)
    base = ((cfg or {}).get("orden") or {}).get("tipo") or ["UltraClass", "KOM930"]
    orden = [t for t in base if t in g] + [t for t in g if t not in base]
    return [(t, g[t]) for t in orden]


def promedio_hang(cargas, palas, camiones):
    """(promedio min, N° registros) de tHang para un conjunto de flotas de palas y de camiones."""
    s = n = 0
    palas, camiones = set(palas), set(camiones)
    for fc, fa, sm, c in cargas.get("hang", []):
        if fc in palas and fa in camiones:
            s += sm
            n += c
    return (s / n if n else None), n


def tabla_hang(cargas, tipos_palas, tipos_camiones):
    filas = []
    for t_cam, camiones in grupos_camiones(tipos_camiones):
        for etiqueta, palas in grupos_palas(tipos_palas):
            prom, n = promedio_hang(cargas, palas, camiones)
            if n:
                filas.append({"interaccion": f"{etiqueta} – {t_cam}", "pala": etiqueta, "camion": t_cam,
                              "n": n, "min": prom})
    return filas


def promedio_descarga(cargas, destinos, tipo_destino, camiones):
    camiones = set(camiones)
    sc = sd = n = 0
    for d, fa, c1, c2, c in cargas.get("desc", []):
        if fa in camiones and _tipo_d(destinos, d) == tipo_destino:
            sc += c1
            sd += c2
            n += c
    if not n:
        return None
    return {"cola": sc / n, "descarga": sd / n, "total": (sc + sd) / n, "n": n}


def tabla_descarga(cargas, destinos, tipos_camiones):
    filas = []
    for td in TIPOS_DESTINO:
        for t_cam, camiones in grupos_camiones(tipos_camiones):
            r = promedio_descarga(cargas, destinos, td, camiones)
            if r:
                filas.append(dict(r, tipo_destino=td, camion=t_cam))
    return filas


# ----------------------------------------------------------------------------------------
# Tiempos y métricas del registro (Flota de Pala × Tipo de Camión)
# ----------------------------------------------------------------------------------------
ORDEN_TIPOS_PALA = ["Eléctricas", "Hidráulicas"]


def orden_palas(tipos_palas, cfg=None):
    """Flotas de palas en el orden de reporte (Configuración de Equipos); por defecto Eléctricas, luego
    Hidráulicas."""
    tipos_palas = tipos_palas or {}
    fl = list(tipos_palas)
    if cfg is not None:
        import modelo
        return modelo.ordenar_flotas("palas", fl, dict(cfg, tipos=tipos_palas))
    return sorted(fl, key=lambda f: (ORDEN_TIPOS_PALA.index(tipos_palas[f]) if tipos_palas.get(f) in ORDEN_TIPOS_PALA
                                     else len(ORDEN_TIPOS_PALA), fl.index(f)))


def _ejes(claves, tipos_palas, tipos_camiones, cfg_p=None, cfg_c=None):
    palas = orden_palas(tipos_palas, cfg_p)
    palas += sorted({p for p, _t in claves} - set(palas))
    camiones = [t for t, _f in grupos_camiones(tipos_camiones, cfg_c)]
    camiones += sorted({t for _p, t in claves} - set(camiones))
    return palas, camiones


def tiene_estadisticas(cargas):
    return bool(cargas and cargas.get("est"))


def tabla_estadistica(cargas, medida, tipos_palas, tipos_camiones, cfg_p=None, cfg_c=None):
    """[{pala, camion, n, min, prom, max}] por Flota de Pala × Tipo de Camión (promedio por registro)."""
    tc = tipos_camiones or {}
    acc = {}
    for fc, fa, m, s, c, mn, mx in (cargas or {}).get("est", []):
        if m != medida or not c:
            continue
        a = acc.setdefault((fc, tc.get(fa) or fa or "Sin Tipo"), [0.0, 0, mn, mx])
        if a[1]:
            a[2], a[3] = min(a[2], mn), max(a[3], mx)
        a[0] += s
        a[1] += c
    palas, camiones = _ejes(acc, tipos_palas, tc, cfg_p, cfg_c)
    filas = []
    for p in palas:
        for t in camiones:
            a = acc.get((p, t))
            if a and a[1]:
                filas.append({"pala": p, "camion": t, "n": a[1], "min": a[2], "prom": a[0] / a[1], "max": a[3]})
    return filas


def tabla_registro(cargas, tipos_palas, tipos_camiones, cfg_p=None, cfg_c=None):
    """Cuadro de doble entrada Flota de Pala × Tipo de Camión: N° de registros con carga y tonelaje (t)."""
    tc = tipos_camiones or {}
    n, t = Counter(), Counter()
    for fc, fa, nn, tt in (cargas or {}).get("reg", []):
        k = (fc, tc.get(fa) or fa or "Sin Tipo")
        n[k] += nn
        t[k] += tt
    palas, camiones = _ejes(n, tipos_palas, tc, cfg_p, cfg_c)
    palas = [p for p in palas if any(n.get((p, c)) for c in camiones)]
    camiones = [c for c in camiones if any(n.get((p, c)) for p in palas)]
    return {"palas": palas, "camiones": camiones, "n": dict(n), "t": dict(t)}


# ----------------------------------------------------------------------------------------
# Perfil de Alimentación (tonelaje por día o mes, por Fase, Flota e ID de pala)
# ----------------------------------------------------------------------------------------
def id_pala(uc, fc):
    """ID de pala con su flota: «SH001 - P&H4800XPC», «Bin1 - BIN»."""
    uc, fc = str(uc or "").strip(), str(fc or "").strip()
    return f"{uc} - {fc}" if uc and fc else (uc or fc)


def fase_plan(fase):
    """Fase del Plan de Mina: los polígonos sin fase (stocks de remanejo) se reportan como «Rehandle»."""
    return FASE_REHANDLE if fase == SIN_FASE else fase


MESES_CORTOS = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
MODOS_PERIODO = [("dia", "Día"), ("semana", "Semana"), ("mes", "Mes")]
NOMBRE_PERIODO = {"mes": "Mes", "semana": "Semana", "dia": "Día"}
PLURAL_PERIODO = {"mes": "meses", "semana": "semanas", "dia": "días"}


def _periodo(anio, dia, modo):
    """(clave ordenable, rótulo): mes en nombre propio, «Sem N» (semana del año) o DD/MMM."""
    f = fecha_de_dia(anio, dia)
    if modo == "dia":
        return (f.year, f.month, f.day), f"{f.day:02d}/{MESES_CORTOS[f.month - 1]}"
    if modo == "semana":
        semana = (f.timetuple().tm_yday - 1) // 7 + 1
        return (f.year, 0, semana), f"Sem {semana}"
    return (f.year, f.month, 0), MESES[f.month - 1]


def _etq_mes(anio, f):
    return MESES[f.month - 1] + ("" if f.year == int(anio) else f" {f.year}")


def _fase_o(origenes, o):
    return fase_plan((origenes.get(o) or {}).get("fase") or fase_de(o))


def opciones_perfil(cargas, anio, origenes, destinos, orden_flotas=None):
    """Valores disponibles para los filtros del Plan de Mina."""
    fases, flotas, ids, tdest, torig, meses = set(), set(), set(), set(), set(), {}
    for dia, o, d, fc, uc, _t in cargas.get("perfil", []):
        fases.add(_fase_o(origenes, o))
        flotas.add(fc)
        ids.add(id_pala(uc, fc))
        tdest.add(_tipo_d(destinos, d) if d else "Sin Destino")
        torig.add(_tipo_o(origenes, o))
        f = fecha_de_dia(anio, dia)
        meses[(f.year, f.month)] = _etq_mes(anio, f)
    pos = {f: i for i, f in enumerate(orden_flotas or [])}
    return {"fase": sorted(fases, key=lambda x: (x == FASE_REHANDLE, x)),
            "flota": sorted(flotas, key=lambda f: (pos.get(f, len(pos)), f)),
            "id": sorted(ids, key=lambda i: (pos.get(i.split(" - ")[-1], len(pos)), i)),
            "tipo_destino": [t for t in TIPOS_DESTINO + ["Sin Destino"] if t in tdest],
            "tipo_origen": [t for t in TIPOS_ORIGEN if t in torig],
            "mes": [meses[k] for k in sorted(meses)]}


def tabla_perfil(cargas, anio, modo, origenes, destinos, filtros=None, orden_flotas=None):
    """{'periodos': [...], 'filas': [{'fase','flota','id','valores','total'}], 'totales': [...], 'total'}

    modo: 'dia', 'semana' o 'mes'. filtros: {'mes', 'fase', 'flota', 'id', 'tipo_destino', 'tipo_origen'};
    None = todos. El filtro de mes se aplica en cualquier periodicidad.
    """
    filtros = dict(filtros or {})
    if "periodo" in filtros:                       # escenarios v1.3: el filtro de periodo era de meses
        p = filtros.pop("periodo")
        if modo == "mes" and filtros.get("mes") is None:
            filtros["mes"] = p
    sel = {k: (set(v) if v is not None else None) for k, v in filtros.items()}
    claves_p, celdas = {}, {}
    cache_f = {}
    for dia, o, d, fc, uc, t in cargas.get("perfil", []):
        fase = _fase_o(origenes, o)
        ip = id_pala(uc, fc)
        td = _tipo_d(destinos, d) if d else "Sin Destino"
        to = _tipo_o(origenes, o)
        if dia not in cache_f:
            f = fecha_de_dia(anio, dia)
            cache_f[dia] = (_periodo(anio, dia, modo), _etq_mes(anio, f))
        (kp, etq), mes = cache_f[dia]
        for k, v in (("fase", fase), ("flota", fc), ("id", ip), ("tipo_destino", td), ("mes", mes),
                     ("tipo_origen", to)):
            if sel.get(k) is not None and v not in sel[k]:
                break
        else:
            claves_p[kp] = etq
            fila = celdas.setdefault((fase, fc, ip), {})
            fila[kp] = fila.get(kp, 0.0) + t
    orden = sorted(claves_p)
    if len({k[0] for k in orden}) > 1:          # el periodo cruza de año: se agrega el año al rótulo
        for k in orden:
            claves_p[k] = f"{claves_p[k]}/{k[0]}" if modo == "dia" else f"{claves_p[k]} {k[0]}"
    filas, totales = [], [0.0] * len(orden)
    pos_fl = {f: i for i, f in enumerate(orden_flotas or [])}
    for (fase, fc, ip) in sorted(celdas, key=lambda x: (x[0] == FASE_REHANDLE, x[0], pos_fl.get(x[1], len(pos_fl)),
                                                        x[1], x[2])):
        vals = [celdas[(fase, fc, ip)].get(k, 0.0) for k in orden]
        for i, v in enumerate(vals):
            totales[i] += v
        filas.append({"fase": fase, "flota": fc, "id": ip, "valores": vals, "total": sum(vals)})
    return {"periodos": [claves_p[k] for k in orden], "filas": filas, "totales": totales, "total": sum(totales)}


MEDIDAS_REGISTRO = {"N° de Réplicas": {"tipo": "distinct", "col": "Réplica", "formato": "int"}}


def preparar_df_registro(df, anio):
    """Campos para el pivote del registro: Réplica (número de réplica), Fecha, Mes, Fase e ID Pala."""
    claves = {csvio.norm(c): c for c in df.columns}
    if "nrep" in claves:
        s = df[claves["nrep"]]
        num = pd.to_numeric(s.astype(str).str.strip(), errors="coerce")
        if num.notna().any():
            # filas sin número de réplica (p. ej. un encabezado «NREP» repetido) no son datos
            df = df[num.notna()].copy()
            rep = num[num.notna()].round().astype("int64").astype(str)
        else:
            rep = s.astype(str).str.strip()
            rep = rep.where(rep.str.lower() != "nrep")
        orden = sorted(rep.dropna().unique(), key=lambda x: (len(x), x))
        df["Réplica"] = pd.Categorical(rep, categories=orden, ordered=True)
        df = df.drop(columns=[claves["nrep"]])
    # la columna original «Fecha» está en horas del año: se conserva como «Hora del Año (h)»
    if "Hora del Año (h)" not in df.columns and "fecha" in claves:
        df = df.rename(columns={claves["fecha"]: "Hora del Año (h)"})
    if "Hora del Año (h)" in df.columns and anio:
        h = df["Hora del Año (h)"].astype("float64")
        dia = (h // 24)
        dias = sorted(int(x) for x in dia.dropna().unique())
        fechas = {d: fecha_de_dia(anio, d) for d in dias}
        etq_f = {d: f.strftime("%d/%m/%Y") for d, f in fechas.items()}
        df["Fecha"] = pd.Categorical(dia.map(etq_f), categories=list(dict.fromkeys(etq_f[d] for d in dias)), ordered=True)
        meses = {d: MESES[f.month - 1] + ("" if f.year == int(anio) else f" {f.year}") for d, f in fechas.items()}
        df["Mes"] = pd.Categorical(dia.map(meses), categories=list(dict.fromkeys(meses[d] for d in dias)), ordered=True)
        semanas = {d: _periodo(anio, d, "semana")[1] + ("" if f.year == int(anio) else f" {f.year}")
                   for d, f in fechas.items()}
        df["Semana"] = pd.Categorical(dia.map(semanas), categories=list(dict.fromkeys(semanas[d] for d in dias)),
                                      ordered=True)
    if "origen" in claves:
        o = df[claves["origen"]].astype("category")
        df["Fase"] = o.map({c: fase_plan(fase_de(c)) for c in o.cat.categories}).astype("category")
    if "unidad carguio" in claves and "flota carguio" in claves:
        uc, fc = claves["unidad carguio"], claves["flota carguio"]
        df["ID Pala"] = (df[uc].astype(str) + " - " + df[fc].astype(str)).astype("category")
    df.attrs["anio"] = anio
    return df


def material_por_pala_registro(cargas):
    """Σ Carga (t) por flota de carguío según el registro."""
    out = Counter()
    for fc, _uc, t in cargas.get("pala", []):
        out[fc] += t
    return dict(out)
