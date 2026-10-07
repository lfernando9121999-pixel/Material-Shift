"""Constantes globales, rutas y preferencias persistentes de SimA."""
import json
import os
import sys
from pathlib import Path

NOMBRE_PROGRAMA = "SimA – Simulation Analyst"
NOMBRE_CORTO = "SimA"
NOMBRE_EXE = "SimA - Simulation Analyst"          # nombre del ejecutable (sin caracteres especiales)
VERSION = "1.5.0"
VERSION_CORTA = "v1.5"
FECHA_LANZAMIENTO = "07 Octubre 2026"
EXTENSION = ".simx"
VERSION_FORMATO = "1.0"
MAX_DESCRIPCION = 500

CARPETA_ESCENARIOS = "Escenarios"
CARPETA_INPUTS = "Inputs"
CARPETA_OUTPUTS = "Outputs"
CARPETA_MODELO = "Model"


def congelado():
    return bool(getattr(sys, "frozen", False))


def dir_app():
    """Carpeta principal del programa (donde vive el .exe, con Escenarios, Inputs, Outputs y Model).
    Independiente de la ubicación en el equipo."""
    if os.environ.get("SIMA_DIR"):            # carpeta alternativa (pruebas automatizadas)
        return Path(os.environ["SIMA_DIR"])
    if congelado():
        return Path(sys.executable).resolve().parent
    # Código fuente en «<carpeta principal>/Desarrollo/Codigo Fuente»: se sube hasta encontrar el programa
    aqui = Path(__file__).resolve().parent
    for p in aqui.parents:
        if (p / f"{NOMBRE_EXE}.exe").is_file() or (p / CARPETA_MODELO).is_dir():
            return p
    return aqui.parent.parent


def dir_recursos():
    if congelado():
        return Path(getattr(sys, "_MEIPASS", dir_app() / CARPETA_MODELO)) / "recursos"
    return Path(__file__).resolve().parent / "recursos"


def _asegurar(ruta):
    try:
        ruta.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return ruta


def dir_escenarios():
    return _asegurar(dir_app() / CARPETA_ESCENARIOS)


def dir_inputs():
    return _asegurar(dir_app() / CARPETA_INPUTS)


def dir_outputs():
    return _asegurar(dir_app() / CARPETA_OUTPUTS)


def _escribible(ruta):
    try:
        ruta.mkdir(parents=True, exist_ok=True)
        prueba = ruta / ".prueba_escritura"
        prueba.write_text("ok", encoding="utf-8")
        prueba.unlink()
        return True
    except OSError:
        return False


def dir_preferencias():
    """Preferencias del usuario: junto al programa si es escribible; si no, en APPDATA."""
    candidata = dir_app() / CARPETA_MODELO / "Preferencias"
    if _escribible(candidata):
        return candidata
    base = os.environ.get("APPDATA") or str(Path.home())
    alterna = Path(base) / "SimA"
    alterna.mkdir(parents=True, exist_ok=True)
    return alterna


def dir_escritorio():
    """Escritorio real del usuario (respeta OneDrive/redirecciones)."""
    try:
        import ctypes
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [("a", wintypes.DWORD), ("b", wintypes.WORD),
                        ("c", wintypes.WORD), ("d", wintypes.BYTE * 8)]

        guid = GUID(0xB4BFCC3A, 0xDB2C, 0x424C,
                    (wintypes.BYTE * 8)(0xB0, 0x29, 0x7F, 0xE9, 0x9A, 0x87, 0xC6, 0x41))
        ptr = ctypes.c_wchar_p()
        res = ctypes.windll.shell32.SHGetKnownFolderPath(
            ctypes.byref(guid), 0, None, ctypes.byref(ptr))
        if res == 0 and ptr.value:
            ruta = ptr.value
            ctypes.windll.ole32.CoTaskMemFree(ptr)
            if os.path.isdir(ruta):
                return Path(ruta)
    except Exception:
        pass
    alterna = Path.home() / "Desktop"
    return alterna if alterna.is_dir() else Path.home()


# ----------------------------------------------------------------------------
# Preferencias persistentes ("últimos cambios del último modelo")
# ----------------------------------------------------------------------------
def _ruta_prefs():
    return dir_preferencias() / "ultima_configuracion.json"


def cargar_preferencias():
    """Devuelve un dict; ante cualquier error devuelve valores por defecto (vacío)."""
    try:
        with open(_ruta_prefs(), "r", encoding="utf-8-sig") as f:
            datos = json.load(f)
        return datos if isinstance(datos, dict) else {}
    except Exception:
        return {}


def guardar_preferencias(datos):
    try:
        ruta = _ruta_prefs()
        tmp = ruta.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=2)
        os.replace(tmp, ruta)
    except Exception:
        pass
