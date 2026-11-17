# Pipeline E2 · de staging al DW poblado

Un solo punto de entrada (`run_pipeline.py`) lleva los datos de la capa **staging** de BigQuery
(`metro_staging`, intacta desde E1) al **esquema estrella** (`metro_dw`) y ejecuta el **DataMart**
(`metro_mart`). Además genera las tablas y figuras que se publican en el sitio
(`entregas/E2_eda_preparacion/`).

## Pasos

| # | Paso | Módulo | Qué hace | Salida principal |
|---|------|--------|----------|------------------|
| 1 | ingesta | `src/ingesta.py` | Lee las 7 tablas de staging tal cual (todo texto). Sube la fuente nueva de sismos (F6) a staging si hace falta | dataframes crudos |
| 2 | calidad | `src/calidad.py` | Diagnóstico y EDA sobre el dataset crudo: descriptiva, Gini, entropía, figuras 1-14 | `tablas/eda_*.md`, `img/fig01…fig14` |
| 3 | limpieza | `src/limpieza.py` | Codificación, categorías, duplicados, ceros, atípicos, llaves con GTFS, festivos, sismos | `tablas/registro_limpieza.md` |
| 4 | reduccion | `src/reduccion.py` | χ² + V de Cramér, Spearman y PCA ajustados solo con entrenamiento | `tablas/reduccion_*.md`, figs. 15-16 |
| 5 | muestreo | `src/muestreo.py` | Decide no muestrear y genera la muestra pequeña del repo con su prueba de representatividad | `data/sample/`, `tablas/muestreo_*.md` |
| 6 | verificacion | `src/verificacion.py` | Antes vs. después de la preparación | `tablas/verificacion_*.md`, fig. 17 |
| 7 | modelo + carga | `src/modelo_dw.py`, `src/carga.py` | Dimensiones con llaves sustitutas, SCD2, hechos al grano; validaciones; carga a BigQuery y DataMart | `tablas/validaciones_*.md`, `tablas/mart_*.md` |

Todos los parámetros (umbrales, semilla, nombres de datasets, rutas) están en `config.yaml`.
El SQL que ejecuta la carga está en `sql/` (raíz del repositorio): `ddl_dw.sql`, `consultas_mart.sql`,
`validaciones_dw.sql` y `resultados_mart.sql`.

## Opción A · Google Colab (recomendada, sin instalar nada)

1. Abre `pipeline/ejecutar_en_colab.ipynb` en Colab
   (*Archivo → Abrir cuaderno → GitHub*, pega la URL del repositorio y elige la rama).
2. *Entorno de ejecución → Ejecutar todo*. Cuando lo pida, inicia sesión con la cuenta que tiene acceso
   al proyecto `mineria-metro-cdmx`.
3. Al terminar se descarga `resultados_e2.zip`; descomprímelo en la raíz de tu clon local.

## Opción B · En tu computadora

Requiere Python 3.10 a 3.13 (`python3 --version`).

```bash
git clone https://github.com/Fernando-BM/Proyecto_Mineria_Datos.git
cd Proyecto_Mineria_Datos
python3 -m venv .venv && source .venv/bin/activate      # en Windows: .venv\Scripts\activate
pip install -r pipeline/requirements.txt
```

**Autenticación** (cualquiera de las dos; ninguna deja llaves en el repositorio):

- Con Google Cloud CLI: `gcloud auth application-default login`.
- Sin CLI: no hagas nada; la primera corrida abre el navegador para iniciar sesión
  (pydata-google-auth guarda el token en `~/.pydata_google_auth`, fuera del repo).

Si tu proyecto de BigQuery tiene otro ID: `export GCP_PROJECT=mi-proyecto`.

**Ejecución** (siempre desde la raíz del repositorio):

```bash
python pipeline/run_pipeline.py                                  # oficial: BigQuery -> BigQuery
python pipeline/run_pipeline.py --fuente local --destino local   # archivos originales en datos/crudos/, sin credenciales
python pipeline/run_pipeline.py --fuente muestra                 # muestra del repo, sin credenciales (~10 s)
```

Para `--fuente local` hacen falta los tres archivos del portal en `datos/crudos/`
(no se versionan por tamaño; ver nombres en `config.yaml`):
[afluencia Metro](https://datos.cdmx.gob.mx/dataset/afluencia-diaria-del-metro-cdmx),
[afluencia Metrobús](https://datos.cdmx.gob.mx/dataset/afluencia-diaria-de-metrobus-cdmx) y
[GTFS](https://datos.cdmx.gob.mx/dataset/gtfs). Festivos, clima y sismos ya están en el repositorio.

## Tiempo aproximado

| Modo | Tiempo |
|------|--------|
| `--fuente muestra` | ~10 s |
| `--fuente local --destino local` | ~30 s |
| `--fuente bigquery --destino bigquery` | 5 a 10 min (la lectura de 1.18 M filas de staging domina) |

## Garantías

- **Idempotente.** El DDL usa `DROP`/`CREATE OR REPLACE` y la carga recrea las tablas: correrlo dos veces deja
  el mismo DW. Las tablas, figuras y la muestra salen idénticas byte por byte; solo cambia la columna de
  segundos de `registro_pasos`.
- **Semilla fija** (`semilla` en `config.yaml`) para la muestra del repositorio y el submuestreo de la correlación.
- **Validaciones automáticas** (`assert`): 195 estaciones-línea por día, grano único, llaves no nulas, sin
  llaves huérfanas, una sola versión vigente por estación (SCD2), rangos válidos y conteos de BigQuery iguales
  a los cargados. Si una falla, el pipeline se detiene con el mensaje.
- **Sin fuga de información:** cortes de discretización, estandarización y PCA se ajustan solo con la
  partición de entrenamiento (`fin_entrenamiento` en `config.yaml`).
- **Costo:** la ingesta usa `list_rows` (no cobra bytes escaneados); las consultas del DataMart y las
  validaciones escanean menos de 1 GB en total. Funciona en el *sandbox* gratuito de BigQuery (no usa DML).
  En el sandbox las tablas caducan a los 60 días: basta con volver a correr el pipeline.

## Registro

Cada corrida escribe `pipeline/salidas/ultima_ejecucion.log` (filas de entrada y salida por paso y cada
decisión de limpieza con su conteo) y publica `tablas/registro_pasos.md` y `tablas/registro_limpieza.md`.

## Prueba externa

Antes de entregar, un integrante que no escribió el pipeline lo corre desde un clon limpio y llena la tabla
de la sección *Prueba externa* de `entregas/E2_eda_preparacion/pipeline.qmd` (fecha, quién, entorno, modo,
tiempo y resultado).
