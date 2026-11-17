-- =====================================================================
-- DDL del esquema estrella · E1 v2 (ajustada en E2).
-- La versión original de E1 se conserva sin cambios en
-- entregas/E1_arquitectura_dw/sql/ddl_dw.sql. Diferencias (ver ajustes.qmd):
--   1. CREATE OR REPLACE en lugar de CREATE IF NOT EXISTS: el pipeline es
--      idempotente (correrlo dos veces deja el mismo resultado).
--   2. dim_fecha: + es_dia_sin_medicion, es_dia_sismo, sismo_magnitud_max,
--      evento_masivo (retroalimentación de E1: sismos y marchas).
--   3. dim_clima: - lluvia_mm (idéntica a precipitacion_mm, ver reducción).
--   4. dim_estacion: estado_servicio = operando | cerrada | no_inaugurada.
--   5. hechos_afluencia_metro: + es_atipico; afluencia NULL si no se midió.
--   6. hechos_afluencia_metrobus: solo días desde la inauguración de la línea.
-- Lo ejecuta el pipeline (paso carga); no hace falta correrlo a mano.
-- =====================================================================

-- Los hechos se borran primero porque referencian a las dimensiones.
DROP TABLE IF EXISTS metro_dw.hechos_afluencia_metro;
DROP TABLE IF EXISTS metro_dw.hechos_afluencia_metrobus;

-- ---------------------------------------------------------------------
-- dim_fecha · SCD tipo 0. Fuentes: F1 (rango), F4 (validación de festivos),
-- F6 (sismos) y calendario de eventos recurrentes (config.yaml).
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE metro_dw.dim_fecha (
  fecha_key           INT64   NOT NULL OPTIONS (description = 'Llave sustituta inteligente AAAAMMDD'),
  fecha               DATE    NOT NULL,
  anio                INT64,
  mes                 INT64,
  nombre_mes          STRING,
  dia                 INT64,
  dia_semana_num      INT64   OPTIONS (description = '1 = lunes ... 7 = domingo (ISO)'),
  nombre_dia          STRING,
  semana_iso          INT64,
  es_fin_de_semana    BOOL,
  es_dia_quincena     BOOL    OPTIONS (description = 'Día 15 o último día del mes'),
  es_festivo_oficial  BOOL    OPTIONS (description = 'Descanso obligatorio LFT art. 74 (regla legal; F4 la valida)'),
  nombre_festivo      STRING,
  es_semana_santa     BOOL    OPTIONS (description = 'Jueves o Viernes Santo (F4)'),
  es_dia_sin_medicion BOOL    OPTIONS (description = 'Todas las estaciones reportan 0: servicio gratuito, torniquetes sin conteo'),
  es_dia_sismo        BOOL    OPTIONS (description = 'Sismo M >= 6.0 a <= 800 km de la CDMX ese día (hora local), F6 USGS'),
  sismo_magnitud_max  FLOAT64 OPTIONS (description = 'Magnitud máxima del día; NULL sin sismo'),
  evento_masivo       STRING  OPTIONS (description = 'marcha_8M | desfile_16_septiembre | marcha_2_octubre | marcha_25N | peregrinacion_basilica'),
  PRIMARY KEY (fecha_key) NOT ENFORCED
)
OPTIONS (description = 'Dimensión de tiempo diaria, conformada. Responde: P1, P2, P3, P4, P5');

-- ---------------------------------------------------------------------
-- dim_linea · SCD tipo 1. Conformada entre Metro y Metrobús. F1, F2, F3.
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE metro_dw.dim_linea (
  linea_key      INT64   NOT NULL OPTIONS (description = 'Llave sustituta'),
  sistema        STRING  NOT NULL OPTIONS (description = 'Metro | Metrobús'),
  linea_codigo   STRING  NOT NULL OPTIONS (description = '1..9, A, B, 12 (Metro); 1..7 (Metrobús)'),
  nombre_linea   STRING  OPTIONS (description = 'Único entre sistemas: "Metro Línea 1", "Metrobús Línea 1"'),
  terminales     STRING  OPTIONS (description = 'route_long_name de GTFS'),
  color_hex      STRING  OPTIONS (description = 'route_color de GTFS'),
  gtfs_route_id  STRING  OPTIONS (description = 'Llave natural en F3'),
  PRIMARY KEY (linea_key) NOT ENFORCED
)
OPTIONS (description = 'Líneas de Metro y Metrobús (conformada). Responde: P1, P3, P5');

-- ---------------------------------------------------------------------
-- dim_estacion · SCD tipo 2 en estado_servicio; el nombre es tipo 1.
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE metro_dw.dim_estacion (
  estacion_key           INT64   NOT NULL OPTIONS (description = 'Llave sustituta (una por versión)'),
  estacion_nk            STRING  NOT NULL OPTIONS (description = 'Llave natural: L + línea + nombre normalizado'),
  gtfs_stop_id           STRING  OPTIONS (description = 'stop_id de F3'),
  nombre_oficial         STRING  OPTIONS (description = 'stop_name de F3'),
  nombre_en_fuente       STRING  OPTIONS (description = 'Nombre canónico en F1 (después de reparar la codificación)'),
  linea_codigo           STRING  NOT NULL,
  latitud                FLOAT64,
  longitud               FLOAT64,
  es_correspondencia     BOOL    OPTIONS (description = 'La estación existe en más de una línea'),
  estado_servicio        STRING  OPTIONS (description = 'operando | cerrada (racha de ceros >= 7 días) | no_inaugurada'),
  fecha_inicio_vigencia  DATE    NOT NULL,
  fecha_fin_vigencia     DATE    OPTIONS (description = '9999-12-31 para la versión vigente'),
  es_version_vigente     BOOL,
  PRIMARY KEY (estacion_key) NOT ENFORCED
)
OPTIONS (description = 'Estaciones del Metro por línea, con historia de estado de servicio. Responde: P1-P5');

-- ---------------------------------------------------------------------
-- dim_clima · SCD tipo 1. Un registro por día para la ciudad. F5.
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE metro_dw.dim_clima (
  clima_key         INT64   NOT NULL OPTIONS (description = 'Llave sustituta AAAAMMDD'),
  fecha             DATE    NOT NULL,
  precipitacion_mm  FLOAT64,
  temp_max_c        FLOAT64,
  temp_min_c        FLOAT64,
  categoria_lluvia  STRING  OPTIONS (description = 'Escala SMN 24 h: sin_lluvia < 0.1 | ligera < 5.1 | moderada < 25 | fuerte'),
  fecha_descarga    DATE    OPTIONS (description = 'Fecha de la descarga de F5'),
  PRIMARY KEY (clima_key) NOT ENFORCED
)
OPTIONS (description = 'Clima diario de la CDMX (un punto de malla). Responde: P2, P4');

-- ---------------------------------------------------------------------
-- HECHO 1 · Grano: una fila por estación-línea del Metro por día. F1.
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE metro_dw.hechos_afluencia_metro (
  fecha_key         INT64  NOT NULL,
  estacion_key      INT64  NOT NULL,
  linea_key         INT64  NOT NULL,
  clima_key         INT64,
  afluencia         INT64  OPTIONS (description = 'Entradas del día. Aditiva. NULL = no se midió (servicio gratuito)'),
  es_registro_cero  BOOL   OPTIONS (description = 'La fuente reporta 0 (no aditiva)'),
  es_atipico        BOOL   OPTIONS (description = '|z robusto| >= 3.5 contra el mismo día de la semana en 9 semanas vecinas'),
  PRIMARY KEY (fecha_key, estacion_key) NOT ENFORCED,
  FOREIGN KEY (fecha_key)    REFERENCES metro_dw.dim_fecha (fecha_key)       NOT ENFORCED,
  FOREIGN KEY (estacion_key) REFERENCES metro_dw.dim_estacion (estacion_key) NOT ENFORCED,
  FOREIGN KEY (linea_key)    REFERENCES metro_dw.dim_linea (linea_key)       NOT ENFORCED,
  FOREIGN KEY (clima_key)    REFERENCES metro_dw.dim_clima (clima_key)       NOT ENFORCED
)
CLUSTER BY estacion_key, fecha_key
OPTIONS (description = 'Grano: una fila por estación-línea del Metro por día. Responde: P1-P5');

-- ---------------------------------------------------------------------
-- HECHO 2 · Grano: una fila por línea de Metrobús por día (desde su inauguración). F2.
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE metro_dw.hechos_afluencia_metrobus (
  fecha_key   INT64  NOT NULL,
  linea_key   INT64  NOT NULL,
  clima_key   INT64,
  afluencia   INT64  OPTIONS (description = 'Entradas del día en la línea. Aditiva; NULL si el valor era imposible'),
  PRIMARY KEY (fecha_key, linea_key) NOT ENFORCED,
  FOREIGN KEY (fecha_key) REFERENCES metro_dw.dim_fecha (fecha_key) NOT ENFORCED,
  FOREIGN KEY (linea_key) REFERENCES metro_dw.dim_linea (linea_key) NOT ENFORCED,
  FOREIGN KEY (clima_key) REFERENCES metro_dw.dim_clima (clima_key) NOT ENFORCED
)
CLUSTER BY linea_key, fecha_key
OPTIONS (description = 'Grano: una fila por línea de Metrobús por día. Responde: P3, P5');
