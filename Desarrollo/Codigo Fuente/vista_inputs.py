"""Pestaña 'Inputs': General, Configuración de Equipos, Origen y Destino y Vector Plan.

Las tres primeras son requeridas (* Requerido): sin sus datos completos no se ejecuta el análisis. El
Vector Plan es opcional y se edita directamente en su tabla (Indicador Simulador (B) y Variación).
"""
import tkinter as tk
from tkinter import ttk

import config
import fmt
import modelo
import plan
import registro
from csvio import norm as csvio_norm
from dialogos import VentanaModal, aviso
from tema import COLOR_ESTADO, T, Tooltip
from ui_comun import (Aviso, Emergente, ListaChequeo, ScrollFrame, TablaArbol, TablaDatos, VentanaHerramienta,
                      colores_grupo, tamano_legible)
from ui_github import MultiSeleccion, Pestanas


# ============================================================================
# General
# ============================================================================
class PaginaGeneral(ttk.Frame):
    def __init__(self, master, vista):
        super().__init__(master, style="Panel.TFrame")
        self.vista = vista
        self.esc = vista.esc
        self._cargando = False
        self._replica_pendiente = False
        self._sucia = True

        zona = ttk.Frame(self, style="Panel.TFrame", padding=(T.px(20), T.px(12)))
        zona.pack(fill="both", expand=True)
        zona.columnconfigure(1, weight=1)
        r = 0

        def etiqueta(texto, fila, alto=False):
            ttk.Label(zona, text=texto, style="Negrita.TLabel", width=22).grid(
                row=fila, column=0, sticky="nw" if alto else "w", pady=T.px(5),
                padx=(0, T.px(14)))

        etiqueta("Inputs para Análisis", r)
        caja = ttk.Frame(zona, style="Panel.TFrame")
        caja.grid(row=r, column=1, sticky="w", pady=T.px(8))
        self.btn_inputs = ttk.Button(caja, text="Seleccionar Archivos…",
                                     command=lambda: vista.app.seleccionar_inputs(vista))
        self.btn_inputs.pack(side="left")
        self.lbl_inputs = ttk.Label(caja, style="PanelSuave.TLabel")
        self.lbl_inputs.pack(side="left", padx=(T.px(12), 0))
        r += 1

        etiqueta("Nombre del Escenario", r)
        self.var_nombre = tk.StringVar()
        self.ent_nombre = ttk.Entry(zona, textvariable=self.var_nombre, font=T.f["grande"])
        self.ent_nombre.grid(row=r, column=1, sticky="ew", pady=T.px(8))
        self.ent_nombre.bind("<KeyRelease>", self._nombre_editado)
        self.ent_nombre.bind("<FocusOut>", self._nombre_editado)
        r += 1

        etiqueta("Año", r)
        caja_a = ttk.Frame(zona, style="Panel.TFrame")
        caja_a.grid(row=r, column=1, sticky="w", pady=T.px(5))
        self.var_anio = tk.StringVar()
        self.spn_anio = ttk.Spinbox(caja_a, from_=1990, to=2100, textvariable=self.var_anio, width=7,
                                    command=self._anio)
        self.spn_anio.pack(side="left")
        self.spn_anio.bind("<FocusOut>", self._anio)
        self.spn_anio.bind("<Return>", self._anio)
        self.lbl_anio = ttk.Label(caja_a, style="PanelSuave.TLabel")
        self.lbl_anio.pack(side="left", padx=(T.px(12), 0))
        r += 1
        self.lbl_memoria = ttk.Label(zona, style="PanelSuave.TLabel", foreground=T.p["ok"], wraplength=T.px(1000),
                                     justify="left")
        self.lbl_memoria.grid(row=r, column=1, sticky="w")
        r += 1

        etiqueta("Descripción", r, alto=True)
        marco_txt = ttk.Frame(zona, style="Panel.TFrame")
        marco_txt.grid(row=r, column=1, sticky="ew", pady=T.px(5))
        marco_txt.columnconfigure(0, weight=1)
        self.txt = tk.Text(marco_txt, height=2, wrap="word", relief="flat", borderwidth=1,
                           highlightthickness=1, font=T.f["base"], undo=True,
                           padx=T.px(6), pady=T.px(4))
        self.txt.grid(row=0, column=0, sticky="ew")
        sb = ttk.Scrollbar(marco_txt, orient="vertical", command=self.txt.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.txt.configure(yscrollcommand=sb.set)
        pie = ttk.Frame(marco_txt, style="Panel.TFrame")
        pie.grid(row=1, column=0, columnspan=2, sticky="ew")
        self.var_contador = tk.StringVar()
        agarre = ttk.Label(pie, text="◢", style="PanelSuave.TLabel", cursor="sb_v_double_arrow")
        agarre.pack(side="right")
        Tooltip(agarre, "Arrastre para agrandar o reducir")
        agarre.bind("<ButtonPress-1>", self._redim_inicio)
        agarre.bind("<B1-Motion>", self._redim_mover)
        ttk.Label(pie, textvariable=self.var_contador, style="PanelSuave.TLabel").pack(
            side="right", padx=(0, T.px(6)), pady=(T.px(2), 0))
        self.txt.bind("<<Modified>>", self._desc_modificada)
        self.txt.bindtags((str(self.txt), str(self.winfo_toplevel()), "all", "Text"))
        self._retema_texto()
        T.registrar(self._retema_texto)
        r += 1

        etiqueta("Réplicas", r)
        caja2 = ttk.Frame(zona, style="Panel.TFrame")
        caja2.grid(row=r, column=1, sticky="w", pady=T.px(8))
        self.var_replica = tk.StringVar()
        self.cmb = ttk.Combobox(caja2, textvariable=self.var_replica, state="readonly", width=16)
        self.cmb.pack(side="left")
        self.cmb.bind("<<ComboboxSelected>>", self._replica_elegida)
        self.btn_replica = ttk.Button(caja2, text="Actualizar", command=self._aplicar_replica)
        self.btn_replica.pack(side="left", padx=(T.px(10), 0))
        self.lbl_replica = ttk.Label(caja2, style="PanelSuave.TLabel")
        self.lbl_replica.pack(side="left", padx=(T.px(12), 0))
        r += 1

        etiqueta("Días del Período", r)
        caja3 = ttk.Frame(zona, style="Panel.TFrame")
        caja3.grid(row=r, column=1, sticky="w", pady=T.px(8))
        self.var_dias = tk.StringVar(value=f"{self.esc.dias:g}")
        ent = ttk.Entry(caja3, textvariable=self.var_dias, width=8)
        ent.pack(side="left")
        ent.bind("<FocusOut>", self._dias)
        ent.bind("<Return>", self._dias)
        ttk.Label(caja3, style="PanelSuave.TLabel",
                  text="Se ajusta al año (365 ó 366 si es bisiesto). Divisor del Análisis Diario (h/día-eq).").pack(
            side="left", padx=(T.px(12), 0))
        r += 1

        ttk.Label(zona, text="Resumen de Archivos", style="Subtitulo.TLabel").grid(
            row=r, column=0, columnspan=2, sticky="w", pady=(T.px(18), T.px(6)))
        r += 1
        cols = [
            {"key": "archivo", "titulo": "Archivo", "ancho": 220},
            {"key": "filas", "titulo": "Filas", "ancho": 100, "ancla": "e"},
            {"key": "columnas", "titulo": "Columnas", "ancho": 90, "ancla": "e"},
            {"key": "tamano", "titulo": "Tamaño", "ancho": 100, "ancla": "e"},
            {"key": "cod", "titulo": "Codificación", "ancho": 110, "ancla": "center"},
            {"key": "sep", "titulo": "Separador", "ancho": 90, "ancla": "center"},
            {"key": "estado", "titulo": "Estado", "ancho": 130, "ancla": "center"},
        ]
        self.tabla = TablaDatos(zona, cols, alto=6, clave="inputs.archivos")
        self.tabla.grid(row=r, column=0, columnspan=2, sticky="nsew")
        zona.rowconfigure(r, weight=1)

    def _retema_texto(self):
        p = T.p
        self.txt.configure(background=p["campo"], foreground=p["texto"],
                           insertbackground=p["texto"], selectbackground=p["sel"],
                           selectforeground=p["texto"], highlightbackground=p["borde"],
                           highlightcolor=p["acento"])

    def _nombre_editado(self, _e=None):
        if self._cargando:
            return
        nuevo = self.var_nombre.get()
        if nuevo != self.esc.nombre:
            self.esc.nombre = nuevo
            self.esc.nombre_manual = True
            self.esc.marcar_sucio()
            self.esc.notificar("nombre")

    def _desc_modificada(self, _e=None):
        if not self.txt.edit_modified():
            return
        self.txt.edit_modified(False)
        if self._cargando:
            return
        texto = self.txt.get("1.0", "end-1c")
        cuenta = sum(1 for c in texto if not c.isspace())
        if cuenta > config.MAX_DESCRIPCION:
            n, corte = 0, len(texto)
            for i, c in enumerate(texto):
                if not c.isspace():
                    n += 1
                    if n > config.MAX_DESCRIPCION:
                        corte = i
                        break
            texto = texto[:corte].rstrip() if texto[corte - 1:corte].isspace() else texto[:corte]
            self._cargando = True
            self.txt.delete("1.0", "end")
            self.txt.insert("1.0", texto)
            self._cargando = False
            self.txt.edit_modified(False)
            cuenta = sum(1 for c in texto if not c.isspace())
        self.var_contador.set(f"{cuenta} / {config.MAX_DESCRIPCION} Caracteres (sin Espacios)")
        if texto != self.esc.descripcion:
            self.esc.descripcion = texto
            self.esc.marcar_sucio()
            self.esc.notificar("descripcion")

    def _redim_inicio(self, e):
        self._redim = (e.y_root, int(self.txt.cget("height")))

    def _redim_mover(self, e):
        y0, h0 = getattr(self, "_redim", (e.y_root, 2))
        linea = T.f["base"].metrics("linespace")
        self.txt.configure(height=max(2, min(20, h0 + round((e.y_root - y0) / linea))))

    def _anio(self, _e=None):
        try:
            v = int(self.var_anio.get())
            if not 1990 <= v <= 2100:
                raise ValueError
            self.esc.set_anio(v)
        except ValueError:
            self.var_anio.set(str(self.esc.anio or ""))
        self._texto_anio()

    def _texto_anio(self):
        import calendar
        a = self.esc.anio
        self.lbl_anio.configure(text="" if not a else (
            f"{'Año bisiesto' if calendar.isleap(a) else 'Año no bisiesto'} ({366 if calendar.isleap(a) else 365} días). "
            "Sugerido a partir de los CSV; puede modificarse."))

    def _dias(self, _e=None):
        try:
            v = float(self.var_dias.get().replace(",", "."))
            if v <= 0 or v > 3660:
                raise ValueError
            self.esc.set_dias(v)
        except ValueError:
            self.var_dias.set(f"{self.esc.dias:g}")

    def _opciones_replica(self):
        reps = list(self.esc.replicas)
        if len(reps) > 1:
            reps.append("Todas")
        return reps

    def _replica_elegida(self, _e=None):
        self._marcar_replica(self.var_replica.get() != self.esc.replica)

    def _marcar_replica(self, pendiente):
        self._replica_pendiente = pendiente
        if pendiente:
            self.btn_replica.configure(style="Pendiente.TButton", text="Actualizar")
            self.lbl_replica.configure(text="Cambio pendiente de aplicar")
        else:
            self.btn_replica.configure(style="Listo.TButton", text="Actualizado")
            self.lbl_replica.configure(text=f"Réplica aplicada: {self.esc.replica}" if self.esc.replicas else "")

    def _aplicar_replica(self):
        if not self._replica_pendiente:
            return
        self._marcar_replica(False)
        self.vista.app.cambiar_replica(self.vista, self.var_replica.get())

    def refrescar(self):
        self._cargando = True
        e = self.esc
        if self.var_nombre.get() != e.nombre:
            self.var_nombre.set(e.nombre)
        if self.txt.get("1.0", "end-1c") != e.descripcion:
            self.txt.delete("1.0", "end")
            self.txt.insert("1.0", e.descripcion)
            self.txt.edit_modified(False)
        cuenta = sum(1 for c in e.descripcion if not c.isspace())
        self.var_contador.set(f"{cuenta} / {config.MAX_DESCRIPCION} Caracteres (sin Espacios)")
        self._cargando = False
        self.var_dias.set(f"{e.dias:g}")
        self.lbl_memoria.configure(text=("✓  " + e.memoria_aplicada) if e.memoria_aplicada else "",
                                   foreground=T.p["ok"])
        if e.memoria_aplicada:
            self.lbl_memoria.grid()
        else:
            self.lbl_memoria.grid_remove()
        try:
            foco = self.focus_get()
        except (KeyError, tk.TclError):
            foco = None
        if foco is not self.spn_anio:
            self.var_anio.set(str(e.anio or ""))
        self._texto_anio()
        opciones = self._opciones_replica()
        self.cmb.configure(values=opciones, state="readonly" if opciones else "disabled")
        self.var_replica.set(e.replica if e.replica in opciones else (opciones[0] if opciones else ""))
        self._marcar_replica(False)
        self.btn_replica.state(["!disabled"] if opciones else ["disabled"])
        incl = sum(1 for a in e.archivos if a.get("incluido", True))
        self.lbl_inputs.configure(
            text=f"{incl} de {len(e.archivos)} Archivos Seleccionados" if e.archivos
            else "Sin Archivos. Use Modelo ▸ Importar Resultados Simulación CSV")
        self.btn_inputs.state(["!disabled"] if e.archivos else ["disabled"])
        filas = []
        for a in e.archivos:
            estado = "No Encontrado" if not a.get("encontrado", True) else (
                "Excluido" if not a.get("incluido", True) else "Incluido")
            filas.append(([a["nombre"], fmt.entero(a.get("filas")) if a.get("filas") is not None else "–",
                           fmt.entero(a.get("columnas")) if a.get("columnas") else "–",
                           tamano_legible(a.get("tamano")), (a.get("codificacion") or "–").upper(),
                           {",": "Coma (,)", ";": "Punto y Coma (;)", "\t": "Tabulación",
                            "|": "Barra (|)"}.get(a.get("delimitador"), "–"), estado],
                          [a["nombre"], a.get("filas"), a.get("columnas"), a.get("tamano"),
                           a.get("codificacion"), a.get("delimitador"), estado], False))
        self.tabla.cargar(filas)
        self.tabla.fijar_alto(max(4, min(10, len(filas))))


# ============================================================================
# Configuración de tiempos (estados) – ventana de herramienta (no modal)
# ============================================================================
class DialogoTiempos(VentanaHerramienta):
    ORDEN_ESCALON = ["TP", "DPP", "DPNP", "DEP", "DENP", "SB"]

    def __init__(self, padre, clase, columnas, mapa, al_aceptar=None, pagina=None):
        info = modelo.CLASES[clase]
        super().__init__(padre, f"Configuración de Tiempos – {info['plural']}", al_aceptar, True, pagina)
        p = T.p
        columnas = modelo.ordenar_columnas(clase, columnas)
        self.clase, self.columnas = clase, columnas
        self.vars = {}
        self._botones = {}
        marco = ttk.Frame(self, style="Panel.TFrame", padding=(T.px(20), T.px(14)))
        marco.pack(fill="both", expand=True)
        ttk.Label(marco, text=f"Configuración de Tiempos – {info['plural']}", style="Titulo.TLabel").pack(anchor="w")
        ttk.Label(marco, style="PanelSuave.TLabel", wraplength=T.px(760), justify="left",
                  text="Asigne cada columna de tiempo del archivo al estado que le corresponde.").pack(
            anchor="w", pady=(T.px(2), T.px(10)))
        botones = ttk.Frame(marco, style="Panel.TFrame")
        botones.pack(side="bottom", fill="x", pady=(T.px(12), 0))
        ttk.Button(botones, text="Restablecer Valores por Defecto", command=self._restablecer).pack(side="left")
        ttk.Button(botones, text="Aplicar", style="Accent.TButton", command=self.aceptar).pack(side="right")
        ttk.Button(botones, text="Cancelar", command=self.cancelar).pack(side="right", padx=(0, T.px(8)))
        self.lbl_sin = ttk.Label(marco, style="PanelSuave.TLabel")
        self.lbl_sin.pack(side="bottom", anchor="w", pady=(T.px(8), 0))
        caja = tk.Frame(marco, background=p["borde"], padx=1, pady=1)
        caja.pack(fill="both", expand=True)
        zona = ScrollFrame(caja, margen_inferior=False)
        zona.pack(fill="both", expand=True)
        g = zona.interior
        g.columnconfigure(0, weight=1, minsize=T.px(220))
        self._escalonado = True
        self.cab_col = tk.Label(g, background=p["cab"], foreground=p["cab_txt"], font=T.f["negrita"], anchor="w",
                                padx=T.px(12), pady=T.px(8), cursor="hand2")
        self.cab_col.grid(row=0, column=0, sticky="nsew")
        self.cab_col.bind("<Button-1>", lambda e: self._alternar_orden())
        Tooltip(self.cab_col, "Clic para alternar: orden escalonado por estado u orden del archivo")
        for j, (clave, completo, corto) in enumerate(modelo.ESTADOS, start=1):
            g.columnconfigure(j, minsize=T.px(112))
            lbl = tk.Label(g, text=corto, background=COLOR_ESTADO[clave], foreground="#FFFFFF",
                           font=T.f["chica"], wraplength=T.px(100), pady=T.px(6))
            lbl.grid(row=0, column=j, sticky="nsew", padx=1)
            Tooltip(lbl, completo)
        g.columnconfigure(len(modelo.ESTADOS) + 1, minsize=T.px(150))
        tk.Label(g, text="Plantilla Estándar", background=p["cab"], foreground=p["cab_txt"], font=T.f["chica"],
                 padx=T.px(8), pady=T.px(6)).grid(row=0, column=len(modelo.ESTADOS) + 1, sticky="nsew", padx=1)
        for col in columnas:
            var = tk.StringVar(value=mapa.get(col) or "")
            self.vars[col] = var
            etiqueta = tk.Label(g, text=col, foreground=p["texto"], font=T.f["base"], anchor="w",
                                padx=T.px(12), pady=T.px(5))
            fila_botones = []
            for clave, _c, _corto in modelo.ESTADOS:
                b = tk.Radiobutton(g, variable=var, value=clave, indicatoron=False, text="✓",
                                   selectcolor=COLOR_ESTADO[clave], activebackground=p["hover"],
                                   relief="flat", borderwidth=0, highlightthickness=0,
                                   font=T.f["negrita"], pady=T.px(3), cursor="hand2")
                fila_botones.append((clave, b))
            nota = tk.Label(g, font=T.f["chica"], anchor="w", padx=T.px(8))
            self._botones[col] = [etiqueta, None, fila_botones, nota]
            var.trace_add("write", lambda *a, c=col: self._pintar(c))
        self._ordenar_filas()
        g.update_idletasks()
        self._alto = min(g.winfo_reqheight(), T.px(540))
        zona.lienzo.configure(width=T.px(1060), height=self._alto)
        self._contar()

    def mostrar(self, ancho=None, alto=None):
        return super().mostrar()

    def _alternar_orden(self):
        self._escalonado = not self._escalonado
        self._ordenar_filas()

    def _ordenar_filas(self):
        p = T.p
        cols = list(self.columnas)
        if self._escalonado:
            pos = {k: i for i, k in enumerate(self.ORDEN_ESCALON)}
            cols.sort(key=lambda c: (pos.get(self.vars[c].get(), len(pos)), self.columnas.index(c)))
        self.cab_col.configure(text="Columna del Archivo  " + ("▼ Escalonado" if self._escalonado else "▼ Orden del Archivo"))
        for i, col in enumerate(cols, start=1):
            etiqueta, _f, botones, nota = self._botones[col]
            fondo = p["fila_alt"] if i % 2 == 0 else p["panel"]
            self._botones[col][1] = fondo
            etiqueta.configure(background=fondo)
            etiqueta.grid(row=i, column=0, sticky="nsew")
            for j, (_clave, b) in enumerate(botones, start=1):
                b.configure(background=fondo)
                b.grid(row=i, column=j, sticky="nsew", padx=1, pady=1)
            nota.configure(background=fondo)
            nota.grid(row=i, column=len(botones) + 1, sticky="nsew", padx=1, pady=1)
            self._pintar(col)

    def _pintar(self, col):
        p = T.p
        etiqueta, fondo, botones, nota = self._botones[col]
        fondo = fondo or p["panel"]
        v = self.vars[col].get()
        for clave, b in botones:
            b.configure(foreground="#FFFFFF" if v == clave else fondo,
                        activeforeground="#FFFFFF" if v == clave else fondo)
        etiqueta.configure(foreground=p["texto"] if v else p["aviso_borde"])
        est = modelo.ESTADOS_DEFECTO[self.clase].get(csvio_norm(col))
        if est and v and v != est:
            nota.configure(text=f"≠  {modelo.CORTO_ESTADO[est]}", foreground=p["aviso_borde"])
        elif est:
            nota.configure(text="=  Estándar", foreground=p["suave"])
        else:
            nota.configure(text="", foreground=p["suave"])
        self._contar()

    def _contar(self):
        n = sum(1 for v in self.vars.values() if not v.get())
        dif = modelo.diferencias_estandar(self.clase, {c: v.get() for c, v in self.vars.items() if v.get()})
        if hasattr(self, "lbl_sin"):
            texto = ("Todas las columnas tienen un estado asignado." if n == 0 else
                     f"{n} columna(s) sin estado: complételas para poder ejecutar el análisis.")
            if dif:
                texto += f"   ·   {len(dif)} columna(s) difieren de la plantilla estándar."
            self.lbl_sin.configure(text=texto)

    def _restablecer(self):
        for col, var in self.vars.items():
            var.set(modelo.estado_por_defecto(self.clase, col) or "")

    def resultado_actual(self):
        return {c: (v.get() or None) for c, v in self.vars.items()}


# ============================================================================
# Configuración de Equipos
# ============================================================================
class PaginaEstadosInputs(ttk.Frame):
    """Por clase: flotas con su tipo y categoría, resumen de la asignación de estados y orden de reporte
    (Tipo, Categoría y Flota: de arriba hacia abajo el orden de las filas; de izquierda a derecha la
    prioridad). Los avisos van al pie."""

    def __init__(self, master, vista):
        super().__init__(master, style="Panel.TFrame")
        self.vista = vista
        self.esc = vista.esc
        self._sel_orden = None
        self._sucia = True
        self.zona = ScrollFrame(self)
        self.zona.pack(fill="both", expand=True)

    def refrescar(self):
        nuevo = self.zona.preparar()
        cont = ttk.Frame(nuevo, style="Panel.TFrame", padding=(T.px(20), T.px(12)))
        cont.pack(fill="both", expand=True)
        avisos = []
        for clase in modelo.ORDEN_CLASES:
            self._clase(cont, clase, avisos)
        for a in avisos:
            Aviso(cont, a).pack(fill="x", pady=(T.px(6), 0))
        self.zona.publicar(nuevo)

    def _clase(self, padre, clase, avisos):
        info = modelo.CLASES[clase]
        cfg = self.esc.clases.get(clase)
        habilitada = cfg is not None and self.esc.clase_habilitada(clase)
        tk.Label(padre, text=info["plural"], background=T.p["panel"], foreground=T.p["acento"],
                 font=T.f["subtitulo"], anchor="w").pack(fill="x", pady=(T.px(4), T.px(4)))
        fila = tk.Frame(padre, background=T.p["panel"])
        fila.pack(fill="x", pady=(0, T.px(12)))
        if not habilitada:
            tk.Label(fila, text=f"Archivo no disponible en este escenario: {info['archivo']}",
                     background=T.p["panel"], foreground=T.p["suave"], font=T.f["base"]).pack(anchor="w")
            return
        fila.columnconfigure(0, weight=5, uniform=f"eq{clase}")
        fila.columnconfigure(1, weight=3, uniform=f"eq{clase}")
        izq = self._recuadro(fila)
        izq.grid(row=0, column=0, sticky="nsew", padx=(0, T.px(10)))
        der = self._recuadro(fila)
        der.grid(row=0, column=1, sticky="nsew")
        self._flotas(izq, clase, cfg, info)
        self._orden(der, clase, cfg)
        sin = [c for c, v in cfg["mapa_estados"].items() if not v]
        if sin:
            avisos.append(f"{info['plural']}: {len(sin)} columna(s) de tiempo sin estado asignado. "
                          "Complételas en la Configuración de Tiempos para poder ejecutar el análisis.")
        dif = modelo.diferencias_estandar(clase, {c: v for c, v in cfg["mapa_estados"].items() if v})
        if dif:
            detalle = "; ".join(f"{c.replace('(hs)', '').strip()}: {modelo.CORTO_ESTADO.get(v, v)} "
                                f"(estándar: {modelo.CORTO_ESTADO[e]})" for c, v, e in dif)
            avisos.append(f"{info['plural']}: la configuración de tiempos difiere de la plantilla estándar — {detalle}. "
                          "Esto cambia la Disponibilidad y la Utilización. Use «Restablecer Valores por Defecto» en la "
                          "Configuración de Tiempos si no fue intencional.")

    @staticmethod
    def _recuadro(master):
        p = T.p
        return tk.Frame(master, background=p["panel"], highlightthickness=1, highlightbackground=p["borde"])

    def _flotas(self, caja, clase, cfg, info):
        p = T.p
        sup = tk.Frame(caja, background=p["panel"])
        sup.pack(fill="x", padx=T.px(14), pady=(T.px(10), T.px(6)))
        tk.Label(sup, text=f"N° de {info['plural']}: {fmt.entero(cfg['n_equipos'])}", background=p["panel"],
                 foreground=p["texto"], font=T.f["negrita"]).pack(side="left")
        ttk.Button(sup, text=f"Configuración de Tiempos – {info['plural']}…",
                   command=lambda: self.vista.app.configurar_tiempos(self.vista, clase)).pack(side="right")
        cuerpo = tk.Frame(caja, background=p["panel"])
        cuerpo.pack(fill="both", expand=True, padx=T.px(14), pady=(0, T.px(12)))
        grilla = tk.Frame(cuerpo, background=p["panel"])
        grilla.pack(side="left", anchor="n")
        con_cat = clase == "perforadoras"
        titulos = ["Flota", f"N° de {info['plural']}", info["tipo_titulo"]] + ([modelo.CATEGORIA] if con_cat else [])
        for j, t in enumerate(titulos):
            tk.Label(grilla, text=t, background=p["panel"], foreground=p["suave"], font=T.f["negrita"],
                     anchor="center" if j == 1 else "w").grid(row=0, column=j, sticky="ew",
                                                             padx=(0 if j == 0 else T.px(14), T.px(10)),
                                                             pady=(0, T.px(3)))
        tipos = dict(cfg["tipos"])
        energia = cfg.get("energia") or {}
        for i, flota in enumerate(modelo.ordenar_flotas(clase, cfg["flotas"], cfg), start=1):
            tk.Label(grilla, text=flota, background=p["panel"], foreground=p["texto"], font=T.f["base"],
                     anchor="w").grid(row=i, column=0, sticky="w", pady=T.px(2))
            tk.Label(grilla, text=fmt.entero(cfg["flotas"][flota]), background=p["panel"], foreground=p["texto"],
                     font=T.f["base"]).grid(row=i, column=1, padx=(T.px(14), T.px(10)))
            seg = tk.Frame(grilla, background=p["panel"])
            seg.grid(row=i, column=2, sticky="w", padx=(T.px(14), 0))
            var = tk.StringVar(value=tipos.get(flota) or "")
            for opcion in info["tipos"]:
                ttk.Radiobutton(seg, text=opcion, value=opcion, variable=var, style="Segmento.Toolbutton",
                                command=lambda f=flota, v=var: self._elegir(clase, f, v)).pack(side="left", padx=(0, T.px(4)))
            if not var.get():
                tk.Label(seg, text="Sin Asignar", background=p["panel"], foreground=p["requerido"],
                         font=T.f["negrita"]).pack(side="left", padx=(T.px(6), 0))
            if con_cat:
                fe = tk.Frame(grilla, background=p["panel"])
                fe.grid(row=i, column=3, sticky="w", padx=(T.px(14), 0))
                var_e = tk.StringVar(value=energia.get(flota) or "")
                for opcion in modelo.ENERGIAS:
                    ttk.Radiobutton(fe, text=opcion, value=opcion, variable=var_e, style="Segmento.Toolbutton",
                                    command=lambda f=flota, v=var_e: self.esc.set_energia(f, v.get())
                                    ).pack(side="left", padx=(0, T.px(4)))
        # Resumen de la asignación de estados (N° de columnas de tiempo por estado)
        res = tk.Frame(cuerpo, background=p["panel"], highlightthickness=1, highlightbackground=p["separador"])
        res.pack(side="right", anchor="n", padx=(T.px(18), 0))
        tk.Label(res, text="Estado", background=p["cab"], foreground=p["cab_txt"], font=T.f["negrita"],
                 anchor="w", padx=T.px(10), pady=T.px(4)).grid(row=0, column=0, sticky="nsew")
        tk.Label(res, text="N°", background=p["cab"], foreground=p["cab_txt"], font=T.f["negrita"],
                 anchor="e", padx=T.px(10), pady=T.px(4)).grid(row=0, column=1, sticky="nsew")
        Tooltip(res, "N° de columnas de tiempo asignadas a cada estado (Configuración de Tiempos)")
        cuenta = {k: 0 for k in modelo.CLAVES}
        sin = 0
        for v in cfg["mapa_estados"].values():
            if v in cuenta:
                cuenta[v] += 1
            else:
                sin += 1
        cortos = {"TP": "Productivo", "DPP": "DPP", "DPNP": "DPNP", "DEP": "DEP", "DENP": "DENP", "SB": "Stand By"}
        filas = [(cortos[k], cuenta[k], COLOR_ESTADO[k], modelo.NOMBRE_ESTADO[k]) for k in cortos]
        if sin:
            filas.append(("Sin Asignar", sin, p["requerido"], "Columnas sin estado asignado"))
        for i, (nombre, n, color, completo) in enumerate(filas, start=1):
            f = tk.Frame(res, background=p["panel"])
            f.grid(row=i, column=0, sticky="nsew", padx=(T.px(8), 0))
            tk.Frame(f, background=color, width=T.px(8), height=T.px(8)).pack(side="left", padx=(0, T.px(6)))
            etq = tk.Label(f, text=nombre, background=p["panel"], foreground=p["texto"], font=T.f["chica"],
                           anchor="w")
            etq.pack(side="left", pady=T.px(1))
            Tooltip(etq, completo)
            tk.Label(res, text=str(n), background=p["panel"], foreground=p["texto"] if n else p["deshab"],
                     font=T.f["negrita"], anchor="e", padx=T.px(10)).grid(row=i, column=1, sticky="nsew")

    def _elegir(self, clase, flota, var):
        tipos = dict(self.esc.clases[clase]["tipos"])
        tipos[flota] = var.get()
        self.esc.set_tipos(clase, tipos)
        self.vista.app.reejecutar_si_corresponde(self.vista)

    # --- orden de reporte ----------------------------------------------------------------------------
    def _orden(self, caja, clase, cfg):
        p = T.p
        orden = modelo.orden_normalizado(clase, cfg.get("orden"), list(cfg.get("flotas") or {}))
        cab = tk.Frame(caja, background=p["panel"])
        cab.pack(fill="x", padx=T.px(14), pady=(T.px(10), T.px(6)))
        tk.Label(cab, text="Orden de Reporte", background=p["panel"], foreground=p["texto"],
                 font=T.f["negrita"]).pack(side="left")
        ayuda = tk.Label(cab, text="ⓘ", background=p["panel"], foreground=p["suave"], font=T.f["base"], cursor="hand2")
        ayuda.pack(side="left", padx=(T.px(6), 0))
        Tooltip(ayuda, "Orden en que se leen las tablas fijas, los gráficos y las tablas dinámicas: de arriba hacia "
                       "abajo el orden de cada lista; de izquierda a derecha la prioridad (◀ ▶). Seleccione un valor "
                       "y use ▲ ▼ para moverlo.")
        ttk.Button(cab, text="Restablecer", style="Chico.TButton",
                   command=lambda: self.esc.set_orden(clase, None)).pack(side="right")
        cuerpo = tk.Frame(caja, background=p["panel"])
        cuerpo.pack(fill="both", expand=True, padx=T.px(14), pady=(0, T.px(12)))
        nombres = dict(modelo.dims_orden(clase))
        prio = orden["prioridad"]
        for j, dim in enumerate(prio):
            cuerpo.columnconfigure(j, weight=1, uniform=f"o{clase}")
            col = tk.Frame(cuerpo, background=p["panel"], highlightthickness=1, highlightbackground=p["separador"])
            col.grid(row=0, column=j, sticky="nsew", padx=(0 if j == 0 else T.px(6), 0))
            hdr = tk.Frame(col, background=p["cab"])
            hdr.pack(fill="x")
            izq = tk.Label(hdr, text="◀", background=p["cab"], foreground=p["suave"] if j else p["deshab"],
                           font=T.f["chica"], cursor="hand2" if j else "arrow", padx=T.px(4))
            izq.pack(side="left")
            der = tk.Label(hdr, text="▶", background=p["cab"],
                           foreground=p["suave"] if j < len(prio) - 1 else p["deshab"], font=T.f["chica"],
                           cursor="hand2" if j < len(prio) - 1 else "arrow", padx=T.px(4))
            der.pack(side="right")
            tk.Label(hdr, text=f"{j + 1}. {nombres[dim]}", background=p["cab"], foreground=p["cab_txt"],
                     font=T.f["negrita"], pady=T.px(3)).pack(side="left", expand=True)
            if j:
                izq.bind("<Button-1>", lambda e, d=dim: self._prioridad(clase, orden, d, -1))
            if j < len(prio) - 1:
                der.bind("<Button-1>", lambda e, d=dim: self._prioridad(clase, orden, d, 1))
            lista = tk.Frame(col, background=p["panel"])
            lista.pack(fill="both", expand=True, pady=(T.px(2), 0))
            for k, valor in enumerate(orden[dim]):
                elegido = self._sel_orden == (clase, dim, valor)
                fondo = p["sel"] if elegido else p["panel"]
                lb = tk.Label(lista, text=f"{k + 1}.  {valor}", background=fondo, foreground=p["texto"],
                              font=T.f["chica"], anchor="w", padx=T.px(8), pady=T.px(1), cursor="hand2")
                lb.pack(fill="x")
                lb.bind("<Button-1>", lambda e, d=dim, v=valor: self._elegir_orden(clase, d, v))
            botones = tk.Frame(col, background=p["panel"])
            botones.pack(fill="x", pady=(T.px(2), T.px(4)))
            for txt, paso in (("▲", -1), ("▼", 1)):
                b = ttk.Button(botones, text=txt, width=3, style="Chico.TButton",
                               command=lambda d=dim, s=paso: self._mover(clase, orden, d, s))
                b.pack(side="left", padx=(T.px(6), 0))

    def _elegir_orden(self, clase, dim, valor):
        self._sel_orden = (clase, dim, valor)
        self.refrescar()

    def _mover(self, clase, orden, dim, paso):
        if not self._sel_orden or self._sel_orden[:2] != (clase, dim):
            return
        lista = list(orden[dim])
        v = self._sel_orden[2]
        if v not in lista:
            return
        i = lista.index(v)
        j = max(0, min(len(lista) - 1, i + paso))
        if i == j:
            return
        lista.insert(j, lista.pop(i))
        nuevo = dict(orden)
        nuevo[dim] = lista
        self.esc.set_orden(clase, nuevo)

    def _prioridad(self, clase, orden, dim, paso):
        prio = list(orden["prioridad"])
        i = prio.index(dim)
        j = max(0, min(len(prio) - 1, i + paso))
        prio.insert(j, prio.pop(i))
        nuevo = dict(orden)
        nuevo["prioridad"] = prio
        self.esc.set_orden(clase, nuevo)


# ============================================================================
# Origen y Destino (columnas H e I del registro de cargas)
# ============================================================================
def _ton(t):
    """Material en toneladas, entero (#,###,###)."""
    return f"{(t or 0):,.0f}"


LIMITE_CONFIRMAR = 50          # cambios masivos (más de 50 registros distintos) piden confirmación


def _confirmar_masivo(padre, n, que):
    from dialogos import confirmar
    if n <= LIMITE_CONFIRMAR:
        return True
    return confirmar(padre, "Confirmar Cambio", [f"Se modificarán {n:,} {que}.", "¿Está seguro?"],
                     ("Sí, Aplicar", "Cancelar"), cancelar=1) == 0


class PaginaOrigenDestino(ttk.Frame):
    def __init__(self, master, vista):
        super().__init__(master, style="Panel.TFrame")
        self.vista = vista
        self.esc = vista.esc
        self._sucia = True
        self._fases_filtro = None
        cont = ttk.Frame(self, style="Panel.TFrame", padding=(T.px(20), T.px(12)))
        cont.pack(fill="both", expand=True)
        self.vacio = Aviso(cont, "No hay datos del registro de cargas. Importe e incluya o_registro_cargas.csv "
                                 "(Modelo ▸ Importar Resultados Simulación CSV).")
        self.cuerpo = ttk.Frame(cont, style="Panel.TFrame")
        self.cuerpo.columnconfigure(0, weight=3)
        self.cuerpo.columnconfigure(1, weight=2)
        self.cuerpo.rowconfigure(0, weight=1)
        self._origenes(self.cuerpo).grid(row=0, column=0, sticky="nsew", padx=(0, T.px(8)))
        self._destinos(self.cuerpo).grid(row=0, column=1, sticky="nsew", padx=(T.px(8), 0))

    # ---- Orígenes ----------------------------------------------------------------------
    def _origenes(self, master):
        caja = ttk.LabelFrame(master, text="  Orígenes  ", style="Tarjeta.TLabelframe", padding=(T.px(10), T.px(6)))
        fila = ttk.Frame(caja, style="Panel.TFrame")
        fila.pack(fill="x", pady=(0, T.px(6)))
        self._img_buscar = T.icono("buscar", 14, T.p["suave"])
        ttk.Label(fila, image=self._img_buscar, style="Panel.TLabel").pack(side="left", padx=(0, T.px(4)))
        self.var_buscar = tk.StringVar()
        ent = ttk.Entry(fila, textvariable=self.var_buscar, width=26)
        ent.pack(side="left")
        Tooltip(ent, "Buscar origen (p. ej. «Stk» o «F11»). Seleccione varias filas con Ctrl / Shift o Ctrl+A y "
                     "asigne el Tipo de Origen o la Condición con los botones.")
        self.var_buscar.trace_add("write", lambda *a: self._pintar_origenes())
        self.sel_fase = MultiSeleccion(fila, "Fase", [], self._filtro_fases, plural="Todas", ancho=14)
        self.sel_fase.pack(side="left", padx=(T.px(12), 0))
        ttk.Button(fila, text="Seleccionar Filtrados", style="Chico.TButton",
                   command=lambda: self.tabla_o.seleccionar_todo()).pack(side="left", padx=(T.px(8), 0))
        self.lbl_conteo = ttk.Label(fila, style="PanelSuave.TLabel", font=T.f["chica"])
        self.lbl_conteo.pack(side="right")
        asignar = ttk.Frame(caja, style="Panel.TFrame")
        asignar.pack(fill="x", pady=(0, T.px(6)))
        ttk.Label(asignar, text="Tipo Origen", style="Panel.TLabel").pack(side="left", padx=(0, T.px(6)))
        for t in registro.TIPOS_ORIGEN:
            ttk.Button(asignar, text=t, style="Chico.TButton",
                       command=lambda t=t: self._asignar(tipo=t)).pack(side="left", padx=(0, T.px(3)))
        ttk.Label(asignar, text="Condición", style="Panel.TLabel").pack(side="left", padx=(T.px(16), T.px(6)))
        for c in registro.CONDICIONES:
            ttk.Button(asignar, text=c, style="Chico.TButton",
                       command=lambda c=c: self._asignar(condicion=c)).pack(side="left", padx=(0, T.px(3)))
        self.sel_relleno = MultiSeleccion(asignar, "Fases en Relleno", [], self._fases_relleno, plural="Ninguna", ancho=16)
        self.sel_relleno.pack(side="left", padx=(T.px(16), 0))
        Tooltip(self.sel_relleno.boton, "Marque las fases cuyos polígonos están en condición Relleno; "
                                        "al desmarcar una fase vuelve a Insitu")
        self.tabla_o = TablaDatos(caja, [{"key": "o", "titulo": "Origen", "ancho": 200},
                                         {"key": "f", "titulo": "Fase", "ancho": 80, "ancla": "center"},
                                         {"key": "t", "titulo": "Material (t)", "ancho": 110, "ancla": "e"},
                                         {"key": "tipo", "titulo": "Tipo Origen", "ancho": 100, "ancla": "center"},
                                         {"key": "cond", "titulo": "Condición", "ancho": 95, "ancla": "center"}],
                                  alto=16, grupo="f", clave="inputs.origenes")
        self.tabla_o.pack(fill="both", expand=True)
        self.tabla_o.arbol.bind("<Control-a>", lambda e: (self.tabla_o.seleccionar_todo(), "break")[1])
        self.lbl_resumen_o = ttk.Label(caja, style="PanelSuave.TLabel", font=T.f["chica"])
        self.lbl_resumen_o.pack(anchor="w", pady=(T.px(4), 0))
        return caja

    def _fases(self):
        return sorted({c.get("fase") or registro.fase_de(o) for o, c in self.esc.origenes.items()},
                      key=lambda f: (f == registro.SIN_FASE, f))

    def _filtro_fases(self, valores):
        fases = self._fases()
        self._fases_filtro = None if set(valores) == set(fases) else set(valores)
        self._pintar_origenes()

    def _pintar_origenes(self):
        p = T.p
        sel = self.tabla_o.valores_seleccion(0)
        q = self.var_buscar.get().strip().lower()
        fases = self._fases()
        self.sel_fase.set_opciones(fases)
        if self._fases_filtro is not None:
            self._fases_filtro &= set(fases)
            self.sel_fase.seleccion = [f for f in fases if f in self._fases_filtro] or None
            self.sel_fase._texto()
        self.tabla_o.etiqueta("Rehandle", foreground=p["est_DPP"])
        self.tabla_o.etiqueta("N/A", foreground=p["deshab"])
        self.tabla_o.etiqueta("Relleno", foreground=p["est_DENP"], font=T.f["tabla_n"])
        filas = []
        for o, c in self.esc.origenes.items():
            fase = c.get("fase") or registro.fase_de(o)
            if (q and q not in o.lower()) or (self._fases_filtro is not None and fase not in self._fases_filtro):
                continue
            tags = [c.get("tipo")] + (["Relleno"] if c.get("condicion") == "Relleno" else [])
            filas.append(([o, fase, _ton(c.get("carga")), c.get("tipo"), c.get("condicion")],
                          [o, fase, c.get("carga") or 0, c.get("tipo"), c.get("condicion")], False, tags))
        self.tabla_o.cargar(filas)
        self.tabla_o.seleccionar_valores(sel, 0)
        self.lbl_conteo.configure(text=f"{len(filas):,} de {len(self.esc.origenes):,} orígenes")
        cuenta = {t: sum(1 for c in self.esc.origenes.values() if c.get("tipo") == t) for t in registro.TIPOS_ORIGEN}
        n_rell = sum(1 for c in self.esc.origenes.values() if c.get("condicion") == "Relleno")
        self.lbl_resumen_o.configure(text="   ·   ".join(f"{t}: {n:,}" for t, n in cuenta.items())
                                     + f"   ·   Relleno: {n_rell:,}")
        self.sel_relleno.set_opciones(fases, conservar=False)
        en_rell = self.esc.fases_en_relleno()
        self.sel_relleno.seleccion = None if (fases and len(en_rell) == len(fases)) else list(en_rell)
        self.sel_relleno.plural = "Todas"
        self.sel_relleno._texto()

    def _fases_relleno(self, valores):
        antes = set(self.esc.fases_en_relleno())
        ahora = set(valores or [])
        marcar, desmarcar = ahora - antes, antes - ahora
        if not marcar and not desmarcar:
            return
        afectados = sum(1 for o, c in self.esc.origenes.items()
                        if (c.get("fase") or registro.fase_de(o)) in (marcar | desmarcar))
        if not _confirmar_masivo(self, afectados, "polígonos (condición por fase)"):
            self._pintar_origenes()
            return
        self.esc.set_fases_relleno(marcar, desmarcar)

    def _asignar(self, tipo=None, condicion=None):
        sel = self.tabla_o.valores_seleccion(0)
        if not sel:
            aviso(self, "Sin Selección", "Seleccione uno o más orígenes (use la búsqueda, el filtro de Fase y "
                                         "«Seleccionar Filtrados» para asignar a muchos a la vez).")
            return
        valor = tipo or condicion
        cambian = [o for o in sel if (self.esc.origenes.get(o) or {}).get("tipo" if tipo else "condicion") != valor]
        if not _confirmar_masivo(self, len(cambian), f"orígenes ({'Tipo Origen' if tipo else 'Condición'}: {valor})"):
            return
        self.esc.set_origenes(sel, tipo=tipo, condicion=condicion)

    # ---- Destinos ------------------------------------------------------------------------
    def _destinos(self, master):
        caja = ttk.LabelFrame(master, text="  Destinos  ", style="Tarjeta.TLabelframe", padding=(T.px(10), T.px(6)))
        fila = ttk.Frame(caja, style="Panel.TFrame")
        fila.pack(fill="x", pady=(0, T.px(6)))
        ttk.Button(fila, text="Configurar Tipo de Destino…", style="Accent.TButton",
                   command=self._configurar_destinos).pack(side="left")
        self.tabla_d = TablaDatos(caja, [{"key": "tipo", "titulo": "Tipo Destino", "ancho": 92},
                                         {"key": "d", "titulo": "Destino", "ancho": 120},
                                         {"key": "t", "titulo": "Material (t)", "ancho": 100, "ancla": "e"}],
                                  alto=16, grupo="tipo", clave="inputs.destinos", modo_seleccion="browse")
        self.tabla_d.pack(fill="both", expand=True)
        self.tabla_d.arbol.bind("<Double-Button-1>", lambda e: self._configurar_destinos())
        self.lbl_resumen_d = ttk.Label(caja, style="PanelSuave.TLabel", font=T.f["chica"])
        self.lbl_resumen_d.pack(anchor="w", pady=(T.px(4), 0))
        return caja

    def _pintar_destinos(self):
        filas = [([c.get("tipo"), d, _ton(c.get("carga"))], [c.get("tipo"), d, c.get("carga") or 0], False)
                 for d, c, _k in _destinos_ordenados(self.esc.destinos)]
        self.tabla_d.cargar(filas)
        cuenta = {t: sum(1 for c in self.esc.destinos.values() if c.get("tipo") == t) for t in registro.TIPOS_DESTINO}
        self.lbl_resumen_d.configure(text="   ·   ".join(f"{t}: {n:,}" for t, n in cuenta.items()))

    def _configurar_destinos(self):
        if not self.esc.destinos:
            return
        DialogoDestinos(self, self.esc.destinos, lambda r: self.esc.set_destinos(r), pagina=self).mostrar()

    def refrescar(self):
        if not self.esc.origenes and not self.esc.destinos:
            self.cuerpo.pack_forget()
            self.vacio.pack(fill="x")
            return
        self.vacio.pack_forget()
        self.cuerpo.pack(fill="both", expand=True)
        self._pintar_origenes()
        self._pintar_destinos()


def _destinos_ordenados(destinos):
    """[(destino, cfg, índice dentro de su tipo)] en el orden Chancador, Stockpile, Botadero y alfabético."""
    pos = {t: i for i, t in enumerate(registro.TIPOS_DESTINO)}
    orden = sorted(destinos.items(), key=lambda x: (pos.get(x[1].get("tipo"), 9), x[0].lower()))
    salida, previo, k = [], None, 0
    for d, c in orden:
        if c.get("tipo") != previo:
            previo, k = c.get("tipo"), 0
        salida.append((d, c, k))
        k += 1
    return salida


class DialogoDestinos(VentanaHerramienta):
    """Valores únicos de Destino con botones Chancador / Stockpile / Botadero (no modal)."""

    def __init__(self, padre, destinos, al_aceptar=None, pagina=None):
        super().__init__(padre, "Tipo de Destino", al_aceptar, True, pagina)
        p = T.p
        self.destinos = destinos
        marco = ttk.Frame(self, style="Panel.TFrame", padding=(T.px(18), T.px(14)))
        marco.pack(fill="both", expand=True)
        ttk.Label(marco, text="Tipo de Destino", style="Titulo.TLabel").pack(anchor="w")
        ttk.Label(marco, style="PanelSuave.TLabel", text="Por defecto se asigna según la columna «Tipo Destino» del "
                                                          "registro de cargas (o Botadero si no la tiene).").pack(
            anchor="w", pady=(T.px(2), T.px(10)))
        botones = ttk.Frame(marco, style="Panel.TFrame")
        botones.pack(side="bottom", fill="x", pady=(T.px(10), 0))
        ttk.Button(botones, text="Restablecer según Registro", command=self._restablecer).pack(side="left")
        ttk.Button(botones, text="Aplicar", style="Accent.TButton", command=self.aceptar).pack(side="right")
        ttk.Button(botones, text="Cancelar", command=self.cancelar).pack(side="right", padx=(0, T.px(8)))
        caja = tk.Frame(marco, background=p["borde"], padx=1, pady=1)
        caja.pack(fill="both", expand=True)
        zona = ScrollFrame(caja, margen_inferior=False)
        zona.pack(fill="both", expand=True)
        g = zona.interior
        g.columnconfigure(0, weight=1)
        for j, t in enumerate(("Destino", "Material (t)", "Tipo Destino")):
            tk.Label(g, text=t, background=p["cab"], foreground=p["cab_txt"], font=T.f["tabla_n"],
                     anchor="center", padx=T.px(10), pady=T.px(5)).grid(row=0, column=j, sticky="nsew")
        self.vars = {}
        for i, (d, c, _k) in enumerate(_destinos_ordenados(destinos), start=1):
            gi = registro.TIPOS_DESTINO.index(c.get("tipo")) if c.get("tipo") in registro.TIPOS_DESTINO else 5
            fondo = colores_grupo(gi)[0]
            tk.Label(g, text=d, background=fondo, foreground=p["texto"], font=T.f["tabla"], anchor="w",
                     padx=T.px(14), pady=T.px(3)).grid(row=i, column=0, sticky="nsew")
            tk.Label(g, text=_ton(c.get("carga")), background=fondo, foreground=p["texto"], font=T.f["tabla"],
                     anchor="e", padx=T.px(12)).grid(row=i, column=1, sticky="nsew")
            var = tk.StringVar(value=c.get("tipo"))
            self.vars[d] = var
            seg = tk.Frame(g, background=fondo)
            seg.grid(row=i, column=2, sticky="nsew", padx=(T.px(6), T.px(8)))
            for t in registro.TIPOS_DESTINO:
                ttk.Radiobutton(seg, text=t, value=t, variable=var, style="Segmento.Toolbutton").pack(
                    side="left", padx=(0, 1), pady=T.px(2))
        g.update_idletasks()
        zona.lienzo.configure(width=T.px(620), height=min(g.winfo_reqheight(), T.px(480)))

    def _restablecer(self):
        for d, var in self.vars.items():
            var.set(self.destinos[d].get("tipo_csv") or "Botadero")

    def resultado_actual(self):
        return {d: v.get() for d, v in self.vars.items()}


# ============================================================================
# Vector Plan (edición directa en la tabla)
# ============================================================================
class DialogoNombrePlan(VentanaModal):
    """Validación del nombre del plan después de importar."""

    def __init__(self, padre, nombre):
        super().__init__(padre, "Confirmar Plan")
        marco = ttk.Frame(self, style="Panel.TFrame", padding=(T.px(20), T.px(16)))
        marco.pack(fill="both", expand=True)
        ttk.Label(marco, text=f"¿El «{nombre}» es correcto?", style="Subtitulo.TLabel").pack(anchor="w")
        ttk.Label(marco, style="PanelSuave.TLabel", text="Puede corregir el nombre antes de confirmar.").pack(
            anchor="w", pady=(T.px(2), T.px(8)))
        self.var = tk.StringVar(value=nombre)
        e = ttk.Entry(marco, textvariable=self.var, width=44)
        e.pack(anchor="w")
        e.focus_set()
        botones = ttk.Frame(marco, style="Panel.TFrame")
        botones.pack(fill="x", pady=(T.px(14), 0))
        ttk.Button(botones, text="Sí, Confirmar", style="Accent.TButton", command=self._ok).pack(side="right")
        ttk.Button(botones, text="Cancelar", command=self.cancelar).pack(side="right", padx=(0, T.px(8)))
        self.bind("<Return>", lambda e: self._ok())

    def _ok(self):
        if self.var.get().strip():
            self.resultado = self.var.get().strip()
            self.destroy()


class EditorIndicador(Emergente):
    """Indicador Simulador (B) de un parámetro: búsqueda, selección múltiple dentro de una misma familia
    (las opciones incompatibles se inhabilitan) y «Sin Vínculo»."""

    def __init__(self, ancla, x, y, esc, fila, al_aceptar):
        super().__init__(ancla, f"Indicador Simulador (B) – {fila['texto'].strip()[:48]}")
        self.al_aceptar = al_aceptar
        cat = plan.catalogo(esc)
        self.claves = [k for k, _e in cat]
        etiquetas = dict(cat)
        actual = [c for c in plan.claves_de(fila.get("vinculo")) if c in self.claves]
        self._marcados0 = set(actual)
        p = T.p
        self._nota = tk.Label(self.cuerpo, background=p["panel"], foreground=p["suave"], font=T.f["chica"],
                              anchor="w", justify="left", wraplength=T.px(470))
        self._nota.pack(fill="x", padx=T.px(10), pady=(T.px(6), 0))
        self.lista = ListaChequeo(self.cuerpo, self.claves, actual, habilitado=self._habilitado, alto=14, ancho=480,
                                  etiquetas=etiquetas, al_cambiar=self._cambio, con_todo=False)
        self.lista.marcados = set(actual)
        self.lista._pintar()
        self.lista.pack(fill="both", expand=True)
        pie = tk.Frame(self.cuerpo, background=p["panel"])
        pie.pack(fill="x", padx=T.px(8), pady=T.px(8))
        ttk.Button(pie, text="Sin Vínculo", style="Chico.TButton", command=self._sin_vinculo).pack(side="left")
        ttk.Button(pie, text="Aceptar", style="Accent.TButton", command=lambda: self.cerrar(True)).pack(side="right")
        ttk.Button(pie, text="Cancelar", style="Chico.TButton", command=lambda: self.cerrar(False)).pack(
            side="right", padx=(0, T.px(6)))
        self._inicial = list(actual)
        self._cambio()
        self.mostrar(x, y)
        if self.lista.entrada is not None:
            self.lista.entrada.focus_set()

    def _familia(self):
        marcados = self.lista.marcados if hasattr(self, "lista") else self._marcados0
        sel = [k for k in self.claves if k in marcados]
        return plan.familia(sel[0]) if sel else None

    def _habilitado(self, clave):
        fam = self._familia()
        return fam is None or plan.familia(clave) == fam

    def _cambio(self):
        fam = self._familia()
        n = len(self.lista.marcados)
        if n > 1:
            modo = plan.COMBINACION.get(fam.split("|")[0], "Suma") if fam else ""
            self._nota.configure(text=f"{n} indicadores combinados ({modo}). Solo se pueden combinar indicadores del "
                                      "mismo tipo: las demás opciones quedan inhabilitadas.")
        elif n == 1:
            self._nota.configure(text="Puede marcar más indicadores del mismo tipo para combinarlos (suma o promedio "
                                      "ponderado según el indicador).")
        else:
            self._nota.configure(text="Sin vínculo: el parámetro se mostrará con «-».")
        self.lista._pintar()

    def _sin_vinculo(self):
        self.lista.marcados = set()
        self.cerrar(True)

    def aplicar(self):
        sel = [k for k in self.claves if k in self.lista.marcados]
        if sorted(sel) == sorted(self._inicial):
            return
        self.al_aceptar(sel[0] if len(sel) == 1 else (sel or plan.SIN_VINCULO))


class EditorVariacion(Emergente):
    def __init__(self, ancla, x, y, fila, al_aceptar):
        super().__init__(ancla, "Variación")
        self.al_aceptar = al_aceptar
        self.actual = fila.get("variacion") or plan.variacion_por_defecto(fila.get("unidad"))
        claves = list(plan.VARIACIONES)
        self.lista = ListaChequeo(self.cuerpo, claves, [self.actual], unica=True, alto=4, ancho=260,
                                  etiquetas={k: f"{c}   —   {l}" for k, (c, l) in plan.VARIACIONES.items()},
                                  al_cambiar=lambda: self.cerrar(True))
        self.lista.pack(fill="both", expand=True, pady=(0, T.px(8)))
        self.mostrar(x, y)

    def aplicar(self):
        sel = list(self.lista.marcados)
        if sel and sel[0] != self.actual:
            self.al_aceptar(sel[0])


class PaginaVectorPlan(ttk.Frame):
    """Tabla del plan con edición directa: clic en «Indicador Simulador (B)» o en «Variación» para cambiarlos.
    Toda la tabla se muestra (sin recorte) y los avisos de cada parámetro van al pie."""

    COLS = [{"titulo": "Parámetro", "ancho": 240}, {"titulo": "Unidad", "ancho": 70, "ancla": "center"},
            {"titulo": "Vector Plan (A)", "ancho": 100, "ancla": "e"},
            {"titulo": "Indicador Simulador (B)", "ancho": 420, "ancla": "w"},
            {"titulo": "Variación", "ancho": 90, "ancla": "center"}]

    def __init__(self, master, vista):
        super().__init__(master, style="Panel.TFrame")
        self.vista = vista
        self.esc = vista.esc
        self._sucia = True
        self.zona = ScrollFrame(self)
        self.zona.pack(fill="both", expand=True)

    def refrescar(self):
        nuevo = self.zona.preparar()
        cont = ttk.Frame(nuevo, style="Panel.TFrame", padding=(T.px(20), T.px(12)))
        cont.pack(fill="both", expand=True)
        barra = ttk.Frame(cont, style="Panel.TFrame")
        barra.pack(fill="x", pady=(0, T.px(8)))
        ttk.Button(barra, text="Importar Métricas Plan…", style="Accent.TButton",
                   command=lambda: self.vista.app.importar_plan(self.vista)).pack(side="left")
        pl = self.esc.plan
        b = ttk.Button(barra, text="Restablecer Vínculos Sugeridos", command=self._sugeridos)
        b.pack(side="left", padx=(T.px(8), 0))
        lbl = ttk.Label(barra, style="PanelSuave.TLabel")
        lbl.pack(side="left", padx=(T.px(14), 0))
        if not pl:
            b.state(["disabled"])
            lbl.configure(text="Opcional. Sin plan importado: el archivo puede tener cualquier nombre (formato «Vector Plan»).")
            self.zona.publicar(nuevo)
            return
        revisar = plan.revisar_vinculos(self.esc, pl["filas"])
        sin = sum(1 for f in pl["filas"] if f["tipo"] == "item" and not f.get("vinculo"))
        partes = [pl.get("nombre"), pl.get("archivo")] + ([f"importado el {pl['fecha']}"] if pl.get("fecha") else [])
        lbl.configure(text="  ·  ".join(p for p in partes if p))
        cat = plan.catalogo(self.esc)
        filas, actual, n = [], None, 0
        for i, f in enumerate(pl["filas"]):
            if f["tipo"] == "seccion":
                actual = {"texto": f["texto"], "valores": ["", "", "", ""], "hijos": [], "tag": "seccion",
                          "abierto": True, "_i": i}
                filas.append(actual)
                n += 1
                continue
            item = {"texto": f["texto"].strip(), "_i": i,
                    "valores": [f["unidad"], plan.texto_valor(f, f["valor"]), plan.etiqueta(self.esc, f.get("vinculo"), cat),
                                plan.VARIACIONES[f.get("variacion") or "resta"][0]],
                    "tag": "marca" if i in revisar else None}
            (actual["hijos"] if actual else filas).append(item)
            n += 1
        self.tabla = TablaArbol(cont, self.COLS, alto=n + 1, abiertos=True, colores=False, clave="vector_plan")
        self.tabla.pack(fill="x")
        self.tabla.cargar(filas)
        self.tabla.arbol.bind("<ButtonRelease-1>", self._clic_celda, add="+")
        self.tabla.arbol.configure(cursor="hand2")
        Tooltip(self.tabla.arbol, "Clic en «Indicador Simulador (B)» o en «Variación» para editarlos")
        if revisar or sin:
            pie = tk.Frame(cont, background=T.p["panel"])
            pie.pack(fill="x", pady=(T.px(10), 0))
            tk.Label(pie, text="Observaciones", background=T.p["panel"], foreground=T.p["texto"],
                     font=T.f["negrita"], anchor="w").pack(fill="x")
            for i, motivo in sorted(revisar.items()):
                f = pl["filas"][i]
                tk.Label(pie, text=f"⚠  El ítem {f['texto'].strip()}: {motivo}.", background=T.p["panel"],
                         foreground=T.p["marca_fila"], font=T.f["base"], anchor="w", justify="left").pack(fill="x")
            if sin:
                tk.Label(pie, text=f"ⓘ  {sin} parámetro(s) sin indicador del simulador: se mostrarán con «-».",
                         background=T.p["panel"], foreground=T.p["suave"], font=T.f["base"], anchor="w").pack(fill="x")
        self.zona.publicar(nuevo)

    def _clic_celda(self, e):
        f, j, iid = self.tabla.celda_en(e)
        if f is None or f.get("tag") == "seccion" or "_i" not in f or j not in (3, 4):
            return
        fila = self.esc.plan["filas"][f["_i"]]
        bb = self.tabla.arbol.bbox(iid, self.tabla._claves[j])
        x = self.tabla.arbol.winfo_rootx() + (bb[0] if bb else e.x)
        y = self.tabla.arbol.winfo_rooty() + (bb[1] + bb[3] if bb else e.y + 20)
        if j == 3:
            EditorIndicador(self.tabla.arbol, x, y, self.esc, fila, lambda v, i=f["_i"]: self._cambiar(i, vinculo=v))
        else:
            EditorVariacion(self.tabla.arbol, x, y, fila, lambda v, i=f["_i"]: self._cambiar(i, variacion=v))
        return "break"

    def _cambiar(self, i, vinculo=None, variacion=None):
        filas = [dict(f) for f in self.esc.plan["filas"]]
        if vinculo is not None:
            filas[i]["vinculo"] = vinculo
            filas[i].pop("revisar", None)
        if variacion is not None:
            filas[i]["variacion"] = variacion
        self.esc.set_plan(dict(self.esc.plan, filas=filas))

    def _sugeridos(self):
        import copy
        filas = copy.deepcopy(self.esc.plan["filas"])
        for f in filas:
            f.pop("vinculo", None)
            f.pop("revisar", None)
        plan.vincular(self.esc, filas)
        self.esc.set_plan(dict(self.esc.plan, filas=filas))
        self.vista.app.mensaje("Vínculos restablecidos a los sugeridos por SimA")


# ============================================================================
# Contenedor de la pestaña Inputs
# ============================================================================
class PaginaInputs(ttk.Frame):
    REQUERIDAS = ("general", "equipos", "od")

    def __init__(self, master, vista):
        super().__init__(master, style="Panel.TFrame")
        self.vista = vista
        self.sub = Pestanas(self)
        self.sub.pack(fill="both", expand=True, padx=T.px(8), pady=(T.px(2), T.px(8)))
        self.general = PaginaGeneral(self.sub, vista)
        self.estados = PaginaEstadosInputs(self.sub, vista)
        self.od = PaginaOrigenDestino(self.sub, vista)
        self.vplan = PaginaVectorPlan(self.sub, vista)
        self.sub.add(self.general, text="General")
        self.sub.add(self.estados, text="Configuración de Equipos")
        self.sub.add(self.od, text="Origen y Destino")
        self.sub.add(self.vplan, text="Vector Plan")
        for pag in (self.general, self.estados, self.od):          # secciones requeridas
            self.sub.tab(pag, marca=True)
        self.leyenda = tk.Label(self.sub.derecha, text="* Requerido", font=T.f["negrita"])
        self.leyenda.pack(side="right", padx=T.px(10))
        T.registrar(self._pintar_leyenda)
        self._pintar_leyenda()
        self._sucia = False

    def _pintar_leyenda(self):
        self.leyenda.configure(background=T.p["panel"], foreground=T.p["requerido"])

    def _pagina(self, clave):
        return {"general": self.general, "equipos": self.estados, "od": self.od}.get(clave)

    def ir_a_pendiente(self):
        pend = self.vista.esc.pendientes()
        for k in self.REQUERIDAS:
            if k in pend:
                self.sub.select(self._pagina(k))
                return

    def refrescar(self):
        esc = self.vista.esc
        hay = any(esc.clase_habilitada(c) and c in esc.clases for c in modelo.ORDEN_CLASES)
        self.sub.tab(self.estados, state="normal" if hay else "disabled")
        if not hay and self.sub.select() is self.estados:
            self.sub.select(self.general)
        actual = self.sub.select()
        self.sub.marcar_sucias(excepto=actual)
        if actual is not None:
            actual._sucia = False
            actual.refrescar()
