# SimA – Simulation Analyst

**Versión 1.5.0** · Date Release: 07 Octubre 2026 · Windows 10 / 11 · No requiere Python ni instalación

---

## Contenido de la carpeta

| Carpeta / Archivo | Uso |
|---|---|
| `SimA - Simulation Analyst.exe` | **Programa** (doble clic). La carpeta completa puede copiarse a cualquier ubicación o equipo. |
| `Escenarios\` · `Inputs\` · `Outputs\` | Escenarios `.simx` · CSV sugeridos · Reportes exportados. |
| `Model\` | Archivos internos del programa (no se modifican). Incluye `Preferencias\`. |
| `Manual de Usuario SimA v1.4.docx` | Guía paso a paso (versión anterior; el flujo de trabajo no cambia). |
| `Desarrollo\` | Código fuente (`compilar.ps1` regenera el programa) y verificación de cálculos. |

## Novedades de la versión 1.5

| Área | Cambio |
|---|---|
| **General** | Nuevo nombre «SimA – Simulation Analyst» con la versión a la derecha. Modo claro en grises suaves (los gráficos conservan sus colores) y separadores tenues entre pestañas. Sin parpadeos al actualizar: solo se reconstruye la pestaña visible. Minimizar, maximizar y mover la ventana funcionan sin bloqueos. |
| **Ventanas** | El explorador de archivos se abre a tamaño medio, centrado sobre el programa, movible y redimensionable. Cada escenario puede llevarse a otra ventana (arrastrando su pestaña o con clic derecho) y a otra pantalla. Las listas y filtros quedan ligados al programa y se abren en su misma pantalla. |
| **Emergentes** | No bloquean el programa; solo una abierta a la vez (abrir otra cierra la anterior conservando lo elegido) y se cierran al cambiar de pestaña. Filtros movibles, con ✕, estilo Excel: Limpiar Filtro, (Seleccionar Todo) y búsqueda cuando hay más de 8 valores. |
| **Tablas y gráficos** | Columnas reordenables arrastrando el encabezado. Clic derecho: Copiar Tabla / con Formato / como Imagen; Copiar Datos de Gráfico / Gráfico como Imagen / como Formato de PPT. Un color por grupo, más claro. Barra horizontal solo cuando las columnas no caben. |
| **Archivo** | «Abrir Existente» con los escenarios recientes. Diálogos más compactos con el título del programa. Archivos del Modelo con selección múltiple (Ctrl / Shift). |
| **Inputs** | `*` solo en General, Configuración de Equipos y Origen y Destino («* Requerido» en rojo oscuro); sin datos requeridos no se ejecuta (Descripción es opcional). **Configuración de Equipos** (antes Inputs de Análisis de Estados): flotas con resumen de columnas por estado y **Orden de Reporte** (prioridad Tipo / Categoría / Flota y orden de valores) aplicado a todo el programa. «Fuente de Energía» pasa a **Categoría**. **Origen y Destino**: Fase multiselección. **Vector Plan**: tabla completa con edición directa, indicador con selección múltiple de la misma familia (suma o promedio ponderado) y búsqueda. |
| **Análisis de Estados** | Botones Resumen / Detallado. Resumen: indicadores, distribución a todo el ancho, Por Flota y Por Tipo lado a lado, Por ID con «Gráficos por ID» por flota. Subpestañas Perforadoras / Palas / Camiones. |
| **Análisis de Tiempos** | Botones Tablas / Gráfico. |
| **Orígenes y Destinos** | Valores de la cascada centrados; tabla inferior a todo el alto; sin textos de ayuda. |
| **Tiempos y Métricas** | Subpestañas **Tiempos Ciclo** (Mínimo · Promedio · Máximo con gráfico de puntos) y **Métricas** (Registro de Ciclos, N° de Pases, Carga por Camión, N° Taladros, Productividad de Palas y de Camiones Por Flota / Por ID). |
| **Plan de Mina** | Día – Semana – Mes; filtro Tipo de Origen; «Rehandle»; ID Pala «SH001 - P&H4800»; divisor arrastrable; tabla Fase ▸ Flota Pala ▸ ID Pala agrupable con subtotales. |
| **Plan vs Simulación** | Subpestañas Reporte y Gráfico; columnas con el nombre del plan y del escenario; encabezado fijo; observaciones al pie con la fila en rojo. |
| **Tablas Dinámicas** | Diseño tipo DevExpress: grupos combinados y desplegables, subtotales y encabezados de varios niveles. Barra: Campo Calculado (fórmulas tipo Excel), Editar Expresiones, Formato de Campos, Actualizar, Campos Visibles, Opciones de Pivote, Expandir y Contraer. Réplica nunca usa NREP. |
| **Reportes** | Excel y PowerPoint con todas las pestañas y subpestañas en la configuración base (sin filtros). Cada hoja indica «Caso [escenario]» y la Fecha de Corrida. PowerPoint: una lámina por pestaña cuando es posible, tablas resumidas (nunca partidas) y gráficos nativos editables. |

## Flujo de trabajo

1. **Modelo ▸ Importar Resultados Simulación CSV** (`Ctrl+I`) o el icono «Importar Inputs» del panel.
2. **Inputs**: completar las subpestañas marcadas con `*` (Requerido) y, si se desea, el Orden de Reporte.
3. **Modelo ▸ Ejecutar Análisis** (`F5`).
4. Revisar las pestañas de resultados y filtrar desde los encabezados.
5. **Archivo ▸ Guardar** (`Ctrl+S`).
6. **Modelo ▸ Exportar**: Excel (`Ctrl+E`), PowerPoint (`Ctrl+Shift+E`) o Plan vs Simulación (`Ctrl+Shift+P`).

## Reglas de cálculo

| Indicador | Fórmula |
|---|---|
| Disponibilidad | (Productivo + Det. Proceso Prog. + Det. Proceso No Prog.) ÷ (Tiempo Calendario − Stand By) |
| Utilización | Productivo ÷ (Productivo + Det. Proceso Prog. + Det. Proceso No Prog.) |
| Tiempos del registro | Solo registros con carga. Promedio por registro (Σ minutos ÷ N° de registros); mínimo y máximo. |
| Carga por Camión | Mínimo, promedio y máximo de la columna «Carga (t)» por Flota de Pala y Tipo de Camión. |
| Productividad (palas y camiones) | Material Movido (Mt) × 1,000,000 ÷ Horas Productivas (h). |
| Material Movido por Pala (plan) | Material de la flota ÷ N° de palas × 365 ÷ días del periodo (Mtpa). |
| Indicadores combinados (Vector Plan) | Toneladas, taladros y conteos se suman; porcentajes y tiempos se promedian ponderados. |
| Fecha / Semana | 01/01/Año + parte entera de (horas ÷ 24) · Semana N = (día del año − 1) ÷ 7 + 1. |

## Atajos de teclado

| Atajo | Acción | Atajo | Acción |
|---|---|---|---|
| `Ctrl+N` · `Ctrl+O` | Nuevo · Abrir | `Ctrl+I` | Importar CSV |
| `Ctrl+S` · `Ctrl+Shift+S` | Guardar · Guardar como | `F5` | Ejecutar análisis |
| `Ctrl+E` · `Ctrl+Shift+E` | Exportar Excel · PowerPoint | `Ctrl+Shift+P` | Plan vs Simulación |
| `Ctrl+Shift+A` | Análisis de Estados (Pivot) | `Ctrl+Shift+R` | Registro de Cargas (Pivot) |
| `Ctrl+Shift+M` | Modo noche | `Ctrl+Tab` | Siguiente escenario |
| `Ctrl+W` · `F1` | Cerrar escenario · Acerca de | `Ctrl+C` | Copiar la selección de una tabla |

## Límites conocidos

- El ejecutable no está firmado: Windows puede pedir confirmación y analizarlo la primera vez (el primer arranque
  tarda más).
- Al maximizar o restaurar, Windows puede mostrar zonas sin pintar durante menos de un segundo mientras se ajusta
  el contenido.
- Los `.simx` de versiones anteriores se abren sin cambios; para ver Tiempos Ciclo y Carga por Camión hay que
  ejecutar el análisis (`F5`) una vez.
