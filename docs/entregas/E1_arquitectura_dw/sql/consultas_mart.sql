-- =====================================================================
-- E1 · Paso 5: DataMart (metro_mart). Una vista por pregunta de E0,
-- construidas sobre el esquema estrella de metro_dw.
-- Las tablas del DW están vacías en E1: las vistas devuelven 0 filas,
-- pero deben crearse sin error (validez sintáctica y semántica).
-- Operadores OLAP usados: ROLLUP (P1), funciones de ventana (P1, P2, P4),
-- PIVOT (P3), GROUPING SETS (P4) y CUBE (P5).
-- =====================================================================


-- ---------------------------------------------------------------------
-- P1 · ¿Qué combinaciones de línea, estación y día de la semana concentran
--      los picos de afluencia y qué tan lejos están de su nivel base?
-- (a) ROLLUP: afluencia media diaria por línea y día de la semana,
--     con subtotales por línea y total de la red.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW metro_mart.v_p1_rollup_linea_dia AS
-- Las filas con nombre_linea NULL son el total de la red; las filas con
-- dia_semana_num NULL son el subtotal de cada línea.
SELECT
  l.nombre_linea,
  f.dia_semana_num,
  SUM(h.afluencia)                          AS afluencia_total,
  COUNT(DISTINCT h.fecha_key)               AS dias_observados,
  SAFE_DIVIDE(SUM(h.afluencia),
              COUNT(DISTINCT h.fecha_key))  AS afluencia_media_diaria
FROM metro_dw.hechos_afluencia_metro AS h
JOIN metro_dw.dim_linea  AS l ON l.linea_key = h.linea_key
JOIN metro_dw.dim_fecha  AS f ON f.fecha_key = h.fecha_key
WHERE f.anio >= 2022
  AND NOT h.es_registro_cero
GROUP BY ROLLUP (l.nombre_linea, f.dia_semana_num);

-- (b) Ventanas: índice de cada estación-día contra su propia base
--     (media de la estación en todos los días) y ranking por día.
CREATE OR REPLACE VIEW metro_mart.v_p1_picos_vs_base AS
WITH media_por_dia AS (
  SELECT
    l.nombre_linea,
    e.estacion_nk,
    e.nombre_oficial,
    f.dia_semana_num,
    f.nombre_dia,
    AVG(h.afluencia) AS media_dia
  FROM metro_dw.hechos_afluencia_metro AS h
  JOIN metro_dw.dim_estacion AS e ON e.estacion_key = h.estacion_key
  JOIN metro_dw.dim_linea    AS l ON l.linea_key    = h.linea_key
  JOIN metro_dw.dim_fecha    AS f ON f.fecha_key    = h.fecha_key
  WHERE f.anio >= 2022
    AND NOT h.es_registro_cero
  GROUP BY l.nombre_linea, e.estacion_nk, e.nombre_oficial, f.dia_semana_num, f.nombre_dia
),
con_indices AS (
  SELECT
    *,
    SAFE_DIVIDE(media_dia,
                AVG(media_dia) OVER (PARTITION BY estacion_nk))           AS indice_vs_base,
    RANK() OVER (PARTITION BY dia_semana_num ORDER BY media_dia DESC)     AS rank_en_el_dia
  FROM media_por_dia
)
SELECT *
FROM con_indices
WHERE rank_en_el_dia <= 20;


-- ---------------------------------------------------------------------
-- P2 · ¿Es posible anticipar con 24 h la afluencia diaria por estación y
--      clasificar los días de alta demanda?
-- Conjunto de entrenamiento: rezagos (ventanas LAG), línea base ingenua
-- (media del mismo día de la semana en las 4 semanas previas, requerida
-- por el criterio de éxito de E0) y etiqueta de alta demanda.
-- Umbral provisional 1.20 x base: se fija con el resultado de P1 en E2.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW metro_mart.v_p2_dataset_pronostico AS
WITH serie AS (
  SELECT
    h.estacion_key,
    e.estacion_nk,
    f.fecha,
    f.dia_semana_num,
    f.es_festivo_oficial,
    f.es_dia_quincena,
    f.es_semana_santa,
    c.precipitacion_mm,
    e.estado_servicio,
    h.afluencia
  FROM metro_dw.hechos_afluencia_metro AS h
  JOIN metro_dw.dim_estacion AS e ON e.estacion_key = h.estacion_key
  JOIN metro_dw.dim_fecha    AS f ON f.fecha_key    = h.fecha_key
  LEFT JOIN metro_dw.dim_clima AS c ON c.clima_key  = h.clima_key
),
con_rezagos AS (
  SELECT
    *,
    LAG(afluencia, 1) OVER (PARTITION BY estacion_nk ORDER BY fecha)     AS afluencia_t_menos_1,
    LAG(afluencia, 7) OVER (PARTITION BY estacion_nk ORDER BY fecha)     AS afluencia_t_menos_7,
    AVG(afluencia) OVER (
      PARTITION BY estacion_nk, dia_semana_num
      ORDER BY fecha
      ROWS BETWEEN 4 PRECEDING AND 1 PRECEDING
    )                                                                     AS base_ingenua_4sem
  FROM serie
)
SELECT
  *,
  SAFE_DIVIDE(ABS(afluencia - base_ingenua_4sem), afluencia)              AS error_abs_pct_base,
  afluencia > 1.20 * base_ingenua_4sem                                    AS es_alta_demanda
FROM con_rezagos
WHERE estado_servicio = 'operando';


-- ---------------------------------------------------------------------
-- P3 · ¿Cuántos perfiles de demanda hay y qué alternativas existen?
-- (a) PIVOT: perfil semanal de cada estación (participación de cada día
--     de la semana en su demanda); es la matriz de entrada del clustering.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW metro_mart.v_p3_perfil_semanal_estacion AS
WITH media AS (
  SELECT
    e.estacion_nk,
    e.linea_codigo,
    f.dia_semana_num,
    AVG(h.afluencia) AS media_dia
  FROM metro_dw.hechos_afluencia_metro AS h
  JOIN metro_dw.dim_estacion AS e ON e.estacion_key = h.estacion_key
  JOIN metro_dw.dim_fecha    AS f ON f.fecha_key    = h.fecha_key
  WHERE f.anio >= 2022
    AND NOT h.es_registro_cero
  GROUP BY e.estacion_nk, e.linea_codigo, f.dia_semana_num
),
participacion AS (
  SELECT
    estacion_nk,
    linea_codigo,
    dia_semana_num,
    SAFE_DIVIDE(media_dia, SUM(media_dia) OVER (PARTITION BY estacion_nk)) AS part
  FROM media
)
SELECT *
FROM participacion
PIVOT (ANY_VALUE(part) FOR dia_semana_num IN
  (1 AS lun, 2 AS mar, 3 AS mie, 4 AS jue, 5 AS vie, 6 AS sab, 7 AS dom));

-- (b) Complementariedad Metro ↔ Metrobús a nivel línea-día (ajuste de P3:
--     Metrobús solo publica afluencia por línea). Correlación diaria.
CREATE OR REPLACE VIEW metro_mart.v_p3_correlacion_metro_metrobus AS
WITH metro AS (
  SELECT fecha_key, linea_key, SUM(afluencia) AS afluencia
  FROM metro_dw.hechos_afluencia_metro
  GROUP BY fecha_key, linea_key
),
metrobus AS (
  SELECT fecha_key, linea_key, afluencia
  FROM metro_dw.hechos_afluencia_metrobus
  WHERE afluencia IS NOT NULL
)
SELECT
  lm.nombre_linea                  AS linea_metro,
  lb.nombre_linea                  AS linea_metrobus,
  CORR(m.afluencia, b.afluencia)   AS correlacion_diaria,
  COUNT(*)                         AS dias_en_comun
FROM metro    AS m
JOIN metrobus AS b  ON b.fecha_key  = m.fecha_key
JOIN metro_dw.dim_linea AS lm ON lm.linea_key = m.linea_key
JOIN metro_dw.dim_linea AS lb ON lb.linea_key = b.linea_key
JOIN metro_dw.dim_fecha AS f  ON f.fecha_key  = m.fecha_key
WHERE f.anio >= 2022
GROUP BY lm.nombre_linea, lb.nombre_linea;


-- ---------------------------------------------------------------------
-- P4 · ¿Qué días son anomalías y qué proporción se explica por eventos
--      identificables (festivos, lluvia, cierres)?
-- Ventana: z-score contra el mismo día de la semana en las 8 semanas
-- previas. GROUPING SETS: conteo de anomalías por cada posible causa.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW metro_mart.v_p4_anomalias_por_causa AS
WITH serie AS (
  SELECT
    h.estacion_key,
    f.fecha,
    f.dia_semana_num,
    f.es_festivo_oficial,
    c.categoria_lluvia,
    e.estado_servicio,
    h.afluencia,
    AVG(h.afluencia)         OVER ventana AS media_ref,
    STDDEV_SAMP(h.afluencia) OVER ventana AS sd_ref
  FROM metro_dw.hechos_afluencia_metro AS h
  JOIN metro_dw.dim_fecha    AS f ON f.fecha_key    = h.fecha_key
  JOIN metro_dw.dim_estacion AS e ON e.estacion_key = h.estacion_key
  LEFT JOIN metro_dw.dim_clima AS c ON c.clima_key  = h.clima_key
  WINDOW ventana AS (
    PARTITION BY h.estacion_key, f.dia_semana_num
    ORDER BY f.fecha
    ROWS BETWEEN 8 PRECEDING AND 1 PRECEDING
  )
),
anomalias AS (
  SELECT *, SAFE_DIVIDE(afluencia - media_ref, sd_ref) AS z
  FROM serie
)
SELECT
  es_festivo_oficial,
  categoria_lluvia,
  estado_servicio,
  COUNT(*) AS estacion_dias_anomalos
FROM anomalias
WHERE ABS(z) >= 3
GROUP BY GROUPING SETS (
  (es_festivo_oficial),
  (categoria_lluvia),
  (estado_servicio),
  ()
);


-- ---------------------------------------------------------------------
-- P5 (reserva) · ¿El Metrobús absorbe demanda cuando una línea del Metro
--      suspende servicio? Cuasiexperimento: cierre de L1 (jul-2022 a nov-2025).
-- CUBE: afluencia media diaria por sistema, línea y periodo.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW metro_mart.v_p5_absorcion_cierre_l1 AS
WITH diario AS (
  SELECT h.fecha_key, h.linea_key, SUM(h.afluencia) AS afluencia
  FROM metro_dw.hechos_afluencia_metro AS h
  GROUP BY h.fecha_key, h.linea_key
  UNION ALL
  SELECT fecha_key, linea_key, afluencia
  FROM metro_dw.hechos_afluencia_metrobus
  WHERE afluencia IS NOT NULL
),
etiquetado AS (
  SELECT
    l.sistema,
    l.nombre_linea,
    CASE
      WHEN f.fecha <  DATE '2022-07-11' THEN '1_antes_del_cierre'
      WHEN f.fecha <  DATE '2025-11-16' THEN '2_durante_el_cierre'
      ELSE                                   '3_despues_de_reabrir'
    END AS periodo,
    d.afluencia
  FROM diario AS d
  JOIN metro_dw.dim_linea AS l ON l.linea_key = d.linea_key
  JOIN metro_dw.dim_fecha AS f ON f.fecha_key = d.fecha_key
  WHERE f.anio >= 2019
)
SELECT
  sistema,
  nombre_linea,
  periodo,
  AVG(afluencia)  AS afluencia_media_diaria,
  COUNT(*)        AS linea_dias
FROM etiquetado
GROUP BY CUBE (sistema, nombre_linea, periodo);
