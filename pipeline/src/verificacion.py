"""PASO 6 · VERIFICACIÓN: antes vs. después de la preparación.

Recalcula las medidas clave sobre los datos crudos y sobre los datos
preparados y responde: ¿la preparación conservó el fenómeno de E0
(picos por estación y día, concentración y patrón semanal)?
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from . import graficas as G
from .calidad import integrar_crudo
from .utiles import LOG, entropia, gini, guardar_figura, participacion_top, tabla_md


def _medidas(nombre: str, x: pd.Series) -> dict:
    x = pd.Series(x, dtype=float).dropna()
    q1, q3 = x.quantile([.25, .75])
    return {"variable": nombre, "n": len(x), "media": x.mean(), "mediana": x.median(),
            "desv. est.": x.std(), "IQR": q3 - q1, "asimetría": stats.skew(x),
            "% ceros": (x == 0).mean()}


def ejecutar(cfg: dict, crudos: dict, limpio: dict, analitico: pd.DataFrame, reg, figuras: bool = True) -> None:
    reg.inicio("verificacion")
    crudo, mb_crudo, _ = integrar_crudo(cfg, crudos)
    m = limpio["metro"]
    # "Después" para análisis: estación-días medidos y en operación (lo que verá el modelado)
    despues = m[(m["estado_servicio"] == "operando") & m["afluencia"].notna()]
    red_antes = crudo.groupby("fecha")["afluencia"].sum()
    red_desp = m.groupby("fecha")["afluencia"].sum(min_count=1)
    mb_desp = limpio["metrobus"]["afluencia"]

    filas = []
    for etapa, est, red, mb in [("antes", crudo["afluencia"], red_antes, mb_crudo["afluencia"]),
                                ("después", despues["afluencia"], red_desp, mb_desp)]:
        for f in [_medidas("afluencia estación-día (Metro)", est), _medidas("afluencia diaria de la red", red),
                  _medidas("afluencia línea-día (Metrobús)", mb)]:
            f["etapa"] = etapa
            filas.append(f)
    tabla = pd.DataFrame(filas)[["variable", "etapa", "n", "media", "mediana", "desv. est.", "IQR",
                                 "asimetría", "% ceros"]].sort_values(["variable", "etapa"], ascending=[True, True])
    tabla_md(tabla, "verificacion_antes_despues", cfg)

    # Fenómeno de E0: ¿se conserva?
    def fenomeno(df, etiqueta):
        d = df[df["fecha"].dt.year == 2025]
        tot = d.groupby(["linea_codigo", "estacion"])["afluencia"].sum().astype(float)
        dw = d.assign(ds=d["fecha"].dt.dayofweek).groupby("ds")["afluencia"].sum().astype(float)
        top = tot.sort_values(ascending=False).head(10).index
        r = df[df["fecha"].dt.year >= 2022].groupby("fecha")["afluencia"].sum().astype(float)
        r = r[r > 0]
        return {"etapa": etiqueta, "Gini estaciones 2025": gini(tot[tot > 0]),
                "top 10 % estaciones 2025": participacion_top(tot[tot > 0], .10),
                "H norm. día de la semana 2025": entropia(dw.values, k=7)[1],
                "domingo / lunes-viernes (mediana red 2022+)":
                    r[r.index.dayofweek == 6].median() / r[r.index.dayofweek < 5].median(),
                "top-10 estaciones 2025": ", ".join(f"{e} (L{l})" for l, e in top[:5]) + "…"}
    crudo_f = crudo.rename(columns={})
    fen = pd.DataFrame([fenomeno(crudo_f, "antes"), fenomeno(despues, "después")])
    tabla_md(fen, "verificacion_fenomeno", cfg)

    if figuras:
        plt = G.plt
        fig, axs = plt.subplots(1, 2, figsize=(11.5, 4))
        bins = np.linspace(0, 120_000, 121)
        axs[0].hist(crudo["afluencia"], bins=bins, histtype="step", lw=1.4, color=G.COLORES[1], label="antes (crudo)")
        axs[0].hist(despues["afluencia"].astype(float), bins=bins, histtype="step", lw=1.4, ls="--",
                    color=G.COLORES[0], label="después (en operación y medido)")
        axs[0].set(title="Distribución estación-día", xlabel="entradas por estación-día", ylabel="estación-días",
                   yscale="log")
        axs[0].xaxis.set_major_formatter(G.miles); axs[0].legend(fontsize=8)
        ventana = slice("2017-08-01", "2017-11-15")
        axs[1].plot(red_antes[ventana].index, red_antes[ventana] / 1e6, color=G.COLORES[1], lw=1.4,
                    label="antes: 0 en los días de gratuidad")
        axs[1].plot(red_desp[ventana].index, red_desp[ventana] / 1e6, color=G.COLORES[0], lw=1.4, ls="--",
                    marker="o", ms=2, label="después: NULL (no medido)")
        axs[1].set(title="Red diaria alrededor del 19-S de 2017", ylabel="millones de entradas", xlabel="fecha")
        axs[1].legend(fontsize=8); axs[1].tick_params(axis="x", rotation=30)
        fig.suptitle("Fig. 17 · Antes vs. después de la preparación", x=0.01, ha="left", fontweight="bold")
        fig.tight_layout()
        guardar_figura(fig, "fig17_antes_despues", cfg)
    LOG.info("  antes vs después: %d variables comparadas", tabla["variable"].nunique())
    reg.fin("verificacion", len(crudo), len(despues), "estación-días en operación y medidos")
