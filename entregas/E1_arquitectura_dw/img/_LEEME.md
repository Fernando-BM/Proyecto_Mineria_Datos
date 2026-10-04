# Capturas de pantalla de E1

Las páginas del sitio ya hacen referencia a estos archivos. Guarden cada captura en esta carpeta con **exactamente** este nombre, en PNG o JPEG (si cambian la extensión, actualicen la referencia en la página):

| Archivo | Qué muestra | Página |
|---------|-------------|--------|
| `F1_portal.jpeg`, `F2_portal.jpeg`, `F3_portal.jpeg` | Página del conjunto en datos.cdmx.gob.mx | fuentes |
| `F4_api.jpeg`, `F5_api.jpeg` | Respuesta de la API abierta en el navegador | fuentes |
| `BQ_creacion_datasets.png` | Resultado de `00_datasets.sql` (3 sentencias, SUCCESS) | arquitectura |
| `BQ_metro_staging.png`, `BQ_datasets.png`, `BQ_metro_mart.png` | Pestaña Details de cada dataset (staging, dw, mart) con Data location: US | arquitectura |
| `STG_esquema_*.png` y `STG_preview_*.png` (metro, metrobus, gtfs_stops, gtfs_routes, festivos, clima) | Esquema y vista previa de cada tabla de staging; las vistas previas también se usan en fuentes | arquitectura, fuentes |
| `STG_carga_metro.png` | Consulta a `INFORMATION_SCHEMA.JOBS_BY_USER` con los 6 trabajos de carga | arquitectura |
| `STG_perfilado.png` | Editor con la consulta de "195 filas por día" y su resultado | arquitectura, fuentes |
| `PERF_resumen.png` y `PERF_f1_cobertura`, `PERF_f1_lineas_codificacion`, `PERF_f1_ceros`, `PERF_f2_metrobus`, `PERF_f3_gtfs`, `PERF_f4_festivos`, `PERF_f5_clima` (.png) | Resultados de `01_perfilado_staging.sql` | fuentes |
| `DW_ddl_ejecucion.png` | Resultado de `ddl_dw.sql` (6 sentencias, SUCCESS) | estrella |
| `DW_*.png` (6 tablas) | Pestaña Esquema de cada tabla del DW | estrella |
| `MART_vistas.png`, `MART_validacion.png` | Vistas del mart y una consulta validada | arquitectura |

Antes de guardar, revisen que no aparezcan correos, IDs de facturación, llaves ni tokens.
