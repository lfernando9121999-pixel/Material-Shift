"""Importación diferida de pandas y numpy: la ventana abre sin esperar a cargarlos.

Se cargan en segundo plano apenas arranca el programa (precargar) o en el primer uso, lo que ocurra antes.
"""
import importlib
import threading


class _Modulo:
    def __init__(self, nombre):
        self._nombre = nombre
        self._modulo = None

    def _cargar(self):
        if self._modulo is None:
            self._modulo = importlib.import_module(self._nombre)
        return self._modulo

    def __getattr__(self, atributo):
        return getattr(self._cargar(), atributo)


np = _Modulo("numpy")
pd = _Modulo("pandas")


def precargar():
    """Carga pandas/numpy en un hilo mientras el usuario ve la interfaz."""
    threading.Thread(target=lambda: (np._cargar(), pd._cargar()), daemon=True).start()
