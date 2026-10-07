"""Pestaña 'Registro de Cargas (Pivot)': tabla dinámica + gráfico sobre o_registro_cargas.csv.

Misma estructura que 'Análisis de Estados (Pivot)'. El archivo se carga al abrir la pestaña (una vez)
y se agregan los campos Réplica (número de réplica), Fecha, Mes, Fase e ID Pala, y la medida
«N° de Réplicas». Sin el CSV se muestra el último resultado guardado.
"""
from tkinter import ttk

import registro
from tema import T
from ui_comun import Placeholder
from vista_pivot import PaginaPivot


def config_inicial(df):
    flota = next((c for c in df.columns if c.lower().startswith("flota carg")), None)
    carga = next((c for c in df.columns if c.lower().startswith("carga (t")), None)
    varias = "Réplica" in df.columns and len(df["Réplica"].cat.categories) > 1
    filas = ([{"campo": "Réplica"}] if varias else []) + ([{"campo": flota}] if flota else [])
    return {"filas": filas, "columnas": [{"campo": "Mes"}] if "Mes" in df.columns else [],
            "valores": [{"campo": carga, "agg": "sum"}] if carga else [], "filtros": []}


class PaginaPivotRegistro(ttk.Frame):
    def __init__(self, master, vista):
        super().__init__(master, style="Panel.TFrame")
        self.vista = vista
        self.esc = vista.esc
        self._sucia = True
        self.pivot = None
        self._firma = None
        self.vacio = Placeholder(self, "Registro de Cargas (Pivot)",
                                 "Se carga al abrir esta pestaña. Requiere o_registro_cargas.csv incluido en el escenario.")
        self.vacio.pack(fill="both", expand=True)
        T.registrar(self._tema)

    def _tema(self):
        """Modo noche / claro: el pivote se reconstruye con los colores nuevos (conserva su configuración)."""
        self._firma = None
        if self.pivot is not None and self.winfo_ismapped():
            self.after_idle(self.al_mostrar)

    def refrescar(self):
        if self.winfo_ismapped():
            self.al_mostrar()

    def al_mostrar(self):
        doc = self.vista
        firma = (id(doc.df_registro), self.esc.anio)
        if self.pivot is not None and firma == self._firma:
            return
        if doc.df_registro is None and not doc.app.cargar_registro(doc):
            guardado = self.esc.pivot if isinstance(self.esc.pivot, dict) else None
            if guardado and guardado.get("resultado") and self.pivot is None:
                self._construir(None, guardado, "No se encontró o_registro_cargas.csv: se muestra el último "
                                                "resultado guardado de la tabla dinámica.")
            return
        if doc.df_registro.attrs.get("anio") != self.esc.anio:      # cambió el año: se recalculan las fechas
            doc.df_registro = registro.preparar_df_registro(doc.df_registro, self.esc.anio)
        self._firma = (id(doc.df_registro), self.esc.anio)
        guardado = self.esc.pivot if isinstance(self.esc.pivot, dict) else None
        self._construir(doc.df_registro, guardado)

    def _construir(self, df, guardado, motivo=None):
        self.vacio.pack_forget()
        if self.pivot is not None:
            self.pivot.destroy()

        def guardar(estado, sucio=True):
            self.esc.pivot = estado
            if sucio:
                self.esc.marcar_sucio()
                self.vista.app.refrescar_titulos()

        self.pivot = PaginaPivot(self, self.vista, df, guardado, medidas=registro.MEDIDAS_REGISTRO,
                                 al_guardar=guardar, motivo_solo_lectura=motivo,
                                 config_inicial=config_inicial(df) if df is not None else None)
        self.pivot.pack(fill="both", expand=True)
