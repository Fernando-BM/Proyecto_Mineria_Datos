"""PASO 5 · MUESTREO.

Decisión: el análisis y la carga al DW usan la POBLACIÓN completa (no
hace falta muestrear: 1.18 millones de filas caben en memoria y en la capa
gratuita de BigQuery, y no hay clase a balancear porque no se modela).

Aparte, el repositorio necesita una muestra pequeña (GitHub no aloja el
CSV de 60 MB y la ayudantía debe poder correr el pipeline sin
credenciales). Esa muestra es estratificada por año y trimestre, por
bloques de semanas completas (no rompe el orden de la serie), con semilla
fija, y se verifica su representatividad contra la población.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from .utiles import LOG, RAIZ, ruta, tabla_md


def _semanas_muestra(fechas: pd.Series, cfg: dict) -> pd.DatetimeIndex:
    rng = np.random.default_rng(cfg["semilla"])
    lunes = pd.Series(pd.date_range(fechas.min(), fechas.max(), freq="W-MON"))
    lunes = lunes[lunes + pd.Timedelta(days=6) <= fechas.max()]
    estrato = lunes.dt.year.astype(str) + "-T" + lunes.dt.quarter.astype(str)
    elegidos = []
    for _, g in lunes.groupby(estrato):
        k = min(cfg["muestra"]["semanas_por_trimestre"], len(g))
        elegidos += list(rng.choice(g.values, size=k, replace=False))
    dias = pd.DatetimeIndex(sorted(pd.Timestamp(l) + pd.Timedelta(days=i) for l in elegidos for i in range(7)))
    return dias


def ejecutar(cfg: dict, crudos: dict, limpio: dict, reg, escribir_muestra: bool = True) -> None:
    reg.inicio("muestreo")
    n = len(crudos["metro"])
    tamano_mb = crudos["metro"].memory_usage(deep=True).sum() / 1e6
    decision = pd.DataFrame([
        {"aspecto": "Población", "valor": f"{n:,} estación-días del Metro (2010-01-01 a 2026-07-31) y "
                                         f"{len(limpio['metrobus']):,} línea-días del Metrobús"},
        {"aspecto": "Volumen", "valor": f"{tamano_mb:,.0f} MB en memoria; la tabla staging del Metro pesa ~60 MB "
                                        "en BigQuery (la capa gratuita permite 1 TB de consultas al mes)"},
        {"aspecto": "Desbalance", "valor": "No aplica: no se entrena ningún modelo en E2"},
        {"aspecto": "Redundancia", "valor": "Cada fila es un estación-día distinto; no hay registros repetidos que resumir"},
        {"aspecto": "Decisión", "valor": "No se muestrea: EDA, reducción y carga al DW usan la población completa"},
        {"aspecto": "Muestra del repositorio", "valor": "Solo para probar el pipeline sin credenciales "
                                                       "(--fuente muestra): una semana completa por año y trimestre"},
    ])
    tabla_md(decision, "muestreo_decision", cfg)

    # --- Muestra del repositorio
    m = limpio["metro"]
    dias = _semanas_muestra(m["fecha"], cfg)
    pobl = m[m["afluencia"].notna()]
    mues = pobl[pobl["fecha"].isin(dias)]

    # Representatividad: población vs muestra (población = datos limpios)
    filas = []
    for nombre, p, s in [("afluencia estación-día", pobl["afluencia"].astype(float), mues["afluencia"].astype(float))]:
        ks = stats.ks_2samp(p, s)
        filas.append({"variable": nombre, "prueba": "Kolmogorov-Smirnov", "estadístico": ks.statistic,
                      "p": ks.pvalue, "media población": p.mean(), "media muestra": s.mean(),
                      "mediana población": p.median(), "mediana muestra": s.median()})
    cl = limpio["clima"]
    cp, cs = cl["precipitacion_mm"], cl.loc[cl["fecha"].isin(dias), "precipitacion_mm"]
    ks = stats.ks_2samp(cp, cs)
    filas.append({"variable": "precipitación diaria (mm)", "prueba": "Kolmogorov-Smirnov", "estadístico": ks.statistic,
                  "p": ks.pvalue, "media población": cp.mean(), "media muestra": cs.mean(),
                  "mediana población": cp.median(), "mediana muestra": cs.median()})
    for var, pp, ss in [
        ("línea", pobl["linea_codigo"], mues["linea_codigo"]),
        ("día de la semana", pobl["fecha"].dt.dayofweek, mues["fecha"].dt.dayofweek),
        ("categoría de lluvia", cl["categoria_lluvia"], cl.loc[cl["fecha"].isin(dias), "categoria_lluvia"]),
        ("año", pobl["fecha"].dt.year, mues["fecha"].dt.year),
    ]:
        prop = pp.value_counts(normalize=True)
        obs = ss.value_counts().reindex(prop.index, fill_value=0)
        chi = stats.chisquare(obs, prop * obs.sum())
        filas.append({"variable": var, "prueba": "χ² de bondad de ajuste", "estadístico": chi.statistic,
                      "p": chi.pvalue, "media población": np.nan, "media muestra": np.nan,
                      "mediana población": np.nan, "mediana muestra": np.nan})
    rep = pd.DataFrame(filas)
    tabla_md(rep, "muestreo_representatividad", cfg)
    LOG.info("  muestra del repo: %d semanas, %s estación-días (%.1f %% de la población)",
             len(dias) // 7, f"{len(mues):,}", 100 * len(mues) / len(pobl))

    if escribir_muestra:
        d = ruta(cfg["muestra"]["directorio"] + "/x").parent
        txt = dias.strftime("%Y-%m-%d")
        gz = {"method": "gzip", "mtime": 0}          # mismo contenido -> mismos bytes (idempotente)
        crudos["metro"][crudos["metro"]["fecha"].isin(txt)].to_csv(d / "metro.csv.gz", index=False, compression=gz)
        crudos["metrobus"][crudos["metrobus"]["fecha"].isin(txt)].to_csv(d / "metrobus.csv.gz", index=False,
                                                                          compression=gz)
        crudos["clima"][crudos["clima"]["time"].isin(txt)].to_csv(d / "clima.csv.gz", index=False, compression=gz)
        st = crudos["gtfs_stops"]
        st[st["stop_id"].str.startswith(("B_02", "B_03"))].to_csv(d / "gtfs_stops.csv.gz", index=False,
                                                                   compression=gz)
        for k in ["gtfs_routes", "festivos", "sismos"]:
            crudos[k].to_csv(d / f"{k}.csv.gz", index=False, compression=gz)
        tam = sum(p.stat().st_size for p in d.glob("*.csv.gz")) / 1e6
        LOG.info("  muestra escrita en %s (%.1f MB)", d.relative_to(RAIZ), tam)
    reg.fin("muestreo", n, n, "población completa; muestra solo para el repositorio")
