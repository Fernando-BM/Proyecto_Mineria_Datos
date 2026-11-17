"""PASO 4 · REDUCCIÓN DE DIMENSIONALIDAD.

Arma el dataset analítico limpio (una fila por estación-línea × día en
operación, 2022 en adelante) con todas las variables candidatas y aplica
chi-cuadrada + V de Cramér, correlación de Spearman y PCA. Todo lo que
aprende parámetros (cortes de discretización, estandarización, PCA) se
ajusta SOLO con la partición de entrenamiento (fecha <= fin_entrenamiento)
para no filtrar información del periodo de prueba.
Produce la tabla de decisión por variable.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

from . import graficas as G
from .utiles import LOG, entropia, guardar_figura, tabla_md


def dataset_analitico(cfg: dict, limpio: dict) -> pd.DataFrame:
    m = limpio["metro"].copy()
    m = m[m["afluencia"].notna()].sort_values(["linea_codigo", "estacion", "fecha"])
    m["afluencia"] = m["afluencia"].astype(float)
    m["dia_semana_num"] = m["fecha"].dt.dayofweek + 1
    g = m.groupby(["linea_codigo", "estacion"])["afluencia"]
    m["afluencia_t_menos_1"] = g.shift(1)
    m["afluencia_t_menos_7"] = g.shift(7)
    m["base_ingenua_4sem"] = (m.groupby(["linea_codigo", "estacion", "dia_semana_num"])["afluencia"]
                              .transform(lambda s: s.shift(1).rolling(4, min_periods=1).mean()))
    cal = limpio["calendario"]
    m = m.merge(cal, on="fecha", how="left").merge(limpio["clima"], on="fecha", how="left")
    est = limpio["estaciones"][["linea_codigo", "nombre_en_fuente", "latitud", "longitud", "es_correspondencia"]]
    m = m.merge(est, left_on=["linea_codigo", "estacion"], right_on=["linea_codigo", "nombre_en_fuente"],
                how="left").drop(columns="nombre_en_fuente")
    m["anio"] = m["fecha"].dt.year
    m["mes"] = m["fecha"].dt.month
    m["dia"] = m["fecha"].dt.day
    m["semana_iso"] = m["fecha"].dt.isocalendar().week.astype(int).values
    m["es_fin_de_semana"] = m["dia_semana_num"] >= 6
    m["es_dia_quincena"] = (m["dia"] == 15) | m["fecha"].dt.is_month_end
    m["evento_masivo"] = m["evento_masivo"].fillna("ninguno")
    m["sismo_magnitud_max"] = m["sismo_magnitud_max"].fillna(0.0)
    umbral = cfg["alta_demanda"]["umbral_vs_base"]
    m["es_alta_demanda"] = m["afluencia"] > umbral * m["base_ingenua_4sem"]
    ini = pd.Timestamp(cfg["reduccion"]["inicio_modelado"])
    a = m[(m["fecha"] >= ini) & (m["estado_servicio"] == "operando") & m["base_ingenua_4sem"].notna()].copy()
    a["particion"] = np.where(a["fecha"] <= pd.Timestamp(cfg["reduccion"]["fin_entrenamiento"]),
                              "entrenamiento", "prueba")
    return a.reset_index(drop=True)


def cramer_v(tabla: pd.DataFrame) -> tuple[float, float, int, float, float]:
    chi2, p, gl, esperadas = stats.chi2_contingency(tabla.values, correction=False)
    n = tabla.values.sum()
    r, k = tabla.shape
    v = np.sqrt(chi2 / (n * (min(r, k) - 1)))
    return chi2, p, gl, v, float(esperadas.min())


def ejecutar(cfg: dict, limpio: dict, reg, figuras: bool = True) -> pd.DataFrame:
    reg.inicio("reduccion")
    rc = cfg["reduccion"]
    a = dataset_analitico(cfg, limpio)
    tr = a[a["particion"] == "entrenamiento"]
    LOG.info("  dataset analítico: %s filas (%s entrenamiento, %s prueba), %d columnas",
             f"{len(a):,}", f"{len(tr):,}", f"{(a.particion == 'prueba').sum():,}", a.shape[1])
    y = tr["es_alta_demanda"]

    # --- Chi-cuadrada + V de Cramér contra la etiqueta de alta demanda (solo entrenamiento)
    q_temp = tr["temp_max_c"].quantile([.25, .5, .75]).values      # cortes aprendidos en entrenamiento
    tr = tr.assign(temp_max_cuartil=pd.cut(tr["temp_max_c"], [-np.inf, *q_temp, np.inf],
                                           labels=["Q1", "Q2", "Q3", "Q4"]).astype(str),
                   sismo=tr["es_dia_sismo"].astype(bool))
    categoricas = {
        "dia_semana_num": "día de la semana (7)", "mes": "mes (12)", "es_fin_de_semana": "fin de semana",
        "es_dia_quincena": "día de quincena", "es_festivo_oficial": "festivo LFT",
        "es_semana_santa": "Jueves/Viernes Santo", "evento_masivo": "evento masivo (6)",
        "sismo": "día con sismo", "categoria_lluvia": "categoría de lluvia (4)",
        "temp_max_cuartil": "temperatura máx. (cuartiles de entrenamiento)",
        "linea_codigo": "línea (12)", "es_correspondencia": "estación de correspondencia",
        "es_atipico": "marca de atípico",
    }
    filas = []
    for var, desc in categoricas.items():
        t = pd.crosstab(tr[var], y)
        chi2, p, gl, v, emin = cramer_v(t)
        filas.append({"variable": var, "descripción": desc, "categorías": t.shape[0], "chi2": chi2, "gl": gl,
                      "p": p, "frec. esperada mínima": emin, "V de Cramér": v})
    chi = pd.DataFrame(filas)
    alfa_bonf = rc["alfa"] / len(chi)
    chi["p ajustada (Bonferroni)"] = np.minimum(chi["p"] * len(chi), 1.0)
    chi["significativa"] = chi["p"] < alfa_bonf
    chi["efecto >= V mín."] = chi["V de Cramér"] >= rc["v_cramer_min"]
    chi = chi.sort_values("V de Cramér", ascending=False)
    tabla_md(chi.drop(columns=["p"]), "reduccion_chi2", cfg)

    # --- Correlación de Spearman entre numéricas (solo entrenamiento)
    numericas = ["afluencia", "afluencia_t_menos_1", "afluencia_t_menos_7", "base_ingenua_4sem",
                 "precipitacion_mm", "lluvia_mm", "temp_max_c", "temp_min_c", "sismo_magnitud_max",
                 "latitud", "longitud", "anio", "mes", "semana_iso", "dia"]
    muestra_corr = tr[numericas].sample(n=min(200_000, len(tr)), random_state=cfg["semilla"])
    rho = muestra_corr.corr(method="spearman")
    tabla_md(rho.round(3).reset_index().rename(columns={"index": "variable"}), "reduccion_spearman", cfg)
    pares = []
    for i, v1 in enumerate(numericas):
        for v2 in numericas[i + 1:]:
            if abs(rho.loc[v1, v2]) >= rc["rho_redundancia"]:
                pares.append({"variable 1": v1, "variable 2": v2, "rho de Spearman": rho.loc[v1, v2]})
    tabla_md(pd.DataFrame(pares), "reduccion_pares_redundantes", cfg)
    # Relación con el objetivo, en escala relativa (cociente contra la base)
    rel = tr.assign(cociente=tr["afluencia"] / tr["base_ingenua_4sem"],
                    c1=tr["afluencia_t_menos_1"] / tr["base_ingenua_4sem"],
                    c7=tr["afluencia_t_menos_7"] / tr["base_ingenua_4sem"])
    obj = []
    for v in ["c1", "c7", "precipitacion_mm", "temp_max_c", "temp_min_c", "sismo_magnitud_max", "mes", "dia"]:
        d = rel[[v, "cociente"]].replace([np.inf, -np.inf], np.nan).dropna()
        r_, p_ = stats.spearmanr(d[v], d["cociente"])
        obj.append({"variable": {"c1": "t-1 / base", "c7": "t-7 / base"}.get(v, v),
                    "rho con el cociente afluencia/base": r_, "p": p_})
    tabla_md(pd.DataFrame(obj), "reduccion_relacion_objetivo", cfg)

    # --- PCA (1): variables numéricas del día (clima), estandarizadas con entrenamiento
    dias = (a[["fecha", "particion", "precipitacion_mm", "lluvia_mm", "temp_max_c", "temp_min_c"]]
            .drop_duplicates("fecha"))
    clima_vars = ["precipitacion_mm", "lluvia_mm", "temp_max_c", "temp_min_c"]
    dtr = dias[dias["particion"] == "entrenamiento"][clima_vars]
    esc = StandardScaler().fit(dtr)
    pca = PCA().fit(esc.transform(dtr))
    var_pca = pd.DataFrame({"componente": [f"CP{i + 1}" for i in range(len(clima_vars))],
                            "varianza explicada": pca.explained_variance_ratio_,
                            "acumulada": np.cumsum(pca.explained_variance_ratio_)})
    cargas = pd.DataFrame(pca.components_.T, index=clima_vars,
                          columns=[f"CP{i + 1}" for i in range(len(clima_vars))]).round(3)
    tabla_md(var_pca, "reduccion_pca_clima_varianza", cfg)
    tabla_md(cargas.reset_index().rename(columns={"index": "variable"}), "reduccion_pca_clima_cargas", cfg)
    k_clima = int(np.searchsorted(np.cumsum(pca.explained_variance_ratio_), rc["varianza_pca"]) + 1)

    # --- PCA (2): perfil semanal de las estaciones (entrada del clustering de P3)
    perfil = (tr[~tr["es_registro_cero"]].groupby(["linea_codigo", "estacion", "dia_semana_num"])["afluencia"]
              .mean().unstack())
    part = perfil.div(perfil.sum(axis=1), axis=0)
    esc2 = StandardScaler().fit(part)
    pca2 = PCA().fit(esc2.transform(part))
    var_pca2 = pd.DataFrame({"componente": [f"CP{i + 1}" for i in range(7)],
                             "varianza explicada": pca2.explained_variance_ratio_,
                             "acumulada": np.cumsum(pca2.explained_variance_ratio_)})
    cargas2 = pd.DataFrame(pca2.components_[:3].T, index=["lun", "mar", "mié", "jue", "vie", "sáb", "dom"],
                           columns=["CP1", "CP2", "CP3"]).round(3)
    tabla_md(var_pca2, "reduccion_pca_perfil_varianza", cfg)
    tabla_md(cargas2.reset_index().rename(columns={"index": "día"}), "reduccion_pca_perfil_cargas", cfg)
    k_perfil = int(np.searchsorted(np.cumsum(pca2.explained_variance_ratio_), rc["varianza_pca"]) + 1)
    LOG.info("  PCA clima: %d componentes para %.0f %%; PCA perfil semanal: %d componentes",
             k_clima, 100 * rc["varianza_pca"], k_perfil)

    # --- Tabla de decisión por variable
    vchi = chi.set_index("variable")["V de Cramér"]
    r = rho

    def v(x):
        return f"V = {vchi[x]:.3f}"

    def p_(x, y):
        return f"ρ({x}, {y}) = {r.loc[x, y]:.2f}"

    robj = pd.DataFrame(obj).set_index("variable")["rho con el cociente afluencia/base"]
    nombres_rel = {"c1": "t-1 / base", "c7": "t-7 / base"}

    def rr(x):
        return f"ρ({nombres_rel.get(x, x)}, cociente) = {robj[nombres_rel.get(x, x)]:.3f}"

    def pajd(x):
        return float(chi.set_index("variable").loc[x, "p ajustada (Bonferroni)"])

    decisiones = [
        ("fecha", "fecha", "—", "Conservar (llave)", "Llave temporal del grano; de ella se derivan las variables de calendario."),
        ("anio", "numérica discreta", "correlación", "Conservar", f"{p_('anio', 'afluencia')}; no es redundante con ninguna otra y marca el régimen posterior a la pandemia (riesgo R5)."),
        ("mes", "categórica ordinal", "χ² + correlación", "Conservar", f"{v('mes')}: única variable que pasa los dos umbrales (p ajustada < {rc['alfa']} y V ≥ {rc['v_cramer_min']}). {p_('mes', 'semana_iso')}: de la pareja se queda mes, más interpretable."),
        ("semana_iso", "numérica discreta", "correlación", "Descartar", f"{p_('mes', 'semana_iso')} ≥ {rc['rho_redundancia']}: redundante con mes."),
        ("dia (del mes)", "numérica discreta", "correlación", "Transformar", f"{rr('dia')} con el cociente contra la base: sin relación útil como número; su único efecto esperado (pago de quincena) ya está en es_dia_quincena."),
        ("nombre_mes, nombre_dia", "texto", "no aplica (etiqueta)", "Conservar en el DW (descriptiva)", "Etiquetas para reportes; repiten mes y dia_semana_num, no entran al modelo."),
        ("dia_semana_num", "categórica (7)", "χ² + PCA del perfil", "Conservar (dominio)", f"{v('dia_semana_num')} < {rc['v_cramer_min']}, pero la etiqueta ya compara contra el mismo día de la semana, así que su efecto queda absorbido por construcción. Es el eje de la línea base, de P1 y del perfil semanal de P3."),
        ("es_fin_de_semana", "binaria", "χ²", "Combinar", f"{v('es_fin_de_semana')}; se deriva de dia_semana_num sin pérdida."),
        ("es_dia_quincena", "binaria", "χ²", "Conservar (dominio)", f"{v('es_dia_quincena')}; efecto pequeño, pero la quincena es variable de calendario pedida en P2 desde E0."),
        ("es_festivo_oficial, nombre_festivo", "binaria / texto", "χ²", "Conservar (dominio)", f"{v('es_festivo_oficial')}; poco frecuente (119 días), pero es la causa que más anomalías explica en P4."),
        ("es_semana_santa", "binaria", "χ²", "Conservar (dominio)", f"{v('es_semana_santa')}; causa conocida de caídas de demanda (P4)."),
        ("evento_masivo", "categórica (6)", "χ²", "Conservar (dominio)", f"{v('evento_masivo')}; nueva en E2 por la retroalimentación de E1; explica cierres puntuales y picos (P4)."),
        ("es_dia_sismo, sismo_magnitud_max", "binaria / numérica", "χ² + correlación", "Descartar como predictor; conservar en el DW", f"χ² no significativo (p ajustada = {pajd('sismo'):.2f}, {v('sismo')}) y {rr('sismo_magnitud_max')}: un sismo no cambia la demanda del día. Se queda en dim_fecha como causa candidata de P4 (retroalimentación de E1)."),
        ("es_dia_sin_medicion", "binaria", "no aplica (filtro)", "Conservar en el DW", "Marca los 10 días sin conteo; dentro del dataset analítico vale siempre falso."),
        ("linea_codigo", "categórica (12)", "χ²", "Conservar (dominio)", f"{v('linea_codigo')}; es la dimensión de P1, P3 y P5."),
        ("estacion_nk, nombre_oficial, nombre_en_fuente, gtfs_stop_id", "identificadores", "no aplica (llave)", "Conservar (llave / descriptiva)", "Identifican la unidad de análisis; no son predictores."),
        ("sistema, nombre_linea, terminales, color_hex, gtfs_route_id", "texto (dim_linea)", "no aplica (etiqueta)", "Conservar en el DW (descriptiva)", "Atributos de la línea para reportes y para cruzar Metro con Metrobús (P3, P5); no son predictores."),
        ("llaves sustitutas y metadatos (fecha_key, estacion_key, vigencias, es_version_vigente, fecha_descarga)", "llaves", "no aplica", "Conservar en el DW", "Estructura del esquema estrella y de la SCD tipo 2; no son variables de análisis."),
        ("latitud, longitud", "numéricas", "correlación", "Conservar", f"{p_('latitud', 'afluencia')}; no son redundantes y dan la cercanía Metro ↔ Metrobús de P3."),
        ("es_correspondencia", "binaria", "χ²", "Combinar", f"{v('es_correspondencia')}; es un atributo fijo de cada estación, así que en un modelo por estación ya está implícito. Se queda en dim_estacion para describir P1 y P3."),
        ("estado_servicio", "categórica (3)", "no aplica (filtro)", "Conservar en el DW", "Decide qué días entran al entrenamiento (solo 'operando', riesgo R3); dentro del dataset es constante."),
        ("precipitacion_mm", "numérica", "correlación + PCA", "Conservar (dominio)", f"{rr('precipitacion_mm')}: relación débil (Fig. 10, resultado negativo), pero es la hipótesis de clima de P2 y una causa candidata de P4; E3 medirá si aporta."),
        ("lluvia_mm", "numérica", "correlación + PCA", "Descartar", f"{p_('precipitacion_mm', 'lluvia_mm')}: idéntica a la precipitación los 6,056 días (CP4 del PCA con varianza 0). Se quita también del DW."),
        ("categoria_lluvia", "categórica (4)", "χ²", "Conservar (dominio)", f"{v('categoria_lluvia')}; versión discreta de la precipitación para atribuir anomalías en P4."),
        ("temp_max_c, temp_min_c", "numéricas", "χ² (cuartiles) + correlación + PCA", "Descartar como predictor; conservar en el DW", f"{v('temp_max_cuartil')}, {rr('temp_max_c')} y {rr('temp_min_c')}: efecto mínimo y ninguna pregunta de E0 lo pide. No son redundantes entre sí ({p_('temp_max_c', 'temp_min_c')}), por eso quedan en dim_clima como contexto de los días anómalos (P4)."),
        ("afluencia", "numérica (objetivo)", "—", "Conservar (medida)", "Medida del hecho y objetivo de la regresión de P2."),
        ("afluencia_t_menos_1", "numérica", "correlación", "Conservar", f"{rr('c1')}; es el dato más reciente disponible a las 20:00 h de la víspera. {p_('afluencia_t_menos_1', 'base_ingenua_4sem')} < {rc['rho_redundancia']}: no es redundante con la base."),
        ("afluencia_t_menos_7", "numérica", "correlación", "Combinar", f"{p_('afluencia_t_menos_7', 'base_ingenua_4sem')} ≥ {rc['rho_redundancia']}: redundante; ya es uno de los 4 valores que promedia la base."),
        ("base_ingenua_4sem", "numérica", "correlación", "Conservar", "Línea base obligatoria del criterio de éxito de E0; define la etiqueta de alta demanda."),
        ("es_alta_demanda", "binaria (objetivo)", "—", "Conservar (objetivo)", f"Etiqueta de la clasificación de P2 (umbral {cfg['alta_demanda']['umbral_vs_base']} × base, Fig. 13)."),
        ("es_registro_cero", "binaria", "no aplica (medida no aditiva)", "Conservar en el DW", "Separa cierres de un día (P4)."),
        ("es_atipico", "binaria", "χ²", "Descartar como predictor (fuga); conservar en el DW", f"{v('es_atipico')}. Se calcula con semanas posteriores al día (ventana centrada): usarla para pronosticar filtraría el futuro. En el DW sirve para describir P4."),
        ("perfil semanal (7 participaciones por estación)", "numéricas derivadas", "PCA", "Conservar originales", f"CP1 explica {var_pca2['varianza explicada'].iloc[0]:.0%} (entre semana vs. fin de semana) y CP1+CP2 {var_pca2['acumulada'].iloc[1]:.0%}; {k_perfil} componentes alcanzan {rc['varianza_pca']:.0%}. Para el clustering de P3 (E3) se probarán las 7 participaciones y las 2 componentes."),
        ("clima (4 numéricas)", "numéricas", "PCA", "Conservar originales", f"{k_clima} componentes alcanzan {rc['varianza_pca']:.0%}; al quitar lluvia_mm quedan 3 variables, así que las componentes no ahorran casi nada y se pierde la interpretación."),
    ]
    tabla_decision = pd.DataFrame(decisiones, columns=["variable", "tipo", "técnica(s)", "decisión", "justificación"])
    tabla_md(tabla_decision, "reduccion_decision_por_variable", cfg, csv=True)

    if figuras:
        _figuras(cfg, rho, var_pca, cargas, var_pca2, cargas2, part)

    reg.fin("reduccion", len(limpio["metro"]), len(a),
            f"dataset analítico 2022+ en operación: {len(a):,} filas × {a.shape[1]} columnas")
    return a


def _figuras(cfg, rho, var_pca, cargas, var_pca2, cargas2, part):
    plt = G.plt
    fig, ax = G.figura(8.5, 7)
    im = ax.imshow(rho.values, cmap="RdBu_r", vmin=-1, vmax=1)
    ax.set_xticks(range(len(rho))); ax.set_xticklabels(rho.columns, rotation=60, ha="right", fontsize=8)
    ax.set_yticks(range(len(rho))); ax.set_yticklabels(rho.index, fontsize=8); ax.grid(False)
    for i in range(len(rho)):
        for j in range(len(rho)):
            ax.text(j, i, f"{rho.values[i, j]:.2f}", ha="center", va="center", fontsize=6,
                    color="white" if abs(rho.values[i, j]) > 0.6 else "black")
    fig.colorbar(im, ax=ax, label="ρ de Spearman", shrink=0.8)
    ax.set_title("Fig. 15 · Correlación de Spearman entre variables numéricas (entrenamiento 2022-2024)")
    guardar_figura(fig, "fig15_spearman", cfg)

    fig, axs = plt.subplots(1, 3, figsize=(12, 3.8))
    axs[0].bar(var_pca["componente"], var_pca["varianza explicada"], color=G.COLORES[0], label="por componente")
    axs[0].plot(var_pca["componente"], var_pca["acumulada"], color=G.COLORES[1], marker="o", label="acumulada")
    axs[0].axhline(cfg["reduccion"]["varianza_pca"], color=G.GRIS, ls="--", lw=0.8)
    axs[0].set(title="Clima: sedimentación", ylabel="proporción de varianza"); axs[0].legend(fontsize=8)
    axs[0].yaxis.set_major_formatter(G.pct)
    axs[1].bar(var_pca2["componente"], var_pca2["varianza explicada"], color=G.COLORES[2])
    axs[1].plot(var_pca2["componente"], var_pca2["acumulada"], color=G.COLORES[1], marker="o")
    axs[1].axhline(cfg["reduccion"]["varianza_pca"], color=G.GRIS, ls="--", lw=0.8)
    axs[1].set(title="Perfil semanal: sedimentación", ylabel="proporción de varianza")
    axs[1].yaxis.set_major_formatter(G.pct)
    x = np.arange(7)
    axs[2].bar(x - 0.2, cargas2["CP1"], width=0.4, color=G.COLORES[2], label="CP1")
    axs[2].bar(x + 0.2, cargas2["CP2"], width=0.4, color=G.COLORES[3], label="CP2", hatch="//")
    axs[2].set_xticks(x); axs[2].set_xticklabels(cargas2.index)
    axs[2].axhline(0, color=G.TINTA, lw=0.6)
    axs[2].set(title="Perfil semanal: cargas", ylabel="carga"); axs[2].legend(fontsize=8)
    fig.suptitle("Fig. 16 · PCA ajustado solo con entrenamiento (2022-2024)", x=0.01, ha="left", fontweight="bold")
    fig.tight_layout()
    guardar_figura(fig, "fig16_pca", cfg)
