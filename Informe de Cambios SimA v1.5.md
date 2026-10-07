# Informe de Cambios – SimA v1.5

**Programa:** `SimA - Simulation Analyst.exe` (carpeta principal) · **Versión:** 1.5.0 · **Fecha:** 07/10/2026

El ejecutable reemplaza al de v1.4. Se conservan preferencias, escenarios, inputs y outputs.

---

## 1. Cambios Implementados

| Área | Cambio |
|---|---|
| **General** | Nuevo nombre con «v1.5» a la derecha. Modo claro en grises suaves y separadores tenues entre pestañas. Sin parpadeos al actualizar: solo se reconstruye la pestaña visible. |
| **Ventanas** | Explorador de archivos a tamaño medio, centrado sobre el programa, movible y redimensionable. Cada escenario puede llevarse a otra ventana o pantalla (arrastrando su pestaña o con clic derecho). |
| **Emergentes y Filtros** | No bloquean el programa, una sola abierta a la vez y se cierran al cambiar de pestaña. Filtros estilo Excel. |
| **Tablas y Gráficos** | Columnas reordenables arrastrando. Clic derecho: copiar como texto, con formato, como imagen o como gráfico de PPT. |
| **Archivo** | «Abrir Existente» con escenarios recientes; diálogos más compactos. |
| **Inputs** | Configuración de Equipos con Orden de Reporte; «Fuente de Energía» pasa a Categoría; Vector Plan con edición directa e indicadores combinables. |
| **Resultados** | Resumen / Detallado en Análisis de Estados; Tiempos Ciclo y Métricas; Plan de Mina con tabla agrupable y subtotales; Plan vs Simulación con Reporte y Gráfico. |
| **Tablas Dinámicas** | Estilo DevExpress con campos calculados tipo fórmula de Excel. |
| **Reportes** | Excel con todas las pestañas y subpestañas sin filtros; cada hoja indica «Caso [escenario]» y la Fecha de Corrida. PowerPoint con una lámina por pestaña, tablas resumidas (nunca partidas) y gráficos editables. |

## 2. Problemas Encontrados y Corregidos

| Problema | Solución |
|---|---|
| Abrir un escenario lo marcaba como modificado y pedía guardar al cerrar. | La tabla dinámica se construye solo al mostrarse y su primer guardado no marca cambios. |
| Zonas negras al maximizar o acoplar. | Redibujo diferido al cambiar de tamaño; ahora se pintan en menos de 1 s. |
| Tarjetas de indicadores cortadas a media pantalla. | Se reacomodan en dos filas; la última ocupa el ancho restante. |
| El diálogo de archivos aparecía en otra posición y luego saltaba. | Permanece invisible hasta quedar centrado. |
| La tabla dinámica no cambiaba de colores en modo noche. | Se reconstruye al cambiar de tema. |
| La barra de progreso del Registro de Cargas no avanzaba. | Lectura por bloques de 100,000 filas con avance desde el inicio. |
| Las etiquetas de gráficos en Excel ignoraban su formato. | Formato de etiqueta fijado en cada gráfico. |
| Reporte Excel lento (13 s). | Estilos compartidos: ahora tarda unos 5 s. |

## 3. Verificación

| Prueba | Resultado |
|---|---|
| Cálculos vs *Resultados Ejemplo.xlsx* (MODS4) | Idénticos a v1.4: 38 ítems exactos. Hang a 2 decimales. Ítem 9.x con la diferencia ya documentada (configuración no estándar en el libro de referencia). |
| Prueba automática de interfaz | 26/26 sin errores; 27 vistas en modo claro y oscuro. |
| Tiempos de apertura | 0.1 – 0.6 s por vista; Registro de Cargas (CSV de 183 MB) unos 6 s. |
| Escritorio (Windows-MCP) | Correcto: mover a otra pantalla; acoplar a media pantalla y cuadrante; maximizar, minimizar y restaurar; filtros en la misma pantalla y movibles; desacoplar escenario; modo noche en ambas ventanas; exportar a Excel y abrir sin reparación. |
| Autotest del ejecutable | Calcular, guardar y exportar: correcto. |
| Reportes Excel / PowerPoint | Correctos en 5 escenarios. |

## 4. Interpretaciones

| Indicación | Interpretación |
|---|---|
| «Añadir un filtro de» (frase incompleta) | Filtro por **Tipo de Origen**. |
| «Clase» en la priorización | **Categoría**. |
| Filtros por defecto | La Réplica nunca se usa como filtro por defecto. |
| «Vincular Filtros» | Retirado de las pestañas; queda como opción en el menú Modelo. |

## 5. Pendientes y Límites Conocidos

- El Manual de Usuario sigue en v1.4.
- El primer arranque de cada ejecutable nuevo tarda unos 20 s mientras Windows lo analiza.
- Al maximizar o restaurar puede verse una zona sin pintar durante menos de 1 s.
- Los `.simx` anteriores requieren ejecutar el análisis (`F5`) una vez para ver Tiempos Ciclo y Carga por Camión.

## 6. Documentación Relacionada

- `Leame.md` (carpeta principal): novedades, flujo de trabajo, reglas de cálculo y atajos.
- `Desarrollo\Verificacion\Verificacion de Calculos.md`: detalle de la verificación.
- `Desarrollo\Verificacion\Resultados de Referencia\`: escenario, reportes y resultados de referencia v1.5.
