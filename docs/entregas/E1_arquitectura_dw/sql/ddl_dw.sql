-- =====================================================================
-- E1 · Paso 4: DDL del esquema estrella en la capa DW (metro_dw).
-- Dos tablas de hechos con dimensiones conformadas:
--   hechos_afluencia_metro    -> una fila por estación-línea por día
--   hechos_afluencia_metrobus -> una fila por línea de Metrobús por día
-- Las tablas se crean VACÍAS: poblarlas es trabajo de E2.
-- BigQuery no impone las llaves (NOT ENFORCED); se declaran para
-- documentar el diseño. Ejecutar completo, en este orden.
-- =====================================================================

-- ---------------------------------------------------------------------
-- dim_fecha · SCD tipo 0 (calendario fijo)
-- Fuentes: F1 (rango de fechas) + F4 (festivos, validados contra LFT art. 74)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS metro_dw.dim_fecha (
  fecha_key          INT64   NOT NULL OPTIONS (description = 'Llave sustituta inteligente AAAAMMDD'),
  fecha              DATE    NOT NULL,
  anio               INT64,
  mes                INT64,
  nombre_mes         STRING,
  dia                INT64,
  dia_semana_num     INT64   OPTIONS (description = '1 = lunes ... 7 = domingo (ISO)'),
  nombre_dia         STRING,
  semana_iso         INT64,
  es_fin_de_semana   BOOL,
  es_dia_quincena    BOOL    OPTIONS (description = 'Día 15 o último día del mes'),
  es_festivo_oficial BOOL    OPTIONS (description = 'Descanso obligatorio LFT art. 74'),
  nombre_festivo     STRING,
  es_semana_santa    BOOL    OPTIONS (description = 'Jueves o Viernes Santo (F4, tipo School/Bank)'),
  PRIMARY KEY (fecha_key) NOT ENFORCED
)
OPTIONS (description = 'Dimensión de tiempo diaria, conformada. Responde: P1, P2, P3, P4, P5');

-- ---------------------------------------------------------------------
-- dim_linea · SCD tipo 1 (se sobrescribe: color y terminales sin historia)
-- Conformada entre Metro y Metrobús. Fuentes: F1, F2, F3 (routes.txt)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS metro_dw.dim_linea (
  linea_key        INT64   NOT NULL OPTIONS (description = 'Llave sustituta'),
  sistema          STRING  NOT NULL OPTIONS (description = 'Metro | Metrobús'),
  linea_codigo     STRING  NOT NULL OPTIONS (description = 'Código normalizado: 1..12, A, B (Metro); 1..7 (Metrobús)'),
  nombre_linea     STRING,
  terminales       STRING  OPTIONS (description = 'route_long_name de GTFS'),
  color_hex        STRING  OPTIONS (description = 'route_color de GTFS'),
  gtfs_route_id    STRING  OPTIONS (description = 'Llave natural en F3'),
  PRIMARY KEY (linea_key) NOT ENFORCED
)
OPTIONS (description = 'Líneas de Metro y Metrobús (conformada). Responde: P1, P3, P5');

-- ---------------------------------------------------------------------
-- dim_estacion · SCD tipo 2 en estado_servicio (periodos de cierre);
--                el nombre se sobrescribe (tipo 1): F1 no conserva su historia
-- Una fila por estación-línea y versión. Fuentes: F1 (nombres), F3 (stops.txt)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS metro_dw.dim_estacion (
  estacion_key            INT64   NOT NULL OPTIONS (description = 'Llave sustituta (una por versión)'),
  estacion_nk             STRING  NOT NULL OPTIONS (description = 'Llave natural: linea_codigo + nombre normalizado'),
  gtfs_stop_id            STRING  OPTIONS (description = 'stop_id de F3, p. ej. B_0200L1-PANTITLAN'),
  nombre_oficial          STRING,
  nombre_en_fuente        STRING  OPTIONS (description = 'Texto tal como aparece en F1, para trazabilidad'),
  linea_codigo            STRING  NOT NULL,
  latitud                 FLOAT64,
  longitud                FLOAT64,
  es_correspondencia      BOOL    OPTIONS (description = 'La estación existe en más de una línea'),
  estado_servicio         STRING  OPTIONS (description = 'operando | cerrada_obra | cerrada_incidente | no_inaugurada'),
  fecha_inicio_vigencia   DATE    NOT NULL,
  fecha_fin_vigencia      DATE    OPTIONS (description = 'NULL o 9999-12-31 para la versión vigente'),
  es_version_vigente      BOOL,
  PRIMARY KEY (estacion_key) NOT ENFORCED
)
OPTIONS (description = 'Estaciones del Metro por línea, con historia. Responde: P1, P2, P3, P4, P5');

-- ---------------------------------------------------------------------
-- dim_clima · SCD tipo 1 (se sobrescribe si la fuente reprocesa el día)
-- Un registro por día para la ciudad. Fuente: F5
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS metro_dw.dim_clima (
  clima_key           INT64   NOT NULL OPTIONS (description = 'Llave sustituta'),
  fecha               DATE    NOT NULL,
  precipitacion_mm    FLOAT64,
  lluvia_mm           FLOAT64,
  temp_max_c          FLOAT64,
  temp_min_c          FLOAT64,
  categoria_lluvia    STRING  OPTIONS (description = 'sin_lluvia | ligera | moderada | fuerte (umbrales a fijar en E2)'),
  fecha_descarga      DATE    OPTIONS (description = 'Fecha de la descarga de F5 que originó el registro'),
  PRIMARY KEY (clima_key) NOT ENFORCED
)
OPTIONS (description = 'Clima diario de la CDMX (un punto de malla). Responde: P2, P4');

-- ---------------------------------------------------------------------
-- HECHO 1 · Grano: una fila por estación-línea del Metro por día.
-- Fuente: F1. Medida aditiva: afluencia.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS metro_dw.hechos_afluencia_metro (
  fecha_key          INT64  NOT NULL,
  estacion_key       INT64  NOT NULL,
  linea_key          INT64  NOT NULL,
  clima_key          INT64,
  afluencia          INT64  OPTIONS (description = 'Entradas registradas en el día. Aditiva en todas las dimensiones'),
  es_registro_cero   BOOL   OPTIONS (description = 'Bandera no aditiva: la fuente reporta 0 (cierre o sin servicio)'),
  PRIMARY KEY (fecha_key, estacion_key) NOT ENFORCED,
  FOREIGN KEY (fecha_key)    REFERENCES metro_dw.dim_fecha (fecha_key)       NOT ENFORCED,
  FOREIGN KEY (estacion_key) REFERENCES metro_dw.dim_estacion (estacion_key) NOT ENFORCED,
  FOREIGN KEY (linea_key)    REFERENCES metro_dw.dim_linea (linea_key)       NOT ENFORCED,
  FOREIGN KEY (clima_key)    REFERENCES metro_dw.dim_clima (clima_key)       NOT ENFORCED
)
CLUSTER BY estacion_key, fecha_key
OPTIONS (description = 'Grano: una fila por estación-línea del Metro por día. Responde: P1, P2, P3, P4, P5');

-- ---------------------------------------------------------------------
-- HECHO 2 · Grano: una fila por línea de Metrobús por día.
-- Fuente: F2. Medida aditiva: afluencia (NULL cuando la fuente dice 'NaN').
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS metro_dw.hechos_afluencia_metrobus (
  fecha_key   INT64  NOT NULL,
  linea_key   INT64  NOT NULL,
  clima_key   INT64,
  afluencia   INT64  OPTIONS (description = 'Entradas del día en la línea. Aditiva; NULL antes de la inauguración'),
  PRIMARY KEY (fecha_key, linea_key) NOT ENFORCED,
  FOREIGN KEY (fecha_key) REFERENCES metro_dw.dim_fecha (fecha_key) NOT ENFORCED,
  FOREIGN KEY (linea_key) REFERENCES metro_dw.dim_linea (linea_key) NOT ENFORCED,
  FOREIGN KEY (clima_key) REFERENCES metro_dw.dim_clima (clima_key) NOT ENFORCED
)
CLUSTER BY linea_key, fecha_key
OPTIONS (description = 'Grano: una fila por línea de Metrobús por día. Responde: P3, P5');
