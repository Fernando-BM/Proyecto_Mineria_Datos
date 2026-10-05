-- =====================================================================
-- E1 · Paso 1: crear los tres datasets (capas) en la MISMA ubicación.
-- Ejecutar en la consola de BigQuery con el proyecto del equipo
-- seleccionado arriba a la izquierda. No requiere nombre de proyecto.
-- =====================================================================

CREATE SCHEMA IF NOT EXISTS metro_staging
OPTIONS (
  location    = 'US',
  description = 'Capa staging: datos crudos tal como vienen de cada fuente (F1-F5), sin limpiar.'
);

CREATE SCHEMA IF NOT EXISTS metro_dw
OPTIONS (
  location    = 'US',
  description = 'Capa DW: esquema estrella (2 hechos con dimensiones conformadas).'
);

CREATE SCHEMA IF NOT EXISTS metro_mart
OPTIONS (
  location    = 'US',
  description = 'Capa DataMart: vistas que responden P1-P5 de E0 sobre metro_dw.'
);
