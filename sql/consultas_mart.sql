-- =====================================================================
-- DataMart (metro_mart) · E1 v2 (ajustada en E2). Una o dos vistas por
-- pregunta de E0 sobre el esquema estrella poblado.
-- Original de E1 sin cambios en entregas/E1_arquitectura_dw/sql/consultas_mart.sql.
-- Cambios (ver ajustes.qmd):
--   * Se excluyen los días no medidos (afluencia NULL).
--   * Las ventanas se particionan por estacion_nk (la llave estable), no por
--     estacion_key, que cambia con cada versión SCD2.
--   * P2: umbral de alta demanda desde config.yaml ({umbral_alta_demanda}).
--   * P4: causa probable con festivos, eventos masivos, sismos, lluvia y cierres.
--   * P3: correlación sin el ciclo semanal, además de la de niveles.
--   * P5: el periodo de referencia empieza en 2022 (sin la pandemia) y se
--     agrega v_p5_diferencia_vs_control (líneas abiertas del Metro como control).
-- Lo ejecuta el pipeline (paso carga), que sustituye {umbral_alta_demanda}.
-- Operadores OLAP: ROLLUP (P1), ventanas (P1, P2, P3, P4, P5), PIVOT (P3),
-- GROUPING SETS (P4) y CUBE (P5).
-- =====================================================================

-- P1 (a) · ROLLUP: afluencia media diaria por línea y día de la semana,
-- con subtotal por línea (dia_semana_num NULL) y total de la red (ambos NULL).
CREATE OR REPLACE VIEW metro_mart.v_p1_rollup_linea_dia AS
SELECT
  l.nombre_linea,
  f.dia_semana_num,
  SUM(h.afluencia)                                        AS afluencia_total,
  COUNT(DISTINCT h.fecha_key)                             AS dias_observados,
  SAFE_DIVIDE(SUM(h.afluencia), COUNT(DISTINCT h.fecha_key)) AS afluencia_media_diaria
FROM metro_dw.hechos_afluencia_metro AS h
JOIN metro_dw.dim_linea AS l ON l.linea_key = h.linea_key
JOIN metro_dw.dim_fecha AS f ON f.fecha_key = h.fecha_key
WHERE f.anio >= 2022
  AND h.afluencia IS NOT NULL
  AND NOT h.es_registro_cero
GROUP BY ROLLUP (l.nombre_linea, f.dia_semana_num);

-- P1 (b) · Ventanas: índice de cada estación-día de la semana contra su
-- propia base y ranking de las 20 estaciones más cargadas por día.
CREATE OR REPLACE VIEW metro_mart.v_p1_picos_vs_base AS
WITH media_por_dia AS (
  SELECT
    l.nombre_linea,
    e.estacion_nk,
    ANY_VALUE(e.nombre_oficial) AS nombre_oficial,
    f.dia_semana_num,
    f.nombre_dia,
    AVG(h.afluencia) AS media_dia
  FROM metro_dw.hechos_afluencia_metro AS h
  JOIN metro_dw.dim_estacion AS e ON e.estacion_key = h.estacion_key
  JOIN metro_dw.dim_linea    AS l ON l.linea_key    = h.linea_key
  JOIN metro_dw.dim_fecha    AS f ON f.fecha_key    = h.fecha_key
  WHERE f.anio >= 2022
    AND h.afluencia IS NOT NULL
    AND NOT h.es_registro_cero
  GROUP BY l.nombre_linea, e.estacion_nk, f.dia_semana_num, f.nombre_dia
),
con_indices AS (
  SELECT
    *,
    SAFE_DIVIDE(media_dia, AVG(media_dia) OVER (PARTITION BY estacion_nk)) AS indice_vs_base,
    RANK() OVER (PARTITION BY dia_semana_num ORDER BY media_dia DESC)      AS rank_en_el_dia
  FROM media_por_dia
)
SELECT * FROM con_indices WHERE rank_en_el_dia <= 20;

-- P2 · Conjunto para el pronóstico a 24 h: rezagos, línea base ingenua
-- (media del mismo día de la semana en las 4 semanas previas, la del
-- criterio de éxito) y etiqueta de alta demanda.
CREATE OR REPLACE VIEW metro_mart.v_p2_dataset_pronostico AS
WITH serie AS (
  SELECT
    e.estacion_nk,
    e.linea_codigo,
    f.fecha,
    f.dia_semana_num,
    f.mes,
    f.es_festivo_oficial,
    f.es_dia_quincena,
    f.es_semana_santa,
    f.es_dia_sismo,
    f.evento_masivo,
    c.precipitacion_mm,
    c.temp_max_c,
    c.categoria_lluvia,
    e.estado_servicio,
    h.afluencia
  FROM metro_dw.hechos_afluencia_metro AS h
  JOIN metro_dw.dim_estacion AS e ON e.estacion_key = h.estacion_key
  JOIN metro_dw.dim_fecha    AS f ON f.fecha_key    = h.fecha_key
  LEFT JOIN metro_dw.dim_clima AS c ON c.clima_key  = h.clima_key
  WHERE h.afluencia IS NOT NULL
),
con_rezagos AS (
  SELECT
    *,
    LAG(afluencia, 1) OVER (PARTITION BY estacion_nk ORDER BY fecha) AS afluencia_t_menos_1,
    LAG(afluencia, 7) OVER (PARTITION BY estacion_nk ORDER BY fecha) AS afluencia_t_menos_7,
    AVG(afluencia) OVER (
      PARTITION BY estacion_nk, dia_semana_num
      ORDER BY fecha
      ROWS BETWEEN 4 PRECEDING AND 1 PRECEDING
    )                                                                 AS base_ingenua_4sem
  FROM serie
)
SELECT
  *,
  SAFE_DIVIDE(ABS(afluencia - base_ingenua_4sem), afluencia) AS error_abs_pct_base,
  afluencia > {umbral_alta_demanda} * base_ingenua_4sem      AS es_alta_demanda
FROM con_rezagos
WHERE estado_servicio = 'operando';

-- P3 (a) · PIVOT: perfil semanal de cada estación (participación de cada
-- día de la semana en su demanda). Matriz de entrada del clustering.
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
    AND h.afluencia IS NOT NULL
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

-- P3 (b) · Complementariedad Metro ↔ Metrobús por línea-día (P3 ajustada).
-- Ajuste E2 (retroalimentación de E1: que la consulta responda la pregunta):
-- la correlación de los niveles (correlacion_bruta) sale alta para casi
-- cualquier par porque todas las líneas comparten el ciclo semanal. Por eso
-- se agrega correlacion_sin_ciclo: correlación de la desviación de cada
-- línea-día contra la media del MISMO día de la semana en sus 4 semanas
-- previas. Mide si dos líneas reciben los mismos choques inesperados. Una
-- línea de Metrobús poco acoplada a una del Metro es mejor candidata a
-- alternativa: cuando el Metro se satura sin aviso, ella no se satura a la vez.
-- Solo días con todas las estaciones de la línea del Metro en operación y sin
-- festivos ni Semana Santa (choques de calendario que comparten todas).
CREATE OR REPLACE VIEW metro_mart.v_p3_correlacion_metro_metrobus AS
WITH metro AS (
  SELECT h.fecha_key, h.linea_key, SUM(h.afluencia) AS afluencia
  FROM metro_dw.hechos_afluencia_metro AS h
  JOIN metro_dw.dim_estacion AS e ON e.estacion_key = h.estacion_key
  WHERE h.afluencia IS NOT NULL
  GROUP BY h.fecha_key, h.linea_key
  HAVING COUNTIF(e.estado_servicio <> 'operando') = 0
),
metrobus AS (
  SELECT fecha_key, linea_key, afluencia
  FROM metro_dw.hechos_afluencia_metrobus
  WHERE afluencia IS NOT NULL
),
diario AS (
  SELECT 'Metro' AS sistema, fecha_key, linea_key, afluencia FROM metro
  UNION ALL
  SELECT 'Metrobús' AS sistema, fecha_key, linea_key, afluencia FROM metrobus
),
relativo AS (
  SELECT
    d.sistema,
    d.fecha_key,
    d.linea_key,
    d.afluencia,
    SAFE_DIVIDE(d.afluencia, AVG(d.afluencia) OVER (
      PARTITION BY d.linea_key, f.dia_semana_num
      ORDER BY d.fecha_key
      ROWS BETWEEN 4 PRECEDING AND 1 PRECEDING)) - 1 AS desviacion
  FROM diario AS d
  JOIN metro_dw.dim_fecha AS f ON f.fecha_key = d.fecha_key
  WHERE f.anio >= 2021
    AND NOT f.es_festivo_oficial
    AND NOT f.es_semana_santa
)
SELECT
  lm.nombre_linea                  AS linea_metro,
  lb.nombre_linea                  AS linea_metrobus,
  CORR(m.afluencia, b.afluencia)   AS correlacion_bruta,
  CORR(m.desviacion, b.desviacion) AS correlacion_sin_ciclo,
  COUNT(*)                         AS dias_en_comun
FROM relativo AS m
JOIN relativo AS b
  ON b.fecha_key = m.fecha_key AND b.sistema = 'Metrobús'
JOIN metro_dw.dim_linea AS lm ON lm.linea_key = m.linea_key
JOIN metro_dw.dim_linea AS lb ON lb.linea_key = b.linea_key
WHERE m.sistema = 'Metro'
  AND m.fecha_key >= 20220101
GROUP BY lm.nombre_linea, lb.nombre_linea;

-- P4 · Anomalías (|z| >= 3 contra el mismo día de la semana en las 8
-- semanas previas, solo días en operación) y su causa probable.
-- GROUPING SETS: conteo por causa, por evento, por lluvia y total.
CREATE OR REPLACE VIEW metro_mart.v_p4_anomalias_por_causa AS
WITH serie AS (
  SELECT
    e.estacion_nk,
    f.fecha,
    f.es_festivo_oficial,
    f.es_semana_santa,
    f.es_dia_sismo,
    IFNULL(f.evento_masivo, 'ninguno') AS evento_masivo,
    IFNULL(c.categoria_lluvia, 'sin_dato') AS categoria_lluvia,
    h.es_registro_cero,
    h.afluencia,
    AVG(h.afluencia)         OVER ventana AS media_ref,
    STDDEV_SAMP(h.afluencia) OVER ventana AS sd_ref
  FROM metro_dw.hechos_afluencia_metro AS h
  JOIN metro_dw.dim_fecha    AS f ON f.fecha_key    = h.fecha_key
  JOIN metro_dw.dim_estacion AS e ON e.estacion_key = h.estacion_key
  LEFT JOIN metro_dw.dim_clima AS c ON c.clima_key  = h.clima_key
  WHERE e.estado_servicio = 'operando'
    AND h.afluencia IS NOT NULL
  WINDOW ventana AS (
    PARTITION BY e.estacion_nk, f.dia_semana_num
    ORDER BY f.fecha
    ROWS BETWEEN 8 PRECEDING AND 1 PRECEDING
  )
),
anomalias AS (
  SELECT
    *,
    SAFE_DIVIDE(afluencia - media_ref, sd_ref) AS z,
    CASE
      WHEN es_registro_cero                         THEN 'cierre_puntual'
      WHEN es_festivo_oficial OR es_semana_santa    THEN 'festivo_o_semana_santa'
      WHEN evento_masivo <> 'ninguno'               THEN 'evento_masivo'
      WHEN es_dia_sismo                             THEN 'sismo'
      WHEN categoria_lluvia = 'fuerte'              THEN 'lluvia_fuerte'
      ELSE                                               'sin_causa_atribuida'
    END AS causa_probable
  FROM serie
)
SELECT
  causa_probable,
  evento_masivo,
  categoria_lluvia,
  COUNT(*)            AS estacion_dias_anomalos,
  COUNTIF(z > 0)      AS anomalias_altas,
  COUNTIF(z < 0)      AS anomalias_bajas
FROM anomalias
WHERE ABS(z) >= 3
GROUP BY GROUPING SETS (
  (causa_probable),
  (evento_masivo),
  (categoria_lluvia),
  ()
);

-- P5 (reserva) · CUBE: afluencia media diaria por sistema, línea y periodo
-- respecto del cierre de la Línea 1 (jul-2022 a nov-2025). Ajuste E2: el
-- periodo "antes" empieza en 2022 (en E1 era 2019) porque el EDA mostró que
-- 2020-2021 (pandemia) hundía el nivel de referencia y simulaba absorción.
CREATE OR REPLACE VIEW metro_mart.v_p5_absorcion_cierre_l1 AS
WITH diario AS (
  SELECT h.fecha_key, h.linea_key, SUM(h.afluencia) AS afluencia
  FROM metro_dw.hechos_afluencia_metro AS h
  WHERE h.afluencia IS NOT NULL
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
  WHERE f.fecha >= DATE '2022-01-01'
)
SELECT
  sistema,
  nombre_linea,
  periodo,
  AVG(afluencia) AS afluencia_media_diaria,
  COUNT(*)       AS linea_dias
FROM etiquetado
GROUP BY CUBE (sistema, nombre_linea, periodo);


-- P5 (b) · Ventanas: diferencia contra un grupo de control (ajuste E2 por la
-- retroalimentación de E1). Compara cuánto cambió cada línea de Metrobús al
-- cerrar y al reabrir la Línea 1 contra cuánto cambiaron, en los mismos días,
-- las 10 líneas del Metro que siguieron abiertas (control: todas menos la 1 y
-- la 12, que reabrió durante el periodo). La recuperación de la pandemia y la
-- estacionalidad afectan a los dos grupos por igual, así que la diferencia
-- aísla lo que solo le pasó a cada línea. Absorción esperada: diferencia
-- positiva durante el cierre y negativa al reabrir.
CREATE OR REPLACE VIEW metro_mart.v_p5_diferencia_vs_control AS
WITH diario AS (
  SELECT h.fecha_key, l.sistema, l.nombre_linea, SUM(h.afluencia) AS afluencia
  FROM metro_dw.hechos_afluencia_metro AS h
  JOIN metro_dw.dim_linea AS l ON l.linea_key = h.linea_key
  WHERE h.afluencia IS NOT NULL
  GROUP BY h.fecha_key, l.sistema, l.nombre_linea
  UNION ALL
  SELECT h.fecha_key, l.sistema, l.nombre_linea, h.afluencia
  FROM metro_dw.hechos_afluencia_metrobus AS h
  JOIN metro_dw.dim_linea AS l ON l.linea_key = h.linea_key
  WHERE h.afluencia IS NOT NULL
),
por_grupo AS (
  SELECT
    fecha_key,
    CASE WHEN sistema = 'Metro' AND nombre_linea <> 'Metro Línea 1'
         THEN 'Metro: control (10 líneas abiertas)' ELSE nombre_linea END AS grupo,
    SUM(afluencia) AS afluencia
  FROM diario
  WHERE nombre_linea <> 'Metro Línea 12'
  GROUP BY fecha_key, grupo
),
etiquetado AS (
  SELECT
    p.grupo,
    CASE
      WHEN f.fecha <  DATE '2022-07-11' THEN '1_antes_del_cierre'
      WHEN f.fecha <  DATE '2025-11-16' THEN '2_durante_el_cierre'
      ELSE                                   '3_despues_de_reabrir'
    END AS periodo,
    p.afluencia
  FROM por_grupo AS p
  JOIN metro_dw.dim_fecha AS f ON f.fecha_key = p.fecha_key
  WHERE f.fecha >= DATE '2022-01-01'
),
medias AS (
  SELECT grupo, periodo, AVG(afluencia) AS afluencia_media_diaria, COUNT(*) AS dias
  FROM etiquetado
  GROUP BY grupo, periodo
),
cambios AS (
  SELECT
    *,
    SAFE_DIVIDE(afluencia_media_diaria,
                LAG(afluencia_media_diaria) OVER (PARTITION BY grupo ORDER BY periodo)) - 1
      AS cambio_vs_periodo_previo
  FROM medias
)
SELECT
  c.grupo,
  c.periodo,
  c.afluencia_media_diaria,
  c.dias,
  c.cambio_vs_periodo_previo,
  c.cambio_vs_periodo_previo - k.cambio_vs_periodo_previo AS diferencia_vs_control
FROM cambios AS c
JOIN cambios AS k
  ON k.periodo = c.periodo
 AND k.grupo = 'Metro: control (10 líneas abiertas)';
