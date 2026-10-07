"""Panel lateral 'Archivos del Modelo' (lista gráfica de CSV) y ventana de selección de inputs.

Selección como en el Explorador de Windows: clic (uno), Ctrl+clic (agrega o quita), Shift+clic (rango, hacia
arriba o hacia abajo) y Ctrl+A (todos)."""
import os
import tkinter as tk
from tkinter import ttk

import fmt
from tema import T, Tooltip
from ui_comun import ScrollFrame, VentanaHerramienta, mostrar_menu, nuevo_menu, tamano_legible


def detalle_archivo(a):
    partes = [tamano_legible(a.get("tamano"))]
    if a.get("filas") is not None:
        partes.append(f"{fmt.entero(a['filas'])} filas")
    return " · ".join(partes)


class PanelArchivos(ttk.Frame):
    """Lista de archivos CSV del escenario con iconos, estado y barra de acciones."""

    # (icono, información al pasar el mouse, método, requiere selección)
    ACCIONES = [("agregar_archivo", "Importar Inputs (agregar CSV al escenario)", "_importar", False),
                ("cambiar", "Cambiar Input (reemplazar el archivo seleccionado por otro)", "_cambiar", True),
                ("borrar", "Eliminar del Escenario los archivos seleccionados (no se borran del disco)", "_eliminar", True),
                ("carpeta", "Mostrar Carpeta del Archivo", "_carpeta", True),
                ("abrir_externo", "Abrir Archivo con el programa predeterminado", "_abrir", True)]

    def __init__(self, master, vista):
        super().__init__(master, style="Tarjeta.TFrame")
        self.vista = vista
        self.esc = vista.esc
        self._sel = []                    # nombres seleccionados (en orden de selección)
        self._ancla = None
        self._marcos = {}

        cab = ttk.Frame(self, style="Panel.TFrame", padding=(T.px(12), T.px(8), T.px(6), T.px(4)))
        cab.pack(fill="x", padx=1, pady=(1, 0))
        ttk.Label(cab, text="Archivos del Modelo", style="Negrita.TLabel").pack(side="left")
        self.btn_pin = ttk.Button(cab, style="Icono.TButton", command=vista.alternar_panel)
        self.btn_pin.pack(side="right")
        Tooltip(self.btn_pin, "Fijar / Ocultar Automáticamente")
        self.barra = ttk.Frame(self, style="Panel.TFrame", padding=(T.px(8), 0, T.px(8), T.px(6)))
        self.barra.pack(fill="x", padx=1)
        self._botones = []
        for icono, tip, metodo, req in self.ACCIONES:
            b = ttk.Button(self.barra, style="Icono.TButton", command=getattr(self, metodo), takefocus=False)
            b.pack(side="left", padx=(0, T.px(2)))
            Tooltip(b, tip)
            self._botones.append((b, icono, req))
        ttk.Frame(self, style="Linea.TFrame", height=1).pack(fill="x", padx=1)
        self.lista = ScrollFrame(self, margen_inferior=False)
        self.lista.pack(fill="both", expand=True, padx=1)
        ttk.Frame(self, style="Linea.TFrame", height=1).pack(fill="x", padx=1)
        self.pie = ttk.Label(self, style="PanelSuave.TLabel", padding=(T.px(12), T.px(6)))
        self.pie.pack(fill="x", padx=1, pady=(0, 1))
        T.registrar(self.refrescar)
        self.refrescar()

    # ------------------------------------------------------------------
    def actualizar_pin(self, fijo):
        self.btn_pin.configure(image=T.icono("pin", 15, T.p["acento"] if fijo else T.p["suave"]))

    def _seleccionados(self):
        return [a for n in self._sel for a in [self.esc.archivo(n)] if a]

    def _pintar_botones(self):
        n = len(self._seleccionados())
        for b, icono, req in self._botones:
            activo = not req or n > 0
            b.configure(image=T.icono(icono, 16, T.p["texto"] if activo else T.p["deshab"]))
            b.state(["!disabled"] if activo else ["disabled"])

    def refrescar(self):
        for w in self.lista.interior.winfo_children():
            w.destroy()
        self._marcos = {}
        archivos = self.esc.archivos
        self._sel = [n for n in self._sel if self.esc.archivo(n)]
        if not archivos:
            ttk.Label(self.lista.interior, style="PanelSuave.TLabel", wraplength=T.px(220),
                      justify="left", padding=(T.px(14), T.px(18)),
                      text="Aún no hay archivos.\n\nUse el botón «Importar Inputs» o Modelo ▸ Importar "
                           "Resultados Simulación CSV para agregarlos.").pack(fill="x")
        for a in archivos:
            self._item(a)
        incl = sum(1 for a in archivos if a.get("incluido", True))
        total = sum(a.get("tamano") or 0 for a in archivos)
        sel = f" · {len(self._sel)} Seleccionados" if len(self._sel) > 1 else ""
        self.pie.configure(text=f"{len(archivos)} Archivos · {incl} Incluidos · {total / 1024 ** 2:,.1f} MB{sel}")
        self.actualizar_pin(self.vista.panel_fijo)
        self._pintar_botones()

    def _item(self, a):
        p = T.p
        faltante = not a.get("encontrado", True)
        excluido = not a.get("incluido", True)
        elegido = a["nombre"] in self._sel
        fondo = p["sel"] if elegido else p["panel"]
        color_icono = p["aviso_borde"] if faltante else (p["deshab"] if excluido else p["acento"])
        marco = tk.Frame(self.lista.interior, background=fondo, padx=T.px(10), pady=T.px(7))
        marco.pack(fill="x")
        ico = tk.Label(marco, image=T.icono("csv", 24, color_icono), background=fondo)
        ico.pack(side="left", padx=(0, T.px(10)))
        textos = tk.Frame(marco, background=fondo)
        textos.pack(side="left", fill="x", expand=True)
        nombre = tk.Label(textos, text=a["nombre"], background=fondo,
                          foreground=p["deshab"] if (excluido or faltante) else p["texto"],
                          font=T.f["negrita"], anchor="w")
        nombre.pack(fill="x")
        estado = "No encontrado" if faltante else (("Excluido · " if excluido else "") + detalle_archivo(a))
        det = tk.Label(textos, text=estado, background=fondo,
                       foreground=p["aviso_borde"] if faltante else p["suave"], font=T.f["chica"], anchor="w")
        det.pack(fill="x")
        lbl = None
        if faltante:
            lbl = tk.Label(marco, image=T.icono("alerta", 14, p["aviso_borde"]), background=fondo)
            lbl.pack(side="right")
            Tooltip(lbl, "Archivo no encontrado")
        else:
            lbl = tk.Label(marco, image=T.icono("ok", 14, p["ok"] if not excluido else p["deshab"]),
                           background=fondo, cursor="hand2")
            lbl.pack(side="right")
            Tooltip(lbl, "Incluido en el análisis (clic para excluir)" if not excluido else
                    "Excluido del análisis (clic para incluir)")
            lbl.bind("<Button-1>", lambda e, arch=a: self._alternar(arch))
        widgets = [marco, ico, textos, nombre, det, lbl]
        self._marcos[a["nombre"]] = widgets
        for w in widgets:
            w.bind("<Enter>", lambda e, ws=widgets, n=a["nombre"]: self._hover(ws, n, True), add="+")
            w.bind("<Leave>", lambda e, ws=widgets, n=a["nombre"]: self._hover(ws, n, False), add="+")
            w.bind("<Button-3>", lambda e, n=a["nombre"]: self._contextual(e, n))
        for w in widgets[:5]:
            w.bind("<Button-1>", lambda e, n=a["nombre"]: self._clic(n, ""))
            w.bind("<Control-Button-1>", lambda e, n=a["nombre"]: self._clic(n, "ctrl"))
            w.bind("<Shift-Button-1>", lambda e, n=a["nombre"]: self._clic(n, "shift"))
            w.bind("<Control-a>", lambda e: self._todos())

    def _hover(self, widgets, nombre, dentro):
        c = T.p["sel"] if nombre in self._sel else (T.p["hover"] if dentro else T.p["panel"])
        for w in widgets:
            try:
                w.configure(background=c)
            except tk.TclError:
                pass

    def _clic(self, nombre, modo):
        nombres = [a["nombre"] for a in self.esc.archivos]
        if modo == "shift" and self._ancla in nombres:
            i, j = nombres.index(self._ancla), nombres.index(nombre)
            a, b = (i, j) if i <= j else (j, i)
            self._sel = nombres[a:b + 1] if i <= j else list(reversed(nombres[a:b + 1]))
        elif modo == "ctrl":
            if nombre in self._sel:
                self._sel.remove(nombre)
            else:
                self._sel.append(nombre)
            self._ancla = nombre
        else:
            self._sel = [nombre]
            self._ancla = nombre
        self._repintar_seleccion()
        self.focus_set()

    def _todos(self):
        self._sel = [a["nombre"] for a in self.esc.archivos]
        self._repintar_seleccion()

    def _repintar_seleccion(self):
        for n, ws in self._marcos.items():
            self._hover(ws, n, False)
        self._pintar_botones()
        archivos = self.esc.archivos
        incl = sum(1 for a in archivos if a.get("incluido", True))
        total = sum(a.get("tamano") or 0 for a in archivos)
        sel = f" · {len(self._sel)} Seleccionados" if len(self._sel) > 1 else ""
        self.pie.configure(text=f"{len(archivos)} Archivos · {incl} Incluidos · {total / 1024 ** 2:,.1f} MB{sel}")

    def _alternar(self, a):
        if not a.get("encontrado", True):
            return
        objetivo = self._seleccionados() if a["nombre"] in self._sel and len(self._sel) > 1 else [a]
        nuevo = not a.get("incluido", True)
        self.esc.aplicar_seleccion({x["nombre"]: nuevo for x in objetivo if x.get("encontrado", True)})
        self.vista.tras_cambio_archivos()

    def _contextual(self, e, nombre):
        if nombre not in self._sel:
            self._clic(nombre, "")
        m = nuevo_menu(self)
        a = self.esc.archivo(nombre)
        m.add_command(label="Abrir Archivo", command=self._abrir,
                      state="disabled" if not (a and a.get("encontrado", True)) else "normal")
        mostrar_menu(m, e)

    # --- acciones de la barra ----------------------------------------------------------------
    def _importar(self):
        self.vista.app.importar()

    def _cambiar(self):
        sel = self._seleccionados()
        if sel:
            self.vista.app.reubicar(self.vista, sel[-1]["nombre"])

    def _eliminar(self):
        sel = self._seleccionados()
        if sel:
            self.vista.app.eliminar_archivos(self.vista, [a["nombre"] for a in sel])

    def _carpeta(self):
        sel = self._seleccionados()
        if sel:
            self.vista.app.mostrar_carpeta(sel[-1].get("ruta"))

    def _abrir(self):
        for a in self._seleccionados()[:5]:
            self.vista.app.abrir_archivo(a.get("ruta"))


class DialogoInputs(VentanaHerramienta):
    """'Inputs para Análisis': casillas para elegir qué CSV se cargarán (no modal)."""

    def __init__(self, padre, escenario, al_aceptar=None, pagina=None):
        super().__init__(padre, "Inputs para Análisis", al_aceptar, True, pagina)
        p = T.p
        self.esc = escenario
        self.vars = {}
        marco = ttk.Frame(self, style="Panel.TFrame", padding=(T.px(20), T.px(16)))
        marco.pack(fill="both", expand=True)
        ttk.Label(marco, text="Inputs para Análisis", style="Titulo.TLabel").pack(anchor="w")
        ttk.Label(marco, style="PanelSuave.TLabel", wraplength=T.px(520), justify="left",
                  text="Marque los archivos que se utilizarán en el análisis. "
                       "Los archivos no encontrados se omiten automáticamente.").pack(
            anchor="w", pady=(T.px(4), T.px(12)))
        botones = ttk.Frame(marco, style="Panel.TFrame")
        botones.pack(side="bottom", fill="x", pady=(T.px(14), 0))
        ttk.Button(botones, text="Seleccionar Todo", command=lambda: self._todo(True)).pack(side="left")
        ttk.Button(botones, text="Ninguno", command=lambda: self._todo(False)).pack(side="left", padx=(T.px(8), 0))
        ttk.Button(botones, text="Cargar", style="Accent.TButton", command=self.aceptar).pack(side="right")
        ttk.Button(botones, text="Cancelar", command=self.cancelar).pack(side="right", padx=(0, T.px(8)))
        caja = tk.Frame(marco, background=p["borde"], padx=1, pady=1)
        caja.pack(fill="both", expand=True)
        zona = ScrollFrame(caja, margen_inferior=False)
        zona.pack(fill="both", expand=True)
        interior = zona.interior
        for a in escenario.archivos:
            faltante = not a.get("encontrado", True) or not os.path.isfile(a.get("ruta") or "")
            fila = ttk.Frame(interior, style="Panel.TFrame", padding=(T.px(12), T.px(8)))
            fila.pack(fill="x")
            ttk.Label(fila, image=T.icono("csv", 24, p["aviso_borde"] if faltante else p["acento"]),
                      style="Panel.TLabel").pack(side="left", padx=(0, T.px(10)))
            textos = ttk.Frame(fila, style="Panel.TFrame")
            textos.pack(side="left", fill="x", expand=True)
            ttk.Label(textos, text=a["nombre"], style="Negrita.TLabel").pack(anchor="w")
            det = "No encontrado en la ubicación guardada" if faltante else detalle_archivo(a)
            ttk.Label(textos, text=det, style="PanelSuave.TLabel" if not faltante else "Panel.TLabel",
                      foreground=p["aviso_borde"] if faltante else None).pack(anchor="w")
            var = tk.BooleanVar(value=(a.get("incluido", True) and not faltante))
            self.vars[a["nombre"]] = var
            ttk.Checkbutton(fila, variable=var, style="Panel.TCheckbutton",
                            state="disabled" if faltante else "normal").pack(side="right")
            ttk.Frame(interior, style="Linea.TFrame", height=1).pack(fill="x")
        interior.update_idletasks()
        zona.lienzo.configure(width=T.px(580), height=min(interior.winfo_reqheight(), T.px(8 * 64)))
        self.bind("<Return>", lambda e: self.aceptar())
        self._inicial = {n: v.get() for n, v in self.vars.items()}

    def _todo(self, valor):
        for nombre, var in self.vars.items():
            a = self.esc.archivo(nombre)
            if a and a.get("encontrado", True) and os.path.isfile(a.get("ruta") or ""):
                var.set(valor)

    def resultado_actual(self):
        return {n: v.get() for n, v in self.vars.items()}

    def resultado_al_cerrar(self):
        # al cerrarse por abrir otra ventana solo se carga si hubo cambios
        actual = self.resultado_actual()
        return actual if actual != self._inicial else None
