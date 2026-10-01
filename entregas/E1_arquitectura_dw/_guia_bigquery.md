# Guía para ejecutar E1 en BigQuery (uso interno del equipo)

Este archivo empieza con `_`, así que Quarto no lo publica en el sitio. Sigan los pasos en orden.
Cada captura va en `img/` con **exactamente** el nombre indicado, porque las páginas ya las referencian.

> ⚠️ Antes de cada captura, revisen que no se vean correos, IDs de facturación, llaves ni tokens.
> Nunca suban archivos `.json` de cuentas de servicio.

---

## 0. Descargar las fuentes (en su computadora)

| Fuente | Cómo obtenerla | Archivo |
|--------|----------------|---------|
| F1 | <https://datos.cdmx.gob.mx/dataset/afluencia-diaria-del-metro-cdmx> → *Afluencia Diaria del Metro (Simple)* → Descargar | CSV de 59.9 MB |
| F2 | <https://datos.cdmx.gob.mx/dataset/afluencia-diaria-de-metrobus-cdmx> → *Afluencia Diaria del Metrobús (Simple)* → Descargar | CSV de 2.1 MB |
| F3 | <https://datos.cdmx.gob.mx/dataset/gtfs> → Descargar ZIP → descomprimir | `stops.txt`, `routes.txt` |
| F4 y F5 | `cd entregas/E1_arquitectura_dw/staging && python3 descargar_apis.py` | `festivos_…jsonl`, `clima_…csv` |

📸 Mientras descargan, tomen las capturas de la página de origen:
`F1_portal.png`, `F2_portal.png`, `F3_portal.png`, y abran en el navegador
<https://date.nager.at/api/v3/PublicHolidays/2025/MX> → `F4_api.png` y
<https://archive-api.open-meteo.com/v1/archive?latitude=19.4326&longitude=-99.1332&start_date=2025-06-01&end_date=2025-06-07&daily=precipitation_sum,temperature_2m_max&timezone=America%2FMexico_City> → `F5_api.png`.

## 1. Crear los datasets

En la consola de BigQuery, con el proyecto del curso seleccionado, peguen y ejecuten `sql/00_datasets.sql`.

📸 `BQ_datasets.png`: el explorador con `metro_staging`, `metro_dw` y `metro_mart`, y el panel de detalles de uno de ellos mostrando **Ubicación de datos: US**.

## 2. Cargar staging

Para cada tabla: clic en `metro_staging` → **Crear tabla** → Origen: **Subir**. Usen **Editar como texto** en el esquema y peguen el que se indica. En *Opciones avanzadas*, pongan las filas de encabezado a omitir.

| Tabla | Archivo | Formato | Filas a omitir | Esquema (Editar como texto) |
|-------|---------|---------|----------------|------------------------------|
| `stg_metro_afluencia` | CSV de F1 | CSV | 1 | `fecha:STRING,anio:STRING,mes:STRING,linea:STRING,estacion:STRING,afluencia:STRING` |
| `stg_metrobus_afluencia` | CSV de F2 | CSV | 1 | `fecha:STRING,anio:STRING,mes:STRING,linea:STRING,afluencia:STRING` |
| `stg_gtfs_stops` | `stops.txt` | CSV | 1 | `stop_id:STRING,stop_name:STRING,stop_lat:STRING,stop_lon:STRING,zone_id:STRING,wheelchair_boarding:STRING` |
| `stg_gtfs_routes` | `routes.txt` | CSV | 1 | `route_id:STRING,agency_id:STRING,route_short_name:STRING,route_long_name:STRING,route_type:STRING,route_color:STRING,route_text_color:STRING` |
| `stg_festivos_nager` | `festivos_mx_nager_2010_2026.jsonl` | JSONL | — | **Detectar automáticamente** |
| `stg_clima_openmeteo` | `clima_cdmx_openmeteo_2010_2026.csv` | CSV | **4** | `time:STRING,precipitation_sum_mm:STRING,rain_sum_mm:STRING,temperature_2m_max_c:STRING,temperature_2m_min_c:STRING` |

**Antes de cargar**, revisen que el encabezado de cada CSV tenga las columnas en ese orden: abran el archivo y lean la primera línea. Si el orden es otro, ajusten el esquema; no reordenen el archivo.
Si la carga de F1 marca un error de codificación, en *Opciones avanzadas* pongan **Codificación: UTF-8**. **No** corrijan el texto mal codificado: en staging se conserva.

📸 Por cada tabla: la vista previa (`STG_preview_metro.png`, `STG_preview_metrobus.png`, `STG_preview_gtfs.png`, `STG_preview_festivos.png`, `STG_preview_clima.png`).
📸 De F1 además: `STG_carga_metro.png` (Historial de trabajos → el trabajo de carga) y `STG_esquema_metro.png` (pestaña Esquema).
📸 Las capturas `F1_vista_previa.png` … `F5_vista_previa.png` pueden ser las mismas vistas previas de staging.

Anoten la **fecha de carga** y las filas de `stg_gtfs_routes` en la tabla de `arquitectura.qmd`.

## 3. Perfilar staging

Ejecuten `sql/01_perfilado_staging.sql` consulta por consulta y comparen contra los valores esperados de cada comentario.

📸 `STG_perfilado.png`: el resultado de la consulta de "195 filas por día".

## 4. Crear el DW

Peguen y ejecuten `sql/ddl_dw.sql` completo (crea las dimensiones antes que los hechos).

📸 Pestaña **Esquema** de cada tabla: `DW_dim_fecha.png`, `DW_dim_linea.png`, `DW_dim_estacion.png`, `DW_dim_clima.png`, `DW_hechos_afluencia_metro.png`, `DW_hechos_afluencia_metrobus.png`.

## 5. Crear el DataMart

Peguen y ejecuten `sql/consultas_mart.sql` completo.

📸 `MART_vistas.png`: `metro_mart` desplegado con las 7 vistas.
📸 `MART_validacion.png`: abran cualquier vista (p. ej. `v_p5_absorcion_cierre_l1`), pongan su SQL en el editor y capturen la marca verde de "Esta consulta procesará 0 B".

## 6. Completar y publicar

1. Busquen `.todo` en `arquitectura.qmd` y `uso_ia.qmd` y llénenlo con lo que hicieron.
2. `quarto preview` para revisar que todo se vea bien, incluidas las imágenes.
3. Commit y push a `dev`; el workflow publica el sitio.

## Si alguien les pregunta en la verificación oral

- **¿Por qué ese grano?** Porque F1 publica exactamente 195 filas por día, una por estación-línea, y eso coincide con el objetivo de E0 de pronosticar el día siguiente por estación. La hora no existe en ninguna fuente.
- **¿Por qué dos hechos?** Metrobús solo publica por línea. Si se mezcla todo, el grano baja a línea-día y se pierden P1–P4.
- **¿Por qué SCD 2 en estaciones?** Porque los cierres por periodo (L12 desde 2021, L1 2022–2025) cambian el estado de servicio y P2, P4 y P5 necesitan saber qué estado tenía cada estación en cada fecha.
- **¿Qué dimensión responde P4?** `dim_clima` (lluvia), `dim_fecha` (festivos) y `dim_estacion` (cierres).
- **¿Qué problema de integración encontraron?** Texto mal codificado (`LÃ­nea 1`) en 2021–2023, 8 estaciones con nombre distinto entre afluencia y GTFS, y festivos de Nager.Date desplazados respecto a la Ley Federal del Trabajo.
