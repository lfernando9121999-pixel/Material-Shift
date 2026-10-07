"""Pestaña 'Tiempos y Métricas' (subpestañas Tiempos Ciclo y Métricas).

Tiempos Ciclo: carguío, cuadrado y hang (izquierda); colas en carga y en descarga, descarga y Tiempo de
Descarga Plan (derecha). Cada tiempo por Flota de Pala × Tipo de Camión con Mínimo, Promedio por registro y
Máximo y su gráfico de rango.
Métricas: Registro de Ciclos, N° de Pases, Carga por Camión y N° Taladros (izquierda); Productividad de
Palas y de Camiones (derecha, Por Flota o Por ID): Material Movido (Mt) × 1,000,000 ÷ Horas Productivas (h).
Solo se consideran los registros con carga; los promedios se ponderan por N° de registros.
"""
import tkinter as tk
from tkinter import ttk

import fmt
import modelo
import registro
from graficos import GraficoBarras, paleta_series
from tema import T
from ui_comun import (Aviso, FiltrosPagina, Placeholder, ScrollFrame, TablaDatos, barra_filtros, caja,
                      filtros_vista)
from ui_github import Pestanas, Segmentado

PAGINA = "tiempos_metricas"
DIMS = {"p": "Flota de Pala", "c": "Tipo de Camión"}
MODOS_REGISTRO = [("n", "N° Ciclos"), ("pct", "Ciclos (%)"), ("t", "Tonelaje (Mt)")]
NIVELES = [("flota", "Por Flota"), ("id", "Por ID")]
TIEMPOS_IZQ = ["cg", "cu", "hang"]
TIEMPOS_DER = ["cc", "cola", "desc"]


def m2(v):
    return "–" if v is None else f"{v:,.2f}"


def color_camion(t):
    p = T.p
    return {"UltraClass": p["est_DPP"], "KOM930": p["est_DEP"]}.get(t, p["est_DPNP"])


def filas_filtradas(filas, filtros):
    fp, fc = filtros.get("Flota de Pala"), filtros.get("Tipo de Camión")
    return [f for f in filas if (fp is None or f["pala"] in fp) and (fc is None or f["camion"] in fc)]


def cfg_palas(esc):
    return esc.clases.get("palas")


def cfg_camiones(esc):
    return esc.clases.get("camiones")


def tabla_y_grafico_estadistica(master, filas, titulo, unidad, ctx, clave, decimales=2):
    """Tabla Flota de Pala · Tipo de Camión · Mínimo · Promedio · Máximo + gráfico de rango."""
    fmt_v = (lambda v: "–" if v is None else f"{v:,.{decimales}f}")
    cols = [{"key": "p", "titulo": "Flota Equipo Pala", "ancho": 120},
            {"key": "c", "titulo": "Tipo Camiones", "ancho": 110},
            {"key": "mn", "titulo": f"Mínimo ({unidad})", "ancho": 90, "ancla": "e"},
            {"key": "pr", "titulo": f"Promedio ({unidad})", "ancho": 90, "ancla": "e"},
            {"key": "mx", "titulo": f"Máximo ({unidad})", "ancho": 90, "ancla": "e"}]
    t = TablaDatos(master, cols, alto=max(2, len(filas)), contexto=ctx, dims=DIMS, clave=clave)
    t.pack(fill="x")
    t.cargar([([f["pala"], f["camion"], fmt_v(f["min"]), fmt_v(f["prom"]), fmt_v(f["max"])],
               [f["pala"], f["camion"], f["min"], f["prom"], f["max"]], False) for f in filas])
    if not filas:
        return
    g = GraficoBarras(master, alto=44 + 46 * len(filas))
    g.nombre = f"{titulo} ({unidad})"
    g.pack(fill="x", pady=(T.px(8), 0))
    g.datos([(f["pala"], f["camion"]) for f in filas],
            [("Mínimo", [f["min"] for f in filas], None), ("Promedio", [f["prom"] for f in filas], None),
             ("Máximo", [f["max"] for f in filas], None)],
            rango=True, formato=fmt_v, unidad=unidad)


class _Sub(ttk.Frame):
    """Subpestaña con desplazamiento y construcción diferida (sin parpadeo)."""

    def __init__(self, master, pagina):
        super().__init__(master, style="Panel.TFrame")
        self.pagina = pagina
        self.zona = ScrollFrame(self)
        self.zona.pack(fill="both", expand=True)
        self._pendiente = True

    def refrescar(self):
        self.construir()

    def construir(self):
        self._pendiente = False
        self._sucia = False
        nuevo = self.zona.preparar()
        cont = ttk.Frame(nuevo, style="Panel.TFrame", padding=(T.px(18), T.px(10)))
        cont.pack(fill="both", expand=True)
        try:
            self._construir(cont)
        finally:
            self.zona.publicar(nuevo)


class SubTiempos(_Sub):
    def _construir(self, cont):
        pg = self.pagina
        esc = pg.esc
        res = esc.resultados or {}
        cargas = res.get("cargas")
        tp = (esc.clases.get("palas") or {}).get("tipos") or {}
        tc = (esc.clases.get("camiones") or {}).get("tipos") or {}
        pg.avisos(cont)
        if not cargas or not tp or not tc:
            Aviso(cont, "Los tiempos requieren o_registro_cargas.csv y los archivos de estado de palas y camiones.").pack(fill="x")
            return
        barra_filtros(cont, pg.ctx)
        filtros = filtros_vista(esc, PAGINA)
        if not registro.tiene_estadisticas(cargas):
            Aviso(cont, "Este escenario se calculó con una versión anterior: ejecute nuevamente el análisis (F5) para "
                        "obtener los tiempos de carguío, cuadrado, colas y descarga del registro de cargas.").pack(
                fill="x", pady=(0, T.px(8)))
            return
        rej = ttk.Frame(cont, style="Panel.TFrame")
        rej.pack(fill="x")
        rej.columnconfigure((0, 1), weight=1, uniform="t")
        izq = ttk.Frame(rej, style="Panel.TFrame")
        der = ttk.Frame(rej, style="Panel.TFrame")
        izq.grid(row=0, column=0, sticky="nsew", padx=(0, T.px(6)))
        der.grid(row=0, column=1, sticky="nsew", padx=(T.px(6), 0))
        medidas = {m: (t, u) for m, t, u in registro.MEDIDAS_TIEMPO}
        for columna, claves in ((izq, TIEMPOS_IZQ), (der, TIEMPOS_DER)):
            for med in claves:
                titulo, unidad = medidas[med]
                filas = filas_filtradas(registro.tabla_estadistica(cargas, med, tp, tc, cfg_palas(esc),
                                                                   cfg_camiones(esc)), filtros)
                marco, _c, cuerpo = caja(columna, f"{titulo} (min)")
                marco.pack(fill="x", pady=(0, T.px(10)))
                tabla_y_grafico_estadistica(cuerpo, filas, titulo, unidad, pg.ctx, f"t.{med}")
        self._descarga_plan(der, cargas, tc)

    def _descarga_plan(self, columna, cargas, tc):
        esc = self.pagina.esc
        marco, _c, cuerpo = caja(columna, "Tiempo de Descarga Plan (min)")
        marco.pack(fill="x", pady=(0, T.px(10)))
        fc = filtros_vista(esc, PAGINA).get("Tipo de Camión")
        filas = [f for f in registro.tabla_descarga(cargas, esc.destinos, tc) if fc is None or f["camion"] in fc]
        t = TablaDatos(cuerpo, [{"key": "d", "titulo": "Tipo de Destino", "ancho": 105},
                                {"key": "c", "titulo": "Tipo de Camión", "ancho": 105},
                                {"key": "q", "titulo": "Promedio Cola en Descarga (min)", "ancla": "e"},
                                {"key": "x", "titulo": "Promedio Descarga (min)", "ancla": "e"},
                                {"key": "t", "titulo": "Tiempo de Descarga Total (min)", "ancla": "e"}],
                       alto=max(2, len(filas)), contexto=self.pagina.ctx, dims={"c": "Tipo de Camión"}, clave="t.plan")
        t.pack(fill="x")
        t.cargar([([f["tipo_destino"], f["camion"], m2(f["cola"]), m2(f["descarga"]), m2(f["total"])],
                   [f["tipo_destino"], f["camion"], f["cola"], f["descarga"], f["total"]], False) for f in filas])
        if filas:
            g = GraficoBarras(cuerpo, alto=60 + 24 * len(filas))
            g.nombre = "Tiempo de Descarga Plan (min)"
            g.pack(fill="x", pady=(T.px(8), 0))
            g.datos([(f["tipo_destino"], f["camion"]) for f in filas],
                    [("Promedio Cola en Descarga", [f["cola"] for f in filas], T.p["est_DPNP"]),
                     ("Promedio Descarga", [f["descarga"] for f in filas], T.p["est_TP"])],
                    apilado=True, horizontal=True, formato=m2, unidad="min")


class SubMetricas(_Sub):
    def _construir(self, cont):
        pg = self.pagina
        esc = pg.esc
        res = esc.resultados or {}
        cargas = res.get("cargas")
        clases = res.get("clases") or {}
        tp = (esc.clases.get("palas") or {}).get("tipos") or {}
        tc = (esc.clases.get("camiones") or {}).get("tipos") or {}
        pg.avisos(cont)
        barra_filtros(cont, pg.ctx)
        filtros = filtros_vista(esc, PAGINA)
        rej = ttk.Frame(cont, style="Panel.TFrame")
        rej.pack(fill="both", expand=True)
        rej.columnconfigure((0, 1), weight=1, uniform="m")
        celdas_izq = []
        if cargas and tp and tc and registro.tiene_estadisticas(cargas):
            celdas_izq.append(lambda m: self._registro(m, cargas, tp, tc, filtros))
            celdas_izq.append(lambda m: self._estadistica(m, cargas, registro.MEDIDA_PASES, tp, tc, filtros, 2))
            celdas_izq.append(lambda m: self._estadistica(m, cargas, registro.MEDIDA_CARGA, tp, tc, filtros, 1))
        elif cargas:
            celdas_izq.append(lambda m: Aviso(m, "Ejecute nuevamente el análisis (F5) para obtener el Registro de "
                                                 "Ciclos, el N° de Pases y la Carga por Camión."))
        if clases.get("perforadoras"):
            celdas_izq.append(lambda m: self._taladros(m, clases["perforadoras"]))
        for i, crear in enumerate(celdas_izq):
            celda = ttk.Frame(rej, style="Panel.TFrame")
            celda.grid(row=i, column=0, sticky="nsew", padx=(0, T.px(6)), pady=(0, T.px(10)))
            crear(celda)
        n = max(len(celdas_izq), 1)
        derechas = []
        if clases.get("palas"):
            derechas.append(lambda m: self._productividad(m, clases["palas"], "palas", filtros))
        if clases.get("camiones"):
            derechas.append(lambda m: self._productividad(m, clases["camiones"], "camiones", filtros))
        # Palas: alto de Registro de Ciclos + N° de Pases; Camiones: alto de Carga por Camión + N° Taladros
        if len(derechas) == 2 and n >= 2:
            mitad = (n + 1) // 2
            ubicacion = [(0, mitad), (mitad, n - mitad)]
        elif len(derechas) == 2:
            ubicacion = [(0, 1), (1, 1)]
        else:
            ubicacion = [(0, n)]
        for crear, (r0, span) in zip(derechas, ubicacion):
            celda = ttk.Frame(rej, style="Panel.TFrame")
            celda.grid(row=r0, column=1, rowspan=max(1, span), sticky="nsew", padx=(T.px(6), 0), pady=(0, T.px(10)))
            crear(celda)

    # ---- Registro de Ciclos (doble entrada) ---------------------------------------------------
    def _registro(self, master, cargas, tp, tc, filtros):
        esc = self.pagina.esc
        modo = esc.vistas.get("registro_modo", "n")
        marco, cab, cuerpo = caja(master, "Registro de Ciclos")
        marco.pack(fill="both", expand=True)
        Segmentado(cab, MODOS_REGISTRO, modo, self._modo_registro).pack(side="right")
        r = registro.tabla_registro(cargas, tp, tc, cfg_palas(esc), cfg_camiones(esc))
        fp, fc = filtros.get("Flota de Pala"), filtros.get("Tipo de Camión")
        palas = [p for p in r["palas"] if fp is None or p in fp]
        cams = [c for c in r["camiones"] if fc is None or c in fc]
        base = r["n"] if modo in ("n", "pct") else r["t"]
        total = sum(base.get((p, c), 0) for p in palas for c in cams) or 1.0

        def f(v):
            if modo == "pct":
                return f"{v / total * 100:,.2f}%"
            if modo == "t":
                return f"{v / 1e6:,.2f}"
            return f"{v:,.0f}"
        sufijo = {"n": "", "pct": " (%)", "t": " (Mt)"}[modo]
        cols = [{"key": "p", "titulo": "Flota Equipo Pala", "ancho": 130}] + \
               [{"key": f"c{j}", "titulo": c + sufijo, "ancho": 100, "ancla": "e"} for j, c in enumerate(cams)] + \
               [{"key": "t", "titulo": "Total" + sufijo, "ancho": 105, "ancla": "e"}]
        filas = []
        for p in palas:
            vals = [base.get((p, c), 0) for c in cams]
            filas.append(([p] + [f(v) if v else "" for v in vals] + [f(sum(vals))], [p] + vals + [sum(vals)], False))
        tot = [sum(base.get((p, c), 0) for p in palas) for c in cams]
        filas.append((["Total"] + [f(v) for v in tot] + [f(sum(tot))], ["Total"] + tot + [sum(tot)], True))
        t = TablaDatos(cuerpo, cols, alto=len(filas), contexto=self.pagina.ctx, dims={"p": "Flota de Pala"},
                       clave="m.registro")
        t.pack(fill="x")
        t.cargar(filas)
        if palas and cams:
            g = GraficoBarras(cuerpo, alto=60 + 30 * len(palas))
            g.nombre = "Registro de Ciclos – " + dict(MODOS_REGISTRO)[modo]
            g.pack(fill="x", pady=(T.px(8), 0))
            factor = 100.0 / total if modo == "pct" else (1e-6 if modo == "t" else 1.0)
            g.datos(palas, [(c, [base.get((p, c), 0) * factor for p in palas], color_camion(c)) for c in cams],
                    apilado=True, horizontal=True,
                    formato=(lambda v: f"{v:,.1f}%") if modo == "pct" else (
                        (lambda v: f"{v:,.1f}") if modo == "t" else (lambda v: f"{v:,.0f}")),
                    formato_eje=(lambda v: f"{v:,.0f}%") if modo == "pct" else (
                        (lambda v: f"{v:,.0f}") if modo == "t" else (lambda v: f"{v / 1e3:,.0f} k" if v >= 1e3 else f"{v:,.0f}")),
                    unidad={"n": "ciclos", "pct": "%", "t": "Mt"}[modo])

    def _modo_registro(self, valor):
        self.pagina.esc.vistas["registro_modo"] = valor
        self.pagina.esc.marcar_sucio()
        self.after_idle(self.construir)

    # ---- N° de Pases y Carga por Camión ---------------------------------------------------------
    def _estadistica(self, master, cargas, medida, tp, tc, filtros, decimales):
        esc = self.pagina.esc
        med, titulo, unidad = medida
        filas = filas_filtradas(registro.tabla_estadistica(cargas, med, tp, tc, cfg_palas(esc), cfg_camiones(esc)),
                                filtros)
        marco, _c, cuerpo = caja(master, f"{titulo} ({unidad})")
        marco.pack(fill="both", expand=True)
        if not filas and med == "t":
            Aviso(cuerpo, "Ejecute nuevamente el análisis (F5) para obtener la carga por camión.").pack(fill="x")
            return
        tabla_y_grafico_estadistica(cuerpo, filas, titulo, unidad, self.pagina.ctx, f"m.{med}", decimales)

    # ---- Productividad de Palas y de Camiones (Por Flota / Por ID) ---------------------------------
    def _productividad(self, master, r, clase, filtros):
        esc = self.pagina.esc
        clave_v = "productividad_id" if clase == "palas" else "productividad_id_camiones"
        por_id = bool(esc.vistas.get(clave_v))
        titulo = "Productividad de Palas (t/h)" if clase == "palas" else "Productividad de Camiones (t/h)"
        marco, cab, cuerpo = caja(master, titulo)
        marco.pack(fill="both", expand=True)
        Segmentado(cab, NIVELES, "id" if por_id else "flota",
                   lambda v, k=clave_v: self._cambiar_nivel(k, v)).pack(side="right")
        dim = "Flota de Pala" if clase == "palas" else None
        fsel = filtros.get(dim) if dim else None
        tsel = filtros.get("Tipo de Camión") if clase == "camiones" else None

        def prod(f):
            return f["metrica_total"] * 1e6 / f["horas_productivas"] if f.get("horas_productivas") else None
        paleta = paleta_series()
        color_flota = {f["nombre"]: paleta[i % len(paleta)] for i, f in enumerate(r["flota"])}
        flotas = [f for f in r["flota"] if (fsel is None or f["nombre"] in fsel) and (tsel is None or f.get("tipo") in tsel)]
        filas, cats, vals, colores = [], [], [], []
        if por_id:
            nombres = {f["nombre"] for f in flotas}
            for e in [x for x in r["id"] if x["flota"] in nombres]:
                filas.append(([e.get("tipo", ""), e["flota"], str(e["nombre"]), fmt.entero(e["horas_productivas"]),
                               m2(e["metrica_total"]), fmt.entero(prod(e))],
                              [e.get("tipo", ""), e["flota"], str(e["nombre"]), e["horas_productivas"], e["metrica_total"],
                               prod(e)], False))
                cats.append((str(e["nombre"]), e["flota"]))
                vals.append(prod(e))
                colores.append(color_flota[e["flota"]])
            cols = [{"key": "tp", "titulo": "Tipo", "ancho": 100}, {"key": "f", "titulo": "Flota", "ancho": 120},
                    {"key": "i", "titulo": "ID", "ancho": 90}]
        else:
            for f in flotas:
                filas.append(([f.get("tipo", ""), f["nombre"], fmt.entero(f["horas_productivas"]), m2(f["metrica_total"]),
                               fmt.entero(prod(f))],
                              [f.get("tipo", ""), f["nombre"], f["horas_productivas"], f["metrica_total"], prod(f)], False))
                cats.append(f["nombre"])
                vals.append(prod(f))
                colores.append(color_camion(f.get("tipo")) if clase == "camiones" else color_flota[f["nombre"]])
            cols = [{"key": "tp", "titulo": "Tipo", "ancho": 100}, {"key": "f", "titulo": "Flota", "ancho": 140}]
        cols += [{"key": "h", "titulo": "Horas Productivas (h)", "ancla": "e"},
                 {"key": "m", "titulo": "Material Movido (Mt)", "ancla": "e"},
                 {"key": "p", "titulo": "Productividad (t/h)", "ancla": "e"}]
        if len(filas) > 1 and not por_id:
            hp = sum(f["horas_productivas"] for f in flotas)
            mt = sum(f["metrica_total"] for f in flotas)
            pt = mt * 1e6 / hp if hp else None
            filas.append((["Total", "", fmt.entero(hp), m2(mt), fmt.entero(pt)], ["Total", "", hp, mt, pt], True))
        dims = {"f": dim} if dim else {"tp": "Tipo de Camión"}
        t = TablaDatos(cuerpo, cols, alto=max(2, min(len(filas), 10)), contexto=self.pagina.ctx, dims=dims,
                       clave=f"m.prod_{clase}_{'id' if por_id else 'flota'}", grupo="f" if por_id else None)
        t.pack(fill="x")
        t.cargar(filas)
        if not cats:
            return
        necesario = 40 + 22 * len(cats)
        g_cont = cuerpo
        if len(cats) > 24:                    # muchos equipos: el gráfico se desplaza dentro del recuadro
            zona = ScrollFrame(cuerpo, margen_inferior=False)
            zona.pack(fill="both", expand=True, pady=(T.px(8), 0))
            zona.configure(height=T.px(420))
            g_cont = zona.interior
        g = GraficoBarras(g_cont, alto=necesario)
        g.nombre = titulo
        if g_cont is cuerpo:            # el gráfico ocupa el alto del recuadro (sin espacio vacío)
            g.pack(fill="both", expand=True, pady=(T.px(8), 0))
        else:
            g.pack(fill="x", pady=(T.px(8), 0))
        g.datos(cats, [("Productividad (t/h)", vals, None)], horizontal=True, colores_barra=colores,
                formato=lambda v: f"{v:,.0f}", unidad="t/h")

    def _cambiar_nivel(self, clave, valor):
        self.pagina.esc.vistas[clave] = valor == "id"
        self.pagina.esc.marcar_sucio()
        self.after_idle(self.construir)

    # ---- N° Taladros ------------------------------------------------------------------------
    def _taladros(self, master, r):
        esc = self.pagina.esc
        marco, _cab, cuerpo = caja(master, "N° Taladros")
        marco.pack(fill="both", expand=True)
        cfg = esc.clases.get("perforadoras") or {}
        categoria = cfg.get("energia") or {}
        filas = []
        for f in r["flota"]:
            filas.append(([f.get("tipo") or modelo.SIN_ASIGNAR, f["nombre"], categoria.get(f["nombre"], ""),
                           fmt.entero(f["n_equipos"]), fmt.entero(f["metrica_total"])],
                          [f.get("tipo"), f["nombre"], categoria.get(f["nombre"], ""), f["n_equipos"], f["metrica_total"]],
                          False))
        total = sum(f["metrica_total"] for f in r["flota"])
        filas.append((["Total", "", "", fmt.entero(r["n_equipos"]), fmt.entero(total)],
                      ["Total", "", "", r["n_equipos"], total], True))
        t = TablaDatos(cuerpo, [{"key": "t", "titulo": "Tipo de Perforadora", "ancho": 130},
                                {"key": "f", "titulo": "Flota", "ancho": 120},
                                {"key": "c", "titulo": modelo.CATEGORIA, "ancho": 90, "ancla": "center"},
                                {"key": "n", "titulo": "N° de Perforadoras", "ancho": 115, "ancla": "e"},
                                {"key": "x", "titulo": "N° Taladros", "ancho": 110, "ancla": "e"}],
                       alto=len(filas), grupo=None, clave="m.taladros")
        t.pack(fill="x")
        t.cargar(filas)
        flotas = r["flota"]
        g = GraficoBarras(cuerpo, alto=40 + 24 * len(flotas))
        g.nombre = "N° Taladros"
        g.pack(fill="x", pady=(T.px(8), 0))
        colores = {"Precorte": T.p["est_DPP"], "Buffer": T.p["est_DEP"], "Producción": T.p["est_TP"]}
        g.datos([f["nombre"] for f in flotas], [("N° Taladros", [f["metrica_total"] for f in flotas], None)],
                horizontal=True, colores_barra=[colores.get(f.get("tipo"), T.p["acento"]) for f in flotas],
                formato=lambda v: f"{v:,.0f}", unidad="und")


class PaginaProductividad(ttk.Frame):
    """Contenedor 'Tiempos y Métricas'."""

    def __init__(self, master, vista):
        super().__init__(master, style="Panel.TFrame")
        self.vista = vista
        self.esc = vista.esc
        self._sucia = True
        self.ctx = FiltrosPagina(self.esc, PAGINA, lambda _g: self.after_idle(self._reconstruir))
        self.vacio = Placeholder(self, "Sin Resultados", "Ejecute el análisis (F5) para ver tiempos y métricas.")
        self.cuerpo = ttk.Frame(self, style="Panel.TFrame")
        self.sub = Pestanas(self.cuerpo, al_cambiar=self._al_mostrar)
        self.sub.pack(fill="both", expand=True)
        self.tiempos = SubTiempos(self.sub, self)
        self.metricas = SubMetricas(self.sub, self)
        self.sub.add(self.tiempos, text="Tiempos Ciclo")
        self.sub.add(self.metricas, text="Métricas")

    def avisos(self, cont):
        if not self.esc.vigente:
            Aviso(cont, "Los resultados no corresponden a la configuración actual. "
                        "Ejecute nuevamente el análisis (F5).").pack(fill="x", pady=(0, T.px(8)))

    def _al_mostrar(self, pagina):
        if getattr(pagina, "_pendiente", False):
            pagina.construir()

    def _reconstruir(self):
        for s in (self.tiempos, self.metricas):
            s._pendiente = True
        actual = self.sub.select()
        if actual is not None:
            actual.construir()

    def refrescar(self):
        res = self.esc.resultados or {}
        if not res.get("clases"):
            self.cuerpo.pack_forget()
            self.vacio.pack(fill="both", expand=True)
            return
        self.vacio.pack_forget()
        self.cuerpo.pack(fill="both", expand=True, padx=T.px(8), pady=(T.px(2), T.px(8)))
        self._reconstruir()
