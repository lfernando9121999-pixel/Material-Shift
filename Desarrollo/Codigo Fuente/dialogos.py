"""Diálogos modales con el estilo del programa: avisos amarillos, confirmaciones y progreso."""
import queue
import threading
import tkinter as tk
from tkinter import ttk

import config
from tema import T, centrar, titulo_oscuro


class Dialogo(tk.Toplevel):
    """Diálogo modal genérico. 'resultado' guarda el índice del botón elegido."""

    def __init__(self, padre, titulo, mensajes, botones=("Aceptar",), tipo="info",
                 predeterminado=0, cancelar=None, ancho=460):
        super().__init__(padre)
        self.resultado = cancelar if cancelar is not None else len(botones) - 1
        self._cancelar = cancelar
        self.withdraw()
        # barra de título con el nombre del programa; el asunto va dentro del aviso
        self.title(config.NOMBRE_PROGRAMA)
        self.transient(padre.winfo_toplevel())
        self.resizable(False, False)
        p = T.p
        self.configure(background=p["panel"])
        colores = {"aviso": (p["aviso_bg"], p["aviso_borde"], p["aviso_txt"], "alerta"),
                   "error": (p["panel_alt"], p["error"], p["texto"], "error"),
                   "info": (p["panel_alt"], p["acento"], p["texto"], "info"),
                   "pregunta": (p["panel_alt"], p["acento"], p["texto"], "info")}
        bg, borde, txt, icono = colores.get(tipo, colores["info"])

        cab = tk.Frame(self, background=bg, highlightbackground=borde, highlightthickness=0)
        cab.pack(fill="x")
        tk.Frame(cab, background=borde, height=T.px(3)).pack(fill="x")
        interior = tk.Frame(cab, background=bg)
        interior.pack(fill="x", padx=T.px(16), pady=T.px(9))
        img = T.icono(icono, 22, borde if tipo != "aviso" else p["aviso_txt"])
        if img:
            self._img = img
            tk.Label(interior, image=img, background=bg).pack(side="left", padx=(0, T.px(12)))
        tk.Label(interior, text=titulo, background=bg, foreground=txt,
                 font=T.f["subtitulo"], anchor="w").pack(side="left", fill="x", expand=True)

        cuerpo = tk.Frame(self, background=p["panel"])
        cuerpo.pack(fill="both", expand=True, padx=T.px(16), pady=(T.px(10), 0))
        if isinstance(mensajes, str):
            mensajes = [mensajes]
        for m in mensajes:
            tk.Label(cuerpo, text=m, background=p["panel"], foreground=p["texto"],
                     justify="left", anchor="w", wraplength=T.px(ancho),
                     font=T.f["base"]).pack(fill="x", pady=(0, T.px(4)))

        pie = tk.Frame(self, background=p["panel"])
        pie.pack(fill="x", padx=T.px(16), pady=(T.px(8), T.px(14)))
        self._botones = []
        for i, texto in reversed(list(enumerate(botones))):
            estilo = "Accent.TButton" if i == predeterminado else "TButton"
            b = ttk.Button(pie, text=texto, style=estilo, command=lambda i=i: self._elegir(i))
            b.pack(side="right", padx=(T.px(8), 0))
            self._botones.append(b)
        self.bind("<Return>", lambda e: self._elegir(predeterminado))
        self.bind("<Escape>", lambda e: self._elegir(self._cancelar if self._cancelar is not None
                                                     else len(botones) - 1))
        self.protocol("WM_DELETE_WINDOW", lambda: self._elegir(
            self._cancelar if self._cancelar is not None else len(botones) - 1))
        titulo_oscuro(self, T.nombre == "oscuro")
        centrar(self, padre.winfo_toplevel())
        self.deiconify()
        self.grab_set()
        self.focus_set()
        self.wait_window(self)

    def _elegir(self, i):
        self.resultado = i
        self.destroy()


def aviso(padre, titulo, mensajes, boton="Aceptar"):
    """Alerta amarilla (advertencia no bloqueante del flujo)."""
    return Dialogo(padre, titulo, mensajes, (boton,), tipo="aviso", cancelar=0).resultado


def error(padre, titulo, mensajes):
    return Dialogo(padre, titulo, mensajes, ("Aceptar",), tipo="error", cancelar=0).resultado


def info(padre, titulo, mensajes):
    return Dialogo(padre, titulo, mensajes, ("Aceptar",), tipo="info", cancelar=0).resultado


def confirmar(padre, titulo, mensajes, botones=("Sí", "No"), predeterminado=0, cancelar=None):
    return Dialogo(padre, titulo, mensajes, botones, tipo="pregunta",
                   predeterminado=predeterminado, cancelar=cancelar).resultado


# ----------------------------------------------------------------------------
# Trabajo en segundo plano con barra de progreso
# ----------------------------------------------------------------------------
class Progreso(tk.Toplevel):
    """Ejecuta 'trabajo(progreso, cancelado)' en un hilo y muestra el avance.

    progreso(fraccion, texto=None) puede llamarse desde el hilo.
    """

    def __init__(self, padre, titulo, trabajo, cancelable=True):
        super().__init__(padre)
        self.withdraw()
        self.title(titulo)
        self.transient(padre.winfo_toplevel())
        self.resizable(False, False)
        p = T.p
        self.configure(background=p["panel"])
        self._cola = queue.Queue()
        self._cancel = threading.Event()
        self.resultado = None
        self.excepcion = None
        self.cancelado = False

        marco = tk.Frame(self, background=p["panel"])
        marco.pack(fill="both", expand=True, padx=T.px(22), pady=T.px(18))
        tk.Label(marco, text=titulo, background=p["panel"], foreground=p["texto"],
                 font=T.f["subtitulo"]).pack(anchor="w")
        self._texto = tk.StringVar(value="Preparando…")
        tk.Label(marco, textvariable=self._texto, background=p["panel"], foreground=p["suave"],
                 width=58, anchor="w").pack(anchor="w", pady=(T.px(6), T.px(10)))
        self._barra = ttk.Progressbar(marco, mode="determinate", maximum=1000,
                                      length=T.px(420))
        self._barra.pack(fill="x")
        if cancelable:
            ttk.Button(marco, text="Cancelar", command=self._pedir_cancelar).pack(
                anchor="e", pady=(T.px(14), 0))
        self.protocol("WM_DELETE_WINDOW", self._pedir_cancelar if cancelable else (lambda: None))
        titulo_oscuro(self, T.nombre == "oscuro")
        centrar(self, padre.winfo_toplevel())
        self.deiconify()
        self.grab_set()

        def prog(fraccion, texto=None):
            self._cola.put(("p", fraccion, texto))

        def correr():
            try:
                self._cola.put(("ok", trabajo(prog, self._cancel.is_set)))
            except BaseException as e:  # noqa
                self._cola.put(("err", e))

        self._hilo = threading.Thread(target=correr, daemon=True)
        self._hilo.start()
        self.after(60, self._sondear)
        self.wait_window(self)

    def _pedir_cancelar(self):
        self._cancel.set()
        self.cancelado = True
        self._texto.set("Cancelando…")

    def _sondear(self):
        try:
            while True:
                msg = self._cola.get_nowait()
                if msg[0] == "p":
                    self._barra["value"] = max(0.0, min(1.0, msg[1])) * 1000
                    if msg[2]:
                        self._texto.set(msg[2])
                elif msg[0] == "ok":
                    self.resultado = msg[1]
                    self.destroy()
                    return
                else:
                    self.excepcion = msg[1]
                    self.destroy()
                    return
        except queue.Empty:
            pass
        self.after(60, self._sondear)


def con_progreso(padre, titulo, trabajo, cancelable=True):
    """Devuelve (resultado, excepcion). Si el usuario cancela, excepcion es csvio.Cancelado."""
    import csvio
    d = Progreso(padre, titulo, trabajo, cancelable)
    if d.excepcion is not None:
        return None, d.excepcion
    if d.cancelado and d.resultado is None:
        return None, csvio.Cancelado()
    return d.resultado, None


class VentanaModal(tk.Toplevel):
    """Base para ventanas emergentes modales con el tema del programa."""

    def __init__(self, padre, titulo, redimensionable=False):
        super().__init__(padre)
        self.withdraw()
        self.title(titulo)
        self.padre = padre.winfo_toplevel()
        self.transient(self.padre)
        self.resizable(redimensionable, redimensionable)
        self.configure(background=T.p["panel"])
        self.resultado = None
        self.protocol("WM_DELETE_WINDOW", self.cancelar)
        self.bind("<Escape>", lambda e: self.cancelar())

    def cancelar(self):
        self.resultado = None
        self.destroy()

    def mostrar(self):
        titulo_oscuro(self, T.nombre == "oscuro")
        centrar(self, self.padre)
        self.deiconify()
        self.grab_set()
        self.focus_set()
        self.wait_window(self)
        return self.resultado
