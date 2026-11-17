-- =====================================================================
-- Resultados del DataMart que se publican en el sitio (E2).
-- Cada bloque empieza con "-- @nombre" y el pipeline guarda su resultado
-- en entregas/E2_eda_preparacion/tablas/mart_<nombre>.md (y .csv).
-- Todas leen vistas de metro_mart; ninguna usa SELECT * sobre tablas.
-- =====================================================================

-- @p1_rollup_linea_dia
-- ROLLUP: media diaria por línea y día (2022 en adelante); la fila
-- "TOTAL RED" es el total que agrega ROLLUP.
SELECT
  IFNULL(nombre_linea, 'TOTAL RED') AS linea,
  ROUND(MAX(IF(dia_semana_num = 1, afluencia_media_diaria, NULL))) AS lun,
  ROUND(MAX(IF(dia_semana_num = 2, afluencia_media_diaria, NULL))) AS mar,
  ROUND(MAX(IF(dia_semana_num = 3, afluencia_media_diaria, NULL))) AS mie,
  ROUND(MAX(IF(dia_semana_num = 4, afluencia_media_diaria, NULL))) AS jue,
  ROUND(MAX(IF(dia_semana_num = 5, afluencia_media_diaria, NULL))) AS vie,
  ROUND(MAX(IF(dia_semana_num = 6, afluencia_media_diaria, NULL))) AS sab,
  ROUND(MAX(IF(dia_semana_num = 7, afluencia_media_diaria, NULL))) AS dom,
  ROUND(MAX(IF(dia_semana_num IS NULL, afluencia_media_diaria, NULL))) AS todos_los_dias
FROM metro_mart.v_p1_rollup_linea_dia
GROUP BY nombre_linea
ORDER BY todos_los_dias DESC;

-- @p1_picos_vs_base
-- Ventanas: las 5 estaciones con más entradas en cada día de la semana.
SELECT nombre_dia, rank_en_el_dia, nombre_linea, nombre_oficial,
       ROUND(media_dia) AS media_dia, ROUND(indice_vs_base, 3) AS indice_vs_base
FROM metro_mart.v_p1_picos_vs_base
WHERE rank_en_el_dia <= 5
ORDER BY dia_semana_num, rank_en_el_dia, nombre_oficial;

-- @p2_resumen_por_anio
-- Ventanas: tamaño del conjunto de pronóstico, proporción de días de alta
-- demanda y error de la línea base ingenua (lo que el modelo debe mejorar).
-- WAPE = suma de errores absolutos / suma de entradas (no se dispara cuando
-- un día tiene muy pocas entradas, a diferencia del promedio del error relativo).
-- La mediana es exacta (PERCENTILE_CONT) para que el resultado no varíe entre corridas.
SELECT
  anio,
  COUNT(*)                                                       AS estacion_dias,
  ROUND(AVG(CAST(es_alta_demanda AS INT64)), 4)                  AS proporcion_alta_demanda,
  ROUND(SAFE_DIVIDE(SUM(ABS(afluencia - base_ingenua_4sem)), SUM(afluencia)), 4) AS wape_base_ingenua,
  ROUND(ANY_VALUE(mediana_error), 4)                             AS error_mediano_base_ingenua
FROM (
  SELECT
    EXTRACT(YEAR FROM fecha) AS anio,
    es_alta_demanda,
    afluencia,
    base_ingenua_4sem,
    PERCENTILE_CONT(error_abs_pct_base, 0.5) OVER (PARTITION BY EXTRACT(YEAR FROM fecha)) AS mediana_error
  FROM metro_mart.v_p2_dataset_pronostico
  WHERE fecha >= DATE '2022-01-01'
    AND base_ingenua_4sem IS NOT NULL
    AND afluencia > 0
)
GROUP BY anio
ORDER BY anio;

-- @p3_perfil_por_linea
-- PIVOT: participación media de cada día de la semana por línea.
SELECT
  linea_codigo,
  COUNT(*)                AS estaciones,
  ROUND(AVG(lun), 4) AS lun, ROUND(AVG(mar), 4) AS mar, ROUND(AVG(mie), 4) AS mie,
  ROUND(AVG(jue), 4) AS jue, ROUND(AVG(vie), 4) AS vie, ROUND(AVG(sab), 4) AS sab,
  ROUND(AVG(dom), 4) AS dom
FROM metro_mart.v_p3_perfil_semanal_estacion
GROUP BY linea_codigo
ORDER BY dom DESC, linea_codigo;

-- @p3_acoplamiento_por_linea
-- Ventanas: para cada línea del Metro, la línea de Metrobús más acoplada
-- (comparte sus choques inesperados) y la menos acoplada (mejor candidata a
-- alternativa), con la correlación sin ciclo semanal; se muestra también el
-- rango de la correlación de niveles para ver por qué esa no sirve.
WITH r AS (
  SELECT
    linea_metro, linea_metrobus, correlacion_bruta, correlacion_sin_ciclo, dias_en_comun,
    ROW_NUMBER() OVER (PARTITION BY linea_metro ORDER BY correlacion_sin_ciclo DESC, linea_metrobus) AS orden_mas,
    ROW_NUMBER() OVER (PARTITION BY linea_metro ORDER BY correlacion_sin_ciclo ASC, linea_metrobus)  AS orden_menos
  FROM metro_mart.v_p3_correlacion_metro_metrobus
)
SELECT
  linea_metro,
  MAX(dias_en_comun)                                              AS dias,
  ROUND(MIN(correlacion_bruta), 3)                                AS bruta_min,
  ROUND(MAX(correlacion_bruta), 3)                                AS bruta_max,
  MAX(IF(orden_mas = 1, linea_metrobus, NULL))                    AS metrobus_mas_acoplada,
  ROUND(MAX(IF(orden_mas = 1, correlacion_sin_ciclo, NULL)), 3)   AS sin_ciclo_max,
  MAX(IF(orden_menos = 1, linea_metrobus, NULL))                  AS metrobus_menos_acoplada,
  ROUND(MAX(IF(orden_menos = 1, correlacion_sin_ciclo, NULL)), 3) AS sin_ciclo_min
FROM r
GROUP BY linea_metro
ORDER BY linea_metro;

-- @p4_anomalias_por_causa
-- GROUPING SETS: anomalías por causa probable y proporción del total.
SELECT
  IFNULL(causa_probable, 'TOTAL') AS causa_probable,
  estacion_dias_anomalos, anomalias_altas, anomalias_bajas,
  ROUND(SAFE_DIVIDE(estacion_dias_anomalos,
        SUM(IF(causa_probable IS NULL AND evento_masivo IS NULL AND categoria_lluvia IS NULL,
               estacion_dias_anomalos, 0)) OVER ()), 4) AS proporcion
FROM metro_mart.v_p4_anomalias_por_causa
WHERE evento_masivo IS NULL AND categoria_lluvia IS NULL
ORDER BY estacion_dias_anomalos DESC, causa_probable;

-- @p4_anomalias_por_evento
SELECT evento_masivo, estacion_dias_anomalos, anomalias_altas, anomalias_bajas
FROM metro_mart.v_p4_anomalias_por_causa
WHERE evento_masivo IS NOT NULL
ORDER BY estacion_dias_anomalos DESC, evento_masivo;

-- @p5_absorcion_cierre_l1
-- CUBE: media diaria por sistema y periodo, y por línea de Metrobús y periodo.
SELECT
  IFNULL(sistema, 'TODOS')      AS sistema,
  IFNULL(nombre_linea, 'TODAS') AS linea,
  periodo,
  ROUND(afluencia_media_diaria) AS afluencia_media_diaria,
  linea_dias
FROM metro_mart.v_p5_absorcion_cierre_l1
WHERE periodo IS NOT NULL
  AND (nombre_linea IS NULL OR sistema = 'Metrobús'
       OR nombre_linea IN ('Metro Línea 1', 'Metro Línea 2', 'Metro Línea 12'))
  AND NOT (sistema IS NULL AND nombre_linea IS NOT NULL)
ORDER BY sistema, linea, periodo;

-- @p5_diferencia_vs_control
-- Ventanas (LAG): cambio de cada línea respecto del periodo previo y su
-- diferencia contra las 10 líneas del Metro que siguieron abiertas.
SELECT
  grupo,
  periodo,
  ROUND(afluencia_media_diaria)        AS afluencia_media_diaria,
  dias,
  ROUND(cambio_vs_periodo_previo, 3)   AS cambio_vs_periodo_previo,
  ROUND(diferencia_vs_control, 3)      AS diferencia_vs_control
FROM metro_mart.v_p5_diferencia_vs_control
ORDER BY grupo, periodo;
