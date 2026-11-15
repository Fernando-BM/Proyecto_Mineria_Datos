"""PASO 3 · LIMPIEZA. Trata el ruido detectado en el diagnóstico.

Nada se elimina ni se imputa en silencio: cada tratamiento llama a
`registro.limpiar(...)` con su conteo y su justificación, y el registro
completo se publica en tablas/registro_limpieza.md.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from .utiles import LOG, clave_texto, reparar_codificacion, slug

MESES = {"Enero": 1, "Febrero": 2, "Marzo": 3, "Abril": 4, "Mayo": 5, "Junio": 6,
         "Julio": 7, "Agosto": 8, "Septiembre": 9, "Octubre": 10, "Noviembre": 11,
         "Diciembre": 12}
ORDEN_METRO = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "A", "B", "12"]


# =====================================================================
# Calendario: festivos (LFT), Semana Santa, sismos y eventos recurrentes
# =====================================================================
def _n_lunes(anio: int, mes: int, n: int) -> pd.Timestamp:
    d = pd.Timestamp(anio, mes, 1)
    primer_lunes = d + pd.Timedelta(days=(7 - d.weekday()) % 7)
    return primer_lunes + pd.Timedelta(weeks=n - 1)


def festivos_lft(anios, transmision: list[str]) -> dict:
    """Días de descanso obligatorio del art. 74 de la Ley Federal del Trabajo."""
    dias = {}
    for a in anios:
        dias[pd.Timestamp(a, 1, 1)] = "Año Nuevo"
        dias[_n_lunes(a, 2, 1)] = "Día de la Constitución"
        dias[_n_lunes(a, 3, 3)] = "Natalicio de Benito Juárez"
        dias[pd.Timestamp(a, 5, 1)] = "Día del Trabajo"
        dias[pd.Timestamp(a, 9, 16)] = "Día de la Independencia"
        dias[_n_lunes(a, 11, 3)] = "Día de la Revolución"
        dias[pd.Timestamp(a, 12, 25)] = "Navidad"
    for f in transmision:
        dias[pd.Timestamp(f)] = "Transmisión del Poder Ejecutivo Federal"
    return dias


def _calendario(cfg: dict, crudos: dict, reg) -> pd.DataFrame:
    ini, fin = pd.Timestamp(cfg["periodo"]["inicio"]), pd.Timestamp(cfg["periodo"]["fin"])
    cal = pd.DataFrame({"fecha": pd.date_range(ini, fin, freq="D")})
    n = len(cal)

    # --- Festivos: la regla legal manda; F4 se usa para validarla.
    lft = festivos_lft(range(ini.year, fin.year + 1), cfg["transmision_poder_ejecutivo"])
    lft = {k: v for k, v in lft.items() if ini <= k <= fin}
    fest = crudos["festivos"].copy()
    fest["fecha"] = pd.to_datetime(fest["date"])
    publicos = fest[fest["types"].str.contains("Public")]
    nager = set(publicos["fecha"]) & set(cal["fecha"])
    solo_nager = sorted(nager - set(lft))
    solo_lft = sorted(set(lft) - nager)
    reg.limpiar("festivos (F4)", "Fecha de festivo desplazada respecto de la ley", "date",
                len(solo_nager), len(publicos),
                "Se usa la fecha del art. 74 de la LFT; F4 solo valida",
                "Nager.Date recorre Año Nuevo y Día del Trabajo cuando caen en fin de semana "
                f"({', '.join(d.strftime('%Y-%m-%d') for d in solo_nager[:6])}…); la ley no prevé ese "
                f"recorrido. Fechas de la ley ausentes en F4: {len(solo_lft)}")
    cal["es_festivo_oficial"] = cal["fecha"].isin(lft.keys())
    cal["nombre_festivo"] = cal["fecha"].map(lft)

    santa = fest[fest["localName"].isin(["Jueves Santo", "Viernes Santo"])]["fecha"]
    cal["es_semana_santa"] = cal["fecha"].isin(set(santa))

    # --- Sismos (F6, USGS): fecha local de la Ciudad de México.
    s = crudos["sismos"].copy()
    s["mag"] = pd.to_numeric(s["mag"], errors="coerce")
    s["t"] = pd.to_datetime(s["time"], utc=True).dt.tz_convert(cfg["sismos"]["zona_horaria"])
    s["fecha"] = s["t"].dt.tz_localize(None).dt.normalize()
    s = s[s["mag"] >= cfg["sismos"]["magnitud_min"]]
    dif_dia = (s["t"].dt.tz_convert("UTC").dt.tz_localize(None).dt.normalize() != s["fecha"]).sum()
    reg.limpiar("sismos (F6)", "Hora en UTC: el día local puede ser el anterior", "time",
                int(dif_dia), len(s), "Convertir a hora de la Ciudad de México antes de tomar la fecha",
                "Un sismo de madrugada en UTC ocurrió la noche previa en la CDMX "
                "(p. ej. el de Chiapas de 2017: 2017-09-08 04:49 UTC = 2017-09-07 23:49 local)")
    por_dia = s.groupby("fecha")["mag"].max()
    cal["sismo_magnitud_max"] = cal["fecha"].map(por_dia)
    cal["es_dia_sismo"] = cal["sismo_magnitud_max"].notna()

    # --- Eventos masivos recurrentes (retroalimentación de E1).
    ev = cfg["eventos_recurrentes"]
    cal["evento_masivo"] = cal["fecha"].dt.strftime("%m-%d").map(ev)
    LOG.info("  calendario: %d días, %d festivos LFT, %d días con sismo, %d días con evento",
             n, cal["es_festivo_oficial"].sum(), cal["es_dia_sismo"].sum(),
             cal["evento_masivo"].notna().sum())
    return cal


# =====================================================================
# Clima (F5)
# =====================================================================
def categoria_lluvia(mm: pd.Series, umbrales: dict) -> pd.Series:
    return pd.cut(mm, [-np.inf, umbrales["ligera"], umbrales["moderada"], umbrales["fuerte"], np.inf],
                  right=False, labels=["sin_lluvia", "ligera", "moderada", "fuerte"]).astype(str)


def _clima(cfg: dict, raw: pd.DataFrame, reg) -> pd.DataFrame:
    c = pd.DataFrame({
        "fecha": pd.to_datetime(raw["time"]),
        "precipitacion_mm": pd.to_numeric(raw["precipitation_sum_mm"], errors="coerce"),
        "lluvia_mm": pd.to_numeric(raw["rain_sum_mm"], errors="coerce"),
        "temp_max_c": pd.to_numeric(raw["temperature_2m_max_c"], errors="coerce"),
        "temp_min_c": pd.to_numeric(raw["temperature_2m_min_c"], errors="coerce"),
    })
    n = len(c)
    nulos = int(c.isna().any(axis=1).sum())
    reg.limpiar("clima (F5)", "Valores faltantes", "todas", nulos, n,
                "Ninguna acción" if nulos == 0 else "Dejar NULL",
                "La API entrega un registro por día sin huecos en 2010-2026")
    fuera = int(((c.precipitacion_mm < 0) | (c.temp_min_c > c.temp_max_c) |
                 (c.temp_max_c > 45) | (c.temp_min_c < -15)).sum())
    reg.limpiar("clima (F5)", "Valores fuera de rango físico", "precipitación y temperaturas", fuera, n,
                "Ninguna acción" if fuera == 0 else "Marcar NULL",
                "Precipitación >= 0, mínima <= máxima y temperaturas entre -15 y 45 °C")
    iguales = int((c.precipitacion_mm == c.lluvia_mm).sum())
    reg.limpiar("clima (F5)", "Variable duplicada", "lluvia_mm", iguales, n,
                "Se pasa a la tabla de reducción (redundante con precipitacion_mm)",
                "En la CDMX no nieva: la lluvia es igual a la precipitación total en todos los días")
    c["categoria_lluvia"] = categoria_lluvia(c["precipitacion_mm"], cfg["lluvia_mm"])
    return c


# =====================================================================
# GTFS (F3): catálogo de estaciones y líneas
# =====================================================================
def _gtfs(cfg: dict, crudos: dict, reg) -> tuple[pd.DataFrame, pd.DataFrame]:
    st = crudos["gtfs_stops"]
    m = st[st["stop_id"].str.startswith("B_02")].copy()
    m["linea_codigo"] = m["stop_id"].str.extract(r"^B_02\d*L([0-9AB]+)[-_]")[0]
    mal = m["stop_id"].str.contains(r"^B_02\d*L[0-9AB]+_", regex=True)
    reg.limpiar("gtfs (F3)", "Identificador con formato distinto", "stop_id", int(mal.sum()), len(m),
                "Leer la línea con una expresión que acepta '-' o '_'",
                f"{', '.join(m.loc[mal, 'stop_id'])} usa '_' en lugar de '-'")
    m["nombre_oficial"] = m["stop_name"].str.replace(r"\s+", " ", regex=True).str.strip()
    m["latitud"] = pd.to_numeric(m["stop_lat"])
    m["longitud"] = pd.to_numeric(m["stop_lon"])
    m["clave"] = m["nombre_oficial"].map(clave_texto)
    est = m[["stop_id", "linea_codigo", "nombre_oficial", "clave", "latitud", "longitud"]]

    r = crudos["gtfs_routes"]
    filas = []
    metro = r[(r["agency_id"] == "METRO")]
    for _, x in metro.iterrows():
        cod = x["route_short_name"].replace("L", "")
        filas.append(("Metro", cod, x["route_long_name"], x["route_color"], x["route_id"]))
    mb = r[(r["agency_id"] == "MB") & r["route_short_name"].str.fullmatch(r"\d")]
    for _, x in mb.iterrows():
        filas.append(("Metrobús", x["route_short_name"], x["route_long_name"], x["route_color"],
                      x["route_id"]))
    lin = pd.DataFrame(filas, columns=["sistema", "linea_codigo", "terminales", "color_hex",
                                       "gtfs_route_id"])
    lin["color_hex"] = lin["color_hex"].replace("", np.nan)
    return est, lin


# =====================================================================
# Metro (F1)
# =====================================================================
def _metro(cfg: dict, raw: pd.DataFrame, gtfs: pd.DataFrame, reg) -> tuple[pd.DataFrame, pd.DataFrame]:
    lim = cfg["limpieza"]
    n = len(raw)
    df = pd.DataFrame({"fecha": pd.to_datetime(raw["fecha"], format="%Y-%m-%d", errors="coerce")})

    # --- Tipos y rangos
    afl = pd.to_numeric(raw["afluencia"], errors="coerce")
    reg.limpiar("metro (F1)", "Tipos: fecha o afluencia no convertibles", "fecha, afluencia",
                int(df["fecha"].isna().sum() + afl.isna().sum()), n,
                "Ninguna acción", "Todas las fechas son ISO válidas y todas las afluencias son enteros")
    reg.limpiar("metro (F1)", "Afluencia negativa", "afluencia", int((afl < 0).sum()), n,
                "Ninguna acción", "No hay valores negativos")
    incons = ((pd.to_numeric(raw["anio"], errors="coerce") != df["fecha"].dt.year) |
              (raw["mes"].map(MESES) != df["fecha"].dt.month))
    reg.limpiar("metro (F1)", "Columnas redundantes con la fecha", "anio, mes", int(incons.sum()), n,
                "Descartar anio y mes; se derivan de la fecha en dim_fecha",
                "Coinciden con la fecha en todas las filas; mantenerlas duplica información")

    # --- Codificación (UTF-8 leído como Latin-1)
    linea = raw["linea"].map(reparar_codificacion)
    est = raw["estacion"].map(reparar_codificacion)
    reg.limpiar("metro (F1)", "Doble codificación de texto", "linea", int((linea != raw["linea"]).sum()), n,
                "Reparar (latin-1 -> utf-8)", "'LÃ­nea 1' es 'Línea 1' mal leído; no cambia el significado")
    reg.limpiar("metro (F1)", "Doble codificación de texto", "estacion", int((est != raw["estacion"]).sum()), n,
                "Reparar (latin-1 -> utf-8)", "'CatÃ³lica' es 'Católica' mal leído; afecta a toda la serie")

    # --- Categorías: línea y nombre canónico
    df["linea_codigo"] = linea.str.extract(r"(\w+)\s*$")[0].str.upper()
    reg.limpiar("metro (F1)", "Categorías inconsistentes", "linea",
                int(raw["linea"].nunique()), int(raw["linea"].nunique()),
                f"Mapear a código de línea: {raw['linea'].nunique()} textos -> {df['linea_codigo'].nunique()} líneas",
                "'Linea 1', 'Línea 1' y 'LÃ­nea 1' son la misma línea")
    canon = lim["nombres_canonicos"]
    cambia = est.isin(canon.keys())
    reg.limpiar("metro (F1)", "Variantes de escritura de una estación", "estacion", int(cambia.sum()), n,
                "Unificar al nombre canónico", "; ".join(f"'{k}' -> '{v}'" for k, v in canon.items()) +
                " (la fuente cambió la escritura en junio de 2023)")
    df["estacion"] = est.replace(canon)
    df["afluencia"] = afl.astype("int64")

    # --- Duplicados
    exactos = int(df.duplicated().sum())
    reg.limpiar("metro (F1)", "Duplicados exactos", "todas", exactos, n,
                "Ninguna acción" if exactos == 0 else "Eliminar", "No hay filas idénticas")
    llave = ["fecha", "linea_codigo", "estacion"]
    dup = df.duplicated(llave, keep=False)
    d = lim["estacion_duplicada"]
    caso = dup & (df["linea_codigo"] == d["linea"]) & (df["estacion"] == d["nombre_repetido"])
    if (dup & ~caso).any():
        raise AssertionError(f"Duplicados de llave no previstos: {df[dup & ~caso].head()}")
    if caso.any():
        # En cada par repetido, el valor mayor es la estación que falta: en 2019 y
        # oct-nov 2020 Deportivo Oceanía superó a Oceanía en 97-100 % de los días.
        mayor = df[caso].groupby("fecha")["afluencia"].transform("max") == df.loc[caso, "afluencia"]
        idx = mayor[mayor].index
        primero = df.loc[idx].drop_duplicates("fecha").index   # por si ambos valores son iguales
        df.loc[primero, "estacion"] = d["nombre_faltante"]
        reg.limpiar("metro (F1)", "Llave natural duplicada (fecha, línea, estación)", "estacion",
                    int(caso.sum()), n,
                    f"Reasignar el valor mayor de cada par a '{d['nombre_faltante']}'",
                    f"En {df.loc[caso, 'fecha'].dt.strftime('%Y-%m').unique().tolist()} la línea "
                    f"{d['linea']} trae '{d['nombre_repetido']}' dos veces y le falta "
                    f"'{d['nombre_faltante']}'. En los meses vecinos esta supera a la otra en 97-100 % "
                    "de los días")
    assert not df.duplicated(llave).any(), "el grano estación-línea-día no es único"
    por_dia = df.groupby("fecha").size()
    assert (por_dia == cfg["esperado"]["estaciones_linea"]).all(), \
        "no todos los días tienen 195 estaciones-línea"

    # --- Llaves con F3 (GTFS)
    df["clave"] = df["estacion"].map(clave_texto)
    cat = df[["linea_codigo", "estacion", "clave"]].drop_duplicates()
    cat = cat.merge(gtfs[["linea_codigo", "clave", "stop_id", "nombre_oficial", "latitud", "longitud"]],
                    on=["linea_codigo", "clave"], how="left")
    auto = int(cat["stop_id"].notna().sum())
    eq = lim["equivalencias_gtfs"]
    faltan = cat["stop_id"].isna()
    llave_eq = cat["linea_codigo"] + "|" + cat["estacion"]
    cat.loc[faltan, "stop_id"] = llave_eq[faltan].map(eq)
    g = gtfs.set_index("stop_id")
    for c in ["nombre_oficial", "latitud", "longitud"]:
        cat.loc[faltan, c] = cat.loc[faltan, "stop_id"].map(g[c])
    sin_par = int(cat["stop_id"].isna().sum())
    reg.limpiar("metro (F1) × gtfs (F3)", "Llaves que no coinciden al unir", "estacion",
                len(cat) - auto, len(cat),
                f"Tabla de equivalencias ({len(eq)} nombres compuestos); quedan {sin_par} sin pareja",
                f"{auto} de {len(cat)} unen por nombre normalizado; los otros se escriben distinto "
                "(p. ej. 'Garibaldi/Lagunilla' vs 'Garibaldi y Lagunilla')")
    assert sin_par == 0, "hay estaciones sin coordenadas de GTFS"

    # --- Días sin medición: la red completa registra < umbral de su nivel habitual
    df = df.sort_values(["linea_codigo", "estacion", "fecha"]).reset_index(drop=True)
    df["es_registro_cero"] = df["afluencia"] == 0
    total_ceros = int(df["es_registro_cero"].sum())
    red = df.groupby("fecha")["afluencia"].sum().to_frame("total")
    red["dow"] = red.index.dayofweek
    red["base"] = red.groupby("dow")["total"].transform(lambda s: s.shift(1).rolling(4, min_periods=1).median())
    red["cociente"] = red["total"] / red["base"]
    dias_sin = red.index[red["cociente"] < lim["umbral_sin_medicion"]]
    sin_med = df["fecha"].isin(dias_sin)
    df["tipo_cero"] = np.where(sin_med, "sin_medicion", "")
    txt_dias = ", ".join(f"{d:%Y-%m-%d} ({red.loc[d, 'cociente']:.0%})" for d in dias_sin)
    reg.limpiar("metro (F1)", f"Días en que toda la red registra menos del "
                f"{lim['umbral_sin_medicion']:.0%} de su nivel habitual", "afluencia",
                int(sin_med.sum()), n,
                "Dejar afluencia NULL (no medida) en esos días y marcarlos en dim_fecha",
                f"{len(dias_sin)} días: {txt_dias}. Coinciden con la gratuidad del transporte por la "
                "contingencia ambiental de marzo de 2016 y tras el sismo del 19-S de 2017: los "
                "torniquetes no contaron. No es demanda cero ni casi cero")

    primera = df[~df["es_registro_cero"] & ~sin_med].groupby(["linea_codigo", "estacion"])["fecha"].min()
    df["_primera"] = pd.MultiIndex.from_frame(df[["linea_codigo", "estacion"]]).map(primera)
    no_inaug = df["es_registro_cero"] & (df["fecha"] < df["_primera"]) & ~sin_med
    df.loc[no_inaug, "tipo_cero"] = "no_inaugurada"

    resto = df["es_registro_cero"] & ~sin_med & ~no_inaug
    validos = df[~sin_med & ~no_inaug].copy()
    validos["_racha"] = (validos["es_registro_cero"] !=
                         validos.groupby(["linea_codigo", "estacion"])["es_registro_cero"].shift()).cumsum()
    validos["_largo"] = validos.groupby("_racha")["afluencia"].transform("size")
    largo = validos["_largo"].reindex(df.index)
    cierre = resto & (largo >= lim["min_dias_cierre"])
    puntual = resto & (largo < lim["min_dias_cierre"])
    df.loc[cierre, "tipo_cero"] = "cierre"
    df.loc[puntual, "tipo_cero"] = "puntual"
    reg.limpiar("metro (F1)", "Ceros antes de la inauguración", "afluencia", int(no_inaug.sum()), n,
                "Conservar 0; estado_servicio = no_inaugurada (versión SCD2)",
                "Ceros estructurales: la Línea 12 abrió en octubre de 2012 y la serie empieza en 2010")
    reg.limpiar("metro (F1)", f"Rachas de ceros de {lim['min_dias_cierre']} días o más", "afluencia",
                int(cierre.sum()), n, "Conservar 0; estado_servicio = cerrada (versión SCD2)",
                "Cierres reales (L12 2014-2015 y 2021-2024, L1 2022-2025, pandemia 2020, incendio "
                "del PCC 2021, L9 2023-2024…). Se excluyen del entrenamiento, no se imputan")
    reg.limpiar("metro (F1)", f"Ceros aislados (menos de {lim['min_dias_cierre']} días)", "afluencia",
                int(puntual.sum()), n, "Conservar 0 con es_registro_cero = TRUE",
                "Cierres de un día por marchas o eventos (p. ej. Zócalo en varios 8 de marzo): son el "
                "fenómeno que estudia P4, no un error")
    ceros_sin_med = int((df["es_registro_cero"] & sin_med).sum())
    assert ceros_sin_med + int(no_inaug.sum() + cierre.sum() + puntual.sum()) == total_ceros
    df.loc[sin_med, "afluencia"] = np.nan
    df["afluencia"] = df["afluencia"].astype("Int64")

    # --- Estado de servicio diario (base de la SCD tipo 2). En los días sin
    #     medición se hereda el estado del día anterior de la misma estación.
    df["estado_servicio"] = np.select([df["tipo_cero"] == "no_inaugurada", df["tipo_cero"] == "cierre"],
                                      ["no_inaugurada", "cerrada"], "operando")
    df.loc[sin_med, "estado_servicio"] = np.nan
    df["estado_servicio"] = (df.groupby(["linea_codigo", "estacion"])["estado_servicio"].ffill()
                             .fillna("operando"))

    # --- Atípicos: z robusto contra la mediana móvil del mismo día de la semana
    df["dia_semana"] = df["fecha"].dt.dayofweek
    op = df["estado_servicio"].eq("operando") & df["afluencia"].notna()
    x = df.loc[op, ["linea_codigo", "estacion", "dia_semana", "fecha", "afluencia"]].copy()
    x["afluencia"] = x["afluencia"].astype(float)
    x = x.sort_values(["linea_codigo", "estacion", "dia_semana", "fecha"])
    w = lim["ventana_semanas"]
    g = x.groupby(["linea_codigo", "estacion", "dia_semana"])["afluencia"]
    x["_med"] = g.transform(lambda s: s.rolling(w, center=True, min_periods=5).median())
    x["_dev"] = (x["afluencia"] - x["_med"]).abs()
    x["_mad"] = x.groupby(["linea_codigo", "estacion", "dia_semana"])["_dev"].transform(
        lambda s: s.rolling(w, center=True, min_periods=5).median())
    x["_mad"] = np.maximum(x["_mad"], lim["mad_minimo_relativo"] * x["_med"])
    x["z_robusto"] = 0.6745 * (x["afluencia"] - x["_med"]) / x["_mad"].replace(0, np.nan)
    df["z_robusto"] = x["z_robusto"].reindex(df.index)
    df["es_atipico"] = df["z_robusto"].abs() >= lim["z_robusto_atipico"]
    altos = int((df["z_robusto"] >= lim["z_robusto_atipico"]).sum())
    bajos = int((df["z_robusto"] <= -lim["z_robusto_atipico"]).sum())
    reg.limpiar("metro (F1)", f"Atípicos (|z robusto| >= {lim['z_robusto_atipico']})", "afluencia",
                altos + bajos, int(op.sum()),
                "Conservar el valor y marcar es_atipico = TRUE",
                f"{altos:,} altos y {bajos:,} bajos frente a las {w} semanas vecinas del mismo día (MAD con piso "
                f"de {lim['mad_minimo_relativo']:.0%} de la mediana local). Son festivos, vacaciones, "
                "peregrinaciones, marchas o cierres parciales: el fenómeno de P4. Eliminarlos borraría "
                "justamente los días que el operador quiere anticipar")

    # --- Catálogo de estaciones
    cat["estacion_nk"] = "L" + cat["linea_codigo"] + "-" + cat["estacion"].map(slug)
    lineas_por_nombre = cat.groupby("clave")["linea_codigo"].transform("nunique")
    cat["es_correspondencia"] = lineas_por_nombre > 1
    cat = cat.rename(columns={"estacion": "nombre_en_fuente", "stop_id": "gtfs_stop_id"})
    cols = ["fecha", "linea_codigo", "estacion", "afluencia", "es_registro_cero", "tipo_cero",
            "estado_servicio", "z_robusto", "es_atipico"]
    return df[cols], cat.drop(columns=["clave"])


# =====================================================================
# Metrobús (F2)
# =====================================================================
def _metrobus(cfg: dict, raw: pd.DataFrame, reg) -> pd.DataFrame:
    n = len(raw)
    b = pd.DataFrame({
        "fecha": pd.to_datetime(raw["fecha"], format="%Y-%m-%d"),
        "linea_codigo": raw["linea"].map(reparar_codificacion).str.extract(r"(\d+)\s*$")[0],
        "afluencia": pd.to_numeric(raw["afluencia"], errors="coerce"),
    })
    reg.limpiar("metrobús (F2)", "Categorías inconsistentes", "linea", int(raw["linea"].nunique()),
                int(raw["linea"].nunique()),
                f"Mapear a código: {raw['linea'].nunique()} textos -> {b['linea_codigo'].nunique()} líneas",
                "'Línea 1' y 'linea 1' son la misma línea")
    ini = pd.Timestamp(cfg["periodo"]["inicio"])
    antes = b["fecha"] < ini
    reg.limpiar("metrobús (F2)", "Fuera del periodo común", "fecha", int(antes.sum()), n,
                f"Excluir días anteriores a {cfg['periodo']['inicio']}",
                "Metro, clima y dim_fecha empiezan en 2010; P3 y P5 solo comparan días en común. "
                "Incluye el primer día de la serie (2005-07-26), que trae 3 millones en una línea")
    b = b[~antes].copy()
    nan = b["afluencia"].isna()
    primera = b[~nan].groupby("linea_codigo")["fecha"].min()
    pre = nan & (b["fecha"] < b["linea_codigo"].map(primera))
    assert pre.sum() == nan.sum(), "hay 'NaN' después de la inauguración de una línea"
    reg.limpiar("metrobús (F2)", "Texto 'NaN' antes de inaugurar la línea", "afluencia", int(pre.sum()),
                len(b), "Excluir la fila (la línea no existía)",
                "Ausencia estructural, no un dato perdido: todos los 'NaN' son anteriores al primer valor "
                "de su línea. Imputarlos inventaría demanda")
    b = b[~pre].copy()
    med = b.groupby("linea_codigo")["afluencia"].transform("median")
    imposible = b["afluencia"] < cfg["limpieza"]["metrobus_min_vs_mediana"] * med
    reg.limpiar("metrobús (F2)", "Valor imposible en día de servicio", "afluencia", int(imposible.sum()),
                len(b), "Dejar NULL (no imputar)",
                "; ".join(f"{r.fecha:%Y-%m-%d} línea {r.linea_codigo}: {int(r.afluencia)} entradas"
                          for r in b[imposible].itertuples()) + " frente a una mediana de ~100 mil")
    b.loc[imposible, "afluencia"] = np.nan
    assert not b.duplicated(["fecha", "linea_codigo"]).any()
    b["afluencia"] = b["afluencia"].round().astype("Int64")
    return b.sort_values(["linea_codigo", "fecha"]).reset_index(drop=True)


# =====================================================================
def ejecutar(cfg: dict, crudos: dict, reg) -> dict:
    reg.inicio("limpieza")
    entrada = sum(len(v) for v in crudos.values())
    cal = _calendario(cfg, crudos, reg)
    clima = _clima(cfg, crudos["clima"], reg)
    gtfs, lineas = _gtfs(cfg, crudos, reg)
    metro, estaciones = _metro(cfg, crudos["metro"], gtfs, reg)
    metrobus = _metrobus(cfg, crudos["metrobus"], reg)

    sin_med = set(metro.loc[metro["tipo_cero"] == "sin_medicion", "fecha"])
    cal["es_dia_sin_medicion"] = cal["fecha"].isin(sin_med)

    orden = {c: i for i, c in enumerate(ORDEN_METRO)}
    lineas["_o"] = np.where(lineas["sistema"] == "Metro", lineas["linea_codigo"].map(orden),
                            100 + pd.to_numeric(lineas["linea_codigo"], errors="coerce"))
    lineas = lineas.sort_values("_o").drop(columns="_o").reset_index(drop=True)
    lineas["nombre_linea"] = lineas["sistema"] + " Línea " + lineas["linea_codigo"]
    esperado = cfg["esperado"]
    assert (lineas["sistema"] == "Metro").sum() == esperado["lineas_metro"]
    assert (lineas["sistema"] == "Metrobús").sum() == esperado["lineas_metrobus"]
    assert set(metro["linea_codigo"]) <= set(lineas.loc[lineas.sistema == "Metro", "linea_codigo"])
    assert set(metrobus["linea_codigo"]) <= set(lineas.loc[lineas.sistema == "Metrobús", "linea_codigo"])

    limpio = {"metro": metro, "metrobus": metrobus, "estaciones": estaciones, "lineas": lineas,
              "calendario": cal, "clima": clima}
    salida = sum(len(v) for v in limpio.values())
    reg.fin("limpieza", entrada, salida,
            f"metro {len(metro):,} · metrobús {len(metrobus):,} · estaciones {len(estaciones)}")
    return limpio
