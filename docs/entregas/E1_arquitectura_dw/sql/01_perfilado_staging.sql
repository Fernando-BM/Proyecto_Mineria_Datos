-- =====================================================================
-- E1 · Paso 3: perfilado de la capa staging (evidencia de que se
-- abrieron los datos). Cada consulta escanea solo las columnas que usa;
-- ninguna usa SELECT *. Costo total aproximado: < 200 MB escaneados.
-- Los valores esperados son los obtenidos el 2026-10-01 en el portal.
-- =====================================================================

-- F1 · Cobertura y tamaño del panel Metro.
-- Esperado: 2010-01-01 a 2026-07-31, 1,180,920 filas, 6,056 días.
SELECT
  MIN(fecha)             AS primera_fecha,
  MAX(fecha)             AS ultima_fecha,
  COUNT(*)               AS filas,
  COUNT(DISTINCT fecha)  AS dias
FROM metro_staging.stg_metro_afluencia;

-- F1 · Panel completo: debe haber exactamente 195 filas por día.
SELECT filas_por_dia, COUNT(*) AS dias
FROM (
  SELECT fecha, COUNT(*) AS filas_por_dia
  FROM metro_staging.stg_metro_afluencia
  GROUP BY fecha
)
GROUP BY filas_por_dia;

-- F1 · Problema de codificación: el texto de `linea` cambia de
-- "Linea 1" a "LÃ­nea 1" (UTF-8 leído como Latin-1) entre
-- 2021-01-01 y 2023-05-31. Esperado: 24 valores distintos para 12 líneas.
SELECT linea, MIN(fecha) AS desde, MAX(fecha) AS hasta, COUNT(*) AS filas
FROM metro_staging.stg_metro_afluencia
GROUP BY linea
ORDER BY linea;

-- F1 · Ceros estructurales por línea y año (cierres e inauguraciones).
-- Esperado: 62,025 ceros en total, concentrados en L12 y L1.
SELECT
  REGEXP_EXTRACT(linea, r'(\w+)$') AS linea_codigo,
  anio,
  COUNTIF(afluencia = '0')         AS registros_cero
FROM metro_staging.stg_metro_afluencia
GROUP BY linea_codigo, anio
HAVING registros_cero > 0
ORDER BY registros_cero DESC
LIMIT 25;

-- F2 · Metrobús: grano línea-día y valores 'NaN' antes de inaugurar.
-- Esperado: 53,732 filas, 2005-07-26 a 2026-07-31, 17,227 'NaN'.
SELECT
  MIN(fecha)                  AS primera_fecha,
  MAX(fecha)                  AS ultima_fecha,
  COUNT(*)                    AS filas,
  COUNT(DISTINCT linea)       AS valores_linea,
  COUNTIF(afluencia = 'NaN')  AS registros_nan
FROM metro_staging.stg_metrobus_afluencia;

-- F3 · GTFS: el Metro (agencia 02) tiene 195 paradas, una por
-- estación-línea, igual que las 195 filas diarias de F1.
SELECT
  COUNTIF(STARTS_WITH(stop_id, 'B_02')) AS paradas_metro,
  COUNT(*)                              AS paradas_totales
FROM metro_staging.stg_gtfs_stops;

-- F4 · Festivos: tipos de día y festivos desplazados que no
-- corresponden al art. 74 de la LFT (p. ej. Día del Trabajo en 2016-05-02).
SELECT date, localName, ARRAY_TO_STRING(types, '|') AS tipos
FROM metro_staging.stg_festivos_nager
WHERE localName IN ('Día del Trabajo', 'Año Nuevo')
ORDER BY date;

-- F5 · Clima: un registro por día, sin huecos. Esperado: 6,056 días.
SELECT MIN(time) AS desde, MAX(time) AS hasta, COUNT(*) AS dias
FROM metro_staging.stg_clima_openmeteo;
