"""PASO 1 · INGESTA. Lee la capa staging tal como está (todo como texto).

Tres orígenes, con exactamente las mismas columnas que las tablas de
staging de BigQuery creadas en E1:
  --fuente bigquery : metro_staging en BigQuery (corrida oficial).
  --fuente local    : los archivos originales en datos/crudos/ (sin credenciales).
  --fuente muestra  : la muestra pequeña versionada en pipeline/data/sample/.
La ingesta no transforma valores. La única tabla que escribe en staging
es la nueva fuente de sismos (F6), y solo si todavía no existe.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pandas as pd

from .utiles import LOG, RAIZ, sha256

COLUMNAS = {
    "metro": ["fecha", "anio", "mes", "linea", "estacion", "afluencia"],
    "metrobus": ["fecha", "anio", "mes", "linea", "afluencia"],
    "gtfs_stops": ["stop_id", "stop_name", "stop_lat", "stop_lon"],
    "gtfs_routes": ["route_id", "agency_id", "route_short_name", "route_long_name",
                    "route_type", "route_color"],
    "festivos": ["date", "localName", "types"],
    "clima": ["time", "precipitation_sum_mm", "rain_sum_mm",
              "temperature_2m_max_c", "temperature_2m_min_c"],
    "sismos": ["time", "latitude", "longitude", "depth", "mag", "magType", "id", "place"],
}
SISMOS_COLUMNAS_ARCHIVO = [
    "time", "latitude", "longitude", "depth", "mag", "magType", "nst", "gap", "dmin", "rms",
    "net", "id", "updated", "place", "type", "horizontalError", "depthError", "magError",
    "magNst", "status", "locationSource", "magSource"]


def _csv(path: Path, **kw) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False, **kw)


# ---------------------------------------------------------------------
# Origen: archivos originales
# ---------------------------------------------------------------------
def _local(cfg: dict) -> tuple[dict, list[dict]]:
    fl = cfg["fuente_local"]
    datos, huellas = {}, []
    for clave in ["metro", "metrobus", "festivos", "clima", "sismos", "gtfs_zip"]:
        p = RAIZ / fl[clave]
        if not p.exists():
            raise FileNotFoundError(
                f"No existe {p}. Descarga la fuente (ver pipeline/README.md) o usa --fuente muestra.")
        huellas.append({"fuente": clave, "archivo": fl[clave], "sha256": sha256(p)})
    datos["metro"] = _csv(RAIZ / fl["metro"])[COLUMNAS["metro"]]
    datos["metrobus"] = _csv(RAIZ / fl["metrobus"])[COLUMNAS["metrobus"]]
    with zipfile.ZipFile(RAIZ / fl["gtfs_zip"]) as z:
        datos["gtfs_stops"] = _csv(io.BytesIO(z.read("stops.txt")))[COLUMNAS["gtfs_stops"]]
        datos["gtfs_routes"] = _csv(io.BytesIO(z.read("routes.txt")))[COLUMNAS["gtfs_routes"]]
    fest = pd.read_json(RAIZ / fl["festivos"], lines=True, dtype=False)
    fest["types"] = fest["types"].map(lambda t: "|".join(t) if isinstance(t, list) else str(t))
    fest["date"] = pd.to_datetime(fest["date"]).dt.strftime("%Y-%m-%d")
    datos["festivos"] = fest[COLUMNAS["festivos"]].astype(str)
    # Open-Meteo: 3 líneas de metadatos + encabezado con unidades. Igual que en
    # staging, se omite el encabezado original y se nombran las columnas por posición.
    clima = _csv(RAIZ / fl["clima"], skiprows=4, header=None)
    clima.columns = COLUMNAS["clima"]
    datos["clima"] = clima
    datos["sismos"] = _csv(RAIZ / fl["sismos"])[COLUMNAS["sismos"]]
    return datos, huellas


def _muestra(cfg: dict) -> tuple[dict, list[dict]]:
    d = RAIZ / cfg["muestra"]["directorio"]
    datos = {k: _csv(d / f"{k}.csv.gz") for k in COLUMNAS}
    return datos, [{"fuente": "muestra", "archivo": str(d.relative_to(RAIZ)), "sha256": ""}]


# ---------------------------------------------------------------------
# Origen: BigQuery (capa staging)
# ---------------------------------------------------------------------
def _asegurar_sismos_en_staging(cli, cfg: dict) -> None:
    """F6 es nueva en E2: se sube a staging tal como viene del USGS (todo
    STRING), con WRITE_TRUNCATE para que repetir la corrida dé lo mismo."""
    from google.cloud import bigquery
    b = cfg["bigquery"]
    tabla = f"{b['proyecto']}.{b['datasets']['staging']}.{b['tablas_staging']['sismos']}"
    esquema = [bigquery.SchemaField(c, "STRING") for c in SISMOS_COLUMNAS_ARCHIVO]
    conf = bigquery.LoadJobConfig(schema=esquema, source_format=bigquery.SourceFormat.CSV,
                                  skip_leading_rows=1, allow_quoted_newlines=True,
                                  write_disposition="WRITE_TRUNCATE")
    with open(RAIZ / cfg["fuente_local"]["sismos"], "rb") as f:
        cli.load_table_from_file(f, tabla, job_config=conf).result()
    LOG.info("  staging: %s cargada desde %s", tabla, cfg["fuente_local"]["sismos"])


def _bigquery(cfg: dict, cli) -> tuple[dict, list[dict]]:
    b = cfg["bigquery"]
    _asegurar_sismos_en_staging(cli, cfg)
    datos, huellas = {}, []
    for clave, cols in COLUMNAS.items():
        tabla = f"{b['proyecto']}.{b['datasets']['staging']}.{b['tablas_staging'][clave]}"
        # list_rows (tabledata.list) no cobra bytes escaneados, a diferencia de SELECT.
        t = cli.get_table(tabla)
        campos = [f for f in t.schema if f.name in cols]
        faltan = set(cols) - {f.name for f in campos}
        if faltan:
            raise KeyError(f"{tabla} no tiene las columnas {sorted(faltan)}")
        df = cli.list_rows(t, selected_fields=campos, page_size=50_000).to_dataframe(
            create_bqstorage_client=False)
        if clave == "festivos":
            df["types"] = df["types"].map(lambda t: "|".join(t) if t is not None else "")
            df["date"] = df["date"].astype(str)
        datos[clave] = df[cols].astype(str).replace({"None": "", "nan": ""})
        huellas.append({"fuente": clave, "archivo": tabla, "sha256": ""})
    return datos, huellas


# ---------------------------------------------------------------------
def ejecutar(cfg: dict, fuente: str, registro, cli=None) -> tuple[dict, list[dict]]:
    registro.inicio("ingesta")
    if fuente == "bigquery":
        datos, huellas = _bigquery(cfg, cli)
    elif fuente == "local":
        datos, huellas = _local(cfg)
    elif fuente == "muestra":
        datos, huellas = _muestra(cfg)
    else:
        raise ValueError(f"fuente desconocida: {fuente}")
    total = 0
    for k, df in datos.items():
        LOG.info("  %-12s %10s filas · %d columnas", k, f"{len(df):,}", df.shape[1])
        total += len(df)
    registro.fin("ingesta", total, total, f"origen={fuente}")
    return datos, huellas
