"""Punto de entrada único del pipeline de E2: staging -> DW poblado.

Uso (desde la raíz del repositorio):
    python pipeline/run_pipeline.py                                  # BigQuery -> BigQuery (corrida oficial)
    python pipeline/run_pipeline.py --fuente local --destino local   # archivos originales, sin credenciales
    python pipeline/run_pipeline.py --fuente muestra --destino local # prueba rápida con la muestra del repo

Pasos, en orden: ingesta -> calidad -> limpieza -> reduccion -> muestreo
-> verificacion -> carga. Todos los parámetros están en pipeline/config.yaml.
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src import (calidad, carga, ingesta, limpieza, modelo_dw, muestreo,  # noqa: E402
                 reduccion, verificacion)
from src.utiles import LOG, Registro, cargar_config, configurar_log, tabla_md  # noqa: E402

import pandas as pd  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fuente", choices=["bigquery", "local", "muestra"], default="bigquery")
    ap.add_argument("--destino", choices=["bigquery", "local"], default=None,
                    help="por omisión, bigquery si la fuente es bigquery y local en otro caso")
    ap.add_argument("--sin-figuras", action="store_true", help="omite las figuras del EDA (más rápido)")
    args = ap.parse_args()
    destino = args.destino or ("bigquery" if args.fuente == "bigquery" else "local")

    cfg = cargar_config()
    if args.fuente == "muestra":
        # La muestra no debe sobrescribir las tablas y figuras publicadas en el sitio.
        cfg["salidas"]["tablas"] = "pipeline/salidas/muestra/tablas"
        cfg["salidas"]["figuras"] = "pipeline/salidas/muestra/img"
        cfg["salidas"]["dw_local"] = "pipeline/salidas/muestra/dw"
        cfg["_modo_muestra"] = True
    configurar_log(cfg)
    random.seed(cfg["semilla"])
    np.random.seed(cfg["semilla"])
    t0 = time.time()
    LOG.info("Pipeline E2 · fuente=%s · destino=%s · semilla=%s", args.fuente, destino, cfg["semilla"])

    cli = None
    if "bigquery" in (args.fuente, destino):
        from src import bq
        cli = bq.cliente(cfg)

    reg = Registro()
    crudos, huellas = ingesta.ejecutar(cfg, args.fuente, reg, cli)
    calidad.ejecutar(cfg, crudos, reg, figuras=not args.sin_figuras)
    limpio = limpieza.ejecutar(cfg, crudos, reg)
    analitico = reduccion.ejecutar(cfg, limpio, reg, figuras=not args.sin_figuras)
    muestreo.ejecutar(cfg, crudos, limpio, reg, escribir_muestra=args.fuente != "muestra")
    verificacion.ejecutar(cfg, crudos, limpio, analitico, reg, figuras=not args.sin_figuras)

    reg.inicio("modelo")
    dw = modelo_dw.construir(limpio, cfg)
    reg.fin("modelo", sum(len(v) for v in limpio.values()),
            sum(len(v) for k, v in dw.items() if not k.startswith("_")), "esquema estrella E1 v2")
    carga.ejecutar(cfg, dw, destino, reg, cli)

    # Registro por paso y registro de limpieza (también publicados en el sitio)
    tabla_md(pd.DataFrame(reg.pasos), "registro_pasos", cfg)
    tabla_md(pd.DataFrame(reg.limpieza), "registro_limpieza", cfg)
    tabla_md(pd.DataFrame(huellas), "huellas_fuentes", cfg)
    LOG.info("=" * 60)
    LOG.info("Pipeline terminado en %.1f min. Registro completo en %s",
             (time.time() - t0) / 60, cfg["salidas"]["log"])


if __name__ == "__main__":
    main()
