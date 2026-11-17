-- =====================================================================
-- Evidencia de consistencia del DW poblado (E2). El pipeline la ejecuta
-- después de la carga y compara cada valor con lo esperado; también se
-- puede correr a mano en la consola de BigQuery para la captura.
-- Columnas: prueba · valor · esperado (0 = no debe haber casos;
-- NULL = conteo informativo que el pipeline compara con sus propios datos).
-- =====================================================================
SELECT prueba, valor, esperado FROM (
  -- Conteo de filas por tabla
  SELECT '01 filas dim_fecha' AS prueba, COUNT(*) AS valor, CAST(NULL AS INT64) AS esperado FROM metro_dw.dim_fecha
  UNION ALL SELECT '02 filas dim_linea', COUNT(*), NULL FROM metro_dw.dim_linea
  UNION ALL SELECT '03 filas dim_estacion', COUNT(*), NULL FROM metro_dw.dim_estacion
  UNION ALL SELECT '04 filas dim_clima', COUNT(*), NULL FROM metro_dw.dim_clima
  UNION ALL SELECT '05 filas hechos_afluencia_metro', COUNT(*), NULL FROM metro_dw.hechos_afluencia_metro
  UNION ALL SELECT '06 filas hechos_afluencia_metrobus', COUNT(*), NULL FROM metro_dw.hechos_afluencia_metrobus

  -- Unicidad del grano: filas menos combinaciones distintas de llaves
  UNION ALL
  SELECT '07 grano metro (fecha_key, estacion_key): filas repetidas',
         COUNT(*) - COUNT(DISTINCT CONCAT(CAST(fecha_key AS STRING), '-', CAST(estacion_key AS STRING))), 0
  FROM metro_dw.hechos_afluencia_metro
  UNION ALL
  SELECT '08 grano metro (fecha, estación-línea natural): filas repetidas',
         COUNT(*) - COUNT(DISTINCT CONCAT(CAST(h.fecha_key AS STRING), '-', e.estacion_nk)), 0
  FROM metro_dw.hechos_afluencia_metro AS h
  JOIN metro_dw.dim_estacion AS e ON e.estacion_key = h.estacion_key
  UNION ALL
  SELECT '09 grano metrobús (fecha_key, linea_key): filas repetidas',
         COUNT(*) - COUNT(DISTINCT CONCAT(CAST(fecha_key AS STRING), '-', CAST(linea_key AS STRING))), 0
  FROM metro_dw.hechos_afluencia_metrobus

  -- Llaves nulas en los hechos
  UNION ALL
  SELECT '10 metro: llaves nulas',
         COUNTIF(fecha_key IS NULL OR estacion_key IS NULL OR linea_key IS NULL), 0
  FROM metro_dw.hechos_afluencia_metro

  -- Llaves huérfanas (LEFT JOIN sin pareja en la dimensión)
  UNION ALL
  SELECT '11 metro: fecha_key huérfanas', COUNTIF(d.fecha_key IS NULL), 0
  FROM metro_dw.hechos_afluencia_metro AS h
  LEFT JOIN metro_dw.dim_fecha AS d ON d.fecha_key = h.fecha_key
  UNION ALL
  SELECT '12 metro: estacion_key huérfanas', COUNTIF(d.estacion_key IS NULL), 0
  FROM metro_dw.hechos_afluencia_metro AS h
  LEFT JOIN metro_dw.dim_estacion AS d ON d.estacion_key = h.estacion_key
  UNION ALL
  SELECT '13 metro: linea_key huérfanas', COUNTIF(d.linea_key IS NULL), 0
  FROM metro_dw.hechos_afluencia_metro AS h
  LEFT JOIN metro_dw.dim_linea AS d ON d.linea_key = h.linea_key
  UNION ALL
  SELECT '14 metro: clima_key huérfanas', COUNTIF(h.clima_key IS NOT NULL AND d.clima_key IS NULL), 0
  FROM metro_dw.hechos_afluencia_metro AS h
  LEFT JOIN metro_dw.dim_clima AS d ON d.clima_key = h.clima_key
  UNION ALL
  SELECT '15 metrobús: fecha_key huérfanas', COUNTIF(d.fecha_key IS NULL), 0
  FROM metro_dw.hechos_afluencia_metrobus AS h
  LEFT JOIN metro_dw.dim_fecha AS d ON d.fecha_key = h.fecha_key
  UNION ALL
  SELECT '16 metrobús: linea_key huérfanas', COUNTIF(d.linea_key IS NULL), 0
  FROM metro_dw.hechos_afluencia_metrobus AS h
  LEFT JOIN metro_dw.dim_linea AS d ON d.linea_key = h.linea_key

  -- SCD tipo 2: cada hecho cae dentro de la vigencia de su versión
  UNION ALL
  SELECT '17 metro: hechos fuera de la vigencia de su versión',
         COUNTIF(f.fecha < e.fecha_inicio_vigencia OR f.fecha > e.fecha_fin_vigencia), 0
  FROM metro_dw.hechos_afluencia_metro AS h
  JOIN metro_dw.dim_estacion AS e ON e.estacion_key = h.estacion_key
  JOIN metro_dw.dim_fecha AS f ON f.fecha_key = h.fecha_key
  UNION ALL
  SELECT '18 dim_estacion: estaciones sin exactamente una versión vigente', COUNT(*), 0
  FROM (SELECT estacion_nk FROM metro_dw.dim_estacion GROUP BY estacion_nk
        HAVING COUNTIF(es_version_vigente) <> 1)

  -- Rangos válidos
  UNION ALL
  SELECT '19 metro: afluencia negativa', COUNTIF(afluencia < 0), 0 FROM metro_dw.hechos_afluencia_metro
  UNION ALL
  SELECT '20 metrobús: afluencia negativa', COUNTIF(afluencia < 0), 0 FROM metro_dw.hechos_afluencia_metrobus
)
ORDER BY prueba;
