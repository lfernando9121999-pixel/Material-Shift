"""Estructura común de tablas de reporte (usada por Excel y PowerPoint)."""
import modelo

# Paleta de reporte (la misma del modelo: Primer/GitHub, modo claro)
COLOR_CAB = "24292F"
COLOR_ACENTO = "0969DA"
COLOR_ALT = "F6F8FA"
COLOR_TOTAL = "EAEEF2"
COLOR_TEXTO = "1F2328"
COLOR_SUAVE = "656D76"
COLOR_ESTADO = {"TP": "1A7F37", "DPP": "0969DA", "DPNP": "8250DF",
                "DEP": "BF8700", "DENP": "BC4C00", "SB": "6E7781"}

SIN_TOTAL = ("disponibilidad", "utilizacion")
DETALLE = [("dpp", "Det. Proceso Prog. (h)"), ("dpnp", "Det. Proceso No Prog. (h)"),
           ("dep", "Det. Equipo Prog. (h)"), ("denp", "Det. Equipo No Prog. (h)"),
           ("sb", "Stand By (h)"), ("tc", "Tiempo Calendario (h)")]


def filtros_vista(esc, pagina):
    """Filtros vinculados guardados de una página (pantalla y reportes): {dimensión: set(valores)}."""
    if not esc.vistas.get("vincular_filtros", True):
        return {}
    return {k: set(v) for k, v in (esc.vistas.get("filtros") or {}).get(pagina, {}).items()
            if "|" not in k and v is not None}


def texto_filtros(filtros):
    return "; ".join(f"{k}: {', '.join(sorted(map(str, v)))}" for k, v in filtros.items()) if filtros else ""


def _sumar_filas(filas, nombre):
    """Agrega filas de flota/equipo (horas, métrica y N° de equipos) y recalcula sus indicadores."""
    fila = {k: sum(float(f.get(k) or 0.0) for f in filas) for k in ("tp", "dpp", "dpnp", "dep", "denp", "sb",
                                                                       "metrica_total")}
    fila["n_equipos"] = int(sum(f.get("n_equipos") or 0 for f in filas))
    modelo._derivados(fila)
    fila["nombre"] = nombre
    return fila


def filtrar_clase(r, filtros, clase=None):
    """Resultado de una clase con los filtros vinculados aplicados ({'Flota'|'Tipo'|'ID': set(valores)}).

    Las tablas por Tipo y el Total se recalculan (cociente de sumas) con lo que queda visible, como en la
    interfaz. Sin filtros devuelve el resultado original."""
    if not r or not filtros:
        return r
    fl, tp, ids = filtros.get("Flota"), filtros.get("Tipo"), filtros.get("ID")

    def ok_f(nombre, tipo):
        return (fl is None or nombre in fl) and (tp is None or (tipo or "") in tp)
    lista_ids = [e for e in r.get("id", []) if ok_f(e.get("flota"), e.get("tipo")) and (ids is None or str(e["nombre"]) in ids)]
    if ids is not None:
        base = {}
        for e in lista_ids:
            base.setdefault(e["flota"], []).append(e)
        flotas = [dict(_sumar_filas(base[f["nombre"]], f["nombre"]), tipo=f.get("tipo", ""))
                  for f in r["flota"] if f["nombre"] in base]
    else:
        flotas = [f for f in r["flota"] if ok_f(f["nombre"], f.get("tipo"))]
    tipos_orden = modelo.CLASES[clase]["tipos"] + [modelo.SIN_ASIGNAR] if clase else []
    por_tipo = {}
    for f in flotas:
        por_tipo.setdefault(f.get("tipo") or modelo.SIN_ASIGNAR, []).append(f)
    claves = [t for t in tipos_orden if t in por_tipo] + [t for t in por_tipo if t not in tipos_orden]
    salida = dict(r)
    salida["flota"] = flotas
    salida["tipo"] = [_sumar_filas(por_tipo[t], t) for t in claves]
    salida["id"] = lista_ids
    salida["total"] = _sumar_filas(flotas, "Total") if flotas else dict(r["total"], n_equipos=0)
    salida["n_equipos"] = salida["total"]["n_equipos"]
    return salida


def columnas_nivel(clase, nivel, detalle=False):
    """Lista de (clave, titulo, tipo) con tipo en {texto, entero, dec1, pct}."""
    info = modelo.CLASES[clase]
    met = "dec1" if info["metrica"] == "material" else "entero"
    cols = []
    if nivel == "id":
        cols += [("tipo", "Tipo", "texto"), ("flota", "Flota", "texto"), ("nombre", "ID", "texto")]
    else:
        cols += [("nombre", "Flota" if nivel == "flota" else "Tipo", "texto"),
                 ("n_equipos", f"N° de {info['plural']}", "entero")]
    cols.append(("horas_productivas", "Horas Productivas (h)", "entero"))
    if detalle:
        cols += [(k, t, "entero") for k, t in DETALLE]
    cols += [("disponibilidad", "Disponibilidad (%)", "pct"),
             ("utilizacion", "Utilización (%)", "pct")]
    if nivel == "id":
        cols.append(("metrica_total", info["metrica_id"], met))
    else:
        cols += [("metrica_total", info["metrica_total"], met),
                 ("metrica_prom", info["metrica_prom"], met)]
    return cols


def tablas_clase(res, clase, detalle=False):
    """Devuelve [{'titulo', 'columnas', 'filas', 'totales'}] para Flota, Tipo e ID."""
    salida = []
    for nivel, titulo, filas, con_total in (
            ("flota", "Por Flota", res["flota"], True),
            ("tipo", "Por Tipo", res["tipo"], True),
            ("id", "Por ID", res["id"], False)):
        cols = columnas_nivel(clase, nivel, detalle)
        datos = [[f.get(k) for k, _t, _ty in cols] for f in filas]
        totales = []
        if con_total:
            # Disponibilidad y Utilización se reportan por flota/tipo/equipo, no en el total
            datos.append(["Total" if k == "nombre" else ("" if k in SIN_TOTAL else res["total"].get(k))
                          for k, _t, _ty in cols])
            totales.append(len(datos) - 1)
        salida.append({"titulo": titulo, "columnas": cols, "filas": datos, "totales": totales})
    return salida


def resumen_flotas(resultados):
    """Una fila por flota (de las tres clases) con sus indicadores."""
    filas = []
    for clase in modelo.ORDEN_CLASES:
        r = (resultados or {}).get("clases", {}).get(clase)
        if not r:
            continue
        info = modelo.CLASES[clase]
        for f in r["flota"]:
            filas.append({"clase": info["plural"], "flota": f["nombre"], "tipo": f.get("tipo", ""),
                          "n": f["n_equipos"], "hp": f["horas_productivas"], "disp": f["disponibilidad"],
                          "util": f["utilizacion"], "metrica_nombre": info["metrica_total"],
                          "metrica": f["metrica_total"], "material": info["metrica"] == "material"})
    return filas


def resumen_clases(resultados):
    """Una fila por clase con los indicadores globales."""
    filas = []
    for clase in modelo.ORDEN_CLASES:
        r = (resultados or {}).get("clases", {}).get(clase)
        if not r:
            continue
        t = r["total"]
        info = modelo.CLASES[clase]
        filas.append({
            "clase": info["plural"], "n": r["n_equipos"], "hp": t["horas_productivas"],
            "disp": t["disponibilidad"], "util": t["utilizacion"],
            "metrica_nombre": info["metrica_total"], "metrica": t["metrica_total"],
            "material": info["metrica"] == "material",
        })
    return filas
