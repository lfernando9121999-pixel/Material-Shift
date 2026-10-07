"""Gestión de guardado y carga de escenarios en formato .simx (JSON con extensión propia).

Mejoras respecto al código base del documento de especificación:
  * Rutas completas (el usuario guarda/abre en cualquier carpeta) y nombres saneados.
  * Escritura atómica (archivo temporal + reemplazo) para no corromper un escenario existente.
  * Serialización segura de tipos numpy/NaN (JSON estándar válido).
  * Lectura tolerante (UTF-8 con o sin BOM), validación de estructura y versión.
  * Sin 'print' (el ejecutable sin consola no dispone de salida estándar); se usa logging.
"""
import gzip
import json
import logging
import math
import os
from datetime import datetime
from pathlib import Path

import config
import fmt

log = logging.getLogger("sima.archivo")


class ErrorEscenario(Exception):
    """Error legible para el usuario al guardar o abrir un escenario."""


def _limpiar(obj):
    """Convierte numpy/NaN/Inf/Path a tipos JSON válidos."""
    try:
        import numpy as np
    except Exception:  # pragma: no cover
        np = None
    if isinstance(obj, dict):
        return {str(k): _limpiar(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_limpiar(v) for v in obj]
    if isinstance(obj, Path):
        return str(obj)
    if np is not None:
        if isinstance(obj, np.generic):
            obj = obj.item()
        elif isinstance(obj, np.ndarray):
            return _limpiar(obj.tolist())
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return round(obj, 7)
    return obj


class GestorEscenarios:
    """Guarda, abre y lista escenarios .simx."""

    def __init__(self, carpeta=None):
        self.carpeta = Path(carpeta) if carpeta else config.dir_escenarios()
        try:
            self.carpeta.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass

    # ------------------------------------------------------------------
    def ruta_por_defecto(self, nombre_escenario, carpeta=None):
        base = Path(carpeta) if carpeta else self.carpeta
        return base / (fmt.nombre_archivo_seguro(nombre_escenario) + config.EXTENSION)

    @staticmethod
    def _asegurar_extension(ruta):
        ruta = Path(ruta)
        if ruta.suffix.lower() != config.EXTENSION:
            ruta = ruta.with_name(ruta.name + config.EXTENSION)
        return ruta

    def _escribir(self, ruta, contenido):
        ruta = self._asegurar_extension(ruta)
        try:
            ruta.parent.mkdir(parents=True, exist_ok=True)
            tmp = ruta.with_name(ruta.name + ".tmp")
            # JSON compacto y comprimido (gzip): el archivo pesa ~10 veces menos y se abre más rápido
            texto = json.dumps(_limpiar(contenido), separators=(",", ":"), ensure_ascii=False)
            with gzip.open(tmp, "wb", compresslevel=6) as f:
                f.write(texto.encode("utf-8"))
            os.replace(tmp, ruta)
        except OSError as e:
            raise ErrorEscenario(f"No se pudo guardar el escenario en:\n{ruta}\n\n{e.strerror or e}")
        log.info("Guardado %s (%d bytes sin comprimir)", ruta, len(texto))
        return ruta

    @staticmethod
    def _metadata(nombre, estado):
        return {
            "version": config.VERSION_FORMATO,
            "programa": config.NOMBRE_PROGRAMA,
            "programa_version": config.VERSION,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "estado": estado,
            "nombre": nombre,
        }

    # ------------------------------------------------------------------
    def guardar_configuracion(self, ruta, nombre_escenario, config_dict):
        """Guarda solo parámetros/configuración (estado: no_ejecutado)."""
        return self._escribir(ruta, {
            "metadata": self._metadata(nombre_escenario, "no_ejecutado"),
            "configuracion": config_dict,
        })

    def guardar_con_resultados(self, ruta, nombre_escenario, config_dict, resultados_dict):
        """Guarda parámetros + resultados (estado: ejecutado)."""
        return self._escribir(ruta, {
            "metadata": self._metadata(nombre_escenario, "ejecutado"),
            "configuracion": config_dict,
            "resultados": resultados_dict,
        })

    # ------------------------------------------------------------------
    def cargar_escenario(self, ruta):
        ruta = Path(ruta)
        if not ruta.is_file():
            raise ErrorEscenario(f"No se encontró el archivo:\n{ruta}")
        try:
            with open(ruta, "rb") as f:
                crudo = f.read()
            if crudo[:2] == b"\x1f\x8b":           # v1.3+: comprimido; v1.0–v1.2: texto JSON
                crudo = gzip.decompress(crudo)
            datos = json.loads(crudo.decode("utf-8-sig"))
        except (OSError, EOFError):
            raise ErrorEscenario(f"El archivo «{ruta.name}» está dañado o no es un escenario de SimA.")
        except UnicodeDecodeError:
            raise ErrorEscenario("El archivo no tiene una codificación válida (se esperaba UTF-8).")
        except json.JSONDecodeError:
            raise ErrorEscenario(
                f"El archivo «{ruta.name}» está dañado o no es un escenario de SimA.")
        if (not isinstance(datos, dict) or "metadata" not in datos
                or not isinstance(datos.get("configuracion"), dict)):
            raise ErrorEscenario(f"«{ruta.name}» no tiene la estructura de un escenario de SimA.")
        version = str(datos["metadata"].get("version", "1.0"))
        if version.split(".")[0] != config.VERSION_FORMATO.split(".")[0]:
            raise ErrorEscenario(
                f"«{ruta.name}» fue creado con una versión incompatible del formato ({version}).")
        return datos

    def listar_escenarios(self, carpeta=None):
        base = Path(carpeta) if carpeta else self.carpeta
        try:
            return sorted(p.stem for p in base.iterdir()
                          if p.is_file() and p.suffix.lower() == config.EXTENSION)
        except OSError:
            return []
