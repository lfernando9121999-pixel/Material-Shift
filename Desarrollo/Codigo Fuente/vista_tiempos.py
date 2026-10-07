"""Pestaña 'Análisis por Tiempos' (hojas Analytics by h-eq / Analytics by yr-eq).

Por flota: horas por actividad agrupadas en los seis estados, expresadas por equipo
(h/día-eq = Σ horas / N° equipos / días; h/periodo-eq = Σ horas / N° equipos), con
Horas Productivas, Disponibilidad, Utilización y Horas por Equipo (suma ≈ 24 ó ≈ 24 × días).

Reporte por Flota: tablas de detalle (actividad × estado) con los indicadores a la derecha.
Reporte Gráfico : comparación visual entre flotas y por actividad, con filtros de flotas e IDs.
"""
import tkinter as tk
from tkinter import ttk

import fmt
import modelo
from graficos import GraficoBarras
from tema import COLOR_ESTADO, T
from ui_comun import Aviso, Placeholder, ScrollFrame, TablaDatos
from ui_github import MultiSeleccion, Pestanas, Segmentado


def _nombre_corto(col):
    return col.replace("(hs)", "").replace("(h)", "").strip()


def _fmt(unidad):
    dec = modelo.UNIDADES[unidad]["decimales"]
    return lambda v: "" if v is None else f"{v:,.{dec}f}"


def _paso_actividad(vmax, unidad, dias):
    base = 1.0 if unidad == "dia" else float(dias)
    for m in (0.5, 1, 2, 4, 8):
        if vmax / (m * base) <= 6:
            return m * base
    return 8 * base


class VistaTiemposClase(ttk.Frame):
    def __init__(self, master, pagina, clase):
        super().__init__(master, style="Panel.TFrame")
        self.pagina, self.clase = pagina, clase
        self.info = modelo.CLASES[clase]
        self._pendiente = True
        self.zona = ScrollFrame(self)
        self.zona.pack(fill="both", expand=True)

    # ---------------------------------------------------------------------------------
    def refrescar(self):
        self.construir()

    def construir(self):
        self._pendiente = False
        self._sucia = False
        nuevo = self.zona.preparar()
        try:
            self._construir(nuevo)
        finally:
            self.zona.publicar(nuevo)

    def _construir(self, interior):
        vista = self.pagina.vista
        unidad, modo = vista.unidad_tiempos, vista.modo_tiempos
        u = modelo.UNIDADES[unidad]
        cont = ttk.Frame(interior, style="Panel.TFrame", padding=(T.px(18), T.px(10)))
        cont.pack(fill="both", expand=True)
        t = (self.pagina.esc.resultados or {}).get("tiempos", {}).get(self.clase)
        cab = ttk.Frame(cont, style="Panel.TFrame")
        cab.pack(fill="x")
        ttk.Label(cab, text=f"{u['titulo']} – {self.info['plural']} ({u['unidad']})",
                  style="Subtitulo.TLabel").pack(side="left")
        Segmentado(cab, [("tabla", "Tablas"), ("grafico", "Gráfico")], modo,
                   self.pagina.cambiar_modo).pack(side="right")
        ttk.Label(cont, style="PanelSuave.TLabel", font=T.f["chica"],
                  text=("Valores por equipo: Σ horas de la flota ÷ N° de equipos"
                        + (f" ÷ {self.pagina.esc.dias:g} días." if unidad == "dia" else " (periodo simulado)."))
                  ).pack(anchor="w", pady=(T.px(1), T.px(8)))
        if not t or not t.get("ids"):
            Aviso(cont, "No hay datos de tiempos para esta clase. Ejecute el análisis (F5) "
                        "con los archivos CSV disponibles.").pack(fill="x")
            return
        if not self.pagina.esc.vigente:
            Aviso(cont, "Los resultados no corresponden a la configuración actual. "
                        "Ejecute nuevamente el análisis (F5).").pack(fill="x", pady=(0, T.px(8)))

        flotas = modelo.flotas_de(t)
        ids_flotas, ids_elegidos = flotas, None
        if modo == "grafico":
            barra = ttk.Frame(cont, style="Panel.TFrame")
            barra.pack(fill="x", pady=(0, T.px(8)))
            mf = MultiSeleccion(barra, "Flotas", flotas, self._cambio_flotas, plural="Todas")
            mf.seleccion = self.sel_flotas if self.sel_flotas and set(self.sel_flotas) <= set(flotas) else None
            mf._texto()
            mf.pack(side="left")
            ids_flotas = mf.valores()
            ids_disp = [e["id"] for e in t["ids"] if e["flota"] in ids_flotas]
            mi = MultiSeleccion(barra, "IDs", ids_disp, self._cambio_ids, plural="Todos")
            mi.seleccion = [i for i in (self.sel_ids or []) if i in ids_disp] or None
            mi._texto()
            mi.pack(side="left", padx=(T.px(14), 0))
            ids_elegidos = set(mi.valores())

        dias = self.pagina.esc.dias
        bloques = []
        for f in ids_flotas:
            ids = [e for e in t["ids"] if e["flota"] == f and (ids_elegidos is None or e["id"] in ids_elegidos)]
            b = modelo.bloque_tiempos(t, ids, unidad, dias)
            if b:
                bloques.append((f, ids, b))
        if not bloques:
            Aviso(cont, "La selección no contiene equipos.").pack(fill="x")
            return
        if modo == "grafico":
            self._reporte_grafico(cont, t, bloques, unidad, u)
        else:
            for f, ids, b in bloques:
                self._bloque_tabla(cont, t, f, ids, b, unidad)

    # selección de flotas e IDs del Reporte Gráfico (se guarda en el escenario para exportar lo que se ve)
    @property
    def sel_flotas(self):
        return self.pagina.esc.vistas.setdefault("tiempos_flotas", {}).get(self.clase)

    @property
    def sel_ids(self):
        return self.pagina.esc.vistas.setdefault("tiempos_ids", {}).get(self.clase)

    def _cambio_flotas(self, valores):
        todas = modelo.flotas_de((self.pagina.esc.resultados or {}).get("tiempos", {}).get(self.clase) or {"ids": []})
        self.pagina.esc.vistas.setdefault("tiempos_flotas", {})[self.clase] = None if set(valores) == set(todas) else valores
        self.after_idle(self.construir)

    def _cambio_ids(self, valores):
        self.pagina.esc.vistas.setdefault("tiempos_ids", {})[self.clase] = valores
        self.after_idle(self.construir)

    # ---- Reporte Gráfico ---------------------------------------------------------------
    def _reporte_grafico(self, cont, t, bloques, unidad, u):
        dias = self.pagina.esc.dias
        f = _fmt(unidad)
        ttk.Label(cont, text=f"Distribución por Estado ({u['unidad']})", style="Subtitulo.TLabel").pack(anchor="w")
        g = GraficoBarras(cont, alto=70 + 36 * len(bloques))
        g.nombre = f"Distribución por Estado – {self.info['plural']} ({u['unidad']})"
        g.pack(fill="x", pady=(T.px(2), T.px(10)))
        series = [(modelo.FILA_TIEMPOS[k], [b["por_estado"][k] for _f, _i, b in bloques], COLOR_ESTADO[k])
                  for k in modelo.ORDEN_TIEMPOS]
        paso = modelo.paso_eje(unidad, dias)
        tope = paso * 6 if max(b["total"] for _f, _i, b in bloques) <= paso * 6 * 1.0005 else None
        g.datos([(fl, f"({b['n']} und)") for fl, _i, b in bloques], series, apilado=True, horizontal=True,
                formato=f, unidad=u["unidad"], paso=paso, tope=tope,
                formato_eje=lambda v: f"{v:,.0f}")

        ttk.Label(cont, text=f"Horas por Actividad ({u['unidad']})", style="Subtitulo.TLabel").pack(anchor="w")
        rejilla = ttk.Frame(cont, style="Panel.TFrame")
        rejilla.pack(fill="x", pady=(T.px(4), 0))
        rejilla.columnconfigure((0, 1), weight=1, uniform="g")
        cols_t = t["columnas"]
        for k, (fl, ids, b) in enumerate(bloques):
            caja = tk.Frame(rejilla, highlightthickness=1, highlightbackground=T.p["borde"], background=T.p["panel"])
            caja.grid(row=k // 2, column=k % 2, sticky="nsew", padx=(0 if k % 2 == 0 else T.px(8), 0),
                      pady=(0, T.px(8)))
            enc = tk.Frame(caja, background=T.p["panel"])
            enc.pack(fill="x", padx=T.px(10), pady=(T.px(6), 0))
            tk.Label(enc, text=fl, background=T.p["panel"], foreground=T.p["texto"], font=T.f["negrita"],
                     anchor="w").pack(side="left")
            tk.Label(enc, text=f"{b['n']} und  ·  Disp. {fmt.porcentaje(b['disponibilidad'])}  ·  "
                               f"Util. {fmt.porcentaje(b['utilizacion'])}",
                     background=T.p["panel"], foreground=T.p["suave"], font=T.f["negrita"], anchor="e").pack(side="right")
            gr = GraficoBarras(caja, alto=40 + 22 * len(cols_t))
            gr.nombre = f"Horas por Actividad – {fl} ({u['unidad']})"
            gr.pack(fill="x", padx=T.px(4), pady=(0, T.px(4)))
            vmax = max(b["valores"] + [0.0])
            gr.datos([_nombre_corto(c["nombre"]) for c in cols_t], [(f"Horas ({u['unidad']})", b["valores"], None)],
                     horizontal=True, colores_barra=[COLOR_ESTADO[c["estado"]] for c in cols_t], formato=f,
                     paso=_paso_actividad(vmax, unidad, dias), formato_eje=lambda v: f"{v:,.0f}" if v >= 10 or v == int(v) else f"{v:,.1f}")

    # ---- Reporte por Flota ------------------------------------------------------------------
    def _bloque_tabla(self, cont, t, flota, ids, b, unidad):
        u = modelo.UNIDADES[unidad]
        f = _fmt(unidad)
        p = T.p
        caja = tk.Frame(cont, highlightthickness=1, highlightbackground=p["borde"], background=p["panel"])
        caja.pack(fill="x", pady=(T.px(4), T.px(8)))
        cab = tk.Frame(caja, background=p["panel_alt"])
        cab.pack(fill="x")
        tipo = ids[0]["tipo"] if ids else ""
        tk.Label(cab, text=flota, background=p["panel_alt"], foreground=p["texto"],
                 font=T.f["subtitulo"]).pack(side="left", padx=T.px(12), pady=T.px(5))
        tk.Label(cab, text=f"{b['n']} und  ·  Tipo: {tipo}", background=p["panel_alt"], foreground=p["suave"],
                 font=T.f["chica"]).pack(side="left")
        cuerpo = tk.Frame(caja, background=p["panel"])
        cuerpo.pack(fill="x", padx=T.px(10), pady=T.px(8))

        # Indicadores a la derecha, apilados (transpuestos)
        kpi = tk.Frame(cuerpo, background=p["panel"])
        kpi.pack(side="right", fill="y", padx=(T.px(12), 0))
        for et, val, col in (("Horas Productivas", f(b["horas_productivas"]), COLOR_ESTADO["TP"]),
                             ("Disponibilidad", fmt.porcentaje(b["disponibilidad"]), COLOR_ESTADO["DPP"]),
                             ("Utilización", fmt.porcentaje(b["utilizacion"]), COLOR_ESTADO["DPNP"]),
                             (u["total"], f(b["total"]), COLOR_ESTADO["SB"])):
            fila = tk.Frame(kpi, background=p["panel"])
            fila.pack(fill="x", pady=(0, T.px(5)))
            tk.Frame(fila, background=col, width=T.px(3)).pack(side="left", fill="y")
            txt = tk.Frame(fila, background=p["panel"])
            txt.pack(side="left", padx=(T.px(6), 0))
            tk.Label(txt, text=et, background=p["panel"], foreground=p["suave"], font=T.f["chica"],
                     anchor="w").pack(fill="x")
            tk.Label(txt, text=val, background=p["panel"], foreground=p["texto"], font=T.f["subtitulo"],
                     anchor="w").pack(fill="x")

        cols_t = t["columnas"]
        columnas = [{"key": "estado", "titulo": "Estado", "ancho": 135}]
        columnas += [{"key": f"a{j}", "titulo": _nombre_corto(c["nombre"]), "ancho": 70, "ancla": "e"}
                     for j, c in enumerate(cols_t)]
        columnas.append({"key": "horas", "titulo": f"Horas ({u['unidad']})", "ancho": 100, "ancla": "e"})
        filas = []
        for k in modelo.ORDEN_TIEMPOS:
            vis = [modelo.FILA_TIEMPOS[k]]
            raw = [modelo.FILA_TIEMPOS[k]]
            for v, c in zip(b["valores"], cols_t):
                vis.append(f(v) if c["estado"] == k else "")
                raw.append(v if c["estado"] == k else None)
            vis.append(f(b["por_estado"][k]))
            raw.append(b["por_estado"][k])
            filas.append((vis, raw, False, "est_" + k))
        tot_vis = ["Total"] + [f(v) for v in b["valores"]] + [f(b["total"])]
        filas.append((tot_vis, ["Total"] + b["valores"] + [b["total"]], True))
        tabla = TablaDatos(cuerpo, columnas, alto=len(filas), hscroll=True, ordenable=False)
        for k in modelo.ORDEN_TIEMPOS:
            tabla.etiqueta("est_" + k, foreground=COLOR_ESTADO[k])
        tabla.pack(side="left", fill="x", expand=True)
        tabla.cargar(filas)


class PaginaTiempos(ttk.Frame):
    def __init__(self, master, vista):
        super().__init__(master, style="Panel.TFrame")
        self.vista = vista
        self.esc = vista.esc
        self.vacio = Placeholder(self, "Sin Resultados",
                                 "Ejecute el análisis (F5) para generar el análisis por tiempos.")
        self.cuerpo = ttk.Frame(self, style="Panel.TFrame")
        self.sub = Pestanas(self.cuerpo, al_cambiar=self._al_mostrar)
        self.seg_unidad = Segmentado(self.sub.derecha, [(k, v["boton"]) for k, v in modelo.UNIDADES.items()],
                                     vista.unidad_tiempos, self.cambiar_unidad)
        self.seg_unidad.pack(side="right", padx=T.px(8), pady=T.px(3))
        self.vistas = {}
        for clase in modelo.ORDEN_CLASES:
            v = VistaTiemposClase(self.sub, self, clase)
            self.vistas[clase] = v
            self.sub.add(v, text=modelo.CLASES[clase]["plural"], contador=0)
        self.sub.pack(fill="both", expand=True)
        self._sucia = True

    def _al_mostrar(self, pagina):
        if getattr(pagina, "_pendiente", False):
            pagina.construir()

    def cambiar_unidad(self, valor):
        self.vista.unidad_tiempos = valor
        self._reconstruir()

    def cambiar_modo(self, valor):
        self.vista.modo_tiempos = valor
        self._reconstruir()

    def _reconstruir(self):
        for v in self.vistas.values():
            v._pendiente = True
        actual = self.sub.select()
        if actual is not None:
            self.after_idle(actual.construir)

    def refrescar(self):
        self.seg_unidad.set(self.vista.unidad_tiempos)
        tiempos = (self.esc.resultados or {}).get("tiempos") or {}
        if not tiempos:
            self.cuerpo.pack_forget()
            self.vacio.pack(fill="both", expand=True)
            return
        self.vacio.pack_forget()
        self.cuerpo.pack(fill="both", expand=True, padx=T.px(8), pady=(T.px(2), T.px(8)))
        primero = None
        for clase, v in self.vistas.items():
            t = tiempos.get(clase)
            if t and t.get("ids"):
                self.sub.tab(v, state="normal", contador=len(t["ids"]))
                primero = primero or v
            else:
                self.sub.tab(v, state="disabled", contador=None)
            v._pendiente = True
        actual = self.sub.select()
        if actual is None or actual._pendiente and self.sub._tab(actual)["estado"] == "disabled":
            actual = primero
            if primero is not None:
                self.sub.select(primero)
        if actual is not None:
            actual.construir()
