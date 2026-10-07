"""Pestaña 'Plan vs Simulación' (subpestañas Reporte y Gráfico).

Reporte: Vector Plan frente a la simulación de cada réplica, con la variación definida en Inputs ▸ Vector
Plan. Los encabezados quedan fijos al desplazarse; las observaciones de cada parámetro van al pie de la
tabla y la fila se resalta en rojo. Gráfico: comparación por sección."""
import re
import tkinter as tk
from tkinter import ttk

import plan
from graficos import GraficoBarras, paleta_series
from tema import T
from ui_comun import Aviso, Placeholder, ScrollFrame, TablaArbol
from ui_github import Pestanas


def _corto(texto):
    return re.sub(r"^\s*\d+(\.\d+)*\.?\s*", "", texto).strip()


class _Reporte(ttk.Frame):
    def __init__(self, master, pagina):
        super().__init__(master, style="Panel.TFrame")
        self.pagina = pagina

    def refrescar(self):
        esc = self.pagina.esc
        for w in self.winfo_children():
            w.destroy()
        cont = ttk.Frame(self, style="Panel.TFrame", padding=(T.px(18), T.px(10), T.px(18), T.px(10)))
        cont.pack(fill="both", expand=True)
        reps = plan.replicas_resultados(esc)
        nombre_plan = esc.plan.get("nombre", "Plan")
        cab = ttk.Frame(cont, style="Panel.TFrame")
        cab.pack(fill="x", pady=(0, T.px(6)))
        ttk.Label(cab, text=f"{nombre_plan}   vs   {esc.nombre_visible}", style="Subtitulo.TLabel").pack(side="left")
        ttk.Button(cab, text="Exportar Resultados Plan vs Simulación…", style="Accent.TButton",
                   command=lambda: self.pagina.vista.app.exportar_plan(self.pagina.vista)).pack(side="right")
        if not esc.vigente:
            Aviso(cont, "Los resultados no corresponden a la configuración actual. "
                        "Ejecute nuevamente el análisis (F5).").pack(fill="x", pady=(0, T.px(8)))
        revisar = plan.revisar_vinculos(esc, esc.plan["filas"])
        sin = [f for f in esc.plan["filas"] if f["tipo"] == "item" and not f.get("vinculo")]
        por = esc.resultados["por_replica"]
        multi = len(reps) > 1
        cols = [{"titulo": "Indicador", "ancho": 290}, {"titulo": "Unidad", "ancho": 60, "ancla": "center"},
                {"titulo": nombre_plan, "ancho": 110}]
        for r in reps:
            cols.append({"titulo": f"{esc.nombre_visible} – Réplica {r}" if multi else esc.nombre_visible, "ancho": 130})
            cols.append({"titulo": f"Variación Réplica {r}" if multi else "Variación", "ancho": 100})
        cat = plan.catalogo(esc)
        filas, actual = [], None
        for i, f in enumerate(esc.plan["filas"]):
            if f["tipo"] == "seccion":
                actual = {"texto": f["texto"], "valores": [""] * (len(cols) - 1), "hijos": [], "tag": "seccion",
                          "abierto": True}
                filas.append(actual)
                continue
            sims = [plan.valor(esc, f.get("vinculo"), por[r]) for r in reps]
            vals = [f["unidad"], plan.texto_valor(f, f["valor"])]
            for s in sims:
                vals += [plan.texto_valor(f, s),
                         plan.texto_variacion(f, f.get("variacion"), plan.variacion(f.get("variacion"), f["valor"], s))]
            item = {"texto": f["texto"].strip(), "valores": vals,
                    "tag": "marca" if (i in revisar or not f.get("vinculo")) else None}
            (actual["hijos"] if actual is not None else filas).append(item)
        # pie: observaciones de cada parámetro (la fila se resalta en rojo)
        pie = tk.Frame(cont, background=T.p["panel"])
        pie.pack(side="bottom", fill="x", pady=(T.px(8), 0))
        obs = [(i, m) for i, m in sorted(revisar.items())]
        if obs or sin:
            tk.Label(pie, text="Observaciones", background=T.p["panel"], foreground=T.p["texto"], font=T.f["negrita"],
                     anchor="w").pack(fill="x")
            for i, motivo in obs:
                tk.Label(pie, text=f"⚠  {esc.plan['filas'][i]['texto'].strip()}: {motivo}. Revíselo en Inputs ▸ Vector "
                                   "Plan (o use «Restablecer Vínculos Sugeridos»).", background=T.p["panel"],
                         foreground=T.p["marca_fila"], font=T.f["base"], anchor="w", justify="left").pack(fill="x")
            for f in sin:
                tk.Label(pie, text=f"ⓘ  {f['texto'].strip()}: sin indicador del simulador (se muestra «-»).",
                         background=T.p["panel"], foreground=T.p["marca_fila"], font=T.f["base"], anchor="w").pack(fill="x")
        tabla = TablaArbol(cont, cols, alto=10, abiertos=True, colores=False, clave="plan_vs_sim")
        tabla.pack(fill="both", expand=True)          # encabezados fijos: la tabla se desplaza por dentro
        tabla.cargar(filas)


class _Graficos(ttk.Frame):
    def __init__(self, master, pagina):
        super().__init__(master, style="Panel.TFrame")
        self.pagina = pagina
        self.zona = ScrollFrame(self)
        self.zona.pack(fill="both", expand=True)

    def refrescar(self):
        esc = self.pagina.esc
        nuevo = self.zona.preparar()
        cont = ttk.Frame(nuevo, style="Panel.TFrame", padding=(T.px(18), T.px(12)))
        cont.pack(fill="both", expand=True)
        reps = plan.replicas_resultados(esc)
        por = esc.resultados["por_replica"]
        multi = len(reps) > 1
        secciones = []
        for f in esc.plan["filas"]:
            if f["tipo"] == "seccion":
                secciones.append((f["texto"], []))
            elif secciones:
                secciones[-1][1].append((f, [plan.valor(esc, f.get("vinculo"), por[r]) for r in reps]))
        rej = ttk.Frame(cont, style="Panel.TFrame")
        rej.pack(fill="x")
        rej.columnconfigure((0, 1), weight=1, uniform="g")
        paleta = paleta_series()
        k = 0
        nombre_plan = esc.plan.get("nombre", "Plan")
        for titulo, items in secciones:
            items = [(f, s) for f, s in items if f["valor"] is not None or any(v is not None for v in s)]
            if not items:
                continue
            pct = plan.es_porcentaje(items[0][0])
            factor = 100.0 if pct else 1.0
            unidad = items[0][0]["unidad"]
            series = [(nombre_plan, [(f["valor"] or 0.0) * factor for f, _s in items], T.p["suave"])]
            for j, r in enumerate(reps):
                series.append((f"Réplica {r}" if multi else esc.nombre_visible,
                               [(s[j] or 0.0) * factor for _f, s in items], paleta[j % len(paleta)]))
            caja = tk.Frame(rej, highlightthickness=1, highlightbackground=T.p["borde"], background=T.p["panel"])
            caja.grid(row=k // 2, column=k % 2, sticky="nsew", padx=(0 if k % 2 == 0 else T.px(8), 0),
                      pady=(0, T.px(8)))
            tk.Label(caja, text=_corto(titulo), background=T.p["panel"], foreground=T.p["texto"],
                     font=T.f["negrita"], anchor="w").pack(fill="x", padx=T.px(10), pady=(T.px(6), 0))
            g = GraficoBarras(caja, alto=60 + 26 * len(items) * (len(reps) + 1) ** 0.5 + 20)
            g.nombre = _corto(titulo)
            g.pack(fill="x", padx=T.px(4), pady=(0, T.px(4)))
            dec = plan.decimales(items[0][0])
            g.datos([_corto(f["texto"]) for f, _s in items], series, horizontal=True,
                    formato=(lambda v: f"{v:,.1f}%") if pct else (lambda v, d=dec: f"{v:,.{d}f}"),
                    unidad=unidad, formato_eje=(lambda v: f"{v:,.0f}%") if pct else (
                        lambda v: f"{v:,.0f}" if v == int(v) else f"{v:,.1f}"))
            k += 1
        self.zona.publicar(nuevo)


class PaginaPlan(ttk.Frame):
    def __init__(self, master, vista):
        super().__init__(master, style="Panel.TFrame")
        self.vista = vista
        self.esc = vista.esc
        self._sucia = True
        self.vacio = Placeholder(self)
        self.cuerpo = ttk.Frame(self, style="Panel.TFrame")
        self.sub = Pestanas(self.cuerpo)
        self.sub.pack(fill="both", expand=True, padx=T.px(8), pady=(T.px(2), T.px(8)))
        self.reporte = _Reporte(self.sub, self)
        self.graficos = _Graficos(self.sub, self)
        self.sub.add(self.reporte, text="Reporte")
        self.sub.add(self.graficos, text="Gráfico")

    def refrescar(self):
        esc = self.esc
        if not esc.plan:
            self.cuerpo.pack_forget()
            self.vacio.poner("Sin Vector Plan", "Importe las métricas del plan en Inputs ▸ Vector Plan "
                                                "(botón «Importar Métricas Plan»).")
            self.vacio.pack(fill="both", expand=True)
            return
        if not plan.replicas_resultados(esc):
            self.cuerpo.pack_forget()
            self.vacio.poner("Sin Resultados", "Ejecute el análisis (F5) para comparar la simulación con el plan.")
            self.vacio.pack(fill="both", expand=True)
            return
        self.vacio.pack_forget()
        self.cuerpo.pack(fill="both", expand=True)
        actual = self.sub.select()
        self.sub.marcar_sucias(excepto=actual)
        if actual is not None:
            actual.refrescar()
