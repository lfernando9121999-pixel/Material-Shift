"""Modelo de análisis de Estados de Equipos (Perforadoras, Palas y Camiones).

Reglas (replican la plantilla de cálculo):
  Tiempo Calendario = Productivo + Det. Proceso Prog. + Det. Proceso No Prog.
                      + Det. Equipo Prog. + Det. Equipo No Prog. + Stand By
  Disponibilidad = (Productivo + Det. Proceso Prog. + Det. Proceso No Prog.)
                   / (Tiempo Calendario - Stand By)
  Utilización    = Productivo / (Productivo + Det. Proceso Prog. + Det. Proceso No Prog.)
Los promedios por flota/tipo son ponderados (cociente de sumas).
Un equipo solo se cuenta si la suma de sus columnas de estado es > 0.
"""
import math


import csvio
from perezoso import np, pd

# Estados -------------------------------------------------------------------
ESTADOS = [
    ("TP", "Tiempo Productivo", "Productivo"),
    ("DPP", "Detención de Proceso Programado", "Det. Proceso Prog."),
    ("DPNP", "Detención de Proceso No Programado", "Det. Proceso No Prog."),
    ("DEP", "Detención de Equipo Programado", "Det. Equipo Prog."),
    ("DENP", "Detención de Equipo No Programado", "Det. Equipo No Prog."),
    ("SB", "Stand By", "Stand By"),
]
CLAVES = [e[0] for e in ESTADOS]
NOMBRE_ESTADO = {e[0]: e[1] for e in ESTADOS}
CORTO_ESTADO = {e[0]: e[2] for e in ESTADOS}
SIN_ASIGNAR = "Sin Asignar"

# Clases de equipo ------------------------------------------------------------
CLASES = {
    "perforadoras": {
        "archivo": "o_estado_perforadoras.csv",
        "singular": "Perforadora", "plural": "Perforadoras",
        "tab": "Estado de Perforadoras",
        "tipos": ["Precorte", "Buffer", "Producción"],
        "tipo_titulo": "Tipo de Perforadoras",
        "metrica": "taladros",
        "metrica_total": "N° Taladros Total", "metrica_prom": "N° Taladros Prom.",
        "metrica_id": "N° Taladros",
    },
    "palas": {
        "archivo": "o_estado_cargadoras.csv",
        "singular": "Pala", "plural": "Palas",
        "tab": "Estado de Palas",
        "tipos": ["Eléctricas", "Hidráulicas"],
        "tipo_titulo": "Tipo de Palas",
        "metrica": "material",
        "metrica_total": "Material Total (Mt)", "metrica_prom": "Material Prom. (Mt)",
        "metrica_id": "Material (Mt)",
    },
    "camiones": {
        "archivo": "o_estado_camiones.csv",
        "singular": "Camión", "plural": "Camiones",
        "tab": "Estado de Camiones",
        "tipos": ["UltraClass", "KOM930"],
        "tipo_titulo": "Tipo de Camiones",
        "metrica": "material",
        "metrica_total": "Material Total (Mt)", "metrica_prom": "Material Prom. (Mt)",
        "metrica_id": "Material (Mt)",
    },
}
ORDEN_CLASES = ["perforadoras", "palas", "camiones"]


def clase_de_archivo(nombre):
    n = nombre.lower()
    for clave, c in CLASES.items():
        if c["archivo"] == n:
            return clave
    return None


# Valores por defecto (derivados de la plantilla de cálculo) -------------------
_DEF_PERF = {
    "produccion": "TP", "desplazamiento": "TP", "espera material": "DPNP",
    "voladura": "DPP", "mant correctivo": "DENP", "mant preventivo": "DEP",
    "mant programado": "DEP", "otras detenciones": "DPP", "cambio turno": "DPP",
    "stand by": "SB",
}
_DEF_PALAS = {
    "espera camion": "TP", "carga": "TP", "posicionamiento": "TP", "desplazamiento": "TP",
    "falta material": "DPNP", "voladura": "DPP", "cambio turno": "DPP",
    "otras detenciones": "DPP", "mant correctivo": "DENP", "mant programado": "DEP",
    "mant preventivo": "DEP", "stand by": "SB",
}
_DEF_CAMIONES = {
    "cola carga": "TP", "cuadrado": "TP", "carga": "TP", "viaje cargado": "TP",
    "cola descarga": "TP", "descarga": "TP", "viaje vacio": "TP",
    "sin cargadora": "DPNP", "sin material": "DPNP",
    "mant correctivo": "DENP", "mant programado": "DEP", "mant preventivo": "DEP",
    "cambio turno": "DPP", "otras detenciones": "DPP", "voladura": "DPP", "stand by": "SB",
}
ESTADOS_DEFECTO = {"perforadoras": _DEF_PERF, "palas": _DEF_PALAS, "camiones": _DEF_CAMIONES}

_TIPOS_DEFECTO = {
    "perforadoras": {"smartrocd65": "Precorte", "dmm2": "Buffer",
                     "49hr320xpc": "Producción", "pv351": "Producción"},
    "palas": {"ex5600 6": "Hidráulicas", "ex5600": "Hidráulicas", "ex8000": "Hidráulicas",
              "p&h4800": "Eléctricas", "p&h4100": "Eléctricas", "p&h4800xpc": "Eléctricas"},
    "camiones": {"kom930": "KOM930", "kom980": "UltraClass", "cat798": "UltraClass"},
}

# Orden de presentación de las actividades (Configuración de Tiempos y Análisis por Tiempos):
# Productivo, Det. Proceso No Prog., Det. Proceso Prog., Det. Equipo No Prog., Det. Equipo Prog., Stand By
_ORDEN_ACTIVIDADES = {
    "perforadoras": ["produccion", "desplazamiento", "espera material", "voladura", "cambio turno",
                     "otras detenciones", "mant correctivo", "mant preventivo", "mant programado",
                     "stand by"],
    "palas": ["espera camion", "carga", "posicionamiento", "desplazamiento", "falta material",
              "voladura", "cambio turno", "otras detenciones", "mant correctivo", "mant programado",
              "mant preventivo", "stand by"],
    "camiones": ["cola carga", "cuadrado", "carga", "viaje cargado", "cola descarga", "descarga",
                 "viaje vacio", "sin cargadora", "sin material", "voladura", "cambio turno",
                 "otras detenciones", "mant correctivo", "mant programado", "mant preventivo",
                 "stand by"],
}


def ordenar_columnas(clase, columnas):
    """Columnas de tiempo en el orden de la plantilla; las no reconocidas, al final (orden del CSV)."""
    orden = _ORDEN_ACTIVIDADES.get(clase, [])
    pos = {n: i for i, n in enumerate(orden)}
    return sorted(columnas, key=lambda c: (pos.get(csvio.norm(c), len(orden)), list(columnas).index(c)))


def _clave_flota(f):
    return "".join(ch for ch in csvio.norm(f) if ch.isalnum() or ch in "& ").replace(" ", "")


def normalizar_tipo(clase, valor):
    """Devuelve la opción de tipo válida (sin distinguir mayúsculas), o None."""
    for t in CLASES[clase]["tipos"]:
        if valor and str(valor).lower() == t.lower():
            return t
    return None


ENERGIAS = ["Eléctrica", "Diésel"]
CATEGORIA = "Categoría"            # (antes «Fuente de Energía»): Eléctrica / Diésel
DIMENSIONES_ORDEN = [("tipo", "Tipo"), ("categoria", CATEGORIA), ("flota", "Flota")]


def dims_orden(clase):
    """Dimensiones con orden de reporte configurable en cada clase (Categoría solo en perforadoras)."""
    return [d for d in DIMENSIONES_ORDEN if d[0] != "categoria" or clase == "perforadoras"]


def orden_normalizado(clase, orden, flotas):
    """Orden de reporte de una clase: {'prioridad': [...], 'tipo': [...], 'categoria': [...], 'flota': [...]}.
    Se conserva lo elegido por el usuario y se completan los valores nuevos (agnóstico a las flotas leídas)."""
    orden = dict(orden or {})
    claves = [k for k, _n in dims_orden(clase)]
    prio = [k for k in (orden.get("prioridad") or []) if k in claves]
    prio += [k for k in claves if k not in prio]
    tipos = list(CLASES[clase]["tipos"])
    sal = {"prioridad": prio,
           "tipo": [t for t in (orden.get("tipo") or []) if t in tipos] + [t for t in tipos if t not in (orden.get("tipo") or [])],
           "flota": [f for f in (orden.get("flota") or []) if f in flotas] + [f for f in flotas if f not in (orden.get("flota") or [])]}
    if clase == "perforadoras":
        cat = orden.get("categoria") or []
        sal["categoria"] = [c for c in cat if c in ENERGIAS] + [c for c in ENERGIAS if c not in cat]
    return sal


def clave_orden_flota(clase, flota, cfg, posicion=0):
    """Orden de reporte según Configuración de Equipos: prioridad de Tipo, Categoría y Flota (por defecto
    Tipo → Categoría → Flota) y el orden de cada lista; sin configuración, el orden del archivo."""
    cfg = cfg or {}
    orden = cfg.get("orden") or orden_normalizado(clase, None, [])
    t = (cfg.get("tipos") or {}).get(flota)
    e = (cfg.get("energia") or {}).get(flota) if clase == "perforadoras" else None
    valores = {"tipo": t, "categoria": e, "flota": flota}
    clave = []
    for d in orden.get("prioridad") or ["tipo", "categoria", "flota"]:
        lista = orden.get(d) or []
        v = valores.get(d)
        clave.append(lista.index(v) if v in lista else (posicion if d == "flota" else len(lista)))
    clave.append(posicion)
    return tuple(clave)


def ordenar_flotas(clase, flotas, cfg):
    flotas = list(flotas)
    return sorted(flotas, key=lambda f: clave_orden_flota(clase, f, cfg, flotas.index(f)))


def ordenar_tipos(clase, tipos, cfg):
    """Tipos en el orden de reporte elegido (los no configurados, al final)."""
    orden = ((cfg or {}).get("orden") or {}).get("tipo") or CLASES[clase]["tipos"]
    tipos = list(tipos)
    return sorted(tipos, key=lambda t: (orden.index(t) if t in orden else len(orden), tipos.index(t)))


def ordenar_resultado(r, clase, cfg):
    """Ordena en el lugar las tablas por Flota, Tipo e ID de un resultado según el orden de reporte."""
    if not r:
        return r
    orden = ordenar_flotas(clase, [f["nombre"] for f in r.get("flota", [])], cfg)
    pos = {f: i for i, f in enumerate(orden)}
    r["flota"] = sorted(r.get("flota", []), key=lambda f: pos.get(f["nombre"], len(pos)))
    if r.get("tipo"):
        tipos = ordenar_tipos(clase, [t["nombre"] for t in r["tipo"]], cfg)
        r["tipo"] = sorted(r["tipo"], key=lambda t: tipos.index(t["nombre"]))
    if r.get("id"):
        ids = list(r["id"])
        r["id"] = sorted(ids, key=lambda e: (pos.get(e.get("flota"), len(pos)), ids.index(e)))
    return r


def ordenar_tiempos(t, clase, cfg):
    if t and t.get("ids"):
        orden = ordenar_flotas(clase, flotas_de(t), cfg)
        pos = {f: i for i, f in enumerate(orden)}
        ids = list(t["ids"])
        t["ids"] = sorted(ids, key=lambda e: (pos.get(e["flota"], len(pos)), ids.index(e)))
    return t


def energia_por_defecto(flota):
    """Fuente de energía sugerida de una perforadora: los modelos XPC (P&H/Komatsu) son eléctricos."""
    c = _clave_flota(flota)
    return "Eléctrica" if ("xpc" in c or "electr" in c) else "Diésel"


def tipo_por_defecto(clase, flota):
    tabla = {k.replace(" ", ""): v for k, v in _TIPOS_DEFECTO[clase].items()}
    return tabla.get(_clave_flota(flota))


def estado_por_defecto(clase, encabezado, previo=None):
    """Prioridad: último valor usado por el usuario > valor de plantilla > sin asignar."""
    if previo:
        v = previo.get(encabezado) or previo.get(csvio.norm(encabezado))
        if v in CLAVES:
            return v
    return ESTADOS_DEFECTO[clase].get(csvio.norm(encabezado))


def diferencias_estandar(clase, mapa):
    """[(columna, estado actual, estado estándar)] de las columnas que difieren de la plantilla."""
    salida = []
    for col, v in (mapa or {}).items():
        est = ESTADOS_DEFECTO[clase].get(csvio.norm(col))
        if est and v != est:
            salida.append((col, v, est))
    return salida


# Lectura de archivos de estado --------------------------------------------------
class DatosEstado:
    """Tabla normalizada de un archivo o_estado_*.csv."""

    def __init__(self, df, columnas_estado, nombre_metrica):
        self.df = df
        self.columnas_estado = columnas_estado
        self.nombre_metrica = nombre_metrica

    @property
    def replicas(self):
        return list(dict.fromkeys(self.df["NREP"].tolist()))

    def nombres_escenario(self):
        return self.df["ESCENARIO"].value_counts()


_COL_METRICA = ("taladros", "carga acum")


def leer_estado(ruta, meta):
    df = csvio.leer_df(ruta, meta)
    cols = list(df.columns)
    claves = [csvio.norm(c) for c in cols]

    def buscar(nombre, defecto):
        return claves.index(nombre) if nombre in claves else defecto

    i_esc, i_rep = buscar("escenario", 0), buscar("nrep", 1)
    i_id, i_flota = buscar("id", 2), buscar("flota", 3)
    if max(i_esc, i_rep, i_id, i_flota) >= len(cols):
        raise csvio.ErrorLectura(
            f"«{meta['nombre']}» no tiene las columnas ESCENARIO, NREP, ID y FLOTA.")
    i_met = None
    for i in range(len(cols) - 1, i_flota, -1):
        if claves[i] in _COL_METRICA:
            i_met = i
            break
    if i_met is None and len(cols) > 28:       # columna AC por posición
        i_met = 28
    fin = i_met if i_met is not None else len(cols)
    estado_idx = [i for i in range(i_flota + 1, fin) if not csvio.es_vacio(cols[i])]
    if not estado_idx:
        raise csvio.ErrorLectura(f"«{meta['nombre']}» no contiene columnas de estados (E a AB).")

    out = pd.DataFrame({
        "ESCENARIO": df.iloc[:, i_esc].astype(str).str.strip(),
        "NREP": csvio.normalizar_replica(df.iloc[:, i_rep]),
        "ID": df.iloc[:, i_id].astype(str).str.strip(),
        "FLOTA": df.iloc[:, i_flota].astype(str).str.strip(),
    })
    nombres = []
    for i in estado_idx:
        nombres.append(cols[i])
        out[cols[i]] = pd.to_numeric(df.iloc[:, i], errors="coerce").fillna(0.0)
    if i_met is not None:
        out["__METRICA__"] = pd.to_numeric(df.iloc[:, i_met], errors="coerce").fillna(0.0)
        nombre_met = cols[i_met]
    else:
        out["__METRICA__"] = 0.0
        nombre_met = ""
    out = out[(out["ID"] != "") & (out["ID"].str.lower() != "nan") & (out["NREP"] != "")]
    return DatosEstado(out.reset_index(drop=True), nombres, nombre_met)


def inventario(datos):
    """Flotas con equipos activos y cantidad de equipos (suma de estados > 0)."""
    d = datos.df
    activo = d[datos.columnas_estado].sum(axis=1) > 0
    act = d[activo]
    flotas = {}
    for flota, g in act.groupby("FLOTA", sort=False):
        flotas[str(flota)] = int(g["ID"].nunique())
    return {"columnas": list(datos.columnas_estado), "flotas": flotas,
            "n_equipos": int(act["ID"].nunique())}


# Cálculo -------------------------------------------------------------------------
def _div(a, b):
    return float(a) / float(b) if b and not math.isclose(float(b), 0.0) else None


def _derivados(fila):
    tp, dpp, dpnp = fila["tp"], fila["dpp"], fila["dpnp"]
    tc = tp + dpp + dpnp + fila["dep"] + fila["denp"] + fila["sb"]
    fila["tc"] = tc
    fila["horas_productivas"] = tp
    fila["disponibilidad"] = _div(tp + dpp + dpnp, tc - fila["sb"])
    fila["utilizacion"] = _div(tp, tp + dpp + dpnp)
    n = fila["n_equipos"]
    fila["metrica_prom"] = _div(fila["metrica_total"], n)
    return fila


def _sumar(grupo):
    fila = {k.lower(): float(grupo[k.lower()].sum()) for k in CLAVES}
    fila["metrica_total"] = float(grupo["metrica"].sum())
    fila["n_equipos"] = int(len(grupo))
    return _derivados(fila)


def _base(datos, clase, replica):
    """Una fila por equipo activo: horas por columna y métrica, para la réplica pedida.

    'Todas' promedia cada equipo entre réplicas (sumarlas multiplicaría las horas).
    """
    d = datos.df
    cols = datos.columnas_estado
    if replica not in (None, "", "Todas"):
        d = d[d["NREP"] == str(replica)]
        if d.empty:
            raise csvio.ErrorLectura(
                f"La réplica «{replica}» no existe en «{CLASES[clase]['archivo']}».")
    base = d.groupby(["NREP", "ID", "FLOTA"], sort=False)[cols + ["__METRICA__"]].sum().reset_index()
    if replica in (None, "", "Todas") and base["NREP"].nunique() > 1:
        base = base.groupby(["ID", "FLOTA"], sort=False)[cols + ["__METRICA__"]].mean().reset_index()
    # Solo equipos con horas > 0 (suma de todas las columnas de estado)
    return base[base[cols].sum(axis=1) > 0].reset_index(drop=True)


def calcular(datos, clase, mapa_estados, tipos, replica):
    """Devuelve un dict serializable con tablas por Flota, Tipo e ID."""
    info = CLASES[clase]
    cols = datos.columnas_estado
    advertencias = []
    base = _base(datos, clase, replica)

    sin_asignar = [c for c in cols if mapa_estados.get(c) not in CLAVES]
    if sin_asignar:
        advertencias.append(
            "Columnas sin estado asignado (no incluidas en el cálculo): " + ", ".join(sin_asignar))

    eq = pd.DataFrame({"ID": base["ID"], "FLOTA": base["FLOTA"]})
    for k in CLAVES:
        usar = [c for c in cols if mapa_estados.get(c) == k]
        eq[k.lower()] = base[usar].sum(axis=1) if usar else 0.0
    metrica = base["__METRICA__"]
    eq["metrica"] = metrica / 1e6 if info["metrica"] == "material" else metrica
    eq["TIPO"] = eq["FLOTA"].map(lambda f: tipos.get(f) or SIN_ASIGNAR)
    sin_tipo = sorted({f for f in eq["FLOTA"] if not tipos.get(f)})
    if sin_tipo:
        advertencias.append("Flotas sin tipo asignado: " + ", ".join(sin_tipo))

    # claves en minúscula coinciden con _sumar
    def tabla_por(col, orden=None):
        filas = []
        grupos = {str(k): g for k, g in eq.groupby(col, sort=False)}
        claves = list(grupos)
        if orden:
            claves = [k for k in orden if k in grupos] + [k for k in claves if k not in orden]
        for k in claves:
            fila = _sumar(grupos[k])
            fila["nombre"] = k
            if col == "FLOTA":
                tps = grupos[k]["TIPO"].unique()
                fila["tipo"] = tps[0] if len(tps) == 1 else ""
            filas.append(fila)
        return filas

    flota = tabla_por("FLOTA")
    ordenes = list(info["tipos"]) + [SIN_ASIGNAR]
    tipo = tabla_por("TIPO", ordenes)
    total = _sumar(eq)
    total["nombre"] = "Total"

    ids = []
    for _, r in eq.iterrows():
        fila = {k.lower(): float(r[k.lower()]) for k in CLAVES}
        fila["metrica_total"] = float(r["metrica"])
        fila["n_equipos"] = 1
        _derivados(fila)
        fila["nombre"] = r["ID"]
        fila["flota"] = r["FLOTA"]
        fila["tipo"] = r["TIPO"]
        ids.append(fila)

    return {
        "clase": clase,
        "n_equipos": int(len(eq)),
        "replica": str(replica) if replica else "Todas",
        "metrica_origen": datos.nombre_metrica,
        "flota": flota, "tipo": tipo, "id": ids, "total": total,
        "advertencias": advertencias,
    }



# Análisis por tiempos (hojas "Analytics by h-eq" y "Analytics by yr-eq") ----------------
# Orden de filas de la plantilla: Producción, Det. Proceso NP, Det. Proceso P, Det. Equipo NP,
# Det. Equipo P, Stand By.
ORDEN_TIEMPOS = ["TP", "DPNP", "DPP", "DENP", "DEP", "SB"]
FILA_TIEMPOS = {"TP": "Producción", "DPNP": "Det. Proceso No Prog.", "DPP": "Det. Proceso Prog.",
                "DENP": "Det. Equipo No Prog.", "DEP": "Det. Equipo Prog.", "SB": "Stand By"}
UNIDADES = {
    "dia": {"boton": "Análisis Diario (h/d-eq)", "titulo": "Análisis Diario de Tiempos",
            "unidad": "h/día-eq", "total": "Horas/Día-Equipo", "decimales": 2},
    "anio": {"boton": "Análisis de Horas-Periodo (h/periodo-eq)", "titulo": "Análisis de Horas-Periodo",
             "unidad": "h/periodo-eq", "total": "Horas/Periodo-Equipo", "decimales": 1},
}


def paso_eje(unidad, dias):
    """Separación del eje en los gráficos de tiempos: 4 h/día (0-4-8-…-24) o su equivalente en el periodo."""
    return 4.0 if unidad == "dia" else 4.0 * float(dias)


def tiempos(datos, clase, mapa_estados, tipos, replica):
    """Horas por actividad de cada equipo (sumas del período) ordenadas por estado."""
    base = _base(datos, clase, replica)
    orden = ordenar_columnas(clase, datos.columnas_estado)
    cols = [c for k in ORDEN_TIEMPOS for c in orden if mapa_estados.get(c) == k]
    ids = []
    for _, r in base.iterrows():
        ids.append({"id": str(r["ID"]), "flota": str(r["FLOTA"]),
                    "tipo": tipos.get(str(r["FLOTA"])) or SIN_ASIGNAR,
                    "h": [round(float(r[c]), 6) for c in cols]})
    return {"columnas": [{"nombre": c, "estado": mapa_estados[c]} for c in cols], "ids": ids}


def flotas_de(t):
    return list(dict.fromkeys(e["flota"] for e in t["ids"]))


def bloque_tiempos(t, ids, unidad="dia", dias=365):
    """Tabla de la hoja Analytics para un grupo de equipos (una flota o una selección de IDs).

    Valor por actividad = Σ horas del grupo / N° equipos / días   (h/día-eq)
                        = Σ horas del grupo / N° equipos          (h/año-eq)
    Disponibilidad y Utilización se calculan con las mismas fórmulas (ponderadas por horas).
    """
    n = len(ids)
    if n == 0:
        return None
    cols = t["columnas"]
    divisor = n * (float(dias) if unidad == "dia" else 1.0)
    valores = [sum(e["h"][j] for e in ids) / divisor for j in range(len(cols))]
    por_estado = {k: 0.0 for k in CLAVES}
    for v, c in zip(valores, cols):
        por_estado[c["estado"]] += v
    tp, dpp, dpnp = por_estado["TP"], por_estado["DPP"], por_estado["DPNP"]
    total = sum(por_estado.values())
    return {"n": n, "valores": valores, "por_estado": por_estado, "total": total,
            "horas_productivas": tp,
            "disponibilidad": _div(tp + dpp + dpnp, total - por_estado["SB"]),
            "utilizacion": _div(tp, tp + dpp + dpnp)}

# Datos para "Análisis de Estados (Pivot)" ---------------------------------------------------
COLS_PIVOT = [("tp", "Horas Productivas (h)"), ("dpp", "Det. Proceso Prog. (h)"),
              ("dpnp", "Det. Proceso No Prog. (h)"), ("dep", "Det. Equipo Prog. (h)"),
              ("denp", "Det. Equipo No Prog. (h)"), ("sb", "Stand By (h)"),
              ("tc", "Tiempo Calendario (h)")]
MEDIDAS_ESTADOS = {
    "N° Equipos": {"tipo": "distinct", "col": "ID", "formato": "int"},
    "Disponibilidad (%)": {"tipo": "ratio", "formato": "pct",
                           "num": ["Horas Productivas (h)", "Det. Proceso Prog. (h)",
                                   "Det. Proceso No Prog. (h)"],
                           "den": ["Tiempo Calendario (h)"], "menos": ["Stand By (h)"]},
    "Utilización (%)": {"tipo": "ratio", "formato": "pct",
                        "num": ["Horas Productivas (h)"],
                        "den": ["Horas Productivas (h)", "Det. Proceso Prog. (h)",
                                "Det. Proceso No Prog. (h)"]},
}


def dataset_estados(resultados, clase, cfg=None):
    """Una fila por equipo y réplica, construida desde los resultados (no requiere los CSV).
    Flota y Tipo se ordenan según el orden de reporte (Configuración de Equipos)."""
    info = CLASES[clase]
    filas = []
    energia = (cfg or {}).get("energia") or {}
    for rep, r in ((resultados or {}).get("por_replica") or {}).items():
        if rep == "Todas" or str(rep).strip().lower() == "nrep":
            continue
        rc = r.get("clases", {}).get(clase)
        if not rc:
            continue
        for e in rc["id"]:
            fila = {"Réplica": str(rep), "Tipo": e.get("tipo", ""), "Flota": e.get("flota", ""),
                    "ID": str(e["nombre"])}
            if clase == "perforadoras":
                fila[CATEGORIA] = energia.get(e.get("flota", ""), "")
            for k, t in COLS_PIVOT:
                fila[t] = float(e.get(k) or 0.0)
            fila[info["metrica_id"]] = float(e.get("metrica_total") or 0.0)
            filas.append(fila)
    df = pd.DataFrame(filas)
    if df.empty:
        return df
    reps = sorted(df["Réplica"].unique(), key=lambda x: (len(x), x))
    df["Réplica"] = pd.Categorical(df["Réplica"], categories=reps, ordered=True)
    flotas = ordenar_flotas(clase, list(dict.fromkeys(df["Flota"])), cfg)
    df["Flota"] = pd.Categorical(df["Flota"], categories=flotas, ordered=True)
    tipos = ordenar_tipos(clase, list(dict.fromkeys(df["Tipo"])), cfg)
    df["Tipo"] = pd.Categorical(df["Tipo"], categories=tipos, ordered=True)
    df["ID"] = pd.Categorical(df["ID"], categories=list(dict.fromkeys(df["ID"])), ordered=True)
    if CATEGORIA in df.columns:
        cats = ((cfg or {}).get("orden") or {}).get("categoria") or ENERGIAS
        presentes = [c for c in cats if c in set(df[CATEGORIA])] + \
                    [c for c in dict.fromkeys(df[CATEGORIA]) if c not in cats]
        df[CATEGORIA] = pd.Categorical(df[CATEGORIA], categories=presentes, ordered=True)
    return df