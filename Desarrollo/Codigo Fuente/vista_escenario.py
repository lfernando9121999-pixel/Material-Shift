"""Vista de un escenario: panel 'Archivos del Modelo' + pestañas de trabajo.

Solo se reconstruye la pestaña visible; las demás se marcan y se reconstruyen al mostrarse (menos espera
y sin parpadeos al cambiar un dato)."""
import tkinter as tk
from tkinter import ttk

from panel_archivos import PanelArchivos
from tema import T, Tooltip
from ui_comun import cerrar_emergente
from ui_github import Pestanas
from vista_analisis import PaginaAnalisis, SelectorReplica
from vista_cargas import PaginaCargas
from vista_inputs import PaginaInputs
from vista_perfil import PaginaPerfil
from vista_pivot_estados import PaginaPivotEstados
from vista_pivot_registro import PaginaPivotRegistro
from vista_plan import PaginaPlan
from vista_productividad import PaginaProductividad
from vista_tiempos import PaginaTiempos

ANCHO_PANEL = 290
ANCHO_TIRA = 28


class VistaEscenario(ttk.Frame):
    def __init__(self, master, app, esc):
        super().__init__(master)
        self.app, self.esc = app, esc
        self.panel_fijo = app.panel_fijo
        self.df_registro = None
        self._registro_fallido = None
        self._pendiente = False
        self._ocultar_id = None

        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        self.nb = Pestanas(self, fondo="bg", grande=True, al_cambiar=self._al_cambiar_pestana, tarjeta=True)
        self.nb.grid(row=0, column=1, sticky="nsew", padx=(T.px(6), T.px(8)), pady=(T.px(2), T.px(8)))
        # Año de la simulación: siempre visible junto a las pestañas
        self.chip_anio = tk.Label(self.nb.derecha, cursor="hand2")
        self.chip_anio.pack(side="right", padx=(T.px(4), T.px(6)), pady=T.px(4))
        self.chip_anio.bind("<Button-1>", lambda e: self._ir_anio())
        Tooltip(self.chip_anio, "Año de la simulación (clic para modificarlo en Inputs ▸ General)")
        self.sel_replica = SelectorReplica(self.nb.derecha, self)
        self.pag_inputs = PaginaInputs(self.nb, self)
        self.pag_analisis = PaginaAnalisis(self.nb, self)
        self.pag_tiempos = PaginaTiempos(self.nb, self)
        self.pag_cargas = PaginaCargas(self.nb, self)
        self.pag_productividad = PaginaProductividad(self.nb, self)
        self.pag_perfil = PaginaPerfil(self.nb, self)
        self.pag_plan = PaginaPlan(self.nb, self)
        # Tablas dinámicas: Análisis de Estados (Pivot) y Registro de Cargas (Pivot)
        self.pag_dinamicas = ttk.Frame(self.nb, style="Panel.TFrame")
        self.pag_dinamicas.refrescar = self._refrescar_dinamicas
        self.sub_dinamicas = Pestanas(self.pag_dinamicas, al_cambiar=lambda p: self.after_idle(p.al_mostrar))
        self.sub_dinamicas.pack(fill="both", expand=True, padx=T.px(8), pady=(T.px(2), T.px(8)))
        self.pag_pivot = PaginaPivotEstados(self.sub_dinamicas, self)
        self.pag_registro = PaginaPivotRegistro(self.sub_dinamicas, self)
        self.sub_dinamicas.add(self.pag_pivot, text="Análisis de Estados (Pivot)")
        self.sub_dinamicas.add(self.pag_registro, text="Registro de Cargas (Pivot)")
        self.nb.add(self.pag_inputs, text="Inputs")
        self.nb.add(self.pag_analisis, text="Análisis de Estados")
        self.nb.add(self.pag_tiempos, text="Análisis de Tiempos")
        self.nb.add(self.pag_cargas, text="Orígenes y Destinos")
        self.nb.add(self.pag_productividad, text="Tiempos y Métricas")
        self.nb.add(self.pag_perfil, text="Plan de Mina")
        self.nb.add(self.pag_plan, text="Plan vs Simulación")
        self.nb.add(self.pag_dinamicas, text="Tablas Dinámicas")
        self._ubicar_replica(self.nb.select())
        self._pintar_anio()
        T.registrar(self._pintar_anio)

        self.panel = PanelArchivos(self, self)
        self.tira = tk.Canvas(self, width=T.px(ANCHO_TIRA), highlightthickness=0, borderwidth=0)
        self.tira.bind("<Enter>", lambda e: self._mostrar_overlay())
        self.tira.bind("<Button-1>", lambda e: self._mostrar_overlay())
        self.panel.bind("<Leave>", lambda e: self._programar_ocultar())
        self.panel.bind("<Enter>", lambda e: self._cancelar_ocultar())
        self._colocar_panel()
        T.registrar(self._dibujar_tira)
        esc.conectar(self._on_cambio)

    def destroy(self):
        try:
            self.esc.desconectar(self._on_cambio)
        except Exception:
            pass
        super().destroy()

    def _pintar_anio(self):
        p = T.p
        a = self.esc.anio
        self.chip_anio.configure(text=f"   Año {a}   " if a else "   Año –   ", background=p["sel"],
                                 foreground=p["acento"], font=T.f["negrita"], padx=T.px(4), pady=T.px(1))

    def _ir_anio(self):
        self.mostrar_pestana("inputs")
        self.pag_inputs.sub.select(self.pag_inputs.general)
        try:
            self.pag_inputs.general.spn_anio.focus_set()
        except tk.TclError:
            pass

    # ---- estado de las vistas (se guarda en el escenario y se usa al exportar) -----------------
    @property
    def unidad_tiempos(self):
        return self.esc.vistas.get("unidad_tiempos", "dia")

    @unidad_tiempos.setter
    def unidad_tiempos(self, v):
        self.esc.vistas["unidad_tiempos"] = v

    @property
    def modo_tiempos(self):
        return self.esc.vistas.get("modo_tiempos", "tabla")

    @modo_tiempos.setter
    def modo_tiempos(self, v):
        self.esc.vistas["modo_tiempos"] = v

    # ---- panel fijo / auto-ocultar ----------------------------------------------------
    def alternar_panel(self):
        self.app.set_panel_fijo(not self.panel_fijo)

    def set_panel_fijo(self, fijo):
        self.panel_fijo = fijo
        self._colocar_panel()

    def _colocar_panel(self):
        self.panel.grid_forget()
        self.panel.place_forget()
        self.tira.grid_forget()
        self._cancelar_ocultar()
        if self.panel_fijo:
            self.panel.configure(width=T.px(ANCHO_PANEL))
            self.panel.pack_propagate(False)
            self.panel.grid(row=0, column=0, sticky="ns", padx=(T.px(8), 0), pady=(T.px(8), T.px(8)))
        else:
            self.tira.grid(row=0, column=0, sticky="ns", padx=(T.px(8), 0), pady=(T.px(8), T.px(8)))
            self._dibujar_tira()
        self.panel.actualizar_pin(self.panel_fijo)

    def _dibujar_tira(self):
        p = T.p
        self.tira.configure(background=p["panel_alt"])
        self.tira.delete("all")
        self.tira.create_text(T.px(ANCHO_TIRA) / 2, T.px(110), text="Archivos del Modelo", angle=90,
                              fill=p["suave"], font=T.f["negrita"])

    def _mostrar_overlay(self):
        if self.panel_fijo:
            return
        self._cancelar_ocultar()
        self.panel.configure(width=T.px(ANCHO_PANEL))
        self.panel.pack_propagate(False)
        self.panel.place(in_=self, x=T.px(ANCHO_TIRA + 8), y=T.px(8), width=T.px(ANCHO_PANEL),
                         relheight=1.0, height=-T.px(16))
        self.panel.lift()

    def _programar_ocultar(self):
        if self.panel_fijo:
            return
        self._cancelar_ocultar()
        self._ocultar_id = self.after(450, self._ocultar_overlay)

    def _cancelar_ocultar(self):
        if self._ocultar_id:
            self.after_cancel(self._ocultar_id)
            self._ocultar_id = None

    def _ocultar_overlay(self):
        self._ocultar_id = None
        if self.panel_fijo:
            return
        x, y = self.winfo_pointerxy()
        w = self.winfo_containing(x, y)
        while w is not None:
            if w is self.panel:
                self._programar_ocultar()
                return
            w = w.master
        self.panel.place_forget()

    # ---- sincronización con el escenario -------------------------------------------------
    def _on_cambio(self, que="todo"):
        if que in ("nombre", "descripcion"):
            self.app.refrescar_titulos()
            return
        if self._pendiente:
            return
        self._pendiente = True
        self.after_idle(lambda: self.refrescar_todo(que))

    def _paginas(self):
        return (self.pag_inputs, self.pag_analisis, self.pag_tiempos, self.pag_cargas, self.pag_productividad,
                self.pag_perfil, self.pag_plan, self.pag_dinamicas)

    def refrescar_todo(self, que="todo"):
        """Refresca lo visible; las demás pestañas se reconstruyen cuando se muestran."""
        self._pendiente = False
        try:
            if not self.winfo_exists():
                return
            self._pintar_anio()
            self.panel.refrescar()
            self.sel_replica.refrescar()
            actual = self.nb.select()
            self.nb.marcar_sucias(excepto=actual)
            if actual is not None:
                actual._sucia = False
                actual.refrescar()
        except tk.TclError:
            return
        self.app.refrescar_titulos()
        self.app.actualizar_barra_estado()

    def _refrescar_dinamicas(self):
        self.sub_dinamicas.marcar_sucias(excepto=self.sub_dinamicas.select())
        actual = self.sub_dinamicas.select()
        if actual is not None:
            actual.refrescar()

    def al_mostrar(self):
        """La vista vuelve a mostrarse (cambio de escenario o de ventana)."""
        actual = self.nb.select()
        if actual is not None and getattr(actual, "_sucia", False):
            actual._sucia = False
            actual.refrescar()

    def tras_cambio_archivos(self, recargar=True):
        self.app.recargar_si_corresponde(self, recargar)

    # ---- pestañas ------------------------------------------------------------------------------
    def _al_cambiar_pestana(self, pagina):
        if pagina is getattr(self, "pag_dinamicas", None):
            actual = self.sub_dinamicas.select()
            if actual is not None:
                self.after_idle(actual.al_mostrar)
        self._ubicar_replica(pagina)

    def _ubicar_replica(self, pagina):
        if not hasattr(self, "sel_replica"):
            return
        con = pagina in (getattr(self, "pag_analisis", None), getattr(self, "pag_tiempos", None),
                         getattr(self, "pag_cargas", None), getattr(self, "pag_productividad", None),
                         getattr(self, "pag_perfil", None))
        if con:
            self.sel_replica.pack(side="right", padx=(0, T.px(6)), after=self.chip_anio)
        else:
            self.sel_replica.pack_forget()

    _CLAVES = ("inputs", "analisis", "tiempos", "cargas", "productividad", "perfil", "plan", "pivot", "registro")

    def _pagina_de(self, cual):
        return {"inputs": self.pag_inputs, "analisis": self.pag_analisis, "pivot": self.pag_pivot,
                "tiempos": self.pag_tiempos, "cargas": self.pag_cargas, "productividad": self.pag_productividad,
                "perfil": self.pag_perfil, "plan": self.pag_plan, "registro": self.pag_registro}.get(cual)

    def pestana_actual(self):
        actual = self.nb.select()
        if actual is self.pag_dinamicas:
            return "registro" if self.sub_dinamicas.select() is self.pag_registro else "pivot"
        for k in self._CLAVES:
            if self._pagina_de(k) is actual:
                return k
        return "inputs"

    def mostrar_pestana(self, cual):
        pagina = self._pagina_de(cual)
        if pagina in (self.pag_pivot, self.pag_registro):
            self.nb.select(self.pag_dinamicas)
            self.sub_dinamicas.select(pagina)
        elif pagina is not None:
            self.nb.select(pagina)
        cerrar_emergente(salvo=pagina)
