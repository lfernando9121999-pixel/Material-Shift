# Material Shift v2.0

Modelo de reasignación de materiales: redistribuye el tonelaje semanal entre chancadoras y destinos donantes en dos circuitos independientes, **Desmonte** y **Mineral**. Es el sucesor del *Modelo de Reasignación de Materiales v19.5* (AjustePlan2034_Portable). El motor de cálculo es el mismo y da resultados idénticos.

**Cómo abrir:** doble clic en `Material Shift.exe`. No requiere instalación: Python, el motor y el visor van dentro de `Model\`. Necesita el componente WebView2 de Microsoft Edge, que viene incluido en Windows 11.

---

## Carpetas

| Carpeta / archivo | Contenido |
|---|---|
| `Material Shift.exe` | El programa. La carpeta completa puede copiarse a otra ubicación. |
| `Escenarios\` | Escenarios `.csv`. Incluye los Casos 1–4 de v19.5 y el **Caso 5 · Mineral completo** (2042 con Mineral configurado). |
| `Inputs\` | Planes base de ejemplo: `Ajuste Plan 2034.xlsx` y `Ajuste Plan 2042.xlsx`. |
| `Outputs\` | Excel de salida y los resultados de cada corrida (`<escenario> - Resultados.json` y `- Dashboard.html`). |
| `Model\` | Archivos internos: motor Python, páginas de la interfaz, WebView2, logo y preferencias. |
| `Desarrollo\` | Código fuente (`compilar.ps1` regenera el exe) y pruebas de verificación con sus capturas. |

---

## Flujo de trabajo

1. **Inputs:** elige el *Archivo base* y la *Hoja* (los marcados con \* son requeridos). Las chancadoras, donantes, fases y materiales se detectan solos. Con **Editar** defines qué columna es Receptor/Donante y de qué circuito (Desmonte/Mineral).
2. **Objetivos · Prioridad · Material:** cada pestaña tiene sus subpestañas **Desmonte | Mineral**. Cada circuito tiene su propio modo, granularidad (semanal/diario), objetivo y tolerancia.
3. **Calcular (`F5`):** calcula ambos circuitos (~2 s). El dashboard aparece a la derecha.
4. Revisa los resultados en **Dashboard · Tabla · Materiales**, y compara corridas en **Comparar Escenarios**.
5. **Excel (`Ctrl+E`):** genera y abre el *Plan Modificado* con el nombre exacto de *Archivo de salida*.
6. **Guardar (`Ctrl+S`):** guarda el escenario como `.csv` legible en Excel.

---

## Novedades respecto de v19.5

- **Nombre, logo y versión:** *Material Shift v2.0*, con logo nuevo (mismo estilo que SimA), **modo noche** y ventana que recuerda su tamaño y posición.
- **Inputs** (antes «Datos»), con «* Requerido» y la hoja elegida de una lista.
- **Criterios por circuito:** Desmonte y Mineral ya no comparten modo, semanal/diario ni objetivo diario.
- **Prioridad:** columnas *1. Donantes* y *2. Fases* que se ordenan **arrastrando** (o con `Alt+↑/↓`). Se agregan *Restablecer* y *Copiar a la otra chancadora*.
- **Dashboard:**
  - Indicadores *Destinos / Balance material / Tabla materiales* en **verde claro «✓ Ok»** o **rojo claro «! Revisar (n)»**.
  - Botones **Semanal | Diario** en cada gráfico, con el título que cambia según la vista.
  - Las leyendas dicen **«Plan»** y el **nombre del escenario** (antes «Base» y «Modificado»).
- **Comparar Escenarios:** elige A y B (corridas de la sesión o resultados guardados) y verás un gráfico A vs B, los totales por destino y por tipo de material, una tabla de indicadores con B − A y el detalle por semana o día.
- **Clic derecho** sobre gráficos: *Copiar datos*, *Copiar como imagen*, *Guardar imagen*, **Copiar como gráfico de PowerPoint (editable)** y *Exportar a PowerPoint*. Sobre tablas: *Copiar tabla*, *Copiar con formato* y *Copiar como imagen*.
- **Escenario `.csv` v3:** tabla de objetivos con columnas Desmonte y Mineral, y la matriz de materiales de Mineral. Los `.csv/.txt/.json` de v19 se siguen abriendo.
- **Aviso de escenario actualizado:** si el `.csv` abierto se modifica fuera del programa, en el pie aparece «Nuevo escenario disponible… ¿Desea actualizar?». Los resultados de la corrida se conservan.
- **Rapidez:** Calcular pasa de ~17 s a ~2 s, la detección de ~9 s a ~0.2 s y el Excel de ~16 s a ~6 s. El dashboard funciona sin internet.
- **Menú Exportar:** *Excel · Reporte completo* (validaciones de ambos circuitos), *PowerPoint · gráficos de la vista* y *Dashboard en el navegador* para compartir.

---

## Atajos de teclado

| Atajo | Acción | Atajo | Acción |
|---|---|---|---|
| `F5` | Calcular | `Ctrl+E` | Excel · Plan Modificado |
| `Ctrl+N` · `Ctrl+O` | Nuevo · Abrir escenario | `Ctrl+Shift+E` | PowerPoint · gráficos |
| `Ctrl+S` · `Ctrl+Shift+S` | Guardar · Guardar como | `Ctrl+Shift+C` | Comparar escenarios |
| `Ctrl+Tab` | Cambiar circuito | `Ctrl+Shift+M` | Modo noche |
| `Alt+↑/↓` | Mover fila (Prioridad) | `F1` | Guía rápida |

---

## Notas

- **Balance material «! Revisar (n)» en Mineral:** casi siempre falta marcar algún donante que sí tiene tonelaje en el Excel (en el 2042, `yan_bl_v`). No es un error de cálculo. Revisa *Inputs › Columnas detectadas › Editar*.
- **Escenarios de otra PC:** si la ruta del *Archivo base* no existe, el programa busca el mismo nombre junto al escenario y en `Inputs\`, y avisa en el pie.
- **Resultados para comparar:** cada corrida guarda `<escenario> - Resultados.json` en la carpeta de salida. Si recalculas el mismo escenario, el archivo se reemplaza; la sesión conserva en memoria las últimas 12 corridas.
- **Copiar como gráfico de PowerPoint** requiere PowerPoint instalado. Sin él, usa *Exportar a PowerPoint (.pptx)*.
- **Copiar tabla como imagen** copia la parte visible de la tabla. Para la tabla completa usa *Copiar con formato*.
- La primera vez que se abre un exe nuevo, Windows puede tardar unos segundos en analizarlo (no está firmado).
