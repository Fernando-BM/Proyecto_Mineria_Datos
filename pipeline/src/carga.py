"""PASO 7 · CARGA. Puebla el esquema estrella de E1 (v2) y ejecuta el DataMart.

--destino bigquery : DDL idempotente (CREATE OR REPLACE), carga de las 6
                     tablas, creación de las vistas, validaciones SQL y
                     resultados del DataMart publicados en el sitio.
--destino local    : las 6 tablas en Parquet (pipeline/salidas/dw/) con las
                     mismas validaciones en pandas. Sirve para la prueba sin
                     credenciales; las vistas del DataMart solo corren en BigQuery.
La capa staging no se toca (salvo la tabla nueva de sismos, en la ingesta).
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from . import bq
from .utiles import LOG, RAIZ, ruta, tabla_md

TABLAS = ["dim_fecha", "dim_linea", "dim_estacion", "dim_clima",
          "hechos_afluencia_metro", "hechos_afluencia_metrobus"]


def _local(cfg: dict, dw: dict) -> None:
    d = ruta(Path(cfg["salidas"]["dw_local"]) / "x").parent
    for t in TABLAS:
        dw[t].to_parquet(d / f"{t}.parquet", index=False)
        LOG.info("  %-28s %10s filas -> %s", t, f"{len(dw[t]):,}", (d / f"{t}.parquet").relative_to(RAIZ))
    _mart_local(cfg, dw)


def _mart_local(cfg: dict, dw: dict) -> None:
    """Sin credenciales: ejecuta el mismo SQL del DataMart y de las validaciones
    en DuckDB (traducido de BigQuery con sqlglot). Los resultados quedan en
    pipeline/salidas/mart_local/; los oficiales salen de BigQuery."""
    import duckdb
    import sqlglot

    def trad(sql: str) -> str:
        return sqlglot.transpile(sql, read="bigquery", write="duckdb")[0]

    con = duckdb.connect()
    con.execute("CREATE SCHEMA metro_dw; CREATE SCHEMA metro_mart;")
    for t in TABLAS:
        con.register("_df", dw[t])
        con.execute(f"CREATE TABLE metro_dw.{t} AS SELECT * FROM _df")
        con.unregister("_df")
    vistas = bq.dividir_sentencias(_sql(cfg, "mart"))
    for st in vistas:
        con.execute(trad(st))
    salida = dict(cfg, salidas=dict(cfg["salidas"], tablas=str(Path(cfg["salidas"]["dw_local"]).parent / "mart_local")))
    val = con.execute(trad(_sql(cfg, "validaciones"))).df()
    _revisar_validaciones(val, dw, salida, "validaciones_duckdb")
    for bloque in re.split(r"^-- @", _sql(cfg, "resultados_mart"), flags=re.M)[1:]:
        nombre, sql = bloque.split("\n", 1)
        tabla_md(con.execute(trad(sql)).df(), f"mart_{nombre.strip()}", salida)
    LOG.info("  DataMart emulado en DuckDB: %d vistas y %s consultas -> %s", len(vistas),
             len(re.findall(r"^-- @", _sql(cfg, "resultados_mart"), flags=re.M)), salida["salidas"]["tablas"])


def _revisar_validaciones(val: pd.DataFrame, dw: dict, cfg: dict, nombre: str) -> None:
    conteo = {f"filas {t}": len(dw[t]) for t in TABLAS}
    val["esperado"] = [conteo.get(re.sub(r"^\d+ ", "", p), e) for p, e in zip(val["prueba"], val["esperado"])]
    val["resultado"] = ["OK" if int(v) == int(e) else "FALLA" for v, e in zip(val["valor"], val["esperado"])]
    tabla_md(val, nombre, cfg)
    LOG.info("  %s: %d de %d OK", nombre, (val["resultado"] == "OK").sum(), len(val))
    fallas = val[val["resultado"] != "OK"]
    assert fallas.empty, f"Validaciones fallidas ({nombre}):\n{fallas}"


def _sql(cfg: dict, clave: str) -> str:
    texto = (RAIZ / cfg["bigquery"]["sql"][clave]).read_text(encoding="utf-8")
    return texto.replace("{umbral_alta_demanda}", str(cfg["alta_demanda"]["umbral_vs_base"]))


def _bigquery(cfg: dict, dw: dict, cli) -> None:
    from google.cloud import bigquery
    b = cfg["bigquery"]
    ds_dw = f"{b['proyecto']}.{b['datasets']['dw']}"

    # 1. DDL v2 (borra y recrea vacías las 6 tablas: idempotente)
    bq.ejecutar_script(cli, _sql(cfg, "ddl"), "DDL del DW (sql/ddl_dw.sql)")

    # 2. Carga: el esquema se toma de la tabla recién creada, así se respetan
    #    tipos, modos NOT NULL, descripciones y llaves declaradas.
    for t in TABLAS:
        tabla = cli.get_table(f"{ds_dw}.{t}")
        conf = bigquery.LoadJobConfig(schema=tabla.schema, write_disposition="WRITE_APPEND")
        df = dw[t][[c.name for c in tabla.schema]]
        cli.load_table_from_dataframe(df, tabla, job_config=conf).result()
        n = cli.get_table(tabla).num_rows
        assert n == len(df), f"{t}: se cargaron {n} filas de {len(df)}"
        LOG.info("  %-28s %10s filas cargadas", t, f"{n:,}")

    # 3. Vistas del DataMart
    bq.ejecutar_script(cli, _sql(cfg, "mart"), "vistas del DataMart (sql/consultas_mart.sql)")

    # 4. Validaciones en BigQuery contra lo que el pipeline sabe que cargó
    val = bq.consulta_df(cli, _sql(cfg, "validaciones"))
    _revisar_validaciones(val, dw, cfg, "validaciones_bigquery")

    # 5. Resultados del DataMart que se publican en el sitio
    texto = _sql(cfg, "resultados_mart")
    for bloque in re.split(r"^-- @", texto, flags=re.M)[1:]:
        nombre, sql = bloque.split("\n", 1)
        res = bq.consulta_df(cli, sql)
        tabla_md(res, f"mart_{nombre.strip()}", cfg)
        LOG.info("  DataMart %-28s %5d filas -> tablas/mart_%s.md", nombre.strip(), len(res), nombre.strip())


def ejecutar(cfg: dict, dw: dict, destino: str, reg, cli=None) -> None:
    reg.inicio("carga")
    total = sum(len(dw[t]) for t in TABLAS)
    tabla_md(dw["_validaciones"], "validaciones_modelo", cfg)
    resumen = pd.DataFrame([{"tabla": t, "filas": len(dw[t]), "columnas": dw[t].shape[1]} for t in TABLAS])
    tabla_md(resumen, "dw_filas_por_tabla", cfg)
    if destino == "bigquery":
        _bigquery(cfg, dw, cli)
    elif destino == "local":
        _local(cfg, dw)
    else:
        raise ValueError(f"destino desconocido: {destino}")
    reg.fin("carga", total, total, f"destino={destino}")
