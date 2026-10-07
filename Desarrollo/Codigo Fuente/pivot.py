"""Motor de tabla dinámica (sin interfaz).

calcular_cubo(): resume los datos en todos los niveles de Filas y Columnas (con subtotales y totales
generales) para mostrarlos agrupados y desplegables. Las medidas ponderadas (Disponibilidad, Utilización,
Promedio Ponderado y Promedio) se calculan como cociente de sumas en cada celda, subtotal y total, con
cualquier filtro. Los campos calculados (expresiones tipo Excel) pueden ser por fila (un campo más) o de
resumen (se evalúan en cada celda).

calcular(): versión plana (todo desplegado, sin subtotales) para exportar y graficar.
"""
import copy
import math

import expresiones as ex
from perezoso import np, pd

RECUENTO = "Recuento de Filas"
AGREGACIONES = {
    "sum": ("Suma", "sum"),
    "mean": ("Promedio", "mean"),
    "count": ("Cuenta", "count"),
    "nunique": ("Cuenta Distinta", "nunique"),
    "min": ("Mínimo", "min"),
    "max": ("Máximo", "max"),
    "median": ("Mediana", "median"),
    "wmean": ("Promedio Ponderado", "wmean"),
}
TOTAL = "Total General"
MAX_FILAS = 20000
MAX_COLUMNAS = 400
SEP = "\n"
MOSTRAR_COMO = {None: "Valor", "pct_total": "% del Total General", "pct_fila": "% del Total de la Fila",
                "pct_col": "% del Total de la Columna"}
_ABREV = {"pct_total": "Total", "pct_fila": "Fila", "pct_col": "Columna"}
OPCIONES = {"totales_generales_filas": True, "totales_generales_columnas": True, "subtotales_filas": True,
            "subtotales_columnas": True, "encabezados_columnas": True, "encabezados_filas": True,
            "lineas_horizontales": True, "lineas_verticales": True, "encabezados_filtro": True,
            "campos_visibles": True, "auto": True}
FORMATOS = {"#,##0": "Entero (#,##0)", "#,##0.0": "Un Decimal (#,##0.0)", "#,##0.00": "Dos Decimales (#,##0.00)",
            "#,##0.000": "Tres Decimales (#,##0.000)", "0.0%": "Porcentaje (0.0%)", "0.00%": "Porcentaje (0.00%)",
            "General": "Automático"}


class ErrorPivot(Exception):
    pass


def opciones(cfg):
    """Opciones de presentación (con equivalencia de las claves de versiones anteriores)."""
    o = dict(OPCIONES)
    if "totales_filas" in cfg:
        o["totales_generales_columnas"] = bool(cfg["totales_filas"])
    if "totales_columnas" in cfg:
        o["totales_generales_filas"] = bool(cfg["totales_columnas"])
    if "auto" in cfg:
        o["auto"] = bool(cfg["auto"])
    o.update({k: bool(v) for k, v in (cfg.get("opciones") or {}).items() if k in OPCIONES})
    return o


def es_numerico(serie):
    return pd.api.types.is_numeric_dtype(serie.dtype) and not pd.api.types.is_bool_dtype(serie.dtype)


def campos_ocultos(df):
    """Columnas que no se ofrecen como campos (p. ej. el NREP original: la réplica es «Réplica»)."""
    return {c for c in df.columns if str(c).strip().lower() in ("nrep",)}


def nombres_campos(df, medidas=None, cfg=None):
    calc = [e["nombre"] for e in (cfg or {}).get("expresiones", []) if e.get("nombre")]
    ocultos = campos_ocultos(df)
    return [RECUENTO] + list(medidas or {}) + [c for c in df.columns if c not in ocultos] + \
        [c for c in calc if c not in df.columns]


def campo_numerico(df, campo, medidas=None):
    return campo == RECUENTO or campo in (medidas or {}) or (campo in df.columns and es_numerico(df[campo]))


def agregacion_por_defecto(df, campo, medidas=None):
    if campo in (medidas or {}):
        return "medida"
    return "sum" if campo_numerico(df, campo) else "count"


def agregaciones_validas(df, campo, medidas=None):
    if campo in (medidas or {}):
        return []
    if campo_numerico(df, campo):
        return [k for k in AGREGACIONES if k != "wmean"]
    return ["count", "nunique"]


def valores_filtro(df, campo, otros_filtros=None):
    """Valores únicos (categóricos) o rango (numéricos) para el filtro. Con otros_filtros solo se ofrecen los
    valores que existen con los demás filtros activos (filtros en cascada)."""
    s = df[campo]
    m = _mascara(df, otros_filtros or [])
    if m is not None:
        s = s[m]
    if es_numerico(s):
        if len(s) == 0 or s.isna().all():
            return {"numerico": True, "min": 0.0, "max": 0.0}
        return {"numerico": True, "min": float(np.nanmin(s)), "max": float(np.nanmax(s))}
    if isinstance(s.dtype, pd.CategoricalDtype):
        presentes = set(s.dropna().unique()) if m is not None else None
        valores = [str(v) for v in s.cat.categories if presentes is None or v in presentes]
    else:
        valores = sorted(map(str, s.dropna().unique()))
    return {"numerico": False, "valores": [v for v in valores if v.strip().lower() != "nrep"]}


def n_distintos(df, campo):
    try:
        return int(df[campo].nunique(dropna=True))
    except (KeyError, TypeError):
        return 0


def _mascara(df, filtros):
    mascara = None
    for f in filtros:
        campo = f["campo"]
        if campo not in df.columns:
            continue
        s = df[campo]
        if f.get("incluir") is not None:
            m = s.astype(str).isin([str(v) for v in f["incluir"]]) if not isinstance(
                s.dtype, pd.CategoricalDtype) else s.isin(list(f["incluir"]))
        elif f.get("min") is not None or f.get("max") is not None:
            m = pd.Series(True, index=df.index)
            if f.get("min") is not None:
                m &= s >= f["min"]
            if f.get("max") is not None:
                m &= s <= f["max"]
        else:
            continue
        mascara = m if mascara is None else (mascara & m)
    return mascara


def filtro_activo(f):
    return f.get("incluir") is not None or f.get("min") is not None or f.get("max") is not None


def _etiqueta_intervalo(v, ancho):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return ""
    return f"{v:,.6g} – {v + ancho:,.6g}"


def _texto(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return ""
    if isinstance(v, (float, np.floating)):
        return f"{v:,.6g}"
    return str(v)


def _num(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) or math.isinf(x) else x


# ----------------------------------------------------------------------------------------
# Campos calculados
# ----------------------------------------------------------------------------------------
def preparar_expresiones(df, cfg):
    """Agrega al DataFrame los campos calculados por fila y devuelve (df, medidas de resumen, avisos)."""
    exprs = [e for e in (cfg.get("expresiones") or []) if e.get("nombre") and e.get("expresion")]
    if not exprs:
        return df, {}, []
    trabajo = df
    resumen, avisos = {}, []
    disponibles = set(df.columns)
    for e in exprs:
        try:
            nodo, es_res = ex.validar(e["expresion"], disponibles)
        except ex.ErrorExpresion as err:
            avisos.append(f"Campo calculado «{e['nombre']}»: {err}")
            continue
        if es_res:
            resumen[e["nombre"]] = {"tipo": "expr", "nodo": nodo, "agregados": ex.agregados_usados(nodo),
                                    "formato": "num"}
        else:
            if trabajo is df:
                trabajo = df.copy()
            try:
                trabajo[e["nombre"]] = ex.columna_fila(trabajo, nodo)
            except Exception as err:  # noqa
                avisos.append(f"Campo calculado «{e['nombre']}»: {err}")
                continue
        disponibles.add(e["nombre"])
    return trabajo, resumen, avisos


# ----------------------------------------------------------------------------------------
# Cubo
# ----------------------------------------------------------------------------------------
_COMPOSABLE = {"sum": "sum", "min": "min", "max": "max"}


def nombre_valor(v, medidas=None, cfg=None, repetidos=None):
    """Nombre del valor sin «Suma de» (ya se sabe cómo se calcula); si el mismo campo se usa con dos
    resúmenes distintos se aclara entre paréntesis."""
    campo = v["campo"]
    titulo = ((cfg or {}).get("titulos") or {}).get(campo) or campo
    agg = v.get("agg") or "sum"
    if repetidos and campo in repetidos and agg not in ("medida", None) and campo != RECUENTO:
        if agg == "wmean":
            return f"{titulo} (Ponderado por {v.get('peso', '–')})"
        return f"{titulo} ({AGREGACIONES.get(agg, AGREGACIONES['sum'])[0]})"
    return titulo


def calcular_cubo(df, cfg, medidas=None):
    """Devuelve el cubo: dims, valores, árboles de filas y columnas y celdas por nivel."""
    medidas = dict(medidas or {})
    cfg = copy.deepcopy(cfg)
    df, med_expr, avisos = preparar_expresiones(df, cfg)
    medidas.update(med_expr)
    ocultos = campos_ocultos(df)
    filas_c = [f for f in cfg.get("filas", []) if f["campo"] in df.columns and f["campo"] not in ocultos]
    cols_c = [f for f in cfg.get("columnas", []) if f["campo"] in df.columns and f["campo"] not in ocultos]
    vals_c = [v for v in cfg.get("valores", [])
              if v["campo"] == RECUENTO or v["campo"] in df.columns or v["campo"] in medidas]
    filtros = [f for f in cfg.get("filtros", []) if f["campo"] in df.columns]
    if not vals_c:
        vals_c = [{"campo": RECUENTO, "agg": "sum"}]
    mascara = _mascara(df, filtros)
    sub = df if mascara is None else df[mascara]
    if len(sub) == 0:
        raise ErrorPivot("Los filtros actuales no dejan ninguna fila.")

    trabajo = pd.DataFrame(index=sub.index)
    dims = []
    for lista, rol in ((filas_c, "f"), (cols_c, "c")):
        for i, d in enumerate(lista):
            nombre = f"{rol}{i}"
            s = sub[d["campo"]]
            if d.get("intervalo") and es_numerico(s):
                w = float(d["intervalo"])
                trabajo[nombre] = np.floor(s.astype("float64") / w) * w
            else:
                trabajo[nombre] = s
            d["_col"] = nombre
            dims.append(nombre)

    aux, funcs = {}, {}                 # columnas auxiliares componibles: nombre -> serie, función
    no_comp = []                         # (col, serie, función) no componibles (cuenta distinta, mediana)
    specs = []                           # (tipo, datos) por valor
    formatos = []

    def aux_col(clave, serie, func):
        if clave not in aux:
            aux[clave] = serie
            funcs[clave] = func
        return clave
    repetidos = {c for c in [v["campo"] for v in vals_c] if [v["campo"] for v in vals_c].count(c) > 1}
    fmt_usuario = cfg.get("formatos_campo") or {}
    for j, v in enumerate(vals_c):
        campo = v["campo"]
        agg = v.get("agg") or (agregacion_por_defecto(df, campo, medidas) if campo in df.columns else "sum")
        if campo in medidas:
            m = medidas[campo]
            if m["tipo"] == "ratio":
                num = sum((sub[c].astype("float64") for c in m["num"]), 0.0)
                den = sum((sub[c].astype("float64") for c in m["den"]), 0.0) \
                    - sum((sub[c].astype("float64") for c in m.get("menos", [])), 0.0)
                specs.append(("cociente", (aux_col(f"v{j}n", num, "sum"), aux_col(f"v{j}d", den, "sum"))))
            elif m["tipo"] == "distinct":
                no_comp.append((f"v{j}", sub[m["col"]], "nunique"))
                specs.append(("directo", f"v{j}"))
            elif m["tipo"] == "expr":
                refs = {}
                for f_, c_ in m["agregados"]:
                    s = sub[c_]
                    s_num = pd.to_numeric(s, errors="coerce") if not es_numerico(s) else s.astype("float64")
                    if f_ == "SUMA":
                        refs[(f_, c_)] = ("aux", aux_col(f"e_s_{c_}", s_num, "sum"))
                    elif f_ == "CONTAR":
                        refs[(f_, c_)] = ("aux", aux_col(f"e_n_{c_}", s.notna().astype("float64"), "sum"))
                    elif f_ == "PROMEDIO":
                        refs[(f_, c_)] = ("prom", aux_col(f"e_s_{c_}", s_num, "sum"),
                                          aux_col(f"e_n_{c_}", s_num.notna().astype("float64"), "sum"))
                    elif f_ == "MINIMO":
                        refs[(f_, c_)] = ("aux", aux_col(f"e_mn_{c_}", s_num, "min"))
                    else:
                        refs[(f_, c_)] = ("aux", aux_col(f"e_mx_{c_}", s_num, "max"))
                specs.append(("expr", (m["nodo"], refs)))
            formatos.append(m.get("formato", "num"))
            continue
        if campo == RECUENTO:
            specs.append(("directo_aux", aux_col("recuento", pd.Series(1.0, index=sub.index), "sum")))
            formatos.append("int")
            continue
        s = sub[campo]
        numerico = es_numerico(s)
        x = s.astype("float64") if numerico else s
        if agg == "wmean" and v.get("peso") in df.columns and numerico:
            w = sub[v["peso"]].astype("float64").where(x.notna())
            specs.append(("cociente", (aux_col(f"v{j}n", x * w, "sum"), aux_col(f"v{j}d", w, "sum"))))
            formatos.append("num")
        elif agg in ("sum",) and numerico:
            specs.append(("directo_aux", aux_col(f"v{j}s", x, "sum")))
            formatos.append("num")
        elif agg == "mean" and numerico:
            specs.append(("cociente", (aux_col(f"v{j}s", x, "sum"), aux_col(f"v{j}c", x.notna().astype("float64"), "sum"))))
            formatos.append("num")
        elif agg in ("min", "max") and numerico:
            specs.append(("directo_aux", aux_col(f"v{j}{agg}", x, agg)))
            formatos.append("num")
        elif agg == "nunique":
            no_comp.append((f"v{j}", s, "nunique"))
            specs.append(("directo", f"v{j}"))
            formatos.append("int")
        elif agg == "median" and numerico:
            no_comp.append((f"v{j}", x, "median"))
            specs.append(("directo", f"v{j}"))
            formatos.append("num")
        else:                                           # cuenta (también para textos)
            specs.append(("directo_aux", aux_col(f"v{j}c", s.notna().astype("float64"), "sum")))
            formatos.append("int")
        if campo in fmt_usuario and fmt_usuario[campo] not in (None, "General"):
            formatos[-1] = fmt_usuario[campo]
    nombres = [nombre_valor(v, medidas, cfg, repetidos) for v in vals_c]
    modos = [v.get("mostrar") if v.get("mostrar") in MOSTRAR_COMO else None for v in vals_c]

    for c, s in aux.items():
        trabajo[c] = s
    f_cols = [d["_col"] for d in filas_c]
    c_cols = [d["_col"] for d in cols_c]
    todas = f_cols + c_cols
    fmap = {c: _COMPOSABLE[f] for c, f in funcs.items()}
    if todas:
        base = trabajo.groupby(todas, observed=True, sort=True)[list(aux)].agg(fmap) if aux else \
            trabajo.groupby(todas, observed=True, sort=True).size().to_frame("_n")[[]]
    else:
        base = None

    def etiqueta(d, valor):
        if d.get("intervalo") and not isinstance(valor, str):
            return _etiqueta_intervalo(valor, float(d["intervalo"]))
        return _texto(valor)

    # árboles de filas y columnas (en el orden de los datos: categorías ordenadas o valores ordenados)
    def arbol(n_ini, n_dims, lista_d):
        raiz, idx = [], {}
        if not n_dims or base is None:
            return raiz, 0
        claves = base.index if isinstance(base.index, pd.MultiIndex) else [(k,) for k in base.index]
        hojas = 0
        vistos = set()
        for k in claves:
            k = k if isinstance(k, tuple) else (k,)
            parte = tuple(etiqueta(lista_d[i], k[n_ini + i]) for i in range(n_dims))
            if parte in vistos:
                continue
            vistos.add(parte)
            hojas += 1
            nivel = raiz
            for i in range(n_dims):
                ruta = parte[:i + 1]
                nodo = idx.get(ruta)
                if nodo is None:
                    nodo = {"etq": parte[i], "ruta": ruta, "hijos": []}
                    idx[ruta] = nodo
                    nivel.append(nodo)
                nivel = nodo["hijos"]
        return raiz, hojas

    arbol_f, n_hojas_f = arbol(0, len(f_cols), filas_c)
    arbol_c, n_hojas_c = arbol(len(f_cols), len(c_cols), cols_c)
    if n_hojas_f > MAX_FILAS:
        avisos.append(f"La tabla tiene {n_hojas_f:,} filas; se muestran las primeras {MAX_FILAS:,}. Agregue filtros "
                      "o agrupe por intervalo.")
        arbol_f = _recortar(arbol_f, MAX_FILAS)
    if n_hojas_c * len(specs) > MAX_COLUMNAS:
        avisos.append(f"La tabla tiene {n_hojas_c * len(specs):,} columnas; se muestran las primeras {MAX_COLUMNAS}.")
        arbol_c = _recortar(arbol_c, max(1, MAX_COLUMNAS // max(1, len(specs))))

    celdas = {}

    def nivel(i, j):
        claves = f_cols[:i] + c_cols[:j]
        if base is not None and claves:
            agr = base.groupby(level=claves, observed=True, sort=False).agg(fmap) if aux else None
        elif aux:
            agr = pd.DataFrame({c: [getattr(trabajo[c], fmap[c])()] for c in aux})
        else:
            agr = None
        extras = {}
        for col, serie, fn in no_comp:
            if claves:
                s = serie.groupby([trabajo[k] for k in claves], observed=True).agg(fn)
                extras[col] = {(k if isinstance(k, tuple) else (k,)): v for k, v in s.items()}
            else:
                extras[col] = {(): getattr(serie, fn)()}
        if agr is not None:
            indice = [(k if isinstance(k, tuple) else (k,)) if claves else () for k in agr.index]
        elif extras:
            indice = list(next(iter(extras.values())))
        else:
            indice = [()]
        arr = {c: agr[c].to_numpy(dtype="float64", na_value=np.nan) for c in agr.columns} if agr is not None else {}
        for pos, kk in enumerate(indice):
            rp = tuple(etiqueta(filas_c[a], kk[a]) for a in range(i))
            cp = tuple(etiqueta(cols_c[b], kk[i + b]) for b in range(j))
            fila = []
            for t, dato in specs:
                if t == "directo_aux":
                    fila.append(_num(arr[dato][pos]))
                elif t == "cociente":
                    n_, d_ = arr[dato[0]][pos], arr[dato[1]][pos]
                    fila.append(_num(n_ / d_) if d_ else None)
                elif t == "directo":
                    fila.append(_num(extras[dato].get(kk)))
                else:
                    nodo, refs = dato

                    def resolver(ref, pos=pos):
                        if ref[0] == "agg":
                            r = refs[(ref[1], ref[2])]
                            if r[0] == "prom":
                                d_ = arr[r[2]][pos]
                                return arr[r[1]][pos] / d_ if d_ else float("nan")
                            return float(arr[r[1]][pos])
                        raise ex.ErrorExpresion("Campo fuera de una función de resumen.")
                    try:
                        with np.errstate(all="ignore"):
                            r_ = ex.evaluar(nodo, resolver, None)
                        fila.append(_num(r_) if not isinstance(r_, str) else None)
                    except Exception:  # noqa
                        fila.append(None)
            celdas[(rp, cp)] = fila

    for i in range(len(f_cols) + 1):
        for j in range(len(c_cols) + 1):
            nivel(i, j)

    for d in filas_c + cols_c:
        d.pop("_col", None)
    titulos = cfg.get("titulos") or {}
    return {"dims_filas": [titulos.get(d["campo"], d["campo"]) + (f" [{d['intervalo']:g}]" if d.get("intervalo") else "")
                           for d in filas_c],
            "dims_cols": [titulos.get(d["campo"], d["campo"]) + (f" [{d['intervalo']:g}]" if d.get("intervalo") else "")
                          for d in cols_c],
            "valores": nombres, "formatos": [("pct" if modos[k] else f) for k, f in enumerate(formatos)],
            "modos": modos, "arbol_filas": arbol_f, "arbol_cols": arbol_c, "celdas": celdas, "avisos": avisos}


def _recortar(arbol, maximo):
    cuenta = [0]

    def rec(nodos):
        salida = []
        for n in nodos:
            if cuenta[0] >= maximo:
                break
            if n["hijos"]:
                h = rec(n["hijos"])
                if h:
                    salida.append(dict(n, hijos=h))
            else:
                salida.append(n)
                cuenta[0] += 1
        return salida
    return rec(arbol)


def valor(cubo, rp, cp, k):
    """Valor de la celda (fila rp, columna cp, valor k) aplicando «Mostrar Valores Como»."""
    fila = cubo["celdas"].get((tuple(rp), tuple(cp)))
    if fila is None or k >= len(fila) or fila[k] is None:
        return None
    v = fila[k]
    modo = cubo["modos"][k]
    if not modo:
        return v
    if modo == "pct_total":
        den = (cubo["celdas"].get(((), ())) or [None] * (k + 1))[k]
    elif modo == "pct_fila":
        den = (cubo["celdas"].get((tuple(rp), ())) or [None] * (k + 1))[k]
    else:
        den = (cubo["celdas"].get(((), tuple(cp))) or [None] * (k + 1))[k]
    return v / den if den else None


def filas_vista(cubo, colapsadas=None, subtotales=True, total=True):
    """[(ruta, tipo, nivel)] tipo: 'dato' (hoja o grupo contraído), 'subtotal' o 'total'."""
    colapsadas = colapsadas or set()
    salida = []

    def rec(nodos):
        for n in nodos:
            if n["hijos"] and n["ruta"] not in colapsadas:
                rec(n["hijos"])
                if subtotales:
                    salida.append((n["ruta"], "subtotal", len(n["ruta"])))
            else:
                salida.append((n["ruta"], "dato", len(n["ruta"])))
    rec(cubo["arbol_filas"])
    if not cubo["dims_filas"]:
        salida.append(((), "dato", 0))
    elif total:
        salida.append(((), "total", 0))
    return salida


def cols_vista(cubo, colapsadas=None, subtotales=True, total=True):
    """[(ruta, tipo, k)] por columna física (el valor k es el nivel más interno)."""
    colapsadas = colapsadas or set()
    nv = len(cubo["valores"])
    salida = []

    def rec(nodos):
        for n in nodos:
            if n["hijos"] and n["ruta"] not in colapsadas:
                rec(n["hijos"])
                if subtotales:
                    salida.extend((n["ruta"], "subtotal", k) for k in range(nv))
            else:
                salida.extend((n["ruta"], "dato", k) for k in range(nv))
    if cubo["dims_cols"]:
        rec(cubo["arbol_cols"])
        if total:
            salida.extend(((), "total", k) for k in range(nv))
    else:
        salida.extend(((), "dato", k) for k in range(nv))
    return salida


def todas_las_rutas(arbol):
    salida = []

    def rec(nodos):
        for n in nodos:
            if n["hijos"]:
                salida.append(n["ruta"])
                rec(n["hijos"])
    rec(arbol)
    return salida


# ----------------------------------------------------------------------------------------
# Versión plana (exportar / graficar)
# ----------------------------------------------------------------------------------------
def calcular(df, cfg, medidas=None):
    """{'columnas', 'filas', 'n_dim', 'totales', 'formatos', 'avisos'}: todo desplegado, sin subtotales."""
    cubo = calcular_cubo(df, cfg, medidas)
    return aplanar(cubo, opciones(cfg))


def aplanar(cubo, opc=None, colapsadas_f=None, colapsadas_c=None, subtotales=False):
    opc = opc or OPCIONES
    filas_v = filas_vista(cubo, colapsadas_f, subtotales and opc["subtotales_filas"], opc["totales_generales_filas"])
    cols_v = cols_vista(cubo, colapsadas_c, subtotales and opc["subtotales_columnas"], opc["totales_generales_columnas"])
    nd = max(1, len(cubo["dims_filas"]))
    una = len(cubo["valores"]) == 1
    columnas = list(cubo["dims_filas"]) or ["Total"]
    for ruta, tipo, k in cols_v:
        if tipo == "total":
            etq = TOTAL
        else:
            etq = " · ".join(ruta) + (" Total" if tipo == "subtotal" else "")
        nombre = cubo["valores"][k]
        if not cubo["dims_cols"]:
            columnas.append(nombre + (f" (% {_ABREV[cubo['modos'][k]]})" if cubo["modos"][k] else ""))
        else:
            columnas.append(etq if una else f"{nombre}{SEP}{etq}")
    filas, totales = [], []
    for ruta, tipo, _n in filas_v:
        if tipo == "total":
            etiquetas = [TOTAL] + [""] * (nd - 1)
            totales.append(len(filas))
        elif not cubo["dims_filas"]:
            etiquetas = ["Total"]
        else:
            etiquetas = list(ruta) + [""] * (nd - len(ruta))
            if tipo == "subtotal":
                etiquetas[len(ruta) - 1] += " Total"
        filas.append(etiquetas + [valor(cubo, ruta, cr, k) for cr, _t, k in cols_v])
    formatos = [None] * nd + [cubo["formatos"][k] for _r, _t, k in cols_v]
    return {"columnas": columnas, "filas": filas, "n_dim": nd, "totales": totales, "formatos": formatos,
            "avisos": cubo.get("avisos", [])}


def _nombre_valor(v, medidas=None):
    """Compatibilidad: nombre de un valor (sin «Suma de»)."""
    return nombre_valor(v, medidas)
