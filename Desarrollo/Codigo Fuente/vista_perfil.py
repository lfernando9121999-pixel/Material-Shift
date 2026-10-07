"""Pestaña 'Plan de Mina': tonelaje (t) por día, semana o mes, por Fase, Flota de Pala e ID de pala.

Fecha de cada carga = 1 de enero del año de simulación + parte entera de (Fecha en horas ÷ 24).
Semana: «Sem N» (N = (día del año − 1) ÷ 7 + 1). Día: DD/MMM. Los polígonos sin fase se reportan como
«Rehandle». Filtros por mes, fase, flota de pala, ID de pala, tipo de destino y tipo de origen; la vista
se guarda con el escenario. Un divisor arrastrable separa los indicadores y gráficos de la tabla por Fase,
Flota Pala e ID Pala (agrupada y desplegable, con subtotales).
"""
import tkinter as tk
from tkinter import ttk

import registro
from graficos import GraficoBarras, paleta_series
from grilla import GrillaPivot, cubo_desde_filas
from tema import T
from ui_comun import Aviso, Placeholder, ScrollFrame, TablaArbol
from ui_github import MultiSeleccion, Segmentado, TarjetaTendencia

FILTROS = [("mes", "Mes", "Todos"), ("fase", "Fase", "Todas"), ("flota", "Flota Pala", "Todas"),
           ("id", "ID Pala", "Todos"), ("tipo_destino", "Tipo de Destino", "Todos"),
           ("tipo_origen", "Tipo de Origen", "Todos")]
DIM_A_FILTRO = {"Fase": "fase", "Flota Pala": "flota", "ID Pala": "id"}
ADJETIVO = {"dia": "Diario", "semana": "Semanal", "mes": "Mensual"}


def t_fmt(v):
    return f"{v:,.0f}"


def kt(v):
    return f"{v / 1e3:,.1f}"


def orden_flotas(esc):
    return registro.orden_palas((esc.clases.get("palas") or {}).get("tipos") or {}, esc.clases.get("palas"))


class FiltrosPerfil:
    """Filtros del encabezado de las tablas: son los mismos de la barra superior."""

    vinculado = True

    def __init__(self, pagina):
        self.pagina = pagina

    def valores(self, dim, tabla=None):
        v = self.pagina.cfg["filtros"].get(DIM_A_FILTRO.get(dim, ""))
        return None if v is None else set(v)

    def fijar(self, dim, valores, tabla=None):
        clave = DIM_A_FILTRO.get(dim)
        if clave:
            self.pagina.cfg["filtros"][clave] = None if valores is None else list(valores)
            self.pagina.esc.marcar_sucio()
            self.pagina.after_idle(self.pagina.refrescar)


class PaginaPerfil(ttk.Frame):
    def __init__(self, master, vista):
        super().__init__(master, style="Panel.TFrame")
        self.vista = vista
        self.esc = vista.esc
        self._sucia = True
        self.ctx = FiltrosPerfil(self)
        self.vacio = Placeholder(self, "Sin Datos del Registro de Cargas",
                                 "Incluya o_registro_cargas.csv y ejecute el análisis (F5).")
        self.cuerpo = ttk.Frame(self, style="Panel.TFrame")
        self.barra = ttk.Frame(self.cuerpo, style="Panel.TFrame", padding=(T.px(18), T.px(10), T.px(18), T.px(4)))
        self.barra.pack(fill="x")
        self.panel = tk.PanedWindow(self.cuerpo, orient="vertical", sashwidth=T.px(7), sashrelief="flat",
                                    borderwidth=0, opaqueresize=True, sashcursor="sb_v_double_arrow")
        self.panel.pack(fill="both", expand=True)
        self.sup = ScrollFrame(self.panel)
        self.inf = ttk.Frame(self.panel, style="Panel.TFrame")
        self.panel.add(self.sup, minsize=T.px(140), stretch="always")
        self.panel.add(self.inf, minsize=T.px(140), stretch="always")
        self.panel.bind("<Enter>", lambda e: self._sash(True))
        self.panel.bind("<Leave>", lambda e: self._sash(False))
        self._ubicado = False
        self.grilla = None
        T.registrar(lambda: self._sash(False))

    def _sash(self, activo):
        try:
            self.panel.configure(background=T.p["acento"] if activo else T.p["borde"])
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    @property
    def cfg(self):
        c = self.esc.perfil_cfg
        c.setdefault("modo", "mes")
        c.setdefault("filtros", {})
        f = c["filtros"]
        if "periodo" in f:
            p = f.pop("periodo")
            if c["modo"] == "mes" and p:
                f.setdefault("mes", p)
        return c

    def _modo(self, valor):
        self.cfg["modo"] = valor
        self.esc.marcar_sucio()
        self.after_idle(self.refrescar)

    def _filtro(self, clave, opciones, valores):
        self.cfg["filtros"][clave] = None if set(valores) == set(opciones) else list(valores)
        self.esc.marcar_sucio()
        self.after_idle(self.refrescar)

    def _limpiar(self):
        self.cfg["filtros"] = {}
        self.esc.marcar_sucio()
        self.after_idle(self.refrescar)

    def refrescar(self):
        res = self.esc.resultados or {}
        cargas = res.get("cargas")
        if not cargas or not cargas.get("perfil"):
            self.cuerpo.pack_forget()
            self.vacio.pack(fill="both", expand=True)
            return
        self.vacio.pack_forget()
        self.cuerpo.pack(fill="both", expand=True)
        self._sash(False)
        anio = self.esc.anio or 2000
        modo = self.cfg["modo"]
        nom = registro.NOMBRE_PERIODO.get(modo, "Mes")
        orden = orden_flotas(self.esc)
        ops = registro.opciones_perfil(cargas, anio, self.esc.origenes, self.esc.destinos, orden)
        filtros = self.cfg["filtros"]
        # barra fija: periodicidad y filtros
        for w in self.barra.winfo_children():
            w.destroy()
        # el botón se ubica primero para que siempre quede visible aunque la ventana sea angosta
        ttk.Button(self.barra, text="Limpiar Filtros", style="Chico.TButton", command=self._limpiar).pack(
            side="right", padx=(T.px(8), 0))
        Segmentado(self.barra, registro.MODOS_PERIODO, modo, self._modo).pack(side="left")
        for clave, etq, plural in FILTROS:
            m = MultiSeleccion(self.barra, etq, ops.get(clave, []), lambda v, k=clave: self._filtro(k, ops[k], v),
                               plural=plural, ancho=9)
            sel = filtros.get(clave)
            m.seleccion = ([x for x in sel if x in ops.get(clave, [])] or None) if sel else None
            m._texto()
            m.pack(side="left", padx=(T.px(8), 0))

        tabla = registro.tabla_perfil(cargas, anio, modo, self.esc.origenes, self.esc.destinos, filtros, orden)
        nuevo = self.sup.preparar()
        cont = ttk.Frame(nuevo, style="Panel.TFrame", padding=(T.px(18), T.px(6), T.px(18), T.px(6)))
        cont.pack(fill="both", expand=True)
        if not self.esc.vigente:
            Aviso(cont, "Los resultados no corresponden a la configuración actual. "
                        "Ejecute nuevamente el análisis (F5).").pack(fill="x", pady=(0, T.px(8)))
        for w in self.inf.winfo_children():
            w.destroy()
        self.grilla = None
        if not tabla["filas"]:
            Aviso(cont, "La selección no contiene cargas. Use «Limpiar Filtros».").pack(fill="x")
            self.sup.publicar(nuevo)
            return
        per = tabla["periodos"]
        self._indicadores(cont, tabla, modo)
        ttk.Label(cont, text=f"Tonelaje por {nom} y Flota Pala (t)", style="Subtitulo.TLabel").pack(anchor="w")
        flotas = [f for f in orden if any(x["flota"] == f for x in tabla["filas"])]
        flotas += [f for f in dict.fromkeys(x["flota"] for x in tabla["filas"]) if f not in flotas]
        paleta = paleta_series()
        series = []
        for j, fl in enumerate(flotas):
            vals = [sum(f["valores"][i] for f in tabla["filas"] if f["flota"] == fl) for i in range(len(per))]
            series.append((fl, vals, paleta[j % len(paleta)]))
        g = GraficoBarras(cont, alto=300)
        g.nombre = f"Tonelaje por {nom} y Flota Pala (t)"
        g.pack(fill="x", pady=(T.px(2), T.px(8)))
        g.datos(per, series, apilado=True, formato=lambda v: f"{v / 1e3:,.0f} kt" if v >= 1e3 else f"{v:,.0f}",
                formato_eje=lambda v: f"{v / 1e6:,.1f} Mt" if v >= 1e6 else f"{v / 1e3:,.0f} kt",
                mostrar_valores=modo == "mes", mostrar_total=modo != "dia")
        fila = ttk.Frame(cont, style="Panel.TFrame")
        fila.pack(fill="x", pady=(T.px(4), T.px(8)))
        fila.columnconfigure((0, 1), weight=1, uniform="r")
        self._por_flota(fila, tabla, flotas, nom, modo, 0)
        self._por_flota(fila, tabla, flotas, nom, modo, 1)
        self.sup.publicar(nuevo)
        # tabla inferior: Fase · Flota Pala · ID Pala × periodos (agrupada y desplegable, con subtotales)
        abajo = ttk.Frame(self.inf, style="Panel.TFrame", padding=(T.px(18), T.px(6), T.px(18), T.px(10)))
        abajo.pack(fill="both", expand=True)
        ttk.Label(abajo, text="Tonelaje por Fase, Flota e ID de Pala (t)", style="Subtitulo.TLabel").pack(anchor="w")
        cubo = cubo_desde_filas(["Fase", "Flota Pala", "ID Pala"], per,
                                [{"claves": (f["fase"], f["flota"], f["id"]), "valores": f["valores"]}
                                 for f in tabla["filas"]], "Tonelaje (t)", "int", nom)
        estado = self.esc.vistas.setdefault("plan_mina_grilla", {})
        self.grilla = GrillaPivot(abajo, self._estado_grilla, nombre="Tonelaje por Fase, Flota e ID de Pala")
        self.grilla.pack(fill="both", expand=True, pady=(T.px(4), 0))
        self.grilla.cargar(cubo, {"subtotales_columnas": False}, estado.get("colapsadas_filas"))
        if not self._ubicado:
            self.after(220, self._ubicar)

    def _estado_grilla(self, estado):
        self.esc.vistas["plan_mina_grilla"] = estado
        self.esc.marcar_sucio()

    def _ubicar(self):
        try:
            alto = self.panel.winfo_height()
            if alto > 300:
                self.panel.sash_place(0, 0, int(alto * 0.62))
                self._ubicado = True
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    def _indicadores(self, cont, tabla, modo):
        """Tarjetas con mini gráfico de la serie del periodo."""
        per, tot = tabla["periodos"], tabla["totales"]
        con = [i for i in range(len(tot)) if tot[i] > 0] or [0]
        n_pos = len(con)
        i_max = max(con, key=lambda i: tot[i])
        i_min = min(con, key=lambda i: tot[i])
        prom = tabla["total"] / n_pos
        n_palas = len({f["id"] for f in tabla["filas"]})
        n_fases = len({f["fase"] for f in tabla["filas"]})
        adj = ADJETIVO.get(modo, "Mensual")
        p = T.p
        datos = [("Tonelaje Movido Total", f"{tabla['total'] / 1e6:,.2f} Mt", f"{n_palas} palas  ·  {n_fases} fases",
                  p["est_TP"], None, None),
                 (f"Tonelaje Promedio {adj}", f"{kt(prom)} kt",
                  f"{n_pos} {registro.PLURAL_PERIODO.get(modo, 'periodos')} con carga", p["acento"], None, prom),
                 (f"Tonelaje Máximo {adj}", f"{kt(tot[i_max])} kt", per[i_max], p["est_DENP"], i_max, None),
                 (f"Tonelaje Mínimo {adj}", f"{kt(tot[i_min])} kt", per[i_min], p["est_DPNP"], i_min, None)]
        k = ttk.Frame(cont, style="Panel.TFrame")
        k.pack(fill="x", pady=(T.px(4), T.px(10)))
        for i, (tit, val, det, col, dest, linea) in enumerate(datos):
            k.columnconfigure(i, weight=1, uniform="k")
            TarjetaTendencia(k, tit, val, det, col, serie=tot, destacar=dest, linea=linea).grid(
                row=0, column=i, sticky="nsew", padx=(0 if i == 0 else T.px(8), 0))

    def _por_flota(self, master, tabla, flotas, nom, modo, columna):
        """columna 0: Material Total por Flota Pala ▸ ID Pala; 1: Promedio por periodo."""
        n_per = len(tabla["periodos"]) or 1
        total = tabla["total"] or 1.0
        promedio = columna == 1
        adj = ADJETIVO.get(modo, "Mensual")
        titulo = (f"Tonelaje Promedio {adj} – Flota Pala ▸ ID Pala (t)" if promedio
                  else "Tonelaje Total – Flota Pala ▸ ID Pala (t)")
        filas = []
        for fl in flotas:
            ids = {}
            for f in tabla["filas"]:
                if f["flota"] == fl:
                    ids[f["id"]] = ids.get(f["id"], 0.0) + f["total"]
            s = sum(ids.values())
            orden = sorted(ids.items(), key=lambda x: -x[1])
            if promedio:
                filas.append({"texto": fl, "valores": [t_fmt(s / n_per)],
                              "hijos": [{"texto": i, "valores": [t_fmt(v / n_per)]} for i, v in orden]})
            else:
                filas.append({"texto": fl, "valores": [t_fmt(s), f"{s / total * 100:,.2f}%"],
                              "hijos": [{"texto": i, "valores": [t_fmt(v), f"{v / total * 100:,.2f}%"]}
                                        for i, v in orden]})
        if promedio:
            filas.append({"texto": "Total", "valores": [t_fmt(tabla["total"] / n_per)], "total": True})
            cols = [{"titulo": "Flota Pala ▸ ID Pala", "ancho": 200}, {"titulo": f"Promedio {adj} (t)", "ancho": 150}]
        else:
            filas.append({"texto": "Total", "valores": [t_fmt(tabla["total"]), "100.00%"], "total": True})
            cols = [{"titulo": "Flota Pala ▸ ID Pala", "ancho": 200}, {"titulo": "Tonelaje (t)", "ancho": 130},
                    {"titulo": "Participación (%)", "ancho": 120}]
        caja = ttk.Frame(master, style="Panel.TFrame")
        caja.grid(row=0, column=columna, sticky="nsew", padx=(0 if columna == 0 else T.px(8), 0))
        ttk.Label(caja, text=titulo, style="Subtitulo.TLabel").pack(anchor="w", pady=(0, T.px(4)))
        t = TablaArbol(caja, cols, alto=len(filas) + 1, contexto=self.ctx, dims={"#0": "Flota Pala"}, clave="flota")
        t.pack(fill="x")
        t.cargar(filas)
