"""Pestaña 'Orígenes y Destinos': tonelaje por tipo de origen (con desglose por fase y polígono) y por tipo
de destino (cascada + tabla desplegable) y flujo de material Tipo de Origen → Condición → Polígono → Tipo de
Destino. Usa la configuración de Inputs ▸ Origen y Destino.

Un divisor arrastrable separa los reportes del flujo: al bajarlo aparece la barra de desplazamiento del
bloque superior. Los filtros de encabezado pueden vincularse (Tipo de Origen, Tipo de Destino, Condición).
"""
import tkinter as tk
from tkinter import ttk

import registro
from graficos import GraficoBarras
from tema import T
from ui_comun import (Aviso, FiltrosPagina, Placeholder, ScrollFrame, TablaArbol, barra_filtros, caja,
                      filtros_vista)

PAGINA = "origenes"


def mt(t):
    return "–" if t is None else f"{t / 1e6:,.2f}"


def pct(a, b):
    return f"{a / b * 100:,.2f}%" if b else "–"


def colores_tipo():
    p = T.p
    return {"Expit": p["est_TP"], "Rehandle": p["est_DPP"], "N/A": p["est_SB"],
            "Chancador": p["est_DENP"], "Stockpile": p["est_DEP"], "Botadero": p["est_DPNP"],
            "Total": p["suave"]}


def filtrar_cargas(cargas, esc, filtros):
    """Registro od filtrado por Tipo de Origen / Tipo de Destino / Condición / Fase (filtros vinculados)."""
    if not filtros:
        return cargas
    to, td, co, fa = (filtros.get(k) for k in ("Tipo de Origen", "Tipo de Destino", "Condición", "Fase"))
    od = []
    for o, d, t in cargas.get("od", []):
        cfg = esc.origenes.get(o) or {}
        if to is not None and (cfg.get("tipo") or "Expit") not in to:
            continue
        if co is not None and (cfg.get("condicion") or "Insitu") not in co:
            continue
        if fa is not None and (cfg.get("fase") or registro.fase_de(o)) not in fa:
            continue
        if td is not None and ((esc.destinos.get(d) or {}).get("tipo") or "Botadero") not in td:
            continue
        od.append([o, d, t])
    return dict(cargas, od=od)


def bloque_origen(master, datos, fases, ctx):
    """Cascada por tipo de origen + tabla Tipo ▸ Fases ▸ Polígonos."""
    tipos = [t for t in registro.TIPOS_ORIGEN if datos["tipos"].get(t, 0) > 0 or t != "N/A"]
    total = datos["total"]
    marco, _cab, cuerpo = caja(master, "Reporte por Tipo de Origen")
    _cascada(cuerpo, tipos, datos, "Reporte por Tipo de Origen (Mt)")
    filas = []
    for t in tipos:
        det = datos["detalle"].get(t, [])
        hijos = []
        for fase, tf, polis in fases.get(t, []):
            hijos.append({"texto": fase, "valores": [mt(tf), pct(tf, total), f"{len(polis):,}"],
                          "hijos": [{"texto": n, "valores": [mt(v), pct(v, total), ""]} for n, v in polis]})
        filas.append({"texto": t, "valores": [mt(datos["tipos"].get(t, 0.0)), pct(datos["tipos"].get(t, 0.0), total),
                                              f"{len(det):,}"], "hijos": hijos})
    filas.append({"texto": "Total", "valores": [mt(total), "100.00%" if total else "–",
                                                f"{sum(len(v) for v in datos['detalle'].values()):,}"], "total": True})
    tabla = TablaArbol(cuerpo, [{"titulo": "Tipo de Origen ▸ Fase ▸ Polígono", "ancho": 230},
                                {"titulo": "Material (Mt)", "ancho": 100}, {"titulo": "Participación (%)", "ancho": 110},
                                {"titulo": "N° Orígenes", "ancho": 90}], alto=len(filas) + 2,
                       contexto=ctx, dims={"#0": "Tipo de Origen"}, clave="origen")
    tabla.pack(fill="x", pady=(T.px(2), 0))
    tabla.cargar(filas)
    return marco


def bloque_destino(master, datos, ctx):
    tipos = [t for t in registro.TIPOS_DESTINO]
    total = datos["total"]
    marco, _cab, cuerpo = caja(master, "Reporte por Tipo de Destino")
    _cascada(cuerpo, tipos, datos, "Reporte por Tipo de Destino (Mt)")
    filas = []
    for t in tipos:
        det = sorted(datos["detalle"].get(t, []), key=lambda x: x[0].lower())
        filas.append({"texto": t, "valores": [mt(datos["tipos"].get(t, 0.0)), pct(datos["tipos"].get(t, 0.0), total),
                                              f"{len(det):,}"],
                      "hijos": [{"texto": n, "valores": [mt(v), pct(v, total), ""]} for n, v in det]})
    filas.append({"texto": "Total", "valores": [mt(total), "100.00%" if total else "–",
                                                f"{sum(len(v) for v in datos['detalle'].values()):,}"], "total": True})
    tabla = TablaArbol(cuerpo, [{"titulo": "Tipo de Destino ▸ Destino", "ancho": 200},
                                {"titulo": "Material (Mt)", "ancho": 100}, {"titulo": "Participación (%)", "ancho": 110},
                                {"titulo": "N° Destinos", "ancho": 90}], alto=len(filas) + 2,
                       contexto=ctx, dims={"#0": "Tipo de Destino"}, clave="destino")
    tabla.pack(fill="x", pady=(T.px(2), 0))
    tabla.cargar(filas)
    return marco


def _cascada(master, tipos, datos, nombre=""):
    col = colores_tipo()
    g = GraficoBarras(master, alto=220)
    g.nombre = nombre
    g.pack(fill="x")
    g.datos(tipos + ["Total"], [("Material (Mt)", [datos["tipos"].get(t, 0.0) / 1e6 for t in tipos] +
                                 [datos["total"] / 1e6], None)],
            cascada=True, colores_barra=[col.get(t, T.p["acento"]) for t in tipos] + [col["Total"]],
            formato=lambda v: f"{v:,.1f}", unidad="Mt", formato_eje=lambda v: f"{v:,.0f}")


class PaginaCargas(ttk.Frame):
    def __init__(self, master, vista):
        super().__init__(master, style="Panel.TFrame")
        self.vista = vista
        self.esc = vista.esc
        self._sucia = True
        self.ctx = FiltrosPagina(self.esc, PAGINA, lambda _g: self.after_idle(self.refrescar))
        self.vacio = Placeholder(self, "Sin Datos del Registro de Cargas",
                                 "Incluya o_registro_cargas.csv en Inputs para Análisis y ejecute el análisis (F5).")
        # Divisor arrastrable (resaltado al pasar el mouse) entre los reportes y el flujo de material
        self.panel = tk.PanedWindow(self, orient="vertical", sashwidth=T.px(7), sashrelief="flat", borderwidth=0,
                                    opaqueresize=True, sashcursor="sb_v_double_arrow")
        self.sup = ScrollFrame(self.panel)
        self.inf = ttk.Frame(self.panel, style="Panel.TFrame")
        self.panel.add(self.sup, minsize=T.px(120), stretch="always")
        self.panel.add(self.inf, minsize=T.px(120), stretch="always")
        self.panel.bind("<Enter>", lambda e: self._sash(True))
        self.panel.bind("<Leave>", lambda e: self._sash(False))
        self._ubicado = False
        T.registrar(lambda: self._sash(False))

    def _sash(self, activo):
        try:
            self.panel.configure(background=T.p["acento"] if activo else T.p["borde"])
        except tk.TclError:
            pass

    def refrescar(self):
        res = self.esc.resultados or {}
        cargas = res.get("cargas")
        if not cargas:
            self.panel.pack_forget()
            self.vacio.pack(fill="both", expand=True)
            return
        self.vacio.pack_forget()
        self.panel.pack(fill="both", expand=True)
        self._sash(False)
        nuevo = self.sup.preparar()
        cont = ttk.Frame(nuevo, style="Panel.TFrame", padding=(T.px(18), T.px(10), T.px(18), T.px(6)))
        cont.pack(fill="both", expand=True)
        if not self.esc.vigente:
            Aviso(cont, "Los resultados no corresponden a la configuración actual. "
                        "Ejecute nuevamente el análisis (F5).").pack(fill="x", pady=(0, T.px(8)))
        barra_filtros(cont, self.ctx)
        c = filtrar_cargas(cargas, self.esc, filtros_vista(self.esc, PAGINA))
        o = registro.por_tipo_origen(c, self.esc.origenes)
        d = registro.por_tipo_destino(c, self.esc.destinos)
        fases = registro.fases_por_tipo(c, self.esc.origenes)
        fila = ttk.Frame(cont, style="Panel.TFrame")
        fila.pack(fill="x")
        fila.columnconfigure((0, 1), weight=1, uniform="c")
        bloque_origen(fila, o, fases, self.ctx).grid(row=0, column=0, sticky="nsew", padx=(0, T.px(6)))
        bloque_destino(fila, d, self.ctx).grid(row=0, column=1, sticky="nsew", padx=(T.px(6), 0))
        self.sup.publicar(nuevo)
        for w in self.inf.winfo_children():
            w.destroy()
        abajo = ttk.Frame(self.inf, style="Panel.TFrame", padding=(T.px(18), T.px(6), T.px(18), T.px(10)))
        abajo.pack(fill="both", expand=True)
        self._flujo(abajo, c)
        if not self._ubicado:
            self.after(200, self._ubicar)

    def _ubicar(self):
        try:
            alto = self.panel.winfo_height()
            if alto > 300:
                req = self.sup.interior.winfo_reqheight()
                self.panel.sash_place(0, 0, min(req + T.px(4), int(alto * 0.68)))
                self._ubicado = True
        except tk.TclError:
            pass

    def _flujo(self, cont, cargas):
        m = registro.flujo_poligonos(cargas, self.esc.origenes, self.esc.destinos)
        if not m:
            return
        marco, _cab, cuerpo = caja(cont, "Flujo de Material: Tipo de Origen ▸ Condición ▸ Polígono → Tipo de Destino (Mt)")
        marco.pack(fill="both", expand=True)
        destinos = registro.TIPOS_DESTINO
        cols = [{"titulo": "Tipo de Origen ▸ Condición ▸ Polígono", "ancho": 260}] + \
               [{"titulo": f"{t} (Mt)", "ancho": 110} for t in destinos] + \
               [{"titulo": "Total (Mt)", "ancho": 110}, {"titulo": "Mineral a Planta (%)", "ancho": 130}]

        def valores(cnt):
            s = sum(cnt.get(t, 0.0) for t in destinos)
            return [mt(cnt.get(t, 0.0)) for t in destinos] + [mt(s), pct(cnt.get("Chancador", 0.0), s)]
        filas, tot_col = [], {t: 0.0 for t in destinos}
        for t_o in registro.TIPOS_ORIGEN:
            conds = [(k[1], v) for k, v in m.items() if k[0] == t_o]
            if not conds:
                continue
            suma_t = {t: 0.0 for t in destinos}
            hijos = []
            for cond, polis in sorted(conds, key=lambda x: registro.CONDICIONES.index(x[0])
                                      if x[0] in registro.CONDICIONES else 9):
                suma_c = {t: sum(p.get(t, 0.0) for p in polis.values()) for t in destinos}
                for t in destinos:
                    suma_t[t] += suma_c[t]
                det = sorted(polis.items(), key=lambda x: -sum(x[1].values()))
                hijos.append({"texto": cond, "valores": valores(suma_c),
                              "hijos": [{"texto": o, "valores": valores(cnt)} for o, cnt in det]})
            for t in destinos:
                tot_col[t] += suma_t[t]
            filas.append({"texto": t_o, "valores": valores(suma_t), "hijos": hijos, "abierto": True})
        filas.append({"texto": "Total", "valores": valores(tot_col), "total": True})
        tabla = TablaArbol(cuerpo, cols, alto=4, contexto=self.ctx, dims={"#0": "Tipo de Origen"}, clave="flujo")
        tabla.pack(fill="both", expand=True)          # ocupa todo el espacio bajo el divisor
        tabla.cargar(filas)
