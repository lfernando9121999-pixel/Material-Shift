"""Tabla dinámica con gráfico: grilla agrupada (filas y columnas desplegables con subtotales) y gráfico a la
izquierda; campos y áreas (Filtros, Columnas, Filas, Valores) a la derecha.

Barra superior: Agregar Campo Calculado, Editar Expresiones, Formato de Campos, Actualizar, Campos Visibles,
Opciones de Pivote, Expandir y Contraer. Se usa en Tablas Dinámicas ▸ Análisis de Estados (Pivot) y
Registro de Cargas (Pivot). Las medidas ponderadas y los promedios se calculan como cociente de sumas.
"""
import copy
import math
import tkinter as tk
from tkinter import ttk

import expresiones as ex
import pivot
from dialogos import aviso, confirmar, error
from graficos import GraficoBarras
from grilla import GrillaPivot, formateador
from tema import T, Tooltip
from ui_comun import (Aviso, Emergente, ListaChequeo, Placeholder, ScrollFrame, TablaDatos, VentanaHerramienta,
                      mostrar_menu, nuevo_menu)
from ui_github import MultiSeleccion, Segmentado

NOMBRES_AREA = {"filtros": "Filtros", "columnas": "Columnas", "filas": "Filas", "valores": "Valores"}
LIMITE_CELDAS_GUARDADAS = 6000
MAX_CATEGORIAS_GRAFICO = 40
LIMITE_DISTINTOS = 50
CAMPOS_FECHA = ("Fecha", "Mes", "Semana", "Hora del Año (h)")
GRUPOS_CAMPOS = [("dim", "Dimensiones", "Abc"), ("fecha", "Fechas y Periodos", "◷"),
                 ("num", "Valores Numéricos", "Σ"), ("medida", "Medidas Calculadas", "ƒx"),
                 ("calc", "Campos Calculados", "ƒx")]
OPCIONES_MENU = [("encabezados_columnas", "Mostrar Encabezados de Columnas"),
                 ("encabezados_filas", "Mostrar Encabezados de Filas"),
                 ("totales_generales_columnas", "Mostrar Totales Generales de Columnas"),
                 ("totales_generales_filas", "Mostrar Totales Generales de Filas"),
                 ("subtotales_columnas", "Mostrar Subtotales de Columnas"),
                 ("subtotales_filas", "Mostrar Subtotales de Filas"),
                 ("lineas_horizontales", "Mostrar Líneas Horizontales"),
                 ("lineas_verticales", "Mostrar Líneas Verticales"),
                 ("encabezados_filtro", "Mostrar Barra de Filtros Activos"),
                 ("auto", "Actualización Automática")]


def tipo_campo(df, campo, medidas, calculados=()):
    if campo in calculados:
        return "calc"
    if campo == pivot.RECUENTO or campo in (medidas or {}):
        return "medida"
    if campo in CAMPOS_FECHA:
        return "fecha"
    return "num" if pivot.campo_numerico(df, campo) else "dim"


# ----------------------------------------------------------------------------
# Ventanas auxiliares
# ----------------------------------------------------------------------------
class FiltroCampo(Emergente):
    """Filtro de un campo (estilo Excel): valores con casillas (en cascada con los demás filtros) o rango."""

    def __init__(self, ancla, campo, info, filtro, al_aplicar):
        super().__init__(ancla, f"Filtro – {campo}")
        self.info, self.al_aplicar = info, al_aplicar
        c = self.cuerpo
        if info["numerico"]:
            tk.Label(c, text=f"Rango de los datos: {info['min']:,.6g} a {info['max']:,.6g}", background=T.p["panel"],
                     foreground=T.p["suave"], font=T.f["chica"]).pack(anchor="w", padx=T.px(10), pady=(T.px(8), T.px(6)))
            fila = tk.Frame(c, background=T.p["panel"])
            fila.pack(anchor="w", padx=T.px(10))
            self.v_min = tk.StringVar(value="" if filtro.get("min") is None else f"{filtro['min']:g}")
            self.v_max = tk.StringVar(value="" if filtro.get("max") is None else f"{filtro['max']:g}")
            ttk.Label(fila, text="Desde", style="Panel.TLabel").grid(row=0, column=0, padx=(0, 6))
            ttk.Entry(fila, textvariable=self.v_min, width=14).grid(row=0, column=1)
            ttk.Label(fila, text="Hasta", style="Panel.TLabel").grid(row=0, column=2, padx=(12, 6))
            ttk.Entry(fila, textvariable=self.v_max, width=14).grid(row=0, column=3)
            self.lista = None
        else:
            prev = filtro.get("incluir")
            self.lista = ListaChequeo(c, info["valores"], None if prev is None else [str(v) for v in prev], alto=12)
            self.lista.pack(fill="both", expand=True, pady=(T.px(4), 0))
        pie = tk.Frame(c, background=T.p["panel"])
        pie.pack(fill="x", padx=T.px(8), pady=T.px(8))
        ttk.Button(pie, text="Quitar Filtro", style="Chico.TButton", command=self._quitar).pack(side="left")
        ttk.Button(pie, text="Aceptar", style="Accent.TButton", command=lambda: self.cerrar(True)).pack(side="right")
        ttk.Button(pie, text="Cancelar", style="Chico.TButton", command=lambda: self.cerrar(False)).pack(
            side="right", padx=(0, T.px(6)))
        self.mostrar()

    @staticmethod
    def _num(texto):
        texto = texto.strip().replace(",", ".")
        return float(texto) if texto else None

    def aplicar(self):
        if self.info["numerico"]:
            try:
                self.al_aplicar({"min": self._num(self.v_min.get()), "max": self._num(self.v_max.get()), "incluir": None})
            except ValueError:
                pass
        else:
            sel = self.lista.seleccion()
            if sel == []:
                return
            self.al_aplicar({"incluir": sel, "min": None, "max": None})

    def _quitar(self):
        self.cerrar(False)
        self.al_aplicar({"incluir": None, "min": None, "max": None})


class DialogoIntervalo(VentanaHerramienta):
    def __init__(self, padre, campo, valor, al_aceptar, pagina=None):
        super().__init__(padre, "Agrupar por Intervalo", al_aceptar, False, pagina)
        marco = ttk.Frame(self, style="Panel.TFrame", padding=(T.px(20), T.px(16)))
        marco.pack()
        ttk.Label(marco, text=f"Ancho del intervalo para «{campo}» (por ejemplo 1, 7 o 0.5):", style="Panel.TLabel",
                  wraplength=T.px(340)).pack(anchor="w")
        self.v = tk.StringVar(value="" if valor is None else f"{valor:g}")
        e = ttk.Entry(marco, textvariable=self.v, width=18)
        e.pack(anchor="w", pady=(T.px(8), T.px(14)))
        e.focus_set()
        fila = ttk.Frame(marco, style="Panel.TFrame")
        fila.pack(fill="x")
        ttk.Button(fila, text="Aceptar", style="Accent.TButton", command=self.aceptar).pack(side="right")
        ttk.Button(fila, text="Cancelar", command=self.cancelar).pack(side="right", padx=(0, 8))
        self.bind("<Return>", lambda e: self.aceptar())

    def resultado_actual(self):
        try:
            v = float(self.v.get().strip().replace(",", ".") or 0)
            return v if v >= 0 and not math.isnan(v) else None
        except ValueError:
            return None


class DialogoExpresion(VentanaHerramienta):
    """Agregar o editar un campo calculado con el editor de expresiones (campos, funciones, operadores y
    constantes con búsqueda y descripción)."""

    def __init__(self, padre, pagina, campos, existente=None, al_aceptar=None):
        super().__init__(padre, "Campo Calculado", al_aceptar, True, pagina)
        p = T.p
        self.campos = list(campos)
        self.original = (existente or {}).get("nombre")
        marco = ttk.Frame(self, style="Panel.TFrame", padding=(T.px(18), T.px(14)))
        marco.pack(fill="both", expand=True)
        ttk.Label(marco, text="Editor de Expresiones", style="Titulo.TLabel").pack(anchor="w")
        fila = ttk.Frame(marco, style="Panel.TFrame")
        fila.pack(fill="x", pady=(T.px(8), T.px(6)))
        ttk.Label(fila, text="Nombre", style="Negrita.TLabel", width=10).pack(side="left")
        self.v_nombre = tk.StringVar(value=(existente or {}).get("nombre", ""))
        ttk.Entry(fila, textvariable=self.v_nombre, width=40).pack(side="left")
        ttk.Label(marco, text="Expresión (como una fórmula de Excel: campos entre corchetes, p. ej. [Carga (t)] / 1000)",
                  style="PanelSuave.TLabel").pack(anchor="w")
        self.txt = tk.Text(marco, height=4, wrap="word", font=T.f["mono"], relief="flat", highlightthickness=1,
                           background=p["campo"], foreground=p["texto"], insertbackground=p["texto"],
                           highlightbackground=p["borde"], highlightcolor=p["acento"], padx=T.px(6), pady=T.px(4))
        self.txt.pack(fill="x", pady=(T.px(2), T.px(4)))
        self.txt.insert("1.0", (existente or {}).get("expresion", ""))
        self.lbl = tk.Label(marco, background=p["panel"], font=T.f["chica"], anchor="w", justify="left",
                            wraplength=T.px(760))
        self.lbl.pack(fill="x")
        self.txt.bind("<KeyRelease>", lambda e: self._validar())
        # explorador: categorías | elementos (con búsqueda) | descripción
        expl = ttk.Frame(marco, style="Panel.TFrame")
        expl.pack(fill="both", expand=True, pady=(T.px(8), 0))
        self.cat = tk.Listbox(expl, height=6, exportselection=False, activestyle="none", relief="flat",
                              highlightthickness=1, highlightbackground=p["borde"], background=p["panel"],
                              foreground=p["texto"], selectbackground=p["sel"], selectforeground=p["texto"],
                              font=T.f["base"], width=14)
        for c in ("Campos", "Funciones", "Operadores", "Constantes"):
            self.cat.insert("end", c)
        self.cat.pack(side="left", fill="y")
        self.cat.selection_set(0)
        self.cat.bind("<<ListboxSelect>>", lambda e: self._llenar())
        medio = ttk.Frame(expl, style="Panel.TFrame")
        medio.pack(side="left", fill="both", expand=True, padx=T.px(8))
        self.v_q = tk.StringVar()
        ttk.Entry(medio, textvariable=self.v_q).pack(fill="x")
        self.v_q.trace_add("write", lambda *a: self._llenar())
        self.items = tk.Listbox(medio, height=8, exportselection=False, activestyle="none", relief="flat",
                                highlightthickness=1, highlightbackground=p["borde"], background=p["panel"],
                                foreground=p["texto"], selectbackground=p["sel"], selectforeground=p["texto"],
                                font=T.f["base"])
        self.items.pack(fill="both", expand=True, pady=(T.px(4), 0))
        self.items.bind("<<ListboxSelect>>", lambda e: self._describir())
        self.items.bind("<Double-Button-1>", lambda e: self._insertar())
        self.desc = tk.Label(expl, background=p["panel_alt"], foreground=p["texto"], font=T.f["base"], anchor="nw",
                             justify="left", wraplength=T.px(260), width=36, padx=T.px(8), pady=T.px(6))
        self.desc.pack(side="left", fill="y")
        botones = ttk.Frame(marco, style="Panel.TFrame")
        botones.pack(fill="x", pady=(T.px(12), 0))
        ttk.Label(botones, text="Doble clic en un elemento para insertarlo.", style="PanelSuave.TLabel").pack(side="left")
        ttk.Button(botones, text="Aceptar", style="Accent.TButton", command=self.aceptar).pack(side="right")
        ttk.Button(botones, text="Cancelar", command=self.cancelar).pack(side="right", padx=(0, T.px(8)))
        self._llenar()
        self._validar()

    def _elementos(self):
        c = self.cat.get(self.cat.curselection()[0]) if self.cat.curselection() else "Campos"
        if c == "Campos":
            return [(f"[{x}]", f"Campo: {x}") for x in self.campos]
        if c == "Funciones":
            return [(f"{k}()", d) for k, (_a, d) in ex.FUNCIONES.items()]
        if c == "Operadores":
            return [(o, d) for o, d in ex.OPERADORES]
        return list(ex.CONSTANTES)

    def _llenar(self):
        q = self.v_q.get().strip().lower()
        self._lista = [(t, d) for t, d in self._elementos() if not q or q in t.lower() or q in d.lower()]
        self.items.delete(0, "end")
        for t, _d in self._lista:
            self.items.insert("end", t)
        self.desc.configure(text="")

    def _describir(self):
        sel = self.items.curselection()
        if sel:
            self.desc.configure(text=self._lista[sel[0]][1])

    def _insertar(self):
        sel = self.items.curselection()
        if not sel:
            return
        t = self._lista[sel[0]][0]
        if t.endswith("()"):
            self.txt.insert("insert", t[:-1])
            self.txt.insert("insert", ")")
            self.txt.mark_set("insert", "insert-1c")
        else:
            self.txt.insert("insert", t)
        self.txt.focus_set()
        self._validar()

    def _validar(self):
        texto = self.txt.get("1.0", "end-1c").strip()
        if not texto:
            self.lbl.configure(text="Escriba una expresión.", foreground=T.p["suave"])
            return None
        try:
            _n, resumen = ex.validar(texto, set(self.campos))
        except ex.ErrorExpresion as e:
            self.lbl.configure(text=f"✕  {e}", foreground=T.p["error"])
            return None
        self.lbl.configure(text="✓  Expresión válida · " + ("Medida de resumen (se calcula en cada celda; úsela en "
                                                             "Valores)" if resumen else "Campo por fila (úselo en Filas, "
                                                                                       "Columnas, Filtros o Valores)"),
                           foreground=T.p["ok"])
        return texto

    def resultado_actual(self):
        nombre = self.v_nombre.get().strip()
        texto = self._validar()
        if not nombre or texto is None:
            return None
        return {"nombre": nombre, "expresion": texto, "original": self.original}

    def aceptar(self):
        if not self.v_nombre.get().strip():
            aviso(self, "Campo Calculado", "Escriba un nombre para el campo.")
            return
        if self._validar() is None:
            aviso(self, "Campo Calculado", "Corrija la expresión antes de aceptar.")
            return
        super().aceptar()


class DialogoFormatos(VentanaHerramienta):
    """Formato de Campos: título, formato numérico, resumen por defecto y ponderación de cada campo."""

    RESUMENES = [("sum", "Suma"), ("mean", "Promedio"), ("wmean", "Promedio Ponderado"), ("min", "Mínimo"),
                 ("max", "Máximo"), ("count", "Cuenta"), ("nunique", "Cuenta Distinta"), ("median", "Mediana")]

    def __init__(self, padre, pagina, campos, cfg, al_aceptar):
        super().__init__(padre, "Formato de Campos", al_aceptar, True, pagina)
        p = T.p
        self.campos = campos            # [(nombre, tipo)]
        marco = ttk.Frame(self, style="Panel.TFrame", padding=(T.px(18), T.px(14)))
        marco.pack(fill="both", expand=True)
        ttk.Label(marco, text="Formato de Campos", style="Titulo.TLabel").pack(anchor="w")
        ttk.Label(marco, style="PanelSuave.TLabel", text="Título que se muestra, formato de los números, resumen al "
                                                          "agregarlo a Valores y campo de ponderación.").pack(
            anchor="w", pady=(T.px(2), T.px(8)))
        botones = ttk.Frame(marco, style="Panel.TFrame")
        botones.pack(side="bottom", fill="x", pady=(T.px(10), 0))
        ttk.Button(botones, text="Aplicar", style="Accent.TButton", command=self.aceptar).pack(side="right")
        ttk.Button(botones, text="Cancelar", command=self.cancelar).pack(side="right", padx=(0, T.px(8)))
        caja = tk.Frame(marco, background=p["borde"], padx=1, pady=1)
        caja.pack(fill="both", expand=True)
        zona = ScrollFrame(caja, margen_inferior=False)
        zona.pack(fill="both", expand=True)
        g = zona.interior
        for j, t in enumerate(("Campo", "Tipo", "Título", "Formato", "Resumen", "Ponderado por")):
            tk.Label(g, text=t, background=p["cab"], foreground=p["cab_txt"], font=T.f["tabla_n"], padx=T.px(8),
                     pady=T.px(5)).grid(row=0, column=j, sticky="nsew")
        numericos = [n for n, t in campos if t in ("num", "calc")]
        nombres_fmt = list(pivot.FORMATOS.values())
        self._fmt_inv = {v: k for k, v in pivot.FORMATOS.items()}
        nombres_res = [n for _k, n in self.RESUMENES]
        self._res_inv = {n: k for k, n in self.RESUMENES}
        self.filas = {}
        tipos = {"dim": "Texto", "fecha": "Fecha / Periodo", "num": "Número", "medida": "Medida", "calc": "Calculado"}
        for i, (nombre, tipo) in enumerate(campos, start=1):
            fondo = p["fila_alt"] if i % 2 == 0 else p["panel"]
            tk.Label(g, text=nombre, background=fondo, foreground=p["texto"], font=T.f["tabla"], anchor="w",
                     padx=T.px(8)).grid(row=i, column=0, sticky="nsew")
            tk.Label(g, text=tipos.get(tipo, tipo), background=fondo, foreground=p["suave"], font=T.f["tabla"],
                     padx=T.px(8)).grid(row=i, column=1, sticky="nsew")
            v_t = tk.StringVar(value=(cfg.get("titulos") or {}).get(nombre, ""))
            ttk.Entry(g, textvariable=v_t, width=24).grid(row=i, column=2, sticky="ew", padx=T.px(4), pady=1)
            v_f = tk.StringVar(value=pivot.FORMATOS.get((cfg.get("formatos_campo") or {}).get(nombre, "General"), "Automático"))
            cb_f = ttk.Combobox(g, textvariable=v_f, values=nombres_fmt, state="readonly", width=22)
            cb_f.grid(row=i, column=3, padx=T.px(4), pady=1)
            v_r = tk.StringVar(value=dict(self.RESUMENES).get((cfg.get("resumen_campo") or {}).get(nombre, "sum"), "Suma"))
            v_p = tk.StringVar(value=(cfg.get("peso_campo") or {}).get(nombre, "<Ninguno>"))
            if tipo == "num" or tipo == "calc":
                ttk.Combobox(g, textvariable=v_r, values=nombres_res, state="readonly", width=18).grid(
                    row=i, column=4, padx=T.px(4), pady=1)
                ttk.Combobox(g, textvariable=v_p, values=["<Ninguno>"] + [n for n in numericos if n != nombre],
                             state="readonly", width=22).grid(row=i, column=5, padx=T.px(4), pady=1)
            else:
                cb_f.configure(state="disabled" if tipo in ("dim", "fecha") else "readonly")
            self.filas[nombre] = (v_t, v_f, v_r, v_p, tipo)
        g.update_idletasks()
        zona.lienzo.configure(width=min(g.winfo_reqwidth(), T.px(1100)), height=min(g.winfo_reqheight(), T.px(460)))

    def resultado_actual(self):
        titulos, formatos, resumen, peso = {}, {}, {}, {}
        for nombre, (v_t, v_f, v_r, v_p, tipo) in self.filas.items():
            if v_t.get().strip() and v_t.get().strip() != nombre:
                titulos[nombre] = v_t.get().strip()
            f = self._fmt_inv.get(v_f.get(), "General")
            if f != "General":
                formatos[nombre] = f
            if tipo in ("num", "calc"):
                r = self._res_inv.get(v_r.get(), "sum")
                if r != "sum":
                    resumen[nombre] = r
                if v_p.get() and v_p.get() != "<Ninguno>":
                    peso[nombre] = v_p.get()
        return {"titulos": titulos, "formatos_campo": formatos, "resumen_campo": resumen, "peso_campo": peso}


# ----------------------------------------------------------------------------
# Campos y áreas (etiquetas con borde fino)
# ----------------------------------------------------------------------------
class _Chip(tk.Label):
    def __init__(self, master, texto, simbolo="", activo=True):
        p = T.p
        super().__init__(master, text=(f"{simbolo}   " if simbolo else "") + texto, anchor="w",
                         background=p["panel"], foreground=p["texto"] if activo else p["deshab"], font=T.f["base"],
                         padx=T.px(8), pady=T.px(2), highlightthickness=1, highlightbackground=p["separador"],
                         cursor="hand2" if activo else "arrow")
        self.bind("<Enter>", lambda e: self.configure(background=p["hover"]))
        self.bind("<Leave>", lambda e: self.configure(background=p["panel"]))


class AreaPivot(tk.Frame):
    def __init__(self, master, pagina, clave):
        p = T.p
        super().__init__(master, background=p["panel"])
        self.pagina, self.clave = pagina, clave
        self._area = clave
        self.items = []
        tk.Label(self, text=NOMBRES_AREA[clave], background=p["panel"], foreground=p["acento"], font=T.f["negrita"],
                 anchor="w").pack(fill="x", pady=(T.px(4), T.px(2)))
        self.caja = tk.Frame(self, background=p["panel_alt"], highlightthickness=1, highlightbackground=p["borde"])
        self.caja.pack(fill="both", expand=True)
        self.caja._area = clave

    def texto(self, it):
        if self.clave == "valores":
            t = pivot.nombre_valor(it, self.pagina.medidas, self.pagina.cfg)
            return t + (f"  [{pivot.MOSTRAR_COMO[it['mostrar']]}]" if it.get("mostrar") in pivot.MOSTRAR_COMO
                        and it.get("mostrar") else "")
        t = ((self.pagina.cfg.get("titulos") or {}).get(it["campo"]) or it["campo"])
        if it.get("intervalo"):
            t += f"  [Intervalo {it['intervalo']:g}]"
        if self.clave == "filtros" and pivot.filtro_activo(it):
            t += "  ⚑"
        return t

    def refrescar(self):
        for w in self.caja.winfo_children():
            w.destroy()
        for i, it in enumerate(self.items):
            ch = _Chip(self.caja, self.texto(it))
            ch.pack(fill="x", padx=T.px(4), pady=(T.px(3) if i == 0 else T.px(2), 0))
            ch._area, ch._indice = self.clave, i
            self.pagina._enlazar_drag(ch, self.clave, i)
            ch.bind("<Double-Button-1>", lambda e, i=i: self._doble(e, i))
            ch.bind("<Button-3>", lambda e, i=i: self._contextual(e, i))
        if not self.items:
            tk.Label(self.caja, text="Arrastre campos aquí", background=T.p["panel_alt"], foreground=T.p["deshab"],
                     font=T.f["chica"]).pack(pady=T.px(8))

    def _doble(self, e, i):
        if self.pagina.solo_lectura:
            return
        if self.clave == "filtros":
            self.pagina.editar_filtro(i, e.widget)
        else:
            self._contextual(e, i)

    def _contextual(self, e, i):
        if self.pagina.solo_lectura:
            return
        it = self.items[i]
        pg = self.pagina
        m = nuevo_menu(self)
        if self.clave == "valores" and it["campo"] not in pg.medidas:
            sub = nuevo_menu(m)
            for clave in pivot.agregaciones_validas(pg.df, it["campo"], pg.medidas):
                sub.add_command(label=pivot.AGREGACIONES[clave][0], command=lambda c=clave: pg.cambiar_agg(i, c))
            if pivot.campo_numerico(pg.df, it["campo"]) and it["campo"] != pivot.RECUENTO:
                pond = nuevo_menu(sub)
                for peso in pg.campos_numericos():
                    if peso != it["campo"]:
                        pond.add_command(label=peso, command=lambda w=peso: pg.cambiar_agg(i, "wmean", w))
                sub.add_separator()
                sub.add_cascade(label="Promedio Ponderado por", menu=pond)
            m.add_cascade(label="Resumir Valores por", menu=sub)
        if self.clave == "valores":
            como = nuevo_menu(m)
            for k, etq in pivot.MOSTRAR_COMO.items():
                como.add_command(label=("●  " if it.get("mostrar") == k else "     ") + etq,
                                 command=lambda kk=k: pg.mostrar_como(i, kk))
            m.add_cascade(label="Mostrar Valores Como", menu=como)
        if self.clave == "filtros":
            m.add_command(label="Editar Filtro…", command=lambda: pg.editar_filtro(i, e.widget))
        if self.clave in ("filas", "columnas") and pg.es_numerico(it["campo"]):
            m.add_command(label="Agrupar por Intervalo…", command=lambda: pg.editar_intervalo(self.clave, i))
            if it.get("intervalo"):
                m.add_command(label="Quitar Agrupación", command=lambda: pg.quitar_intervalo(self.clave, i))
        m.add_separator()
        if self.clave != "valores":
            for destino in ("filas", "columnas", "filtros"):
                if destino != self.clave:
                    m.add_command(label=f"Mover a {NOMBRES_AREA[destino]}",
                                  command=lambda d=destino: pg.mover(self.clave, i, d))
        m.add_command(label="Subir", command=lambda: pg.reordenar(self.clave, i, i - 1),
                      state="normal" if i > 0 else "disabled")
        m.add_command(label="Bajar", command=lambda: pg.reordenar(self.clave, i, i + 1),
                      state="normal" if i < len(self.items) - 1 else "disabled")
        m.add_separator()
        m.add_command(label="Quitar Campo", command=lambda: pg.quitar(self.clave, i))
        mostrar_menu(m, e)


# ----------------------------------------------------------------------------
# Página de tabla dinámica
# ----------------------------------------------------------------------------
class PaginaPivot(ttk.Frame):
    """df: datos (None = solo lectura con el último resultado guardado).
    guardado: {"config":..., "resultado":...}; al_guardar(dict) persiste el estado en el escenario."""

    def __init__(self, master, vista, df, guardado=None, titulo=None, medidas=None, al_guardar=None,
                 motivo_solo_lectura=None, config_inicial=None, nota=None):
        super().__init__(master, style="Panel.TFrame")
        self.vista = vista
        self.esc = vista.esc
        self.df = df
        self.medidas_base = dict(medidas or {})
        self.al_guardar = al_guardar
        self.solo_lectura = df is None
        self._drag = None
        self._tarea = None
        self._cubo = None
        self._tabla = None
        self._ultimo_guardado = guardado
        self._primer_guardado = True       # el primer cálculo al abrir no es un cambio del usuario
        self.cfg = {"filas": [], "columnas": [], "valores": [], "filtros": [], "opciones": {},
                    "grafico": True, "grafico_apilado": False, "grafico_horizontal": False, "grafico_series": None,
                    "expresiones": [], "titulos": {}, "formatos_campo": {}, "resumen_campo": {}, "peso_campo": {},
                    "colapsadas_filas": [], "colapsadas_columnas": []}
        if guardado and isinstance(guardado.get("config"), dict):
            self.cfg.update(copy.deepcopy(guardado["config"]))
        elif config_inicial:
            self.cfg.update(copy.deepcopy(config_inicial))
        self.opc = pivot.opciones(self.cfg)
        self._resultado = (guardado or {}).get("resultado")

        if self.solo_lectura:
            Aviso(self, motivo_solo_lectura or "Se muestra el último resultado guardado. "
                  "Los archivos CSV no están disponibles.").pack(fill="x", padx=T.px(12), pady=(T.px(8), 0))
        self._barra_herramientas()
        self.panel = ttk.PanedWindow(self, orient="horizontal")
        self.panel.pack(fill="both", expand=True, padx=T.px(8), pady=(T.px(4), T.px(8)))
        izq = ttk.PanedWindow(self.panel, orient="vertical")
        self.der = ttk.Frame(self.panel, style="Panel.TFrame", width=T.px(300))
        self.panel.add(izq, weight=1)
        self.panel.add(self.der, weight=0)
        sup = ttk.Frame(izq, style="Panel.TFrame")
        izq.add(sup, weight=3)
        self._izq = izq
        self.barra_filtros = tk.Frame(sup, background=T.p["panel"])
        self.barra_filtros.pack(fill="x")
        self.marco_res = ttk.Frame(sup, style="Panel.TFrame")
        self.marco_res.pack(fill="both", expand=True)
        inf = ttk.Frame(izq, style="Panel.TFrame")
        izq.add(inf, weight=2)
        self._barra_grafico(inf)
        self._panel_campos()
        if self.solo_lectura:
            for b in self._botones_edicion:
                b.state(["disabled"])
        self._pintar_campos()
        self._refrescar_areas()
        self.after(250, self._ubicar_divisor)
        if self.df is not None:
            if any(self.cfg[k] for k in ("filas", "columnas", "valores")):
                self.after(60, self.calcular)
            else:
                self._estado_vacio()
        elif self._resultado:
            self._mostrar_plano(self._resultado)
        else:
            self._estado_vacio()

    # ---- estructura -------------------------------------------------------------------------------------
    def _barra_herramientas(self):
        p = T.p
        barra = tk.Frame(self, background=p["panel_alt"], highlightthickness=1, highlightbackground=p["separador"])
        barra.pack(fill="x", padx=T.px(8), pady=(T.px(8), 0))
        self._imgs = []
        self._botones_edicion = []

        def boton(texto, icono, cmd, tip, edicion=True):
            img = T.icono(icono, 16, p["texto"]) if icono else None
            self._imgs.append(img)
            b = ttk.Button(barra, text=texto, image=img or "", compound="left", style="Tool.TButton", command=cmd,
                           takefocus=False)
            b.pack(side="left", padx=(T.px(2), 0), pady=T.px(3))
            Tooltip(b, tip)
            if edicion:
                self._botones_edicion.append(b)
            return b

        def sep():
            tk.Frame(barra, background=p["separador"], width=1).pack(side="left", fill="y", padx=T.px(6), pady=T.px(6))
        boton(" Agregar Campo Calculado", "funcion", self.agregar_expresion,
              "Crea un campo con una expresión tipo Excel (por fila o de resumen)")
        boton(" Editar Expresiones", "editar", self.editar_expresiones, "Modifica o elimina los campos calculados")
        boton(" Formato de Campos", "formato", self.formatos, "Título, formato numérico, resumen y ponderación de cada campo")
        boton(" Actualizar", "actualizar", self.calcular, "Recalcula la tabla dinámica")
        sep()
        self.v_campos = tk.BooleanVar(value=self.opc.get("campos_visibles", True))
        ttk.Checkbutton(barra, text="Campos Visibles", variable=self.v_campos, style="TCheckbutton",
                        command=self._campos_visibles).pack(side="left", padx=(T.px(4), T.px(4)))
        self.btn_opc = boton(" Opciones de Pivote ▾", "opciones", self._menu_opciones,
                             "Encabezados, totales, subtotales, líneas y actualización automática", edicion=False)
        sep()
        boton(" Expandir", "expandir", lambda: self.grilla and self.grilla.expandir_todo(), "Despliega todos los grupos",
              edicion=False)
        boton(" Contraer", "contraer", lambda: self.grilla and self.grilla.contraer_todo(),
              "Contrae al primer nivel de filas y columnas", edicion=False)
        sep()
        boton(" Copiar Tabla", "copiar", self._copiar, "Copia la tabla (péguela en Excel)", edicion=False)
        boton(" Exportar a Excel", "excel", self._exportar, "Exporta la tabla y su gráfico a Excel", edicion=False)
        boton(" Limpiar", "borrar", self.limpiar, "Quita todos los campos de las áreas")
        self.grilla = None

    def _barra_grafico(self, inf):
        barra_g = ttk.Frame(inf, style="Panel.TFrame")
        barra_g.pack(fill="x", pady=(T.px(8), T.px(4)))
        ttk.Label(barra_g, text="Gráfico", style="Subtitulo.TLabel").pack(side="left", padx=(0, T.px(14)))
        self.v_graf = tk.BooleanVar(value=self.cfg.get("grafico", True))
        ttk.Checkbutton(barra_g, text="Mostrar", variable=self.v_graf, style="Panel.TCheckbutton",
                        command=self._opciones_grafico).pack(side="left")
        self.seg_tipo = Segmentado(barra_g, [("agrupado", "Agrupadas"), ("apilado", "Apiladas")],
                                   "apilado" if self.cfg.get("grafico_apilado") else "agrupado",
                                   lambda v: self._opciones_grafico())
        self.seg_tipo.pack(side="left", padx=(T.px(14), 0))
        self.seg_ori = Segmentado(barra_g, [("v", "Vertical"), ("h", "Horizontal")],
                                  "h" if self.cfg.get("grafico_horizontal") else "v", lambda v: self._opciones_grafico())
        self.seg_ori.pack(side="left", padx=(T.px(10), 0))
        self.sel_series = MultiSeleccion(barra_g, "Series", [], lambda v: self._opciones_grafico(),
                                         plural="Todas las Series", ancho=24)
        self.sel_series.pack(side="left", padx=(T.px(14), 0))
        self.grafico = GraficoBarras(inf, alto=220)
        self.grafico.nombre = "Tabla Dinámica"
        self.grafico.pack(fill="both", expand=True)

    def _panel_campos(self):
        p = T.p
        der = self.der
        der.pack_propagate(False)
        ttk.Label(der, text="Campos", style="Subtitulo.TLabel").pack(anchor="w", padx=T.px(8))
        fila = tk.Frame(der, background=p["campo"], highlightthickness=1, highlightbackground=p["borde"],
                        highlightcolor=p["acento"])
        fila.pack(fill="x", padx=T.px(8), pady=(T.px(3), T.px(3)))
        self._lupa = T.icono("buscar", 13, p["suave"])
        tk.Label(fila, image=self._lupa, background=p["campo"]).pack(side="left", padx=(T.px(6), T.px(2)))
        self.var_buscar = tk.StringVar()
        tk.Entry(fila, textvariable=self.var_buscar, relief="flat", background=p["campo"], foreground=p["texto"],
                 insertbackground=p["texto"], font=T.f["base"]).pack(side="left", fill="x", expand=True, ipady=T.px(3))
        self.var_buscar.trace_add("write", lambda *a: self._pintar_campos())
        cont = ttk.PanedWindow(der, orient="vertical")
        cont.pack(fill="both", expand=True, padx=T.px(8))
        self._der = cont
        arriba = ttk.Frame(cont, style="Panel.TFrame")
        abajo = ttk.Frame(cont, style="Panel.TFrame")
        cont.add(arriba, weight=1)
        cont.add(abajo, weight=2)
        self.lista_campos = ScrollFrame(arriba, margen_inferior=False)
        self.lista_campos.pack(fill="both", expand=True, pady=(0, T.px(4)))
        ttk.Label(abajo, text="Arrastre campos entre las áreas (doble clic agrega)", style="PanelSuave.TLabel",
                  font=T.f["chica"]).pack(anchor="w", pady=(T.px(4), 0))
        zona = ttk.Frame(abajo, style="Panel.TFrame")
        zona.pack(fill="both", expand=True)
        zona.columnconfigure((0, 1), weight=1, uniform="a")
        zona.rowconfigure((0, 1), weight=1)
        self.areas = {c: AreaPivot(zona, self, c) for c in ("filtros", "columnas", "filas", "valores")}
        self.areas["filtros"].grid(row=0, column=0, sticky="nsew", padx=(0, T.px(5)), pady=(0, T.px(2)))
        self.areas["columnas"].grid(row=0, column=1, sticky="nsew", pady=(0, T.px(2)))
        self.areas["filas"].grid(row=1, column=0, sticky="nsew", padx=(0, T.px(5)))
        self.areas["valores"].grid(row=1, column=1, sticky="nsew")
        validos = None if self.df is None else set(self.nombres_campos())
        for clave, area in self.areas.items():
            area.items = [dict(x) for x in self.cfg.get(clave, [])
                          if isinstance(x, dict) and x.get("campo") and (validos is None or x["campo"] in validos)]
        # filtros guardados con valores que ya no existen (p. ej. otra réplica): se descartan esos valores
        if self.df is not None:
            from perezoso import pd
            for f in self.areas["filtros"].items:
                if f.get("incluir") is not None and f["campo"] in self.df.columns:
                    s = self.df[f["campo"]]
                    presentes = set(map(str, s.cat.categories)) if isinstance(s.dtype, pd.CategoricalDtype) \
                        else set(map(str, s.dropna().unique()))
                    f["incluir"] = [v for v in f["incluir"] if str(v) in presentes] or None
        if not self.opc.get("campos_visibles", True):
            self.panel.forget(self.der)

    def _ubicar_divisor(self):
        try:
            alto = self._izq.winfo_height()
            if alto > 200:
                self._izq.sashpos(0, int(alto * 0.56))
            alto = self._der.winfo_height()
            if alto > 200:
                self._der.sashpos(0, int(alto * 0.42))
        except Exception:
            pass

    # ---- utilidades -------------------------------------------------------------------------------------------
    @property
    def medidas(self):
        m = dict(self.medidas_base)
        for e in self.cfg.get("expresiones") or []:
            try:
                if self.df is not None and ex.es_resumen(ex.analizar(e["expresion"])):
                    m[e["nombre"]] = {"tipo": "expr"}
            except ex.ErrorExpresion:
                pass
        return m

    def calculados(self):
        return [e["nombre"] for e in self.cfg.get("expresiones") or []]

    def nombres_campos(self):
        if self.df is None:
            return []
        return pivot.nombres_campos(self.df, self.medidas_base, self.cfg)

    def df_calculado(self):
        """Datos con los campos calculados por fila (se recalcula solo si cambian las expresiones)."""
        firma = tuple((e["nombre"], e["expresion"]) for e in self.cfg.get("expresiones") or [])
        if getattr(self, "_firma_calc", None) != firma:
            self._firma_calc = firma
            self._df_calc = pivot.preparar_expresiones(self.df, self.cfg)[0] if firma else self.df
        return self._df_calc

    def es_numerico(self, campo):
        if self.df is None or campo == pivot.RECUENTO or campo in self.medidas:
            return False
        df = self.df_calculado() if campo in self.calculados() else self.df
        return campo in df.columns and pivot.campo_numerico(df, campo)

    def campos_numericos(self):
        return [c for c in self.df.columns if pivot.es_numerico(self.df[c])] if self.df is not None else []

    def _pintar_campos(self):
        cont = self.lista_campos.interior
        for w in cont.winfo_children():
            w.destroy()
        if self.df is None:
            return
        q = self.var_buscar.get().strip().lower()
        calc = self.calculados()
        grupos = {g: [] for g, _n, _s in GRUPOS_CAMPOS}
        for nombre in self.nombres_campos():
            if q and q not in nombre.lower():
                continue
            grupos["calc" if nombre in calc else tipo_campo(self.df, nombre, self.medidas_base)].append(nombre)
        grupos["dim"].sort(key=lambda n: (n != "Réplica", 0))
        grupos["fecha"].sort(key=lambda n: CAMPOS_FECHA.index(n) if n in CAMPOS_FECHA else 9)
        p = T.p
        for g, titulo, simbolo in GRUPOS_CAMPOS:
            if not grupos[g]:
                continue
            tk.Label(cont, text=f"{titulo}  ({len(grupos[g])})", background=p["panel"], foreground=p["acento"],
                     font=T.f["negrita"], anchor="w").pack(fill="x", pady=(T.px(6), T.px(2)))
            for nombre in grupos[g]:
                marca = "#" if nombre == pivot.RECUENTO else simbolo
                titulo_c = (self.cfg.get("titulos") or {}).get(nombre)
                ch = _Chip(cont, nombre + (f"  ({titulo_c})" if titulo_c else ""), marca)
                ch.pack(fill="x", pady=(0, T.px(2)), padx=(0, T.px(2)))
                self._enlazar_drag(ch, "campos", nombre)
                ch.bind("<Double-Button-1>", lambda e, n=nombre: self._doble_campo(n))

    def _doble_campo(self, nombre):
        if self.solo_lectura:
            return
        t = tipo_campo(self.df, nombre, self.medidas, self.calculados())
        destino = "valores" if t in ("medida", "num", "calc") else "filas"
        if t == "calc" and nombre not in self.medidas:
            destino = "valores" if self.es_numerico(nombre) else "filas"
        self._agregar(destino, {"campo": nombre})

    def _df_filtro(self, campo):
        return self.df_calculado() if campo in self.calculados() else self.df

    # ---- arrastrar y soltar ---------------------------------------------------------------------------------
    def _enlazar_drag(self, w, origen, dato):
        w.bind("<ButtonPress-1>", lambda e: self._dn(e, origen, dato), add="+")
        w.bind("<B1-Motion>", self._mv, add="+")
        w.bind("<ButtonRelease-1>", self._up, add="+")

    def _dn(self, e, origen, dato):
        self._drag = None
        if self.solo_lectura:
            return
        if origen == "campos":
            campo, idx = dato, None
        else:
            idx = dato
            campo = self.areas[origen].items[idx]["campo"]
        self._drag = {"origen": origen, "campo": campo, "idx": idx, "x": e.x_root, "y": e.y_root, "ghost": None}

    def _mv(self, e):
        d = self._drag
        if not d:
            return
        if d["ghost"] is None:
            if abs(e.x_root - d["x"]) + abs(e.y_root - d["y"]) < 8:
                return
            g = tk.Toplevel(self)
            g.wm_overrideredirect(True)
            g.transient(self.winfo_toplevel())
            try:
                g.attributes("-alpha", 0.9)
            except tk.TclError:
                pass
            tk.Label(g, text=" " + d["campo"] + " ", background=T.p["acento"], foreground="#FFFFFF",
                     font=T.f["negrita"], padx=T.px(10), pady=T.px(4)).pack()
            d["ghost"] = g
        d["ghost"].geometry(f"+{e.x_root + 14}+{e.y_root + 10}")

    def _up(self, e):
        d, self._drag = self._drag, None
        if not d or d["ghost"] is None:
            return
        d["ghost"].destroy()
        w = self.winfo_containing(e.x_root, e.y_root)
        destino, pos = None, None
        while w is not None:
            if hasattr(w, "_indice") and hasattr(w, "_area"):
                destino, pos = w._area, w._indice
                break
            if hasattr(w, "_area"):
                destino = w._area
                break
            w = w.master
        self._soltar(d, destino, pos)

    def _soltar(self, d, destino, pos):
        origen = d["origen"]
        if destino is None or destino == "campos":
            if origen in self.areas:
                self.quitar(origen, d["idx"])
            return
        if origen == destino:
            if pos is not None and pos != d["idx"]:
                self.reordenar(origen, d["idx"], pos)
            return
        if origen in self.areas:
            self.areas[origen].items.pop(d["idx"])
        self._agregar(destino, {"campo": d["campo"]}, pos)

    # ---- manipulación de áreas ---------------------------------------------------------------------------------
    def _agregar(self, destino, item, pos=None):
        campo = item["campo"]
        item = dict(item)
        medidas = self.medidas
        if destino == "valores":
            if campo == pivot.RECUENTO:
                item["agg"] = "sum"
            elif campo in medidas:
                item["agg"] = "medida"
            else:
                defecto = (self.cfg.get("resumen_campo") or {}).get(campo)
                if defecto and defecto in pivot.agregaciones_validas(self.df, campo, medidas) + ["wmean"]:
                    item.setdefault("agg", defecto)
                    if defecto == "wmean" and (self.cfg.get("peso_campo") or {}).get(campo):
                        item["peso"] = self.cfg["peso_campo"][campo]
                    elif defecto == "wmean":
                        item["agg"] = "mean"
                item.setdefault("agg", pivot.agregacion_por_defecto(self.df, campo, medidas)
                                if campo in self.df.columns else "sum")
        else:
            if campo == pivot.RECUENTO or campo in medidas:
                aviso(self, "Campo No Disponible", f"«{campo}» es una medida: solo puede usarse en Valores.")
                self._refrescar_areas()
                return
            if destino in ("filas", "columnas") and not item.get("intervalo") and campo in self.df.columns:
                n = pivot.n_distintos(self.df, campo)
                if n > LIMITE_DISTINTOS:
                    r = confirmar(self, "Confirmar Campo",
                                  [f"«{campo}» tiene {n:,} valores distintos: la tabla tendrá muchas "
                                   f"{'filas' if destino == 'filas' else 'columnas'}.",
                                   "¿Está seguro? (Para valores numéricos puede agruparlos por intervalo.)"],
                                  ("Sí, Agregar", "Cancelar"), cancelar=1)
                    if r != 0:
                        self._refrescar_areas()
                        return
            for otra in ("filas", "columnas", "filtros"):
                self.areas[otra].items = [x for x in self.areas[otra].items if x["campo"] != campo]
        lista = self.areas[destino].items
        if pos is None or pos > len(lista):
            lista.append(item)
        else:
            lista.insert(pos, item)
        if destino == "filtros":
            self._refrescar_areas()
            i = len(lista) - 1 if pos is None else pos
            self.after_idle(lambda: self.editar_filtro(i, self.areas["filtros"].caja))
            return
        self._cambio()

    def quitar(self, area, idx):
        self.areas[area].items.pop(idx)
        self._cambio()

    def mover(self, origen, idx, destino):
        item = self.areas[origen].items.pop(idx)
        self._agregar(destino, {"campo": item["campo"]})

    def reordenar(self, area, a, b):
        lista = self.areas[area].items
        b = max(0, min(b, len(lista) - 1))
        lista.insert(b, lista.pop(a))
        self._cambio()

    def mostrar_como(self, idx, modo):
        it = self.areas["valores"].items[idx]
        if modo:
            it["mostrar"] = modo
        else:
            it.pop("mostrar", None)
        self._cambio()

    def cambiar_agg(self, idx, agg, peso=None):
        it = self.areas["valores"].items[idx]
        it["agg"] = agg
        if peso:
            it["peso"] = peso
        else:
            it.pop("peso", None)
        self._cambio()

    def editar_filtro(self, idx, ancla):
        if idx >= len(self.areas["filtros"].items):
            return
        it = self.areas["filtros"].items[idx]
        df = self._df_filtro(it["campo"])
        if it["campo"] not in df.columns:
            return
        otros = [f for i, f in enumerate(self.areas["filtros"].items) if i != idx and pivot.filtro_activo(f)]
        if any(o["campo"] not in df.columns for o in otros):
            df = self.df_calculado()
        info = pivot.valores_filtro(df, it["campo"], [o for o in otros if o["campo"] in df.columns])

        def aplicar(r, i=idx):
            if i < len(self.areas["filtros"].items):
                self.areas["filtros"].items[i].update(r)
                self._cambio()
        FiltroCampo(ancla, it["campo"], info, it, aplicar)

    def editar_intervalo(self, area, idx):
        it = self.areas[area].items[idx]

        def aplicar(r):
            it["intervalo"] = r if r > 0 else None
            self._cambio()
        DialogoIntervalo(self, it["campo"], it.get("intervalo") or 1, aplicar, pagina=self).mostrar()

    def quitar_intervalo(self, area, idx):
        self.areas[area].items[idx].pop("intervalo", None)
        self._cambio()

    def limpiar(self):
        for a in self.areas.values():
            a.items = []
        self._cambio()

    def _refrescar_areas(self):
        for a in self.areas.values():
            a.refrescar()
        self._pintar_filtros_activos()

    def _pintar_filtros_activos(self):
        for w in self.barra_filtros.winfo_children():
            w.destroy()
        activos = [f for f in self.areas["filtros"].items if pivot.filtro_activo(f)]
        if not activos or not self.opc.get("encabezados_filtro", True):
            return
        p = T.p
        for i, f in enumerate(self.areas["filtros"].items):
            if not pivot.filtro_activo(f):
                continue
            vals = f.get("incluir")
            texto = (f"{f['campo']}: " + (", ".join(map(str, vals[:3])) + (f" +{len(vals) - 3}" if len(vals) > 3 else ""))
                     if vals is not None else f"{f['campo']}: {f.get('min', '')} – {f.get('max', '')}")
            chip = tk.Label(self.barra_filtros, text="⚑ " + texto, background=p["sel"], foreground=p["texto"],
                            font=T.f["chica"], padx=T.px(6), pady=T.px(1), highlightthickness=1,
                            highlightbackground=p["acento"], cursor="hand2")
            chip.pack(side="left", padx=(0, T.px(6)), pady=(0, T.px(4)))
            chip.bind("<Button-1>", lambda e, i=i: self.editar_filtro(i, e.widget))

    def _menu_opciones(self):
        m = nuevo_menu(self)
        for clave, texto in OPCIONES_MENU:
            m.add_command(label=("✓   " if self.opc.get(clave, True) else "      ") + texto,
                          command=lambda k=clave: self._alternar_opcion(k))
        x, y = self.btn_opc.winfo_rootx(), self.btn_opc.winfo_rooty() + self.btn_opc.winfo_height()
        try:
            m.tk_popup(x, y)
        finally:
            m.grab_release()

    def _alternar_opcion(self, clave):
        self.opc[clave] = not self.opc.get(clave, True)
        self.cfg.setdefault("opciones", {})[clave] = self.opc[clave]
        if clave == "auto":
            self._guardar_estado()
            return
        if clave == "encabezados_filtro":
            self._pintar_filtros_activos()
            self._guardar_estado()
            return
        if self._cubo is not None and self.grilla is not None:
            self.grilla.cargar(self._cubo, self.opc, self.cfg.get("colapsadas_filas"), self.cfg.get("colapsadas_columnas"),
                               self._formateadores(self._cubo))
        self._guardar_estado()

    def _campos_visibles(self):
        v = self.v_campos.get()
        self.opc["campos_visibles"] = v
        self.cfg.setdefault("opciones", {})["campos_visibles"] = v
        if v and str(self.der) not in self.panel.panes():
            self.panel.add(self.der, weight=0)
        elif not v and str(self.der) in self.panel.panes():
            self.panel.forget(self.der)
        self._guardar_estado()

    def _opciones_grafico(self):
        self.cfg["grafico"] = self.v_graf.get()
        self.cfg["grafico_apilado"] = self.seg_tipo.get() == "apilado"
        self.cfg["grafico_horizontal"] = self.seg_ori.get() == "h"
        self.cfg["grafico_series"] = self.sel_series.seleccion
        self._dibujar_grafico()
        self._guardar_estado()

    def _cambio(self):
        self._refrescar_areas()
        if self.opc.get("auto", True):
            self._programar()

    def _programar(self):
        if self._tarea:
            self.after_cancel(self._tarea)
        self._tarea = self.after(250, self.calcular)

    # ---- campos calculados y formatos ---------------------------------------------------------------------------
    def _campos_para_expresion(self):
        if self.df is None:
            return []
        return [c for c in self.df.columns if c not in pivot.campos_ocultos(self.df)] + \
            [e["nombre"] for e in self.cfg.get("expresiones") or [] if e["nombre"] not in self.df.columns]

    def agregar_expresion(self, existente=None):
        if self.df is None:
            return

        def aplicar(r):
            exprs = [e for e in self.cfg.get("expresiones") or [] if e["nombre"] not in (r["nombre"], r.get("original"))]
            exprs.append({"nombre": r["nombre"], "expresion": r["expresion"]})
            self.cfg["expresiones"] = exprs
            if r.get("original") and r["original"] != r["nombre"]:
                for a in self.areas.values():
                    for it in a.items:
                        if it["campo"] == r["original"]:
                            it["campo"] = r["nombre"]
            self._pintar_campos()
            self._cambio()
            self.vista.app.mensaje(f"Campo calculado «{r['nombre']}» listo: arrástrelo a Filas, Columnas o Valores")
        campos = [c for c in self._campos_para_expresion() if not existente or c != existente.get("nombre")]
        DialogoExpresion(self, self, campos, existente, aplicar).mostrar(T.px(900), T.px(560))

    def editar_expresiones(self):
        exprs = self.cfg.get("expresiones") or []
        if not exprs:
            aviso(self, "Editar Expresiones", "Aún no hay campos calculados. Use «Agregar Campo Calculado».")
            return
        m = nuevo_menu(self)
        for e in exprs:
            sub = nuevo_menu(m)
            sub.add_command(label="Editar…", command=lambda x=e: self.agregar_expresion(x))
            sub.add_command(label="Eliminar", command=lambda x=e: self._eliminar_expresion(x))
            m.add_cascade(label=f"{e['nombre']}   =   {e['expresion'][:48]}", menu=sub)
        x, y = self.winfo_pointerxy()
        try:
            m.tk_popup(x, y)
        finally:
            m.grab_release()

    def _eliminar_expresion(self, e):
        self.cfg["expresiones"] = [x for x in self.cfg.get("expresiones") or [] if x["nombre"] != e["nombre"]]
        for a in self.areas.values():
            a.items = [it for it in a.items if it["campo"] != e["nombre"]]
        self._pintar_campos()
        self._cambio()

    def formatos(self):
        if self.df is None:
            return
        calc = self.calculados()
        campos = [(n, tipo_campo(self.df, n, self.medidas_base, calc)) for n in self.nombres_campos()
                  if n != pivot.RECUENTO]

        def aplicar(r):
            self.cfg.update(r)
            self._pintar_campos()
            self._cambio()
        DialogoFormatos(self, self, campos, self.cfg, aplicar).mostrar()

    # ---- cálculo y resultado ---------------------------------------------------------------------------------
    def _config_actual(self):
        cfg = dict(self.cfg)
        for k in ("filas", "columnas", "valores", "filtros"):
            cfg[k] = [dict(x) for x in self.areas[k].items]
        cfg["opciones"] = {k: v for k, v in self.opc.items()}
        return cfg

    def calcular(self):
        self._tarea = None
        if self.df is None:
            return
        self.cfg = self._config_actual()
        if not (self.cfg["filas"] or self.cfg["columnas"] or self.cfg["valores"]):
            self._estado_vacio()
            self._guardar_estado()
            return
        try:
            self.configure(cursor="watch")
            cubo = pivot.calcular_cubo(self.df, self.cfg, self.medidas_base)
        except pivot.ErrorPivot as e:
            self._mensaje(str(e))
            return
        except MemoryError:
            error(self, "Memoria Insuficiente", "El resultado es demasiado grande. "
                  "Agregue filtros o reduzca los campos en Filas y Columnas.")
            return
        except Exception as e:  # noqa
            self._mensaje(f"No se pudo calcular la tabla: {e}")
            return
        finally:
            self.configure(cursor="")
        self._cubo = cubo
        self._mostrar_cubo(cubo)
        self._guardar_estado()

    def _formateadores(self, cubo):
        from grilla import formateadores_auto
        return formateadores_auto(cubo)

    def _mensaje(self, texto):
        for w in self.marco_res.winfo_children():
            w.destroy()
        self.grilla = None
        Placeholder(self.marco_res, "Tabla Dinámica", texto).pack(fill="both", expand=True)
        self.grafico.datos([], [])

    def _mostrar_cubo(self, cubo):
        if self.grilla is None or not self.grilla.winfo_exists():
            for w in self.marco_res.winfo_children():
                w.destroy()
            self.grilla = GrillaPivot(self.marco_res, self._estado_grilla)
            self.grilla.pack(fill="both", expand=True)
        for w in self.marco_res.winfo_children():
            if isinstance(w, Aviso):
                w.destroy()
        if cubo.get("avisos"):
            Aviso(self.marco_res, " ".join(cubo["avisos"])).pack(fill="x", pady=(0, T.px(4)), before=self.grilla)
        self.grilla.cargar(cubo, self.opc, self.cfg.get("colapsadas_filas"), self.cfg.get("colapsadas_columnas"),
                           self._formateadores(cubo))
        plano = pivot.aplanar(cubo, self.opc)
        self._resultado = plano
        series = [c for j, c in enumerate(plano["columnas"]) if j >= plano["n_dim"] and pivot.TOTAL not in c]
        self.sel_series.set_opciones(series)
        guard = self.cfg.get("grafico_series")
        elegidas = [s for s in (guard or []) if s in series]
        if not elegidas and series:
            fmts = plano.get("formatos") or []
            pct = [c for j, c in enumerate(plano["columnas"]) if c in series and j < len(fmts) and fmts[j] == "pct"]
            elegidas = pct or series[: max(1, len(series) if len(cubo["valores"]) == 1 else 1)]
        self.sel_series.seleccion = None if set(elegidas) == set(series) else elegidas
        self.sel_series._texto()
        self._dibujar_grafico()

    def _estado_grilla(self, estado):
        self.cfg["colapsadas_filas"] = estado["colapsadas_filas"]
        self.cfg["colapsadas_columnas"] = estado["colapsadas_columnas"]
        self._guardar_estado()

    def _mostrar_plano(self, tabla):
        """Solo lectura: último resultado guardado (tabla plana)."""
        for w in self.marco_res.winfo_children():
            w.destroy()
        n_dim = tabla["n_dim"]
        formatos = tabla.get("formatos") or [None] * len(tabla["columnas"])
        funcs = [None if j < n_dim else (formateador(formatos[j]) or formateador("#,##0.0"))
                 for j in range(len(tabla["columnas"]))]
        filas = [([("" if v is None else (str(v) if j < n_dim else funcs[j](v))) for j, v in enumerate(f)], f,
                  i in tabla["totales"]) for i, f in enumerate(tabla["filas"])]
        cols = [{"key": f"c{j}", "titulo": n.replace(pivot.SEP, " · "), "ancla": "w" if j < n_dim else "e"}
                for j, n in enumerate(tabla["columnas"])]
        t = TablaDatos(self.marco_res, cols, alto=12, hscroll=True)
        t.pack(fill="both", expand=True)
        t.cargar(filas)
        self._tabla = t
        self._resultado = tabla
        self._dibujar_grafico()

    def _guardar_estado(self):
        if self.al_guardar is None:
            return
        tabla = self._resultado
        guardable = None
        if tabla is not None and len(tabla["filas"]) * max(1, len(tabla["columnas"])) <= LIMITE_CELDAS_GUARDADAS:
            guardable = tabla
        nuevo = {"config": self._limpia_cfg(), "resultado": guardable}
        primero, self._primer_guardado = self._primer_guardado, False
        if nuevo != self._ultimo_guardado:
            self._ultimo_guardado = nuevo
            # al abrir solo se normaliza la configuración guardada: no marca el escenario como modificado
            self.al_guardar(nuevo, not primero)

    def _limpia_cfg(self):
        cfg = copy.deepcopy(self._config_actual() if not self.solo_lectura else self.cfg)
        for k in ("filas", "columnas", "valores", "filtros"):
            cfg[k] = [{kk: vv for kk, vv in x.items() if not kk.startswith("_")} for x in cfg.get(k, [])]
        cfg.pop("decimales", None)
        return cfg

    def _estado_vacio(self):
        for w in self.marco_res.winfo_children():
            w.destroy()
        self.grilla = None
        self._cubo = None
        self._resultado = None
        Placeholder(self.marco_res, "Tabla Dinámica Vacía",
                    "Arrastre campos a Filas, Columnas y Valores para construir el análisis.").pack(fill="both", expand=True)
        self.grafico.datos([], [])

    def _dibujar_grafico(self):
        tabla = self._resultado
        if not self.v_graf.get() or not tabla:
            self.grafico.datos([], [])
            if not self.v_graf.get():
                self.grafico.configure(height=1)
            return
        self.grafico.configure(height=T.px(220))
        n_dim = tabla["n_dim"]
        formatos = tabla.get("formatos") or [None] * len(tabla["columnas"])
        elegidas = set(self.sel_series.valores())
        idx = [j for j, c in enumerate(tabla["columnas"]) if j >= n_dim and pivot.TOTAL not in c and c in elegidas]
        if not idx:
            self.grafico.datos([], [])
            return
        base_fmt = "pct" if formatos[idx[0]] == "pct" else "num"
        idx = [j for j in idx if ("pct" if formatos[j] == "pct" else "num") == base_fmt]
        filas = [f for i, f in enumerate(tabla["filas"]) if i not in tabla["totales"]][:MAX_CATEGORIAS_GRAFICO]
        categorias = [" · ".join(str(x) for x in f[:n_dim] if str(x)) for f in filas]
        factor = 100.0 if base_fmt == "pct" else 1.0
        series = [(str(tabla["columnas"][j]).replace(pivot.SEP, " · "),
                   [None if f[j] is None else f[j] * factor for f in filas], None) for j in idx]
        formato = (lambda v: f"{v:,.1f}%") if base_fmt == "pct" else (lambda v: f"{v:,.0f}" if abs(v) >= 100 else f"{v:,.2f}")
        self.grafico.datos(categorias, series, apilado=self.seg_tipo.get() == "apilado",
                           horizontal=self.seg_ori.get() == "h", formato=formato,
                           titulo=("" if len(tabla["filas"]) - len(tabla["totales"]) <= MAX_CATEGORIAS_GRAFICO
                                   else f"Se grafican las primeras {MAX_CATEGORIAS_GRAFICO} categorías"))

    def _copiar(self):
        if self.grilla is not None:
            self.grilla.copiar()
        elif self._tabla is not None:
            self._tabla.copiar()

    def _exportar(self):
        if self._resultado is None:
            aviso(self, "Sin Resultado", "No hay una tabla para exportar.")
            return
        self.vista.app.exportar_tabla_pivot(self.vista, self._resultado, self.cfg)
