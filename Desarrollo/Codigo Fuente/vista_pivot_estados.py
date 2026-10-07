"""Pestaña 'Análisis de Estados (Pivot)': tabla dinámica + gráfico por clase de equipo.

Los datos se arman desde los resultados calculados (una fila por equipo y réplica), por lo que funciona
aunque el escenario se abra sin los CSV. Flota y Tipo siguen el orden de reporte de Configuración de Equipos.
"""
from tkinter import ttk

import modelo
from tema import T
from ui_comun import Placeholder
from ui_github import Pestanas
from vista_pivot import PaginaPivot


def config_inicial(clase, replicas):
    info = modelo.CLASES[clase]
    return {
        "filas": [{"campo": "Tipo"}, {"campo": "Flota"}],
        # con varias réplicas, cada réplica en su columna (la réplica no se usa como filtro por defecto)
        "columnas": [{"campo": "Réplica"}] if len(replicas) > 1 else [],
        "valores": [{"campo": "N° Equipos", "agg": "medida"},
                    {"campo": "Horas Productivas (h)", "agg": "sum"},
                    {"campo": "Disponibilidad (%)", "agg": "medida"},
                    {"campo": "Utilización (%)", "agg": "medida"},
                    {"campo": info["metrica_id"], "agg": "sum"}],
        "filtros": [],
        "grafico_series": None,
    }


class ContenedorClase(ttk.Frame):
    def __init__(self, master, pagina, clase):
        super().__init__(master, style="Panel.TFrame")
        self.pagina, self.clase = pagina, clase
        self.pivot = None
        self._firma = None
        T.registrar(self._tema)

    def _tema(self):
        """Modo noche / claro: el pivote se reconstruye con los colores nuevos (conserva su configuración)."""
        self._firma = None
        if self.pivot is not None and self.winfo_ismapped():
            self.after_idle(self.asegurar)

    def asegurar(self):
        esc = self.pagina.esc
        res = esc.resultados or {}
        cfg_clase = esc.clases.get(self.clase) or {}
        firma = (id(res.get("por_replica")), esc.vigente, repr(cfg_clase.get("orden")))
        if self.pivot is not None and firma == self._firma:
            return
        self._firma = firma
        for w in self.winfo_children():
            w.destroy()
        self.pivot = None
        df = modelo.dataset_estados(res, self.clase, cfg_clase)
        if df.empty:
            Placeholder(self, "Sin Datos", "Ejecute el análisis (F5) para habilitar el pivote.").pack(
                fill="both", expand=True)
            return
        guardado = esc.pivots.get(self.clase)
        replicas = [str(r) for r in res.get("replicas", []) if r != "Todas"]

        def guardar(estado, sucio=True, c=self.clase):
            nuevo = {"config": estado["config"]}
            if esc.pivots.get(c) != nuevo:
                esc.pivots[c] = nuevo
                if sucio:
                    esc.marcar_sucio()
                    self.pagina.vista.app.refrescar_titulos()

        self.pivot = PaginaPivot(
            self, self.pagina.vista, df, guardado={"config": guardado["config"]} if guardado else None,
            medidas=modelo.MEDIDAS_ESTADOS, al_guardar=guardar,
            config_inicial=config_inicial(self.clase, replicas))
        self.pivot.pack(fill="both", expand=True)


class PaginaPivotEstados(ttk.Frame):
    def __init__(self, master, vista):
        super().__init__(master, style="Panel.TFrame")
        self.vista = vista
        self.esc = vista.esc
        self._sucia = True
        self.cuerpo = ttk.Frame(self, style="Panel.TFrame")
        self.cuerpo.pack(fill="both", expand=True)
        self.vacio = Placeholder(self.cuerpo, "Sin Resultados",
                                 "Ejecute el análisis (F5) para generar las tablas dinámicas.")
        # el pivote se calcula solo cuando su pestaña está a la vista (no al abrir el escenario)
        self.sub = Pestanas(self.cuerpo, al_cambiar=lambda p: p.asegurar() if self.winfo_ismapped() else None,
                            alinear="right")
        self.vistas = {}
        for clase in modelo.ORDEN_CLASES:
            c = ContenedorClase(self.sub, self, clase)
            self.vistas[clase] = c
            self.sub.add(c, text=modelo.CLASES[clase]["plural"])

    def refrescar(self):
        clases = (self.esc.resultados or {}).get("clases", {})
        if not clases:
            self.sub.pack_forget()
            self.vacio.pack(fill="both", expand=True)
            return
        self.vacio.pack_forget()
        self.sub.pack(fill="both", expand=True, padx=T.px(10), pady=(T.px(4), T.px(10)))
        primero = None
        for clase, c in self.vistas.items():
            self.sub.tab(c, state="normal" if clase in clases else "disabled")
            if clase in clases:
                primero = primero or c
        actual = self.sub.select()
        if actual is None or actual.clase not in clases:
            actual = primero
            self.sub.select(actual)
        if actual is not None and self.winfo_ismapped():
            actual.asegurar()

    def al_mostrar(self):
        actual = self.sub.select()
        if actual is not None:
            actual.asegurar()
