"""PASO 2 · CALIDAD (diagnóstico y EDA sobre los datos crudos).

Ensambla el dataset analítico al grano de E1 (estación-línea × día) sin
limpiar todavía: solo se convierten tipos y fechas y se repara la doble
codificación para poder leer los nombres. Calcula la estadística
descriptiva en las cuatro dimensiones, Gini (con curva de Lorenz) y
entropía, y produce las figuras del informe de EDA.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from . import graficas as G
from .limpieza import ORDEN_METRO, categoria_lluvia
from .utiles import (LOG, entropia, gini, guardar_figura, lorenz, participacion_top,
                     reparar_codificacion, tabla_md)

DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
PERIODOS = [("2010-2019", 2010, 2019), ("2020-2021", 2020, 2021), ("2022-2026", 2022, 2026)]


# ---------------------------------------------------------------------
# Dataset analítico crudo
# ---------------------------------------------------------------------
def integrar_crudo(cfg: dict, crudos: dict) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    r = crudos["metro"]
    m = pd.DataFrame({
        "fecha": pd.to_datetime(r["fecha"]),
        "linea_codigo": r["linea"].map(reparar_codificacion).str.extract(r"(\w+)\s*$")[0].str.upper(),
        "estacion": r["estacion"].map(reparar_codificacion),
        "afluencia": pd.to_numeric(r["afluencia"]).astype("int64"),
    })
    c = crudos["clima"]
    clima = pd.DataFrame({
        "fecha": pd.to_datetime(c["time"]),
        "precipitacion_mm": pd.to_numeric(c["precipitation_sum_mm"]),
        "lluvia_mm": pd.to_numeric(c["rain_sum_mm"]),
        "temp_max_c": pd.to_numeric(c["temperature_2m_max_c"]),
        "temp_min_c": pd.to_numeric(c["temperature_2m_min_c"]),
    })
    clima["categoria_lluvia"] = categoria_lluvia(clima["precipitacion_mm"], cfg["lluvia_mm"])
    f = crudos["festivos"]
    fest = set(pd.to_datetime(f.loc[f["types"].str.contains("Public"), "date"]))
    m = m.merge(clima, on="fecha", how="left")
    m["es_festivo_f4"] = m["fecha"].isin(fest)
    m["anio"] = m["fecha"].dt.year
    m["dia_semana"] = m["fecha"].dt.dayofweek
    m["periodo"] = pd.cut(m["anio"], [2009, 2019, 2021, 2100], labels=[p[0] for p in PERIODOS]).astype(str)
    b = crudos["metrobus"]
    mb = pd.DataFrame({
        "fecha": pd.to_datetime(b["fecha"]),
        "linea_codigo": b["linea"].map(reparar_codificacion).str.extract(r"(\d+)\s*$")[0],
        "afluencia": pd.to_numeric(b["afluencia"], errors="coerce"),
    })
    return m, mb, clima


# ---------------------------------------------------------------------
# Estadística descriptiva
# ---------------------------------------------------------------------
def describir(x: pd.Series) -> dict:
    x = pd.Series(x, dtype=float).dropna()
    q = x.quantile([0.05, 0.25, 0.5, 0.75, 0.95, 0.99])
    media = x.mean()
    moda = x.round(0).mode()
    mad = (x - x.median()).abs().median()
    return {
        "n": len(x), "media": media, "mediana": q[0.5],
        "moda": moda.iloc[0] if len(moda) else np.nan,
        "media recortada 10 %": stats.trim_mean(x, 0.10),
        "P5": q[0.05], "Q1": q[0.25], "Q3": q[0.75], "P95": q[0.95], "P99": q[0.99],
        "mínimo": x.min(), "máximo": x.max(), "rango": x.max() - x.min(),
        "varianza": x.var(), "desviación estándar": x.std(), "IQR": q[0.75] - q[0.25],
        "MAD": mad, "CV": x.std() / media if media else np.nan,
        "asimetría": stats.skew(x), "curtosis (exceso)": stats.kurtosis(x),
        "media / mediana": media / q[0.5] if q[0.5] else np.nan,
        "desv. est. / IQR": x.std() / (q[0.75] - q[0.25]) if q[0.75] > q[0.25] else np.nan,
    }


def _tabla_descriptiva(variables: dict) -> pd.DataFrame:
    d = pd.DataFrame({k: describir(v) for k, v in variables.items()})
    d.index.name = "medida"
    return d.reset_index()


# ---------------------------------------------------------------------
def ejecutar(cfg: dict, crudos: dict, reg, figuras: bool = True) -> dict:
    reg.inicio("calidad")
    m, mb, clima = integrar_crudo(cfg, crudos)
    cifras: dict[str, object] = {}

    # --- Diagnóstico de calidad por tabla y variable ------------------
    diag = []
    def fila(tabla, var, s, nota=""):
        s_txt = s.astype(str)
        diag.append({"tabla": tabla, "variable": var, "filas": len(s),
                     "vacios_o_NaN": int((s_txt.isin(["", "NaN", "nan", "None"])).sum()),
                     "ceros": int((s_txt == "0").sum()), "distintos": int(s.nunique()), "nota": nota})
    r = crudos["metro"]
    fila("metro (F1)", "fecha", r["fecha"], f"{r['fecha'].min()} a {r['fecha'].max()}")
    fila("metro (F1)", "linea", r["linea"], "24 textos para 12 líneas (doble codificación)")
    fila("metro (F1)", "estacion", r["estacion"], "nombres con doble codificación")
    fila("metro (F1)", "afluencia", r["afluencia"], "enteros >= 0")
    b = crudos["metrobus"]
    fila("metrobús (F2)", "fecha", b["fecha"], f"{b['fecha'].min()} a {b['fecha'].max()}")
    fila("metrobús (F2)", "linea", b["linea"], "14 textos para 7 líneas")
    fila("metrobús (F2)", "afluencia", b["afluencia"], "'NaN' antes de inaugurar cada línea")
    c = crudos["clima"]
    for v in ["precipitation_sum_mm", "rain_sum_mm", "temperature_2m_max_c", "temperature_2m_min_c"]:
        fila("clima (F5)", v, c[v])
    fila("festivos (F4)", "date", crudos["festivos"]["date"], "festivos y Semana Santa 2010-2026")
    fila("sismos (F6)", "mag", crudos["sismos"]["mag"], "M >= 6.0 a <= 800 km")
    fila("gtfs (F3)", "stop_id (Metro)", crudos["gtfs_stops"]["stop_id"][
        crudos["gtfs_stops"]["stop_id"].str.startswith("B_02")], "195 paradas del Metro")
    tabla_md(pd.DataFrame(diag), "diagnostico_calidad", cfg)

    dup_llave = int(m.duplicated(["fecha", "linea_codigo", "estacion"]).sum())
    cifras.update({
        "filas dataset analítico": len(m), "variables dataset analítico": m.shape[1],
        "días": m["fecha"].nunique(), "estaciones-línea por día": int(m.groupby("fecha").size().iloc[0]),
        "primera fecha": m["fecha"].min().date(), "última fecha": m["fecha"].max().date(),
        "ceros Metro": int((m["afluencia"] == 0).sum()),
        "porcentaje de ceros Metro": (m["afluencia"] == 0).mean(),
        "llave natural duplicada (filas extra)": dup_llave,
        "NaN Metrobús": int(mb["afluencia"].isna().sum()),
    })

    # --- Descriptiva en las cuatro dimensiones -------------------------
    red = m.groupby("fecha")["afluencia"].sum()
    base_red = red.groupby(red.index.dayofweek).transform(lambda s: s.shift(1).rolling(4, min_periods=1).median())
    bajos = (red / base_red)[(red / base_red) < cfg["limpieza"]["umbral_sin_medicion"]]
    cifras["días con la red < 10 % de su nivel habitual"] = ", ".join(f"{d:%Y-%m-%d}" for d in bajos.index)
    cifras["días con 0 en las 195 estaciones"] = int((m.groupby("fecha")["afluencia"].sum() == 0).sum())
    mb10 =mb[(mb["fecha"] >= cfg["periodo"]["inicio"])]
    desc = _tabla_descriptiva({
        "afluencia estación-día (Metro)": m["afluencia"],
        "afluencia estación-día > 0 (Metro)": m.loc[m["afluencia"] > 0, "afluencia"],
        "afluencia diaria de la red (Metro)": red,
        "afluencia línea-día (Metrobús)": mb10["afluencia"],
        "precipitación diaria (mm)": clima["precipitacion_mm"],
        "temperatura máxima (°C)": clima["temp_max_c"],
    })
    tabla_md(desc, "eda_descriptiva", cfg)

    # Por grupo: línea, día de la semana y periodo
    post = m[m["anio"] >= 2022]
    por_linea = (post.groupby("linea_codigo")["afluencia"]
                 .agg(n="size", media="mean", mediana="median", desv_est="std",
                      Q1=lambda s: s.quantile(.25), Q3=lambda s: s.quantile(.75),
                      ceros=lambda s: (s == 0).sum())
                 .reindex(ORDEN_METRO))
    por_linea["IQR"] = por_linea["Q3"] - por_linea["Q1"]
    por_linea["CV"] = por_linea["desv_est"] / por_linea["media"]
    por_linea["participacion_total"] = post.groupby("linea_codigo")["afluencia"].sum() / post["afluencia"].sum()
    por_linea = por_linea.sort_values("mediana", ascending=False)
    tabla_md(por_linea.drop(columns=["Q1", "Q3"]).reset_index().rename(columns={"linea_codigo": "línea"}),
             "eda_por_linea", cfg)

    red_post = red[red.index.year >= 2022]
    red_post = red_post[red_post > 0]
    por_dia = red_post.groupby(red_post.index.dayofweek).agg(["size", "mean", "median", "std",
                                                              lambda s: s.quantile(.75) - s.quantile(.25)])
    por_dia.columns = ["días", "media", "mediana", "desv_est", "IQR"]
    por_dia["CV"] = por_dia["desv_est"] / por_dia["media"]
    por_dia["vs_mediana_lun_vie"] = por_dia["mediana"] / red_post[red_post.index.dayofweek < 5].median()
    por_dia.index = [DIAS[i] for i in por_dia.index]
    tabla_md(por_dia.reset_index().rename(columns={"index": "día"}), "eda_por_dia_semana", cfg)

    filas_p = []
    for nombre, a0, a1 in PERIODOS:
        s = m[(m["anio"] >= a0) & (m["anio"] <= a1)]
        rd = red[(red.index.year >= a0) & (red.index.year <= a1)]
        rd = rd[rd > 0]
        tot_est = s.groupby(["linea_codigo", "estacion"])["afluencia"].sum()
        filas_p.append({"periodo": nombre, "días": s["fecha"].nunique(),
                        "media red/día": rd.mean(), "mediana red/día": rd.median(),
                        "desv. est. red/día": rd.std(), "IQR red/día": rd.quantile(.75) - rd.quantile(.25),
                        "mediana estación-día": s["afluencia"].median(),
                        "% ceros": (s["afluencia"] == 0).mean(),
                        "Gini estaciones": gini(tot_est[tot_est > 0])})
    tabla_md(pd.DataFrame(filas_p), "eda_por_periodo", cfg)

    # --- Concentración: Gini y Lorenz ----------------------------------
    anual_est = m.groupby(["anio", "linea_codigo", "estacion"])["afluencia"].sum().reset_index()
    anual_lin = m.groupby(["anio", "linea_codigo"])["afluencia"].sum().reset_index()
    mb_ok = mb10.dropna()
    anual_mb = mb_ok.groupby([mb_ok["fecha"].dt.year, "linea_codigo"])["afluencia"].sum().reset_index()
    anual_mb.columns = ["anio", "linea_codigo", "afluencia"]
    filas_g = []
    for a, g in anual_est.groupby("anio"):
        x = g.loc[g["afluencia"] > 0, "afluencia"]
        gl = anual_lin.loc[anual_lin["anio"] == a, "afluencia"]
        gm = anual_mb.loc[anual_mb["anio"] == a, "afluencia"]
        dias = m.loc[m["anio"] == a, "fecha"].nunique()
        filas_g.append({"año": a, "días": dias, "estaciones con entradas": len(x),
                        "Gini estaciones": gini(x), "top 10 % estaciones": participacion_top(x, .10),
                        "Gini líneas Metro": gini(gl[gl > 0]),
                        "líneas Metrobús": int((gm > 0).sum()), "Gini líneas Metrobús": gini(gm[gm > 0])})
    gini_anual = pd.DataFrame(filas_g)
    tabla_md(gini_anual, "eda_gini_por_anio", cfg)

    pr = clima.set_index("fecha")["precipitacion_mm"]
    filas_ll = []
    for a, s in pr.groupby(pr.index.year):
        dias_lluvia = (s >= cfg["lluvia_mm"]["ligera"]).sum()
        filas_ll.append({"año": a, "días": len(s), "días con lluvia": dias_lluvia,
                         "mm totales": s.sum(), "Gini días": gini(s),
                         "% del total en el 10 % de días más lluviosos": participacion_top(s, .10)})
    gini_lluvia = pd.DataFrame(filas_ll)
    tabla_md(gini_lluvia, "eda_gini_lluvia", cfg)
    cifras.update({
        "Gini lluvia 2010-2026 (días)": gini(pr), "top 10 % días lluvia": participacion_top(pr, .10),
        "días sin lluvia (%)": (pr < cfg["lluvia_mm"]["ligera"]).mean(),
    })

    # --- Heterogeneidad: entropía normalizada ------------------------------
    filas_h = []
    def entrada(var, grupo, conteos, nota=""):
        p = conteos / conteos.sum()
        h, hn = entropia(p.values, k=len(conteos))
        filas_h.append({"variable": var, "ámbito": grupo, "K": len(conteos), "moda": p.idxmax(),
                        "proporción de la moda": p.max(), "H (bits)": h, "H normalizada": hn, "nota": nota})
    entrada("línea (filas)", "2022-2026", post["linea_codigo"].value_counts(),
            "reparto de estaciones entre líneas")
    entrada("línea (entradas)", "2022-2026", post.groupby("linea_codigo")["afluencia"].sum(),
            "reparto de la demanda entre líneas")
    entrada("línea Metrobús (entradas)", "2022-2026",
            mb_ok[mb_ok["fecha"].dt.year >= 2022].groupby("linea_codigo")["afluencia"].sum())
    entrada("día de la semana (entradas)", "2022-2026", post.groupby("dia_semana")["afluencia"].sum()
            .rename(index=dict(enumerate(DIAS))))
    entrada("categoría de lluvia (días)", "2010-2026", clima["categoria_lluvia"].value_counts())
    temporada = clima[clima["fecha"].dt.month.isin([6, 7, 8, 9])]
    seca = clima[clima["fecha"].dt.month.isin([12, 1, 2, 3])]
    entrada("categoría de lluvia (días)", "jun-sep (lluvias)", temporada["categoria_lluvia"].value_counts())
    entrada("categoría de lluvia (días)", "dic-mar (secas)", seca["categoria_lluvia"].value_counts())
    tipo_reg = np.where(m["afluencia"] > 0, "positivo", "cero")
    entrada("tipo de registro", "2010-2026", pd.Series(tipo_reg).value_counts())
    tabla_md(pd.DataFrame(filas_h), "eda_entropia", cfg)

    # Entropía del perfil semanal de cada estación (P3)
    perfil = (post[post["afluencia"] > 0].groupby(["linea_codigo", "estacion", "dia_semana"])["afluencia"]
              .mean().unstack())
    part = perfil.div(perfil.sum(axis=1), axis=0)
    hn = part.apply(lambda r: entropia(r.values, k=7)[1], axis=1)
    ent_est = pd.DataFrame({"H normalizada": hn, "participación sáb+dom": part[[5, 6]].sum(axis=1),
                            "media diaria": perfil.mean(axis=1)}).reset_index()
    resumen_ent = ent_est.sort_values("H normalizada")
    tabla_md(pd.concat([resumen_ent.head(5), resumen_ent.tail(5)]).rename(
        columns={"linea_codigo": "línea"}), "eda_entropia_perfil_extremos", cfg)
    cifras.update({"H normalizada perfil semanal: mínima": hn.min(), "máxima": hn.max(),
                   "mediana": hn.median(),
                   "correlación Spearman H vs media diaria": stats.spearmanr(ent_est["H normalizada"],
                                                                            ent_est["media diaria"])[0]})

    # Entropía por año del reparto entre líneas
    filas_hl = []
    for a, g in anual_lin.groupby("anio"):
        filas_hl.append({"año": a, "H norm. líneas Metro": entropia(g["afluencia"].values, k=12)[1],
                         "H norm. líneas Metrobús": entropia(
                             anual_mb.loc[anual_mb["anio"] == a, "afluencia"].values,
                             k=max(2, int((anual_mb["anio"] == a).sum())))[1]})
    ent_anual = pd.DataFrame(filas_hl)
    tabla_md(ent_anual, "eda_entropia_lineas_por_anio", cfg)

    # --- Alta demanda: cociente contra la línea base ingenua (P1 -> P2) ---
    s = m[(m["afluencia"] > 0)].sort_values(["linea_codigo", "estacion", "fecha"]).copy()
    s["base"] = (s.groupby(["linea_codigo", "estacion", "dia_semana"])["afluencia"]
                  .transform(lambda v: v.shift(1).rolling(4, min_periods=4).mean()))
    s["cociente"] = s["afluencia"] / s["base"]
    sp = s[(s["anio"] >= 2022) & s["base"].notna()]
    umbral = cfg["alta_demanda"]["umbral_vs_base"]
    qs = sp["cociente"].quantile([.5, .9, .95, .99])
    cifras.update({"cociente vs base: mediana": qs[.5], "P90": qs[.9], "P95": qs[.95], "P99": qs[.99],
                   f"% estación-días > {umbral} x base (2022+)": (sp["cociente"] > umbral).mean()})
    por_anio_ad = sp.groupby("anio")["cociente"].apply(lambda v: (v > umbral).mean())
    tabla_md(pd.DataFrame({"año": por_anio_ad.index, f"% > {umbral} x base": por_anio_ad.values,
                           "estación-días": sp.groupby("anio").size().values}), "eda_alta_demanda_por_anio", cfg)

    # Lluvia vs desviación de la base: resultado negativo
    sp2 = sp.dropna(subset=["precipitacion_mm"])
    rho, p = stats.spearmanr(sp2["precipitacion_mm"], sp2["cociente"])
    por_cat = sp2.groupby("categoria_lluvia")["cociente"].agg(["size", "median", "mean"])
    por_cat["% > umbral"] = sp2.groupby("categoria_lluvia")["cociente"].apply(lambda v: (v > umbral).mean())
    tabla_md(por_cat.reindex(["sin_lluvia", "ligera", "moderada", "fuerte"]).reset_index(),
             "eda_lluvia_vs_alta_demanda", cfg)
    cifras.update({"Spearman lluvia vs cociente": rho, "p-valor": p})

    tabla_md(pd.DataFrame({"cifra": list(cifras.keys()), "valor": list(cifras.values())}), "eda_cifras", cfg)

    if figuras:
        _figuras(cfg, m, mb, clima, red, anual_est, gini_anual, gini_lluvia, ent_est, ent_anual, sp, post)
    reg.fin("calidad", len(m), len(m), f"dataset analítico crudo: {len(m):,} × {m.shape[1]}")
    return {"crudo": m}


# ---------------------------------------------------------------------
# Figuras del EDA
# ---------------------------------------------------------------------
def _figuras(cfg, m, mb, clima, red, anual_est, gini_anual, gini_lluvia, ent_est, ent_anual, sp, post):
    plt = G.plt
    umbral = cfg["alta_demanda"]["umbral_vs_base"]

    # Fig. 1 · Serie diaria de la red
    fig, ax = G.figura(10, 4.2)
    ax.plot(red.index, red.values / 1e6, color=G.GRIS, lw=0.4, label="día")
    ax.plot(red.index, red.rolling(28, center=True).mean() / 1e6, color=G.COLORES[0], lw=1.6,
            label="media móvil de 28 días")
    eventos = [("2012-10-30", "Abre L12"), ("2016-03-16", "Contingencia\n(gratuidad)"),
               ("2017-09-20", "Gratuidad 19-S\n(0 registrado)"),
               ("2020-03-23", "Pandemia"), ("2021-01-09", "Incendio PCC"), ("2021-05-04", "Cierre L12"),
               ("2022-07-11", "Obra L1"), ("2025-11-16", "Reabre L1")]
    for f, t in eventos:
        x = pd.Timestamp(f)
        ax.axvline(x, color=G.COLORES[1], lw=0.7, ls="--")
        ax.text(x, 7.55, t, fontsize=7, rotation=90, va="top", ha="right", color=G.TINTA)
    ax.set(title="Fig. 1 · Entradas diarias a la red del Metro, 2010-2026 (datos crudos)",
           ylabel="millones de entradas por día", xlabel="fecha", ylim=(0, 7.6))
    ax.legend(loc="lower left")
    G.fuente(ax, "Fuente: F1 (SEMOVI). Suma de las 195 estaciones-línea por día, sin limpiar.")
    guardar_figura(fig, "fig01_serie_red", cfg)

    # Fig. 2 · Distribución de la afluencia estación-día
    fig, axs = plt.subplots(1, 3, figsize=(11, 3.6))
    x = m["afluencia"]
    axs[0].hist(x / 1e3, bins=60, color=G.COLORES[0], density=True, label="60 bins")
    axs[0].hist(x / 1e3, bins=200, histtype="step", color=G.COLORES[1], lw=0.9, density=True, label="200 bins")
    axs[0].set(title="Escala lineal (dos anchos de bin)", xlabel="miles de entradas por estación-día",
               ylabel="densidad")
    axs[0].legend(fontsize=8)
    axs[1].hist(np.log10(x[x > 0]), bins=60, color=G.COLORES[2])
    axs[1].set(title="Escala log10 (sin ceros)", xlabel="log10(entradas)", ylabel="estación-días")
    axs[1].yaxis.set_major_formatter(G.miles)
    axs[2].boxplot(x / 1e3, vert=False, widths=0.5, flierprops={"markersize": 1, "alpha": 0.2},
                   medianprops={"color": G.COLORES[1], "lw": 1.6})
    axs[2].set(title="Diagrama de caja", xlabel="miles de entradas por estación-día", yticks=[])
    fig.suptitle("Fig. 2 · Distribución de las entradas por estación-día, 2010-2026", x=0.01, ha="left",
                 fontweight="bold")
    fig.tight_layout()
    guardar_figura(fig, "fig02_distribucion_afluencia", cfg)

    # Fig. 3 · Caja por línea ordenada por mediana (2022+)
    orden = post.groupby("linea_codigo")["afluencia"].median().sort_values(ascending=False).index
    fig, ax = G.figura(10, 4.2)
    ax.boxplot([post.loc[post["linea_codigo"] == l, "afluencia"] for l in orden], labels=[f"L{l}" for l in orden],
               flierprops={"markersize": 1, "alpha": 0.15}, medianprops={"color": G.COLORES[1], "lw": 1.6})
    ax.set(title="Fig. 3 · Entradas por estación-día según la línea, 2022-2026 (ordenadas por mediana)",
           ylabel="entradas por estación-día", xlabel="línea del Metro")
    ax.yaxis.set_major_formatter(G.miles)
    G.fuente(ax, "Incluye los ceros de cierres (puntos en 0); la caja va del Q1 al Q3 y la línea naranja es la mediana.")
    guardar_figura(fig, "fig03_caja_por_linea", cfg)

    # Fig. 4 · Mapa de calor línea × día de la semana (mediana estación-día, 2022+)
    pos = post[post["afluencia"] > 0]
    tab = pos.groupby(["linea_codigo", "dia_semana"])["afluencia"].median().unstack().reindex(orden)
    fig, ax = G.figura(8, 4.8)
    im = ax.imshow(tab.values, cmap="cividis", aspect="auto")
    ax.set_xticks(range(7)); ax.set_xticklabels(DIAS)
    ax.set_yticks(range(len(tab))); ax.set_yticklabels([f"L{l}" for l in tab.index])
    ax.grid(False)
    for i in range(tab.shape[0]):
        for j in range(7):
            v = tab.values[i, j]
            ax.text(j, i, f"{v / 1000:.1f}", ha="center", va="center", fontsize=7.5,
                    color="white" if v < np.nanmedian(tab.values) else "black")
    fig.colorbar(im, ax=ax, label="mediana de entradas por estación-día", format=G.miles)
    ax.set(title="Fig. 4 · Mediana de entradas por estación-día: línea × día de la semana (miles, 2022-2026)")
    guardar_figura(fig, "fig04_calor_linea_dia", cfg)

    # Fig. 5 · Curvas de Lorenz de estaciones + Gini por año
    fig, axs = plt.subplots(1, 2, figsize=(11, 4.2))
    estilos = ["-", "--", ":", "-."]
    for k, a in enumerate([2013, 2019, 2021, 2025]):
        x = anual_est.loc[(anual_est["anio"] == a) & (anual_est["afluencia"] > 0), "afluencia"]
        p, l = lorenz(x)
        axs[0].plot(p, l, ls=estilos[k], color=G.COLORES[k], lw=1.6, label=f"{a} (G = {gini(x):.3f})")
    axs[0].plot([0, 1], [0, 1], color=G.GRIS, lw=0.8, label="igualdad perfecta")
    axs[0].set(title="Curva de Lorenz: estaciones-línea", xlabel="proporción acumulada de estaciones (de menor a mayor)",
               ylabel="proporción acumulada de entradas")
    axs[0].xaxis.set_major_formatter(G.pct); axs[0].yaxis.set_major_formatter(G.pct)
    axs[0].legend(fontsize=8)
    g = gini_anual
    axs[1].plot(g["año"], g["Gini estaciones"], marker="o", color=G.COLORES[0], label="estaciones-línea (195)")
    axs[1].plot(g["año"], g["Gini líneas Metro"], marker="s", ls="--", color=G.COLORES[1], label="líneas Metro (12)")
    axs[1].plot(g["año"], g["Gini líneas Metrobús"], marker="^", ls=":", color=G.COLORES[2],
                label="líneas Metrobús (en servicio)")
    axs[1].axvspan(2019.5, 2021.5, color="#EEE", zorder=0)
    axs[1].set(title="Coeficiente de Gini por año", xlabel="año", ylabel="Gini", ylim=(0, 0.6))
    axs[1].legend(fontsize=8)
    fig.suptitle("Fig. 5 · Concentración de las entradas entre estaciones y líneas", x=0.01, ha="left",
                 fontweight="bold")
    fig.tight_layout()
    guardar_figura(fig, "fig05_lorenz_gini_estaciones", cfg)

    # Fig. 6 · Pareto de estaciones (2025)
    x = (anual_est[anual_est["anio"] == 2025].assign(et=lambda d: d["estacion"] + " (L" + d["linea_codigo"] + ")")
         .sort_values("afluencia", ascending=False))
    top = x.head(25)
    fig, ax = G.figura(11, 4.4)
    ax.bar(range(len(top)), top["afluencia"] / 1e6, color=G.COLORES[0])
    ax.set_xticks(range(len(top))); ax.set_xticklabels(top["et"], rotation=70, ha="right", fontsize=7.5)
    ax.set_ylabel("millones de entradas en 2025")
    ax2 = ax.twinx()
    ax2.plot(range(len(top)), (top["afluencia"].cumsum() / x["afluencia"].sum()).values, color=G.COLORES[1],
             marker="o", ms=3)
    ax2.set_ylabel("% acumulado del total de la red"); ax2.yaxis.set_major_formatter(G.pct)
    ax2.set_ylim(0, 0.6); ax2.grid(False); ax2.spines["right"].set_visible(True)
    ax.set_title("Fig. 6 · Pareto: las 25 estaciones-línea con más entradas en 2025")
    guardar_figura(fig, "fig06_pareto_estaciones", cfg)

    # Fig. 7 · Lorenz de la lluvia
    fig, axs = plt.subplots(1, 2, figsize=(11, 4))
    pr = clima["precipitacion_mm"]
    p, l = lorenz(pr)
    axs[0].plot(p, l, color=G.COLORES[0], lw=1.8, label=f"2010-2026 (G = {gini(pr):.3f})")
    axs[0].plot([0, 1], [0, 1], color=G.GRIS, lw=0.8, label="igualdad perfecta")
    axs[0].set(title="Curva de Lorenz: precipitación por día", xlabel="proporción acumulada de días",
               ylabel="proporción acumulada de lluvia")
    axs[0].xaxis.set_major_formatter(G.pct); axs[0].yaxis.set_major_formatter(G.pct); axs[0].legend(fontsize=8)
    gl = gini_lluvia
    axs[1].bar(gl["año"], gl["Gini días"], color=G.COLORES[2])
    axs[1].set(title="Gini de la lluvia diaria por año", xlabel="año", ylabel="Gini", ylim=(0.5, 1))
    axs[1].set_xticks(gl["año"][::2]); axs[1].set_xticklabels(gl["año"][::2], rotation=45)
    fig.suptitle("Fig. 7 · Concentración de la lluvia: pocos días acumulan casi toda la precipitación", x=0.01,
                 ha="left", fontweight="bold")
    fig.tight_layout()
    guardar_figura(fig, "fig07_lorenz_lluvia", cfg)

    # Fig. 8 · Entropía del perfil semanal por estación (P3)
    fig, axs = plt.subplots(1, 2, figsize=(11, 4))
    axs[0].hist(ent_est["H normalizada"], bins=30, color=G.COLORES[3])
    axs[0].set(title="Distribución entre las 195 estaciones", xlabel="entropía normalizada del perfil semanal",
               ylabel="estaciones")
    axs[1].scatter(ent_est["participación sáb+dom"], ent_est["H normalizada"], s=14, alpha=0.7,
                   color=G.COLORES[0], edgecolor="none")
    axs[1].set(title="Más fin de semana = perfil más parejo", xlabel="participación de sábado y domingo",
               ylabel="entropía normalizada")
    axs[1].xaxis.set_major_formatter(G.pct)
    fig.suptitle("Fig. 8 · Heterogeneidad del perfil semanal de cada estación, 2022-2026", x=0.01,
                 ha="left", fontweight="bold")
    fig.tight_layout()
    guardar_figura(fig, "fig08_entropia_perfil_semanal", cfg)

    # Fig. 9 · Lluvia: categorías y temporada
    fig, axs = plt.subplots(1, 2, figsize=(11, 4))
    cats = ["sin_lluvia", "ligera", "moderada", "fuerte"]
    vc = clima["categoria_lluvia"].value_counts().reindex(cats)
    orden_c = vc.sort_values(ascending=False)
    axs[0].bar(orden_c.index, orden_c.values, color=G.COLORES[0])
    axs[0].set(title="Días por categoría (ordenadas por frecuencia)", ylabel="días", xlabel="categoría SMN")
    tab = pd.crosstab(clima["fecha"].dt.month, clima["categoria_lluvia"], normalize="index").reindex(columns=cats)
    abajo = np.zeros(12)
    tonos = ["#E6E8ED", "#9DB4E0", "#3A64B8", "#14254F"]
    for c, t in zip(cats, tonos):
        axs[1].bar(tab.index, tab[c].values, bottom=abajo, color=t, label=c, edgecolor="white", lw=0.4)
        abajo += tab[c].values
    axs[1].set(title="Composición por mes (barras al 100 %)", xlabel="mes", ylabel="proporción de días")
    axs[1].set_xticks(range(1, 13)); axs[1].yaxis.set_major_formatter(G.pct)
    axs[1].legend(fontsize=7.5, ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.15))
    fig.suptitle("Fig. 9 · Categoría de lluvia diaria en la CDMX, 2010-2026", x=0.01, ha="left", fontweight="bold")
    fig.tight_layout()
    guardar_figura(fig, "fig09_lluvia_categorias", cfg)

    # Fig. 10 · Lluvia vs desviación de la base (resultado negativo)
    fig, ax = G.figura(8.5, 4.2)
    s = sp.dropna(subset=["precipitacion_mm"])
    s = s[s["cociente"].between(0, 3)]
    hb = ax.hexbin(s["precipitacion_mm"], s["cociente"], gridsize=45, bins="log", cmap="cividis", mincnt=1)
    ax.axhline(1, color="white", lw=0.8)
    ax.axhline(umbral, color=G.COLORES[1], lw=1, ls="--", label=f"umbral de alta demanda ({umbral} × base)")
    fig.colorbar(hb, ax=ax, label="estación-días (escala log)")
    ax.set(title="Fig. 10 · Lluvia del día vs entradas respecto de la base ingenua (2022-2026)",
           xlabel="precipitación del día (mm)", ylabel="entradas / media de las 4 semanas previas")
    ax.legend(loc="upper right", fontsize=8)
    guardar_figura(fig, "fig10_lluvia_vs_cociente", cfg)

    # Fig. 11 · Patrón de ceros: línea × año
    z = m.assign(cero=m["afluencia"] == 0).groupby(["linea_codigo", "anio"])["cero"].mean().unstack().reindex(ORDEN_METRO)
    fig, ax = G.figura(10, 4.4)
    im = ax.imshow(z.values, cmap="Greys", aspect="auto", vmin=0, vmax=1)
    ax.set_xticks(range(z.shape[1])); ax.set_xticklabels(z.columns, rotation=45)
    ax.set_yticks(range(len(z))); ax.set_yticklabels([f"L{l}" for l in z.index]); ax.grid(False)
    for i in range(z.shape[0]):
        for j in range(z.shape[1]):
            v = z.values[i, j]
            if v >= 0.005:
                ax.text(j, i, f"{v:.0%}", ha="center", va="center", fontsize=6.5,
                        color="white" if v > 0.5 else "black")
    fig.colorbar(im, ax=ax, label="% de estación-días en cero", format=G.pct)
    ax.set(title="Fig. 11 · Dónde están los ceros: % de estación-días con 0 entradas por línea y año")
    guardar_figura(fig, "fig11_ceros_linea_anio", cfg)

    # Fig. 12 · Red por día de la semana (2022+)
    r = red[(red.index.year >= 2022) & (red > 0)]
    fig, ax = G.figura(8, 3.8)
    datos = [r[r.index.dayofweek == d].values / 1e6 for d in range(7)]
    ax.boxplot(datos, labels=DIAS, flierprops={"markersize": 2, "alpha": 0.4},
               medianprops={"color": G.COLORES[1], "lw": 1.6})
    ax.set(title="Fig. 12 · Entradas diarias a la red por día de la semana, 2022-2026",
           ylabel="millones de entradas por día", xlabel="día de la semana")
    G.fuente(ax, "Los puntos bajos entre semana son festivos, vacaciones y días de cierre de líneas.")
    guardar_figura(fig, "fig12_red_por_dia_semana", cfg)

    # Fig. 13 · Cociente contra la base ingenua (define el umbral de P2)
    fig, ax = G.figura(8.5, 3.8)
    c = sp["cociente"].clip(0, 2.5)
    ax.hist(c, bins=120, color=G.COLORES[0])
    ax.axvline(umbral, color=G.COLORES[1], ls="--", lw=1.4,
               label=f"umbral {umbral}: {(sp['cociente'] > umbral).mean():.1%} de los estación-días")
    ax.set(title="Fig. 13 · Entradas del día / media del mismo día en las 4 semanas previas (2022-2026)",
           xlabel="cociente (1 = igual a la base)", ylabel="estación-días")
    ax.yaxis.set_major_formatter(G.miles); ax.legend()
    guardar_figura(fig, "fig13_cociente_base", cfg)

    # Fig. 14 · P5: Metrobús alrededor del cierre de L1
    fig, ax = G.figura(10, 4.2)
    mbv = mb.dropna()
    mbv = mbv[mbv["fecha"] >= "2019-01-01"]
    piv = mbv.pivot_table(index="fecha", columns="linea_codigo", values="afluencia").rolling(28, center=True).mean()
    for k, l in enumerate(piv.columns):
        ax.plot(piv.index, piv[l] / 1e3, lw=1.2, color=G.COLORES[k % 6], ls=["-", "--", ":", "-."][k % 4],
                label=f"Metrobús L{l}")
    l1 = m[(m["linea_codigo"] == "1") & (m["fecha"] >= "2019-01-01")].groupby("fecha")["afluencia"].sum()
    ax.plot(l1.index, l1.rolling(28, center=True).mean() / 1e3, color=G.TINTA, lw=2, label="Metro L1")
    ax.axvspan(pd.Timestamp("2022-07-11"), pd.Timestamp("2025-11-15"), color="#F1E3D3", zorder=0,
               label="obra de la L1")
    ax.set(title="Fig. 14 · Entradas diarias (media móvil de 28 días) del Metrobús y de la Línea 1 del Metro",
           ylabel="miles de entradas por día", xlabel="fecha")
    ax.legend(ncol=5, fontsize=7.5, loc="upper center", bbox_to_anchor=(0.5, -0.14))
    guardar_figura(fig, "fig14_metrobus_cierre_l1", cfg)
    LOG.info("  figuras del EDA: 14 guardadas en %s", cfg["salidas"]["figuras"])
