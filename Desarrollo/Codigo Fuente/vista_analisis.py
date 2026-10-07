"""Pestaña 'Análisis de Estados' (subpestañas Perforadoras, Palas y Camiones).

Resumen: indicadores, distribución del tiempo calendario a todo el ancho, Por Flota y Por Tipo lado a
lado, y Por ID con sus gráficos por flota (pestañas verticales). Detallado: tablas con horas por estado,
sin gráficos. Los filtros de encabezado se vinculan con tarjetas, gráficos y tablas.
"""
import tkinter as tk
from datetime import datetime
from tkinter import ttk

import fmt
import modelo
import reporte
from graficos import GraficoBarras
from tema import COLOR_ESTADO, T
from ui_comun import Aviso, FiltrosPagina, Placeholder, ScrollFrame, TablaDatos, barra_filtros, filtros_vista
from ui_github import Pestanas, Segmentado, TarjetaKPI, TiraVertical

DETALLE = [("dpp", "Det. Proceso Prog. (h)"), ("dpnp", "Det. Proceso No Prog. (h)"),
           ("dep", "Det. Equipo Prog. (h)"), ("denp", "Det. Equipo No Prog. (h)"),
           ("sb", "Stand By (h)"), ("tc", "Tiempo Calendario (h)")]
SIN_TOTAL = ("disponibilidad", "utilizacion")
MODOS = [("resumen", "Resumen"), ("detallado", "Detallado")]
FILAS_ID = 18


class SelectorReplica(ttk.Frame):
    """Réplica activa del escenario: ubicación fija junto a las pestañas principales."""

    def __init__(self, master, vista, estilo="TFrame", estilo_lbl="TLabel"):
        super().__init__(master, style=estilo)
        self.vista = vista
        ttk.Label(self, text="Réplica", style=estilo_lbl, font=T.f["negrita"]).pack(side="left", padx=(0, T.px(6)))
        self.var = tk.StringVar()
        self.cmb = ttk.Combobox(self, textvariable=self.var, state="readonly", width=9)
        self.cmb.pack(side="left")
        self.cmb.bind("<<ComboboxSelected>>", self._elegir)
        self.refrescar()

    def _elegir(self, _e=None):
        valor = self.var.get()
        if valor and valor != self.vista.esc.replica:
            self.vista.app.cambiar_replica(self.vista, valor)

    def refrescar(self):
        e = self.vista.esc
        ops = e.opciones_replica
        self.cmb.configure(values=ops, state="readonly" if len(ops) > 1 else "disabled")
        self.var.set(e.replica if e.replica in ops else (ops[0] if ops else "–"))


def especificacion(clase, nivel, detalle):
    """Devuelve (columnas, función fila->(visibles, orden, total))."""
    info = modelo.CLASES[clase]
    material = info["metrica"] == "material"
    fmt_met = fmt.decimal1 if material else fmt.entero
    campos = []
    if nivel == "id":
        campos += [("tipo", "Tipo", 100, "w", str), ("flota", "Flota", 130, "w", str), ("nombre", "ID", 100, "w", str)]
    else:
        campos += [("nombre", "Flota" if nivel == "flota" else "Tipo", 150, "w", str),
                   ("n_equipos", f"N° de {info['plural']}", 110, "e", fmt.entero)]
    campos.append(("horas_productivas", "Horas Productivas (h)", 140, "e", fmt.entero))
    if detalle:
        campos += [(k, t, 150, "e", fmt.entero) for k, t in DETALLE]
    campos += [("disponibilidad", "Disponibilidad (%)", 125, "e", fmt.porcentaje),
               ("utilizacion", "Utilización (%)", 120, "e", fmt.porcentaje)]
    if nivel == "id":
        campos.append(("metrica_total", info["metrica_id"], 120, "e", fmt_met))
    else:
        campos += [("metrica_total", info["metrica_total"], 145, "e", fmt_met),
                   ("metrica_prom", info["metrica_prom"], 145, "e", fmt_met)]
    columnas = [{"key": k, "titulo": t, "ancho": a, "ancla": an} for k, t, a, an, _f in campos]

    def fila(d, total=False):
        vis, raw = [], []
        for k, _t, _a, _an, f in campos:
            v = None if (total and k in SIN_TOTAL) else d.get(k)
            raw.append(v)
            if total and k in SIN_TOTAL:
                vis.append("")
            else:
                vis.append(f(v) if f is not str else ("" if v is None else str(v)))
        return vis, raw, total

    return columnas, fila


def color_cantidad():
    return "#39C5CF" if T.nombre == "oscuro" else "#1B7C83"


def tarjetas_clase(master, r, info, filas_min=0):
    """Fila de tarjetas con el detalle por flota (mismo ancho y alto en las tres clases)."""
    material = info["metrica"] == "material"
    f_met = fmt.decimal1 if material else fmt.entero
    flotas = r["flota"]
    datos = [
        (f"N° de {info['plural']}", fmt.entero(r["n_equipos"]), f"{len(flotas)} Flotas", color_cantidad(),
         [(f["nombre"], fmt.entero(f["n_equipos"])) for f in flotas], None),
        ("Horas Productivas (h)", "", "", COLOR_ESTADO["TP"],
         [(f["nombre"], fmt.entero(f["horas_productivas"])) for f in flotas], None),
        ("Disponibilidad (%)", "", "", COLOR_ESTADO["DPP"],
         [(f["nombre"], fmt.porcentaje(f["disponibilidad"])) for f in flotas], None),
        ("Utilización (%)", "", "", COLOR_ESTADO["DPNP"],
         [(f["nombre"], fmt.porcentaje(f["utilizacion"])) for f in flotas], None),
        (info["metrica_total"], f_met(r["total"]["metrica_total"]), "", COLOR_ESTADO["DEP"],
         [(f["nombre"], f_met(f["metrica_total"]), f_met(f["metrica_prom"])) for f in flotas],
         ("Flota", "Suma", "Prom.")),
    ]
    marco = ttk.Frame(master, style="Panel.TFrame")
    tarjetas = [TarjetaKPI(marco, tit, val, det, col, filas=filas, columnas=cols, filas_min=filas_min)
                for tit, val, det, col, filas, cols in datos]
    pesos = [7 if d[5] else 4 for d in datos]
    estado = {"por_fila": None}

    def acomodar(_e=None):
        """Una fila si las tarjetas caben sin cortar cifras; si la ventana es angosta, filas de tres."""
        ancho = marco.winfo_width()
        if ancho < 50:
            return
        necesario = sum(t.ancho_minimo() for t in tarjetas) + T.px(8) * (len(tarjetas) - 1)
        por_fila = len(tarjetas) if necesario <= ancho else 3
        if por_fila == estado["por_fila"]:
            return
        estado["por_fila"] = por_fila
        for c in range(len(tarjetas)):
            marco.columnconfigure(c, weight=0, uniform="")
        for i, t in enumerate(tarjetas):
            fila, c = divmod(i, por_fila)
            # la última tarjeta de una fila incompleta ocupa el espacio restante (p. ej. la de tres columnas)
            span = por_fila - c if i == len(tarjetas) - 1 else 1
            t.grid(row=fila, column=c, columnspan=span, sticky="nsew", padx=(0 if c == 0 else T.px(8), 0),
                   pady=(0 if fila == 0 else T.px(8), 0))
            marco.columnconfigure(c, weight=pesos[i] if por_fila == len(tarjetas) else 1, uniform="kpi")

    for i, t in enumerate(tarjetas):
        marco.columnconfigure(i, weight=pesos[i], uniform="kpi")
        t.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else T.px(8), 0))
    marco.bind("<Configure>", acomodar, add="+")
    return marco


DIMS = {"flota": {"nombre": "Flota"}, "tipo": {"nombre": "Tipo"},
        "id": {"nombre": "ID", "flota": "Flota", "tipo": "Tipo"}}


def distribucion(master, filas, alto=None, nombre="Distribución del Tiempo Calendario (%)"):
    """Gráfico 100 % apilado de la distribución del tiempo calendario por estado."""
    g = GraficoBarras(master, alto=alto or max(130, 64 + 34 * len(filas)))
    g.nombre = nombre
    series = []
    for k in modelo.CLAVES:
        vals = [(f.get(k.lower(), 0) / f["tc"] * 100) if f.get("tc") else 0 for f in filas]
        series.append((modelo.NOMBRE_ESTADO[k], vals, COLOR_ESTADO[k]))
    g.datos([str(f["nombre"]) for f in filas], series, apilado=True, horizontal=True,
            formato=lambda v: f"{v:,.1f}%", formato_eje=lambda v: f"{v:,.0f}%",
            paso=20, tope=100, mostrar_valores=True, mostrar_total=False)
    return g


class VistaClase(ttk.Frame):
    def __init__(self, master, pagina, clase):
        super().__init__(master, style="Panel.TFrame")
        self.pagina, self.vista, self.clase = pagina, pagina.vista, clase
        self.info = modelo.CLASES[clase]
        self._resultado = None
        self._vigente = True
        self._sucia = True
        self.ctx = FiltrosPagina(self.vista.esc, f"estados.{clase}", lambda _g: self.after_idle(self.construir))
        self.zona = ScrollFrame(self)
        self.zona.pack(fill="both", expand=True)

    def refrescar(self):
        self.construir()

    def construir(self):
        self._sucia = False
        res = (self.vista.esc.resultados or {}).get("clases", {}).get(self.clase)
        if res is None:
            return
        esc = self.vista.esc
        detalle = esc.vistas.get("estados_modo", "resumen") == "detallado"
        nuevo = self.zona.preparar()
        cont = ttk.Frame(nuevo, style="Panel.TFrame", padding=(T.px(18), T.px(12)))
        cont.pack(fill="both", expand=True)
        if not esc.vigente:
            Aviso(cont, "Los resultados no corresponden a la configuración actual. "
                        "Ejecute nuevamente el análisis (F5) para actualizarlos.").pack(fill="x", pady=(0, T.px(8)))
        for a in res.get("advertencias", []):
            Aviso(cont, a).pack(fill="x", pady=(0, T.px(8)))
        barra_filtros(cont, self.ctx)
        r = reporte.filtrar_clase(res, filtros_vista(esc, f"estados.{self.clase}"), self.clase)
        if not r["flota"]:
            Aviso(cont, "Los filtros actuales no dejan ningún equipo. Use «Limpiar Filtros».").pack(fill="x")
            self.zona.publicar(nuevo)
            return
        tarjetas_clase(cont, r, self.info, self.pagina.filas_kpi()).pack(fill="x", pady=(0, T.px(14)))
        if detalle:
            for titulo, nivel, filas in (("Por Flota", "flota", r["flota"] + [r["total"]]),
                                          ("Por Tipo", "tipo", r["tipo"] + [r["total"]]),
                                          ("Por ID", "id", r["id"])):
                self._titulo(cont, titulo)
                self._tabla(cont, nivel, filas, nivel != "id", True, FILAS_ID if nivel == "id" else None).pack(
                    fill="x", pady=(0, T.px(12)))
        else:
            self._titulo(cont, "Distribución del Tiempo Calendario (%)")
            distribucion(cont, r["flota"]).pack(fill="x", pady=(0, T.px(12)))
            fila = ttk.Frame(cont, style="Panel.TFrame")
            fila.pack(fill="x", pady=(0, T.px(12)))
            fila.columnconfigure((0, 1), weight=1, uniform="ft")
            for j, (titulo, nivel, filas) in enumerate((("Por Flota", "flota", r["flota"] + [r["total"]]),
                                                        ("Por Tipo", "tipo", r["tipo"] + [r["total"]]))):
                col = ttk.Frame(fila, style="Panel.TFrame")
                col.grid(row=0, column=j, sticky="nsew", padx=(0, T.px(8)) if j == 0 else (T.px(8), 0))
                self._titulo(col, titulo)
                self._tabla(col, nivel, filas, True, False).pack(fill="x")
            self._por_id(cont, r)
        self.zona.publicar(nuevo)

    @staticmethod
    def _titulo(master, texto):
        ttk.Label(master, text=texto, style="Subtitulo.TLabel").pack(anchor="w", pady=(0, T.px(4)))

    def _tabla(self, master, nivel, filas, con_total, detalle, max_filas=None):
        columnas, fila = especificacion(self.clase, nivel, detalle)
        datos = [fila(d, con_total and i == len(filas) - 1) for i, d in enumerate(filas)]
        alto = len(datos) if max_filas is None else max(2, min(len(datos), max_filas))
        t = TablaDatos(master, columnas, alto=alto, contexto=self.ctx, dims=DIMS[nivel],
                       clave=f"{self.clase}.{nivel}")
        t.cargar(datos)
        return t

    def _por_id(self, cont, r):
        fila = ttk.Frame(cont, style="Panel.TFrame")
        fila.pack(fill="x")
        fila.columnconfigure(0, weight=11, uniform="pid")
        fila.columnconfigure(1, weight=9, uniform="pid")
        izq = ttk.Frame(fila, style="Panel.TFrame")
        izq.grid(row=0, column=0, sticky="nsew", padx=(0, T.px(8)))
        der = ttk.Frame(fila, style="Panel.TFrame")
        der.grid(row=0, column=1, sticky="nsew", padx=(T.px(8), 0))
        self._titulo(izq, "Por ID")
        n = min(len(r["id"]), FILAS_ID)
        t = self._tabla(izq, "id", r["id"], False, False, FILAS_ID)
        t.pack(fill="x")
        ttk.Label(izq, style="PanelSuave.TLabel", font=T.f["chica"],
                  text=f"{fmt.entero(len(r['id']))} equipos con tiempo registrado "
                       "(se omiten los equipos con valor 0).").pack(anchor="w", pady=(T.px(3), 0))
        # Gráficos por ID: pestañas verticales por flota y distribución de cada equipo
        self._titulo(der, "Gráficos por ID")
        flotas = [f["nombre"] for f in r["flota"]]
        guard = (self.vista.esc.vistas.get("estados_flota_id") or {}).get(self.clase)
        flota = guard if guard in flotas else (flotas[0] if flotas else None)
        alto = T.px(22) * max(n, 2) + T.px(30)
        caja = ttk.Frame(der, style="Panel.TFrame")
        caja.pack(fill="both", expand=True)
        tira = TiraVertical(caja, flotas, flota, lambda v: self._elegir_flota(v, cuerpo, r, alto))
        tira.pack(side="left", fill="y")
        cuerpo = ttk.Frame(caja, style="Panel.TFrame", height=alto)
        cuerpo.pack(side="left", fill="both", expand=True, padx=(T.px(6), 0))
        cuerpo.pack_propagate(False)
        self._grafico_id(cuerpo, r, flota, alto)

    def _elegir_flota(self, flota, cuerpo, r, alto):
        self.vista.esc.vistas.setdefault("estados_flota_id", {})[self.clase] = flota
        for w in cuerpo.winfo_children():
            w.destroy()
        self._grafico_id(cuerpo, r, flota, alto)

    def _grafico_id(self, cuerpo, r, flota, alto):
        ids = [e for e in r["id"] if e.get("flota") == flota]
        if not ids:
            return
        necesario = 50 + 22 * len(ids)
        if T.px(necesario) <= alto:
            distribucion(cuerpo, ids, alto=alto / T.escala, nombre=f"Distribución por ID – {flota}").pack(
                fill="both", expand=True)
            return
        zona = ScrollFrame(cuerpo, margen_inferior=False)
        zona.pack(fill="both", expand=True)
        distribucion(zona.interior, ids, alto=necesario, nombre=f"Distribución por ID – {flota}").pack(fill="x")


class PaginaAnalisis(ttk.Frame):
    def __init__(self, master, vista):
        super().__init__(master, style="Panel.TFrame")
        self.vista = vista
        self.esc = vista.esc
        self._sucia = True
        self.vacio = Placeholder(self, "Sin Resultados",
                                 "Importe los archivos del modelo y ejecute el análisis (F5) para ver los resultados.")
        self.sub = Pestanas(self)
        self.lbl_fecha = ttk.Label(self.sub.derecha, style="PanelSuave.TLabel", font=T.f["chica"])
        self.lbl_fecha.pack(side="right", padx=(T.px(4), T.px(10)))
        self.seg_modo = Segmentado(self.sub.derecha, MODOS, self.esc.vistas.get("estados_modo", "resumen"),
                                   self._modo)
        self.seg_modo.pack(side="right", padx=(T.px(8), T.px(10)), pady=T.px(3))
        self.vistas = {}
        for clase in modelo.ORDEN_CLASES:
            v = VistaClase(self.sub, self, clase)
            self.vistas[clase] = v
            self.sub.add(v, text=modelo.CLASES[clase]["plural"], contador=0)

    def filas_kpi(self):
        """Alto común de las tarjetas (no cambia al pasar de una subpestaña a otra)."""
        clases = (self.esc.resultados or {}).get("clases", {})
        return max([len(r.get("flota", [])) for r in clases.values()] + [3]) + 1

    def _modo(self, valor):
        self.esc.vistas["estados_modo"] = valor
        self.esc.marcar_sucio()
        self.sub.marcar_sucias(excepto=self.sub.select())
        actual = self.sub.select()
        if actual is not None:
            actual.construir()

    def refrescar(self):
        res = self.esc.resultados
        clases = (res or {}).get("clases", {})
        if not clases:
            self.sub.pack_forget()
            self.vacio.pack(fill="both", expand=True)
            return
        self.vacio.pack_forget()
        self.sub.pack(fill="both", expand=True, padx=T.px(8), pady=(T.px(2), T.px(8)))
        self.seg_modo.set(self.esc.vistas.get("estados_modo", "resumen"))
        try:
            self.lbl_fecha.configure(text="Calculado el " + fmt.fecha_hora(datetime.fromisoformat(res["fecha"])))
        except Exception:
            self.lbl_fecha.configure(text="")
        primero = None
        for clase, v in self.vistas.items():
            if clase in clases:
                self.sub.tab(v, state="normal", contador=clases[clase]["n_equipos"])
                primero = primero or v
            else:
                self.sub.tab(v, state="disabled", contador=None)
        actual = self.sub.select()
        if actual is None or actual.clase not in clases:
            actual = primero
        self.sub.marcar_sucias()
        if actual is not None:
            if self.sub.select() is not actual:
                self.sub.select(actual)
            else:
                actual.construir()
